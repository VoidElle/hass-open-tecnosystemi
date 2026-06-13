"""Tests for binary sensor entities (Pico + Polaris)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.open_pico.binary_sensor import (
    PicoMaintenanceBinarySensor,
    PolarisDeviceErrorBinarySensor,
    PolarisZoneErrorBinarySensor,
)
from custom_components.open_pico.const import DOMAIN
from tests.conftest import make_polaris_zone


class TestPicoMaintenanceBinarySensor:
    @pytest.fixture
    def sensor(self, pico_coordinator):
        return PicoMaintenanceBinarySensor(pico_coordinator, 0)

    def test_unique_id(self, sensor, pico_coordinator):
        assert sensor.unique_id == f"{DOMAIN}_filter_maintenance_{pico_coordinator.family_name}"

    def test_name(self, sensor):
        assert "Filter" in sensor.name

    def test_is_on_when_maintenance_needed(self, sensor, pico_coordinator):
        pico_coordinator.data.device_info.needs_clean_filters_maintenance = True
        assert sensor.is_on is True

    def test_is_off_when_no_maintenance(self, sensor, pico_coordinator):
        pico_coordinator.data.device_info.needs_clean_filters_maintenance = False
        assert sensor.is_on is False

    def test_is_none_when_no_data(self, sensor, pico_coordinator):
        pico_coordinator.data = None
        assert sensor.is_on is None

    def test_is_none_when_no_device_info(self, sensor, pico_coordinator):
        pico_coordinator.data.device_info = None
        assert sensor.is_on is None

    def test_icon_maintenance_needed(self, sensor, pico_coordinator):
        pico_coordinator.data.device_info.needs_clean_filters_maintenance = True
        assert sensor.icon == "mdi:air-filter-remove"

    def test_icon_no_maintenance(self, sensor, pico_coordinator):
        pico_coordinator.data.device_info.needs_clean_filters_maintenance = False
        assert sensor.icon == "mdi:air-filter"


class TestPolarisDeviceErrorBinarySensor:
    @pytest.fixture
    def sensor(self, polaris_coordinator):
        return PolarisDeviceErrorBinarySensor(polaris_coordinator)

    def test_unique_id(self, sensor, polaris_coordinator):
        assert sensor.unique_id == f"polaris_{polaris_coordinator.serial}_device_error"

    def test_is_on_when_error(self, sensor, polaris_coordinator):
        polaris_coordinator.data.device.has_error = True
        assert sensor.is_on is True

    def test_is_off_when_no_error(self, sensor, polaris_coordinator):
        polaris_coordinator.data.device.has_error = False
        assert sensor.is_on is False

    def test_is_none_when_no_data(self, sensor, polaris_coordinator):
        polaris_coordinator.data = None
        assert sensor.is_on is None

    def test_extra_state_attributes_with_errors(self, sensor, polaris_coordinator):
        polaris_coordinator.data.device.active_errors = ["E01", "E02"]
        attrs = sensor.extra_state_attributes
        assert attrs["active_errors"] == ["E01", "E02"]

    def test_extra_state_attributes_no_data(self, sensor, polaris_coordinator):
        polaris_coordinator.data = None
        assert sensor.extra_state_attributes == {}

    def test_device_info(self, sensor, polaris_coordinator):
        info = sensor.device_info
        assert (DOMAIN, f"polaris_{polaris_coordinator.serial}") in info["identifiers"]
        assert info["manufacturer"] == "Tecnosystemi"


class TestPolarisZoneErrorBinarySensor:
    @pytest.fixture
    def sensor(self, polaris_coordinator):
        return PolarisZoneErrorBinarySensor(polaris_coordinator, 1)

    def test_unique_id(self, sensor, polaris_coordinator):
        assert sensor.unique_id == f"polaris_{polaris_coordinator.serial}_zone_1_error"

    def test_name_from_zone(self, sensor, polaris_coordinator):
        name = sensor.name
        assert name is not None
        assert "Error" in name

    def test_name_none_when_zone_missing(self, sensor, polaris_coordinator):
        polaris_coordinator.data.zones = []
        assert sensor.name is None

    def test_is_on_when_zone_error(self, sensor, polaris_coordinator):
        polaris_coordinator.data.zones[0].has_error = True
        assert sensor.is_on is True

    def test_is_off_when_no_zone_error(self, sensor, polaris_coordinator):
        polaris_coordinator.data.zones[0].has_error = False
        assert sensor.is_on is False

    def test_is_none_when_no_data(self, sensor, polaris_coordinator):
        polaris_coordinator.data = None
        assert sensor.is_on is None

    def test_available_false_when_zone_missing(self, sensor, polaris_coordinator):
        polaris_coordinator.data.zones = []
        assert sensor.available is False

    def test_extra_state_attributes(self, sensor, polaris_coordinator):
        polaris_coordinator.data.zones[0].active_errors = ["Z01"]
        attrs = sensor.extra_state_attributes
        assert attrs["active_errors"] == ["Z01"]

    def test_extra_state_attributes_no_zone(self, sensor, polaris_coordinator):
        polaris_coordinator.data.zones = []
        assert sensor.extra_state_attributes == {}
