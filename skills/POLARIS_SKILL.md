---
# Agent skill — install locally with:
#   npx skills add ./POLARIS_SKILL.md
# or from GitHub after pushing:
#   npx skills add <owner>/<repo>
name: polaris-memory
description: >
  Persistent memory for the Hassio Open Pico / Polaris integration.
  Carries forward all protocol knowledge, design decisions, and code structure
  so the agent never needs to re-read source files or re-derive the protocol
  from the APK. Auto-activate when user mentions Polaris, open_pico, Tecnosystemi,
  ControlUnit, upd_cu, or asks about the HVAC integration.
---

# Polaris Integration — Agent Memory

## Project Location
Root of this repository — install as HA custom integration at `custom_components/hassio_open_pico/` (folder name matters).

---

## Protocol (from decompiled APK `it.tecnosystemi.TS`)

### Transport (from `MySocket.java`)
- **TCP**, port **1235**, device IP from config
- Per-command short-lived connections (open → send → read → close) — matches `MySocketReadAndWrite.doInBackground`
- `BUFFER_SIZE = 1000` bytes per read chunk
- **Connect timeout**: `1000ms` (`SOCKET_TIMEOUT`). Retry once after `800ms` sleep (2 attempts total in `connectWithSocket`)
- **Read timeout**: `1000ms` normal, `15000ms` (`SOCKET_MORE_TIMEOUT`) when `useLong=true` (set for slow commands like `scan_wifi`, `config`)
- **Retry logic**: `timeouttimes = 3` — on timeout response (`TIMEOUTERR`), `commandToCU` recurses up to 3 times with `500ms` delay between attempts, then resets to 3 and returns `""`
- **Read loop**: reads until chunk `< 1000` bytes → end of response. 100ms sleep between chunks if full buffer. Our Python mirrors this with `len(chunk) < _BUFFER_SIZE` break
- **Send**: `PrintWriter.write()` + `flush()` — plain UTF-8 string, no framing/length prefix
- **Response validation**: checks `res` key in JSON. `res=1` = OK. Missing `res` key = error. `res=4` = CMD_NOT_FOUND
- No cloud dependency when in local/offline mode

### Command Format
All commands are UTF-8 JSON strings. Key `"c"` is the command type.

#### Read state — CU level
```json
{"c": "stato_r", "pin": "<pin>"}
```
Fallback if `res=4` (CMD_NOT_FOUND):
```json
{"c": "stato", "pin": "<pin>"}
```
- Used when activity is `ControlUnitActivity` (CU screen)
- Calls `offlineResCURistretto()` on response

#### Read state — zone level
```json
{"c": "stato_zona", "pin": "<pin>", "id_zona": <zone_id>}
```
- Used when activity is `ZoneActivity` (single zone screen)
- Only sent in offline/local mode
- Calls `offlineResZona()` on response
- **Not needed for HA integration** — we poll full CU state (`stato_r`) which includes all zones

#### Polling loop (from `BaseActivity.inizializeGetState`)
- Runs on `Handler.postDelayed(this, thread_sleep)` — repeats every `thread_sleep` ms
- Guards: skips if `gettingstate=true` OR `interrupt=true` OR `sendingstate=true`
- Online mode: HTTP `ThreadWebService` → `GETSTATEFIRST` (op 12) first call, `GETSTATE` (op 11) subsequent
- Offline/local mode: TCP `stato_r` → `offlineResCURistretto()`
- `stopgetState()`: sets `interrupt=true`, calls `thread.interrupt()`, clears handler callbacks
- Our HA equivalent: `DataUpdateCoordinator` with `update_interval=timedelta(seconds=scan_interval)` — same pattern, cleaner

#### Global machine on/off + mode — `upd_cu`
```json
{
  "c": "upd_cu",
  "pin": "<pin>",
  "is_off": 0,
  "is_cool": 0,
  "cool_mod": 0,
  "t_can": 230,
  "f_inv": -1,
  "f_est": -1
}
```
- `is_off`: `0`=machine ON, `1`=machine OFF
- `is_cool`: `0`=heating, `1`=cooling
- `cool_mod`: `1`=Raffrescamento, `2`=Deumidificazione, `3`=Ventilazione (only when `is_cool=1`)
- `t_can`: canal setpoint in °C × 10
- `f_inv`/`f_est`: function winter/summer (`-1`=not configured)

