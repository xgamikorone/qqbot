"""Checks source-aware notification delivery without real QQ requests."""

import asyncio
import datetime
import dataclasses
import time
import unittest
from unittest import mock

import live_forwarding
import qq_message_id
import reply_sources


class SourceAwareForwardingTests(unittest.IsolatedAsyncioTestCase):
    """Covers canonical IDs, waiting, and ambiguous delivery outcomes."""

    async def asyncSetUp(self) -> None:
        self.api = mock.Mock()
        self.api.post_message = mock.AsyncMock(return_value={"id": "sent-id"})
        self.api.get_channels = mock.AsyncMock(return_value=[
            {
                "id": "2",
                "guild_id": "1"
            },
            {
                "id": "3",
                "guild_id": "1"
            },
        ])
        self.seed = qq_message_id.encode_message_id(1, 2, 10, 123)
        self.api.get_message = mock.AsyncMock(
            return_value={
                "id":
                    self.seed,
                "channel_id":
                    "2",
                "guild_id":
                    "1",
                "timestamp":
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "author": {
                    "bot": False
                },
            })
        self.pool = reply_sources.ReplySources(
            self.api,
            reply_sources.Settings(
                enabled=True,
                automatic_forwarding=True,
                max_probes_per_batch=1,
                guilds=(reply_sources.GuildSettings("1", ("2",), ("3",)),),
            ),
            ":memory:",
            sleep=mock.AsyncMock(),
        )
        config: live_forwarding.ForwardingConfig = {
            "enabled":
                True,
            "dry_run":
                False,
            "max_event_age_seconds":
                300,
            "send_interval_seconds":
                .01,
            "channels": [{
                "channel_id": "3",
                "enabled": True,
                "all_streamers": True,
                "super_chat": {
                    "enabled": True
                }
            }],
        }
        self.forwarder = live_forwarding.LiveForwardingServer(self.api, config)
        await self.forwarder.reply_sources.close()
        self.forwarder.reply_sources = self.pool
        self.forwarder.inbox = live_forwarding.Inbox(":memory:")
        self.event: live_forwarding.LiveEvent = {
            "schema_version": 1,
            "event_id": "a" * 64,
            "event_type": "super_chat",
            "streamer_uid": "1",
            "streamer_name": "streamer",
            "room_id": "2",
            "session_id": "3",
            "occurred_at": "now",
            "sender_name": "viewer",
            "sender_uid": "4",
            "amount_cents": 3000,
            "message": "hello",
            "received_at": time.time(),
        }
        self.forwarder.inbox.accept(self.event, config)

    async def asyncTearDown(self) -> None:
        await self.forwarder.close()

    async def run_until_sent_attempt(self) -> str:
        """Runs a worker until it settles one attempted delivery."""
        task = asyncio.create_task(self.forwarder.worker("3"))
        try:
            for _ in range(100):
                await asyncio.sleep(.002)
                assert self.forwarder.inbox is not None
                row = self.forwarder.inbox.conn.execute(
                    "SELECT status FROM deliveries").fetchone()
                if self.api.post_message.await_count and row[0] != "sending":
                    return str(row[0])
            self.fail("No delivery attempt completed")
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_send_uses_cross_channel_canonical_source(self) -> None:
        await self.pool.register_seed("1", "2", self.seed)
        with self.assertLogs("botpy.live_forwarding", level="INFO") as records:
            self.assertEqual("sent", await self.run_until_sent_attempt())
        output = "\n".join(records.output)
        self.assertIn("event_id=" + self.event["event_id"], output)
        self.assertIn("mode=reply", output)
        self.assertIn("msg_id=" + self.seed, output)
        self.assertIn("source_channel_id=2", output)
        self.assertNotIn("hello", output)
        call = self.api.post_message.await_args
        assert call is not None
        self.assertEqual("3", call.kwargs["channel_id"])
        self.assertEqual(self.seed, call.kwargs["msg_id"])

    async def test_manual_experiment_does_not_change_existing_sender(
            self) -> None:
        self.pool.settings = dataclasses.replace(self.pool.settings,
                                                 automatic_forwarding=False)
        with self.assertLogs("botpy.live_forwarding", level="INFO") as records:
            self.assertEqual("sent", await self.run_until_sent_attempt())
        self.assertIn("mode=proactive", "\n".join(records.output))
        self.assertIn("msg_id=-", "\n".join(records.output))
        call = self.api.post_message.await_args
        assert call is not None
        self.assertNotIn("msg_id", call.kwargs)
        self.api.get_message.assert_not_awaited()
        self.api.get_channels.assert_not_awaited()

    async def test_no_source_leaves_pending_and_never_sends_proactively(
            self) -> None:
        task = asyncio.create_task(self.forwarder.worker("3"))
        try:
            await asyncio.sleep(.02)
            self.api.post_message.assert_not_awaited()
            assert self.forwarder.inbox is not None
            row = self.forwarder.inbox.conn.execute(
                "SELECT status,attempts FROM deliveries").fetchone()
            self.assertEqual(("pending", 0), tuple(row))
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_timeout_is_unknown_without_another_source_or_proactive_retry(
            self) -> None:
        await self.pool.register_seed("1", "2", self.seed)
        self.api.post_message.side_effect = asyncio.TimeoutError()
        self.assertEqual("unknown", await self.run_until_sent_attempt())
        self.api.post_message.assert_awaited_once()
        self.assertEqual([], (await self.pool.status("1"))["sources"])

    async def test_explicit_source_rejection_is_not_reported_as_unknown(
            self) -> None:
        await self.pool.register_seed("1", "2", self.seed)
        self.api.post_message.return_value = {"code": 304027}
        self.assertEqual("failed", await self.run_until_sent_attempt())
        self.api.post_message.assert_awaited_once()
