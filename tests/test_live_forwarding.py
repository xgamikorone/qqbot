import asyncio
import copy
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from botpy.errors import SequenceNumberError
from live_forwarding import Inbox, LiveForwardingServer, format_event, load_config, matches, validate_event

def event(kind="super_chat", amount=5000):
    return dict(schema_version=1, event_id="a"*64, event_type=kind, streamer_uid="1", streamer_name="主播", room_id="2", session_id="3", occurred_at="2026-11-01 12:00:00", sender_name="用户", sender_uid="4", amount_cents=amount, message="你好<@everyone>", received_at=time.time(), **({"gift_name":"礼物", "quantity":2, "coin_type":"gold"} if kind=="gift" else {}))

def config():
    return dict(enabled=True, dry_run=False, max_event_age_seconds=300, send_interval_seconds=0.01, channels=[
        dict(channel_id="10",enabled=True,streamer_uids=["1"],super_chat={"enabled":True,"min_amount_cents":3000}, gift={"enabled":True,"min_amount_cents":10000,"paid_only":True}),
        dict(channel_id="20",enabled=True,all_streamers=True,super_chat={"enabled":True,"min_amount_cents":10000}),
    ])

class RuleTests(unittest.TestCase):
    def test_independent_channel_thresholds_and_paid_gifts(self):
        channels=config()["channels"]
        self.assertTrue(matches(channels[0],event()))
        self.assertFalse(matches(channels[1],event()))
        self.assertTrue(matches(channels[0],event("gift",10000)))
        silver=event("gift",10000);silver["coin_type"]="silver"
        self.assertFalse(matches(channels[0],silver))
        other=event();other["streamer_uid"]="9"
        self.assertFalse(matches(channels[0],other))

    def test_validation_and_mentions(self):
        validate_event(event())
        self.assertNotIn("<@",format_event(event()))
        for field,value in (("schema_version",2),("amount_cents",-1),("amount_cents",True),("received_at",float('nan')),("channel_id","10")):
            item=event();item[field]=value
            with self.assertRaises(ValueError):validate_event(item)

    def test_configuration_fail_closed(self):
        self.assertFalse(load_config()["enabled"])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"rules.yaml"
            for text in ('enabled: wrong', 'channels: [{channel_id: "10", enabled: true}]', 'channels: [{channel_id: 10, all_streamers: true}]', 'send_interval_seconds: 0'):
                path.write_text(text,encoding='utf-8')
                with self.assertRaises(ValueError):load_config(path)

class InboxTests(unittest.TestCase):
    def test_restart_dedupe_snapshots_dry_run_and_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'events.db');store=Inbox(path)
            item=event();cfg=config()
            self.assertTrue(store.accept(item,cfg))
            self.assertIsNotNone(store.next("10"));self.assertIsNone(store.next("20"))
            store.mark(store.next("10"),"sending")
            store.conn.close();store=Inbox(path)
            self.assertFalse(store.accept(item,cfg))
            self.assertEqual('unknown',store.conn.execute('SELECT status FROM deliveries').fetchone()[0])
            for identifier,dry,age in (("b",True,0),("c",False,400)):
                item=event();item['event_id']=identifier*64;item['received_at']-=age
                cfg['dry_run']=dry;store.accept(item,cfg)
            self.assertEqual(2,store.conn.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0])
            store.conn.close()

class ForwardHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.api=type('API',(),{})();self.api.post_message=AsyncMock(return_value={'id':'sent-id'})
        self.service=LiveForwardingServer(self.api,config())
        self.service.token='test-token';self.service.inbox=Inbox(':memory:')
        app=web.Application(client_max_size=65536);app.router.add_post('/internal/live-events',self.service.receive)
        self.browser=TestClient(TestServer(app));await self.browser.start_server()
    async def asyncTearDown(self):
        await self.browser.close();await self.service.close()
    async def test_auth_validation_ack_and_dedup(self):
        response=await self.browser.post('/internal/live-events',json=event());self.assertEqual(401,response.status)
        for _ in range(2):
            response=await self.browser.post('/internal/live-events',headers={'Authorization':'Bearer test-token'},json=event())
            self.assertEqual(202,response.status);self.assertTrue((await response.json())['accepted'])
        self.assertEqual(1,self.service.inbox.conn.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0])
        bad=event();bad['amount_cents']=-1
        response=await self.browser.post('/internal/live-events',headers={'Authorization':'Bearer test-token'},json=bad);self.assertEqual(400,response.status)
    async def run_worker_until_called(self, result=None, error=None):
        self.api.post_message.reset_mock();self.api.post_message.side_effect=error;self.api.post_message.return_value=result
        item=event();item['event_id']=str(self.service.inbox.conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]+1)*64
        self.service.inbox.accept(item,self.service.config)
        task=asyncio.create_task(self.service.worker('10'))
        try:
            for _ in range(100):
                await asyncio.sleep(.002)
                row=self.service.inbox.conn.execute('SELECT status FROM deliveries WHERE event_id=?',(item['event_id'],)).fetchone()
                if self.api.post_message.await_count and row[0]!='sending':return row[0]
            self.fail('worker did not finish')
        finally:
            task.cancel();await asyncio.gather(task,return_exceptions=True)
    async def test_delivery_states_no_false_success(self):
        self.assertEqual('sent',await self.run_worker_until_called({'id':'m'}))
        self.assertEqual('audit',await self.run_worker_until_called({'code':304023}))
        self.assertEqual('unknown',await self.run_worker_until_called(None))
        self.assertEqual('failed',await self.run_worker_until_called(error=RuntimeError('rejected')))
    async def test_explicit_rate_limit_retries_and_timeout_unknown(self):
        self.assertEqual('pending',await self.run_worker_until_called(error=SequenceNumberError('limited')))
        self.assertEqual('unknown',await self.run_worker_until_called(error=asyncio.TimeoutError()))
