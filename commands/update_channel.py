from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging

_log = logging.get_logger()

@command("修改频道parent_id", "update_channel_parent_id")
class UpdateChannelCommand(Command):
    async def execute(self, message: Message, args: List[str]):
        if len(args) < 2:
            await self.send_reply(message, "格式错误，正确格式为 修改频道parent_id 频道id parent_id")
            return
        try:
            out = await self.client.api.update_channel(args[0], parent_id=args[1])
            res_str = f"修改结果返回:\n{str(out)}"
        except Exception as e:
            res_str = f"错误: {e}"
        await self.send_reply(message, res_str)
