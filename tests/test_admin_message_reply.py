"""Tests optional reply IDs through the admin HTTP endpoint and SDK."""

import types
import unittest
from unittest import mock

from aiohttp import test_utils
from aiohttp import web

import admin_server
import botpy_ext


class AdminMessageReplyTests(unittest.IsolatedAsyncioTestCase):
    """Exercises the real panel route without making QQ API requests."""

    async def asyncSetUp(self) -> None:
        self.request = mock.AsyncMock(return_value={"id": "sent-id"})
        api = botpy_ext.ExtendedBotAPI(http=types.SimpleNamespace(
            request=self.request))
        self.server = admin_server.BotAdminServer(
            types.SimpleNamespace(api=api))
        self.server._token = "test-only-token"
        app = web.Application(middlewares=[self.server._auth_middleware])
        app.router.add_get("/api/operations", self.server._operations)
        app.router.add_post("/api/operations/{operation_id}",
                            self.server._invoke)
        self.browser = test_utils.TestClient(test_utils.TestServer(app))
        await self.browser.start_server()
        self.headers = {"Authorization": "Bearer test-only-token"}

    async def asyncTearDown(self) -> None:
        await self.browser.close()

    async def test_catalog_exposes_optional_text_reply_id(self) -> None:
        response = await self.browser.get("/api/operations",
                                          headers=self.headers)
        self.assertEqual(200, response.status)
        operations = (await response.json())["operations"]
        operation = next(
            item for item in operations if item["id"] == "post_message")
        field = next(
            item for item in operation["fields"] if item["name"] == "msg_id")
        self.assertEqual("text", field["kind"])
        self.assertFalse(field["required"])
        self.assertTrue(field["placeholder"])
        self.request.assert_not_awaited()

    async def test_reply_id_is_forwarded_unchanged(self) -> None:
        message_id = "088484f5d4ffe996ebdc0110fedce5d80238ab0e48bac78ad706"
        response = await self.browser.post(
            "/api/operations/post_message",
            json={
                "channel_id": "723086974",
                "content": "reply test",
                "msg_id": message_id,
            },
            headers=self.headers,
        )
        self.assertEqual(200, response.status, await response.text())
        self.request.assert_awaited_once()
        call = self.request.await_args
        assert call is not None
        payload = call.kwargs["json"]
        self.assertEqual(message_id, payload["msg_id"])
        self.assertEqual("723086974", payload["channel_id"])
        self.assertEqual("reply test", payload["content"])
        self.assertEqual("sent-id", (await response.json())["result"]["id"])

    async def test_blank_or_omitted_reply_id_keeps_previous_behavior(
            self) -> None:
        for extra in ({}, {"msg_id": ""}):
            with self.subTest(extra=extra):
                self.request.reset_mock()
                response = await self.browser.post(
                    "/api/operations/post_message",
                    json={
                        "channel_id": "123",
                        "content": "test",
                        **extra
                    },
                    headers=self.headers,
                )
                self.assertEqual(200, response.status)
                call = self.request.await_args
                assert call is not None
                self.assertIsNone(call.kwargs["json"]["msg_id"])

    async def test_non_text_reply_id_is_rejected_before_sdk_request(
            self) -> None:
        response = await self.browser.post(
            "/api/operations/post_message",
            json={
                "channel_id": "123",
                "content": "test",
                "msg_id": 123
            },
            headers=self.headers,
        )
        self.assertEqual(400, response.status)
        self.request.assert_not_awaited()
