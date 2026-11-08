"""Config flow for Open Pico / Open Polaris integration."""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CLOUD_COMMAND_DELAY, CLOUD_SCAN_INTERVAL, DOMAIN, POLARIS_SCAN_INTERVAL, entry_command_delay, entry_scan_interval

_LOGGER = logging.getLogger(__name__)


# ─── Connection checks (shared by setup and reconfigure) ─────────────
# Each returns an errors["base"] key, or None when the device answered.

async def _check_pico_local(ip: str, pin: str, device_id: str) -> str | None:
    from open_pico_local_api import PicoClient  # noqa: PLC0415

    client = None
    try:
        # Goes through the shared UDP transport, so it is safe while entries are running.
        client = PicoClient(ip=ip, pin=pin, device_id=device_id, timeout=10)
        await asyncio.wait_for(client.connect(), timeout=15)
        await asyncio.wait_for(client.get_status(), timeout=15)
    except asyncio.TimeoutError:
        return "timeout"
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Pico validation failed for %s: %s", ip, err)
        return "cannot_connect"
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass
    return None


async def _check_pico_cloud(
    email: str, password: str, serial: str, pin: str, name: str, android_id: str,
) -> str | None:
    from open_pico_local_api import PicoDeviceError  # noqa: PLC0415
    from open_pico_local_api.cloud import PicoAuthError, PicoCloudClient  # noqa: PLC0415

    client = None
    try:
        client = PicoCloudClient(
            email, password, serial=serial, pin=pin, name=name, device_id=android_id,
        )
        await asyncio.wait_for(client.connect(), timeout=30)
        await asyncio.wait_for(client.get_status(), timeout=30)
    except PicoAuthError:
        return "invalid_auth"
    except PicoDeviceError as err:
        _LOGGER.debug("Pico cloud validation failed for %s: %s", serial, err)
        return "invalid_pin" if "Wrong PIN" in str(err) else "cannot_connect"
    except asyncio.TimeoutError:
        return "timeout"
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Pico cloud validation failed for %s: %s", serial, err)
        return "cannot_connect"
    finally:
        if client is not None:
            await client.disconnect()
    return None


async def _check_polaris_local(ip: str, pin: str) -> str | None:
    from open_polaris_local_api import PolarisApiError, PolarisLocalClient  # noqa: PLC0415

    try:
        client = PolarisLocalClient(ip=ip, pin=pin, timeout=10)
        await asyncio.wait_for(client.connect(), timeout=15)
        await client.close()
    except asyncio.TimeoutError:
        return "timeout"
    except PolarisApiError as err:
        # The CU answered but rejected stato (res != 1): the PIN is its only input.
        _LOGGER.debug("Polaris validation rejected for %s: %s", ip, err)
        return "invalid_pin"
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Polaris validation failed for %s: %s", ip, err)
        return "cannot_connect"
    return None


async def _check_polaris_cloud(
    email: str, password: str, serial: str, pin: str, name: str, android_id: str,
) -> str | None:
    from open_polaris_local_api import PolarisApiError  # noqa: PLC0415
    from open_polaris_local_api.cloud import PolarisAuthError, PolarisCloudClient  # noqa: PLC0415

    client = None
    try:
        client = PolarisCloudClient(
            email, password, serial=serial, pin=pin, name=name, android_id=android_id,
        )
        # connect() logs in and reads GetCUState: a wrong PIN fails here
        await asyncio.wait_for(client.connect(), timeout=30)
    except PolarisAuthError:
        return "invalid_auth"
    except PolarisApiError as err:
        _LOGGER.debug("Polaris cloud validation failed for %s: %s", serial, err)
        return "invalid_pin" if "Wrong PIN" in str(err) else "cannot_connect"
    except asyncio.TimeoutError:
        return "timeout"
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Polaris cloud validation failed for %s: %s", serial, err)
        return "cannot_connect"
    finally:
        if client is not None:
            await client.disconnect()
    return None


