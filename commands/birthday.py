from textwrap import dedent

import aiohttp
from .base import command, Command
from botpy.message import Message
from typing import List
from botpy import logging
from dao import get_dao
from dotenv import load_dotenv

birthday_template = dedent("""\
    ✨🎉 对所有的烦恼说 bye bye 👋💫
    🎈💖 对所有的快乐说 hi hi 🌈✨
    🎂🎀 亲爱的亲爱的{name}生日快乐 🎊🥳
    🌟✨ 每一天都精彩 🌸💐
    🌺🌼 看幸福的花儿为你盛开 🌷🌷
    🎵🎶 听美妙的音乐为你喝彩 👏✨
    🎂🎉 亲爱的亲爱的{name}生日快乐 💖🎁
    💝🌟 祝你幸福永远 ✨
    ♾️💖 幸福永远 🎊🎊
""")

@command("生日快乐", "happy_birthday")
class BirthdayCommand(Command):
    name = "birthday"
    cn_name = "生日快乐"
    async def execute(self, message: Message, args: List[str]):
        if not args:
            await self.send_reply(message, "请输入生日的用户!")
            return
        
        name = args[0]
        reply = birthday_template.format(name=name).strip()
        await self.send_reply(message, reply)
        return