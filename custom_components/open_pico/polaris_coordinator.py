"""DataUpdateCoordinator for Polaris 5X devices (local TCP port 1235, or the vendor cloud as fallback)."""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from open_polaris_local_api import PolarisLocalClient, PolarisApiError, PolarisDevice, PolarisZone

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Local TCP polling (port 1235).
# 30 seconds avoids overwhelming the CU's limited TCP stack,
# which would block the official app's cloud sync.
POLARIS_SCAN_INTERVAL = 30

# Delay (seconds) after sending a command before polling.
# The Polaris CU needs time to process commands; polling too
# soon returns stale state, causing the UI to "bounce back".
_CMD_SETTLE_DELAY = 1.0

# Maximum zone detail requests per poll cycle.
# Fetching all zones at once can exceed the setup timeout (30s) or
# overwhelm the CU.  Instead, fetch a few zones per poll cycle and
# accumulate results across polls.
_ZONE_DETAILS_PER_POLL = 2

# After initial fetch, refresh one zone every N polls (round-robin).
# With 6 zones at 30s poll interval and N=3, each zone refreshes
# every ~18 polls = ~9 min.  This keeps serranda/fancoil values
# reasonably fresh without adding a stato_zona to every poll.
_ZONE_REFRESH_INTERVAL = 3

# Maximum consecutive failures before a zone is skipped for details.
# Reset to 0 on success.  Dynamic SWING_MODE handles the zone
# showing up one poll after recovery.
_MAX_ZONE_FAILURES = 3


@dataclass
class PolarisData:
    """Container for Polaris coordinator data."""

    device: PolarisDevice
    zones: list[PolarisZone]