#### Zone update — `upd_zona` (from `Zona.update_ZONA_Command()`)
```json
{
  "c": "upd_zona",
  "id_zona": 1,
  "name": "ZONA 1",
  "is_off": 0,
  "t_set": "215",
  "fan_set": 1,
  "shu_set": 1,
  "is_crono": 0,
  "pin": "<pin>"
}
```
- `name`: always uppercase (`.toUpperCase()` in APK)
- `t_set`: `String.valueOf((int)(Double.parseDouble(setTemp) * 10))` — integer string e.g. `"215"` for 21.5°C
- `is_off`: `1`=zone off, `0`=zone on
- `is_crono`: `1`=crono mode, `0`=manual
- `fan_set` / `shu_set` — always both sent with same value. Logic from `update_ZONA_Command()`:
  - Only fancoil present (`serranda == -1`): use `fancoilSet`
  - Only serranda present (`fancoil == -1`): use `serrandaSet`
  - Both present + `lastFancoil=true` (default): use `fancoilSet`
  - Both present + `lastFancoil=false`: use `serrandaSet`
  - Any value of `7` → send as `16` on the wire (AUTO mode encoding)
- `pin` added by caller (activity), not by `update_ZONA_Command()` itself

#### Crono (schedule) update — `upd_fasce` (from `Zona.updCronoCommand()` + `Crono.commandUpd()`)
```json
{
  "c": "upd_fasce",
  "id_zona": 1,
  "pin": "<pin>",
  "0": [{"i": 32, "f": 64, "t": 215}, {"i": 0, "f": 0, "t": 240}, ...],
  "1": [...],
  "2": [...],
  "3": [...],
  "4": [...],
  "5": [...],
  "6": [...]
}
```
- Keys `"0"`…`"6"` = Mon…Sun (7 days)
- Each day has exactly **4 slots** (array of 4)
- Each slot JSON fields (from `Constants.java`):
  - `"i"` (`JSON_COMMAND_START`) = start time as **15-min units** (0–95, where 96=24:00)
  - `"f"` (`JSON_COMMAND_END`) = end time as **15-min units**
  - `"t"` (`JSON_COMMAND_TEMP`) = target temp × 10 (int), e.g. `215` = 21.5°C
- **Empty/void slot**: `{"i": 0, "f": 0, "t": 240}` — temp `240` = sentinel for "no slot" (`commandUpdVoid()`)
- **Time conversion**: `HH:MM` → int = `(hours * 60 + minutes) / 15`. E.g. `08:00` → `32`, `16:00` → `64`
- **Reverse**: int → `HH:MM` = `(n * 15) / 60 : (n * 15) % 60`. If hours == 24 → treat as 00
- **Temp encoding**: stored as display string (e.g. `"21.5"`) → wire = `(int)(Double.parseDouble(temp) * 10)` = `215`
- Slot validity (`isok()`): start != end, end > start, startTime < endTime (positive diff), temp parseable as double
- `normalizzaOrario()`: called on read — converts int-encoded times back to `HH:MM` and temp ÷ 10

### Response fields — zone (stato full format, from `getZonaFromJsonOffline`)
| Field | Meaning |
|-------|---------|
| `id_zona` or `nr` | zone ID |
| `name` | zone name |
| `t` | current temp × 10 (int) |
| `t_set` | set temp × 10 (int) |
| `is_off` | zone off (0/1) |
| `is_cool` | cooling active (0/1) |
| `fan` | fancoil current speed (-1=not present) |
| `fan_set` | fancoil setpoint |
| `shu` | serranda current (-1=not present) |
| `shu_set` | serranda setpoint |
| `EV` | EV valve state |
| `err` | error bitmask (int) |
| `is_crono` | crono mode active (0/1) |
| `crono_on` | crono fascia active (0/1) |
| `u` | humidity (string) |
| `u_set` | set humidity (string) |
| `c_win` | cwin value |
| `c_badge` | cbadge value |

