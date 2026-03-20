from commands.utils import is_admin
from .base import command, Command
from dao import get_dao
from botpy.message import Message
from botpy import logging
from typing import List
from textwrap import dedent
from .utils import ALLOWED_CHANNELS

_log = logging.get_logger()


@command("加昵称", "add_nickname")
class AddNicknameCommand(Command):
    """添加uid和对应的昵称"""
    name = "add_nickname"
    cn_name = "加昵称"
    async def execute(self, message: Message, args: List[str]):
        _log.info(f"AddNicknameCommand: {args}")
        # channel_id = int(message.channel_id)
        # if channel_id not in ALLOWED_CHANNELS:
        #     await self.send_reply(message, "该功能不允许在此频道被使用！")
        #     return
        member = message.member
        roles = member.roles
        if not is_admin(roles):
            await self.send_reply(message, "该功能仅管理员可用！")
            return
        if len(args) < 2:
            await self.send_reply(message, "格式错误，应为：加昵称 <uid> <昵称>！")
        uid_or_nickname = args[0]
        dao = get_dao()
        if uid_or_nickname.isdigit():
            uid = int(uid_or_nickname)
        else:
            uid = dao.get_uid_by_nickname(uid_or_nickname)
            if uid is None:
                await self.send_reply(
                    message, f"昵称{uid_or_nickname}没有对应的uid，请先添加！"
                )
                return
        nickname = args[1]
        if nickname.isdigit():
            await self.send_reply(
                message, "昵称不能为纯数字，否则在查询时bot无法判断是uid还是昵称！"
            )
            return
        if dao.add_nickname(uid, nickname):
            await self.send_reply(message, f"成功为uid {uid}添加昵称 {nickname}！")
        else:
            await self.send_reply(message, f"添加失败，昵称 {nickname} 可能已存在！")


@command("所有昵称", "all_nicknames")
class AllNicknamesCommand(Command):
    """列出所有昵称"""
    name = "all_nicknames"
    cn_name = "所有昵称"
    async def execute(self, message: Message, args: List[str]):
        dao = get_dao()
        all_nicknames = dao.get_all_nicknames()
        res_str = "所有昵称:\n"

        res_str += "\n".join(
            [f"{nickname['uid']}:{nickname['nickname']}" for nickname in all_nicknames]
        )
        await self.send_reply(message, res_str)


@command("查昵称", "check_nickname")
class CheckNicknameCommand(Command):
    """根据uid或昵称查询对应的昵称"""
    name = "check_nickname"
    cn_name = "查昵称"
    async def execute(self, message: Message, args: List[str]):
        if not args:
            await self.send_reply(message, "请输入要查询的uid")
        uid_or_nickname = args[0]
        dao = get_dao()
        if uid_or_nickname.isdigit():
            uid = int(uid_or_nickname)
        else:
            uid = dao.get_uid_by_nickname(uid_or_nickname)
            if uid is None:
                await self.send_reply(
                    message, f"昵称{uid_or_nickname}没有对应的uid，请先添加！"
                )
                return

        nicknames = dao.get_nicknames_by_uid(uid)
        _log.info(f"uid: {uid}, nicknames: {nicknames}")
        if not nicknames:
            await self.send_reply(message, f"uid {uid}没有昵称！")
        else:
            res_str = f"uid {uid}的昵称有：\n"
            res_str += "\n".join(nicknames)
            await self.send_reply(message, res_str)


@command("查uid", "check_uid")
class CheckUidCommand(Command):
    """根据昵称查询对应的uid"""
    name = "check_uid"
    cn_name = "查uid"
    async def execute(self, message: Message, args: List[str]):
        if not args:
            await self.send_reply(message, "请输入要查询的昵称!")
            return
        nickname = args[0]
        if nickname.isdigit():
            await self.send_reply(message, "昵称不能为纯数字!")
        dao = get_dao()
        uid = dao.get_uid_by_nickname(nickname)
        _log.info(f"nickname: {nickname}, uid: {uid}")
        if uid is None:
            await self.send_reply(message, f"昵称 {nickname} 没有对应的uid!")
            return
        await self.send_reply(message, f"昵称 {nickname} 对应的uid为 {uid}!")


@command("删昵称", "delete_nickname")
class DeleteNicknameCommand(Command):
    """删除昵称"""
    name = "delete_nickname"
    cn_name = "删昵称"
    async def execute(self, message: Message, args: List[str]):
        # channel_id = int(message.channel_id)
        # if channel_id not in ALLOWED_CHANNELS:
        #     await self.send_reply(message, "该功能不允许在此频道被使用！")
        member = message.member
        roles = member.roles
        if not is_admin(roles):
            await self.send_reply(message, "该功能仅管理员可用！")
            return
        if not args:
            await self.send_reply(message, "请输入要删除的昵称！")

        member = message.member
        roles = member.roles
        _log.info(f"roles: {roles}")
        if roles is None:
            await self.send_reply(message, "你没有管理昵称的权限！")
            return

        has_permission = is_admin(roles)
        if not has_permission:
            await self.send_reply(message, "你没有管理昵称的权限！")
            return

        nickname = args[0]
        dao = get_dao()
        if nickname.isdigit():
            # 如果输入是uid，则删除uid对应的昵称
            uid = int(nickname)
            if dao.delete_nickname_by_uid(uid):
                await self.send_reply(message, f"成功删除uid {uid}对应的昵称！")
            else:
                await self.send_reply(message, f"删除失败，uid {uid} 没有对应的昵称！")
            return

        if dao.delete_nickname(nickname):
            await self.send_reply(message, f"成功删除昵称 {nickname}！")
        else:
            await self.send_reply(message, f"删除失败，昵称 {nickname} 可能不存在！")

nickname_help_str = dedent("""\
    昵称管理帮助：
    昵称是用于根据uid进行便捷查询的方式。每个uid可以对应多个昵称，每个昵称只能对应一个uid。

    加昵称 <uid或昵称> <昵称>
    为用户uid或昵称添加昵称，如果第一个参数使用昵称，需确保改昵称已经被添加，其他命令相同。
    示例：加昵称 1217754423 邦邦 或 加昵称 邦邦 又一

    所有昵称
    列出所有已添加的昵称

    查昵称 <uid或昵称>
    根据uid或昵称查询该用户的所有昵称
    示例：查昵称 1217754423 或 查昵称 又一

    查uid <昵称>
    根据昵称查询对应的uid
    示例：查uid 又一

    删昵称 <昵称或uid>
    删除指定昵称或uid对应的所有昵称（需要管理员权限）
    示例：删昵称 又一 或 删昵称 1217754423

    昵称帮助
    显示此帮助信息""")

@command("昵称帮助", "nickname_help")
class NicknameHelpCommand(Command):
    """关于昵称的帮助"""
    name = "nickname_help"
    cn_name = "昵称帮助"
    async def execute(self, message: Message, args: List[str]):
        
        await self.send_reply(message, nickname_help_str)
