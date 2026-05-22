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
        # user_name = message.author.username
        mentions = message.mentions
        filtered_users = [u for u in mentions if not u.bot]
        # _log.info(f"filtered_users: {filtered_users}")

        if not filtered_users:
            filtered_users = [message.author]
        user_id = filtered_users[0].id
        user = await self.client.api.get_guild_member(message.guild_id, user_id)
        user_name = user["user"]["username"]
        avatar = user["user"]["avatar"]

        await self.send_reply(message, f"{user_name}")


@command("皮套")
class FakeId(Command):
    name = "fake_id"
    cn_name = "皮套"

    async def execute(self, message: Message, args: List[str]):
        mentions = message.mentions
        filtered_users = [u for u in mentions if not u.bot]
        user_id = filtered_users[0].id
        user = await self.client.api.get_guild_member(message.guild_id, user_id)

        name = user["nick"]
        avatar = user["user"]["avatar"]

        await self.client.api.post_message(
            message.channel_id,
            name,
            image=avatar,
            msg_id=message.id
        )


