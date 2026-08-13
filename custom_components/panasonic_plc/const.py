"""Constants for the Panasonic PLC integration."""

# MIT License
#
# Copyright (c) 2026 Michael Berlenz
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

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
