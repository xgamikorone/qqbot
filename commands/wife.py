import asyncio
import io
import os
import re
import uuid
from commands.utils import is_admin, convert_str_to_date
from .base import command, Command
from dao import get_dao
from botpy.message import Message
from botpy import logging
from typing import List
from textwrap import dedent
import aiohttp
from PIL import Image, ImageOps, UnidentifiedImageError
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


def get_attachment_url(message: Message) -> str | None:
    attachments = getattr(message, "attachments", None) or []
    if not attachments:
        return None
    url = getattr(attachments[0], "url", "")
    if url and not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url or None


def is_image_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


MAX_WIFE_IMAGE_SIZE = 1024 * 1024
MAX_WIFE_DOWNLOAD_SIZE = 20 * 1024 * 1024


def save_wife_image(data: bytes, extension: str) -> str:
    """验证图片并保存；超过 1 MB 时逐步压缩为 JPEG。"""
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.verify()
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)
            image.load()
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError("下载内容不是有效图片") from e

    image_dir = os.path.join("imgs", "wives")
    os.makedirs(image_dir, exist_ok=True)

    if len(data) <= MAX_WIFE_IMAGE_SIZE:
        relative_path = os.path.join(image_dir, f"{uuid.uuid4().hex}{extension}")
        with open(relative_path, "wb") as image_file:
            image_file.write(data)
        return relative_path.replace(os.sep, "/")

    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba_image = image.convert("RGBA")
        rgb_image = Image.new("RGB", rgba_image.size, "white")
        rgb_image.paste(rgba_image, mask=rgba_image.getchannel("A"))
        image = rgb_image
    else:
        image = image.convert("RGB")

    while True:
        for quality in (85, 75, 65, 55, 45, 35, 25, 15):
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=quality, optimize=True)
            compressed = output.getvalue()
            if len(compressed) <= MAX_WIFE_IMAGE_SIZE:
                relative_path = os.path.join(image_dir, f"{uuid.uuid4().hex}.jpg")
                with open(relative_path, "wb") as image_file:
                    image_file.write(compressed)
                return relative_path.replace(os.sep, "/")

        width, height = image.size
        if width <= 64 and height <= 64:
            raise ValueError("图片无法压缩到 1 MB 以内")
        image.thumbnail((max(64, int(width * 0.8)), max(64, int(height * 0.8))), Image.Resampling.LANCZOS)


def remove_local_wife_image(path: str | None) -> None:
    """只删除 imgs/wives 目录内的本地图片。"""
    if not path or path.startswith(("http://", "https://")):
        return

    image_dir = os.path.realpath(os.path.join("imgs", "wives"))
    target = os.path.realpath(path)
    try:
        is_in_wife_dir = os.path.commonpath((image_dir, target)) == image_dir
    except ValueError:
        return

    if is_in_wife_dir and target != image_dir and os.path.isfile(target):
        try:
            os.remove(target)
        except OSError as e:
            _log.warning(f"删除旧老婆图片失败: {target}, error: {e}")

async def download_wife_image(url: str) -> str:
    """下载并压缩老婆图片，返回用于写入数据库的相对路径。"""
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_WIFE_DOWNLOAD_SIZE:
                raise ValueError("原始图片不能超过 20 MB")

            data = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                data.extend(chunk)
                if len(data) > MAX_WIFE_DOWNLOAD_SIZE:
                    raise ValueError("原始图片不能超过 20 MB")

            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            extensions = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "image/webp": ".webp",
                "image/bmp": ".bmp",
            }
            extension = extensions.get(content_type)
            if extension is None:
                extension = os.path.splitext(url.split("?", 1)[0])[1].lower()
                if extension not in extensions.values():
                    raise ValueError("下载内容不是支持的图片格式")

    return await asyncio.to_thread(save_wife_image, bytes(data), extension)

async def send_wife_card(command: Command, message: Message, wife: dict, title: str):
    status = "启用" if wife.get("enabled", 1) else "禁用"
    await command.client.api.post_message(
        content=f"{title}\nID：{wife['id']}\n名字：{wife.get('name') or '未命名'}\n状态：{status}",
        channel_id=message.channel_id,
        file_image=wife["url"],
        msg_id=message.id,
    )

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
            date_str = beijing_now().strftime("%Y-%m-%d")
        else:
            arg = args[0]
            date = convert_str_to_date(arg, today=beijing_now().date())
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


@command("老婆详情", "按ID查老婆", "wife_by_id")
class WifeByIdCommand(Command):
    name = "wife_by_id"
    cn_name = "老婆详情"

    async def execute(self, message: Message, args: List[str]):
        if len(args) != 1 or not args[0].isdigit():
            await self.send_reply(message, "用法：/老婆详情 <id>")
            return
        wife = get_dao().get_wife_by_id(int(args[0]))
        if not wife:
            await self.send_reply(message, f"没有找到 ID 为 {args[0]} 的老婆。")
            return
        await send_wife_card(self, message, wife, "查询结果")


