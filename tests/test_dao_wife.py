import unittest

from dao import Dao


class WifeDaoTest(unittest.TestCase):
    def setUp(self):
        self.dao = Dao(":memory:")

    def tearDown(self):
        self.dao.close()

    def _add_wife_record(
        self, user_id: str, wife_name: str, date: str, url_suffix: str = ""
    ) -> None:
        wife_id = self.dao.add_wife(
            wife_name, f"https://example.com/{wife_name}/{url_suffix or date}.jpg"
        )
        self.assertIsNotNone(wife_id)
        self.dao.conn.execute(
            """
            INSERT INTO user_wife_daily
                (user_id, wife_id, channel_id, guild_id, date)
            VALUES (?, ?, 'channel', 'guild', ?)
            """,
            (user_id, wife_id, date),
        )
        self.dao.conn.commit()

    def test_schema_is_initialized_for_new_database(self):
        tables = {
            row["name"]
            for row in self.dao.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        self.assertTrue(
            {"users", "command_records", "wife_urls", "user_wife_daily"}
            <= tables
        )

    def test_wife_user_ranking_is_paginated(self):
        for index in range(12):
            self._add_wife_record(
                user_id=f"user-{index:02d}",
                wife_name="Alice",
                date=f"2026-07-{index + 1:02d}",
                url_suffix=str(index),
            )

        first_page = self.dao.get_wife_user_counts_by_name("Alice", page=1)
        second_page = self.dao.get_wife_user_counts_by_name("Alice", page=2)

        self.assertEqual(10, len(first_page))
        self.assertEqual(["user-10", "user-11"], [row["user_id"] for row in second_page])

    def test_wife_counts_merge_rows_with_the_same_name(self):
        self._add_wife_record("user-1", "Alice", "2026-07-01", "first")
        self._add_wife_record("user-1", "Alice", "2026-07-02", "second")

        rows = self.dao.get_user_wife_counts("user-1")

        self.assertEqual(1, len(rows))
        self.assertEqual("Alice", rows[0]["name"])
        self.assertEqual(2, rows[0]["count"])


if __name__ == "__main__":
    unittest.main()
