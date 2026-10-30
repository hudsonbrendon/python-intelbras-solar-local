"""Protocol constants for Intelbras (Sungrow WiNet-S) inverters.

Register addresses are 0-based, as sent on the wire. Sungrow's public
documentation numbers them 1-based, so ``doc address - 1`` maps to the
values below.
"""

from __future__ import annotations

DEFAULT_PORT = 502
DEFAULT_UNIT = 1
DEFAULT_WINET_PORT = 8082
WINET_WS_PATH = "/ws/home/overview"

MODBUS_TIMEOUT = 5
WINET_TIMEOUT = 10

FC_READ_HOLDING = 3
FC_READ_INPUT = 4
FC_WRITE_SINGLE = 6

# (start, count) blocks polled on every cycle. The holding block stops before
# 5019: reading it in a block fails with Modbus exception 4 on the IONS-5K M5.
INPUT_BLOCKS: tuple[tuple[int, int], ...] = ((4989, 61), (5050, 100), (5225, 2))
# Single reads past 5007: a block read fails with exception 4 at register 5019.
HOLDING_BLOCKS: tuple[tuple[int, int], ...] = ((4999, 9), (5018, 1), (5035, 1))

# Inverter firmware: ARM at 5799 and DSP at 5814, 15 ASCII registers each.
# Read once: the WiNet-S answers blocks that touch unmapped registers with an
# empty frame, so this stays out of the per-poll blocks.
FIRMWARE_BLOCK = (5799, 30)

# Datalogger web UI (port 80): read-only endpoints, authenticated by the token
# handed out by the WebSocket ``connect`` service.
WINET_HTTP_ABOUT = "/about/list"
WINET_HTTP_OVERVIEW = "/device/overview"
WINET_HTTP_PARAMS = "/device/getParam"
WINET_HTTP_WIFI_SCAN = "/wifi/updateStaScan"
WINET_HTTP_DEVICE_INFO = "/device/getInfo"
WINET_HTTP_FAULT_HISTORY = "/historyfault/list"
WINET_HTTP_MAINTENANCE = "/system/maintenance"
WINET_HTTP_AP = "/wifi/listAP"
WINET_HTTP_TIME = "/time/get"
WINET_HTTP_TRANSMIT = "/transmit/list"

# Parameter groups of /device/getParam and the WebSocket "param" service.
PARAM_SYSTEM = 1
PARAM_PROTECTION = 2
WIFI_SCAN_TIMEOUT = 20

# Grid-fault codes of the datalogger's fault history (/historyfault/list), from
# the web UI's fault table and language files. Unknown codes are reported as
# ``fault_<code>``.
FAULT_NAMES = {
    1: "grid_over_voltage",
    2: "grid_under_voltage",
    3: "grid_over_frequency",
    4: "grid_under_frequency",
    5: "grid_interruption",
    6: "leakage_current",
    7: "grid_abnormal",
    8: "grid_voltage_unbalance",
    12: "ambient_over_temperature",
    14: "insulation_resistance",
    15: "ground_fault",
    16: "afci_error",
    18: "meter_reverse_connection",
    19: "meter_communication",
    22: "bms_communication",
    23: "battery_reverse_polarity",
    28: "boost_capacitor_overvoltage_alarm",
    29: "boost_capacitor_overvoltage_fault",
    30: "string_current_backfeed",
    32: "abnormal_shutdown",
    35: "pv_grounding_fault",
    62: "hardware_fault",
    1001: "external_power_supply",
    # Codes the web UI's table names only through its language files.
    9: "pv_reverse_connection_fault",
    10: "pv_reverse_connection_alarm",
    11: "pv_abnormal_alarm",
    13: "ambient_under_temperature",
    17: "backup_load_overpower",
    20: "grid_conflict",
    21: "parallel_communication",
    24: "battery_alarm",
    25: "battery_fault",
    26: "pv_overvoltage",
    27: "mppt_reverse_connection",
    63: "system_alarm",
    64: "system_fault",
}

# Writable holding registers
REG_CLOCK = 4999  # year, month, day, hour, minute, second (6 registers)
REG_START_STOP = 5005
REG_POWER_LIMIT_SWITCH = 5006
REG_POWER_LIMIT = 5007  # 0.1 %
REG_POWER_FACTOR = 5018  # S16, 0.001; |pf| between 0.8 and 1
REG_REACTIVE_MODE = 5035

# Reactive power regulation modes (REG_REACTIVE_MODE). The reactive power
# percentage register next to it reads 0xFFFF on the IONS-5K, so "qt" is
# listed for completeness but likely unsupported.
REACTIVE_MODES = {
    0x55: "off",
    0xA1: "power_factor",
    0xA2: "qt",
    0xA3: "q_p",
    0xA4: "q_u",
}

START = 0xCF
STOP = 0xCE
ENABLE = 0xAA
DISABLE = 0x55

WORK_STATES: dict[int, str] = {
    0x0000: "running",
    0x8000: "stopped",
    0x1300: "key_stop",
    0x1500: "emergency_stop",
    0x1400: "standby",
    0x1200: "initial_standby",
    0x1600: "starting",
    0x9100: "alarm_run",
    0x8100: "derating_run",
    0x8200: "dispatch_run",
    0x5500: "fault",
    0x2500: "communication_fault",
}
PRODUCING_STATES = frozenset({0x0000, 0x9100, 0x8100, 0x8200})
FAULT_STATE = 0x5500

# Sungrow device type codes seen behind the Intelbras brand.
DEVICE_MODELS: dict[int, str] = {0x2614: "IONS-5K M5"}
