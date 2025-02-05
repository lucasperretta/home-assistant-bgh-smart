import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import pybgh
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_PASSWORD,
    CONF_USERNAME,
    STATE_UNKNOWN,
    UnitOfTemperature,
)

_LOGGER = logging.getLogger(__name__)

MAP_MODE_ID = {
    0: HVACMode.OFF,
    1: HVACMode.COOL,
    2: HVACMode.HEAT,
    3: HVACMode.DRY,
    4: HVACMode.FAN_ONLY,
    254: HVACMode.AUTO,
}

MAP_FAN_MODE_ID = {1: FAN_LOW, 2: FAN_MEDIUM, 3: FAN_HIGH, 254: FAN_AUTO}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the BGH Smart climate device from config entry."""
    loop = asyncio.get_running_loop()

    def create_client():
        return pybgh.BghClient(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])

    # Run the blocking client initialization in a separate thread
    with ThreadPoolExecutor() as pool:
        client = await loop.run_in_executor(pool, create_client)

    if not client.token:
        _LOGGER.error("Could not connect to BGH Smart cloud")
        return False

    def get_devices():
        """Fetch devices from the BGH Smart API."""
        devices = []
        for home in client.get_homes():
            home_devices = client.get_devices(home["HomeID"])
            for _device_id, device in home_devices.items():
                devices.append(device)
        return devices

    # Fetch devices in a separate thread
    with ThreadPoolExecutor() as pool:
        devices = await loop.run_in_executor(pool, get_devices)

    async_add_entities(BghHVAC(device, client) for device in devices)


class BghHVAC(ClimateEntity):
    """Representation of a BGH Smart HVAC."""

    def __init__(self, device, client):
        """Initialize a BGH Smart HVAC."""
        self._device = device
        self._client = client

        self._device_name = self._device["device_name"]
        self._device_id = self._device["device_id"]
        self._home_id = self._device["device_data"]["HomeID"]
        self._min_temp = None
        self._max_temp = None
        self._current_temperature = None
        self._target_temperature = None
        self._mode = STATE_UNKNOWN
        self._fan_speed = FAN_AUTO

        self._parse_data()

        self._hvac_modes = [
            HVACMode.AUTO,
            HVACMode.COOL,
            HVACMode.HEAT,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
            HVACMode.OFF,
        ]
        self._fan_modes = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
        self._support = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

    def _parse_data(self):
        """Parse the data in self._device"""
        self._min_temp = 17
        self._max_temp = 30

        # Sometimes the API doesn't answer with the raw_data
        if self._device["raw_data"]:
            self._current_temperature = self._device["data"]["temperature"]
            self._target_temperature = self._device["data"]["target_temperature"]
            self._mode = MAP_MODE_ID[self._device["data"]["mode_id"]]
            self._fan_speed = MAP_FAN_MODE_ID[self._device["data"]["fan_speed"]]

    def update(self):
        """Fetch new state data for this HVAC.
        This is the only method that should fetch new data for Home Assistant.
        """
        self._device = self._client.get_status(self._home_id, self._device_id)
        self._parse_data()

    @property
    def name(self):
        """Return the display name of this HVAC."""
        return self._device_name

    @property
    def temperature_unit(self):
        """BGH Smart API uses celsius on the backend."""
        return UnitOfTemperature.CELSIUS

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the target temperature."""
        return self._target_temperature

    @property
    def min_temp(self):
        """Return the minimum temperature for the current mode of operation."""
        return self._min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature for the current mode of operation."""
        return self._max_temp

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support

    @property
    def hvac_mode(self):
        """Return the current mode of operation if unit is on."""
        return self._mode

    @property
    def hvac_modes(self):
        """List of available operation modes."""
        return self._hvac_modes

    @property
    def fan_mode(self):
        """Return the current fan mode."""
        return self._fan_speed

    @property
    def fan_modes(self):
        """List of available fan modes."""
        return self._fan_modes

    def set_mode(self):
        """Push the settings to the unit."""
        self._client.set_mode(
            self._device_id, self._mode, self._target_temperature, self._fan_speed
        )

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        operation_mode = kwargs.get(ATTR_HVAC_MODE)

        if temperature:
            self._target_temperature = temperature

        if operation_mode:
            self._mode = operation_mode

        self.set_mode()

    def set_hvac_mode(self, operation_mode):
        """Set new target operation mode."""
        self._mode = operation_mode
        self.set_mode()

    def set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        self._fan_speed = fan_mode
        self.set_mode()
