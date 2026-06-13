"""Tests for __init__.py entry setup and teardown."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from custom_components.open_pico.const import DOMAIN


def make_entry(device_type: str, entry_id: str = "entry1", name: str = "Test") -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.title = name
    entry.data = {
        "device_type": device_type,
        "ip": "192.168.1.50",
        "pin": "1234",
        "name": name,
        "local_port": 40069,
        "verbose": False,
        "scan_interval": 30,
    }
    return entry


class TestAsyncSetupEntry:
    async def test_unknown_device_type_returns_false(self, mock_hass):
        from custom_components.open_pico import async_setup_entry

        entry = make_entry("unknown")
        result = await async_setup_entry(mock_hass, entry)
        assert result is False

    async def test_pico_setup_creates_coordinator(self, mock_hass):
        from custom_components.open_pico import async_setup_entry

        entry = make_entry("pico")
        mock_hass.data = {}

        with (
            patch("custom_components.open_pico._setup_pico_entry") as mock_pico_setup,
            patch("custom_components.open_pico.PICO_PLATFORMS", []),
        ):
            mock_coordinator = MagicMock()
            mock_pico_setup.return_value = mock_coordinator

            result = await async_setup_entry(mock_hass, entry)

        assert result is True
        assert mock_hass.data[DOMAIN][entry.entry_id]["coordinator"] is mock_coordinator
        assert mock_hass.data[DOMAIN][entry.entry_id]["device_type"] == "pico"

    async def test_polaris_setup_creates_coordinator(self, mock_hass):
        from custom_components.open_pico import async_setup_entry

        entry = make_entry("polaris")
        mock_hass.data = {}

        with (
            patch("custom_components.open_pico._setup_polaris_entry") as mock_polaris_setup,
            patch("custom_components.open_pico.POLARIS_PLATFORMS", []),
        ):
            mock_coordinator = MagicMock()
            mock_polaris_setup.return_value = mock_coordinator

            result = await async_setup_entry(mock_hass, entry)

        assert result is True
        assert mock_hass.data[DOMAIN][entry.entry_id]["device_type"] == "polaris"


class TestAsyncUnloadEntry:
    async def test_unload_pico_entry(self, mock_hass):
        from custom_components.open_pico import async_unload_entry

        entry = make_entry("pico", entry_id="e1")
        mock_hass.data = {
            DOMAIN: {
                "e1": {
                    "coordinator": MagicMock(async_shutdown=AsyncMock()),
                    "device_type": "pico",
                }
            }
        }
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        mock_hass.config_entries.async_entries = MagicMock(return_value=[])

        result = await async_unload_entry(mock_hass, entry)
        assert result is True
        assert "e1" not in mock_hass.data[DOMAIN]

    async def test_unload_polaris_entry(self, mock_hass):
        from custom_components.open_pico import async_unload_entry

        entry = make_entry("polaris", entry_id="e2")
        mock_coord = MagicMock()
        mock_coord.async_shutdown = AsyncMock()
        mock_hass.data = {
            DOMAIN: {
                "e2": {
                    "coordinator": mock_coord,
                    "device_type": "polaris",
                }
            }
        }
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        mock_hass.config_entries.async_entries = MagicMock(return_value=[])

        result = await async_unload_entry(mock_hass, entry)
        assert result is True
        mock_coord.async_shutdown.assert_called_once()

    async def test_unload_pico_shuts_down_manager_when_last(self, mock_hass):
        from custom_components.open_pico import async_unload_entry

        entry = make_entry("pico", entry_id="e3")
        mock_manager = MagicMock()
        mock_manager.shutdown = AsyncMock()
        mock_hass.data = {
            DOMAIN: {
                "e3": {
                    "coordinator": MagicMock(async_shutdown=AsyncMock()),
                    "device_type": "pico",
                },
                "pico_manager": mock_manager,
            }
        }
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        # No remaining pico entries
        mock_hass.config_entries.async_entries = MagicMock(return_value=[])

        await async_unload_entry(mock_hass, entry)
        mock_manager.shutdown.assert_called_once()

    async def test_unload_platforms_failure_returns_false(self, mock_hass):
        from custom_components.open_pico import async_unload_entry

        entry = make_entry("pico", entry_id="e4")
        mock_hass.data = {DOMAIN: {"e4": {"coordinator": MagicMock(), "device_type": "pico"}}}
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
        mock_hass.config_entries.async_entries = MagicMock(return_value=[])

        result = await async_unload_entry(mock_hass, entry)
        assert result is False
