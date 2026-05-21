import asyncio
from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging
from dao import get_dao

@command("真身")
class RealId(Command):
    name = "real_id"
    cn_name = "真身"

    async def execute(self, message: Message, args: List[str]):
        user_name = message.author.username
        user = await self.client.api.get_guild_member(message.guild_id, message.author.id)
        user_name2 = user["user"]["username"]
        avatar = user["user"]["avatar"]

        await self.send_reply(message, f"{user_name2}, {avatar}")