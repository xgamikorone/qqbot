import asyncio
import os
import re
from textwrap import dedent

import aiohttp
from dotenv import load_dotenv

from commands.api import (
    get_num_followers,
    get_num_guards,
    get_tagged_streamers,
    get_user_info_by_uids,
    get_users_name_like,
)
from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging
from .categories import categories
from .tags import tags_map


_log = logging.get_logger()


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

        if category not in tags_map:
            # 输入是主播名称
            name_pattern = category
            users = await get_users_name_like(name_pattern)
            if not users:
                await self.send_reply(
                    message, f"{category}既不是已知分类，也没有找到匹配的主播！"
                )
                return

            uids = [user["uid"] for user in users]
        else:
            tag_id = tags_map[category]
            data = await get_tagged_streamers(tag_id)
            if data is None:
                await self.send_reply(
                    message, f"获取 {category} 分类主播信息失败, 请稍后再试"
                )
                return
            uids = [item["uid"] for item in data]

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

        # num_guards_strs = []
        record_time = ""
        name_guards_delta_list = []
        for uid in filtered_uids:
            guard_info = num_guards.get(str(uid), {})
            num_guards_this_uid = guard_info.get("num_guards", None)
            delta = guard_info.get("delta", None)
            name = user_infos[str(uid)]["name"]
            record_time = guard_info.get("record_time", "")
            delta_str = f"+{delta}" if delta is not None and delta > 0 else str(delta)
            # num_guards_str = f"{name}: {num_guards_this_uid if num_guards_this_uid is not None else '获取失败'}{' (' + delta_str + ')' if delta is not None else ''}"
            # num_guards_strs.append(num_guards_str)
            name_guards_delta_list.append((name, num_guards_this_uid, delta_str))

        name_guards_delta_list.sort(
            key=lambda x: (x[1] if x[1] is not None else -1, x[2]), reverse=True
        )
        num_guards_strs = [
            f"{name}: {guards if guards is not None else '获取失败'}{' (' + delta + ')' if delta is not None else ''}"
            for name, guards, delta in name_guards_delta_list
        ]

        res_str += "\n".join(num_guards_strs)
        res_str += f"\n\n对比时间: {record_time}"
        await self.send_reply(message, res_str)
        return


guards_help_str = dedent(
    f"""\
    /舰长 [分类] 查询当前分类舰长数，默认查询四禧丸子。
    分类包括: {','.join(tags_map)}
    """
)


@command("舰长帮助", "guards_help")
class GuardsHelpCommand(Command):
    name = "guards_help"
    cn_name = "舰长帮助"

    async def execute(self, message: Message, args: List[str]):
        await self.send_reply(message, guards_help_str)
        return


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

        if category not in tags_map:
            # 输入是主播名称
            name_pattern = category
            users = await get_users_name_like(name_pattern)
            if not users:
                await self.send_reply(
                    message, f"{category}既不是已知分类，也没有找到匹配的主播！"
                )
                return

            uids = [user["uid"] for user in users]
        else:
            tag_id = tags_map[category]
            data = await get_tagged_streamers(tag_id)
            if data is None:
                await self.send_reply(
                    message, f"获取 {category} 分类主播信息失败, 请稍后再试"
                )
                return
            uids = [item["uid"] for item in data]

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
        # fans_strs = []
        name_followers_delta_list = []
        for uid in uids:
            fans_info = fans_data.get(str(uid), {})
            num_followers = fans_info.get("num_followers", None)
            delta = fans_info.get("delta", None)
            delta_str = f"+{delta}" if delta is not None and delta > 0 else str(delta)
            # fans_this_uid_str = f"{user_infos[str(uid)]['name']}: {num_followers if num_followers is not None else '获取失败'}{' (' + delta_str + ')' if delta is not None else ''}"
            # fans_strs.append(fans_this_uid_str)
            record_time = fans_info.get("record_time", "")
            name_followers_delta_list.append(
                (user_infos[str(uid)]["name"], num_followers, delta_str)
            )

        name_followers_delta_list.sort(
            key=lambda x: (x[1] if x[1] is not None else -1, x[2]), reverse=True
        )
        fans_strs = [
            f"{name}: {followers if followers is not None else '获取失败'}{' (' + delta + ')' if delta is not None else ''}"
            for name, followers, delta in name_followers_delta_list
        ]

        res_str += "\n".join(fans_strs)
        res_str += f"\n\n对比时间: {record_time}"
        await self.send_reply(message, res_str)
        return


followers_help_str = dedent(
    f"""\
    /粉丝 [分类] 查询当前分类粉丝数，默认查询四禧丸子。
    分类包括: {','.join(tags_map)}
    """
)


@command("粉丝帮助", "followers_help")
class FollowersHelpCommand(Command):
    name = "followers_help"
    cn_name = "粉丝帮助"

    async def execute(self, message: Message, args: List[str]):
        await self.send_reply(message, followers_help_str)
        return
