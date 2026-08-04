import unittest

from dao import Dao


class CommandRecordDaoBehaviorTest(unittest.TestCase):
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
            self.dao.add_command_record(
                message_id, "channel", guild_id, "/command", user_id,
                user_name, command_name, ""
            )
        )

    def test_command_and_user_counts_are_scoped_to_guild(self):
        self.assertEqual(
            [("wife", 3), ("rank", 1)],
            [(row["command_name"], row["count"]) for row in self.dao.get_command_counts_cur_guild("guild-a")],
        )
        self.assertEqual(
            [("wife", 2)],
            [(row["command_name"], row["count"]) for row in self.dao.get_user_command_counts_cur_guild("user-1", "guild-a")],
        )

    def test_command_user_ranking_and_rank_count(self):
        rows = self.dao.get_command_counts_per_user_cur_guild("wife", "guild-a")
        count = self.dao.get_command_counts_by_user_cur_guild("wife", "user-2", "guild-a")
        rank = self.dao.get_command_counts_rank_by_user_cur_guild("wife", "guild-a", count["count"])
        self.assertEqual([("user-1", 2), ("user-2", 1)], [(r["user_id"], r["count"]) for r in rows])
        self.assertEqual(1, count["count"])
        self.assertEqual(1, rank["greater_count"])

    def test_history_names_and_fuzzy_search(self):
        self.assertEqual(["Alice2", "Alice"], self.dao.get_user_history_nicknames("user-1", "guild-a"))
        self.assertEqual(
            [{"user_id": "user-1", "user_name": "Alice2"}],
            self.dao.get_user_by_nickname_like_in_records("Alice2", "guild-a"),
        )


if __name__ == "__main__":
    unittest.main()
