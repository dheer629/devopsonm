"""Short-TTL cache with in-flight de-duplication (spec section 62)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ..config import settings


@dataclass
class _Entry:
    value: Any
    stored_at: float


class TTLCache:
    def __init__(self, ttl_s: float | None = None, max_entries: int = 256) -> None:
        self.ttl_s = ttl_s or settings.cache_ttl_s
        self.max_entries = max_entries
        self._data: dict[str, _Entry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.hits = 0
        self.misses = 0

    def _evict(self) -> None:
        if len(self._data) <= self.max_entries:
            return
        oldest = sorted(self._data.items(), key=lambda kv: kv[1].stored_at)
        for key, _ in oldest[: len(self._data) - self.max_entries]:
            self._data.pop(key, None)

    def get(self, key: str) -> tuple[Any, int] | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        age = time.monotonic() - entry.stored_at
        if age > self.ttl_s:
            self._data.pop(key, None)
            return None
        return entry.value, int(age * 1000)

    async def get_or_set(
        self, key: str, factory: Callable[[], Awaitable[Any]]
    ) -> tuple[Any, int, bool]:
        """Return (value, cache_age_ms, from_cache) with single-flight fill."""
        cached = self.get(key)
        if cached is not None:
            self.hits += 1
            value, age = cached
            return value, age, True
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self.get(key)
            if cached is not None:
                self.hits += 1
                value, age = cached
                return value, age, True
            self.misses += 1
            value = await factory()
            self._data[key] = _Entry(value=value, stored_at=time.monotonic())
            self._evict()
            return value, 0, False

    def invalidate(self, prefix: str = "") -> None:
        if not prefix:
            self._data.clear()
            return
        for key in [k for k in self._data if k.startswith(prefix)]:
            self._data.pop(key, None)

    def stats(self) -> dict[str, int]:
        return {"entries": len(self._data), "hits": self.hits, "misses": self.misses}


cache = TTLCache()
