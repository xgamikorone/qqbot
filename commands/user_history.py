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

@command("谁是", "whois")
class WhoIsCommand(Command):
    name = "whois"
    cn_name = "谁是"

    async def execute(self, message: Message, args: List[str]):
        if not args:
            await self.send_reply(message, "请输入昵称关键词")
            return

        nickname_keyword = args[0]
        guild_id = message.guild_id

        # 从command_records表中查询包含该关键词的用户
        users = get_dao().get_user_by_nickname_like_in_records(nickname_keyword, guild_id)

        if not users:
            await self.send_reply(message, f"找不到包含'{nickname_keyword}'的昵称")
            return

        # 获取用户的当前昵称
        user_ids = [user["user_id"] for user in users]
        usernames = await self._fetch_usernames(guild_id, user_ids)

        result = f"找到{len(users)}个包含'{nickname_keyword}'的用户：\n"
        for user in users:
            current_nick = usernames.get(user["user_id"], "未知用户")
            result += f"曾用昵称: {user['user_name']}, 现在昵称: {current_nick}\n"

        await self.send_reply(message, result.rstrip("\n"))

    async def _fetch_usernames(self, guild_id: str, user_ids: List[str]) -> dict:
        """获取用户在服务器中的当前昵称"""
        result: dict = {}
        for uid in user_ids:
            try:
                user = await self.client.api.get_guild_member(guild_id, uid)
                result[uid] = user["nick"]
            except Exception:
                result[uid] = "未知用户"
        return result
        