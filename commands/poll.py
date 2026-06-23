import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp
from botpy import logging
from botpy.message import Message

from .base import Command, command


_log = logging.get_logger()


class PollApiError(Exception):
    """投票接口返回了无法处理的结果。"""


# 以下两个类型是 bot 内部使用的统一数据模型，不包含 B 站接口字段名。
@dataclass(frozen=True)
class PollEntry:
    id: str
    title: str
    votes: int
    link: Optional[str] = None


@dataclass(frozen=True)
class PollGroupResult:
    key: str
    name: str
    entries: List[PollEntry]


# 这是 B 站投票源的配置。以后接入其他平台时，应新增对应的平台配置类型。
@dataclass(frozen=True)
class BilibiliGroupConfig:
    name: str
    remote_group_id: str
    page_size: int = 13


@dataclass(frozen=True)
class BilibiliPollConfig:
    name: str
    remote_vote_id: str
    groups: Dict[str, BilibiliGroupConfig]


POLLS: Dict[str, BilibiliPollConfig] = {
    "师徒杯": BilibiliPollConfig(
        name="师徒杯",
        remote_vote_id="23ERA1wloghvxay00",
        groups={
            "徒弟": BilibiliGroupConfig(
                name="徒弟组",
                remote_group_id="24ERA1wloghvtgl00",
            ),
            "师父": BilibiliGroupConfig(
                name="师父组",
                remote_group_id="24ERA1wloghvtc600",
            ),
        },
    )
}


class BilibiliPollClient:
    """隔离 B 站请求参数和响应字段，向上层返回统一投票模型。"""

    API_URL = "https://api.bilibili.com/x/activity_components/vote_new/rank"

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch_group(
        self,
        poll: BilibiliPollConfig,
        group_key: str,
        group: BilibiliGroupConfig,
        page: int = 1,
    ) -> PollGroupResult:
        params = {
            "group_id": group.remote_group_id,
            "pn": page,
            "ps": group.page_size,
            "type": 2,
            "vote_id": poll.remote_vote_id,
        }

        print(self.API_URL, params)  # 调试用
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
            "Origin": "https://live.bilibili.com",
            "Referer": "https://live.bilibili.com/",
        }
        try:
            async with self.session.get(self.API_URL, params=params, headers=headers) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            raise PollApiError("请求 B 站投票接口失败") from exc

        if not isinstance(payload, dict):
            raise PollApiError("B 站投票接口返回格式异常")

        if payload.get("code", 0) != 0:
            message = payload.get("message") or payload.get("msg") or "未知错误"
            raise PollApiError(f"B 站投票接口错误：{message}")

        raw_items = payload.get("data", {}).get("items", [])
        if not isinstance(raw_items, list):
            raise PollApiError("B 站投票列表格式异常")

        entries = [self._parse_entry(item) for item in raw_items if isinstance(item, dict)]
        return PollGroupResult(key=group_key, name=group.name, entries=entries)

    @staticmethod
    def _parse_entry(raw: Dict[str, Any]) -> PollEntry:
        """B 站字段变化时，主要修改这一处即可。"""
        item = raw.get("item")
        if not isinstance(item, dict):
            item = {}

        raw_votes = raw.get("vote", 0)
        try:
            votes = int(raw_votes)
        except (TypeError, ValueError):
            votes = 0

        return PollEntry(
            id=str(raw.get("item_id", "")),
            title=str(item.get("title") or "未知选手"),
            votes=votes,
            link=item.get("jump_url"),
        )


@command("投票")
class PollCommand(Command):
    name = "poll"
    cn_name = "投票"

    async def execute(self, message: Message, args: List[str]):
        if args and args[0] in ("列表", "list"):
            await self.send_reply(message, "可查询的投票：" + "、".join(POLLS))
            return

        # 保留旧行为：/投票 默认查询师徒杯的所有分组。
        poll_name = args[0] if args else "师徒杯"
        poll = POLLS.get(poll_name)
        if poll is None:
            await self.send_reply(
                message,
                f"没有找到投票：{poll_name}\n可查询的投票：" + "、".join(POLLS),
            )
            return

        group_key = args[1] if len(args) > 1 else None
        if group_key and group_key not in poll.groups:
            await self.send_reply(
                message,
                f"没有找到分组：{group_key}\n可查询的分组："
                + "、".join(poll.groups),
            )
            return

        try:
            page = int(args[2]) if len(args) > 2 else 1
            if page < 1:
                raise ValueError
        except ValueError:
            await self.send_reply(message, "页码必须是大于 0 的整数。")
            return

        selected_groups = (
            {group_key: poll.groups[group_key]} if group_key else poll.groups
        )
        timeout = aiohttp.ClientTimeout(total=15, connect=5)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                client = BilibiliPollClient(session)
                results = await asyncio.gather(
                    *(
                        client.fetch_group(poll, key, group, page)
                        for key, group in selected_groups.items()
                    )
                )
        except PollApiError as exc:
            _log.exception("Failed to fetch poll data")
            await self.send_reply(message, f"无法获取投票数据：{exc}")
            return

        await self.send_reply(message, self._render_results(poll, results, page))

    @staticmethod
    def _render_results(
        poll: BilibiliPollConfig,
        results: List[PollGroupResult],
        page: int,
    ) -> str:
        sections = [f"{poll.name}投票（第 {page} 页）"]

        for result in results:
            lines = [f"{result.name}:"]
            if not result.entries:
                lines.append("暂无投票数据")
            else:
                lines.extend(
                    f"{index}. {entry.title} - {entry.votes}票"
                    for index, entry in enumerate(result.entries, start=1)
                )
            sections.append("\n".join(lines))

        return "\n\n".join(sections)
