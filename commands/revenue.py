from datetime import datetime, timedelta
from enum import IntEnum
import os
from .base import command, Command, cooldown
from dao import get_dao
from botpy.message import Message
from botpy import logging
from typing import List, Optional
import asyncio
import aiohttp
from dotenv import load_dotenv
from textwrap import dedent
from .utils import get_name_from_uid, is_admin


_log = logging.get_logger()
load_dotenv()
api_url = os.getenv("API_URL")
proxy = os.getenv("PROXY")
_log.info(f"api_url: {api_url}, proxy: {proxy}")

# 创建全局 session 实例，添加连接池限制和超时设置
import atexit

# 延迟初始化 session
global_session = None

async def get_session():
    global global_session
    if global_session is None or global_session.closed:
        connector = aiohttp.TCPConnector(limit=50, limit_per_host=20)
        timeout = aiohttp.ClientTimeout(total=60, connect=20, sock_read=20, sock_connect=20)
        global_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return global_session

# 程序退出时清理
@atexit.register
def cleanup():
    import asyncio
    if global_session and not global_session.closed:
        try:
            # 尝试获取运行中的事件循环
            loop = asyncio.get_running_loop()
            loop.create_task(global_session.close())
        except RuntimeError:
            # 没有运行中的事件循环，创建一个新的
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(global_session.close())
                loop.close()
            except Exception:
                # 如果仍然失败，忽略错误，因为程序已经在退出
                pass


class ErrorCode(IntEnum):
    NO_LIVE_SESSIONS = -1
    ERROR_FETCHING_DATA = -2


async def get_last_session_id(uid: int) -> int:
    url = f"{api_url}/live_sessions/{uid}"
    headers = {"Referer": "https://bilivupstats.top/"}
    try:
        session = await get_session()
        async with session.get(url, headers=headers, proxy=proxy) as response:
            data = await response.json()
            if data:
                live_sessions = data["live_sessions"]
                if not live_sessions:
                    return -1
                return live_sessions[-1]["session_id"]
            return ErrorCode.NO_LIVE_SESSIONS
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return ErrorCode.ERROR_FETCHING_DATA


async def get_session_revenue(session_id: int) -> dict:
    url = f"{api_url}/live_revenue/{session_id}"
    headers = {"Referer": "https://bilivupstats.top/"}
    try:
        session = await get_session()
        async with session.get(url, headers=headers, proxy=proxy) as response:
            data = await response.json()
            if data:
                revenue = data
                return revenue
            return {}
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return {}


async def get_session_info(session_id: int) -> dict:
    url = f"{api_url}/live_session_info/{session_id}"
    headers = {"Referer": "https://bilivupstats.top/"}
    try:
        session = await get_session()
        async with session.get(url, headers=headers, proxy=proxy) as response:
            data = await response.json()
            if data:
                return data["live_session"]
            return {}
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return {}

async def get_danmu_info(session_id: int) -> int:
    url = f"{api_url}/danmu/{session_id}"
    headers = {"Referer": "https://bilivupstats.top/"}
    params = {
        "limit": 1,
        "sort": "asc"
    }
    try:
        session = await get_session()
        async with session.get(url, headers=headers, proxy=proxy, params=params) as response:
            data = await response.json()
            if data:
                return data["count"]
            return 0
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return 0

async def get_super_chats(uid: int, start: int, end: int) -> list:
    url = f"{api_url}/streamer_super_chats/{uid}"
    headers = {"Referer": "https://bilivupstats.top/"}
    try:
        session = await get_session()
        async with session.get(
            url, params={"start": start, "end": end}, proxy=proxy, headers=headers
        ) as response:
            data = await response.json()
            if data:
                return data["super_chats"]
            return []
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return []


async def get_guards(uid: int, start: int, end: int) -> list:
    url = f"{api_url}/streamer_guards/{uid}"
    headers = {"Referer": "https://bilivupstats.top/"}
    try:
        session = await get_session()
        async with session.get(
            url, params={"start": start, "end": end}, proxy=proxy, headers=headers
        ) as response:
            data = await response.json()
            if data:
                return data["guards"]
            return []
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return []


