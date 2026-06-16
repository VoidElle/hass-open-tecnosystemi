"""Tests for PicoFan entity."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.open_pico.fan import PicoFan
from custom_components.open_pico.const import DOMAIN, MODE_INT_TO_PRESET, MODE_PRESET_TO_INT
from tests.conftest import make_pico_operating


@pytest.fixture
def fan(pico_coordinator):
    return PicoFan(pico_coordinator, 0)


class TestPicoFanAttributes:
    def test_unique_id(self, fan, pico_coordinator):
        assert fan.unique_id == f"{DOMAIN}_fan_{pico_coordinator.family_name}"

    def test_name(self, fan):
        assert fan._attr_translation_key == "pico"

    def test_preset_modes_complete(self, fan):
        assert set(fan.preset_modes) == set(MODE_PRESET_TO_INT.keys())
        assert len(fan.preset_modes) == 12


class TestPicoFanState:
    def test_is_on_when_device_on(self, fan, pico_coordinator):
        pico_coordinator.data.is_on = True
        assert fan.is_on is True

    def test_is_off_when_device_off(self, fan, pico_coordinator):
        pico_coordinator.data.is_on = False
        assert fan.is_on is False

    def test_preset_mode_returns_mapped_string(self, fan, pico_coordinator):
        pico_coordinator.data.operating.mode.value = 1
        assert fan.preset_mode == "heat_recovery"

    def test_preset_mode_no_data(self, fan, pico_coordinator):
        pico_coordinator.data = None
        assert fan.preset_mode is None

    def test_preset_mode_none_mode(self, fan, pico_coordinator):
        pico_coordinator.data.operating.mode = None
        # current_mode delegates to data
        pico_coordinator.data = MagicMock()
        pico_coordinator.data.operating = MagicMock()
        pico_coordinator.data.operating.mode = None
        # Override coordinator.current_mode to return None
        type(pico_coordinator).current_mode = property(lambda self: None)
        assert fan.preset_mode is None

    def test_speed_count_with_fan_speed_support(self, fan, pico_coordinator):
        pico_coordinator.data.support_fan_speed_control = True
        pico_coordinator.data.operating.night_mode = 0
        assert fan.speed_count == 100

    def test_speed_count_without_fan_speed_support(self, fan, pico_coordinator):
        pico_coordinator.data.support_fan_speed_control = False
        assert fan.speed_count == 1

    def test_speed_count_night_mode(self, fan, pico_coordinator):
        pico_coordinator.data.support_fan_speed_control = True
        pico_coordinator.data.operating.night_mode = 1
        assert fan.speed_count == 1

    def test_percentage_with_speed_support(self, fan, pico_coordinator):
        pico_coordinator.data.support_fan_speed_control = True
        pico_coordinator.data.operating.night_mode = 0
        pico_coordinator.data.operating.speed_requested = 75
        assert fan.percentage == 75

    def test_percentage_on_without_speed_support(self, fan, pico_coordinator):
        pico_coordinator.data.support_fan_speed_control = False
        pico_coordinator.data.is_on = True
        assert fan.percentage == 100

    def test_percentage_off_without_speed_support(self, fan, pico_coordinator):
        pico_coordinator.data.support_fan_speed_control = False
        pico_coordinator.data.is_on = False
        assert fan.percentage == 0


class TestPicoFanControl:
    async def test_set_percentage_zero_turns_off(self, fan, pico_coordinator):
        pico_coordinator.async_turn_off = AsyncMock()
        await fan.async_set_percentage(0)
        pico_coordinator.async_turn_off.assert_called_once()

    async def test_set_percentage_turns_on_if_off(self, fan, pico_coordinator):
        pico_coordinator.data.is_on = False
        pico_coordinator.async_turn_on = AsyncMock()
        pico_coordinator.data.support_fan_speed_control = True
        pico_coordinator.data.operating.night_mode = 0
        pico_coordinator.async_set_fan_speed = AsyncMock()

        await fan.async_set_percentage(60)
        pico_coordinator.async_turn_on.assert_called_once()

    async def test_set_percentage_calls_set_fan_speed(self, fan, pico_coordinator):
        pico_coordinator.data.is_on = True
        pico_coordinator.data.support_fan_speed_control = True
        pico_coordinator.data.operating.night_mode = 0
        pico_coordinator.async_set_fan_speed = AsyncMock()

        await fan.async_set_percentage(80)
        pico_coordinator.async_set_fan_speed.assert_called_once_with(80)

    async def test_set_percentage_unsupported_mode_raises(self, fan, pico_coordinator):
        pico_coordinator.data.is_on = True
        pico_coordinator.data.support_fan_speed_control = False
        with pytest.raises(HomeAssistantError, match="does not support fan speed"):
            await fan.async_set_percentage(50)

    async def test_set_percentage_night_mode_raises(self, fan, pico_coordinator):
        pico_coordinator.data.is_on = True
        pico_coordinator.data.support_fan_speed_control = True
        pico_coordinator.data.operating.night_mode = 1
        with pytest.raises(HomeAssistantError, match="night mode"):
            await fan.async_set_percentage(50)

    async def test_set_preset_mode_valid(self, fan, pico_coordinator):
        pico_coordinator.async_set_mode = AsyncMock()
        await fan.async_set_preset_mode("extraction")
        pico_coordinator.async_set_mode.assert_called_once()

    async def test_set_preset_mode_invalid_raises(self, fan):
        with pytest.raises(ValueError, match="Invalid mode"):
            await fan.async_set_preset_mode("nonexistent_mode")

    async def test_turn_on_basic(self, fan, pico_coordinator):
        pico_coordinator.async_turn_on = AsyncMock()
        await fan.async_turn_on()
        pico_coordinator.async_turn_on.assert_called_once()

    async def test_turn_on_with_preset(self, fan, pico_coordinator):
        pico_coordinator.async_turn_on = AsyncMock()
        pico_coordinator.async_set_mode = AsyncMock()
        await fan.async_turn_on(preset_mode="extraction")
        pico_coordinator.async_turn_on.assert_called_once()
        pico_coordinator.async_set_mode.assert_called_once()

    async def test_turn_off(self, fan, pico_coordinator):
        pico_coordinator.async_turn_off = AsyncMock()
        await fan.async_turn_off()
        pico_coordinator.async_turn_off.assert_called_once()
