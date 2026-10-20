"""Configuration models and YAML loading."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

ValueType = Literal[
    "OctetString",
    "Integer32",
    "Counter32",
    "Counter64",
    "Gauge32",
    "TimeTicks",
]
SourceType = Literal["static", "snmp", "callable"]

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expand_env(value: object) -> object:
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda match: os.environ.get(match.group(1), match.group(2) or ""), value
        )
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


class AgentConfig(BaseModel):
    bind_address: str = "127.0.0.1"
    port: int = Field(default=1161, ge=1, le=65535)
    pen: int = Field(default=32473, ge=1, le=4_294_967_295)
    max_sessions: int = Field(default=100, ge=1, le=100)
    snmp_versions: list[Literal["v1", "v2c", "v3"]] = ["v2c"]
    community: str = "public"
    v3_user: str = ""
    v3_auth_password: str = ""
    v3_priv_password: str = ""
    log_level: str = "INFO"
    device_host: str = "127.0.0.1"
    device_port: int = Field(default=161, ge=1, le=65535)
    device_community: str = "public"
    poll_interval_seconds: float = Field(default=5, gt=0)
    device_timeout_seconds: float = Field(default=2, gt=0)
    device_retries: int = Field(default=1, ge=0, le=10)

    @model_validator(mode="after")
    def validate_security(self) -> AgentConfig:
        if "v1" in self.snmp_versions:
            raise ValueError("SNMPv1 is disabled; remove it from snmp_versions")
        if "v3" in self.snmp_versions:
            if not (self.v3_user and self.v3_auth_password and self.v3_priv_password):
                raise ValueError(
                    "SNMPv3 requires SNMP_V3_USER, SNMP_V3_AUTH_PASSWORD, "
                    "and SNMP_V3_PRIV_PASSWORD"
                )
            if len(self.v3_auth_password) < 8 or len(self.v3_priv_password) < 8:
                raise ValueError("SNMPv3 auth and privacy passwords must be at least 8 characters")
        if not self.community:
            raise ValueError("SNMP community must not be empty")
        if not self.device_host:
            raise ValueError("PDU_HOST must be set to the source device address")
        if not self.device_community:
            raise ValueError("PDU_COMMUNITY must not be empty")
        return self


class MappingEntry(BaseModel):
    custom_oid: str
    name: str
    source: SourceType
    source_oid: str | None = None
    value: str | int | None = None
    type: ValueType
    ttl_seconds: float = Field(default=30, gt=0)
    access: Literal["read-only", "read-write"] = "read-only"

    @field_validator("custom_oid", "source_oid")
    @classmethod
    def validate_oid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            parts = tuple(int(part) for part in value.strip(".").split("."))
        except ValueError as exc:
            raise ValueError(f"Invalid OID: {value}") from exc
        if len(parts) < 2 or any(part < 0 for part in parts):
            raise ValueError(f"Invalid OID: {value}")
        return ".".join(str(part) for part in parts)

    @model_validator(mode="after")
    def validate_source(self) -> MappingEntry:
        if self.source == "static" and self.value is None:
            raise ValueError(f"Static mapping {self.name} requires a value")
        if self.source == "snmp" and self.source_oid is None:
            raise ValueError(f"SNMP mapping {self.name} requires source_oid")
        if self.source == "callable":
            raise ValueError("Callable mappings are not available until a safe plugin API exists")
        if self.type == "OctetString" and self.value is not None and not isinstance(self.value, str):
            raise ValueError(f"OctetString mapping {self.name} requires a string value")
        if self.type != "OctetString" and self.value is not None and not isinstance(self.value, int):
            raise ValueError(f"Numeric mapping {self.name} requires an integer value")
        if self.type == "Integer32" and self.value is not None and not 0 <= self.value <= 65535:
            raise ValueError(f"Integer32 mapping {self.name} value is outside the PDU MIB range")
        if self.access != "read-only":
            raise ValueError("SET is not implemented; mappings must be read-only")
        return self


def load_config(path: Path) -> AgentConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Agent config must be a YAML mapping: {path}")
    return AgentConfig.model_validate(_expand_env(raw))


def load_oid_map(path: Path, pen: int) -> list[MappingEntry]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        raise ValueError(f"OID map must be a YAML list: {path}")
    entries = [MappingEntry.model_validate(_expand_env(item)) for item in raw]
    if not entries:
        raise ValueError("OID map must define at least one custom object")
    root = (1, 3, 6, 1, 4, 1, pen)
    seen: set[tuple[int, ...]] = set()
    for entry in entries:
        oid = tuple(int(part) for part in entry.custom_oid.split("."))
        if oid[: len(root)] != root:
            raise ValueError(f"{entry.name} is outside configured PEN subtree {'.'.join(map(str, root))}")
        if len(oid) < len(root) + 2 or oid[-1] != 0:
            raise ValueError(f"Scalar OID {entry.custom_oid} must end in .0")
        if oid in seen:
            raise ValueError(f"Duplicate custom OID: {entry.custom_oid}")
        seen.add(oid)
    return sorted(entries, key=lambda entry: tuple(int(part) for part in entry.custom_oid.split(".")))
