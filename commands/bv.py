"""BV lookup with native channel images and uploaded group rich media."""

import dataclasses
import datetime
import logging
import textwrap
import typing

from botpy import message as botpy_message

from integrations import live_data
from messaging import command_replies
from utils import async_retry
from . import base
from . import help_catalog

_log = logging.getLogger(__name__)


class VideoStats(typing.TypedDict):
    """Counters consumed from the upstream video response."""

    view: int
    danmaku: int
    like: int
    reply: int
    favorite: int


class VideoOwner(typing.TypedDict):
    """Uploader fields used in the reply."""

    name: str


class VideoData(typing.TypedDict):
    """Required fields from the legacy upstream JSON interface."""

    title: str
    pic: str
    pubdate: int
    owner: VideoOwner
    stat: VideoStats
    bvid: str


class VideoResponse(typing.TypedDict, total=False):
    """Upstream success or business error response."""

    code: int
    message: str
    data: VideoData


@dataclasses.dataclass(frozen=True)
class VideoReply:
    """Transport-independent video presentation."""

    content: str
    image: str


async def get_bv_info_with_retry(
        bv: str,
        max_attempts: int = 3,
        retry_delay: float = 1.0) -> VideoResponse | None:
    """Retries empty upstream responses without retrying business errors."""
    response = await async_retry.retry_empty(
        lambda: live_data.get_bv_info(bv),
        max_attempts=max_attempts,
        retry_delay=retry_delay,
        on_retry=lambda attempt, total: _log.warning(
            "查询 BV 失败，第 %s/%s 次尝试，即将重试", attempt, total),
    )
    if not isinstance(response, dict):
        return None
    # The legacy HTTP client returns untyped JSON. Rendering below guards
    # missing fields and invalid timestamps at this external boundary.
    return typing.cast(VideoResponse, response)


def build_video_reply(data: VideoData) -> VideoReply:
    """Renders shared video metadata in Beijing time."""
    zone = datetime.timezone(datetime.timedelta(hours=8))
    pubdate = datetime.datetime.fromtimestamp(data["pubdate"], tz=zone)
    stat = data["stat"]
    content = textwrap.dedent(f"""\
        标题: {data['title']}
        up主: {data['owner']['name']}
        view: {stat['view']}, danmaku: {stat['danmaku']}, like: {stat['like']}
        reply: {stat['reply']}, favorite: {stat['favorite']}
        bv号: {data['bvid']}
        发布时间: {pubdate.strftime('%Y-%m-%d %H:%M:%S')}
    """)
    image = data["pic"]
    if not isinstance(image, str) or not image:
        raise ValueError("视频缺少封面地址")
    return VideoReply(content, image)


@base.command("查bv", "查BV", "查视频")
class SearchBVCommand(base.Command):
    supported_scenes = frozenset({"guild", "group"})
    name = "bv"
    cn_name = "bv"
    help = help_catalog.CommandHelp(
        title="查BV",
        category="直播数据",
        summary="查询视频信息和封面",
        usage="/查bv <BV号>",
        examples=("/查bv BV1xx411c7mD",),
    )

    async def query_video(self, args: list[str]) -> VideoReply | str:
        """Returns video presentation or a user-facing validation error."""
        if not args:
            return "请输入要查询的BV号!"
        response = await get_bv_info_with_retry("".join(args))
        if not response or response.get("code") != 0:
            error = response.get("message", "未知错误") if response else "未知错误"
            return f"查询遇到错误, {error}"
        try:
            if "data" not in response:
                raise ValueError("视频响应缺少 data")
            return build_video_reply(response["data"])
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            return "查询遇到错误, 视频信息不完整或格式不正确"

    async def execute(self, message: botpy_message.Message,
                      args: list[str]) -> bool:
        """Preserves the legacy direct channel entry point."""
        return await self.execute_guild(message, args)

    async def execute_guild(self, message: botpy_message.Message,
                            args: list[str]) -> bool:
        """Keeps the original channel image URL reply."""
        result = await self.query_video(args)
        if isinstance(result, str):
            await self.reply_guild(message, result)
            return False
        await self.client.api.post_message(
            channel_id=message.channel_id,
            content=result.content,
            image=result.image,
            msg_id=message.id,
        )
        return True

    async def execute_group(self, message: botpy_message.GroupMessage,
                            args: list[str]) -> bool:
        """Uploads the cover before replying with group rich media."""
        result = await self.query_video(args)
        if isinstance(result, str):
            await self.reply_group(message, result)
            return False
        try:
            await self.reply_group_image(message, result.content, result.image)
        except command_replies.GroupImageUploadError:
            _log.warning("BV 封面上传失败，回复文字信息")
            await self.reply_group(message, result.content + "\n封面暂时无法加载。")
        return True
