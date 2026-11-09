<div align="center">
  <img src="./assets/logo.png" alt="Logo" height="200">
  <br>
  <h1>🏠 Open Tecnosystemi</h1>
  <p><em>Home Assistant integration for Tecnosystemi Pico and Polaris 5X devices</em></p>
  <br>
  <a href="https://github.com/VoidElle/open-pico-local-api"><img src="https://img.shields.io/badge/open--pico--local--api-v2.7.0-blue?style=flat-square&logo=github" alt="open-pico-local-api"></a>
  <a href="https://github.com/VoidElle/open-polaris-local-api"><img src="https://img.shields.io/badge/open--polaris--local--api-v2.0.1-blue?style=flat-square&logo=github" alt="open-polaris-local-api"></a>
  <a href="https://github.com/VoidElle/hass-open-tecnosystemi/releases"><img src="https://img.shields.io/github/v/release/VoidElle/hass-open-tecnosystemi?style=flat-square&label=version" alt="version"></a>
  <a href="https://github.com/VoidElle/hass-open-tecnosystemi/blob/master/LICENSE"><img src="https://img.shields.io/github/license/VoidElle/hass-open-tecnosystemi?style=flat-square" alt="license"></a>
  <br>
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Default-41BDF5?style=flat-square&logo=home-assistant-community-store" alt="HACS"></a>
  <a href="https://www.home-assistant.io/"><img src="https://img.shields.io/badge/Home%20Assistant-%E2%89%A52026.11-41BDF5?style=flat-square&logo=home-assistant" alt="Home Assistant"></a>
  <a href="https://github.com/VoidElle/hass-open-tecnosystemi/stargazers"><img src="https://img.shields.io/github/stars/VoidElle/hass-open-tecnosystemi?style=flat-square" alt="stars"></a>
  <a href="https://github.com/VoidElle/hass-open-tecnosystemi/commits"><img src="https://img.shields.io/github/last-commit/VoidElle/hass-open-tecnosystemi?style=flat-square" alt="last commit"></a>
  <a href="https://github.com/VoidElle/hass-open-tecnosystemi/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow/status/VoidElle/hass-open-tecnosystemi/tests.yml?style=flat-square&label=tests" alt="tests"></a>
</div>

> **Disclaimer:** this is an unofficial, community-developed project. It is not affiliated with, endorsed by, or supported by Tecnosystemi S.p.A. All product names and trademarks are the property of their respective owners.

Open Tecnosystemi is a Home Assistant integration that enables management of Tecnosystemi devices through Home Assistant.

**Supported device families:**
- **Pico** - Local UDP-based ventilation and air quality units
- **Polaris 5X** - Local TCP-based HVAC zone controllers

Both device families communicate **over your local network**. Both can also be set up through the Tecnosystemi cloud instead, for units Home Assistant cannot reach on the LAN.

## Installation 📦
### Via HACS (Recommended) ⭐
Open Tecnosystemi is available in the **HACS Default** repository - no custom repository needed.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=VoidElle&repository=hass-open-tecnosystemi&category=integration)

1. Open HACS in your Home Assistant interface
2. Go to "Integrations" tab
3. Click **+ Explore & Download Repositories**
4. Search for "Open Tecnosystemi"
5. Click on the integration and then Download
6. Select the latest version and click Download
7. Restart Home Assistant 🔄

### Manual Installation 🔧
1. Copy the `custom_components/open_pico/` folder from this repository into your Home Assistant `custom_components` directory (the folder must stay named `open_pico`)
2. Restart Home Assistant

## Add the Integration to Home Assistant 🧩

After installing (via HACS or manually) and restarting Home Assistant:

1. Go to **Settings -> Devices & Services**
2. Click **+ Add Integration**
3. Search for **"Open Tecnosystemi"**
4. Select it from the list
5. Choose the device family: **Pico** or **Polaris**
6. Choose the setup method: **Manual**, **Scan** or **Cloud**

## Configuration ⚙️

All configuration is done through the Home Assistant UI - no `configuration.yaml` editing required.

### Auto-scan