async def get_user_super_chats(
    uid: int,
    start_time: str,
    end_time: str,
    streamer_uids: Optional[List[int]],
    start: int,
    end: int,
) -> list:
    url = f"{api_url}/user_super_chats_by_uid/{uid}"
    headers = {"Referer": "https://bilivupstats.top/"}
    params = {
        "start_time": start_time,
        "end_time": end_time,
        "start": start,
        "end": end,
    }
    if streamer_uids is not None:
        params["streamer_uids"] = streamer_uids
    try:
        session = await get_session()
        async with session.get(
            url,
            params=params,
            proxy=proxy,
            headers=headers,
        ) as response:
            data = await response.json()
            if data:
                return data["super_chats"]
            return []
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return []


async def get_user_guards(
    uid: int,
    start_time: str,
    end_time: str,
    streamer_uids: Optional[List[int]],
    start: int,
    end: int,
):
    url = f"{api_url}/user_guards_by_uid/{uid}"
    headers = {"Referer": "https://bilivupstats.top/"}
    params = {
        "start_time": start_time,
        "end_time": end_time,
        "start": start,
        "end": end,
    }
    if streamer_uids is not None:
        params["streamer_uids"] = streamer_uids
    try:
        session = await get_session()
        async with session.get(
            url,
            params=params,
            proxy=proxy,
            headers=headers,
        ) as response:
            data = await response.json()
            if data:
                return data["guards"]
            return []
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return []


async def get_user_danmus(
    uid: int,
    start_time: str,
    end_time: str,
    streamer_uids: Optional[List[int]],
    start: int,
    end: int,
):
    url = f"{api_url}/user_danmus_by_uid/{uid}"
    headers = {"Referer": "https://bilivupstats.top/"}
    params = {
        "start_time": start_time,
        "end_time": end_time,
        "start": start,
        "end": end,
    }
    if streamer_uids is not None:
        params["streamer_uids"] = streamer_uids
    try:
        session = await get_session()
        async with session.get(
            url,
            params=params,
            proxy=proxy,
            headers=headers,
        ) as response:
            data = await response.json()
            if data:
                return data["danmus"]
            return []
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return []

async def get_online_members(session_id: int) -> dict:
    url = f"{api_url}/online_members/{session_id}"
    headers = {"Referer": "https://bilivupstats.top/"}

    try:
        session = await get_session()
        async with session.get(
            url,
            proxy=proxy,
            headers=headers,
        ) as response:
            data = await response.json()
            if data:
                return data
            return {}
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return {}


@command("查营收", "营收", "revenue")
class RevenueCommand(Command):
    name = "revenue"
    cn_name = "查营收"

    async def execute(self, message: Message, args: List[str]):
        _log.info(f"RevenueCommand args: {args}")
        if not args:
            await self.send_reply(message, "请输入要查询的主播uid或昵称")
        uid_or_nickname = args[0]
        if uid_or_nickname.isdigit():
            uid = int(uid_or_nickname)
        elif uid_or_nickname.lower().startswith("uid:"):
            uid = int(uid_or_nickname[4:].strip())
        else:
            # 是昵称
            dao = get_dao()
            uid = dao.get_uid_by_nickname(uid_or_nickname)
            if uid is None:
                await self.send_reply(message, f"未找到昵称为{uid_or_nickname}的主播")
                return
        _log.info(f"uid: {uid}")
        last_session_id = await get_last_session_id(uid)
        _log.info(f"last_session_id: {last_session_id}")
        name = await get_name_from_uid(uid)
        _log.info(f"name: {name}")
        if name is None:
            name = uid_or_nickname
        if last_session_id == ErrorCode.NO_LIVE_SESSIONS:
            await self.send_reply(message, f"主播{name}没有直播记录")
            return
        if last_session_id == ErrorCode.ERROR_FETCHING_DATA:
            await self.send_reply(message, f"查询{name}的直播数据失败")
            return
        revenue = await get_session_revenue(last_session_id)
        revenue = revenue["revenue"]
        _log.info(f"revenue:\n{revenue}")

        session_info = await get_session_info(last_session_id)
        _log.info(f"session_info:\n{session_info}")
        if not session_info:
            await self.send_reply(message, f"查询{name}的直播数据失败")
            return
        if not revenue:
            await self.send_reply(message, f"查询{name}的直播数据失败")
            return

        online_members = await get_online_members(last_session_id)
        # _log.info(f"online_members:\n{online_members}")
        if not online_members:
            max_online = 0
            avg_online = 0
        else:
            max_online = online_members["max"]
            avg_online = online_members["avg"]

        # danmu_count = await get_danmu_info(last_session_id)
        # _log.info(f"danmu_count: {danmu_count}")

        guard_revenue = revenue.get("guards", 0)
        gift_revenue = revenue.get("gifts", 0)
        sc_revenue = revenue.get("super_chats", 0)
        total = revenue.get("total", 0)
        start_time = session_info["start_time"]
        # erase "T" in start time 2026-03-09T21:01:38 -> 2026-03-09 21:01:38
        start_time = start_time.replace("T", " ")
        end_time = "" if session_info["end_time"] is None else session_info["end_time"]
        if end_time is not None:
            end_time = end_time.replace("T", " ")
        res_str = (
            f"主播{name}的最近一场直播营收:\n"
            f"直播标题: {session_info.get('title', '')}\n"
            f"直播时间: {start_time}~{end_time}\n"
            f"同接(最高/平均): {max_online}/{round(avg_online)}\n"
            # f"弹幕数: {danmu_count}\n"
            f"舰队收入: {round(guard_revenue, 2)}\n"
            f"礼物收入: {round(gift_revenue, 2)}\n"
            f"SC收入: {round(sc_revenue, 2)}\n"
            f"总收入: {round(total, 2)}"
        )
        await self.send_reply(message, res_str)


