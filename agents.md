# agent.md: Custom-PEN SNMP Agent (Python)

Guidance for AI coding agents and contributors working on this project. Read this fully before changing code.

## 1. Project goal

Build an **SNMP agent** in Python that:

- Exposes data **only under our own IANA Private Enterprise Number (PEN)** subtree: `1.3.6.1.4.1.<PEN>`.
- **Never exposes the device's native OIDs** to managers. Values are translated from device OIDs / data sources into our custom OIDs.
- Supports **up to 100 concurrent managers/sessions**, regardless of SNMP version (v1/v2c/v3) or transport (UDP v4/v6; others if added later).
- Serves reads from a **cache**, so manager count does not multiply load on real devices.

### Key terms

| Term | Meaning here |
|---|---|
| PEN | IANA Private Enterprise Number. Use `32473` (RFC 5612 documentation PEN) until our own is assigned. |
| Custom OID | An OID under `1.3.6.1.4.1.<PEN>` that managers query. |
| Source OID | The real device OID or data source the value comes from. Never shown to managers. |
| Connection | A concurrent manager session. SNMP/UDP is connectionless, so this is enforced in application logic. |

## 2. Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.10+ |
| SNMP engine | `pysnmp` (maintained fork; verify API names against the installed version) |
| MIB compile | `pysmi` (`mibdump`) |
| Concurrency | `asyncio` |
| Config / validation | `pyyaml` + `pydantic` |
| Tests | `pytest`, `pytest-asyncio`; net-snmp CLI (`snmpget`, `snmpwalk`, `snmpbulkwalk`) for integration |
| Lint / format | `ruff`, `black`, `mypy` |

```bash
pip install pysnmp pysmi pyyaml pydantic pytest pytest-asyncio ruff black mypy
```

## 3. Architecture

```
Manager(s) -> SNMP Agent (pysnmp, UDP, v1/v2c/v3)
                 |  VACM: only 1.3.6.1.4.1.<PEN> visible
                 v
          Connection limiter (max 100)
                 v
          OID Mapper: custom OID <-> source OID / data source
                 v
          Cache (TTL) <- Background poller (async)
```

## 4. Repository layout

```
snmp-agent/
├── agent.md
├── pyproject.toml
├── config/
│   ├── agent.yaml          # bind addr, port, PEN, limits, v3 users
│   └── oid_map.yaml        # custom OID -> source mapping
├── mibs/
│   └── CUSTOM-MIB.txt      # SMIv2 definition under our PEN
├── src/snmp_agent/
│   ├── __main__.py         # entrypoint
│   ├── config.py           # pydantic models + YAML loading
│   ├── engine.py           # pysnmp engine, transports, VACM, responders
│   ├── limiter.py          # 100-session limiter
│   ├── mapper.py           # OID translation layer
│   ├── cache.py            # TTL cache
│   ├── poller.py           # background device polling
│   └── mib_instances.py    # MibScalar/MibScalarInstance registration
└── tests/
    ├── unit/
    └── integration/
```

## 5. OID design

Root: `1.3.6.1.4.1.<PEN>`

| Subtree | Purpose |
|---|---|
| `<PEN>.1` | System info (name, uptime, version) |
| `<PEN>.2` | Interfaces table |
| `<PEN>.3` | Sensors / metrics |
| `<PEN>.99` | Agent self-stats (active sessions, rejected count, cache age) |

Rules:

- Every object must be defined in `mibs/CUSTOM-MIB.txt` **and** appear in `config/oid_map.yaml`.
- OIDs must be **strictly ordered lexicographically**, or GetNext / walks will break.
- Scalars end in `.0`. Tables use proper index columns.
- Never reuse or renumber a published OID; deprecate instead.

### Mapping format (`config/oid_map.yaml`)

```yaml
- custom_oid: 1.3.6.1.4.1.32473.1.1.0
  name: customSysName
  source: snmp                  # snmp | static | callable
  source_oid: 1.3.6.1.2.1.1.5.0
  type: OctetString             # OctetString | Integer32 | Counter32 | Gauge32 | TimeTicks | ...
  ttl_seconds: 30
  access: read-only
```

## 6. Behavior requirements

