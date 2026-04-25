import datetime
import re
from typing import Optional

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
            async with session.get(
                url, params={"mid": uid}, headers=headers
            ) as response:
                data = await response.json()
                if data["code"] == 0:
                    return data["data"]["card"]["name"]
                return None
    except Exception as e:
        _log.exception(f"Error fetching data from {url}: {e}")
        return None


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = datetime.date(year + 1, 1, 1)
    else:
        next_month = datetime.date(year, month + 1, 1)
    return (next_month - datetime.timedelta(days=1)).day

TODAY_STRS = ["今天", "today", "今日", "本日"]
YESTERDAY_STRS = ["昨天", "yesterday", "昨日"]

def convert_str_to_date(date_str: str) -> Optional[datetime.date]:
    date_str = date_str.strip()
    today = datetime.date.today()

    # ===== 1. 相对时间 =====
    if date_str in TODAY_STRS:
        return today
    if date_str in YESTERDAY_STRS:
        return today - datetime.timedelta(days=1)
    if date_str == "前天":
        return today - datetime.timedelta(days=2)

    # N天前 / N天后
    m = re.match(r"(\d+)天(前|后)", date_str)
    if m:
        n = int(m.group(1))
        if m.group(2) == "前":
            return today - datetime.timedelta(days=n)
        else:
            return today + datetime.timedelta(days=n)

    # N周前 / N周后
    m = re.match(r"(\d+)周(前|后)", date_str)
    if m:
        n = int(m.group(1))
        delta = datetime.timedelta(weeks=n)
        return today - delta if m.group(2) == "前" else today + delta

    # N个月前 / N个月后（简单实现）
    m = re.match(r"(\d+)个?月(前|后)", date_str)
    if m:
        n = int(m.group(1))
        month = today.month - n if m.group(2) == "前" else today.month + n
        year = today.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = min(today.day, _days_in_month(year, month))
        return datetime.date(year, month, day)

    # N年前 / N年后
    m = re.match(r"(\d+)年(前|后)", date_str)
    if m:
        n = int(m.group(1))
        year = today.year - n if m.group(2) == "前" else today.year + n
        return today.replace(year=year)

    # ===== 2. 中文日期 =====
    # 2024年3月15日
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", date_str)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # 3月15日（默认今年）
    m = re.match(r"(\d{1,2})月(\d{1,2})日?", date_str)
    if m:
        return datetime.date(today.year, int(m.group(1)), int(m.group(2)))

    # ===== 3. 标准格式 =====
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    # ===== 4. 不带年份（默认今年）=====
    for fmt in ("%m-%d", "%m/%d", "%m.%d"):
        try:
            d = datetime.datetime.strptime(date_str, fmt)
            return datetime.date(today.year, d.month, d.day)
        except ValueError:
            continue

    return None
