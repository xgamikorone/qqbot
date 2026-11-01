"""Local authenticated event inbox and independent per-channel delivery workers."""
import asyncio
import hmac
import json
import logging
import math
import os
from pathlib import Path
import re
import sqlite3
import time

from aiohttp import web
from botpy.errors import SequenceNumberError
import yaml

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent


def load_config(path=None):
    config = yaml.safe_load(Path(path or ROOT / "config/live_forwarding.yaml").read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) - {"enabled", "channels", "max_event_age_seconds", "send_interval_seconds", "dry_run"}:
        raise ValueError("Invalid forwarding configuration")
    for key in ("enabled", "dry_run"):
        if type(config.get(key, False)) is not bool:
            raise ValueError("Forwarding switches must be booleans")
    for key, default in (("max_event_age_seconds", 300), ("send_interval_seconds", 1)):
        value = config.setdefault(key, default)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("Forwarding limits must be positive")
    channels = config.setdefault("channels", [])
    if not isinstance(channels, list) or len(channels) > 100:
        raise ValueError("Invalid channel list")
    ids = set()
    for channel in channels:
        if not isinstance(channel, dict) or set(channel) - {"channel_id", "enabled", "all_streamers", "streamer_uids", "super_chat", "gift"}:
            raise ValueError("Invalid channel configuration")
        channel_id = channel.get("channel_id")
        if not isinstance(channel_id, str) or not channel_id.isdigit() or channel_id in ids:
            raise ValueError("Channel IDs must be distinct numeric strings")
        ids.add(channel_id)
        for key in ("enabled", "all_streamers"):
            if type(channel.get(key, False)) is not bool:
                raise ValueError("Invalid channel switch")
        uids = channel.get("streamer_uids", [])
        if not isinstance(uids, list) or any(not isinstance(uid, str) or not uid.isdigit() for uid in uids):
            raise ValueError("Streamer UIDs must be numeric strings")
        if (channel.get("all_streamers", False) and uids) or (not channel.get("all_streamers", False) and not uids):
            raise ValueError("Choose all_streamers or a nonempty streamer_uids list")
        for kind in ("super_chat", "gift"):
            rule = channel.get(kind, {})
            if not isinstance(rule, dict) or set(rule) - {"enabled", "min_amount_cents", "paid_only"}:
                raise ValueError("Invalid event rule")
            for key in ("enabled", "paid_only"):
                if type(rule.get(key, False)) is not bool:
                    raise ValueError("Invalid event switch")
            amount = rule.get("min_amount_cents", 0)
            if type(amount) is not int or amount < 0:
                raise ValueError("Amounts must be nonnegative integer cents")
    return config


def validate_event(event):
    allowed = {"schema_version", "event_id", "event_type", "streamer_uid", "streamer_name", "room_id", "session_id", "occurred_at", "sender_name", "sender_uid", "amount_cents", "message", "received_at", "gift_name", "quantity", "coin_type", "raw_amount"}
    if not isinstance(event, dict) or set(event) - allowed or type(event.get("schema_version")) is not int or event["schema_version"] != 1:
        raise ValueError("Invalid event version or fields")
    if not isinstance(event.get("event_id"), str) or not re.fullmatch(r"[a-f0-9]{64}", event["event_id"]):
        raise ValueError("Invalid event ID")
    if event.get("event_type") not in ("gift", "super_chat"):
        raise ValueError("Invalid event type")
    for key in ("streamer_uid", "room_id", "session_id", "sender_uid"):
        if not isinstance(event.get(key), str) or not event[key].isdigit():
            raise ValueError("Invalid event identifier")
    for key, maximum in (("streamer_name", 255), ("sender_name", 255), ("occurred_at", 64), ("message", 4000)):
        if not isinstance(event.get(key), str) or len(event[key]) > maximum:
            raise ValueError("Invalid event text")
    if type(event.get("amount_cents")) is not int or not 0 <= event["amount_cents"] <= 10**12:
        raise ValueError("Invalid amount")
    received = event.get("received_at")
    if type(received) not in (int, float) or not math.isfinite(received) or received <= 0 or received > time.time() + 60:
        raise ValueError("Invalid timestamp")
    if event["event_type"] == "gift":
        if not isinstance(event.get("gift_name"), str) or len(event["gift_name"]) > 255 or type(event.get("quantity")) is not int or event["quantity"] <= 0 or event.get("coin_type") not in ("gold", "silver"):
            raise ValueError("Invalid gift")


def matches(channel, event):
    if not channel.get("enabled", False):
        return False
    if not channel.get("all_streamers", False) and event["streamer_uid"] not in channel.get("streamer_uids", []):
        return False
    rule = channel.get(event["event_type"], {})
    return (rule.get("enabled", False) and event["amount_cents"] >= rule.get("min_amount_cents", 0)
            and not (event["event_type"] == "gift" and rule.get("paid_only", True) and event["coin_type"] != "gold"))


def plain(text):
    # External content cannot create QQ mentions or render HTML-like control tags.
    return str(text).replace("<", "＜").replace(">", "＞").replace("\r", "")


def format_event(event):
    label = "SC通知" if event["event_type"] == "super_chat" else "礼物通知"
    body = (f"【{label}】\n主播：{plain(event['streamer_name'])}（{event['streamer_uid']}）\n"
            f"用户：{plain(event['sender_name'])}\n金额：¥{event['amount_cents'] // 100}.{event['amount_cents'] % 100:02d}\n")
    if event["event_type"] == "gift":
        body += f"礼物：{plain(event['gift_name'])} × {event['quantity']}\n"
    else:
        body += f"内容：{plain(event['message'])[:2000]}\n"
    return body + f"时间：{plain(event['occurred_at'])}"