class PolarisCoordinator(DataUpdateCoordinator[PolarisData]):
    """Coordinator for a single Polaris CU (Control Unit) via local TCP."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: PolarisLocalClient,
        device_name: str,
        scan_interval: int = POLARIS_SCAN_INTERVAL,
        command_delay: float = _CMD_SETTLE_DELAY,
        cloud: bool = False,
    ) -> None:
        """Initialize.

        cloud=True: client is a PolarisCloudClient. Zone details come from the
        GetCUState zones (no stato_zona calls) and command_delay is longer
        because the backend applies commands asynchronously.
        """
        self.client = client
        self._cloud = cloud
        self._command_delay = command_delay
        self.device_name = device_name
        self.polaris_ip = client.ip
        self._zone_details: dict[int, dict] = {}
        self._zone_refresh_index: int = 0
        self._zone_failures: dict[int, int] = {}
        self._poll_count: int = 0
        # Serialize all TCP communications to the CU.
        # The Polaris CU has a very limited TCP stack and cannot handle
        # concurrent connections -- multiple simultaneous requests cause
        # it to stop responding entirely, requiring a physical reset.
        self._tcp_lock = asyncio.Lock()

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} Polaris ({device_name})",
            update_method=self._async_update_data,
            update_interval=timedelta(seconds=scan_interval),
        )

    @property
    def serial(self) -> str:
        """Return device serial (from last status, or IP-based fallback)."""
        if self.client.device and self.client.device.serial:
            return self.client.device.serial
        if self._cloud:
            return self.client.serial
        return self.client.ip.replace(".", "_")

    # ─── Zone detail fetching (incremental + refresh) ───────────────

    def _zones_needing_details(self, zones: list[PolarisZone]) -> list[PolarisZone]:
        """Return zones that still need stato_zona data.

        Skips zones that already have details cached, zones with
        errors (num_error != 0), and zones that have failed too
        many times consecutively.
        """
        return [
            z for z in zones
            if z.zone_id not in self._zone_details
            and not z.num_error
            and self._zone_failures.get(z.zone_id, 0) < _MAX_ZONE_FAILURES
        ]

    async def _async_fetch_zone_details_incremental(
        self, zones: list[PolarisZone],
    ) -> None:
        """Fetch stato_zona for a few zones per call, storing each result
        immediately so partial progress is never lost.

        Two modes:
        - Initial: fetch missing zones, up to _ZONE_DETAILS_PER_POLL per cycle.
        - Refresh: after all zones are cached, rotate through one zone per
          _ZONE_REFRESH_INTERVAL polls in round-robin to keep serranda/fancoil
          values fresh.
        """
        pending = self._zones_needing_details(zones)

        if pending:
            # Initial fetch: get missing zones
            batch = pending[:_ZONE_DETAILS_PER_POLL]
        else:
            # Refresh: only run every N polls to reduce CU load
            if self._poll_count % _ZONE_REFRESH_INTERVAL != 0:
                return
            valid_zones = [z for z in zones if not z.num_error]
            if not valid_zones:
                return
            idx = self._zone_refresh_index % len(valid_zones)
            batch = [valid_zones[idx]]
            self._zone_refresh_index = idx + 1

        for zone in batch:
            try:
                async with asyncio.timeout(self.client.timeout + 1):
                    detail = await self.client.get_zone_detail(zone.zone_id)
                if detail:
                    self._zone_details[zone.zone_id] = detail
                    self._zone_failures.pop(zone.zone_id, None)
                    _LOGGER.debug(
                        "[%s] Fetched details for zone %d (%s)",
                        self.device_name, zone.zone_id, zone.name,
                    )
            except Exception as err:
                fails = self._zone_failures.get(zone.zone_id, 0) + 1
                self._zone_failures[zone.zone_id] = fails
                _LOGGER.warning(
                    "[%s] Failed to fetch details for zone %d (%d/%d): %s",
                    self.device_name, zone.zone_id, fails,
                    _MAX_ZONE_FAILURES, err,
                )
            # 1s spacing between stato_zona requests — runs even after
            # a failure so the next request doesn't fire immediately.
            await asyncio.sleep(1)

        if pending:
            remaining = len(pending) - len(batch)
            if remaining > 0:
                _LOGGER.debug(
                    "[%s] Zone details: %d cached, %d remaining",
                    self.device_name, len(self._zone_details), remaining,
                )
            else:
                _LOGGER.info(
                    "[%s] All zone details fetched (%d zones)",
                    self.device_name, len(self._zone_details),
                )

    # ─── Main update ─────────────────────────────────────────────────

    async def _async_update_data(self) -> PolarisData:
        """Fetch device + zone data via local TCP."""
        try:
            async with self._tcp_lock:
                device, zones = await self.client.async_update()

                # Incrementally fetch zone details (serranda/fancoil).
                # stato_zona returns per-zone data not included in stato_r.
                # We fetch a few zones per poll cycle and accumulate results,
                # so a single slow/errored zone never blocks the others.
                #
                # Skip on the first refresh (self.data is None) because it
                # runs inside the 30s setup timeout in __init__.py; a single
                # slow zone could fail the whole setup.
                if self._cloud:
                    # stato_zona is local-only, but GetCUState zones already carry
                    # its serranda/fancoil fields: rebuild the cache from them.
                    # The cloud has no EV_set, so MiniDiscovery2X zones get no swing.
                    self._zone_details = {
                        z.zone_id: {
                            "shu": z.serranda, "shu_set": z.serranda_set,
                            "fan": z.fancoil, "fan_set": z.fancoil_set, "EV": z.ev,
                        }
                        for z in zones
                    }
                elif zones and self.data is not None:
                    await self._async_fetch_zone_details_incremental(zones)

            self._poll_count += 1

            # Merge cached serranda/fancoil data into zone objects.
            # The library's update_zone() checks zone.serranda != -1 and
            # zone.fancoil != -1 to decide whether to include shu_set/fan_set
            # in commands.  Without this merge, temp/on/off commands would
            # stop sending fan_set on fancoil zones.
            #
            # We merge only shu/shu_set/fan/fan_set — NOT the EV→shu fallback.
            # MiniDiscovery2X zones report shu=-1 in stato_zona, so z.serranda
            # stays -1 and ordinary commands correctly skip shu_set for them.
            # The swing_mode UI reads EV_set from zone_details directly.
            for z in zones:
                detail = self._zone_details.get(z.zone_id)
                if detail:
                    z.serranda = detail.get("shu", -1)
                    z.serranda_set = detail.get("shu_set", -1)
                    z.fancoil = detail.get("fan", -1)
                    z.fancoil_set = detail.get("fan_set", -1)

            _LOGGER.debug(
                "[%s] Polaris update: on=%s, mode=%s, zones=%d",
                self.device_name,
                device.is_on,
                device.cooling_mode_name,
                len(zones),
            )

            if self.client.verbose:
                _LOGGER.debug(
                    "[Polaris][%s] Device state: is_off=%s, is_cooling=%s, "
                    "operating_mode=%d (%s), t_can=%s, f_inv=%s, f_est=%s, "
                    "ir_present=%s, num_errors=%s, serial=%s, fw=%s",
                    self.device_name,
                    device.is_off, device.is_cooling,
                    device.operating_mode, device.cooling_mode_name,
                    device.t_can, device.f_inv, device.f_est,
                    device.ir_present, device.num_errors,
                    device.serial, device.fw_ver,
                )
                for z in zones:
                    detail = self._zone_details.get(z.zone_id, {})
                    _LOGGER.debug(
                        "[Polaris][%s] Zone '%s' (id=%d): is_off=%s, "
                        "temp=%s, set_temp=%s, humidity=%s, set_humidity=%s, "
                        "shu=%s, shu_set=%s, EV=%s, EV_set=%s, "
                        "fan=%s, fan_set=%s, "
                        "ev=%s, is_crono=%s, num_error=%s",
                        self.device_name, z.name, z.zone_id,
                        z.is_off, z.current_temp, z.set_temp,
                        z.humidity, z.set_humidity,
                        detail.get("shu", "?"), detail.get("shu_set", "?"),
                        detail.get("EV", "?"), detail.get("EV_set", "?"),
                        detail.get("fan", "?"), detail.get("fan_set", "?"),
                        z.ev, z.is_crono_mode, z.num_error,
                    )

            return PolarisData(device=device, zones=zones)

        except PolarisApiError as err:
            raise UpdateFailed(f"Polaris error: {err}") from err
        except TimeoutError as err:
            raise UpdateFailed(f"Polaris timeout: {err}") from err
        except Exception as err:
            _LOGGER.error(
                "[%s] Error polling Polaris: %s",
                self.device_name, err, exc_info=True,
            )
            raise UpdateFailed(f"Error polling Polaris: {err}") from err

    # ─── Helper properties ───────────────────────────────────────────

    @property
    def polaris_device(self) -> PolarisDevice | None:
        return self.data.device if self.data else None

    @property
    def polaris_zones(self) -> list[PolarisZone]:
        return self.data.zones if self.data else []

    @property
    def zone_details(self) -> dict[int, dict]:
        """Return cached zone details (from stato_zona)."""
        return self._zone_details

    # ─── Command helper ──────────────────────────────────────────────

    async def _command(
        self,
        coro: Coroutine[Any, Any, Any],
        delay: float | None = None,
    ) -> None:
        """Send a command under the TCP lock, wait, then refresh.

        All control methods follow the same pattern:
        1. Acquire the TCP lock (serialize with polling).
        2. Send the command.
        3. Wait for the CU to process the change.
        4. Request a data refresh so the UI updates.
        """
        async with self._tcp_lock:
            await coro
        await asyncio.sleep(self._command_delay if delay is None else delay)
        await self.async_request_refresh()

    # ─── Control methods: device-level ───────────────────────────────

    async def async_turn_on(self) -> None:
        """Turn device on."""
        await self._command(self.client.turn_on())

    async def async_turn_off(self) -> None:
        """Turn device off."""
        await self._command(self.client.turn_off())

    async def async_set_hvac(self, is_cooling: bool, mode: int) -> None:
        """Set CU on with the given heating/cooling mode."""
        await self._command(
            self.client.update_cu(
                is_off=False, is_cooling=is_cooling, operating_mode=mode,
            )
        )

    async def async_set_cooling_mode(self, mode: int) -> None:
        """Set cooling mode (1=raff, 2=deum, 3=vent)."""
        await self._command(self.client.set_cooling_mode(mode))

    async def async_set_heating_mode(self) -> None:
        """Switch to heating mode."""
        await self._command(self.client.set_heating_mode())

    # ─── Control methods: zone-level ─────────────────────────────────

    def _find_zone(self, zone_id: int) -> PolarisZone | None:
        """Find zone by ID in current data."""
        for z in self.polaris_zones:
            if z.zone_id == zone_id:
                return z
        return None

    async def async_set_zone_temp(self, zone_id: int, temperature: float) -> None:
        """Set zone target temperature."""
        zone = self._find_zone(zone_id)
        if zone:
            await self._command(self.client.set_zone_temp(zone, temperature))
        else:
            _LOGGER.error("Zone %d not found", zone_id)

    async def async_turn_zone_on(self, zone_id: int) -> None:
        """Turn a zone on."""
        zone = self._find_zone(zone_id)
        if zone:
            await self._command(self.client.turn_zone_on(zone))

    async def async_turn_zone_off(self, zone_id: int) -> None:
        """Turn a zone off."""
        zone = self._find_zone(zone_id)
        if zone:
            await self._command(self.client.turn_zone_off(zone))

    async def async_update_zone(self, zone_id: int, **kwargs) -> None:
        """Generic zone update with arbitrary kwargs."""
        zone = self._find_zone(zone_id)
        if zone:
            await self._command(self.client.update_zone(zone, **kwargs))

    async def async_set_zone_serranda(self, zone_id: int, value: int) -> None:
        """Set serranda (damper) value for a zone.

        Args:
            zone_id: The zone to update.
            value: 0=Auto, 1=A1, 2=A2, 3=A3.

        The library's update_zone checks zone.serranda != -1 to decide
        whether to include shu_set in the command.  For MiniDiscovery2X
        zones, shu is always -1 (serranda is reported via EV/EV_set).
        We temporarily set zone.serranda so the damper command includes
        shu_set, then restore it immediately — while still holding the
        lock — so a concurrent command cannot see the override.
        """
        zone = self._find_zone(zone_id)
        if not zone:
            _LOGGER.error("Zone %d not found for serranda update", zone_id)
            return

        # Send the command under the lock, restoring zone.serranda
        # before releasing so no other command sees the override.
        async with self._tcp_lock:
            old_serranda = zone.serranda
            zone.serranda = value
            try:
                await self.client.set_zone_serranda(zone, value)
            finally:
                zone.serranda = old_serranda

        # Update the cache before the refresh so the UI shows the new position
        # immediately. Write only the fields the module uses: shu on Stealth2X,
        # EV on MiniDiscovery2X (shu == -1). Writing shu there would make the
        # merge set zone.serranda and add shu_set to every later command; writing
        # EV on Stealth2X would overwrite its valve state.
        detail = self._zone_details.get(zone_id)
        if detail:
            if detail.get("shu", -1) != -1:
                detail["shu"] = detail["shu_set"] = value
            else:
                detail["EV"] = detail["EV_set"] = value
            self.async_update_listeners()

        # Serranda needs more time to settle than other commands.
        await asyncio.sleep(max(2, self._command_delay))
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and disconnect client."""
        await self.client.close()
