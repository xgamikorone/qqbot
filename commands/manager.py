from html import unescape
from typing import List, Tuple
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

    def _split_chained_msgs(self, msgs: List[str]) -> List[List[str]]:
        """按 && 拆分命令链，保留每段命令的 @bot 前缀。"""
        if len(msgs) < 2:
            return [msgs]

        prefix = msgs[0]
        segments: List[List[str]] = []
        current: List[str] = [prefix]

        for token in msgs[1:]:
            token = unescape(token)
            parts = token.split("&&")
            for index, part in enumerate(parts):
                if index > 0:
                    segments.append(current)
                    current = [prefix]
                if part:
                    current.append(part)

        segments.append(current)
        return segments

    async def execute(self, message: Message, msgs: List[str]) -> bool:
        """执行命令，返回是否找到命令"""

        if message.author.id in ["18135437345708881591"]:
            await self.client.api.post_message(
                message.channel_id, "你已被禁止使用丸子bot!", msg_id=message.id
            )
            return True

        chained_msgs = self._split_chained_msgs(msgs)
        if len(chained_msgs) > 1:
            found_any = False
            for chained_msg in chained_msgs:
                if len(chained_msg) < 2:
                    await self.client.api.post_message(
                        message.channel_id,
                        "&& 前后都需要有命令",
                        msg_id=message.id,
                    )
                    return True

                found, success = await self._execute_one(message, chained_msg)
                found_any = found_any or found
                if not found:
                    if found_any:
                        await self.client.api.post_message(
                            message.channel_id,
                            f"未知命令: {chained_msg[1]}",
                            msg_id=message.id,
                        )
                    return found_any
                if not success:
                    break
            return found_any

        found, _ = await self._execute_one(message, msgs)
        return found

    async def _execute_one(self, message: Message, msgs: List[str]) -> Tuple[bool, bool]:
        """执行单条命令，返回 (是否找到命令, 是否执行成功)。"""

        # msgs[0]应该是@bot，msgs[1]应该是命令名
        # 如果命令以/开头，则去掉开头的/
        cmd_name = msgs[1].lstrip("/")
        _log.info(f"cmd: {cmd_name}")

        # 没有空格的情况 拆分cmd和参数
        if cmd_name not in self.commands:
            for cmd in self.commands:
                if (
                    cmd_name.startswith(cmd)  # 匹配命令别名
                    and cmd != cmd_name  # 别名不能是命令名的子串
                ):
                    arg = cmd_name[len(cmd) :]
                    cmd_name = cmd_name[: len(cmd)]

                    msgs = [msgs[0]] + [cmd_name, arg] + msgs[2:]
                    break

        if cmd_name in self.commands:
            args = msgs[2:]
            success = True
            try:
                await self.commands[cmd_name].execute(message, args)
            except Exception as e:
                success = False
                _log.exception(f"Error executing command {cmd_name}: {e}")
                await self.commands[cmd_name].send_reply(
                    message, f"执行命令时发生错误: {e}"
                )
            await self.commands[cmd_name].after_execute(message, args)

            return True, success
        return False, False
