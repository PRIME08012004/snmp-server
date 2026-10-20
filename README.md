# Custom-PEN SNMP Agent

An asyncio-based SNMP agent scaffold that serves mapped values under a custom enterprise subtree. Device-native OIDs are source identifiers only and are never registered as manager-visible objects.

## Current milestone

The agent polls five PDU 1 input 1 measurements from the source device every five seconds and serves them from cache under the custom PEN. It listens over SNMPv2c on `127.0.0.1:1161` by default. SNMPv3 setup is supported when credentials are supplied through environment variables.

Read-write operations, live session limiting, and self-stat values are not implemented. Only the five selected PDU measurements are mapped; the source PDU MIB is not loaded into the manager-visible MIB tree.

## Install and run

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m snmp_agent --config config/agent.yaml --oid-map config/oid_map.yaml
```

The development configuration binds to localhost and uses the `public` v2c community. Override `SNMP_COMMUNITY` before exposing the agent beyond localhost. Enable the configured v3 user by setting all three variables; v3 uses SHA authentication and AES privacy:

```bash
export SNMP_V3_USER=monitor
export SNMP_V3_AUTH_PASSWORD='replace-with-a-secret-at-least-8-chars'
export SNMP_V3_PRIV_PASSWORD='replace-with-another-secret'
```

SNMPv3 is enabled in the sample config, so these variables are required to start with that config. To run only v2c for local development, remove `v3` from `snmp_versions`.

Set the source PDU's address and read community for polling:

```bash
export PDU_HOST=192.0.2.10
export PDU_COMMUNITY='your-device-read-community'
```

The sample uses source SNMPv2c. Poll interval, timeout, retries, and port are configurable in `config/agent.yaml`.

## Exposed measurements

```bash
snmpget -v2c -c public localhost:1161 1.3.6.1.4.1.32473.3.1.0
snmpwalk -v2c -c public localhost:1161 1.3.6.1.4.1.32473
```

The custom OIDs `.3.1.0` through `.3.5.0` return current, voltage, power, energy, and power factor respectively. They map to source OIDs `1.3.6.1.4.1.42578.1.2.1.0` through `.5.0` (energy is `.5.0`; power factor is `.4.0`).

VACM limits v2c and v3 access to the configured PEN subtree. Set is not registered, and mappings currently reject `read-write` access.

## Configuration

- `config/agent.yaml`: bind address, port, PEN, SNMP credentials, source PDU target, poll interval, and session-limit target.
- `config/oid_map.yaml`: manager-visible OID to source mapping. Scalar OIDs must end in `.0` and stay under the configured PEN.
- `mibs/CUSTOM-MIB.txt`: initial manager-facing MIB definitions.
- `pdu.mib`: source device MIB under enterprise `42578`; use it to choose source OIDs after confirming device semantics and units.

The `32473` PEN is the documentation placeholder from `agents.md`; replace it with an assigned PEN before production.
