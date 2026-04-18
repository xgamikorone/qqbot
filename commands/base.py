from typing import Dict, Type, List
from abc import ABC, abstractmethod
from botpy.client import Client
from botpy.message import Message
from botpy import logging
from dao import get_dao
from collections import defaultdict
from utils.time_utils import beijing_now

_command_registry: Dict[str, Type["Command"]] = {}
_log = logging.get_logger(__name__)

last_used = defaultdict(float)

def cooldown(seconds: int):
    """冷却装饰器：限制命令的全局使用频率"""
    def decorator(func):
        async def wrapper(self, message: Message, args: List[str]):
            command_name = self.name
            now_ts = beijing_now().timestamp()
            elapsed = now_ts - last_used[command_name]
            if elapsed < seconds:
                remaining = seconds - elapsed
                _log.info(f"命令 {command_name} 冷却中，还需等待 {remaining:.1f} 秒")
                await self.send_reply(message, f"命令冷却中，还需等待 {remaining:.1f} 秒")
                return
            last_used[command_name] = now_ts
            return await func(self, message, args)
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


class Command(ABC):
    """所有命令的基类"""
    name = "base"
    cn_name = "基础命令"
    def __init__(self, client: Client):
        self.client = client

    @abstractmethod
    async def execute(self, message: Message, args: List[str]):
        """执行命令"""
        pass

    async def send_reply(self, message: Message, content: str, is_reply: bool = True):
        """统一的回复方法"""
        if is_reply:
            await self.client.api.post_message(
                channel_id=message.channel_id, content=content, msg_id=message.id
            )
        else:
            await self.client.api.post_message(
                channel_id=message.channel_id, content=content
            )

    async def after_execute(self, message: Message, args: List[str]):
        """命令执行后执行的操作"""
        await self.add_to_database(message, args)
        pass

    async def add_to_database(self, message: Message, args: List[str]):
        """将命令执行结果添加到数据库"""

        dao = get_dao()
        dao.add_command_record(
            message_id=message.id,
            channel_id=message.channel_id,
            guild_id=message.guild_id,
            content=message.content,
            user_id=message.author.id,
            user_name=message.author.username,
            command_name=self.name,
            command_args=" ".join(args),
        )

