import asyncio
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Literal


_log = logging.getLogger(__name__)
_CACHE_SCHEMA_VERSION = 1
_SAFE_KEY = re.compile(r"^[a-zA-Z0-9_-]+$")
_locks: dict[tuple[str, str], asyncio.Lock] = {}


@dataclass(frozen=True)
class CachedRevenueRank:
    data: dict
    cached_at: datetime


@dataclass(frozen=True)
class RevenueRankFetchResult:
    data: dict | None
    source: Literal["remote", "cache", "unavailable"]
    cached_at: datetime | None = None


class RevenueRankCache:
    def __init__(self, root: Path | str = "data/cache/revenue_rank"):
        self.root = Path(root)

    def path_for(self, month: str, category: str) -> Path:
        if not _SAFE_KEY.fullmatch(month) or not _SAFE_KEY.fullmatch(category):
            raise ValueError("缓存键包含非法字符")
        return self.root / f"{month}_{category}.json"

    def load(self, month: str, category: str) -> CachedRevenueRank | None:
        path = self.path_for(month, category)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if not self._is_valid_document(document, month, category):
                raise ValueError("缓存内容与请求不匹配")
            return CachedRevenueRank(
                data=document["data"],
                cached_at=datetime.fromisoformat(document["cached_at"]),
            )
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            _log.warning("Ignoring invalid revenue rank cache %s: %s", path, error)
            return None

    def save(
        self,
        month: str,
        category: str,
        data: dict,
        *,
        cached_at: datetime | None = None,
    ) -> None:
        if not _is_valid_payload(data):
            raise ValueError("营收排行响应结构无效")

        path = self.path_for(month, category)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": _CACHE_SCHEMA_VERSION,
            "month": month,
            "category": category,
            "cached_at": (cached_at or datetime.now()).isoformat(timespec="seconds"),
            "data": data,
        }

        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.stem}_",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                json.dump(document, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass

    @staticmethod
    def _is_valid_document(document: object, month: str, category: str) -> bool:
        if not isinstance(document, dict):
            return False
        try:
            datetime.fromisoformat(document["cached_at"])
        except (KeyError, TypeError, ValueError):
            return False
        return (
            document.get("schema_version") == _CACHE_SCHEMA_VERSION
            and document.get("month") == month
            and document.get("category") == category
            and _is_valid_payload(document.get("data"))
        )


def _is_valid_payload(data: object) -> bool:
    return (
        isinstance(data, dict)
        and isinstance(data.get("anchors"), list)
    )


async def fetch_revenue_rank_cached(
    month: str,
    category: str,
    *,
    fetch_remote: Callable[[str, str], Awaitable[dict | None]],
    cache: RevenueRankCache,
    now: datetime | None = None,
    retry_attempts: int = 3,
    retry_delay: float = 1,
) -> RevenueRankFetchResult:
    now = now or datetime.now()
    is_current_month = month == now.strftime("%Y%m")
    lock = _locks.setdefault((month, category), asyncio.Lock())

    async with lock:
        for attempt in range(retry_attempts):
            try:
                data = await fetch_remote(month, category)
            except Exception as error:
                _log.warning(
                    "Revenue rank request failed for %s/%s: %s",
                    month,
                    category,
                    error,
                )
                data = None
            if _is_valid_payload(data):
                if not is_current_month:
                    try:
                        cache.save(month, category, data, cached_at=now)
                    except (OSError, ValueError) as error:
                        _log.warning(
                            "Failed to save revenue rank cache for %s/%s: %s",
                            month,
                            category,
                            error,
                        )
                return RevenueRankFetchResult(data=data, source="remote")
            if attempt + 1 < retry_attempts and retry_delay > 0:
                await asyncio.sleep(retry_delay)

        if not is_current_month:
            cached = cache.load(month, category)
            if cached is not None:
                return RevenueRankFetchResult(
                    data=cached.data,
                    source="cache",
                    cached_at=cached.cached_at,
                )

        return RevenueRankFetchResult(data=None, source="unavailable")
