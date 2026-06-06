"""Open Pico integration for Home Assistant.

Supports two device families:
  - Pico: Ventilation/air quality units (local UDP, ports 40069/40070)
  - Polaris 5: HVAC zone controllers (local TCP, port 1235)

Devices are added via the UI (Settings -> Integrations -> Add Integration).
"""
from __future__ import annotations

import asyncio
import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from open_polaris_local_api import PolarisLocalClient

from .const import DOMAIN
from .coordinator import MainCoordinator
from .pico_manager import PicoClientManager
from .polaris_coordinator import PolarisCoordinator

_LOGGER = logging.getLogger(__name__)

PICO_PLATFORMS: list[Platform] = [
    Platform.FAN,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
]

POLARIS_PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Open Pico from a UI config entry (one device per entry)."""
    hass.data.setdefault(DOMAIN, {})

    device_type = entry.data.get("device_type", "pico")

    if device_type == "pico":
        coordinator = await _setup_pico_entry(hass, entry)
        platforms = PICO_PLATFORMS
    elif device_type == "polaris":
        coordinator = await _setup_polaris_entry(hass, entry)
        platforms = POLARIS_PLATFORMS
    else:
        _LOGGER.error("Unknown device_type '%s' in config entry %s", device_type, entry.entry_id)
        return False

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "device_type": device_type,
    }

    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    _LOGGER.info("Config entry set up: %s (%s)", entry.title, device_type)
    return True


async def _setup_pico_entry(hass: HomeAssistant, entry: ConfigEntry) -> MainCoordinator:
    """Set up one Pico device from a config entry."""
    ip: str = entry.data["ip"]
    pin: str = entry.data["pin"]
    name: str = entry.data["name"]
    local_port: int = entry.data.get("local_port", 40069)
    verbose: bool = entry.data.get("verbose", False)
    name_slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    # PicoClientManager is a singleton shared across all Pico config entries
    if "pico_manager" not in hass.data[DOMAIN]:
        manager = PicoClientManager(local_port=local_port, verbose=verbose)
        try:
            await manager.initialize()
        except Exception as err:
            raise ConfigEntryNotReady(f"Failed to initialize shared UDP transport: {err}") from err
        hass.data[DOMAIN]["pico_manager"] = manager
    else:
        manager: PicoClientManager = hass.data[DOMAIN]["pico_manager"]

    device_id = f"pico_{name_slug}"
    client = manager.create_client(
        ip=ip, pin=pin, device_id=device_id,
        timeout=15, retry_attempts=3, retry_delay=2.0,
    )

    try:
        await asyncio.wait_for(client.connect(), timeout=30)
    except Exception as err:
        raise ConfigEntryNotReady(f"Cannot connect to Pico {ip}: {err}") from err

    coordinator = MainCoordinator(hass, client, name)

    try:
        async with asyncio.timeout(30):
            await coordinator.async_refresh()
    except Exception as err:
        await client.disconnect()
        raise ConfigEntryNotReady(f"Initial refresh failed for Pico {ip}: {err}") from err

    if not coordinator.last_update_success:
        await client.disconnect()
        raise ConfigEntryNotReady(
            f"Initial refresh failed for Pico {ip}: {coordinator.last_exception}"
        )

    return coordinator


async def _setup_polaris_entry(hass: HomeAssistant, entry: ConfigEntry) -> PolarisCoordinator:
    """Set up one Polaris device from a config entry."""
    ip: str = entry.data["ip"]
    pin: str = entry.data["pin"]
    name: str = entry.data["name"]
    scan_interval: int = entry.data.get("scan_interval", 30)
    verbose: bool = entry.data.get("verbose", False)
    name_slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    device_id = f"polaris_{name_slug}"
    client = PolarisLocalClient(
        ip=ip, pin=pin, device_id=device_id,
        port=1235, timeout=15, retry_attempts=3, retry_delay=2.0, verbose=verbose,
    )

    try:
        await asyncio.wait_for(client.connect(), timeout=30)
    except Exception as err:
        raise ConfigEntryNotReady(f"Cannot connect to Polaris {ip}: {err}") from err

    coordinator = PolarisCoordinator(hass, client, name, scan_interval=scan_interval)

    try:
        async with asyncio.timeout(30):
            await coordinator.async_refresh()
    except Exception as err:
        await client.close()
        raise ConfigEntryNotReady(f"Initial refresh failed for Polaris {ip}: {err}") from err

    if not coordinator.last_update_success:
        await client.close()
        raise ConfigEntryNotReady(
            f"Initial refresh failed for Polaris {ip}: {coordinator.last_exception}"
        )

    return coordinator


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    device_type = entry.data.get("device_type", "pico")
    platforms = PICO_PLATFORMS if device_type == "pico" else POLARIS_PLATFORMS

    unloaded = await hass.config_entries.async_unload_platforms(entry, platforms)

    if unloaded:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        coordinator = entry_data.get("coordinator")
        if coordinator:
            try:
                await coordinator.async_shutdown()
            except Exception as err:
                _LOGGER.error("Error shutting down coordinator for %s: %s", entry.title, err)

        if device_type == "pico":
            remaining_pico = any(
                e.data.get("device_type") == "pico"
                for e in hass.config_entries.async_entries(DOMAIN)
                if e.entry_id != entry.entry_id
            )
            if not remaining_pico and "pico_manager" in hass.data.get(DOMAIN, {}):
                try:
                    await hass.data[DOMAIN]["pico_manager"].shutdown()
                except Exception as err:
                    _LOGGER.error("Error shutting down PicoClientManager: %s", err)
                hass.data[DOMAIN].pop("pico_manager", None)

    _LOGGER.info("Config entry unloaded: %s", entry.title)
    return unloaded


