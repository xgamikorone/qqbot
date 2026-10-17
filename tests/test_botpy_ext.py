import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from botpy.api import BotAPI

from botpy_ext import ExtendedBotAPI


class ExtendedBotAPITests(unittest.IsolatedAsyncioTestCase):
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
