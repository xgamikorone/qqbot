from .base import command, Command, _command_registry, _command_name_to_formal_name, _command_alias_to_name
from .manager import CommandManager
from . import (
    helps,
    repeat,
    # channel_info,
    # update_channel,
    revenue,
    emoji,
    nickname, 
    # chat,
    stats,
    online,
    guards,
    user,
    at,
    wife,
    chuang,
    answer_book,
    birthday,
    rank,
    test,
    create,
    current_time,
)

__all__ = ["command", "Command", "_command_registry", "CommandManager", "_command_name_to_formal_name", "_command_alias_to_name"]
