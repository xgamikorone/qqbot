import random
from .base import command, Command
from dao import get_dao
from botpy.message import Message
from botpy import logging
from typing import List
from botpy import message as botpy_message
from messaging import command_replies
from . import help_catalog
from utils.time_utils import beijing_now_str

_log = logging.get_logger()

# IMG_LOW = "https://pic2.ziyuan.wang/user/hanyuu1/2026/02/lt500_ed6a34b019d02.gif"
# IMG_HIGH = "https://pic2.ziyuan.wang/user/hanyuu1/2026/02/ge500_71e8b3a9b69c7.gif"
# IMG_BREAK = "https://pic2.ziyuan.wang/user/hanyuu1/2026/02/record_de6566a4f660d.png"

IMG_LOW = "imgs/chuang/low.gif"
IMG_HIGH = "imgs/chuang/high.gif"
IMG_BREAK = "imgs/chuang/break.png"


def today_str() -> str:
    """Returns the current Beijing calendar date."""
    return beijing_now_str("%Y-%m-%d")


def biased_random(
    min_v: int = 1,
    max_v: int = 999,
    power: float = 27.0,
    uniform_weight: float = 0.6,
) -> int:
    """
    用均匀与偏小分布的混合曲线生成随机数。

    uniform_weight 让低数值区间保持较均匀；power 让高数值逐渐稀少。
    """
    r = random.random()              # [0,1)
    scaled = uniform_weight * r + (1 - uniform_weight) * (r ** power)
    value = min_v + scaled * (max_v - min_v + 1)
    return int(value)


@command("chuang", "开创")
class ChuangCommand(Command):
    supported_scenes = frozenset({"guild", "group"})
    name = "chuang"
    cn_name = "开创"
    help = help_catalog.CommandHelp(
        title="开创",
        category="娱乐",
        summary="查看今天被瞳瞳车创飞的距离",
        usage="/开创",
        examples=("/开创",),
        details="群聊按群和成员每日独立生成结果；重复查询保持当天距离，排名按当前记录计算。",
    )

    async def execute_group(
        self, message: botpy_message.GroupMessage, args: list[str]
    ) -> bool:
        """Creates or replays this member's result within the current group."""
        nickname = await self.group_display_name(message) or "一位朋友"
        result = get_dao().group_chuang.get_or_create(
            command_replies.require_id(message.group_openid),
            command_replies.require_id(message.author.member_openid),
            today_str(),
            biased_random,
        )
        image = (
            IMG_BREAK
            if result.personal_record
            else (IMG_HIGH if result.distance >= 500 else IMG_LOW)
        )
        lines = [
            "注意！注意！瞳瞳车来咯~~~！",
            "",
            f"{nickname}今天被瞳瞳车创飞了{result.distance}米！",
            f"🏅 今日排名第{result.daily_rank}名。",
        ]
        if result.personal_record:
            lines.extend(
                [
                    "",
                    "🎉 恭喜你刷新了自己的最高纪录",
                    f"🎊 达到{result.distance}米，历史排名第{result.history_rank}名。",
                ]
            )
        content = "\n".join(lines)
        try:
            await self.reply_group_local_image(message, image, content)
        except command_replies.GroupImageUploadError:
            await self.reply_group(message, content + "\n图片暂时无法加载。")
        return True

    async def execute(self, message: Message, args: List[str]) -> None:
        """Preserves the original channel game and record semantics."""
        dao = get_dao()
        today = today_str()

        user_id = message.author.id
        nickname = message.author.username
        channel_id = message.channel_id
        guild_id = message.guild_id

        # 1️⃣ 查今天是否已经创过
        today_row = dao.chuang.get_distance(user_id, today)

        _log.info(
            f"user_id: {user_id}, nickname: {nickname}, channel_id: {channel_id}, guild_id: {guild_id}, today: {today}, today_row: {today_row}")
        refreshed = False  # 是否刷新个人纪录

        if today_row is not None:
            distance = today_row
        else:
            distance = biased_random()

            # 2️⃣ 查询历史最高纪录（插入前）
            history_max = dao.chuang.get_history_max(user_id)

            if distance > history_max:
                refreshed = True

            dao.chuang.record(user_id, distance, channel_id, guild_id, today)

        # 3️⃣ 今日群内排名
        today_rank = dao.chuang.get_daily_rank(
            distance, message.guild_id, today)

        # 4️⃣ 历史排名（只有破纪录才算）
        history_rank = None
        if refreshed:
            history_rank = dao.chuang.get_history_rank(
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
            file_image=img,   # botpy 支持 image 参数
        )
