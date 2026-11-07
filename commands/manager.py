"""Shared command parsing with explicitly typed SDK event entry points."""

import collections.abc
import html
import logging
import re

from botpy import client as botpy_client
from botpy import message as botpy_message

from dao import get_dao
from messaging import command_replies
from . import base
from . import help_catalog

_LOG = logging.getLogger(__name__)
RunCommand = collections.abc.Callable[
    [base.Command, list[str]], collections.abc.Awaitable[bool | None]
]
SendText = collections.abc.Callable[[str], collections.abc.Awaitable[None]]
RecordCommand = collections.abc.Callable[
    [base.Command, list[str], int, bool], collections.abc.Awaitable[None]
]


@base.command("所有命令", "all_commands")
class AllCommandsCommand(base.Command):
    supported_scenes = frozenset({"guild", "group"})
    name = "all_commands"
    cn_name = "所有命令"
    help = help_catalog.CommandHelp(
        title="所有命令",
        category="系统",
        summary="按分类查看可用功能",
        usage="/所有命令",
        show_in_overview=False,
    )

    async def execute(
        self, message: botpy_message.Message, args: list[str]
    ) -> None:
        """Retains the legacy channel entry point."""
        include_owner = get_dao().owners.contains(message.author.id)
        await self.reply_guild(
            message,
            base.render_scene_help("guild", include_owner=include_owner),
        )

    async def execute_group(
        self, message: botpy_message.GroupMessage, args: list[str]
    ) -> None:
        """Lists only implemented group commands."""
        await self.reply_group(message, base.render_scene_help("group"))


class CommandManager:
    """Parses once; dispatches original SDK objects to scene-specific methods."""

    def __init__(self, client: botpy_client.Client) -> None:
        self.client = client
        self.commands = {
            alias: cls(client) for alias, cls in base._command_registry.items()
        }
        self._sender = base.Command(client)

    def normalize_msgs(self, msgs: list[str]) -> list[str]:
        """Splits a channel mention joined to a command."""
        if not msgs:
            return msgs
        match = re.fullmatch(r"(<@!?\d+>)(.+)", msgs[0])
        return [*match.groups(), *msgs[1:]] if match else msgs

    def _split_chained_msgs(self, msgs: list[str]) -> list[list[str]]:
        """Preserves the parser prefix while splitting escaped command chains."""
        if len(msgs) < 2:
            return [msgs]
        segments: list[list[str]] = []
        current = [msgs[0]]
        for token in msgs[1:]:
            for index, part in enumerate(html.unescape(token).split("&&")):
                if index:
                    segments.append(current)
                    current = [msgs[0]]
                if part:
                    current.append(part)
        return [*segments, current]

    async def execute(
        self, message: botpy_message.Message, msgs: list[str]
    ) -> bool:
        """Compatibility alias for callers of the old channel manager."""
        return await self.execute_guild(message, msgs)

    async def execute_guild(
        self, message: botpy_message.Message, msgs: list[str]
    ) -> bool:
        """Keeps guild, channel, member, and attachment data untouched."""

        async def reply(content: str) -> None:
            await self._sender.reply_guild(message, content)

        if message.author.id == "18135437345708881591":
            await reply("你已被禁止使用丸子bot!")
            return True

        async def run(command: base.Command, args: list[str]) -> bool | None:
            return await command.execute_guild(message, args)

        async def record(
            command: base.Command, args: list[str], index: int, succeeded: bool
        ) -> None:
            await command.after_execute_guild(message, args)

        return await self._dispatch(
            self.normalize_msgs(msgs),
            "guild",
            run,
            reply,
            record,
            is_owner=get_dao().owners.contains(message.author.id),
        )

    async def execute_group(self, message: botpy_message.GroupMessage) -> bool:
        """Handles mention-stripped group text without creating fake fields."""
        if (
            not message.group_openid
            or not message.author.member_openid
            or not message.id
        ):
            _LOG.warning("忽略缺少身份字段的群消息")
            return False

        async def reply(content: str) -> None:
            await self._sender.reply_group(message, content)

        async def run(command: base.Command, args: list[str]) -> bool | None:
            return await command.execute_group(message, args)

        async def record(
            command: base.Command, args: list[str], index: int, succeeded: bool
        ) -> None:
            await command.after_execute_group(
                message, args, command_index=index, succeeded=succeeded
            )

        with command_replies.reply_scope(message):
            if (message.content or "").strip().lstrip("/") == "hello":
                await reply("hi")
                return True
            return await self._dispatch(
                ["group", *(message.content or "").split()],
                "group",
                run,
                reply,
                record,
            )

    async def execute_user(self, message: botpy_message.C2CMessage) -> bool:
        """Handles C2C; channel DirectMessage remains a separate event type."""
        if not message.author.user_openid or not message.id:
            _LOG.warning("忽略缺少身份字段的单聊消息")
            return False

        async def reply(content: str) -> None:
            await self._sender.reply_user(message, content)

        async def run(command: base.Command, args: list[str]) -> bool | None:
            return await command.execute_user(message, args)

        async def record(
            command: base.Command, args: list[str], index: int, succeeded: bool
        ) -> None:
            await command.after_execute_user(
                message, args, command_index=index, succeeded=succeeded
            )

        with command_replies.reply_scope(message):
            return await self._dispatch(
                ["user", *(message.content or "").split()],
                "user",
                run,
                reply,
                record,
            )

    async def _dispatch(
        self,
        tokens: list[str],
        scene: base.Scene,
        run: RunCommand,
        reply: SendText,
        record: RecordCommand,
        *,
        is_owner: bool = False,
    ) -> bool:
        """Shares lookup, capability, permission, failure and recording policy."""
        found_any = False
        for index, segment in enumerate(self._split_chained_msgs(tokens)):
            if len(segment) < 2:
                await reply("请输入命令；&& 前后都需要有命令。")
                return True
            name = segment[1].lstrip("/")
            args = segment[2:]
            if name not in self.commands:
                for alias in sorted(self.commands, key=len, reverse=True):
                    if name.startswith(alias):
                        args = [name[len(alias) :], *args]
                        name = alias
                        break
            command = self.commands.get(name)
            if command is None:
                if scene != "guild" or found_any:
                    await reply("未知命令，输入 /帮助 查看可用命令。")
                return found_any
            found_any = True
            if not command.supports_scene(scene):
                await reply("这个命令尚未开放当前场景使用。")
                return True
            if command.owner_only and not is_owner:
                await reply("这个命令只有作者本人可以使用。")
                return True
            succeeded = True
            try:
                succeeded = await run(command, args) is not False
            except Exception:
                succeeded = False
                _LOG.error(
                    "命令执行失败: scene=%s command=%s", scene, command.name
                )
                await reply("执行命令时发生错误，请稍后再试。")
            try:
                await record(command, args, index, succeeded)
            except Exception:
                _LOG.error(
                    "命令记录失败: scene=%s command=%s", scene, command.name
                )
            if not succeeded:
                break
        return found_any
