import unittest

from dao import Dao


class CommandRecordRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.dao = Dao(":memory:")
        self._record("1", "guild-a", "user-1", "Alice", "wife")
        self._record("2", "guild-a", "user-1", "Alice2", "wife")
        self._record("3", "guild-a", "user-2", "Bob", "wife")
        self._record("4", "guild-a", "user-2", "Bob", "rank")
        self._record("5", "guild-b", "user-3", "Carol", "wife")

    def tearDown(self):
        self.dao.close()

    def _record(self, message_id, guild_id, user_id, user_name, command_name):
        self.assertTrue(
            self.dao.command_records.record(
                message_id, "channel", guild_id, "/command", user_id,
                user_name, command_name, ""
            )
        )

    def test_command_and_user_counts_are_scoped_to_guild(self):
        self.assertEqual(
            [("wife", 3), ("rank", 1)],
            [(row["command_name"], row["count"]) for row in self.dao.command_records.get_command_counts("guild-a")],
        )
        self.assertEqual(
            [("wife", 2)],
            [(row["command_name"], row["count"]) for row in self.dao.command_records.get_user_counts("user-1", "guild-a")],
        )

    def test_command_user_ranking_and_rank_count(self):
        rows = self.dao.command_records.get_command_users("wife", "guild-a")
        count = self.dao.command_records.get_user_command_count("wife", "user-2", "guild-a")
        rank = self.dao.command_records.get_command_user_rank("wife", "guild-a", count)
        self.assertEqual([("user-1", 2), ("user-2", 1)], [(r["user_id"], r["count"]) for r in rows])
        self.assertEqual(1, count)
        self.assertEqual(2, rank)

    def test_history_names_and_fuzzy_search(self):
        self.assertEqual(["Alice2", "Alice"], self.dao.command_records.get_user_history("user-1", "guild-a"))
        self.assertEqual(
            [{"user_id": "user-1", "user_name": "Alice2"}],
            self.dao.command_records.find_users_by_nickname("Alice2", "guild-a"),
        )


if __name__ == "__main__":
    unittest.main()
