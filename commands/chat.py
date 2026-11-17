"""Channel and group chat entries sharing one model service."""

import collections.abc

from botpy import message as botpy_message

from chat import service as chat_service
from chat.model_client import ChatError
from database.repositories import chat_repository
from messaging import command_replies
from . import base
from . import help_catalog
from . import text_query

# Groups cannot render Markdown and have no channel-style mention syntax.
GROUP_PROMPT_SUFFIX = (
    "当前对话发生在 QQ 群聊中：回复会作为群消息发送，不能渲染 Markdown，"
    "也不要用频道的提及格式，请使用纯文本并尽量简短，控制在 500 字以内。"
)

_Sender = collections.abc.Callable[[str], collections.abc.Awaitable[object]]
_Reply = collections.abc.Callable[[str], collections.abc.Awaitable[None]]


@base.command("聊天", "chat")
class ChatCommand(base.Command):
    """Runs one chat flow and sends through the scene's native transport."""

    supported_scenes = frozenset({"guild", "group"})
    name = "chat"
    cn_name = "聊天"
    help = help_catalog.CommandHelp(
        title="聊天",
        category="工具",
        summary="与 AI 助手进行个人会话",
        usage="/聊天 <内容 | /reset | /stop | 人格 设置/查看/清除>",
        examples=(
            "/聊天 你好",
            "/聊天 /reset",
            "/聊天 /stop",
            "/聊天 人格 设置 像熟悉直播的朋友一样回答，语气轻松",
        ),
        details="/聊天 内容：与 AI 对话（仅管理员启用的频道或群聊）。\n"
        "/聊天 /reset：清除当前对话历史，保留人格设置。不删除备份或供应商记录。\n"
        "/聊天 /stop：取消当前生成。\n"
        "/聊天 人格 设置 <描述>：保存当前群或子频道的人格偏好，最多 500 字符。\n"
        "支持自然语言和【PERSONA_LOAD】标签卡。标签可用反斜杠分隔。\n"
        "/聊天 人格 查看：在当前群或子频道显示你的人格设置，其他人也能看到。\n"
        "/聊天 人格 清除：恢复默认风格。设置和清除会停止当前生成，保留历史。\n"
        "群聊中每位成员各自独立上下文和每日额度。\n"
        "内容会发送到配置的模型供应商，请勿提交敏感信息。普通命令记录不保存聊天正文；"
        "有效历史默认保留 7 天。发送异常的回答最多保留 24 小时供管理员排错，"
        "不进入后续聊天上下文。",
    )

    async def execute(
        self, message: botpy_message.Message, args: list[str]
    ) -> bool:
        """Retains the legacy channel entry point for direct callers."""
        return await self.execute_guild(message, args)

    async def execute_guild(
        self, message: botpy_message.Message, args: list[str]
    ) -> bool:
        """Keeps the existing channel admission and reply transport."""
        service = self._enabled_service()
        if service is None:
            await self.send_reply(message, "聊天功能尚未启用。")
            return False
        if str(message.channel_id) not in service.config.allowed_channel_ids:
            await self.send_reply(message, "此频道尚未开放聊天功能。")
            return False

        async def send(content: str) -> object:
            return await self.client.api.post_message(
                channel_id=message.channel_id,
                msg_id=message.id,
                content=content,
            )

        async def reply(content: str) -> None:
            await self.send_reply(message, content)

        return await self._dispatch(
            service,
            chat_repository.session_key(
                message.guild_id, message.channel_id, message.author.id
            ),
            str(message.author.id),
            args,
            send,
            reply,
            "",
        )

    async def execute_group(
        self, message: botpy_message.GroupMessage, args: list[str]
    ) -> bool:
        """Uses group transport with per-member history and quota."""
        service = self._enabled_service()
        if service is None:
            await self.reply_group(message, "聊天功能尚未启用。")
            return False
        group_id = command_replies.require_id(message.group_openid)
        member_id = command_replies.require_id(message.author.member_openid)
        if group_id not in service.config.allowed_group_ids:
            await self.reply_group(message, "此群尚未开放聊天功能。")
            return False

        async def send(content: str) -> object:
            result: object = None
            for chunk in text_query.split_group_text(content):
                result = await self.client.api.post_group_message(
                    group_openid=group_id,
                    content=chunk,
                    msg_id=message.id,
                    msg_seq=command_replies.next_sequence(message),
                )
                # Stop at the first unconfirmed chunk. The service classifies
                # this response and must never save a partially sent answer.
                if not isinstance(result, dict) or not result.get("id"):
                    return result
            return result

        async def reply(content: str) -> None:
            await self.reply_group(message, content)

        return await self._dispatch(
            service,
            chat_repository.group_session_key(group_id, member_id),
            f"group:{member_id}",
            args,
            send,
            reply,
            GROUP_PROMPT_SUFFIX,
        )

    def _enabled_service(self) -> chat_service.ChatService | None:
        """Returns the shared service only when it is built and enabled."""
        service = getattr(self.client, "chat_service", None)
        if not isinstance(service, chat_service.ChatService):
            return None
        return service if service.config.enabled else None

    async def _dispatch(
        self,
        service: chat_service.ChatService,
        key: str,
        user_id: str,
        args: list[str],
        send: _Sender,
        reply: _Reply,
        extra_system: str,
    ) -> bool:
        """Shares reset, stop and normal-turn handling across both scenes."""
        text = " ".join(args).strip()
        try:
            if text == "/reset":
                await service.reset(key)
                await reply("当前会话已重置。")
            elif text == "/stop":
                await service.stop(key)
                await reply("已停止当前聊天生成。")
            elif args and args[0] == "人格":
                await reply(await self._persona_command(service, key, args[1:]))
            else:
                await service.reply(
                    key, user_id, text, send, extra_system=extra_system
                )
            return True
        except ChatError as error:
            await reply(str(error))
            return False

    async def _persona_command(
        self, service: chat_service.ChatService, key: str, args: list[str]
    ) -> str:
        """Handles persona settings without requesting a model response."""
        if args == ["查看"]:
            preference = service.persona(key)
            if preference:
                return f"当前会话的人格设置\n{preference}"
            return "当前会话使用默认人格。"
        if args == ["清除"]:
            await service.set_persona(key, "")
            return "已清除当前会话的人格设置，恢复默认风格。"
        if args and args[0] == "设置":
            preference = " ".join(args[1:]).strip()
            if preference:
                await service.set_persona(key, preference)
                return "已保存当前会话的人格设置，下次聊天生效。"
        raise ChatError(
            "用法：/聊天 人格 设置 <描述>、人格 查看 或 人格 清除。"
        )

    async def after_execute(
        self, message: botpy_message.Message, args: list[str]
    ) -> None:
        """Keeps channel chat bodies out of the shared command records."""
        return
