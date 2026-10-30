"""Tests for the WiNet-S HTTP endpoints and the Wi-Fi scan."""

from __future__ import annotations

import aiohttp
import pytest

from intelbras_solar_local import WiNetClient, winet as winet_mod


@pytest.fixture(autouse=True)
def fast_scan(monkeypatch):
    real_sleep = winet_mod.asyncio.sleep
    monkeypatch.setattr(winet_mod.asyncio, "sleep", lambda s: real_sleep(0))


def _client(session, server):
    return WiNetClient("127.0.0.1", session, port=server.port, http_port=server.port)


async def test_info_uses_ws_token_on_http(winet_server):
    async with aiohttp.ClientSession() as session:
        info = await _client(session, winet_server).async_get_info()
    assert info.serial == "B12345"
    assert info.firmware_version == "WIFI-SV300.001.03.P002"
    assert info.build_version == "WIFI-SV300.001.03.B000"
    assert info.hardware_version == "M_WI-FI_V01_V01_A"
    assert info.cloud_server == "app.isolarcloud.com"
    assert info.timezone == "UTC-03:00"
    assert info.wifi_connected is True and info.ethernet_connected is False
    assert info.country == "brazil_240"
    assert info.hotspot_ssid == "IN-B12345"
    assert info.ntp_server == "ntp.api.bz"
    assert info.iec104_enabled is True
    paths = [p for p, _ in winet_server.http_calls]
    assert paths == [
        "/about/list",
        "/device/overview",
        "/wifi/listAP",
        "/time/get",
        "/transmit/list",
    ]


async def test_wifi_signal_scans_then_polls(winet_server):
    async with aiohttp.ClientSession() as session:
        signal = await _client(session, winet_server).async_get_wifi_signal()
    assert (signal.ssid, signal.rssi) == ("CASA", -36)
    assert winet_server.http_calls[0][1]["sta_scan"] == "1"


async def test_grid_parameters_use_first_device(winet_server):
    async with aiohttp.ClientSession() as session:
        params = await _client(session, winet_server).async_get_grid_parameters()
    assert [(p.key, p.value, p.unit, p.register) for p in params] == [
        ("protection_series", 2.0, None, 32313),
        ("overvoltage_single_protect_value", 268.8, "V", 32323),
        ("overvoltage_level1_protect_time", None, "s", 32364),
    ]
    query = winet_server.http_calls[0][1]
    assert (query["type"], query["dev_id"], query["dev_type"], query["dev_code"]) == (
        "2",
        "1",
        "21",
        "9748",
    )


async def test_grid_parameters_without_devices(winet_server):
    winet_server.replies["devicelist"] = {"list": [], "count": 0}
    async with aiohttp.ClientSession() as session:
        assert await _client(session, winet_server).async_get_grid_parameters() == []


async def test_inverter_info(winet_server):
    async with aiohttp.ClientSession() as session:
        info = await _client(session, winet_server).async_get_inverter_info()
    assert info.serial == "XS123456780"
    assert info.rated_power == 5.0
    assert info.arm_version == "SUNSTONE-S_01011.01.39"
    assert info.mdsp_version == "SUNSTONE-S_03011.01.24"
    assert info.sdsp_version is None and info.rated_reactive_power is None
    assert winet_server.http_calls[0][1]["dev_id"] == "1"


async def test_fault_history_newest_first(winet_server):
    from datetime import datetime

    async with aiohttp.ClientSession() as session:
        events = await _client(session, winet_server).async_get_fault_history()
    assert [(e.time, e.name, e.active) for e in events] == [
        (datetime(2026, 9, 18, 11, 46, 45), "grid_interruption", False),
        (datetime(2026, 9, 18, 11, 46, 35), "grid_interruption", True),
        (datetime(2026, 8, 7, 15, 41, 57), "leakage_current", True),
        (None, "fault_99", True),
    ]
    assert events[0].level == "fault" and events[0].reason == "10"
    form = winet_server.http_calls[0][1]
    assert form["end_time"].startswith("2037")  # firmware limit: 32-bit time_t
    assert (form["page"], form["limit"], form["dev_type"]) == ("1", "100", "21")


