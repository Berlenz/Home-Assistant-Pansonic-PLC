# Panasonic PLC for Home Assistant

Home Assistant custom integration to read and write Panasonic FP PLC values via MEWTOCOL over TCP.

- Domain: `panasonic_plc`
- Integration type: local polling
- Supported value types: `BOOL`, `INT`, `DINT`, `UINT`, `UDINT`, `WORD`, `DWORD`, `REAL`

This integration supports:
- Reading PLC values as Home Assistant sensors.
- Exposing Home Assistant entity states back to PLC addresses.
- Direct write service calls.
- Batch read optimizations for word addresses and bit addresses.

## Features

### 1. Sensor read (PLC -> Home Assistant)
Configure PLC addresses under `sensors`.

### 2. Expose entities (Home Assistant -> PLC)
Configure Home Assistant entities under `expose` to write their state to PLC addresses.

### 3. Manual write service
Service: `panasonic_plc.write`

## Installation

### Option A: Manual installation
1. Copy this folder to your Home Assistant config:
   - `config/custom_components/panasonic_plc/`
2. Restart Home Assistant.
3. Add YAML configuration (example below).

### Option B: Existing custom setup
If the integration is already present in `custom_components`, only update files and restart Home Assistant.

## YAML Configuration (Packages)

Place a YAML file in your Home Assistant `packages` directory, for example:
- `config/packages/panasonic_plc.yaml`

Example configuration:

```yaml
panasonic_plc:
  - ipv4_address: 192.168.178.100
    port: 9094
    plc_name: "PLC1"
    station_number: 1
    scan_interval: 1.0  # seconds, examples: 0.5 or 00:00:00.500000 or 00:00:10

    sensors:  # PLC -> Home Assistant: Fetch data from the PLC to Home Assistant based on the configured "scan_interval".
      - name: "Heatpump Circulation Pump" #sensor.heatpump_circulation_pump
        fp_address: "Y27F"
        data_type: "BOOL"

      - name: "Heatpump Buffer Inlet Temperature" #sensor.heatpump_buffer_inlet_temperature
        fp_address: "DDT667"
        data_type: "REAL"
        precision: 2
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement

      - name: "Heatpump Diverter Valve Request OPEN"  #sensor.heatpump_diverter_valve_request_open
        fp_address: "X26F"
        data_type: "BOOL"

    expose:  # Home Assistant -> PLC: When the sensor value changes in Home Assistant, write the value to the PLC.
      - entity_id: "binary_sensor.is_door_open"
        fp_address: "R3A"
        data_type: "BOOL"

      - entity_id: "sensor.weather_solar_radiation"
        fp_address: "DT3"
        data_type: "INT"

      - entity_id: "sensor.weather_wind_gust"
        fp_address: "DDT17"
        data_type: "REAL"
```

## Data Types

- `BOOL`: 1-bit contact address (for example FP addresses `R1A`, `XF`, `Y0`, `L0`, `T0`, `C1000`)
- `INT`: 16-bit signed
- `DINT`: 32-bit signed
- `UINT`: 16-bit unsigned
- `UDINT`: 32-bit unsigned
- `WORD`: 16-bit hex
- `DWORD`: 32-bit hex
- `REAL`: 32-bit float

## Address Families

Examples by category:

- Bit contacts: `R...`, `X...`, `Y...`, `L...`, `T...`, `C...`
- 16-bit word contacts: `WR...`, `WX...`, `WY...`, `WL...`
- 32-bit word contacts: `DWR...`, `DWX...`, `DWY...`, `DWL...`
- 16-bit registers: `DT...`, `LD...`, `FL...`
- 32-bit registers: `DDT...`, `DLD...`, `DFL...`

## Service: Write to PLC

Call service:
- `panasonic_plc.write`

Fields:
- `ipv4_address_or_plc_name` (optional)
- `fp_address` (required)
- `data_type` (required)
- `payload` (required)

Example service call:

```yaml
service: panasonic_plc.write
data:
  ipv4_address_or_plc_name: "PLC1"
  fp_address: "DT0"
  data_type: "INT"
  payload: "123"
```

## Troubleshooting

- Verify PLC IP, port, and station number.
- Check that each `fp_address` matches the selected `data_type`.
- Start with a slower `scan_interval` if communication is unstable.
- Confirm network access from Home Assistant host to PLC TCP port.

## Notes

- `scan_interval` accepts float seconds and time-period style values.
- If `plc_name` is not set, the integration uses IP-based naming.
