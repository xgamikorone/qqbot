from .base import Command, command
from .help_catalog import CommandHelp
from chat.model_client import ChatError
from database.repositories.chat_repository import session_key

@command("聊天", "chat")
class ChatCommand(Command):
    name = "chat"
    cn_name = "聊天"
    help = CommandHelp(title="聊天", category="工具", summary="与 AI 助手进行个人会话",
        usage="/聊天 <内容 | /reset | /stop>", examples=("/聊天 你好", "/聊天 /reset", "/聊天 /stop"),
        details="/聊天 内容：与 AI 对话（仅管理员启用的频道）。\n/聊天 /reset：清除当前频道的个人会话，不删除备份或供应商记录。\n/聊天 /stop：取消当前生成。\n内容会发送到配置的模型供应商，请勿提交敏感信息。普通命令记录不保存聊天正文；有效历史默认保留 7 天。")

    async def execute(self, message, args):
        service = getattr(self.client, "chat_service", None)
        if service is None or not service.config.enabled:
            await self.send_reply(message, "聊天功能尚未启用。")
            return False
        if str(message.channel_id) not in service.config.allowed_channel_ids:
            await self.send_reply(message, "此频道尚未开放聊天功能。")
            return False
        text = " ".join(args).strip()
        key = session_key(message.guild_id, message.channel_id, message.author.id)
        try:
            if text == "/reset":
                await service.reset(key)
                await self.send_reply(message, "当前频道的个人聊天会话已重置。")
            elif text == "/stop":
                await service.stop(key)
                await self.send_reply(message, "已停止当前聊天生成。")
            else:
                async def sender(content):
                    return await self.client.api.post_message(channel_id=message.channel_id, msg_id=message.id, content=content)
                await service.reply(key, str(message.author.id), text, sender)
            return True
        except ChatError as error:
            await self.send_reply(message, str(error))
            return False

    async def after_execute(self, message, args):
        # Chat uses separate retention-controlled storage, never command_records.
        return
