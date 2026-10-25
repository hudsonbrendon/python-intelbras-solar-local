"""Async client for Intelbras solar inverters over the local network."""
from __future__ import annotations

import logging
from datetime import datetime
from types import TracebackType

import aiohttp

from .const import (
    DEFAULT_PORT,
    DEFAULT_UNIT,
    DEFAULT_WINET_PORT,
    DISABLE,
    ENABLE,
    FC_READ_HOLDING,
    FC_READ_INPUT,
    FIRMWARE_BLOCK,
    HOLDING_BLOCKS,
    INPUT_BLOCKS,
    REG_CLOCK,
    REG_POWER_LIMIT,
    REG_POWER_LIMIT_SWITCH,
    REG_START_STOP,
    START,
    STOP,
)
from .exceptions import IntelbrasSolarError
from .modbus import ModbusTcpClient
from .models import (
    DataloggerInfo,
    GridParameter,
    InverterStatus,
    WifiSignal,
    parse_firmware,
    parse_registers,
)
from .winet import WiNetClient

_LOGGER = logging.getLogger(__name__)


class IntelbrasSolarClient:
    """Talks to one inverter through its WiNet-S datalogger.

    Modbus TCP is the primary source; the WiNet-S WebSocket adds datalogger
    connectivity, the fault list and the commercial model, best-effort.

    Args:
        host: IP or hostname of the WiNet-S datalogger.
        port: Modbus TCP port.
        unit: Modbus unit id of the inverter.
        session: optional ``aiohttp`` session for the WebSocket; one is created
            (and closed by :meth:`async_close`) when omitted.
        winet_port: WebSocket port of the datalogger web UI.
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        unit: int = DEFAULT_UNIT,
        session: aiohttp.ClientSession | None = None,
        winet_port: int = DEFAULT_WINET_PORT,
    ) -> None:
        self.host = host
        self.port = port
        self.unit = unit
        self.winet_port = winet_port
        self._session = session
        self._owns_session = session is None
        self.modbus = ModbusTcpClient(host, port, unit)
        self._firmware: tuple[str | None, str | None] | None = None

    async def __aenter__(self) -> IntelbrasSolarClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.async_close()

    async def async_close(self) -> None:
        """Close the Modbus connection and the session this client created."""
        await self.modbus.async_close()
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def winet(self) -> WiNetClient:
        """WebSocket client for the datalogger, sharing this client's session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return WiNetClient(self.host, self._session, self.winet_port)

    async def async_get_inverter_data(self) -> InverterStatus:
        """Read every polled register block over Modbus.

        Raises:
            IntelbrasSolarConnectionError: datalogger unreachable.
            IntelbrasSolarProtocolError: Modbus exception reply.
        """
        inp: dict[int, int] = {}
        hold: dict[int, int] = {}
        for start, count in INPUT_BLOCKS:
            inp |= await self.modbus.async_read(FC_READ_INPUT, start, count)
        for start, count in HOLDING_BLOCKS:
            hold |= await self.modbus.async_read(FC_READ_HOLDING, start, count)
        status = parse_registers(inp, hold)
        status.arm_firmware, status.dsp_firmware = await self._async_firmware()
        return status

    async def _async_firmware(self) -> tuple[str | None, str | None]:
        """ARM/DSP versions, read once; a failed read is retried next poll."""
        if self._firmware is None:
            try:
                regs = await self.modbus.async_read(FC_READ_INPUT, *FIRMWARE_BLOCK)
            except IntelbrasSolarError as err:
                _LOGGER.debug("Firmware registers unavailable: %s", err)
                return None, None
            self._firmware = parse_firmware(regs)
        return self._firmware

    async def async_get_status(self) -> InverterStatus:
        """Modbus snapshot plus datalogger state (``datalogger`` may be None).

        A WebSocket failure never fails the call; only Modbus errors raise.
        """
        status = await self.async_get_inverter_data()
        try:
            status.datalogger = await self.winet.async_get_status()
        except IntelbrasSolarError as err:
            _LOGGER.debug("WiNet datalogger read failed: %s", err)
        return status

    async def async_get_datalogger_info(self) -> DataloggerInfo:
        """Datalogger serial, firmware/hardware versions and network links."""
        return await self.winet.async_get_info()

    async def async_get_wifi_signal(self) -> WifiSignal:
        """Joined Wi-Fi network and RSSI (runs a ~3 s station scan)."""
        return await self.winet.async_get_wifi_signal()

    async def async_get_grid_parameters(self) -> list[GridParameter]:
        """Grid-protection thresholds and trip times."""
        return await self.winet.async_get_grid_parameters()

    async def async_set_inverter_on(self, on: bool) -> None:
        """Start (``True``) or stop (``False``) power generation."""
        await self.modbus.async_write(REG_START_STOP, START if on else STOP)

    async def async_set_power_limit_enabled(self, enabled: bool) -> None:
        """Turn the active power limitation on or off."""
        await self.modbus.async_write(
            REG_POWER_LIMIT_SWITCH, ENABLE if enabled else DISABLE
        )

    async def async_set_power_limit(self, percent: float) -> None:
        """Set the active power limit, 0–100 % of nominal power."""
        if not 0 <= percent <= 100:
            raise ValueError("percent must be between 0 and 100")
        await self.modbus.async_write(REG_POWER_LIMIT, round(percent * 10))

    async def async_set_clock(self, when: datetime) -> None:
        """Set the inverter clock (one register per field)."""
        fields = (when.year, when.month, when.day, when.hour, when.minute, when.second)
        for offset, value in enumerate(fields):
            await self.modbus.async_write(REG_CLOCK + offset, value)
