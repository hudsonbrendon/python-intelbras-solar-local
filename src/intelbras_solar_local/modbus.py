"""Minimal asyncio Modbus TCP client (FC3, FC4, FC6).

Only what the inverter needs, with no third-party dependency, so it never
clashes with the ``pymodbus`` version pinned by Home Assistant.
"""
from __future__ import annotations

import asyncio
import struct

from .const import (
    DEFAULT_PORT,
    DEFAULT_UNIT,
    FC_WRITE_SINGLE,
    MODBUS_TIMEOUT,
)
from .exceptions import IntelbrasSolarConnectionError, IntelbrasSolarProtocolError

_MBAP = struct.Struct(">HHHB")


class ModbusTcpClient:
    """One persistent Modbus TCP connection, reopened on demand after errors."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        unit: int = DEFAULT_UNIT,
        timeout: float = MODBUS_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.unit = unit
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._tid = 0
        # The WiNet-S serves one request at a time; serialize every call.
        self._lock = asyncio.Lock()

    async def async_close(self) -> None:
        """Close the TCP connection (it reopens on the next request)."""
        if self._writer is not None:
            self._writer.close()
        self._reader = self._writer = None

    async def async_read(
        self, function: int, address: int, count: int
    ) -> dict[int, int]:
        """Read ``count`` registers starting at ``address``.

        Args:
            function: ``3`` (holding) or ``4`` (input).
            address: 0-based start register.
            count: number of registers (max 125).

        Returns:
            Mapping of register address to its unsigned 16-bit value.
        """
        body = await self._request(struct.pack(">BHH", function, address, count))
        size = body[1]
        values = struct.unpack(f">{size // 2}H", body[2 : 2 + size])
        return {address + i: v for i, v in enumerate(values)}

    async def async_write(self, address: int, value: int) -> None:
        """Write one holding register (FC6)."""
        await self._request(struct.pack(">BHH", FC_WRITE_SINGLE, address, value))

    async def _request(self, pdu: bytes) -> bytes:
        async with self._lock:
            try:
                body = await asyncio.wait_for(self._roundtrip(pdu), self.timeout)
            except (OSError, TimeoutError, asyncio.IncompleteReadError) as err:
                await self.async_close()
                raise IntelbrasSolarConnectionError(
                    f"Modbus {self.host}:{self.port}: {err!r}"
                ) from err
        if body[0] & 0x80:
            raise IntelbrasSolarProtocolError(
                f"Modbus exception {body[1]} on function {body[0] & 0x7F}"
            )
        return body

    async def _roundtrip(self, pdu: bytes) -> bytes:
        if self._writer is None:
            self._reader, self._writer = await asyncio.open_connection(
                self.host, self.port
            )
        assert self._reader is not None
        self._tid = (self._tid + 1) & 0xFFFF
        self._writer.write(_MBAP.pack(self._tid, 0, len(pdu) + 1, self.unit) + pdu)
        await self._writer.drain()
        while True:
            tid, _, length, _ = _MBAP.unpack(await self._reader.readexactly(7))
            body = await self._reader.readexactly(length - 1)
            # Drop late replies to a request that already timed out.
            if tid == self._tid:
                return body
