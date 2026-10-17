import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from admin_operations import get_operation
from admin_server import BotAdminServer, OperationInputError, invoke_operation
from botpy_ext import ExtendedBotAPI


class FakeAPI:
    async def post_message(self, **kwargs):
        return kwargs

    async def mute_member(self, **kwargs):
        return kwargs


class FakeClient:
    api = FakeAPI()


class AdminServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_invokes_only_declared_operation_fields(self):
        result = await invoke_operation(
            FakeClient(),
            get_operation("post_message"),
            {"channel_id": "123", "content": "hello"},
        )

        self.assertEqual({"channel_id": "123", "content": "hello"}, result)

    async def test_rejects_unknown_operation_field(self):
        with self.assertRaisesRegex(OperationInputError, "未知参数"):
            await invoke_operation(
                FakeClient(),
                get_operation("post_message"),
                {"channel_id": "123", "content": "hello", "unexpected": True},
            )

    async def test_invokes_member_mute_with_declared_fields(self):
        result = await invoke_operation(
            FakeClient(),
            get_operation("mute_member"),
            {"guild_id": "guild-1", "user_id": "user-1", "mute_seconds": "3600"},
        )

        self.assertEqual(
            {"guild_id": "guild-1", "user_id": "user-1", "mute_seconds": "3600"},
            result,
        )


class MenuPanelHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.request = AsyncMock(return_value={"version": 1})
        client = SimpleNamespace(api=ExtendedBotAPI(SimpleNamespace(request=self.request)))
        server = BotAdminServer(client)
        server._token = "test-only-token"
        app = web.Application(middlewares=[server._auth_middleware])
        app.router.add_get("/api/operations", server._operations)
        app.router.add_post("/api/operations/{operation_id}", server._invoke)
        self.browser = TestClient(TestServer(app))
        await self.browser.start_server()
        self.headers = {"Authorization": "Bearer test-only-token"}

    async def asyncTearDown(self):
        await self.browser.close()

    async def test_new_operations_require_authentication(self):
        response = await self.browser.post("/api/operations/delete_panel", json={"panel_id": "p1"})
        self.assertEqual(401, response.status)
        self.request.assert_not_awaited()

    async def test_catalog_and_all_menu_panel_forms_reach_extended_api(self):
        cases = {
            "get_global_menu": {},
            "update_global_menu": {"menu": '{"items": []}'},
            "get_panels": {"scope": "c2c", "limit": "20"},
            "create_panel": {"scope": "group", "target_type": "specific", "panel": '{"items": []}', "group_openids": '["g1"]'},
            "get_panel": {"panel_id": "p1"},
            "update_panel": {"panel_id": "p1", "panel": '{"items": []}'},
            "delete_panel": {"panel_id": "p1"},
            "update_panel_targets": {"panel_id": "p1", "op": "add", "user_openids": '["u1"]'},
        }
        response = await self.browser.get("/api/operations", headers=self.headers)
        catalog = (await response.json())["operations"]
        self.assertTrue(set(cases) <= {item["id"] for item in catalog})
        for name, payload in cases.items():
            with self.subTest(operation=name):
                self.request.reset_mock()
                response = await self.browser.post("/api/operations/" + name, json=payload, headers=self.headers)
                self.assertEqual(200, response.status, await response.text())
                self.request.assert_awaited_once()
                if name == "create_panel":
                    self.assertEqual(["g1"], self.request.await_args.kwargs["json"]["group_openids"])

    async def test_invalid_inputs_return_400_without_http_request(self):
        for payload in ({"scope": "unknown"}, {"scope": "c2c", "limit": "51"}, {"scope": "c2c", "unexpected": "x"}):
            response = await self.browser.post("/api/operations/get_panels", json=payload, headers=self.headers)
            self.assertEqual(400, response.status)
        self.request.assert_not_awaited()

    async def test_empty_delete_response_is_success_but_timeout_is_not(self):
        self.request.return_value = {}
        response = await self.browser.post("/api/operations/delete_panel", json={"panel_id": "p1"}, headers=self.headers)
        self.assertEqual(200, response.status)
        self.assertEqual({}, (await response.json())["result"])
        self.request.return_value = None
        response = await self.browser.post("/api/operations/delete_panel", json={"panel_id": "p1"}, headers=self.headers)
        self.assertEqual(504, response.status)
        self.assertIn("先查询确认", await response.text())


if __name__ == "__main__":
    unittest.main()
