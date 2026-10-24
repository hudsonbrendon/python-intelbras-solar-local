# Changelog

All notable changes to this project are documented here.

## [0.1.0] - 2026-10-24

### Added
- `IntelbrasSolarClient`: async client for Intelbras (Sungrow WiNet-S) inverters with `async_get_status`, `async_get_inverter_data`, and the controls `async_set_inverter_on`, `async_set_power_limit_enabled`, `async_set_power_limit` and `async_set_clock`.
- `ModbusTcpClient`: dependency-free asyncio Modbus TCP client (FC3, FC4, FC6).
- `WiNetClient`: reader for the datalogger WebSocket (`connect`, `state`, `fault` and `devicelist` services).
- `InverterStatus`, `DataloggerStatus` and `Mppt` dataclasses, built by `parse_registers` and `parse_datalogger`.
- Exceptions `IntelbrasSolarError`, `IntelbrasSolarConnectionError` and `IntelbrasSolarProtocolError`.
