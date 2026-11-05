"""Offline tests for DeepSeek tool calls, budgets, and fixed endpoints."""

import asyncio
from collections.abc import AsyncIterator
import dataclasses
import json
import types
from typing import Any
import unittest
from unittest import mock

from chat import config
from chat import model_client
from chat import web_tools


def response(data: object, status: int = 200) -> mock.MagicMock:
    """Builds a simulated aiohttp response, including chunked reads."""

    async def chunks(size: int) -> AsyncIterator[bytes]:
        yield json.dumps(data).encode()

    result = mock.MagicMock()
    result.__aenter__ = mock.AsyncMock(return_value=types.SimpleNamespace(
        status=status,
        json=mock.AsyncMock(return_value=data),
        content=types.SimpleNamespace(iter_chunked=chunks),
    ))
    result.__aexit__ = mock.AsyncMock(return_value=False)
    return result


def message(content: str | None = "answer",
            calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Builds a model response with usage on every round."""
    return {
        "choices": [{
            "message": {
                "content": content,
                "tool_calls": calls
            }
        }],
        "usage": {
            "prompt_tokens": 2,
            "completion_tokens": 1
        }
    }


def call(name: str,
         arguments: object,
         identifier: str = "c1") -> dict[str, Any]:
    return {
        "id": identifier,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments)
        }
    }


class ChatWebTests(unittest.IsolatedAsyncioTestCase):
    """Exercises the model and tool interfaces without paid network calls."""

    async def asyncSetUp(self) -> None:
        self.environment = mock.patch.dict("os.environ", {
            "CHAT_API_KEY": "test-only",
            "CHAT_BASE_URL": "https://api.deepseek.com",
            "CHAT_MODEL": "test-model",
        },
                                           clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.session = mock.MagicMock()
        self.session.closed = False
        self.session.close = mock.AsyncMock()
        self.client = model_client.ModelClient(
            dataclasses.replace(config.ChatConfig(), web_enabled=True))
        self.client.session = self.session
        self.addAsyncCleanup(self.client.close)

    async def test_search_fetch_answer_and_usage(self) -> None:
        self.session.post.side_effect = [
            response(message(None, [call("web_search", {"query": "news"})])),
            response({
                "results": [{
                    "title": "News",
                    "url": "https://example.com/news",
                    "summary": "current facts"
                }]
            }),
            response(
                message(None, [
                    call("web_fetch", {"url": "https://example.com/news"}, "c2")
                ])),
            response({"content": "page facts"}),
            response(message("verified answer")),
        ]
        result = await self.client.generate([
            {
                "role": "system",
                "content": "original persona"
            },
            {
                "role": "user",
                "content": "question"
            },
        ])
        self.assertIn("verified answer", result.text)
        self.assertIn("News", result.text)
        self.assertNotIn("example.com", result.text)
        self.assertEqual((6, 3), (result.input_tokens, result.output_tokens))
        requests = self.session.post.call_args_list
        self.assertEqual("https://api.deepseek.com/v1/tools/search",
                         requests[1].args[0])
        self.assertEqual({
            "query": "news",
            "count": 3,
            "need_content": False
        }, requests[1].kwargs["json"])
        final = requests[-1].kwargs["json"]["messages"]
        self.assertEqual("original persona", final[0]["content"])
        self.assertEqual("c2", final[-1]["tool_call_id"])
        self.assertTrue(
            all(not item.kwargs["allow_redirects"] for item in requests))

    async def test_no_search_when_model_answers_directly(self) -> None:
        self.session.post.return_value = response(message())
        result = await self.client.generate([])
        self.assertEqual("answer", result.text)
        self.session.post.assert_called_once()

    async def test_final_answer_removes_model_urls_and_domain_only_sources(
            self) -> None:
        self.session.post.side_effect = [
            response(message(None, [call("web_search", {"query": "time"})])),
            response({
                "results": [{
                    "title": "time.is 当前时间",
                    "site_name": "time.is",
                    "url": "https://time.is/"
                }]
            }),
            response(message("参考 [时钟](https://time.is/) 或 time.is，温度3.14度。")),
        ]
        result = await self.client.generate([])
        self.assertNotIn("time.is", result.text)
        self.assertNotIn("https://", result.text)
        self.assertIn("时钟", result.text)
        self.assertIn("当前时间", result.text)
        self.assertIn("3.14", result.text)

    async def test_disabled_preserves_existing_request_format(self) -> None:
        self.client.config = config.ChatConfig()
        self.session.post.return_value = response(message())
        await self.client.generate([])
        self.assertNotIn("tools", self.session.post.call_args.kwargs["json"])

    async def test_wrong_provider_is_rejected_without_network(self) -> None:
        with mock.patch.dict("os.environ",
                             {"CHAT_BASE_URL": "https://proxy.example"}):
            with self.assertRaises(model_client.ChatError):
                await self.client.generate([])
        self.session.post.assert_not_called()

    async def test_excessive_model_calls_stop_before_tool_execution(
            self) -> None:
        self.session.post.return_value = response(
            message(None, [
                call("web_search", {"query": "x"}, str(index))
                for index in range(5)
            ]))
        with self.assertRaises(model_client.ChatError):
            await self.client.generate([])
        self.session.post.assert_called_once()

    async def test_tool_failure_is_visible_without_leaking_response(
            self) -> None:
        self.session.post.side_effect = [
            response(message(None, [call("web_search", {"query": "news"})])),
            response({"secret": "private"}, 403),
            response(message("not verified")),
        ]
        result = await self.client.generate([])
        self.assertIn("联网查询失败", result.text)
        self.assertNotIn("private", result.text)

    async def test_cancel_propagates(self) -> None:
        self.session.post.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.client.generate([])

    async def test_fetch_requires_search_result_and_blocks_private_urls(
            self) -> None:
        tools = web_tools.WebTools(self.session, "test-only", 2, 2, 1000)
        for url in ("https://127.0.0.1", "http://example.com",
                    "https://example.com/not-searched"):
            self.assertIn(
                "error", await tools.execute("web_fetch",
                                             json.dumps({"url": url})))
        self.session.post.assert_not_called()

    async def test_tool_budget_unknown_tools_and_invalid_arguments(
            self) -> None:
        tools = web_tools.WebTools(self.session, "test-only", 1, 1, 1000)
        for name, args in (("shell", "{}"), ("web_search", "broken"),
                           ("web_search", '{"query":"news"}')):
            self.assertIn("error", await tools.execute(name, args))
        self.session.post.assert_not_called()

    async def test_search_budget_and_context_remain_bounded(self) -> None:
        self.session.post.return_value = response({
            "results": [{
                "url": "https://example.com",
                "title": "title",
                "summary": "a" * 10000
            },]
        })
        tools = web_tools.WebTools(self.session, "test-only", 2, 2, 2000)
        for _ in range(3):
            await tools.execute("web_search", '{"query":"news"}')
        self.assertEqual(2, self.session.post.call_count)
        self.assertGreaterEqual(tools.chars_left, 0)
        self.assertEqual(0, tools.remaining["web_search"])

    async def test_web_mode_does_not_forward_other_provider_backup_key(
            self) -> None:
        with mock.patch.dict("os.environ", {
                "ZHIPU_API_KEY": "another-provider-key",
                "CHAT_BASE_URL": "https://api.deepseek.com",
        },
                             clear=True):
            with self.assertRaises(model_client.ChatError):
                await self.client.generate([])
        self.session.post.assert_not_called()

    def test_public_url_validation(self) -> None:
        for url in ("https://user:pass@example.com", "https://192.168.1.1",
                    "https://169.254.169.254", "https://host.local",
                    "file:///etc/passwd"):
            self.assertIsNone(web_tools.public_url(url))
        self.assertEqual("https://example.com",
                         web_tools.public_url("https://example.com"))
