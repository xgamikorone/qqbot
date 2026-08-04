from datetime import datetime, timedelta, timezone

from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging
from .api import get_bv_info
from textwrap import dedent
from utils.async_retry import retry_empty
_log = logging.get_logger()


async def get_bv_info_with_retry(
    bv: str, max_attempts: int = 3, retry_delay: float = 1.0
):
    return await retry_empty(
        lambda: get_bv_info(bv),
        max_attempts=max_attempts,
        retry_delay=retry_delay,
        on_retry=lambda attempt, total: _log.warning(
            f"查询 BV 失败，第 {attempt}/{total} 次尝试，即将重试"
        ),
    )


@command("查bv", "查BV", "查视频")
class SearchBVCommand(Command):
    name = "bv"
    cn_name = "bv"

    async def execute(self, message: Message, args: List[str]):
        if not args:
            await self.send_reply(message, "请输入要查询的BV号!")
            return
        bv = "".join(args)
        r = await get_bv_info_with_retry(bv)
        if not r or r.get("code") != 0:
            await self.send_reply(
                message, f"查询遇到错误, {r.get('message', '未知错误') if r else '未知错误'}"
            )
            return
        
        data = r["data"]
        pic = data["pic"]
        title = data["title"]
        stat = data["stat"]
        pubdate = data["pubdate"]
        tz_utc8 = timezone(timedelta(hours=8))
        dt = datetime.fromtimestamp(pubdate, tz=tz_utc8)
        pubdate_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        owner = data["owner"]
        bv = data["bvid"]

        reply = dedent(
            f"""\
                标题: {title}
                up主: {owner["name"]}
                播放: {stat["view"]}, 弹幕: {stat["danmaku"]}, 点赞: {stat["like"]}
                评论: {stat["reply"]}, 收藏: {stat["favorite"]}
                bv号: {bv}
                发布时间: {pubdate_str}
            """
        )
        await self.client.api.post_message(
            channel_id=message.channel_id,
            content=reply,
            image=pic,
            msg_id=message.id
        )

        


