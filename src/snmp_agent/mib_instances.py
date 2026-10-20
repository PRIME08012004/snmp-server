"""PySNMP scalar instances backed by the shared in-memory cache."""

from __future__ import annotations

import logging
from typing import Any

from pysnmp.proto import rfc1902
from pysnmp.smi import exval

from snmp_agent.cache import ValueCache
from snmp_agent.config import MappingEntry

logger = logging.getLogger(__name__)


def asn1_value(entry: MappingEntry, value: str | int) -> Any:
    value_class = getattr(rfc1902, entry.type)
    return value_class(value)


def register_mapped_scalars(mib_builder: Any, entries: list[MappingEntry], cache: ValueCache) -> None:
    from pysnmp.proto.api import v2c

    mib_scalar, mib_scalar_instance = mib_builder.import_symbols(
        "SNMPv2-SMI", "MibScalar", "MibScalarInstance"
    )

    class CachedScalarInstance(mib_scalar_instance):  # type: ignore[misc, valid-type]
        def __init__(self, entry: MappingEntry) -> None:
            oid = tuple(int(part) for part in entry.custom_oid.split("."))
            if entry.value is not None:
                initial: str | int = entry.value
            else:
                initial = "" if entry.type == "OctetString" else 0
            super().__init__(oid[:-1], (oid[-1],), asn1_value(entry, initial))
            self.entry = entry

        def getValue(self, name: Any, **context: Any) -> Any:  # noqa: N802
            record = cache.read(self.entry.custom_oid)
            if record is None:
                return exval.noSuchInstance
            if record.stale:
                logger.warning("Serving stale cached value for %s", self.entry.name)
            return asn1_value(self.entry, record.value)

    symbols: dict[str, Any] = {}
    for index, entry in enumerate(entries):
        oid = tuple(int(part) for part in entry.custom_oid.split("."))
        base_oid = oid[:-1]
        initial = entry.value if entry.value is not None else ("" if entry.type == "OctetString" else 0)
        syntax = asn1_value(entry, initial)
        symbols[f"{entry.name}Object"] = mib_scalar(base_oid, syntax).setMaxAccess("readonly")
        symbols[f"{entry.name}Instance"] = CachedScalarInstance(entry)
    mib_builder.export_symbols("CUSTOM-MIB", **symbols)
