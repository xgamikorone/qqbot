from datetime import datetime
from enum import IntEnum
import os
from typing import List, Optional
import atexit
import asyncio

import aiohttp
from dotenv import load_dotenv

from botpy import logging

_log = logging.get_logger()
load_dotenv()
api_url = os.getenv("API_URL")
proxy = os.getenv("PROXY")
global_session = None


async def get_session():
    global global_session
    if global_session is None or global_session.closed:
        connector = aiohttp.TCPConnector(limit=50, limit_per_host=20)
        timeout = aiohttp.ClientTimeout(
            total=60, connect=20, sock_read=20, sock_connect=20
        )
        global_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return global_session


@atexit.register
def cleanup():
    if global_session and not global_session.closed:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(global_session.close())
        except RuntimeError:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(global_session.close())
                loop.close()
            except Exception:
                pass


async def get_tagged_streamers(tag_id: int) -> List[dict] | None:
    url = f"{api_url}/tag_users/{tag_id}"
    headers = {}
    try:
        session = await get_session()
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
    headers = {}
    try:
        session = await get_session()
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
    headers = {}
    try:
        session = await get_session()
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


async def get_num_followers(uids: List[int]):
    url = f"{api_url}/streamers_followers"
    headers = {}
    try:
        session = await get_session()
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


async def get_on_live_sessions():
    url = f"{api_url}/on_live_sessions_with_online_numbers"
    headers = {}
    try:
        session = await get_session()
        async with session.get(url, proxy=proxy, headers=headers) as response:
            data = await response.json()
            if not data:
                return None
            return data.get("data", None)

    except Exception as e:
        _log.error(f"Error getting on_live_sessions: {e}")
        return []


async def get_revenue_rank(month: str, filter: str):
    cur_month = datetime.now().strftime("%Y%m")
    is_cur_month = month == cur_month
    if is_cur_month:
        url = "https://dc.hihivr.top/gift"
    else:
        url = "https://dc.hihivr.top/gift/by_month"
    try:
        session = await get_session()
        async with session.get(
            url,
            params={"month": month, "filter": filter},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0"
            },
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data
            return None
    except aiohttp.ClientError as e:
        _log.error(f"Failed to get revenue rank: {e}")
        return None


class ErrorCode(IntEnum):
    NO_LIVE_SESSIONS = -1
    ERROR_FETCHING_DATA = -2


async def get_last_session_id(uid: int) -> int:
    url = f"{api_url}/live_sessions/{uid}"
    headers = {}
    try:
        session = await get_session()
        async with session.get(url, headers=headers, proxy=proxy) as response:
            data = await response.json()
            if data:
                live_sessions = data["live_sessions"]
                if not live_sessions:
                    return ErrorCode.NO_LIVE_SESSIONS
                return live_sessions[-1]["session_id"]
            return ErrorCode.NO_LIVE_SESSIONS
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return ErrorCode.ERROR_FETCHING_DATA


async def get_session_revenue(session_id: int) -> dict:
    url = f"{api_url}/live_revenue/{session_id}"
    headers = {}
    try:
        session = await get_session()
        async with session.get(url, headers=headers, proxy=proxy) as response:
            data = await response.json()
            if data:
                return data
            return {}
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return {}


async def get_session_info(session_id: int) -> dict:
    url = f"{api_url}/live_session_info/{session_id}"
    headers = {}
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
    headers = {}
    params = {"limit": 1, "sort": "asc"}
    try:
        session = await get_session()
        async with session.get(
            url, headers=headers, proxy=proxy, params=params
        ) as response:
            data = await response.json()
            if data:
                return data["count"]
            return 0
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return 0


async def get_super_chats(uid: int, start: int, end: int) -> list:
    url = f"{api_url}/streamer_super_chats/{uid}"
    headers = {}
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
    headers = {}
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
    headers = {}
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
    headers = {}
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
    headers = {}
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
    headers = {}
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

async def get_users_name_like(name: str) -> list[dict]:
    url = f"{api_url}/users_name_like"
    headers = {}
    try:
        session = await get_session()
        async with session.get(
            url,
            params={"name": name},
            proxy=proxy,
            headers=headers,
        ) as response:
            data = await response.json()
            if data:
                return data["data"]
            return []
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return []
    
async def get_bv_info(bv: str):
    url = f"{api_url}/bv_info"
    headers = {}
    try:
        session = await get_session()
        async with session.get(
            url,
            params={"bv": bv},
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