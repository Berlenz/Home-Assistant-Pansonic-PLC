"""Constants for the Panasonic PLC integration."""

from typing import Final

from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_PORT, CONF_SENSORS, Platform

DOMAIN: Final = "panasonic_plc"
DATA_HUBS: Final = "hubs"

CONF_IPV4_ADDRESS: Final = "ipv4_address"
CONF_PLC_NAME: Final = "plc_name"
CONF_STATION_NUMBER: Final = "station_number"
CONF_IPV4_ADDRESS_OR_PLC_NAME: Final = "ipv4_address_or_plc_name"
CONF_PANASONIC_PLC_DATA_TYPE: Final = "data_type"
CONF_PANASONIC_PLC_FP_ADDRESS: Final = "fp_address"
CONF_REAL_NUMBER_PRECISION: Final = "precision"
CONF_PANASONIC_PLC_PAYLOAD: Final = "payload"
CONF_EXPOSE_DEFAULT_VALUE: Final = "default"
CONF_PANASONIC_PLC_EXPOSE: Final = "expose"

ATTR_DISCOVER_DEVICES: Final = "devices"
SERVICE_NAME__WRITE_TO_PANASONIC_PLC: Final = "write"

SUPPORTED_PLATFORMS = ((Platform.SENSOR, CONF_SENSORS), (Platform.BINARY_SENSOR, CONF_SENSORS))
