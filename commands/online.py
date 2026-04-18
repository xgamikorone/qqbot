import asyncio
import os
import re
from textwrap import dedent

import aiohttp

from commands.api import get_on_live_sessions
from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging
from dao import get_dao
from dotenv import load_dotenv
from .categories import categories

load_dotenv()

_log = logging.get_logger()

# api_url = os.getenv("API_URL")
# proxy = os.getenv("PROXY")
# _log.info(f"api_url: {api_url}, proxy: {proxy}")

exclusive_uids = [
    3493269266762688,
    3494353391585585,
    3493271057730096,
    2109776,
    480680646,
    3546567734725599
]





@command("看谁", "高能", "gn", "同接")
class OnlineNumberCommand(Command):
    """获取在线同接数"""

    name = "online_number"
    cn_name = "高能"

    async def execute(self, message: Message, args: List[str]):
        sessions = await get_on_live_sessions()
        if sessions is None:
            await self.send_reply(message, "获取在线直播时发生错误！请联系作者。")
            return

        if not sessions:
            await self.send_reply(message, "目前无人开播！\n如数据有误，请联系作者。")
            return

        sessions.sort(key=lambda x: x["online_count"]
                      if x["online_count"] is not None else 0, reverse=True)

        sessions = list(filter(
            lambda x: x["uid"] not in exclusive_uids, sessions
        ))

        res_str = "目前高能:\n"
        res_str += "\n".join(
            [f"{session['name']}: {session['online_count']}" for session in sessions]
        )
        res_str += "\n如数据有误，请联系作者。"
        await self.send_reply(message, res_str)


online_help_str = dedent("""\
    输入"高能"/"gn"/"看谁"/"同接"可获取在线同接数。
    """)


@command("同接帮助", "online_help")
class OnlineHelpCommand(Command):
    name = "online_help"
    cn_name = "同接帮助"

    async def execute(self, message: Message, args: List[str]):
        await self.send_reply(message, online_help_str)