@command("查老婆", "查询老婆", "搜索老婆", "wife_search")
class SearchWifeCommand(Command):
    name = "search_wife"
    cn_name = "查老婆"

    async def execute(self, message: Message, args: List[str]):
        keyword = " ".join(args).strip()
        if not keyword:
            await self.send_reply(message, "用法：/查老婆 <名字关键字>")
            return
        wives = get_dao().search_wives_by_name(keyword)
        if not wives:
            await self.send_reply(message, f"没有找到名字包含“{keyword}”的老婆。")
            return
        lines = [
            f"{wife['id']}（{'启用' if wife['enabled'] else '禁用'}）：{wife.get('name') or '未命名'}"
            for wife in wives
        ]
        suffix = "\n最多显示 50 条。" if len(wives) == 50 else ""
        await self.send_reply(message, "查询结果：\n" + "\n".join(lines) + suffix)


@command("设置老婆状态", "wife_enable")
class SetWifeEnabledCommand(Command):
    name = "set_wife_enabled"
    cn_name = "设置老婆状态"
    owner_only = True

    async def execute(self, message: Message, args: List[str]):
        if len(args) < 2 or not args[0].isdigit():
            await self.send_reply(message, "用法：/设置老婆状态 <id> <启用|禁用>")
            return
        states = {
            "启用": True, "开启": True, "1": True, "true": True, "on": True,
            "禁用": False, "关闭": False, "0": False, "false": False, "off": False,
        }
        state_text = args[1].lower()
        if state_text not in states:
            await self.send_reply(message, "状态只能是“启用”或“禁用”。")
            return
        wife_id = int(args[0])
        if not get_dao().set_wife_enabled(wife_id, states[state_text]):
            await self.send_reply(message, f"设置失败：ID {wife_id} 不存在。")
            return
        await self.send_reply(message, f"已{'启用' if states[state_text] else '禁用'}老婆 ID {wife_id}。")


@command("增加老婆", "添加老婆", "wife_add")
class AddWifeCommand(Command):
    name = "add_wife"
    cn_name = "增加老婆"
    owner_only = True

    async def execute(self, message: Message, args: List[str]):
        url = get_attachment_url(message)
        name_args = args
        if not url and args and is_image_url(args[-1]):
            url = args[-1]
            name_args = args[:-1]
        name = " ".join(name_args).strip()
        if not name or not url:
            await self.send_reply(message, "用法：/增加老婆 <名字> <图片URL>，也可以发送图片附件。")
            return
        try:
            local_path = await download_wife_image(url)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError) as e:
            _log.warning(f"下载老婆图片失败: {e}")
            await self.send_reply(message, f"增加失败：图片下载失败（{e}）。")
            return

        wife_id = get_dao().add_wife(name, local_path)
        if wife_id is None:
            try:
                os.remove(local_path)
            except OSError:
                _log.warning(f"清理老婆图片失败: {local_path}")
            await self.send_reply(message, "增加失败，写入数据库时发生错误。")
            return
        await self.send_reply(message, f"增加成功：ID {wife_id}，名字：{name}。")


@command("更新老婆", "修改老婆", "wife_update")
class UpdateWifeCommand(Command):
    name = "update_wife"
    cn_name = "更新老婆"
    owner_only = True

    async def execute(self, message: Message, args: List[str]):
        if not args or not args[0].isdigit():
            await self.send_reply(message, "用法：/更新老婆 <id> <新名字或-> [新图片URL]；也可以发送图片附件。")
            return
        wife_id = int(args[0])
        old_wife = get_dao().get_wife_by_id(wife_id)
        if not old_wife:
            await self.send_reply(message, f"更新失败：ID {wife_id} 不存在。")
            return
        url = get_attachment_url(message)
        remaining = args[1:]
        if not url and remaining and is_image_url(remaining[-1]):
            url = remaining[-1]
            remaining = remaining[:-1]
        name_text = " ".join(remaining).strip()
        name = None if not name_text or name_text == "-" else name_text
        if name is None and url is None:
            await self.send_reply(message, "请至少提供一个新名字或一张新图片。")
            return

        local_path = None
        if url is not None:
            try:
                local_path = await download_wife_image(url)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError) as e:
                _log.warning(f"下载或压缩老婆图片失败: {e}")
                await self.send_reply(message, f"更新失败：图片处理失败（{e}）。")
                return

        if not get_dao().update_wife(wife_id, name=name, url=local_path):
            if local_path is not None:
                remove_local_wife_image(local_path)
            await self.send_reply(message, "更新失败，写入数据库时发生错误。")
            return

        if local_path is not None and old_wife.get("url") != local_path:
            remove_local_wife_image(old_wife.get("url"))
        await send_wife_card(self, message, get_dao().get_wife_by_id(wife_id), "更新成功")

@command("老婆刷新时间", "设置老婆刷新时间", "wife_refresh_time", "set_wife_refresh_time")
class WifeRefreshTimeCommand(Command):
    name = "wife_refresh_time"
    cn_name = "老婆刷新时间"
    owner_only = True

    async def execute(self, message: Message, args: List[str]):
        dao = get_dao()
        current_refresh_time = dao.get_wife_refresh_time()

        if not args or args[0] in ("查看", "查询", "current"):
            await self.send_reply(message, f"当前老婆刷新时间：{current_refresh_time}")
            return

        roles = getattr(message.member, "roles", None)
        

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