@command("查SC", "SC", "sc", "super_chat")
class SuperChatCommand(Command):
    PAGE_SIZE = 10
    name = "super_chat"
    cn_name = "查SC"

    async def execute(self, message: Message, args: List[str]):
        _log.info(f"SuperChatCommand args: {args}")
        if not args:
            await self.send_reply(message, "请输入要查询的主播uid或昵称")
        uid_or_nickname = args[0]
        num_page = 0 if len(args) < 2 else int(args[1])
        if num_page < 0:
            num_page = 0
        _log.info(f"num_page: {num_page}")
        if uid_or_nickname.isdigit():
            uid = int(uid_or_nickname)
        elif uid_or_nickname.lower().startswith("uid:"):
            uid = int(uid_or_nickname[4:].strip())
        else:
            # 是昵称
            dao = get_dao()
            uid = dao.get_uid_by_nickname(uid_or_nickname)
            if uid is None:
                await self.send_reply(message, f"未找到昵称为{uid_or_nickname}的主播")
                return
        name = await get_name_from_uid(uid)
        _log.info(f"uid: {uid}, name: {name}")
        if name is None:
            name = uid_or_nickname
        super_chats = await get_super_chats(
            uid,
            num_page * self.PAGE_SIZE,
            (num_page + 1) * self.PAGE_SIZE,
        )
        _log.info(f"super_chats:\n{super_chats}")

        res_str = (
            f"主播 {name}的最近 {num_page * self.PAGE_SIZE+1}~{(num_page + 1) * self.PAGE_SIZE}条SC:\n"
            f"格式为: 用户名:SC内容;时间;价格\n"
        )
        # for sc in super_chats:
        #     res_str += f"{sc['user_name']}: {sc['message']}; {sc['record_time']}; {sc['price']}\n"

        res_str += "\n".join(
            [
                f"{sc['user_name']}: {sc['message']}; {sc['record_time']}; {sc['price']}"
                for sc in super_chats
            ]
        )
        await self.send_reply(message, res_str)


