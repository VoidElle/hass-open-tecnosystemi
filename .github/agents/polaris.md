---
name: polaris
description: Expert agent for the Polaris HVAC integration. Use when working on Polaris TCP protocol, PolarisCoordinator, PolarisLocalClient, climate entities, or anything in polaris_api/ or polaris_coordinator.py.
---

# Polaris Integration — Agent Memory

Root of this repository. Install as HA custom integration at `custom_components/hassio_open_pico/`.

---

## YAML Config

```yaml
open_pico:
  polaris_devices:
    - ip: "192.168.1.x"
      pin: "1234"
      name: "Polaris CU"     # optional
      scan_interval: 30      # seconds, min 10, default 30
```

Config schema: `POLARIS_DEVICE_SCHEMA` in `__init__.py`. `scan_interval < 10` rejected by voluptuous.

---

## Setup Flow (`__init__.py → _setup_polaris_devices`)

For each device:
1. Create `PolarisLocalClient(ip, pin, port=1235, timeout=5.0, retry_attempts=2, retry_delay=1.0)`
2. `client.connect()` → calls `async_update()` → performs first TCP poll
3. Create `PolarisCoordinator(hass, client, device_name, scan_interval)`
4. `await coordinator.async_config_entry_first_refresh()` with 30s timeout
5. Append to `hass.data[DOMAIN]["polaris_coordinators"]`
6. Load `POLARIS_PLATFORMS = [Platform.CLIMATE, Platform.SENSOR]` via `discovery.async_load_platform`

### hass.data layout
```python
hass.data[DOMAIN] = {
    "coordinators": [MainCoordinator, ...],          # Pico devices
    "polaris_coordinators": [PolarisCoordinator, ...],
    "manager": PicoClientManager,
    "config": domain_config,
}
```

---

## Protocol (from decompiled APK `it.tecnosystemi.TS`)

### Transport
- **TCP**, port **1235**
- Per-command short-lived connections (open → write → read → close) — mirrors `MySocket.sendAndReceive`
- `_BUFFER_SIZE = 4096` in our client (`1000` in APK Java)
- Read loop: `while True: chunk = await reader.read(_BUFFER_SIZE); if len(chunk) < _BUFFER_SIZE: break`
- **Connect timeout**: APK uses `1000ms`; our client wraps each command in `asyncio.wait_for(timeout=self.timeout)`
- **Retry**: `retry_attempts=2`, `retry_delay=1.0s` — mirrors APK's `timeouttimes=3` / 500ms
- Send: `writer.write(json.dumps(cmd).encode("utf-8")); await writer.drain()`
- Response validation: check `res` key. `res=1` = OK, `res=4` = CMD_NOT_FOUND, missing = protocol error
- No IDP, no `frm` envelope — command key is `"c"` (not `"cmd"`)

### Command: Read state — `stato_r`
```json
{"c": "stato_r", "pin": "<pin>"}
```
Fallback if `res=4` (CMD_NOT_FOUND — old firmware):
```json
{"c": "stato", "pin": "<pin>"}
```
Implementation in `polaris_client.py → get_status()`:
```python
cmd = {"c": "stato_r", "pin": self.pin}
response = await self._send_command_with_retry(cmd)
if response.get("res") == 4:
    cmd = {"c": "stato", "pin": self.pin}
    response = await self._send_command_with_retry(cmd)
```
**Never send `stato_sync` over TCP** — cloud/HTTP only.

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
- Implementation in `polaris_client.py → update_cu()`: reads from `self._device` to fill unchanged fields

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
  - Value `7` (AUTO) → send as `16` on wire
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
- Time: `HH:MM` → int = `(hours * 60 + minutes) / 15` (e.g. `08:00` → `32`)

---

## Data Models (`polaris_api/models.py`)

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
`PolarisDevice.cooling_mode_name` → `{0:"Riscaldamento", 1:"Raffrescamento", 2:"Deumidificazione", 3:"Ventilazione"}`

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

### Response field mapping (ridotto → full)
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

## Client (`polaris_api/polaris_client.py`)

### `PolarisLocalClient`
```python
client = PolarisLocalClient(ip, pin, port=1235, timeout=5.0,
                             retry_attempts=2, retry_delay=1.0, verbose=False)
```
- `connect()` → calls `async_update()` → sets `_connected=True`, caches `_device`/`_zones`
- `disconnect()` / `close()` → sets `_connected=False` (TCP is stateless per-command)
- `async_update()` → `get_status()` → `PolarisDevice.from_local()` + `PolarisZone.from_local()` for each zone

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
```

---

## Coordinator (`polaris_coordinator.py`)

### `PolarisCoordinator`
`coordinator.data` is `PolarisData(device: PolarisDevice, zones: list[PolarisZone])`.

```python
coordinator.polaris_device  # PolarisDevice | None
coordinator.polaris_zones   # list[PolarisZone]
coordinator.serial          # device serial or IP-based fallback
```

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
- `async_set_hvac_mode(OFF)` → `coordinator.async_turn_off()`
- `async_set_hvac_mode(other)` → `client.update_cu(is_off=False, is_cooling=..., operating_mode=...)` + refresh
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
- `async_set_temperature` → `coordinator.async_set_zone_temp(zone_id, temp)`
- `async_turn_on/off` → `coordinator.async_turn_zone_on/off(zone_id)`

---

## Troubleshooting / Known Behaviours

### `res` values
| `res` | Meaning |
|-------|---------|
| `1` | OK |
| `4` | CMD_NOT_FOUND — fall back `stato_r` → `stato` |
| other | Error |
| missing | Protocol error / wrong format |

### Critical rules
- `stato_sync` is cloud/HTTP only — **never send over TCP**
- `upd_cu` must send ALL fields — read `self._device` state and merge before sending
- Polling too fast (< 10s) overloads device TCP stack → official app shows "Stato sistema non sincronizzato"
- Default `scan_interval: 30s` is safe
- `t_can` stored internally as °C; multiply by 10 when sending in `upd_cu`
- `t_set` sent as integer string: `str(round(temp * 10))`
- `fan_set`/`shu_set` value `7` → send as `16` (AUTO encoding)

### APK Source References
- `it.tecnosystemi.TS.Model.ControlUnit.update_CU_command()` — canonical `upd_cu` builder
- `it.tecnosystemi.TS.Model.Zona.update_ZONA_Command()` — canonical `upd_zona` builder
- `it.tecnosystemi.TS.Commands.Protocols` — command string constants
- `it.tecnosystemi.TS.Utils.Constants` — all integer constants (`CU_ON=0`, `CU_OFF=1`, `CU_OPERATINGMODE_RAFF=1`, etc.)
- `it.tecnosystemi.TS.Commands.MySocket.commandToCU()` — TCP send/retry logic
- `it.tecnosystemi.TS.Activity.ControlUnitActivity` — UI → command flow (btnOnOff, btnRaff, saveData)
