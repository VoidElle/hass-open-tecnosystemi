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


# ─── Incremental zone details (issue #23 / PR #24) ───────────────────────────

MINI_DETAIL = {"shu": -1, "shu_set": -1, "EV": 2, "EV_set": 2, "fan": -1, "fan_set": -1}
STEALTH_DETAIL = {"shu": 1, "shu_set": 1, "EV": 0, "EV_set": 0, "fan": 3, "fan_set": 3}


@pytest.fixture
def detail_coordinator(real_polaris_coordinator, mock_polaris_client, monkeypatch):
    """Coordinator with get_zone_detail mocked and the 1s spacing sleeps disabled."""
    import custom_components.open_pico.polaris_coordinator as mod

    monkeypatch.setattr(mod.asyncio, "sleep", AsyncMock())
    mock_polaris_client.timeout = 15
    mock_polaris_client.get_zone_detail = AsyncMock(return_value=dict(MINI_DETAIL))
    mock_polaris_client.set_zone_serranda = AsyncMock()
    return real_polaris_coordinator


def _zones(*ids, **kwargs):
    return [make_polaris_zone(zone_id=i, **kwargs) for i in ids]


class TestPolarisZoneDetailsIncremental:
    async def test_first_refresh_skips_details(self, detail_coordinator, mock_polaris_client):
        # First refresh runs under the 30s setup timeout: no stato_zona allowed.
        detail_coordinator.data = None
        await detail_coordinator._async_update_data()
        mock_polaris_client.get_zone_detail.assert_not_called()

    async def test_fetches_at_most_two_missing_zones_per_poll(self, detail_coordinator, mock_polaris_client):
        mock_polaris_client.async_update.return_value = (make_polaris_device(), _zones(1, 2, 3))
        await detail_coordinator._async_update_data()
        assert [c.args[0] for c in mock_polaris_client.get_zone_detail.call_args_list] == [1, 2]
        assert set(detail_coordinator.zone_details) == {1, 2}

        await detail_coordinator._async_update_data()
        assert set(detail_coordinator.zone_details) == {1, 2, 3}

    async def test_failed_zone_succeeds_on_next_poll(self, detail_coordinator, mock_polaris_client):
        mock_polaris_client.async_update.return_value = (make_polaris_device(), _zones(1, 2))
        mock_polaris_client.get_zone_detail.side_effect = [
            TimeoutError("no answer"), dict(MINI_DETAIL),  # poll 1: zone 1 fails, zone 2 ok
            dict(MINI_DETAIL),                             # poll 2: zone 1 retried
        ]
        await detail_coordinator._async_update_data()
        assert set(detail_coordinator.zone_details) == {2}
        assert detail_coordinator._zone_failures == {1: 1}

        await detail_coordinator._async_update_data()
        assert set(detail_coordinator.zone_details) == {1, 2}
        assert detail_coordinator._zone_failures == {}

    async def test_zone_skipped_after_max_failures(self, detail_coordinator, mock_polaris_client):
        mock_polaris_client.async_update.return_value = (make_polaris_device(), _zones(1))
        mock_polaris_client.get_zone_detail.side_effect = TimeoutError("no answer")
        for _ in range(3):
            await detail_coordinator._async_update_data()
        assert detail_coordinator._zone_failures[1] == 3
        assert detail_coordinator._zones_needing_details(_zones(1)) == []

    async def test_errored_zones_not_fetched(self, detail_coordinator, mock_polaris_client):
        mock_polaris_client.async_update.return_value = (make_polaris_device(), _zones(1, num_error=1))
        await detail_coordinator._async_update_data()
        mock_polaris_client.get_zone_detail.assert_not_called()

    async def test_spacing_sleep_runs_after_failure(self, detail_coordinator, mock_polaris_client):
        import custom_components.open_pico.polaris_coordinator as mod

        mock_polaris_client.async_update.return_value = (make_polaris_device(), _zones(1))
        mock_polaris_client.get_zone_detail.side_effect = TimeoutError("no answer")
        await detail_coordinator._async_update_data()
        mod.asyncio.sleep.assert_awaited_with(1)

    async def test_hanging_zone_cut_by_per_zone_timeout(self, detail_coordinator, mock_polaris_client):
        import asyncio

        async def hang(_zone_id):
            await asyncio.Event().wait()

        mock_polaris_client.timeout = 0.01  # outer limit = timeout + 1
        mock_polaris_client.async_update.return_value = (make_polaris_device(), _zones(1))
        mock_polaris_client.get_zone_detail.side_effect = hang
        await asyncio.wait_for(detail_coordinator._async_update_data(), timeout=5)
        assert detail_coordinator._zone_failures == {1: 1}

    async def test_refresh_round_robin_every_n_polls(self, detail_coordinator, mock_polaris_client):
        from custom_components.open_pico.polaris_coordinator import _ZONE_REFRESH_INTERVAL

        mock_polaris_client.async_update.return_value = (make_polaris_device(), _zones(1, 2))
        await detail_coordinator._async_update_data()  # initial fetch: both zones
        mock_polaris_client.get_zone_detail.reset_mock()

        fetched = []
        for _ in range(2 * _ZONE_REFRESH_INTERVAL):
            await detail_coordinator._async_update_data()
            fetched += [c.args[0] for c in mock_polaris_client.get_zone_detail.call_args_list]
            mock_polaris_client.get_zone_detail.reset_mock()
        # One refresh per interval, alternating zones.
        assert fetched == [1, 2]