class Inbox:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY,payload TEXT NOT NULL,received_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS deliveries(event_id TEXT NOT NULL,channel_id TEXT NOT NULL,status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,next_attempt REAL NOT NULL DEFAULT 0,message_id TEXT,
                PRIMARY KEY(event_id,channel_id));
            CREATE INDEX IF NOT EXISTS idx_deliveries_due ON deliveries(channel_id,status,next_attempt);
        """)
        # A crash during a send has unknown outcome: do not automatically duplicate it.
        with self.conn:
            self.conn.execute("UPDATE deliveries SET status='unknown' WHERE status='sending'")

    def accept(self, event, config):
        payload = json.dumps(event, ensure_ascii=False, sort_keys=True)
        with self.conn:
            existing = self.conn.execute("SELECT 1 FROM events WHERE event_id=?", (event["event_id"],)).fetchone()
            if existing:
                return False
            self.conn.execute("INSERT INTO events VALUES (?,?,?)", (event["event_id"], payload, event["received_at"]))
            if time.time() - event["received_at"] <= config["max_event_age_seconds"]:
                for channel in config["channels"]:
                    if matches(channel, event):
                        status = "dry_run" if config.get("dry_run", True) else "pending"
                        self.conn.execute("INSERT INTO deliveries(event_id,channel_id,status) VALUES (?,?,?)", (event["event_id"], channel["channel_id"], status))
        return True

    def next(self, channel):
        return self.conn.execute("SELECT d.*,e.payload,e.received_at FROM deliveries d JOIN events e USING(event_id) WHERE channel_id=? AND status='pending' AND next_attempt<=? ORDER BY received_at LIMIT 1", (channel, time.time())).fetchone()

    def mark(self, row, status, message_id=None):
        attempts = row["attempts"] + 1
        with self.conn:
            self.conn.execute("UPDATE deliveries SET status=?,attempts=?,next_attempt=?,message_id=? WHERE event_id=? AND channel_id=?", (status, attempts, time.time() + min(60, 2**min(attempts, 6)), message_id, row["event_id"], row["channel_id"]))


class LiveForwardingServer:
    def __init__(self, api, config, db_path=None):
        self.api, self.config = api, config
        self.db_path = db_path or str(ROOT / "live_forwarding.db")
        self.token = os.getenv("LIVE_FORWARD_TOKEN", "").strip()
        self.inbox = None
        self.runner = None
        self.tasks = []
        self.wake = asyncio.Event()

    async def receive(self, request):
        if not self.token or not hmac.compare_digest(request.headers.get("Authorization", ""), "Bearer " + self.token):
            raise web.HTTPUnauthorized()
        try:
            event = await request.json()
            validate_event(event)
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(text="Invalid live event") from None
        self.inbox.accept(event, self.config)
        self.wake.set()
        return web.json_response({"accepted": True, "event_id": event["event_id"]}, status=202)

    async def worker(self, channel_id):
        while True:
            self.wake.clear()
            row = self.inbox.next(channel_id)
            if row:
                if time.time() - row["received_at"] > self.config["max_event_age_seconds"]:
                    self.inbox.mark(row, "expired")
                    continue
                self.inbox.mark(row, "sending")
                try:
                    result = await asyncio.wait_for(self.api.post_message(channel_id=channel_id, content=format_event(json.loads(row["payload"]))), 10)
                    if isinstance(result, dict) and result.get("id"):
                        self.inbox.mark(row, "sent", str(result["id"]))
                    elif isinstance(result, dict) and result.get("code") == 304023:
                        self.inbox.mark(row, "audit")
                    else:
                        self.inbox.mark(row, "unknown")
                except asyncio.CancelledError:
                    raise
                except SequenceNumberError:
                    # Explicit 429 rejection is safe to retry, unlike a read timeout.
                    self.inbox.mark(row, "pending" if row["attempts"] < 8 else "failed")
                except asyncio.TimeoutError:
                    self.inbox.mark(row, "unknown")
                except Exception:
                    # SDK failures can include both rejection and ambiguous outcomes.
                    # Never blindly repeat a proactive message that might be delivered.
                    self.inbox.mark(row, "failed")
                    log.warning("Live notification failed: channel=%s event=%s", channel_id, row["event_id"])
                await asyncio.sleep(self.config["send_interval_seconds"])
                continue
            try:
                await asyncio.wait_for(self.wake.wait(), 1)
            except asyncio.TimeoutError:
                pass

    async def start(self):
        if self.runner or not self.config.get("enabled", False):
            return
        if not self.token or self.token.startswith("your_"):
            raise ValueError("LIVE_FORWARD_TOKEN is required")
        self.inbox = Inbox(self.db_path)
        app = web.Application(client_max_size=65536)
        app.router.add_post("/internal/live-events", self.receive)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, "127.0.0.1", int(os.getenv("LIVE_FORWARD_PORT", "8091"))).start()
        self.tasks = [asyncio.create_task(self.worker(c["channel_id"])) for c in self.config["channels"] if c.get("enabled", False)]

    async def close(self):
        if self.runner:
            await self.runner.cleanup()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.inbox:
            self.inbox.conn.close()
        self.runner = None
