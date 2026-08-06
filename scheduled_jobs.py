import os

from add_default_nicknames import add_default_nicknames
from task_scheduler import CronSchedule, ScheduledTask


def build_scheduled_tasks() -> tuple[ScheduledTask, ...]:
    """根据环境变量生成本进程需要运行的定时任务。"""

    if not _read_bool("NICKNAME_SYNC_ENABLED", default=True):
        return ()

    schedule = CronSchedule(
        hour=_read_int("NICKNAME_SYNC_HOUR", default=4),
        minute=_read_int("NICKNAME_SYNC_MINUTE", default=0),
    )
    return (
        ScheduledTask(
            id="sync_default_nicknames",
            description="同步主播默认昵称到数据库",
            callback=add_default_nicknames,
            schedule=schedule,
        ),
    )


def _read_int(name: str, *, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer, got {value!r}") from error


def _read_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean, got {value!r}")
