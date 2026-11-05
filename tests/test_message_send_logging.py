"""Checks metadata-only channel send logs without contacting QQ."""

import asyncio
import types
import unittest
from unittest import mock

from botpy_ext import api as extended_api


class MessageSendLoggingTests(unittest.IsolatedAsyncioTestCase):
    """Ensures modes, IDs, outcomes, and privacy survive the SDK adapter."""

    async def asyncSetUp(self) -> None:
        self.request = mock.AsyncMock(return_value={"id": "sent-id"})
        self.api = extended_api.ExtendedBotAPI(http=types.SimpleNamespace(
            request=self.request))

    async def test_reply_logs_source_and_returned_id_but_not_content(
            self) -> None:
        with self.assertLogs("botpy.channel_send", level="INFO") as records:
            result = await self.api.post_message("123",
                                                 content="private-content",
                                                 msg_id="source-id")
        self.assertEqual({"id": "sent-id"}, result)
        output = "\n".join(records.output)
        self.assertIn("mode=reply", output)
        self.assertIn("msg_id='source-id'", output)
        self.assertIn("message_id='sent-id'", output)
        self.assertIn("status=sent", output)
        self.assertNotIn("private-content", output)
        call = self.request.await_args
        assert call is not None
        self.assertEqual("source-id", call.kwargs["json"]["msg_id"])
        attempts = [
            record.getMessage().split("attempt=", 1)[1].split()[0]
            for record in records.records
        ]
        self.assertEqual(2, len(attempts))
        self.assertEqual(attempts[0], attempts[1])

    async def test_proactive_and_event_reply_modes(self) -> None:
        for arguments, mode in (({}, "proactive"), ({
                "event_id": "event-id"
        }, "event_reply")):
            with self.subTest(mode=mode):
                with self.assertLogs("botpy.channel_send",
                                     level="INFO") as records:
                    await self.api.post_message("123",
                                                content="test",
                                                **arguments)
                self.assertIn("mode=" + mode, "\n".join(records.output))
                self.assertIn("msg_id='-'", "\n".join(records.output))

    async def test_pending_response_logs_audit_id(self) -> None:
        self.request.return_value = {
            "code": 304023,
            "data": {
                "message_audit": {
                    "audit_id": "audit-id"
                }
            },
        }
        with self.assertLogs("botpy.channel_send", "INFO") as records:
            await self.api.post_message("123", content="private-content")
        self.assertIn("audit_id='audit-id'", "\n".join(records.output))
        self.assertNotIn("private-content", "\n".join(records.output))

    async def test_audit_rejection_and_empty_result_are_not_logged_as_sent(
            self) -> None:
        for result, status in (({
                "code": 304024
        }, "audit"), ({
                "code": 304027
        }, "rejected"), (None, "unknown")):
            with self.subTest(status=status):
                self.request.return_value = result
                with self.assertLogs("botpy.channel_send",
                                     level="INFO") as records:
                    await self.api.post_message("123", msg_id="source-id")
                output = "\n".join(records.output)
                self.assertIn("status=" + status, output)
                self.assertNotIn("status=sent", output)

    async def test_error_and_cancellation_are_preserved_without_private_details(
            self) -> None:
        for error in (RuntimeError("private-error-response"),
                      asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                self.request.reset_mock()
                self.request.side_effect = error
                with self.assertLogs("botpy.channel_send",
                                     level="INFO") as records:
                    with self.assertRaises(type(error)):
                        await self.api.post_message("123", msg_id="source-id")
                self.request.assert_awaited_once()
                self.assertIn("msg_id='source-id'", "\n".join(records.output))
                self.assertNotIn("private-error-response",
                                 "\n".join(records.output))

    async def test_untrusted_ids_are_escaped_and_bounded_in_logs_only(
            self) -> None:
        message_id = "id\nforged-log " + "a" * 300
        with self.assertLogs("botpy.channel_send", level="INFO") as records:
            await self.api.post_message("123", msg_id=message_id)
        self.assertTrue(
            all("\n" not in item.getMessage() for item in records.records))
        self.assertNotIn("a" * 300, "\n".join(records.output))
        call = self.request.await_args
        assert call is not None
        self.assertEqual(message_id, call.kwargs["json"]["msg_id"])
