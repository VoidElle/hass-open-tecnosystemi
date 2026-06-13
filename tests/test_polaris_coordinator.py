"""Tests for PolarisCoordinator."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import make_polaris_device, make_polaris_zone
from custom_components.open_pico.polaris_coordinator import PolarisCoordinator, PolarisData


@pytest.fixture
def real_polaris_coordinator(mock_hass, mock_polaris_client):
    """Instantiate the real PolarisCoordinator for logic tests."""
    coord = PolarisCoordinator(mock_hass, mock_polaris_client, "Test Polaris", scan_interval=30)
    device = make_polaris_device()
    zones = [make_polaris_zone(zone_id=1), make_polaris_zone(zone_id=2, name="Bedroom")]
    coord.data = PolarisData(device=device, zones=zones)
    coord.async_request_refresh = AsyncMock()
    return coord


class TestPolarisCoordinatorProperties:
    def test_serial_from_client_device(self, real_polaris_coordinator, mock_polaris_client):
        mock_polaris_client.device.serial = "ABC123"
        assert real_polaris_coordinator.serial == "ABC123"

    def test_serial_fallback_to_ip(self, real_polaris_coordinator, mock_polaris_client):
        mock_polaris_client.device = None
        # Patch client.device to None so serial falls back
        real_polaris_coordinator.client.device = None
        result = real_polaris_coordinator.serial
        # IP is 192.168.1.60 → fallback is "192_168_1_60" or comes from client.ip
        assert "." not in result  # Should be IP with underscores

    def test_polaris_device_from_data(self, real_polaris_coordinator):
        dev = real_polaris_coordinator.polaris_device
        assert dev is not None
        assert dev.serial == "SN123456"

    def test_polaris_device_no_data(self, real_polaris_coordinator):
        real_polaris_coordinator.data = None
        assert real_polaris_coordinator.polaris_device is None

    def test_polaris_zones_from_data(self, real_polaris_coordinator):
        zones = real_polaris_coordinator.polaris_zones
        assert len(zones) == 2
        assert zones[0].zone_id == 1

    def test_polaris_zones_no_data(self, real_polaris_coordinator):
        real_polaris_coordinator.data = None
        assert real_polaris_coordinator.polaris_zones == []


class TestPolarisCoordinatorControl:
    async def test_turn_on(self, real_polaris_coordinator, mock_polaris_client):
        await real_polaris_coordinator.async_turn_on()
        mock_polaris_client.turn_on.assert_called_once()
        real_polaris_coordinator.async_request_refresh.assert_called_once()

    async def test_turn_off(self, real_polaris_coordinator, mock_polaris_client):
        await real_polaris_coordinator.async_turn_off()
        mock_polaris_client.turn_off.assert_called_once()
        real_polaris_coordinator.async_request_refresh.assert_called_once()

    async def test_set_cooling_mode(self, real_polaris_coordinator, mock_polaris_client):
        await real_polaris_coordinator.async_set_cooling_mode(1)
        mock_polaris_client.set_cooling_mode.assert_called_once_with(1)

    async def test_set_heating_mode(self, real_polaris_coordinator, mock_polaris_client):
        await real_polaris_coordinator.async_set_heating_mode()
        mock_polaris_client.set_heating_mode.assert_called_once()


class TestPolarisCoordinatorZoneControl:
    async def test_set_zone_temp_found(self, real_polaris_coordinator, mock_polaris_client):
        await real_polaris_coordinator.async_set_zone_temp(1, 22.5)
        mock_polaris_client.set_zone_temp.assert_called_once()
        zone_arg, temp_arg = mock_polaris_client.set_zone_temp.call_args[0]
        assert zone_arg.zone_id == 1
        assert temp_arg == 22.5

    async def test_set_zone_temp_not_found(self, real_polaris_coordinator, mock_polaris_client):
        await real_polaris_coordinator.async_set_zone_temp(99, 22.5)
        mock_polaris_client.set_zone_temp.assert_not_called()

    async def test_turn_zone_on(self, real_polaris_coordinator, mock_polaris_client):
        await real_polaris_coordinator.async_turn_zone_on(1)
        mock_polaris_client.turn_zone_on.assert_called_once()

    async def test_turn_zone_off(self, real_polaris_coordinator, mock_polaris_client):
        await real_polaris_coordinator.async_turn_zone_off(2)
        mock_polaris_client.turn_zone_off.assert_called_once()

    async def test_update_zone(self, real_polaris_coordinator, mock_polaris_client):
        await real_polaris_coordinator.async_update_zone(1, fancoil_set=2)
        mock_polaris_client.update_zone.assert_called_once()
        kwargs = mock_polaris_client.update_zone.call_args[1]
        assert kwargs["fancoil_set"] == 2


class TestPolarisCoordinatorUpdateData:
    async def test_successful_update(self, real_polaris_coordinator, mock_polaris_client):
        device = make_polaris_device()
        zones = [make_polaris_zone()]
        mock_polaris_client.async_update.return_value = (device, zones)

        result = await real_polaris_coordinator._async_update_data()
        assert result.device is device
        assert result.zones == zones

    async def test_polaris_api_error_raises_update_failed(self, real_polaris_coordinator, mock_polaris_client):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        from open_polaris_local_api import PolarisApiError
        mock_polaris_client.async_update.side_effect = PolarisApiError("bad response")
        with pytest.raises(UpdateFailed, match="Polaris error"):
            await real_polaris_coordinator._async_update_data()

    async def test_timeout_raises_update_failed(self, real_polaris_coordinator, mock_polaris_client):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        mock_polaris_client.async_update.side_effect = TimeoutError()
        with pytest.raises(UpdateFailed, match="timeout"):
            await real_polaris_coordinator._async_update_data()

    async def test_generic_error_raises_update_failed(self, real_polaris_coordinator, mock_polaris_client):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        mock_polaris_client.async_update.side_effect = RuntimeError("boom")
        with pytest.raises(UpdateFailed):
            await real_polaris_coordinator._async_update_data()


class TestPolarisCoordinatorShutdown:
    async def test_shutdown_closes_client(self, real_polaris_coordinator, mock_polaris_client):
        await real_polaris_coordinator.async_shutdown()
        mock_polaris_client.close.assert_called_once()
