"""Print everything the inverter reports.

Usage: python examples/status.py 192.168.31.17
"""

import asyncio
from dataclasses import asdict
import json
import sys

from intelbras_solar_local import IntelbrasSolarClient


async def main(host: str) -> None:
    async with IntelbrasSolarClient(host) as client:
        status = await client.async_get_status()
    data = asdict(status) | {
        "model": status.model,
        "work_state": status.work_state,
        "producing": status.producing,
        "has_fault": status.has_fault,
    }
    print(json.dumps(data, indent=1, default=str, ensure_ascii=False))


asyncio.run(main(sys.argv[1]))
