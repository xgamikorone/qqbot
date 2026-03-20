import asyncio
import os
from commands.utils import is_admin
from .base import command, Command
from dao import get_dao
from botpy.message import Message
from botpy import logging
from typing import List
from textwrap import dedent
import aiohttp

_log = logging.get_logger()

_log.info(f"共有{get_dao().get_num_wives()}个老婆")


@command("来个老婆", "wife")
class WifeCommand(Command):
    name = "wife"
    cn_name = "来个老婆"
    async def execute(self, message: Message, args: List[str]):
        
        dao = get_dao()

        wife_result = dao.get_wife(
            message.author.id,
            message.channel_id,
            message.guild_id
        )

        if not wife_result:
            await self.send_reply(message, f"<@!{message.author.id}>, 获取老婆失败，请稍后再试！")
            return
        
        url = wife_result.get("url", "")
        if not url:
            await self.send_reply(message, f"<@!{message.author.id}>, 获取老婆失败，请稍后再试！")
            return
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                await self.client.api.post_message(
                    content=f"<@!{message.author.id}>, 你的今日老婆：{wife_result['name']}",
                    channel_id=message.channel_id,
                    file_image=url,
                    msg_id=message.id
                )
                break  # 成功就退出循环

            except Exception as e:
                _log.warning(f"发送老婆图片失败，第{attempt}次重试: {e}")

                if attempt == max_retries:
                    _log.error("发送老婆图片最终失败")
                    await self.send_reply(
                        message,
                        f"<@!{message.author.id}>, 图片发送失败，你的老婆是：{wife_result['name']}！"
                    )
                else:
                    await asyncio.sleep(1)  # 每次失败后等1秒再试
