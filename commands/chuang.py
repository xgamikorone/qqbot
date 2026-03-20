from datetime import datetime
import random
from commands.utils import is_admin
from .base import command, Command
from dao import get_dao
from botpy.message import Message
from botpy import logging
from typing import List
from textwrap import dedent

_log = logging.get_logger()

# IMG_LOW = "https://pic2.ziyuan.wang/user/hanyuu1/2026/02/lt500_ed6a34b019d02.gif"
# IMG_HIGH = "https://pic2.ziyuan.wang/user/hanyuu1/2026/02/ge500_71e8b3a9b69c7.gif"
# IMG_BREAK = "https://pic2.ziyuan.wang/user/hanyuu1/2026/02/record_de6566a4f660d.png"

IMG_LOW = "https://i.imgs.ovh/2026/02/16/yuix7h.gif"
IMG_HIGH = "https://i.imgs.ovh/2026/02/16/yuiBAe.gif"
IMG_BREAK = "https://i.imgs.ovh/2026/02/16/yuiXJa.png"


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def biased_random(min_v=1, max_v=999, power=2.0):
    """
    power 越大，越偏向小数
    1.0 = 均匀随机
    2~3 = 比较平滑
    >3  = 很保守
    """
    r = random.random()              # [0,1)
    biased = r ** power
    value = min_v + biased * (max_v - min_v)
    return int(value)


@command("chuang", "开创")
class ChuangCommand(Command):
    name = "chuang"
    cn_name = "开创"

    async def execute(self, message: Message, args: List[str]):
        dao = get_dao()
        today = today_str()

        user_id = message.author.id
        nickname = message.author.username
        channel_id = message.channel_id
        guild_id = message.guild_id

        # 1️⃣ 查今天是否已经创过
        today_row = dao.get_today_chuang_distance(
            user_id, message.guild_id, today)

        _log.info(
            f"user_id: {user_id}, nickname: {nickname}, channel_id: {channel_id}, guild_id: {guild_id}, today: {today}, today_row: {today_row}")
        refreshed = False  # 是否刷新个人纪录

        if today_row is not None:
            distance = today_row
        else:
            distance = biased_random(power=2.5)

            # 2️⃣ 查询历史最高纪录（插入前）
            history_max = dao.get_chuang_history_max(user_id)

            if distance > history_max:
                refreshed = True

            dao.insert_chuang(user_id, distance, channel_id, guild_id, today)

        # 3️⃣ 今日群内排名
        today_rank = dao.get_today_chuang_rank_cur_guild(
            distance, message.guild_id, today)

        # 4️⃣ 历史排名（只有破纪录才算）
        history_rank = None
        if refreshed:
            history_rank = dao.get_chuang_history_rank_cur_guild(
                distance, message.guild_id)

        # 5️⃣ 选择图片（破纪录优先）
        if refreshed:
            img = IMG_BREAK
        elif distance >= 500:
            img = IMG_HIGH
        else:
            img = IMG_LOW

        # 6️⃣ 组装文案
        lines = [
            "注意！注意！瞳瞳车来咯~~~！",
            "",
            f"{nickname}今天被瞳瞳车创飞了{distance}米！",
            f"🏅 今日排名第{today_rank}名。",
        ]

        if refreshed:
            lines.extend([
                "",
                "🎉 恭喜你刷新了自己的最高纪录",
                f"🎊 达到{distance}米，历史排名第{history_rank}名。",
            ])

        msg = "\n".join(lines)

        # 7️⃣ 发送（先图后文 or 合并，看你习惯）
        await message.reply(
            content=msg,
            image=img,   # botpy 支持 image 参数
        )
