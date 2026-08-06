from collections.abc import Awaitable, Callable

from add_default_nicknames import add_default_nicknames
from commands.api import get_num_followers, get_num_guards, get_user_info_by_uids
from commands.categories import categories
from scheduled_task_config import ScheduledTasksConfig, TaskConfig
from task_scheduler import ScheduledTask


MessageSender = Callable[[str, str], Awaitable[None]]
SUPPORTED_TASK_IDS = {
    "sync_default_nicknames",
    "send_fans_and_guards_message",
}


def build_scheduled_tasks(
    config: ScheduledTasksConfig,
    *,
    message_sender: MessageSender | None = None,
) -> tuple[ScheduledTask, ...]:
    """将已验证的配置绑定到代码中明确允许的任务回调。"""

    unknown_task_ids = set(config.tasks) - SUPPORTED_TASK_IDS
    if unknown_task_ids:
        names = ", ".join(sorted(unknown_task_ids))
        raise ValueError(f"unknown scheduled task IDs: {names}")

    tasks = []
    nickname_config = config.tasks.get("sync_default_nicknames")
    if nickname_config is not None:
        _reject_unknown_parameters(
            "sync_default_nicknames", nickname_config, allowed=set()
        )
        if nickname_config.enabled:
            tasks.append(
                ScheduledTask(
                    id="sync_default_nicknames",
                    description="同步主播默认昵称到数据库",
                    callback=add_default_nicknames,
                    schedule=nickname_config.schedule,
                )
            )

    message_config = config.tasks.get("send_fans_and_guards_message")
    if message_config is not None:
        _reject_unknown_parameters(
            "send_fans_and_guards_message",
            message_config,
            allowed={"channel_id", "category"},
        )
        if message_config.enabled:
            if message_sender is None:
                raise ValueError(
                    "message_sender is required for send_fans_and_guards_message"
                )
            channel_id = _require_string_parameter(
                "send_fans_and_guards_message", message_config, "channel_id"
            )
            category = _require_string_parameter(
                "send_fans_and_guards_message", message_config, "category"
            )

            async def send_fans_and_guards_message() -> None:
                content = await generate_fans_and_guards_message(category)
                await message_sender(channel_id, content)

            tasks.append(
                ScheduledTask(
                    id="send_fans_and_guards_message",
                    description="定时发送粉丝数和舰长数测试消息",
                    callback=send_fans_and_guards_message,
                    schedule=message_config.schedule,
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


def _reject_unknown_parameters(
    task_id: str, task_config: TaskConfig, *, allowed: set[str]
) -> None:
    unknown = set(task_config.parameters) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"unknown parameters for scheduled task {task_id}: {names}")


def _require_string_parameter(
    task_id: str, task_config: TaskConfig, parameter_name: str
) -> str:
    value = task_config.parameters.get(parameter_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"scheduled task {task_id}.{parameter_name} must be a non-empty string"
        )
    return value.strip()
