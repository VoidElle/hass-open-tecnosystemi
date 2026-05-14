"""Button platform for Open Pico integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .base import BaseEntity
from .coordinator import MainCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict[str, Any] | None = None,
) -> None:
    """Set up the Button platform from YAML."""
    if discovery_info is None:
        return

    # Get all coordinators from hass.data
    coordinators = hass.data[DOMAIN]["coordinators"]

    # Create button entities for each coordinator/device
    buttons = []
    for idx, coordinator in enumerate(coordinators):
        buttons.append(PicoMaintenanceResetButton(coordinator, idx))

    async_add_entities(buttons)
    _LOGGER.info("Added %d button(s)", len(buttons))


class PicoMaintenanceResetButton(BaseEntity, ButtonEntity):
    """Button to reset filter maintenance on Pico device."""

    _attr_translation_key = "reset_filter_maintenance"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_icon = "mdi:gesture-tap-button"

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the button."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_reset_maintenance_{coordinator.family_name}"
        self._attr_name = f"{coordinator.device_name} Reset Filter Maintenance"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Button is only available when device needs maintenance
        if not super().available:
            return False

        if not self.coordinator.data or not self.coordinator.data.device_info:
            return False

        return self.coordinator.data.device_info.needs_clean_filters_maintenance

    async def async_press(self) -> None:
        """Handle the button press - reset maintenance."""
        try:
            _LOGGER.debug(
                "[%s] Resetting filter maintenance",
                self.coordinator.device_name
            )

            await self.coordinator.client.reset_maintenance(retry=True)

            _LOGGER.info(
                "[%s] Filter maintenance reset command sent",
                self.coordinator.device_name
            )

            # Request immediate coordinator refresh to update states
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error(
                "[%s] Error resetting maintenance: %s",
                self.coordinator.device_name,
                err,
                exc_info=True
            )