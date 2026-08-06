import difflib
import os
from typing import List

import botpy
from botpy import logging
from botpy.interaction import Interaction
from botpy.types.forum import Post
from botpy.message import DirectMessage, GroupMessage, Message
from dotenv import load_dotenv

import commands
from commands import CommandManager
from scheduled_jobs import build_scheduled_tasks
from scheduled_task_config import load_scheduled_tasks_config
from task_scheduler import TaskScheduler

_log = logging.get_logger()

load_dotenv()


class MyClient(botpy.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cmd_manager = CommandManager(self)
        self.scheduled_task_config = load_scheduled_tasks_config()
        self.task_scheduler = TaskScheduler(
            timezone=self.scheduled_task_config.timezone
        )
        self.task_scheduler.register_all(
            build_scheduled_tasks(
                self.scheduled_task_config,
                message_sender=self._send_scheduled_message,
            )
        )
        print(list(self.cmd_manager.commands.keys()))
        print(commands._command_name_to_formal_name)

    async def on_ready(self):
        if self.task_scheduler.start():
            _log.info("调度器已启动")

    async def _send_scheduled_message(self, channel_id: str, content: str) -> None:
        await self.api.post_message(channel_id=channel_id, content=content)
        _log.info(
            "已发送定时消息到 %s，长度 %d",
            channel_id,
            len(content),
        )

    async def on_at_message_create(self, message: Message):
        print(message.content)
        msgs = self.cmd_manager.normalize_msgs(message.content.split())

        if len(msgs) < 2:
            await self.api.post_message(
                channel_id=message.channel_id, content="你在说什么？", msg_id=message.id
            )
            return

        if not await self.cmd_manager.execute(message, msgs):
            raw_cmd_name = msgs[1].lstrip("/") if len(msgs) > 1 else ""
            suggestion = self._get_command_suggestion(raw_cmd_name)
            fallback_msg = (
                f"未知命令。你要找的是不是 `/{suggestion}`？"
                if suggestion
                else "未知命令"
            )
            await self.api.post_message(
                channel_id=message.channel_id, content=fallback_msg, msg_id=message.id
            )

    def _get_command_suggestion(self, cmd_name: str) -> str | None:
        if not cmd_name:
            return None
        all_cmds = list(self.cmd_manager.commands.keys())
        matches = difflib.get_close_matches(cmd_name, all_cmds, n=1, cutoff=0.6)
        return matches[0] if matches else None

    async def on_group_at_message_create(self, message: GroupMessage):
        print(message.content)
        msgs = message.content.split()

        if msgs[0].lstrip("/") == "hello":
            await message.reply(content="hi")
            return

    async def on_direct_message_create(self, message: DirectMessage):
        print(message.content)
        msgs = message.content.split()

        # if len(msgs) < 2:
        #     await self.api.post_message(
        #         channel_id=message.channel_id,
        #         content="你在说什么？",
        #         msg_id=message.id
        #     )
        #     return

        cmd_name = msgs[0].lstrip("/")
        if cmd_name == "hello":
            await self.api.post_dms(guild_id=message.guild_id, content="hi")

    async def on_forum_thread_create(self, thread):
        print(thread)

    async def on_forum_post_create(self, post: Post):
        """
        此处为处理该事件的代码
        """
        print(post)

    async def on_interaction_create(self, interaction: Interaction):
        pass


if __name__ == "__main__":

    app_id = os.getenv("APP_ID")
    app_secret = os.getenv("SECRET")
    intents = botpy.Intents().default()
    client = MyClient(intents=intents)

    client.run(appid=app_id, secret=app_secret)
