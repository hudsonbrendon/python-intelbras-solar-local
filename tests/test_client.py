"""Tests for the high-level client."""
from __future__ import annotations

from datetime import datetime

import pytest

from intelbras_solar_local import IntelbrasSolarClient, __version__


async def test_status_merges_modbus_and_winet(inverter, winet_server):
    async with IntelbrasSolarClient(
        "127.0.0.1", inverter.port, winet_port=winet_server.port
    ) as client:
        status = await client.async_get_status()
    assert status.serial == "XS123456780"
    assert status.datalogger is not None and status.datalogger.total_alarms == 1
    assert status.arm_firmware == "ARM_SUNSTONE-S_V11_V01_A"
    assert status.dsp_firmware == "MDSP_SUNSTONE-S_V11_V01_A"


async def test_status_survives_winet_down(inverter, unused_tcp_port):
    async with IntelbrasSolarClient(
        "127.0.0.1", inverter.port, winet_port=unused_tcp_port
    ) as client:
        status = await client.async_get_status()
    assert status.power_ac == 2265 and status.datalogger is None


async def test_controls_write_expected_registers(inverter):
    async with IntelbrasSolarClient("127.0.0.1", inverter.port, unit=1) as client:
        await client.async_set_inverter_on(False)
        await client.async_set_inverter_on(True)
        await client.async_set_power_limit_enabled(False)
        await client.async_set_power_limit(87.5)
        await client.async_set_clock(datetime(2026, 1, 2, 3, 4, 5))
        with pytest.raises(ValueError):
            await client.async_set_power_limit(101)
    assert [(a, v) for _, a, v in inverter.writes] == [
        (5005, 0xCE), (5005, 0xCF), (5006, 0x55), (5007, 875),
        (4999, 2026), (5000, 1), (5001, 2), (5002, 3), (5003, 4), (5004, 5),
    ]


def test_version():
    assert __version__ == "0.3.0"


async def test_firmware_read_once_and_retried_after_failure(inverter):
    from intelbras_solar_local.const import FIRMWARE_BLOCK

    async with IntelbrasSolarClient("127.0.0.1", inverter.port) as client:
        reads = []
        real = client.modbus.async_read

        async def spy(fc, start, count):
            reads.append(start)
            return await real(fc, start, count)

        client.modbus.async_read = spy
        inverter.garbage = []
        first = await client.async_get_inverter_data()
        second = await client.async_get_inverter_data()
    assert first.dsp_firmware == second.dsp_firmware == "MDSP_SUNSTONE-S_V11_V01_A"
    assert reads.count(FIRMWARE_BLOCK[0]) == 1
