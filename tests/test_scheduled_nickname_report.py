import unittest
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from live_monitor_client import (
    LiveMonitorError,
    LiveMonitorHealth,
    MonitorComponentHealth,
)
from scheduled_jobs import build_scheduled_tasks
from scheduled_task_config import ScheduledTasksConfig, TaskConfig
from task_scheduler import CronSchedule


def make_config(*, max_age_seconds: int = 30) -> ScheduledTasksConfig:
    return ScheduledTasksConfig(
        timezone=ZoneInfo("Asia/Shanghai"),
        tasks={
            "sync_default_nicknames": TaskConfig(
                enabled=True,
                schedule=CronSchedule(hour=4),
                parameters={
                    "channel_id": "channel-1",
                    "max_age_seconds": max_age_seconds,
                },
            )
        },
    )


class ScheduledNicknameReportTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_nickname_and_health_results_to_configured_channel(self):
        sender = AsyncMock()
        health = LiveMonitorHealth(
            healthy=True,
            status="healthy",
            components=(
                MonitorComponentHealth(
                    name="LiveMonitor",
                    healthy=True,
                    status="running",
                    age_seconds=2.5,
                ),
            ),
        )

        with (
            patch(
                "scheduled_jobs.add_default_nicknames",
                new=AsyncMock(return_value=3),
            ) as sync,
            patch(
                "scheduled_jobs.check_live_monitor_health",
                new=AsyncMock(return_value=health),
            ) as check_health,
        ):
            task = build_scheduled_tasks(
                make_config(max_age_seconds=45),
                message_sender=sender,
            )[0]
            await task.callback()

        sync.assert_awaited_once_with()
        check_health.assert_awaited_once_with(45)
        sender.assert_awaited_once()
        channel_id, content = sender.await_args.args
        self.assertEqual("channel-1", channel_id)
        self.assertIn("默认昵称同步：成功，新增 3 个昵称", content)
        self.assertIn("Live Monitor：正常（healthy）", content)
        self.assertIn("LiveMonitor：正常（running，心跳 2.5 秒前）", content)

    async def test_reports_both_failures_before_marking_task_failed(self):
        sender = AsyncMock()
        with (
            patch(
                "scheduled_jobs.add_default_nicknames",
                new=AsyncMock(side_effect=RuntimeError("database unavailable")),
            ),
            patch(
                "scheduled_jobs.check_live_monitor_health",
                new=AsyncMock(
                    side_effect=LiveMonitorError("无法连接 Live Monitor")
                ),
            ) as check_health,
        ):
            task = build_scheduled_tasks(
                make_config(),
                message_sender=sender,
            )[0]
            with self.assertRaisesRegex(RuntimeError, "scheduled task steps failed"):
                await task.callback()

        check_health.assert_awaited_once_with(30)
        sender.assert_awaited_once()
        content = sender.await_args.args[1]
        self.assertIn("默认昵称同步：失败", content)
        self.assertIn("Live Monitor：检查失败（无法连接 Live Monitor）", content)

    def test_requires_sender_channel_and_valid_max_age(self):
        with self.assertRaisesRegex(ValueError, "message_sender is required"):
            build_scheduled_tasks(make_config())

        with self.assertRaisesRegex(ValueError, "max_age_seconds"):
            build_scheduled_tasks(
                make_config(max_age_seconds=301),
                message_sender=AsyncMock(),
            )


if __name__ == "__main__":
    unittest.main()
