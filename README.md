<p align="center"><img src="docs/assets/logo.png" width="300" alt="Intelbras"></p>

# python-intelbras-solar-local

[![Tests](https://github.com/hudsonbrendon/python-intelbras-solar-local/actions/workflows/tests.yml/badge.svg)](https://github.com/hudsonbrendon/python-intelbras-solar-local/actions/workflows/tests.yml)
[![PyPI version](https://img.shields.io/pypi/v/python-intelbras-solar-local.svg)](https://pypi.org/project/python-intelbras-solar-local/)
[![Python](https://img.shields.io/pypi/pyversions/python-intelbras-solar-local.svg)](https://pypi.org/project/python-intelbras-solar-local/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

This is an async Python client that reads and controls **Intelbras solar inverters** over the local network, with no cloud
and no account. It was built for the
[`ha-intelbras-solar-local`](https://github.com/hudsonbrendon/ha-intelbras-solar-local) Home Assistant integration.

Intelbras IONS inverters are rebranded **Sungrow** string inverters, and their Wi-Fi datalogger is a Sungrow **WiNet-S**.
The datalogger exposes two interfaces without a login, and this library uses both:

- **Modbus TCP** on port `502`, using the Sungrow SG-RS register map. This is the main data source.
- The **datalogger WebSocket** on port `8082`, which the built-in web UI uses. It provides Wi-Fi and cloud link state,
  active faults and alarms, and the commercial model.

## Features

- ⚡ Power readings: AC, DC, apparent and reactive power, plus power factor.
- 🔋 Energy counters for today, the month, the year and the lifetime total (0.1 kWh resolution).
- ☀️ Voltage, current and power for each MPPT input.
- 🔌 Grid voltage, current and frequency (0.01 Hz).
- 🩺 Health data: work state, internal temperature, bus voltage, insulation resistance and fault code.
- 🧩 Firmware: the inverter's ARM and DSP versions, and the datalogger's application, build and hardware versions.
- 📶 Datalogger Wi-Fi: the joined SSID and its RSSI.
- 🛡️ Grid protection: the over/under-voltage and frequency thresholds per level, and their trip times.
- 📡 Datalogger data: Wi-Fi and cloud connectivity, active fault list and alarm count.
- 🛠️ Controls: start or stop the inverter, switch power limitation on or off, set the power limit (%), set the clock.
- No `pymodbus` dependency. The library ships a tiny asyncio Modbus TCP client, so it never clashes with the version
  that Home Assistant pins.
- Fully async (`aiohttp`) and typed (`py.typed`).

## Installation

```bash
pip install python-intelbras-solar-local
```

## Quickstart

```python
import asyncio
from intelbras_solar_local import IntelbrasSolarClient


async def main() -> None:
    async with IntelbrasSolarClient("192.168.31.17") as client:
        status = await client.async_get_status()
        print(status.model, status.serial, status.work_state)
        print(f"{status.power_ac} W now, {status.energy_today} kWh today")
        for n, mppt in enumerate(status.mppts, 1):
            print(f"MPPT{n}: {mppt.voltage} V x {mppt.current} A = {mppt.power} W")


asyncio.run(main())
```

## Supported hardware

| Inverter | Datalogger firmware | Sungrow type code |
|---|---|---|
| Intelbras IONS-5K M5 | `WIFI-SV300.001.03.P002` (WiNet-S) | `0x2614` |

Other Intelbras IONS models and Sungrow SG-RS inverters behind a WiNet-S should work as well.
If yours differs, open an issue with the output of `examples/status.py`.

## API overview

| Method | Description |
|--------|-------------|
| `async_get_status()` | Returns an `InverterStatus` from Modbus, with a `DataloggerStatus` when the WebSocket answers (best-effort) |
| `async_get_inverter_data()` | Modbus-only `InverterStatus` |
| `winet.async_get_status()` | Datalogger-only `DataloggerStatus` |
| `async_get_datalogger_info()` | `DataloggerInfo`: serial, firmware/build/hardware versions, cloud server, timezone, Wi-Fi/Ethernet link |
| `async_get_wifi_signal()` | `WifiSignal`: joined SSID and RSSI (dBm). It runs a ~3 s station scan, so don't call it every poll |
| `async_get_inverter_info()` | `InverterInfo`: serial, model, ratings, ARM/MDSP/SDSP/CPLD firmware versions |
| `async_get_fault_history()` | `FaultEvent` list: recorded faults and warnings, newest first |
| `async_get_grid_parameters()` | `GridParameter` list: grid-protection thresholds and trip times |
| `async_set_inverter_on(on)` | Starts or stops generation (holding register 5005) |
| `async_set_power_limit_enabled(enabled)` | Switches power limitation on or off (5006) |
| `async_set_power_limit(percent)` | Sets the power limit, 0–100 % (5007) |
| `async_set_clock(datetime)` | Sets the inverter clock (4999–5004) |

The register map and the WebSocket protocol are documented in the
[docs](https://hudsonbrendon.github.io/python-intelbras-solar-local/protocol/).

## Development

```bash
uv venv && uv pip install -e ".[test]"
pytest
ruff check .
```

## License

MIT © Hudson Brendon. This project is not affiliated with Intelbras or Sungrow.
