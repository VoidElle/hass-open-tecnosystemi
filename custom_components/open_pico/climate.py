"""Climate platform for Polaris 5X devices (local TCP port 1235).

Two entity types:
- PolarisMainClimate: one per CU - controls global machine on/off, heat/cool mode,
  and cooling sub-mode (Raffrescamento / Deumidificazione / Ventilazione).
- PolarisZoneClimate: one per zone - controls individual zone on/off and target temp.
  Zone on/off is independent of the machine (upd_zona, not upd_cu).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from open_polaris_local_api import PolarisZone

from .const import DOMAIN
from .polaris_coordinator import PolarisCoordinator

_LOGGER = logging.getLogger(__name__)


# HVAC mode <-> (is_cooling, cool_mod) mapping
_HVAC_TO_CU: dict[HVACMode, tuple[bool, int]] = {
    HVACMode.HEAT:     (False, 0),
    HVACMode.COOL:     (True,  1),
    HVACMode.DRY:      (True,  2),
    HVACMode.FAN_ONLY: (True,  3),
}
_CU_TO_HVAC: dict[tuple[bool, int], HVACMode] = {v: k for k, v in _HVAC_TO_CU.items()}

# Serranda (damper) position mapping for swing_mode.
# MiniDiscovery2X modules report serranda via EV/EV_set fields (not shu/shu_set).
# Values: 0=Auto, 1=A1, 2=A2, 3=A3.
SERRANDA_OPTIONS = {0: "Auto", 1: "A1", 2: "A2", 3: "A3"}
SERRANDA_LABEL_TO_VALUE = {v: k for k, v in SERRANDA_OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Polaris climate entities from a config entry."""
    if entry.data.get("device_type") != "polaris":
        return

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    verbose = entry.data.get("verbose", False)
    zones = coordinator.data.zones if coordinator.data else []

    entities: list[ClimateEntity] = [PolarisMainClimate(coordinator)]
    for zone in zones:
        entities.append(PolarisZoneClimate(coordinator, zone.zone_id))
        if verbose:
            _LOGGER.debug(
                "[Polaris][%s] Adding zone climate: '%s' (id=%d)",
                coordinator.device_name, zone.name, zone.zone_id,
            )

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
    - OFF    -> upd_cu is_off=1
    - HEAT   -> upd_cu is_off=0, is_cool=0, cool_mod=0  (Riscaldamento)
    - COOL   -> upd_cu is_off=0, is_cool=1, cool_mod=1  (Raffrescamento)
    - DRY    -> upd_cu is_off=0, is_cool=1, cool_mod=2  (Deumidificazione)
    - FAN_ONLY -> upd_cu is_off=0, is_cool=1, cool_mod=3 (Ventilazione)
    """

    _attr_has_entity_name = True
    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
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
            "model": "Polaris 5X",
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
    def native_current_temperature(self) -> float | None:
        """Return canal temperature if available."""
        dev = self._device
        return float(dev.t_can) if dev and dev.t_can is not None else None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        _LOGGER.debug("[%s] set_hvac_mode: %s", self._coordinator.device_name, hvac_mode)
        if hvac_mode == HVACMode.OFF:
            await self._coordinator.async_turn_off()
        else:
            is_cooling, cool_mod = _HVAC_TO_CU[hvac_mode]
            await self._coordinator.async_set_hvac(is_cooling, cool_mod)

    async def async_turn_on(self) -> None:
        _LOGGER.debug("[%s] turn_on", self._coordinator.device_name)
        await self._coordinator.async_turn_on()

    async def async_turn_off(self) -> None:
        _LOGGER.debug("[%s] turn_off", self._coordinator.device_name)
        await self._coordinator.async_turn_off()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

# ─── Zone-level entity ───────────────────────────────────────────────────────

class PolarisZoneClimate(CoordinatorEntity[PolarisCoordinator], ClimateEntity):
    """Climate entity for a single Polaris zone.

    Controls:
    - Zone on/off independently (upd_zona is_off) - does NOT affect other zones
    - Target temperature (upd_zona t_set)

    Mode/preset are read-only here (reflect CU state) - change them via the
    PolarisMainClimate entity.

    Swing mode (serranda/damper) is enabled dynamically once zone details
    arrive from stato_zona.  This avoids fixing the feature at entity creation
    time, when details may not yet be available (see issue #23).
    """

    _attr_has_entity_name = True
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 10.0
    _attr_max_temp = 30.0
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    # OFF = zone off, AUTO = zone active (machine decides heat/cool/vent).
    # Zone entities cannot change machine mode - use PolarisMainClimate for that.
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.AUTO]

    def __init__(self, coordinator: PolarisCoordinator, zone_id: int) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._coordinator = coordinator
        self._attr_unique_id = f"polaris_{coordinator.serial}_zone_{zone_id}"
        self._has_serranda = False

    def _check_serranda_support(self) -> bool:
        """Check if this zone has a serranda (damper) based on zone details.

        Called on every coordinator update to dynamically enable/disable
        SWING_MODE when zone details arrive (they may not be available at
        entity creation time due to incremental fetching).

        Stealth2X modules report serranda via shu/shu_set (shu != -1).
        MiniDiscovery2X modules report serranda via EV/EV_set instead
        (shu is always -1 for these modules).  We check both fields.
        """
        detail = self._coordinator.zone_details.get(self._zone_id, {})
        if not detail:
            return False
        shu = detail.get("shu", -1)
        ev_set = detail.get("EV_set", -1)
        return (shu != -1) or (ev_set >= 0)

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
            "model": "Polaris 5X",
            "sw_version": dev.fw_ver if dev else None,
        }

    @property
    def native_current_temperature(self) -> float | None:
        zone = self._zone
        return zone.current_temp if zone else None

    @property
    def native_target_temperature(self) -> float | None:
        zone = self._zone
        return zone.set_temp if zone else None

    @property
    def current_humidity(self) -> float | None:
        zone = self._zone
        return zone.humidity if zone else None

    @property
    def hvac_mode(self) -> HVACMode:
        """OFF if zone or machine is off. AUTO (= zone active) otherwise."""
        zone = self._zone
        if not zone or zone.is_off:
            return HVACMode.OFF
        dev = self._device
        if dev and dev.is_off:
            return HVACMode.OFF
        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running action based on CU operating mode.

        The zone inherits its action from the CU mode.
        """
        zone = self._zone
        dev = self._device
        if not zone or zone.is_off or (dev and dev.is_off):
            return HVACAction.OFF
        if not dev:
            return HVACAction.IDLE
        mode = _CU_TO_HVAC.get((dev.is_cooling, dev.operating_mode), HVACMode.HEAT)
        if mode == HVACMode.COOL:
            return HVACAction.COOLING
        if mode == HVACMode.HEAT:
            return HVACAction.HEATING
        if mode == HVACMode.DRY:
            return HVACAction.DRYING
        if mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN
        return HVACAction.IDLE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """OFF = turn zone off (upd_zona). AUTO = turn zone on (upd_zona)."""
        _LOGGER.debug("[%s] zone %d set_hvac_mode: %s", self._coordinator.device_name, self._zone_id, hvac_mode)
        if hvac_mode == HVACMode.OFF:
            await self._coordinator.async_turn_zone_off(self._zone_id)
        else:
            await self._coordinator.async_turn_zone_on(self._zone_id)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature: float | None = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            _LOGGER.debug("[%s] zone %d set_temperature: %.1f", self._coordinator.device_name, self._zone_id, temperature)
            await self._coordinator.async_set_zone_temp(self._zone_id, temperature)

    async def async_turn_on(self) -> None:
        """Turn this zone on (upd_zona is_off=0). Other zones unaffected."""
        _LOGGER.debug("[%s] zone %d turn_on", self._coordinator.device_name, self._zone_id)
        await self._coordinator.async_turn_zone_on(self._zone_id)

    async def async_turn_off(self) -> None:
        """Turn this zone off (upd_zona is_off=1). Other zones unaffected."""
        _LOGGER.debug("[%s] zone %d turn_off", self._coordinator.device_name, self._zone_id)
        await self._coordinator.async_turn_zone_off(self._zone_id)

    @property
    def swing_mode(self) -> str | None:
        """Return current serranda (damper) position.

        Reads from coordinator.zone_details (the stato_zona cache),
        falling back to EV_set for MiniDiscovery2X zones where
        shu_set is always -1.  The coordinator merges shu/shu_set
        into zone objects for command purposes, but the UI position
        must also cover the EV_set case.
        """
        if not self._has_serranda:
            return None
        detail = self._coordinator.zone_details.get(self._zone_id, {})
        if not detail:
            return None
        value = detail.get("shu_set", -1)
        if value == -1:
            value = detail.get("EV_set", -1)
        return SERRANDA_OPTIONS.get(value, "Auto")

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set serranda (damper) position: Auto, A1, A2, A3."""
        value = SERRANDA_LABEL_TO_VALUE.get(swing_mode)
        if value is None:
            _LOGGER.error("Unknown serranda option: %s", swing_mode)
            return
        _LOGGER.debug(
            "[Polaris] zone %d set_swing_mode: %s (%d)",
            self._zone_id, swing_mode, value,
        )
        await self._coordinator.async_set_zone_serranda(self._zone_id, value)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        Dynamically enable/disable SWING_MODE based on zone details.
        Zone details may arrive after entity creation (incremental fetching),
        so we check on every update rather than only in __init__.
        """
        has_serranda = self._check_serranda_support()
        if has_serranda != self._has_serranda:
            self._has_serranda = has_serranda
            if has_serranda:
                self._attr_supported_features |= ClimateEntityFeature.SWING_MODE
                self._attr_swing_modes = list(SERRANDA_OPTIONS.values())
                _LOGGER.info(
                    "[Polaris] Zone %d: serranda enabled dynamically",
                    self._zone_id,
                )
            else:
                self._attr_supported_features &= ~ClimateEntityFeature.SWING_MODE
                self._attr_swing_modes = None
                _LOGGER.info(
                    "[Polaris] Zone %d: serranda disabled",
                    self._zone_id,
                )
        self.async_write_ha_state()