Instead of entering the IP manually, both Pico and Polaris support network scanning:

1. Select **Scan** as the setup method
2. Enter your subnet (e.g. `192.168.1.0/24`) and PIN
3. The integration will probe the network and list discovered devices
4. Select a device and give it a name

Already-configured devices are automatically excluded from scan results.

### Cloud connection

Use **Cloud** only when the Pico or the Polaris CU is not reachable on your local network. The connection type is chosen once, at setup: an entry set up locally never switches to the cloud, and a cloud entry never uses the LAN.

1. Select **Cloud** as the setup method
2. Enter your Tecnosystemi account email and password
3. Pick the device, then enter its PIN and a name

Notes: state is polled every 30 seconds and the refresh after a command waits 3 seconds, because the vendor backend applies commands with a delay. Both values can be set in the device step and changed later with **Configure** (raise the command delay if the state flips back after a command). The account credentials are stored in the config entry. Polaris CUs with firmware older than 4.x can take up to 10 minutes to apply a cloud command.

The Tecnosystemi backend allows only one session per account at a time. While the integration is running, the official app shows an alert and stops working. To change something from the app, disable the integration first and enable it again afterwards.

### Changing settings after setup

| Setting | Where | Entries |
|---|---|---|
| Polling interval (5–300 s) | **Configure** | all |
| Command delay (0–30 s) | **Configure** | cloud only |
| PIN | **Reconfigure** (entry menu ⋮) | all |
| IP address | **Reconfigure** | local only |
| Cloud email and password | **Reconfigure** | cloud only |
| Name | not changeable: remove the entry and add it again | all |

Default polling intervals: local Pico 5 seconds, local Polaris 60 seconds, cloud 30 seconds. **Configure** reloads the entry to apply the change. **Reconfigure** tests the new values against the device and keeps the old ones if the test fails.

## Features ✨

### Pico
- 🌐 **Local UDP Communication**: Direct device control without cloud dependency
- 📊 **Real-time Monitoring**: Temperature, humidity, CO2, TVOC sensors
- 🎛️ **Full Control**: Operating modes, fan speed, night mode, LED control, target humidity
- 🧹 **Filter Maintenance**: Maintenance alert binary sensor and reset button
- ☁️ **Cloud Connection**: Optional, for units not reachable on the LAN

#### Mode-dependent controls
Like the official app, some Pico controls only work in certain operating modes:
- **Fan speed** and **Night mode**: Heat Recovery, Extraction, Immission, Comfort Summer, Comfort Winter. In the other modes, and while night mode is on, the fan entity shows only on/off.
- **Target humidity**: Humidity Recovery, Humidity Extraction, Humidity/CO2 Recovery, Humidity/CO2 Extraction. In the other modes the entity is unavailable.

CO2, eCO2 and TVOC read 0 on models without the air quality sensor. They also read 0 on models with the sensor until a mode that turns it on is active. The backend reports both cases the same way, so these entities are always created. Disable them in Home Assistant if you don't need them.

### Polaris 5X
- 🌐 **Local TCP Communication**: Direct device control on port 1235, no cloud or internet required
- 🌡️ **Climate Entities**: Per-zone temperature control
- ❄️ **HVAC Modes**: Heating, Cooling (Raffrescamento, Deumidificazione, Ventilazione)
- 💧 **Zone Sensors**: Temperature and humidity per zone
- 📊 **Operating Mode**: Global CU operating mode sensor
- 🌀 **Damper Control**: Per-zone damper (serranda) position via the zone climate swing mode
- 🚨 **Error Sensors**: CU and per-zone error binary sensors
- ☁️ **Cloud Connection**: Optional, for CUs not reachable on the LAN

### General
- 🔄 **Multi-Device Support**: Control multiple devices of both types simultaneously
- 🏷️ **Device Organization**: Entities are grouped per device for easy management

## Limitations ⚠️
- Pico and Polaris need local network access unless set up with the cloud connection, which depends on the Tecnosystemi backend
- Polaris in cloud mode: no damper (swing) control on MiniDiscovery2X zones, because the cloud does not report their damper setpoint

