from typing import List

from botpy import logging
from botpy.message import Message
from botpy import message as botpy_message

from user_updates import UserUpdatesConfigError, load_latest_user_update
from .base import Command, command
from .help_catalog import CommandHelp

_log = logging.get_logger(__name__)


@command("最近更新", "最新更新", "更新日志", "whats_new", "u", "update")
class RecentUpdatesCommand(Command):
    supported_scenes = frozenset({"guild", "group"})
    name = "recent_updates"
    cn_name = "最近更新"
    help = CommandHelp(
        title="最近更新",
        category="系统",
        summary="查看最近一次面向用户的功能更新",
        usage="/最近更新",
        examples=("/最近更新",),
    )

    def build_update(self) -> str:
        """Loads the shared update text for both supported scenes."""
        try:
            update = load_latest_user_update()
        except UserUpdatesConfigError:
            _log.exception("加载用户更新记录失败")
            return "暂时无法获取最近更新，请稍后再试。"

        if update is None:
            return "暂无面向用户的更新记录。"

        return update.render()

    async def execute(self, message: Message, args: List[str]) -> None:
        """Preserves the existing channel command entry."""
        await self.send_reply(message, self.build_update())

    async def execute_group(
        self, message: botpy_message.GroupMessage, args: list[str]
    ) -> None:
        """Uses group transport with the shared update text."""
        await self.reply_group(message, self.build_update())
