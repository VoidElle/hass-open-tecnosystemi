"""Open Pico integration for Home Assistant.

Supports two device families:
  - Pico: Ventilation/air quality units (local UDP, ports 40069/40070)
  - Polaris 5: HVAC zone controllers (local TCP, port 1235)
"""
from __future__ import annotations

import asyncio
import logging
import voluptuous as vol

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import MainCoordinator
from .pico_manager import PicoClientManager

_LOGGER = logging.getLogger(__name__)

# Platforms for Pico devices
PICO_PLATFORMS: list[Platform] = [
    Platform.FAN,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
]

# Platforms for Polaris devices
POLARIS_PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SENSOR,
]

# Define the Pico device schema (local UDP)
PICO_DEVICE_SCHEMA = vol.Schema({
    vol.Required("ip"): cv.string,
    vol.Required("pin"): cv.string,
    vol.Optional("name"): cv.string,
})

# Define the Polaris device schema (local TCP port 1235)
POLARIS_DEVICE_SCHEMA = vol.Schema({
    vol.Required("ip"): cv.string,
    vol.Required("pin"): cv.string,
    vol.Optional("name"): cv.string,
    # scan_interval: how often (seconds) to poll the device.
    # Lower values give faster updates but may disrupt the device's
    # persistent cloud connection (causing the official app to show
    # "Stato sistema non sincronizzato"). Default: 30s is a safe balance.
    vol.Optional("scan_interval", default=30): vol.All(int, vol.Range(min=10)),
})