async def test_fault_history_pages_until_count(winet_server, monkeypatch):
    from intelbras_solar_local import winet as winet_mod

    monkeypatch.setattr(winet_mod, "FAULT_PAGE_SIZE", 2)
    async with aiohttp.ClientSession() as session:
        events = await _client(session, winet_server).async_get_fault_history()
    pages = [c[1]["page"] for c in winet_server.http_calls]
    assert pages == ["1", "2"]
    assert len(events) == 4


async def test_connect_retries_once_when_dropped(winet_server):
    winet_server.drops["connect"] = 1
    async with aiohttp.ClientSession() as session:
        info = await _client(session, winet_server).async_get_info()
    assert info.serial == "B12345"
    assert [r["service"] for r in winet_server.received].count("connect") == 2


async def test_connect_gives_up_after_retry(winet_server):
    from intelbras_solar_local import IntelbrasSolarConnectionError

    winet_server.drops["connect"] = 2
    async with aiohttp.ClientSession() as session:
        with pytest.raises(IntelbrasSolarConnectionError):
            await _client(session, winet_server).async_get_info()


async def test_system_parameters_parse_ranges_and_options(winet_server):
    from intelbras_solar_local import PARAM_SYSTEM

    async with aiohttp.ClientSession() as session:
        params = await _client(session, winet_server).async_get_parameters(PARAM_SYSTEM)
    standby, pid, f1 = params
    assert (standby.key, standby.value, standby.unit) == ("standby_time", 20.0, "s")
    assert (standby.minimum, standby.maximum, standby.options) == (10.0, 900.0, {})
    assert standby.kind == PARAM_SYSTEM and standby.param_id == 2
    assert pid.options == {"enable": "170", "prohibited": "85"}
    assert pid.option == "prohibited" and pid.unit is None
    assert f1.key == "config_key_1001939" and f1.accuracy == 2


async def test_set_parameter_sends_formatted_value(winet_server):
    from intelbras_solar_local import PARAM_SYSTEM

    async with aiohttp.ClientSession() as session:
        client = _client(session, winet_server)
        _, pid, f1 = await client.async_get_parameters(PARAM_SYSTEM)
        await client.async_set_parameter(pid, "enable")
        await client.async_set_parameter(f1, 60.5)
    sent = [r for r in winet_server.received if r["service"] == "param"]
    assert sent[0]["type"] == "1" and sent[0]["devid_array"] == ["1"]
    assert sent[0]["list"][0] == {
        "accuracy": 0,
        "id": None,
        "param_addr": 30310,
        "param_id": 5,
        "param_name": "I18N_COMMON_PID_NIGHT_REPAIR",
        "param_type": 2,
        "param_value": "170",
    }
    assert sent[1]["list"][0]["param_value"] == "60.50"


async def test_set_parameter_validates_before_sending(winet_server):
    from intelbras_solar_local import PARAM_SYSTEM

    async with aiohttp.ClientSession() as session:
        client = _client(session, winet_server)
        standby, pid, _ = await client.async_get_parameters(PARAM_SYSTEM)
        with pytest.raises(ValueError):
            await client.async_set_parameter(standby, 5)
        with pytest.raises(ValueError):
            await client.async_set_parameter(pid, "maybe")
    assert not [r for r in winet_server.received if r["service"] == "param"]


async def test_set_parameter_rejected_by_inverter(winet_server):
    from intelbras_solar_local import PARAM_SYSTEM, IntelbrasSolarProtocolError

    winet_server.param_result["value"] = -1
    async with aiohttp.ClientSession() as session:
        client = _client(session, winet_server)
        standby, _, _ = await client.async_get_parameters(PARAM_SYSTEM)
        with pytest.raises(IntelbrasSolarProtocolError):
            await client.async_set_parameter(standby, 30)


async def test_reboot_posts_maintenance(winet_server):
    async with aiohttp.ClientSession() as session:
        await _client(session, winet_server).async_reboot()
    path, form = winet_server.http_calls[-1]
    assert path == "/system/maintenance" and form["reboot"] == "1"
