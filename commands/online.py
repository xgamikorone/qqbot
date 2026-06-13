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
from .categories import categories, category_to_names

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

always_show_categories = []


def get_always_show_groups(sessions):
    groups = []
    shown_uids = set()
    for category in always_show_categories:
        category_uids = categories.get(category)
        if category_uids is None:
            _log.warning(f"unknown always show category: {category}")
            continue
        category_uid_set = set(category_uids)
        category_sessions = [
            session for session in sessions
            if session["uid"] in category_uid_set and session["uid"] not in shown_uids
        ]
        if not category_sessions:
            continue
        groups.append((category, category_sessions))
        shown_uids.update(session["uid"] for session in category_sessions)
    return groups, shown_uids





@command("看谁", "高能", "gn", "同接")
class OnlineNumberCommand(Command):
    """获取在线同接数"""

    name = "online_number"
    cn_name = "高能"

    async def execute(self, message: Message, args: List[str]):
        limit = 10
        if args:
            arg = args[0].strip().lower()
            if arg in ("all", "/all", "a", "/a"):
                limit = None
            elif arg.isdigit() and int(arg) > 0:
                limit = int(arg)
            else:
                await self.send_reply(message, "参数错误, 请输入正整数或 all")
                return

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

        always_show_groups, always_show_uids = get_always_show_groups(sessions)
        normal_sessions = [
            session for session in sessions if session["uid"] not in always_show_uids
        ]

        total_count = len(normal_sessions)
        if limit is not None:
            normal_sessions = normal_sessions[:limit]

        lines = ["目前高能:"]
        for category, category_sessions in always_show_groups:
            category_name = category_to_names.get(category, category)
            lines.append(f"{category_name}:")
            lines.extend(
                f"{session['name']}: {session['online_count']}"
                for session in category_sessions
            )

        top_title = "top all:" if limit is None else f"top {limit}:"
        lines.append(top_title)
        lines.extend(
            f"{session['name']}: {session['online_count']}"
            for session in normal_sessions
        )

        res_str = "\n".join(lines)
        folded_count = total_count - len(normal_sessions)
        if folded_count > 0:
            res_str += f"\n还有{folded_count}位主播的数据已折叠，可使用参数all/a显示全部，或参数n显示前n名。"
        res_str += "\n如数据有误，请联系作者。"
        await self.send_reply(message, res_str)


online_help_str = dedent("""\
    输入"高能"/"gn"/"看谁"/"同接"可获取在线同接数。
    默认显示前10名，参数n显示前n名，参数all/a显示全部。
    """)


@command("同接帮助", "online_help")
class OnlineHelpCommand(Command):
    name = "online_help"
    cn_name = "同接帮助"

    async def execute(self, message: Message, args: List[str]):
        await self.send_reply(message, online_help_str)
