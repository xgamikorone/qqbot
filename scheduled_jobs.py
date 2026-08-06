import os
from collections.abc import Awaitable, Callable

from add_default_nicknames import add_default_nicknames
from commands.api import get_num_followers, get_num_guards, get_user_info_by_uids
from commands.categories import categories
from task_scheduler import CronSchedule, ScheduledTask


MessageSender = Callable[[str, str], Awaitable[None]]


def build_scheduled_tasks(
    *, message_sender: MessageSender | None = None
) -> tuple[ScheduledTask, ...]:
    """根据环境变量生成本进程需要运行的定时任务。"""

    tasks = []
    if _read_bool("NICKNAME_SYNC_ENABLED", default=True):
        tasks.append(
            ScheduledTask(
                id="sync_default_nicknames",
                description="同步主播默认昵称到数据库",
                callback=add_default_nicknames,
                schedule=CronSchedule(
                    hour=_read_int("NICKNAME_SYNC_HOUR", default=4),
                    minute=_read_int("NICKNAME_SYNC_MINUTE", default=0),
                ),
            )
        )

    if message_sender is not None and _read_bool(
        "FANS_GUARDS_MESSAGE_ENABLED", default=True
    ):
        channel_id = os.getenv("FANS_GUARDS_MESSAGE_CHANNEL_ID", "8338248").strip()
        category = os.getenv("FANS_GUARDS_MESSAGE_CATEGORY", "wan").strip()

        async def send_fans_and_guards_message() -> None:
            content = await generate_fans_and_guards_message(category)
            await message_sender(channel_id, content)

        tasks.append(
            ScheduledTask(
                id="send_fans_and_guards_message",
                description="定时发送粉丝数和舰长数测试消息",
                callback=send_fans_and_guards_message,
                schedule=CronSchedule(
                    hour=_read_int("FANS_GUARDS_MESSAGE_HOUR", default=23),
                    minute=_read_int("FANS_GUARDS_MESSAGE_MINUTE", default=55),
                ),
            )
        )

    return tuple(tasks)


async def generate_fans_and_guards_message(category: str = "wan") -> str:
    uids = categories[category]
    user_infos = await get_user_info_by_uids(uids)
    if user_infos is None:
        return "获取用户信息失败"

    fans_data = await get_num_followers(uids)
    if fans_data is None:
        return "获取粉丝信息失败"

    filtered_uids = [uid for uid in uids if str(uid) in user_infos]
    fans_lines = []
    record_time = ""
    for uid in filtered_uids:
        fans_info = fans_data.get(str(uid), {})
        num_followers = fans_info.get("num_followers")
        delta = fans_info.get("delta")
        delta_str = f"+{delta}" if delta is not None and delta > 0 else str(delta)
        suffix = f" ({delta_str})" if delta is not None else ""
        fans_lines.append(
            f"{user_infos[str(uid)]['name']}: "
            f"{num_followers if num_followers is not None else '获取失败'}{suffix}"
        )
        record_time = fans_info.get("record_time", record_time)

    room_ids = [user_infos[str(uid)]["room_id"] for uid in filtered_uids]
    guards_data = await get_num_guards(filtered_uids, room_ids)
    if guards_data is None:
        return "粉丝数:\n" + "\n".join(fans_lines) + "\n\n获取舰长信息失败"

    guards_lines = []
    for uid in filtered_uids:
        guard_info = guards_data.get(str(uid), {})
        num_guards = guard_info.get("num_guards")
        delta = guard_info.get("delta")
        delta_str = f"+{delta}" if delta is not None and delta > 0 else str(delta)
        suffix = f" ({delta_str})" if delta is not None else ""
        guards_lines.append(
            f"{user_infos[str(uid)]['name']}: "
            f"{num_guards if num_guards is not None else '获取失败'}{suffix}"
        )
        record_time = guard_info.get("record_time", record_time)

    return (
        "粉丝数:\n"
        + "\n".join(fans_lines)
        + "\n\n舰长数:\n"
        + "\n".join(guards_lines)
        + f"\n\n对比时间: {record_time}"
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
