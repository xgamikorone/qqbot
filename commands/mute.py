from datetime import datetime

from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging
from .categories import categories
from .tags import tags_map
from .help_catalog import CommandHelp

_log = logging.get_logger()

@command("禁言", "mute")
class MuteCommand(Command):
    name = "mute"
    cn_name = "禁言"
    owner_only = True

    async def execute(self, message: Message, args: List[str]):
        if len(args) < 2:
            await self.send_reply(message, "用法：/禁言 @用户 [时长(分钟)]")
            return

        user_id = args[0]
        duration = int(args[1]) if len(args) > 1 else 0
        mute_end_timestamp = int(datetime.timestamp(datetime.now())) + duration * 60 if duration > 0 else None

        # 调用禁言逻辑，这里假设有一个 mute_user 函数
        success = await self.client.api.mute_member(message.guild_id, user_id, mute_end_timestamp=str(mute_end_timestamp))
        if success:
            await self.send_reply(message, f"已禁言用户 {user_id} {duration} 分钟")
        else:
            await self.send_reply(message, f"禁言用户 {user_id} 失败")
