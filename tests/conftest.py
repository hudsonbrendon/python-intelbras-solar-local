"""Shared fixtures: captured registers and fake Modbus / WiNet servers."""
from __future__ import annotations

import asyncio
import json
import struct

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

# Captured from a real IONS-5K M5 on 2026-10-24 (serial replaced).
INPUT = {
    4989: 0x5853, 4990: 0x3132, 4991: 0x3334, 4992: 0x3536, 4993: 0x3738,
    4994: 0x3000, 4999: 0x2614, 5000: 50, 5002: 277, 5003: 15345, 5005: 7262,
    5007: 645, 5008: 2265, 5010: 1890, 5011: 62, 5012: 1860, 5013: 65,
    5016: 2408, 5018: 2310, 5021: 97, 5030: 2265, 5032: 65532, 5033: 65535,
    5034: 1000, 5035: 600, 5070: 1663, 5112: 578, 5127: 6378, 5143: 22384,
    5144: 2, 5146: 3770, 5147: 6006, 5225: 3533, 5226: 1,
}
# "ARM_SUNSTONE-S_V11_V01_A" at 5799 and "MDSP_SUNSTONE-S_V11_V01_A" at 5814.
def _ascii_regs(start: int, text: str, count: int = 15) -> dict[int, int]:
    raw = text.encode().ljust(count * 2, b"\0")
    return {start + i: int.from_bytes(raw[2 * i : 2 * i + 2]) for i in range(count)}


FIRMWARE = _ascii_regs(5799, "ARM_SUNSTONE-S_V11_V01_A") | _ascii_regs(
    5814, "MDSP_SUNSTONE-S_V11_V01_A"
)

HOLDING = {
    4999: 2026, 5000: 10, 5001: 24, 5002: 14, 5003: 51, 5004: 39,
    5005: 0xCF, 5006: 0xAA, 5007: 1000,
}

WINET_REPLIES = {
    "connect": {"token": "tok-1", "uid": 1},
    "state": {
        "total_fault": "0", "total_alarm": "1", "wifi_conn_sts": "1",
        "cloud_conn_sts": "0",
    },
    "fault": {"list": [], "count": 0},
    "devicelist": {
        "list": [
            {
                "dev_id": 1,
                "dev_type": 21,
                "dev_code": 9748,
                "dev_sn": "XS123456780",
                "dev_model": "IONS-5K M5",
            }
        ],
        "count": 1,
    },
}

ABOUT = {
    "list": [
        {"data_name": f"I18N_COMMON_{name}", "data_value": value}
        for name, value in (
            ("DEVICE_SN", "B12345"),
            ("APPLI_SOFT_VERSION", "WIFI-SV300.001.03.P002"),
            ("BUILD_SOFT_VERSION", "WIFI-SV300.001.03.B000"),
            ("VERSION", "M_WI-FI_V01_V01_A"),
        )
    ]
}
OVERVIEW = {
    "module_info": {"module_sn": "B12345", "module_ver": "M_WI-FI_V01_V01_A"},
    "net_info": {"wifi_conn_sts": 1, "eth_conn_sts": 0},
    "remote_info": {"ip": "app.isolarcloud.com"},
    "sys_time": {"timezone": "UTC-03:00"},
}
DEVICE_INFO = {
    "list": [
        {"data_name": f"I18N_COMMON_{name}", "data_value": value, "data_unit": ""}
        for name, value in (
            ("DEVICE_SN", "XS123456780"),
            ("DEVICE_MODEL", "IONS-5K M5"),
            ("RATED_POWER_RATED", "5.0"),
            ("ARM_SOFT_VERSION", "SUNSTONE-S_01011.01.39"),
            ("MDSP_SOFT_VERSION", "SUNSTONE-S_03011.01.24"),
            ("PVD_SOFT_VERSION", "--"),
        )
    ]
}
FAULT_HISTORY = {
    "list": [
        {"warning_time": t, "warning_level": 1, "warning_code": code,
         "warning_reason": "10", "warning_appear": appear}
        for t, code, appear in (
            ("2026-08-07 15:41:57", 6, 1),
            ("2026-09-18 11:46:45", 5, 0),
            ("2026-09-18 11:46:35", 5, 1),
            ("bad", 99, 1),
        )
    ],
    "count": 4,
}
PARAMS = {
    "list": [
        {
            "param_addr": addr,
            "param_name": f"I18N_COMMON_{name}",
            "param_value": value,
            "unit": unit,
        }
        for addr, name, value, unit in (
            (32313, "PROTECTION_SERIES", "2", "I18N_COMMON_PROTECT_PARAMS_GRADE"),
            (32323, "OVERVOLTAGE_SINGLE_PROTECT_VALUE", "268.8", "V"),
            (32364, "OVERVOLTAGE_LEVEL1_PROTECT_TIME", "--", "s"),
        )
    ]
}


