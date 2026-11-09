"""Group wife presentation with shared images and isolated daily records."""

import collections.abc
import os
import logging

from botpy import message as botpy_message

import dao
from database.repositories import group_wife_repository
from messaging import command_replies
from utils import time_utils
from . import base
from . import text_query
from . import utils

_LOG = logging.getLogger(__name__)


def _asset(
    value: collections.abc.Mapping[str, object],
) -> group_wife_repository.WifeAsset:
    """Converts the legacy catalog dictionary at its untyped boundary."""
    identifier, url = value.get("id"), value.get("url")
    if not isinstance(identifier, int) or not isinstance(url, str):
        raise ValueError("无效的老婆资源")
    name = value.get("name")
    return group_wife_repository.WifeAsset(
        identifier,
        name if isinstance(name, str) and name else "未命名",
        url,
        bool(value.get("enabled", True)),
    )


async def _text(
    command: base.Command, message: botpy_message.GroupMessage, content: str
) -> None:
    for chunk in text_query.split_group_text(content):
        await command.reply_group(message, chunk)


async def _image(
    command: base.Command,
    message: botpy_message.GroupMessage,
    content: str,
    url: str,
) -> None:
    """Falls back only before a send attempt; resource files are never deleted."""
    try:
        if url.startswith(("https://", "http://")):
            await command.reply_group_image(message, content, url)
        else:
            await command.reply_group_local_image(message, url, content)
    except command_replies.GroupImageUploadError:
        await _text(command, message, content + "\n图片暂时无法加载。")


async def draw_daily(
    command: base.Command, message: botpy_message.GroupMessage, args: list[str]
) -> bool:
    """Applies the shared refresh gate before atomically assigning today's wife."""
    # Lazy import reuses legacy rendering without a module initialization cycle.
    from . import wife

    database = dao.get_dao()
    refresh = database.settings.get_wife_refresh_time(
        "group", command_replies.require_id(message.group_openid)
    )
    now, threshold = wife.get_today_refresh_time(refresh)
    name = await command.group_display_name(message) or "一位朋友"
    if now < threshold:
        remaining = wife.format_remaining_time(
            int((threshold - now).total_seconds())
        )
        await _text(
            command,
            message,
            f"{name}, 还没有到今日老婆刷新时间哦！刷新时间：{refresh}，还要等{remaining}。",
        )
        return False
    result = database.group_wives.get_or_draw(
        command_replies.require_id(message.group_openid),
        command_replies.require_id(message.author.member_openid),
        now.strftime("%Y-%m-%d"),
    )
    if result is None:
        await _text(command, message, f"{name}, 获取老婆失败，请稍后再试！")
        return False
    await _image(
        command, message, f"{name}, 你的今日老婆：{result.name}", result.url
    )
    return True


async def history(
    command: base.Command, message: botpy_message.GroupMessage, args: list[str]
) -> bool:
    """Queries this member's history in this group without drawing a result."""
    today = time_utils.beijing_now().date()
    date = utils.convert_str_to_date(args[0], today=today) if args else today
    if date is None or len(args) > 1:
        await _text(
            command,
            message,
            "无法解析日期，请使用 /我的老婆 [今天、昨天、N天前或 YYYY-MM-DD]。",
        )
        return False
    date_str = date.strftime("%Y-%m-%d")
    name = await command.group_display_name(message) or "一位朋友"
    result = dao.get_dao().group_wives.get_for_date(
        command_replies.require_id(message.group_openid),
        command_replies.require_id(message.author.member_openid),
        date_str,
    )
    if result is None:
        await _text(command, message, f"{name}, 你在{date_str}没有老婆哦！")
        return True
    await _image(
        command,
        message,
        f"{name}, 你在{date_str}的老婆是：{result.name}!",
        result.url,
    )
    return True


async def detail(
    command: base.Command, message: botpy_message.GroupMessage, args: list[str]
) -> bool:
    """Shows a shared catalog resource without assigning it to a member."""
    if len(args) != 1 or not args[0].isdigit():
        await _text(command, message, "用法：/老婆详情 <id>")
        return False
    row = dao.get_dao().wives.get_by_id(int(args[0]))
    if not row:
        await _text(command, message, f"没有找到 ID 为 {args[0]} 的老婆。")
        return False
    resource = _asset(row)
    await _image(
        command,
        message,
        f"查询结果\nID：{resource.id}\n名字：{resource.name}\n状态：{'启用' if resource.enabled else '禁用'}",
        resource.url,
    )
    return True


async def catalog(
    command: base.Command,
    message: botpy_message.GroupMessage,
    args: list[str],
    *,
    search: bool = False,
) -> bool:
    """Renders a catalog/search table and always cleans its temporary image."""
    from . import wife

    page = 1
    if search:
        keyword = " ".join(args).strip()
        if not keyword:
            await _text(command, message, "用法：/查老婆 <名字关键字>")
            return False
        rows = dao.get_dao().wives.search_by_name(keyword)
        total = len(rows)
        title = "老婆查询结果"
    else:
        if len(args) > 1 or (
            args and (not args[0].isdigit() or int(args[0]) < 1)
        ):
            await _text(
                command, message, "用法：/老婆列表 [页数]，页数必须是正整数。"
            )
            return False
        page = int(args[0]) if args else 1
        rows, total = dao.get_dao().wives.get_page(page=page, page_size=10)
        title = "老婆列表"
    if total == 0:
        await _text(
            command,
            message,
            "没有找到匹配的老婆。" if search else "老婆列表为空。",
        )
        return True
    pages = (total + 9) // 10
    if page > pages:
        await _text(
            command, message, f"第 {page} 页不存在，当前共 {pages} 页。"
        )
        return False
    fallback = f"{title}（第 {page}/{pages} 页，共 {total} 个）：\n" + "\n".join(
        f"{row['id']}（{'启用' if row.get('enabled', 1) else '禁用'}）：{row.get('name') or '未命名'}"
        for row in rows
    )
    if search and len(rows) == 10:
        fallback += "\n最多显示 10 条。"
    path = None
    try:
        try:
            path = await wife.build_wife_list_image(
                rows, page, pages, total, title=title
            )
        except Exception:
            await _text(command, message, fallback)
            return True
        # Keep the full list in fallback if only uploading fails. A failed
        # send may already have delivered and must not resend the table.
        try:
            await command.reply_group_local_image(
                message, path, f"{title}（第 {page}/{pages} 页）"
            )
        except command_replies.GroupImageUploadError:
            await _text(command, message, fallback)
        return True
    finally:
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                _LOG.warning("清理群老婆列表临时图片失败")
