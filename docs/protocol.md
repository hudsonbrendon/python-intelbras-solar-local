# Protocol

These notes come from reverse-engineering an Intelbras IONS-5K M5 with datalogger firmware `WIFI-SV300.001.03.P002`
on 2026-10-24. The library was tested against that real unit.

## Identification

- The datalogger web UI (`GET /`, a Vue + layui app) contains `version:"WiNet_V1.0.0AB2020112601"`. That string marks it
  as a **Sungrow WiNet-S** sold under the Intelbras brand.
- The WebSocket `devicelist` reports `dev_model "IONS-5K M5"`, `dev_code 9748` (`0x2614`) and `dev_type 21`
  (string inverter).
- Open ports: 80 (web UI), 443, **502 (Modbus TCP)** and **8082 (WebSocket)**. Ports 502 and 8082 require no login.

## WebSocket: `ws://<ip>:8082/ws/home/overview`

Requests and replies are JSON. Every reply has the shape `{result_code: 1, result_msg, result_data: {service, ...}}`.
The server also pushes unsolicited `notice` messages, so match each reply on its `service` field.

| Request | Reply |
|---|---|
| `{"service":"connect","token":""}` | Session `token` (no login) |
| `devicelist` with `type:"0"`, `is_check_token:"0"` | Inverters: serial, model, `dev_id`, `link_status` |
| `real` with `dev_id` | 16 readings with I18N `data_name` keys |
| `direct` with `dev_id` | Voltage and current for each MPPT |
| `statistics` / `runtime` | Daily and total energy, current power, adjustable P/Q limits |
| `state` | `total_fault`, `total_alarm`, `wifi_conn_sts`, `cloud_conn_sts` |
| `fault` | Active fault list |
| `real_battery`, `deviceInfo` | `result_code` 211/215 on this model (not supported) |

## Modbus TCP (port 502, unit 1)

This is the Sungrow SG-RS map. Addresses are 0-based (documentation address − 1), and 32-bit values are sent low word
first.

### Input registers (FC4)

| Register | Value | Scale |
|---|---|---|
| 4989–4998 | Serial number (ASCII) | |
| 4999 | Device type code | |
| 5000 | Nominal power | 0.1 kW |
| 5002 | Daily energy | 0.1 kWh |
| 5003 U32 | Total energy | kWh |
| 5005 U32 | Total running time | h |
| 5007 S16 | Internal temperature | 0.1 °C |
| 5008 U32 | Apparent power | VA |
| 5010/5011, 5012/5013 | MPPT1 and MPPT2 voltage / current | 0.1 V / 0.1 A |
| 5016 U32 | Total DC power | W |
| 5018 / 5021 | Phase A voltage / current | 0.1 V / 0.1 A |
| 5030 U32 | Active power | W |
| 5032 S32 | Reactive power | var |
| 5034 S16 | Power factor | 0.001 |
| 5037 | Work state (see `WORK_STATES`) | |
| 5038–5043 / 5044 | Fault time / fault code | |
| 5070 | Array insulation resistance | kΩ |
| 5112 | Running time today | min |
| 5127 U32 | Monthly energy | 0.1 kWh |
| 5143 U32 | Total energy (high resolution) | 0.1 kWh |
| 5146 / 5147 | Bus voltage / grid frequency | 0.1 V / 0.01 Hz |
| 5225 U32 | Yearly energy (inferred) | 0.1 kWh |

### Holding registers (FC3 read, FC6 write)

| Register | Value |
|---|---|
| 4999–5004 | Clock: year, month, day, hour, minute, second |
| 5005 | `0xCF` start, `0xCE` stop |
| 5006 | Power limitation: `0xAA` on, `0x55` off |
| 5007 | Power limit in 0.1 % |

On this unit, a block read of the holding registers fails with exception 4 once it reaches register 5019.

## Not verified

- The yearly energy register (5225) is inferred. It read 6907 kWh while the Intelbras cloud showed 6842 kWh.
- The control register values come from Sungrow's documentation and match what this unit reads back. They are
  exercised against a fake server in the tests.
