# Pico Integration

Local UDP-based ventilation and air quality units by Tecnosystemi.

## Protocol
- **Transport**: UDP unicast
- **Local port**: 40069 (outbound from HA)
- **Device port**: 40070 (device listens here)
- A single shared UDP socket (`SharedTransportManager`) is reused across all Pico devices to minimise socket usage.
- Each device has a unique `device_id` (slug of user-provided name, e.g. `pico_living_room`).

## Setup

### Manual
Fields required at config flow:

| Field | Description |
|-------|-------------|
| `ip` | Device LAN IP address |
| `pin` | Device PIN (displayed in device UI) |
| `name` | Friendly name (used in entity IDs and device registry) |

### Auto-Scan
1. Enter subnet (e.g. `192.168.1.0/24`) and PIN
2. Integration probes the network via `PicoAutoDiscovery.discover()`
3. Already-configured devices are excluded from results
4. Select a discovered IP, assign a name

---

## Entities

### Fan — `fan.<name>_cmv`
Main control entity for the Pico device.

| Feature | Supported |
|---------|-----------|
| Turn on / off | ✅ |
| Preset modes | ✅ (12 operating modes) |
| Fan speed (%) | ✅ (when mode supports it and night mode is off) |

**Preset modes** (operating modes):

| Preset | Mode ID |
|--------|---------|
| `heat_recovery` | 1 |
| `extraction` | 2 |
| `immission` | 3 |
| `humidity_recovery` | 4 |
| `humidity_extraction` | 5 |
| `comfort_summer` | 6 |
| `comfort_winter` | 7 |
| `co2_recovery` | 8 |
| `co2_extraction` | 9 |
| `humidity_co2_recovery` | 10 |
| `humidity_co2_extraction` | 11 |
| `natural_ventilation` | 12 |

Fan speed is only settable when `support_fan_speed_control=True` and night mode is not active.
Setting percentage to 0 turns the device off.

---

### Sensors

| Entity | Device Class | Unit | Notes |
|--------|-------------|------|-------|
| `sensor.<name>_temperature` | temperature | °C | |
| `sensor.<name>_humidity` | humidity | % | |
| `sensor.<name>_co2` | CO₂ | ppm | |
| `sensor.<name>_tvoc` | VOC | ppm | Icon changes with level |
| `sensor.<name>_eco2` | CO₂ (eCO₂) | ppm | Icon changes with level |

**TVOC icon thresholds** (ppm):
- < 220: `mdi:air-filter` (Excellent)
- 220–660: `mdi:chemical-weapon` (Good)
- 660–2200: `mdi:alert-circle-outline` (Moderate)
- 2200–5500: `mdi:alert` (Poor)
- > 5500: `mdi:alert-octagon` (Very Poor)

**eCO₂ icon thresholds** (ppm):
- < 600: Excellent
- 600–1000: Good
- 1000–1500: Moderate
- 1500–2000: Poor
- > 2000: Very Poor

---

### Switches

| Entity | Description | Condition |
|--------|-------------|-----------|
| `switch.<name>_night_mode` | Enables night mode | Only available when mode supports night mode |
| `switch.<name>_led_status` | Controls panel LED | Always available |

When night mode is active, fan speed control is disabled.

---

### Select Entities

| Entity | Options | Notes |
|--------|---------|-------|
| `select.<name>_preset_mode` | All 12 preset modes | Mirrors fan preset |
| `select.<name>_target_humidity` | `40%`, `50%`, `60%` | Only available when mode supports humidity target |

---

### Binary Sensor

| Entity | Device Class | Description |
|--------|-------------|-------------|
| `binary_sensor.<name>_filter_maintenance_required` | problem | `on` when filters need cleaning |

---

### Button

| Entity | Description | Condition |
|--------|-------------|-----------|
| `button.<name>_reset_filter_maintenance` | Sends maintenance reset command | Only available when `filter_maintenance = on` |

---

## Update Interval
Default: **5 seconds** (`DEFAULT_SCAN_INTERVAL` in `const.py`).

## Multi-Device Support
Multiple Pico devices share one UDP socket. The `PicoClientManager` singleton is created on first Pico entry setup and destroyed when the last Pico entry is removed.

## Error Handling
- If device is unreachable on poll, coordinator attempts reconnect automatically.
- 3 retry attempts with 2 s delay between attempts.
- `ConfigEntryNotReady` raised if initial connect/refresh fails.
