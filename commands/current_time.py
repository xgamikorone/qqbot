from typing import List

from botpy.message import Message

from .base import command, Command, cooldown
from utils.time_utils import beijing_now_str

@command("time")
class CurrentTimeCommand(Command):
    name = "time"
    cn_name = "当前时间"
    async def execute(self, message: Message, args: List[str]):
        time_str = beijing_now_str()
        await self.send_reply(message, f"当前北京时间：{time_str}")