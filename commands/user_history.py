import asyncio
from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging
from dao import get_dao


@command("用户历史", "这是谁")
class UserHistory(Command):
    name = "user_history"
    cn_name = "用户历史"

    async def execute(self, message: Message, args: List[str]):
        mentions = message.mentions
        filtered_users = [u for u in mentions if not u.bot]
        if not filtered_users:
            filtered_users = [message.author]
        user = filtered_users[0]
        user_id = user.id

        history_names = get_dao().get_user_history_nicknames(user_id, message.guild_id)

        result = f"<@!{user_id}>的曾用昵称:\n"
        result += "\n".join(history_names)

        await self.send_reply(message, result)
        return
