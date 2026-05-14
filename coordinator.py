"""DataUpdateCoordinator for Open Pico integration."""

from datetime import timedelta
import logging
import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from pico_client import PicoClient
from models.pico_device_model import PicoDeviceModel
from enums.device_mode_enum import DeviceModeEnum

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class MainCoordinator(DataUpdateCoordinator):
    """The main coordinator for Open Pico devices."""

    data: PicoDeviceModel | None

    def __init__(
            self,
            hass: HomeAssistant,
            client: PicoClient,
            device_name: str = None
    ) -> None:
        """Initialize coordinator."""
        self.client = client
        self.pico_ip = client.ip
        self.device_id = client.device_id
        self.device_name = device_name or f"Pico {client.ip}"

        # Track consecutive failures for IDP reset
        self._consecutive_failures = 0
        self._max_failures_before_reset = 3

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({self.device_name})",
            update_method=self.async_update_data,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def async_update_data(self) -> PicoDeviceModel:
        """
        Fetch data from device.

        This is called independently by Home Assistant's coordinator
        for each device at the specified update_interval.
        No coordination with other devices is needed!
        """
        try:
            _LOGGER.debug("[%s] Starting data update", self.device_name)

            # Check connection status
            if not self.client.connected:
                _LOGGER.warning("[%s] Device not connected, attempting to reconnect...", self.device_name)
                try:
                    await self.client.connect()
                    _LOGGER.info("[%s] Reconnected successfully", self.device_name)
                except Exception as conn_err:
                    raise UpdateFailed(f"Failed to reconnect: {conn_err}") from conn_err

            # Get device status (independent API call)
            status = await self.client.get_status(retry=True)

            if status is None:
                raise UpdateFailed("Device returned no status data")

            _LOGGER.debug(
                "[%s] Status: ON=%s, Mode=%s, Temp=%.1f°C, Humidity=%.1f%%, Speed=%d%%",
                self.device_name,
                status.is_on,
                status.operating.mode.name,
                status.sensors.temperature,
                status.sensors.humidity,
                status.operating.speed_row
            )

            return status

        except UpdateFailed:
            # Re-raise UpdateFailed as-is
            raise
        except Exception as err:
            _LOGGER.error(
                "[%s] Error communicating with device: %s",
                self.device_name, err, exc_info=True
            )
            raise UpdateFailed(f"Error communicating with device: {err}") from err

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        _LOGGER.debug("[%s] Shutting down coordinator", self.device_name)
        # Client disconnect is handled by PicoClientManager
        pass

    @property
    def family_name(self) -> str:
        """Return a normalized device name suitable for use in unique IDs.

        Derived from the user-configured ``name`` in configuration.yaml, which
        is stable and unique even when the device IP address changes.

        Example: "Living Room Pico" → "living_room_pico"
        """
        return re.sub(r"[^a-z0-9]+", "_", self.device_name.lower()).strip("_")

    # Helper properties for easy access to device data
    @property
    def is_on(self) -> bool:
        """Check if device is on."""
        return self.data.is_on if self.data else False

    @property
    def temperature(self) -> float:
        """Get current temperature."""
        return self.data.sensors.temperature if self.data else 0.0

    @property
    def humidity(self) -> float:
        """Get current humidity."""
        return self.data.sensors.humidity if self.data else 0.0

    @property
    def air_quality(self) -> int:
        """Get air quality index."""
        return self.data.sensors.air_quality if self.data else 0

    @property
    def current_mode(self) -> DeviceModeEnum | None:
        """Get current operating mode."""
        return self.data.operating.mode if self.data else None

    @property
    def fan_speed(self) -> int:
        """Get current fan speed percentage."""
        return self.data.operating.speed_requested if self.data else 0

    @property
    def night_mode_enabled(self) -> bool:
        """Check if night mode is enabled."""
        return self.data.operating.night_mode == 1 if self.data else False

    @property
    def supports_fan_speed(self) -> bool:
        """Check if device supports fan speed control."""
        return self.data.support_fan_speed_control if self.data else False

    @property
    def supports_night_mode(self) -> bool:
        """Check if device supports night mode."""
        return self.data.support_night_mode_toggle if self.data else False

    @property
    def supports_target_humidity(self) -> bool:
        """Check if device supports target humidity selection."""
        return self.data.support_target_humidity_selection if self.data else False

    # Control methods - these trigger immediate actions followed by refresh
    async def async_turn_on(self) -> None:
        """Turn the device on."""
        _LOGGER.debug("[%s] Turning ON", self.device_name)
        await self.client.turn_on(retry=True)
        await self.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn the device off."""
        _LOGGER.debug("[%s] Turning OFF", self.device_name)
        await self.client.turn_off(retry=True)
        await self.async_request_refresh()

    async def async_set_mode(self, mode: DeviceModeEnum | int) -> None:
        """Set operating mode."""
        _LOGGER.debug("[%s] Setting mode to %s", self.device_name, mode)
        await self.client.change_operating_mode(mode, retry=True)
        await self.async_request_refresh()

    async def async_set_fan_speed(self, percentage: int) -> None:
        """Set fan speed percentage."""
        _LOGGER.debug("[%s] Setting fan speed to %d%%", self.device_name, percentage)

        if not self.supports_fan_speed and percentage != 100:
            raise ValueError(f"Device does not support fan speed control in current mode ({self.current_mode})")

        await self.client.change_fan_speed(percentage, retry=True, force=False)
        await self.async_request_refresh()

    async def async_set_night_mode(self, enable: bool) -> None:
        """Set night mode."""
        _LOGGER.debug("[%s] Setting night mode to %s", self.device_name, enable)

        if not self.supports_night_mode:
            raise ValueError(f"Device does not support night mode in current mode ({self.current_mode})")

        await self.client.set_night_mode(enable, retry=True, force=False)
        await self.async_request_refresh()

    async def async_set_led_status(self, enable: bool) -> None:
        """Set LED status."""
        _LOGGER.debug("[%s] Setting LED to %s", self.device_name, "ON" if enable else "OFF")
        await self.client.set_led_status(enable, retry=True)
        await self.async_request_refresh()

    async def async_set_target_humidity(self, target: int) -> None:
        """Set target humidity."""
        _LOGGER.debug("[%s] Setting target humidity to %d", self.device_name, target)

        if not self.supports_target_humidity:
            raise ValueError(f"Device does not support target humidity in current mode ({self.current_mode})")

        await self.client.set_target_humidity(target, retry=True, force=False)
        await self.async_request_refresh()