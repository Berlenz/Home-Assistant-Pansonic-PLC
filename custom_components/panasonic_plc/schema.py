"""Voluptuous schemas for the Panasonic PLC integration."""

from __future__ import annotations

from abc import ABC
from datetime import timedelta
from typing import ClassVar

import voluptuous as vol
from homeassistant.components.sensor import CONF_STATE_CLASS, DEVICE_CLASSES_SCHEMA, STATE_CLASSES_SCHEMA, SensorStateClass
from homeassistant.const import CONF_DEVICE_CLASS, CONF_ENTITY_ID, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL, CONF_SENSORS, CONF_UNIT_OF_MEASUREMENT
from homeassistant.helpers import config_validation as cv

from .MewtocolComConnection import DataTypes
from .const import (
    CONF_EXPOSE_DEFAULT_VALUE,
    CONF_IPV4_ADDRESS,
    CONF_IPV4_ADDRESS_OR_PLC_NAME,
    CONF_PLC_NAME,
    CONF_PANASONIC_PLC_DATA_TYPE,
    CONF_PANASONIC_PLC_EXPOSE,
    CONF_PANASONIC_PLC_FP_ADDRESS,
    CONF_PANASONIC_PLC_PAYLOAD,
    CONF_REAL_NUMBER_PRECISION,
    CONF_STATION_NUMBER,
)

data_type_validator = vol.All(vol.Upper, vol.In(DataTypes.__members__))


def validate_scan_interval(value: object) -> timedelta:
    """Validate and normalize scan interval values, including sub-second values."""
    if isinstance(value, timedelta):
        return value
    if isinstance(value, (int, float)):
        return timedelta(seconds=float(value))
    return cv.time_period(value)


SCHEMA_ETHERNET_CONNECTION = vol.Schema(
    {
        vol.Required(CONF_IPV4_ADDRESS): cv.string,
        vol.Required(CONF_PORT): cv.port,
        vol.Optional(CONF_PLC_NAME, default=""): cv.string,
        vol.Optional(CONF_STATION_NUMBER, default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=99)),
        vol.Optional(CONF_SCAN_INTERVAL): vol.All(vol.Any(cv.time_period, vol.Coerce(float)), validate_scan_interval),
    }
)


class PanasonicPLCPlatformSchema(ABC):
    """Voluptuous schema for Panasonic PLC platform entity configuration."""

    PLATFORM: ClassVar[str]
    ENTITY_SCHEMA: ClassVar[vol.Schema]

    @classmethod
    def platform_node(cls) -> dict[vol.Optional, vol.All]:
        """Return a schema node for the platform."""
        return {vol.Optional(str(cls.PLATFORM)): vol.All(cv.ensure_list, [cls.ENTITY_SCHEMA])}


class SensorSchema(PanasonicPLCPlatformSchema):
    """Voluptuous schema for Panasonic PLC sensors."""

    PLATFORM = CONF_SENSORS

    ENTITY_SCHEMA = vol.Schema(
        {
            vol.Optional(CONF_NAME, default=""): cv.string, #A PLC name for this device used within Home Assistant. If not set the name of the address is used.
            vol.Required(CONF_PANASONIC_PLC_FP_ADDRESS): cv.string, #FP address in the PLC
            vol.Required(CONF_PANASONIC_PLC_DATA_TYPE): data_type_validator, #Data type of the address in the PLC
            vol.Optional(CONF_REAL_NUMBER_PRECISION, default=None): vol.Any(None, cv.positive_int), #Precision for REAL numbers like precision = 2 => "1.12" or precision = 3 => "1.123"
            vol.Optional(CONF_UNIT_OF_MEASUREMENT): cv.string,
            vol.Optional(CONF_DEVICE_CLASS): DEVICE_CLASSES_SCHEMA,
            vol.Optional(CONF_STATE_CLASS, default=SensorStateClass.MEASUREMENT): STATE_CLASSES_SCHEMA,
        }
    )


class ExposeSchema(PanasonicPLCPlatformSchema):
    """Voluptuous schema for Panasonic PLC exposures."""
    #To write the value of entities into the PLC after the entity's value has changed.

    PLATFORM = CONF_PANASONIC_PLC_EXPOSE

    ENTITY_SCHEMA = vol.Schema(
        {
            vol.Required(CONF_ENTITY_ID): cv.entity_id, #Entity name whose value is to be transmitted to the PLC.
            vol.Required(CONF_PANASONIC_PLC_FP_ADDRESS): cv.string, #FP address in the PLC
            vol.Required(CONF_PANASONIC_PLC_DATA_TYPE): data_type_validator, #Data type of the address in the PLC
            vol.Optional(CONF_EXPOSE_DEFAULT_VALUE): cv.string,
        }
    )


SCHEMA_SERVICE_WRITE_TO_PLC = vol.Schema(
    {
        vol.Optional(CONF_IPV4_ADDRESS_OR_PLC_NAME): cv.string, #IPV4 address of the PLC, or the the name set for the PLC in the Ethernet connection setting where the IPV4 address was defined. If not set the first defined connection is used.
        vol.Required(CONF_PANASONIC_PLC_FP_ADDRESS): cv.string,
        vol.Required(CONF_PANASONIC_PLC_DATA_TYPE): data_type_validator, #Data type of the address in the PLC
        vol.Required(CONF_PANASONIC_PLC_PAYLOAD): cv.string, #Value to send to PLC, e.g. "1.23" as data type "REAL"
    }
)

