"""Client for the WiNet-S datalogger web UI: WebSocket (8082) and HTTP (80).

No login is needed to read: ``connect`` hands out a session token that the
other WebSocket services and the HTTP endpoints accept.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
import time
from typing import Any

import aiohttp

from .const import (
    DEFAULT_WINET_PORT,
    PARAM_PROTECTION,
    WIFI_SCAN_TIMEOUT,
    WINET_HTTP_ABOUT,
    WINET_HTTP_AP,
    WINET_HTTP_DEVICE_INFO,
    WINET_HTTP_FAULT_HISTORY,
    WINET_HTTP_MAINTENANCE,
    WINET_HTTP_OVERVIEW,
    WINET_HTTP_PARAMS,
    WINET_HTTP_TIME,
    WINET_HTTP_TRANSMIT,
    WINET_HTTP_WIFI_SCAN,
    WINET_TIMEOUT,
    WINET_WS_PATH,
)
from .exceptions import IntelbrasSolarConnectionError, IntelbrasSolarProtocolError
from .models import (
    DataloggerInfo,
    DataloggerStatus,
    FaultEvent,
    InverterInfo,
    Parameter,
    WifiSignal,
    parse_datalogger,
    parse_datalogger_info,
    parse_fault_history,
    parse_inverter_info,
    parse_parameters,
)

# Fault history paging; 20 pages of 100 cover far more than the datalogger keeps.
FAULT_PAGE_SIZE = 100
FAULT_MAX_PAGES = 20

# Seconds between starting a Wi-Fi scan and reading its result.
WIFI_SCAN_SETTLE = 5

# Writing a parameter waits for the inverter to acknowledge it over RS485.
PARAM_WRITE_TIMEOUT = 30

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
    async def _open(
        self,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> AsyncIterator[_Session]:
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
            devices = await s.call("devicelist", type="0", is_check_token="0")  # noqa: S106
        return parse_datalogger(state, faults, devices)

    async def async_get_info(self) -> DataloggerInfo:
        """Datalogger identity, versions, network links and system settings."""
        async with self._open() as s:
            about = await s.http("GET", WINET_HTTP_ABOUT, page=1, limit=10)
            overview = await s.http("GET", WINET_HTTP_OVERVIEW)
            extra = []
            for path in (WINET_HTTP_AP, WINET_HTTP_TIME, WINET_HTTP_TRANSMIT):
                try:
                    extra.append(await s.http("GET", path, page=1, limit=10))
                except IntelbrasSolarProtocolError:
                    extra.append({})
        return parse_datalogger_info(about, overview, *extra)

    async def async_reboot(self) -> None:
        """Reboot the datalogger (the web UI's system maintenance button).

        Readings stop for about a minute while it restarts; the inverter keeps
        producing.
        """
        async with self._open() as s:
            await s.http("POST", WINET_HTTP_MAINTENANCE, reboot="1")

    async def async_get_wifi_signal(self) -> WifiSignal:
        """Run a station scan and return the joined network and its RSSI.

        This is the web UI's Wi-Fi refresh button: the scan takes about 3 s and
        does not change any setting. Do not call it on every poll.
        """
        async with self._open() as s:
            await s.http("POST", WINET_HTTP_WIFI_SCAN, sta_scan="1")
        # The scan takes the radio off-channel and drops the WebSocket about
        # 2 s in; readings before that are stale or taken mid-scan.
        await asyncio.sleep(WIFI_SCAN_SETTLE)
        async with self._open(WIFI_SCAN_TIMEOUT) as s:
            while True:
                code, data = await s.call_raw("stalist")
                if code == 1 and "curr_signal" in data:
                    return WifiSignal(data.get("curr_ssid"), data.get("curr_signal"))
                if code not in (1, _NOT_READY):
                    msg = data.get("_msg")
                    raise IntelbrasSolarProtocolError(f"WiNet stalist: {msg}")
                await asyncio.sleep(1)

    async def async_get_grid_parameters(self) -> list[Parameter]:
        """Grid-protection thresholds and trip times of the first inverter."""
        return await self.async_get_parameters(PARAM_PROTECTION)

    async def async_get_parameters(self, kind: int) -> list[Parameter]:
        """Parameters of one group (:data:`PARAM_SYSTEM`/:data:`PARAM_PROTECTION`)."""
        async with self._open() as s:
            dev = await _first_device(s)
            if dev is None:
                return []
            data = await s.http("GET", WINET_HTTP_PARAMS, type=str(kind), **dev)
        return parse_parameters(data.get("list") or [], kind)

    async def async_set_parameter(self, param: Parameter, value: float | str) -> None:
        """Write one parameter through the web UI's WebSocket ``param`` service.

        ``value`` is a number for numeric parameters or an option name (a key
        of ``param.options``) for option parameters. It is checked against the
        parameter's range or options before anything is sent.
        """
        raw = _raw_parameter_value(param, value)
        async with self._open(PARAM_WRITE_TIMEOUT) as s:
            dev = await _first_device(s)
            if dev is None:
                raise IntelbrasSolarProtocolError("WiNet param: no inverter found")
            item = {
                "accuracy": param.accuracy,
                "id": None,
                "param_addr": param.register,
                "param_id": param.param_id,
                "param_name": param.raw_name,
                "param_type": param.param_type,
                "param_value": raw,
            }
            reply = await s.call(
                "param",
                dev_code=dev["dev_code"],
                dev_type=dev["dev_type"],
                devid_array=[dev["dev_id"]],
                type=str(param.kind),
                count="1",
                list=[item],
                current_pack_num=1,
                pack_num_total=1,
                park_serial=int(time.time() * 1000),
            )
        results = [r for r in reply.get("list") or [] if r.get("param_pid", -1) != -1]
        if not any(
            r.get("param_id") == param.param_id and r.get("result") == 0
            for r in results
        ):
            raise IntelbrasSolarProtocolError(
                f"WiNet param: inverter rejected {param.key}={raw}"
            )

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
                "limit": str(FAULT_PAGE_SIZE),
            }
            # Page through it: the web UI export's page=limit=-1 sometimes
            # returns an empty list.
            rows: list[dict[str, Any]] = []
            for page in range(1, FAULT_MAX_PAGES + 1):
                data = await s.http(
                    "POST", WINET_HTTP_FAULT_HISTORY, page=str(page), **form
                )
                batch = data.get("list") or []
                rows += batch
                if len(batch) < FAULT_PAGE_SIZE or len(rows) >= data.get("count", 0):
                    break
        return parse_fault_history(rows)


def _raw_parameter_value(param: Parameter, value: float | str) -> str:
    """Validate ``value`` for ``param`` and format it as the web UI sends it."""
    if param.options:
        if value not in param.options:
            raise ValueError(f"{param.key}: {value!r} not in {sorted(param.options)}")
        return param.options[str(value)]
    number = float(value)
    if (
        param.minimum is not None
        and param.maximum is not None
        and not param.minimum <= number <= param.maximum
    ):
        raise ValueError(
            f"{param.key}: {number} outside [{param.minimum}, {param.maximum}]"
        )
    return f"{number:.{param.accuracy}f}"


async def _first_device(s: _Session) -> dict[str, str] | None:
    """``dev_id``/``dev_type``/``dev_code`` of the first device, as strings."""
    devices = await s.call("devicelist", type="0", is_check_token="0")  # noqa: S106
    dev = (devices.get("list") or [None])[0]
    if dev is None:
        return None
    return {k: str(dev[k]) for k in ("dev_id", "dev_type", "dev_code")}
