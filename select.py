"""Select platform for Open Pico integration."""
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from enums.target_humidity_enum import TargetHumidityEnum
from enums.device_mode_enum import DeviceModeEnum

from .const import DOMAIN, TARGET_HUMIDITY_OPTIONS, REVERSED_TARGET_HUMIDITY_OPTIONS, MODE_INT_TO_PRESET, MODE_PRESET_TO_INT
from .base import BaseEntity
from .coordinator import MainCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
):
    """Set up the Select platform from YAML."""

    # Get all coordinators from hass.data
    coordinators = hass.data[DOMAIN]["coordinators"]

    # Create select entities for each coordinator/device
    selects = [
        entity
        for idx, coordinator in enumerate(coordinators)
        for entity in [
            PicoTargetHumiditySelect(coordinator, idx),
            PicoPresetModeSelect(coordinator, idx)
        ]
    ]

    async_add_entities(selects)


class PicoTargetHumiditySelect(BaseEntity, SelectEntity):
    """Representation of a Pico Target Humidity Select."""

    _attr_translation_key = "target_humidity"

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the select."""
        super().__init__(coordinator, device_index)

        # Set unique_id based on stable user-configured family name
        self._attr_unique_id = f"{DOMAIN}_target_humidity_{coordinator.family_name}"
        self._attr_name = f"{coordinator.device_name} - Target Humidity"

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
        if not self.coordinator.data:
            return None

        # Get the target humidity enum value from sensors
        humidity_enum = self.coordinator.data.sensors.humidity_setpoint

        # Convert enum value (1, 2, 3) to option string ("40%", "50%", "60%")
        key = int(humidity_enum)
        return TARGET_HUMIDITY_OPTIONS.get(key)

    @property
    def options(self) -> list[str]:
        """Return the list of available options."""
        return list(TARGET_HUMIDITY_OPTIONS.values())

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""

        # Check if current mode supports target humidity control
        if not self.coordinator.supports_target_humidity:
            current_mode = self.coordinator.data.operating.mode.name if self.coordinator.data else "Unknown"
            raise HomeAssistantError(
                f"Current mode '{current_mode}' does not support target humidity selection"
            )

        # Convert option string ("40%", "50%", "60%") to int (1, 2, 3)
        humidity_target_int = REVERSED_TARGET_HUMIDITY_OPTIONS.get(option)
        if humidity_target_int is None:
            raise ValueError(f"Invalid humidity option: {option}")

        try:
            # Convert to TargetHumidityEnum
            # 1 -> FORTY_PERCENT, 2 -> FIFTY_PERCENT, 3 -> SIXTY_PERCENT
            target_enum = TargetHumidityEnum(humidity_target_int)
            await self.coordinator.async_set_target_humidity(target_enum)
        except Exception as err:
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
        self._attr_name = f"{coordinator.device_name} - Preset Mode"

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if not self.coordinator.data:
            return None

        # Get the current mode enum value (int)
        mode_int = int(self.coordinator.current_mode)

        # Convert to preset string
        return MODE_INT_TO_PRESET.get(mode_int)

    @property
    def options(self) -> list[str]:
        """Return the list of available options."""
        return list(MODE_PRESET_TO_INT.keys())

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in self.options:
            raise ValueError(f"Invalid mode: {option}")

        # Convert preset mode string to int
        mode_int = MODE_PRESET_TO_INT.get(option)
        if mode_int is None:
            raise ValueError(f"Unknown preset mode: {option}")

        try:
            # Convert int to DeviceModeEnum
            mode_enum = DeviceModeEnum(mode_int)
            await self.coordinator.async_set_mode(mode_enum)
        except Exception as err:
            _LOGGER.error("Failed to set preset mode: %s", err)
            raise HomeAssistantError(f"Failed to set preset mode: {err}") from err