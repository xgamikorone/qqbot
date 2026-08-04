import unittest

from dao import Dao


class ChuangDaoBehaviorTest(unittest.TestCase):
    def setUp(self):
        self.dao = Dao(":memory:")
        self._record("user-1", 100, "guild-a", "2026-08-01")
        self._record("user-2", 200, "guild-a", "2026-08-01")
        self._record("user-1", 300, "guild-a", "2026-08-02")
        self._record("user-3", 999, "guild-b", "2026-08-01")

    def tearDown(self):
        self.dao.close()

    def _record(self, user_id: str, distance: int, guild_id: str, date: str):
        self.dao.insert_chuang(user_id, distance, "channel", guild_id, date)

    def test_daily_distance_and_rank_are_scoped_to_guild(self):
        distance = self.dao.get_today_chuang_distance(
            "user-1", "guild-a", "2026-08-01"
        )
        rank = self.dao.get_today_chuang_rank_cur_guild(
            distance, "guild-a", "2026-08-01"
        )

        self.assertEqual(100, distance)
        self.assertEqual(2, rank)
        self.assertEqual(
            ["user-2", "user-1"],
            [
                row["user_id"]
                for row in self.dao.get_chuang_top_k_cur_guild(
                    10, "2026-08-01", "guild-a"
                )
            ],
        )

    def test_history_ranking_keeps_each_users_best_record(self):
        rows = self.dao.get_chuang_top_k_cur_guild_history(10, "guild-a")
        user_best = self.dao.get_user_chuang_history_best("user-2", "guild-a")

        self.assertEqual(
            [("user-1", 300), ("user-2", 200)],
            [(row["user_id"], row["distance"]) for row in rows],
        )
        self.assertEqual(200, user_best["distance"])
        self.assertEqual(2, user_best["history_rank"])

    def test_total_distance_statistics_include_rank(self):
        rows = self.dao.get_chuang_total_top_k_cur_guild(10, "guild-a")
        user_total = self.dao.get_user_chuang_total("user-2", "guild-a")

        self.assertEqual(
            [("user-1", 400), ("user-2", 200)],
            [(row["user_id"], row["total_distance"]) for row in rows],
        )
        self.assertEqual(200, user_total["total_distance"])
        self.assertEqual(2, user_total["rank"])

    def test_average_and_count_statistics_honor_minimum_count(self):
        average_rows = self.dao.get_chuang_average_top_k_cur_guild(
            10, "guild-a", min_limit=2
        )
        count_rows = self.dao.get_chuang_times_rank_cur_guild("guild-a", 10)

        self.assertEqual(["user-1"], [row["user_id"] for row in average_rows])
        self.assertEqual(200.0, self.dao.get_user_chuang_average("user-1", "guild-a"))
        self.assertEqual(1, self.dao.get_avg_distance_rank_cur_guild(200, "guild-a", 2))
        self.assertEqual(
            [("user-1", 2), ("user-2", 1)],
            [(row["user_id"], row["chuang_time"]) for row in count_rows],
        )
        self.assertEqual(2, self.dao.get_user_chuang_times_rank_cur_guild(1, "guild-a"))


if __name__ == "__main__":
    unittest.main()
