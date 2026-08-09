from dataclasses import dataclass
from datetime import datetime, time
from typing import Any


@dataclass(frozen=True)
class RevenuePeriodOptions:
    start_time: datetime
    end_time: datetime
    top_n: int


def _parse_time(value: str, *, end_of_day: bool) -> datetime:
    normalized = value.strip().replace("T", "_")
    for fmt in ("%Y-%m-%d_%H:%M:%S", "%Y-%m-%d_%H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(normalized, fmt)
            if fmt == "%Y-%m-%d" and end_of_day:
                return datetime.combine(parsed.date(), time(23, 59, 59))
            return parsed
        except ValueError:
            continue
    raise ValueError(f"时间格式错误: {value}")


def parse_revenue_period_args(
    args: list[str], *, now: datetime | None = None
) -> RevenuePeriodOptions:
    now = now or datetime.now()
    start_time = datetime.combine(now.date(), time.min)
    end_time = now
    top_n = 20

    index = 0
    while index < len(args):
        flag = args[index].lower()
        if flag not in {"/s", "/e", "/n"} or index + 1 >= len(args):
            raise ValueError(f"未知或缺少参数: {args[index]}")
        value = args[index + 1]
        if flag == "/s":
            start_time = _parse_time(value, end_of_day=False)
        elif flag == "/e":
            end_time = _parse_time(value, end_of_day=True)
        else:
            if not value.isdigit() or not 1 <= int(value) <= 100:
                raise ValueError("显示数量必须是 1-100 的整数")
            top_n = int(value)
        index += 2

    if start_time > end_time:
        raise ValueError("开始时间不能晚于结束时间")
    return RevenuePeriodOptions(start_time, end_time, top_n)


def normalize_realtime_revenue(payload: Any, top_n: int) -> list[dict[str, Any]]:
    items = payload.get("data", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []

    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            rows.append(
                {
                    "name": str(item.get("name") or item.get("uid") or "未知主播"),
                    "uid": item.get("uid"),
                    "gift_income": float(item.get("gift_income") or 0),
                    "guard_income": float(item.get("guard_income") or 0),
                    "super_chat_income": float(item.get("super_chat_income") or 0),
                    "total_income": float(item.get("total_income") or 0),
                }
            )
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda row: row["total_income"], reverse=True)
    return rows[:top_n]
