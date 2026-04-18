# AGENTS.md — Hassio Open Pico

Home Assistant custom integration for Tecnosystemi **Pico** (ventilation/air quality) and **Polaris 5** (HVAC zone controllers) devices over local UDP (ports 40069/40070). No cloud dependency.

## Architecture Overview

Two parallel device families share the same integration domain (`open_pico`):

| Family | Coordinator | Client | Platforms |
|---|---|---|---|
| Pico | `coordinator.py` → `MainCoordinator` | `open_pico_local_api/pico_client.py` | FAN, SWITCH, SELECT, SENSOR, BUTTON, BINARY_SENSOR |
| Polaris 5 | `polaris_coordinator.py` → `PolarisCoordinator` | `polaris_api/polaris_client.py` | CLIMATE, SENSOR |

Setup entry point is `async_setup` in `__init__.py`, which reads YAML config and stores coordinators in:
- `hass.data[DOMAIN]["coordinators"]` — list of `MainCoordinator` (Pico)
- `hass.data[DOMAIN]["polaris_coordinators"]` — list of `PolarisCoordinator` (Polaris)

## Key Design Decisions

- **Shared UDP transport for Pico**: all Pico clients share a single UDP socket via `SharedTransportManager` (singleton in `open_pico_local_api/shared_transport_manager.py`). Created by `PicoClientManager` in `pico_manager.py`. Pass `use_shared_transport=True` when creating `PicoClient`.
- **Polaris uses its own socket**: `PolarisLocalClient` manages its own UDP connection (port 40070 → device, `local_port` → listen).
- **Coordinator pattern**: all entity state is read from `coordinator.data` (`PicoDeviceModel` or `PolarisData`). Control actions call client methods then immediately call `await self.async_request_refresh()`.
- **YAML-only config**: no UI config flow exists yet. Schema lives in `__init__.py` (`CONFIG_SCHEMA`). `manifest.json` has `"single_config_entry": false`.
- **Poll interval**: 5 seconds for both families (`DEFAULT_SCAN_INTERVAL` / `POLARIS_SCAN_INTERVAL` in `const.py`).

## Entity Pattern

All Pico entities inherit `BaseEntity` (`base.py`) which extends `CoordinatorEntity`. Each entity receives a `coordinator` and a `device_index`. The `available` property gates all state reads:

```python
@property
def available(self) -> bool:
    return self.coordinator.last_update_success and self.coordinator.data is not None
```

Polaris entities follow the same pattern but use `PolarisCoordinator` and access `coordinator.data.device` / `coordinator.data.zones` (a `PolarisData` dataclass).

## Adding a New Platform

1. Create `<platform>.py` at root, import the relevant coordinator from `hass.data[DOMAIN]`.
2. For Pico: iterate `hass.data[DOMAIN]["coordinators"]`; for Polaris: `hass.data[DOMAIN]["polaris_coordinators"]`.
3. Add the platform to `PICO_PLATFORMS` or `POLARIS_PLATFORMS` in `__init__.py`.
4. Add translation keys to `translations/en.json` and `translations/it.json`.

## Key Files

- `__init__.py` — integration setup, YAML schema, device family bootstrapping
- `const.py` — `DOMAIN`, scan intervals, `MODE_INT_TO_PRESET` map, `POLARIS_COOLING_MODES`
- `coordinator.py` / `polaris_coordinator.py` — all control methods call client then `async_request_refresh()`
- `pico_manager.py` — shared UDP transport lifecycle for Pico
- `open_pico_local_api/pico_client.py` — low-level Pico UDP protocol
- `polaris_api/polaris_client.py` — low-level Polaris UDP protocol
- `open_pico_local_api/models/` — `PicoDeviceModel`, `SensorReadingsModel`, `OperatingParametersModel`
- `polaris_api/models.py` — `PolarisDevice`, `PolarisZone`

## Development & Testing

No automated test suite exists. To test manually:

1. Install into HA `custom_components/hassio_open_pico/` (folder name matters).
2. Add config to `configuration.yaml` under key `open_pico:`.
3. Restart HA; check logs with `verbose: true` for debug output.
4. Validate YAML before restart: **Developer Tools → YAML → Check Configuration**.

The integration is loaded via `async_setup` (YAML-based), not `async_setup_entry` — UI "Add Integration" step is required to register the domain but performs no configuration.

