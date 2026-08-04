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
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from utils.time_utils import beijing_now

_log = logging.get_logger()

_log.info(f"共有{get_dao().wives.count_enabled()}个老婆")


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

def make_wife_thumbnail(source) -> Image.Image:
    """从文件路径或字节创建 160x160 的缩略图。"""
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        image = ImageOps.fit(image, (160, 160), method=Image.Resampling.LANCZOS)
        return image.copy()


async def load_wife_thumbnail(source: str) -> Image.Image | None:
    try:
        if source.startswith(("http://", "https://")):
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(source) as response:
                    response.raise_for_status()
                    data = await response.read()
                    if len(data) > 10 * 1024 * 1024:
                        return None
            return await asyncio.to_thread(make_wife_thumbnail, io.BytesIO(data))
        return await asyncio.to_thread(make_wife_thumbnail, source)
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError, UnidentifiedImageError):
        return None


def fit_table_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    suffix = "…"
    while text and draw.textbbox((0, 0), text + suffix, font=font)[2] > max_width:
        text = text[:-1]
    return text + suffix


async def build_wife_list_image(
    wives: list[dict], page: int, total_pages: int, total: int, title: str = "老婆列表"
) -> str:
    """生成老婆列表图片表格，并返回临时图片路径。"""
    thumbnails = await asyncio.gather(
        *(load_wife_thumbnail(wife.get("url") or "") for wife in wives)
    )

    width = 1100
    title_height = 90
    header_height = 64
    row_height = 180
    footer_height = 70
    height = title_height + header_height + row_height * len(wives) + footer_height
    table = Image.new("RGB", (width, height), "#f7f4ef")
    draw = ImageDraw.Draw(table)
    font_path = os.path.join("fonts", "simhei.ttf")
    title_font = ImageFont.truetype(font_path, 38)
    header_font = ImageFont.truetype(font_path, 28)
    body_font = ImageFont.truetype(font_path, 27)
    footer_font = ImageFont.truetype(font_path, 23)

    draw.rectangle((0, 0, width, title_height), fill="#49392f")
    draw.text((36, 24), title, font=title_font, fill="white")
    draw.text((width - 210, 32), f"第 {page}/{total_pages} 页", font=footer_font, fill="#eadfd5")

    columns = (0, 130, 600, 770, width)
    header_top = title_height
    draw.rectangle((0, header_top, width, header_top + header_height), fill="#d9c2ad")
    headers = (("ID", 65), ("名字", 365), ("状态", 685), ("缩略图", 935))
    for label, center_x in headers:
        box = draw.textbbox((0, 0), label, font=header_font)
        draw.text((center_x - (box[2] - box[0]) / 2, header_top + 15), label, font=header_font, fill="#34271f")

    for index, (wife, thumbnail) in enumerate(zip(wives, thumbnails)):
        top = header_top + header_height + index * row_height
        bottom = top + row_height
        draw.rectangle((0, top, width, bottom), fill="#fffdf9" if index % 2 == 0 else "#f0e8df")
        draw.line((0, bottom, width, bottom), fill="#cbb8a6", width=1)
        id_text = str(wife["id"])
        id_box = draw.textbbox((0, 0), id_text, font=body_font)
        draw.text((65 - (id_box[2] - id_box[0]) / 2, top + 72), id_text, font=body_font, fill="#352b25")
        name = fit_table_text(draw, wife.get("name") or "未命名", body_font, 410)
        draw.text((160, top + 72), name, font=body_font, fill="#352b25")
        status = "启用" if wife.get("enabled", 1) else "禁用"
        status_box = draw.textbbox((0, 0), status, font=body_font)
        status_color = "#287a45" if wife.get("enabled", 1) else "#a14343"
        draw.text((685 - (status_box[2] - status_box[0]) / 2, top + 72), status, font=body_font, fill=status_color)
        if thumbnail is not None:
            table.paste(thumbnail, (855, top + 10))
        else:
            draw.rounded_rectangle((855, top + 10, 1015, top + 170), radius=8, fill="#d8d2cc")
            missing_box = draw.textbbox((0, 0), "无图片", font=footer_font)
            draw.text((935 - (missing_box[2] - missing_box[0]) / 2, top + 78), "无图片", font=footer_font, fill="#756b64")

    for x in columns[1:-1]:
        draw.line((x, header_top, x, height - footer_height), fill="#bda995", width=2)
    footer_top = height - footer_height
    draw.rectangle((0, footer_top, width, height), fill="#49392f")
    footer = f"第 {page}/{total_pages} 页 · 共 {total} 个"
    draw.text((36, footer_top + 20), footer, font=footer_font, fill="white")

    output_path = os.path.join("imgs", f"wife_list_{uuid.uuid4().hex}.jpg")
    for quality in (88, 78, 68, 58):
        table.save(output_path, "JPEG", quality=quality, optimize=True)
        if os.path.getsize(output_path) <= MAX_WIFE_IMAGE_SIZE:
            return output_path
    os.remove(output_path)
    raise ValueError("老婆列表图片无法压缩到 1 MB 以内")

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

        wife_result = dao.wives.get_or_draw(
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

        wife_result = dao.wives.get_for_date(message.author.id, date_str)

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


@command("老婆列表", "wife_list")
class WifeListCommand(Command):
    name = "wife_list"
    cn_name = "老婆列表"

    async def execute(self, message: Message, args: List[str]):
        if len(args) > 1 or (args and (not args[0].isdigit() or int(args[0]) < 1)):
            await self.send_reply(message, "用法：/老婆列表 [页数]，页数必须是正整数。")
            return

        page = int(args[0]) if args else 1
        wives, total = get_dao().wives.get_page(page=page, page_size=10)
        if total == 0:
            await self.send_reply(message, "老婆列表为空。")
            return

        total_pages = (total + 9) // 10
        if page > total_pages:
            await self.send_reply(message, f"第 {page} 页不存在，当前共 {total_pages} 页。")
            return

        lines = [f"{wife['id']}：{wife.get('name') or '未命名'}" for wife in wives]
        fallback_text = (
            f"老婆列表（第 {page}/{total_pages} 页，共 {total} 个）：\n" + "\n".join(lines)
        )
        image_path = None
        try:
            image_path = await build_wife_list_image(wives, page, total_pages, total)
            await self.client.api.post_message(
                content=f"老婆列表（第 {page}/{total_pages} 页）",
                channel_id=message.channel_id,
                file_image=image_path,
                msg_id=message.id,
            )
            return
        except Exception as e:
            _log.exception(f"生成或发送老婆列表图片失败，改用文字回复: {e}")
        finally:
            if image_path and os.path.isfile(image_path):
                try:
                    os.remove(image_path)
                except OSError as e:
                    _log.warning(f"清理老婆列表临时图片失败: {e}")

        await self.send_reply(message, fallback_text)

@command("老婆详情", "按ID查老婆", "wife_by_id")
class WifeByIdCommand(Command):
    name = "wife_by_id"
    cn_name = "老婆详情"

    async def execute(self, message: Message, args: List[str]):
        if len(args) != 1 or not args[0].isdigit():
            await self.send_reply(message, "用法：/老婆详情 <id>")
            return
        wife = get_dao().wives.get_by_id(int(args[0]))
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
        wives = get_dao().wives.search_by_name(keyword)
        if not wives:
            await self.send_reply(message, f"没有找到名字包含“{keyword}”的老婆。")
            return
        lines = [
            f"{wife['id']}（{'启用' if wife['enabled'] else '禁用'}）：{wife.get('name') or '未命名'}"
            for wife in wives
        ]
        suffix = "\n最多显示 10 条。" if len(wives) == 10 else ""
        fallback_text = "查询结果：\n" + "\n".join(lines) + suffix
        image_path = None
        try:
            image_path = await build_wife_list_image(
                wives, 1, 1, len(wives), title="老婆查询结果"
            )
            await self.client.api.post_message(
                content=f"名字包含“{keyword}”的老婆",
                channel_id=message.channel_id,
                file_image=image_path,
                msg_id=message.id,
            )
            return
        except Exception as e:
            _log.exception(f"生成或发送老婆查询图片失败，改用文字回复: {e}")
        finally:
            if image_path and os.path.isfile(image_path):
                try:
                    os.remove(image_path)
                except OSError as e:
                    _log.warning(f"清理老婆查询临时图片失败: {e}")

        await self.send_reply(message, fallback_text)


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
        if not get_dao().wives.set_enabled(wife_id, states[state_text]):
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

        wife_id = get_dao().wives.add(name, local_path)
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
        old_wife = get_dao().wives.get_by_id(wife_id)
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

        if not get_dao().wives.update(wife_id, name=name, url=local_path):
            if local_path is not None:
                remove_local_wife_image(local_path)
            await self.send_reply(message, "更新失败，写入数据库时发生错误。")
            return

        if local_path is not None and old_wife.get("url") != local_path:
            remove_local_wife_image(old_wife.get("url"))
        await send_wife_card(self, message, get_dao().wives.get_by_id(wife_id), "更新成功")

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
