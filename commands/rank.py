from dataclasses import dataclass
from typing import List, Callable, Awaitable, Optional, Dict, Any
from utils.time_utils import beijing_now_str

from .base import (
    command,
    Command,
    _command_name_to_formal_name,
    _command_alias_to_name,
    _command_registry,
)
from dao import get_dao
from botpy.message import Message
from botpy import logging
from textwrap import dedent

_log = logging.get_logger()


# =========================================================
# ⭐ 类型定义
# =========================================================

RenderRow = Callable[[int, Dict[str, Any]], str]
RenderFooter = Callable[[List[Dict[str, Any]]], Awaitable[Optional[str]]]


@dataclass
class RankConfig:
    title: str
    top_data: List[Dict[str, Any]]
    render_row: RenderRow
    render_footer: Optional[RenderFooter] = None


@dataclass
class RankResult:
    config: Optional[RankConfig] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.config is not None


rank_help_str = dedent(
    """\
    目前已有以下排行指令:
    —————————————
    🔹 排行榜 被创丨历史被创丨累计被创 | 被创次数 | 平均被创 [最少次数(3)]
    🔹 排行榜 命令丨他的命令 [@用户(不加则为自己)]丨命令用户 [命令名]"""
)


# =========================================================
# ⭐ Command
# =========================================================


