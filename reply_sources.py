"""Opt-in, bounded discovery of real QQ messages for experimental replies.

Only metadata is retained. Successful GETs are candidates, not proof of reply
permission. All reads use the bot's existing authenticated SDK and allowlists.
"""

import asyncio
import collections
from collections.abc import Awaitable, Callable, Mapping
import dataclasses
import datetime
import logging
import pathlib
import sqlite3
import time
from typing import Literal

from botpy import api as bot_api
from botpy import errors as bot_errors
import yaml

import qq_message_id

_ROOT = pathlib.Path(__file__).resolve().parent
_LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class GuildSettings:
    """Explicit source and delivery allowlists within one guild."""

    guild_id: str
    source_channel_ids: tuple[str, ...]
    target_channel_ids: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Settings:
    """Local safety budgets, not claims about official rate limits."""

    enabled: bool = False
    automatic_forwarding: bool = False
    max_source_age_seconds: int = 270
    max_probes_per_batch: int = 10
    discovery_interval_seconds: int = 15
    discovery_requests_per_minute: int = 60
    max_sequence_distance: int = 100
    max_uses_per_source: int = 1
    guilds: tuple[GuildSettings, ...] = ()


def load_config(path: str | pathlib.Path | None = None) -> Settings:
    """Loads strict experiment settings; rejects excessive query budgets.

    Raises:
        ValueError: Configuration is malformed or exceeds local safety limits.
        OSError: The configuration cannot be read.
        yaml.YAMLError: The configuration is not YAML.
    """
    config_path = pathlib.Path(path or _ROOT / "config/reply_sources.yaml")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    allowed = {item.name for item in dataclasses.fields(Settings)}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError("Invalid reply source settings")
    for key in ("enabled", "automatic_forwarding"):
        if type(raw.get(key, False)) is not bool:
            raise ValueError("Reply source switches must be boolean")
    if raw.get("automatic_forwarding", False) and not raw.get("enabled", False):
        raise ValueError("Automatic forwarding requires the experiment enabled")
    defaults = Settings()
    limits = {
        "max_source_age_seconds": (1, 270),
        "max_probes_per_batch": (1, 10),
        "discovery_interval_seconds": (5, 3600),
        "discovery_requests_per_minute": (1, 60),
        "max_sequence_distance": (1, 100),
        "max_uses_per_source": (1, 5),
    }
    numbers: dict[str, int] = {}
    for key, (minimum, maximum) in limits.items():
        value = raw.get(key, getattr(defaults, key))
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f"Invalid reply source limit: {key}")
        numbers[key] = value
    guilds = raw.get("guilds", [])
    if not isinstance(guilds, list) or len(guilds) > 20:
        raise ValueError("Invalid reply source guild list")
    routes: list[GuildSettings] = []
    guild_ids: set[str] = set()
    channels_seen: set[str] = set()
    for guild in guilds:
        if not isinstance(guild, dict) or set(guild) != {
                "guild_id", "source_channel_ids", "target_channel_ids"
        }:
            raise ValueError("Invalid reply source guild")
        guild_id = guild["guild_id"]
        if (not isinstance(guild_id, str) or not guild_id.isascii() or
                not guild_id.isdigit() or guild_id in guild_ids):
            raise ValueError("Guild IDs must be distinct numeric strings")
        guild_ids.add(guild_id)
        lists: list[tuple[str, ...]] = []
        for key in ("source_channel_ids", "target_channel_ids"):
            values = guild[key]
            if (not isinstance(values, list) or not 1 <= len(values) <= 20 or
                    any(not isinstance(value, str) or not value.isascii() or
                        not value.isdigit() for value in values) or
                    len(set(values)) != len(values)):
                raise ValueError("Channel allowlists require distinct IDs")
            lists.append(tuple(values))
        all_channels = set(lists[0]) | set(lists[1])
        if all_channels & channels_seen:
            raise ValueError("A channel cannot belong to multiple guilds")
        channels_seen.update(all_channels)
        routes.append(GuildSettings(guild_id, lists[0], lists[1]))
    return Settings(enabled=raw.get("enabled", False),
                    automatic_forwarding=raw.get("automatic_forwarding", False),
                    guilds=tuple(routes),
                    **numbers)


@dataclasses.dataclass(frozen=True)
class ReplySource:
    """Canonical GET-verified source; never includes message content."""

    message_id: str
    guild_id: str
    channel_id: str
    timestamp: float


@dataclasses.dataclass
class _Seed:
    message_id: str
    sequence: int
    offset: int = 1


