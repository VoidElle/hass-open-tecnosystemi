"""Tests for config flow (OpenPicoConfigFlow)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.open_pico.config_flow import OpenPicoConfigFlow


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_flow() -> OpenPicoConfigFlow:
    flow = OpenPicoConfigFlow()
    flow.hass = MagicMock()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    flow._async_current_entries = MagicMock(return_value=[])
    # async_show_form and async_create_entry are real methods — we spy on them
    flow.async_show_form = MagicMock(return_value={"type": "form"})
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    return flow


# ─── Step: user ──────────────────────────────────────────────────────────────

class TestStepUser:
    async def test_shows_form_when_no_input(self):
        flow = _make_flow()
        result = await flow.async_step_user(None)
        flow.async_show_form.assert_called_once()
        assert flow.async_show_form.call_args[1]["step_id"] == "user"

    async def test_routes_to_pico(self):
        flow = _make_flow()
        flow.async_step_pico = AsyncMock(return_value={"type": "form"})
        await flow.async_step_user({"device_type": "pico"})
        flow.async_step_pico.assert_called_once()

    async def test_routes_to_polaris(self):
        flow = _make_flow()
        flow.async_step_polaris = AsyncMock(return_value={"type": "form"})
        await flow.async_step_user({"device_type": "polaris"})
        flow.async_step_polaris.assert_called_once()


# ─── Step: pico ──────────────────────────────────────────────────────────────

class TestStepPico:
    async def test_shows_form_when_no_input(self):
        flow = _make_flow()
        result = await flow.async_step_pico(None)
        flow.async_show_form.assert_called_once()

    async def test_routes_to_manual(self):
        flow = _make_flow()
        flow.async_step_pico_manual = AsyncMock(return_value={"type": "form"})
        await flow.async_step_pico({"method": "manual"})
        flow.async_step_pico_manual.assert_called_once()

    async def test_routes_to_scan(self):
        flow = _make_flow()
        flow.async_step_pico_scan = AsyncMock(return_value={"type": "form"})
        await flow.async_step_pico({"method": "scan"})
        flow.async_step_pico_scan.assert_called_once()


# ─── Step: pico_manual ───────────────────────────────────────────────────────

class TestStepPicoManual:
    async def test_shows_form_when_no_input(self):
        flow = _make_flow()
        result = await flow.async_step_pico_manual(None)
        flow.async_show_form.assert_called_once()

    async def test_successful_manual_creates_entry(self):
        flow = _make_flow()
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()

        with patch("custom_components.open_pico.config_flow.asyncio.wait_for", new=AsyncMock()):
            with patch("builtins.__import__", side_effect=lambda name, *a, **kw: MagicMock() if name == "open_pico_local_api" else __import__(name, *a, **kw)):
                # Patch PicoClient directly in config_flow module
                with patch("custom_components.open_pico.config_flow.OpenPicoConfigFlow.async_step_pico_manual.__wrapped__", create=True):
                    pass

        # Simpler: directly patch inside the method's import scope
        with patch("open_pico_local_api.PicoClient") as MockPicoClient:
            mock_instance = MagicMock()
            mock_instance.connect = AsyncMock()
            mock_instance.disconnect = AsyncMock()
            MockPicoClient.return_value = mock_instance

            with patch("asyncio.wait_for", return_value=None):
                result = await flow.async_step_pico_manual({
                    "ip": "192.168.1.50",
                    "pin": "1234",
                    "name": "Test Pico",
                })

        flow.async_create_entry.assert_called_once()
        call_kwargs = flow.async_create_entry.call_args[1]
        assert call_kwargs["data"]["device_type"] == "pico"
        assert call_kwargs["data"]["ip"] == "192.168.1.50"
        assert call_kwargs["title"] == "Test Pico"

    async def test_connect_failure_shows_error(self):
        flow = _make_flow()

        with patch("open_pico_local_api.PicoClient") as MockPicoClient:
            mock_instance = MagicMock()
            mock_instance.connect = AsyncMock(side_effect=OSError("refused"))
            MockPicoClient.return_value = mock_instance

            with patch("asyncio.wait_for", side_effect=OSError("refused")):
                result = await flow.async_step_pico_manual({
                    "ip": "192.168.1.50",
                    "pin": "1234",
                    "name": "Test Pico",
                })

        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"]["base"] == "cannot_connect"


# ─── Step: pico_scan ─────────────────────────────────────────────────────────

class TestStepPicoScan:
    async def test_shows_form_when_no_input(self):
        flow = _make_flow()
        result = await flow.async_step_pico_scan(None)
        flow.async_show_form.assert_called_once()

    async def test_discovery_failure_shows_error(self):
        flow = _make_flow()

        with patch("open_pico_local_api.PicoAutoDiscovery") as MockDiscovery:
            MockDiscovery.discover = AsyncMock(side_effect=RuntimeError("timeout"))
            result = await flow.async_step_pico_scan({
                "pin": "1234",
                "subnet": "192.168.1.0/24",
            })

        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"]["base"] == "discovery_failed"

    async def test_no_devices_found_shows_error(self):
        flow = _make_flow()

        with patch("open_pico_local_api.PicoAutoDiscovery") as MockDiscovery:
            MockDiscovery.discover = AsyncMock(return_value=[])
            result = await flow.async_step_pico_scan({
                "pin": "1234",
                "subnet": "192.168.1.0/24",
            })

        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"]["base"] == "no_devices_found"

    async def test_devices_found_routes_to_results(self):
        flow = _make_flow()
        flow.async_step_pico_scan_results = AsyncMock(return_value={"type": "form"})

        with patch("open_pico_local_api.PicoAutoDiscovery") as MockDiscovery:
            MockDiscovery.discover = AsyncMock(return_value=["192.168.1.50"])
            await flow.async_step_pico_scan({
                "pin": "1234",
                "subnet": "192.168.1.0/24",
            })

        flow.async_step_pico_scan_results.assert_called_once()
        assert flow._scan_pin == "1234"

    async def test_already_configured_ips_excluded(self):
        flow = _make_flow()
        existing_entry = MagicMock()
        existing_entry.data = {"device_type": "pico", "ip": "192.168.1.50"}
        flow._async_current_entries = MagicMock(return_value=[existing_entry])
        flow.async_step_pico_scan_results = AsyncMock(return_value={"type": "form"})

        with patch("open_pico_local_api.PicoAutoDiscovery") as MockDiscovery:
            MockDiscovery.discover = AsyncMock(return_value=["192.168.1.50", "192.168.1.51"])
            await flow.async_step_pico_scan({
                "pin": "1234",
                "subnet": "192.168.1.0/24",
            })

        assert flow._discovered_ips == ["192.168.1.51"]


# ─── Step: pico_scan_results / confirm ───────────────────────────────────────

class TestStepPicoScanResults:
    async def test_shows_form_when_no_input(self):
        flow = _make_flow()
        flow._discovered_ips = ["192.168.1.50"]
        result = await flow.async_step_pico_scan_results(None)
        flow.async_show_form.assert_called_once()

    async def test_selects_ip_and_routes_to_confirm(self):
        flow = _make_flow()
        flow._discovered_ips = ["192.168.1.50"]
        flow.async_step_pico_scan_confirm = AsyncMock(return_value={"type": "form"})
        await flow.async_step_pico_scan_results({"ip": "192.168.1.50"})
        assert flow._selected_ip == "192.168.1.50"
        flow.async_step_pico_scan_confirm.assert_called_once()


class TestStepPicoScanConfirm:
    async def test_creates_entry(self):
        flow = _make_flow()
        flow._selected_ip = "192.168.1.50"
        flow._scan_pin = "1234"
        await flow.async_step_pico_scan_confirm({"name": "Living Room Pico"})
        flow.async_create_entry.assert_called_once()
        data = flow.async_create_entry.call_args[1]["data"]
        assert data["ip"] == "192.168.1.50"
        assert data["pin"] == "1234"
        assert data["name"] == "Living Room Pico"

    async def test_shows_form_when_no_input(self):
        flow = _make_flow()
        flow._selected_ip = "192.168.1.50"
        await flow.async_step_pico_scan_confirm(None)
        flow.async_show_form.assert_called_once()


# ─── Polaris: manual ─────────────────────────────────────────────────────────

class TestStepPolarisManual:
    async def test_shows_form_when_no_input(self):
        flow = _make_flow()
        result = await flow.async_step_polaris_manual(None)
        flow.async_show_form.assert_called_once()

    async def test_successful_creates_entry(self):
        flow = _make_flow()

        with patch("open_polaris_local_api.PolarisLocalClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.connect = AsyncMock()
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            with patch("asyncio.wait_for", return_value=None):
                await flow.async_step_polaris_manual({
                    "ip": "192.168.1.60",
                    "pin": "5678",
                    "name": "Test Polaris",
                    "scan_interval": 30,
                })

        flow.async_create_entry.assert_called_once()
        data = flow.async_create_entry.call_args[1]["data"]
        assert data["device_type"] == "polaris"
        assert data["ip"] == "192.168.1.60"

    async def test_connect_failure_shows_error(self):
        flow = _make_flow()

        with patch("open_polaris_local_api.PolarisLocalClient"):
            with patch("asyncio.wait_for", side_effect=OSError("refused")):
                await flow.async_step_polaris_manual({
                    "ip": "192.168.1.60",
                    "pin": "5678",
                    "name": "Test Polaris",
                    "scan_interval": 30,
                })

        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"]["base"] == "cannot_connect"


# ─── Polaris: scan ───────────────────────────────────────────────────────────

class TestStepPolarisScan:
    async def test_discovery_failure_shows_error(self):
        flow = _make_flow()

        with patch("open_polaris_local_api.PolarisAutoDiscovery") as MockDiscovery:
            MockDiscovery.discover = AsyncMock(side_effect=RuntimeError("timeout"))
            await flow.async_step_polaris_scan({
                "pin": "5678",
                "subnet": "192.168.1.0/24",
            })

        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["errors"]["base"] == "discovery_failed"

    async def test_devices_found_routes_to_results(self):
        flow = _make_flow()
        flow.async_step_polaris_scan_results = AsyncMock(return_value={"type": "form"})

        with patch("open_polaris_local_api.PolarisAutoDiscovery") as MockDiscovery:
            MockDiscovery.discover = AsyncMock(return_value=["192.168.1.60"])
            await flow.async_step_polaris_scan({
                "pin": "5678",
                "subnet": "192.168.1.0/24",
            })

        flow.async_step_polaris_scan_results.assert_called_once()


class TestStepPolarisScanConfirm:
    async def test_creates_entry(self):
        flow = _make_flow()
        flow._selected_ip = "192.168.1.60"
        flow._scan_pin = "5678"
        await flow.async_step_polaris_scan_confirm({
            "name": "Upstairs Polaris",
            "scan_interval": 30,
        })
        flow.async_create_entry.assert_called_once()
        data = flow.async_create_entry.call_args[1]["data"]
        assert data["device_type"] == "polaris"
        assert data["scan_interval"] == 30

    async def test_shows_form_when_no_input(self):
        flow = _make_flow()
        flow._selected_ip = "192.168.1.60"
        await flow.async_step_polaris_scan_confirm(None)
        flow.async_show_form.assert_called_once()