@command("rank", "排行榜")
class RankCommand(Command):
    name = "rank"
    cn_name = "排行榜"

    # =====================================================
    # 入口
    # =====================================================

    async def execute(self, message: Message, args: List[str]):
        if not args:
            await self.send_reply(message, rank_help_str)
            return

        cmd = args[0]
        result = await self._get_rank_config(
            cmd=cmd,
            message=message,
            args=args[1:],
        )

        if not result:
            await self.send_reply(message, rank_help_str)
            return

        if not result.ok:
            await self.send_reply(message, result.error or "未知错误")
            return

        if not result.config:
            await self.send_reply(message, result.error or "未知错误")
            return

        result = await self._build_rank_message(result.config)
        await self.send_reply(message, result)

    # =====================================================
    # 分发
    # =====================================================

    async def _get_rank_config(
        self, cmd: str, message: Message, args: List[str]
    ) -> RankResult:

        rank_map = {
            "被创": self._rank_today,
            "历史被创": self._rank_history,
            "累计被创": self._rank_total,
            "平均被创": self._rank_average,
            "被创次数": self._rank_chuang_time,
            "命令": self._rank_command_counts,
            "他的命令": self._rank_user_command_counts,
            "命令用户": self._rank_command_user_counts,
        }

        handler = rank_map.get(cmd)
        if not handler:
            return RankResult(error="未知指令")

        return await handler(message, args)

    # =====================================================
    # 今日被创
    # =====================================================

    async def _rank_today(self, message: Message, args: List[str]) -> RankResult:

        dao = get_dao()
        guild_id = message.guild_id
        user_id = message.author.id
        today_str = beijing_now_str("%Y-%m-%d")

        top_data = dao.get_chuang_top_k_cur_guild(10, today_str, guild_id)

        user_ids = [row["user_id"] for row in top_data]
        usernames = await self._fetch_usernames(guild_id, user_ids)

        def render_row(rank: int, row: dict) -> str:
            username = usernames.get(row["user_id"], "未知用户")
            return f"{rank}. {username}: {row['distance']}m"

        async def render_footer(
            top_data: List[dict],
        ) -> Optional[str]:

            if any(row["user_id"] == user_id for row in top_data):
                return None

            distance = dao.get_today_chuang_distance(user_id, guild_id, today_str)

            if distance is None:
                return None

            rank = dao.get_chuang_history_rank_cur_guild(distance, guild_id)

            user = await self.client.api.get_guild_member(guild_id, user_id)

            return f"{rank + 1}. " f"{user['nick']}: {distance}m"

        return RankResult(
            RankConfig(
                title="今日被创排行榜:",
                top_data=top_data,
                render_row=render_row,
                render_footer=render_footer,
            )
        )

    # =====================================================
    # 历史被创
    # =====================================================

    async def _rank_history(self, message: Message, args: List[str]) -> RankResult:

        dao = get_dao()
        guild_id = message.guild_id
        user_id = message.author.id

        top_data = dao.get_chuang_top_k_cur_guild_history(10, guild_id)

        user_ids = [row["user_id"] for row in top_data]
        usernames = await self._fetch_usernames(guild_id, user_ids)

        def render_row(rank: int, row: dict) -> str:
            username = usernames.get(row["user_id"], "未知用户")
            return f"{rank}. {username}: {row['distance']}m"

        async def render_footer(
            top_data: List[dict],
        ) -> Optional[str]:

            if any(row["user_id"] == user_id for row in top_data):
                return None

            data = dao.get_user_chuang_history_best(user_id, guild_id)

            if not data:
                return None

            user = await self.client.api.get_guild_member(guild_id, user_id)

            return f"{data['history_rank']}. " f"{user['nick']}: {data['distance']}m"

        return RankResult(
            RankConfig(
                title="历史被创排行榜:",
                top_data=top_data,
                render_row=render_row,
                render_footer=render_footer,
            )
        )

    # =====================================================
    # 累计被创
    # =====================================================

    async def _rank_total(self, message: Message, args: List[str]) -> RankResult:

        dao = get_dao()
        guild_id = message.guild_id
        user_id = message.author.id

        top_data = dao.get_chuang_total_top_k_cur_guild(10, guild_id)

        user_ids = [row["user_id"] for row in top_data]
        usernames = await self._fetch_usernames(guild_id, user_ids)

        def render_row(rank: int, row: dict) -> str:
            username = usernames.get(row["user_id"], "未知用户")
            return f"{rank}. {username}: " f"{row['total_distance']}m"

        async def render_footer(
            top_data: List[dict],
        ) -> Optional[str]:

            if any(row["user_id"] == user_id for row in top_data):
                return None

            data = dao.get_user_chuang_total(user_id, guild_id)

            if not data:
                return None

            user = await self.client.api.get_guild_member(guild_id, user_id)

            return f"{data['rank']}. " f"{user['nick']}: " f"{data['total_distance']}m"

        return RankResult(
            RankConfig(
                title="累计被创排行榜:",
                top_data=top_data,
                render_row=render_row,
                render_footer=render_footer,
            )
        )

    # =====================================================
    # 平均被创
    # =====================================================
    async def _rank_average(self, message: Message, args: List[str]) -> RankResult:
        dao = get_dao()
        guild_id = message.guild_id
        user_id = message.author.id

        min_limit = 3
        if args:
            if args[0].isdigit():
                min_limit = int(args[0])
            else:
                return RankResult(error="参数错误, 请输入一个整数")

        top_data = dao.get_chuang_average_top_k_cur_guild(10, guild_id, min_limit)

        user_ids = [row["user_id"] for row in top_data]
        usernames = await self._fetch_usernames(guild_id, user_ids)

        def render_row(rank: int, row: dict) -> str:
            username = usernames.get(row["user_id"], "未知用户")
            return f"{rank}. {username}: " f"{row['average_distance']:.2f}m"

        async def render_footer(
            top_data: List[dict],
        ) -> Optional[str]:

            if any(row["user_id"] == user_id for row in top_data):
                return None

            # 判断用户被创次数是否大于min_limit
            num_chuang = dao.get_user_chuang_time(user_id, guild_id)
            if num_chuang < min_limit:
                return f"本榜单仅统计被创次数大于等于{min_limit}次的用户，当前用户被创次数为{num_chuang}次！"

            avg_distance = dao.get_user_chuang_average(user_id, guild_id)
            # 这里avg_distance一定是有效的

            rank = dao.get_avg_distance_rank_cur_guild(
                avg_distance, guild_id, min_limit
            )

            return f"{rank}. {message.author.username}: {avg_distance:.2f}m"

        return RankResult(
            RankConfig(
                title="平均被创排行榜:",
                top_data=top_data,
                render_row=render_row,
                render_footer=render_footer,
            )
        )

    # =====================================================
    # 被创次数
    # =====================================================
    async def _rank_chuang_time(self, message: Message, args: List[str]) -> RankResult:
        dao = get_dao()
        guild_id = message.guild_id
        user_id = message.author.id

        top_data = dao.get_chuang_times_rank_cur_guild(guild_id, 10)

        user_ids = [row["user_id"] for row in top_data]
        usernames = await self._fetch_usernames(guild_id, user_ids)

        def render_row(rank: int, row: dict) -> str:
            username = usernames.get(row["user_id"], "未知用户")
            return f"{rank}. {username}: {row['chuang_time']}"

        async def render_footer(
            top_data: List[dict],
        ) -> Optional[str]:

            if any(row["user_id"] == user_id for row in top_data):
                return None

            times = dao.get_user_chuang_time(user_id, guild_id)

            rank = dao.get_user_chuang_times_rank_cur_guild(times, guild_id)

            return f"{rank}. {message.author.username}: {times}"

        return RankResult(
            RankConfig(
                title="被创次数排行榜:",
                top_data=top_data,
                render_row=render_row,
                render_footer=render_footer,
            )
        )

    # =====================================================
    # 命令统计
    # =====================================================

    async def _rank_command_counts(
        self, message: Message, args: List[str]
    ) -> RankResult:
        dao = get_dao()
        guild_id = message.guild_id

        top_data = dao.get_command_counts_cur_guild(guild_id)[:10]

        def render_row(rank: int, row: dict) -> str:
            command_name = _command_name_to_formal_name.get(
                row["command_name"], row["command_name"]
            )
            return f"{rank}. {command_name}: {row['count']}"

        return RankResult(
            RankConfig(
                title="命令统计:",
                top_data=top_data,
                render_row=render_row,
            )
        )

    # =====================================================
    # 他的命令统计
    # =====================================================

    async def _rank_user_command_counts(
        self, message: Message, args: List[str]
    ) -> RankResult:
        dao = get_dao()
        mentions = message.mentions
        filtered_users = [u for u in mentions if not u.bot]
        _log.info(f"filtered_users: {filtered_users}")

        if not filtered_users:
            filtered_users = [message.author]

        user = filtered_users[0]
        user_id = user.id
        guild_id = message.guild_id
        top_data = dao.get_user_command_counts_cur_guild(user_id, guild_id)[:10]

        def render_row(rank: int, row: dict) -> str:
            command_name = _command_name_to_formal_name.get(
                row["command_name"], row["command_name"]
            )
            return f"{rank}. {command_name}: {row['count']}"

        return RankResult(
            RankConfig(
                title=f"{user.username}的命令统计:",
                top_data=top_data,
                render_row=render_row,
                render_footer=None,
            )
        )

    async def _rank_command_user_counts(
        self, message: Message, args: List[str]
    ) -> RankResult:
        command_name = args[0]
        if command_name not in _command_name_to_formal_name:
            command_name = _command_alias_to_name.get(command_name, None)
            if not command_name:
                # await self.send_reply(message, "命令不存在！")
                return RankResult(
                    error=f"命令{command_name}不存在！",
                )
        dao = get_dao()
        guild_id = message.guild_id
        user_id = message.author.id
        top_data = dao.get_command_counts_per_user_cur_guild(command_name, guild_id)[
            :10
        ]
        user_ids = [row["user_id"] for row in top_data]
        usernames = await self._fetch_usernames(guild_id, user_ids)

        def render_row(rank: int, row: dict) -> str:
            username = usernames.get(row["user_id"], "未知用户")
            return f"{rank}. {username}: {row['count']}"

        async def render_footer(
            top_data: List[dict],
        ) -> Optional[str]:

            if any(row["user_id"] == user_id for row in top_data):
                return None

            data = dao.get_command_counts_by_user_cur_guild(
                command_name, user_id, guild_id
            )

            if not data:
                return None

            count = data.get("count", 0)

            data = dao.get_command_counts_rank_by_user_cur_guild(
                command_name, guild_id, count
            )
            if not data:
                return None
            rank = data.get("greater_count", 0) + 1

            user = await self.client.api.get_guild_member(guild_id, user_id)
            return f"{rank}. " f"{user['nick']}: " f"{count}次"

        return RankResult(
            RankConfig(
                title=f"{command_name}的用户统计:",
                top_data=top_data,
                render_row=render_row,
                render_footer=render_footer,
            )
        )

    # =====================================================
    # 通用渲染
    # =====================================================

    async def _build_rank_message(
        self,
        config: RankConfig,
    ) -> str:

        lines = [config.render_row(i + 1, row) for i, row in enumerate(config.top_data)]

        result = config.title + "\n" + "\n".join(lines)

        if config.render_footer:
            footer = await config.render_footer(config.top_data)
            if footer:
                result += "\n" + footer

        return result

    # =====================================================
    # 用户名获取
    # =====================================================

    async def _fetch_usernames(
        self,
        guild_id: str,
        user_ids: List[str],
    ) -> Dict[str, str]:

        result: Dict[str, str] = {}

        for uid in user_ids:
            try:
                user = await self.client.api.get_guild_member(guild_id, uid)
                result[uid] = user["nick"]
            except Exception:
                result[uid] = "未知用户"

        return result
