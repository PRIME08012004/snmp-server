"""PySNMP engine and custom-subtree access control."""

from __future__ import annotations

from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config, engine
from pysnmp.entity.rfc3413 import cmdrsp, context

from snmp_agent.cache import ValueCache
from snmp_agent.config import AgentConfig, MappingEntry
from snmp_agent.mib_instances import register_mapped_scalars


def create_engine(
    settings: AgentConfig, entries: list[MappingEntry], cache: ValueCache
) -> engine.SnmpEngine:
    snmp_engine = engine.SnmpEngine()
    config.add_transport(
        snmp_engine,
        udp.DOMAIN_NAME,
        udp.UdpTransport().open_server_mode((settings.bind_address, settings.port)),
    )

    subtree = (1, 3, 6, 1, 4, 1, settings.pen)
    if "v2c" in settings.snmp_versions:
        config.add_v1_system(snmp_engine, "agent-community", settings.community)
        config.add_vacm_user(snmp_engine, 2, "agent-community", "noAuthNoPriv", subtree, subtree)
    if "v3" in settings.snmp_versions:
        config.add_v3_user(
            snmp_engine,
            settings.v3_user,
            config.USM_AUTH_HMAC96_SHA,
            settings.v3_auth_password,
            config.USM_PRIV_CFB128_AES,
            settings.v3_priv_password,
        )
        config.add_vacm_user(
            snmp_engine, 3, settings.v3_user, "authPriv", subtree, subtree
        )

    snmp_context = context.SnmpContext(snmp_engine)
    register_mapped_scalars(snmp_context.get_mib_instrum().get_mib_builder(), entries, cache)
    cmdrsp.GetCommandResponder(snmp_engine, snmp_context)
    cmdrsp.NextCommandResponder(snmp_engine, snmp_context)
    cmdrsp.BulkCommandResponder(snmp_engine, snmp_context)
    return snmp_engine
