import shutil
import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from utils.revenue_rank_cache import (
    RevenueRankCache,
    fetch_revenue_rank_cached,
)


class RevenueRankCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = Path("tests") / f".revenue_cache_{uuid4().hex}"
        self.temp_dir.mkdir()
        self.cache = RevenueRankCache(self.temp_dir)
        self.payload = {"anchors": [{"uid": 1, "total_revenue": 10}]}

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_round_trip_preserves_payload_and_metadata(self):
        cached_at = datetime(2026, 8, 25, 12, 30)
        self.cache.save("202607", "vr", self.payload, cached_at=cached_at)

        cached = self.cache.load("202607", "vr")

        self.assertIsNotNone(cached)
        self.assertEqual(self.payload, cached.data)
        self.assertEqual(cached_at, cached.cached_at)

    def test_invalid_cache_is_treated_as_miss(self):
        path = self.cache.path_for("202607", "vr")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json", encoding="utf-8")

        self.assertIsNone(self.cache.load("202607", "vr"))

    async def test_historical_success_updates_cache(self):
        async def fetch_remote(month, category):
            return self.payload

        result = await fetch_revenue_rank_cached(
            "202607",
            "vr",
            fetch_remote=fetch_remote,
            cache=self.cache,
            now=datetime(2026, 8, 25),
            retry_delay=0,
        )

        self.assertEqual("remote", result.source)
        self.assertEqual(self.payload, self.cache.load("202607", "vr").data)

    async def test_historical_failure_falls_back_to_cache(self):
        self.cache.save(
            "202607", "vr", self.payload, cached_at=datetime(2026, 8, 1)
        )

        async def fetch_remote(month, category):
            return None

        result = await fetch_revenue_rank_cached(
            "202607",
            "vr",
            fetch_remote=fetch_remote,
            cache=self.cache,
            now=datetime(2026, 8, 25),
            retry_attempts=2,
            retry_delay=0,
        )

        self.assertEqual("cache", result.source)
        self.assertEqual(self.payload, result.data)
        self.assertEqual(datetime(2026, 8, 1), result.cached_at)

    async def test_current_month_never_falls_back_to_cache(self):
        self.cache.save("202608", "vr", self.payload)

        async def fetch_remote(month, category):
            return None

        result = await fetch_revenue_rank_cached(
            "202608",
            "vr",
            fetch_remote=fetch_remote,
            cache=self.cache,
            now=datetime(2026, 8, 25),
            retry_delay=0,
        )

        self.assertEqual("unavailable", result.source)
        self.assertIsNone(result.data)


if __name__ == "__main__":
    unittest.main()
