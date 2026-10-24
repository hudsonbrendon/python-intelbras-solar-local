# Usage

## Reading

`async_get_status()` reads every Modbus block. It then tries the datalogger WebSocket. A WebSocket failure leaves
`status.datalogger` as `None` and does not fail the call; only Modbus errors raise.

```python
import asyncio
from intelbras_solar_local import (
    IntelbrasSolarClient,
    IntelbrasSolarConnectionError,
)

async def main():
    async with IntelbrasSolarClient("192.168.31.17") as client:
        try:
            status = await client.async_get_status()
        except IntelbrasSolarConnectionError:
            print("Datalogger unreachable (the inverter sleeps at night)")
            return
        print(status.work_state, status.producing, status.has_fault)
        print(status.energy_today, status.energy_month, status.energy_year)
        if status.datalogger:
            print("Wi-Fi:", status.datalogger.wifi_connected)
            print("Faults:", status.datalogger.faults)

asyncio.run(main())
```

To share an `aiohttp.ClientSession`, as Home Assistant does, pass `session=`. The client then leaves the session open
when it closes.

## One client at a time

The WiNet-S datalogger serves Modbus TCP poorly to concurrent clients: requests time out, and replies can arrive
malformed. The client raises `IntelbrasSolarProtocolError` for malformed replies and reopens the connection, so a bad
reply never turns into wrong data. Even so, keep one Modbus client per datalogger.

## Controls

!!! warning
    These calls write holding registers on the inverter. Stopping the inverter halts generation until it is started
    again.

```python
await client.async_set_power_limit_enabled(True)
await client.async_set_power_limit(80)      # % of nominal power
await client.async_set_inverter_on(False)   # stop generating
await client.async_set_inverter_on(True)    # start again
```

## Errors

| Exception | When |
|---|---|
| `IntelbrasSolarConnectionError` | The host is unreachable, the request times out, or the socket closes |
| `IntelbrasSolarProtocolError` | Modbus exception reply, or WiNet `result_code` other than 1 |
| `IntelbrasSolarError` | Base class of both |
