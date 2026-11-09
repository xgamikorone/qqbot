"""Offline final-answer diagnostics and summary thinking-control tests."""

import unittest
from unittest import mock

from chat import config
from chat import model_client


class EmptyAnswerTests(unittest.IsolatedAsyncioTestCase):
    """Uses synthetic provider responses without paid requests or credentials."""

    def setUp(self) -> None:
        self.environment = mock.patch.dict(
            "os.environ",
            {
                "CHAT_API_KEY": "offline-secret",
                "CHAT_BASE_URL": "https://api.deepseek.com",
                "CHAT_MODEL": "offline-model",
            },
            clear=True,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.session = mock.MagicMock()
        self.session.closed = False
        self.response = mock.MagicMock(status=200)
        self.session.post.return_value.__aenter__ = mock.AsyncMock(
            return_value=self.response
        )
        self.client = model_client.ModelClient(
            config.ChatConfig(), disable_thinking=True
        )
        self.client.session = self.session

    def set_response(
        self, content: object, reason: object = "stop", **fields: object
    ) -> None:
        """Configures a single synthetic chat-completions response."""
        self.response.json = mock.AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {"content": content, **fields},
                        "finish_reason": reason,
                    }
                ],
                "usage": {"completion_tokens": 800},
            }
        )

    async def test_summary_disables_thinking_on_supported_official_endpoint(
        self,
    ) -> None:
        self.set_response("最终结论")
        result = await self.client.generate([])
        self.assertEqual("最终结论", result.text)
        payload = self.session.post.call_args.kwargs["json"]
        self.assertEqual({"type": "disabled"}, payload["thinking"])
        self.assertEqual(800, payload["max_tokens"])

    async def test_regular_chat_keeps_existing_thinking_behavior(self) -> None:
        self.client.disable_thinking = False
        self.set_response("最终结论")
        await self.client.generate([])
        self.assertNotIn("thinking", self.session.post.call_args.kwargs["json"])

    def test_unknown_provider_and_forced_thinking_model_are_untouched(
        self,
    ) -> None:
        for base, model, expected in (
            ("https://api.deepseek.com/v1", "deepseek-chat", True),
            ("https://open.bigmodel.cn/api/paas/v4", "glm-4.5-flash", True),
            ("https://api.z.ai/api/paas/v4", "glm-4.7", True),
            ("https://api.z.ai/api/paas/v4", "glm-5.3", False),
            ("https://third-party.example/v1", "deepseek-chat", False),
            ("https://api.deepseek.com.evil.example", "fake", False),
        ):
            with self.subTest(base=base, model=model):
                self.assertEqual(
                    expected, model_client._supports_direct_answer(base, model)
                )

    async def test_reasoning_exhaustion_is_diagnosed_without_leaking_text(
        self,
    ) -> None:
        self.set_response(None, "length", reasoning_content="private reasoning")
        with self.assertLogs(model_client._LOG, level="WARNING") as logs:
            with self.assertRaises(model_client.ChatError) as error:
                await self.client.generate([])
        self.assertIn("输出长度上限", str(error.exception))
        output = "\n".join(logs.output)
        self.assertIn("finish_reason=length", output)
        self.assertIn("output_tokens=800", output)
        for secret in ("private reasoning", "offline-secret", "offline-model"):
            self.assertNotIn(secret, output)
            self.assertNotIn(secret, str(error.exception))
        self.assertEqual(1, self.session.post.call_count)

    async def test_reasoning_only_is_never_used_as_the_answer(self) -> None:
        self.set_response("", reasoning_content="private reasoning")
        with self.assertLogs(model_client._LOG, level="WARNING"):
            with self.assertRaisesRegex(
                model_client.ChatError, "仅返回思考内容"
            ):
                await self.client.generate([])

    async def test_content_filter_has_distinct_safe_error(self) -> None:
        self.set_response(None, "content_filter", refusal="private refusal")
        with self.assertLogs(model_client._LOG, level="WARNING") as logs:
            with self.assertRaisesRegex(model_client.ChatError, "内容策略"):
                await self.client.generate([])
        self.assertNotIn("private refusal", "\n".join(logs.output))

    async def test_empty_or_unsupported_content_logs_only_safe_metadata(
        self,
    ) -> None:
        for content in (None, "  ", {"private": "body"}, []):
            self.set_response(content, "private-reason")
            with self.assertLogs(model_client._LOG, level="WARNING") as logs:
                with self.assertRaisesRegex(
                    model_client.ChatError, "未返回有效回答"
                ):
                    await self.client.generate([])
            output = "\n".join(logs.output)
            self.assertIn("finish_reason=unknown", output)
            self.assertNotIn("private", output)

    async def test_valid_answer_does_not_include_reasoning(self) -> None:
        self.set_response("正式回答", reasoning_content="private reasoning")
        result = await self.client.generate([])
        self.assertEqual("正式回答", result.text)
