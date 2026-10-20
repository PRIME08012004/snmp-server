"""Validated custom-to-source OID mapping."""

from __future__ import annotations

from snmp_agent.config import MappingEntry


class OidMapper:
    def __init__(self, entries: list[MappingEntry]) -> None:
        self._by_oid = {entry.custom_oid: entry for entry in entries}

    def get(self, custom_oid: str) -> MappingEntry | None:
        return self._by_oid.get(custom_oid)

    def ordered(self) -> list[MappingEntry]:
        return sorted(self._by_oid.values(), key=lambda entry: tuple(map(int, entry.custom_oid.split("."))))
