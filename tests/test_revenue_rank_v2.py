import unittest
from datetime import datetime

from utils.revenue_rank_v2 import (
    merge_realtime_revenue,
    normalize_realtime_revenue,
    parse_revenue_period_args,
)


class RevenueRankV2Test(unittest.TestCase):
    def test_defaults_to_current_month_and_top_twenty(self):
        now = datetime(2026, 8, 9, 16, 30, 0)
        options = parse_revenue_period_args([], now=now)
        self.assertEqual(datetime(2026, 8, 1), options.start_time)
        self.assertEqual(now, options.end_time)
        self.assertEqual(("202608",), options.months)
        self.assertEqual(20, options.top_n)
        self.assertEqual("vr", options.tag)

    def test_parses_month_range_and_top_n(self):
        options = parse_revenue_period_args(
            ["/m", "202606-202608", "/n", "5"],
            now=datetime(2026, 8, 9, 16, 30, 0),
        )
        self.assertEqual(("202606", "202607", "202608"), options.months)
        self.assertEqual(datetime(2026, 6, 1), options.periods[0][0])
        self.assertEqual(datetime(2026, 6, 30, 23, 59, 59), options.periods[0][1])
        self.assertEqual(datetime(2026, 8, 1), options.periods[-1][0])
        self.assertEqual(datetime(2026, 8, 9, 16, 30), options.periods[-1][1])
        self.assertEqual(5, options.top_n)

    def test_parses_non_contiguous_months(self):
        options = parse_revenue_period_args(
            ["/m", "202601,202603"], now=datetime(2026, 8, 9)
        )
        self.assertEqual(("202601", "202603"), options.months)
        self.assertEqual(2, len(options.periods))

    def test_parses_tag_filter(self):
        options = parse_revenue_period_args(
            ["/f", "psp", "/m", "202608"], now=datetime(2026, 8, 9)
        )
        self.assertEqual("psp", options.tag)

    def test_normalizes_sorts_and_limits_rows(self):
        payload = [
            {"name": "A", "gift_income": 1, "guard_income": 2, "super_chat_income": 3, "total_income": 6},
            {"name": "B", "total_income": 10},
        ]
        rows = normalize_realtime_revenue(payload, 1)
        self.assertEqual(["B"], [row["name"] for row in rows])
        self.assertEqual(10, rows[0]["total_income"])

    def test_merges_same_streamer_across_months(self):
        rows = merge_realtime_revenue(
            [
                [{"uid": 1, "name": "A", "gift_income": 2, "total_income": 2}],
                [{"uid": 1, "name": "A", "guard_income": 3, "total_income": 3}],
            ],
            top_n=20,
        )
        self.assertEqual(1, len(rows))
        self.assertEqual(5, rows[0]["total_income"])


if __name__ == "__main__":
    unittest.main()
