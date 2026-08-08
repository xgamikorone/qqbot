import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from commands.scheduled_tasks import RunScheduledTaskCommand
from task_scheduler import CronSchedule, ScheduledTask


def make_task(task_id: str = "sync_default_nicknames") -> ScheduledTask:
    return ScheduledTask(
        id=task_id,
        description="同步主播默认昵称并检查 Live Monitor",
        callback=lambda: None,
        schedule=CronSchedule(hour=4),
    )


class RunScheduledTaskCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.scheduler = SimpleNamespace(
            list_tasks=Mock(return_value=(make_task(),)),
            run_now=AsyncMock(),
        )
        self.api = SimpleNamespace(post_message=AsyncMock())
        self.command = RunScheduledTaskCommand(
            SimpleNamespace(api=self.api, task_scheduler=self.scheduler)
        )
        self.message = SimpleNamespace(channel_id="command-channel", id="message-1")

    async def test_lists_registered_tasks_without_arguments(self):
        await self.command.execute(self.message, [])

        content = self.api.post_message.await_args.kwargs["content"]
        self.assertIn("sync_default_nicknames", content)
        self.assertIn("同步主播默认昵称并检查 Live Monitor", content)
        self.scheduler.run_now.assert_not_awaited()

    async def test_runs_registered_task_by_id(self):
        await self.command.execute(self.message, ["sync_default_nicknames"])

        self.scheduler.run_now.assert_awaited_once_with("sync_default_nicknames")
        replies = [call.kwargs["content"] for call in self.api.post_message.await_args_list]
        self.assertIn("开始执行定时任务：sync_default_nicknames", replies)
        self.assertIn("定时任务执行成功：sync_default_nicknames", replies)

    async def test_reports_task_failure_without_leaking_exception_details(self):
        self.scheduler.run_now.side_effect = RuntimeError("sensitive detail")

        await self.command.execute(self.message, ["sync_default_nicknames"])

        final_reply = self.api.post_message.await_args.kwargs["content"]
        self.assertIn("结果异常", final_reply)
        self.assertNotIn("sensitive detail", final_reply)

    async def test_rejects_unknown_task_id(self):
        await self.command.execute(self.message, ["missing"])

        self.scheduler.run_now.assert_not_awaited()
        content = self.api.post_message.await_args.kwargs["content"]
        self.assertIn("未找到已注册的定时任务：missing", content)

    def test_command_is_owner_only_and_documented(self):
        self.assertTrue(self.command.owner_only)
        self.assertEqual("管理", self.command.help.category)


if __name__ == "__main__":
    unittest.main()
