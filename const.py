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
POLARIS_SCAN_INTERVAL = 10  # seconds (cloud API, don't hammer it)

POLARIS_COOLING_MODES = {
    0: "Riscaldamento",
    1: "Raffrescamento",
    2: "Deumidificazione",
    3: "Ventilazione",
}

# ─── ProAir API protocol constants ──────────────────────────────────
# These are PUBLIC protocol constants extracted from the official
# Tecnosystemi Android APK (it.tecnosystemi.TS). They are the same
# for every user and are NOT private credentials.
PROAIR_BASE_URL = "https://proair.azurewebsites.net"

# API Basic auth uses a fixed password for all users; the username
# is the user's email (or a fallback value before login).
PROAIR_API_AUTH_PARTS = ("Pwd", "ProAir")   # joined at runtime
PROAIR_FALLBACK_USER_PARTS = ("Usr", "ProAir")  # joined at runtime

# AES token rotation parameters (from APK constants)
PROAIR_DEVICE_ID = "c610101212ff9aec"
PROAIR_CIPHER_SALT = "ns91wr48"
# Initial handshake token (base64, not a secret — identical for every install)
PROAIR_STARTING_TOKEN_PARTS = (
    "Ga5mM61KCm5Bk18l", "hD5J999jC2Mu0Vaf"
)  # joined at runtime