"""Admin experiment controls, tested against a fake authenticated QQ SDK."""

import datetime
import types
import unittest
from unittest import mock

from aiohttp import test_utils
from aiohttp import web

from admin import server as admin_server
import qq_message_id
import reply_sources


class AdminReplySourceTests(unittest.IsolatedAsyncioTestCase):
    """Verifies explicit dispatch, authentication, and safe manual reads."""

    async def asyncSetUp(self) -> None:
        self.api = mock.Mock()
        self.api.post_message = mock.AsyncMock()
        self.api.get_channels = mock.AsyncMock(return_value=[
            {
                "id": "2",
                "guild_id": "1"
            },
            {
                "id": "3",
                "guild_id": "1"
            },
        ])
        self.seed = qq_message_id.encode_message_id(1, 2, 10, 1)
        self.api.get_message = mock.AsyncMock(
            return_value={
                "id":
                    self.seed,
                "guild_id":
                    "1",
                "channel_id":
                    "2",
                "timestamp":
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "author": {
                    "bot": False
                },
                "content":
                    "private message body",
            })
        self.pool = reply_sources.ReplySources(
            self.api,
            reply_sources.Settings(
                enabled=True,
                max_probes_per_batch=1,
                guilds=(reply_sources.GuildSettings("1", ("2",), ("3",)),),
            ),
            ":memory:",
            sleep=mock.AsyncMock(),
        )
        client = types.SimpleNamespace(
            api=self.api,
            live_forwarding=types.SimpleNamespace(reply_sources=self.pool))
        server = admin_server.BotAdminServer(client)
        server._token = "test-only-token"
        app = web.Application(middlewares=[server._auth_middleware])
        app.router.add_get("/api/operations", server._operations)
        app.router.add_post("/api/operations/{operation_id}", server._invoke)
        self.browser = test_utils.TestClient(test_utils.TestServer(app))
        await self.browser.start_server()
        self.headers = {"Authorization": "Bearer test-only-token"}

    async def asyncTearDown(self) -> None:
        await self.browser.close()
        await self.pool.close()

    async def test_register_probe_and_status_never_send_or_return_body(
            self) -> None:
        response = await self.browser.post(
            "/api/operations/reply_source_register",
            json={
                "guild_id": "1",
                "channel_id": "2",
                "message_id": self.seed
            },
            headers=self.headers,
        )
        self.assertEqual(200, response.status, await response.text())
        self.assertNotIn("private message body", await response.text())
        self.api.get_message.return_value[
            "id"] = qq_message_id.encode_message_id(1, 2, 11, 2)
        response = await self.browser.post(
            "/api/operations/reply_source_probe",
            json={"guild_id": "1"},
            headers=self.headers,
        )
        self.assertEqual(200, response.status)
        self.assertEqual(1, (await response.json())["result"]["queries"])
        self.api.get_message.reset_mock()
        self.api.get_channels.reset_mock()
        response = await self.browser.post(
            "/api/operations/reply_source_status",
            json={"guild_id": "1"},
            headers=self.headers,
        )
        self.assertEqual(200, response.status)
        self.assertNotIn("private message body", await response.text())
        self.api.get_message.assert_not_awaited()
        self.api.get_channels.assert_not_awaited()
        self.api.post_message.assert_not_awaited()

    async def test_auth_and_allowlists_are_enforced_before_qq_query(
            self) -> None:
        response = await self.browser.post("/api/operations/reply_source_probe",
                                           json={"guild_id": "1"})
        self.assertEqual(401, response.status)
        for payload in ({"guild_id": "9"}, {"guild_id": "1", "limit": 999}):
            response = await self.browser.post(
                "/api/operations/reply_source_probe",
                json=payload,
                headers=self.headers,
            )
            self.assertEqual(400, response.status)
        self.api.get_message.assert_not_awaited()
        self.api.get_channels.assert_not_awaited()

    async def test_catalog_exposes_three_experiment_forms(self) -> None:
        response = await self.browser.get("/api/operations",
                                          headers=self.headers)
        operations = (await response.json())["operations"]
        experiment = {
            item["id"] for item in operations if item["category"] == "实验消息来源"
        }
        self.assertEqual(
            {
                "reply_source_register", "reply_source_probe",
                "reply_source_status"
            }, experiment)

    async def test_disabled_experiment_returns_actionable_error(self) -> None:
        self.pool.settings = reply_sources.Settings()
        response = await self.browser.post(
            "/api/operations/reply_source_probe",
            json={"guild_id": "1"},
            headers=self.headers,
        )
        self.assertEqual(400, response.status)
        self.assertIn("尚未启用", await response.text())
        self.api.get_channels.assert_not_awaited()
