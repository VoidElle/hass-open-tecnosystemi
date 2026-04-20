"""DataUpdateCoordinator for Polaris 5 devices (local TCP port 1235)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .polaris_api.polaris_client import PolarisLocalClient, PolarisApiError
from .polaris_api.models import PolarisDevice, PolarisZone

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Local TCP polling (port 1235)
POLARIS_SCAN_INTERVAL = 5


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
    ) -> None:
        """Initialize."""
        self.client = client
        self.device_name = device_name
        self.polaris_ip = client.ip

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} Polaris ({device_name})",
            update_method=self._async_update_data,
            update_interval=timedelta(seconds=POLARIS_SCAN_INTERVAL),
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
            device, zones = await self.client.async_update()

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

    # ─── Helper properties ───────────────────────────────────────────

    @property
    def polaris_device(self) -> PolarisDevice | None:
        return self.data.device if self.data else None

    @property
    def polaris_zones(self) -> list[PolarisZone]:
        return self.data.zones if self.data else []

    # ─── Control methods: device-level ───────────────────────────────

    async def async_turn_on(self) -> None:
        """Turn device on."""
        await self.client.turn_on()
        await self.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn device off."""
        await self.client.turn_off()
        await self.async_request_refresh()

    async def async_set_cooling_mode(self, mode: int) -> None:
        """Set cooling mode (1=raff, 2=deum, 3=vent)."""
        await self.client.set_cooling_mode(mode)
        await self.async_request_refresh()

    async def async_set_heating_mode(self) -> None:
        """Switch to heating mode."""
        await self.client.set_heating_mode()
        await self.async_request_refresh()

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
            await self.client.set_zone_temp(zone, temperature)
            await self.async_request_refresh()
        else:
            _LOGGER.error("Zone %d not found", zone_id)

    async def async_turn_zone_on(self, zone_id: int) -> None:
        """Turn a zone on."""
        zone = self._find_zone(zone_id)
        if zone:
            await self.client.turn_zone_on(zone)
            await self.async_request_refresh()

    async def async_turn_zone_off(self, zone_id: int) -> None:
        """Turn a zone off."""
        zone = self._find_zone(zone_id)
        if zone:
            await self.client.turn_zone_off(zone)
            await self.async_request_refresh()

    async def async_update_zone(self, zone_id: int, **kwargs) -> None:
        """Generic zone update with arbitrary kwargs."""
        zone = self._find_zone(zone_id)
        if zone:
            await self.client.update_zone(zone, **kwargs)
            await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and disconnect client."""
        await self.client.close()
