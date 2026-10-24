"""WebSocket client for the WiNet-S datalogger web UI (port 8082).

No login is needed to read: ``connect`` hands out a session token that the
other read services accept.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from .const import DEFAULT_WINET_PORT, WINET_TIMEOUT, WINET_WS_PATH
from .exceptions import IntelbrasSolarConnectionError, IntelbrasSolarProtocolError
from .models import DataloggerStatus, parse_datalogger


class WiNetClient:
    """Reads datalogger state, faults and the device list over WebSocket."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        port: int = DEFAULT_WINET_PORT,
        timeout: float = WINET_TIMEOUT,
    ) -> None:
        self.url = f"ws://{host}:{port}{WINET_WS_PATH}"
        self._session = session
        self._timeout = timeout

    async def async_get_status(self) -> DataloggerStatus:
        """Open a session, read ``state``, ``fault`` and ``devicelist``, close."""
        try:
            async with asyncio.timeout(self._timeout):
                async with self._session.ws_connect(self.url) as ws:
                    token = (await _call(ws, "connect", token=""))["token"]
                    state = await _call(ws, "state", token=token)
                    faults = await _call(ws, "fault", token=token)
                    devices = await _call(
                        ws, "devicelist", token=token, type="0", is_check_token="0"
                    )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise IntelbrasSolarConnectionError(f"WiNet {self.url}: {err!r}") from err
        return parse_datalogger(state, faults, devices)


async def _call(
    ws: aiohttp.ClientWebSocketResponse, service: str, **extra: Any
) -> dict[str, Any]:
    """Send one request and wait for the reply of the same ``service``.

    The server also pushes unsolicited ``notice`` messages; they are skipped.
    """
    await ws.send_str(json.dumps({"lang": "en_us", "service": service, **extra}))
    async for msg in ws:
        if msg.type is not aiohttp.WSMsgType.TEXT:
            continue
        try:
            reply = json.loads(msg.data)
        except ValueError as err:
            raise IntelbrasSolarProtocolError(f"WiNet {service}: bad JSON") from err
        data = reply.get("result_data") or {}
        if data.get("service") != service:
            continue
        if reply.get("result_code") != 1:
            raise IntelbrasSolarProtocolError(
                f"WiNet {service}: {reply.get('result_msg')}"
            )
        return data
    raise IntelbrasSolarConnectionError(f"WiNet {service}: connection closed")
