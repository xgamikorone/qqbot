import os
import logging
import typing

import aiohttp
from dotenv import load_dotenv

from . import base
from . import help_catalog
from . import text_query

_log = logging.getLogger(__name__)
load_dotenv()
api_url = os.getenv("API_URL")
proxy = os.getenv("PROXY")


class Streamer(typing.TypedDict):
    """Fields consumed from the external users endpoint."""

    uid: int | str
    name: str


async def get_all_streamers() -> list[Streamer] | None:
    """Validates the legacy untyped JSON boundary; None means query failure."""
    url = f"{api_url}/users"
    headers = {}
    try:
        timeout = aiohttp.ClientTimeout(total=20, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, proxy=proxy,
                                   headers=headers) as response:
                response.raise_for_status()
                data = await response.json()
                if not isinstance(data, dict):
                    return None
                users = data.get("users")
                if not isinstance(users, list):
                    return None
                streamers: list[Streamer] = []
                for user in users:
                    if not isinstance(user, dict):
                        return None
                    uid, name = user.get("uid"), user.get("name")
                    if (not isinstance(uid, (int, str)) or
                            isinstance(uid, bool) or not isinstance(name, str)):
                        return None
                    streamers.append({"uid": uid, "name": name})
                return streamers
    except (aiohttp.ClientError, TimeoutError, ValueError):
        # URLs and exception text may contain configuration/credentials.
        _log.warning("获取主播列表失败")
        return None


@base.command("所有主播", "收录主播", "all_streamers")
class AllStreamersCommand(text_query.TextQueryCommand):
    name = "all_streamers"
    cn_name = "收录主播"
    help = help_catalog.CommandHelp(title="所有主播",
                                    category="直播数据",
                                    summary="列出已收录主播及 UID",
                                    usage="/所有主播",
                                    examples=("/所有主播", "/收录主播"))

    async def query_and_reply(self, args: list[str],
                              reply: text_query.TextSender) -> bool:
        """Shares list rendering; the group transport splits long results."""
        streamers = await get_all_streamers()
        if streamers is None:
            await reply("获取主播列表时出错!")
            return False
        if not streamers:
            await reply("暂无收录主播。")
            return True

        res_str = f"已收录{len(streamers)}位主播，列表如下:\n"
        res_str += '\n'.join(
            [f"{user['name']}: {user['uid']}" for user in streamers])
        await reply(res_str)
        return True
