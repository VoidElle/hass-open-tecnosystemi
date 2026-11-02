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


def make_cloud_entry(entry_id: str = "cloud1") -> MagicMock:
    entry = make_entry("pico", entry_id=entry_id, name="Cloud Pico")
    entry.data = {
        "device_type": "pico",
        "connection": "cloud",
        "email": "a@b.c",
        "password": "pw",
        "serial": "ABC123",
        "pin": "1234",
        "name": "Cloud Pico",
        "android_id": "0123456789abcdef",
        "verbose": True,
    }
    return entry


class TestSetupPicoEntry:
    async def test_cloud_builds_cloud_client_without_manager(self, mock_hass, mock_pico_client):
        from custom_components.open_pico import _setup_pico_entry

        mock_hass.data = {DOMAIN: {}}
        coordinator = MagicMock(last_update_success=True, async_refresh=AsyncMock())
        with (
            patch("custom_components.open_pico.PicoCloudClient", return_value=mock_pico_client) as cloud_cls,
            patch("custom_components.open_pico.PicoClientManager") as manager_cls,
            patch("custom_components.open_pico.MainCoordinator", return_value=coordinator) as coord_cls,
        ):
            result = await _setup_pico_entry(mock_hass, make_cloud_entry())

        assert result is coordinator
        assert cloud_cls.call_args.kwargs["device_id"] == "0123456789abcdef"
        assert cloud_cls.call_args.kwargs["serial"] == "ABC123"
        manager_cls.assert_not_called()
        assert coord_cls.call_args.kwargs == {"scan_interval": 30, "command_delay": 3}

    async def test_cloud_uses_entry_intervals(self, mock_hass, mock_pico_client):
        from custom_components.open_pico import _setup_pico_entry

        mock_hass.data = {DOMAIN: {}}
        entry = make_cloud_entry()
        entry.data = {**entry.data, "scan_interval": 60, "command_delay": 6}
        coordinator = MagicMock(last_update_success=True, async_refresh=AsyncMock())
        with (
            patch("custom_components.open_pico.PicoCloudClient", return_value=mock_pico_client),
            patch("custom_components.open_pico.MainCoordinator", return_value=coordinator) as coord_cls,
        ):
            await _setup_pico_entry(mock_hass, entry)

        assert coord_cls.call_args.kwargs == {"scan_interval": 60, "command_delay": 6}

    async def test_cloud_auth_error_raises_config_entry_error(self, mock_hass, mock_pico_client):
        from homeassistant.exceptions import ConfigEntryError
        from open_pico_local_api.cloud import PicoAuthError
        from custom_components.open_pico import _setup_pico_entry

        mock_hass.data = {DOMAIN: {}}
        mock_pico_client.connect.side_effect = PicoAuthError("bad")
        with patch("custom_components.open_pico.PicoCloudClient", return_value=mock_pico_client):
            with pytest.raises(ConfigEntryError):
                await _setup_pico_entry(mock_hass, make_cloud_entry())

    async def test_cloud_connect_failure_raises_not_ready(self, mock_hass, mock_pico_client):
        from homeassistant.exceptions import ConfigEntryNotReady
        from custom_components.open_pico import _setup_pico_entry

        mock_hass.data = {DOMAIN: {}}
        mock_pico_client.connect.side_effect = OSError("down")
        with patch("custom_components.open_pico.PicoCloudClient", return_value=mock_pico_client):
            with pytest.raises(ConfigEntryNotReady):
                await _setup_pico_entry(mock_hass, make_cloud_entry())

    async def test_entry_without_connection_key_uses_local_path(self, mock_hass, mock_pico_client):
        from custom_components.open_pico import _setup_pico_entry

        mock_hass.data = {DOMAIN: {}}
        manager = MagicMock(initialize=AsyncMock())
        manager.create_client.return_value = mock_pico_client
        coordinator = MagicMock(last_update_success=True, async_refresh=AsyncMock())
        with (
            patch("custom_components.open_pico.PicoClientManager", return_value=manager),
            patch("custom_components.open_pico.PicoCloudClient") as cloud_cls,
            patch("custom_components.open_pico.MainCoordinator", return_value=coordinator),
        ):
            await _setup_pico_entry(mock_hass, make_entry("pico"))

        cloud_cls.assert_not_called()
        manager.create_client.assert_called_once()


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

    async def test_unload_cloud_entry_disconnects_client(self, mock_hass, mock_pico_client):
        from custom_components.open_pico import async_unload_entry

        entry = make_cloud_entry("c1")
        coord = MagicMock(async_shutdown=AsyncMock(), client=mock_pico_client)
        mock_hass.data = {DOMAIN: {"c1": {"coordinator": coord, "device_type": "pico"}}}

        assert await async_unload_entry(mock_hass, entry) is True
        mock_pico_client.disconnect.assert_awaited_once()

    async def test_unload_keeps_manager_while_local_entry_remains(self, mock_hass):
        from custom_components.open_pico import async_unload_entry

        entry = make_entry("pico", entry_id="e5")
        mock_manager = MagicMock(shutdown=AsyncMock())
        mock_hass.data = {
            DOMAIN: {
                "e5": {"coordinator": MagicMock(async_shutdown=AsyncMock()), "device_type": "pico"},
                "pico_manager": mock_manager,
            }
        }
        other_local = make_entry("pico", entry_id="e6")
        mock_hass.config_entries.async_entries = MagicMock(return_value=[other_local])

        await async_unload_entry(mock_hass, entry)
        mock_manager.shutdown.assert_not_called()

    async def test_unload_shuts_down_manager_when_only_cloud_remains(self, mock_hass):
        from custom_components.open_pico import async_unload_entry

        entry = make_entry("pico", entry_id="e7")
        mock_manager = MagicMock(shutdown=AsyncMock())
        mock_hass.data = {
            DOMAIN: {
                "e7": {"coordinator": MagicMock(async_shutdown=AsyncMock()), "device_type": "pico"},
                "pico_manager": mock_manager,
            }
        }
        mock_hass.config_entries.async_entries = MagicMock(return_value=[make_cloud_entry("c2")])

        await async_unload_entry(mock_hass, entry)
        mock_manager.shutdown.assert_called_once()
