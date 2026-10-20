# Learnings

Living notes for the SNMP server project. Update this file when new source files, requirements, or implementation decisions add durable context.

## Current repository

- `agents.md` is the project brief. The agent should expose values under the project's own enterprise subtree, hide device-native OIDs, serve manager reads from a cache, and target up to 100 concurrent managers.
- The brief uses PEN `32473` as a placeholder. It also calls out unresolved choices: whether data is proxied or generated locally, the final PEN, and what to do when the session limit is reached.
- The repository includes the project brief, source `pdu.mib`, initial Python package, YAML config and OID map, custom MIB, and README.

## `pdu.mib` findings

- The module is named `PDU-MIB` and defines enterprise root `1.3.6.1.4.1.42578`, with branches `pdu1` through `pdu11`.
- It has 3,212 `OBJECT-TYPE` declarations: 2,805 read-only and 407 read-write. The MIB describes PDU information such as alarms, device name, electrical measurements, outlets, sensors, and I/O status.
- The definitions use older SMIv1-style syntax (`RFC1155-SMI`, `RFC-1212`, `ACCESS`, and `STATUS optional`). The MIB imports `TRAP-TYPE`, but a trap definition has not been found so far.
- Nearly all object descriptions are blank (`" "`), so names and syntax alone may not fully explain device-specific meanings or units.
- This is a source/device MIB under PEN `42578`; it is not the project's manager-facing custom MIB. Any future mapper should translate selected source values into the chosen custom subtree and must not expose this source subtree directly.
- The MIB's many read-write objects do not by themselves authorize writes in the new agent. Write support should be explicitly mapped and constrained by project requirements.

## Implementation reminders from the project brief

- Keep manager-visible OIDs inside `1.3.6.1.4.1.<project PEN>` and preserve lexicographic order for GetNext/GetBulk walks.
- Build an explicit custom-OID-to-source mapping; do not register every source MIB object automatically.
- Keep responders cache-backed and move blocking device I/O out of the async event loop.
- Verify the installed and pinned `pysnmp` API before implementing engine setup; the project brief notes that API names vary by version.

## Initial implementation decisions

- The repository now has a Python package under `src/snmp_agent/`, with Pydantic config validation, custom OID-map validation, an in-memory TTL cache, a background refresh loop, PySNMP responders, a sample custom MIB, and local-run documentation.
- The requested scope is now limited to `currentL1PDU1`, `voltageL1PDU1`, `powerL1PDU1`, `energyL1PDU1`, and `pfL1PDU1` from PDU 1 input 1. Their source OIDs are `1.3.6.1.4.1.42578.1.2.1.0` through `.5.0`; each is declared `INTEGER (0..65535)` in `pdu.mib`.
- Those values are exposed as custom read-only scalar OIDs `1.3.6.1.4.1.32473.3.1.0` through `.3.5.0`, respectively ordered current, voltage, power, energy, and power factor. The manager-facing MIB defines only those five objects.
- The async source poller now batches all five requests into one SNMPv2c GET every five seconds by default. Configure the device address and community with `PDU_HOST` and `PDU_COMMUNITY`; source SNMPv3 is not wired yet.
- PySNMP is constrained to major version 7 (`pysnmp>=7.1,<8`). The agent registers GET, GETNEXT, and GETBULK responders and applies VACM read views rooted at the configured PEN.
- The sample config binds to loopback and lists v2c and v3. Because no credentials are committed, running that exact config requires v3 username/auth/privacy environment variables; v3 uses SHA and AES. For a v2c-only local run, remove `v3` from `snmp_versions`.
- SET is not registered, and read-write map entries are rejected until write semantics and access controls are implemented.
- The MIB contains only currently mapped custom objects. Self-stats are not advertised until their live counters and mappings exist.
- The implementation has not been executed or tested yet. Session limiting, self-stats, source-device availability, and MIB compilation remain to be checked or implemented.

## Pending validation

- The source and custom MIB files have not yet been compiled or checked against a device implementation.
- Confirm the source device's scalar instance behavior, measurement units/scaling, and power-factor encoding; the source descriptions are blank.
- Confirm the final PEN and session-limit behavior before production configuration. Data is now intended to be proxied from the PDU using the five selected source OIDs.
