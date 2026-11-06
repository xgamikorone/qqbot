"""Tests short-lived outgoing diagnostics independently of chat context."""

import asyncio
import sqlite3
import types
import unittest
from unittest import mock

from aiohttp import test_utils
from aiohttp import web
from botpy import errors as bot_errors

from admin import server as admin_server
from chat import config
from chat import model_client
from chat import service
from database import schema
from database.repositories import chat_repository


class ChatDeliveryTests(unittest.IsolatedAsyncioTestCase):
    """Exercises persistence, retention, reset, and admin-only detail access."""

    async def asyncSetUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        schema.initialize_schema(self.conn)
        self.repo = chat_repository.ChatRepository(self.conn)
        self.model = mock.Mock(spec=model_client.ModelClient)
        self.model.generate = mock.AsyncMock(
            return_value=model_client.GenerationResult("private final answer",
                                                       "fake", 10, 2))
        self.model.close = mock.AsyncMock()
        self.service = service.ChatService(config.ChatConfig(), self.repo,
                                           self.model)

    async def asyncTearDown(self) -> None:
        await self.service.close()
        self.conn.close()

    async def send_failure(self, error: Exception | None = None) -> None:
        sender = mock.AsyncMock(side_effect=error, return_value=None)
        with self.assertRaises(model_client.ChatError):
            await self.service.reply("key", "u", "private question", sender)
        sender.assert_awaited_once()

    async def test_failure_stores_final_answer_but_not_history_or_question(
            self) -> None:
        await self.send_failure(RuntimeError("private-exception-secret"))
        self.assertEqual([], self.repo.history("key", 7))
        records = self.repo.list_deliveries()
        self.assertEqual(1, len(records))
        self.assertNotIn("answer", records[0])
        detail = self.repo.delivery_detail(records[0]["id"])
        assert detail is not None
        self.assertEqual("private final answer", detail["answer"])
        self.assertEqual("failed", detail["status"])
        self.assertEqual("RuntimeError", detail["error_type"])
        self.assertNotIn("private-exception-secret", str(detail))
        self.assertNotIn("private question", str(detail))

    async def test_known_business_diagnostic_is_available_to_admin_only(
            self) -> None:
        detail = 'type:business, code:30, msg:["[[少女] [图片]]"]'
        await self.send_failure(bot_errors.ServerError(detail))
        record = self.repo.delivery_detail(self.repo.list_deliveries()[0]["id"])
        assert record is not None
        self.assertEqual(detail, record["error_text"])
        self.assertEqual("", self.repo.list_deliveries()[0]["error_text"])

    async def test_sending_is_persisted_before_the_actual_call(self) -> None:

        async def sender(text: str) -> object:
            record = self.repo.delivery_detail(
                self.repo.list_deliveries()[0]["id"])
            assert record is not None
            self.assertEqual(text, record["answer"])
            self.assertEqual("sending", record["status"])
            return {"id": "sent"}

        await self.service.reply("key", "u", "question", sender)
        self.assertEqual([], self.repo.list_deliveries())
        self.assertEqual([("question", "private final answer")],
                         self.repo.history("key", 7))

    async def test_unconfirmed_and_timeout_are_unknown(self) -> None:
        for error in (None, asyncio.TimeoutError()):
            await self.send_failure(error)
        self.assertEqual({"unknown"},
                         {row["status"] for row in self.repo.list_deliveries()})

    async def test_pending_audit_never_becomes_chat_context(self) -> None:
        sender = mock.AsyncMock(return_value={"code": 304024})
        self.assertEqual(
            "pending", await self.service.reply("key", "u", "question", sender))
        self.assertEqual([], self.repo.history("key", 7))
        self.assertEqual("pending", self.repo.list_deliveries()[0]["status"])

    async def test_history_write_failure_does_not_resend(self) -> None:
        sender = mock.AsyncMock(return_value={"id": "sent"})
        with mock.patch.object(self.repo,
                               "append",
                               side_effect=sqlite3.OperationalError()):
            await self.service.reply("key", "u", "question", sender)
        sender.assert_awaited_once()
        self.assertEqual("sent_unrecorded",
                         self.repo.list_deliveries()[0]["status"])

    async def test_reset_removes_diagnostics_and_ids_are_not_reused(
            self) -> None:
        old = self.repo.begin_delivery("key", self.model.generate.return_value)
        self.repo.reset("key")
        new = self.repo.begin_delivery("other",
                                       self.model.generate.return_value)
        self.assertGreater(new, old)
        self.repo.finish_delivery(old, "failed")
        self.assertIsNone(self.repo.delivery_detail(old))
        record = self.repo.delivery_detail(new)
        assert record is not None
        self.assertEqual("sending", record["status"])

    async def test_reset_during_send_cannot_restore_deleted_diagnostic(
            self) -> None:
        started = asyncio.Event()

        async def sender(text: str) -> object:
            started.set()
            await asyncio.Event().wait()
            return None

        task = asyncio.create_task(
            self.service.reply("key", "u", "question", sender))
        await started.wait()
        self.assertEqual(1, len(self.repo.list_deliveries()))
        await self.service.reset("key")
        with self.assertRaises(model_client.ChatError):
            await task
        self.assertEqual([], self.repo.list_deliveries())
        self.assertEqual([], self.repo.history("key", 7))

    async def test_capacity_is_bounded(self) -> None:
        for _ in range(1002):
            self.repo.begin_delivery("key", self.model.generate.return_value)
        self.assertEqual(
            1000,
            self.conn.execute(
                "SELECT COUNT(*) FROM chat_deliveries").fetchone()[0])

    async def test_expired_records_are_deleted_by_background_cleanup(
            self) -> None:
        record_id = self.repo.begin_delivery("key",
                                             self.model.generate.return_value)
        self.conn.execute("UPDATE chat_deliveries SET expires_at=0")
        self.conn.commit()
        await self.service.start()
        await asyncio.sleep(0)
        self.assertIsNone(self.repo.delivery_detail(record_id))
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM chat_deliveries").fetchone()[0])

    async def test_failed_diagnostic_write_does_not_break_send_or_resend(
            self) -> None:
        sender = mock.AsyncMock(return_value={"id": "sent"})
        with mock.patch.object(self.repo,
                               "begin_delivery",
                               side_effect=sqlite3.OperationalError()):
            await self.service.reply("key", "u", "question", sender)
        sender.assert_awaited_once()
        self.assertEqual(1, len(self.repo.history("key", 7)))

    async def test_generated_answer_is_bounded_and_length_is_recorded(
            self) -> None:
        self.model.generate.return_value = model_client.GenerationResult(
            "x" * 11000, "fake")
        sender = mock.AsyncMock()
        with self.assertRaises(model_client.ChatError):
            await self.service.reply("key", "u", "question", sender)
        sender.assert_not_awaited()
        detail = self.repo.delivery_detail(self.repo.list_deliveries()[0]["id"])
        assert detail is not None
        self.assertEqual(10000, len(detail["answer"]))
        self.assertEqual(11000, detail["answer_chars"])
        self.assertEqual("not_sent", detail["status"])

    async def test_admin_auth_detail_and_no_store(self) -> None:
        await self.send_failure(RuntimeError())
        record_id = self.repo.list_deliveries()[0]["id"]
        server = admin_server.BotAdminServer(
            types.SimpleNamespace(chat_service=self.service))
        server._token = "test-only-token"
        app = web.Application(middlewares=[server._auth_middleware])
        app.router.add_post("/api/operations/{operation_id}", server._invoke)
        async with test_utils.TestClient(test_utils.TestServer(app)) as browser:
            path = "/api/operations/chat_delivery_detail"
            response = await browser.post(path, json={"record_id": record_id})
            self.assertEqual(401, response.status)
            headers = {"Authorization": "Bearer test-only-token"}
            response = await browser.post(path,
                                          json={"record_id": record_id},
                                          headers=headers)
            self.assertEqual(200, response.status)
            self.assertEqual("no-store", response.headers["Cache-Control"])
            self.assertEqual("private final answer",
                             (await response.json())["result"]["answer"])
            response = await browser.post("/api/operations/chat_delivery_list",
                                          json={},
                                          headers=headers)
            self.assertNotIn("private final answer", await response.text())

    async def test_validation_and_schema_initialization_are_safe(self) -> None:
        with self.assertRaises(ValueError):
            self.repo.list_deliveries(101)
        with self.assertRaises(ValueError):
            self.repo.delivery_detail(-1)
        record_id = self.repo.begin_delivery("key",
                                             self.model.generate.return_value)
        schema.initialize_schema(self.conn)
        self.assertIsNotNone(self.repo.delivery_detail(record_id))
