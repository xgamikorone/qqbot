from .base import command, Command, _command_name_to_formal_name, _command_alias_to_name
from botpy.message import Message
from typing import List
from botpy import logging
from dao import get_dao
from textwrap import dedent

_log = logging.get_logger()

COMMAND_NAME_TO_FORMAL_NAME = {}


@command("命令统计", "command_stats")
class StatsCommand(Command):
    name = "command_stats"
    cn_name = "命令统计"

    async def execute(self, message: Message, args: List[str]):
        dao = get_dao()
        result = dao.get_command_counts_cur_guild(message.guild_id)
        if not result:
            await self.send_reply(message, "获取命令次数统计失败，稍后再试试吧！")
            return
        result = result[:10]
        res_str = f"命令的使用次数统计:\n"
        res_str += "\n".join([f"{_command_name_to_formal_name.get(r['command_name'], r['command_name']) }: {r['count']}" for r in result])
        _log.info(res_str)
        await self.send_reply(message, res_str)
        return


@command("他的命令统计", "his_stats_command")
class HisStatsCommand(Command):
    name = "his_stats_command"
    cn_name = "他的命令统计"

    async def execute(self, message: Message, args: List[str]):
        mentions = message.mentions
        filtered_users = [u for u in mentions if not u.bot]
        _log.info(f"filtered_users: {filtered_users}")
        if not filtered_users:
            # 未指定则为自己
            filtered_users = [message.author]
        dao = get_dao()
        res_str = ""
        for u in filtered_users:
            result = dao.get_user_command_counts_cur_guild(u.id, message.guild_id)
            result = result[:10]
            res_str += f"用户{u.username}的命令的使用次数统计:\n"
            res_str += "\n".join([f"{_command_name_to_formal_name.get(r['command_name'], r['command_name'])}: {r['count']}" for r in result])
            res_str += "\n"
            
        _log.info(res_str)
        await self.send_reply(message, res_str.rstrip('\n'))

@command("命令用户统计", "command_user_stats")
class CommandUserStatsCommand(Command):
    """查询某个命令被哪些用户使用最多"""
    name = "command_user_stats"
    cn_name = "命令用户统计"

    async def execute(self, message: Message, args: List[str]):
        command_name = args[0]
        dao = get_dao()
        result = dao.get_command_counts_per_user_cur_guild(command_name, message.guild_id)
        if not result:
            await self.send_reply(message, f"命令{command_name}没有被任何用户使用过！")
            return
        
        result = result[:10]
        from pprint import pprint
        pprint(result)
        res_str = f"命令{command_name}被以下用户使用次数:\n"
        user_names = []
        for r in result:
            user_id = int(r["user_id"])
            print(user_id)
            try:
                user = await self.client.api.get_guild_member(guild_id=message.guild_id, user_id=str(user_id))
                user_names.append(user["nick"])
            except:
                user_names.append("未知用户")

        res_str += '\n'.join(
            [f"{i+1}. {user_names[i]}: {result[i]['count']}" for i in range(len(user_names))]
        )

        _log.info(res_str)
        await self.send_reply(message, res_str)

@command("命令统计帮助", "command_stats_help")
class StatsHelpCommand(Command):
    name = "command_stats_help"
    cn_name = "命令统计帮助"

    async def execute(self, message: Message, args: List[str]):
        help_text = dedent("""\
            命令统计帮助
            ============
            
            1. 命令统计
               获取所有命令的使用次数统计
               使用: /命令统计
            
            2. 他的命令统计
               获取指定用户的命令使用次数统计，未指定用户则统计自己
               使用: /他的命令统计 [@user]
            
            3. 命令用户统计
               查询某个命令被哪些用户使用最多
               使用: /命令用户统计 <command_name>
        """)
        # _log.info(help_text)
        await self.send_reply(message, help_text)
