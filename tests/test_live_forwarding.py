"""Tests routing, durable acceptance, and QQ delivery outcomes."""

import asyncio
import pathlib
import tempfile
import time
from typing import Any, Literal
import unittest
from unittest import mock

from aiohttp import test_utils
from aiohttp import web
from botpy import errors as bot_errors

from live_forwarding import server as forwarding


def event(kind: Literal["super_chat", "gift"] = "super_chat",
          amount: int = 5000) -> forwarding.LiveEvent:
    item: forwarding.LiveEvent = dict(schema_version=1,
                                      event_id="a" * 64,
                                      event_type=kind,
                                      streamer_uid="1",
                                      streamer_name="主播",
                                      room_id="2",
                                      session_id="3",
                                      occurred_at="2026-11-01 12:00:00",
                                      sender_name="用户",
                                      sender_uid="4",
                                      amount_cents=amount,
                                      message="你好<@everyone>",
                                      received_at=time.time())
    if kind == "gift":
        item["gift_name"] = "礼物"
        item["quantity"] = 2
        item["coin_type"] = "gold"
    return item


def config() -> forwarding.ForwardingConfig:
    return dict(enabled=True,
                dry_run=False,
                max_event_age_seconds=300,
                send_interval_seconds=0.01,
                channels=[
                    dict(channel_id="10",
                         enabled=True,
                         streamer_uids=["1"],
                         super_chat={
                             "enabled": True,
                             "min_amount_cents": 3000
                         },
                         gift={
                             "enabled": True,
                             "min_amount_cents": 10000,
                             "paid_only": True
                         }),
                    dict(channel_id="20",
                         enabled=True,
                         all_streamers=True,
                         super_chat={
                             "enabled": True,
                             "min_amount_cents": 10000
                         }),
                ])


class RuleTests(unittest.TestCase):

    def test_independent_channel_thresholds_and_paid_gifts(self) -> None:
        channels = config()["channels"]
        self.assertTrue(forwarding.matches(channels[0], event()))
        self.assertFalse(forwarding.matches(channels[1], event()))
        self.assertTrue(forwarding.matches(channels[0], event("gift", 10000)))
        silver = event("gift", 10000)
        silver["coin_type"] = "silver"
        self.assertFalse(forwarding.matches(channels[0], silver))
        other = event()
        other["streamer_uid"] = "9"
        self.assertFalse(forwarding.matches(channels[0], other))

    def test_validation_and_mentions(self) -> None:
        forwarding.validate_event(event())
        self.assertNotIn("<@", forwarding.format_event(event()))
        for field, value in (("schema_version",
                              2), ("amount_cents", -1), ("amount_cents", True),
                             ("received_at", float('nan')), ("channel_id",
                                                             "10")):
            item: dict[str, object] = dict(event())
            item[field] = value
            with self.assertRaises(ValueError):
                forwarding.validate_event(item)

    def test_configuration_fail_closed(self) -> None:
        self.assertFalse(forwarding.load_config()["enabled"])
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "rules.yaml"
            for text in ('enabled: wrong',
                         'channels: [{channel_id: "10", enabled: true}]',
                         'channels: [{channel_id: 10, all_streamers: true}]',
                         'send_interval_seconds: 0'):
                path.write_text(text, encoding='utf-8')
                with self.assertRaises(ValueError):
                    forwarding.load_config(path)


class InboxTests(unittest.TestCase):

    def test_restart_dedupe_snapshots_dry_run_and_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(pathlib.Path(directory) / 'events.db')
            store = forwarding.Inbox(path)
            item = event()
            cfg = config()
            self.assertTrue(store.accept(item, cfg))
            self.assertIsNotNone(store.next("10"))
            self.assertIsNone(store.next("20"))
            pending = store.next("10")
            assert pending is not None
            store.mark(pending, "sending")
            store.conn.close()
            store = forwarding.Inbox(path)
            self.assertFalse(store.accept(item, cfg))
            self.assertEqual(
                'unknown',
                store.conn.execute('SELECT status FROM deliveries').fetchone()
                [0])
            for identifier, dry, age in (("b", True, 0), ("c", False, 400)):
                item = event()
                item['event_id'] = identifier * 64
                item['received_at'] -= age
                cfg['dry_run'] = dry
                store.accept(item, cfg)
            self.assertEqual(
                2,
                store.conn.execute(
                    'SELECT COUNT(*) FROM deliveries').fetchone()[0])
            store.conn.close()


class ForwardHTTPTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self) -> None:
        self.api = mock.Mock()
        self.api.post_message = mock.AsyncMock(return_value={'id': 'sent-id'})
        self.service = forwarding.LiveForwardingServer(self.api, config())
        self.service.token = 'test-token'
        self.service.inbox = forwarding.Inbox(':memory:')
        app = web.Application(client_max_size=65536)
        app.router.add_post('/internal/live-events', self.service.receive)
        self.browser = test_utils.TestClient(test_utils.TestServer(app))
        await self.browser.start_server()

    async def asyncTearDown(self) -> None:
        await self.browser.close()
        await self.service.close()

    async def test_auth_validation_ack_and_dedup(self) -> None:
        assert self.service.inbox is not None
        response = await self.browser.post('/internal/live-events',
                                           json=event())
        self.assertEqual(401, response.status)
        for _ in range(2):
            response = await self.browser.post(
                '/internal/live-events',
                headers={'Authorization': 'Bearer test-token'},
                json=event())
            self.assertEqual(202, response.status)
            self.assertTrue((await response.json())['accepted'])
        self.assertEqual(
            1,
            self.service.inbox.conn.execute(
                'SELECT COUNT(*) FROM deliveries').fetchone()[0])
        bad = event()
        bad['amount_cents'] = -1
        response = await self.browser.post(
            '/internal/live-events',
            headers={'Authorization': 'Bearer test-token'},
            json=bad)
        self.assertEqual(400, response.status)

    async def run_worker_until_called(self,
                                      result: dict[str, Any] | None = None,
                                      error: Exception | None = None) -> str:
        assert self.service.inbox is not None
        self.api.post_message.reset_mock()
        self.api.post_message.side_effect = error
        self.api.post_message.return_value = result
        item = event()
        item['event_id'] = str(
            self.service.inbox.conn.execute(
                'SELECT COUNT(*) FROM events').fetchone()[0] + 1) * 64
        self.service.inbox.accept(item, self.service.config)
        task = asyncio.create_task(self.service.worker('10'))
        try:
            for _ in range(100):
                await asyncio.sleep(.002)
                row = self.service.inbox.conn.execute(
                    'SELECT status FROM deliveries WHERE event_id=?',
                    (item['event_id'],)).fetchone()
                if self.api.post_message.await_count and row[0] != 'sending':
                    return row[0]
            self.fail('worker did not finish')
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_delivery_states_no_false_success(self) -> None:
        self.assertEqual('sent', await
                         self.run_worker_until_called({'id': 'm'}))
        self.assertEqual('audit', await
                         self.run_worker_until_called({'code': 304023}))
        self.assertEqual('unknown', await self.run_worker_until_called(None))
        self.assertEqual(
            'failed', await
            self.run_worker_until_called(error=RuntimeError('rejected')))

    async def test_explicit_rate_limit_retries_and_timeout_unknown(
            self) -> None:
        self.assertEqual(
            'pending', await self.run_worker_until_called(
                error=bot_errors.SequenceNumberError('limited')))
        self.assertEqual(
            'unknown', await
            self.run_worker_until_called(error=asyncio.TimeoutError()))
