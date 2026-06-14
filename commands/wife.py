import asyncio
import datetime
import os
import re
from commands.utils import is_admin, convert_str_to_date
from .base import command, Command
from dao import get_dao
from botpy.message import Message
from botpy import logging
from typing import List
from textwrap import dedent
import aiohttp
from utils.time_utils import beijing_now

_log = logging.get_logger()

_log.info(f"共有{get_dao().get_num_wives()}个老婆")


def parse_refresh_time(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None

    match = re.fullmatch(r"(\d{1,2})(?::(\d{1,2}))?", text)
    if not match:
        match = re.fullmatch(r"(\d{1,2})点(?:(\d{1,2})分?)?", text)

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    return f"{hour:02d}:{minute:02d}"


def format_remaining_time(seconds: int) -> str:
    minutes = max(1, (seconds + 59) // 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}小时{minutes}分钟"
    return f"{minutes}分钟"


def get_today_refresh_time(refresh_time: str):
    hour, minute = map(int, refresh_time.split(":"))
    now = beijing_now()
    return now, now.replace(hour=hour, minute=minute, second=0, microsecond=0)


@command("来个老婆", "wife")
class WifeCommand(Command):
    name = "wife"
    cn_name = "来个老婆"

    async def execute(self, message: Message, args: List[str]):

        dao = get_dao()
        refresh_time = dao.get_wife_refresh_time()
        now, today_refresh_time = get_today_refresh_time(refresh_time)
        if now < today_refresh_time:
            remaining_seconds = int((today_refresh_time - now).total_seconds())
            await self.send_reply(
                message,
                f"<@!{message.author.id}>, 还没有到今日老婆刷新时间哦！刷新时间：{refresh_time}，还要等{format_remaining_time(remaining_seconds)}。",
            )
            return

        wife_result = dao.get_wife(
            message.author.id, message.channel_id, message.guild_id
        )

        if not wife_result:
            await self.send_reply(
                message, f"<@!{message.author.id}>, 获取老婆失败，请稍后再试！"
            )
            return

        url = wife_result.get("url", "")
        if not url:
            await self.send_reply(
                message, f"<@!{message.author.id}>, 获取老婆失败，请稍后再试！"
            )
            return
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                await self.client.api.post_message(
                    content=f"<@!{message.author.id}>, 你的今日老婆：{wife_result['name']}",
                    channel_id=message.channel_id,
                    file_image=url,
                    msg_id=message.id,
                )
                break  # 成功就退出循环

            except Exception as e:
                _log.warning(f"发送老婆图片失败，第{attempt}次重试: {e}")

                if attempt == max_retries:
                    _log.error("发送老婆图片最终失败")
                    await self.send_reply(
                        message,
                        f"<@!{message.author.id}>, 图片发送失败，你的老婆是：{wife_result['name']}！",
                    )
                else:
                    await asyncio.sleep(1)  # 每次失败后等1秒再试


@command("我的老婆")
class MyWifeCommand(Command):
    name = "my_wife"
    cn_name = "我的老婆"

    async def execute(self, message: Message, args: List[str]):
        dao = get_dao()

        if not args:
            date_str = datetime.date.today().strftime("%Y-%m-%d")
        else:
            arg = args[0]
            date = convert_str_to_date(arg)
            if date is None:
                await self.send_reply(
                    message,
                    f"<@!{message.author.id}>, 无法解析日期, 请使用相对时间(如:今天、昨天、前天、N天前)或绝对时间(如:2024-06-01)!",
                )
                return
            date_str = date.strftime("%Y-%m-%d")

        wife_result = dao.get_user_wife_certain_date(message.author.id, date_str)

        if not wife_result:
            await self.send_reply(
                message, f"<@!{message.author.id}>, 你在{date_str}没有老婆哦！"
            )
            return

        url = wife_result.get("url", "")
        await self.client.api.post_message(
            content=f"<@!{message.author.id}>, 你在{date_str}的老婆是：{wife_result['name']}!",
            channel_id=message.channel_id,
            file_image=url,
            msg_id=message.id,
        )
        return


@command("老婆刷新时间", "设置老婆刷新时间", "wife_refresh_time", "set_wife_refresh_time")
class WifeRefreshTimeCommand(Command):
    name = "wife_refresh_time"
    cn_name = "老婆刷新时间"

    async def execute(self, message: Message, args: List[str]):
        dao = get_dao()
        current_refresh_time = dao.get_wife_refresh_time()

        if not args or args[0] in ("查看", "查询", "current"):
            await self.send_reply(message, f"当前老婆刷新时间：{current_refresh_time}")
            return

        roles = getattr(message.member, "roles", None)
        if not roles or not is_admin(roles):
            await self.send_reply(message, "该功能仅管理员可用！")
            return

        refresh_time = parse_refresh_time(args[0])
        if refresh_time is None:
            await self.send_reply(
                message,
                "格式错误，应为 /设置老婆刷新时间 <HH:MM>，例如：/设置老婆刷新时间 08:00",
            )
            return

        if dao.set_wife_refresh_time(refresh_time):
            await self.send_reply(message, f"老婆刷新时间已设置为：{refresh_time}")
        else:
            await self.send_reply(message, "设置老婆刷新时间失败，请稍后再试！")
