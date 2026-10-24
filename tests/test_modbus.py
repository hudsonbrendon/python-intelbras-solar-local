"""Tests for the Modbus TCP transport."""
from __future__ import annotations

import pytest

from intelbras_solar_local import (
    IntelbrasSolarConnectionError,
    IntelbrasSolarProtocolError,
    ModbusTcpClient,
)


async def test_read_and_write(inverter):
    client = ModbusTcpClient("127.0.0.1", inverter.port, unit=7)
    assert await client.async_read(4, 5002, 2) == {5002: 277, 5003: 15345}
    await client.async_write(5007, 900)
    assert inverter.writes == [(7, 5007, 900)]
    assert await client.async_read(3, 5007, 1) == {5007: 900}
    await client.async_close()


async def test_exception_reply_raises_protocol_error(inverter):
    client = ModbusTcpClient("127.0.0.1", inverter.port)
    with pytest.raises(IntelbrasSolarProtocolError, match="exception 1"):
        await client.async_read(2, 0, 1)
    # The connection survives a protocol error.
    assert await client.async_read(4, 5000, 1) == {5000: 50}
    await client.async_close()


async def test_unreachable_raises_connection_error(inverter):
    port = inverter.port
    await inverter.stop()
    client = ModbusTcpClient("127.0.0.1", port, timeout=1)
    with pytest.raises(IntelbrasSolarConnectionError):
        await client.async_read(4, 5000, 1)
