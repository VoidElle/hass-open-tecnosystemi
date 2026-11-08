# Polaris 5X

Tecnosystemi Polaris 5X HVAC zone controllers (CU), controlled over your local network (TCP), with an optional cloud fallback.

## Network Requirements

- Home Assistant and the Polaris CU must be on the same network.
- Allow TCP from Home Assistant to the CU on port **1235**.
- Give the CU a static or reserved IP: the integration connects to the IP entered at setup.

## Setup

### Manual

| Field | Default | Description |
|-------|---------|-------------|
| IP | — | Device LAN IP address |
| PIN | — | Device PIN |
| Name | — | Friendly name |
| Scan interval | 30 s | Poll interval (10–300 s, step 5) |

Keep the scan interval at 30 s or more: the CU has a limited network stack, and polling it too often stops the official app from syncing (it shows "Stato sistema non sincronizzato").

### Scan
1. Enter your subnet (e.g. `192.168.1.0/24`) and the PIN.
2. The integration probes TCP port 1235 on every host, sending the PIN, and lists the Polaris CUs that answer.
3. Already-configured devices are left out.
4. Pick a device, give it a name and a scan interval.

### Cloud
Use it only when the CU is not reachable on your local network.
1. Enter your Tecnosystemi account email and password.
2. Pick the CU, then enter its PIN and a name.

The state is polled every 30 s by default (10-300 s). After a command the integration waits 3 s by default (0-30 s) before refreshing. The vendor backend queues commands: a CU with firmware older than 4.x can take up to 10 minutes to apply them. Raise the delay if the state flips back after a command. The account email and password are stored in the config entry.

Damper (swing) control works in cloud mode only on zones that report the damper through `shu` (Stealth2X). MiniDiscovery2X zones get no swing mode, because the cloud does not send their damper setpoint.

The Tecnosystemi backend allows one session per account at a time: while the integration is running, the official app shows an alert and stops working.

---

## Entities

### Climate — Main (`climate.<name>`)
One per Polaris CU. Controls the whole machine.

| Feature | Supported |
|---------|-----------|
| Turn on / off | ✅ |
| HVAC modes | ✅ |

**HVAC modes:**

| HA mode | Tecnosystemi name |
|---------|-------------------|
| `heat` | Riscaldamento (heating) |
| `cool` | Raffrescamento (cooling) |
| `dry` | Deumidificazione (dehumidification) |
| `fan_only` | Ventilazione (ventilation) |
| `off` | Machine off |

The current temperature shows the canal temperature.

---

### Climate — Zone (`climate.<name>_<zone_name>`)
One per zone reported by the CU, named after the zone name stored on the device.

| Feature | Supported |
|---------|-----------|
| Turn on / off (zone only) | ✅ |
| Target temperature | ✅ (10–30 °C, step 0.5) |
| HVAC mode | `off` / `auto` only |
| Swing mode (damper / serranda) | ✅ `Auto`, `A1`, `A2`, `A3`, only for zones with a damper |

Turning a zone off does not affect the other zones or the CU.
`auto` means the zone is active; the machine mode is set on the main climate entity.

The damper data is read from the CU a few zones at a time after setup, so the swing mode can appear a minute or two after the zone entity. Zones that report an error are skipped until the error clears.

---

### Sensors

| Entity | Description |
|--------|-------------|
| `sensor.<name>_operating_mode` | CU mode: `heating`, `cooling`, `dehumidification`, `ventilation` |
| `sensor.<name>_<zone_name>_temperature` | Zone temperature (°C) |
| `sensor.<name>_<zone_name>_humidity` | Zone humidity (%) |

`sensor.<name>_operating_mode` also has these attributes: `operating_mode_id`, `is_cooling`, `is_off`, `firmware`, `serial`.

---

### Binary Sensors

| Entity | Description |
|--------|-------------|
| `binary_sensor.<name>_device_error` | The CU has at least one active error. The `active_errors` attribute lists them. |
| `binary_sensor.<name>_<zone_name>_error` | The zone has at least one active error. The `active_errors` attribute lists them. |

---

## Device
All entities of a CU are grouped under one device: manufacturer Tecnosystemi, model Polaris 5X, firmware from the CU.

## Connection Problems
- If the CU stops answering, its entities become unavailable until the next successful poll.
- If the CU cannot be reached when Home Assistant starts, the entry is retried automatically.
- Cloud: wrong email, password or PIN stops the entry with an error. To fix it, delete the entry and add the device again (re-adding it without deleting aborts with "already configured").
