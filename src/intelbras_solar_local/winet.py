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
    GridParameter,
    WifiSignal,
    parse_datalogger,
    parse_datalogger_info,
    parse_grid_parameters,
)

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
                async with self._session.ws_connect(self.url) as ws:
                    session = _Session(ws, self._session, self.base_url)
                    session.token = (await session.call("connect"))["token"]
                    yield session
        except (aiohttp.ClientError, TimeoutError) as err:
            raise IntelbrasSolarConnectionError(f"WiNet {self.url}: {err!r}") from err

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
            devices = await s.call("devicelist", type="0", is_check_token="0")
            dev = (devices.get("list") or [None])[0]
            if dev is None:
                return []
            data = await s.http(
                "GET",
                WINET_HTTP_PARAMS,
                type="2",
                dev_id=str(dev["dev_id"]),
                dev_type=str(dev["dev_type"]),
                dev_code=str(dev["dev_code"]),
            )
        return parse_grid_parameters(data.get("list") or [])
