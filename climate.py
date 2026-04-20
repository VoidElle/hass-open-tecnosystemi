"""Climate platform for Polaris 5 zones (local TCP port 1235).

Each Polaris zone is exposed as a HA Climate entity with:
- HVAC modes: off, heat, cool
- Temperature control: 10-30°C, step 0.5
- Current temperature reading
- Current humidity reading (if available)
- Preset modes for cooling sub-modes (Raffrescamento, Deumidificazione, Ventilazione)
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .polaris_coordinator import PolarisCoordinator, PolarisData
from .polaris_api.models import PolarisZone

_LOGGER = logging.getLogger(__name__)

# Cooling sub-mode presets
PRESET_RAFFRESCAMENTO = "Raffrescamento"
PRESET_DEUMIDIFICAZIONE = "Deumidificazione"
PRESET_VENTILAZIONE = "Ventilazione"

_COOLING_PRESETS = [PRESET_RAFFRESCAMENTO, PRESET_DEUMIDIFICAZIONE, PRESET_VENTILAZIONE]
_PRESET_TO_MODE = {
    PRESET_RAFFRESCAMENTO: 1,
    PRESET_DEUMIDIFICAZIONE: 2,
    PRESET_VENTILAZIONE: 3,
}
_MODE_TO_PRESET = {v: k for k, v in _PRESET_TO_MODE.items()}


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Polaris climate entities from discovery."""
    if DOMAIN not in hass.data:
        return

    polaris_coordinators: list[PolarisCoordinator] = hass.data[DOMAIN].get("polaris_coordinators", [])

    entities: list[PolarisZoneClimate] = []

    for coordinator in polaris_coordinators:
        if coordinator.data and coordinator.data.zones:
            for zone in coordinator.data.zones:
                entities.append(PolarisZoneClimate(coordinator, zone.zone_id))
                _LOGGER.debug(
                    "Adding Polaris zone climate: %s (zone_id=%d)",
                    zone.name, zone.zone_id,
                )

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d Polaris zone climate entities", len(entities))


class PolarisZoneClimate(CoordinatorEntity[PolarisCoordinator], ClimateEntity):
    """Climate entity for a single Polaris zone."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 10.0
    _attr_max_temp = 30.0
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    _attr_preset_modes = _COOLING_PRESETS

    def __init__(self, coordinator: PolarisCoordinator, zone_id: int) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._coordinator = coordinator

        # Use serial + zone_id for unique identification
        self._attr_unique_id = f"polaris_{coordinator.serial}_zone_{zone_id}"

    @property
    def _zone(self) -> PolarisZone | None:
        """Get the current zone data from coordinator."""
        if not self.coordinator.data:
            return None
        for z in self.coordinator.data.zones:
            if z.zone_id == self._zone_id:
                return z
        return None

    @property
    def _device_data(self):
        """Get device-level data."""
        return self.coordinator.data.device if self.coordinator.data else None

    # ─── Entity properties ───────────────────────────────────────────

    @property
    def name(self) -> str:
        """Return zone name."""
        zone = self._zone
        return zone.name.strip() if zone else f"Zone {self._zone_id}"

    @property
    def available(self) -> bool:
        """Return True if zone data is available."""
        return super().available and self._zone is not None

    @property
    def device_info(self):
        """Return device info for the parent CU."""
        dev = self._device_data
        return {
            "identifiers": {(DOMAIN, f"polaris_{self._coordinator.serial}")},
            "name": dev.name if dev else f"Polaris {self._coordinator.serial}",
            "manufacturer": "Tecnosystemi",
            "model": "Polaris 5",
            "sw_version": dev.fw_ver if dev else None,
        }

    # ─── Climate state ───────────────────────────────────────────────

    @property
    def current_temperature(self) -> float | None:
        """Return current zone temperature."""
        zone = self._zone
        return zone.current_temp if zone else None

    @property
    def target_temperature(self) -> float | None:
        """Return target zone temperature."""
        zone = self._zone
        return zone.set_temp if zone else None

    @property
    def current_humidity(self) -> float | None:
        """Return current humidity if available."""
        zone = self._zone
        return zone.humidity if zone else None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        zone = self._zone
        if not zone or zone.is_off:
            return HVACMode.OFF

        dev = self._device_data
        if dev and dev.is_cooling and dev.operating_mode > 0:
            return HVACMode.COOL
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action."""
        zone = self._zone
        if not zone or zone.is_off:
            return HVACAction.OFF

        dev = self._device_data
        if dev and dev.is_cooling:
            return HVACAction.COOLING
        return HVACAction.HEATING

    @property
    def preset_mode(self) -> str | None:
        """Return current cooling preset if in cooling mode."""
        dev = self._device_data
        if dev and dev.is_cooling and dev.operating_mode in _MODE_TO_PRESET:
            return _MODE_TO_PRESET[dev.operating_mode]
        return None

    # ─── Climate actions ─────────────────────────────────────────────

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self._coordinator.async_turn_zone_off(self._zone_id)
        elif hvac_mode == HVACMode.HEAT:
            await self._coordinator.async_set_heating_mode()
            await self._coordinator.async_turn_zone_on(self._zone_id)
        elif hvac_mode == HVACMode.COOL:
            # Default to Raffrescamento when switching to cool
            dev = self._device_data
            current_mode = dev.operating_mode if dev else 0
            if current_mode == 0:
                await self._coordinator.async_set_cooling_mode(1)
            await self._coordinator.async_turn_zone_on(self._zone_id)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self._coordinator.async_set_zone_temp(self._zone_id, temperature)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set cooling sub-mode preset."""
        mode = _PRESET_TO_MODE.get(preset_mode)
        if mode is not None:
            await self._coordinator.async_set_cooling_mode(mode)

    async def async_turn_on(self) -> None:
        """Turn zone on."""
        await self._coordinator.async_turn_zone_on(self._zone_id)

    async def async_turn_off(self) -> None:
        """Turn zone off."""
        await self._coordinator.async_turn_zone_off(self._zone_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
