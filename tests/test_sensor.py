"""Tests for sensor entities (Pico + Polaris)."""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest

from custom_components.open_pico.sensor import (
    PicoTemperatureSensor,
    PicoHumiditySensor,
    PicoAirQualitySensor,
    PicoTVOCSensor,
    PicoECO2Sensor,
    PolarisZoneTemperatureSensor,
    PolarisZoneHumiditySensor,
    PolarisOperatingModeSensor,
)
from custom_components.open_pico.const import DOMAIN, POLARIS_COOLING_MODES
from tests.conftest import make_polaris_zone


# ─── Pico sensors ────────────────────────────────────────────────────────────

class TestPicoTemperatureSensor:
    @pytest.fixture
    def sensor(self, pico_coordinator):
        return PicoTemperatureSensor(pico_coordinator, 0)

    def test_unique_id(self, sensor, pico_coordinator):
        assert sensor.unique_id == f"{DOMAIN}_temperature_{pico_coordinator.family_name}"

    def test_native_value(self, sensor, pico_coordinator):
        pico_coordinator.data.sensors.temperature = 22.5
        pico_coordinator.data.sensors.temperature_celsius = 22.5
        assert sensor.native_value == 22.5

    def test_native_value_no_data(self, sensor, pico_coordinator):
        pico_coordinator.data = None
        assert sensor.native_value is None

    def test_native_value_no_sensors(self, sensor, pico_coordinator):
        pico_coordinator.data.sensors = None
        assert sensor.native_value is None


class TestPicoHumiditySensor:
    @pytest.fixture
    def sensor(self, pico_coordinator):
        return PicoHumiditySensor(pico_coordinator, 0)

    def test_unique_id(self, sensor, pico_coordinator):
        assert sensor.unique_id == f"{DOMAIN}_humidity_{pico_coordinator.family_name}"

    def test_native_value(self, sensor, pico_coordinator):
        pico_coordinator.data.sensors.humidity = 55.0
        pico_coordinator.data.sensors.humidity_percent = 55.0
        assert sensor.native_value == 55.0

    def test_native_value_no_data(self, sensor, pico_coordinator):
        pico_coordinator.data = None
        assert sensor.native_value is None


class TestPicoAirQualitySensor:
    @pytest.fixture
    def sensor(self, pico_coordinator):
        return PicoAirQualitySensor(pico_coordinator, 0)

    def test_unique_id(self, sensor, pico_coordinator):
        assert sensor.unique_id == f"{DOMAIN}_air_quality_{pico_coordinator.family_name}"

    def test_native_value(self, sensor, pico_coordinator):
        pico_coordinator.data.sensors.air_quality = 850
        assert sensor.native_value == 850

    def test_native_value_no_sensors(self, sensor, pico_coordinator):
        pico_coordinator.data.sensors = None
        assert sensor.native_value is None


class TestPicoTVOCSensor:
    @pytest.fixture
    def sensor(self, pico_coordinator):
        return PicoTVOCSensor(pico_coordinator, 0)

    def test_unique_id(self, sensor, pico_coordinator):
        assert sensor.unique_id == f"{DOMAIN}_tvoc_{pico_coordinator.family_name}"

    def test_native_value(self, sensor, pico_coordinator):
        pico_coordinator.data.sensors.tvoc = 300
        assert sensor.native_value == 300

    @pytest.mark.parametrize("tvoc,expected_icon", [
        (100, "mdi:air-filter"),
        (220, "mdi:chemical-weapon"),
        (700, "mdi:alert-circle-outline"),
        (3000, "mdi:alert"),
        (6000, "mdi:alert-octagon"),
    ])
    def test_icon_thresholds(self, sensor, pico_coordinator, tvoc, expected_icon):
        pico_coordinator.data.sensors.tvoc = tvoc
        assert sensor.icon == expected_icon

    def test_icon_no_data(self, sensor, pico_coordinator):
        pico_coordinator.data = None
        assert sensor.icon == "mdi:chemical-weapon"


