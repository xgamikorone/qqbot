import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from commands.scheduled_tasks import (
    RunScheduledTaskCommand,
    parse_task_parameter_overrides,
)
from scheduled_task_errors import ScheduledTaskParameterError
from task_scheduler import CronSchedule, ScheduledTask


def make_task(task_id: str = "daily_maintenance_report") -> ScheduledTask:
    return ScheduledTask(
        id=task_id,
        description="每日维护与使用汇报",
        callback=lambda: None,
        schedule=CronSchedule(hour=4),
    )


class RunScheduledTaskCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.scheduler = SimpleNamespace(
            list_tasks=Mock(return_value=(make_task(),)),
            run_now=AsyncMock(),
        )
        self.runner = AsyncMock()
        self.api = SimpleNamespace(post_message=AsyncMock())
        self.command = RunScheduledTaskCommand(
            SimpleNamespace(
                api=self.api,
                task_scheduler=self.scheduler,
                run_scheduled_task=self.runner,
            )
        )
        self.message = SimpleNamespace(channel_id="command-channel", id="message-1")

    async def test_lists_registered_tasks_without_arguments(self):
        await self.command.execute(self.message, [])

        content = self.api.post_message.await_args.kwargs["content"]
        self.assertIn("daily_maintenance_report", content)
        self.assertIn("每日维护与使用汇报", content)
        self.scheduler.run_now.assert_not_awaited()
        self.runner.assert_not_awaited()

    async def test_runs_registered_task_by_id(self):
        await self.command.execute(self.message, ["daily_maintenance_report"])

        self.runner.assert_awaited_once_with(
            "daily_maintenance_report", {}
        )
        replies = [call.kwargs["content"] for call in self.api.post_message.await_args_list]
        self.assertIn("开始执行定时任务：daily_maintenance_report", replies)
        self.assertIn("定时任务执行成功：daily_maintenance_report", replies)

    async def test_reports_task_failure_without_leaking_exception_details(self):
        self.runner.side_effect = RuntimeError("sensitive detail")

        await self.command.execute(self.message, ["daily_maintenance_report"])

        final_reply = self.api.post_message.await_args.kwargs["content"]
        self.assertIn("结果异常", final_reply)
        self.assertNotIn("sensitive detail", final_reply)

    async def test_rejects_unknown_task_id(self):
        await self.command.execute(self.message, ["missing"])

        self.scheduler.run_now.assert_not_awaited()
        content = self.api.post_message.await_args.kwargs["content"]
        self.assertIn("未找到已注册的定时任务：missing", content)

    async def test_passes_typed_parameter_overrides_to_runner(self):
        await self.command.execute(
            self.message,
            [
                "daily_maintenance_report",
                "usage_top_limit=10",
                "max_age_seconds=60",
            ],
        )

        self.runner.assert_awaited_once_with(
            "daily_maintenance_report",
            {"usage_top_limit": 10, "max_age_seconds": 60},
        )
        first_reply = self.api.post_message.await_args_list[0].kwargs["content"]
        self.assertIn("usage_top_limit=10", first_reply)

    async def test_reports_parameter_format_and_validation_errors(self):
        await self.command.execute(
            self.message,
            ["daily_maintenance_report", "usage_top_limit"],
        )
        self.runner.assert_not_awaited()
        self.assertIn(
            "参数格式错误",
            self.api.post_message.await_args.kwargs["content"],
        )

        self.api.post_message.reset_mock()
        self.runner.side_effect = ScheduledTaskParameterError(
            "usage_top_limit must be between 1 and 10"
        )
        await self.command.execute(
            self.message,
            ["daily_maintenance_report", "usage_top_limit=20"],
        )
        self.assertIn(
            "任务参数错误",
            self.api.post_message.await_args.kwargs["content"],
        )

    def test_parses_integer_boolean_and_string_values(self):
        self.assertEqual(
            {"count": -2, "enabled": True, "category": "wan"},
            parse_task_parameter_overrides(
                ["count=-2", "enabled=true", "category=wan"]
            ),
        )

    def test_command_is_owner_only_and_documented(self):
        self.assertTrue(self.command.owner_only)
        self.assertEqual("管理", self.command.help.category)


if __name__ == "__main__":
    unittest.main()
