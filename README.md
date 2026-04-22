<div align="center">
  <img src="./assets/logo.png" alt="Logo" height="200">
  <br>
  <small><em>(Official Tecnosystemi logo not used due to copyright restrictions)</em></small>
  <br><br>
  <h1>🏠 Hassio Open Pico</h1>
  <p><em>Home Assistant integration for Tecnosystemi Pico and Polaris 5 devices</em></p>
</div>


Hassio Open Pico is a Home Assistant integration that enables management of Tecnosystemi devices through Home Assistant.

**Supported device families:**
- **Pico** — Local UDP-based ventilation and air quality units
- **Polaris 5X** — Local TCP-based HVAC zone controllers

Both device families communicate **entirely over your local network**, requiring no cloud connectivity.

This integration took inspiration from:
- The official [Tecnosystemi](https://play.google.com/store/apps/details?id=it.tecnosystemi.TS&hl=it) mobile application
- My own reverse engineered POC mobile application [Open Pico](https://github.com/VoidElle/open-pico-app)

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

After installing the integration (via HACS or manually) **and restarting Home Assistant**, you must add it from the UI:

1. Go to **Settings → Devices & Services**
2. Click **➕ Add Integration**
3. Search for **"Hassio Open Pico"**
4. Select it from the list
5. Go to the **configuration** step below

At this point, Home Assistant will load the integration and apply the configuration defined in `configuration.yaml`.

> ⚠️ **Important**  
> Even though configuration is YAML-based, this UI step is still required to register the integration inside Home Assistant.

## Configuration ⚙️

The integration is configured via `configuration.yaml`. You can configure Pico devices, Polaris 5 devices, or both.

### Pico devices (local)

```yaml
open_pico:
  # Optional: Enable verbose logging (default: false)
  verbose: false

  # Pico devices (local UDP, port 40069)
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

Polaris 5 devices communicate via **local TCP on port 1235** — the same protocol used by the official Tecnosystemi app. You need the device's local IP address and PIN code.

> **How to find the IP and PIN:** Connect to the Polaris device's WiFi access point (SSID starts with `POLARIS_`), or find its IP in your router's DHCP table. The PIN is the same one you use in the official Tecnosystemi app when selecting a device.

```yaml
open_pico:
  # Polaris 5 devices (local TCP, port 1235)
  polaris_devices:
    - ip: "192.168.8.200"
      pin: "0000"
      name: "Polaris Living Room"
      # Optional: polling interval in seconds (default: 30, minimum: 10)
      # The Polaris CU has a limited TCP stack. Polling too frequently
      # can disrupt the device's persistent cloud connection, causing
      # the official Tecnosystemi app to show "Stato sistema non sincronizzato".
      # Increase this value if you experience that issue.
      scan_interval: 30
```

| Parameter       | Required | Description                                                                                                                                      |
|-----------------|----------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| `ip`            | Yes      | Local IP address of the Polaris CU device                                                                                                        |
| `pin`           | Yes      | Device PIN code (the one you enter when selecting a device in the app)                                                                           |
| `name`          | No       | Friendly name (defaults to the name configured in the device)                                                                                    |
| `scan_interval` | No       | Polling interval in seconds (default: `30`, minimum: `10`). Lower values give faster HA updates but may interrupt the official app's cloud sync. |

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
      scan_interval: 30
```
1. Save your `configuration.yaml`
2. Check configuration validity: Developer Tools > YAML > Check Configuration
3. Restart Home Assistant

## Features ✨

### Pico
- 🌐 **Local UDP Communication**: Direct device control without cloud dependency
- 📊 **Real-time Monitoring**: Temperature, humidity, CO2, TVOC sensors
- 🎛️ **Full Control**: Operating modes, fan speed, night mode, LED control

### Polaris 5X
- 🌐 **Local TCP Communication**: Direct device control on port 1235, no cloud or internet required
- 🌡️ **Climate Entities**: Per-zone temperature control
- ❄️ **HVAC Modes**: Heating, Cooling (Raffrescamento, Deumidificazione, Ventilazione)
- 💧 **Zone Sensors**: Temperature and humidity per zone
- 📊 **Operating Mode**: Global CU operating mode sensor

### General
- 🔄 **Multi-Device Support**: Control multiple devices of both types simultaneously
- 🏷️ **Device Organization**: Use Home Assistant areas for logical grouping
- ⚡ **Concurrent Polling**: Efficient updates across all devices (5 second interval)

## Limitations ⚠️
- Both Pico and Polaris require local network access (devices must be on the same network as Home Assistant)
- Configuration via YAML only (no UI configuration flow yet)

## Tested On 🧪
- PICO PRO PLUS 30 **(ACD100052)**
- PICO PRO PLUS 60 **(ACD100054)**
- Polaris 5X

*Most features should work on all Pico and Polaris models*

## Contributing 🤝

Contributions are welcome! 

### How to Help
- 🐛 **Report bugs** via [GitHub Issues](https://github.com/VoidElle/hassio-open-pico/issues)
- 🌍 **Translate** to more languages
- 🔧 **Submit PRs** for improvements via [GitHub Pull requests](https://github.com/VoidElle/hassio-open-pico/pulls)
- 📖 **Improve documentation**

### Development
1. Fork and clone the repository
2. Create a feature branch: `git checkout -b feature/name`
3. Follow [Home Assistant dev guidelines](https://developers.home-assistant.io/)
4. Submit a PR with clear description