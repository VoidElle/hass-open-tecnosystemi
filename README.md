<div align="center">
  <img src="./assets/logo.png" alt="Logo" height="200">
  <br>
  <small><em>(Official Tecnosystemi logo not used due to copyright restrictions)</em></small>
  <br><br>
  <h1>🏠 Hassio Open Pico</h1>
  <p><em>Home Assistant integration for Tecnosystemi Pico and Polaris 5 devices</em></p>

  [![GitHub Release](https://img.shields.io/github/v/release/VoidElle/hassio-open-pico?style=flat-square)](https://github.com/VoidElle/hassio-open-pico/releases)
  [![HACS](https://img.shields.io/badge/HACS-Custom-orange?style=flat-square)](https://github.com/hacs/integration)
  [![License](https://img.shields.io/github/license/VoidElle/hassio-open-pico?style=flat-square)](LICENSE)
  [![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue?style=flat-square)](https://www.home-assistant.io/)
</div>


Hassio Open Pico is a Home Assistant integration that enables management of Tecnosystemi devices through Home Assistant.

**Supported device families:**
- **Pico** — Ventilation and air quality units
- **Polaris 5** — HVAC zone controllers

Both device families communicate over the **same local UDP protocol** (ports 40069/40070), requiring no cloud connectivity.

This integration took inspiration from:
- The official [Tecnosystemi](https://play.google.com/store/apps/details?id=it.tecnosystemi.TS&hl=it) mobile application
- My own reverse engineered POC mobile application [Open Pico](https://github.com/VoidElle/open-pico-app)

## Prerequisites ✅

- **Home Assistant** 2024.1 or newer
- **Python** 3.11+ (bundled with Home Assistant)
- Pico / Polaris devices must be on the **same local network** as Home Assistant
- UDP ports **40069** and **40070** must be reachable from the HA host (not blocked by firewall)

## Installation 📦
### Via HACS (Recommended) ⭐
[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=VoidElle&repository=hassio-open-pico&category=integration)

### Via HACS (Manual)
1. Add custom repository:
   - Open HACS in your Home Assistant interface
    - Go to "Integrations" tab
    - Click on the three dots in the top right corner and select "Custom repositories"
    - Enter the repository URL: `https://github.com/VoidElle/hassio-open-pico`
    - Select "Integration" as the category
    - Click "Add"


2. Install the integration:
   - In HACS Integrations, click + Explore & Download Repositories
   - Search for "Hassio Open Pico"
   - Click on the integration and then Download
   - Select the latest version and click Download


3. Restart Home Assistant 🔄

### Manual Installation 🔧
1. Copy the repository content inside a folder called `hassio_open_pico`
2. Move the folder to your `custom_components` directory
3. Restart Home Assistant

## Add the Integration to Home Assistant 🧩

> ⚠️ **Required step — do not skip!**  
> Even though configuration is YAML-based, registering the integration from the UI is mandatory. Without this step, Home Assistant will not load it.

After installing and restarting Home Assistant:

1. Go to **Settings → Devices & Services**
2. Click **➕ Add Integration**
3. Search for **"Hassio Open Pico"**
4. Select it — no further UI configuration is needed
5. Proceed to the **Configuration** section below

## Configuration ⚙️

The integration is configured via `configuration.yaml`. You can configure Pico devices, Polaris 5 devices, or both.

### Pico devices (local)

```yaml
open_pico:
  # Optional: Enable verbose logging (default: false)
  verbose: false

  # Pico devices (local UDP)
  devices:
    - ip: "192.168.8.133"
      pin: "1234"
      name: "Living Room"

    - ip: "192.168.8.159"
      pin: "1234"
      name: "Bedroom"
```

| Parameter | Required | Description                         |
|-----------|----------|-------------------------------------|
| `ip`      | Yes      | Local IP address of the Pico device |
| `pin`     | Yes      | Device PIN code                     |
| `name`    | No       | Friendly name for the device        |

### Polaris 5 devices (local)

Polaris 5 devices communicate via the same local UDP protocol as Pico devices. You need the device's local IP address and PIN code.

> **How to find the IP and PIN:** Connect to the Polaris device's WiFi access point (SSID starts with `POLARIS_`), or find its IP in your router's DHCP table. The PIN is the same one you use in the official Tecnosystemi app when selecting a device.

```yaml
open_pico:
  # Polaris 5 devices (local UDP)
  polaris_devices:
    - ip: "192.168.8.200"
      pin: "0000"
      name: "Polaris Living Room"
```

| Parameter | Required | Description                                                            |
|-----------|----------|------------------------------------------------------------------------|
| `ip`      | Yes      | Local IP address of the Polaris CU device                              |
| `pin`     | Yes      | Device PIN code (the one you enter when selecting a device in the app) |
| `name`    | No       | Friendly name (defaults to the name configured in the device)          |

### Mixed configuration (Pico + Polaris)

You can configure both Pico and Polaris devices in the same integration:

```yaml
open_pico:
  verbose: false

  devices:
    - ip: "192.168.8.133"
      pin: "1234"
      name: "Pico Living Room"

  polaris_devices:
    - ip: "192.168.8.200"
      pin: "0000"
      name: "Polaris Living Room"
```

**After configuration:**
1. Save your `configuration.yaml`
2. Check configuration validity: **Developer Tools → YAML → Check Configuration**
3. Restart Home Assistant

## Features ✨

### Pico
- 🌐 **Local UDP Communication**: Direct device control without cloud dependency
- 📊 **Real-time Monitoring**: Temperature, humidity, CO2, TVOC sensors
- 🎛️ **Full Control**: Operating modes, fan speed, night mode, LED control

### Polaris 5
- 🌐 **Local UDP Communication**: Direct device control, no cloud or internet required
- 🌡️ **Climate Entities**: Per-zone temperature control (10-30°C, 0.5° step)
- ❄️ **HVAC Modes**: Heating, Cooling (Raffrescamento, Deumidificazione, Ventilazione)
- 📊 **Zone Sensors**: Temperature, humidity, and operating mode per zone

### General
- 🔄 **Multi-Device Support**: Control multiple devices of both types simultaneously
- 🏷️ **Device Organization**: Use Home Assistant areas for logical grouping
- ⚡ **Concurrent Polling**: Efficient updates across all devices
- 🔌 **Shared UDP Transport**: All Pico devices share a single UDP socket, no port conflicts

## Limitations ⚠️
- Both Pico and Polaris require local network access (devices must be on the same network as Home Assistant)
- Configuration via YAML only (no UI configuration flow yet)

## Tested On 🧪
- PICO PRO PLUS 30 **(ACD100052)**
- PICO PRO PLUS 60 **(ACD100054)**
- **Polaris 5** (via local UDP)

*Most features should work on all Pico and Polaris models*

## Troubleshooting 🔧

**Integration not showing up after installation**
Make sure you completed the UI registration step (**Settings → Devices & Services → Add Integration**). The integration won't load without it, even if `configuration.yaml` is correct.

**Device unavailable / no entities**
- Confirm the device IP is reachable from HA: `ping <device_ip>`
- Check the PIN matches the one used in the official Tecnosystemi app
- UDP ports 40069/40070 must not be blocked between HA and the device
- Enable verbose logging and restart HA to see detailed errors:
  ```yaml
  open_pico:
    verbose: true
  ```

**YAML configuration error on startup**
Validate before restarting: **Developer Tools → YAML → Check Configuration**. The most common mistakes are a wrong `pin` type (must be a string, e.g. `"1234"` not `1234`) or an unreachable IP.

**Entities stuck after a control action**
Each control method calls `async_request_refresh()` immediately after sending the command. If the device is slow to respond, wait one polling cycle (5 seconds) before reporting a bug.

## Contributing 🤝

Contributions are welcome!

### How to Help
- 🐛 **Report bugs** via [GitHub Issues](https://github.com/VoidElle/hassio-open-pico/issues)
- 🌍 **Translate** to more languages
- 🔧 **Submit PRs** for improvements via [GitHub Pull Requests](https://github.com/VoidElle/hassio-open-pico/pulls)
- 📖 **Improve documentation**

### Development Setup
1. Fork and clone the repository
2. Copy the folder into your HA instance as `custom_components/hassio_open_pico/` (the folder name matters)
3. Add a test device to `configuration.yaml` with `verbose: true`
4. Restart HA and check **Settings → System → Logs** for `[open_pico]` entries
5. After making changes, validate config with **Developer Tools → YAML → Check Configuration** before restarting

Create a feature branch before starting work:
```bash
git checkout -b feature/your-feature-name
```

## Work in progress 🚧
- [X] Include the device sensors as entities
- [X] Polaris 5 local UDP support
- [X] Polaris climate entities (heat/cool/off per zone)
- [X] Polaris cooling sub-modes (Cooling, Dehumidification, Ventilation)
- [ ] Polaris auto-discovery via network scan
- [ ] Pico auto-discovery via network scan
- [X] Show device error/maintenance flags as entities
- [ ] UI configuration flow (alternative to YAML)
- [ ] Fix entities IDs, they are incomprehensible
- [ ] Fix device unique IDs, currently they are based on IP address, it is not ideal
