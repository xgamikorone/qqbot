import asyncio
import logging

from commands.user import get_all_streamers
from dao import get_dao


logger = logging.getLogger(__name__)


async def add_default_nicknames() -> int:
    users = await get_all_streamers()
    if users is None:
        raise RuntimeError("cannot fetch all streamers")

    dao = get_dao()
    added_count = 0
    for user in users:
        uid = user["uid"]
        nickname = user["name"]
        if dao.nicknames.add(uid, nickname):
            added_count += 1

    logger.info(
        "default nickname sync completed: fetched=%d, added=%d, skipped=%d",
        len(users),
        added_count,
        len(users) - added_count,
    )
    return added_count


if __name__ == "__main__":
    count = asyncio.run(add_default_nicknames())
    print(f"同步完成，新增 {count} 个默认昵称。")
