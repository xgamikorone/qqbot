import unittest
from datetime import datetime
from unittest.mock import patch

from daily_usage_report import build_yesterday_usage_report
from dao import Dao
from utils.time_utils import BEIJING_TZ


class DailyUsageReportTests(unittest.TestCase):
    def setUp(self):
        self.dao = Dao(":memory:")
        self._insert("1", "user-1", "Alice", "wife", "2026-08-06 23:59:59")
        self._insert("2", "user-1", "Alice", "wife", "2026-08-07 01:00:00")
        self._insert("3", "user-2", "Bob", "wife", "2026-08-07 12:00:00")
        self._insert("4", "user-1", "Alice New", "rank", "2026-08-07 23:59:59")
        self._insert("5", "user-3", "Carol", "wife", "2026-08-08 00:00:00")
        self.dao.conn.commit()

    def tearDown(self):
        self.dao.close()

    def _insert(
        self,
        message_id: str,
        user_id: str,
        user_name: str,
        command_name: str,
        created_at: str,
    ) -> None:
        self.dao.conn.execute(
            """
            INSERT INTO command_records
                (message_id, channel_id, guild_id, content, created_at,
                 user_id, user_name, command_name, command_args)
            VALUES (?, 'channel', 'guild', '/command', ?, ?, ?, ?, '')
            """,
            (message_id, created_at, user_id, user_name, command_name),
        )

    def test_repository_summarizes_half_open_period_and_latest_user_name(self):
        summary = self.dao.command_records.get_usage_summary(
            start_at="2026-08-07 00:00:00",
            end_at="2026-08-08 00:00:00",
            limit=5,
        )

        self.assertEqual(3, summary.total_commands)
        self.assertEqual(2, summary.unique_users)
        self.assertEqual(
            [("wife", 2), ("rank", 1)],
            [(item.name, item.count) for item in summary.top_commands],
        )
        self.assertEqual(
            [("user-1", "Alice New", 2), ("user-2", "Bob", 1)],
            [
                (item.user_id, item.user_name, item.count)
                for item in summary.top_users
            ],
        )

    def test_builds_yesterday_report_in_beijing_time(self):
        now = datetime(2026, 8, 8, 2, 0, tzinfo=BEIJING_TZ)
        with (
            patch("daily_usage_report.get_dao", return_value=self.dao),
            patch.dict(
                "daily_usage_report._command_name_to_formal_name",
                {"wife": "今日老婆", "rank": "排行榜"},
                clear=True,
            ),
        ):
            report = build_yesterday_usage_report(limit=5, now=now)
            content = report.render()

        self.assertEqual("2026-08-07", report.date)
        self.assertIn("总调用：3 次 · 活跃成员：2 人", content)
        self.assertIn("1. 今日老婆：2 次", content)
        self.assertIn("1. Alice New：2 次", content)

    def test_empty_period_has_a_compact_message(self):
        with patch("daily_usage_report.get_dao", return_value=self.dao):
            report = build_yesterday_usage_report(
                now=datetime(2026, 8, 10, 2, 0, tzinfo=BEIJING_TZ)
            )

        self.assertIn("总调用：0 次 · 活跃成员：0 人", report.render())
        self.assertIn("昨日没有命令使用记录", report.render())


if __name__ == "__main__":
    unittest.main()
