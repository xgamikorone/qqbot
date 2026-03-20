import aiohttp
from botpy.logging import logging

_log = logging.getLogger()

ALLOWED_CHANNELS = [723086974]


def is_admin(roles: list[str], admin_ids=(2, 4, 5)):
    return any(int(role) in admin_ids for role in roles)


async def get_name_from_uid(uid: int):
    url = "https://api.bilibili.com/x/web-interface/card"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, 
                                   params={"mid": uid},
                                   headers=headers) as response:
                data = await response.json()
                if data["code"] == 0:
                    return data["data"]["card"]["name"]
                return None
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return None
