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
        # 找出imgs/wives目录下所有文件
        files = os.listdir("./imgs/wives")

        # 依次发送所有文件
        for file in files:
            file_path = os.path.join("./imgs/wives", file)
            await self.client.api.post_message(
                message.channel_id,
                content=f"这是{file_path}:",
                file_image=file_path
            )
