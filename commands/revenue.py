from datetime import timedelta
from .base import command, Command, cooldown
from . import text_query
from dao import get_dao
from botpy.message import Message
from botpy import logging
from typing import List
import asyncio
from textwrap import dedent
from .help_catalog import CommandHelp
from integrations.live_data import (
    ErrorCode,
    get_last_session_id,
    get_session_revenue,
    get_session_info,
    get_super_chats,
    get_guards,
    get_user_super_chats,
    get_user_guards,
    get_user_danmus,
    get_online_members,
)
from .utils import get_name_from_uid, is_admin, is_admin_or_owner
from utils.time_utils import beijing_now


_log = logging.get_logger()


@command("查舰长", "guards")
class StreamerGuardsCommand(text_query.TextQueryCommand):
    """Queries streamer guard-purchase records with V2 nickname matching."""

    PAGE_SIZE = 10
    name = "streamer_guards"
    cn_name = "查舰长"
    max_num_uids = 5
    help = CommandHelp(
        title="查舰长",
        category="直播数据",
        summary="分页查询主播收到的上舰记录",
        usage="/查舰长 <uid或昵称> [页码]",
        details="查询主播收到的上舰记录，与 /舰长 查询当前舰长数不同。\n"
        "支持 UID、uid:12345、精确昵称和模糊昵称，最多匹配 5 位主播。\n"
        "页码从 0 开始，每页 10 条；负数按 0 处理。\n"
        "用法：/查舰长 <uid或昵称> [页码]",
    )

    async def query_and_reply(
        self, args: list[str], reply: text_query.TextSender
    ) -> bool:
        """Keeps each matched streamer's records and the legacy price units."""
        if not args:
            await reply("请输入要查询的主播uid或昵称")
            return False
        try:
            page = max(0, int(args[1])) if len(args) > 1 else 0
        except ValueError:
            await reply("页码格式错误，请输入整数；页码从 0 开始")
            return False
        try:
            uids = _resolve_query_uids(args[0], self.max_num_uids)
        except ValueError:
            await reply("UID 格式错误，请输入正整数或 uid:正整数")
            return False
        if not uids:
            await reply(f"未找到昵称为{args[0]}的主播")
            return False

        sections: list[str] = []
        succeeded = True
        levels = {1: "总督", 2: "提督", 3: "舰长"}
        for uid in uids:
            try:
                name = await get_name_from_uid(uid) or str(uid)
                records = await get_guards(
                    uid, page * self.PAGE_SIZE, (page + 1) * self.PAGE_SIZE
                )
                if records is None:
                    sections.append(f"查询{name}的上舰记录失败")
                    succeeded = False
                    continue
                rows = [
                    f"{record['user_name']}: "
                    f"{levels.get(record['guard_level'], record['guard_level'])}; "
                    f"{record['num']}; {record['record_time']}; "
                    f"{record['price'] / 1000.}"
                    for record in records
                ]
                sections.append(
                    f"主播 {name}的最近 {page * self.PAGE_SIZE + 1}~{(page + 1) * self.PAGE_SIZE}个舰长:\n"
                    "格式为: 用户名:舰长等级;数量;时间;价格\n"
                    + ("\n".join(rows) if rows else "暂无上舰记录")
                )
            except TimeoutError:
                sections.append(f"查询主播{uid}的上舰记录超时，请稍后再试")
                succeeded = False
            finally:
                await asyncio.sleep(1.0)
        await reply("\n\n".join(sections))
        return succeeded


