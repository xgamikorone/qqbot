import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from botpy.api import BotAPI

from botpy_ext import ExtendedBotAPI
from botpy_ext.api import APIInputError


class ExtendedBotAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_new_routes_bodies_and_pagination(self):
        cases = [
            ("update_global_menu", {"menu": {"items": []}}, "PUT", "/v2/menu", {"json": {"menu": {"items": []}}}),
            ("get_panels", {"scope": "group", "cursor": "next", "limit": 10}, "GET", "/v2/panels", {"params": {"scope": "group", "cursor": "next", "limit": 10}}),
            ("create_panel", {"scope": "group", "target_type": "specific", "panel": {"items": []}, "group_openids": ["g1"]}, "POST", "/v2/panels", {"json": {"scope": "group", "target_type": "specific", "panel": {"items": []}, "group_openids": ["g1"]}}),
            ("get_panel", {"panel_id": "p_123"}, "GET", "/v2/panels/p_123", {}),
            ("update_panel", {"panel_id": "p_123", "panel": {"items": []}}, "PUT", "/v2/panels/p_123", {"json": {"panel": {"items": []}}}),
            ("delete_panel", {"panel_id": "p_123"}, "DELETE", "/v2/panels/p_123", {}),
            ("update_panel_targets", {"panel_id": "p_123", "op": "del", "user_openids": ["u1"]}, "PUT", "/v2/panels/p_123/target", {"json": {"op": "del", "user_openids": ["u1"]}}),
        ]
        for method, arguments, verb, path, kwargs in cases:
            with self.subTest(method=method):
                response = {"test": "unfiltered"}
                request = AsyncMock(return_value=response)
                api = ExtendedBotAPI(SimpleNamespace(request=request))
                self.assertIs(response, await getattr(api, method)(**arguments))
                route = request.await_args.args[0]
                self.assertEqual(verb, route.method)
                self.assertEqual("https://api.sgroup.qq.com" + path, route.url)
                self.assertEqual(kwargs, request.await_args.kwargs)

    async def test_optional_fields_are_omitted_and_global_scopes_supported(self):
        request = AsyncMock(return_value={})
        api = ExtendedBotAPI(SimpleNamespace(request=request))
        await api.get_panels("c2c")
        self.assertEqual({"params": {"scope": "c2c"}}, request.await_args.kwargs)
        for scope in ("c2c", "group", "channel", "dm"):
            await api.create_panel(scope, "all", {})
            self.assertEqual({"json": {"scope": scope, "target_type": "all", "panel": {}}}, request.await_args.kwargs)

    async def test_bad_inputs_never_make_a_request(self):
        cases = [
            ("get_panels", {"scope": "invalid"}),
            ("get_panels", {"scope": "c2c", "limit": 51}),
            ("get_panels", {"scope": "c2c", "limit": True}),
            ("update_global_menu", {"menu": []}),
            ("update_global_menu", {"menu": {"items": [{}] * 11}}),
            ("update_panel", {"panel_id": "p1", "panel": {"items": [{}] * 21}}),
            ("get_panel", {"panel_id": "../menu"}),
            ("create_panel", {"scope": "dm", "target_type": "specific", "panel": {}}),
            ("create_panel", {"scope": "group", "target_type": "all", "panel": {}, "group_openids": ["g"]}),
            ("create_panel", {"scope": "group", "target_type": "specific", "panel": {}, "user_openids": ["u"]}),
            ("update_panel_targets", {"panel_id": "p1", "op": "remove", "user_openids": ["u"]}),
            ("update_panel_targets", {"panel_id": "p1", "op": "add"}),
            ("update_panel_targets", {"panel_id": "p1", "op": "add", "user_openids": ["u"] * 21}),
            ("update_panel_targets", {"panel_id": "p1", "op": "add", "user_openids": ["u"], "group_openids": ["g"]}),
        ]
        for method, arguments in cases:
            with self.subTest(method=method, arguments=arguments):
                request = AsyncMock()
                api = ExtendedBotAPI(SimpleNamespace(request=request))
                with self.assertRaises(APIInputError):
                    await getattr(api, method)(**arguments)
                request.assert_not_awaited()

    async def test_global_menu_uses_existing_http_client_and_preserves_response(self):
        payload = {"version": 1, "menu": {"items": [
            {"type": "send_message", "name": "帮助", "send_message": "/help"},
        ]}}
        request = AsyncMock(return_value=payload)
        api = ExtendedBotAPI(SimpleNamespace(request=request))

        self.assertIs(payload, await api.get_global_menu())
        request.assert_awaited_once()
        route, = request.await_args.args
        self.assertEqual("GET", route.method)
        self.assertEqual("/v2/menu", route.path)
        self.assertEqual({}, request.await_args.kwargs)

    async def test_unconfigured_menu_and_sdk_timeout_are_preserved(self):
        request = AsyncMock(side_effect=[{"version": 0, "menu": None}, None])
        api = ExtendedBotAPI(SimpleNamespace(request=request))
        self.assertEqual({"version": 0, "menu": None}, await api.get_global_menu())
        self.assertIsNone(await api.get_global_menu())

    async def test_sdk_error_is_not_hidden(self):
        request = AsyncMock(side_effect=RuntimeError("SDK request rejected"))
        api = ExtendedBotAPI(SimpleNamespace(request=request))
        with self.assertRaisesRegex(RuntimeError, "SDK request rejected"):
            await api.get_global_menu()

    async def test_existing_sdk_methods_still_use_same_transport(self):
        payload = {"id": "bot-id"}
        request = AsyncMock(return_value=payload)
        api = ExtendedBotAPI(SimpleNamespace(request=request))
        self.assertIsInstance(api, BotAPI)
        self.assertIs(payload, await api.me())
        self.assertEqual("/users/@me", request.await_args.args[0].path)


if __name__ == "__main__":
    unittest.main()
