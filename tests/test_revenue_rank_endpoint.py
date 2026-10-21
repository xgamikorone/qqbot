import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import aiohttp

from commands import api


class RevenueRankEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def fetch(self, month, base_url="", status=200, error=None):
        payload = {"anchors": [], "filter": "vr", "refresh_time": "test"}
        response = SimpleNamespace(status=status, json=AsyncMock(return_value=payload, side_effect=error))
        context = AsyncMock()
        context.__aenter__.return_value = response
        session = Mock()
        session.get.return_value = context
        clock = Mock()
        clock.now.return_value.strftime.return_value = "202610"
        with patch.dict("os.environ", {"REVENUE_RANK_BASE_URL": base_url}), patch.object(api, "datetime", clock), patch.object(api, "get_session", new=AsyncMock(return_value=session)):
            result = await api.get_revenue_rank(month, "vr")
        return result, session, response, payload

    async def test_new_default_routes_preserve_params_and_response(self):
        for month, path in (("202610", "/gift"), ("202609", "/gift/by_month")):
            result, session, _, payload = await self.fetch(month)
            self.assertIs(payload, result)
            self.assertEqual("https://dc.yioio.top" + path, session.get.call_args.args[0])
            self.assertEqual({"month": month, "filter": "vr"}, session.get.call_args.kwargs["params"])
            self.assertFalse(session.get.call_args.kwargs["allow_redirects"])

    async def test_override_normalizes_trailing_slash_and_whitespace(self):
        result, session, _, _ = await self.fetch("202609", " https://rank.example.test/// ")
        self.assertIsNotNone(result)
        self.assertEqual("https://rank.example.test/gift/by_month", session.get.call_args.args[0])

    def test_missing_or_blank_setting_uses_new_default(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual("https://dc.yioio.top", api.get_revenue_rank_base_url())
        with patch.dict("os.environ", {"REVENUE_RANK_BASE_URL": "   "}):
            self.assertEqual("https://dc.yioio.top", api.get_revenue_rank_base_url())

    async def test_invalid_origin_does_not_make_request(self):
        for origin in ("http://dc.yioio.top", "https://user:secret@rank.test", "https://rank.test/gift", "https://rank.test?q=x", "https://rank.test/#fragment"):
            result, session, _, _ = await self.fetch("202610", origin)
            self.assertIsNone(result)
            session.get.assert_not_called()

    async def test_redirect_and_non_200_are_not_parsed_or_followed(self):
        for status in (301, 302, 403, 500):
            result, session, response, _ = await self.fetch("202610", status=status)
            self.assertIsNone(result)
            response.json.assert_not_awaited()
            self.assertFalse(session.get.call_args.kwargs["allow_redirects"])

    async def test_invalid_json_timeout_and_network_errors_return_none(self):
        for error in (ValueError("bad JSON"), asyncio.TimeoutError(), aiohttp.ClientError("network failure")):
            result, _, _, _ = await self.fetch("202610", error=error)
            self.assertIsNone(result)