## Documentation 📖
Per-device setup and entity reference: [Pico](docs/pico.md) · [Polaris 5X](docs/polaris.md) ([index](docs/index.md)).

## Troubleshooting 🔍

### Integration not found after installation
Ensure you have fully restarted Home Assistant after installing the integration. A reload of HACS alone is not sufficient.

### Device scan returns no results
- Verify the subnet you entered matches the one your devices are on (e.g. `192.168.1.0/24`).
- Make sure the device is powered on and reachable from Home Assistant's host.
- Check that no firewall or VLAN rule is blocking UDP (Pico) or TCP port 1235 (Polaris) traffic between Home Assistant and the device.
- Already-configured devices are excluded from scan results. Check **Settings -> Devices & Services** if you expect to see a device that is already set up.

### Entities become unavailable
- Confirm the device IP address hasn't changed. If your router uses DHCP, consider assigning a static/reserved IP to the device.
- Enable debug logging (see [Debugging / Logging](#debugging--logging-) below) and check the Home Assistant logs for connection errors.
- If the address has changed, enter the new one with **Reconfigure**.

### Wrong PIN / authentication failure
- Double-check the PIN in the device's own app or manual.
- Setup and **Reconfigure** test the PIN and show **Wrong PIN** when the device rejects it (cloud entries and local Polaris; a local Pico with a wrong PIN shows a connection error).
- If the PIN of an existing entry changed, update it with **Reconfigure** instead of re-adding the device.

### Polaris CU drops off the network
The Polaris CU has a small network stack. If it goes offline often, or the official app stops seeing it while the integration runs, raise the polling interval with **Configure** (for example to 120 seconds).

### Changes not reflected in Home Assistant
Each entry polls on a fixed interval (see [Changing settings after setup](#changing-settings-after-setup)). If an update seems delayed, you can force a refresh from **Developer Tools → Actions** by calling `homeassistant.update_entity` on the affected entity.

## Debugging / Logging 🪵

To enable verbose logging, add the following to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.open_pico: debug
    open_pico_local_api: debug
    open_polaris_local_api: debug
```

| Logger | Covers |
|---|---|
| `custom_components.open_pico` | Entire integration (coordinators, entities, config flow) |
| `open_pico_local_api` | Pico UDP local API library |
| `open_polaris_local_api` | Polaris TCP local API library |

You can also change log levels at runtime without restarting HA via **Developer Tools → Actions** and calling the `logger.set_level` action.

## Tested On 🧪
- PICO PRO PLUS 30 **(ACD100052)**
- PICO PRO PLUS 60 **(ACD100054)**
- Polaris 5X

*Most features should work on all Pico and Polaris models*

## Contributing 🤝

Contributions are welcome! 

### How to Help
- 🐛 **Report bugs** via [GitHub Issues](https://github.com/VoidElle/hass-open-tecnosystemi/issues)
- 🌍 **Translate** to more languages
- 🔧 **Submit PRs** for improvements via [GitHub Pull requests](https://github.com/VoidElle/hass-open-tecnosystemi/pulls)
- 📖 **Improve documentation**

### Development
1. Fork and clone the repository
2. Create a feature branch: `git checkout -b feature/name`
3. Follow [Home Assistant dev guidelines](https://developers.home-assistant.io/)
4. Submit a PR with clear description

### Scripts

Helper scripts live in the `scripts/` folder.

#### `scripts/bump_version.sh`

Bumps the integration version in `manifest.json`.

```bash
# Interactive menu
./scripts/bump_version.sh

# Auto-increment
./scripts/bump_version.sh patch   # X.Y.Z -> X.Y.(Z+1)
./scripts/bump_version.sh minor   # X.Y.Z -> X.(Y+1).0
./scripts/bump_version.sh major   # X.Y.Z -> (X+1).0.0

# Explicit version
./scripts/bump_version.sh X.Y.Z
```

After bumping, commit and tag:
```bash
git add custom_components/open_pico/manifest.json
git commit -m "chore: bump version to vX.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```
