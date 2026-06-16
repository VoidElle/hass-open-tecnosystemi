"""Tests for select entities (Preset Mode, Target Humidity)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.open_pico.select import PicoTargetHumiditySelect, PicoPresetModeSelect
from custom_components.open_pico.const import DOMAIN, TARGET_HUMIDITY_OPTIONS, MODE_PRESET_TO_INT


@pytest.fixture
def humidity_select(pico_coordinator):
    return PicoTargetHumiditySelect(pico_coordinator, 0)


@pytest.fixture
def preset_select(pico_coordinator):
    return PicoPresetModeSelect(pico_coordinator, 0)


class TestTargetHumiditySelect:
    def test_unique_id(self, humidity_select, pico_coordinator):
        assert humidity_select.unique_id == f"{DOMAIN}_target_humidity_{pico_coordinator.family_name}"

    def test_name(self, humidity_select):
        assert humidity_select._attr_translation_key == "target_humidity"

    def test_options_are_percentage_strings(self, humidity_select):
        assert set(humidity_select.options) == {"40%", "50%", "60%"}

    def test_available_when_supported(self, humidity_select, pico_coordinator):
        pico_coordinator.data.support_target_humidity_selection = True
        assert humidity_select.available is True

    def test_not_available_when_unsupported(self, humidity_select, pico_coordinator):
        pico_coordinator.data.support_target_humidity_selection = False
        assert humidity_select.available is False

    def test_current_option_50(self, humidity_select, pico_coordinator):
        pico_coordinator.data.sensors.humidity_setpoint = 2
        assert humidity_select.current_option == "50%"

    def test_current_option_40(self, humidity_select, pico_coordinator):
        pico_coordinator.data.sensors.humidity_setpoint = 1
        assert humidity_select.current_option == "40%"

    def test_current_option_60(self, humidity_select, pico_coordinator):
        pico_coordinator.data.sensors.humidity_setpoint = 3
        assert humidity_select.current_option == "60%"

    def test_current_option_no_data(self, humidity_select, pico_coordinator):
        pico_coordinator.data = None
        assert humidity_select.current_option is None

    async def test_select_option_valid(self, humidity_select, pico_coordinator):
        pico_coordinator.data.support_target_humidity_selection = True
        pico_coordinator.async_set_target_humidity = AsyncMock()
        await humidity_select.async_select_option("50%")
        pico_coordinator.async_set_target_humidity.assert_called_once()

    async def test_select_option_unsupported_raises(self, humidity_select, pico_coordinator):
        pico_coordinator.data.support_target_humidity_selection = False
        pico_coordinator.data.operating.mode.name = "extraction"
        with pytest.raises(HomeAssistantError, match="does not support target humidity"):
            await humidity_select.async_select_option("50%")

    async def test_select_option_invalid_value_raises(self, humidity_select, pico_coordinator):
        pico_coordinator.data.support_target_humidity_selection = True
        with pytest.raises(ValueError, match="Invalid humidity option"):
            await humidity_select.async_select_option("99%")

    async def test_select_option_wraps_error(self, humidity_select, pico_coordinator):
        pico_coordinator.data.support_target_humidity_selection = True
        pico_coordinator.async_set_target_humidity = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(HomeAssistantError):
            await humidity_select.async_select_option("40%")


class TestPresetModeSelect:
    def test_unique_id(self, preset_select, pico_coordinator):
        assert preset_select.unique_id == f"{DOMAIN}_preset_mode_{pico_coordinator.family_name}"

    def test_name(self, preset_select):
        assert preset_select._attr_translation_key == "preset_mode"

    def test_options_all_12_modes(self, preset_select):
        assert len(preset_select.options) == 12
        assert set(preset_select.options) == set(MODE_PRESET_TO_INT.keys())

    def test_current_option_from_mode(self, preset_select, pico_coordinator):
        pico_coordinator.data.operating.mode.value = 2
        # current_mode delegates to operating.mode
        type(pico_coordinator).current_mode = property(
            lambda self: self.data.operating.mode
        )
        assert preset_select.current_option == "extraction"

    def test_current_option_no_data(self, preset_select, pico_coordinator):
        pico_coordinator.data = None
        assert preset_select.current_option is None

    async def test_select_valid_mode(self, preset_select, pico_coordinator):
        pico_coordinator.async_set_mode = AsyncMock()
        await preset_select.async_select_option("heat_recovery")
        pico_coordinator.async_set_mode.assert_called_once()

    async def test_select_invalid_mode_raises(self, preset_select):
        with pytest.raises(ValueError, match="Invalid mode"):
            await preset_select.async_select_option("unknown_mode")

    async def test_select_option_wraps_error(self, preset_select, pico_coordinator):
        pico_coordinator.async_set_mode = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(HomeAssistantError):
            await preset_select.async_select_option("extraction")
