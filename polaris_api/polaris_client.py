"""Local TCP client for Tecnosystemi Polaris 5 (CU) devices.

Communicates directly with the device over TCP port 1235 — the same
transport used by the official Tecnosystemi Android app (MySocket class).

Protocol:
- Commands are sent as a UTF-8 JSON string over a raw TCP socket.
- The device replies with a JSON string.
- Each command/response pair uses its own short-lived connection
  (matches the MySocket.sendAndReceive pattern in the APK).
- Command key is "c" (not "cmd"). No IDP or frm envelope needed.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .models import PolarisDevice, PolarisZone

_LOGGER = logging.getLogger(__name__)

_BUFFER_SIZE = 4096


class PolarisLocalClient:
    """Async local TCP client for Polaris 5 CU devices."""

    def __init__(
        self,
        ip: str,
        pin: str,
        device_id: str | None = None,
        port: int = 1235,
        timeout: float = 5.0,
        retry_attempts: int = 2,
        retry_delay: float = 1.0,
        verbose: bool = False,
    ) -> None:
        """Initialize the Polaris local client.

        Args:
            ip: IP address of the Polaris CU device.
            pin: Device PIN code.
            device_id: Friendly identifier (auto-generated if omitted).
            port: TCP port on the device (default 1235).
            timeout: Per-command socket timeout in seconds.
            retry_attempts: Number of retries on failure/timeout.
            retry_delay: Delay between retries in seconds.
            verbose: Enable verbose debug logging.
        """
        self.ip = ip
        self.pin = pin
        self.port = port
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.verbose = verbose

        self.device_id = device_id or f"polaris_{ip}:{port}"

        self._connected = False

        # Cached state
        self._device: PolarisDevice | None = None
        self._zones: list[PolarisZone] = []

    # ─── Properties ─────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def device(self) -> PolarisDevice | None:
        return self._device

    @property
    def zones(self) -> list[PolarisZone]:
        return self._zones

    # ─── Connection management ──────────────────────────────────────

    async def connect(self) -> None:
        """Verify connectivity by performing an initial async_update.

        Sets _connected=True and populates _device/_zones on success.
        TCP is stateless per-command so there is nothing to keep open.
        """
        if self._connected:
            return
        await self.async_update()  # raises TimeoutError / ConnectionError on failure
        if self.verbose:
            _LOGGER.debug("[%s] Connected to %s:%d", self.device_id, self.ip, self.port)

    async def disconnect(self) -> None:
        """Mark client as disconnected (TCP is stateless per-command)."""
        self._connected = False
        if self.verbose:
            _LOGGER.debug("[%s] Disconnected", self.device_id)

    async def close(self) -> None:
        await self.disconnect()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
        return False

    # ─── Public API: Read ───────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        """Fetch device status via local TCP.

        Mirrors BaseActivity.inizializeGetState(true) / offlineResCURistretto():
        1. Try CMD_STATO_R ("stato_r") — compact/ridotto format used for local polling.
        2. If the device returns res=4 (CMD_NOT_FOUND), fall back to CMD_STATO ("stato").

        "stato_sync" is a cloud/HTTP command and must NOT be sent over TCP.
        """
        cmd = {"c": "stato_r", "pin": self.pin}
        response = await self._send_command_with_retry(cmd)

        # res=4 → CMD_NOT_FOUND: device doesn't support stato_r, try full stato
        if response is not None and response.get("res") == 4:
            if self.verbose:
                _LOGGER.debug("[%s] stato_r not supported (res=4), falling back to stato", self.device_id)
            cmd = {"c": "stato", "pin": self.pin}
            response = await self._send_command_with_retry(cmd)

        if response is None:
            raise TimeoutError(f"No response from Polaris device at {self.ip}:{self.port}")
        return response

    async def async_update(self) -> tuple[PolarisDevice, list[PolarisZone]]:
        """Full refresh: fetch status and parse device + zones."""
        raw = await self.get_status()

        self._device = PolarisDevice.from_local(raw)
        self._connected = True

        # local: "zone" (JSON_OFFLINE_COMMAND_ZONE), cloud: "Zones" (JSON_CU_ZONE)
        zones_data = raw.get("zone", raw.get("Zones", []))
        self._zones = [
            PolarisZone.from_local(z)
            for z in zones_data
            if isinstance(z, dict)
        ] if isinstance(zones_data, list) else []

        _LOGGER.debug(
            "[%s] Polaris update: on=%s, mode=%s, zones=%d",
            self.device_id,
            self._device.is_on,
            self._device.cooling_mode_name,
            len(self._zones),
        )

        return self._device, self._zones

    # ─── Public API: Write (zone) ───────────────────────────────────

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

        Command format from APK DEX (Zona.update_ZONA_Command):
        {"c":"upd_zona","id_zona":...,"name":...,"is_off":...,"t_set":"<int*10>",
         "fan_set":...,"shu_set":...,"is_crono":...,"pin":...}
        """
        effective_is_off = is_off if is_off is not None else zone.is_off
        if set_temp is not None:
            effective_temp = set_temp
        elif zone.set_temp is not None:
            effective_temp = zone.set_temp
        else:
            raise ValueError(
                f"Cannot update zone {zone.zone_id}: no target temperature known. "
                "Set a temperature explicitly."
            )
        effective_crono = is_crono if is_crono is not None else zone.is_crono_mode
        set_temp_int = round(effective_temp * 10)

        cmd: dict[str, Any] = {
            "c": "upd_zona",
            "id_zona": zone.zone_id,
            "name": zone.name,
            "is_off": 1 if effective_is_off else 0,
            "t_set": str(set_temp_int),
            "is_crono": 1 if effective_crono else 0,
            "pin": self.pin,
        }

        # fan_set / shu_set — protocol always sends both with the same value.
        # Hardware presence: zone.fancoil / zone.serranda == -1 → not installed.
        # When only one type present, its set-point drives both fields.
        # When both present, fancoil takes priority (lastFancoil=True default).
        eff_fancoil = fancoil_set if fancoil_set is not None else zone.fancoil_set
        eff_serranda = serranda_set if serranda_set is not None else zone.serranda_set
        fancoil_present = zone.fancoil != -1
        serranda_present = zone.serranda != -1

        if not fancoil_present and serranda_present:
            if eff_serranda is not None and eff_serranda != -1:
                shu_val = 16 if eff_serranda == 7 else eff_serranda
                cmd["shu_set"] = shu_val
                cmd["fan_set"] = shu_val
        else:
            if eff_fancoil is not None and eff_fancoil != -1:
                fan_val = 16 if eff_fancoil == 7 else eff_fancoil
                cmd["fan_set"] = fan_val
                cmd["shu_set"] = fan_val
            elif serranda_present and eff_serranda is not None and eff_serranda != -1:
                shu_val = 16 if eff_serranda == 7 else eff_serranda
                cmd["shu_set"] = shu_val
                cmd["fan_set"] = shu_val

        result = await self._send_command_with_retry(cmd)
        if result is None:
            _LOGGER.warning("[%s] No response for upd_zona (zone %d)", self.device_id, zone.zone_id)

        _LOGGER.info(
            "[%s] Zone '%s' updated: is_off=%s, temp=%.1f°C",
            self.device_id, zone.name, effective_is_off, effective_temp,
        )

    # ─── Public API: Write (CU / device) ────────────────────────────

    async def update_cu(
        self,
        *,
        is_off: bool | None = None,
        is_cooling: bool | None = None,
        operating_mode: int | None = None,
    ) -> None:
        """Update CU (device-level) settings.

        Command format from APK DEX (ControlUnit.update_CU_command):
        {"c":"upd_cu","pin":...,"is_off":...,"is_cool":...,"cool_mod":...,
         "t_can":<°C*10>,"f_inv":...,"f_est":...}
        """
        dev = self._device
        eff_is_off = is_off if is_off is not None else (dev.is_off if dev else False)
        eff_is_cooling = is_cooling if is_cooling is not None else (dev.is_cooling if dev else False)
        eff_op_mode = operating_mode if operating_mode is not None else (dev.operating_mode if dev else 0)

        cmd: dict[str, Any] = {
            "c": "upd_cu",
            "pin": self.pin,
            "is_off": 1 if eff_is_off else 0,
            "is_cool": 1 if eff_is_cooling else 0,
            "cool_mod": eff_op_mode,
            "t_can": (dev.t_can * 10) if dev else 0,
            "f_inv": dev.f_inv if dev else 0,
            "f_est": dev.f_est if dev else 0,
        }

        result = await self._send_command_with_retry(cmd)
        if result is None:
            _LOGGER.warning("[%s] No response for upd_cu", self.device_id)

        _LOGGER.info(
            "[%s] CU '%s' updated: is_off=%s, cooling=%s, mode=%d",
            self.device_id,
            dev.name if dev else self.ip,
            eff_is_off, eff_is_cooling, eff_op_mode,
        )

    # ─── Convenience methods ────────────────────────────────────────

    async def turn_on(self) -> None:
        await self.update_cu(is_off=False)

    async def turn_off(self) -> None:
        await self.update_cu(is_off=True)

    async def set_cooling_mode(self, mode: int) -> None:
        """Set cooling mode (1=raffrescamento, 2=deumidificazione, 3=ventilazione)."""
        await self.update_cu(is_off=False, is_cooling=True, operating_mode=mode)

    async def set_heating_mode(self) -> None:
        await self.update_cu(is_off=False, is_cooling=False, operating_mode=0)

    async def set_zone_temp(self, zone: PolarisZone, temperature: float) -> None:
        await self.update_zone(zone, set_temp=temperature)

    async def turn_zone_on(self, zone: PolarisZone) -> None:
        await self.update_zone(zone, is_off=False)

    async def turn_zone_off(self, zone: PolarisZone) -> None:
        await self.update_zone(zone, is_off=True)

    # ─── TCP transport ──────────────────────────────────────────────

    async def _send_command_with_retry(
        self,
        cmd: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Send a command with retries, returning the parsed response or None."""
        for attempt in range(1, self.retry_attempts + 1):
            if attempt > 1:
                if self.verbose:
                    _LOGGER.debug("[%s] Retry %d/%d", self.device_id, attempt, self.retry_attempts)
                await asyncio.sleep(self.retry_delay)

            try:
                result = await asyncio.wait_for(
                    self._send_and_receive(cmd),
                    timeout=self.timeout,
                )
                if result is not None:
                    return result
            except asyncio.TimeoutError:
                if self.verbose:
                    _LOGGER.debug(
                        "[%s] Timeout on attempt %d for '%s'",
                        self.device_id, attempt, cmd.get("c"),
                    )
            except Exception as err:
                if self.verbose:
                    _LOGGER.debug("[%s] Error on attempt %d: %s", self.device_id, attempt, err)

        return None

    async def _send_and_receive(self, cmd: dict[str, Any]) -> dict[str, Any] | None:
        """Open a TCP connection, send the command JSON, read and return the response.

        Mirrors MySocket.sendAndReceive: each call opens and closes its own socket.
        """
        payload = json.dumps(cmd).encode("utf-8")

        if self.verbose:
            _LOGGER.debug("-> [%s] SEND '%s': %s", self.device_id, cmd.get("c"), payload.decode())

        reader, writer = await asyncio.open_connection(self.ip, self.port)
        try:
            writer.write(payload)
            await writer.drain()

            data = b""
            while True:
                chunk = await reader.read(_BUFFER_SIZE)
                if not chunk:
                    break
                data += chunk
                if len(chunk) < _BUFFER_SIZE:
                    # Partial read = end of response (mirrors Java's i < 1000 check)
                    break

            if not data:
                return None

            raw_str = data.decode("utf-8")
            if self.verbose:
                _LOGGER.debug("<- [%s] RECV: %s", self.device_id, raw_str)

            return json.loads(raw_str)

        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


class PolarisApiError(Exception):
    """Error communicating with the Polaris device."""
