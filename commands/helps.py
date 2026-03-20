from datetime import datetime, timedelta
from enum import IntEnum
import os
from textwrap import dedent
from .base import command, Command
from dao import get_dao
from botpy.message import Message
from botpy import logging
from typing import List, Optional
from .nickname import nickname_help_str
from .revenue import revenue_help_str
# from .chat import chat_help_str
from .guards import guards_help_str, followers_help_str
from .online import online_help_str
from .revenue_rank import revenue_rank_help_str
from .rank import rank_help_str
from .answer_book import answer_book_help_str

overall_help_message = dedent(
    """\
    丸子bot包括以下功能，请输入/帮助 <功能名> 获取详细信息：
    /昵称 为b站用户设置频道昵称
    /数据 查询直播相关数据
    /表情 贴表情
    /舰长 查看舰长数
    /粉丝 查看粉丝数
    /同接 查看当前直播同接人数
    /斗虫 查看数据对比
    /来个老婆 每日获得一个随机老婆
    /排行榜 查看各项排行榜
    /答案之书 向答案之书提问
    /生日快乐
    """
).strip()


@command("help", "h", "帮助")
class HelpCommand(Command):
    name = "help"
    cn_name = "帮助"

    async def execute(self, message: Message, args: List[str]):
        if len(args) == 0:
            await self.send_reply(message, overall_help_message)
            return
        command_name = args[0]
        if command_name.startswith("/"):
            command_name = command_name[1:]

        if command_name == "昵称":
            await self.send_reply(message, nickname_help_str)
            return
        if command_name == "数据":
            await self.send_reply(message, revenue_help_str)
            return
        if command_name == "表情":
            emoji_help_str = dedent(
                """\
                表情功能：
                /贴表情 <表情序号或具体表情>
                直接@丸子bot，则会在当前消息下贴表情。
                引用消息后@丸子bot，则会在引用消息下贴表情。
                """
            )
            await self.send_reply(message, emoji_help_str.strip())
            return
        # if command_name == "聊天":
        #     await self.send_reply(message, chat_help_str)
        #     return
        
        if command_name == "舰长":
            await self.send_reply(message, guards_help_str)
            return
        
        if command_name == "粉丝":
            await self.send_reply(message, followers_help_str)
            return
        
        if command_name == "同接":
            await self.send_reply(message, online_help_str)
            return
        
        if command_name == "斗虫":
            await self.send_reply(message, revenue_rank_help_str)
            return
        
        if command_name == "来个老婆":
            await self.send_reply(message, "直接输入就可以了，这还用我教你吗？")
            return
        
        if command_name == "排行榜":
            await self.send_reply(message, rank_help_str)
            return
        
        if command_name == "答案之书":
            await self.send_reply(message, answer_book_help_str)
            return
        
        if command_name == "生日快乐":
            await self.send_reply(message, "格式为 /生日快乐 <用户>")
            return
        await self.send_reply(message, f"未找到{command_name}命令的帮助信息")
        return