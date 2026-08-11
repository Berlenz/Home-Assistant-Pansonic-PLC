"""Hub implementation for the Panasonic PLC integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, CONF_SENSORS, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .MewtocolComConnection import MewtocolComConnection
from .const import (
    CONF_IPV4_ADDRESS,
    CONF_PLC_NAME,
    CONF_PANASONIC_PLC_DATA_TYPE,
    CONF_PANASONIC_PLC_EXPOSE,
    CONF_PANASONIC_PLC_FP_ADDRESS,
    CONF_PANASONIC_PLC_PAYLOAD,
    CONF_STATION_NUMBER,
    DOMAIN,
    SERVICE_NAME__WRITE_TO_PANASONIC_PLC,
)
from .expose import ExposeSensor, create_panasonic_plc_exposure
from .schema import CONF_IPV4_ADDRESS_OR_PLC_NAME, SCHEMA_SERVICE_WRITE_TO_PLC

_LOGGER = logging.getLogger(__name__)


def get_hub_name(plc_name: str, ip_address: str) -> str:
    """Return a stable hub name for the configured PLC."""
    return plc_name or ip_address or "panasonic_plc"


def get_sensor_configs_from_entry(entry: ConfigEntry | Any | None) -> list[dict[str, Any]]:
    """Return sensor configs from entry options or, as a fallback, from the entry data."""
    if entry is None:
        return []

    options = getattr(entry, "options", None) or {}
    if CONF_SENSORS in options and options[CONF_SENSORS]:
        return options[CONF_SENSORS]

    data = getattr(entry, "data", None) or {}
    return data.get(CONF_SENSORS, [])


async def async_panasonic_plc_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Panasonic PLC hubs for YAML configuration."""
    hass.data.setdefault(DOMAIN, {"hubs": {}})
    hub_collect = hass.data[DOMAIN]["hubs"]

    for conf_hub in config[DOMAIN]:
        hub = PanasonicPlcHub(hass, config=conf_hub)
        hub_collect[hub.name] = hub
        await hub.async_setup()

        for expose_config in conf_hub.get(CONF_PANASONIC_PLC_EXPOSE, []):
            hub.exposures.append(create_panasonic_plc_exposure(hass, hub.connection, expose_config))

    async def async_stop_panasonic_plc_hubs(event: Event) -> None:
        for hub in hub_collect.values():
            await hub.async_close()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop_panasonic_plc_hubs)

    async def service_write_to_plc(service: ServiceCall) -> None:
        target = service.data.get(CONF_IPV4_ADDRESS_OR_PLC_NAME, "")
        hub = get_hub(hub_collect, target)
        await hub.service_write_to_plc(service)

    if not hass.services.has_service(DOMAIN, SERVICE_NAME__WRITE_TO_PANASONIC_PLC):
        hass.services.async_register(
            DOMAIN,
            SERVICE_NAME__WRITE_TO_PANASONIC_PLC,
            service_write_to_plc,
            schema=SCHEMA_SERVICE_WRITE_TO_PLC,
        )

    return True


