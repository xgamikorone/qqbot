import asyncio
import os
import re
from textwrap import dedent

import aiohttp
from dotenv import load_dotenv
from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging
from .categories import categories


_log = logging.get_logger()

load_dotenv()
api_url = os.getenv("API_URL")
proxy = os.getenv("PROXY")


async def get_tagged_streamers(tag_id: int) -> List[int] | None:
    url = f"{api_url}/tag_users/{tag_id}"
    headers = {"Referer": "https://bilivupstats.top/"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, proxy=proxy) as response:
                data = await response.json()
                if data and "data" in data:
                    return data["data"]
                return None
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return None


async def get_user_info_by_uids(uids: List[int]) -> dict | None:
    url = f"{api_url}/streamers_room_ids"
    headers = {"Referer": "https://bilivupstats.top/"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params={"uids": uids}, headers=headers, proxy=proxy
            ) as response:
                data = await response.json()
                if data:
                    return data["data"]
                return None
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return None


async def get_num_guards(uids: List[int], room_ids: List[int]):
    url = f"{api_url}/streamers_guards"
    headers = {"Referer": "https://bilivupstats.top/"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params={"uids": uids, "room_ids": room_ids},
                headers=headers,
                proxy=proxy,
            ) as response:
                data = await response.json()
                if data:
                    return data["data"]
                return None
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return None


@command("舰长", "num_guards")
class GuardsCommand(Command):
    """查询指定主播的当前舰长数量"""

    name = "guards"
    cn_name = "舰长"

    async def execute(self, message: Message, args: List[str]):
        _log.info(f"Executing {self.name} command with args: {args}")
        if not args:
            category = "wan"
        else:
            category = args[0]

        if category not in categories:
            await self.send_reply(message, f"未知的分类：{category}")
            return

        uids = categories[category]
        user_infos = await get_user_info_by_uids(uids)
        if user_infos is None:
            await self.send_reply(message, f"获取 {category} 分类主播信息失败")
            return

        res_str = f"舰长数:\n"
        filtered_uids = []
        room_ids = []
        for uid in uids:
            user_info = user_infos.get(str(uid), None)
            if user_info is None:
                continue
            filtered_uids.append(uid)
            room_ids.append(user_info["room_id"])

        num_guards = await get_num_guards(filtered_uids, room_ids)
        _log.info(f"num_guards: {num_guards}")
        if num_guards is None:
            await self.send_reply(message, f"获取 {category} 分类主播舰长信息失败")
            return

        num_guards_strs = []
        record_time = ""
        for uid in filtered_uids:
            guard_info = num_guards.get(str(uid), {})
            num_guards_this_uid = guard_info.get("num_guards", None)
            delta = guard_info.get("delta", None)
            name = user_infos[str(uid)]["name"]
            record_time = guard_info.get("record_time", "")
            delta_str = f"+{delta}" if delta is not None and delta > 0 else str(delta)
            num_guards_str = f"{name}: {num_guards_this_uid if num_guards_this_uid is not None else '获取失败'}{' (' + delta_str + ')' if delta is not None else ''}"
            num_guards_strs.append(num_guards_str)

        res_str += "\n".join(num_guards_strs)
        res_str += f"\n\n对比时间: {record_time}"
        await self.send_reply(message, res_str)
        return


guards_help_str = dedent(
    f"""\
    /舰长 [分类] 查询当前分类舰长数，默认查询四禧丸子。
    分类包括: {','.join(categories)}
    """
)


@command("舰长帮助", "guards_help")
class GuardsHelpCommand(Command):
    name = "guards_help"
    cn_name = "舰长帮助"

    async def execute(self, message: Message, args: List[str]):
        await self.send_reply(message, guards_help_str)
        return


async def get_num_followers(uids: List[int]):
    url = f"{api_url}/streamers_followers"
    headers = {"Referer": "https://bilivupstats.top/"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params={"uids": uids}, headers=headers, proxy=proxy
            ) as response:
                data = await response.json()
                if data:
                    return data["data"]
                return None
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return None


@command("粉丝", "followers")
class FollowersCommand(Command):
    name = "followers"
    cn_name = "粉丝"

    async def execute(self, message: Message, args: List[str]):
        _log.info(f"Executing {self.name} command with args: {args}")
        if not args:
            category = "wan"
        else:
            category = args[0]

        if category not in categories:
            await self.send_reply(message, f"未知的分类：{category}")
            return

        uids = categories[category]
        fans_data = await get_num_followers(uids)
        if fans_data is None:
            await self.send_reply(message, f"获取 {category} 分类主播粉丝信息失败")
            return

        _log.info(f"fans_data: {fans_data}")

        user_infos = await get_user_info_by_uids(uids)
        if user_infos is None:
            await self.send_reply(message, f"获取 {category} 分类主播信息失败")
            return

        res_str = f"粉丝数:\n"
        record_time = ""
        fans_strs = []
        for uid in uids:
            fans_info = fans_data.get(str(uid), {})
            num_followers = fans_info.get("num_followers", None)
            delta = fans_info.get("delta", None)
            delta_str = f"+{delta}" if delta is not None and delta > 0 else str(delta)
            fans_this_uid_str = f"{user_infos[str(uid)]['name']}: {num_followers if num_followers is not None else '获取失败'}{' (' + delta_str + ')' if delta is not None else ''}"
            fans_strs.append(fans_this_uid_str)
            record_time = fans_info.get("record_time", "")

        res_str += "\n".join(fans_strs)
        res_str += f"\n\n对比时间: {record_time}"
        await self.send_reply(message, res_str)
        return


followers_help_str = dedent(
    f"""\
    /粉丝 [分类] 查询当前分类粉丝数，默认查询四禧丸子。
    分类包括: {','.join(categories)}
    """
)


@command("粉丝帮助", "followers_help")
class FollowersHelpCommand(Command):
    name = "followers_help"
    cn_name = "粉丝帮助"

    async def execute(self, message: Message, args: List[str]):
        await self.send_reply(message, followers_help_str)
        return
