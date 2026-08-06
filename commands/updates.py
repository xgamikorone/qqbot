from typing import List

from botpy import logging
from botpy.message import Message

from user_updates import UserUpdatesConfigError, load_latest_user_update
from .base import Command, command
from .help_catalog import CommandHelp


_log = logging.get_logger(__name__)


@command("最近更新", "最新更新", "更新日志", "whats_new")
class RecentUpdatesCommand(Command):
    name = "recent_updates"
    cn_name = "最近更新"
    help = CommandHelp(
        title="最近更新",
        category="系统",
        summary="查看最近一次面向用户的功能更新",
        usage="/最近更新",
        examples=("/最近更新",),
    )

    async def execute(self, message: Message, args: List[str]):
        try:
            update = load_latest_user_update()
        except UserUpdatesConfigError:
            _log.exception("加载用户更新记录失败")
            await self.send_reply(message, "暂时无法获取最近更新，请稍后再试。")
            return

        if update is None:
            await self.send_reply(message, "暂无面向用户的更新记录。")
            return

        await self.send_reply(message, update.render())
