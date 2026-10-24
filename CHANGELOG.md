# Changelog

All notable changes to this project are documented here.

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
