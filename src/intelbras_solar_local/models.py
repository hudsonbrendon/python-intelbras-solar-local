"""Typed models parsed from inverter registers and datalogger messages."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .const import (
    DEVICE_MODELS,
    ENABLE,
    FAULT_STATE,
    PRODUCING_STATES,
    REG_POWER_LIMIT,
    REG_POWER_LIMIT_SWITCH,
    REG_START_STOP,
    STOP,
    WORK_STATES,
)


@dataclass
class Mppt:
    """One MPPT (string) input."""

    voltage: float
    current: float

    @property
    def power(self) -> int:
        """DC power of this input in W."""
        return round(self.voltage * self.current)


@dataclass
class DataloggerStatus:
    """State reported by the WiNet-S WebSocket."""

    model: str | None = None
    wifi_connected: bool | None = None
    cloud_connected: bool | None = None
    total_faults: int = 0
    total_alarms: int = 0
    faults: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class InverterStatus:
    """Snapshot of the inverter at a point in time.

    ``online`` is ``False`` when the datalogger could not be read (typically at
    night, when the inverter powers down); every other field is then ``None``.
    """

    online: bool = True
    serial: str | None = None
    device_type_code: int | None = None
    nominal_power: float | None = None  # kW
    energy_today: float | None = None  # kWh
    energy_month: float | None = None  # kWh
    energy_year: float | None = None  # kWh
    energy_total: float | None = None  # kWh
    running_hours_total: int | None = None
    running_minutes_today: int | None = None
    temperature: float | None = None  # °C
    power_ac: int | None = None  # W
    power_dc: int | None = None  # W
    power_apparent: int | None = None  # VA
    power_reactive: int | None = None  # var
    power_factor: float | None = None
    grid_voltage: float | None = None  # V
    grid_current: float | None = None  # A
    grid_frequency: float | None = None  # Hz
    bus_voltage: float | None = None  # V
    insulation_resistance: int | None = None  # kΩ
    work_state_code: int | None = None
    fault_code: int | None = None
    inverter_on: bool | None = None
    power_limit_enabled: bool | None = None
    power_limit: float | None = None  # %
    clock: datetime | None = None
    mppts: list[Mppt] = field(default_factory=list)
    datalogger: DataloggerStatus | None = None

    @property
    def model(self) -> str | None:
        """Commercial model: from the datalogger, else the device type table."""
        if self.datalogger and self.datalogger.model:
            return self.datalogger.model
        if self.device_type_code is None:
            return None
        return DEVICE_MODELS.get(
            self.device_type_code, f"Sungrow 0x{self.device_type_code:04X}"
        )

    @property
    def work_state(self) -> str | None:
        """Work state as a snake_case key (see ``WORK_STATES``)."""
        if self.work_state_code is None:
            return None
        return WORK_STATES.get(self.work_state_code, "unknown")

    @property
    def producing(self) -> bool | None:
        """True while the inverter is feeding the grid."""
        if self.work_state_code is None:
            return None
        return self.work_state_code in PRODUCING_STATES

    @property
    def has_fault(self) -> bool | None:
        """True on a Modbus fault code, a fault state or a datalogger fault."""
        if self.work_state_code is None:
            return None
        return bool(
            self.fault_code
            or self.work_state_code == FAULT_STATE
            or (self.datalogger and self.datalogger.total_faults)
        )


def parse_registers(inp: dict[int, int], hold: dict[int, int]) -> InverterStatus:
    """Build an :class:`InverterStatus` from raw input and holding registers.

    Sungrow stores 32-bit values low word first.
    """

    def u32(a: int) -> int:
        return inp[a] | inp[a + 1] << 16

    def s16(v: int) -> int:
        return v - 0x10000 if v & 0x8000 else v

    def s32(a: int) -> int:
        v = u32(a)
        return v - 0x100000000 if v & 0x80000000 else v

    serial = b"".join(struct.pack(">H", inp[a]) for a in range(4989, 4999))
    try:
        clock = datetime(*(hold[a] for a in range(4999, 5005)))
    except ValueError:
        clock = None
    return InverterStatus(
        serial=serial.decode("ascii", "ignore").strip("\x00 "),
        device_type_code=inp[4999],
        nominal_power=inp[5000] / 10,
        energy_today=inp[5002] / 10,
        energy_month=u32(5127) / 10,
        energy_year=u32(5225) / 10,
        energy_total=u32(5143) / 10,
        running_hours_total=u32(5005),
        running_minutes_today=inp[5112],
        temperature=s16(inp[5007]) / 10,
        power_apparent=u32(5008),
        power_dc=u32(5016),
        power_ac=u32(5030),
        power_reactive=s32(5032),
        power_factor=s16(inp[5034]) / 1000,
        grid_voltage=inp[5018] / 10,
        grid_current=inp[5021] / 10,
        grid_frequency=inp[5147] / 100,
        bus_voltage=inp[5146] / 10,
        insulation_resistance=inp[5070],
        work_state_code=inp[5037],
        fault_code=inp[5044],
        inverter_on=hold[REG_START_STOP] != STOP,
        power_limit_enabled=hold[REG_POWER_LIMIT_SWITCH] == ENABLE,
        power_limit=hold[REG_POWER_LIMIT] / 10,
        clock=clock,
        # Two MPPTs on the IONS-5K M5; models with a third use 5014/5015.
        mppts=[Mppt(inp[a] / 10, inp[a + 1] / 10) for a in (5010, 5012)],
    )


def parse_datalogger(
    state: dict[str, Any], faults: dict[str, Any], devices: dict[str, Any]
) -> DataloggerStatus:
    """Build a :class:`DataloggerStatus` from WiNet-S ``result_data`` payloads."""
    device = (devices.get("list") or [{}])[0]
    return DataloggerStatus(
        model=device.get("dev_model"),
        wifi_connected=state.get("wifi_conn_sts") == "1",
        cloud_connected=state.get("cloud_conn_sts") == "1",
        total_faults=int(state.get("total_fault", 0) or 0),
        total_alarms=int(state.get("total_alarm", 0) or 0),
        faults=list(faults.get("list") or []),
    )

