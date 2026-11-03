# Pico

Tecnosystemi Pico ventilation and air quality units, controlled over your local network (UDP), with an optional cloud fallback.

## Network Requirements

- Home Assistant and the Pico must be on the same network.
- Allow UDP between them: the Pico listens on port **40070** and always replies to port **40069** on the Home Assistant host.
- Give the Pico a static or reserved IP: the integration connects to the IP entered at setup.

## Setup

### Manual

| Field | Description |
|-------|-------------|
| IP | Device LAN IP address |
| PIN | Device PIN |
| Name | Friendly name, used in entity IDs and the device registry |

### Scan
1. Enter your subnet (e.g. `192.168.1.0/24`) and the PIN.
2. The integration probes the network and lists the Pico devices that answer. Only devices with that PIN answer.
3. Already-configured devices are left out.
4. Pick a device and give it a name.

### Cloud
Use it only when the Pico is not reachable on your local network.
1. Enter your Tecnosystemi account email and password.
2. Pick the device, then enter its PIN and a name.

The state is polled every 30 s by default (10-300 s). After a command the integration waits 3 s by default (0-30 s) before refreshing, because the vendor backend applies commands with a short delay. Raise this delay if the state flips back after a command. The account email and password are stored in the config entry.

The Tecnosystemi backend allows one session per account at a time: while the integration is running, the official app shows an alert and stops working.

---

## Entities

### Fan — `fan.<name>_cmv`
Main control entity.

| Feature | Supported |
|---------|-----------|
| Turn on / off | ✅ |
| Preset modes | ✅ (12 operating modes) |
| Fan speed (%) | ✅ (when the mode supports it and night mode is off) |

**Preset modes:**

| Preset | Mode |
|--------|------|
| `heat_recovery` | Heat recovery |
| `extraction` | Extraction |
| `immission` | Immission |
| `humidity_recovery` | Humidity recovery |
| `humidity_extraction` | Humidity extraction |
| `comfort_summer` | Comfort summer |
| `comfort_winter` | Comfort winter |
| `co2_recovery` | CO2 recovery |
| `co2_extraction` | CO2 extraction |
| `humidity_co2_recovery` | Humidity/CO2 recovery |
| `humidity_co2_extraction` | Humidity/CO2 extraction |
| `natural_ventilation` | Natural ventilation |

Fan speed can be set in Heat Recovery, Extraction, Immission, Comfort Summer and Comfort Winter, while night mode is off. 100% is accepted in any mode outside night mode. In the other cases the fan entity shows only on/off.
Setting the speed to 0% turns the device off.

---

### Sensors

| Entity | Device Class | Unit | Notes |
|--------|-------------|------|-------|
| `sensor.<name>_temperature` | temperature | °C | |
| `sensor.<name>_humidity` | humidity | % | |
| `sensor.<name>_co2` | CO₂ | ppm | |
| `sensor.<name>_tvoc` | VOC | ppm | Icon changes with level |
| `sensor.<name>_eco2` | CO₂ (eCO₂) | ppm | Icon changes with level |

CO2, eCO2 and TVOC read 0 on models without the air quality sensor. They also read 0 on models with the sensor until a mode that turns it on is active (e.g. CO2 recovery). Disable these entities if you don't need them.

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
| `switch.<name>_night_mode` | Enables night mode | Available only in modes that support fan speed |
| `switch.<name>_led_status` | Controls the panel LED | Always available |

When night mode is on, fan speed control is disabled.

---

### Select Entities

| Entity | Options | Notes |
|--------|---------|-------|
| `select.<name>_preset_mode` | All 12 preset modes | Same as the fan preset |
| `select.<name>_target_humidity` | `40%`, `50%`, `60%` | Available only in Humidity Recovery, Humidity Extraction, Humidity/CO2 Recovery, Humidity/CO2 Extraction |

---

### Binary Sensor

| Entity | Device Class | Description |
|--------|-------------|-------------|
| `binary_sensor.<name>_filter_maintenance_required` | problem | `on` when the filters need cleaning |

---

### Button

| Entity | Description | Condition |
|--------|-------------|-----------|
| `button.<name>_reset_filter_maintenance` | Resets the filter maintenance alert | Available only when the maintenance alert is on |

---

## Update Interval
Local: every **5 seconds**. Cloud: every **30 seconds** by default, set at setup.

## Connection Problems
- If the Pico stops answering, the integration reconnects by itself on the next poll and the entities become unavailable until it answers again.
- If the Pico cannot be reached when Home Assistant starts, the entry is retried automatically.
- Cloud: wrong email or password stops the entry with an error; fix the credentials by adding the device again.
