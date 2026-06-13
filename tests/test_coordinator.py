"""Tests for MainCoordinator (Pico)."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from tests.conftest import make_pico_device_model, make_pico_operating


@pytest.fixture
def real_pico_coordinator(mock_hass, mock_pico_client):
    """Instantiate the real MainCoordinator for logic tests."""
    from custom_components.open_pico.coordinator import MainCoordinator
    coord = MainCoordinator(mock_hass, mock_pico_client, "Test Device")
    coord.data = make_pico_device_model()
    coord.async_request_refresh = AsyncMock()
    return coord


class TestMainCoordinatorProperties:
    def test_family_name_slug(self, real_pico_coordinator):
        assert real_pico_coordinator.family_name == "test_device"

    def test_family_name_special_chars(self, mock_hass, mock_pico_client):
        from custom_components.open_pico.coordinator import MainCoordinator
        coord = MainCoordinator(mock_hass, mock_pico_client, "Hallway -- Unit #1!")
        assert coord.family_name == "hallway_unit_1"

    def test_is_on_true(self, real_pico_coordinator):
        real_pico_coordinator.data.is_on = True
        assert real_pico_coordinator.is_on is True

    def test_is_on_no_data(self, real_pico_coordinator):
        real_pico_coordinator.data = None
        assert real_pico_coordinator.is_on is False

    def test_temperature(self, real_pico_coordinator):
        real_pico_coordinator.data.sensors.temperature = 23.4
        assert real_pico_coordinator.temperature == 23.4

    def test_temperature_no_data(self, real_pico_coordinator):
        real_pico_coordinator.data = None
        assert real_pico_coordinator.temperature == 0.0

    def test_humidity(self, real_pico_coordinator):
        real_pico_coordinator.data.sensors.humidity = 62.0
        assert real_pico_coordinator.humidity == 62.0

    def test_air_quality(self, real_pico_coordinator):
        real_pico_coordinator.data.sensors.air_quality = 950
        assert real_pico_coordinator.air_quality == 950

    def test_fan_speed(self, real_pico_coordinator):
        real_pico_coordinator.data.operating.speed_requested = 75
        assert real_pico_coordinator.fan_speed == 75

    def test_night_mode_enabled(self, real_pico_coordinator):
        real_pico_coordinator.data.operating.night_mode = 1
        assert real_pico_coordinator.night_mode_enabled is True

    def test_night_mode_disabled(self, real_pico_coordinator):
        real_pico_coordinator.data.operating.night_mode = 0
        assert real_pico_coordinator.night_mode_enabled is False

    def test_supports_fan_speed(self, real_pico_coordinator):
        real_pico_coordinator.data.support_fan_speed_control = True
        assert real_pico_coordinator.supports_fan_speed is True

    def test_supports_night_mode(self, real_pico_coordinator):
        real_pico_coordinator.data.support_night_mode_toggle = True
        assert real_pico_coordinator.supports_night_mode is True

    def test_supports_target_humidity(self, real_pico_coordinator):
        real_pico_coordinator.data.support_target_humidity_selection = True
        assert real_pico_coordinator.supports_target_humidity is True


class TestMainCoordinatorControl:
    async def test_turn_on(self, real_pico_coordinator, mock_pico_client):
        await real_pico_coordinator.async_turn_on()
        mock_pico_client.turn_on.assert_called_once_with(retry=True)
        real_pico_coordinator.async_request_refresh.assert_called_once()

    async def test_turn_off(self, real_pico_coordinator, mock_pico_client):
        await real_pico_coordinator.async_turn_off()
        mock_pico_client.turn_off.assert_called_once_with(retry=True)
        real_pico_coordinator.async_request_refresh.assert_called_once()

    async def test_set_mode(self, real_pico_coordinator, mock_pico_client):
        mode = MagicMock()
        await real_pico_coordinator.async_set_mode(mode)
        mock_pico_client.change_operating_mode.assert_called_once_with(mode, retry=True)
        real_pico_coordinator.async_request_refresh.assert_called_once()

    async def test_set_fan_speed_valid(self, real_pico_coordinator, mock_pico_client):
        real_pico_coordinator.data.support_fan_speed_control = True
        real_pico_coordinator.data.operating.night_mode = 0
        await real_pico_coordinator.async_set_fan_speed(80)
        mock_pico_client.change_fan_speed.assert_called_once_with(80, retry=True, force=False)

    async def test_set_fan_speed_unsupported_raises(self, real_pico_coordinator):
        real_pico_coordinator.data.support_fan_speed_control = False
        with pytest.raises(ValueError, match="does not support"):
            await real_pico_coordinator.async_set_fan_speed(50)

    async def test_set_night_mode_on(self, real_pico_coordinator, mock_pico_client):
        real_pico_coordinator.data.support_night_mode_toggle = True
        await real_pico_coordinator.async_set_night_mode(True)
        mock_pico_client.set_night_mode.assert_called_once_with(True, retry=True, force=False)

    async def test_set_night_mode_unsupported_raises(self, real_pico_coordinator):
        real_pico_coordinator.data.support_night_mode_toggle = False
        with pytest.raises(ValueError, match="does not support"):
            await real_pico_coordinator.async_set_night_mode(True)

    async def test_set_led_status(self, real_pico_coordinator, mock_pico_client):
        await real_pico_coordinator.async_set_led_status(True)
        mock_pico_client.set_led_status.assert_called_once_with(True, retry=True)

    async def test_set_target_humidity_valid(self, real_pico_coordinator, mock_pico_client):
        real_pico_coordinator.data.support_target_humidity_selection = True
        await real_pico_coordinator.async_set_target_humidity(2)
        mock_pico_client.set_target_humidity.assert_called_once_with(2, retry=True, force=False)

    async def test_set_target_humidity_unsupported_raises(self, real_pico_coordinator):
        real_pico_coordinator.data.support_target_humidity_selection = False
        with pytest.raises(ValueError, match="does not support"):
            await real_pico_coordinator.async_set_target_humidity(2)


class TestMainCoordinatorUpdateData:
    async def test_successful_update(self, real_pico_coordinator, mock_pico_client):
        new_data = make_pico_device_model(is_on=False)
        mock_pico_client.get_status.return_value = new_data
        mock_pico_client.connected = True

        result = await real_pico_coordinator.async_update_data()
        assert result is new_data

    async def test_update_reconnects_when_disconnected(self, real_pico_coordinator, mock_pico_client):
        mock_pico_client.connected = False
        new_data = make_pico_device_model()
        mock_pico_client.get_status.return_value = new_data

        await real_pico_coordinator.async_update_data()
        mock_pico_client.connect.assert_called_once()

    async def test_update_none_status_raises(self, real_pico_coordinator, mock_pico_client):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        mock_pico_client.connected = True
        mock_pico_client.get_status.return_value = None
        with pytest.raises(UpdateFailed, match="no status data"):
            await real_pico_coordinator.async_update_data()

    async def test_update_exception_raises_update_failed(self, real_pico_coordinator, mock_pico_client):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        mock_pico_client.connected = True
        mock_pico_client.get_status.side_effect = OSError("network error")
        with pytest.raises(UpdateFailed):
            await real_pico_coordinator.async_update_data()


class TestMainCoordinatorShutdown:
    async def test_shutdown_is_noop(self, real_pico_coordinator):
        await real_pico_coordinator.async_shutdown()

