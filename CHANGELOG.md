# Changelog

All notable changes to this project are documented here.

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
