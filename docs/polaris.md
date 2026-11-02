# Polaris 5X Integration

Local TCP-based HVAC zone controllers by Tecnosystemi.

## Protocol
- **Transport**: TCP on port **1235**
- One `PolarisLocalClient` per device (no shared transport)
- Each command opens a short-lived TCP connection (open, send JSON, read reply, close); no persistent socket
- Integration client settings: timeout 15 s, 3 attempts, 2 s between attempts

## Setup

### Manual
Fields required at config flow:

| Field | Default | Description |
|-------|---------|-------------|
| `ip` | — | Device LAN IP address |
| `pin` | — | Device PIN |
| `name` | — | Friendly name |
| `scan_interval` | 30 s | Poll interval (10–300 s, step 5) |

30 s default avoids overwhelming the CU's limited TCP stack, which would block official-app cloud sync.

### Auto-Scan
1. Enter subnet and PIN
2. Integration uses `PolarisAutoDiscovery.discover()`
3. Already-configured devices are excluded
4. Select IP, assign name and scan interval

---

## Entities

### Climate — Main (`climate.<name>`)
One per Polaris CU (Control Unit). Controls the global machine.

| Feature | Supported |
|---------|-----------|
| Turn on / off | ✅ |
| HVAC modes | ✅ |

**HVAC mode mapping**:

| HA Mode | is_cooling | cool_mod | Tecnosystemi name |
|---------|-----------|----------|-------------------|
| `heat` | `false` | 0 | Riscaldamento |
| `cool` | `true` | 1 | Raffrescamento |
| `dry` | `true` | 2 | Deumidificazione |
| `fan_only` | `true` | 3 | Ventilazione |
| `off` | — | — | Machine off |

`current_temperature` reflects `t_can` (canal temperature sensor).

---

### Climate — Zone (`climate.<name>_<zone_name>`)
One per zone reported by the CU. Named after the zone name stored on the device.

| Feature | Supported |
|---------|-----------|
| Turn on / off (zone only) | ✅ |
| Target temperature | ✅ (10–30 °C, step 0.5) |
| HVAC mode | `off` / `auto` only |
| Swing mode (damper / serranda) | ✅ `Auto`, `A1`, `A2`, `A3`, only for zones with a damper installed |

Zone on/off is **independent** — turning a zone off does not affect other zones or the CU.
`auto` = zone active; machine HVAC mode is set on the main climate entity.

Damper data comes from `stato_zona`, read once on the first successful poll for zones without errors. A zone that reports an error at startup, or any zone when the fetch times out, has no swing mode until the integration reloads.

---

### Sensors

| Entity | Description |
|--------|-------------|
| `sensor.<name>_operating_mode` | CU global mode string (`heating`, `cooling`, `dehumidification`, `ventilation`) |
| `sensor.<name>_<zone_name>_temperature` | Zone current temperature (°C) |
| `sensor.<name>_<zone_name>_humidity` | Zone humidity (%) |

`sensor.<name>_operating_mode` also exposes extra attributes:
- `operating_mode_id` — raw integer
- `is_cooling` — bool
- `is_off` — bool
- `firmware` — firmware version string
- `serial` — device serial number

---

### Binary Sensors

| Entity | Description |
|--------|-------------|
| `binary_sensor.<name>_device_error` | CU has at least one active error bit. `active_errors` attribute lists them. |
| `binary_sensor.<name>_<zone_name>_error` | Zone has at least one active error bit. |

---

## Device Registry
All entities for a Polaris device share one device entry, keyed by `polaris_<serial>` (or `polaris_<ip_underscored>` if serial unavailable). Device metadata:

| Field | Value |
|-------|-------|
| Manufacturer | Tecnosystemi |
| Model | Polaris 5X |
| Firmware | from `fw_ver` field |

---

## Coordinator Data (`PolarisData`)
The coordinator fetches via `client.async_update()` which returns `(PolarisDevice, list[PolarisZone])`. These are wrapped in a `PolarisData` dataclass:

```python
@dataclass
class PolarisData:
    device: PolarisDevice
    zones: list[PolarisZone]
```

---

## Error Handling
- `PolarisApiError` → `UpdateFailed`
- `TimeoutError` → `UpdateFailed`
- `ConfigEntryNotReady` raised if initial connect/refresh fails
