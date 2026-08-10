import unittest
from datetime import datetime

from utils.revenue_rank_v2 import (
    format_month_label,
    format_revenue_period_label,
    merge_realtime_revenue,
    normalize_realtime_revenue,
    parse_revenue_period_args,
    resolve_revenue_tag_id,
)


class RevenueRankV2Test(unittest.TestCase):
    def test_formats_months_as_compact_ranges(self):
        self.assertEqual("2026年08月", format_month_label(("202608",)))
        self.assertEqual(
            "2026年06月–08月",
            format_month_label(("202606", "202607", "202608")),
        )
        self.assertEqual(
            "2025年11月–2026年02月",
            format_month_label(("202511", "202512", "202601", "202602")),
        )
        self.assertEqual(
            "2026年01月–03月（共2个月）",
            format_month_label(("202601", "202603")),
        )

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

    def test_parses_all_tag_filter(self):
        options = parse_revenue_period_args(
            ["/f", "all"], now=datetime(2026, 8, 9)
        )
        self.assertEqual("all", options.tag)
        self.assertEqual(0, resolve_revenue_tag_id(options.tag, {"vr": 6}))

    def test_parses_today(self):
        now = datetime(2026, 8, 9, 16, 30)
        options = parse_revenue_period_args(["/d", "今天"], now=now)
        self.assertEqual(datetime(2026, 8, 9), options.start_time)
        self.assertEqual(now, options.end_time)
        self.assertEqual("2026年08月09日", format_revenue_period_label(options))

    def test_parses_yesterday(self):
        options = parse_revenue_period_args(
            ["/d", "昨天"], now=datetime(2026, 8, 9, 16, 30)
        )
        self.assertEqual(datetime(2026, 8, 8), options.start_time)
        self.assertEqual(datetime(2026, 8, 8, 23, 59, 59), options.end_time)

    def test_parses_short_day_range(self):
        options = parse_revenue_period_args(
            ["/d", "8-5到8-9"], now=datetime(2026, 8, 9, 16, 30)
        )
        self.assertEqual(datetime(2026, 8, 5), options.start_time)
        self.assertEqual(datetime(2026, 8, 9, 16, 30), options.end_time)
        self.assertEqual(
            "2026年08月05日–09日", format_revenue_period_label(options)
        )

    def test_rejects_month_and_day_together(self):
        with self.assertRaisesRegex(ValueError, "不能同时"):
            parse_revenue_period_args(
                ["/m", "202608", "/d", "今天"], now=datetime(2026, 8, 9)
            )

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
