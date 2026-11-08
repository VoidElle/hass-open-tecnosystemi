# Open Tecnosystemi — Documentation

Home Assistant integration for **Tecnosystemi Pico** (ventilation/air quality) and **Polaris 5X** (HVAC zone controllers).

Both device families communicate **over the local network**. Both also have an optional cloud fallback for units not reachable on the LAN.

---

## Contents

| Page | Description |
|------|-------------|
| [Pico](pico.md) | Pico device setup, entities, and control |
| [Polaris](polaris.md) | Polaris 5X device setup, entities, and control |

---

## Quick Start

### Requirements
- Home Assistant ≥ 2024.1
- Devices on the same local network as Home Assistant

### Installation
Via HACS (recommended): the integration is in the HACS Default repository. Search **Open Tecnosystemi** in HACS, download, restart HA.

Manual: copy `custom_components/open_pico/` into your HA `custom_components/` directory, restart.

### Adding a Device
1. **Settings → Devices & Services → + Add Integration**
2. Search **Open Tecnosystemi**
3. Choose device family: **Pico** or **Polaris**
4. Choose setup method: **Manual** (enter IP/PIN/name), **Scan** (subnet discovery) or **Cloud** (Tecnosystemi account)

---

## Tested Hardware

| Device | Model Number |
|--------|-------------|
| PICO PRO PLUS 30 | ACD100052 |
| PICO PRO PLUS 60 | ACD100054 |
| Polaris 5X | — |
