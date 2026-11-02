---
name: pico
description: Expert agent for the Pico ventilation/air quality device integration. Use when working on the UDP protocol, the cloud fallback (PicoCloudClient), PicoClientManager, SharedTransportManager, MainCoordinator, or any Pico entities (fan, sensor, switch, select, button, binary_sensor).
---

# Hassio Open Pico — Pico Device Integration

Home Assistant custom integration for Tecnosystemi **Pico** ventilation/air quality devices.  
Protocol: **local UDP**, listen port `40069`, send to device port `40070`. Optional **cloud fallback** (HTTPS, vendor backend) for devices not reachable on the LAN; see [Cloud fallback](#cloud-fallback-picocloudclient).

---

## YAML Config Schema

```yaml
open_pico:
  devices:
    - ip: "192.168.1.x"
      pin: "1234"
      name: "Pico Device"   # optional
  local_port: 40069         # optional, default 40069
  verbose: false            # optional debug logging
```

Config schema lives in `__init__.py` (`PICO_DEVICE_SCHEMA`, `CONFIG_SCHEMA`).

---

## Architecture

### Setup flow (`__init__.py -> async_setup`)
1. Read `devices` list from YAML
2. Create `PicoClientManager` -> `initialize()` (binds shared UDP socket on `local_port`)
3. For each device: `manager.create_client(ip, pin, ...)` -> `client.connect()` -> create `MainCoordinator` -> `async_refresh()`
4. Append coordinator to `hass.data[DOMAIN]["coordinators"]`
5. Cloud branch (`entry.data["connection"] == "cloud"`): `_setup_pico_entry` builds `PicoCloudClient` directly (HTTPS, no `PicoClientManager`), `PicoAuthError` -> `ConfigEntryError`, other connect errors -> `ConfigEntryNotReady`; coordinator gets `scan_interval` / `command_delay` from `entry.data` (defaults `CLOUD_SCAN_INTERVAL`, `CLOUD_COMMAND_DELAY`). Unload calls `client.disconnect()`; the manager shutdown check counts only local entries.
6. Load platforms via `discovery.async_load_platform` for all `PICO_PLATFORMS`

### hass.data layout
```python
hass.data[DOMAIN] = {
    "coordinators": [MainCoordinator, ...],      # Pico devices
    "polaris_coordinators": [...],               # Polaris devices (see polaris.md)
    "manager": PicoClientManager,                # shared UDP manager
    "config": domain_config,
}
```

### Platforms (`PICO_PLATFORMS` in `__init__.py`)
```python
[Platform.FAN, Platform.SWITCH, Platform.SELECT, Platform.SENSOR, Platform.BUTTON, Platform.BINARY_SENSOR]
```

---

## Shared UDP Transport

All Pico clients share **one UDP socket** — avoids port conflicts when multiple devices are present.

### Key classes
| Class | File | Role |
|-------|------|------|
| `PicoClientManager` | `pico_manager.py` | Creates/manages clients; owns `SharedTransportManager` singleton |
| `SharedTransportManager` | `open-pico-local-api` pkg (`shared_transport_manager`) | Singleton; binds UDP socket; routes responses by IDP range |
| `PicoClient` | `open-pico-local-api` pkg (`pico_client`) | Per-device client; always `use_shared_transport=True` |

### IDP routing
Each device gets an allocated IDP range (`idp_range_start`, `idp_range_size=10000`).  
`SharedTransportManager._find_device_by_idp(idp)` routes responses to correct device queue.  
IDP counter wraps within allocated range. On IDP sync failure: reset counter, retry up to `retry_attempts` times.

### `PicoClientManager.create_client()` defaults
```python
timeout=15, retry_attempts=3, retry_delay=2.0, device_port=40070
device_id = f"pico_{ip.replace('.', '_')}"
```

---

## Protocol (`PicoClient`)

### Commands (all `cmd: "upd_pico"` or `cmd: "stato_sync"`)

**Get status:**
```json
{"cmd": "stato_sync", "frm": "app", "pin": "<pin>", "idp": <int>}
```

**Turn on/off:**
```json
{"on_off": 1, "cmd": "upd_pico", "frm": "app", "pin": "<pin>", "idp": <int>}
```
`on_off: 1` = ON, `on_off: 2` = OFF

**Change mode:**
```json
{"mod": <int>, "on_off": 1, "cmd": "upd_pico", "frm": "app", "pin": "<pin>", "idp": <int>}
```

**Change fan speed:**
```json
{"spd_row": <percentage>, "speed": 0, "cmd": "upd_pico", "frm": "app", "pin": "<pin>", "idp": <int>}
```

**Night mode:**
```json
{"night_mod": 1, "cmd": "upd_pico", "frm": "app", "pin": "<pin>", "idp": <int>}
```
`night_mod: 1` = enable, `night_mod: 2` = disable

**LED:**
```json
{"led_on_off_breve": 1, "cmd": "upd_pico", "frm": "app", "pin": "<pin>", "idp": <int>}
```
`led_on_off_breve: 1` = ON, `2` = OFF

**Target humidity:**
```json
{"s_umd": <TargetHumidityEnum>, "cmd": "upd_pico", "frm": "app", "pin": "<pin>", "idp": <int>}
```

**Maintenance reset:**
```json
{"man_reset": [1, 0, ...], "cmd": "upd_pico", "frm": "app", "pin": "<pin>", "idp": <int>}
```
`man_reset[0] = 1` resets filter maintenance (index 0 only). Read current `man` array from status first.

### ACK handshake
- Device sends ACK: `{"res": 99, "frm": "mst", "idp": <int>}`
- Client must reply: `{"idp": <int>, "frm": "app", "res": 99}` then await status response
- `_wait_for_response()` handles this: detects ACK -> waits for real response -> sends ACK reply

---

## Data Models

### `PicoDeviceModel` (from `stato_sync` response)
Fields parsed in `PicoDeviceModel.from_dict(data)`:

| Model | Fields |
|-------|--------|
| `DeviceInfoModel` | `ip`, `fw_ver`, `fw_note`, `vr`, `modello`, `BaseTop`, `Grd_DM`, `config_mod`, `id_slave`, `name`, `has_slave`, `bmp_slave`, `man[]` |
| `SensorReadingsModel` | `v_tmpr` (temp), `v_umd` (humidity), `v_AirQ`, `v_Tvoc`, `v_ECo2`, `umd_raw`, `s_umd` (humidity setpoint), `s_co2` |
| `OperatingParametersModel` | `mod` (mode), `step_mod`, `on_off`, `speed`, `spd_rich`, `spd_row`, `fan_dir`, `verso`, `Delta_tmprCiclo`, `Delta_umdCiclo`, `night_mod`, `led_on_off`, `led_on_off_breve`, `led_color`, `m_crono`, `tw_active` |
| `SystemInfoModel` | `cntr`, `memfree`, `up_time`, `date`, `time`, `week` |
| `ParameterArraysModel` | `par_rt`, `par_mm`, `par_amb`, `par_ext`, `err[]`, `man[]` |

**Key computed properties:**
- `PicoDeviceModel.is_on` -> `operating.on_off == OnOffStateEnum.ON`
- `PicoDeviceModel.support_fan_speed_control` -> `operating.mode in MODULAR_FAN_SPEED_PRESET_MODES`
- `PicoDeviceModel.support_target_humidity_selection` -> `operating.mode in HUMIDITY_SELECTOR_PRESET_MODES`
- `PicoDeviceModel.support_night_mode_toggle` -> same as fan speed
- `DeviceInfoModel.needs_clean_filters_maintenance` -> `man[0] == 1`

### Operating modes (`DeviceModeEnum` / `MODE_INT_TO_PRESET`)
| Int | Enum | Preset string |
|-----|------|---------------|
| 1 | `HEAT_RECOVERY` | `heat_recovery` |
| 2 | `EXTRACTION` | `extraction` |
| 3 | `IMMISSION` | `immission` |
| 4 | `HUMIDITY_RECOVERY` | `humidity_recovery` |
| 5 | `HUMIDITY_EXTRACTION` | `humidity_extraction` |
| 6 | `COMFORT_SUMMER` | `comfort_summer` |
| 7 | `COMFORT_WINTER` | `comfort_winter` |
| 8 | `CO2_RECOVERY` | `co2_recovery` |
| 9 | `CO2_EXTRACTION` | `co2_extraction` |
| 10 | `HUMIDITY_CO2_RECOVERY` | `humidity_co2_recovery` |
| 11 | `HUMIDITY_CO2_EXTRACTION` | `humidity_co2_extraction` |
| 12 | `NATURAL_VENTILATION` | `natural_ventilation` |

**Fan speed supported modes** (`MODULAR_FAN_SPEED_PRESET_MODES`):  
`HEAT_RECOVERY, EXTRACTION, IMMISSION, COMFORT_SUMMER, COMFORT_WINTER`

**Humidity setpoint supported modes** (`HUMIDITY_SELECTOR_PRESET_MODES`):  
`HUMIDITY_RECOVERY, HUMIDITY_EXTRACTION, HUMIDITY_CO2_RECOVERY, HUMIDITY_CO2_EXTRACTION`

### `TargetHumidityEnum` / `TARGET_HUMIDITY_OPTIONS`
`1` -> `"40%"`, `2` -> `"50%"`, `3` -> `"60%"`

---

## Coordinator (`MainCoordinator`)

`coordinator.data` is `PicoDeviceModel | None`. All control methods call client then `async_request_refresh()`.

### Convenience properties
```python
coordinator.is_on          # bool
coordinator.temperature    # float (v_tmpr)
coordinator.humidity       # float (v_umd)
coordinator.air_quality    # int (v_AirQ)
coordinator.current_mode   # DeviceModeEnum | None
coordinator.fan_speed      # int (spd_requested %)
coordinator.night_mode_enabled  # bool
coordinator.supports_fan_speed      # bool (mode-gated)
coordinator.supports_night_mode     # bool (mode-gated)
coordinator.supports_target_humidity  # bool (mode-gated)
```

### Control methods
```python
coordinator.async_turn_on()
coordinator.async_turn_off()
coordinator.async_set_mode(mode: DeviceModeEnum | int)
coordinator.async_set_fan_speed(percentage: int)   # raises if mode unsupported
coordinator.async_set_night_mode(enable: bool)     # raises if mode unsupported
coordinator.async_set_led_status(enable: bool)
coordinator.async_set_target_humidity(target: int) # raises if mode unsupported
```

### Failure handling
`_consecutive_failures` tracked; `_max_failures_before_reset = 3`. On disconnect -> reconnect in `async_update_data`.

---

## Cloud fallback (`PicoCloudClient`)

Used only for entries with `entry.data["connection"] == "cloud"` (entries without the key are local). Never make it automatic: local UDP stays the primary path.

### Entry data
`device_type: "pico"`, `connection: "cloud"`, `name`, `pin`, `email`, `password`, `serial` (upper-case), `android_id` (16 hex, generated once per entry), `scan_interval`, `command_delay`, `verbose`. Read both intervals with `.get()` + default.

### Config flow (`config_flow.py`)
`pico` step `setup_method == "cloud"` -> `async_step_pico_cloud` (email/password, login + `get_devices()`, keeps `LVDV_Type == 1` not yet configured) -> `async_step_pico_cloud_device` (serial select, PIN, name; generates `android_id`, validates with a fresh client `connect()` + `get_status()`, wrong PIN -> `invalid_pin`). Client is always disconnected after validation.

### Setup (`__init__.py -> _setup_pico_entry`)
- `PicoCloudClient(email, password, serial, pin, name, device_id=android_id, timeout=15, retry_attempts=2, retry_delay=2.0, verbose)`. `device_id` is the `android_id` (AES key seed sent at login), not an HA id
- No `PicoClientManager` / UDP transport. `client.ip == "cloud"`, `coordinator.pico_ip` = serial in logs
- `connect()` (30 s): `PicoAuthError` -> `ConfigEntryError`, anything else -> `ConfigEntryNotReady`
- `MainCoordinator(..., scan_interval=entry.data.get("scan_interval", CLOUD_SCAN_INTERVAL), command_delay=entry.data.get("command_delay", CLOUD_COMMAND_DELAY))`. Defaults 30 s / 3 s; the user sets both in the `pico_cloud_device` step (10-300 s step 5, 0-30 s), same pattern as Polaris `scan_interval`
- Unload: `client.disconnect()` (closes the aiohttp session); manager shutdown counts only local Pico entries

### Status and commands
- `get_status()` -> `GET GetPICOState`. `ResDescr` = backend `frm:"db"` record (control fields only) + `lastpk` (JSON string of the device's last `stato_sync`). Since library **2.6.2** `lastpk` is decoded and wins; flat fields only fill missing keys. Result is a normal `PicoDeviceModel`, same values as local: sensors, `par_rt`/`par_mm`, `memfree`, `is_led_state_on` are real
- Before 2.6.2 cloud sensors were all `0` and an off LED read as on (db encodes `led_on_off_breve` off as `0`, device sends `2`). Never pin `open-pico-local-api` below `2.6.2`, and never add integration-side workarounds for these
- `data.device_info.name` is the name stored on the device (account name is in `raw_data["name"]`). Entities use `coordinator.device_name` (entry name), so this does not matter here
- Commands are inherited from `PicoClient` and return after the **cloud ack** only (no `res: 99`); the device applies them asynchronously, hence `command_delay` before `_refresh_after_command()` refreshes
- `reset_idp()` only resets the client counter; `bruteforce_idp()` raises `NotSupportedError`. Session re-login is automatic (55 min or HTTP 401)

### Debugging
- Bad credentials -> `PicoAuthError` (subclass of `PicoDeviceError`, import from `open_pico_local_api.cloud`). Wrong PIN -> `PicoDeviceError("Wrong PIN")`
- State flips back after a command: backend has not applied it yet; raise the entry's command delay (re-add the entry with a higher value, e.g. 6), do not drop the refresh
- `verbose: true` logs every HTTP request/response; logs contain email and PIN, redact before sharing

---

## Entities

### `BaseEntity` (`base.py`)
- Extends `CoordinatorEntity[MainCoordinator]`
- `_attr_has_entity_name = True`
- `available`: `coordinator.last_update_success and coordinator.data is not None`
- `device_info`: identifiers `(DOMAIN, coordinator.family_name)`, name `coordinator.device_name` (entry name, not `data.device_info.name`), manufacturer `"Tecnosystemi"`, model `f"Model {device_info.model}"`, sw_version `device_info.firmware_version`
- `unique_id` pattern: `f"{DOMAIN}_{entity_type}_{coordinator.pico_ip.replace('.', '_')}"`

### Platform summary
| Platform | Entity class | `unique_id` suffix | Notes |
|----------|-------------|-------------------|-------|
| FAN | `PicoFan` | `fan_<ip>` | Presets = all modes; speed% only when `supports_fan_speed` and not night mode |
| SWITCH | `PicoNightModeSwitch` | `night_mode_<ip>` | `available` gated by `supports_night_mode` |
| SWITCH | `PicoLEDStatusSwitch` | `led_status_<ip>` | `led_on_off_breve: 1=ON, 2=OFF` |
| SELECT | `PicoTargetHumiditySelect` | `target_humidity_<ip>` | `available` gated by `supports_target_humidity` |
| SELECT | `PicoPresetModeSelect` | `preset_mode_<ip>` | All 12 modes |
| SENSOR | `PicoTemperatureSensor` etc. | see sensor.py | Temperature, humidity, AirQ, TVOC, eCO2 |
| BUTTON | `PicoMaintenanceResetButton` | `reset_maintenance_<ip>` | `available` only when `needs_clean_filters_maintenance` |
| BINARY_SENSOR | `PicoMaintenanceBinarySensor` | `filter_maintenance_<ip>` | `PROBLEM` class; reads `man[0]` |

---

## Adding a New Platform

1. Create `<platform>.py` at repo root
2. `async_setup_platform`: read `hass.data[DOMAIN]["coordinators"]`
3. Entity class extends `BaseEntity`; `unique_id` = `f"{DOMAIN}_{type}_{coordinator.pico_ip.replace('.', '_')}"`
4. Add to `PICO_PLATFORMS` list in `__init__.py`
5. Add translation keys to `translations/en.json` and `translations/it.json`

---

## Development & Testing

No automated test suite. Manual steps:
1. Install at `custom_components/hassio_open_pico/` (folder name matters)
2. Add YAML config under `open_pico:`
3. Restart HA; check logs with `verbose: true`
4. Validate YAML: **Developer Tools -> YAML -> Check Configuration**

Loaded via `async_setup` (YAML), not `async_setup_entry`. UI "Add Integration" registers the domain but does nothing else.
