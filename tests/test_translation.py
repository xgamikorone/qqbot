import asyncio
from hashlib import md5
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from commands.base import _command_registry, _running_commands, last_used
from commands.help_catalog import HelpCatalog
from commands.translate import TranslateCommand, parse_arguments
from utils.baidu_translate import (
    TRANSLATE_URL, TranslationError, TranslationResult, build_payload,
    parse_response, translate,
)


class TranslationParsingTests(unittest.TestCase):
    def test_sign_uses_original_utf8_text_before_form_encoding(self):
        with patch("utils.baidu_translate.secrets.token_hex", return_value="salt"):
            payload = build_payload("appid", "test-key", "你好 & +\nworld", "auto", "en")
        expected = md5("appid你好 & +\nworldsalttest-key".encode("utf-8")).hexdigest()
        self.assertEqual(expected, payload["sign"])
        self.assertEqual("你好 & +\nworld", payload["q"])
        self.assertNotIn("test-key", payload.values())

    def test_defaults_flags_aliases_and_option_terminator(self):
        cases = [
            (["Hello", "world"], ("auto", "zh", "Hello world")),
            (["--to", "英文", "你好"], ("auto", "en", "你好")),
            (["--from", "JP", "--to", "zh", "こんにちは"], ("jp", "zh", "こんにちは")),
            (["--", "--help"], ("auto", "zh", "--help")),
        ]
        for args, expected in cases:
            self.assertEqual(expected, parse_arguments(args))

    def test_invalid_and_oversized_arguments(self):
        for args in ([], ["--to"], ["--to", "auto", "hi"], ["--to", "../en", "hi"], ["--bad", "hi"], ["--to", "en", "--to", "zh", "hi"], ["中" * 1001]):
            with self.subTest(args=args[:3]), self.assertRaises(TranslationError):
                parse_arguments(args)

    def test_multiple_paragraphs_unicode_and_html_are_preserved(self):
        result = parse_response({"from": "en", "to": "zh", "trans_result": [{"dst": "你好 & 世界"}, {"dst": "第二段"}]})
        self.assertEqual(TranslationResult("en", "zh", "你好 & 世界\n第二段"), result)

    def test_business_errors_are_safe_and_use_friendly_messages(self):
        for code, expected in (("54003", "频繁"), ("54004", "余额"), ("54001", "鉴权"), ("58001", "语言"), ("unknown", "拒绝")):
            with self.subTest(code=code), self.assertRaises(TranslationError) as caught:
                parse_response({"error_code": code, "error_msg": "secret and private text"})
            self.assertIn(expected, str(caught.exception))
            self.assertNotIn("secret", str(caught.exception))

    def test_malformed_and_empty_responses_are_rejected(self):
        for value in (None, [], {}, {"trans_result": []}, {"trans_result": [{"dst": 2}]}, {"trans_result": [{"dst": " "}]}):
            with self.subTest(value=value), self.assertRaises(TranslationError):
                parse_response(value)


