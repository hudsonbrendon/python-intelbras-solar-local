<p align="center"><img src="assets/logo.png" width="300" alt="Intelbras"></p>

# python-intelbras-solar-local

**python-intelbras-solar-local** is an async Python library that reads and controls Intelbras solar inverters straight
from your LAN. Intelbras IONS inverters are rebranded Sungrow units with a WiNet-S Wi-Fi datalogger. The library talks
Modbus TCP to the inverter, and reads datalogger state from the WebSocket of its built-in web UI. Neither interface asks
for a login. The library has no Home Assistant dependency.

## Install

```bash
pip install python-intelbras-solar-local
```

## Quickstart

```python
import asyncio
from intelbras_solar_local import IntelbrasSolarClient


async def main():
    async with IntelbrasSolarClient("192.168.31.17") as client:
        status = await client.async_get_status()
        print(status.model, status.power_ac, status.energy_today)


asyncio.run(main())
```
