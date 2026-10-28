import asyncio
import logging
from .model_client import ChatError

log = logging.getLogger(__name__)

class ChatService:
    def __init__(self, config, repository, model):
        self.config, self.repository, self.model = config, repository, model
        self.tasks = {}
        self.closed = False
        self.slots = asyncio.Semaphore(config.max_concurrent_requests)

    async def reply(self, key, user_id, text, send_reply):
        if self.closed or len(self.tasks) >= self.config.max_pending_requests:
            raise ChatError("聊天请求繁忙，请稍后再试。")
        if key in self.tasks:
            raise ChatError("你的上一条聊天正在处理，可使用 /聊天 /stop 取消。")
        if not text.strip() or len(text) > self.config.max_input_chars:
            raise ChatError(f"请输入 1–{self.config.max_input_chars} 字符的聊天内容。")
        version = self.repository.version(key)
        task = asyncio.create_task(self._run(key, user_id, text, version, send_reply))
        self.tasks[key] = task
        try:
            return await asyncio.wait_for(task, timeout=self.config.request_timeout_seconds)
        except asyncio.TimeoutError:
            raise ChatError("聊天等待或生成超时，请稍后再试。") from None
        except asyncio.CancelledError:
            raise ChatError("本次聊天已取消。") from None
        finally:
            if self.tasks.get(key) is task:
                self.tasks.pop(key, None)

    async def _run(self, key, user_id, text, version, send_reply):
        async with self.slots:
            if not self.repository.reserve(user_id, self.config.daily_requests_per_user):
                raise ChatError("今天的聊天请求额度已用完。")
            pairs = self.repository.history(key, self.config.retention_days)
            budget = self.config.max_context_chars - len(self.config.prompt) - len(text)
            history = []
            for question, answer in reversed(pairs):
                if len(question) + len(answer) > budget:
                    break
                budget -= len(question) + len(answer)
                history[0:0] = [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
            result = await self.model.generate([{"role": "system", "content": self.config.prompt}, *history, {"role": "user", "content": text}])
            if self.repository.version(key) != version:
                raise ChatError("会话已重置，旧回答已丢弃。")
            if len(result.text) > 3500:
                raise ChatError("模型回答过长，未发送，请要求更简短的回答。")
            try:
                response = await send_reply(result.text)
            except Exception:
                raise ChatError("QQ 未能发送回答，本轮不会加入聊天上下文。") from None
            if self.repository.version(key) != version:
                raise ChatError("会话已重置，本轮未保存。")
            if isinstance(response, dict) and response.get("id"):
                status = "sent"
            elif isinstance(response, dict) and response.get("code") == 304023:
                status = "pending"
            else:
                raise ChatError("QQ 未确认回答发送成功，本轮不会加入聊天上下文。")
            try:
                self.repository.append(key, text, result, status)
            except Exception:
                log.error("Chat persistence failed after delivery; not resending")
            return status

    async def stop(self, key):
        task = self.tasks.get(key)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def reset(self, key):
        self.repository.reset(key)
        await self.stop(key)

    async def close(self):
        self.closed = True
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
        await self.model.close()
