"""Select platform for Open Pico integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from open_pico_local_api import TargetHumidityEnum, DeviceModeEnum

from .const import DOMAIN, TARGET_HUMIDITY_OPTIONS, REVERSED_TARGET_HUMIDITY_OPTIONS, MODE_INT_TO_PRESET, MODE_PRESET_TO_INT
from .base import BaseEntity
from .coordinator import MainCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Pico selects from a config entry."""
    if entry.data.get("device_type") != "pico":
        return
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([
        PicoTargetHumiditySelect(coordinator, 0),
        PicoPresetModeSelect(coordinator, 0),
    ])


class PicoTargetHumiditySelect(BaseEntity, SelectEntity):
    """Representation of a Pico Target Humidity Select."""

    _attr_translation_key = "target_humidity"

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the select."""
        super().__init__(coordinator, device_index)

        # Set unique_id based on stable user-configured family name
        self._attr_unique_id = f"{DOMAIN}_target_humidity_{coordinator.family_name}"
        self._attr_name = "Target Humidity"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Only available if the device supports target humidity selection
        return (
            super().available and
            self.coordinator.supports_target_humidity
        )

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if self._optimistic:
            return self._attr_current_option
        if not self.coordinator.data:
            return None
        key = int(self.coordinator.data.sensors.humidity_setpoint)
        return TARGET_HUMIDITY_OPTIONS.get(key)

    @property
    def options(self) -> list[str]:
        """Return the list of available options."""
        return list(TARGET_HUMIDITY_OPTIONS.values())

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        _LOGGER.debug("[%s] target_humidity: select_option %s", self.coordinator.device_name, option)

        if not self.coordinator.supports_target_humidity:
            current_mode = self.coordinator.data.operating.mode.name if self.coordinator.data else "Unknown"
            raise HomeAssistantError(
                f"Current mode '{current_mode}' does not support target humidity selection"
            )

        humidity_target_int = REVERSED_TARGET_HUMIDITY_OPTIONS.get(option)
        if humidity_target_int is None:
            raise ValueError(f"Invalid humidity option: {option}")

        self._optimistic = True
        self._attr_current_option = option
        self.async_write_ha_state()

        try:
            target_enum = TargetHumidityEnum(humidity_target_int)
            await self.coordinator.async_set_target_humidity(target_enum)
        except Exception as err:
            self._optimistic = False
            _LOGGER.error("Failed to set target humidity: %s", err)
            raise HomeAssistantError(f"Failed to set target humidity: {err}") from err


class PicoPresetModeSelect(BaseEntity, SelectEntity):
    """Representation of a Pico Preset Mode Select."""

    _attr_translation_key = "preset_mode"

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the select."""
        super().__init__(coordinator, device_index)

        # Set unique_id based on stable user-configured family name
        self._attr_unique_id = f"{DOMAIN}_preset_mode_{coordinator.family_name}"
        self._attr_name = "Preset Mode"

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if self._optimistic:
            return self._attr_current_option
        if not self.coordinator.data:
            _LOGGER.debug("[%s] current_option: current_mode is None", self.coordinator.device_name)
            return None
        mode = self.coordinator.current_mode
        if mode is None:
            _LOGGER.debug("[%s] current_option: current_mode is None", self.coordinator.device_name)
            return None
        return MODE_INT_TO_PRESET.get(mode.value)

    @property
    def options(self) -> list[str]:
        """Return the list of available options."""
        return list(MODE_PRESET_TO_INT.keys())

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        _LOGGER.debug("[%s] preset_mode: select_option %s", self.coordinator.device_name, option)
        if option not in self.options:
            raise ValueError(f"Invalid mode: {option}")

        mode_int = MODE_PRESET_TO_INT.get(option)
        if mode_int is None:
            raise ValueError(f"Unknown preset mode: {option}")

        self._optimistic = True
        self._attr_current_option = option
        self.async_write_ha_state()

        try:
            mode_enum = DeviceModeEnum(mode_int)
            await self.coordinator.async_set_mode(mode_enum)
        except Exception as err:
            self._optimistic = False
            _LOGGER.error("Failed to set preset mode: %s", err)
            raise HomeAssistantError(f"Failed to set preset mode: {err}") from err