"""Bounded group-scoped display-name cache with optional member API lookup."""

import asyncio
import collections
import dataclasses
import logging
import time

from botpy import api as botpy_api
from botpy import message as botpy_message

from botpy_ext import group_members
from database.repositories import group_repository

_LOG = logging.getLogger(__name__)


def event_name(message: botpy_message.GroupMessage) -> str:
    """Returns a display name without treating OpenIDs as names."""
    name = getattr(message.author, "username", "")
    return name.strip() if isinstance(name, str) else ""


@dataclasses.dataclass(frozen=True)
class CachedName:
    """Cache entry; an empty name also suppresses repeated failing lookups."""

    name: str
    expires: float


class GroupNameResolver:
    """Shares names across commands, while keeping group identities separate."""

    def __init__(
        self,
        api: botpy_api.BotAPI,
        repository: group_repository.GroupRepository,
    ) -> None:
        self._api = api
        self._repository = repository
        self._cache: collections.OrderedDict[tuple[str, str], CachedName] = (
            collections.OrderedDict()
        )
        self._lock = asyncio.Lock()
        self._blocked_until = 0.0
        self._next_request = 0.0

    def _remember(self, key: tuple[str, str], name: str, ttl: float) -> None:
        self._cache[key] = CachedName(name, time.monotonic() + ttl)
        self._cache.move_to_end(key)
        while len(self._cache) > 2048:
            self._cache.popitem(last=False)

    async def resolve(self, message: botpy_message.GroupMessage) -> str:
        """Prefers event names, then cache, then a bounded optional lookup."""
        name = event_name(message)
        group_id, member_id = message.group_openid, message.author.member_openid
        if (
            not isinstance(group_id, str)
            or not group_id
            or not isinstance(member_id, str)
            or not member_id
        ):
            return name
        key = (group_id, member_id)
        if name:
            self._remember(key, name, 600)
            return name
        async with self._lock:
            # A newer named event may arrive while a previous lookup awaits.
            name = event_name(message)
            cached = self._cache.get(key)
            if name:
                self._remember(key, name, 600)
                return name
            if cached and cached.expires > time.monotonic():
                name = cached.name
            else:
                name = (
                    cached.name
                    if cached
                    else self._repository.get_display_name(*key)
                )
                now = time.monotonic()
                if now >= self._blocked_until and now >= self._next_request:
                    # 30 QPM documented limit; no bursts across different users.
                    self._next_request = now + 2.1
                    result = await group_members.fetch_member_name(
                        self._api, *key
                    )
                    newer = self._cache.get(key)
                    if newer is not None and newer is not cached:
                        name = newer.name
                    elif result.name:
                        name = result.name
                    if result.permission_denied:
                        self._blocked_until = time.monotonic() + 3600
                        _LOG.info("群成员昵称接口无权限，暂停查询一小时")
                    if newer is cached:
                        self._remember(key, name, 600 if result.name else 60)
                elif now >= self._blocked_until:
                    self._remember(key, name, 3)
            if name:
                setattr(message.author, "username", name)
            return name
