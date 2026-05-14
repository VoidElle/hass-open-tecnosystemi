---
name: pico
description: Expert agent for the Pico ventilation/air quality device integration. Use when working on the UDP protocol, PicoClientManager, SharedTransportManager, MainCoordinator, or any Pico entities (fan, sensor, switch, select, button, binary_sensor).
---

# Hassio Open Pico — Pico Device Integration

Home Assistant custom integration for Tecnosystemi **Pico** ventilation/air quality devices.  
Protocol: **local UDP**, listen port `40069`, send to device port `40070`. No cloud dependency.

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

### Setup flow (`__init__.py → async_setup`)
1. Read `devices` list from YAML
2. Create `PicoClientManager` → `initialize()` (binds shared UDP socket on `local_port`)
3. For each device: `manager.create_client(ip, pin, ...)` → `client.connect()` → create `MainCoordinator` → `async_refresh()`
4. Append coordinator to `hass.data[DOMAIN]["coordinators"]`
5. Load platforms via `discovery.async_load_platform` for all `PICO_PLATFORMS`

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
- `_wait_for_response()` handles this: detects ACK → waits for real response → sends ACK reply

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
- `PicoDeviceModel.is_on` → `operating.on_off == OnOffStateEnum.ON`
- `PicoDeviceModel.support_fan_speed_control` → `operating.mode in MODULAR_FAN_SPEED_PRESET_MODES`
- `PicoDeviceModel.support_target_humidity_selection` → `operating.mode in HUMIDITY_SELECTOR_PRESET_MODES`
- `PicoDeviceModel.support_night_mode_toggle` → same as fan speed
- `DeviceInfoModel.needs_clean_filters_maintenance` → `man[0] == 1`

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
`1` → `"40%"`, `2` → `"50%"`, `3` → `"60%"`

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
`_consecutive_failures` tracked; `_max_failures_before_reset = 3`. On disconnect → reconnect in `async_update_data`.

---

## Entities

### `BaseEntity` (`base.py`)
- Extends `CoordinatorEntity[MainCoordinator]`
- `_attr_has_entity_name = True`
- `available`: `coordinator.last_update_success and coordinator.data is not None`
- `device_info`: identifiers `(DOMAIN, coordinator.pico_ip)`, name from `data.device_info.name`, manufacturer `"Tecnosystemi"`, model `f"Model {device_info.model}"`, sw_version `device_info.firmware_version`
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
4. Validate YAML: **Developer Tools → YAML → Check Configuration**

Loaded via `async_setup` (YAML), not `async_setup_entry`. UI "Add Integration" registers the domain but does nothing else.
