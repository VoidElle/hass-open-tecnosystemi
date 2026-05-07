"""Climate platform for Polaris 5 devices (local TCP port 1235).

Two entity types:
- PolarisMainClimate: one per CU — controls global machine on/off, heat/cool mode,
  and cooling sub-mode (Raffrescamento / Deumidificazione / Ventilazione).
- PolarisZoneClimate: one per zone — controls individual zone on/off and target temp.
  Zone on/off is independent from the machine (upd_zona, not upd_cu).
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
from .polaris_coordinator import PolarisCoordinator
from .polaris_api.models import PolarisZone

_LOGGER = logging.getLogger(__name__)


# HVAC mode <-> (is_cooling, cool_mod) mapping
_HVAC_TO_CU: dict[HVACMode, tuple[bool, int]] = {
    HVACMode.HEAT:     (False, 0),
    HVACMode.COOL:     (True,  1),
    HVACMode.DRY:      (True,  2),
    HVACMode.FAN_ONLY: (True,  3),
}
_CU_TO_HVAC: dict[tuple[bool, int], HVACMode] = {v: k for k, v in _HVAC_TO_CU.items()}


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
    verbose = hass.data[DOMAIN].get("config", {}).get("verbose", False)

    entities: list[ClimateEntity] = []

    for coordinator in polaris_coordinators:
        zones = coordinator.data.zones if coordinator.data else []

        # One machine-level entity per CU
        entities.append(PolarisMainClimate(coordinator))
        _LOGGER.debug(
            "Adding Polaris main climate: %s",
            coordinator.device_name,
        )

        # One zone-level entity per zone
        for zone in zones:
            entities.append(PolarisZoneClimate(coordinator, zone.zone_id))
            _LOGGER.debug(
                "Adding Polaris zone climate: %s (zone_id=%d)",
                zone.name, zone.zone_id,
            )
            if verbose:
                _LOGGER.debug(
                    "[Polaris][%s] Zone '%s' (id=%d): is_off=%s, set_temp=%s, "
                    "current_temp=%s, fancoil=%s, serranda=%s",
                    coordinator.device_name, zone.name, zone.zone_id,
                    zone.is_off, zone.set_temp, zone.current_temp,
                    zone.fancoil, zone.serranda,
                )

    if entities:
        async_add_entities(entities)
        _LOGGER.info(
            "Added %d Polaris climate entities (%d CU + %d zones)",
            len(entities),
            sum(1 for e in entities if isinstance(e, PolarisMainClimate)),
            sum(1 for e in entities if isinstance(e, PolarisZoneClimate)),
        )


# ─── Machine-level entity ────────────────────────────────────────────────────

class PolarisMainClimate(CoordinatorEntity[PolarisCoordinator], ClimateEntity):
    """Climate entity for the Polaris CU (global machine).

    Controls:
    - OFF    → upd_cu is_off=1
    - HEAT   → upd_cu is_off=0, is_cool=0, cool_mod=0  (Riscaldamento)
    - COOL   → upd_cu is_off=0, is_cool=1, cool_mod=1  (Raffrescamento)
    - DRY    → upd_cu is_off=0, is_cool=1, cool_mod=2  (Deumidificazione)
    - FAN_ONLY → upd_cu is_off=0, is_cool=1, cool_mod=3 (Ventilazione)
    """

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]

    def __init__(self, coordinator: PolarisCoordinator) -> None:
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._attr_unique_id = f"polaris_{coordinator.serial}_main"

    @property
    def _device(self):
        return self.coordinator.data.device if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return super().available and self._device is not None

    @property
    def device_info(self):
        dev = self._device
        return {
            "identifiers": {(DOMAIN, f"polaris_{self._coordinator.serial}")},
            "name": dev.name if dev else f"Polaris {self._coordinator.serial}",
            "manufacturer": "Tecnosystemi",
            "model": "Polaris 5",
            "sw_version": dev.fw_ver if dev else None,
        }

    @property
    def hvac_mode(self) -> HVACMode:
        dev = self._device
        if not dev or dev.is_off:
            return HVACMode.OFF
        return _CU_TO_HVAC.get((dev.is_cooling, dev.operating_mode), HVACMode.HEAT)

    @property
    def hvac_action(self) -> HVACAction | None:
        dev = self._device
        if not dev or dev.is_off:
            return HVACAction.OFF
        mode = self.hvac_mode
        if mode == HVACMode.COOL:
            return HVACAction.COOLING
        if mode == HVACMode.HEAT:
            return HVACAction.HEATING
        if mode == HVACMode.DRY:
            return HVACAction.DRYING
        if mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        """Return canal temperature if available."""
        dev = self._device
        return float(dev.t_can) if dev and dev.t_can else None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._coordinator.async_turn_off()
        else:
            is_cooling, cool_mod = _HVAC_TO_CU[hvac_mode]
            await self._coordinator.client.update_cu(
                is_off=False,
                is_cooling=is_cooling,
                operating_mode=cool_mod,
            )
            await self._coordinator.async_request_refresh()


    async def async_turn_on(self) -> None:
        await self._coordinator.async_turn_on()

    async def async_turn_off(self) -> None:
        await self._coordinator.async_turn_off()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


# ─── Zone-level entity ───────────────────────────────────────────────────────

class PolarisZoneClimate(CoordinatorEntity[PolarisCoordinator], ClimateEntity):
    """Climate entity for a single Polaris zone.

    Controls:
    - Zone on/off independently (upd_zona is_off) — does NOT affect other zones
    - Target temperature (upd_zona t_set)

    Mode/preset are read-only here (reflect CU state) — change them via the
    PolarisMainClimate entity.
    """

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 10.0
    _attr_max_temp = 30.0
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    # OFF = zone off, FAN_ONLY = zone active (machine decides heat/cool/vent).
    # Zone entities cannot change machine mode — use PolarisMainClimate for that.
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.FAN_ONLY]

    def __init__(self, coordinator: PolarisCoordinator, zone_id: int) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._coordinator = coordinator
        self._attr_unique_id = f"polaris_{coordinator.serial}_zone_{zone_id}"

    @property
    def _zone(self) -> PolarisZone | None:
        if not self.coordinator.data:
            return None
        for z in self.coordinator.data.zones:
            if z.zone_id == self._zone_id:
                return z
        return None

    @property
    def _device(self):
        return self.coordinator.data.device if self.coordinator.data else None

    @property
    def name(self) -> str:
        zone = self._zone
        return zone.name.strip() if zone else f"Zone {self._zone_id}"

    @property
    def available(self) -> bool:
        return super().available and self._zone is not None

    @property
    def device_info(self):
        dev = self._device
        return {
            "identifiers": {(DOMAIN, f"polaris_{self._coordinator.serial}")},
            "name": dev.name if dev else f"Polaris {self._coordinator.serial}",
            "manufacturer": "Tecnosystemi",
            "model": "Polaris 5",
            "sw_version": dev.fw_ver if dev else None,
        }

    @property
    def current_temperature(self) -> float | None:
        zone = self._zone
        return zone.current_temp if zone else None

    @property
    def target_temperature(self) -> float | None:
        zone = self._zone
        return zone.set_temp if zone else None

    @property
    def current_humidity(self) -> float | None:
        zone = self._zone
        return zone.humidity if zone else None

    @property
    def hvac_mode(self) -> HVACMode:
        """OFF if zone or machine is off. FAN_ONLY (= zone active) otherwise."""
        zone = self._zone
        if not zone or zone.is_off:
            return HVACMode.OFF
        dev = self._device
        if dev and dev.is_off:
            return HVACMode.OFF
        return HVACMode.FAN_ONLY

    @property
    def hvac_action(self) -> HVACAction | None:
        zone = self._zone
        dev = self._device
        if not zone or zone.is_off or (dev and dev.is_off):
            return HVACAction.OFF
        return HVACAction.FAN

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """OFF = turn zone off (upd_zona). FAN_ONLY = turn zone on (upd_zona)."""
        if hvac_mode == HVACMode.OFF:
            await self._coordinator.async_turn_zone_off(self._zone_id)
        else:
            await self._coordinator.async_turn_zone_on(self._zone_id)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self._coordinator.async_set_zone_temp(self._zone_id, temperature)

    async def async_turn_on(self) -> None:
        """Turn this zone on (upd_zona is_off=0). Other zones unaffected."""
        await self._coordinator.async_turn_zone_on(self._zone_id)

    async def async_turn_off(self) -> None:
        """Turn this zone off (upd_zona is_off=1). Other zones unaffected."""
        await self._coordinator.async_turn_zone_off(self._zone_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
