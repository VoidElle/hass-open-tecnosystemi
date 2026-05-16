"""Fan platform for Open Pico integration."""
import logging

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from open_pico_local_api import DeviceModeEnum

from .const import DOMAIN, MODE_INT_TO_PRESET, MODE_PRESET_TO_INT
from .base import BaseEntity
from .coordinator import MainCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    _config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    _discovery_info=None,
):
    """Set up the Fan platform from YAML."""

    # Get all coordinators from hass.data
    coordinators = hass.data[DOMAIN]["coordinators"]

    fans = [
        PicoFan(coordinator, idx)
        for idx, coordinator in enumerate(coordinators)
    ]

    _LOGGER.debug("Setting up fan platform: %d fan(s)", len(fans))
    async_add_entities(fans)
    _LOGGER.info("Added %d fan(s)", len(fans))


class PicoFan(BaseEntity, FanEntity):
    """Representation of a Pico Fan."""

    _attr_supported_features = (
        FanEntityFeature.TURN_ON |
        FanEntityFeature.TURN_OFF |
        FanEntityFeature.PRESET_MODE |
        FanEntityFeature.SET_SPEED
    )

    _attr_translation_key = "pico"

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the fan."""
        super().__init__(coordinator, device_index)

        # Set unique_id based on stable user-configured family name
        self._attr_unique_id = f"{DOMAIN}_fan_{coordinator.family_name}"
        self._attr_name = f"{coordinator.device_name} - CMV"

    @property
    def preset_modes(self) -> list[str]:
        """Return available preset modes."""
        return list(MODE_PRESET_TO_INT.keys())

    @property
    def is_on(self) -> bool | None:
        """Return true if the fan is on."""
        return self.coordinator.is_on

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        if not self.coordinator.data:
            _LOGGER.debug("[%s] preset_mode: no data", self.coordinator.device_name)
            return None

        mode = self.coordinator.current_mode
        if mode is None:
            _LOGGER.debug("[%s] preset_mode: current_mode is None", self.coordinator.device_name)
            return None
        return MODE_INT_TO_PRESET.get(mode.value)

    @property
    def speed_count(self) -> int:
        """Return the speed count based on current preset mode."""
        if not self.coordinator.data:
            return 1

        # If the current mode supports speed percentage control and not in night mode
        if self.coordinator.supports_fan_speed and not self.coordinator.night_mode_enabled:
            return 100
        else:
            return 1

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage."""
        if not self.coordinator.data:
            return None

        if self.coordinator.supports_fan_speed and not self.coordinator.night_mode_enabled:
            speed = self.coordinator.fan_speed
            _LOGGER.debug("[%s] percentage: %d%%", self.coordinator.device_name, speed)
            return speed
        else:
            return 100 if self.is_on else 0

    async def async_set_percentage(self, percentage: int) -> None:
        """Set speed based on percentage slider."""
        _LOGGER.debug("[%s] set_percentage: %d%%", self.coordinator.device_name, percentage)
        if percentage == 0:
            await self.async_turn_off()
            return

        # Turn on the device if it's currently off
        if not self.is_on:
            await self.async_turn_on()

        # Check if current mode supports fan speed control
        if not self.coordinator.supports_fan_speed and percentage != 100:
            current_mode = self.preset_mode
            raise HomeAssistantError(
                f"Current mode '{current_mode}' does not support fan speed control"
            )

        # Check if night mode is enabled
        if self.coordinator.night_mode_enabled:
            raise HomeAssistantError(
                "Cannot set fan speed while night mode is enabled"
            )

        # Set the fan speed
        try:
            await self.coordinator.async_set_fan_speed(percentage)
        except Exception as err:
            _LOGGER.error("Failed to set fan speed: %s", err)
            raise HomeAssistantError(f"Failed to set fan speed: {err}") from err

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set a new preset mode."""
        _LOGGER.debug("[%s] set_preset_mode: %s", self.coordinator.device_name, preset_mode)
        if preset_mode not in self.preset_modes:
            raise ValueError(f"Invalid mode: {preset_mode}")

        # Convert preset mode string to int
        mode_int = MODE_PRESET_TO_INT.get(preset_mode)
        if mode_int is None:
            raise ValueError(f"Unknown preset mode: {preset_mode}")

        try:
            # Convert int to DeviceModeEnum
            mode_enum = DeviceModeEnum(mode_int)
            await self.coordinator.async_set_mode(mode_enum)
        except Exception as err:
            _LOGGER.error("Failed to set preset mode: %s", err)
            raise HomeAssistantError(f"Failed to set preset mode: {err}") from err

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **_kwargs
    ) -> None:
        """Turn on the fan."""
        _LOGGER.debug("[%s] turn_on: percentage=%s, preset_mode=%s", self.coordinator.device_name, percentage, preset_mode)
        try:
            await self.coordinator.async_turn_on()

            # If a preset mode is specified, set it after turning on
            if preset_mode and preset_mode in self.preset_modes:
                await self.async_set_preset_mode(preset_mode)

            # If a percentage is specified, set it after turning on
            if percentage is not None and percentage > 0:
                await self.async_set_percentage(percentage)

        except Exception as err:
            _LOGGER.error("Failed to turn on fan: %s", err)
            raise HomeAssistantError(f"Failed to turn on fan: {err}") from err

    async def async_turn_off(self, **_kwargs) -> None:
        """Turn off the fan."""
        _LOGGER.debug("[%s] turn_off", self.coordinator.device_name)
        try:
            await self.coordinator.async_turn_off()
        except Exception as err:
            _LOGGER.error("Failed to turn off fan: %s", err)
            raise HomeAssistantError(f"Failed to turn off fan: {err}") from err