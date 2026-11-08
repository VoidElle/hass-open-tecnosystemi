---
name: polaris
description: Expert agent for the Polaris HVAC integration. Use when working on Polaris TCP protocol, the cloud fallback (PolarisCloudClient), PolarisCoordinator, PolarisLocalClient, climate entities, or anything in the open-polaris-local-api package or polaris_coordinator.py.
---

# Polaris Integration — Agent Memory

Integration lives in `custom_components/open_pico/`. The TCP client and models come from the `open-polaris-local-api` package (pinned in `manifest.json`), not from this repo. Optional **cloud fallback** (HTTPS, vendor backend) for CUs not reachable on the LAN; see [Cloud fallback](#cloud-fallback-polariscloudclient).

---

## Configuration (UI only)

No YAML. Each Polaris CU is one config entry from **Add Integration -> Open Tecnosystemi -> Polaris** (`config_flow.py`): `polaris` (manual / scan / cloud) -> `polaris_manual` | `polaris_scan` -> `polaris_scan_results` -> `polaris_scan_confirm` | `polaris_cloud` -> `polaris_cloud_device`.

Local entry data: `device_type: "polaris"`, `ip`, `pin`, `name`, `scan_interval` (NumberSelector 10-300 s, step 5, default 30), `verbose`. Cloud entry data: see [Cloud fallback](#cloud-fallback-polariscloudclient).

Config entry unique ID: `polaris_<name_slug>` (`_abort_if_unique_id_configured` prevents duplicates). Every step that creates an entry validates connectivity first (`PolarisLocalClient(timeout=10).connect()` within 15 s).

---

## Module map (`custom_components/open_pico/`)
| File | Role |
|------|------|
| `__init__.py` | Entry setup / unload, `PICO_PLATFORMS`, `POLARIS_PLATFORMS` |
| `const.py` | `DOMAIN`, intervals, `MODE_INT_TO_PRESET`/`MODE_PRESET_TO_INT`, `TARGET_HUMIDITY_OPTIONS`/`REVERSED_TARGET_HUMIDITY_OPTIONS`, `POLARIS_COOLING_MODES` |
| `config_flow.py` | UI config flow (Pico + Polaris) |
| `base.py` | `BaseEntity` (Pico entities only) |
| `coordinator.py` | `MainCoordinator` (Pico) |
| `polaris_coordinator.py` | `PolarisCoordinator`, `PolarisData` |
| `pico_manager.py` | `PicoClientManager` (shared UDP transport) |
| `fan.py`, `switch.py`, `select.py`, `button.py` | Pico entities |
| `sensor.py`, `binary_sensor.py` | Pico + Polaris entities |
| `climate.py` | Polaris main + zone climate |

## Setup Flow (`__init__.py -> async_setup_entry -> _setup_polaris_entry`)

1. Cloud branch (`entry.data["connection"] == "cloud"`): see [Cloud fallback](#cloud-fallback-polariscloudclient). Local: create `PolarisLocalClient(ip, pin, device_id=f"polaris_{name_slug}", port=1235, timeout=15, retry_attempts=3, retry_delay=2.0, verbose)`
2. `client.connect()` (30 s) -> failure `ConfigEntryNotReady`
3. Create `PolarisCoordinator(hass, client, name, scan_interval=scan_interval)`
4. `coordinator.async_refresh()` (30 s); failure -> `client.close()` + `ConfigEntryNotReady`
5. Store in `hass.data[DOMAIN][entry.entry_id] = {"coordinator": ..., "device_type": "polaris"}`
6. `async_forward_entry_setups(entry, POLARIS_PLATFORMS)`, `POLARIS_PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.BINARY_SENSOR]`
7. Unload (`async_unload_entry`): unload platforms, then `coordinator.async_shutdown()` -> `client.close()`

---

## Cloud fallback (`PolarisCloudClient`)

Used only for entries with `entry.data["connection"] == "cloud"` (entries without the key are local). Never make it automatic: local TCP stays the primary path.

### Entry data
`device_type: "polaris"`, `connection: "cloud"`, `name`, `pin`, `email`, `password`, `serial` (upper-case), `android_id` (16 hex, generated once per entry), `scan_interval`, `command_delay`, `verbose`. Read both intervals with `.get()` + default.

### Config flow (`config_flow.py`)
`polaris` step `setup_method == "cloud"` -> `async_step_polaris_cloud` (email/password, login + `get_devices()`, which already returns Polaris CUs only; keeps serials not yet configured) -> `async_step_polaris_cloud_device` (serial select, PIN, name; generates `android_id`, validates with a fresh client `connect()`, which logs in and reads `GetCUState`; `PolarisAuthError` -> `invalid_auth`, `PolarisApiError("Wrong PIN")` -> `invalid_pin`). Client is always disconnected after validation. Unique ID `polaris_<name_slug>`, like local entries.

### Setup (`__init__.py -> _setup_polaris_entry`)
- `PolarisCloudClient(email, password, serial, pin, name, android_id, timeout=15, retry_attempts=2, retry_delay=2.0, verbose)`. `android_id` is the AES key seed sent at login, not an HA id
- `connect()` (30 s): `PolarisAuthError` -> `ConfigEntryError`, anything else -> `ConfigEntryNotReady`
- `PolarisCoordinator(..., scan_interval=entry.data.get("scan_interval", CLOUD_SCAN_INTERVAL), command_delay=entry.data.get("command_delay", CLOUD_COMMAND_DELAY), cloud=True)`. Defaults 30 s / 3 s, set in the `polaris_cloud_device` step (10-300 s step 5, 0-30 s)
- Unload: `coordinator.async_shutdown()` -> `client.close()` (closes the aiohttp session), same path as local

### Coordinator in cloud mode (`cloud=True`)
- No `stato_zona` (`get_zone_detail` raises `PolarisApiError` in cloud mode). Each poll rebuilds `zone_details` from the `GetCUState` zones: `{shu, shu_set, fan, fan_set, EV}` from `serranda`/`serranda_set`/`fancoil`/`fancoil_set`/`ev`. The cloud has no `EV_set`, so MiniDiscovery2X zones (shu `-1`) get no swing mode
- `_command()` waits `command_delay` (local default `_CMD_SETTLE_DELAY` = 1 s); serranda waits `max(2, command_delay)`
- `serial` falls back to `client.serial` instead of the IP (`client.ip == "cloud"`)
- Commands are inherited from `PolarisLocalClient` and only queued by the backend (FW < 4.x: up to 10 min). `update_cu` raises `PolarisApiError` if no state is cached; the coordinator always polls before writing, so this does not happen in normal use

### Debugging
- Bad credentials -> `PolarisAuthError` (subclass of `PolarisApiError`, import from `open_polaris_local_api.cloud`). Wrong PIN -> `PolarisApiError("Wrong PIN")`. No reply from the backend -> `TimeoutError`
- The backend allows one session per account: several cloud entries on the same account (Pico or Polaris), or the official app, may log each other out; the client re-logs in on 401
- `verbose: true` logs HTTP requests/responses (login excluded); logs contain email and PIN, redact before sharing

---

## Protocol (from decompiled APK `it.tecnosystemi.TS`)

### Transport
- **TCP**, port **1235**
- Per-command short-lived connections (open -> write -> read -> close) — mirrors `MySocket.sendAndReceive`
- `_BUFFER_SIZE = 4096` in our client (`1000` in APK Java)
- Read loop: `while True: chunk = await reader.read(_BUFFER_SIZE); if len(chunk) < _BUFFER_SIZE: break`
- **Connect timeout**: APK uses `1000ms`; our client wraps each command in `asyncio.wait_for(timeout=self.timeout)`
- **Retry**: `retry_attempts=2`, `retry_delay=1.0s` — mirrors APK's `timeouttimes=3` / 500ms
- Send: `writer.write(json.dumps(cmd).encode("utf-8")); await writer.drain()`
- `res`: `1` = OK, `4` = CMD_NOT_FOUND. The library checks it only in `get_status` (`4` -> fall back to `stato`) and `get_zone_detail` (anything but `1`, missing included -> `PolarisApiError`); write commands ignore it
- No IDP, no `frm` envelope — command key is `"c"` (not `"cmd"`)

### Command: Read state — `stato_r`
```json
{"c": "stato_r", "pin": "<pin>"}
```
Fallback if `res=4` (CMD_NOT_FOUND — old firmware):
```json
{"c": "stato", "pin": "<pin>"}
```
Implementation in the library's `client.py -> get_status()`:
```python
cmd = {"c": "stato_r", "pin": self.pin}
response = await self._send_command_with_retry(cmd)
if response is not None and response.get("res") == 4:
    cmd = {"c": "stato", "pin": self.pin}
    response = await self._send_command_with_retry(cmd)
```
**Never send `stato_sync` over TCP** — cloud/HTTP only.

### Command: Zone detail — `stato_zona`
```json
{"c": "stato_zona", "pin": "<pin>", "id_zona": 1}
```
Returns per-zone fields missing from `stato`/`stato_r`: `fan`, `fan_set`, `shu`, `shu_set`, `EV`, `EV_set`, `v` (fw), `m` (model). `-1` = hardware not installed.
`client.get_zone_detail(zone_id)` raises `TimeoutError` on no reply and `PolarisApiError` when `res != 1`. The integration calls it per zone (see Coordinator); the library's `client.fetch_all_zone_details()` is not used.

### Command: Device-level update — `upd_cu`
```json
{
  "c": "upd_cu", "pin": "<pin>",
  "is_off": 0, "is_cool": 0, "cool_mod": 0,
  "t_can": 230, "f_inv": -1, "f_est": -1
}
```
- `is_off`: `0`=machine ON, `1`=machine OFF
- `is_cool`: `0`=heating, `1`=cooling
- `cool_mod`: `1`=Raffrescamento, `2`=Deumidificazione, `3`=Ventilazione (only when `is_cool=1`); `0` when heating
- `t_can`: canal setpoint in °C × 10 (stored as `PolarisDevice.t_can` in °C; multiply by 10 before sending)
- **Must send ALL fields every time** — device resets missing fields to defaults
- Implementation in the library's `client.py -> update_cu()`: reads from `self._device` to fill unchanged fields

### Command: Zone update — `upd_zona`
```json
{
  "c": "upd_zona", "pin": "<pin>",
  "id_zona": 1, "name": "ZONA 1",
  "is_off": 0, "t_set": "215",
  "fan_set": 1, "shu_set": 1, "is_crono": 0
}
```
- `name`: always uppercase (APK calls `.toUpperCase()`); our code sends `zone.name` as-is (already uppercase from device)
- `t_set`: integer string — `str(round(set_temp * 10))` e.g. `"215"` = 21.5°C
- `fan_set`/`shu_set`: always sent together with same value
  - Value `7` (AUTO) -> send as `16` on wire
  - Only fancoil present (`serranda == -1`): use `fancoil_set`
  - Only serranda present (`fancoil == -1`): use `serranda_set`
  - Both present: fancoil wins (default `lastFancoil=True`)
- `is_off`: `1`=zone off, `0`=zone on — **independent per zone, does not affect other zones**
- `is_crono`: `1`=crono mode, `0`=manual

### Command: Crono update — `upd_fasce`
```json
{
  "c": "upd_fasce", "id_zona": 1, "pin": "<pin>",
  "0": [{"i": 32, "f": 64, "t": 215}, {"i": 0, "f": 0, "t": 240}, ...],
  "1": [...], "2": [...], "3": [...], "4": [...], "5": [...], "6": [...]
}
```
- Keys `"0"`–`"6"` = Mon–Sun; each day has exactly **4 slots**
- `"i"` = start time in 15-min units, `"f"` = end time, `"t"` = temp × 10
- Empty slot sentinel: `{"i": 0, "f": 0, "t": 240}`
- Time: `HH:MM` -> int = `(hours * 60 + minutes) / 15` (e.g. `08:00` -> `32`)

---

## Data Models (`open-polaris-local-api` package)

### `PolarisDevice`
```python
@dataclass
class PolarisDevice:
    serial: str; name: str; fw_ver: str; ip: str
    is_off: bool        # ridotto: "off", full: "is_off"
    is_cooling: bool    # ridotto: "cl", full: "is_cool"
    operating_mode: int # ridotto: "cl_m", full: "cool_mod" (0 when heating)
    t_can: int          # °C (parsed from t_can/tc × 10, stored as °C)
    f_inv: int; f_est: int; ir_present: int; num_errors: int
```
`PolarisDevice.is_on` = `not is_off`
`PolarisDevice.cooling_mode_name` -> `{0:"Heating", 1:"Cooling", 2:"Dehumidification", 3:"Ventilation"}`

Parsed via `PolarisDevice.from_local(data)` — handles both ridotto and full response formats.

### `PolarisZone`
```python
@dataclass
class PolarisZone:
    zone_id: int; name: str
    current_temp: float | None  # ridotto: "t", full: "t"
    set_temp: float | None      # ridotto: "ts", full: "t_set"
    is_off: bool                # ridotto: "off", full: "is_off"
    is_cooling: bool; fancoil: int; fancoil_set: int
    ev: int; serranda: int; serranda_set: int
    is_crono_mode: bool; is_master: bool
    humidity: float | None; set_humidity: float | None
    num_error: int; c_badge; c_win
```
`PolarisZone.is_on` = `not is_off`
Parsed via `PolarisZone.from_local(data)` — handles ridotto, full, and cloud PascalCase fields.

### Response field mapping (ridotto -> full)
**CU (`stato_r` ridotto):**
| Ridotto | Full | Meaning |
|---------|------|---------|
| `off` | `is_off` | machine off (0/1) |
| `cl` | `is_cool` | cooling (0/1) |
| `cl_m` | `cool_mod` | operating mode |
| `tc` | `t_can` | canal temp × 10 |
| `fi` | `f_inv` | function winter |
| `fe` | `f_est` | function summer |
| `ir` | `ir_present` | IR present |
| `m_nr` | `master_nr` | master zone |
| `err_cu` | `err_cu` | error bitmask |
| `zone` | `zone` | zone array |

**Zone (ridotto):**
| Ridotto | Full | Meaning |
|---------|------|---------|
| `nr` | `id_zona` | zone ID |
| `n` | `name` | name |
| `t` | `t` | current temp × 10 |
| `ts` | `t_set` | set temp × 10 |
| `off` | `is_off` | zone off |
| `fan`/`fan_set` | same | fancoil current/set |
| `shu`/`shu_set` | same | serranda current/set |
| `EV` | `EV` | valve |
| `err` | `err` | error bitmask |
| `is_crono`/`crono_on` | same | crono |
| `u`/`us` | `u`/`u_set` | humidity/setpoint |
| `w` | `c_win` | cwin |
| `b` | `c_badge` | cbadge |
| `co` | — | coff flag |

---

## Client (`open-polaris-local-api` package)

### `PolarisLocalClient`
```python
# library defaults
client = PolarisLocalClient(ip, pin, device_id=None, port=1235, timeout=5.0,
                             retry_attempts=2, retry_delay=1.0, verbose=False)
```
The integration overrides them: setup uses `timeout=15, retry_attempts=3, retry_delay=2.0`; config flow validation uses `timeout=10`.
`_send_command_with_retry` returns `None` after all attempts fail; `get_status()` and `get_zone_detail()` turn that into `TimeoutError`, `update_zone`/`update_cu` only log a warning.
- `connect()` -> calls `async_update()` -> sets `_connected=True`, caches `_device`/`_zones`
- `disconnect()` / `close()` -> sets `_connected=False` (TCP is stateless per-command)
- `async_update()` -> `get_status()` -> `PolarisDevice.from_local()` + `PolarisZone.from_local()` for each zone

### Control methods
```python
client.turn_on()                          # update_cu(is_off=False)
client.turn_off()                         # update_cu(is_off=True)
client.set_cooling_mode(mode: int)        # update_cu(is_off=False, is_cooling=True, operating_mode=mode)
client.set_heating_mode()                 # update_cu(is_off=False, is_cooling=False, operating_mode=0)
client.update_zone(zone, *, is_off, set_temp, is_crono, fancoil_set, serranda_set)
client.set_zone_temp(zone, temperature)   # update_zone(zone, set_temp=temperature)
client.turn_zone_on(zone)                 # update_zone(zone, is_off=False)
client.turn_zone_off(zone)                # update_zone(zone, is_off=True)
client.set_zone_serranda(zone, value)     # update_zone(zone, serranda_set=value); library docstring 0=Auto 1=A1 2=A2 3=A3 (the app uses 0=closed, 7=Auto: unverified on hardware)
client.get_zone_detail(zone_id)           # stato_zona
client.fetch_all_zone_details()           # stato_zona for every zone without errors (not used by the integration)
```

---

## Coordinator (`polaris_coordinator.py`)

### `PolarisCoordinator`
`coordinator.data` is `PolarisData(device: PolarisDevice, zones: list[PolarisZone])`.

```python
coordinator.polaris_device  # PolarisDevice | None
coordinator.polaris_zones   # list[PolarisZone]
coordinator.serial          # device serial or IP-based fallback
coordinator.zone_details    # {zone_id: stato_zona dict}
```

Zone details (`stato_zona`, damper/fancoil data) are fetched incrementally under `_tcp_lock`: none on the first refresh (it runs inside the 30 s setup timeout), then up to 2 missing zones per poll (`_ZONE_DETAILS_PER_POLL`), each with its own `client.timeout + 1` s limit and 1 s spacing. Zones with errors are skipped; a zone that fails 3 times in a row (`_MAX_ZONE_FAILURES`) is no longer fetched as missing. Once every zone is cached, one zone is refreshed every 3 polls in turn (`_ZONE_REFRESH_INTERVAL`). Every poll merges the cached `shu`/`shu_set`/`fan`/`fan_set` into the zones (no `EV` fallback), because `stato_r` does not carry them.

### Control methods (all call `async_request_refresh()` after)
```python
coordinator.async_turn_on()
coordinator.async_turn_off()
coordinator.async_set_cooling_mode(mode: int)   # 1=Raff, 2=Deum, 3=Vent
coordinator.async_set_heating_mode()
coordinator.async_set_zone_temp(zone_id, temp)
coordinator.async_turn_zone_on(zone_id)
coordinator.async_turn_zone_off(zone_id)
coordinator.async_update_zone(zone_id, **kwargs)  # generic
coordinator.async_set_zone_serranda(zone_id, value)  # sets zone.serranda only while sending (under the lock), updates the cache (shu/shu_set if shu != -1, else EV/EV_set) and notifies listeners, sleeps 2 s, then refresh
```

`_find_zone(zone_id)` searches `self.polaris_zones` list.

---

## Climate Entities (`climate.py`)

### HVAC mode mapping
```python
_HVAC_TO_CU = {
    HVACMode.HEAT:     (False, 0),   # is_cooling=False, cool_mod=0
    HVACMode.COOL:     (True,  1),   # Raffrescamento
    HVACMode.DRY:      (True,  2),   # Deumidificazione
    HVACMode.FAN_ONLY: (True,  3),   # Ventilazione
}
```

### `PolarisMainClimate` (one per CU)
- `unique_id`: `polaris_<serial>_main`
- Features: `TURN_ON | TURN_OFF`
- HVAC modes: `OFF, HEAT, COOL, DRY, FAN_ONLY`
- `current_temperature`: `dev.t_can` (canal temp, °C)
- `async_set_hvac_mode(OFF)` -> `coordinator.async_turn_off()`
- `async_set_hvac_mode(other)` -> `client.update_cu(is_off=False, is_cooling=..., operating_mode=...)` + refresh
- `device_info` identifiers: `(DOMAIN, f"polaris_{serial}")`

### `PolarisZoneClimate` (one per zone)
- `unique_id`: `polaris_<serial>_zone_<zone_id>`
- Features: `TARGET_TEMPERATURE | TURN_ON | TURN_OFF`
- HVAC modes: `OFF, AUTO` only
  - `AUTO` = zone active (machine decides actual heat/cool/vent)
  - `OFF` = zone off — **other zones unaffected**
- `hvac_mode`: `OFF` if zone or machine is off, else `AUTO`
- `target_temperature_step`: `0.5`, min `10.0`, max `30.0`
- `current_temperature`: `zone.current_temp`
- `target_temperature`: `zone.set_temp`
- `current_humidity`: `zone.humidity`
- `async_set_temperature` -> `coordinator.async_set_zone_temp(zone_id, temp)`
- `async_turn_on/off` -> `coordinator.async_turn_zone_on/off(zone_id)`
- `name`: zone name from the device (`zone.name.strip()`)
- `SWING_MODE` is turned on/off in `_handle_coordinator_update` (details can arrive after the entity is created): damper present when `shu != -1` or `EV_set >= 0`. `swing_mode` reads `shu_set`, falling back to `EV_set`. Swing modes = `SERRANDA_OPTIONS` `{0: "Auto", 1: "A1", 2: "A2", 3: "A3"}` -> `coordinator.async_set_zone_serranda()`

---

## Sensors and Binary Sensors

| Platform | Class | `unique_id` | Value |
|----------|-------|-------------|-------|
| SENSOR | `PolarisOperatingModeSensor` | `polaris_<serial>_operating_mode` | `POLARIS_COOLING_MODES[operating_mode]` (`heating`/`cooling`/`dehumidification`/`ventilation`); attrs `operating_mode_id`, `is_cooling`, `is_off`, `firmware`, `serial` |
| SENSOR | `PolarisZoneTemperatureSensor` | `polaris_<serial>_zone_<id>_temp` | `zone.current_temp` |
| SENSOR | `PolarisZoneHumiditySensor` | `polaris_<serial>_zone_<id>_humidity` | `zone.humidity` |
| BINARY_SENSOR | `PolarisDeviceErrorBinarySensor` | `polaris_<serial>_device_error` | `device.has_error`; attr `active_errors` |
| BINARY_SENSOR | `PolarisZoneErrorBinarySensor` | `polaris_<serial>_zone_<id>_error` | `zone.has_error`; attr `active_errors` |

All Polaris entities extend `CoordinatorEntity` directly (not `BaseEntity`) and share `device_info` identifiers `(DOMAIN, f"polaris_{serial}")`, model `"Polaris 5X"`.

---

## Troubleshooting / Known Behaviours

### `res` values
| `res` | Meaning |
|-------|---------|
| `1` | OK |
| `4` | CMD_NOT_FOUND — fall back `stato_r` -> `stato` |
| other | Error |
| missing | Protocol error / wrong format |

### Critical rules
- `stato_sync` is cloud/HTTP only — **never send over TCP**
- `upd_cu` must send ALL fields — read `self._device` state and merge before sending
- Polling too fast (< 10s) overloads device TCP stack -> official app shows "Stato sistema non sincronizzato"
- Default `scan_interval: 30s` is safe
- `t_can` stored internally as °C; multiply by 10 when sending in `upd_cu`
- `t_set` sent as integer string: `str(round(temp * 10))`
- `fan_set`/`shu_set` value `7` -> send as `16` (AUTO encoding)
- `fan_set`/`shu_set` must carry the same value; sending `fan_set=-1` hangs the CU

### APK Source References
- `it.tecnosystemi.TS.Model.ControlUnit.update_CU_command()` — canonical `upd_cu` builder
- `it.tecnosystemi.TS.Model.Zona.update_ZONA_Command()` — canonical `upd_zona` builder
- `it.tecnosystemi.TS.Commands.Protocols` — command string constants
- `it.tecnosystemi.TS.Utils.Constants` — all integer constants (`CU_ON=0`, `CU_OFF=1`, `CU_OPERATINGMODE_RAFF=1`, etc.)
- `it.tecnosystemi.TS.Commands.MySocket.commandToCU()` — TCP send/retry logic
- `it.tecnosystemi.TS.Activity.ControlUnitActivity` — UI -> command flow (btnOnOff, btnRaff, saveData)