1. **Visibility:** VACM must restrict all users/communities to the custom subtree. A walk of `1.3.6.1` must return nothing outside `1.3.6.1.4.1.<PEN>`.
2. **Operations:** Get, GetNext, GetBulk required. Set only if explicitly added to the mapping (`access: read-write`).
3. **Session limit:** max **100** concurrent sessions (configurable). Track per source (address + port + version/user). Over the limit, return `genErr`/`resourceUnavailable` or drop, per config. Always release slots on completion or error.
4. **Caching:** responders read from cache only. A background poller refreshes entries by TTL. A stale value is served with a log warning; a missing value returns `noSuchInstance`.
5. **Versions:** v2c and v3 enabled by default; v1 off unless configured. v3 uses authPriv (SHA + AES) in production.
6. **Binding:** bind to configured interfaces only. Default dev port `1161`; production `161` via `CAP_NET_BIND_SERVICE` rather than root.
7. **Self-stats:** expose active sessions, total rejected, and cache hit rate under `<PEN>.99`.

## 7. Coding conventions

- Fully `async`; never block the event loop. Wrap blocking I/O in `run_in_executor`.
- Type hints on all public functions; `mypy --strict` clean for `src/`.
- Config is validated at startup by pydantic. Fail fast with a clear error.
- No secrets in the repo. v3 passwords and community strings come from env vars or a secrets file excluded from git.
- Log with the `logging` module (JSON in production). Never log auth/priv passphrases.
- Keep functions small; one responsibility per module as laid out above.
- pysnmp API names differ between versions. Check the installed version's docs before assuming a method name, and pin the version in `pyproject.toml`.

## 8. Commands

```bash
# run (dev)
python -m snmp_agent --config config/agent.yaml

# compile MIB
mibdump --destination-directory=compiled mibs/CUSTOM-MIB.txt

# lint / type / test
ruff check src tests && black --check src tests && mypy src
pytest -q
```

### Manual verification

```bash
# v2c
snmpget  -v2c -c public localhost:1161 1.3.6.1.4.1.32473.1.1.0
snmpwalk -v2c -c public localhost:1161 1.3.6.1.4.1.32473

# v3
snmpwalk -v3 -l authPriv -u monitor -a SHA -A authpass123 \
         -x AES -X privpass123 localhost:1161 1.3.6.1.4.1.32473

# must return nothing (isolation check)
snmpwalk -v2c -c public localhost:1161 1.3.6.1.2.1
```

## 9. Testing requirements

**Unit**
- Mapper returns the correct source for each custom OID; unknown OID raises cleanly.
- Cache TTL expiry and stale handling.
- Limiter: acquire/release, rejection at 101st session, release on exception.

**Integration**
- Get / GetNext / GetBulk / walk under the custom root return correct ordered results.
- Isolation: no native OIDs reachable.
- v2c and v3 both work; wrong credentials are rejected.

**Load**
- 100 parallel `snmpwalk` sessions complete without errors; the 101st is rejected per config.
- Device poll count stays flat as manager count rises (proves the cache works).

## 10. Milestones

1. **M1: Skeleton.** Config loading, engine on UDP 1161, one static scalar served via v2c.
2. **M2: MIB + mapper.** Compile the MIB, load `oid_map.yaml`, register all scalars.
3. **M3: Poller + cache.** Background refresh from real device or data source.
4. **M4: VACM + v3.** Subtree isolation, authPriv users.
5. **M5: Limiter + self-stats.** 100-session enforcement and `<PEN>.99` metrics.
6. **M6: Tables + GetBulk.** Interface and sensor tables.
7. **M7: Hardening + packaging.** Load test, Dockerfile / systemd unit, docs.

## 11. Definition of done

- [ ] All objects defined in MIB and mapping, and correctly ordered
- [ ] Isolation check returns nothing outside the custom subtree
- [ ] 100-session load test passes; session 101 handled per config
- [ ] v3 authPriv works; v1 disabled by default
- [ ] Lint, type check, and tests all green
- [ ] No secrets in repo or logs
- [ ] README covers install, config, run, and test

## 12. Out of scope (for now)

- SNMP over TCP/TLS/SSH (RFC 6353). pysnmp is effectively UDP-only; revisit if required.
- SNMP traps/informs (add later as a separate module).
- A web UI.

## 13. Open questions

- Is data **proxied from real devices** or **generated locally**? This determines whether the poller targets devices or internal sources.
- Final PEN number: still using `32473` placeholder?
- Behavior at session limit: **drop** or **return error**?

## 14. Alternative approach

If hand-rolling the agent proves heavy, run net-snmp `snmpd` with **AgentX** and implement a Python sub-agent (`python-agentx`) that serves only the custom subtree. The mapper, cache, and poller modules stay the same.