"""Tests for config flow (OpenPicoConfigFlow)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from custom_components.open_pico.config_flow import OpenPicoConfigFlow, OpenPicoOptionsFlow


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


    async def test_routes_to_cloud(self):
        flow = _make_flow()
        flow.async_step_pico_cloud = AsyncMock(return_value={"type": "form"})
        await flow.async_step_pico({"method": "cloud"})
        flow.async_step_pico_cloud.assert_called_once()


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

    async def test_cloud_entry_without_ip_does_not_break_scan(self):
        flow = _make_flow()
        cloud_entry = MagicMock()
        cloud_entry.data = {"device_type": "pico", "connection": "cloud", "serial": "SER1"}
        flow._async_current_entries = MagicMock(return_value=[cloud_entry])
        flow.async_step_pico_scan_results = AsyncMock(return_value={"type": "form"})

        with patch("open_pico_local_api.PicoAutoDiscovery") as MockDiscovery:
            MockDiscovery.discover = AsyncMock(return_value=["192.168.1.50"])
            await flow.async_step_pico_scan({"pin": "1234", "subnet": "192.168.1.0/24"})

        flow.async_step_pico_scan_results.assert_called_once()

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

        with patch("open_pico_local_api.PicoClient") as MockPicoClient:
            mock_instance = MagicMock()
            mock_instance.connect = AsyncMock()
            mock_instance.disconnect = AsyncMock()
            MockPicoClient.return_value = mock_instance

            with patch("asyncio.wait_for", return_value=None):
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

    async def test_rejected_reply_shows_invalid_pin(self):
        from open_polaris_local_api import PolarisApiError

        flow = _make_flow()
        with patch("open_polaris_local_api.PolarisLocalClient"):
            with patch("asyncio.wait_for", side_effect=PolarisApiError("stato error: res=0")):
                await flow.async_step_polaris_manual({
                    "ip": "192.168.1.60", "pin": "0000", "name": "Test Polaris",
                })

        assert flow.async_show_form.call_args[1]["errors"]["base"] == "invalid_pin"


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

        with patch("open_polaris_local_api.PolarisLocalClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.connect = AsyncMock()
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            with patch("asyncio.wait_for", return_value=None):
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


# ─── Step: pico_cloud ────────────────────────────────────────────────────────

def _cloud_client(devices=None, connect_exc=None, status_exc=None):
    client = MagicMock()
    client.connect = AsyncMock(side_effect=connect_exc)
    client.get_devices = AsyncMock(return_value=devices or [])
    client.get_status = AsyncMock(side_effect=status_exc)
    client.disconnect = AsyncMock()
    return client


def _dev(serial, lvdv_type=1):
    return {"Serial": serial, "Name": "Casa", "LVDV_Type": lvdv_type, "PlantName": "Home"}


class TestStepPicoCloud:
    async def test_shows_form_when_no_input(self):
        flow = _make_flow()
        await flow.async_step_pico_cloud(None)
        assert flow.async_show_form.call_args[1]["step_id"] == "pico_cloud"

    async def test_invalid_auth(self):
        from open_pico_local_api.cloud import PicoAuthError

        flow = _make_flow()
        client = _cloud_client(connect_exc=PicoAuthError("bad"))
        with patch("open_pico_local_api.cloud.PicoCloudClient", return_value=client):
            await flow.async_step_pico_cloud({"email": "a@b.c", "password": "x"})
        assert flow.async_show_form.call_args[1]["errors"]["base"] == "invalid_auth"
        client.disconnect.assert_awaited_once()

    async def test_timeout(self):
        flow = _make_flow()
        client = _cloud_client(connect_exc=asyncio.TimeoutError())
        with patch("open_pico_local_api.cloud.PicoCloudClient", return_value=client):
            await flow.async_step_pico_cloud({"email": "a@b.c", "password": "x"})
        assert flow.async_show_form.call_args[1]["errors"]["base"] == "timeout"

    async def test_no_devices_when_filtered_out(self):
        flow = _make_flow()
        flow._async_current_entries = MagicMock(
            return_value=[MagicMock(data={"serial": "AAA1"})]
        )
        client = _cloud_client(devices=[_dev("aaa1"), _dev("BBB2", lvdv_type=2)])
        with patch("open_pico_local_api.cloud.PicoCloudClient", return_value=client):
            await flow.async_step_pico_cloud({"email": "a@b.c", "password": "x"})
        assert flow.async_show_form.call_args[1]["errors"]["base"] == "no_cloud_devices"

    async def test_success_filters_and_goes_to_device_step(self):
        flow = _make_flow()
        flow._async_current_entries = MagicMock(
            return_value=[MagicMock(data={"serial": "AAA1"})]
        )
        flow.async_step_pico_cloud_device = AsyncMock(return_value={"type": "form"})
        client = _cloud_client(
            devices=[_dev("AAA1"), _dev("BBB2"), _dev("CCC3", lvdv_type=2)]
        )
        with patch("open_pico_local_api.cloud.PicoCloudClient", return_value=client):
            await flow.async_step_pico_cloud({"email": "a@b.c", "password": "x"})
        flow.async_step_pico_cloud_device.assert_called_once()
        assert [d["Serial"] for d in flow._cloud_devices] == ["BBB2"]
        assert flow._cloud_email == "a@b.c"
        client.disconnect.assert_awaited_once()


# ─── Step: pico_cloud_device ─────────────────────────────────────────────────

class _DeviceError(Exception):
    pass


@pytest.fixture(autouse=True)
def _stub_device_error():
    # conftest's library stub has no PicoDeviceError; real library does
    with patch("open_pico_local_api.PicoDeviceError", _DeviceError, create=True):
        yield


class TestStepPicoCloudDevice:
    INPUT = {"serial": "bbb2", "pin": "1234", "name": "Casa"}

    async def test_success_creates_cloud_entry(self):
        flow = _make_flow()
        flow._cloud_email, flow._cloud_password = "a@b.c", "x"
        client = _cloud_client()
        with patch("open_pico_local_api.cloud.PicoCloudClient", return_value=client):
            await flow.async_step_pico_cloud_device(self.INPUT)
        data = flow.async_create_entry.call_args[1]["data"]
        assert data["connection"] == "cloud"
        assert data["serial"] == "BBB2"
        assert len(data["android_id"]) == 16
        assert (data["scan_interval"], data["command_delay"]) == (30, 3)
        client.disconnect.assert_awaited_once()

    async def test_custom_intervals_stored(self):
        flow = _make_flow()
        flow._cloud_email, flow._cloud_password = "a@b.c", "x"
        with patch("open_pico_local_api.cloud.PicoCloudClient", return_value=_cloud_client()):
            await flow.async_step_pico_cloud_device({**self.INPUT, "scan_interval": 60.0, "command_delay": 6.0})
        data = flow.async_create_entry.call_args[1]["data"]
        assert (data["scan_interval"], data["command_delay"]) == (60, 6)

    async def test_invalid_pin(self):
        flow = _make_flow()
        client = _cloud_client(status_exc=_DeviceError("Wrong PIN"))
        with patch("open_pico_local_api.cloud.PicoCloudClient", return_value=client):
            await flow.async_step_pico_cloud_device(self.INPUT)
        assert flow.async_show_form.call_args[1]["errors"]["base"] == "invalid_pin"
        client.disconnect.assert_awaited_once()

    async def test_cannot_connect(self):
        flow = _make_flow()
        client = _cloud_client(connect_exc=OSError("down"))
        with patch("open_pico_local_api.cloud.PicoCloudClient", return_value=client):
            await flow.async_step_pico_cloud_device(self.INPUT)
        assert flow.async_show_form.call_args[1]["errors"]["base"] == "cannot_connect"
        flow.async_create_entry.assert_not_called()
        client.disconnect.assert_awaited_once()


# ─── Polaris: cloud ──────────────────────────────────────────────────────────

class TestStepPolarisRouting:
    async def test_routes_to_cloud(self):
        flow = _make_flow()
        flow.async_step_polaris_cloud = AsyncMock(return_value={"type": "form"})
        await flow.async_step_polaris({"method": "cloud"})
        flow.async_step_polaris_cloud.assert_called_once()

    async def test_cloud_entry_without_ip_does_not_break_scan(self):
        flow = _make_flow()
        cloud_entry = MagicMock()
        cloud_entry.data = {"device_type": "polaris", "connection": "cloud", "serial": "CU1"}
        flow._async_current_entries = MagicMock(return_value=[cloud_entry])
        flow.async_step_polaris_scan_results = AsyncMock(return_value={"type": "form"})
        with patch("open_polaris_local_api.PolarisAutoDiscovery") as MockDiscovery:
            MockDiscovery.discover = AsyncMock(return_value=["192.168.1.60"])
            await flow.async_step_polaris_scan({"pin": "5678", "subnet": "192.168.1.0/24"})
        flow.async_step_polaris_scan_results.assert_called_once()


def _cu(serial):
    # PolarisCloudClient.get_devices already returns Polaris CUs only
    return {"Serial": serial, "Name": "Casa", "LVDV_Type": 0, "PlantName": "Home"}


class TestStepPolarisCloud:
    async def test_shows_form_when_no_input(self):
        flow = _make_flow()
        await flow.async_step_polaris_cloud(None)
        assert flow.async_show_form.call_args[1]["step_id"] == "polaris_cloud"

    async def test_invalid_auth(self):
        from open_polaris_local_api.cloud import PolarisAuthError

        flow = _make_flow()
        client = _cloud_client(connect_exc=PolarisAuthError("bad"))
        with patch("open_polaris_local_api.cloud.PolarisCloudClient", return_value=client):
            await flow.async_step_polaris_cloud({"email": "a@b.c", "password": "x"})
        assert flow.async_show_form.call_args[1]["errors"]["base"] == "invalid_auth"
        client.disconnect.assert_awaited_once()

    async def test_timeout(self):
        flow = _make_flow()
        client = _cloud_client(connect_exc=asyncio.TimeoutError())
        with patch("open_polaris_local_api.cloud.PolarisCloudClient", return_value=client):
            await flow.async_step_polaris_cloud({"email": "a@b.c", "password": "x"})
        assert flow.async_show_form.call_args[1]["errors"]["base"] == "timeout"

    async def test_no_devices_when_all_configured(self):
        flow = _make_flow()
        flow._async_current_entries = MagicMock(return_value=[MagicMock(data={"serial": "CU1"})])
        client = _cloud_client(devices=[_cu("cu1")])
        with patch("open_polaris_local_api.cloud.PolarisCloudClient", return_value=client):
            await flow.async_step_polaris_cloud({"email": "a@b.c", "password": "x"})
        assert flow.async_show_form.call_args[1]["errors"]["base"] == "no_cloud_devices"

    async def test_success_filters_and_goes_to_device_step(self):
        flow = _make_flow()
        flow._async_current_entries = MagicMock(return_value=[MagicMock(data={"serial": "CU1"})])
        flow.async_step_polaris_cloud_device = AsyncMock(return_value={"type": "form"})
        client = _cloud_client(devices=[_cu("CU1"), _cu("CU2")])
        with patch("open_polaris_local_api.cloud.PolarisCloudClient", return_value=client):
            await flow.async_step_polaris_cloud({"email": "a@b.c", "password": "x"})
        flow.async_step_polaris_cloud_device.assert_called_once()
        assert [d["Serial"] for d in flow._cloud_devices] == ["CU2"]
        assert flow._cloud_email == "a@b.c"
        client.disconnect.assert_awaited_once()


class TestStepPolarisCloudDevice:
    INPUT = {"serial": "cu2", "pin": "1234", "name": "Casa"}

    async def test_success_creates_cloud_entry(self):
        flow = _make_flow()
        flow._cloud_email, flow._cloud_password = "a@b.c", "x"
        client = _cloud_client()
        with patch("open_polaris_local_api.cloud.PolarisCloudClient", return_value=client) as cls:
            await flow.async_step_polaris_cloud_device(self.INPUT)
        data = flow.async_create_entry.call_args[1]["data"]
        assert (data["device_type"], data["connection"], data["serial"]) == ("polaris", "cloud", "CU2")
        assert len(data["android_id"]) == 16
        assert cls.call_args.kwargs["android_id"] == data["android_id"]
        assert (data["scan_interval"], data["command_delay"]) == (30, 3)
        flow.async_set_unique_id.assert_awaited_once_with("polaris_casa")
        client.disconnect.assert_awaited_once()

    async def test_custom_intervals_stored(self):
        flow = _make_flow()
        flow._cloud_email, flow._cloud_password = "a@b.c", "x"
        with patch("open_polaris_local_api.cloud.PolarisCloudClient", return_value=_cloud_client()):
            await flow.async_step_polaris_cloud_device({**self.INPUT, "scan_interval": 60.0, "command_delay": 6.0})
        data = flow.async_create_entry.call_args[1]["data"]
        assert (data["scan_interval"], data["command_delay"]) == (60, 6)

    async def test_invalid_pin(self):
        from open_polaris_local_api import PolarisApiError

        flow = _make_flow()
        client = _cloud_client(connect_exc=PolarisApiError("Wrong PIN"))
        with patch("open_polaris_local_api.cloud.PolarisCloudClient", return_value=client):
            await flow.async_step_polaris_cloud_device(self.INPUT)
        assert flow.async_show_form.call_args[1]["errors"]["base"] == "invalid_pin"
        client.disconnect.assert_awaited_once()

    async def test_invalid_auth(self):
        from open_polaris_local_api.cloud import PolarisAuthError

        flow = _make_flow()
        client = _cloud_client(connect_exc=PolarisAuthError("expired"))
        with patch("open_polaris_local_api.cloud.PolarisCloudClient", return_value=client):
            await flow.async_step_polaris_cloud_device(self.INPUT)
        assert flow.async_show_form.call_args[1]["errors"]["base"] == "invalid_auth"

    async def test_cannot_connect(self):
        flow = _make_flow()
        client = _cloud_client(connect_exc=OSError("down"))
        with patch("open_polaris_local_api.cloud.PolarisCloudClient", return_value=client):
            await flow.async_step_polaris_cloud_device(self.INPUT)
        assert flow.async_show_form.call_args[1]["errors"]["base"] == "cannot_connect"
        flow.async_create_entry.assert_not_called()
        client.disconnect.assert_awaited_once()


class TestOptionsFlow:
    @pytest.fixture
    def entry(self):
        entry = MagicMock(data={"scan_interval": 60}, options={})
        with patch.object(OpenPicoOptionsFlow, "config_entry", new_callable=PropertyMock, return_value=entry):
            yield entry

    @pytest.mark.parametrize(("options", "expected"), [({}, 60), ({"scan_interval": 120}, 120)])
    async def test_form_defaults_to_current_value(self, entry, options, expected):
        entry.options = options
        flow = OpenPicoOptionsFlow()
        flow.async_show_form = MagicMock(return_value={"type": "form"})
        await flow.async_step_init()
        schema = flow.async_show_form.call_args.kwargs["data_schema"]
        assert schema({})["scan_interval"] == expected

    async def test_saves_scan_interval(self, entry):
        flow = OpenPicoOptionsFlow()
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
        await flow.async_step_init({"scan_interval": 90.0})
        flow.async_create_entry.assert_called_once_with(data={"scan_interval": 90})

    async def test_cloud_entry_also_offers_command_delay(self, entry):
        entry.data = {"connection": "cloud", "scan_interval": 30, "command_delay": 3}
        entry.options = {"command_delay": 7}
        flow = OpenPicoOptionsFlow()
        flow.async_show_form = MagicMock(return_value={"type": "form"})
        await flow.async_step_init()
        schema = flow.async_show_form.call_args.kwargs["data_schema"]
        assert schema({}) == {"scan_interval": 30, "command_delay": 7}

    async def test_local_entry_has_no_command_delay(self, entry):
        flow = OpenPicoOptionsFlow()
        flow.async_show_form = MagicMock(return_value={"type": "form"})
        await flow.async_step_init()
        assert "command_delay" not in flow.async_show_form.call_args.kwargs["data_schema"]({})


CLOUD_DATA = {
    "device_type": "polaris", "connection": "cloud", "email": "old@x.it", "password": "old",
    "serial": "ABC", "pin": "1111", "name": "CU", "android_id": "a1", "scan_interval": 30,
}
LOCAL_DATA = {"device_type": "pico", "ip": "192.168.1.5", "pin": "1111", "name": "Living Room"}


class TestReconfigure:
    def _flow(self, data):
        flow = _make_flow()
        entry = MagicMock(data=data)
        flow._get_reconfigure_entry = MagicMock(return_value=entry)
        flow.async_update_reload_and_abort = MagicMock(return_value={"type": "abort"})
        flow.async_show_form = MagicMock(return_value={"type": "form"})
        return flow, entry

    async def test_cloud_form_asks_account_and_pin(self):
        flow, _ = self._flow(CLOUD_DATA)
        await flow.async_step_reconfigure()
        keys = {str(k) for k in flow.async_show_form.call_args.kwargs["data_schema"].schema}
        assert keys == {"email", "password", "pin"}

    async def test_local_form_asks_ip_and_pin(self):
        flow, _ = self._flow(LOCAL_DATA)
        await flow.async_step_reconfigure()
        schema = flow.async_show_form.call_args.kwargs["data_schema"]
        assert {str(k) for k in schema.schema} == {"ip", "pin"}
        assert schema({"pin": "1"})["ip"] == "192.168.1.5"  # prefilled with the current IP

    async def test_local_success_updates_ip_and_pin(self):
        flow, entry = self._flow(LOCAL_DATA)
        with patch("custom_components.open_pico.config_flow._check_entry_data", AsyncMock(return_value=None)) as check:
            await flow.async_step_reconfigure({"ip": " 192.168.1.9 ", "pin": "2222"})
        expected = {**LOCAL_DATA, "ip": "192.168.1.9", "pin": "2222"}
        check.assert_awaited_once_with(expected)
        flow.async_update_reload_and_abort.assert_called_once_with(entry, data=expected)

    async def test_cloud_success_updates_entry(self):
        flow, entry = self._flow(CLOUD_DATA)
        with patch("custom_components.open_pico.config_flow._check_entry_data", AsyncMock(return_value=None)) as check:
            await flow.async_step_reconfigure({"email": " new@x.it ", "password": "new", "pin": " 2222 "})
        expected = {**CLOUD_DATA, "email": "new@x.it", "password": "new", "pin": "2222"}
        check.assert_awaited_once_with(expected)
        flow.async_update_reload_and_abort.assert_called_once_with(entry, data=expected)

    @pytest.mark.parametrize(
        ("other", "error"),
        [
            ({"device_type": "polaris", "ip": "192.168.1.9"}, "ip_already_configured"),
            # a cloud entry's "ip" never collides; the entry's own current IP is fine too
            ({"device_type": "pico", "connection": "cloud", "ip": "192.168.1.9"}, None),
        ],
    )
    async def test_ip_used_by_another_entry_is_rejected(self, other, error):
        flow, entry = self._flow(LOCAL_DATA)
        entry.entry_id = "this"
        flow._async_current_entries = MagicMock(return_value=[
            entry, MagicMock(entry_id="other", data=other),
        ])
        with patch("custom_components.open_pico.config_flow._check_entry_data", AsyncMock(return_value=None)) as check:
            await flow.async_step_reconfigure({"ip": "192.168.1.9", "pin": "1111"})
        if error:
            check.assert_not_awaited()  # no connection attempt
            flow.async_update_reload_and_abort.assert_not_called()
            assert flow.async_show_form.call_args.kwargs["errors"] == {"base": error}
        else:
            flow.async_update_reload_and_abort.assert_called_once()

    async def test_keeping_own_ip_is_allowed(self):
        flow, entry = self._flow(LOCAL_DATA)
        entry.entry_id = "this"
        flow._async_current_entries = MagicMock(return_value=[entry])
        with patch("custom_components.open_pico.config_flow._check_entry_data", AsyncMock(return_value=None)):
            await flow.async_step_reconfigure({"ip": "192.168.1.5", "pin": "2222"})
        flow.async_update_reload_and_abort.assert_called_once()

    async def test_wrong_pin_keeps_entry_and_shows_error(self):
        flow, _ = self._flow(CLOUD_DATA)
        with patch("custom_components.open_pico.config_flow._check_entry_data", AsyncMock(return_value="invalid_pin")):
            await flow.async_step_reconfigure({"email": "old@x.it", "password": "old", "pin": "9999"})
        flow.async_update_reload_and_abort.assert_not_called()
        assert flow.async_show_form.call_args.kwargs["errors"] == {"base": "invalid_pin"}

    @pytest.mark.parametrize(
        ("data", "helper", "args"),
        [
            (LOCAL_DATA, "_check_pico_local", ("192.168.1.5", "1111", "pico_living_room_cfgflow")),
            ({**LOCAL_DATA, "device_type": "polaris"}, "_check_polaris_local", ("192.168.1.5", "1111")),
            (CLOUD_DATA, "_check_polaris_cloud", ("old@x.it", "old", "ABC", "1111", "CU", "a1")),
            ({**CLOUD_DATA, "device_type": "pico"}, "_check_pico_cloud", ("old@x.it", "old", "ABC", "1111", "CU", "a1")),
        ],
    )
    async def test_check_entry_data_dispatch(self, data, helper, args):
        from custom_components.open_pico import config_flow

        with patch.object(config_flow, helper, AsyncMock(return_value=None)) as check:
            assert await config_flow._check_entry_data(data) is None
        check.assert_awaited_once_with(*args)


class TestManualIpInUse:
    @pytest.mark.parametrize(
        ("step", "check"),
        [("async_step_pico_manual", "_check_pico_local"), ("async_step_polaris_manual", "_check_polaris_local")],
    )
    async def test_ip_of_another_local_entry_is_rejected(self, step, check):
        flow = _make_flow()
        flow._async_current_entries = MagicMock(return_value=[
            MagicMock(entry_id="other", data={"device_type": "pico", "ip": "192.168.1.9"}),
        ])
        with patch(f"custom_components.open_pico.config_flow.{check}", AsyncMock(return_value=None)) as checker:
            await getattr(flow, step)({"ip": " 192.168.1.9 ", "pin": "1111", "name": "New"})
        checker.assert_not_awaited()
        flow.async_create_entry.assert_not_called()
        assert flow.async_show_form.call_args.kwargs["errors"] == {"base": "ip_already_configured"}

    async def test_ip_of_cloud_entry_is_allowed(self):
        flow = _make_flow()
        flow._async_current_entries = MagicMock(return_value=[
            MagicMock(entry_id="other", data={"connection": "cloud", "ip": "192.168.1.9"}),
        ])
        with patch("custom_components.open_pico.config_flow._check_polaris_local", AsyncMock(return_value=None)):
            await flow.async_step_polaris_manual({"ip": "192.168.1.9", "pin": "1111", "name": "New"})
        flow.async_create_entry.assert_called_once()
