import os
import unittest
from unittest.mock import patch

from scheduled_jobs import build_scheduled_tasks


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


if __name__ == "__main__":
    unittest.main()