class PanasonicPlcHub:
    """Representation of a Panasonic PLC connection."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry | None = None, config: dict[str, Any] | None = None) -> None:
        """Initialize the hub."""
        self.hass = hass
        self.entry = entry
        self.exposures: list[ExposeSensor] = []
        self.sensor_configs: list[dict[str, Any]] = []
        self._configured_scan_interval: timedelta | None = None

        if entry is not None:
            self._hub_name = entry.title or entry.entry_id
            self.connection = MewtocolComConnection(
                sIPV4Address=entry.data.get(CONF_IPV4_ADDRESS, entry.data.get(CONF_HOST, "")),
                iPort=entry.data.get(CONF_PORT, 8501),
                iStationNumber=entry.data.get(CONF_STATION_NUMBER, 0),
            )
            self.sensor_configs = get_sensor_configs_from_entry(entry)
            self._configured_scan_interval = entry.options.get(CONF_SCAN_INTERVAL) or entry.data.get(CONF_SCAN_INTERVAL)
        else:
            config = config or {}
            self._hub_name = get_hub_name(config.get(CONF_PLC_NAME, ""), config.get(CONF_IPV4_ADDRESS, ""))
            self.connection = MewtocolComConnection(
                sIPV4Address=config.get(CONF_IPV4_ADDRESS, ""),
                iPort=config.get(CONF_PORT, 8501),
                iStationNumber=config.get(CONF_STATION_NUMBER, 0),
            )
            self.sensor_configs = config.get(CONF_SENSORS, [])
            self._configured_scan_interval = config.get(CONF_SCAN_INTERVAL)

        self._coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self._hub_name}",
            update_method=self._async_update_data,
            update_interval=self._calculate_update_interval(),
        )

    @property
    def name(self) -> str:
        """Return the hub name."""
        return self._hub_name

    @property
    def coordinator(self) -> DataUpdateCoordinator[dict[str, Any]]:
        """Return the data coordinator."""
        return self._coordinator

    async def async_setup(self) -> None:
        """Connect to the PLC and initialise the coordinator."""
        self.connection.Connect()
        try:
            await self._coordinator.async_refresh()
        except Exception:  # pragma: no cover - defensive for offline PLCs
            _LOGGER.warning("Initial PLC refresh failed for %s", self._hub_name)

    async def async_close(self) -> None:
        """Disconnect from the PLC and clean up exposures."""
        for exposure in self.exposures:
            exposure.shutdown()
        self.exposures.clear()
        self.connection.Close()

    async def async_restart(self) -> None:
        """Reconnect to the PLC."""
        await self.async_close()
        await self.async_setup()

    def _calculate_update_interval(self) -> timedelta:
        """Return the configured hub scan interval or the default interval."""
        if isinstance(self._configured_scan_interval, timedelta):
            return self._configured_scan_interval
        if isinstance(self._configured_scan_interval, (int, float)):
            return timedelta(seconds=float(self._configured_scan_interval))
        if isinstance(self._configured_scan_interval, str):
            try:
                return timedelta(seconds=float(self._configured_scan_interval))
            except ValueError:
                pass
        return timedelta(seconds=30)

    async def _async_update_data(self) -> dict[str, Any]:
        """Read all configured sensor addresses from the PLC."""
        data: dict[str, Any] = {}
        requests: list[tuple[str, str]] = []
        for sensor_config in self.sensor_configs:
            sFPAddress = sensor_config.get(CONF_PANASONIC_PLC_FP_ADDRESS)
            sDataType = str(sensor_config.get(CONF_PANASONIC_PLC_DATA_TYPE, "")).upper()
            if not sFPAddress or not sDataType:
                continue
            requests.append((sFPAddress, sDataType))

        if not requests:
            return data

        try:
            batched_data = self.connection.ReadFromPlcBatch(requests)
        except Exception as err:
            raise UpdateFailed(f"Unable to read PLC batch: {err}") from err

        for sFPAddress, sDataType in requests:
            value = batched_data.get(sFPAddress)
            if value is None:
                try:
                    value = self.connection.ReadFromPlc(sFPAddress, sDataType)
                except Exception as err:
                    raise UpdateFailed(f"Unable to read {sFPAddress}: {err}") from err
            data[sFPAddress] = value

        return data

    async def service_write_to_plc(self, call: ServiceCall) -> None:
        """Write an arbitrary value to the PLC."""
        sFPAddress = call.data[CONF_PANASONIC_PLC_FP_ADDRESS]
        sDataType = call.data[CONF_PANASONIC_PLC_DATA_TYPE]
        payload = call.data[CONF_PANASONIC_PLC_PAYLOAD]
        try:
            self.connection.WriteToPlc(sFPAddress, sDataType, payload)
        except Exception as err:
            _LOGGER.warning("Exception while writing to PLC: %s", err)


def get_hub(hub_collect: dict[str, PanasonicPlcHub], hub_name: str) -> PanasonicPlcHub:
    """Return the requested hub, defaulting to the first configured one."""
    if not hub_name:
        return next(iter(hub_collect.values()))
    if hub_name in hub_collect:
        return hub_collect[hub_name]
    for hub in hub_collect.values():
        if hub.connection._sIPV4Address == hub_name:
            return hub
    return next(iter(hub_collect.values()))