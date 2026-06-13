"""Tests for button entity (Reset Filter Maintenance)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.open_pico.button import PicoMaintenanceResetButton
from custom_components.open_pico.const import DOMAIN


@pytest.fixture
def button(pico_coordinator):
    return PicoMaintenanceResetButton(pico_coordinator, 0)


class TestPicoMaintenanceResetButton:
    def test_unique_id(self, button, pico_coordinator):
        assert button.unique_id == f"{DOMAIN}_reset_maintenance_{pico_coordinator.family_name}"

    def test_name(self, button):
        assert button.name == "Reset Filter Maintenance"

    def test_available_when_maintenance_needed(self, button, pico_coordinator):
        pico_coordinator.data.device_info.needs_clean_filters_maintenance = True
        assert button.available is True

    def test_not_available_when_no_maintenance(self, button, pico_coordinator):
        pico_coordinator.data.device_info.needs_clean_filters_maintenance = False
        assert button.available is False

    def test_not_available_when_no_data(self, button, pico_coordinator):
        pico_coordinator.data = None
        assert button.available is False

    def test_not_available_when_no_device_info(self, button, pico_coordinator):
        pico_coordinator.data.device_info = None
        assert button.available is False

    async def test_press_calls_reset_maintenance(self, button, pico_coordinator, mock_pico_client):
        pico_coordinator.async_request_refresh = AsyncMock()
        await button.async_press()
        mock_pico_client.reset_maintenance.assert_called_once_with(retry=True)
        pico_coordinator.async_request_refresh.assert_called_once()

    async def test_press_handles_error_gracefully(self, button, pico_coordinator, mock_pico_client):
        mock_pico_client.reset_maintenance.side_effect = RuntimeError("fail")
        # Should not raise — error is logged
        await button.async_press()
