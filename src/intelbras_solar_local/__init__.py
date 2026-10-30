"""Async Python client for Intelbras solar inverters (Sungrow WiNet-S) over the LAN."""

from importlib import metadata

from .client import IntelbrasSolarClient
from .const import (
    DEFAULT_PORT,
    DEFAULT_UNIT,
    DEFAULT_WINET_PORT,
    DEVICE_MODELS,
    FAULT_NAMES,
    PARAM_PROTECTION,
    PARAM_SYSTEM,
    REACTIVE_MODES,
    WORK_STATES,
)
from .exceptions import (
    IntelbrasSolarConnectionError,
    IntelbrasSolarError,
    IntelbrasSolarProtocolError,
)
from .modbus import ModbusTcpClient
from .models import (
    DataloggerInfo,
    DataloggerStatus,
    FaultEvent,
    GridParameter,
    InverterInfo,
    InverterStatus,
    Mppt,
    Parameter,
    WifiSignal,
    parse_datalogger,
    parse_datalogger_info,
    parse_fault_history,
    parse_firmware,
    parse_grid_parameters,
    parse_inverter_info,
    parse_parameters,
    parse_registers,
)
from .winet import WiNetClient

__all__ = [
    "DEFAULT_PORT",
    "DEFAULT_UNIT",
    "DEFAULT_WINET_PORT",
    "DEVICE_MODELS",
    "FAULT_NAMES",
    "PARAM_PROTECTION",
    "PARAM_SYSTEM",
    "REACTIVE_MODES",
    "WORK_STATES",
    "DataloggerInfo",
    "DataloggerStatus",
    "FaultEvent",
    "GridParameter",
    "IntelbrasSolarClient",
    "IntelbrasSolarConnectionError",
    "IntelbrasSolarError",
    "IntelbrasSolarProtocolError",
    "InverterInfo",
    "InverterStatus",
    "ModbusTcpClient",
    "Mppt",
    "Parameter",
    "WiNetClient",
    "WifiSignal",
    "parse_datalogger",
    "parse_datalogger_info",
    "parse_fault_history",
    "parse_firmware",
    "parse_grid_parameters",
    "parse_inverter_info",
    "parse_parameters",
    "parse_registers",
]
try:
    __version__ = metadata.version("python-intelbras-solar-local")
except metadata.PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"
