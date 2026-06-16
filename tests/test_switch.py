"""Tests for switch entities (Night Mode, LED Status)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.open_pico.switch import PicoNightModeSwitch, PicoLEDStatusSwitch
from custom_components.open_pico.const import DOMAIN


@pytest.fixture
def night_switch(pico_coordinator):
    return PicoNightModeSwitch(pico_coordinator, 0)


@pytest.fixture
def led_switch(pico_coordinator):
    return PicoLEDStatusSwitch(pico_coordinator, 0)


class TestNightModeSwitch:
    def test_unique_id(self, night_switch, pico_coordinator):
        assert night_switch.unique_id == f"{DOMAIN}_night_mode_{pico_coordinator.family_name}"

    def test_name(self, night_switch):
        assert night_switch._attr_translation_key == "night_mode"

    def test_is_on_when_night_mode_active(self, night_switch, pico_coordinator):
        pico_coordinator.data.operating.night_mode = 1
        assert night_switch.is_on is True

    def test_is_off_when_night_mode_inactive(self, night_switch, pico_coordinator):
        pico_coordinator.data.operating.night_mode = 0
        assert night_switch.is_on is False

    def test_available_when_supported(self, night_switch, pico_coordinator):
        pico_coordinator.data.support_night_mode_toggle = True
        assert night_switch.available is True

    def test_not_available_when_unsupported(self, night_switch, pico_coordinator):
        pico_coordinator.data.support_night_mode_toggle = False
        assert night_switch.available is False

    async def test_turn_on(self, night_switch, pico_coordinator):
        pico_coordinator.data.support_night_mode_toggle = True
        pico_coordinator.async_set_night_mode = AsyncMock()
        await night_switch.async_turn_on()
        pico_coordinator.async_set_night_mode.assert_called_once_with(True)

    async def test_turn_on_unsupported_raises(self, night_switch, pico_coordinator):
        pico_coordinator.data.support_night_mode_toggle = False
        # current_mode is a property — don't set it, test just needs supports_night_mode=False
        with pytest.raises(HomeAssistantError, match="does not support night mode"):
            await night_switch.async_turn_on()

    async def test_turn_off(self, night_switch, pico_coordinator):
        pico_coordinator.data.support_night_mode_toggle = True
        pico_coordinator.async_set_night_mode = AsyncMock()
        await night_switch.async_turn_off()
        pico_coordinator.async_set_night_mode.assert_called_once_with(False)

    async def test_turn_off_unsupported_raises(self, night_switch, pico_coordinator):
        pico_coordinator.data.support_night_mode_toggle = False
        with pytest.raises(HomeAssistantError, match="does not support night mode"):
            await night_switch.async_turn_off()


class TestLEDStatusSwitch:
    def test_unique_id(self, led_switch, pico_coordinator):
        assert led_switch.unique_id == f"{DOMAIN}_led_status_{pico_coordinator.family_name}"

    def test_name(self, led_switch):
        assert led_switch._attr_translation_key == "led_status"

    def test_is_on_when_led_1(self, led_switch, pico_coordinator):
        pico_coordinator.data.operating.led_on_off_short = 1
        assert led_switch.is_on is True

    def test_is_off_when_led_2(self, led_switch, pico_coordinator):
        pico_coordinator.data.operating.led_on_off_short = 2
        assert led_switch.is_on is False

    def test_is_none_no_data(self, led_switch, pico_coordinator):
        pico_coordinator.data = None
        assert led_switch.is_on is None

    async def test_turn_on_calls_coordinator(self, led_switch, pico_coordinator):
        pico_coordinator.async_set_led_status = AsyncMock()
        await led_switch.async_turn_on()
        pico_coordinator.async_set_led_status.assert_called_once_with(True)

    async def test_turn_off_calls_coordinator(self, led_switch, pico_coordinator):
        pico_coordinator.async_set_led_status = AsyncMock()
        await led_switch.async_turn_off()
        pico_coordinator.async_set_led_status.assert_called_once_with(False)

    async def test_turn_on_wraps_error(self, led_switch, pico_coordinator):
        pico_coordinator.async_set_led_status = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(HomeAssistantError):
            await led_switch.async_turn_on()

    async def test_turn_off_wraps_error(self, led_switch, pico_coordinator):
        pico_coordinator.async_set_led_status = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(HomeAssistantError):
            await led_switch.async_turn_off()
