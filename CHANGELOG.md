# Changelog

All notable changes to this project are documented here.

## [0.4.0] - 2026-10-29

### Added
- `Parameter` replaces `GridParameter`, which stays as an alias. It now carries
  everything the web UI shows for a setting: group (`PARAM_SYSTEM` /
  `PARAM_PROTECTION`), range, decimals, options, the protection levels it
  applies to, and the raw identifiers needed to write it.
- `async_get_system_parameters()` / `async_get_parameters(kind)` read the
  system settings: connecting and reconnecting time, PID recovery, grid
  voltage rise suppression, over-frequency derating, rated active and
  apparent power limits, PV connection mode and total yield adjustment.
- `async_set_parameter(param, value)` writes a system or protection parameter
  through the web UI's WebSocket `param` service, with no login needed. The
  value is checked against the range or options before sending, and an
  inverter rejection raises `IntelbrasSolarProtocolError`.
- `async_set_power_factor()` and `async_set_reactive_mode()` (holding registers
  5018 and 5035). `InverterStatus.power_factor_setting` / `reactive_mode` read
  them back.
- `async_reboot_datalogger()` restarts the WiNet-S.
- `DataloggerInfo` gains `country` (grid code), `hotspot_ssid`, `ntp_server`
  and `iec104_enabled`.
- `FAULT_NAMES` covers every code in the web UI's fault table. `FAULT_NAMES`,
  `PARAM_SYSTEM`, `PARAM_PROTECTION` and `REACTIVE_MODES` are exported.

### Fixed
- `async_get_wifi_signal()` sometimes returned a reading 20–30 dB too low. The
  scan drops the WebSocket about 2 s in, and the old code could read the
  signal mid-scan. It now starts the scan, waits 5 s and reads the result in a
  fresh session.

## [0.3.2] - 2026-10-28

### Fixed
- `async_get_fault_history()` pages through the history 100 rows at a time.
  The web UI export's `page=limit=-1` sometimes returned an empty list.

## [0.3.1] - 2026-10-28

### Fixed
- WebSocket sessions retry the connection once, after 1 s, when the datalogger
  resets the socket or drops `connect`. The WiNet-S does this when a new
  session follows the previous one too quickly, so back-to-back calls such as
  `async_get_inverter_info()` then `async_get_fault_history()` failed
  intermittently.

## [0.3.0] - 2026-10-28

### Added
- `async_get_inverter_info()` returns an `InverterInfo` from `/device/getInfo`:
  serial, model, rated active and reactive power, and the ARM, MDSP, SDSP and
  CPLD firmware versions (for example `SUNSTONE-S_01011.01.39`). The ASCII
  registers behind `InverterStatus.arm_firmware` / `dsp_firmware` hold the
  firmware family (`ARM_SUNSTONE-S_V11_V01_A`), not the version.
- `async_get_fault_history()` returns the datalogger's recorded faults and
  warnings as `FaultEvent` items, newest first. It reads `/historyfault/list`,
  and the history goes back to December 2024 on the test unit. `FAULT_NAMES`
  maps fault codes to names, taken from the web UI's fault table.
- Parsers `parse_inverter_info` and `parse_fault_history`.

## [0.2.0] - 2026-10-25

### Added
- `InverterStatus.arm_firmware` / `dsp_firmware`: inverter firmware versions
  from input registers 5799–5828 (ASCII). They are read once and cached.
- `async_get_datalogger_info()` returns a `DataloggerInfo`: datalogger serial,
  application, build and hardware versions, cloud server, timezone, and Wi-Fi
  and Ethernet link. It reads the web UI endpoints `/about/list` and
  `/device/overview` with the WebSocket session token.
- `async_get_wifi_signal()` returns a `WifiSignal` with the joined SSID and its
  RSSI in dBm. It runs the web UI's station scan (`/wifi/updateStaScan`, about
  3 s) and polls `stalist`.
- `async_get_grid_parameters()` returns a list of `GridParameter`: the
  inverter's grid-protection thresholds and trip times from
  `/device/getParam?type=2`, with their register addresses.
- Parsers `parse_firmware`, `parse_datalogger_info` and `parse_grid_parameters`.

## [0.1.1] - 2026-10-24

### Fixed
- Malformed or mismatched Modbus replies now raise `IntelbrasSolarProtocolError`
  and reopen the connection. Before, a bare `IndexError`/`ValueError` escaped.
  The WiNet-S produced such frames when two clients polled at the same time
  (observed on the real IONS-5K M5): bad MBAP length, wrong function code,
  wrong byte count.
- The Modbus transaction id now starts at a random value, so two concurrent
  clients no longer accept each other's replies.

## [0.1.0] - 2026-10-24

### Added
- `IntelbrasSolarClient`: async client for Intelbras (Sungrow WiNet-S) inverters with `async_get_status`, `async_get_inverter_data`, and the controls `async_set_inverter_on`, `async_set_power_limit_enabled`, `async_set_power_limit` and `async_set_clock`.
- `ModbusTcpClient`: dependency-free asyncio Modbus TCP client (FC3, FC4, FC6).
- `WiNetClient`: reader for the datalogger WebSocket (`connect`, `state`, `fault` and `devicelist` services).
- `InverterStatus`, `DataloggerStatus` and `Mppt` dataclasses, built by `parse_registers` and `parse_datalogger`.
- Exceptions `IntelbrasSolarError`, `IntelbrasSolarConnectionError` and `IntelbrasSolarProtocolError`.
