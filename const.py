"""Constants for Open Pico integration."""

DOMAIN = "open_pico"

DEFAULT_SCAN_INTERVAL = 5

# Device mode mapping - single source of truth
MODE_INT_TO_PRESET = {
    1: "heat_recovery",
    2: "extraction",
    3: "immission",
    4: "humidity_recovery",
    5: "humidity_extraction",
    6: "comfort_summer",
    7: "comfort_winter",
    8: "co2_recovery",
    9: "co2_extraction",
    10: "humidity_co2_recovery",
    11: "humidity_co2_extraction",
    12: "natural_ventilation",
}

# Reverse mapping for preset to int conversion
MODE_PRESET_TO_INT = {v: k for k, v in MODE_INT_TO_PRESET.items()}

# Options for target humidity selector
TARGET_HUMIDITY_OPTIONS = {
    1: "40%",
    2: "50%",
    3: "60%",
}

# Reverse mapping for target humidity selector options
REVERSED_TARGET_HUMIDITY_OPTIONS = {v: k for k, v in TARGET_HUMIDITY_OPTIONS.items()}

# ─── Polaris constants ───────────────────────────────────────────────
POLARIS_SCAN_INTERVAL = 5  # seconds (local TCP port 1235)

POLARIS_COOLING_MODES = {
    0: "Riscaldamento",
    1: "Raffrescamento",
    2: "Deumidificazione",
    3: "Ventilazione",
}