### Response fields — zone (stato_r ridotto format, from `getZonaFromJsonOfflineRidotto`)
Ridotto uses shortened keys; temp fields still use `t`/`t_set` full names:
| Ridotto key | Full key | Meaning |
|-------------|----------|---------|
| `nr` | `id_zona` | zone ID |
| `n` | `name` | zone name |
| `t` | `t` | current temp × 10 |
| `ts` | `t_set` | set temp × 10 |
| `off` | `is_off` | zone off |
| `fan` | `fan` | fancoil speed |
| `fan_set` | `fan_set` | fancoil setpoint |
| `shu` | `shu` | serranda |
| `shu_set` | `shu_set` | serranda setpoint |
| `EV` | `EV` | EV valve |
| `err` | `err` | error bitmask |
| `is_crono` | `is_crono` | crono mode |
| `crono_on` | `crono_on` | crono fascia active |
| `u` | `u` | humidity |
| `us` | `u_set` | set humidity |
| `w` | `c_win` | cwin |
| `b` | `c_badge` | cbadge |
| `co` | — | `coff` flag (zone comfort-off computed state) |

### `coff` computed field
Zone `coff=true` when any of:
- `c_badge == 1`
- `c_win == 1`
- `is_crono=true` AND `crono_on=false` (crono active but outside fascia)

This is a display hint — zone shows as "comfort off". Not a command field.

---

## Key Constants (from `Constants.java`)
- `CU_ON = 0`, `CU_OFF = 1`
- `CU_OPERATINGMODE_RAFF = 1`, `CU_OPERATINGMODE_UMD = 2`, `CU_OPERATINGMODE_VENT = 3`
- Port: `1235`

---

## Code Architecture

### Files
| File | Role |
|------|------|
| `polaris_api/polaris_client.py` | Low-level TCP client — `PolarisLocalClient` |
| `polaris_api/models.py` | `PolarisDevice`, `PolarisZone` dataclasses |
| `polaris_coordinator.py` | `PolarisCoordinator(DataUpdateCoordinator)` — all control methods |
| `climate.py` | HA Climate entities — one per zone |
| `__init__.py` | YAML setup, bootstraps coordinators into `hass.data[DOMAIN]["polaris_coordinators"]` |

### Client methods
```python
client.turn_on()                          # upd_cu is_off=0
client.turn_off()                         # upd_cu is_off=1
client.set_cooling_mode(mode: int)        # upd_cu is_off=0, is_cool=1, cool_mod=mode
client.set_heating_mode()                 # upd_cu is_off=0, is_cool=0, cool_mod=0
client.update_zone(zone, is_off, ...)     # upd_zona
```

### Coordinator methods
```python
coordinator.async_turn_on()
coordinator.async_turn_off()
coordinator.async_set_cooling_mode(mode)  # 1=Raff, 2=Deum, 3=Vent
coordinator.async_set_heating_mode()
coordinator.async_set_zone_temp(zone_id, temp)
coordinator.async_turn_zone_on(zone_id)
coordinator.async_turn_zone_off(zone_id)
```
All methods call `async_request_refresh()` after sending command.

---

## Climate Entity Design (climate.py)

### Two entity types (refactored 2026-04-28)

**`PolarisMainClimate`** — one per CU
- `unique_id`: `polaris_<serial>_main`
- Features: `TURN_ON`, `TURN_OFF`, `PRESET_MODE`
- HVAC modes: `OFF`, `HEAT`, `COOL` → all call `upd_cu`
- Presets: `Raffrescamento`, `Deumidificazione`, `Ventilazione` → `upd_cu cool_mod`
- `current_temperature`: canal temp (`dev.t_can`)
- No target temp (canal setpoint not user-facing in HA)

**`PolarisZoneClimate`** — one per zone
- `unique_id`: `polaris_<serial>_zone_<id>`
- Features: `TARGET_TEMPERATURE`, `TURN_ON`, `TURN_OFF`
- HVAC mode `OFF` → `upd_zona is_off=1` (zone only, other zones unaffected)
- HVAC mode `HEAT`/`COOL` → `upd_zona is_off=0` (zone on; mode set via main entity)
- `async_turn_on/off` → `coordinator.async_turn_zone_on/off(zone_id)` → `upd_zona`
- `current_temperature` / `target_temperature` / `current_humidity` from zone data
- `hvac_mode` reflects CU mode but is read from `dev`; shows `OFF` if machine OR zone is off

