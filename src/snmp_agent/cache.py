"""Small in-memory TTL cache shared by the poller and SNMP responders."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TypeAlias

CacheValue: TypeAlias = str | int


@dataclass(frozen=True)
class CacheRecord:
    value: CacheValue
    updated_at: float
    ttl_seconds: float

    @property
    def stale(self) -> bool:
        return time.monotonic() - self.updated_at > self.ttl_seconds


class ValueCache:
    def __init__(self) -> None:
        self._records: dict[str, CacheRecord] = {}
        self.hits = 0
        self.misses = 0

    def put(self, oid: str, value: CacheValue, ttl_seconds: float) -> None:
        self._records[oid] = CacheRecord(value, time.monotonic(), ttl_seconds)

    def read(self, oid: str) -> CacheRecord | None:
        record = self._records.get(oid)
        if record is None:
            self.misses += 1
            return None
        self.hits += 1
        return record

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0