class TranslationHTTPTests(unittest.IsolatedAsyncioTestCase):
    def mock_session(self, status=200, result=None):
        response = SimpleNamespace(status=status, json=AsyncMock(return_value=result))
        request_context = MagicMock()
        request_context.__aenter__ = AsyncMock(return_value=response)
        session = SimpleNamespace(post=MagicMock(return_value=request_context))
        session_context = MagicMock()
        session_context.__aenter__ = AsyncMock(return_value=session)
        return session_context, session, response

    async def test_https_form_request_uses_environment_credentials(self):
        context, session, response = self.mock_session(result={"from": "en", "to": "zh", "trans_result": [{"dst": "你好"}]})
        with patch.dict("os.environ", {"BAIDU_TRANSLATE_APP_ID": "test-app", "BAIDU_TRANSLATE_APP_KEY": "test-key"}, clear=True), patch("utils.baidu_translate.aiohttp.ClientSession", return_value=context) as factory:
            result = await translate("Hello")
        self.assertEqual("你好", result.text)
        session.post.assert_called_once()
        args, kwargs = session.post.call_args
        self.assertEqual((TRANSLATE_URL,), args)
        self.assertTrue(TRANSLATE_URL.startswith("https://"))
        self.assertNotIn("params", kwargs)
        self.assertEqual("Hello", kwargs["data"]["q"])
        self.assertEqual("test-app", kwargs["data"]["appid"])
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(20, factory.call_args.kwargs["timeout"].total)

    async def test_missing_config_and_invalid_text_do_not_call_network(self):
        with patch.dict("os.environ", {}, clear=True), patch("utils.baidu_translate.aiohttp.ClientSession") as factory:
            for text in ("hi", "", "中" * 1001):
                with self.assertRaises(TranslationError):
                    await translate(text)
            factory.assert_not_called()

    async def test_http_timeout_network_and_json_failures_are_safe_and_not_retried(self):
        for failure in (asyncio.TimeoutError(), aiohttp.ClientError("private secret"), ValueError("private secret")):
            with self.subTest(failure=type(failure).__name__):
                context, session, response = self.mock_session()
                response.json.side_effect = failure
                with patch.dict("os.environ", {"BAIDU_TRANSLATE_APP_ID": "app", "BAIDU_TRANSLATE_APP_KEY": "key"}, clear=True), patch("utils.baidu_translate.aiohttp.ClientSession", return_value=context):
                    with self.assertRaises(TranslationError) as caught:
                        await translate("hi")
                session.post.assert_called_once()
                self.assertNotIn("secret", str(caught.exception))

    async def test_non_200_response_is_not_parsed(self):
        context, session, response = self.mock_session(status=503)
        with patch.dict("os.environ", {"BAIDU_TRANSLATE_APP_ID": "app", "BAIDU_TRANSLATE_APP_KEY": "key"}, clear=True), patch("utils.baidu_translate.aiohttp.ClientSession", return_value=context):
            with self.assertRaises(TranslationError):
                await translate("hi")
        response.json.assert_not_awaited()


class TranslateCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        last_used.pop("translate", None)
        _running_commands.discard("translate")
        self.command = TranslateCommand(SimpleNamespace())
        self.command.send_reply = AsyncMock()
        self.message = SimpleNamespace()

    def tearDown(self):
        last_used.pop("translate", None)
        _running_commands.discard("translate")

    async def test_success_returns_true_and_starts_cooldown(self):
        with patch("commands.translate.translate", new=AsyncMock(return_value=TranslationResult("en", "zh", "你好"))) as request:
            self.assertIs(True, await self.command.execute(self.message, ["Hello"]))
            self.assertIs(False, await self.command.execute(self.message, ["Hello"]))
        request.assert_awaited_once_with("Hello", source="auto", target="zh")
        self.assertIn("冷却", self.command.send_reply.await_args.args[1])

    async def test_invalid_arguments_and_service_failure_do_not_start_cooldown(self):
        with patch("commands.translate.translate", new=AsyncMock(side_effect=TranslationError("请求超时"))) as request:
            self.assertIs(False, await self.command.execute(self.message, []))
            request.assert_not_awaited()
            self.assertIs(False, await self.command.execute(self.message, ["hi"]))
        self.assertNotIn("translate", last_used)

    async def test_long_translation_is_marked_as_truncated(self):
        with patch("commands.translate.translate", new=AsyncMock(return_value=TranslationResult("en", "zh", "中" * 4000))):
            await self.command.execute(self.message, ["hi"])
        self.assertIn("已截断", self.command.send_reply.await_args.args[1])

    def test_registered_aliases_and_help_are_available(self):
        self.assertIs(TranslateCommand, _command_registry["翻译"])
        self.assertIs(TranslateCommand, _command_registry["translate"])
        self.assertIn("--to", HelpCatalog(_command_registry).render("翻译"))
