"""Typed models parsed from inverter registers and datalogger messages."""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .const import (
    DEVICE_MODELS,
    ENABLE,
    FAULT_NAMES,
    FAULT_STATE,
    PARAM_PROTECTION,
    PRODUCING_STATES,
    REACTIVE_MODES,
    REG_POWER_FACTOR,
    REG_POWER_LIMIT,
    REG_POWER_LIMIT_SWITCH,
    REG_REACTIVE_MODE,
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
class DataloggerInfo:
    """Identity and network details of the WiNet-S (rarely change)."""

    serial: str | None = None
    firmware_version: str | None = None
    build_version: str | None = None
    hardware_version: str | None = None
    cloud_server: str | None = None
    timezone: str | None = None
    wifi_connected: bool | None = None
    ethernet_connected: bool | None = None
    country: str | None = None  # grid code, e.g. "brazil_240"
    hotspot_ssid: str | None = None
    ntp_server: str | None = None
    iec104_enabled: bool | None = None  # IEC 60870-5-104 server on port 2404


@dataclass
class WifiSignal:
    """Wi-Fi network the datalogger is joined to, from a station scan."""

    ssid: str | None
    rssi: int | None  # dBm


@dataclass
class Parameter:
    """One inverter setting from the web UI's parameter pages.

    ``kind`` is :data:`PARAM_SYSTEM` or :data:`PARAM_PROTECTION`. ``options``
    maps option names (``enable``, ``curve_a``...) to the raw values the
    datalogger expects; numeric parameters have ``minimum``/``maximum`` and
    ``accuracy`` decimals instead. ``levels`` lists the protection levels a
    protection parameter applies to (``None`` = always).
    """

    key: str
    value: float | str | None
    unit: str | None
    register: int | None
    kind: int = PARAM_PROTECTION
    param_id: int | None = None
    accuracy: int = 0
    minimum: float | None = None
    maximum: float | None = None
    options: dict[str, str] = field(default_factory=dict)
    levels: list[int] | None = None
    raw_name: str = ""
    param_type: int | None = None

    @property
    def option(self) -> str | None:
        """Option name of the current value, for option parameters."""
        for name, raw in self.options.items():
            if self.value is not None and _same(raw, self.value):
                return name
        return None


# Kept for 0.2/0.3 callers.
GridParameter = Parameter


def _same(raw: str, value: float | str) -> bool:
    try:
        return float(raw) == float(value)
    except (TypeError, ValueError):
        return str(raw) == str(value)


@dataclass
class InverterInfo:
    """Inverter identity and firmware versions as the web UI reports them."""

    serial: str | None = None
    model: str | None = None
    rated_power: float | None = None  # kW
    rated_reactive_power: float | None = None  # kvar
    arm_version: str | None = None
    mdsp_version: str | None = None
    sdsp_version: str | None = None
    cpld_version: str | None = None


@dataclass
class FaultEvent:
    """One entry of the datalogger's fault history.

    ``time`` is the inverter's local wall-clock time (naive). ``active`` is
    ``True`` for the event that raised the fault and ``False`` for the one that
    cleared it.
    """

    time: datetime | None
    code: int
    name: str
    level: str  # "fault", "warning" or "prompt"
    active: bool
    reason: str | None


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
    arm_firmware: str | None = None
    dsp_firmware: str | None = None
    power_factor_setting: float | None = None
    reactive_mode: str | None = None  # see REACTIVE_MODES
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
        power_factor_setting=s16(hold[REG_POWER_FACTOR]) / 1000
        if REG_POWER_FACTOR in hold
        else None,
        reactive_mode=REACTIVE_MODES.get(hold.get(REG_REACTIVE_MODE, -1)),
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



def _ascii(regs: dict[int, int], start: int, count: int) -> str | None:
    addresses = range(start, start + count)
    raw = b"".join(struct.pack(">H", regs.get(a, 0)) for a in addresses)
    text = raw.decode("ascii", "ignore").strip("\x00 ")
    return text or None


def parse_firmware(regs: dict[int, int]) -> tuple[str | None, str | None]:
    """ARM and DSP firmware versions from the ``FIRMWARE_BLOCK`` registers."""
    return _ascii(regs, 5799, 15), _ascii(regs, 5814, 15)


def _labelled(items: list[dict[str, Any]]) -> dict[str, str]:
    """Map ``I18N_COMMON_*`` ``data_name`` keys to their values."""
    return {
        str(i.get("data_name", "")).removeprefix("I18N_COMMON_"): i.get("data_value")
        for i in items
    }


def parse_datalogger_info(
    about: dict[str, Any],
    overview: dict[str, Any],
    access_point: dict[str, Any] | None = None,
    clock_settings: dict[str, Any] | None = None,
    transmit: dict[str, Any] | None = None,
) -> DataloggerInfo:
    """Build a :class:`DataloggerInfo` from the web UI's system pages.

    ``about``/``overview`` come from ``/about/list`` and ``/device/overview``;
    the optional ones from ``/wifi/listAP``, ``/time/get`` and
    ``/transmit/list``.
    """
    labels = _labelled(about.get("list") or [])
    module = overview.get("module_info") or {}
    net = overview.get("net_info") or {}
    remote = overview.get("remote_info") or {}
    clock = overview.get("sys_time") or {}
    inverter = (overview.get("list") or [{}])[0]
    ap = ((access_point or {}).get("list") or [{}])[0]
    iec104 = None
    for group in (transmit or {}).get("list") or []:
        if group.get("name") == "iec104":
            iec104 = any(str(s.get("enable")) == "1" for s in group.get("list") or [])

    def flag(value: Any) -> bool | None:
        return None if value is None else str(value) == "1"

    return DataloggerInfo(
        serial=labels.get("DEVICE_SN") or module.get("module_sn"),
        firmware_version=labels.get("APPLI_SOFT_VERSION"),
        build_version=labels.get("BUILD_SOFT_VERSION"),
        hardware_version=labels.get("VERSION") or module.get("module_ver"),
        cloud_server=remote.get("ip"),
        timezone=clock.get("timezone"),
        wifi_connected=flag(net.get("wifi_conn_sts")),
        ethernet_connected=flag(net.get("eth_conn_sts")),
        country=_option_key(country) if (country := inverter.get("country")) else None,
        hotspot_ssid=ap.get("ssid"),
        ntp_server=(clock_settings or {}).get("ntp_server"),
        iec104_enabled=iec104,
    )


_UNITS = {"V", "Hz", "s", "%", "kW", "kVA", "kWh", "%/min"}
_RANGE = re.compile(r"\[\s*(-?[\d.]+)\s*~\s*(-?[\d.]+)\s*\]")


def _param_key(raw_name: str) -> str:
    return raw_name.removeprefix("I18N_COMMON_").removeprefix("I18N_").lower()


def _option_key(raw_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _param_key(raw_name)).strip("_")


def parse_parameters(
    items: list[dict[str, Any]], kind: int = PARAM_PROTECTION
) -> list[Parameter]:
    """Build :class:`Parameter` items from ``/device/getParam?type=<kind>``."""
    params = []
    for item in items:
        raw = item.get("param_value")
        try:
            value: float | str | None = float(raw)
        except (TypeError, ValueError):
            value = raw if raw not in (None, "", "--") else None
        bounds = _RANGE.search(str(item.get("range") or ""))
        levels = item.get("relation")
        if isinstance(levels, str):
            levels = [int(x) for x in re.findall(r"\d+", levels)]
        raw_name = str(item.get("param_name", ""))
        params.append(
            Parameter(
                key=_param_key(raw_name),
                value=value,
                unit=str(item["unit"]) if item.get("unit") in _UNITS else None,
                register=item.get("param_addr"),
                kind=kind,
                param_id=item.get("param_id"),
                accuracy=int(item.get("accuracy") or 0),
                minimum=float(bounds[1]) if bounds else None,
                maximum=float(bounds[2]) if bounds else None,
                options={
                    _option_key(str(o["name"])): str(o["value"])
                    for o in item.get("options") or []
                    if isinstance(o, dict)
                },
                levels=levels or None,
                raw_name=raw_name,
                param_type=item.get("param_type"),
            )
        )
    return params


def parse_grid_parameters(items: list[dict[str, Any]]) -> list[Parameter]:
    """Grid-protection parameters (``/device/getParam?type=2``)."""
    return parse_parameters(items, PARAM_PROTECTION)


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_inverter_info(data: dict[str, Any]) -> InverterInfo:
    """Build an :class:`InverterInfo` from ``/device/getInfo``."""
    raw = _labelled(data.get("list") or [])
    labels = {k: v for k, v in raw.items() if v not in ("", "--")}
    return InverterInfo(
        serial=labels.get("DEVICE_SN"),
        model=labels.get("DEVICE_MODEL"),
        rated_power=_number(labels.get("RATED_POWER_RATED")),
        rated_reactive_power=_number(labels.get("RATED_REACTIVE_POWER")),
        arm_version=labels.get("ARM_SOFT_VERSION"),
        mdsp_version=labels.get("MDSP_SOFT_VERSION"),
        sdsp_version=labels.get("SDSP_SOFT_VERSION"),
        cpld_version=labels.get("CPLD_SOFT_VERSION"),
    )


_LEVELS = {0: "warning", 1: "fault", 2: "warning", 3: "prompt"}


def parse_fault_history(items: list[dict[str, Any]]) -> list[FaultEvent]:
    """Build :class:`FaultEvent` items from ``/historyfault/list``, newest first."""
    events = []
    for item in items:
        code = int(item.get("warning_code", 0))
        reason = item.get("warning_reason")
        try:
            when = datetime.strptime(str(item.get("warning_time")), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            when = None
        events.append(
            FaultEvent(
                time=when,
                code=code,
                name=FAULT_NAMES.get(code, f"fault_{code}"),
                level=_LEVELS.get(int(item.get("warning_level", 1)), "fault"),
                active=str(item.get("warning_appear")) == "1",
                reason=None if reason is None else str(reason),
            )
        )
    events.sort(key=lambda e: e.time or datetime.min, reverse=True)
    return events
