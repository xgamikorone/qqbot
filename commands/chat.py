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
        usage="/聊天 <内容 | /reset | /stop>",
        examples=("/聊天 你好", "/聊天 /reset", "/聊天 /stop"),
        details="/聊天 内容：与 AI 对话（仅管理员启用的频道或群聊）。\n"
        "/聊天 /reset：清除当前会话，不删除备份或供应商记录。\n"
        "/聊天 /stop：取消当前生成。\n"
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
            else:
                await service.reply(
                    key, user_id, text, send, extra_system=extra_system
                )
            return True
        except ChatError as error:
            await reply(str(error))
            return False

    async def after_execute(
        self, message: botpy_message.Message, args: list[str]
    ) -> None:
        """Keeps channel chat bodies out of the shared command records."""
        return
