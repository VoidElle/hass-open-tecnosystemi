"""REST API client for Tecnosystemi Polaris 5 (ProAir cloud service).

Ported from the original Android app and Flutter reimplementation.
Communicates with https://proair.azurewebsites.net/api/v1/
"""
from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

from .models import PolarisDevice, PolarisZone
from .token_manager import TokenManager

_LOGGER = logging.getLogger(__name__)

_BASE_URL = "https://proair.azurewebsites.net"
_API_KEY_PASSWORD = "PwdProAir"
_API_KEY_FALLBACK_EMAIL = "UsrProAir"
_USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 14; HomeAssistant)"
_USER_OBJ_AGENT = "benincapp"


class PolarisClient:
    """Async client for the Polaris 5 ProAir REST API."""

    def __init__(
        self,
        serial: str,
        pin: str,
        email: str | None = None,
        password: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the Polaris client.

        Args:
            serial: CU serial number (e.g. "414705189652"). Can be empty for discovery.
            pin: CU PIN (e.g. "0000")
            email: User email for authentication.
            password: User password (will be AES-encrypted for login).
            session: Optional shared aiohttp session.
        """
        self.serial = serial
        self.pin = pin
        self._email = email or _API_KEY_FALLBACK_EMAIL
        self._password = password
        self._owns_session = session is None
        self._session = session
        self._token_manager = TokenManager()
        self._logged_in = False

        # Cached state
        self._device: PolarisDevice | None = None
        self._zones: list[PolarisZone] = []

    @property
    def device(self) -> PolarisDevice | None:
        """Last known device state."""
        return self._device

    @property
    def zones(self) -> list[PolarisZone]:
        """Last known zones."""
        return self._zones

    # ─── Session management ──────────────────────────────────────────

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Close the HTTP session if we own it."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    # ─── Auth helpers ────────────────────────────────────────────────

    def _build_authorization(self, use_fallback: bool = False) -> str:
        """Build Basic auth header matching the original app.

        Before login: uses fallback credentials (UsrProAir:PwdProAir)
        After login: uses user email (email:PwdProAir)
        """
        import base64
        if use_fallback or not self._logged_in:
            username = _API_KEY_FALLBACK_EMAIL
        else:
            username = self._email
        credentials = f"{username}:{_API_KEY_PASSWORD}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
        return f"Basic {encoded}"

    def _build_headers(self, use_fallback_auth: bool = False) -> dict[str, str]:
        """Build request headers matching the original Android app."""
        token = self._token_manager.retrieve_new_token()
        return {
            "Accept-Encoding": "gzip",
            "Connection": "Keep-Alive",
            "Host": "proair.azurewebsites.net",
            "User-Agent": _USER_AGENT,
            "UserObj-Agent": _USER_OBJ_AGENT,
            "Token": token or "",
            "Authorization": self._build_authorization(use_fallback=use_fallback_auth),
        }

    # ─── Low-level request helpers ───────────────────────────────────

    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        """Perform an authenticated GET request."""
        session = await self._ensure_session()
        url = f"{_BASE_URL}{path}"
        headers = self._build_headers()

        _LOGGER.debug("GET %s params=%s", path, params)

        async with session.get(url, headers=headers, params=params) as resp:
            data = await resp.json(content_type=None)

            if resp.status == 200:
                # Store token from response if available
                self._update_token_from_response(resp, data)
                return data

            _LOGGER.error("GET %s failed: %d %s", path, resp.status, data)
            raise PolarisApiError(f"GET {path} returned {resp.status}: {data}")

    async def _post(self, path: str, body: dict, params: dict[str, str] | None = None) -> Any:
        """Perform an authenticated POST request."""
        session = await self._ensure_session()
        url = f"{_BASE_URL}{path}"
        headers = {
            **self._build_headers(),
            "Content-Type": "application/json; charset=utf-8",
        }

        _LOGGER.debug("POST %s body=%s", path, body)

        async with session.post(url, headers=headers, json=body, params=params) as resp:
            data = await resp.json(content_type=None)

            if resp.status == 200:
                self._update_token_from_response(resp, data)
                return data

            _LOGGER.error("POST %s failed: %d %s", path, resp.status, data)
            raise PolarisApiError(f"POST {path} returned {resp.status}: {data}")

    def _update_token_from_response(self, resp: aiohttp.ClientResponse, data: Any) -> None:
        """Extract and store token from successful response."""
        # Token comes from the response body or stays rotated
        if isinstance(data, dict) and "Token" in data:
            self._token_manager.current_token = data["Token"]

    # ─── Public API: Login ──────────────────────────────────────────

    async def login(self) -> bool:
        """Authenticate with the ProAir cloud using email + password.

        The login endpoint is /apiTS/v2/Login. The password is sent
        AES-encrypted in the request body. On success, the server returns
        a session Token that is used for all subsequent API calls.

        Returns True on success, False on failure.
        """
        if not self._password:
            _LOGGER.warning("No password provided, skipping login")
            return False

        # Encrypt the password using the same AES as token rotation
        encrypted_password = self._token_manager._encrypt(self._password)

        body = {
            "DeviceId": "c610101212ff9aec",
            "Platform": "fcm2",
            "Password": encrypted_password,
            "TokenPush": "",
            "Username": self._email,
        }

        # Login uses fallback auth (UsrProAir:PwdProAir)
        session = await self._ensure_session()
        url = f"{_BASE_URL}/apiTS/v2/Login"
        headers = {
            **self._build_headers(use_fallback_auth=True),
            "Content-Type": "application/json; charset=utf-8",
        }

        _LOGGER.debug("Logging in as %s", self._email)

        async with session.post(url, headers=headers, json=body) as resp:
            data = await resp.json(content_type=None)

            if resp.status == 200 and isinstance(data, dict):
                res_code = data.get("ResCode", -1)
                if res_code == 0 or data.get("Token"):
                    # Store the session token
                    token = data.get("Token", "")
                    if token:
                        self._token_manager.current_token = token
                    self._logged_in = True
                    _LOGGER.info("Login successful for %s (user_id=%s)", self._email, data.get("ID"))
                    return True
                else:
                    _LOGGER.error("Login failed: ResCode=%s, response=%s", res_code, data)
                    return False

            _LOGGER.error("Login request failed: %d %s", resp.status, data)
            return False

    # ─── Public API: Discovery ──────────────────────────────────────

    async def get_plants(self) -> list[dict]:
        """Fetch all plants/devices for the authenticated user.

        Calls /api/v1/GetPlants (no serial needed, uses email from auth).
        Returns a list of device dicts, each with 'Serial', 'Name',
        'LVDV_Type' (1=PICO, other=Polaris), 'FWVer', etc.
        """
        data = await self._get("/api/v1/GetPlants")

        # GetPlants returns ResCode/ResDescr wrapper
        devices: list[dict] = []
        if isinstance(data, dict):
            res_descr = data.get("ResDescr", "")
            if isinstance(res_descr, str):
                plants = json.loads(res_descr)
            elif isinstance(res_descr, list):
                plants = res_descr
            else:
                plants = []

            if isinstance(plants, list):
                for plant in plants:
                    if isinstance(plant, dict):
                        plant_devices = plant.get("ListDevices", [])
                        if isinstance(plant_devices, list):
                            devices.extend(plant_devices)
        elif isinstance(data, list):
            for plant in data:
                if isinstance(plant, dict):
                    plant_devices = plant.get("ListDevices", [])
                    if isinstance(plant_devices, list):
                        devices.extend(plant_devices)

        _LOGGER.debug("GetPlants returned %d devices", len(devices))
        return devices

    @classmethod
    async def discover_polaris_devices(
        cls,
        email: str,
        password: str,
        pin: str | None = None,
    ) -> list[dict]:
        """Discover all Polaris (non-PICO) devices for an email.

        Performs login with email+password, then calls GetPlants to
        discover all devices associated with the account.

        Args:
            email: User email for authentication.
            password: User password.
            pin: Optional PIN (not needed for discovery, only for control).

        Returns:
            List of device dicts with keys: Serial, Name, LVDV_Type, FWVer, etc.
            Only returns non-PICO devices (LVDV_Type != 1).
        """
        # Create a temporary client for login + discovery
        client = cls(serial="", pin=pin or "0000", email=email, password=password)
        try:
            # Step 1: Login
            logged_in = await client.login()
            if not logged_in:
                raise PolarisApiError(f"Login failed for {email}")

            # Step 2: Get all plants/devices
            all_devices = await client.get_plants()

            # Filter: LVDV_Type 1 = PICO, everything else = Polaris/ProAir
            polaris = [d for d in all_devices if d.get("LVDV_Type") != 1]
            _LOGGER.info(
                "Discovered %d Polaris devices (out of %d total) for %s",
                len(polaris), len(all_devices), email,
            )
            return polaris
        finally:
            await client.close()

    # ─── Public API: Read operations ─────────────────────────────────

    async def get_home(self) -> PolarisDevice:
        """Fetch device info from GetHome endpoint.

        Returns basic CU info: name, serial, firmware, on/off, cooling mode, etc.
        """
        params = {"cuSerial": self.serial, "PIN": self.pin}
        data = await self._get("/api/v1/GetHome", params=params)

        # GetHome returns a JSON array with one element
        if isinstance(data, list) and data:
            cu_data = data[0]
        elif isinstance(data, dict):
            if "ResCode" in data and "ResDescr" in data:
                res_descr = data["ResDescr"]
                if isinstance(res_descr, str):
                    parsed = json.loads(res_descr)
                    cu_data = parsed[0] if isinstance(parsed, list) else parsed
                else:
                    cu_data = res_descr
            else:
                cu_data = data
        else:
            raise PolarisApiError(f"Unexpected GetHome response: {data}")

        self._device = PolarisDevice.from_get_home(cu_data)
        return self._device

    async def get_cu_state(self) -> list[PolarisZone]:
        """Fetch zone data from GetCUState endpoint.

        Returns detailed zone info: temperature, setpoint, on/off, modes, etc.
        """
        params = {"cuSerial": self.serial, "PIN": self.pin}
        data = await self._get("/api/v1/GetCUState", params=params)

        # GetCUState may return:
        # 1. Direct JSON object with "Zones" array
        # 2. ResCode/ResDescr wrapper
        # 3. JSON array
        cu_data = None
        if isinstance(data, dict):
            if "ResCode" in data and "ResDescr" in data:
                res_descr = data["ResDescr"]
                if isinstance(res_descr, str):
                    decoded = json.loads(res_descr)
                    cu_data = decoded[0] if isinstance(decoded, list) else decoded
                elif isinstance(res_descr, dict):
                    cu_data = res_descr
            else:
                cu_data = data
        elif isinstance(data, list) and data:
            cu_data = data[0]

        if not cu_data or "Zones" not in cu_data:
            _LOGGER.warning("No Zones in GetCUState response: %s", cu_data)
            self._zones = []
            return self._zones

        zones_data = cu_data["Zones"]
        self._zones = [PolarisZone.from_api(z) for z in zones_data if isinstance(z, dict)]

        _LOGGER.debug("Parsed %d zones from GetCUState", len(self._zones))
        return self._zones

    async def async_update(self) -> tuple[PolarisDevice, list[PolarisZone]]:
        """Full refresh: fetch both device info and zone data.

        Automatically performs login on first call if password is available.
        """
        if not self._logged_in and self._password:
            await self.login()

        device = await self.get_home()
        zones = await self.get_cu_state()
        return device, zones

    # ─── Public API: Write operations (zone) ─────────────────────────

    async def update_zone(
        self,
        zone: PolarisZone,
        *,
        is_off: bool | None = None,
        set_temp: float | None = None,
        is_crono: bool | None = None,
        fancoil_set: int | None = None,
        serranda_set: int | None = None,
    ) -> None:
        """Update a zone's settings.

        Sends to /api/v1/UpdateZonaData using the command format expected
        by the C# backend: snake_case keys, ints for booleans.

        Args:
            zone: The zone to update
            is_off: Turn zone on (False) or off (True)
            set_temp: Target temperature in °C (will be multiplied by 10)
            is_crono: Enable chrono mode
            fancoil_set: Fancoil speed setting
            serranda_set: Shutter/damper setting
        """
        effective_is_off = is_off if is_off is not None else zone.is_off
        effective_temp = set_temp if set_temp is not None else (zone.set_temp or 20.0)
        effective_crono = is_crono if is_crono is not None else zone.is_crono_mode
        set_temp_int = round(effective_temp * 10)

        # Build command JSON (snake_case format matching original Android app)
        cmd_data: dict[str, Any] = {
            "c": "upd_zona",
            "id_zona": zone.zone_id,
            "name": zone.name,
            "is_off": 1 if effective_is_off else 0,
            "t_set": str(set_temp_int),
            "is_crono": 1 if effective_crono else 0,
        }

        # Add fan_set / shu_set if available
        eff_fancoil = fancoil_set if fancoil_set is not None else zone.fancoil_set
        eff_serranda = serranda_set if serranda_set is not None else zone.serranda_set

        if eff_fancoil is not None and eff_fancoil != -1:
            fan_val = 16 if eff_fancoil == 7 else eff_fancoil
            cmd_data["fan_set"] = fan_val
            cmd_data["shu_set"] = fan_val
        elif eff_serranda is not None and eff_serranda != -1:
            shu_val = 16 if eff_serranda == 7 else eff_serranda
            cmd_data["shu_set"] = shu_val
            cmd_data["fan_set"] = shu_val

        cmd_data["pin"] = self.pin

        body = {
            "Cmd": json.dumps(cmd_data),
            "Name": self._device.name if self._device else "",
            "Pin": self.pin,
            "Serial": self.serial,
            "ZoneId": zone.zone_id,
        }

        params = {"cuSerial": self.serial, "PIN": self.pin}
        await self._post("/api/v1/UpdateZonaData", body=body, params=params)

        _LOGGER.info("Zone '%s' updated: is_off=%s, temp=%.1f°C", zone.name, effective_is_off, effective_temp)

    # ─── Public API: Write operations (CU / device) ──────────────────

    async def update_cu(
        self,
        *,
        is_off: bool | None = None,
        is_cooling: bool | None = None,
        operating_mode: int | None = None,
    ) -> None:
        """Update CU (device-level) settings.

        Sends to /api/v1/UpdateCUData using the command format expected
        by the C# backend.

        Args:
            is_off: Turn device on (False) or off (True)
            is_cooling: Enable cooling mode
            operating_mode: 0=heating, 1=raffrescamento, 2=deumidificazione, 3=ventilazione
        """
        dev = self._device
        eff_is_off = is_off if is_off is not None else (dev.is_off if dev else False)
        eff_is_cooling = is_cooling if is_cooling is not None else (dev.is_cooling if dev else False)
        eff_op_mode = operating_mode if operating_mode is not None else (dev.operating_mode if dev else 0)

        cmd_data = {
            "c": "upd_cu",
            "pin": self.pin,
            "is_off": 1 if eff_is_off else 0,
            "is_cool": 1 if eff_is_cooling else 0,
            "cool_mod": eff_op_mode,
            "t_can": 0,
            "f_inv": dev.f_inv if dev else 0,
            "f_est": dev.f_est if dev else 0,
        }

        body = {
            "Cmd": json.dumps(cmd_data),
            "Name": dev.name if dev else "",
            "Pin": self.pin,
            "Serial": self.serial,
        }

        params = {"cuSerial": self.serial, "PIN": self.pin}
        await self._post("/api/v1/UpdateCUData", body=body, params=params)

        _LOGGER.info(
            "CU '%s' updated: is_off=%s, cooling=%s, mode=%d",
            dev.name if dev else self.serial, eff_is_off, eff_is_cooling, eff_op_mode,
        )

    # Convenience methods

    async def turn_on(self) -> None:
        """Turn the device on."""
        await self.update_cu(is_off=False)

    async def turn_off(self) -> None:
        """Turn the device off."""
        await self.update_cu(is_off=True)

    async def set_cooling_mode(self, mode: int) -> None:
        """Set cooling operating mode (1=raff, 2=deum, 3=vent)."""
        await self.update_cu(is_off=False, is_cooling=True, operating_mode=mode)

    async def set_heating_mode(self) -> None:
        """Switch to heating mode."""
        await self.update_cu(is_off=False, is_cooling=False, operating_mode=0)

    async def set_zone_temp(self, zone: PolarisZone, temperature: float) -> None:
        """Set zone target temperature."""
        await self.update_zone(zone, set_temp=temperature)

    async def turn_zone_on(self, zone: PolarisZone) -> None:
        """Turn a zone on."""
        await self.update_zone(zone, is_off=False)

    async def turn_zone_off(self, zone: PolarisZone) -> None:
        """Turn a zone off."""
        await self.update_zone(zone, is_off=True)


class PolarisApiError(Exception):
    """Error communicating with the Polaris API."""
