from typing import List

from botpy.message import Message
from botpy import message as botpy_message

from .base import command, Command, cooldown
from utils.time_utils import beijing_now_str
from .help_catalog import CommandHelp


@command("time", "当前时间")
class CurrentTimeCommand(Command):
    supported_scenes = frozenset({"guild", "group"})
    name = "time"
    cn_name = "当前时间"
    help = CommandHelp(
        title="当前时间", category="工具", summary="查看北京时间", usage="/time"
    )

    async def execute(self, message: Message, args: List[str]) -> None:
        time_str = beijing_now_str()
        await self.send_reply(message, f"当前北京时间：{time_str}")

    async def execute_group(
        self, message: botpy_message.GroupMessage, args: list[str]
    ) -> None:
        """Uses the original group message with the group reply helper."""
        await self.reply_group(message, f"当前北京时间：{beijing_now_str()}")
