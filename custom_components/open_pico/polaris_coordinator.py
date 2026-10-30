"""DataUpdateCoordinator for Polaris 5X devices (local TCP port 1235)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging

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
        self._zone_details_fetched = False
        # Serialize all TCP communications to the CU.
        # The Polaris CU has a very limited TCP stack and cannot handle
        # concurrent connections â multiple simultaneous requests cause
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

    async def _async_update_data(self) -> PolarisData:
        """Fetch device + zone data via local TCP."""
        try:
            async with self._tcp_lock:
                device, zones = await self.client.async_update()

                # Fetch zone details (serranda/fancoil) on first successful update.
                # stato_zona returns per-zone data not included in stato_r.
                # Uses a 10s timeout to avoid blocking setup.
                if not self._zone_details_fetched and zones:
                    try:
                        # Workaround: fetch_all_zone_details() in the API library
                        # skips zones where is_off=True (user-disabled). This is a
                        # bug: it should skip zones where num_error!=0 (comm error).
                        # Temporarily remap is_off to reflect error state so the
                        # buggy skip condition works correctly.
                        saved_is_off = {}
                        for z in zones:
                            saved_is_off[z.zone_id] = z.is_off
                            z.is_off = bool(z.num_error)
                        try:
                            async with asyncio.timeout(10):
                                self._zone_details = await self.client.fetch_all_zone_details()
                        finally:
                            # Always restore original is_off values
                            for z in zones:
                                if z.zone_id in saved_is_off:
                                    z.is_off = saved_is_off[z.zone_id]
                        self._zone_details_fetched = True
                        _LOGGER.info(
                            "[%s] Fetched zone details for %d zones",
                            self.device_name, len(self._zone_details),
                        )
                    except Exception as err:
                        _LOGGER.warning(
                            "[%s] Failed to fetch zone details: %s",
                            self.device_name, err,
                        )
                        self._zone_details_fetched = True  # don't retry every poll

            # Merge cached serranda/fancoil data into zones (no TCP needed).
            # MiniDiscovery2X modules report serranda in EV/EV_set fields
            # (not shu/shu_set which stay -1). Use EV as fallback.
            for z in zones:
                detail = self._zone_details.get(z.zone_id)
                if detail:
                    shu = detail.get("shu", -1)
                    shu_set = detail.get("shu_set", -1)
                    # Fallback: MiniDiscovery2X uses EV/EV_set for serranda
                    if shu == -1 and detail.get("EV_set", -1) != -1:
                        shu = detail.get("EV", -1)
                        shu_set = detail.get("EV_set", -1)
                    z.serranda = shu
                    z.serranda_set = shu_set
                    z.fancoil = detail.get("fan", -1)
                    z.fancoil_set = detail.get("fan_set", -1)

            _LOGGER.debug(
                "[%s] Polaris update: on=%s, mode=%s, zones=%d",
                self.device_name,
                device.is_on,
                device.cooling_mode_name,
                len(zones),
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

    # âââ Helper properties âââââââââââââââââââââââââââââââââââââââââââ

    @property
    def polaris_device(self) -> PolarisDevice | None:
        return self.data.device if self.data else None

    @property
    def polaris_zones(self) -> list[PolarisZone]:
        return self.data.zones if self.data else []

    # âââ Control methods: device-level âââââââââââââââââââââââââââââââ

    async def async_turn_on(self) -> None:
        """Turn device on."""
        async with self._tcp_lock:
            await self.client.turn_on()
        await asyncio.sleep(_CMD_SETTLE_DELAY)
        await self.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn device off."""
        async with self._tcp_lock:
            await self.client.turn_off()
        await asyncio.sleep(_CMD_SETTLE_DELAY)
        await self.async_request_refresh()

    async def async_set_cooling_mode(self, mode: int) -> None:
        """Set cooling mode (1=raff, 2=deum, 3=vent)."""
        async with self._tcp_lock:
            await self.client.set_cooling_mode(mode)
        await asyncio.sleep(_CMD_SETTLE_DELAY)
        await self.async_request_refresh()

    async def async_set_heating_mode(self) -> None:
        """Switch to heating mode."""
        async with self._tcp_lock:
            await self.client.set_heating_mode()
        await asyncio.sleep(_CMD_SETTLE_DELAY)
        await self.async_request_refresh()

    # âââ Control methods: zone-level âââââââââââââââââââââââââââââââââ

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
            async with self._tcp_lock:
                await self.client.set_zone_temp(zone, temperature)
            await asyncio.sleep(_CMD_SETTLE_DELAY)
            await self.async_request_refresh()
        else:
            _LOGGER.error("Zone %d not found", zone_id)

    async def async_turn_zone_on(self, zone_id: int) -> None:
        """Turn a zone on."""
        zone = self._find_zone(zone_id)
        if zone:
            async with self._tcp_lock:
                await self.client.turn_zone_on(zone)
            await asyncio.sleep(_CMD_SETTLE_DELAY)
            await self.async_request_refresh()

    async def async_turn_zone_off(self, zone_id: int) -> None:
        """Turn a zone off."""
        zone = self._find_zone(zone_id)
        if zone:
            async with self._tcp_lock:
                await self.client.turn_zone_off(zone)
            await asyncio.sleep(_CMD_SETTLE_DELAY)
            await self.async_request_refresh()

    async def async_update_zone(self, zone_id: int, **kwargs) -> None:
        """Generic zone update with arbitrary kwargs."""
        zone = self._find_zone(zone_id)
        if zone:
            async with self._tcp_lock:
                await self.client.update_zone(zone, **kwargs)
            await asyncio.sleep(_CMD_SETTLE_DELAY)
            await self.async_request_refresh()

    async def async_set_zone_serranda(self, zone_id: int, value: int) -> None:
        """Set serranda (damper) value for a zone.

        Args:
            zone_id: The zone to update.
            value: 0=Auto, 1=A1, 2=A2, 3=A3.

        Important: upd_zona requires fan_set and shu_set to be set to the
        same value. Sending fan_set=-1 causes the Polaris CU to hang.
        """
        zone = self._find_zone(zone_id)
        if zone:
            async with self._tcp_lock:
                await self.client.set_zone_serranda(zone, value)
            # Update local cache so UI reflects the change immediately
            if zone_id in self._zone_details:
                self._zone_details[zone_id]["shu_set"] = value
                self._zone_details[zone_id]["shu"] = value
                # Also update EV fields for MiniDiscovery2X modules
                self._zone_details[zone_id]["EV_set"] = value
                self._zone_details[zone_id]["EV"] = value
            await asyncio.sleep(2)  # serranda needs more time to settle
            await self.async_request_refresh()
        else:
            _LOGGER.error("Zone %d not found for serranda update", zone_id)

    @property
    def zone_details(self) -> dict[int, dict]:
        """Return cached zone details (from stato_zona)."""
        return self._zone_details

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and disconnect client."""
        await self.client.close()
