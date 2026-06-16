"""Shared fixtures for Open Tecnosystemi tests.

All HA objects (HomeAssistant, ConfigEntry, coordinators, clients) are mocked
so tests run without a real HA instance or physical devices.
"""
from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# Patch async_write_ha_state on the HA Entity base so entity tests don't need
# a real hass instance wired up. Autouse so all tests get it automatically.
@pytest.fixture(autouse=True)
def patch_write_ha_state():
    with patch("homeassistant.helpers.entity.Entity.async_write_ha_state"):
        yield

# ---------------------------------------------------------------------------
# Stub external packages before any integration code is imported
# ---------------------------------------------------------------------------

def _make_stub(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


# open_pico_local_api stubs
class _PicoDeviceModel:
    pass

class _DeviceModeEnum:
    def __init__(self, value):
        self.value = value
        self.name = f"MODE_{value}"

class _TargetHumidityEnum:
    def __init__(self, value):
        self.value = value

class _PicoClient:
    pass

class _SharedTransportManager:
    @staticmethod
    async def get_instance():
        return MagicMock()

class _PicoAutoDiscovery:
    @staticmethod
    async def discover(pin, subnet):
        return []

pico_api_mod = _make_stub(
    "open_pico_local_api",
    PicoDeviceModel=_PicoDeviceModel,
    DeviceModeEnum=_DeviceModeEnum,
    TargetHumidityEnum=_TargetHumidityEnum,
    PicoClient=_PicoClient,
    SharedTransportManager=_SharedTransportManager,
    PicoAutoDiscovery=_PicoAutoDiscovery,
)
sys.modules.setdefault("open_pico_local_api", pico_api_mod)

# open_polaris_local_api stubs
class _PolarisLocalClient:
    pass

class _PolarisApiError(Exception):
    pass

class _PolarisDevice:
    pass

class _PolarisZone:
    pass

class _PolarisAutoDiscovery:
    @staticmethod
    async def discover(pin, subnet):
        return []

polaris_api_mod = _make_stub(
    "open_polaris_local_api",
    PolarisLocalClient=_PolarisLocalClient,
    PolarisApiError=_PolarisApiError,
    PolarisDevice=_PolarisDevice,
    PolarisZone=_PolarisZone,
    PolarisAutoDiscovery=_PolarisAutoDiscovery,
)
sys.modules.setdefault("open_polaris_local_api", polaris_api_mod)

# ---------------------------------------------------------------------------
# Patch HA's frame helper so coordinators can be instantiated in tests
# without a running HA event loop / frame setup.
# ---------------------------------------------------------------------------
try:
    import homeassistant.helpers.frame as _ha_frame
    _ha_frame.report_usage = lambda *args, **kwargs: None
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Helpers to build mock data objects
# ---------------------------------------------------------------------------

def make_pico_sensors(
    temperature: float = 22.5,
    humidity: float = 55.0,
    air_quality: int = 850,
    tvoc: int = 150,
    eco2: int = 700,
    humidity_setpoint: int = 2,
):
    """Return a mock PicoDeviceModel.sensors."""
    sensors = MagicMock()
    sensors.temperature = temperature
    sensors.temperature_celsius = temperature
    sensors.humidity = humidity
    sensors.humidity_percent = humidity
    sensors.air_quality = air_quality
    sensors.tvoc = tvoc
    sensors.eco2 = eco2
    sensors.humidity_setpoint = humidity_setpoint
    return sensors


def make_pico_operating(
    mode_value: int = 1,
    speed_requested: int = 60,
    speed_row: int = 60,
    night_mode: int = 0,
    led_on_off_short: int = 1,
):
    """Return a mock PicoDeviceModel.operating."""
    from unittest.mock import MagicMock

    mode_enum = MagicMock()
    mode_enum.value = mode_value
    mode_enum.name = f"MODE_{mode_value}"

    operating = MagicMock()
    operating.mode = mode_enum
    operating.speed_requested = speed_requested
    operating.speed_row = speed_row
    operating.night_mode = night_mode
    operating.led_on_off_short = led_on_off_short
    return operating


def make_device_info(
    model: str = "PICO_PRO_30",
    firmware_version: str = "2.5.1",
    needs_clean_filters_maintenance: bool = False,
):
    info = MagicMock()
    info.model = model
    info.firmware_version = firmware_version
    info.needs_clean_filters_maintenance = needs_clean_filters_maintenance
    return info


def make_pico_device_model(
    is_on: bool = True,
    support_fan_speed_control: bool = True,
    support_night_mode_toggle: bool = True,
    support_target_humidity_selection: bool = True,
    sensors=None,
    operating=None,
    device_info=None,
):
    model = MagicMock()
    model.is_on = is_on
    model.support_fan_speed_control = support_fan_speed_control
    model.support_night_mode_toggle = support_night_mode_toggle
    model.support_target_humidity_selection = support_target_humidity_selection
    model.sensors = sensors or make_pico_sensors()
    model.operating = operating or make_pico_operating()
    model.device_info = device_info or make_device_info()
    return model


def make_polaris_device(
    is_on: bool = True,
    is_off: bool = False,
    is_cooling: bool = False,
    operating_mode: int = 0,
    cooling_mode_name: str = "heating",
    t_can: float = 21.0,
    has_error: bool = False,
    active_errors: list = None,
    serial: str = "SN123456",
    fw_ver: str = "1.2.1",
    name: str = "Polaris Test",
    num_errors: int = 0,
    f_inv=None, f_est=None, ir_present=None,
):
    dev = MagicMock()
    dev.is_on = is_on
    dev.is_off = is_off
    dev.is_cooling = is_cooling
    dev.operating_mode = operating_mode
    dev.cooling_mode_name = cooling_mode_name
    dev.t_can = t_can
    dev.has_error = has_error
    dev.active_errors = active_errors or []
    dev.serial = serial
    dev.fw_ver = fw_ver
    dev.name = name
    dev.num_errors = num_errors
    dev.f_inv = f_inv
    dev.f_est = f_est
    dev.ir_present = ir_present
    return dev


def make_polaris_zone(
    zone_id: int = 1,
    name: str = "Living Room",
    is_off: bool = False,
    current_temp: float = 20.5,
    set_temp: float = 21.0,
    humidity: float = 48.0,
    set_humidity: float = 50.0,
    has_error: bool = False,
    active_errors: list = None,
    fancoil: int = 0,
    fancoil_set: int = 0,
    serranda: int = 0,
    serranda_set: int = 0,
    ev: int = 0,
    is_crono_mode: bool = False,
    num_error: int = 0,
):
    zone = MagicMock()
    zone.zone_id = zone_id
    zone.name = name
    zone.is_off = is_off
    zone.current_temp = current_temp
    zone.set_temp = set_temp
    zone.humidity = humidity
    zone.set_humidity = set_humidity
    zone.has_error = has_error
    zone.active_errors = active_errors or []
    zone.fancoil = fancoil
    zone.fancoil_set = fancoil_set
    zone.serranda = serranda
    zone.serranda_set = serranda_set
    zone.ev = ev
    zone.is_crono_mode = is_crono_mode
    zone.num_error = num_error
    return zone


# ---------------------------------------------------------------------------
# Mock clients
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_pico_client():
    client = MagicMock()
    client.ip = "192.168.1.50"
    client.device_id = "pico_test_device"
    client.connected = True
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.get_status = AsyncMock(return_value=make_pico_device_model())
    client.turn_on = AsyncMock()
    client.turn_off = AsyncMock()
    client.change_operating_mode = AsyncMock()
    client.change_fan_speed = AsyncMock()
    client.set_night_mode = AsyncMock()
    client.set_led_status = AsyncMock()
    client.set_target_humidity = AsyncMock()
    client.reset_maintenance = AsyncMock()
    return client


@pytest.fixture
def mock_polaris_client():
    client = MagicMock()
    client.ip = "192.168.1.60"
    client.device_id = "polaris_test_device"

    device = make_polaris_device()
    zones = [make_polaris_zone(zone_id=1), make_polaris_zone(zone_id=2, name="Bedroom")]
    client.device = device
    client.verbose = False

    client.connect = AsyncMock()
    client.close = AsyncMock()
    client.async_update = AsyncMock(return_value=(device, zones))
    client.turn_on = AsyncMock()
    client.turn_off = AsyncMock()
    client.set_cooling_mode = AsyncMock()
    client.set_heating_mode = AsyncMock()
    client.set_zone_temp = AsyncMock()
    client.turn_zone_on = AsyncMock()
    client.turn_zone_off = AsyncMock()
    client.update_zone = AsyncMock()
    client.update_cu = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# Mock HomeAssistant + ConfigEntry
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_entries = MagicMock(return_value=[])
    return hass


def _make_config_entry(device_type: str = "pico", entry_id: str = "test_entry_1", extra: dict | None = None) -> MagicMock:
    base: dict[str, Any] = {
        "device_type": device_type,
        "ip": "192.168.1.50" if device_type == "pico" else "192.168.1.60",
        "pin": "1234",
        "name": "Test Device",
        "local_port": 40069,
        "verbose": False,
        **(extra or {}),
    }
    if device_type == "polaris":
        base.setdefault("scan_interval", 30)

    entry = MagicMock()
    entry.entry_id = entry_id
    entry.title = base["name"]
    entry.data = base
    return entry


@pytest.fixture
def pico_config_entry():
    return _make_config_entry("pico")


@pytest.fixture
def polaris_config_entry():
    return _make_config_entry("polaris")


# ---------------------------------------------------------------------------
# Pre-built coordinators (fully mocked — avoid HA frame-helper requirements)
# ---------------------------------------------------------------------------

def _make_pico_coordinator(mock_pico_client):
    """Return a fully mocked MainCoordinator-compatible object."""
    data = make_pico_device_model()

    coord = MagicMock()
    coord.client = mock_pico_client
    coord.pico_ip = mock_pico_client.ip
    coord.device_id = mock_pico_client.device_id
    coord.device_name = "Test Device"
    coord.data = data
    coord.last_update_success = True
    coord.last_exception = None
    coord.async_request_refresh = AsyncMock()

    # family_name slug
    coord.family_name = "test_device"

    # Properties derived from data
    coord.is_on = True
    coord.temperature = data.sensors.temperature
    coord.humidity = data.sensors.humidity
    coord.air_quality = data.sensors.air_quality
    coord.current_mode = data.operating.mode
    coord.fan_speed = data.operating.speed_requested
    coord.night_mode_enabled = data.operating.night_mode == 1
    coord.supports_fan_speed = data.support_fan_speed_control
    coord.supports_night_mode = data.support_night_mode_toggle
    coord.supports_target_humidity = data.support_target_humidity_selection

    # Async control methods — delegate to real implementations via the coordinator
    # We attach the real method bodies bound to this mock.
    from custom_components.open_pico import coordinator as _coord_module

    async def _async_update_data():
        return await _coord_module.MainCoordinator.async_update_data.__wrapped__(coord) \
            if hasattr(_coord_module.MainCoordinator.async_update_data, "__wrapped__") \
            else await _coord_module.MainCoordinator.async_update_data(coord)

    async def _turn_on():
        await mock_pico_client.turn_on(retry=True)
        await coord.async_request_refresh()

    async def _turn_off():
        await mock_pico_client.turn_off(retry=True)
        await coord.async_request_refresh()

    async def _set_mode(mode):
        await mock_pico_client.change_operating_mode(mode, retry=True)
        await coord.async_request_refresh()

    async def _set_fan_speed(percentage):
        if not coord.data.support_fan_speed_control and percentage != 100:
            raise ValueError(f"Device does not support fan speed control in current mode ({coord.current_mode})")
        await mock_pico_client.change_fan_speed(percentage, retry=True, force=False)
        await coord.async_request_refresh()

    async def _set_night_mode(enable):
        if not coord.data.support_night_mode_toggle:
            raise ValueError(f"Device does not support night mode in current mode ({coord.current_mode})")
        await mock_pico_client.set_night_mode(enable, retry=True, force=False)
        await coord.async_request_refresh()

    async def _set_led_status(enable):
        await mock_pico_client.set_led_status(enable, retry=True)
        await coord.async_request_refresh()

    async def _set_target_humidity(target):
        if not coord.data.support_target_humidity_selection:
            raise ValueError(f"Device does not support target humidity in current mode ({coord.current_mode})")
        await mock_pico_client.set_target_humidity(target, retry=True, force=False)
        await coord.async_request_refresh()

    async def _shutdown():
        pass

    async def _async_update_data_real():
        from homeassistant.helpers.update_coordinator import UpdateFailed
        if not mock_pico_client.connected:
            await mock_pico_client.connect()
        status = await mock_pico_client.get_status(retry=True)
        if status is None:
            raise UpdateFailed("Device returned no status data")
        return status

    coord.async_update_data = _async_update_data_real
    coord.async_turn_on = _turn_on
    coord.async_turn_off = _turn_off
    coord.async_set_mode = _set_mode
    coord.async_set_fan_speed = _set_fan_speed
    coord.async_set_night_mode = _set_night_mode
    coord.async_set_led_status = _set_led_status
    coord.async_set_target_humidity = _set_target_humidity
    coord.async_shutdown = _shutdown

    return coord


def _make_polaris_coordinator(mock_polaris_client):
    """Return a fully mocked PolarisCoordinator-compatible object."""
    from custom_components.open_pico.polaris_coordinator import PolarisData
    from open_polaris_local_api import PolarisApiError

    device = make_polaris_device()
    zones = [make_polaris_zone(zone_id=1), make_polaris_zone(zone_id=2, name="Bedroom")]
    data = PolarisData(device=device, zones=zones)

    coord = MagicMock()
    coord.client = mock_polaris_client
    coord.polaris_ip = mock_polaris_client.ip
    coord.device_name = "Test Polaris"
    coord.data = data
    coord.last_update_success = True
    coord.last_exception = None
    coord.async_request_refresh = AsyncMock()

    # serial from client.device.serial
    coord.serial = mock_polaris_client.device.serial

    @property
    def _polaris_device(self):
        return self.data.device if self.data else None

    @property
    def _polaris_zones(self):
        return self.data.zones if self.data else []

    coord.polaris_device = device
    coord.polaris_zones = zones

    def _find_zone(zone_id):
        for z in coord.polaris_zones:
            if z.zone_id == zone_id:
                return z
        return None

    async def _async_update_data():
        from homeassistant.helpers.update_coordinator import UpdateFailed
        try:
            dev, zns = await mock_polaris_client.async_update()
            return PolarisData(device=dev, zones=zns)
        except PolarisApiError as err:
            raise UpdateFailed(f"Polaris error: {err}") from err
        except TimeoutError as err:
            raise UpdateFailed(f"Polaris timeout: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error polling Polaris: {err}") from err

    async def _turn_on():
        await mock_polaris_client.turn_on()
        await coord.async_request_refresh()

    async def _turn_off():
        await mock_polaris_client.turn_off()
        await coord.async_request_refresh()

    async def _set_cooling_mode(mode):
        await mock_polaris_client.set_cooling_mode(mode)
        await coord.async_request_refresh()

    async def _set_heating_mode():
        await mock_polaris_client.set_heating_mode()
        await coord.async_request_refresh()

    async def _set_zone_temp(zone_id, temp):
        z = _find_zone(zone_id)
        if z:
            await mock_polaris_client.set_zone_temp(z, temp)
            await coord.async_request_refresh()

    async def _turn_zone_on(zone_id):
        z = _find_zone(zone_id)
        if z:
            await mock_polaris_client.turn_zone_on(z)
            await coord.async_request_refresh()

    async def _turn_zone_off(zone_id):
        z = _find_zone(zone_id)
        if z:
            await mock_polaris_client.turn_zone_off(z)
            await coord.async_request_refresh()

    async def _update_zone(zone_id, **kwargs):
        z = _find_zone(zone_id)
        if z:
            await mock_polaris_client.update_zone(z, **kwargs)
            await coord.async_request_refresh()

    async def _shutdown():
        await mock_polaris_client.close()

    coord._async_update_data = _async_update_data
    coord.async_turn_on = _turn_on
    coord.async_turn_off = _turn_off
    coord.async_set_cooling_mode = _set_cooling_mode
    coord.async_set_heating_mode = _set_heating_mode
    coord.async_set_zone_temp = _set_zone_temp
    coord.async_turn_zone_on = _turn_zone_on
    coord.async_turn_zone_off = _turn_zone_off
    coord.async_update_zone = _update_zone
    coord.async_shutdown = _shutdown

    return coord


@pytest.fixture
def pico_coordinator(mock_hass, mock_pico_client):
    """Real MainCoordinator with patched request_refresh for entity tests."""
    from custom_components.open_pico.coordinator import MainCoordinator
    coord = MainCoordinator(mock_hass, mock_pico_client, "Test Device")
    coord.data = make_pico_device_model()
    coord.async_request_refresh = AsyncMock()
    return coord


@pytest.fixture
def polaris_coordinator(mock_hass, mock_polaris_client):
    """Real PolarisCoordinator for entity tests."""
    from custom_components.open_pico.polaris_coordinator import PolarisCoordinator, PolarisData
    coord = PolarisCoordinator(mock_hass, mock_polaris_client, "Test Polaris", scan_interval=30)
    device = make_polaris_device()
    zones = [make_polaris_zone(zone_id=1), make_polaris_zone(zone_id=2, name="Bedroom")]
    coord.data = PolarisData(device=device, zones=zones)
    coord.async_request_refresh = AsyncMock()
    return coord

