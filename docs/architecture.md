# Architecture

Internal design of the Open Tecnosystemi integration.

---

## Module Overview

```
custom_components/open_pico/
├── __init__.py            # Entry setup / teardown
├── const.py               # Constants, mode mappings
├── config_flow.py         # UI config flow (Pico + Polaris)
├── base.py                # BaseEntity (CoordinatorEntity subclass)
├── coordinator.py         # MainCoordinator (Pico)
├── polaris_coordinator.py # PolarisCoordinator (Polaris)
├── pico_manager.py        # PicoClientManager (shared UDP transport)
├── fan.py                 # Pico: FanEntity
├── switch.py              # Pico: SwitchEntity (night mode, LED)
├── select.py              # Pico: SelectEntity (preset mode, target humidity)
├── button.py              # Pico: ButtonEntity (reset filter maintenance)
├── sensor.py              # Pico + Polaris: SensorEntity
├── binary_sensor.py       # Pico + Polaris: BinarySensorEntity
└── climate.py             # Polaris: ClimateEntity (main + zone)
```

---

## Config Entry Data Schema

### Pico entry
```json
{
  "device_type": "pico",
  "ip": "192.168.1.50",
  "pin": "1234",
  "name": "Living Room Pico",
  "local_port": 40069,
  "verbose": false
}
```

### Polaris entry
```json
{
  "device_type": "polaris",
  "ip": "192.168.1.60",
  "pin": "5678",
  "name": "Upstairs Polaris",
  "scan_interval": 30,
  "verbose": false
}
```

Unique IDs are `pico_<name_slug>` and `polaris_<name_slug>` respectively, preventing duplicate entries.

---

## Coordinators

### MainCoordinator (Pico)
Extends `DataUpdateCoordinator[PicoDeviceModel]`.

- `update_interval`: 5 s (`DEFAULT_SCAN_INTERVAL`)
- On poll: checks `client.connected`; reconnects if needed; calls `client.get_status(retry=True)`
- Control methods (`async_turn_on`, `async_set_mode`, etc.) call the API then `async_request_refresh()` for immediate state update
- `family_name` property returns a stable slug used in `unique_id` and device registry keys

### PolarisCoordinator (Polaris)
Extends `DataUpdateCoordinator[PolarisData]`.

- `update_interval`: configurable (default 30 s)
- On poll: calls `client.async_update()` → `(PolarisDevice, list[PolarisZone])` wrapped in `PolarisData`
- Zone operations dispatch to `client.turn_zone_on/off`, `client.set_zone_temp`, `client.update_zone`
- `serial` property returns `client.device.serial` or IP-based fallback for device registry keying

---

## Shared UDP Transport (Pico)

```
hass.data[DOMAIN]["pico_manager"]  →  PicoClientManager (singleton per HA instance)
    └── SharedTransportManager    →  single UDP socket on port 40069
        ├── PicoClient(ip=A, ...)
        ├── PicoClient(ip=B, ...)
        └── PicoClient(ip=C, ...)
```

`PicoClientManager` is created when the first Pico entry is set up and destroyed when the last Pico entry is removed. This prevents socket exhaustion with many devices.

---

## `hass.data` Layout

```python
hass.data["open_pico"] = {
    # One entry per config entry:
    "<entry_id_1>": {
        "coordinator": MainCoordinator | PolarisCoordinator,
        "device_type": "pico" | "polaris",
    },
    # Pico-only singleton:
    "pico_manager": PicoClientManager,
}
```

---

## Config Flow Steps

### Pico
```
async_step_user
  └─ async_step_pico
       ├─ (manual) async_step_pico_manual  →  create_entry
       └─ (scan)   async_step_pico_scan
                     └─ async_step_pico_scan_results
                          └─ async_step_pico_scan_confirm  →  create_entry
```

### Polaris
```
async_step_user
  └─ async_step_polaris
       ├─ (manual) async_step_polaris_manual  →  create_entry
       └─ (scan)   async_step_polaris_scan
                     └─ async_step_polaris_scan_results
                          └─ async_step_polaris_scan_confirm  →  create_entry
```

Both manual steps validate connectivity before creating the entry.

---

## Entity Base Class

`BaseEntity(CoordinatorEntity)` — used by all Pico entities:
- Sets `_attr_has_entity_name = True`
- Implements `device_info` from `coordinator.data.device_info`
- `available` = `last_update_success and data is not None`
- `_handle_coordinator_update` → `async_write_ha_state()`

Polaris entities do **not** use `BaseEntity`; they extend `CoordinatorEntity` directly (different coordinator type and device_info structure).

---

## Constants (`const.py`)

| Name | Type | Description |
|------|------|-------------|
| `DOMAIN` | str | `"open_pico"` |
| `DEFAULT_SCAN_INTERVAL` | int | `5` (seconds, Pico) |
| `MODE_INT_TO_PRESET` | dict[int, str] | Mode ID → preset name |
| `MODE_PRESET_TO_INT` | dict[str, int] | Reverse of above |
| `TARGET_HUMIDITY_OPTIONS` | dict[int, str] | 1/2/3 → 40%/50%/60% |
| `REVERSED_TARGET_HUMIDITY_OPTIONS` | dict[str, int] | Reverse of above |
| `POLARIS_COOLING_MODES` | dict[int, str] | 0–3 → mode name strings |

---

## Unload Sequence

```
async_unload_entry
  1. Unload all platforms
  2. coordinator.async_shutdown()
     - Pico: no-op (client managed by PicoClientManager)
     - Polaris: client.close()
  3. (Pico only) If no remaining Pico entries:
       PicoClientManager.shutdown()
         → disconnect all clients
         → SharedTransportManager.shutdown()
```