async def _check_entry_data(data: dict[str, Any]) -> str | None:
    """Check the connection described by a stored config entry's data."""
    polaris = data.get("device_type", "pico") == "polaris"
    if data.get("connection", "local") == "cloud":
        check = _check_polaris_cloud if polaris else _check_pico_cloud
        return await check(
            data["email"], data["password"], data["serial"],
            data["pin"], data["name"], data["android_id"],
        )
    if polaris:
        return await _check_polaris_local(data["ip"], data["pin"])
    name_slug = re.sub(r"[^a-z0-9]+", "_", data["name"].lower()).strip("_")
    return await _check_pico_local(data["ip"], data["pin"], f"pico_{name_slug}_cfgflow")


class OpenPicoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Open Pico / Open Polaris."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OpenPicoOptionsFlow()

    def __init__(self) -> None:
        self._device_type: str | None = None
        self._scan_pin: str | None = None
        self._discovered_ips: list[str] = []
        self._selected_ip: str | None = None
        self._cloud_email: str = ""
        self._cloud_password: str = ""
        self._cloud_devices: list[dict] = []

    # ─── Step 1: pick device family ──────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Entry point - choose Pico or Polaris."""
        if user_input is not None:
            self._device_type = user_input["device_type"]
            if self._device_type == "pico":
                return await self.async_step_pico()
            return await self.async_step_polaris()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("device_type"): SelectSelector(
                    SelectSelectorConfig(
                        options=["pico", "polaris"],
                        translation_key="device_type",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    # ─── Pico: method selection ───────────────────────────────────────

    async def async_step_pico(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose Pico setup method: manual, auto-scan or cloud."""
        if user_input is not None:
            if user_input["method"] == "manual":
                return await self.async_step_pico_manual()
            if user_input["method"] == "cloud":
                return await self.async_step_pico_cloud()
            return await self.async_step_pico_scan()

        return self.async_show_form(
            step_id="pico",
            data_schema=vol.Schema({
                vol.Required("method"): SelectSelector(
                    SelectSelectorConfig(
                        options=["manual", "scan", "cloud"],
                        translation_key="setup_method",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    # ─── Pico: manual entry ───────────────────────────────────────────

    async def async_step_pico_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual Pico setup form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ip = user_input["ip"].strip()
            pin = user_input["pin"].strip()
            name = user_input["name"].strip()
            name_slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

            await self.async_set_unique_id(f"pico_{name_slug}")
            self._abort_if_unique_id_configured()

            if self._ip_in_use(ip):
                errors["base"] = "ip_already_configured"
            elif error := await _check_pico_local(ip, pin, f"pico_{name_slug}_cfgflow"):
                errors["base"] = error

            if not errors:
                return self.async_create_entry(
                    title=name,
                    data={
                        "device_type": "pico",
                        "ip": ip,
                        "pin": pin,
                        "name": name,
                        "local_port": 40069,
                        "verbose": True,
                    },
                )

        return self.async_show_form(
            step_id="pico_manual",
            data_schema=vol.Schema({
                vol.Required("ip"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Required("pin"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required("name"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
            }),
            errors=errors,
        )

    # ─── Pico: cloud ──────────────────────────────────────────────────

    async def async_step_pico_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cloud account login: list the Picos of the account."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input["email"].strip()
            password = user_input["password"]

            devices: list[dict] = []
            client = None
            try:
                from open_pico_local_api.cloud import (  # noqa: PLC0415
                    PicoAuthError,
                    PicoCloudClient,
                )
                client = PicoCloudClient(email, password, timeout=15)
                await asyncio.wait_for(client.connect(), timeout=30)
                devices = await asyncio.wait_for(client.get_devices(), timeout=30)
            except PicoAuthError:
                errors["base"] = "invalid_auth"
            except asyncio.TimeoutError:
                errors["base"] = "timeout"
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Pico cloud login failed: %s", err)
                errors["base"] = "cannot_connect"
            finally:
                if client is not None:
                    await client.disconnect()

            if not errors:
                used = {
                    str(e.data.get("serial", "")).upper()
                    for e in self._async_current_entries()
                }
                self._cloud_devices = [
                    d for d in devices
                    if d.get("LVDV_Type") == 1 and str(d["Serial"]).upper() not in used
                ]
                if not self._cloud_devices:
                    errors["base"] = "no_cloud_devices"
                else:
                    self._cloud_email = email
                    self._cloud_password = password
                    return await self.async_step_pico_cloud_device()

        return self.async_show_form(
            step_id="pico_cloud",
            data_schema=vol.Schema({
                vol.Required("email"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL)
                ),
                vol.Required("password"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }),
            errors=errors,
        )

    async def async_step_pico_cloud_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the cloud Pico and enter its PIN and name."""
        errors: dict[str, str] = {}

        if user_input is not None:
            serial = user_input["serial"].strip().upper()
            pin = user_input["pin"].strip()
            name = user_input["name"].strip()
            name_slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            android_id = uuid.uuid4().hex[:16]
            scan_interval = int(user_input.get("scan_interval", CLOUD_SCAN_INTERVAL))
            command_delay = int(user_input.get("command_delay", CLOUD_COMMAND_DELAY))

            await self.async_set_unique_id(f"pico_{name_slug}")
            self._abort_if_unique_id_configured()

            if error := await _check_pico_cloud(
                self._cloud_email, self._cloud_password, serial, pin, name, android_id,
            ):
                errors["base"] = error

            if not errors:
                return self.async_create_entry(
                    title=name,
                    data={
                        "device_type": "pico",
                        "connection": "cloud",
                        "email": self._cloud_email,
                        "password": self._cloud_password,
                        "serial": serial,
                        "pin": pin,
                        "name": name,
                        "android_id": android_id,
                        "scan_interval": scan_interval,
                        "command_delay": command_delay,
                        "verbose": True,
                    },
                )

        return self.async_show_form(
            step_id="pico_cloud_device",
            data_schema=vol.Schema({
                vol.Required("serial"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {
                                "value": d["Serial"],
                                "label": f'{d["Name"]} ({d["PlantName"]})',
                            }
                            for d in self._cloud_devices
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required("pin"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required("name"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Optional("scan_interval", default=CLOUD_SCAN_INTERVAL): NumberSelector(
                    NumberSelectorConfig(min=10, max=300, step=5, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional("command_delay", default=CLOUD_COMMAND_DELAY): NumberSelector(
                    NumberSelectorConfig(min=0, max=30, step=1, mode=NumberSelectorMode.BOX)
                ),
            }),
            errors=errors,
        )

    # - Pico: auto-scan

    async def async_step_pico_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pico scan parameters form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            pin = user_input["pin"].strip()
            subnet = user_input["subnet"].strip()
            self._scan_pin = pin

            try:
                from open_pico_local_api import PicoAutoDiscovery  # noqa: PLC0415
                ips: list[str] = await PicoAutoDiscovery.discover(
                    pin=pin,
                    subnet=subnet,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Pico discovery failed on subnet %s: %s", subnet, err)
                errors["base"] = "discovery_failed"
                ips = []

            if not errors:
                configured = {
                    e.data.get("ip")  # cloud entries have no ip
                    for e in self._async_current_entries()
                    if e.data.get("device_type") == "pico"
                }
                self._discovered_ips = [ip for ip in ips if ip not in configured]

                if not self._discovered_ips:
                    errors["base"] = "no_devices_found"
                else:
                    return await self.async_step_pico_scan_results()

        return self.async_show_form(
            step_id="pico_scan",
            data_schema=vol.Schema({
                vol.Required("pin"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required("subnet", default="192.168.1.0/24"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
            }),
            errors=errors,
        )

    async def async_step_pico_scan_results(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show discovered Pico IPs; user picks one."""
        if user_input is not None:
            self._selected_ip = user_input["ip"]
            return await self.async_step_pico_scan_confirm()

        return self.async_show_form(
            step_id="pico_scan_results",
            data_schema=vol.Schema({
                vol.Required("ip"): SelectSelector(
                    SelectSelectorConfig(
                        options=self._discovered_ips,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    async def async_step_pico_scan_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm name for the selected Pico."""
        ip = self._selected_ip
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input["name"].strip()
            name_slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

            if error := await _check_pico_local(ip, self._scan_pin, f"pico_{name_slug}_cfgflow"):
                errors["base"] = error

            if not errors:
                await self.async_set_unique_id(f"pico_{name_slug}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=name,
                    data={
                        "device_type": "pico",
                        "ip": ip,
                        "pin": self._scan_pin,
                        "name": name,
                        "local_port": 40069,
                        "verbose": True,
                    },
                )

        return self.async_show_form(
            step_id="pico_scan_confirm",
            data_schema=vol.Schema({
                vol.Required("name"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
            }),
            description_placeholders={"ip": ip},
            errors=errors,
        )

    # ─── Polaris: method selection ────────────────────────────────────

    async def async_step_polaris(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose Polaris setup method: manual, auto-scan or cloud."""
        if user_input is not None:
            if user_input["method"] == "manual":
                return await self.async_step_polaris_manual()
            if user_input["method"] == "cloud":
                return await self.async_step_polaris_cloud()
            return await self.async_step_polaris_scan()

        return self.async_show_form(
            step_id="polaris",
            data_schema=vol.Schema({
                vol.Required("method"): SelectSelector(
                    SelectSelectorConfig(
                        options=["manual", "scan", "cloud"],
                        translation_key="setup_method",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    # ─── Polaris: manual entry ────────────────────────────────────────

    async def async_step_polaris_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual Polaris setup form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ip = user_input["ip"].strip()
            pin = user_input["pin"].strip()
            name = user_input["name"].strip()
            scan_interval = int(user_input.get("scan_interval", POLARIS_SCAN_INTERVAL))
            name_slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

            await self.async_set_unique_id(f"polaris_{name_slug}")
            self._abort_if_unique_id_configured()

            if self._ip_in_use(ip):
                errors["base"] = "ip_already_configured"
            elif error := await _check_polaris_local(ip, pin):
                errors["base"] = error

            if not errors:
                return self.async_create_entry(
                    title=name,
                    data={
                        "device_type": "polaris",
                        "ip": ip,
                        "pin": pin,
                        "name": name,
                        "scan_interval": scan_interval,
                        "verbose": True,
                    },
                )

        return self.async_show_form(
            step_id="polaris_manual",
            data_schema=vol.Schema({
                vol.Required("ip"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Required("pin"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required("name"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Optional("scan_interval", default=POLARIS_SCAN_INTERVAL): NumberSelector(
                    NumberSelectorConfig(min=10, max=300, step=5, mode=NumberSelectorMode.BOX)
                ),
            }),
            errors=errors,
        )

    # ─── Polaris: cloud ───────────────────────────────────────────────

    async def async_step_polaris_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cloud account login: list the Polaris CUs of the account."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input["email"].strip()
            password = user_input["password"]

            devices: list[dict] = []
            client = None
            try:
                from open_polaris_local_api.cloud import (  # noqa: PLC0415
                    PolarisAuthError,
                    PolarisCloudClient,
                )
                client = PolarisCloudClient(email, password, timeout=15)
                await asyncio.wait_for(client.connect(), timeout=30)
                # get_devices returns Polaris CUs only (LVDV_Type 0)
                devices = await asyncio.wait_for(client.get_devices(), timeout=30)
            except PolarisAuthError:
                errors["base"] = "invalid_auth"
            except asyncio.TimeoutError:
                errors["base"] = "timeout"
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Polaris cloud login failed: %s", err)
                errors["base"] = "cannot_connect"
            finally:
                if client is not None:
                    await client.disconnect()

            if not errors:
                used = {
                    str(e.data.get("serial", "")).upper()
                    for e in self._async_current_entries()
                }
                self._cloud_devices = [
                    d for d in devices if str(d["Serial"]).upper() not in used
                ]
                if not self._cloud_devices:
                    errors["base"] = "no_cloud_devices"
                else:
                    self._cloud_email = email
                    self._cloud_password = password
                    return await self.async_step_polaris_cloud_device()

        return self.async_show_form(
            step_id="polaris_cloud",
            data_schema=vol.Schema({
                vol.Required("email"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL)
                ),
                vol.Required("password"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }),
            errors=errors,
        )

    async def async_step_polaris_cloud_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the cloud Polaris CU and enter its PIN and name."""
        errors: dict[str, str] = {}

        if user_input is not None:
            serial = user_input["serial"].strip().upper()
            pin = user_input["pin"].strip()
            name = user_input["name"].strip()
            name_slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            android_id = uuid.uuid4().hex[:16]
            scan_interval = int(user_input.get("scan_interval", CLOUD_SCAN_INTERVAL))
            command_delay = int(user_input.get("command_delay", CLOUD_COMMAND_DELAY))

            await self.async_set_unique_id(f"polaris_{name_slug}")
            self._abort_if_unique_id_configured()

            if error := await _check_polaris_cloud(
                self._cloud_email, self._cloud_password, serial, pin, name, android_id,
            ):
                errors["base"] = error

            if not errors:
                return self.async_create_entry(
                    title=name,
                    data={
                        "device_type": "polaris",
                        "connection": "cloud",
                        "email": self._cloud_email,
                        "password": self._cloud_password,
                        "serial": serial,
                        "pin": pin,
                        "name": name,
                        "android_id": android_id,
                        "scan_interval": scan_interval,
                        "command_delay": command_delay,
                        "verbose": True,
                    },
                )

        return self.async_show_form(
            step_id="polaris_cloud_device",
            data_schema=vol.Schema({
                vol.Required("serial"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {
                                "value": d["Serial"],
                                "label": f'{d["Name"]} ({d["PlantName"]})',
                            }
                            for d in self._cloud_devices
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required("pin"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required("name"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Optional("scan_interval", default=CLOUD_SCAN_INTERVAL): NumberSelector(
                    NumberSelectorConfig(min=10, max=300, step=5, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional("command_delay", default=CLOUD_COMMAND_DELAY): NumberSelector(
                    NumberSelectorConfig(min=0, max=30, step=1, mode=NumberSelectorMode.BOX)
                ),
            }),
            errors=errors,
        )

    # ─── Polaris: auto-scan ───────────────────────────────────────────

    async def async_step_polaris_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Polaris scan parameters form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            pin = user_input["pin"].strip()
            subnet = user_input["subnet"].strip()
            self._scan_pin = pin

            try:
                from open_polaris_local_api import PolarisAutoDiscovery  # noqa: PLC0415
                ips: list[str] = await PolarisAutoDiscovery.discover(
                    pin=pin,
                    subnet=subnet,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Polaris discovery failed on subnet %s: %s", subnet, err)
                errors["base"] = "discovery_failed"
                ips = []

            if not errors:
                configured = {
                    e.data.get("ip")  # cloud entries have no ip
                    for e in self._async_current_entries()
                    if e.data.get("device_type") == "polaris"
                }
                self._discovered_ips = [ip for ip in ips if ip not in configured]

                if not self._discovered_ips:
                    errors["base"] = "no_devices_found"
                else:
                    return await self.async_step_polaris_scan_results()

        return self.async_show_form(
            step_id="polaris_scan",
            data_schema=vol.Schema({
                vol.Required("pin"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required("subnet", default="192.168.1.0/24"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
            }),
            errors=errors,
        )

    async def async_step_polaris_scan_results(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show discovered Polaris IPs; user picks one."""
        if user_input is not None:
            self._selected_ip = user_input["ip"]
            return await self.async_step_polaris_scan_confirm()

        return self.async_show_form(
            step_id="polaris_scan_results",
            data_schema=vol.Schema({
                vol.Required("ip"): SelectSelector(
                    SelectSelectorConfig(
                        options=self._discovered_ips,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    async def async_step_polaris_scan_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm name and scan_interval for the selected Polaris."""
        ip = self._selected_ip
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input["name"].strip()
            scan_interval = int(user_input.get("scan_interval", POLARIS_SCAN_INTERVAL))
            name_slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

            if error := await _check_polaris_local(ip, self._scan_pin):
                errors["base"] = error

            if not errors:
                await self.async_set_unique_id(f"polaris_{name_slug}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=name,
                    data={
                        "device_type": "polaris",
                        "ip": ip,
                        "pin": self._scan_pin,
                        "name": name,
                        "scan_interval": scan_interval,
                        "verbose": True,
                    },
                )

        return self.async_show_form(
            step_id="polaris_scan_confirm",
            data_schema=vol.Schema({
                vol.Required("name"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Optional("scan_interval", default=POLARIS_SCAN_INTERVAL): NumberSelector(
                    NumberSelectorConfig(min=10, max=300, step=5, mode=NumberSelectorMode.BOX)
                ),
            }),
            description_placeholders={"ip": ip},
            errors=errors,
        )

    def _ip_in_use(self, ip: str, exclude_entry_id: str | None = None) -> bool:
        """True when another local entry already points at this IP (exact text match)."""
        return any(
            other.entry_id != exclude_entry_id
            and other.data.get("connection", "local") == "local"
            and other.data.get("ip") == ip
            for other in self._async_current_entries(include_ignore=False)
        )

    # ─── Reconfigure: PIN and cloud credentials ───────────────────────

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the PIN, plus the IP (local) or the account (cloud), of an existing entry."""
        entry = self._get_reconfigure_entry()
        cloud = entry.data.get("connection", "local") == "cloud"
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {**entry.data, "pin": user_input["pin"].strip()}
            if not cloud:
                data["ip"] = user_input["ip"].strip()
            if cloud:
                data["email"] = user_input["email"].strip()
                data["password"] = user_input["password"]
            if not cloud and self._ip_in_use(data["ip"], exclude_entry_id=entry.entry_id):
                errors["base"] = "ip_already_configured"
            elif error := await _check_entry_data(data):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data=data)

        schema: dict[Any, Any] = {}
        if not cloud:
            schema[vol.Required("ip", default=entry.data["ip"])] = TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            )
        if cloud:
            schema[vol.Required("email", default=entry.data["email"])] = TextSelector(
                TextSelectorConfig(type=TextSelectorType.EMAIL)
            )
            schema[vol.Required("password")] = TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            )
        schema[vol.Required("pin")] = TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=vol.Schema(schema), errors=errors,
        )


class OpenPicoOptionsFlow(OptionsFlow):
    """Change the polling interval of an existing entry."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={key: int(value) for key, value in user_input.items()}
            )

        entry = self.config_entry
        schema: dict[Any, Any] = {
            vol.Required("scan_interval", default=entry_scan_interval(entry)): NumberSelector(
                # min 5: local Pico default; 10-300 are the setup-form bounds
                NumberSelectorConfig(min=5, max=300, step=5, mode=NumberSelectorMode.BOX)
            ),
        }
        if entry.data.get("connection", "local") == "cloud":
            schema[vol.Required("command_delay", default=entry_command_delay(entry))] = NumberSelector(
                NumberSelectorConfig(min=0, max=30, step=1, mode=NumberSelectorMode.BOX)
            )
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
