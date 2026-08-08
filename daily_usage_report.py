from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from commands.base import _command_name_to_formal_name
from dao import get_dao
from database.repositories.command_record_repository import CommandUsageSummary
from utils.time_utils import BEIJING_TZ, beijing_now


@dataclass(frozen=True)
class DailyUsageReport:
    date: str
    summary: CommandUsageSummary

    def render(self) -> str:
        lines = [
            f"昨日 Bot 使用总结（{self.date}）",
            f"总调用：{self.summary.total_commands} 次 · "
            f"活跃成员：{self.summary.unique_users} 人",
        ]
        if self.summary.total_commands == 0:
            lines.append("\n昨日没有命令使用记录。")
            return "\n".join(lines)

        lines.append("\n热门命令：")
        lines.extend(
            f"{index}. {_command_name_to_formal_name.get(item.name, item.name)}："
            f"{item.count} 次"
            for index, item in enumerate(self.summary.top_commands, start=1)
        )
        lines.append("\n活跃成员：")
        lines.extend(
            f"{index}. {item.user_name or item.user_id}：{item.count} 次"
            for index, item in enumerate(self.summary.top_users, start=1)
        )
        return "\n".join(lines)


def build_yesterday_usage_report(
    *,
    limit: int = 5,
    now: datetime | None = None,
) -> DailyUsageReport:
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")

    current = now or beijing_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=BEIJING_TZ)
    else:
        current = current.astimezone(BEIJING_TZ)

    today = current.date()
    yesterday = today - timedelta(days=1)
    start_at = f"{yesterday.isoformat()} 00:00:00"
    end_at = f"{today.isoformat()} 00:00:00"
    summary = get_dao().command_records.get_usage_summary(
        start_at=start_at,
        end_at=end_at,
        limit=limit,
    )
    return DailyUsageReport(date=yesterday.isoformat(), summary=summary)
