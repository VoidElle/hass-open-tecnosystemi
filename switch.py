"""Switch platform for Open Pico integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.switch import SwitchEntity, SwitchDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .base import BaseEntity
from .coordinator import MainCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Pico switches from a config entry."""
    if entry.data.get("device_type") != "pico":
        return
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([
        PicoNightModeSwitch(coordinator, 0),
        PicoLEDStatusSwitch(coordinator, 0),
    ])


class PicoNightModeSwitch(BaseEntity, SwitchEntity):
    """Representation of a Pico Night Mode Switch."""

    _attr_translation_key = "night_mode"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the switch."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_night_mode_{coordinator.family_name}"
        self._attr_name = f"{coordinator.device_name} - Night Mode"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Only available if the device supports night mode
        return (
            super().available and
            self.coordinator.supports_night_mode
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if night mode is on."""
        return self.coordinator.night_mode_enabled

    async def async_turn_on(self, **_kwargs) -> None:
        """Turn night mode on."""
        _LOGGER.debug("[%s] night_mode: turn_on", self.coordinator.device_name)
        if not self.coordinator.supports_night_mode:
            current_mode = self.coordinator.current_mode.name if self.coordinator.current_mode else "Unknown"
            raise HomeAssistantError(
                f"Current mode '{current_mode}' does not support night mode"
            )

        try:
            await self.coordinator.async_set_night_mode(True)
        except Exception as err:
            _LOGGER.error("Failed to turn on night mode: %s", err)
            raise HomeAssistantError(f"Failed to turn on night mode: {err}") from err

    async def async_turn_off(self, **_kwargs) -> None:
        """Turn night mode off."""
        _LOGGER.debug("[%s] night_mode: turn_off", self.coordinator.device_name)
        if not self.coordinator.supports_night_mode:
            current_mode = self.coordinator.current_mode.name if self.coordinator.current_mode else "Unknown"
            raise HomeAssistantError(
                f"Current mode '{current_mode}' does not support night mode"
            )

        try:
            await self.coordinator.async_set_night_mode(False)
        except Exception as err:
            _LOGGER.error("Failed to turn off night mode: %s", err)
            raise HomeAssistantError(f"Failed to turn off night mode: {err}") from err

class PicoLEDStatusSwitch(BaseEntity, SwitchEntity):
    """Representation of a Pico LED Status Switch."""

    _attr_translation_key = "led_status"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the switch."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_led_status_{coordinator.family_name}"
        self._attr_name = f"{coordinator.device_name} - LED Status"

    @property
    def is_on(self) -> bool | None:
        """Return True if LED is on."""
        if not self.coordinator.data:
            return None
        # led_on_off_short: 1 = ON, 2 = OFF
        return self.coordinator.data.operating.led_on_off_short == 1

    async def async_turn_on(self, **_kwargs) -> None:
        """Turn LED on."""
        _LOGGER.debug("[%s] led_status: turn_on", self.coordinator.device_name)
        try:
            await self.coordinator.async_set_led_status(True)
        except Exception as err:
            _LOGGER.error("Failed to turn on LED: %s", err)
            raise HomeAssistantError(f"Failed to turn on LED: {err}") from err

    async def async_turn_off(self, **_kwargs) -> None:
        """Turn LED off."""
        _LOGGER.debug("[%s] led_status: turn_off", self.coordinator.device_name)
        try:
            await self.coordinator.async_set_led_status(False)
        except Exception as err:
            _LOGGER.error("Failed to turn off LED: %s", err)
            raise HomeAssistantError(f"Failed to turn off LED: {err}") from err