"""DataUpdateCoordinator for Polaris 5X devices (local TCP port 1235)."""
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
    ) -> None:
        """Initialize."""
        self.client = client
        self.device_name = device_name
        self.polaris_ip = client.ip
        self._zone_details: dict[int, dict] = {}
        self._zone_refresh_index: int = 0
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
        return self.client.ip.replace(".", "_")

    # ─── Zone detail fetching (incremental + refresh) ───────────────

    def _zones_needing_details(self, zones: list[PolarisZone]) -> list[PolarisZone]:
        """Return zones that still need stato_zona data.

        Skips zones that already have details cached and zones with
        errors (num_error != 0), whose stato_zona data is unreliable.
        """
        return [
            z for z in zones
            if z.zone_id not in self._zone_details and not z.num_error
        ]

    @property
    def all_zone_details_fetched(self) -> bool:
        """True when every non-errored zone has cached details."""
        if not self.data or not self.data.zones:
            return False
        return len(self._zones_needing_details(self.data.zones)) == 0

    async def _async_fetch_zone_details_incremental(
        self, zones: list[PolarisZone],
    ) -> None:
        """Fetch stato_zona for a few zones per call, storing each result
        immediately so partial progress is never lost.

        Two modes:
        - Initial: fetch missing zones, up to _ZONE_DETAILS_PER_POLL per cycle.
        - Refresh: after all zones are cached, rotate through one zone per
          poll in round-robin to keep serranda/fancoil values fresh (~3 min
          per zone with 6 zones at 30s poll interval).
        """
        pending = self._zones_needing_details(zones)

        if pending:
            # Initial fetch: get missing zones
            batch = pending[:_ZONE_DETAILS_PER_POLL]
        else:
            # Refresh: round-robin through cached zones
            valid_zones = [z for z in zones if not z.num_error]
            if not valid_zones:
                return
            idx = self._zone_refresh_index % len(valid_zones)
            batch = [valid_zones[idx]]
            self._zone_refresh_index = idx + 1

        for zone in batch:
            try:
                detail = await self.client.get_zone_detail(zone.zone_id)
                if detail:
                    self._zone_details[zone.zone_id] = detail
                    _LOGGER.debug(
                        "[%s] Fetched details for zone %d (%s)",
                        self.device_name, zone.zone_id, zone.name,
                    )
                await asyncio.sleep(1)  # 1s spacing between stato_zona requests
            except Exception as err:
                _LOGGER.warning(
                    "[%s] Failed to fetch details for zone %d: %s",
                    self.device_name, zone.zone_id, err,
                )
                # Don't cache anything — will retry on next poll

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
                # After the initial fetch, we refresh one zone per poll
                # in round-robin to keep values fresh.
                if zones:
                    await self._async_fetch_zone_details_incremental(zones)

            # NOTE: We intentionally do NOT merge zone_details into the
            # PolarisZone objects (z.serranda, z.fancoil, etc.).
            # Reason: the library's update_zone() checks zone.serranda != -1
            # to decide whether to include shu_set/fan_set in every command.
            # If we set z.serranda from EV data, regular temp/on/off commands
            # would unnecessarily send shu_set, which is incorrect for
            # MiniDiscovery2X modules (see issue #23, item 5).
            # Climate entities read serranda values from coordinator.zone_details
            # instead.

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
        delay: float = _CMD_SETTLE_DELAY,
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
        await asyncio.sleep(delay)
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
        whether to include shu_set in the command. Since we no longer
        merge EV→serranda on zone objects (to avoid polluting regular
        commands), we temporarily set zone.serranda so the damper
        command is sent correctly, then restore it.
        """
        zone = self._find_zone(zone_id)
        if not zone:
            _LOGGER.error("Zone %d not found for serranda update", zone_id)
            return

        # Temporarily mark zone as having a serranda so the library
        # includes shu_set/fan_set in the upd_zona command.
        old_serranda = zone.serranda
        zone.serranda = value
        try:
            await self._command(
                self.client.set_zone_serranda(zone, value),
                delay=2,  # serranda needs more time to settle
            )
        finally:
            zone.serranda = old_serranda

        # Update local cache so UI reflects the change immediately
        if zone_id in self._zone_details:
            self._zone_details[zone_id]["shu_set"] = value
            self._zone_details[zone_id]["shu"] = value
            self._zone_details[zone_id]["EV_set"] = value
            self._zone_details[zone_id]["EV"] = value

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and disconnect client."""
        await self.client.close()
