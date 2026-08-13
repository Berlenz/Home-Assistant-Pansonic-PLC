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

## Support this project

If this integration is useful to you, consider buying me a coffee (or a beer 🍺): [Spendier mir ein Bier / Buy me a coffee](https://www.paypal.me/MichaelBerlenz)

## Installation

### Option A: Manual installation
1. Copy this folder to your Home Assistant config:
   - `config/custom_components/panasonic_plc/`
2. Restart Home Assistant.
3. Add YAML configuration (example below).

### Option B: Existing custom setup
If the integration is already present in `custom_components`, only update files and restart Home Assistant.

## Features & YAML Configuration (Packages)

Place a YAML file in your Home Assistant `packages` directory, for example:
- `config/packages/panasonic_plc.yaml`

Connection settings (`ipv4_address`, `port`, `plc_name`, `station_number`, `scan_interval`) are configured once per PLC, and the three features below are configured underneath it.

### 1. Sensor read (PLC -> Home Assistant)
Configure PLC addresses under `sensors` to fetch data from the PLC into Home Assistant based on the configured `scan_interval`. This creates new sensor/binary_sensor entities in Home Assistant.

### 2. Expose entities (Home Assistant -> PLC)
Configure Home Assistant entities under `expose` to write their state to PLC addresses whenever the entity state changes. This only uses entities that already exist in Home Assistant; no new entities are created here.

### 3. Manual write service
Service: `panasonic_plc.write` lets you write a value to a PLC address on demand, independent of `sensors`/`expose` (see [Service: Write to PLC](#service-write-to-plc)).

Example configuration combining all three features:

```yaml
panasonic_plc:
  - ipv4_address: 192.168.178.100
    port: 9094
    plc_name: "PLC1"
    station_number: 1
    scan_interval: 1.0  # seconds, examples: 0.5 or 00:00:00.500000 or 00:00:10

    sensors:  # 1. Sensor read: PLC -> Home Assistant
      - name: "Heatpump Circulation Pump" #binary_sensor.heatpump_circulation_pump
        fp_address: "Y27F"
        data_type: "BOOL"
        icon: mdi:pump

      - name: "Heatpump Buffer Inlet Temperature" #sensor.heatpump_buffer_inlet_temperature
        fp_address: "DDT667"
        data_type: "REAL"
        precision: 2
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement

      - name: "Heatpump Diverter Valve Request OPEN"  #binary_sensor.heatpump_diverter_valve_request_open
        fp_address: "X26F"
        data_type: "BOOL"
        icon: mdi:valve-open

    expose:  # 2. Expose entities: Home Assistant -> PLC
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

Service calls (feature 3) are not part of this YAML block; see [Service: Write to PLC](#service-write-to-plc) for an example.

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

Example automation using a trigger to call the service:

```yaml
automation:
  - alias: "Set target temperature on PLC"
    trigger:
      - platform: state
        entity_id: input_number.target_temperature
    action:
      - service: panasonic_plc.write
        data:
          ipv4_address_or_plc_name: "PLC1"
          fp_address: "DT0"
          data_type: "INT"
          payload: "{{ trigger.to_state.state | int }}"
```

## Address Families

Supported addresses:

- `R`: Bit contact, internal relay/flag
- `X`: Bit contact, input flag
- `Y`: Bit contact, output flag
- `L`: Bit contact, link flag
- `T`: Bit contact, timer flag
- `C`: Bit contact, counter flag
- `WR`: 16-bit word contact, internal relay/flag register
- `WX`: 16-bit word contact, input flag register
- `WY`: 16-bit word contact, output flag register
- `WL`: 16-bit word contact, link flag register
- `DWR`: 32-bit word contact, internal relay/flag register
- `DWX`: 32-bit word contact, input flag register
- `DWY`: 32-bit word contact, output flag register
- `DWL`: 32-bit word contact, link flag register
- `DT`: 16-bit data register
- `LD`: 16-bit link register
- `FL`: 16-bit file register
- `DDT`: 32-bit data register
- `DLD`: 32-bit link register
- `DFL`: 32-bit file register

## Data Types

Supported data types:

- `BOOL`: 1-bit contact address (for example FP addresses `R1A`, `XF`, `Y0`, `L0`, `T0`, `C1000`)
- `INT`: 16-bit signed
- `DINT`: 32-bit signed
- `UINT`: 16-bit unsigned
- `UDINT`: 32-bit unsigned
- `WORD`: 16-bit hex
- `DWORD`: 32-bit hex
- `REAL`: 32-bit float

Allowed addresses per data type:

- `BOOL`: `R`, `X`, `Y`, `L`, `T`, `C`
- `INT`, `UINT`, `WORD`: `DT`, `FL`, `WR`, `WX`, `WY`, `WL`
- `DINT`, `UDINT`, `DWORD`, `REAL`: `DDT`, `DFL`, `DWR`, `DWX`, `DWY`, `DWL`

## Troubleshooting

- Verify PLC IP, port, and station number.
- Check that each `fp_address` matches the selected `data_type`.
- Start with a slower `scan_interval` if communication is unstable.
- Confirm network access from Home Assistant host to PLC TCP port.

## Notes

- `scan_interval` accepts float seconds and time-period style values.
- If `plc_name` is not set, the integration uses IP-based naming.