class TestPicoECO2Sensor:
    @pytest.fixture
    def sensor(self, pico_coordinator):
        return PicoECO2Sensor(pico_coordinator, 0)

    def test_unique_id(self, sensor, pico_coordinator):
        assert sensor.unique_id == f"{DOMAIN}_eco2_{pico_coordinator.family_name}"

    def test_native_value(self, sensor, pico_coordinator):
        pico_coordinator.data.sensors.eco2 = 700
        assert sensor.native_value == 700

    @pytest.mark.parametrize("eco2,expected_icon", [
        (400, "mdi:air-filter"),
        (800, "mdi:molecule-co2"),
        (1200, "mdi:alert-circle-outline"),
        (1700, "mdi:alert"),
        (2500, "mdi:alert-octagon"),
    ])
    def test_icon_thresholds(self, sensor, pico_coordinator, eco2, expected_icon):
        pico_coordinator.data.sensors.eco2 = eco2
        assert sensor.icon == expected_icon


# ─── Polaris sensors ─────────────────────────────────────────────────────────

class TestPolarisZoneTemperatureSensor:
    @pytest.fixture
    def sensor(self, polaris_coordinator):
        return PolarisZoneTemperatureSensor(polaris_coordinator, 1)

    def test_unique_id(self, sensor, polaris_coordinator):
        assert sensor.unique_id == f"polaris_{polaris_coordinator.serial}_zone_1_temp"

    def test_name_from_zone(self, sensor, polaris_coordinator):
        assert "Temperature" in sensor.name

    def test_native_value(self, sensor, polaris_coordinator):
        zone = polaris_coordinator.data.zones[0]
        zone.current_temp = 20.5
        assert sensor.native_value == 20.5

    def test_native_value_no_data(self, sensor, polaris_coordinator):
        polaris_coordinator.data = None
        assert sensor.native_value is None

    def test_available_false_when_zone_missing(self, sensor, polaris_coordinator):
        polaris_coordinator.data.zones = []
        assert sensor.available is False

    def test_device_info_has_identifiers(self, sensor, polaris_coordinator):
        info = sensor.device_info
        assert (DOMAIN, f"polaris_{polaris_coordinator.serial}") in info["identifiers"]


class TestPolarisZoneHumiditySensor:
    @pytest.fixture
    def sensor(self, polaris_coordinator):
        return PolarisZoneHumiditySensor(polaris_coordinator, 1)

    def test_unique_id(self, sensor, polaris_coordinator):
        assert sensor.unique_id == f"polaris_{polaris_coordinator.serial}_zone_1_humidity"

    def test_native_value(self, sensor, polaris_coordinator):
        zone = polaris_coordinator.data.zones[0]
        zone.humidity = 48.0
        assert sensor.native_value == 48.0

    def test_native_value_missing_zone(self, sensor, polaris_coordinator):
        polaris_coordinator.data.zones = []
        assert sensor.native_value is None


class TestPolarisOperatingModeSensor:
    @pytest.fixture
    def sensor(self, polaris_coordinator):
        return PolarisOperatingModeSensor(polaris_coordinator)

    def test_unique_id(self, sensor, polaris_coordinator):
        assert sensor.unique_id == f"polaris_{polaris_coordinator.serial}_operating_mode"

    def test_native_value_heating(self, sensor, polaris_coordinator):
        polaris_coordinator.data.device.operating_mode = 0
        assert sensor.native_value == "heating"

    def test_native_value_cooling(self, sensor, polaris_coordinator):
        polaris_coordinator.data.device.operating_mode = 1
        assert sensor.native_value == "cooling"

    def test_native_value_dehumidification(self, sensor, polaris_coordinator):
        polaris_coordinator.data.device.operating_mode = 2
        assert sensor.native_value == "dehumidification"

    def test_native_value_ventilation(self, sensor, polaris_coordinator):
        polaris_coordinator.data.device.operating_mode = 3
        assert sensor.native_value == "ventilation"

    def test_native_value_unknown(self, sensor, polaris_coordinator):
        polaris_coordinator.data.device.operating_mode = 99
        assert sensor.native_value == "unknown"

    def test_native_value_no_data(self, sensor, polaris_coordinator):
        polaris_coordinator.data = None
        assert sensor.native_value is None

    def test_extra_state_attributes(self, sensor, polaris_coordinator):
        attrs = sensor.extra_state_attributes
        assert "operating_mode_id" in attrs
        assert "is_cooling" in attrs
        assert "firmware" in attrs
        assert "serial" in attrs

    def test_device_info_sw_version(self, sensor, polaris_coordinator):
        info = sensor.device_info
        assert info["sw_version"] == polaris_coordinator.data.device.fw_ver
