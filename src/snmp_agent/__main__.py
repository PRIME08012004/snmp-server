"""Command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from snmp_agent.cache import ValueCache
from snmp_agent.config import load_config, load_oid_map
from snmp_agent.engine import create_engine
from snmp_agent.poller import Poller


async def serve(config_path: Path, map_path: Path) -> None:
    settings = load_config(config_path)
    entries = load_oid_map(map_path, settings.pen)
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cache = ValueCache()
    poller = Poller(entries, cache, settings)
    poller_task = asyncio.create_task(poller.run(), name="snmp-data-poller")
    snmp_engine = create_engine(settings, entries, cache)
    snmp_engine.transport_dispatcher.job_started(1)
    try:
        await asyncio.Future()
    finally:
        poller_task.cancel()
        snmp_engine.close_dispatcher()


def main() -> None:
    parser = argparse.ArgumentParser(description="Custom-PEN SNMP agent")
    parser.add_argument("--config", type=Path, default=Path("config/agent.yaml"))
    parser.add_argument("--oid-map", type=Path, default=Path("config/oid_map.yaml"))
    args = parser.parse_args()
    try:
        asyncio.run(serve(args.config, args.oid_map))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