class TestPolarisZoneDetailsMerge:
    async def test_merge_has_no_ev_fallback(self, detail_coordinator, mock_polaris_client):
        # MiniDiscovery2X: damper lives in EV/EV_set; zone.serranda must stay -1
        # so ordinary commands do not carry shu_set (issue #23 item 5).
        zones = _zones(1)
        mock_polaris_client.async_update.return_value = (make_polaris_device(), zones)
        result = await detail_coordinator._async_update_data()
        z = result.zones[0]
        assert (z.serranda, z.serranda_set, z.fancoil, z.fancoil_set) == (-1, -1, -1, -1)

    async def test_merge_copies_shu_and_fan(self, detail_coordinator, mock_polaris_client):
        mock_polaris_client.async_update.return_value = (make_polaris_device(), _zones(1))
        mock_polaris_client.get_zone_detail.return_value = dict(STEALTH_DETAIL)
        result = await detail_coordinator._async_update_data()
        z = result.zones[0]
        assert (z.serranda, z.serranda_set, z.fancoil, z.fancoil_set) == (1, 1, 3, 3)


class TestPolarisSetZoneSerranda:
    async def test_override_visible_during_send_and_restored(self, detail_coordinator, mock_polaris_client):
        zone = detail_coordinator.data.zones[0]
        zone.serranda = -1
        seen = []
        mock_polaris_client.set_zone_serranda.side_effect = lambda z, v: seen.append(z.serranda)

        await detail_coordinator.async_set_zone_serranda(1, 2)

        assert seen == [2]
        assert zone.serranda == -1
        detail_coordinator.async_request_refresh.assert_awaited_once()

    async def test_override_restored_when_send_fails(self, detail_coordinator, mock_polaris_client):
        zone = detail_coordinator.data.zones[0]
        zone.serranda = -1
        mock_polaris_client.set_zone_serranda.side_effect = OSError("boom")
        with pytest.raises(OSError):
            await detail_coordinator.async_set_zone_serranda(1, 2)
        assert zone.serranda == -1

    async def test_unknown_zone_sends_nothing(self, detail_coordinator, mock_polaris_client):
        await detail_coordinator.async_set_zone_serranda(99, 2)
        mock_polaris_client.set_zone_serranda.assert_not_called()

    async def test_mini_cache_writes_ev_only(self, detail_coordinator):
        # MiniDiscovery2X: writing shu would make the merge set zone.serranda
        # and add shu_set to every later command (issue #23 item 5).
        detail_coordinator._zone_details[1] = dict(MINI_DETAIL)
        await detail_coordinator.async_set_zone_serranda(1, 3)
        detail = detail_coordinator.zone_details[1]
        assert (detail["EV"], detail["EV_set"]) == (3, 3)
        assert (detail["shu"], detail["shu_set"]) == (-1, -1)

    async def test_stealth_cache_writes_shu_only(self, detail_coordinator):
        # Stealth2X: EV is the valve state and must not be overwritten.
        detail_coordinator._zone_details[1] = dict(STEALTH_DETAIL)
        await detail_coordinator.async_set_zone_serranda(1, 3)
        detail = detail_coordinator.zone_details[1]
        assert (detail["shu"], detail["shu_set"]) == (3, 3)
        assert (detail["EV"], detail["EV_set"]) == (0, 0)

    async def test_cache_updated_and_pushed_before_refresh(self, detail_coordinator):
        detail_coordinator._zone_details[1] = dict(MINI_DETAIL)
        seen = []
        detail_coordinator.async_update_listeners = MagicMock(
            side_effect=lambda: seen.append(("listeners", detail_coordinator.zone_details[1]["EV_set"]))
        )
        detail_coordinator.async_request_refresh.side_effect = lambda: seen.append(("refresh", None))
        await detail_coordinator.async_set_zone_serranda(1, 3)
        assert seen == [("listeners", 3), ("refresh", None)]

    async def test_no_cache_entry_no_listener_push(self, detail_coordinator):
        detail_coordinator.async_update_listeners = MagicMock()
        await detail_coordinator.async_set_zone_serranda(1, 3)
        detail_coordinator.async_update_listeners.assert_not_called()
        assert 1 not in detail_coordinator.zone_details


