"""Bounded discovery and reservation tests with simulated QQ responses."""

import asyncio
import dataclasses
import datetime
import pathlib
import tempfile
from typing import Any
import unittest
from unittest import mock

from botpy import errors as bot_errors

from messaging import message_id as codec
from messaging import reply_sources


def settings(**overrides: Any) -> reply_sources.Settings:
    """Builds a small, explicitly allowed experimental route."""
    base = reply_sources.Settings(
        enabled=True,
        max_probes_per_batch=2,
        max_sequence_distance=2,
        guilds=(reply_sources.GuildSettings("1", ("2",), ("3",)),),
    )
    return dataclasses.replace(base, **overrides)


class ConfigTests(unittest.TestCase):
    """Checks opt-in defaults and strict safety budgets."""

    def test_default_is_disabled(self) -> None:
        self.assertFalse(reply_sources.load_config().enabled)

    def test_rejects_invalid_config(self) -> None:
        invalid = (
            "automatic_forwarding: true\nenabled: false",
            "enabled: yesplease",
            "unexpected: true",
            "max_probes_per_batch: 11",
            "max_source_age_seconds: 300",
            "discovery_requests_per_minute: 61",
            "max_uses_per_source: true",
            'guilds: [{guild_id: "1", source_channel_ids: [], '
            'target_channel_ids: ["3"]}]',
            'guilds: [{guild_id: "1", source_channel_ids: ["2", "2"], '
            'target_channel_ids: ["3"]}]',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "sources.yaml"
            for text in invalid:
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text), self.assertRaises(ValueError):
                    reply_sources.load_config(path)


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    """Exercises the discovery interface without network access."""

    async def asyncSetUp(self) -> None:
        self.now = 1793530000.0
        self.api = mock.Mock()
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
        self.api.get_message = mock.AsyncMock()
        self.sleep = mock.AsyncMock()
        self.pool = reply_sources.ReplySources(
            self.api,
            settings(),
            ":memory:",
            clock=lambda: self.now,
            sleep=self.sleep,
        )
        self.addAsyncCleanup(self.pool.close)

    def message(self,
                sequence: int,
                age: float = 0,
                bot: bool = False) -> dict[str, Any]:
        """Returns canonical metadata with real and encoded time separated."""
        timestamp = datetime.datetime.fromtimestamp(
            self.now - age, datetime.timezone.utc).isoformat()
        return {
            "id": codec.encode_message_id(1, 2, sequence, 123),
            "guild_id": "1",
            "channel_id": "2",
            "timestamp": timestamp,
            "author": {
                "bot": bot
            },
            "content": "must not be retained",
        }

    async def register(self, message: dict[str, Any] | None = None) -> None:
        self.api.get_message.return_value = message or self.message(10)
        await self.pool.register_seed("1", "2",
                                      self.api.get_message.return_value["id"])
        self.api.get_message.reset_mock()

    async def test_canonical_id_cross_channel_and_single_reservation(
            self) -> None:
        await self.register()
        canonical = self.message(11)
        canonical["id"] = codec.encode_message_id(1, 2, 11, 999)
        self.api.get_message.side_effect = [
            {
                "message": canonical
            },
            self.message(12, bot=True),
        ]
        result = await self.pool.probe("1")
        self.assertEqual(2, result["queries"])
        self.assertEqual(2, self.api.get_message.await_count)
        first, second = await asyncio.gather(self.pool.acquire("3"),
                                             self.pool.acquire("3"))
        assert first is not None and second is not None
        self.assertNotEqual(first.message_id, second.message_id)
        self.assertEqual({self.message(10)["id"], canonical["id"]},
                         {first.message_id, second.message_id})
        self.assertEqual("2", first.channel_id)
        self.pool.finish(first, "sent")
        self.pool.finish(second, "unknown")
        self.assertIsNone(await self.pool.acquire("3"))
        self.assertIsNone(await self.pool.acquire("999"))
        self.assertNotIn("must not be retained", str(await
                                                     self.pool.status("1")))

    async def test_gap_is_revisited_and_probe_calls_are_capped(self) -> None:
        await self.register(self.message(10, age=280))
        self.api.get_message.side_effect = bot_errors.NotFoundError("missing")
        await self.pool.probe("1")
        sequences = [
            codec.decode_message_id(call.kwargs["message_id"]).sequence
            for call in self.api.get_message.await_args_list
        ]
        self.assertEqual([11, 12], sequences)
        self.pool._cooldown.clear()
        self.api.get_message.side_effect = [self.message(11), self.message(12)]
        self.api.get_message.reset_mock()
        await self.pool.probe("1")
        self.assertEqual(
            11,
            codec.decode_message_id(self.api.get_message.await_args_list[0].
                                    kwargs["message_id"]).sequence)
        self.assertIsNotNone(await self.pool.acquire("3"))
        self.assertTrue(self.sleep.await_count)

    async def test_old_bot_unknown_author_and_future_messages_not_eligible(
            self) -> None:
        for metadata in (self.message(10, age=280), self.message(11, bot=True)):
            await self.register(metadata)
        unknown = self.message(12)
        unknown["author"] = {}
        await self.register(unknown)
        self.assertEqual([], (await self.pool.status("1"))["sources"])
        future = self.message(13, age=-1)
        with self.assertRaises(ValueError):
            await self.register(future)

    async def test_returned_sequence_and_guild_are_validated_before_seed_update(
            self) -> None:
        await self.register(self.message(10, age=280))
        self.api.get_message.return_value = self.message(99)
        result = await self.pool.probe("1")
        self.assertEqual("invalid_response", result["state"])
        self.assertEqual(10, self.pool._seeds["2"].sequence)
        mismatch = self.message(10)
        mismatch["guild_id"] = "9"
        self.api.get_message.return_value = mismatch
        with self.assertRaises(ValueError):
            await self.pool.register_seed("1", "2", self.message(10)["id"])

    async def test_allowlist_rejected_without_queries(self) -> None:
        for guild_id, channel_id in (("9", "2"), ("1", "3")):
            with self.assertRaises(ValueError):
                await self.pool.register_seed(guild_id, channel_id,
                                              self.message(10)["id"])
        self.api.get_channels.assert_not_awaited()
        self.api.get_message.assert_not_awaited()

    async def test_channel_membership_mismatch_blocks_queries(self) -> None:
        self.api.get_channels.return_value = [{"id": "2", "guild_id": "1"}]
        with self.assertRaises(ValueError):
            await self.register()
        self.api.get_message.assert_not_awaited()

    async def test_no_seed_does_not_start_queries(self) -> None:
        result = await self.pool.probe("1")
        self.assertEqual("needs_seed", result["state"])
        self.api.get_channels.assert_not_awaited()
        self.api.get_message.assert_not_awaited()

    async def test_sdk_empty_response_does_not_permanently_pause_source(
            self) -> None:
        await self.register(self.message(10, age=280))
        self.api.get_message.return_value = None
        result = await self.pool.probe("1")
        self.assertEqual("query_failed", result["state"])
        self.assertNotIn("2", self.pool._paused)

    async def test_rate_limit_stops_batch_and_immediate_reprobe(self) -> None:
        await self.register(self.message(10, age=280))
        self.api.get_message.side_effect = bot_errors.SequenceNumberError(
            "limited")
        self.assertEqual("rate_limited", (await self.pool.probe("1"))["state"])
        self.assertEqual(1, self.api.get_message.await_count)
        self.assertEqual("waiting", (await self.pool.probe("1"))["state"])
        self.assertEqual(1, self.api.get_message.await_count)

    async def test_permission_denied_pauses_source_until_explicit_register(
            self) -> None:
        await self.register(self.message(10, age=280))
        self.api.get_message.side_effect = bot_errors.ForbiddenError(
            "forbidden")
        self.assertEqual("permission_denied", (await
                                               self.pool.probe("1"))["state"])
        self.assertIn("2", self.pool._paused)

    async def test_observe_does_not_bypass_target_verification(self) -> None:
        self.pool.observe(self.message(10))
        self.api.get_message.assert_not_awaited()
        self.assertIsNone(await self.pool.acquire("3"))
        # No worker runs until control yields; clean up its discovery first.
        await self.pool.close()

    async def test_expiry_uses_response_time_and_no_reuse_after_timeout(
            self) -> None:
        await self.register()
        source = await self.pool.acquire("3")
        assert source is not None
        self.pool.finish(source, "unknown")
        self.assertIsNone(await self.pool.acquire("3"))
        self.now += 271
        self.assertEqual([], (await self.pool.status("1"))["sources"])

    async def test_sources_are_not_shared_between_guilds(self) -> None:
        await self.register()
        self.pool.settings = dataclasses.replace(
            self.pool.settings,
            guilds=self.pool.settings.guilds +
            (reply_sources.GuildSettings("9", ("8",), ("7",)),),
        )
        self.assertIsNone(await self.pool.acquire("7"))

    async def test_concurrent_probes_share_the_same_cooldown(self) -> None:
        await self.register(self.message(10, age=280))
        self.api.get_message.side_effect = bot_errors.NotFoundError("missing")
        results = await asyncio.gather(self.pool.probe("1"),
                                       self.pool.probe("1"))
        self.assertEqual({"complete", "waiting"},
                         {item["state"] for item in results})
        self.assertEqual(2, self.api.get_message.await_count)

    async def test_reserved_source_is_not_reused_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "sources.db"
            options = settings(max_uses_per_source=3)
            for turn in range(2):
                pool = reply_sources.ReplySources(self.api,
                                                  options,
                                                  path,
                                                  clock=lambda: self.now,
                                                  sleep=self.sleep)
                try:
                    self.api.get_message.return_value = self.message(10)
                    await pool.register_seed("1", "2", self.message(10)["id"])
                    source = await pool.acquire("3")
                    if turn == 0:
                        self.assertIsNotNone(source)
                    else:
                        self.assertIsNone(source)
                finally:
                    await pool.close()

    async def test_disabled_experiment_opens_no_db_and_makes_no_requests(
            self) -> None:
        pool = reply_sources.ReplySources(self.api, reply_sources.Settings())
        self.assertIsNone(pool._conn)
        self.assertIsNone(await pool.acquire("3"))
        with self.assertRaises(ValueError):
            await pool.probe("1")
        with self.assertRaises(ValueError):
            await pool.register_seed("1", "2", self.message(10)["id"])
        await pool.close()
        self.api.get_channels.assert_not_awaited()