@command("查用户SC", "用户SC", "user_sc", "user_super_chat")
class UserSuperChatCommand(Command):
    """查询用户发过的SC, 参数为 <uid或昵称>
    可选参数
    </p> <页码>
    </r> <在uid或昵称的直播间(默认所有直播间)>
    </s> <开始时间(默认半年前)>
    </e> <结束时间(默认当前时间)>
    """

    name = "user_super_chat"
    PAGE_SIZE = 10

    @cooldown(10)
    async def execute(self, message: Message, args: List[str]):
        _log.info(f"UserSuperChatCommand args: {args}")
        # channel_id = int(message.channel_id)
        # if channel_id not in ALLOWED_CHANNELS:
        #     await self.send_reply(message, "该功能不允许在此频道被使用！")
        #     return
        member = message.member
        roles = member.roles
        if not is_admin_or_owner(message):
            await self.send_reply(message, "该功能仅管理员可用！")
            return
        if not args:
            await self.send_reply(message, "请输入要查询的用户uid或昵称")
            return
        uid_or_nickname = args[0]
        if uid_or_nickname.isdigit():
            uid = int(uid_or_nickname)
        elif uid_or_nickname.lower().startswith("uid:"):
            uid = int(uid_or_nickname[4:].strip())
        else:
            # 是昵称
            dao = get_dao()
            uid = dao.nicknames.get_uid(uid_or_nickname)
            if uid is None:
                await self.send_reply(message, f"未找到昵称为{uid_or_nickname}的用户")
                return
        # 检查可选参数
        # e.g. /p 1 /r 又一, 1900141897 (多个主播)
        room_str = ""
        start_time = (beijing_now() - timedelta(days=180)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        end_time = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
        num_page = 0
        for i in range(1, len(args), 2):
            if args[i] == "/p":
                num_page = int(args[i + 1])
                if num_page < 0:
                    num_page = 0
            if args[i] == "/r":
                room_str = args[i + 1]
            if args[i] == "/s":
                start_time = args[i + 1]
            if args[i] == "/e":
                end_time = args[i + 1]
        if end_time < start_time:
            end_time = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
        _log.info(
            f"room_str: {room_str}, num_page: {num_page}, start_time: {start_time}, end_time: {end_time}"
        )
        rooms = []
        if room_str:
            room_str = room_str.replace("，", ",")  # 兼容中文逗号
            rooms = room_str.split(",")
        streamer_uids = []
        for room in rooms:
            if room.isdigit():
                streamer_uids.append(int(room))
            else:
                # 是昵称
                dao = get_dao()
                streamer_uid = dao.nicknames.get_uid(room)
                if streamer_uid is None:
                    await self.send_reply(message, f"未找到昵称为{room}的主播")
                    return
                streamer_uids.append(streamer_uid)
        _log.info(f"streamer_uids: {streamer_uids}")
        # 查询用户发过的SC
        user_super_chats = await get_user_super_chats(
            uid,
            start_time,
            end_time,
            streamer_uids,
            num_page * self.PAGE_SIZE,
            (num_page + 1) * self.PAGE_SIZE,
        )
        _log.info(f"user_super_chats:\n{user_super_chats}")

        res_str = (
            f"用户{uid_or_nickname}发过的SC:\n"
            f"格式为: 用户名:SC内容;时间;价格;直播间\n"
        )
        # for sc in user_super_chats:
        #     res_str += f"{sc['user_name']}: {sc['message']}; {sc['record_time']}; {sc['price']}; {sc['streamer_name']}\n"

        res_str += "\n".join(
            [
                f"{sc['user_name']}: {sc['message']}; {sc['record_time']}; {sc['price']}; {sc['streamer_name']}"
                for sc in user_super_chats
            ]
        )
        _log.info(f"res_str: {res_str}")
        await self.send_reply(message, res_str)

        return True


@command("查用户舰长", "用户舰长", "user_guards", "user_guard")
class UserGuardsCommand(Command):
    """查询用户直播间的舰长, 参数为 <uid或昵称>
    可选参数
    </p> <页码>
    </r> <在uid或昵称的直播间(默认所有直播间)>
    </s> <开始时间(默认半年前)>
    </e> <结束时间(默认当前时间)>
    """

    name = "user_guards"
    cn_name = "查用户舰长"
    PAGE_SIZE = 10

    @cooldown(10)
    async def execute(self, message: Message, args: List[str]):
        _log.info(f"UserGuardsCommand args: {args}")
        # channel_id = int(message.channel_id)
        # if channel_id not in ALLOWED_CHANNELS:
        #     await self.send_reply(message, "该功能不允许在此频道被使用！")
        #     return
        member = message.member
        roles = member.roles
        if not is_admin_or_owner(message):
            await self.send_reply(message, "该功能仅管理员可用！")
            return
        if not args:
            await self.send_reply(message, "请输入要查询的用户uid或昵称")
            return

        uid_or_nickname = args[0]
        if uid_or_nickname.isdigit():
            uid = int(uid_or_nickname)
        elif uid_or_nickname.lower().startswith("uid:"):
            uid = int(uid_or_nickname[4:].strip())
        else:
            # 是昵称
            dao = get_dao()
            uid = dao.nicknames.get_uid(uid_or_nickname)
            if uid is None:
                await self.send_reply(message, f"未找到昵称为{uid_or_nickname}的用户")
                return
        # 检查可选参数
        room_str = ""
        start_time = (beijing_now() - timedelta(days=180)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        end_time = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
        num_page = 0
        for i in range(1, len(args), 2):
            if args[i] == "/p":
                num_page = int(args[i + 1])
                if num_page < 0:
                    num_page = 0
            if args[i] == "/r":
                room_str = args[i + 1]
            if args[i] == "/s":
                start_time = args[i + 1]
            if args[i] == "/e":
                end_time = args[i + 1]
        if end_time < start_time:
            end_time = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
        _log.info(
            f"room_str: {room_str}, num_page: {num_page}, start_time: {start_time}, end_time: {end_time}"
        )
        rooms = []
        if room_str:
            room_str = room_str.replace("，", ",")  # 兼容中文逗号
            rooms = room_str.split(",")
        streamer_uids = []
        for room in rooms:
            if room.isdigit():
                streamer_uids.append(int(room))
            else:
                # 是昵称
                dao = get_dao()
                streamer_uid = dao.nicknames.get_uid(room)
                if streamer_uid is None:
                    await self.send_reply(message, f"未找到昵称为{room}的主播")
                    return
                streamer_uids.append(streamer_uid)
        _log.info(f"streamer_uids: {streamer_uids}")
        # 查询用户发过的SC
        user_guards = await get_user_guards(
            uid,
            start_time,
            end_time,
            streamer_uids,
            num_page * self.PAGE_SIZE,
            (num_page + 1) * self.PAGE_SIZE,
        )
        _log.info(f"user_guards:\n{user_guards}")

        res_str = (
            f"用户{uid_or_nickname}上过的舰长:\n"
            f"格式为: 用户名:舰长等级;数量;时间;价格;直播间\n"
        )
        guard_levels = {
            1: "总督",
            2: "提督",
            3: "舰长",
        }
        # for guard in user_guards:
        #     res_str += f"{guard['user_name']}: {guard_levels[guard["guard_level"]]}; {guard['num']}; {guard['record_time']}; {guard['price'] / 1000.}; {guard['streamer_name']}\n"

        res_str += "\n".join(
            [
                f"{guard['user_name']}: {guard_levels[guard['guard_level']]}; "
                f"{guard['num']}; {guard['record_time']}; "
                f"{guard['price'] / 1000.}; {guard['streamer_name']}"
                for guard in user_guards
            ]
        )

        _log.info(f"res_str: {res_str}")
        await self.send_reply(message, res_str)

        return True


@command("查用户弹幕", "用户弹幕", "user_danmus", "user_danmu")
class UserDanmusCommand(Command):
    """查询用户直播间的弹幕, 参数为 <uid或昵称>
    可选参数

    </p> <页码>
    </r> <在uid或昵称的直播间(默认所有直播间)>
    </s> <开始时间(默认半年前)>
    </e> <结束时间(默认当前时间)>
    """

    PAGE_SIZE = 10
    name = "user_danmus"
    cn_name = "查用户弹幕"

    @cooldown(30)
    async def execute(self, message: Message, args: List[str]):
        _log.info(f"UserGuardsCommand args: {args}")
        # channel_id = int(message.channel_id)
        # if channel_id not in ALLOWED_CHANNELS:
        #     await self.send_reply(message, "该功能不允许在此频道被使用！")
        #     return
        member = message.member
        roles = member.roles
        if not is_admin_or_owner(message):
            await self.send_reply(message, "该功能仅管理员可用！")
            return

        if not args:
            await self.send_reply(message, "请输入要查询的用户uid或昵称")
            return

        uid_or_nickname = args[0]
        if uid_or_nickname.isdigit():
            uid = int(uid_or_nickname)
        elif uid_or_nickname.lower().startswith("uid:"):
            uid = int(uid_or_nickname[4:].strip())
        else:
            # 是昵称
            dao = get_dao()
            uid = dao.nicknames.get_uid(uid_or_nickname)
            if uid is None:
                await self.send_reply(message, f"未找到昵称为{uid_or_nickname}的用户")
                return
        # 检查可选参数
        room_str = ""
        start_time = (beijing_now() - timedelta(days=180)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        end_time = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
        num_page = 0
        for i in range(1, len(args), 2):
            if args[i] == "/p":
                num_page = int(args[i + 1])
                if num_page < 0:
                    num_page = 0
            if args[i] == "/r":
                room_str = args[i + 1]
            if args[i] == "/s":
                start_time = args[i + 1]
            if args[i] == "/e":
                end_time = args[i + 1]
        if end_time < start_time:
            end_time = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
        _log.info(
            f"room_str: {room_str}, num_page: {num_page}, start_time: {start_time}, end_time: {end_time}"
        )
        rooms = []
        if room_str:
            room_str = room_str.replace("，", ",")  # 兼容中文逗号
            rooms = room_str.split(",")
        streamer_uids = []
        for room in rooms:
            if room.isdigit():
                streamer_uids.append(int(room))
            else:
                # 是昵称
                dao = get_dao()
                streamer_uid = dao.nicknames.get_uid(room)
                if streamer_uid is None:
                    await self.send_reply(message, f"未找到昵称为{room}的主播")
                    return
                streamer_uids.append(streamer_uid)
        _log.info(f"streamer_uids: {streamer_uids}")
        # 查询用户发过的SC
        user_danmus = await get_user_danmus(
            uid,
            start_time,
            end_time,
            streamer_uids,
            num_page * self.PAGE_SIZE,
            (num_page + 1) * self.PAGE_SIZE,
        )
        _log.info(f"user_danmus:\n{user_danmus}")

        res_str = (
            f"用户{uid_or_nickname}发送过的弹幕:\n" f"格式为: 用户名:内容;时间;直播间\n"
        )
        # for danmu in user_danmus:
        #     res_str += f"{danmu['send_user_name']}: {danmu["message"]}; {danmu['record_time']}; {danmu['streamer_name']}\n"

        res_str += "\n".join(
            [
                f"{danmu['send_user_name']}: {danmu['message']}; {danmu['record_time']}; {danmu['streamer_name']}"
                for danmu in user_danmus
            ]
        )
        _log.info(f"res_str: {res_str}")
        await self.send_reply(message, res_str)

        return True


revenue_help_str = dedent(
    """\
    数据管理帮助：

    查营收 <uid或昵称>
    查询主播最近一场直播的营收统计
    示例：查营收 12345 或 查营收 小王
    显示: 直播标题、直播时间、总收益、舰队收益、礼物收益、SC收益

    查SC <uid或昵称> [页码]
    查询主播收到的SC列表
    示例：查SC 12345 或 查SC 小王 1
    显示: 用户名、SC内容、时间、价格
    页码: 从0开始，每页10条，不指定则默认为0

    查用户SC <uid或昵称> [选项]
    查询用户发送过的SC列表
    示例：查用户SC 12345 /p 1 /r 又一 /s 2024-01-01 /e 2024-12-31
    
    可选参数:
    /p <页码>          - 页码，默认0，每页10条
    /r <主播uid或昵称> - 指定直播间（多个主播用逗号分隔），默认所有直播间
    /s <开始时间>      - 查询起始时间，格式: "YYYY-MM-DD"，默认半年前
    /e <结束时间>      - 查询结束时间，格式: "YYYY-MM-DD"，默认当前时间

    查用户舰长 <uid或昵称> [选项]
    查询用户上舰的记录
    示例：查用户舰长 12345 /p 0 /r 又一
    
    可选参数: 同上 (/p /r /s /e)
    显示: 用户名、舰长等级（总督/提督/舰长）、数量、时间、价格、直播间

    查用户弹幕 <uid或昵称> [选项]
    查询用户发送过的弹幕
    示例：查用户弹幕 12345 /p 0 /r 又一
    
    可选参数: 同上 (/p /r /s /e)
    显示: 用户名、弹幕内容、时间、直播间

    数据帮助
    显示此帮助信息"""
)


@command("数据帮助", "stats_help")
class RevenueHelpCommand(Command):
    """数据相关命令的帮助"""

    name = "stats_help"
    cn_name = "数据帮助"
    help = CommandHelp(
        title="数据",
        category="直播数据",
        summary="查询直播营收、SC、舰长和弹幕记录",
        details=revenue_help_str,
        lookup_names=(
            "数据",
            "查营收",
            "营收",
            "revenue",
            "查SC",
            "SC",
            "super_chat",
            "查用户SC",
            "用户SC",
            "user_sc",
            "user_super_chat",
            "查用户舰长",
            "用户舰长",
            "user_guards",
            "查用户弹幕",
            "用户弹幕",
            "user_danmus",
        ),
    )

    async def execute(self, message: Message, args: List[str]):

        await self.send_reply(message, revenue_help_str)


# @command("revenue_v2", "查营收v2")
def _resolve_query_uids(value: str, limit: int) -> list[int]:
    """Resolves a UID or shared streamer nickname, without QQ user identities."""
    if value.isdigit() or value.lower().startswith("uid:"):
        uid = int(
            value[4:].strip() if value.lower().startswith("uid:") else value
        )
        if uid <= 0:
            raise ValueError("UID must be positive")
        return [uid]
    repository = get_dao().nicknames
    uid = repository.get_uid(value)
    return ([uid] if uid is not None else repository.find_uids(value))[:limit]


@command("查营收", "营收", "revenue")
class RevenueCommandV2(text_query.TextQueryCommand):
    name = "revenue_v2"
    cn_name = "查营收v2"
    max_num_uids = 5
    help = CommandHelp(
        title="营收",
        category="直播数据",
        summary="查询主播最近一场直播营收",
        usage="/营收 <uid或昵称>",
        examples=("/营收 12345",),
        details="查询最近一场直播营收，支持 UID、uid:12345、昵称和昵称模糊匹配。\n"
        "模糊匹配最多查询 5 位主播。\n用法：/营收 <uid或昵称>",
    )

    async def query_and_reply(
        self, args: list[str], reply: text_query.TextSender
    ) -> bool:
        """Shares revenue queries and text rendering across guild and group."""
        if not args:
            await reply("请输入要查询的主播uid或昵称")
            return False
        try:
            uids = _resolve_query_uids(args[0], self.max_num_uids)
        except ValueError:
            await reply("UID 格式错误，请输入正整数或 uid:正整数")
            return False
        if not uids:
            await reply(f"未找到昵称为{args[0]}的主播")
            return False

        sections: list[str] = []
        succeeded = True
        for uid in uids:
            try:
                last_session_id = await get_last_session_id(uid)
                name = await get_name_from_uid(uid) or str(uid)
                if last_session_id == ErrorCode.NO_LIVE_SESSIONS:
                    sections.append(f"主播{name}没有直播记录")
                    continue
                if last_session_id == ErrorCode.ERROR_FETCHING_DATA:
                    sections.append(f"查询{name}的直播数据失败")
                    succeeded = False
                    continue

                payload = await get_session_revenue(last_session_id)
                revenue = payload.get("revenue") if payload else None
                session_info = await get_session_info(last_session_id)
                if not revenue or not session_info:
                    sections.append(f"查询{name}的直播数据失败")
                    succeeded = False
                    continue
                online = await get_online_members(last_session_id) or {}
                start_time = str(session_info.get("start_time") or "").replace(
                    "T", " "
                )
                end_time = str(session_info.get("end_time") or "").replace(
                    "T", " "
                )
                sections.append(
                    f"主播{name}的最近一场直播营收:\n"
                    f"直播标题:{session_info.get('title', '')}\n"
                    f"直播时间:{start_time}~{end_time}\n"
                    f"同接(最高/平均): {online.get('max') or 0}/{round(online.get('avg') or 0)}\n"
                    f"舰队收入: {round(revenue.get('guards') or 0, 2)}\n"
                    f"礼物收入: {round(revenue.get('gifts') or 0, 2)}\n"
                    f"SC收入: {round(revenue.get('super_chats') or 0, 2)}\n"
                    f"总收入: {round(revenue.get('total') or 0, 2)}"
                )
            except TimeoutError:
                sections.append(f"查询主播{uid}超时，请稍后再试")
                succeeded = False
            finally:
                await asyncio.sleep(1.0)  # Preserve upstream request pacing.
        await reply("\n\n".join(sections))
        return succeeded


@command("查SC", "SC", "sc", "super_chat", "super_chat_v2", "查SCv2")
class SuperChatCommandV2(text_query.TextQueryCommand):
    PAGE_SIZE = 10
    name = "super_chat_v2"
    cn_name = "查SC"
    max_num_uids = 5
    help = CommandHelp(
        title="查SC",
        category="直播数据",
        summary="分页查询主播收到的 SC",
        usage="/查SC <uid或昵称> [页码]",
        examples=("/查SC 12345 0",),
        details="查询主播收到的 SC，支持 UID、uid:12345、昵称和昵称模糊匹配。\n"
        "页码从 0 开始，每页 10 条；负数按 0 处理，最多匹配 5 位主播。\n"
        "用法：/查SC <uid或昵称> [页码]；/查SCv2 仍可使用",
    )

    async def query_and_reply(
        self, args: list[str], reply: text_query.TextSender
    ) -> bool:
        """Retains every matched streamer's results, including empty pages."""
        if not args:
            await reply("请输入要查询的主播uid或昵称")
            return False
        try:
            page = max(0, int(args[1])) if len(args) > 1 else 0
        except ValueError:
            await reply("页码格式错误，请输入整数；页码从 0 开始")
            return False
        try:
            uids = _resolve_query_uids(args[0], self.max_num_uids)
        except ValueError:
            await reply("UID 格式错误，请输入正整数或 uid:正整数")
            return False
        if not uids:
            await reply(f"未找到昵称为{args[0]}的主播")
            return False

        sections: list[str] = []
        succeeded = True
        for uid in uids:
            try:
                name = await get_name_from_uid(uid) or str(uid)
                records = await get_super_chats(
                    uid, page * self.PAGE_SIZE, (page + 1) * self.PAGE_SIZE
                )
                if records is None:
                    sections.append(f"查询{name}的 SC 数据失败")
                    succeeded = False
                    continue
                rows = [
                    f"{record['user_name']}: {record['message']}; "
                    f"{record['record_time']}; {record['price']}"
                    for record in records
                ]
                sections.append(
                    f"主播 {name}的最近 {page * self.PAGE_SIZE}~{(page + 1) * self.PAGE_SIZE}条SC:\n"
                    "格式为: 用户名:SC内容;时间;价格\n"
                    + ("\n".join(rows) if rows else "暂无SC记录")
                )
            except TimeoutError:
                sections.append(f"查询主播{uid}的 SC 超时，请稍后再试")
                succeeded = False
            finally:
                await asyncio.sleep(1.0)  # Preserve upstream request pacing.
        await reply("\n\n".join(sections))
        return succeeded