@pytest.fixture
def cloud_coordinator(mock_hass, mock_polaris_client, monkeypatch):
    """Real coordinator in cloud mode, sleeps recorded instead of awaited."""
    import custom_components.open_pico.polaris_coordinator as mod

    sleep = AsyncMock()
    monkeypatch.setattr(mod.asyncio, "sleep", sleep)
    mock_polaris_client.serial = "CU1"
    mock_polaris_client.get_zone_detail = AsyncMock()
    mock_polaris_client.set_zone_serranda = AsyncMock()
    coord = PolarisCoordinator(mock_hass, mock_polaris_client, "Cloud Polaris",
                               scan_interval=30, command_delay=3, cloud=True)
    coord.data = PolarisData(device=make_polaris_device(), zones=_zones(1))
    coord.async_request_refresh = AsyncMock()
    coord.sleep = sleep
    return coord


class TestPolarisCloudCoordinator:
    async def test_zone_details_built_from_cloud_zones(self, cloud_coordinator, mock_polaris_client):
        zones = [make_polaris_zone(zone_id=1, serranda=1, serranda_set=2, fancoil=-1, fancoil_set=-1, ev=0)]
        mock_polaris_client.async_update = AsyncMock(return_value=(make_polaris_device(), zones))

        await cloud_coordinator._async_update_data()

        mock_polaris_client.get_zone_detail.assert_not_called()  # stato_zona is local-only
        assert cloud_coordinator.zone_details[1] == {"shu": 1, "shu_set": 2, "fan": -1, "fan_set": -1, "EV": 0}

    async def test_command_waits_command_delay(self, cloud_coordinator, mock_polaris_client):
        await cloud_coordinator.async_turn_on()
        mock_polaris_client.turn_on.assert_called_once()
        cloud_coordinator.sleep.assert_awaited_once_with(3)
        cloud_coordinator.async_request_refresh.assert_awaited_once()

    async def test_serranda_waits_at_least_command_delay(self, cloud_coordinator):
        cloud_coordinator._command_delay = 5
        await cloud_coordinator.async_set_zone_serranda(1, 2)
        cloud_coordinator.sleep.assert_awaited_once_with(5)

    def test_serial_fallback_uses_cloud_serial(self, cloud_coordinator, mock_polaris_client):
        mock_polaris_client.device = None
        assert cloud_coordinator.serial == "CU1"

    async def test_local_command_keeps_default_delay(self, detail_coordinator, mock_polaris_client):
        import custom_components.open_pico.polaris_coordinator as mod

        await detail_coordinator.async_turn_on()
        mod.asyncio.sleep.assert_awaited_once_with(1.0)
