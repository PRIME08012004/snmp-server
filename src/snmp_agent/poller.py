"""Background refresh of mapped data sources."""

from __future__ import annotations

import asyncio
import logging

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
)

from snmp_agent.cache import ValueCache
from snmp_agent.config import AgentConfig, MappingEntry

logger = logging.getLogger(__name__)


class Poller:
    """Refresh mapped values from static config or a source SNMP agent."""

    def __init__(
        self, entries: list[MappingEntry], cache: ValueCache, settings: AgentConfig
    ) -> None:
        self._entries = entries
        self._cache = cache
        self._settings = settings
        self._snmp_entries = [entry for entry in entries if entry.source == "snmp"]

    async def run(self) -> None:
        snmp_engine = SnmpEngine()
        target = await UdpTransportTarget.create(
            (self._settings.device_host, self._settings.device_port),
            timeout=self._settings.device_timeout_seconds,
            retries=self._settings.device_retries,
        )
        try:
            while True:
                for entry in self._entries:
                    if entry.source == "static":
                        assert entry.value is not None
                        self._cache.put(entry.custom_oid, entry.value, entry.ttl_seconds)
                if self._snmp_entries:
                    await self._refresh_snmp(snmp_engine, target)
                await asyncio.sleep(self._settings.poll_interval_seconds)
        finally:
            snmp_engine.close_dispatcher()

    async def _refresh_snmp(self, snmp_engine: SnmpEngine, target: UdpTransportTarget) -> None:
        requested = [
            entry for entry in self._snmp_entries if entry.source_oid is not None
        ]
        var_binds = [ObjectType(ObjectIdentity(entry.source_oid)) for entry in requested]
        try:
            error_indication, error_status, error_index, response = await get_cmd(
                snmp_engine,
                CommunityData(self._settings.device_community, mpModel=1),
                target,
                ContextData(),
                *var_binds,
                lookupMib=False,
            )
        except Exception:
            logger.exception("SNMP poll to source device %s failed", self._settings.device_host)
            return
        if error_indication or error_status:
            logger.warning(
                "SNMP poll failed for source device %s: indication=%s status=%s index=%s",
                self._settings.device_host,
                error_indication,
                error_status,
                error_index,
            )
            return
        for entry, (_, value) in zip(requested, response, strict=False):
            try:
                numeric_value = int(value)
            except (TypeError, ValueError):
                logger.warning("Source OID %s returned a non-integer value", entry.source_oid)
                continue
            if not 0 <= numeric_value <= 65535:
                logger.warning("Source OID %s returned out-of-range value %s", entry.source_oid, numeric_value)
                continue
            self._cache.put(entry.custom_oid, numeric_value, entry.ttl_seconds)
