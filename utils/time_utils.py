from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8), name="UTC+8")
SQLITE_BEIJING_NOW_EXPR = "datetime('now', '+8 hours')"


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def beijing_now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return beijing_now().strftime(fmt)


def to_beijing_time_str(value: str) -> str:
    if not value:
        return ""

    text = value.strip()
    normalized = text.replace("Z", "+00:00")

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            dt = datetime.strptime(text.replace("T", " "), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return text

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    else:
        dt = dt.astimezone(BEIJING_TZ)

    return dt.strftime("%Y-%m-%d %H:%M:%S")
