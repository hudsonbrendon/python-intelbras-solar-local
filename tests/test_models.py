"""Tests for register and datalogger parsing."""
from __future__ import annotations

from datetime import datetime

from intelbras_solar_local import parse_datalogger, parse_registers
from intelbras_solar_local.models import DataloggerStatus, InverterStatus

from .conftest import HOLDING, INPUT, WINET_REPLIES


def _full(regs: dict[int, int]) -> dict[int, int]:
    return {a: regs.get(a, 0) for a in range(4989, 5300)}


def test_parse_registers_real_capture():
    s = parse_registers(_full(INPUT), _full(HOLDING))
    assert s.online is True
    assert s.serial == "XS123456780"
    assert s.model == "IONS-5K M5"
    assert s.nominal_power == 5.0
    assert (s.energy_today, s.energy_month) == (27.7, 637.8)
    assert (s.energy_year, s.energy_total) == (6906.9, 15345.6)
    assert (s.power_ac, s.power_dc, s.power_apparent) == (2265, 2408, 2265)
    assert s.power_reactive == -4
    assert s.power_factor == 1.0
    assert s.temperature == 64.5
    assert (s.grid_voltage, s.grid_current, s.grid_frequency) == (231.0, 9.7, 60.06)
    assert (s.bus_voltage, s.insulation_resistance) == (377.0, 1663)
    assert (s.running_hours_total, s.running_minutes_today) == (7262, 578)
    assert [(m.voltage, m.current, m.power) for m in s.mppts] == [
        (189.0, 6.2, 1172),
        (186.0, 6.5, 1209),
    ]
    assert s.work_state == "running" and s.producing and not s.has_fault
    assert s.inverter_on and s.power_limit_enabled and s.power_limit == 100.0
    assert s.clock == datetime(2026, 10, 24, 14, 51, 39)


def test_parse_registers_states_and_signed_values():
    inp = _full(INPUT) | {5037: 0x5500, 5044: 38, 5007: 0xFFF6}
    hold = _full(HOLDING) | {5005: 0xCE, 5006: 0x55, 4999: 0}
    s = parse_registers(inp, hold)
    assert s.work_state == "fault" and s.producing is False and s.has_fault
    assert s.fault_code == 38
    assert s.temperature == -1.0
    assert s.inverter_on is False and s.power_limit_enabled is False
    assert s.clock is None  # invalid date -> None
    odd = parse_registers(_full(INPUT) | {5037: 0x1234}, _full(HOLDING))
    assert odd.work_state == "unknown"


def test_model_fallbacks():
    assert InverterStatus(online=False).model is None
    assert InverterStatus(device_type_code=0x9999).model == "Sungrow 0x9999"
    s = InverterStatus(device_type_code=0x2614, datalogger=DataloggerStatus(model="X"))
    assert s.model == "X"
    assert InverterStatus(online=False).producing is None


def test_parse_datalogger():
    d = parse_datalogger(
        WINET_REPLIES["state"], WINET_REPLIES["fault"], WINET_REPLIES["devicelist"]
    )
    assert d.model == "IONS-5K M5"
    assert d.wifi_connected is True and d.cloud_connected is False
    assert (d.total_faults, d.total_alarms, d.faults) == (0, 1, [])
    empty = parse_datalogger({}, {}, {})
    assert empty.model is None and empty.total_faults == 0


def test_datalogger_fault_counts_as_fault():
    s = parse_registers(_full(INPUT), _full(HOLDING))
    s.datalogger = DataloggerStatus(total_faults=2)
    assert s.has_fault
