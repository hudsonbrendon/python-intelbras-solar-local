"""Tests for the WiNet-S WebSocket client."""

from __future__ import annotations

import aiohttp
import pytest

from intelbras_solar_local import (
    IntelbrasSolarConnectionError,
    IntelbrasSolarProtocolError,
    WiNetClient,
)


async def test_status_skips_notices_and_reuses_token(winet_server):
    async with aiohttp.ClientSession() as session:
        client = WiNetClient("127.0.0.1", session, port=winet_server.port)
        status = await client.async_get_status()
    assert status.model == "IONS-5K M5"
    assert status.total_alarms == 1 and status.cloud_connected is False
    services = [r["service"] for r in winet_server.received]
    assert services == ["connect", "state", "fault", "devicelist"]
    assert all(r["token"] == "tok-1" for r in winet_server.received[1:])


async def test_error_reply_raises_protocol_error(winet_server):
    del winet_server.replies["fault"]
    async with aiohttp.ClientSession() as session:
        client = WiNetClient("127.0.0.1", session, port=winet_server.port)
        with pytest.raises(IntelbrasSolarProtocolError, match="INTER_ABNORMAL"):
            await client.async_get_status()


async def test_unreachable_raises_connection_error(unused_tcp_port):
    async with aiohttp.ClientSession() as session:
        client = WiNetClient("127.0.0.1", session, port=unused_tcp_port)
        with pytest.raises(IntelbrasSolarConnectionError):
            await client.async_get_status()