### Key design decisions
- Zone on/off is **independent** — `upd_zona is_off` per zone, confirmed in `ZoneActivity.saveData()` and `Zona.update_ZONA_Command()`
- Machine on/off via main entity only → no confusion from zone entities shutting down whole machine
- All entities share same `device_info` identifiers → grouped under one HA device

### Key fix applied (2026-04-28)
Original single entity routed `async_turn_on/off` to zone methods (`upd_zona`) instead of CU (`upd_cu`). Refactored into two entity types with correct routing.

---

## YAML Config
```yaml
open_pico:
  polaris_devices:
    - ip: "192.168.1.x"
      pin: "1234"
      name: "Polaris CU"
      scan_interval: 30   # seconds, min 10
```

---

## APK Source References
- `it.tecnosystemi.TS.Model.ControlUnit` — `update_CU_command()` is the canonical command builder
- `it.tecnosystemi.TS.Commands.Protocols` — command string constants
- `it.tecnosystemi.TS.Utils.Constants` — all integer constants
- `it.tecnosystemi.TS.Activity.ControlUnitActivity` — UI → command flow (btnOnOff, btnRaff, saveData)
- `it.tecnosystemi.TS.Commands.MySocket` — TCP sender (`commandToCU(json, ip, port, ...)`)

---

## Troubleshooting / Known Behaviours

### Response `res` values
| `res` | Meaning |
|-------|---------|
| `1`   | OK — command accepted |
| `4`   | CMD_NOT_FOUND — device doesn't support this command (e.g. `stato_r` on old FW) |
| other | Error — device rejected command |
| missing | Protocol error / wrong command format |

### Timeout behaviour (from `MySocket.commandToCU`)
- Response `"timeouterr"` → retry up to 3 times, 500ms apart → return `""` on all failures
- Our Python equivalent: `retry_attempts=3`, `retry_delay=1.0` in `PolarisLocalClient`
- If device IP unreachable: `connectWithSocket` tries twice with 800ms sleep → returns empty socket

### `stato_r` vs `stato`
- Always try `stato_r` first (compact format, less data to parse)
- Fall back to `stato` only if `res=4` — older firmware doesn't support `stato_r`
- `stato_sync` is cloud/HTTP only — **never send over TCP**

### `upd_cu` must send full state
- Device expects ALL fields every time — `is_off`, `is_cool`, `cool_mod`, `t_can`, `f_inv`, `f_est`
- Missing fields may cause device to reset them to defaults
- Always read current `PolarisDevice` state and merge before sending

### Response fields — CU (stato_r ridotto format)
| Ridotto key | Full key | Meaning |
|-------------|----------|---------|
| `off` | `is_off` | machine off (0/1) |
| `cl` | `is_cool` | cooling active (0/1) |
| `cl_m` | `cool_mod` | operating mode (1/2/3) |
| `tc` | `t_can` | canal temp × 10 |
| `fi` | `f_inv` | function winter |
| `fe` | `f_est` | function summer |
| `ir` | `ir_present` | IR present |
| `m_nr` | `master_nr` | master zone nr |
| `err_cu` | `err_cu` | error bitmask |
| `zone` | `zone` | array of zone objects |

### `fan_set`/`shu_set` value `7` → send as `16`
- `ZONE_FANCOIL_AUTO = 7` (app constant) maps to wire value `16`
- Both `fan_set` and `shu_set` always sent together with same value
- Priority: fancoil-only → use `fancoilSet`; serranda-only → use `serrandaSet`; both present → `lastFancoil` flag decides (default `true` = fancoil wins)
- Confirmed in `Zona.update_ZONA_Command()` (APK) and `update_zone()` in `polaris_client.py`

### Zone `t_set` sent as integer string
- `"215"` not `"21.5"` — `(int)(setTemp * 10)` then `String.valueOf()`
- Confirmed in `Zona.update_ZONA_Command()`: `String.valueOf((int)(Double.parseDouble(getSetTemp()) * 10.0))`
- Python sends `str(round(temp * 10))` ✓

### Zone `name` always uppercase
- APK calls `.toUpperCase()` on get and set — device expects uppercase names
- Python should send `zone.name.upper()` in `upd_zona`

### Scan interval warning
- Polling too frequently (< 10s) can disrupt the device's persistent cloud connection
- Official app shows "Stato sistema non sincronizzato" when TCP stack is overloaded
- Default `scan_interval: 30` is safe

