import asyncio
import re
from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging


@command("撤回", "recall")
class RecallCommand(Command):
    async def execute(self, message: Message, args: List[str]):
        if message.message_reference.message_id is None:
            await self.send_reply(message, "请引用要删除的消息！")
            return
        await self.client.api.recall_message(
            message.channel_id, message.message_reference.message_id, True
        )
