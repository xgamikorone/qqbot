from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from add_default_nicknames import add_default_nicknames
from commands.api import get_num_followers, get_num_guards, get_user_info_by_uids
from commands.categories import categories
from live_monitor_client import LiveMonitorError, check_live_monitor_health
from scheduled_task_config import ScheduledTasksConfig, TaskConfig
from task_scheduler import ScheduledTask


MessageSender = Callable[[str, str], Awaitable[None]]


@dataclass(frozen=True)
class TaskDependencies:
    message_sender: MessageSender | None = None


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


def _build_nickname_sync(
    config: TaskConfig, dependencies: TaskDependencies
) -> ScheduledTask:
    task_id = "sync_default_nicknames"
    _reject_unknown_parameters(
        task_id,
        config,
        allowed={"channel_id", "max_age_seconds"},
    )
    sender = dependencies.message_sender
    if sender is None:
        raise ValueError(f"message_sender is required for {task_id}")

    channel_id = _require_string_parameter(task_id, config, "channel_id")
    max_age_seconds = _optional_int_parameter(
        task_id,
        config,
        "max_age_seconds",
        default=30,
        minimum=5,
        maximum=300,
    )

    async def execute() -> None:
        failures: list[str] = []
        try:
            added_count = await add_default_nicknames()
            nickname_result = f"默认昵称同步：成功，新增 {added_count} 个昵称"
        except Exception:
            failures.append("默认昵称同步")
            nickname_result = "默认昵称同步：失败，请查看程序日志"

        try:
            health = await check_live_monitor_health(max_age_seconds)
            health_result = health.render()
            if not health.healthy:
                failures.append("Live Monitor 健康检查")
        except LiveMonitorError as error:
            failures.append("Live Monitor 健康检查")
            health_result = f"Live Monitor：检查失败（{error}）"
        except Exception:
            failures.append("Live Monitor 健康检查")
            health_result = "Live Monitor：检查失败，请查看程序日志"

        content = "定时任务执行结果\n\n" + nickname_result + "\n\n" + health_result
        await sender(channel_id, content)

        if failures:
            failed_steps = "、".join(failures)
            raise RuntimeError(f"scheduled task steps failed: {failed_steps}")

    return ScheduledTask(
        id=task_id,
        description="同步主播默认昵称并检查 Live Monitor",
        callback=execute,
        schedule=config.schedule,
    )


def _build_fans_and_guards_message(
    config: TaskConfig, dependencies: TaskDependencies
) -> ScheduledTask:
    task_id = "send_fans_and_guards_message"
    _reject_unknown_parameters(
        task_id,
        config,
        allowed={"channel_id", "category"},
    )
    sender = dependencies.message_sender
    if sender is None:
        raise ValueError(f"message_sender is required for {task_id}")

    channel_id = _require_string_parameter(task_id, config, "channel_id")
    category = _require_string_parameter(task_id, config, "category")

    async def execute() -> None:
        content = await generate_fans_and_guards_message(category)
        await sender(channel_id, content)

    return ScheduledTask(
        id=task_id,
        description="定时发送粉丝数和舰长数测试消息",
        callback=execute,
        schedule=config.schedule,
    )


TaskBuilder = Callable[[TaskConfig, TaskDependencies], ScheduledTask]
TASK_BUILDERS: dict[str, TaskBuilder] = {
    "sync_default_nicknames": _build_nickname_sync,
    "send_fans_and_guards_message": _build_fans_and_guards_message,
}


def build_scheduled_tasks(
    config: ScheduledTasksConfig,
    *,
    message_sender: MessageSender | None = None,
) -> tuple[ScheduledTask, ...]:
    """将已验证的配置绑定到代码中明确注册的任务工厂。"""

    dependencies = TaskDependencies(message_sender=message_sender)
    tasks = []
    for task_id, task_config in config.tasks.items():
        try:
            builder = TASK_BUILDERS[task_id]
        except KeyError as error:
            raise ValueError(f"unknown scheduled task IDs: {task_id}") from error

        if task_config.enabled:
            tasks.append(builder(task_config, dependencies))

    return tuple(tasks)


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


def _optional_int_parameter(
    task_id: str,
    task_config: TaskConfig,
    parameter_name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = task_config.parameters.get(parameter_name, default)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ValueError(
            f"scheduled task {task_id}.{parameter_name} must be an integer "
            f"between {minimum} and {maximum}"
        )
    return value
