from typing import List
from botpy.message import Message
from botpy import logging, Client
from .base import Command, _command_registry, command

_log = logging.get_logger()


@command("所有命令", "all_commands")
class AllCommandsCommand(Command):
    name = "all_commands"
    cn_name = "所有命令"

    async def execute(self, message: Message, args: List[str]):
        """列出所有可用命令"""
        res_str = f"所有可用命令如下:\n"
        res_str += "\n".join(f"/{cmd}" for cmd in _command_registry)
        await self.send_reply(message, res_str)


class CommandManager:
    """命令管理器：负责命令的初始化和执行"""

    def __init__(self, client: Client):
        self.client = client
        self.commands: dict[str, Command] = {}
        self._init_commands()

    def _init_commands(self):
        """从注册表初始化命令实例"""
        for alias, cmd_class in _command_registry.items():
            self.commands[alias] = cmd_class(self.client)

    async def execute(self, message: Message, msgs: List[str]) -> bool:
        """执行命令，返回是否找到命令"""
        # msgs[0]应该是@bot，msgs[1]应该是命令名
        # 如果命令以/开头，则去掉开头的/
        cmd_name = msgs[1].lstrip("/")
        _log.info(f"cmd: {cmd_name}")

        # 没有空格的情况 拆分cmd和参数
        if cmd_name not in self.commands:
            for cmd in self.commands:
                if (
                    cmd_name.startswith(cmd) # 匹配命令别名
                    and cmd != cmd_name # 别名不能是命令名的子串
                    
                ):
                    arg = cmd_name[len(cmd) :]
                    cmd_name = cmd_name[: len(cmd)]

                    msgs = [msgs[0]] + [cmd_name, arg] + msgs[2:]
                    break

        if cmd_name in self.commands:
            args = msgs[2:]
            await self.commands[cmd_name].execute(message, args)
            await self.commands[cmd_name].after_execute(message, args)

            return True
        return False
