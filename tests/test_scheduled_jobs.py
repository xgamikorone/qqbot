import unittest
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from scheduled_jobs import build_scheduled_tasks, generate_fans_and_guards_message
from scheduled_task_config import ScheduledTasksConfig, TaskConfig
from task_scheduler import CronSchedule


def make_config(tasks: dict[str, TaskConfig]) -> ScheduledTasksConfig:
    return ScheduledTasksConfig(timezone=ZoneInfo("Asia/Shanghai"), tasks=tasks)


def make_task_config(
    *,
    enabled: bool = True,
    hour: int = 4,
    minute: int = 0,
    parameters: dict | None = None,
) -> TaskConfig:
    return TaskConfig(
        enabled=enabled,
        schedule=CronSchedule(hour=hour, minute=minute),
        parameters=parameters or {},
    )


class ScheduledJobsTests(unittest.TestCase):
    def test_builds_nickname_sync_from_typed_config(self):
        config = make_config(
            {
                "sync_default_nicknames": make_task_config(
                    hour=6,
                    minute=15,
                )
            }
        )

        tasks = build_scheduled_tasks(config)

        self.assertEqual(1, len(tasks))
        self.assertEqual("sync_default_nicknames", tasks[0].id)
        self.assertEqual(6, tasks[0].schedule.hour)
        self.assertEqual(15, tasks[0].schedule.minute)

    def test_disabled_or_absent_tasks_are_not_built(self):
        disabled_config = make_config(
            {"sync_default_nicknames": make_task_config(enabled=False)}
        )

        self.assertEqual((), build_scheduled_tasks(disabled_config))
        self.assertEqual((), build_scheduled_tasks(make_config({})))

    def test_rejects_unknown_task_ids_and_parameters(self):
        unknown_task = make_config({"run_arbitrary_code": make_task_config()})
        with self.assertRaisesRegex(ValueError, "unknown scheduled task IDs"):
            build_scheduled_tasks(unknown_task)

        unknown_parameter = make_config(
            {
                "sync_default_nicknames": make_task_config(
                    parameters={"callback": "module.function"}
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "unknown parameters"):
            build_scheduled_tasks(unknown_parameter)


class ScheduledMessageJobTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_and_runs_fans_guards_message_task(self):
        sender = AsyncMock()
        config = make_config(
            {
                "send_fans_and_guards_message": make_task_config(
                    hour=22,
                    minute=10,
                    parameters={"channel_id": "channel-1", "category": "wan"},
                )
            }
        )
        generator = AsyncMock(return_value="stats message")

        with patch(
            "scheduled_jobs.generate_fans_and_guards_message", new=generator
        ):
            tasks = build_scheduled_tasks(config, message_sender=sender)
            await tasks[0].callback()

        self.assertEqual(1, len(tasks))
        self.assertEqual("send_fans_and_guards_message", tasks[0].id)
        self.assertEqual(22, tasks[0].schedule.hour)
        self.assertEqual(10, tasks[0].schedule.minute)
        generator.assert_awaited_once_with("wan")
        sender.assert_awaited_once_with("channel-1", "stats message")

    def test_enabled_message_task_requires_sender_and_parameters(self):
        missing_sender = make_config(
            {
                "send_fans_and_guards_message": make_task_config(
                    parameters={"channel_id": "channel-1", "category": "wan"}
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "message_sender is required"):
            build_scheduled_tasks(missing_sender)

        missing_channel = make_config(
            {
                "send_fans_and_guards_message": make_task_config(
                    parameters={"category": "wan"}
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "channel_id"):
            build_scheduled_tasks(missing_channel, message_sender=AsyncMock())

    async def test_generates_fans_and_guards_message(self):
        user_infos = {
            "1": {"name": "Alice", "room_id": 101},
            "2": {"name": "Bob", "room_id": 102},
        }
        fans_data = {
            "1": {"num_followers": 100, "delta": 2, "record_time": "fans-time"},
            "2": {"num_followers": 200, "delta": -1, "record_time": "fans-time"},
        }
        guards_data = {
            "1": {"num_guards": 10, "delta": 1, "record_time": "guard-time"},
            "2": {"num_guards": 20, "delta": 0, "record_time": "guard-time"},
        }

        with (
            patch.dict("scheduled_jobs.categories", {"test": [1, 2]}),
            patch(
                "scheduled_jobs.get_user_info_by_uids",
                new=AsyncMock(return_value=user_infos),
            ),
            patch(
                "scheduled_jobs.get_num_followers",
                new=AsyncMock(return_value=fans_data),
            ),
            patch(
                "scheduled_jobs.get_num_guards",
                new=AsyncMock(return_value=guards_data),
            ) as get_guards,
        ):
            content = await generate_fans_and_guards_message("test")

        self.assertIn("粉丝数:\nAlice: 100 (+2)\nBob: 200 (-1)", content)
        self.assertIn("舰长数:\nAlice: 10 (+1)\nBob: 20 (0)", content)
        self.assertTrue(content.endswith("对比时间: guard-time"))
        get_guards.assert_awaited_once_with([1, 2], [101, 102])


if __name__ == "__main__":
    unittest.main()
