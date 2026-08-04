import unittest
from unittest.mock import AsyncMock, patch

from utils.async_retry import retry_empty


class BVRetryTest(unittest.IsolatedAsyncioTestCase):
    async def test_retries_empty_responses_until_success(self):
        success = {"code": 0, "data": {}}
        fetch = AsyncMock(side_effect=[{}, None, success])
        with patch("utils.async_retry.asyncio.sleep", new=AsyncMock()) as sleep:
            result = await retry_empty(fetch, retry_delay=0)

        self.assertEqual(success, result)
        self.assertEqual(3, fetch.await_count)
        self.assertEqual(2, sleep.await_count)

    async def test_does_not_retry_business_error(self):
        error = {"code": -400, "message": "请求错误"}
        fetch = AsyncMock(return_value=error)
        result = await retry_empty(fetch)

        self.assertEqual(error, result)
        self.assertEqual(1, fetch.await_count)

    async def test_returns_none_after_attempts_are_exhausted(self):
        fetch = AsyncMock(return_value={})
        with patch("utils.async_retry.asyncio.sleep", new=AsyncMock()):
            result = await retry_empty(fetch, retry_delay=0)

        self.assertIsNone(result)
        self.assertEqual(3, fetch.await_count)


if __name__ == "__main__":
    unittest.main()
