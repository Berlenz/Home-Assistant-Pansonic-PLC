"""Binary sensor platform for the Panasonic PLC integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import (
    CONF_ICON,
    CONF_NAME,
    CONF_SENSORS,
    STATE_OFF,
    STATE_ON,
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
    """Set up binary sensors for the legacy YAML-based configuration path."""
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
        PanasonicPlcBinarySensor(hub, hub.coordinator, entity_config)
        for entity_config in discovery_info.get(CONF_SENSORS, [])
        if str(entity_config.get(CONF_PANASONIC_PLC_DATA_TYPE, "")).upper() == DataTypes.BOOL
    ]
    async_add_entities(sensors)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up binary sensors for a config entry."""
    hub_store = hass.data[DOMAIN]
    hub_collection = hub_store.get(DATA_HUBS, hub_store)
    hub = hub_collection[entry.entry_id]
    sensors = [
        PanasonicPlcBinarySensor(hub, hub.coordinator, entity_config)
        for entity_config in hub.sensor_configs
        if str(entity_config.get(CONF_PANASONIC_PLC_DATA_TYPE, "")).upper() == DataTypes.BOOL
    ]
    async_add_entities(sensors)


class PanasonicPlcBinarySensor(
    CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]],
    BinarySensorEntity,
    RestoreEntity,
):
    """Representation of a Panasonic PLC binary sensor."""

    def __init__(
        self,
        hub: PanasonicPlcHub,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        entry: dict[str, Any],
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._hub = hub
        self._entry = entry
        self._sFPAddress = entry.get(CONF_PANASONIC_PLC_FP_ADDRESS)
        self._attr_name = entry.get(CONF_NAME) or self._sFPAddress
        self._attr_unique_id = f"{self._hub.name}-{self._sFPAddress}"
        self._attr_icon = entry.get(CONF_ICON)
        self._attr_should_poll = False
        self._restored_is_on: bool | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last known value when the entity is added."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is None:
            return

        if last_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
            return

        self._restored_is_on = self._as_bool(last_state.state)
        self.async_write_ha_state()

    @staticmethod
    def _as_bool(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        s_value = str(value).strip().lower()
        if s_value in {"1", "true", STATE_ON}:
            return True
        if s_value in {"0", "false", STATE_OFF}:
            return False
        return None

    @property
    def is_on(self) -> bool | None:
        """Return the current boolean value from coordinator data or restored state."""
        coordinator_data = self.coordinator.data or {}
        if self._sFPAddress in coordinator_data:
            value = self._as_bool(coordinator_data.get(self._sFPAddress))
            if value is not None:
                return value
            return self._restored_is_on
        return self._restored_is_on

    @property
    def available(self) -> bool:
        """Return whether the coordinator successfully updated."""
        return self.coordinator.last_update_success
