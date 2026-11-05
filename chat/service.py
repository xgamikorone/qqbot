import asyncio
from collections.abc import Awaitable, Callable
import logging
import re
from botpy import errors as bot_errors
from .model_client import ChatError
from chat import config as chat_config
from chat import model_client
from database.repositories import chat_repository

log = logging.getLogger(__name__)


class ChatService:

    def __init__(self, config: chat_config.ChatConfig,
                 repository: chat_repository.ChatRepository,
                 model: model_client.ModelClient) -> None:
        self.config, self.repository, self.model = config, repository, model
        self.tasks: dict[str, asyncio.Task[str]] = {}
        self._maintenance: asyncio.Task[None] | None = None
        self.closed = False
        self.slots = asyncio.Semaphore(config.max_concurrent_requests)

    async def reply(
        self,
        key: str,
        user_id: str,
        text: str,
        send_reply: Callable[[str], Awaitable[object]],
    ) -> str:
        """Runs one admitted turn under the appropriate total deadline."""
        if self.closed or len(self.tasks) >= self.config.max_pending_requests:
            raise ChatError("聊天请求繁忙，请稍后再试。")
        if key in self.tasks:
            raise ChatError("你的上一条聊天正在处理，可使用 /聊天 /stop 取消。")
        if not text.strip() or len(text) > self.config.max_input_chars:
            raise ChatError(f"请输入 1–{self.config.max_input_chars} 字符的聊天内容。")
        version = self.repository.version(key)
        task = asyncio.create_task(
            self._run(key, user_id, text, version, send_reply))
        self.tasks[key] = task
        try:
            timeout = (self.config.web_timeout_seconds
                       if self.config.web_enabled else
                       self.config.request_timeout_seconds)
            return await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            raise ChatError("聊天等待或生成超时，请稍后再试。") from None
        except asyncio.CancelledError:
            raise ChatError("本次聊天已取消。") from None
        finally:
            if self.tasks.get(key) is task:
                self.tasks.pop(key, None)

    async def _run(
        self,
        key: str,
        user_id: str,
        text: str,
        version: int,
        send_reply: Callable[[str], Awaitable[object]],
    ) -> str:
        async with self.slots:
            if not self.repository.reserve(user_id,
                                           self.config.daily_requests_per_user):
                raise ChatError("今天的聊天请求额度已用完。")
            pairs = self.repository.history(key, self.config.retention_days)
            budget = self.config.max_context_chars - len(
                self.config.prompt) - len(text)
            history: list[dict[str, str]] = []
            for question, answer in reversed(pairs):
                if len(question) + len(answer) > budget:
                    break
                budget -= len(question) + len(answer)
                history[0:0] = [{
                    "role": "user",
                    "content": question
                }, {
                    "role": "assistant",
                    "content": answer
                }]
            result = await self.model.generate([{
                "role": "system",
                "content": self.config.prompt
            }, *history, {
                "role": "user",
                "content": text
            }])
            if self.repository.version(key) != version:
                raise ChatError("会话已重置，旧回答已丢弃。")
            attempt = None
            try:
                attempt = self.repository.begin_delivery(key, result)
            except Exception:
                log.error(
                    "Chat delivery diagnostics unavailable; no content logged")
            if len(result.text) > 3500:
                self._settle(attempt, "not_sent", "AnswerTooLong")
                raise ChatError("模型回答过长，未发送，请要求更简短的回答。")
            try:
                response = await send_reply(result.text)
            except asyncio.CancelledError:
                self._settle(attempt, "unknown", "CancelledError")
                raise
            except asyncio.TimeoutError:
                self._settle(attempt, "unknown", "TimeoutError")
                raise ChatError("QQ 未确认回答发送结果，本轮不会加入聊天上下文。") from None
            except Exception as error:
                detail = ""
                # Only preserve the SDK's recognized business diagnostic, never
                # arbitrary exception text (which may contain credentials).
                if isinstance(error, bot_errors.ServerError):
                    match = re.match(r"type:business, code:\d+, msg:.*",
                                     str(error))
                    if match:
                        detail = match.group(0)[:1000]
                self._settle(attempt, "failed", type(error).__name__, detail)
                raise ChatError("QQ 未能发送回答，本轮不会加入聊天上下文。") from None
            if self.repository.version(key) != version:
                raise ChatError("会话已重置，本轮未保存。")
            if isinstance(response, dict) and response.get("id"):
                status = "sent"
            elif isinstance(response,
                            dict) and response.get("code") in (304023, 304024):
                status = "pending"
            else:
                self._settle(attempt, "unknown", "UnconfirmedResponse")
                raise ChatError("QQ 未确认回答发送成功，本轮不会加入聊天上下文。")
            self._settle(attempt, status)
            try:
                self.repository.append(key, text, result, status)
            except Exception:
                self._settle(
                    attempt,
                    "sent_unrecorded" if status == "sent" else "pending",
                    "HistoryWriteError")
                log.error(
                    "Chat persistence failed after delivery; not resending")
            else:
                if status == "sent" and attempt is not None:
                    try:
                        self.repository.forget_delivery(attempt)
                    except Exception:
                        log.error("Chat diagnostic cleanup failed; no resend")
            return status

    def _settle(self,
                attempt: int | None,
                status: str,
                error_type: str = "",
                error_text: str = "") -> None:
        if attempt is None:
            return
        try:
            self.repository.finish_delivery(attempt, status, error_type,
                                            error_text)
        except Exception:
            log.error("Chat diagnostic update failed; no content logged")

    async def start(self) -> None:
        """Starts bounded-retention cleanup, including when chat is idle."""
        if self._maintenance is None and not self.closed:
            self._maintenance = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                self.repository.purge_deliveries()
            except Exception:
                log.error("Chat diagnostic retention cleanup failed")
            await asyncio.sleep(60)

    async def delivery_list(self,
                            limit: int = 50
                           ) -> list[chat_repository.DeliveryRecord]:
        """Returns diagnostic metadata to the authenticated admin panel."""
        return self.repository.list_deliveries(limit)

    async def delivery_detail(
            self, record_id: int) -> chat_repository.DeliveryRecord | None:
        """Returns one short-lived answer, never exposing it in guild commands."""
        return self.repository.delivery_detail(record_id)

    async def stop(self, key: str) -> None:
        task = self.tasks.get(key)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def reset(self, key: str) -> None:
        self.repository.reset(key)
        await self.stop(key)

    async def close(self) -> None:
        self.closed = True
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
        if self._maintenance is not None:
            self._maintenance.cancel()
            await asyncio.gather(self._maintenance, return_exceptions=True)
        await self.model.close()
