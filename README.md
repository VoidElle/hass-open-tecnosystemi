<div align="center">
  <img src="./assets/logo.png" alt="Logo" height="200">
  <br>
  <h1>🏠 Open Tecnosystemi</h1>
  <p><em>Home Assistant integration for Tecnosystemi Pico and Polaris 5X devices</em></p>
  <br>
  <a href="https://github.com/VoidElle/open-pico-local-api"><img src="https://img.shields.io/badge/open--pico--local--api-v2.4.0-blue?style=flat-square&logo=github" alt="open-pico-local-api"></a>
  <a href="https://github.com/VoidElle/open-polaris-local-api"><img src="https://img.shields.io/badge/open--polaris--local--api-v1.2.0-blue?style=flat-square&logo=github" alt="open-polaris-local-api"></a>
  <a href="https://github.com/VoidElle/hass-open-tecnosystemi/releases"><img src="https://img.shields.io/github/v/release/VoidElle/hass-open-tecnosystemi?style=flat-square&label=version" alt="version"></a>
  <a href="https://github.com/VoidElle/hass-open-tecnosystemi/blob/master/LICENSE"><img src="https://img.shields.io/github/license/VoidElle/hass-open-tecnosystemi?style=flat-square" alt="license"></a>
  <br>
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange?style=flat-square&logo=home-assistant-community-store" alt="HACS"></a>
  <a href="https://www.home-assistant.io/"><img src="https://img.shields.io/badge/Home%20Assistant-%E2%89%A52024.1-41BDF5?style=flat-square&logo=home-assistant" alt="Home Assistant"></a>
  <a href="https://github.com/VoidElle/hass-open-tecnosystemi/stargazers"><img src="https://img.shields.io/github/stars/VoidElle/hass-open-tecnosystemi?style=flat-square" alt="stars"></a>
  <a href="https://github.com/VoidElle/hass-open-tecnosystemi/commits"><img src="https://img.shields.io/github/last-commit/VoidElle/hass-open-tecnosystemi?style=flat-square" alt="last commit"></a>
  <a href="https://github.com/VoidElle/hass-open-tecnosystemi/actions"><img src="https://img.shields.io/badge/tests-291%20passed-brightgreen?style=flat-square&logo=pytest" alt="tests"></a>
</div>


Open Tecnosystemi is a Home Assistant integration that enables management of Tecnosystemi devices through Home Assistant.

**Supported device families:**
- **Pico** - Local UDP-based ventilation and air quality units
- **Polaris 5X** - Local TCP-based HVAC zone controllers

Both device families communicate **entirely over your local network**, requiring no cloud connectivity.

## Installation 📦
### Via HACS (Recommended) ⭐
[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=VoidElle&repository=hass-open-tecnosystemi&category=integration)

### Via HACS (Manual)
1. Add custom repository:
    - Open HACS in your Home Assistant interface
    - Go to "Integrations" tab
    - Click on the three dots in the top right corner and select "Custom repositories"
    - Enter the repository URL: `https://github.com/VoidElle/hass-open-tecnosystemi`
    - Select "Integration" as the category
    - Click "Add"


2. Install the integration:
   - In HACS Integrations, click + Explore & Download Repositories
   - Search for "Open Tecnosystemi"
   - Click on the integration and then Download
   - Select the latest version and click Download


3. Restart Home Assistant 🔄

### Manual Installation 🔧
1. Copy the repository content inside a folder called `hass_open_tecnosystemi`
2. Move the folder to your `custom_components` directory
3. Restart Home Assistant

## Add the Integration to Home Assistant 🧩

After installing (via HACS or manually) and restarting Home Assistant:

1. Go to **Settings -> Devices & Services**
2. Click **+ Add Integration**
3. Search for **"Open Tecnosystemi"**
4. Select it from the list
5. Choose the device family: **Pico** or **Polaris**
6. Choose the setup method: **Manual** or **Scan**

## Configuration ⚙️

All configuration is done through the Home Assistant UI — no `configuration.yaml` editing required.

### Auto-scan

Instead of entering the IP manually, both Pico and Polaris support network scanning:

1. Select **Scan** as the setup method
2. Enter your subnet (e.g. `192.168.1.0/24`) and PIN
3. The integration will probe the network and list discovered devices
4. Select a device and give it a name

Already-configured devices are automatically excluded from scan results.

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
- 🏷️ **Device Organization**: Entities are grouped per device for easy management
- ⚡ **Concurrent Polling**: Efficient updates across all devices

## Limitations ⚠️
- Both Pico and Polaris require local network access (devices must be on the same network as Home Assistant)

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
./scripts/bump_version.sh patch   # 3.0.0 -> 3.0.1
./scripts/bump_version.sh minor   # 3.0.0 -> 3.1.0
./scripts/bump_version.sh major   # 3.0.0 -> 4.0.0

# Explicit version
./scripts/bump_version.sh 3.2.0
```

After bumping, commit and tag:
```bash
git add manifest.json
git commit -m "chore: bump version to vX.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```