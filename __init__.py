"""Integration setup for Panasonic PLC communication."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT, CONF_SENSORS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType

from .const import DATA_HUBS, DOMAIN, SERVICE_NAME__WRITE_TO_PANASONIC_PLC
from .panasonic_plc_hub import PanasonicPlcHub, async_panasonic_plc_setup
from .schema import ExposeSchema, SCHEMA_ETHERNET_CONNECTION, SCHEMA_SERVICE_WRITE_TO_PLC, SensorSchema

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            cv.ensure_list,
            [
                SCHEMA_ETHERNET_CONNECTION.extend(
                    {
                        **SensorSchema.platform_node(),
                        **ExposeSchema.platform_node(),
                    }
                ),
            ],
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration from YAML configuration."""
    hass.data.setdefault(DOMAIN, {DATA_HUBS: {}})
    if DOMAIN not in config:
        return True

    await async_panasonic_plc_setup(hass, config)

    for conf_hub in config[DOMAIN]:
        if conf_hub.get(CONF_SENSORS):
            await async_load_platform(
                hass,
                Platform.SENSOR,
                DOMAIN,
                conf_hub,
                config,
            )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    hub = PanasonicPlcHub(hass, entry=entry)
    await hub.async_setup()
    hubs = hass.data.setdefault(DOMAIN, {})
    hubs.setdefault(DATA_HUBS, {})[entry.entry_id] = hub
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])

    if not hass.services.has_service(DOMAIN, SERVICE_NAME__WRITE_TO_PANASONIC_PLC):
        hass.services.async_register(
            DOMAIN,
            SERVICE_NAME__WRITE_TO_PANASONIC_PLC,
            hub.service_write_to_plc,
            schema=SCHEMA_SERVICE_WRITE_TO_PLC,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])
    if unload_ok:
        hub = hass.data[DOMAIN][DATA_HUBS].pop(entry.entry_id)
        await hub.async_close()
    return unload_ok

