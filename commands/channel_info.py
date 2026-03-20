from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging

_log = logging.get_logger()

@command("所有频道信息", "all_channel_info")
class AllChannelInfoCommand(Command):
    name = "all_channel_info"
    async def execute(self, message: Message, args: List[str]):
        out = await self.client.api.get_channels("15913006732425380356")
        res_str = "所有频道信息:\n" + "\n".join(str(ch) for ch in out)
        await self.send_reply(message, res_str)

@command("当前频道信息", "cur_channel_info", "current_channel_info")
class CurrentChannelInfoCommand(Command):
    name = "current_channel_info"
    async def execute(self, message: Message, args: List[str]):
        out = await self.client.api.get_channel(channel_id=message.channel_id)
        res_str = (
            f"频道id:{out['id']}\n"
            f"子频道id:{out['guild_id']}\n"
            f"子频道名:{out['name']}\n"
            f"子频道类型:{out['type']}\n"
            f"子频道子类型:{out['sub_type']}"
        )

        await self.send_reply(message, res_str)
