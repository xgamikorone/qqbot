from dataclasses import dataclass
from calendar import monthrange
from datetime import datetime, time
import re
from typing import Any


@dataclass(frozen=True)
class RevenuePeriodOptions:
    months: tuple[str, ...]
    periods: tuple[tuple[datetime, datetime], ...]
    top_n: int
    tag: str

    @property
    def start_time(self) -> datetime:
        return self.periods[0][0]

    @property
    def end_time(self) -> datetime:
        return self.periods[-1][1]


def _month_add(month: str, offset: int) -> str:
    year = int(month[:4])
    month_number = int(month[4:]) + offset
    year += (month_number - 1) // 12
    month_number = (month_number - 1) % 12 + 1
    return f"{year}{month_number:02d}"


def _month_range(start_month: str, end_month: str) -> list[str]:
    months = []
    current = start_month
    while current <= end_month:
        months.append(current)
        current = _month_add(current, 1)
    return months


def _is_valid_month(value: str) -> bool:
    return value.isdigit() and len(value) == 6 and 1 <= int(value[4:]) <= 12


def format_month_label(months: tuple[str, ...]) -> str:
    ordered_months = sorted(set(months))
    if not ordered_months:
        return ""
    if len(ordered_months) == 1:
        month = ordered_months[0]
        return f"{month[:4]}年{month[4:]}月"

    start_month, end_month = ordered_months[0], ordered_months[-1]
    if start_month[:4] == end_month[:4]:
        label = f"{start_month[:4]}年{start_month[4:]}月–{end_month[4:]}月"
    else:
        label = (
            f"{start_month[:4]}年{start_month[4:]}月–"
            f"{end_month[:4]}年{end_month[4:]}月"
        )

    if ordered_months != _month_range(start_month, end_month):
        label += f"（共{len(ordered_months)}个月）"
    return label


def _parse_months(value: str, now: datetime) -> list[str] | None:
    value = value.strip().lower()
    current_month = now.strftime("%Y%m")
    current_year = now.year
    aliases = {
        "本月": [current_month],
        "这个月": [current_month],
        "这月": [current_month],
        "当月": [current_month],
        "上月": [_month_add(current_month, -1)],
        "上个月": [_month_add(current_month, -1)],
        "今年": _month_range(f"{current_year}01", current_month),
        "本年": _month_range(f"{current_year}01", current_month),
        "今年以来": _month_range(f"{current_year}01", current_month),
        "去年": _month_range(f"{current_year - 1}01", f"{current_year - 1}12"),
        "上一年": _month_range(f"{current_year - 1}01", f"{current_year - 1}12"),
        "今年上半年": _month_range(f"{current_year}01", f"{current_year}06"),
        "本年上半年": _month_range(f"{current_year}01", f"{current_year}06"),
        "去年上半年": _month_range(f"{current_year - 1}01", f"{current_year - 1}06"),
        "去年下半年": _month_range(f"{current_year - 1}07", f"{current_year - 1}12"),
    }
    if value in aliases:
        return aliases[value]
    if value in {"今年下半年", "本年下半年"}:
        if current_month < f"{current_year}07":
            return []
        return _month_range(f"{current_year}07", current_month)

    recent_match = re.fullmatch(r"(?:近|最近)(\d+)个?月", value)
    if recent_match:
        count = int(recent_match.group(1))
        if count <= 0:
            return None
        return _month_range(_month_add(current_month, 1 - count), current_month)
    if re.fullmatch(r"(?:近|最近)一年", value):
        return _month_range(_month_add(current_month, -11), current_month)

    if "-" in value:
        start_month, end_month = [part.strip() for part in value.split("-", 1)]
        if not _is_valid_month(start_month) or not _is_valid_month(end_month):
            return None
        if start_month > end_month:
            return None
        return _month_range(start_month, end_month)

    months = [part.strip() for part in value.split(",") if part.strip()]
    if not months or any(not _is_valid_month(month) for month in months):
        return None
    return list(dict.fromkeys(months))


def _period_for_month(month: str, now: datetime) -> tuple[datetime, datetime]:
    year, month_number = int(month[:4]), int(month[4:])
    start = datetime(year, month_number, 1)
    if month == now.strftime("%Y%m"):
        return start, now.replace(microsecond=0)
    last_day = monthrange(year, month_number)[1]
    return start, datetime.combine(datetime(year, month_number, last_day), time.max).replace(
        microsecond=0
    )


def parse_revenue_period_args(
    args: list[str], *, now: datetime | None = None
) -> RevenuePeriodOptions:
    now = now or datetime.now()
    months = [now.strftime("%Y%m")]
    top_n = 20
    tag = "vr"

    index = 0
    while index < len(args):
        flag = args[index].lower()
        if flag not in {"/m", "/n", "/f"} or index + 1 >= len(args):
            raise ValueError(f"未知或缺少参数: {args[index]}")
        value = args[index + 1]
        if flag == "/m":
            parsed_months = _parse_months(value, now)
            if parsed_months is None:
                raise ValueError("月份格式错误")
            months = parsed_months
        elif flag == "/f":
            tag = value.lower()
        else:
            if not value.isdigit() or not 1 <= int(value) <= 100:
                raise ValueError("显示数量必须是 1-100 的整数")
            top_n = int(value)
        index += 2

    periods = tuple(_period_for_month(month, now) for month in months)
    return RevenuePeriodOptions(tuple(months), periods, top_n, tag)


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


def merge_realtime_revenue(
    payloads: list[Any], top_n: int
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for row in normalize_realtime_revenue(payload, top_n=10_000):
            identity = str(row.get("uid") or row["name"])
            if identity not in merged:
                merged[identity] = {**row}
                continue
            target = merged[identity]
            target["name"] = row["name"]
            for field in (
                "gift_income",
                "guard_income",
                "super_chat_income",
                "total_income",
            ):
                target[field] += row[field]
    return sorted(merged.values(), key=lambda row: row["total_income"], reverse=True)[
        :top_n
    ]
