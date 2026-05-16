"""Sensor platform for Open Pico integration.

Supports both Pico device sensors and Polaris zone sensors.
"""
import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    CONCENTRATION_PARTS_PER_MILLION,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, POLARIS_COOLING_MODES
from .base import BaseEntity
from .coordinator import MainCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
        hass: HomeAssistant,
        _config: ConfigType,
        async_add_entities: AddEntitiesCallback,
        _discovery_info=None,
):
    """Set up the Sensor platform from YAML."""

    sensors = []

    # ─── Pico sensors ─────────────────────────────────────────────
    coordinators = hass.data[DOMAIN].get("coordinators", [])
    _LOGGER.debug("Setting up sensor platform: %d Pico coordinator(s)", len(coordinators))
    for idx, coordinator in enumerate(coordinators):
        sensors.extend([
            PicoTemperatureSensor(coordinator, idx),
            PicoHumiditySensor(coordinator, idx),
            PicoAirQualitySensor(coordinator, idx),
            PicoTVOCSensor(coordinator, idx),
            PicoECO2Sensor(coordinator, idx),
        ])

    # ─── Polaris sensors (per-zone temp/humidity + device mode) ───
    verbose = hass.data[DOMAIN].get("config", {}).get("verbose", False)
    polaris_coordinators = hass.data[DOMAIN].get("polaris_coordinators", [])
    _LOGGER.debug("Setting up sensor platform: %d Polaris coordinator(s)", len(polaris_coordinators))
    for coordinator in polaris_coordinators:
        zones = coordinator.data.zones if coordinator.data else []
        if verbose:
            _LOGGER.debug(
                "[Polaris][%s] Setting up sensors: %d zone(s) found",
                coordinator.device_name, len(zones),
            )
        for zone in zones:
            if verbose:
                _LOGGER.debug(
                    "[Polaris][%s] Adding temp+humidity sensors for zone '%s' (id=%d, "
                    "current_temp=%s, humidity=%s)",
                    coordinator.device_name, zone.name, zone.zone_id,
                    zone.current_temp, zone.humidity,
                )
            sensors.append(PolarisZoneTemperatureSensor(coordinator, zone.zone_id))
            sensors.append(PolarisZoneHumiditySensor(coordinator, zone.zone_id))
        # Device-level operating mode sensor
        sensors.append(PolarisOperatingModeSensor(coordinator))
        if verbose:
            _LOGGER.debug(
                "[Polaris][%s] Adding operating mode sensor (current mode=%s, is_off=%s, is_cooling=%s)",
                coordinator.device_name,
                coordinator.data.device.cooling_mode_name if coordinator.data else "unknown",
                coordinator.data.device.is_off if coordinator.data else "unknown",
                coordinator.data.device.is_cooling if coordinator.data else "unknown",
            )

    async_add_entities(sensors)
    _LOGGER.info("Added %d sensor(s)", len(sensors))


class PicoTemperatureSensor(BaseEntity, SensorEntity):
    """Representation of a Pico Temperature Sensor."""

    _attr_translation_key = "temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the sensor."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_temperature_{coordinator.family_name}"
        self._attr_name = f"{coordinator.device_name} - Temperature"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data or not self.coordinator.data.sensors or self.coordinator.data.sensors.temperature is None:
            return None
        return self.coordinator.data.sensors.temperature_celsius


class PicoHumiditySensor(BaseEntity, SensorEntity):
    """Representation of a Pico Humidity Sensor."""

    _attr_translation_key = "humidity"
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the sensor."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_humidity_{coordinator.family_name}"
        self._attr_name = f"{coordinator.device_name} - Humidity"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data or not self.coordinator.data.sensors or self.coordinator.data.sensors.humidity is None:
            return None
        return self.coordinator.data.sensors.humidity_percent


class PicoAirQualitySensor(BaseEntity, SensorEntity):
    """Representation of a Pico Air Quality (CO2) Sensor."""

    _attr_translation_key = "air_quality"
    _attr_device_class = SensorDeviceClass.CO2
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the sensor."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_air_quality_{coordinator.family_name}"
        self._attr_name = f"{coordinator.device_name} - CO2"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data or not self.coordinator.data.sensors or self.coordinator.data.sensors.air_quality is None:
            return None
        return self.coordinator.data.sensors.air_quality


class PicoTVOCSensor(BaseEntity, SensorEntity):
    """Representation of a Pico TVOC (Total Volatile Organic Compounds) Sensor."""

    _attr_translation_key = "tvoc"
    _attr_device_class = SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the sensor."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_tvoc_{coordinator.family_name}"
        self._attr_name = f"{coordinator.device_name} - TVOC"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data or not self.coordinator.data.sensors or self.coordinator.data.sensors.tvoc is None:
            return None
        return self.coordinator.data.sensors.tvoc

    @property
    def icon(self) -> str:
        """Return the icon based on TVOC level."""
        if not self.coordinator.data or not self.coordinator.data.sensors or self.coordinator.data.sensors.tvoc is None:
            return "mdi:chemical-weapon"

        tvoc = self.coordinator.data.sensors.tvoc

        # TVOC level thresholds (ppb or µg/m³)
        # < 220: Excellent
        # 220-660: Good
        # 660-2200: Moderate
        # 2200-5500: Poor
        # > 5500: Very Poor

        if tvoc < 220:
            return "mdi:air-filter"
        elif tvoc < 660:
            return "mdi:chemical-weapon"
        elif tvoc < 2200:
            return "mdi:alert-circle-outline"
        elif tvoc < 5500:
            return "mdi:alert"
        else:
            return "mdi:alert-octagon"


