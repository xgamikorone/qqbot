import os
from commands.utils import is_admin
from .base import command, Command
from dao import get_dao
from botpy.message import Message
from botpy import logging
from typing import List
from textwrap import dedent
import aiohttp
from dotenv import load_dotenv

_log = logging.get_logger()
load_dotenv()
api_url = os.getenv("API_URL")
proxy = os.getenv("PROXY")

async def get_all_streamers() -> list | None:
    url = f"{api_url}/users"
    headers = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, proxy=proxy, headers=headers) as response:
                data = await response.json()
                if not data:
                    return None
                return data.get("users", None)
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return None
        

@command("收录主播", "all_streamers")
class AllStreamersCommand(Command):
    name = "all_streamers"
    cn_name = "收录主播"
    async def execute(self, message: Message, args: List[str]):
        streamers = await get_all_streamers()
        if not streamers or streamers is None:
            await self.send_reply(message, "获取主播列表时出错!")
            return
        
        res_str = f"已收录{len(streamers)}位主播，列表如下:\n"
        res_str += '\n'.join([
            f"{user['name']}: {user['uid']}" for user in streamers
        ])
        await self.send_reply(message, res_str)
        return