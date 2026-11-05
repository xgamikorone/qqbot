"""Offline tests for scheduled delivery and out-of-order QQ audit events."""

import asyncio
import sqlite3
import types
import unittest
from unittest import mock

from botpy import message as botpy_message

import message_audits
import task_scheduler
from database import schema
from database.repositories import message_audit_repository


class MessageAuditTests(unittest.IsolatedAsyncioTestCase):
    """Exercises the same tracker interface used by scheduled jobs."""

    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        schema.initialize_schema(self.connection)
        self.repository = message_audit_repository.MessageAuditRepository(
            self.connection)
        self.tracker = message_audits.MessageAuditTracker(self.repository)
        self.sender = mock.Mock()
        self.sender.post_message = mock.AsyncMock()

    def tearDown(self) -> None:
        self.connection.close()

    def delivery(self) -> dict[str, object]:
        """Reads the public effective-state view, not just HTTP state."""
        row = self.connection.execute(
            "SELECT * FROM scheduled_message_delivery").fetchone()
        assert row is not None
        return dict(row)

    @staticmethod
    def event(channel_id: str = "123") -> types.SimpleNamespace:
        return types.SimpleNamespace(audit_id="audit-1",
                                     channel_id=channel_id,
                                     guild_id="guild-1",
                                     message_id="approved")

    async def submit(self, code: int = 304023) -> None:
        self.sender.post_message.return_value = {
            "code": code,
            "data": {
                "message_audit": {
                    "audit_id": "audit-1"
                }
            },
        }
        await self.tracker.send(self.sender, "daily_maintenance_report", "123",
                                "private-content")

    async def test_both_audit_codes_record_pending_without_false_success(
            self) -> None:
        for code in (304023, 304024):
            with self.subTest(code=code):
                self.connection.execute("DELETE FROM scheduled_message_sends")
                with self.assertLogs("botpy.message_audit", "INFO") as logs:
                    await self.submit(code)
                row = self.delivery()
                self.assertEqual("pending_audit", row["status"])
                self.assertEqual("audit-1", row["audit_id"])
                self.assertEqual("daily_maintenance_report", row["task_id"])
                self.assertEqual(code, row["code"])
                self.assertNotIn("private-content", "\n".join(logs.output))
                self.assertIn("audit_id='audit-1'", "\n".join(logs.output))

    async def test_final_pass_and_rejection_are_idempotent(self) -> None:
        await self.submit()
        event = self.event()
        with self.assertLogs("botpy.message_audit", "INFO") as logs:
            self.tracker.record_event(event, passed=True)
            self.tracker.record_event(event, passed=True)
        self.assertEqual("audit_passed", self.delivery()["status"])
        self.assertEqual("approved", self.delivery()["message_id"])
        self.assertIn("audit_passed", "\n".join(logs.output))
        self.assertEqual(
            1,
            self.connection.execute(
                "SELECT count(*) FROM message_audit_events").fetchone()[0])

    async def test_event_before_http_response_and_reopening_tracker(
            self) -> None:
        self.tracker.record_event(self.event(), passed=False)
        self.tracker = message_audits.MessageAuditTracker(self.repository)
        await self.submit()
        self.assertEqual("audit_rejected", self.delivery()["status"])

    async def test_real_sdk_event_is_persisted(self) -> None:
        await self.submit()
        # botpy's constructors are untyped library boundaries.
        event = botpy_message.MessageAudit(
            mock.Mock(), "event-1", {
                "audit_id": "audit-1",
                "channel_id": "123",
                "guild_id": "guild-1",
                "message_id": "approved",
            })
        self.tracker.record_event(event, passed=True)
        self.assertEqual("audit_passed", self.delivery()["status"])
        self.assertEqual("guild-1", self.delivery()["guild_id"])
        self.assertEqual("", self.delivery()["audit_time"])

    async def test_channel_mismatch_does_not_link_unrelated_event(self) -> None:
        self.tracker.record_event(self.event("other-channel"), passed=True)
        await self.submit()
        self.assertEqual("pending_audit", self.delivery()["status"])

    async def test_immediate_success(self) -> None:
        self.sender.post_message.return_value = {"id": "sent"}
        await self.tracker.send(self.sender, "test-task", "123", "content")
        self.assertEqual("sent", self.delivery()["status"])
        self.assertEqual("sent", self.delivery()["message_id"])

    async def test_missing_audit_id_stays_pending(self) -> None:
        self.sender.post_message.return_value = {"code": 304023}
        await self.tracker.send(self.sender, "test-task", "123", "content")
        self.assertEqual("pending_audit", self.delivery()["status"])
        with self.assertLogs("botpy.message_audit", "WARNING"):
            self.tracker.record_event(object(), passed=True)
        self.assertEqual(
            0,
            self.connection.execute(
                "SELECT count(*) FROM message_audit_events").fetchone()[0])

    async def test_unknown_and_rejected_results_fail_without_retry(
            self) -> None:
        for response, status in ((None, "unknown"), ({
                "code": 123
        }, "rejected")):
            with self.subTest(status=status):
                self.connection.execute("DELETE FROM scheduled_message_sends")
                self.sender.post_message.reset_mock()
                self.sender.post_message.return_value = response
                with self.assertRaisesRegex(RuntimeError, status):
                    await self.tracker.send(self.sender, "task", "123", "x")
                self.sender.post_message.assert_awaited_once()
                self.assertEqual(status, self.delivery()["status"])

    async def test_error_or_cancellation_is_unknown_not_resent(self) -> None:
        for error in (RuntimeError("secret"), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                self.connection.execute("DELETE FROM scheduled_message_sends")
                self.sender.post_message.reset_mock()
                self.sender.post_message.side_effect = error
                with self.assertLogs("botpy.message_audit", "WARNING") as logs:
                    with self.assertRaises(type(error)):
                        await self.tracker.send(self.sender, "task", "123", "x")
                self.assertNotIn("secret", "\n".join(logs.output))
                self.sender.post_message.assert_awaited_once()
                self.assertEqual("unknown", self.delivery()["status"])

    async def test_pre_send_storage_failure_prevents_network_call(self) -> None:
        with mock.patch.object(self.repository,
                               "start",
                               side_effect=sqlite3.OperationalError()):
            with self.assertRaises(sqlite3.OperationalError):
                await self.tracker.send(self.sender, "task", "123", "x")
        self.sender.post_message.assert_not_awaited()

    async def test_post_send_storage_failure_does_not_resend(self) -> None:
        self.sender.post_message.return_value = {"id": "sent"}
        with mock.patch.object(self.repository,
                               "finish",
                               side_effect=sqlite3.OperationalError()):
            with self.assertRaises(sqlite3.OperationalError):
                await self.tracker.send(self.sender, "task", "123", "x")
        self.sender.post_message.assert_awaited_once()

    async def test_scheduler_context_is_reset_on_error(self) -> None:

        async def callback() -> None:
            self.assertEqual("test-task", task_scheduler.CURRENT_TASK_ID.get())
            raise RuntimeError("failed")

        task = task_scheduler.ScheduledTask(
            id="test-task",
            description="test",
            callback=callback,
            schedule=task_scheduler.CronSchedule(hour=2))
        scheduler = task_scheduler.TaskScheduler()
        with self.assertLogs("task_scheduler", "ERROR"):
            with self.assertRaises(RuntimeError):
                await scheduler.run_task(task)
        self.assertEqual("", task_scheduler.CURRENT_TASK_ID.get())