class FakeInverter:
    """In-process Modbus TCP server backed by register dicts."""

    def __init__(self) -> None:
        self.input = dict(INPUT) | FIRMWARE
        self.holding = dict(HOLDING)
        self.writes: list[tuple[int, int, int]] = []
        # Next replies to corrupt: "short_mbap" or "wrong_count".
        self.garbage: list[str] = []
        self.port = 0
        self._server: asyncio.base_events.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    async def _handle(self, reader, writer) -> None:
        while True:
            try:
                header = await reader.readexactly(7)
            except asyncio.IncompleteReadError:
                break
            tid, _, length, unit = struct.unpack(">HHHB", header)
            pdu = await reader.readexactly(length - 1)
            fc, addr, value = struct.unpack(">BHH", pdu)
            if fc in (3, 4):
                regs = self.input if fc == 4 else self.holding
                body = bytes([fc, value * 2]) + b"".join(
                    struct.pack(">H", regs.get(addr + i, 0)) for i in range(value)
                )
            elif fc == 6:
                self.writes.append((unit, addr, value))
                self.holding[addr] = value
                body = pdu
            else:
                body = bytes([fc | 0x80, 1])
            if self.garbage:
                mode = self.garbage.pop(0)
                if mode == "short_mbap":
                    writer.write(struct.pack(">HHHB", tid, 0, 0, unit))
                    await writer.drain()
                    continue
                if mode == "wrong_count":
                    body = bytes([fc, 2, 0, 1])
            writer.write(struct.pack(">HHHB", tid, 0, len(body) + 1, unit) + body)
            await writer.drain()
        writer.close()


@pytest.fixture
async def inverter():
    fake = FakeInverter()
    await fake.start()
    yield fake
    await fake.stop()


@pytest.fixture
async def winet_server():
    """Fake WiNet-S WebSocket; pushes a ``notice`` before every reply."""
    replies = dict(WINET_REPLIES)
    received: list[dict] = []
    http_calls: list[tuple[str, dict]] = []
    scan = {"requested": False, "polls": 0}

    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for msg in ws:
            req = json.loads(msg.data)
            received.append(req)
            notice = {"result_code": 1, "result_data": {"service": "notice"}}
            await ws.send_str(json.dumps(notice))
            service = req["service"]
            if service == "stalist":
                scan["polls"] += 1
                ready = scan["requested"] and scan["polls"] >= 2
                data = (
                    {"curr_ssid": "CASA", "curr_signal": -36, "list": []}
                    if ready
                    else {}
                )
                await ws.send_str(json.dumps({
                    "result_code": 1 if ready else 208,
                    "result_data": {"service": "stalist", **data},
                }))
                continue
            if service not in replies:
                await ws.send_str(json.dumps({
                    "result_code": 211, "result_msg": "I18N_COMMON_INTER_ABNORMAL",
                    "result_data": {"service": service},
                }))
                continue
            await ws.send_str(json.dumps({
                "result_code": 1, "result_msg": "success",
                "result_data": {"service": service, **replies[service]},
            }))
        return ws

    def http(path, body):
        async def _handler(request):
            params = dict(request.query) | dict(await request.post())
            http_calls.append((path, params))
            if params.get("token") != "tok-1":
                return web.Response(text=json.dumps({"result_code": 106}))
            if path == "/wifi/updateStaScan":
                scan["requested"] = True
            # The real server answers JSON with a text/html content type.
            payload = {"result_code": 1, "result_msg": "success", "result_data": body}
            return web.Response(text=json.dumps(payload), content_type="text/html")

        return _handler

    app = web.Application()
    app.router.add_get("/ws/home/overview", handler)
    app.router.add_get("/about/list", http("/about/list", ABOUT))
    app.router.add_get("/device/overview", http("/device/overview", OVERVIEW))
    app.router.add_get("/device/getParam", http("/device/getParam", PARAMS))
    app.router.add_post("/wifi/updateStaScan", http("/wifi/updateStaScan", {}))
    app.router.add_get("/device/getInfo", http("/device/getInfo", DEVICE_INFO))
    app.router.add_post("/historyfault/list", http("/historyfault/list", FAULT_HISTORY))
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    server.replies = replies
    server.received = received
    server.http_calls = http_calls
    yield server
    await server.close()
