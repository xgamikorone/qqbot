import unittest
from datetime import datetime

from utils.revenue_rank_v2 import normalize_realtime_revenue, parse_revenue_period_args


class RevenueRankV2Test(unittest.TestCase):
    def test_defaults_to_today_and_top_twenty(self):
        now = datetime(2026, 8, 9, 16, 30, 0)
        options = parse_revenue_period_args([], now=now)
        self.assertEqual(datetime(2026, 8, 9), options.start_time)
        self.assertEqual(now, options.end_time)
        self.assertEqual(20, options.top_n)

    def test_parses_date_range_and_top_n(self):
        options = parse_revenue_period_args(
            ["/s", "2026-08-01", "/e", "2026-08-02", "/n", "5"]
        )
        self.assertEqual(datetime(2026, 8, 1), options.start_time)
        self.assertEqual(datetime(2026, 8, 2, 23, 59, 59), options.end_time)
        self.assertEqual(5, options.top_n)

    def test_rejects_reversed_period(self):
        with self.assertRaisesRegex(ValueError, "开始时间"):
            parse_revenue_period_args(["/s", "2026-08-03", "/e", "2026-08-02"])

    def test_normalizes_sorts_and_limits_rows(self):
        payload = [
            {"name": "A", "gift_income": 1, "guard_income": 2, "super_chat_income": 3, "total_income": 6},
            {"name": "B", "total_income": 10},
        ]
        rows = normalize_realtime_revenue(payload, 1)
        self.assertEqual(["B"], [row["name"] for row in rows])
        self.assertEqual(10, rows[0]["total_income"])


if __name__ == "__main__":
    unittest.main()
