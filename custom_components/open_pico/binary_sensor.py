"""Binary Sensor platform for Open Pico integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .base import BaseEntity
from .coordinator import MainCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors from a config entry (Pico or Polaris)."""
    device_type = entry.data.get("device_type")
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    if device_type == "pico":
        async_add_entities([PicoMaintenanceBinarySensor(coordinator, 0)])
    elif device_type == "polaris":
        zones = coordinator.data.zones if coordinator.data else []
        entities = [PolarisDeviceErrorBinarySensor(coordinator)]
        for zone in zones:
            entities.append(PolarisZoneErrorBinarySensor(coordinator, zone.zone_id))
        async_add_entities(entities)


class PicoMaintenanceBinarySensor(BaseEntity, BinarySensorEntity):
    """Binary sensor for filter maintenance status."""

    _attr_translation_key = "filter_maintenance"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:air-filter"

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the sensor."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_filter_maintenance_{coordinator.family_name}"

    @property
    def is_on(self) -> bool | None:
        """Return true if maintenance is required."""
        if not self.coordinator.data or not self.coordinator.data.device_info:
            return None
        return self.coordinator.data.device_info.needs_clean_filters_maintenance

    @property
    def icon(self) -> str:
        """Return the icon based on state."""
        if self.is_on:
            return "mdi:air-filter-remove"
        return "mdi:air-filter"


# ═══════════════════════════════════════════════════════════════════════
# Polaris binary sensors
# ═══════════════════════════════════════════════════════════════════════


class PolarisDeviceErrorBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor: Polaris CU has at least one active error bit."""

    _attr_translation_key = "polaris_device_error"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True
    _attr_icon = "mdi:alert-circle"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._attr_unique_id = f"polaris_{coordinator.serial}_device_error"

    @property
    def is_on(self) -> bool | None:
        if not self._coordinator.data:
            return None
        return self._coordinator.data.device.has_error

    @property
    def extra_state_attributes(self) -> dict:
        if not self._coordinator.data:
            return {}
        return {"active_errors": self._coordinator.data.device.active_errors}

    @property
    def device_info(self):
        dev = self._coordinator.data.device if self._coordinator.data else None
        return {
            "identifiers": {(DOMAIN, f"polaris_{self._coordinator.serial}")},
            "name": dev.name if dev else f"Polaris {self._coordinator.serial}",
            "manufacturer": "Tecnosystemi",
            "model": "Polaris 5X",
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class PolarisZoneErrorBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor: a Polaris zone has at least one active error bit."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator, zone_id: int) -> None:
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._zone_id = zone_id
        self._attr_unique_id = f"polaris_{coordinator.serial}_zone_{zone_id}_error"

    @property
    def _zone(self):
        if not self._coordinator.data:
            return None
        for z in self._coordinator.data.zones:
            if z.zone_id == self._zone_id:
                return z
        return None

    @property
    def name(self) -> str | None:
        z = self._zone
        return f"{z.name.strip()} Error" if z else None

    @property
    def available(self) -> bool:
        return super().available and self._zone is not None

    @property
    def is_on(self) -> bool | None:
        z = self._zone
        return z.has_error if z is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        z = self._zone
        return {"active_errors": z.active_errors} if z else {}

    @property
    def device_info(self):
        dev = self._coordinator.data.device if self._coordinator.data else None
        return {
            "identifiers": {(DOMAIN, f"polaris_{self._coordinator.serial}")},
            "name": dev.name if dev else f"Polaris {self._coordinator.serial}",
            "manufacturer": "Tecnosystemi",
            "model": "Polaris 5X",
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()