class PicoECO2Sensor(BaseEntity, SensorEntity):
    """Representation of a Pico eCO2 (equivalent CO2) Sensor."""

    _attr_translation_key = "eco2"
    _attr_device_class = SensorDeviceClass.CO2
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: MainCoordinator, device_index: int):
        """Initialize the sensor."""
        super().__init__(coordinator, device_index)

        self._attr_unique_id = f"{DOMAIN}_eco2_{coordinator.family_name}"
        self._attr_name = f"{coordinator.device_name} - eCO2"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data or not self.coordinator.data.sensors or self.coordinator.data.sensors.eco2 is None:
            return None
        return self.coordinator.data.sensors.eco2

    @property
    def icon(self) -> str:
        """Return the icon based on eCO2 level."""
        if not self.coordinator.data or not self.coordinator.data.sensors or self.coordinator.data.sensors.eco2 is None:
            return "mdi:molecule-co2"

        eco2 = self.coordinator.data.sensors.eco2

        # eCO2 level thresholds (ppm) - similar to CO2
        # < 600: Excellent
        # 600-1000: Good
        # 1000-1500: Moderate
        # 1500-2000: Poor
        # > 2000: Very Poor

        if eco2 < 600:
            return "mdi:air-filter"
        elif eco2 < 1000:
            return "mdi:molecule-co2"
        elif eco2 < 1500:
            return "mdi:alert-circle-outline"
        elif eco2 < 2000:
            return "mdi:alert"
        else:
            return "mdi:alert-octagon"


# ═══════════════════════════════════════════════════════════════════════
# Polaris sensors
# ═══════════════════════════════════════════════════════════════════════


class PolarisZoneTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Temperature sensor for a Polaris zone."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1
    _attr_has_entity_name = True

    def __init__(self, coordinator, zone_id: int):
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._coordinator = coordinator
        self._attr_unique_id = f"polaris_{coordinator.serial}_zone_{zone_id}_temp"

    @property
    def _zone(self):
        if not self.coordinator.data:
            return None
        for z in self.coordinator.data.zones:
            if z.zone_id == self._zone_id:
                return z
        return None

    @property
    def available(self) -> bool:
        return super().available and self._zone is not None

    @property
    def name(self) -> str:
        zone = self._zone
        zone_name = zone.name.strip() if zone else f"Zone {self._zone_id}"
        return f"{zone_name} Temperature"

    @property
    def native_value(self) -> float | None:
        zone = self._zone
        return zone.current_temp if zone else None

    @property
    def device_info(self):
        dev = self.coordinator.data.device if self.coordinator.data else None
        return {
            "identifiers": {(DOMAIN, f"polaris_{self._coordinator.serial}")},
            "name": dev.name if dev else f"Polaris {self._coordinator.serial}",
            "manufacturer": "Tecnosystemi",
            "model": "Polaris 5",
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class PolarisZoneHumiditySensor(CoordinatorEntity, SensorEntity):
    """Humidity sensor for a Polaris zone."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 0
    _attr_has_entity_name = True

    def __init__(self, coordinator, zone_id: int):
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._coordinator = coordinator
        self._attr_unique_id = f"polaris_{coordinator.serial}_zone_{zone_id}_humidity"

    @property
    def _zone(self):
        if not self.coordinator.data:
            return None
        for z in self.coordinator.data.zones:
            if z.zone_id == self._zone_id:
                return z
        return None

    @property
    def available(self) -> bool:
        return super().available and self._zone is not None

    @property
    def name(self) -> str:
        zone = self._zone
        zone_name = zone.name.strip() if zone else f"Zone {self._zone_id}"
        return f"{zone_name} Humidity"

    @property
    def native_value(self) -> float | None:
        zone = self._zone
        return zone.humidity if zone else None

    @property
    def device_info(self):
        dev = self.coordinator.data.device if self.coordinator.data else None
        return {
            "identifiers": {(DOMAIN, f"polaris_{self._coordinator.serial}")},
            "name": dev.name if dev else f"Polaris {self._coordinator.serial}",
            "manufacturer": "Tecnosystemi",
            "model": "Polaris 5",
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class PolarisOperatingModeSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the Polaris CU operating mode (heating/cooling type)."""

    _attr_translation_key = "polaris_operating_mode"
    _attr_has_entity_name = True
    _attr_icon = "mdi:thermostat"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._attr_unique_id = f"polaris_{coordinator.serial}_operating_mode"

    @property
    def native_value(self) -> str | None:
        dev = self.coordinator.data.device if self.coordinator.data else None
        if not dev:
            return None
        return POLARIS_COOLING_MODES.get(dev.operating_mode, "unknown")

    @property
    def extra_state_attributes(self):
        dev = self.coordinator.data.device if self.coordinator.data else None
        if not dev:
            return {}
        return {
            "operating_mode_id": dev.operating_mode,
            "is_cooling": dev.is_cooling,
            "is_off": dev.is_off,
            "firmware": dev.fw_ver,
            "serial": dev.serial,
        }

    @property
    def device_info(self):
        dev = self.coordinator.data.device if self.coordinator.data else None
        return {
            "identifiers": {(DOMAIN, f"polaris_{self._coordinator.serial}")},
            "name": dev.name if dev else f"Polaris {self._coordinator.serial}",
            "manufacturer": "Tecnosystemi",
            "model": "Polaris 5",
            "sw_version": dev.fw_ver if dev else None,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()