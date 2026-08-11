"""Exposures to KNX bus."""
from __future__ import annotations

from collections.abc import Callable
import logging

from homeassistant.const import (
    CONF_ENTITY_ID,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)

from .const import (
    CONF_PANASONIC_PLC_FP_ADDRESS,
    CONF_PANASONIC_PLC_DATA_TYPE,
    CONF_EXPOSE_DEFAULT_VALUE,
)

from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.typing import ConfigType, StateType

from .MewtocolComConnection import DataTypes, MewtocolComConnection

_LOGGER = logging.getLogger(__name__)


@callback
def create_panasonic_plc_exposure(hass: HomeAssistant, connection: MewtocolComConnection, config: ConfigType) -> ExposeSensor:
    """Create exposures from config."""
    sEntityID = config[CONF_ENTITY_ID]
    sFPAddress = config[CONF_PANASONIC_PLC_FP_ADDRESS]
    sDataType = config[CONF_PANASONIC_PLC_DATA_TYPE]
    sDefaultValue = config.get(CONF_EXPOSE_DEFAULT_VALUE)
    exposure = ExposeSensor(
        hass,
        connection,
        sEntityID,
        sFPAddress,
        sDataType,
        sDefaultValue,
    )
    return exposure


class ExposeSensor:
    """Object to Expose Home Assistant entity to KNX bus."""

    def __init__(
        self,
        hass: HomeAssistant,
        connection: MewtocolComConnection,
        sEntityID: str,
        sFPAddress: str,
        sDataType: str,
        sDefaultValue: StateType,
    ) -> None:
        """Initialize of Expose class."""
        self.hass = hass
        self._Connection = connection
        self._sEntityID = sEntityID
        self._sFPAddress = sFPAddress
        self._sDataType = sDataType
        self._sDefaultValue = sDefaultValue
        self._remove_listener: Callable[[], None] | None = None
        self.RegisterListener()
        self.InitExposeState()

    @callback
    def RegisterListener(self) -> None:
        self._remove_listener = async_track_state_change_event(self.hass, [self._sEntityID], self.StateChangedListener)

    @callback
    def InitExposeState(self) -> None:
        """Initialize state of the exposure."""
        sNewState = self.hass.states.get(self._sEntityID)
        sNewExposeValue = self.GetExposeValue(sNewState)

        sOldExposeValue = self._Connection.ReadFromPlc(self._sFPAddress, self._sDataType)
        if sNewExposeValue != sOldExposeValue:
            self.WriteValueToPlc(sNewExposeValue)

    @callback
    def shutdown(self) -> None:
        """Prepare for deletion."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

    def GetExposeValue(self, state: State | None) -> str:
        """Extract value from state."""
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE): #"unknown" "unavailable"
            sValue = self._sDefaultValue
        else:
            sValue = state.state #state.state = str
        if self._sDataType == DataTypes.BOOL:
            if sValue in (STATE_ON, "True"): #"on"
                return "1"
            if sValue in (STATE_OFF, "False"):
                return "0"
        
        return sValue

    async def StateChangedListener(self, event: Event) -> None:
        """Handle entity change."""
        stateNew = event.data.get("new_state") #State
        if (sNewExposeValue := self.GetExposeValue(stateNew)) is None:
            return
        stateOld = event.data.get("old_state") #State
        # don't use default value for comparison on first state change (sOldState is None)
        sOldExposeValue = self.GetExposeValue(stateOld) if stateOld is not None else None
        # don't send same value sequentially
        if sNewExposeValue != sOldExposeValue:
            self.WriteValueToPlc(sNewExposeValue)

    def WriteValueToPlc(self, sValue: str) -> None:
        """Set new value on mewtocol_connection ExposeSensor."""
        try:
            if sValue is not None:
                self._Connection.WriteToPlc(self._sFPAddress, self._sDataType, sValue)
        except Exception as e:
            _LOGGER.warning("Exception: %s", e)


