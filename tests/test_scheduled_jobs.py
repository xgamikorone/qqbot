import os
import unittest
from unittest.mock import AsyncMock, patch

from scheduled_jobs import build_scheduled_tasks, generate_fans_and_guards_message


class ScheduledJobsTests(unittest.TestCase):
    def test_builds_default_nickname_sync(self):
        environment = {
            "NICKNAME_SYNC_ENABLED": "true",
            "NICKNAME_SYNC_HOUR": "6",
            "NICKNAME_SYNC_MINUTE": "15",
        }
        with patch.dict(os.environ, environment):
            tasks = build_scheduled_tasks()

        self.assertEqual(1, len(tasks))
        self.assertEqual("sync_default_nicknames", tasks[0].id)
        self.assertEqual(6, tasks[0].schedule.hour)
        self.assertEqual(15, tasks[0].schedule.minute)

    def test_can_disable_nickname_sync(self):
        with patch.dict(os.environ, {"NICKNAME_SYNC_ENABLED": "false"}):
            self.assertEqual((), build_scheduled_tasks())

    def test_rejects_invalid_configuration(self):
        with patch.dict(os.environ, {"NICKNAME_SYNC_ENABLED": "sometimes"}):
            with self.assertRaisesRegex(ValueError, "must be a boolean"):
                build_scheduled_tasks()

        environment = {
            "NICKNAME_SYNC_ENABLED": "true",
            "NICKNAME_SYNC_HOUR": "morning",
        }
        with patch.dict(os.environ, environment):
            with self.assertRaisesRegex(ValueError, "must be an integer"):
                build_scheduled_tasks()


class ScheduledMessageJobTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_and_runs_fans_guards_message_task(self):
        sender = AsyncMock()
        environment = {
            "NICKNAME_SYNC_ENABLED": "false",
            "FANS_GUARDS_MESSAGE_ENABLED": "true",
            "FANS_GUARDS_MESSAGE_CHANNEL_ID": "channel-1",
            "FANS_GUARDS_MESSAGE_CATEGORY": "wan",
            "FANS_GUARDS_MESSAGE_HOUR": "22",
            "FANS_GUARDS_MESSAGE_MINUTE": "10",
        }
        generator = AsyncMock(return_value="stats message")

        with (
            patch.dict(os.environ, environment),
            patch("scheduled_jobs.generate_fans_and_guards_message", new=generator),
        ):
            tasks = build_scheduled_tasks(message_sender=sender)
            await tasks[0].callback()

        self.assertEqual(1, len(tasks))
        self.assertEqual("send_fans_and_guards_message", tasks[0].id)
        self.assertEqual(22, tasks[0].schedule.hour)
        self.assertEqual(10, tasks[0].schedule.minute)
        generator.assert_awaited_once_with("wan")
        sender.assert_awaited_once_with("channel-1", "stats message")

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
