"""Client for the WiNet-S datalogger web UI: WebSocket (8082) and HTTP (80).

No login is needed to read: ``connect`` hands out a session token that the
other WebSocket services and the HTTP endpoints accept.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import aiohttp

from .const import (
    DEFAULT_WINET_PORT,
    WIFI_SCAN_TIMEOUT,
    WINET_HTTP_ABOUT,
    WINET_HTTP_DEVICE_INFO,
    WINET_HTTP_FAULT_HISTORY,
    WINET_HTTP_OVERVIEW,
    WINET_HTTP_PARAMS,
    WINET_HTTP_WIFI_SCAN,
    WINET_TIMEOUT,
    WINET_WS_PATH,
)
from .exceptions import IntelbrasSolarConnectionError, IntelbrasSolarProtocolError
from .models import (
    DataloggerInfo,
    DataloggerStatus,
    FaultEvent,
    GridParameter,
    InverterInfo,
    WifiSignal,
    parse_datalogger,
    parse_datalogger_info,
    parse_fault_history,
    parse_grid_parameters,
    parse_inverter_info,
)

# Seconds to wait before retrying a ``connect`` the datalogger dropped.
CONNECT_RETRY_DELAY = 1.0

# WiNet result_code for "nothing to report yet" (e.g. stalist before a scan).
_NOT_READY = 208


class _Session:
    """One open WebSocket plus its token, for WebSocket and HTTP calls."""

    def __init__(
        self,
        ws: aiohttp.ClientWebSocketResponse,
        http: aiohttp.ClientSession,
        base_url: str,
    ) -> None:
        self.ws = ws
        self._http = http
        self.base_url = base_url
        self.token = ""

    async def call(self, service: str, **extra: Any) -> dict[str, Any]:
        """Send one WebSocket request and return its ``result_data``."""
        code, data = await self.call_raw(service, **extra)
        if code != 1:
            raise IntelbrasSolarProtocolError(f"WiNet {service}: {data.get('_msg')}")
        return data

    async def call_raw(self, service: str, **extra: Any) -> tuple[int, dict[str, Any]]:
        """Like :meth:`call` but returns ``(result_code, result_data)`` unchecked.

        The server also pushes unsolicited ``notice`` messages; they are skipped.
        """
        payload = {"lang": "en_us", "token": self.token, "service": service, **extra}
        await self.ws.send_str(json.dumps(payload))
        async for msg in self.ws:
            if msg.type is not aiohttp.WSMsgType.TEXT:
                continue
            try:
                reply = json.loads(msg.data)
            except ValueError as err:
                raise IntelbrasSolarProtocolError(f"WiNet {service}: bad JSON") from err
            data = reply.get("result_data") or {}
            if data.get("service") != service:
                continue
            data["_msg"] = reply.get("result_msg")
            return reply.get("result_code"), data
        raise IntelbrasSolarConnectionError(f"WiNet {service}: connection closed")

    async def http(self, method: str, path: str, **params: Any) -> dict[str, Any]:
        """Call a read-only web UI endpoint and return its ``result_data``."""
        query = {
            "token": self.token,
            "lang": "en_us",
            "time123456": int(time.time() * 1000),
            **params,
        }
        kwargs: dict[str, Any] = {"params": query}
        if method == "POST":
            kwargs["data"] = query
        async with self._http.request(method, self.base_url + path, **kwargs) as resp:
            text = await resp.text()
        try:
            reply = json.loads(text)
        except ValueError as err:
            raise IntelbrasSolarProtocolError(f"WiNet {path}: bad JSON") from err
        if reply.get("result_code") != 1:
            raise IntelbrasSolarProtocolError(
                f"WiNet {path}: {reply.get('result_msg')}"
            )
        return reply.get("result_data") or {}


class WiNetClient:
    """Reads datalogger state, faults, identity, Wi-Fi signal and grid settings."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        port: int = DEFAULT_WINET_PORT,
        timeout: float = WINET_TIMEOUT,
        http_port: int = 80,
    ) -> None:
        self.url = f"ws://{host}:{port}{WINET_WS_PATH}"
        self.base_url = f"http://{host}:{http_port}"
        self._session = session
        self._timeout = timeout

    @asynccontextmanager
    async def _open(self, timeout: float | None = None) -> AsyncIterator[_Session]:
        try:
            async with asyncio.timeout(timeout or self._timeout):
                ws, token = await self._async_connect()
                try:
                    session = _Session(ws, self._session, self.base_url)
                    session.token = token
                    yield session
                finally:
                    await ws.close()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise IntelbrasSolarConnectionError(f"WiNet {self.url}: {err!r}") from err

    async def _async_connect(self) -> tuple[aiohttp.ClientWebSocketResponse, str]:
        """Open the WebSocket and get a session token, retrying once.

        The WiNet-S frees a session slot a moment after the previous socket
        closes; until then it resets the connection or drops the ``connect``.
        """
        retries = 1
        while True:
            ws = None
            try:
                ws = await self._session.ws_connect(self.url)
                reply = await _Session(ws, self._session, self.base_url).call("connect")
            except (IntelbrasSolarConnectionError, aiohttp.ClientError):
                if ws is not None:
                    await ws.close()
                if not retries:
                    raise
                retries -= 1
                await asyncio.sleep(CONNECT_RETRY_DELAY)
                continue
            return ws, reply["token"]

    async def async_get_status(self) -> DataloggerStatus:
        """Read ``state``, ``fault`` and ``devicelist`` over WebSocket."""
        async with self._open() as s:
            state = await s.call("state")
            faults = await s.call("fault")
            devices = await s.call("devicelist", type="0", is_check_token="0")
        return parse_datalogger(state, faults, devices)

    async def async_get_info(self) -> DataloggerInfo:
        """Datalogger serial, firmware/hardware versions and network links."""
        async with self._open() as s:
            about = await s.http("GET", WINET_HTTP_ABOUT, page=1, limit=10)
            overview = await s.http("GET", WINET_HTTP_OVERVIEW)
        return parse_datalogger_info(about, overview)

    async def async_get_wifi_signal(self) -> WifiSignal:
        """Run a station scan and return the joined network and its RSSI.

        This is the web UI's Wi-Fi refresh button: the scan takes about 3 s and
        does not change any setting. Do not call it on every poll.
        """
        async with self._open(WIFI_SCAN_TIMEOUT) as s:
            await s.http("POST", WINET_HTTP_WIFI_SCAN, sta_scan="1")
            while True:
                await asyncio.sleep(2)
                code, data = await s.call_raw("stalist")
                if code == 1 and "curr_signal" in data:
                    return WifiSignal(data.get("curr_ssid"), data.get("curr_signal"))
                if code not in (1, _NOT_READY):
                    msg = data.get("_msg")
                    raise IntelbrasSolarProtocolError(f"WiNet stalist: {msg}")

    async def async_get_grid_parameters(self) -> list[GridParameter]:
        """Grid-protection thresholds and trip times of the first inverter."""
        async with self._open() as s:
            dev = await _first_device(s)
            if dev is None:
                return []
            data = await s.http("GET", WINET_HTTP_PARAMS, type="2", **dev)
        return parse_grid_parameters(data.get("list") or [])

    async def async_get_inverter_info(self) -> InverterInfo:
        """Serial, model, ratings and ARM/MDSP/SDSP/CPLD firmware versions."""
        async with self._open() as s:
            dev = await _first_device(s)
            if dev is None:
                return InverterInfo()
            data = await s.http(
                "GET", WINET_HTTP_DEVICE_INFO, dev_id=dev["dev_id"], page=1, limit=100
            )
        return parse_inverter_info(data)

    async def async_get_fault_history(self) -> list[FaultEvent]:
        """Every fault and warning the datalogger recorded, newest first."""
        async with self._open() as s:
            dev = await _first_device(s)
            if dev is None:
                return []
            form = {
                **dev,
                "fault": "1",
                "warning": "1",
                "start_time": "2000-01-01 00:00:00",
                # The firmware rejects dates past 2038 (32-bit time_t).
                "end_time": "2037-12-31 23:59:59",
                # -1/-1 is what the web UI's export uses to get every row.
                "page": "-1",
                "limit": "-1",
            }
            data = await s.http("POST", WINET_HTTP_FAULT_HISTORY, **form)
        return parse_fault_history(data.get("list") or [])


async def _first_device(s: _Session) -> dict[str, str] | None:
    """``dev_id``/``dev_type``/``dev_code`` of the first device, as strings."""
    devices = await s.call("devicelist", type="0", is_check_token="0")
    dev = (devices.get("list") or [None])[0]
    if dev is None:
        return None
    return {k: str(dev[k]) for k in ("dev_id", "dev_type", "dev_code")}
