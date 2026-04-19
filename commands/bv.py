from datetime import datetime, timedelta, timezone

from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging
from .api import get_bv_info
from textwrap import dedent
_log = logging.get_logger()


@command("查bv", "查BV", "查视频")
class SearchBVCommand(Command):
    name = "bv"
    cn_name = "bv"

    async def execute(self, message: Message, args: List[str]):
        if not args:
            await self.send_reply(message, "请输入要查询的BV号!")
            return
        bv = "".join(args)
        r = await get_bv_info(bv)
        if r is None or r["code"] != 0:
            await self.send_reply(message, f"查询遇到错误, {r['message'] if r is not None else '未知错误'}")
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

        reply = dedent(
            f"""\
                标题: {title}
                up主: {owner["name"]}
                播放: {stat["view"]}, 弹幕: {stat["danmaku"]}, 点赞: {stat["like"]}
                评论: {stat["reply"]}, 收藏: {stat["favorite"]}
                发布时间: {pubdate_str}
            """
        )
        await self.client.api.post_message(
            channel_id=message.channel_id,
            content=reply,
            image=pic,
            msg_id=message.id
        )

        


