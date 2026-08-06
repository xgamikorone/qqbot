from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import tzinfo
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


logger = logging.getLogger(__name__)
BEIJING_TZ = ZoneInfo("Asia/Shanghai")

TaskCallback = Callable[[], Awaitable[Any] | Any]


@dataclass(frozen=True)
class CronSchedule:
    """一个按北京时间触发的 Cron 计划。"""

    hour: int
    minute: int = 0
    day_of_week: str | int | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.hour <= 23:
            raise ValueError("hour must be between 0 and 23")
        if not 0 <= self.minute <= 59:
            raise ValueError("minute must be between 0 and 59")


@dataclass(frozen=True)
class ScheduledTask:
    """定时任务的声明，不包含调度器的运行状态。"""

    id: str
    description: str
    callback: TaskCallback
    schedule: CronSchedule

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("task id cannot be empty")
        if not callable(self.callback):
            raise TypeError("task callback must be callable")


class TaskScheduler:
    """
    统一管理定时任务的注册、生命周期、手动执行和日志。

    任务回调可以是同步函数或异步函数。同一任务默认不允许并发执行，
    错过多次运行时会合并成一次。
    """

    def __init__(
        self,
        scheduler: AsyncIOScheduler | None = None,
        *,
        timezone: tzinfo = BEIJING_TZ,
    ) -> None:
        self._timezone = timezone
        self._scheduler = scheduler or AsyncIOScheduler(timezone=timezone)
        self._tasks: dict[str, ScheduledTask] = {}

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def register(self, task: ScheduledTask, *, replace: bool = False) -> None:
        if task.id in self._tasks and not replace:
            raise ValueError(f"scheduled task already registered: {task.id}")

        trigger_options: dict[str, Any] = {
            "hour": task.schedule.hour,
            "minute": task.schedule.minute,
            "timezone": self._timezone,
        }
        if task.schedule.day_of_week is not None:
            trigger_options["day_of_week"] = task.schedule.day_of_week

        trigger = CronTrigger(**trigger_options)
        self._scheduler.add_job(
            self._execute,
            trigger=trigger,
            args=(task,),
            id=task.id,
            name=task.description,
            replace_existing=replace,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
        )
        self._tasks[task.id] = task
        logger.info(
            "registered scheduled task: id=%s, description=%s",
            task.id,
            task.description,
        )

    def register_all(self, tasks: Iterable[ScheduledTask]) -> None:
        for task in tasks:
            self.register(task)

    def start(self) -> bool:
        if self.running:
            return False
        self._scheduler.start()
        logger.info("task scheduler started with %d tasks", len(self._tasks))
        return True

    def remove(self, task_id: str) -> bool:
        if task_id not in self._tasks:
            return False
        try:
            self._scheduler.remove_job(task_id)
        except JobLookupError:
            logger.warning("scheduled job was already absent: id=%s", task_id)
        del self._tasks[task_id]
        logger.info("removed scheduled task: id=%s", task_id)
        return True

    def list_tasks(self) -> tuple[ScheduledTask, ...]:
        return tuple(self._tasks.values())

    async def run_now(self, task_id: str) -> None:
        try:
            task = self._tasks[task_id]
        except KeyError as error:
            raise KeyError(f"unknown scheduled task: {task_id}") from error
        await self._execute(task)

    def shutdown(self, *, wait: bool = True) -> bool:
        if not self.running:
            return False
        self._scheduler.shutdown(wait=wait)
        logger.info("task scheduler stopped")
        return True

    async def _execute(self, task: ScheduledTask) -> None:
        logger.info(
            "scheduled task started: id=%s, description=%s",
            task.id,
            task.description,
        )
        try:
            result = task.callback()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("scheduled task failed: id=%s", task.id)
            raise
        logger.info("scheduled task completed: id=%s", task.id)
