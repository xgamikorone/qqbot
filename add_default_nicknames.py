import asyncio

from commands.user import get_all_streamers
from dao import get_dao

async def add_default_nicknames():
    users = await get_all_streamers()
    if users is None:
        print("Cannot fetch all streamers!")
        return
    
    dao = get_dao()
    for user in users:
        uid = user["uid"]
        nickname = user["name"]
        success = dao.add_nickname(user["uid"], user["name"])
        print(f"为uid {uid}添加昵称 {nickname}，成功? {success}")

if __name__ == '__main__':
    # run the coroutine
    asyncio.run(add_default_nicknames())
    