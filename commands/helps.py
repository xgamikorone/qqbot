from typing import List

from botpy.message import Message
from botpy import message as botpy_message

from dao import get_dao
from .base import Command, _command_registry, command
from . import base
from .help_catalog import CommandHelp, HelpCatalog


@command("help", "h", "帮助")
class HelpCommand(Command):
    supported_scenes = frozenset({"guild", "group", "user"})
    name = "help"
    cn_name = "帮助"
    help = CommandHelp(
        title="帮助",
        category="系统",
        summary="查看 bot 的功能分类和命令用法",
        usage="/帮助 [功能名、命令名或分类]",
        examples=("/帮助", "/帮助 舰长", "/帮助 直播数据"),
        show_in_overview=False,
    )

    async def execute(self, message: Message, args: List[str]):
        query = " ".join(args) if args else None
        include_owner = get_dao().owners.contains(message.author.id)
        content = base.render_scene_help(
            "guild", query, include_owner=include_owner
        )
        await self.send_reply(message, content)

    async def execute_group(
        self, message: botpy_message.GroupMessage, args: list[str]
    ) -> None:
        """Applies the same group capability filter as the dispatcher."""
        await self.reply_group(
            message,
            base.render_scene_help("group", " ".join(args) if args else None),
        )

    async def execute_user(
        self, message: botpy_message.C2CMessage, args: list[str]
    ) -> None:
        """Lists only commands implemented for C2C."""
        await self.reply_user(
            message,
            base.render_scene_help("user", " ".join(args) if args else None),
        )
