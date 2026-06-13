"""Tests for const.py — mappings and domain constants."""
import pytest

from custom_components.open_pico.const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    MODE_INT_TO_PRESET,
    MODE_PRESET_TO_INT,
    TARGET_HUMIDITY_OPTIONS,
    REVERSED_TARGET_HUMIDITY_OPTIONS,
    POLARIS_COOLING_MODES,
)


def test_domain():
    assert DOMAIN == "open_pico"


def test_default_scan_interval():
    assert DEFAULT_SCAN_INTERVAL == 5


class TestModeMapping:
    def test_all_12_modes_present(self):
        assert len(MODE_INT_TO_PRESET) == 12

    def test_mode_ids_1_to_12(self):
        assert set(MODE_INT_TO_PRESET.keys()) == set(range(1, 13))

    def test_reverse_mapping_complete(self):
        assert len(MODE_PRESET_TO_INT) == len(MODE_INT_TO_PRESET)

    def test_round_trip_int_to_preset_to_int(self):
        for mode_id, preset in MODE_INT_TO_PRESET.items():
            assert MODE_PRESET_TO_INT[preset] == mode_id

    def test_known_modes(self):
        assert MODE_INT_TO_PRESET[1] == "heat_recovery"
        assert MODE_INT_TO_PRESET[2] == "extraction"
        assert MODE_INT_TO_PRESET[3] == "immission"
        assert MODE_INT_TO_PRESET[12] == "natural_ventilation"


class TestHumidityOptions:
    def test_three_options(self):
        assert len(TARGET_HUMIDITY_OPTIONS) == 3

    def test_values_are_percentage_strings(self):
        assert set(TARGET_HUMIDITY_OPTIONS.values()) == {"40%", "50%", "60%"}

    def test_keys_1_2_3(self):
        assert set(TARGET_HUMIDITY_OPTIONS.keys()) == {1, 2, 3}

    def test_reverse_round_trip(self):
        for k, v in TARGET_HUMIDITY_OPTIONS.items():
            assert REVERSED_TARGET_HUMIDITY_OPTIONS[v] == k


class TestPolarisCoolingModes:
    def test_four_modes(self):
        assert len(POLARIS_COOLING_MODES) == 4

    def test_mode_names(self):
        assert POLARIS_COOLING_MODES[0] == "heating"
        assert POLARIS_COOLING_MODES[1] == "cooling"
        assert POLARIS_COOLING_MODES[2] == "dehumidification"
        assert POLARIS_COOLING_MODES[3] == "ventilation"
