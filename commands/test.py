import os
from typing import List
from .base import command, Command, cooldown
from dao import get_dao
from botpy.message import Message
from botpy import logging



@command("test")
class TestCommand(Command):
    name = "test"
    cn_name = "测试"
    async def execute(self, message: Message, args: List[str]):
        sub_cmd = args[0] if args else None
        if sub_cmd == "wife":
            wife_id = args[1] if len(args) > 1 else 0


@command("作者测试", "owner_test")
class OwnerTestCommand(Command):
    name = "owner_test"
    cn_name = "作者测试"
    owner_only = True

    async def execute(self, message: Message, args: List[str]):
        await self.send_reply(message, f"<@!{message.author.id}> 作者权限测试通过。")