@command("查舰长", "guards")
class StreamerGuardsCommand(Command):
    PAGE_SIZE = 10
    name = "streamer_guards"
    cn_name = "查舰长"

    async def execute(self, message: Message, args: List[str]):
        _log.info(f"StreamerGuardsCommand args: {args}")
        if not args:
            await self.send_reply(message, "请输入要查询的主播uid或昵称")
        uid_or_nickname = args[0]
        num_page = 0 if len(args) < 2 else int(args[1])
        if num_page < 0:
            num_page = 0
        _log.info(f"num_page: {num_page}")
        if uid_or_nickname.isdigit():
            uid = int(uid_or_nickname)
        elif uid_or_nickname.lower().startswith("uid:"):
            uid = int(uid_or_nickname[4:].strip())
        else:
            # 是昵称
            dao = get_dao()
            uid = dao.get_uid_by_nickname(uid_or_nickname)
            if uid is None:
                await self.send_reply(message, f"未找到昵称为{uid_or_nickname}的主播")
                return
        name = await get_name_from_uid(uid)
        _log.info(f"uid: {uid}, name: {name}")
        if name is None:
            name = uid_or_nickname
        guards = await get_guards(
            uid,
            num_page * self.PAGE_SIZE,
            (num_page + 1) * self.PAGE_SIZE,
        )
        _log.info(f"super_chats:\n{guards}")

        res_str = (
            f"主播 {name}的最近 {num_page * self.PAGE_SIZE+1}~{(num_page + 1) * self.PAGE_SIZE}个舰长:\n"
            f"格式为: 用户名:舰长等级;数量;时间;价格\n"
        )
        guard_levels = {
            1: "总督",
            2: "提督",
            3: "舰长",
        }
        # for sc in super_chats:
        #     res_str += f"{sc['user_name']}: {sc['message']}; {sc['record_time']}; {sc['price']}\n"

        res_str += "\n".join(
            [
                f"{g['user_name']}: {guard_levels.get(g['guard_level'], g['guard_level'])}; {g['num']}; {g['record_time']}; {g['price'] / 1000.}"
                for g in guards
            ]
        )
        await self.send_reply(message, res_str)


