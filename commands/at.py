import asyncio
from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging


_log = logging.get_logger()

@command('at')
class AtCommand(Command):
    name = 'at'
    async def execute(self, message: Message, args: List[str]):
        _log.info(f"Emoji command received: {message.content}")
        await self.send_reply(message, f"<@!{message.author.id}> 你好！")