# Define the YAML configuration schema
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema({
            vol.Optional("devices", default=[]): vol.All(cv.ensure_list, [PICO_DEVICE_SCHEMA]),
            vol.Optional("polaris_devices", default=[]): vol.All(cv.ensure_list, [POLARIS_DEVICE_SCHEMA]),
            vol.Optional("local_port", default=40069): cv.port,
            vol.Optional("verbose", default=False): cv.boolean,
        })
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Open Pico integration from YAML configuration."""

    if DOMAIN not in config:
        return True

    domain_config = config[DOMAIN]
    pico_devices = domain_config.get("devices", [])
    polaris_devices = domain_config.get("polaris_devices", [])
    local_port = domain_config.get("local_port", 40069)
    verbose = domain_config.get("verbose", False)

    _LOGGER.info(
        "Setting up %s with %d Pico device(s) and %d Polaris device(s)",
        DOMAIN, len(pico_devices), len(polaris_devices),
    )

    # Initialize hass.data for this domain
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinators"] = []
    hass.data[DOMAIN]["polaris_coordinators"] = []
    hass.data[DOMAIN]["config"] = domain_config

    platforms_needed: set[Platform] = set()

    # ─── Set up Pico devices (local UDP) ──────────────────────────────
    if pico_devices:
        successful_pico = await _setup_pico_devices(
            hass, pico_devices, local_port, verbose
        )
        if successful_pico > 0:
            platforms_needed.update(PICO_PLATFORMS)

    # ─── Set up Polaris devices (local TCP) ───────────────────────────
    if polaris_devices:
        successful_polaris = await _setup_polaris_devices(
            hass, polaris_devices, verbose
        )
        if successful_polaris > 0:
            platforms_needed.update(POLARIS_PLATFORMS)

    # Check if we have anything
    total = len(hass.data[DOMAIN]["coordinators"]) + len(hass.data[DOMAIN]["polaris_coordinators"])
    if total == 0:
        _LOGGER.error("No devices were successfully set up")
        return False

    # Load platforms using discovery
    for platform in platforms_needed:
        hass.async_create_task(
            discovery.async_load_platform(hass, platform, DOMAIN, {}, config)
        )

    _LOGGER.info("Open Pico integration setup complete: %d total device(s)", total)
    return True


async def _setup_pico_devices(
    hass: HomeAssistant,
    devices: list[dict],
    local_port: int,
    verbose: bool,
) -> int:
    """Set up Pico devices with shared UDP transport. Returns count of successful devices."""

    manager = PicoClientManager(local_port=local_port, verbose=verbose)

    try:
        await manager.initialize()
        hass.data[DOMAIN]["manager"] = manager
        _LOGGER.info("Shared transport initialized on port %d", local_port)
    except Exception as err:
        _LOGGER.error("Failed to initialize shared transport: %s", err, exc_info=True)
        return 0

    successful = 0
    for idx, device_config in enumerate(devices):
        pico_ip = device_config.get("ip")
        pin = device_config.get("pin")
        device_name = device_config.get("name", f"Pico Device {idx + 1}")

        _LOGGER.debug("Setting up Pico device '%s': ip=%s", device_name, pico_ip)

        try:
            device_id = f"pico_{pico_ip.replace('.', '_')}"
            client = manager.create_client(
                ip=pico_ip, pin=pin, device_id=device_id,
                timeout=15, retry_attempts=3, retry_delay=2.0,
            )

            await client.connect()
            coordinator = MainCoordinator(hass, client, device_name)

            try:
                async with asyncio.timeout(30):
                    await coordinator.async_refresh()
                    if not coordinator.last_update_success:
                        raise Exception(f"Initial refresh failed: {coordinator.last_exception}")
            except asyncio.TimeoutError:
                _LOGGER.error("Timeout during initial refresh for Pico '%s' (%s)", device_name, pico_ip)
                await client.disconnect()
                continue
            except Exception as err:
                _LOGGER.error("Initial refresh failed for Pico '%s' (%s): %s", device_name, pico_ip, err)
                await client.disconnect()
                continue

            if not coordinator.data:
                _LOGGER.error("No data from Pico '%s' (%s)", device_name, pico_ip)
                await client.disconnect()
                continue

            hass.data[DOMAIN]["coordinators"].append(coordinator)
            successful += 1

            _LOGGER.info(
                "Pico '%s' (%s): Mode=%s, Temp=%.1f°C, Humidity=%.1f%%",
                device_name, pico_ip,
                coordinator.data.operating.mode.name,
                coordinator.data.sensors.temperature,
                coordinator.data.sensors.humidity,
            )

        except Exception as err:
            _LOGGER.error("Error setting up Pico '%s' (%s): %s", device_name, pico_ip, err, exc_info=True)
            continue

    return successful


async def _setup_polaris_devices(
    hass: HomeAssistant,
    devices: list[dict],
    verbose: bool,
) -> int:
    """Set up Polaris devices with local TCP transport (port 1235).

    Each entry requires 'ip' and 'pin'.
    """
    from .polaris_api.polaris_client import PolarisLocalClient
    from .polaris_coordinator import PolarisCoordinator

    successful = 0

    for idx, device_config in enumerate(devices):
        polaris_ip = device_config.get("ip")
        pin = device_config.get("pin")
        device_name = device_config.get("name", f"Polaris Device {idx + 1}")
        scan_interval = device_config.get("scan_interval", 30)

        _LOGGER.debug("Setting up Polaris device '%s': ip=%s", device_name, polaris_ip)

        try:
            device_id = f"polaris_{polaris_ip.replace('.', '_')}"

            client = PolarisLocalClient(
                ip=polaris_ip,
                pin=pin,
                device_id=device_id,
                port=1235,
                timeout=15,
                retry_attempts=3,
                retry_delay=2.0,
                verbose=verbose,
            )

            # connect() does the initial async_update() internally,
            # so device + zones are already populated after this call.
            try:
                async with asyncio.timeout(30):
                    await client.connect()
                    device = client.device
                    zones = client.zones
            except asyncio.TimeoutError:
                _LOGGER.error(
                    "Timeout connecting to Polaris '%s' (%s)",
                    device_name, polaris_ip,
                )
                continue
            except Exception as err:
                _LOGGER.error(
                    "Failed to connect to Polaris '%s' (%s): %s",
                    device_name, polaris_ip, err,
                )
                continue

            # Use the name from the device if not explicitly set in config
            if device.name and device.name != "Unknown" and "name" not in device_config:
                device_name = device.name

            coordinator = PolarisCoordinator(hass, client, device_name, scan_interval=scan_interval)

            # Initial refresh through the coordinator
            try:
                async with asyncio.timeout(30):
                    await coordinator.async_refresh()
                    if not coordinator.last_update_success:
                        raise Exception(
                            f"Coordinator refresh failed: {coordinator.last_exception}"
                        )
            except Exception as err:
                _LOGGER.error(
                    "Coordinator refresh failed for Polaris '%s': %s",
                    device_name, err,
                )
                await client.disconnect()
                continue

            hass.data[DOMAIN]["polaris_coordinators"].append(coordinator)
            successful += 1

            _LOGGER.info(
                "Polaris '%s' (%s): on=%s, mode=%s, zones=%d",
                device_name, polaris_ip,
                device.is_on, device.cooling_mode_name, len(zones),
            )

        except Exception as err:
            _LOGGER.error(
                "Error setting up Polaris '%s': %s",
                device_name, err, exc_info=True,
            )
            continue

    return successful


async def async_unload_entry(hass: HomeAssistant) -> bool:
    """Unload the integration."""
    _LOGGER.info("Unloading %s integration", DOMAIN)

    # Shutdown Pico coordinators
    if DOMAIN in hass.data and "coordinators" in hass.data[DOMAIN]:
        for coordinator in hass.data[DOMAIN]["coordinators"]:
            try:
                await coordinator.async_shutdown()
            except Exception as err:
                _LOGGER.error("Error shutting down Pico coordinator: %s", err)

    # Shutdown Polaris coordinators
    if DOMAIN in hass.data and "polaris_coordinators" in hass.data[DOMAIN]:
        for coordinator in hass.data[DOMAIN]["polaris_coordinators"]:
            try:
                await coordinator.async_shutdown()
            except Exception as err:
                _LOGGER.error("Error shutting down Polaris coordinator: %s", err)

    # Shutdown the shared Pico manager
    if DOMAIN in hass.data and "manager" in hass.data[DOMAIN]:
        try:
            await hass.data[DOMAIN]["manager"].shutdown()
        except Exception as err:
            _LOGGER.error("Error shutting down manager: %s", err)

    # Remove services
    for service in hass.services.async_services_for_domain(DOMAIN):
        hass.services.async_remove(DOMAIN, service)

    if DOMAIN in hass.data:
        hass.data.pop(DOMAIN)

    _LOGGER.info("Successfully unloaded %s", DOMAIN)
    return True
