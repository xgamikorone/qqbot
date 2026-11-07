from typing import Dict, Type, List
import typing
from botpy import message as botpy_message
from botpy.client import Client
from botpy.message import Message
from botpy import logging
from dao import get_dao
from collections import defaultdict
from functools import wraps
from time import monotonic
from .help_catalog import CommandHelp, HelpCatalog
from messaging import command_replies

_command_registry: Dict[str, Type["Command"]] = {}
_log = logging.get_logger(__name__)

last_used = defaultdict(float)
_running_commands = set()

def cooldown(seconds: int):
    """全局冷却：命令成功返回 True 后计时；失败返回 None/False 或抛异常。"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, message: Message, args: List[str]):
            command_name = self.name
            if command_name in _running_commands:
                await self.send_reply(message, "命令正在执行，请稍后再试")
                return False
            now_ts = monotonic()
            elapsed = now_ts - last_used.get(command_name, now_ts - seconds)
            if command_name in last_used and elapsed < seconds:
                remaining = seconds - elapsed
                _log.info(f"命令 {command_name} 冷却中，还需等待 {remaining:.1f} 秒")
                await self.send_reply(message, f"命令冷却中，还需等待 {remaining:.1f} 秒")
                return False
            _running_commands.add(command_name)
            try:
                result = await func(self, message, args)
                if result is True:
                    last_used[command_name] = monotonic()
                return result
            finally:
                _running_commands.discard(command_name)
        return wrapper
    return decorator

_command_registry: Dict[str, Type["Command"]] = {}
_command_name_to_formal_name: Dict[str, str] = {}
_command_alias_to_name: Dict[str, str] = {}
_log = logging.get_logger(__name__)

def command(*aliases: str):
    """装饰器：自动注册命令及其所有别名"""

    def decorator(cls: Type["Command"]):
        for alias in aliases:
            if alias in _command_registry:
                _log.warning(f"命令别名 {alias} 已存在，将覆盖原有命令")
            _command_registry[alias] = cls
            _command_alias_to_name[alias] = cls.name

        _command_name_to_formal_name[cls.name] = cls.cn_name
        return cls

    return decorator


Scene = typing.Literal["guild", "group", "user"]


class UnsupportedSceneError(ValueError):
    """A command has not implemented the requested messaging scene."""


def render_scene_help(
    scene: Scene, query: str | None = None, *, include_owner: bool = False
) -> str:
    """Uses the same scene support policy as command dispatch."""
    registry = {
        alias: cls
        for alias, cls in _command_registry.items()
        if cls.supports_scene(scene)
    }
    return HelpCatalog(registry).render(query, include_owner=include_owner)


class Command:
    """所有命令的基类"""
    name = "base"
    cn_name = "基础命令"
    owner_only = False
    hidden = False
    supported_scenes: typing.ClassVar[frozenset[Scene]] = frozenset({"guild"})
    help: CommandHelp | None = None

    def __init__(self, client: Client):
        self.client = client

    async def execute(self, message: Message, args: List[str]) -> bool | None:
        """Legacy channel entry; new commands implement execute_guild instead."""
        raise UnsupportedSceneError("暂不支持频道")

    async def execute_guild(
        self, message: Message, args: list[str]
    ) -> bool | None:
        """Keeps existing channel-only command implementations working."""
        return await self.execute(message, args)

    async def execute_group(
        self, message: botpy_message.GroupMessage, args: list[str]
    ) -> bool | None:
        """Handles the original group event, when explicitly supported."""
        raise UnsupportedSceneError("暂不支持群聊")

    async def execute_user(
        self, message: botpy_message.C2CMessage, args: list[str]
    ) -> bool | None:
        """Handles C2C events, distinct from channel DirectMessage events."""
        raise UnsupportedSceneError("暂不支持单聊")

    @classmethod
    def supports_scene(cls, scene: Scene) -> bool:
        """Requires both a declaration and a non-default implementation."""
        if scene not in cls.supported_scenes:
            return False
        if scene == "guild":
            return (
                cls.execute_guild is not Command.execute_guild
                or cls.execute is not Command.execute
            )
        return getattr(cls, f"execute_{scene}") is not getattr(
            Command, f"execute_{scene}"
        )

    async def send_reply(
        self,
        message: Message,
        content: str,
        is_reply: bool = True,
    ) -> None:
        """统一的回复方法"""
        await self.reply_guild(message, content, is_reply=is_reply)

    async def reply_guild(
        self, message: Message, content: str, is_reply: bool = True
    ) -> None:
        """Replies using the original channel and message identifiers."""
        if is_reply:
            await self.client.api.post_message(
                channel_id=message.channel_id, content=content, msg_id=message.id
            )
        else:
            await self.client.api.post_message(
                channel_id=message.channel_id, content=content
            )

    async def reply_group(
        self, message: botpy_message.GroupMessage, content: str
    ) -> None:
        """Uses this incoming event's shared sequence, never instance state."""
        await self.client.api.post_group_message(
            group_openid=command_replies.require_id(message.group_openid),
            content=content,
            msg_id=message.id,
            msg_seq=command_replies.next_sequence(message),
        )

    async def reply_user(
        self, message: botpy_message.C2CMessage, content: str
    ) -> None:
        """Replies to C2C using user_openid, not a channel DM guild ID."""
        sequence = command_replies.next_sequence(message)
        await self.client.api.post_c2c_message(
            openid=message.author.user_openid,
            content=content,
            msg_id=message.id,
            # qq-botpy 1.2.1 annotates this as str, but its default is int 1.
            msg_seq=sequence,  # pyright: ignore[reportArgumentType]
        )

    async def after_execute_guild(
        self, message: Message, args: list[str]
    ) -> None:
        """Preserves legacy hooks, including chat's content retention policy."""
        await self.after_execute(message, args)

    async def after_execute_group(
        self,
        message: botpy_message.GroupMessage,
        args: list[str],
        *,
        command_index: int,
        succeeded: bool,
    ) -> None:
        """Stores group identities without invoking channel record hooks."""
        name = getattr(message.author, "username", "")
        get_dao().groups.record_command(
            group_openid=command_replies.require_id(message.group_openid),
            member_openid=message.author.member_openid,
            display_name=name if isinstance(name, str) else "",
            message_id=message.id,
            command_name=self.name,
            command_index=command_index,
            succeeded=succeeded,
        )

    async def after_execute_user(
        self,
        message: botpy_message.C2CMessage,
        args: list[str],
        *,
        command_index: int,
        succeeded: bool,
    ) -> None:
        """Records C2C usage without storing private message content."""
        get_dao().c2c.record_command(
            user_openid=message.author.user_openid,
            message_id=message.id,
            command_name=self.name,
            command_index=command_index,
            succeeded=succeeded,
        )

    async def after_execute(self, message: Message, args: List[str]):
        """命令执行后执行的操作"""
        await self.add_to_database(message, args)
        pass

    async def add_to_database(self, message: Message, args: List[str]):
        """将命令执行结果添加到数据库"""

        dao = get_dao()
        dao.command_records.record(
            message_id=message.id,
            channel_id=message.channel_id,
            guild_id=message.guild_id,
            content=message.content,
            user_id=message.author.id,
            user_name=message.author.username,
            command_name=self.name,
            command_args=" ".join(args),
        )