class ReplySources:
    """Owns discovery budgets, canonical sources, and durable reservations.

    Network queries are serialized across all guilds. A source is reserved
    before sending and its usage survives restarts, including uncertain sends.
    The owning asyncio loop must perform all calls, including observe().
    """

    def __init__(
        self,
        api: bot_api.BotAPI,
        settings: Settings,
        db_path: str | pathlib.Path | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.api = api
        self.settings = settings
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self._cooldown: dict[str, float] = {}
        self._paused: set[str] = set()
        self._verified_until: dict[str, float] = {}
        self._sources: dict[str, ReplySource] = {}
        self._inflight: set[str] = set()
        self._tasks: dict[str, asyncio.Task[object]] = {}
        self._seeds: dict[str, _Seed] = {}
        self._channel_turn: dict[str, int] = collections.defaultdict(int)
        self._conn: sqlite3.Connection | None = None
        if settings.enabled:
            self._conn = sqlite3.connect(db_path or _ROOT / "reply_sources.db")
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS seeds(
                    channel_id TEXT PRIMARY KEY, message_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS usage(
                    message_id TEXT PRIMARY KEY, uses INTEGER NOT NULL,
                    timestamp REAL NOT NULL, outcome TEXT NOT NULL);
            """)
            for channel_id, message_id in self._conn.execute(
                    "SELECT channel_id,message_id FROM seeds"):
                try:
                    info = qq_message_id.decode_message_id(message_id)
                    self._route(str(info.guild_id), channel_id)
                except ValueError:
                    continue
                self._seeds[channel_id] = _Seed(message_id, info.sequence)

    def _route(self,
               guild_id: str,
               channel_id: str | None = None) -> GuildSettings:
        if not self.settings.enabled:
            raise ValueError("消息来源实验尚未启用，请先修改配置并重启")
        for route in self.settings.guilds:
            if route.guild_id == guild_id:
                if channel_id is None or channel_id in route.source_channel_ids:
                    return route
        raise ValueError("来源 guild/channel 不在配置白名单内")

    def _target_route(self, channel_id: str) -> GuildSettings | None:
        return next((route for route in self.settings.guilds
                     if channel_id in route.target_channel_ids), None)

    async def _read(self, call: Callable[[], Awaitable[object]]) -> object:
        # Include channel-list queries and seed verification in the budget.
        interval = 60 / self.settings.discovery_requests_per_minute
        delay = interval - (time.monotonic() - self._last_request)
        if delay > 0:
            await self._sleep(delay)
        self._last_request = time.monotonic()
        return await asyncio.wait_for(call(), timeout=5)

    async def _verify_channels(self, route: GuildSettings) -> None:
        channels = await self._read(
            lambda: self.api.get_channels(guild_id=route.guild_id))
        if not isinstance(channels, list):
            raise ValueError("未能确认频道列表；停止本轮查询")
        actual = {
            str(item.get("id"))
            for item in channels
            if isinstance(item, dict) and
            str(item.get("guild_id")) == route.guild_id
        }
        expected = set(route.source_channel_ids) | set(route.target_channel_ids)
        if not expected <= actual:
            raise ValueError("来源或目标 channel 不属于配置的 guild")
        self._verified_until[route.guild_id] = time.monotonic() + 300

    def _remember(self,
                  message: object,
                  guild_id: str,
                  channel_id: str,
                  expected_sequence: int | None = None) -> ReplySource | None:
        if isinstance(message, dict) and isinstance(message.get("message"),
                                                    dict):
            message = message["message"]
        if not isinstance(message, dict):
            raise ValueError("QQ 未返回有效消息")
        message_id = message.get("id")
        if not isinstance(message_id, str):
            raise ValueError("QQ 未返回真实消息 ID")
        info = qq_message_id.decode_message_id(message_id)
        if expected_sequence is not None and info.sequence != expected_sequence:
            raise ValueError("查询返回了不同序号的消息")
        if (str(message.get("guild_id")) != guild_id or
                str(message.get("channel_id")) != channel_id or
                str(info.guild_id) != guild_id or
                str(info.channel_id) != channel_id):
            raise ValueError("返回消息的 guild/channel 不匹配")
        stamp = message.get("timestamp")
        try:
            if not isinstance(stamp, str):
                raise ValueError("Missing timestamp")
            parsed = datetime.datetime.fromisoformat(
                stamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("Timestamp requires timezone")
            timestamp = parsed.timestamp()
        except (ValueError, OverflowError) as error:
            raise ValueError("返回消息的真实时间无效") from error
        age = self._clock() - timestamp
        if age < 0:
            raise ValueError("返回消息的时间在未来")
        seed = self._seeds.get(channel_id)
        if seed is None or info.sequence > seed.sequence:
            self._seeds[channel_id] = _Seed(message_id, info.sequence)
            assert self._conn is not None
            with self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO seeds VALUES (?,?)",
                    (channel_id, message_id),
                )
        author = message.get("author")
        if (age > self.settings.max_source_age_seconds or
                not isinstance(author, dict) or author.get("bot") is not False):
            return None
        source = ReplySource(message_id, guild_id, channel_id, timestamp)
        self._sources[message_id] = source
        self._prune()
        return source

    def _prune(self) -> None:
        cutoff = self._clock() - self.settings.max_source_age_seconds
        self._sources = {
            key: value
            for key, value in self._sources.items()
            if value.timestamp > cutoff
        }
        # Bound memory even if the operator manually registers many fresh seeds.
        if len(self._sources) > 1000:
            newest = sorted(self._sources.values(),
                            key=lambda value: value.timestamp,
                            reverse=True)[:1000]
            self._sources = {source.message_id: source for source in newest}
        if self._conn:
            with self._conn:
                self._conn.execute("DELETE FROM usage WHERE timestamp<?",
                                   (cutoff,))

    def observe(self, message: Mapping[str, object]) -> None:
        """Accepts real gateway metadata without network reads."""
        if not self.settings.enabled:
            return
        guild_id, channel_id = str(message.get("guild_id")), str(
            message.get("channel_id"))
        try:
            self._route(guild_id, channel_id)
            self._remember(dict(message), guild_id, channel_id)
        except ValueError:
            # Future protocol variants must not break normal command handling.
            return

    async def register_seed(self, guild_id: str, channel_id: str,
                            message_id: str) -> dict[str, object]:
        """Verifies a manually supplied seed; never sends a QQ message.

        Raises:
            ValueError: The experiment, allowlist, ID, or response is invalid.
            RuntimeError: The authenticated QQ query fails.
        """
        route = self._route(guild_id, channel_id)
        info = qq_message_id.decode_message_id(message_id)
        if str(info.guild_id) != guild_id or str(info.channel_id) != channel_id:
            raise ValueError("种子 ID 与来源 guild/channel 不匹配")
        async with self._lock:
            await self._verify_channels(route)
            result = await self._read(lambda: self.api.get_message(
                channel_id=channel_id, message_id=message_id))
            self._remember(result, guild_id, channel_id, info.sequence)
            self._paused.discard(channel_id)
        return await self.status(guild_id)

    async def probe(self, guild_id: str) -> dict[str, object]:
        """Queries a bounded batch in one guild, without sending messages.

        Missing sequences rotate through a fixed horizon and are retried in
        later batches; a miss never permanently advances the confirmed seed.
        """
        route = self._route(guild_id)
        if not any(channel in self._seeds and channel not in self._paused
                   for channel in route.source_channel_ids):
            return {
                "state": "needs_seed",
                "queries": 0,
                "status": await self.status(guild_id)
            }
        if self._lock.locked() or time.monotonic() < self._cooldown.get(
                guild_id, 0):
            return {"state": "waiting", "queries": 0}
        queries = 0
        state = "complete"
        async with self._lock:
            self._cooldown[guild_id] = (
                time.monotonic() + self.settings.discovery_interval_seconds)
            try:
                await self._verify_channels(route)
                for _ in range(self.settings.max_probes_per_batch):
                    channels = [
                        channel for channel in route.source_channel_ids if
                        channel in self._seeds and channel not in self._paused
                    ]
                    if not channels:
                        state = "needs_seed"
                        break
                    index = self._channel_turn[guild_id] % len(channels)
                    self._channel_turn[guild_id] += 1
                    channel_id = channels[index]
                    seed = self._seeds[channel_id]
                    candidate = qq_message_id.generate_neighbor_message_id(
                        seed.message_id, seed.offset)
                    seed.offset = (
                        seed.offset % self.settings.max_sequence_distance + 1)
                    queries += 1
                    try:
                        result = await self._read(lambda: self.api.get_message(
                            channel_id=channel_id, message_id=candidate))
                        if result is None:
                            state = "query_failed"
                            break
                        requested = qq_message_id.decode_message_id(candidate)
                        self._remember(result, guild_id, channel_id,
                                       requested.sequence)
                    except bot_errors.NotFoundError:
                        continue
                    except (bot_errors.ForbiddenError,
                            bot_errors.AuthenticationFailedError):
                        self._paused.add(channel_id)
                        state = "permission_denied"
                        break
                    except bot_errors.SequenceNumberError:
                        self._cooldown[guild_id] = time.monotonic() + 60
                        state = "rate_limited"
                        break
                    except ValueError:
                        self._paused.add(channel_id)
                        state = "invalid_response"
                        break
                    except (RuntimeError, OSError, asyncio.TimeoutError):
                        state = "query_failed"
                        break
            except bot_errors.SequenceNumberError:
                self._cooldown[guild_id] = time.monotonic() + 60
                state = "rate_limited"
            except (bot_errors.ForbiddenError,
                    bot_errors.AuthenticationFailedError):
                self._paused.update(route.source_channel_ids)
                state = "permission_denied"
            except (ValueError, RuntimeError, OSError, asyncio.TimeoutError):
                state = "channel_verification_failed"
            finally:
                self._cooldown[guild_id] = max(
                    self._cooldown.get(guild_id, 0),
                    time.monotonic() + self.settings.discovery_interval_seconds,
                )
        return {
            "state": state,
            "queries": queries,
            "status": await self.status(guild_id)
        }

    async def acquire(self, target_channel_id: str) -> ReplySource | None:
        """Reserves a source without network waits, or triggers discovery."""
        if not self.settings.enabled:
            return None
        route = self._target_route(target_channel_id)
        if route is None:
            return None
        self._prune()
        assert self._conn is not None
        candidates = sorted(self._sources.values(),
                            key=lambda source: source.timestamp,
                            reverse=True)
        if time.monotonic() >= self._verified_until.get(route.guild_id, 0):
            candidates = []
        for source in candidates:
            if (source.guild_id != route.guild_id or
                    source.message_id in self._inflight):
                continue
            row = self._conn.execute(
                "SELECT uses,outcome FROM usage WHERE message_id=?",
                (source.message_id,)).fetchone()
            uses = row[0] if row else 0
            if (uses >= self.settings.max_uses_per_source or
                    row is not None and row[1] != "sent"):
                continue
            with self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO usage VALUES (?,?,?,?)",
                    (source.message_id, uses + 1, source.timestamp, "reserved"),
                )
            self._inflight.add(source.message_id)
            return source
        task = self._tasks.get(route.guild_id)
        if task is None or task.done():
            task = asyncio.create_task(self.probe(route.guild_id))
            task.add_done_callback(self._discovery_done)
            self._tasks[route.guild_id] = task
        return None

    def _discovery_done(self, task: asyncio.Task[object]) -> None:
        if not task.cancelled() and task.exception() is not None:
            # Retrieve exceptions without logging private SDK response bodies.
            _LOG.warning("Reply source discovery stopped unexpectedly")

    def finish(self, source: ReplySource, outcome: Literal["sent", "rejected",
                                                           "unknown"]) -> None:
        """Settles a reservation; unknown outcomes are never reused."""
        self._inflight.discard(source.message_id)
        assert self._conn is not None
        with self._conn:
            self._conn.execute(
                "UPDATE usage SET outcome=?,uses=CASE WHEN ?='sent' "
                "THEN uses ELSE ? END WHERE message_id=?",
                (outcome, outcome, self.settings.max_uses_per_source,
                 source.message_id),
            )
        if outcome != "sent":
            self._sources.pop(source.message_id, None)

    async def status(self, guild_id: str) -> dict[str, object]:
        """Returns metadata and budgets only; performs no QQ queries."""
        route = self._route(guild_id)
        self._prune()
        return {
            "guild_id":
                guild_id,
            "seeds": [{
                "channel_id": channel_id,
                "sequence": self._seeds[channel_id].sequence,
                "paused": channel_id in self._paused
            }
                      for channel_id in route.source_channel_ids
                      if channel_id in self._seeds],
            "sources": [
                self._source_status(source)
                for source in self._sources.values()
                if source.guild_id == guild_id
            ],
            "max_uses_per_source":
                self.settings.max_uses_per_source,
            "automatic_forwarding":
                self.settings.automatic_forwarding,
            "max_probes_per_batch":
                self.settings.max_probes_per_batch,
            "target_channel_ids":
                list(route.target_channel_ids),
            "channels_verified":
                time.monotonic() < self._verified_until.get(guild_id, 0),
            "next_probe_in_seconds":
                max(0,
                    self._cooldown.get(guild_id, 0) - time.monotonic()),
        }

    def _source_status(self, source: ReplySource) -> dict[str, object]:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT uses,outcome FROM usage WHERE message_id=?",
            (source.message_id,),
        ).fetchone()
        return {
            **dataclasses.asdict(source),
            "age_seconds":
                max(0,
                    self._clock() - source.timestamp),
            "uses":
                row[0] if row else 0,
            "outcome":
                row[1] if row else "available",
        }

    async def close(self) -> None:
        """Cancels discovery and closes storage, preserving spent uses."""
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        if self._conn is not None:
            self._conn.close()
            self._conn = None
