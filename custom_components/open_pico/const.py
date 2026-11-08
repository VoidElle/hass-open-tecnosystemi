"""Constants for Hass Open Tecnosystemi integration."""

DOMAIN = "open_pico"

DEFAULT_SCAN_INTERVAL = 5

# Cloud (vendor backend): poll slower, commands are applied asynchronously
CLOUD_SCAN_INTERVAL = 30
CLOUD_COMMAND_DELAY = 3

# Polaris local TCP: the CU's network stack is fragile, poll gently
POLARIS_SCAN_INTERVAL = 60


def entry_scan_interval(entry) -> int:
    """Polling interval of a config entry: options flow, then setup form, then type default."""
    data = entry.data
    if data.get("connection", "local") == "cloud":
        default = CLOUD_SCAN_INTERVAL
    elif data.get("device_type", "pico") == "polaris":
        default = POLARIS_SCAN_INTERVAL
    else:
        default = DEFAULT_SCAN_INTERVAL
    return entry.options.get("scan_interval", data.get("scan_interval", default))


def entry_command_delay(entry) -> int:
    """Cloud command settle delay: options flow, then setup form, then default."""
    return entry.options.get("command_delay", entry.data.get("command_delay", CLOUD_COMMAND_DELAY))

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
POLARIS_COOLING_MODES = {
    0: "heating",
    1: "cooling",
    2: "dehumidification",
    3: "ventilation",
}
