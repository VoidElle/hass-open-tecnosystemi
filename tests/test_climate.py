"""Tests for climate entities (PolarisMainClimate, PolarisZoneClimate)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from homeassistant.components.climate import HVACMode, HVACAction

from custom_components.open_pico.climate import PolarisMainClimate, PolarisZoneClimate
from custom_components.open_pico.const import DOMAIN
from tests.conftest import make_polaris_device, make_polaris_zone


@pytest.fixture
def main_climate(polaris_coordinator):
    return PolarisMainClimate(polaris_coordinator)


@pytest.fixture
def zone_climate(polaris_coordinator):
    return PolarisZoneClimate(polaris_coordinator, 1)


# ─── PolarisMainClimate ───────────────────────────────────────────────────────

class TestPolarisMainClimateAttributes:
    def test_unique_id(self, main_climate, polaris_coordinator):
        assert main_climate.unique_id == f"polaris_{polaris_coordinator.serial}_main"

    def test_hvac_modes(self, main_climate):
        modes = main_climate.hvac_modes
        assert HVACMode.OFF in modes
        assert HVACMode.HEAT in modes
        assert HVACMode.COOL in modes
        assert HVACMode.DRY in modes
        assert HVACMode.FAN_ONLY in modes

    def test_device_info_has_identifiers(self, main_climate, polaris_coordinator):
        info = main_climate.device_info
        assert (DOMAIN, f"polaris_{polaris_coordinator.serial}") in info["identifiers"]


class TestPolarisMainClimateHvacMode:
    def test_hvac_mode_off_when_device_off(self, main_climate, polaris_coordinator):
        polaris_coordinator.data.device.is_off = True
        assert main_climate.hvac_mode == HVACMode.OFF

    def test_hvac_mode_no_data(self, main_climate, polaris_coordinator):
        polaris_coordinator.data = None
        assert main_climate.hvac_mode == HVACMode.OFF

    def test_hvac_mode_heat(self, main_climate, polaris_coordinator):
        polaris_coordinator.data.device.is_off = False
        polaris_coordinator.data.device.is_cooling = False
        polaris_coordinator.data.device.operating_mode = 0
        assert main_climate.hvac_mode == HVACMode.HEAT

    def test_hvac_mode_cool(self, main_climate, polaris_coordinator):
        polaris_coordinator.data.device.is_off = False
        polaris_coordinator.data.device.is_cooling = True
        polaris_coordinator.data.device.operating_mode = 1
        assert main_climate.hvac_mode == HVACMode.COOL

    def test_hvac_mode_dry(self, main_climate, polaris_coordinator):
        polaris_coordinator.data.device.is_off = False
        polaris_coordinator.data.device.is_cooling = True
        polaris_coordinator.data.device.operating_mode = 2
        assert main_climate.hvac_mode == HVACMode.DRY

    def test_hvac_mode_fan_only(self, main_climate, polaris_coordinator):
        polaris_coordinator.data.device.is_off = False
        polaris_coordinator.data.device.is_cooling = True
        polaris_coordinator.data.device.operating_mode = 3
        assert main_climate.hvac_mode == HVACMode.FAN_ONLY


class TestPolarisMainClimateHvacAction:
    def test_hvac_action_off(self, main_climate, polaris_coordinator):
        polaris_coordinator.data.device.is_off = True
        assert main_climate.hvac_action == HVACAction.OFF

    def test_hvac_action_heating(self, main_climate, polaris_coordinator):
        polaris_coordinator.data.device.is_off = False
        polaris_coordinator.data.device.is_cooling = False
        polaris_coordinator.data.device.operating_mode = 0
        assert main_climate.hvac_action == HVACAction.HEATING

    def test_hvac_action_cooling(self, main_climate, polaris_coordinator):
        polaris_coordinator.data.device.is_off = False
        polaris_coordinator.data.device.is_cooling = True
        polaris_coordinator.data.device.operating_mode = 1
        assert main_climate.hvac_action == HVACAction.COOLING

    def test_hvac_action_drying(self, main_climate, polaris_coordinator):
        polaris_coordinator.data.device.is_off = False
        polaris_coordinator.data.device.is_cooling = True
        polaris_coordinator.data.device.operating_mode = 2
        assert main_climate.hvac_action == HVACAction.DRYING

    def test_hvac_action_fan(self, main_climate, polaris_coordinator):
        polaris_coordinator.data.device.is_off = False
        polaris_coordinator.data.device.is_cooling = True
        polaris_coordinator.data.device.operating_mode = 3
        assert main_climate.hvac_action == HVACAction.FAN


class TestPolarisMainClimateCurrentTemp:
    def test_current_temperature(self, main_climate, polaris_coordinator):
        polaris_coordinator.data.device.t_can = 19.5
        assert main_climate.current_temperature == 19.5

    def test_current_temperature_none(self, main_climate, polaris_coordinator):
        polaris_coordinator.data.device.t_can = None
        assert main_climate.current_temperature is None


class TestPolarisMainClimateControl:
    async def test_set_hvac_mode_off(self, main_climate, polaris_coordinator):
        polaris_coordinator.async_turn_off = AsyncMock()
        await main_climate.async_set_hvac_mode(HVACMode.OFF)
        polaris_coordinator.async_turn_off.assert_called_once()

    async def test_set_hvac_mode_heat(self, main_climate, polaris_coordinator):
        polaris_coordinator.client.update_cu = AsyncMock()
        polaris_coordinator.async_request_refresh = AsyncMock()
        await main_climate.async_set_hvac_mode(HVACMode.HEAT)
        polaris_coordinator.client.update_cu.assert_called_once_with(
            is_off=False, is_cooling=False, operating_mode=0
        )

    async def test_set_hvac_mode_cool(self, main_climate, polaris_coordinator):
        polaris_coordinator.client.update_cu = AsyncMock()
        polaris_coordinator.async_request_refresh = AsyncMock()
        await main_climate.async_set_hvac_mode(HVACMode.COOL)
        polaris_coordinator.client.update_cu.assert_called_once_with(
            is_off=False, is_cooling=True, operating_mode=1
        )

    async def test_set_hvac_mode_dry(self, main_climate, polaris_coordinator):
        polaris_coordinator.client.update_cu = AsyncMock()
        polaris_coordinator.async_request_refresh = AsyncMock()
        await main_climate.async_set_hvac_mode(HVACMode.DRY)
        polaris_coordinator.client.update_cu.assert_called_once_with(
            is_off=False, is_cooling=True, operating_mode=2
        )

    async def test_set_hvac_mode_fan_only(self, main_climate, polaris_coordinator):
        polaris_coordinator.client.update_cu = AsyncMock()
        polaris_coordinator.async_request_refresh = AsyncMock()
        await main_climate.async_set_hvac_mode(HVACMode.FAN_ONLY)
        polaris_coordinator.client.update_cu.assert_called_once_with(
            is_off=False, is_cooling=True, operating_mode=3
        )

    async def test_turn_on(self, main_climate, polaris_coordinator):
        polaris_coordinator.async_turn_on = AsyncMock()
        await main_climate.async_turn_on()
        polaris_coordinator.async_turn_on.assert_called_once()

    async def test_turn_off(self, main_climate, polaris_coordinator):
        polaris_coordinator.async_turn_off = AsyncMock()
        await main_climate.async_turn_off()
        polaris_coordinator.async_turn_off.assert_called_once()


# ─── PolarisZoneClimate ───────────────────────────────────────────────────────

class TestPolarisZoneClimateAttributes:
    def test_unique_id(self, zone_climate, polaris_coordinator):
        assert zone_climate.unique_id == f"polaris_{polaris_coordinator.serial}_zone_1"

    def test_name_from_zone(self, zone_climate, polaris_coordinator):
        assert zone_climate.name == "Living Room"

    def test_name_fallback_when_no_data(self, zone_climate, polaris_coordinator):
        polaris_coordinator.data = None
        assert zone_climate.name == "Zone 1"

    def test_hvac_modes(self, zone_climate):
        assert HVACMode.OFF in zone_climate.hvac_modes
        assert HVACMode.AUTO in zone_climate.hvac_modes

    def test_target_temperature_step(self, zone_climate):
        assert zone_climate.target_temperature_step == 0.5

    def test_min_max_temp(self, zone_climate):
        assert zone_climate.min_temp == 10.0
        assert zone_climate.max_temp == 30.0


class TestPolarisZoneClimateState:
    def test_hvac_mode_off_when_zone_off(self, zone_climate, polaris_coordinator):
        polaris_coordinator.data.zones[0].is_off = True
        assert zone_climate.hvac_mode == HVACMode.OFF

    def test_hvac_mode_off_when_machine_off(self, zone_climate, polaris_coordinator):
        polaris_coordinator.data.zones[0].is_off = False
        polaris_coordinator.data.device.is_off = True
        assert zone_climate.hvac_mode == HVACMode.OFF

    def test_hvac_mode_auto_when_zone_on(self, zone_climate, polaris_coordinator):
        polaris_coordinator.data.zones[0].is_off = False
        polaris_coordinator.data.device.is_off = False
        assert zone_climate.hvac_mode == HVACMode.AUTO

    def test_hvac_action_off(self, zone_climate, polaris_coordinator):
        polaris_coordinator.data.zones[0].is_off = True
        assert zone_climate.hvac_action == HVACAction.OFF

    def test_hvac_action_idle(self, zone_climate, polaris_coordinator):
        polaris_coordinator.data.zones[0].is_off = False
        polaris_coordinator.data.device.is_off = False
        assert zone_climate.hvac_action == HVACAction.IDLE

    def test_current_temperature(self, zone_climate, polaris_coordinator):
        polaris_coordinator.data.zones[0].current_temp = 21.0
        assert zone_climate.current_temperature == 21.0

    def test_target_temperature(self, zone_climate, polaris_coordinator):
        polaris_coordinator.data.zones[0].set_temp = 22.0
        assert zone_climate.target_temperature == 22.0

    def test_current_humidity(self, zone_climate, polaris_coordinator):
        polaris_coordinator.data.zones[0].humidity = 55.0
        assert zone_climate.current_humidity == 55.0

    def test_available_false_when_zone_missing(self, zone_climate, polaris_coordinator):
        polaris_coordinator.data.zones = []
        assert zone_climate.available is False


class TestPolarisZoneClimateControl:
    async def test_set_hvac_mode_off(self, zone_climate, polaris_coordinator):
        polaris_coordinator.async_turn_zone_off = AsyncMock()
        await zone_climate.async_set_hvac_mode(HVACMode.OFF)
        polaris_coordinator.async_turn_zone_off.assert_called_once_with(1)

    async def test_set_hvac_mode_auto(self, zone_climate, polaris_coordinator):
        polaris_coordinator.async_turn_zone_on = AsyncMock()
        await zone_climate.async_set_hvac_mode(HVACMode.AUTO)
        polaris_coordinator.async_turn_zone_on.assert_called_once_with(1)

    async def test_set_temperature(self, zone_climate, polaris_coordinator):
        polaris_coordinator.async_set_zone_temp = AsyncMock()
        await zone_climate.async_set_temperature(temperature=22.5)
        polaris_coordinator.async_set_zone_temp.assert_called_once_with(1, 22.5)

    async def test_set_temperature_no_temp_arg(self, zone_climate, polaris_coordinator):
        polaris_coordinator.async_set_zone_temp = AsyncMock()
        await zone_climate.async_set_temperature()
        polaris_coordinator.async_set_zone_temp.assert_not_called()

    async def test_turn_on(self, zone_climate, polaris_coordinator):
        polaris_coordinator.async_turn_zone_on = AsyncMock()
        await zone_climate.async_turn_on()
        polaris_coordinator.async_turn_zone_on.assert_called_once_with(1)

    async def test_turn_off(self, zone_climate, polaris_coordinator):
        polaris_coordinator.async_turn_zone_off = AsyncMock()
        await zone_climate.async_turn_off()
        polaris_coordinator.async_turn_zone_off.assert_called_once_with(1)
