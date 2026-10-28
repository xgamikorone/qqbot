import asyncio
import sqlite3
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from chat.config import ChatConfig, load_config
from chat.model_client import ChatError, GenerationResult, ModelClient
from chat.service import ChatService
from commands.chat import ChatCommand
from database.schema import initialize_schema
from database.repositories.chat_repository import ChatRepository, session_key


class ChatTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        initialize_schema(self.conn)
        self.repo = ChatRepository(self.conn)
        self.model = SimpleNamespace(generate=AsyncMock(return_value=GenerationResult("回答", "fake", 10, 2)), close=AsyncMock())
        self.config = replace(ChatConfig(), enabled=True, allowed_channel_ids=("123",))
        self.service = ChatService(self.config, self.repo, self.model)
        self.sender = AsyncMock(return_value={"id": "delivered"})

    async def asyncTearDown(self):
        await self.service.close()
        self.conn.close()

    async def test_success_and_channel_isolation(self):
        key = session_key("g", "123", "u")
        await self.service.reply(key, "u", "问题", self.sender)
        self.assertEqual([("问题", "回答")], self.repo.history(key, 7))
        other = session_key("g", "456", "u")
        await self.service.reply(other, "u", "另一个问题", self.sender)
        self.assertEqual(2, len(self.model.generate.await_args.args[0]))

    async def test_failures_and_audit_are_not_context(self):
        for reply in (None, {"code": 304023}):
            sender = AsyncMock(return_value=reply)
            try:
                await self.service.reply("key", "u", "问题", sender)
            except ChatError:
                pass
            self.assertEqual([], self.repo.history("key", 7))
        self.model.generate.side_effect = ChatError("超时")
        with self.assertRaises(ChatError):
            await self.service.reply("key", "u", "问题", self.sender)
        self.assertEqual([], self.repo.history("key", 7))

    async def test_send_failure_consumes_request_but_not_context(self):
        with self.assertRaises(ChatError):
            await self.service.reply("key", "u", "问题", AsyncMock(side_effect=RuntimeError("private")))
        self.assertEqual([], self.repo.history("key", 7))
        self.assertEqual(1, self.conn.execute("SELECT COUNT(*) FROM chat_requests").fetchone()[0])

    async def test_same_session_busy_reset_and_cancellation(self):
        started = asyncio.Event()
        async def generate(messages):
            started.set()
            await asyncio.Event().wait()
        self.model.generate.side_effect = generate
        running = asyncio.create_task(self.service.reply("key", "u", "问题", self.sender))
        await started.wait()
        with self.assertRaises(ChatError):
            await self.service.reply("key", "u", "第二个问题", self.sender)
        await self.service.reset("key")
        with self.assertRaises(ChatError):
            await running
        self.sender.assert_not_awaited()
        self.assertEqual([], self.repo.history("key", 7))
        self.assertEqual({}, self.service.tasks)

    async def test_reset_protects_against_provider_ignoring_cancel(self):
        started = asyncio.Event()
        async def generate(messages):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return GenerationResult("旧回答", "fake")
        self.model.generate.side_effect = generate
        running = asyncio.create_task(self.service.reply("key", "u", "问题", self.sender))
        await started.wait()
        await self.service.reset("key")
        with self.assertRaises(ChatError):
            await running
        self.sender.assert_not_awaited()

    async def test_quota_survives_reset_and_long_input_does_not_call_model(self):
        self.service.config = replace(self.config, daily_requests_per_user=1)
        await self.service.reply("key", "u", "问题", self.sender)
        await self.service.reset("key")
        with self.assertRaises(ChatError):
            await self.service.reply("key", "u", "再问", self.sender)
        with self.assertRaises(ChatError):
            await self.service.reply("other", "other", "x" * 2001, self.sender)
        self.assertEqual(1, self.model.generate.await_count)

    async def test_context_trim_keeps_whole_turns(self):
        self.repo.append("key", "old" * 10, GenerationResult("answer" * 10, "fake"), "sent")
        self.service.config = replace(self.config, max_context_chars=len(self.config.prompt) + 10)
        await self.service.reply("key", "u", "new", self.sender)
        self.assertEqual(["system", "user"], [m["role"] for m in self.model.generate.await_args.args[0]])

    async def test_expired_history_is_removed(self):
        self.repo.append("key", "old", GenerationResult("answer", "fake"), "sent")
        self.conn.execute("UPDATE chat_turns SET created_at=0")
        self.conn.commit()
        self.assertEqual([], self.repo.history("key", 7))

    async def test_total_timeout_includes_queue_and_releases_task(self):
        self.service.config = replace(self.config, request_timeout_seconds=0.01)
        await self.service.slots.acquire()
        await self.service.slots.acquire()
        await self.service.slots.acquire()
        with self.assertRaises(ChatError):
            await self.service.reply("key", "u", "问题", self.sender)
        self.model.generate.assert_not_awaited()
        self.assertEqual({}, self.service.tasks)

    async def test_persistence_failure_does_not_resend(self):
        with patch.object(self.repo, "append", side_effect=sqlite3.OperationalError("disk full")):
            self.assertEqual("sent", await self.service.reply("key", "u", "问题", self.sender))
        self.sender.assert_awaited_once()

    async def test_global_concurrency_and_admission_bound(self):
        self.service.config = replace(self.config, max_pending_requests=2)
        started = asyncio.Event()
        release = asyncio.Event()
        active = 0
        peak = 0
        async def generate(messages):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            started.set()
            await release.wait()
            active -= 1
            return GenerationResult("ok", "fake")
        self.service.slots = asyncio.Semaphore(1)
        self.model.generate.side_effect = generate
        first = asyncio.create_task(self.service.reply("a", "a", "hi", self.sender))
        await started.wait()
        second = asyncio.create_task(self.service.reply("b", "b", "hi", self.sender))
        await asyncio.sleep(0)
        with self.assertRaises(ChatError):
            await self.service.reply("c", "c", "hi", self.sender)
        release.set()
        await asyncio.gather(first, second)
        self.assertEqual(1, peak)

    async def test_disabled_and_channel_gates_and_private_records(self):
        cmd = ChatCommand(SimpleNamespace(chat_service=None))
        cmd.send_reply = AsyncMock()
        message = SimpleNamespace(channel_id="456", guild_id="g", author=SimpleNamespace(id="u"))
        self.assertIs(False, await cmd.execute(message, ["private"]))
        cmd.client.chat_service = self.service
        self.assertIs(False, await cmd.execute(message, ["private"]))
        await cmd.after_execute(message, ["private"])
        self.model.generate.assert_not_awaited()

    async def test_missing_key_does_not_create_http_session(self):
        with patch.dict("os.environ", {}, clear=True), patch("chat.model_client.aiohttp.ClientSession") as factory:
            with self.assertRaises(ChatError):
                await ModelClient(self.config).generate([])
            factory.assert_not_called()

    async def test_model_protocol_and_safe_errors_without_network(self):
        response = SimpleNamespace(status=200, json=AsyncMock(return_value={"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 2, "completion_tokens": 1}}))
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        session = SimpleNamespace(closed=False, post=MagicMock(return_value=context), close=AsyncMock())
        client = ModelClient(self.config)
        client.session = session
        with patch.dict("os.environ", {"CHAT_API_KEY": "fake-test-key"}, clear=True):
            result = await client.generate([{"role": "user", "content": "hi"}])
            self.assertEqual("ok", result.text)
            self.assertFalse(session.post.call_args.kwargs["json"]["stream"])
            self.assertFalse(session.post.call_args.kwargs["allow_redirects"])
            for status in (401, 403, 429, 500):
                response.status = status
                with self.assertRaises(ChatError):
                    await client.generate([])
        await client.close()


class ChatConfigTests(TestCase):
    def test_prompt_restores_group_background_and_preserves_ai_identity(self):
        config = load_config()
        for name in ("四禧丸子", "禧运楼", "恬豆", "梨安", "沐霂", "又一"):
            self.assertIn(name, config.prompt)
        self.assertIn("如实说明自己是 AI 助手", config.prompt)
        self.assertNotIn("隐藏自己的 DeepSeek 身份", config.prompt)
        self.assertLessEqual(len(config.prompt) + config.max_input_chars, config.max_context_chars)

    def test_history_survives_connection_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "test.db")
            conn = sqlite3.connect(path)
            initialize_schema(conn)
            repo = ChatRepository(conn)
            repo.append("key", "question", GenerationResult("answer", "fake"), "sent")
            conn.close()
            conn = sqlite3.connect(path)
            self.assertEqual([("question", "answer")], ChatRepository(conn).history("key", 7))
            conn.close()

    def test_default_disabled_and_invalid_config(self):
        self.assertFalse(load_config().enabled)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chat.yaml"
            for data in ("enabled: yes\nallowed_channel_ids: [123]", "max_input_chars: -1", "unexpected: true", "enabled: wrong"):
                path.write_text(data, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config(path)
