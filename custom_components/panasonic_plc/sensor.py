"""Sensor platform for the Panasonic PLC integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import CONF_STATE_CLASS, SensorEntity
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_NAME,
    CONF_SENSORS,
    CONF_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import (
    CONF_IPV4_ADDRESS,
    CONF_PLC_NAME,
    CONF_PANASONIC_PLC_DATA_TYPE,
    CONF_PANASONIC_PLC_FP_ADDRESS,
    CONF_REAL_NUMBER_PRECISION,
    DATA_HUBS,
    DOMAIN,
)
from .MewtocolComConnection import DataTypes
from .panasonic_plc_hub import PanasonicPlcHub, get_hub_name

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up sensors for the legacy YAML-based configuration path."""
    if discovery_info is None:
        discovery_info = config

    hub_store = hass.data.setdefault(DOMAIN, {DATA_HUBS: {}})
    hub_collection = hub_store.get(DATA_HUBS, hub_store)
    hub_name = get_hub_name(
        discovery_info.get(CONF_PLC_NAME, ""), discovery_info.get(CONF_IPV4_ADDRESS, "")
    )
    hub = hub_collection.get(hub_name)
    if hub is None:
        _LOGGER.debug(
            "Creating missing Panasonic PLC hub for YAML platform setup: %s", hub_name
        )
        hub = PanasonicPlcHub(hass, config=discovery_info)
        hub_collection[hub.name] = hub
        await hub.async_setup()

    sensors = [
        PanasonicPlcSensor(hub, hub.coordinator, entity_config)
        for entity_config in discovery_info.get(CONF_SENSORS, [])
    ]
    async_add_entities(sensors)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up sensors for a config entry."""
    hub_store = hass.data[DOMAIN]
    hub_collection = hub_store.get(DATA_HUBS, hub_store)
    hub = hub_collection[entry.entry_id]
    sensors = [
        PanasonicPlcSensor(hub, hub.coordinator, entity_config)
        for entity_config in hub.sensor_configs
    ]
    async_add_entities(sensors)


class PanasonicPlcSensor(
    CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]],
    SensorEntity,
    RestoreEntity,
):
    """Representation of a Panasonic PLC sensor."""

    def __init__(
        self,
        hub: PanasonicPlcHub,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        entry: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._hub = hub
        self._entry = entry
        self._sFPAddress = entry.get(CONF_PANASONIC_PLC_FP_ADDRESS)
        self._sDataType = str(entry.get(CONF_PANASONIC_PLC_DATA_TYPE, "")).upper()
        self._uiPrecision = entry.get(CONF_REAL_NUMBER_PRECISION)
        self._attr_name = entry.get(CONF_NAME) or self._sFPAddress
        self._attr_unique_id = f"{self._hub.name}-{self._sFPAddress}"
        self._attr_native_unit_of_measurement = entry.get(CONF_UNIT_OF_MEASUREMENT)
        self._attr_device_class = entry.get(CONF_DEVICE_CLASS)
        self._attr_state_class = entry.get(CONF_STATE_CLASS)
        self._attr_should_poll = False
        self._restored_value: Any = None

    async def async_added_to_hass(self) -> None:
        """Restore the last known value when the entity is added."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is None:
            return

        if last_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
            return

        self._restored_value = last_state.state
        self.async_write_ha_state()

    def _format_value(self, value: Any) -> Any:
        """Format REAL values according to the configured precision."""
        if self._sDataType == DataTypes.REAL and self._uiPrecision is not None:
            try:
                return f"{float(value):.{self._uiPrecision}f}"
            except (TypeError, ValueError):
                return value
        return value

    @property
    def native_value(self) -> Any:
        """Return the current value from the coordinator data or the restored value."""
        coordinator_data = self.coordinator.data or {}
        if self._sFPAddress in coordinator_data:
            value = coordinator_data.get(self._sFPAddress)
            if value is None:
                return self._restored_value
            return self._format_value(value)
        if self._restored_value is not None:
            return self._format_value(self._restored_value)
        return None

    @property
    def available(self) -> bool:
        """Return whether the coordinator successfully updated."""
        return self.coordinator.last_update_success

