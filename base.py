"""Base entity which all other entity platform classes can inherit."""

import logging

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from open_pico_local_api import PicoDeviceModel

from .const import DOMAIN
from .coordinator import MainCoordinator

_LOGGER = logging.getLogger(__name__)


class BaseEntity(CoordinatorEntity):
    """Base Entity Class for Open Pico devices."""

    coordinator: MainCoordinator
    def __init__(self, coordinator: MainCoordinator, device_index: int) -> None:
        """Initialise entity."""
        super().__init__(coordinator)
        self.device_index = device_index

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update entity with latest data from coordinator."""
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        if not self.coordinator.data:
            return DeviceInfo(
                identifiers={(DOMAIN, self.coordinator.family_name)},
                name=self.coordinator.device_name,
                manufacturer="Tecnosystemi",
            )

        device_info = self.coordinator.data.device_info

        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.family_name)},
            name=device_info.name or self.coordinator.device_name,
            manufacturer="Tecnosystemi",
            model=f"Model {device_info.model}",
            sw_version=device_info.firmware_version,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data is not None