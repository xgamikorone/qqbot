from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from task_scheduler import CronSchedule


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "scheduled_tasks.yaml"


class ScheduledTaskConfigError(ValueError):
    """定时任务配置无法解析或验证。"""


@dataclass(frozen=True)
class TaskConfig:
    enabled: bool
    schedule: CronSchedule
    parameters: Mapping[str, Any]


@dataclass(frozen=True)
class ScheduledTasksConfig:
    timezone: ZoneInfo
    tasks: Mapping[str, TaskConfig]


def load_scheduled_tasks_config(
    path: str | Path | None = None,
) -> ScheduledTasksConfig:
    config_path = Path(
        path or os.getenv("SCHEDULED_TASKS_CONFIG") or DEFAULT_CONFIG_PATH
    )
    try:
        with config_path.open("r", encoding="utf-8") as file:
            raw_config = yaml.safe_load(file)
    except OSError as error:
        raise ScheduledTaskConfigError(
            f"cannot read scheduled task config {config_path}: {error}"
        ) from error
    except yaml.YAMLError as error:
        raise ScheduledTaskConfigError(
            f"invalid YAML in scheduled task config {config_path}: {error}"
        ) from error

    root = _require_mapping(raw_config, "config root")
    _reject_unknown_keys(root, {"timezone", "tasks"}, "config root")

    timezone_name = root.get("timezone", "Asia/Shanghai")
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ScheduledTaskConfigError("timezone must be a non-empty string")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ScheduledTaskConfigError(
            f"unknown scheduled task timezone: {timezone_name}"
        ) from error

    raw_tasks = _require_mapping(root.get("tasks", {}), "tasks")
    tasks: dict[str, TaskConfig] = {}
    for task_id, raw_task in raw_tasks.items():
        if not isinstance(task_id, str) or not task_id.strip():
            raise ScheduledTaskConfigError("task IDs must be non-empty strings")
        tasks[task_id] = _parse_task(task_id, raw_task)

    return ScheduledTasksConfig(timezone=timezone, tasks=tasks)


def _parse_task(task_id: str, raw_task: Any) -> TaskConfig:
    task = _require_mapping(raw_task, f"task {task_id}")
    _reject_unknown_keys(
        task,
        {"enabled", "schedule", "parameters"},
        f"task {task_id}",
    )

    enabled = task.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ScheduledTaskConfigError(f"task {task_id}.enabled must be a boolean")

    raw_schedule = _require_mapping(task.get("schedule"), f"task {task_id}.schedule")
    _reject_unknown_keys(
        raw_schedule,
        {"hour", "minute", "day_of_week"},
        f"task {task_id}.schedule",
    )
    hour = _require_int(raw_schedule.get("hour"), f"task {task_id}.schedule.hour")
    minute = _require_int(
        raw_schedule.get("minute", 0), f"task {task_id}.schedule.minute"
    )
    day_of_week = raw_schedule.get("day_of_week")
    if day_of_week is not None and not isinstance(day_of_week, (str, int)):
        raise ScheduledTaskConfigError(
            f"task {task_id}.schedule.day_of_week must be a string or integer"
        )
    try:
        schedule = CronSchedule(
            hour=hour,
            minute=minute,
            day_of_week=day_of_week,
        )
    except ValueError as error:
        raise ScheduledTaskConfigError(f"task {task_id}.schedule: {error}") from error

    parameters = _require_mapping(
        task.get("parameters", {}), f"task {task_id}.parameters"
    )
    return TaskConfig(
        enabled=enabled,
        schedule=schedule,
        parameters=dict(parameters),
    )


def _require_mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ScheduledTaskConfigError(f"{location} must be a mapping")
    return value


def _require_int(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScheduledTaskConfigError(f"{location} must be an integer")
    return value


def _reject_unknown_keys(
    mapping: Mapping[str, Any], allowed: set[str], location: str
) -> None:
    unknown = set(mapping) - allowed
    if unknown:
        names = ", ".join(sorted(str(key) for key in unknown))
        raise ScheduledTaskConfigError(f"unknown keys in {location}: {names}")