@command("查用户SC", "用户SC", "user_sc", "user_super_chat")
class UserSuperChatCommand(Command):
    """查询用户发过的SC, 参数为 <uid或昵称>
    可选参数
    </p> <页码>
    </r> <在uid或昵称的直播间(默认所有直播间)>
    </s> <开始时间(默认半年前)>
    </e> <结束时间(默认当前时间)>
    """

    name = "user_super_chat"
    PAGE_SIZE = 10

    @cooldown(10)
    async def execute(self, message: Message, args: List[str]):
        _log.info(f"UserSuperChatCommand args: {args}")
        # channel_id = int(message.channel_id)
        # if channel_id not in ALLOWED_CHANNELS:
        #     await self.send_reply(message, "该功能不允许在此频道被使用！")
        #     return
        member = message.member
        roles = member.roles
        if not is_admin(roles):
            await self.send_reply(message, "该功能仅管理员可用！")
            return
        if not args:
            await self.send_reply(message, "请输入要查询的用户uid或昵称")
        uid_or_nickname = args[0]
        if uid_or_nickname.isdigit():
            uid = int(uid_or_nickname)
        elif uid_or_nickname.lower().startswith("uid:"):
            uid = int(uid_or_nickname[4:].strip())
        else:
            # 是昵称
            dao = get_dao()
            uid = dao.get_uid_by_nickname(uid_or_nickname)
            if uid is None:
                await self.send_reply(message, f"未找到昵称为{uid_or_nickname}的用户")
                return
        # 检查可选参数
        # e.g. /p 1 /r 又一, 1900141897 (多个主播)
        room_str = ""
        start_time = (datetime.now() - timedelta(days=180)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        num_page = 0
        for i in range(1, len(args), 2):
            if args[i] == "/p":
                num_page = int(args[i + 1])
                if num_page < 0:
                    num_page = 0
            if args[i] == "/r":
                room_str = args[i + 1]
            if args[i] == "/s":
                start_time = args[i + 1]
            if args[i] == "/e":
                end_time = args[i + 1]
        if end_time < start_time:
            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _log.info(
            f"room_str: {room_str}, num_page: {num_page}, start_time: {start_time}, end_time: {end_time}"
        )
        rooms = []
        if room_str:
            room_str = room_str.replace("，", ",")  # 兼容中文逗号
            rooms = room_str.split(",")
        streamer_uids = []
        for room in rooms:
            if room.isdigit():
                streamer_uids.append(int(room))
            else:
                # 是昵称
                dao = get_dao()
                streamer_uid = dao.get_uid_by_nickname(room)
                if streamer_uid is None:
                    await self.send_reply(message, f"未找到昵称为{room}的主播")
                    return
                streamer_uids.append(streamer_uid)
        _log.info(f"streamer_uids: {streamer_uids}")
        # 查询用户发过的SC
        user_super_chats = await get_user_super_chats(
            uid,
            start_time,
            end_time,
            streamer_uids,
            num_page * self.PAGE_SIZE,
            (num_page + 1) * self.PAGE_SIZE,
        )
        _log.info(f"user_super_chats:\n{user_super_chats}")

        res_str = (
            f"用户{uid_or_nickname}发过的SC:\n"
            f"格式为: 用户名:SC内容;时间;价格;直播间\n"
        )
        # for sc in user_super_chats:
        #     res_str += f"{sc['user_name']}: {sc['message']}; {sc['record_time']}; {sc['price']}; {sc['streamer_name']}\n"

        res_str += "\n".join(
            [
                f"{sc['user_name']}: {sc['message']}; {sc['record_time']}; {sc['price']}; {sc['streamer_name']}"
                for sc in user_super_chats
            ]
        )
        _log.info(f"res_str: {res_str}")
        await self.send_reply(message, res_str)


@command("查用户舰长", "用户舰长", "user_guards", "user_guard")
class UserGuardsCommand(Command):
    """查询用户直播间的舰长, 参数为 <uid或昵称>
    可选参数
    </p> <页码>
    </r> <在uid或昵称的直播间(默认所有直播间)>
    </s> <开始时间(默认半年前)>
    </e> <结束时间(默认当前时间)>
    """

    name = "user_guards"
    cn_name = "查用户舰长"
    PAGE_SIZE = 10

    @cooldown(10)
    async def execute(self, message: Message, args: List[str]):
        _log.info(f"UserGuardsCommand args: {args}")
        # channel_id = int(message.channel_id)
        # if channel_id not in ALLOWED_CHANNELS:
        #     await self.send_reply(message, "该功能不允许在此频道被使用！")
        #     return
        member = message.member
        roles = member.roles
        if not is_admin(roles):
            await self.send_reply(message, "该功能仅管理员可用！")
            return
        if not args:
            await self.send_reply(message, "请输入要查询的用户uid或昵称")

        uid_or_nickname = args[0]
        if uid_or_nickname.isdigit():
            uid = int(uid_or_nickname)
        elif uid_or_nickname.lower().startswith("uid:"):
            uid = int(uid_or_nickname[4:].strip())
        else:
            # 是昵称
            dao = get_dao()
            uid = dao.get_uid_by_nickname(uid_or_nickname)
            if uid is None:
                await self.send_reply(message, f"未找到昵称为{uid_or_nickname}的用户")
                return
        # 检查可选参数
        room_str = ""
        start_time = (datetime.now() - timedelta(days=180)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        num_page = 0
        for i in range(1, len(args), 2):
            if args[i] == "/p":
                num_page = int(args[i + 1])
                if num_page < 0:
                    num_page = 0
            if args[i] == "/r":
                room_str = args[i + 1]
            if args[i] == "/s":
                start_time = args[i + 1]
            if args[i] == "/e":
                end_time = args[i + 1]
        if end_time < start_time:
            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _log.info(
            f"room_str: {room_str}, num_page: {num_page}, start_time: {start_time}, end_time: {end_time}"
        )
        rooms = []
        if room_str:
            room_str = room_str.replace("，", ",")  # 兼容中文逗号
            rooms = room_str.split(",")
        streamer_uids = []
        for room in rooms:
            if room.isdigit():
                streamer_uids.append(int(room))
            else:
                # 是昵称
                dao = get_dao()
                streamer_uid = dao.get_uid_by_nickname(room)
                if streamer_uid is None:
                    await self.send_reply(message, f"未找到昵称为{room}的主播")
                    return
                streamer_uids.append(streamer_uid)
        _log.info(f"streamer_uids: {streamer_uids}")
        # 查询用户发过的SC
        user_guards = await get_user_guards(
            uid,
            start_time,
            end_time,
            streamer_uids,
            num_page * self.PAGE_SIZE,
            (num_page + 1) * self.PAGE_SIZE,
        )
        _log.info(f"user_guards:\n{user_guards}")

        res_str = (
            f"用户{uid_or_nickname}上过的舰长:\n"
            f"格式为: 用户名:舰长等级;数量;时间;价格;直播间\n"
        )
        guard_levels = {
            1: "总督",
            2: "提督",
            3: "舰长",
        }
        # for guard in user_guards:
        #     res_str += f"{guard['user_name']}: {guard_levels[guard["guard_level"]]}; {guard['num']}; {guard['record_time']}; {guard['price'] / 1000.}; {guard['streamer_name']}\n"

        res_str += "\n".join(
            [
                f"{guard['user_name']}: {guard_levels[guard['guard_level']]}; "
                f"{guard['num']}; {guard['record_time']}; "
                f"{guard['price'] / 1000.}; {guard['streamer_name']}"
                for guard in user_guards
            ]
        )

        _log.info(f"res_str: {res_str}")
        await self.send_reply(message, res_str)


@command("查用户弹幕", "用户弹幕", "user_danmus", "user_danmu")
class UserDanmusCommand(Command):
    """查询用户直播间的弹幕, 参数为 <uid或昵称>
    可选参数

    </p> <页码>
    </r> <在uid或昵称的直播间(默认所有直播间)>
    </s> <开始时间(默认半年前)>
    </e> <结束时间(默认当前时间)>
    """

    PAGE_SIZE = 10
    name = "user_danmus"
    cn_name = "查用户弹幕"

    @cooldown(30)
    async def execute(self, message: Message, args: List[str]):
        _log.info(f"UserGuardsCommand args: {args}")
        # channel_id = int(message.channel_id)
        # if channel_id not in ALLOWED_CHANNELS:
        #     await self.send_reply(message, "该功能不允许在此频道被使用！")
        #     return
        member = message.member
        roles = member.roles
        if not is_admin(roles):
            await self.send_reply(message, "该功能仅管理员可用！")
            return

        if not args:
            await self.send_reply(message, "请输入要查询的用户uid或昵称")

        uid_or_nickname = args[0]
        if uid_or_nickname.isdigit():
            uid = int(uid_or_nickname)
        elif uid_or_nickname.lower().startswith("uid:"):
            uid = int(uid_or_nickname[4:].strip())
        else:
            # 是昵称
            dao = get_dao()
            uid = dao.get_uid_by_nickname(uid_or_nickname)
            if uid is None:
                await self.send_reply(message, f"未找到昵称为{uid_or_nickname}的用户")
                return
        # 检查可选参数
        room_str = ""
        start_time = (datetime.now() - timedelta(days=180)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        num_page = 0
        for i in range(1, len(args), 2):
            if args[i] == "/p":
                num_page = int(args[i + 1])
                if num_page < 0:
                    num_page = 0
            if args[i] == "/r":
                room_str = args[i + 1]
            if args[i] == "/s":
                start_time = args[i + 1]
            if args[i] == "/e":
                end_time = args[i + 1]
        if end_time < start_time:
            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _log.info(
            f"room_str: {room_str}, num_page: {num_page}, start_time: {start_time}, end_time: {end_time}"
        )
        rooms = []
        if room_str:
            room_str = room_str.replace("，", ",")  # 兼容中文逗号
            rooms = room_str.split(",")
        streamer_uids = []
        for room in rooms:
            if room.isdigit():
                streamer_uids.append(int(room))
            else:
                # 是昵称
                dao = get_dao()
                streamer_uid = dao.get_uid_by_nickname(room)
                if streamer_uid is None:
                    await self.send_reply(message, f"未找到昵称为{room}的主播")
                    return
                streamer_uids.append(streamer_uid)
        _log.info(f"streamer_uids: {streamer_uids}")
        # 查询用户发过的SC
        user_danmus = await get_user_danmus(
            uid,
            start_time,
            end_time,
            streamer_uids,
            num_page * self.PAGE_SIZE,
            (num_page + 1) * self.PAGE_SIZE,
        )
        _log.info(f"user_danmus:\n{user_danmus}")

        res_str = (
            f"用户{uid_or_nickname}发送过的弹幕:\n" f"格式为: 用户名:内容;时间;直播间\n"
        )
        # for danmu in user_danmus:
        #     res_str += f"{danmu['send_user_name']}: {danmu["message"]}; {danmu['record_time']}; {danmu['streamer_name']}\n"

        res_str += "\n".join(
            [
                f"{danmu['send_user_name']}: {danmu['message']}; {danmu['record_time']}; {danmu['streamer_name']}"
                for danmu in user_danmus
            ]
        )
        _log.info(f"res_str: {res_str}")
        await self.send_reply(message, res_str)


revenue_help_str = dedent(
    """\
    数据管理帮助：

    查营收 <uid或昵称>
    查询主播最近一场直播的营收统计
    示例：查营收 12345 或 查营收 小王
    显示: 直播标题、直播时间、总收益、舰队收益、礼物收益、SC收益

    查SC <uid或昵称> [页码]
    查询主播收到的SC列表
    示例：查SC 12345 或 查SC 小王 1
    显示: 用户名、SC内容、时间、价格
    页码: 从0开始，每页10条，不指定则默认为0

    查用户SC <uid或昵称> [选项]
    查询用户发送过的SC列表
    示例：查用户SC 12345 /p 1 /r 又一 /s 2024-01-01 /e 2024-12-31
    
    可选参数:
    /p <页码>          - 页码，默认0，每页10条
    /r <主播uid或昵称> - 指定直播间（多个主播用逗号分隔），默认所有直播间
    /s <开始时间>      - 查询起始时间，格式: "YYYY-MM-DD"，默认半年前
    /e <结束时间>      - 查询结束时间，格式: "YYYY-MM-DD"，默认当前时间

    查用户舰长 <uid或昵称> [选项]
    查询用户上舰的记录
    示例：查用户舰长 12345 /p 0 /r 又一
    
    可选参数: 同上 (/p /r /s /e)
    显示: 用户名、舰长等级（总督/提督/舰长）、数量、时间、价格、直播间

    查用户弹幕 <uid或昵称> [选项]
    查询用户发送过的弹幕
    示例：查用户弹幕 12345 /p 0 /r 又一
    
    可选参数: 同上 (/p /r /s /e)
    显示: 用户名、弹幕内容、时间、直播间

    数据帮助
    显示此帮助信息"""
)


@command("数据帮助", "stats_help")
class RevenueHelpCommand(Command):
    """数据相关命令的帮助"""

    name = "stats_help"

    async def execute(self, message: Message, args: List[str]):

        await self.send_reply(message, revenue_help_str)


@command("revenue_v2")
class RevenueCommandV2(Command):
    name = "revenue_v2"
    cn_name = "查营收v2"
    max_num_uids = 5

    async def execute(self, message: Message, args: List[str]):
        _log.info(f"RevenueCommand args: {args}")
        if not args:
            await self.send_reply(message, "请输入要查询的主播uid或昵称")
        uid_or_nickname = args[0]
        uids = []
        if uid_or_nickname.isdigit():
            uid = int(uid_or_nickname)
            uids = [uid]
        elif uid_or_nickname.lower().startswith("uid:"):
            uid = int(uid_or_nickname[4:].strip())
            uids = [uid]
        else:
            # 是昵称
            dao = get_dao()
            uid = dao.get_uid_by_nickname(uid_or_nickname)
            if uid is not None:
                uids = [uid]
            else:
                # 模糊查找
                uids = dao.get_uids_by_nickname_like(uid_or_nickname)
                # 未找到
                if uids is None or not uids:
                    await self.send_reply(
                        message, f"未找到昵称为{uid_or_nickname}的主播"
                    )
                    return
        _log.info(f"uids: {uids}")
        res_str = ""
        uids = uids[: self.max_num_uids]
        for uid in uids:
            last_session_id = await get_last_session_id(uid)
            _log.info(f"last_session_id: {last_session_id}")
            name = await get_name_from_uid(uid)
            _log.info(f"name: {name}")
            if name is None:
                name = uid
            if last_session_id == ErrorCode.NO_LIVE_SESSIONS:
                # await self.send_reply(message, f"主播{name}没有直播记录")
                res_str += f"主播{name}没有直播记录\n\n"
                continue
            if last_session_id == ErrorCode.ERROR_FETCHING_DATA:
                # await self.send_reply(message, f"查询{name}的直播数据失败")
                res_str += f"查询{name}的直播数据失败\n\n"
                continue
            revenue = await get_session_revenue(last_session_id)
            revenue = revenue["revenue"]
            _log.info(f"revenue:\n{revenue}")

            session_info = await get_session_info(last_session_id)
            _log.info(f"session_info:\n{session_info}")
            if not session_info:
                # await self.send_reply(message, f"查询{name}的直播数据失败")
                res_str += f"查询{name}的直播数据失败\n\n"
                continue
            if not revenue:
                # await self.send_reply(message, f"查询{name}的直播数据失败")
                res_str += f"查询{name}的直播数据失败\n\n"
                continue

            guard_revenue = revenue.get("guards", 0)
            gift_revenue = revenue.get("gifts", 0)
            sc_revenue = revenue.get("super_chats", 0)
            total = revenue.get("total", 0)
            res_str += (
                f"主播{name}的最近一场直播营收:\n"
                f"直播标题:{session_info.get('title', '')}\n"
                f"直播时间:{session_info.get('start_time', '')}~{session_info.get('end_time', '')}\n"
                f"舰队收入: {round(guard_revenue, 2)}\n"
                f"礼物收入: {round(gift_revenue, 2)}\n"
                f"SC收入: {round(sc_revenue, 2)}\n"
                f"总收入: {round(total, 2)}\n\n"
            )

            await asyncio.sleep(1.0)  # 避免请求过快

        await self.send_reply(message, res_str.rstrip("\n"))


@command("super_chat_v2")
class SuperChatCommandV2(Command):
    PAGE_SIZE = 10
    name = "super_chat_v2"
    cn_name = "查SCv2"
    max_num_uids = 5

    async def execute(self, message: Message, args: List[str]):
        _log.info(f"SuperChatCommand args: {args}")
        if not args:
            await self.send_reply(message, "请输入要查询的主播uid或昵称")
        uid_or_nickname = args[0]
        num_page = 0 if len(args) < 2 else int(args[1])
        if num_page < 0:
            num_page = 0
        _log.info(f"num_page: {num_page}")
        uids = []
        if uid_or_nickname.isdigit():
            uid = int(uid_or_nickname)
            uids = [uid]
        elif uid_or_nickname.lower().startswith("uid:"):
            uid = int(uid_or_nickname[4:].strip())
            uids = [uid]
        else:
            # 是昵称
            dao = get_dao()
            uid = dao.get_uid_by_nickname(uid_or_nickname)
            if uid is not None:
                uids = [uid]
            else:
                # 模糊查找
                uids = dao.get_uids_by_nickname_like(uid_or_nickname)
                # 未找到
                if uids is None or not uids:
                    await self.send_reply(
                        message, f"未找到昵称为{uid_or_nickname}的主播"
                    )
                    return
        res_str = ""
        uids = uids[: self.max_num_uids]
        for uid in uids:
            name = await get_name_from_uid(uid)
            _log.info(f"uid: {uid}, name: {name}")
            if name is None:
                name = uid
            super_chats = await get_super_chats(
                uid,
                num_page * self.PAGE_SIZE,
                (num_page + 1) * self.PAGE_SIZE,
            )
            _log.info(f"super_chats:\n{super_chats}")

            res_str = (
                f"主播 {name}的最近 {num_page * self.PAGE_SIZE}~{(num_page + 1) * self.PAGE_SIZE}条SC:\n"
                f"格式为: 用户名:SC内容;时间;价格\n"
            )
            # for sc in super_chats:
            #     res_str += f"{sc['user_name']}: {sc['message']}; {sc['record_time']}; {sc['price']}\n"

            res_str += "\n".join(
                [
                    f"{sc['user_name']}: {sc['message']}; {sc['record_time']}; {sc['price']}"
                    for sc in super_chats
                ]
            )

            res_str += "\n\n"
            await asyncio.sleep(1.0)  # 避免请求过快
        await self.send_reply(message, res_str.rstrip("\n"))
