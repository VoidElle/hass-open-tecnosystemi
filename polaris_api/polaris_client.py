"""Local UDP client for Tecnosystemi Polaris 5 (CU) devices.

Uses the same UDP protocol as Pico devices (ports 40069/40070) with
Polaris-specific commands (upd_cu, upd_zona, stato_sync).

Discovered from the Tecnosystemi Android APK DEX analysis:
- UDPSocket class: portaDest=40070, portaRead=40069
- CmdPICO class: {cmd, frm, idp, pin} base command for ALL devices
- JSON_OFFLINE_COMMAND constants: snake_case field names
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from ..open_pico_local_api.shared_transport_manager import SharedTransportManager
from .models import PolarisDevice, PolarisZone

_LOGGER = logging.getLogger(__name__)


class PolarisLocalClient:
    """Async local UDP client for Polaris 5 CU devices.

    Reuses the SharedTransportManager from PicoClient so both device
    families share a single UDP socket on port 40069.
    """

    def __init__(
        self,
        ip: str,
        pin: str,
        device_id: str | None = None,
        device_port: int = 40070,
        local_port: int = 40069,
        timeout: float = 5,
        retry_attempts: int = 3,
        retry_delay: float = 2.0,
        verbose: bool = False,
    ) -> None:
        """Initialize the Polaris local client.

        Args:
            ip: IP address of the Polaris CU device.
            pin: Device PIN code.
            device_id: Unique device identifier (auto-generated if omitted).
            device_port: UDP port to send commands to (default 40070).
            local_port: Local UDP port to listen on (default 40069).
            timeout: Command response timeout in seconds.
            retry_attempts: Number of retries on failure.
            retry_delay: Delay between retries in seconds.
            verbose: Enable verbose debug logging.
        """
        self.ip = ip
        self.pin = pin
        self.device_port = device_port
        self.local_port = local_port
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.verbose = verbose

        self.device_id = device_id or f"polaris_{ip}:{device_port}"

        # Shared transport
        self._transport_manager: SharedTransportManager | None = None

        # IDP management (same mechanism as PicoClient)
        self._idp_counter = 1
        self._idp_range_start = 1
        self._idp_range_size = 10000

        self._response_queue: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._connected = False

        # Cached state
        self._device: PolarisDevice | None = None
        self._zones: list[PolarisZone] = []

    # ─── Properties ─────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        """Check if device is connected."""
        return self._connected

    @property
    def device(self) -> PolarisDevice | None:
        """Last known device state."""
        return self._device

    @property
    def zones(self) -> list[PolarisZone]:
        """Last known zones."""
        return self._zones

    # ─── Connection management ──────────────────────────────────────

    async def connect(self) -> None:
        """Connect to the Polaris device via shared UDP transport."""
        if self._connected:
            return

        try:
            self._transport_manager = await SharedTransportManager.get_instance()

            if not self._transport_manager.is_initialized:
                await self._transport_manager.initialize(
                    local_port=self.local_port,
                    verbose=self.verbose,
                )

            self._idp_range_start, self._idp_range_size = (
                await self._transport_manager.register_device(
                    device_id=self.device_id,
                    ip=self.ip,
                    port=self.device_port,
                    response_queue=self._response_queue,
                    event_callbacks={},
                )
            )

            self._idp_counter = self._idp_range_start
            self._connected = True

            if self.verbose:
                _LOGGER.debug(
                    "Connected Polaris '%s' to %s:%d (IDP range %d-%d)",
                    self.device_id, self.ip, self.device_port,
                    self._idp_range_start,
                    self._idp_range_start + self._idp_range_size - 1,
                )

        except Exception as err:
            raise ConnectionError(f"Failed to connect Polaris: {err}") from err

    async def disconnect(self) -> None:
        """Disconnect from the Polaris device."""
        if not self._connected:
            return

        if self._transport_manager:
            await self._transport_manager.unregister_device(self.device_id)

        self._connected = False

        if self.verbose:
            _LOGGER.debug("Disconnected Polaris '%s'", self.device_id)

    async def close(self) -> None:
        """Alias for disconnect (API compat with old cloud client)."""
        await self.disconnect()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
        return False

    # ─── Public API: Read ───────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        """Send stato_sync and return the raw response dict.

        The Polaris CU responds with a JSON object containing:
        - CU-level fields: is_off, is_cool, cool_mod, f_inv, f_est, ...
        - zones: list of zone objects with id_zona, name, temp, t_set, ...
        """
        if not self._connected:
            raise ConnectionError("Not connected to Polaris device")

        cmd = {
            "cmd": "stato_sync",
            "frm": "app",
            "pin": self.pin,
        }

        response = await self._execute_command_with_retry(cmd)
        if not response:
            raise TimeoutError(f"Failed to get Polaris status from {self.ip}")

        return response

    async def async_update(self) -> tuple[PolarisDevice, list[PolarisZone]]:
        """Full refresh: fetch status and parse device + zones.

        Returns (PolarisDevice, list[PolarisZone]).
        """
        raw = await self.get_status()

        # Parse device-level data
        self._device = PolarisDevice.from_local(raw)

        # Parse zones
        zones_data = raw.get("zones", raw.get("Zones", []))
        if isinstance(zones_data, list):
            self._zones = [
                PolarisZone.from_local(z)
                for z in zones_data
                if isinstance(z, dict)
            ]
        else:
            self._zones = []

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
        """Update a zone's settings via local UDP.

        Uses the upd_zona command format from the APK DEX:
        {"c":"upd_zona", "id_zona":..., "name":..., "is_off":...,
         "t_set":..., "is_crono":..., "fan_set":..., "shu_set":..., "pin":...}
        """
        if not self._connected:
            raise ConnectionError("Not connected to Polaris device")

        effective_is_off = is_off if is_off is not None else zone.is_off
        effective_temp = set_temp if set_temp is not None else (zone.set_temp or 20.0)
        effective_crono = is_crono if is_crono is not None else zone.is_crono_mode
        set_temp_int = round(effective_temp * 10)

        cmd_data: dict[str, Any] = {
            "c": "upd_zona",
            "id_zona": zone.zone_id,
            "name": zone.name,
            "is_off": 1 if effective_is_off else 0,
            "t_set": str(set_temp_int),
            "is_crono": 1 if effective_crono else 0,
            "pin": self.pin,
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

        # Wrap in standard command envelope
        cmd = {
            "cmd": "upd_zona",
            "frm": "app",
            "pin": self.pin,
            **cmd_data,
        }

        result = await self._execute_command_with_retry(cmd)
        if result is None:
            _LOGGER.warning("No response for upd_zona (zone %d)", zone.zone_id)

        _LOGGER.info(
            "Zone '%s' updated: is_off=%s, temp=%.1f°C",
            zone.name, effective_is_off, effective_temp,
        )

    # ─── Public API: Write (CU / device) ────────────────────────────

    async def update_cu(
        self,
        *,
        is_off: bool | None = None,
        is_cooling: bool | None = None,
        operating_mode: int | None = None,
    ) -> None:
        """Update CU (device-level) settings via local UDP.

        Uses the upd_cu command format from the APK DEX:
        {"c":"upd_cu", "pin":..., "is_off":..., "is_cool":...,
         "cool_mod":..., "t_can":..., "f_inv":..., "f_est":...}
        """
        if not self._connected:
            raise ConnectionError("Not connected to Polaris device")

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

        cmd = {
            "cmd": "upd_cu",
            "frm": "app",
            "pin": self.pin,
            **cmd_data,
        }

        result = await self._execute_command_with_retry(cmd)
        if result is None:
            _LOGGER.warning("No response for upd_cu")

        _LOGGER.info(
            "CU '%s' updated: is_off=%s, cooling=%s, mode=%d",
            dev.name if dev else self.ip,
            eff_is_off, eff_is_cooling, eff_op_mode,
        )

    # ─── Convenience methods ────────────────────────────────────────

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

    # ─── IDP management (same pattern as PicoClient) ────────────────

    async def _get_next_idp(self) -> int:
        """Get next IDP within allocated range."""
        async with self._lock:
            idp = self._idp_counter
            self._idp_counter += 1
            if self._idp_counter >= (self._idp_range_start + self._idp_range_size):
                self._idp_counter = self._idp_range_start
            return idp

    async def _reset_idp_counter(self) -> None:
        """Reset IDP counter to start of allocated range."""
        async with self._lock:
            self._idp_counter = self._idp_range_start

    # ─── UDP send/receive (same pattern as PicoClient) ──────────────

    async def _send_udp_packet(self, cmd: dict[str, Any]) -> bool:
        """Send a raw UDP packet to the device."""
        try:
            data = json.dumps(cmd).encode("utf-8")
            await self._transport_manager.send_to_device(self.device_id, data)

            if self.verbose:
                cmd_name = cmd.get("cmd", cmd.get("c", "unknown"))
                _LOGGER.debug(
                    "-> [%s] SENT: %s (idp:%s)",
                    self.device_id, cmd_name, cmd.get("idp"),
                )
            return True

        except Exception as err:
            if self.verbose:
                _LOGGER.debug("[%s] Send error: %s", self.device_id, err)
            raise

    async def _execute_command_with_retry(
        self,
        cmd_dict: dict[str, Any],
        retry: bool = True,
    ) -> dict[str, Any] | None:
        """Execute a command with IDP sync retry logic."""
        max_attempts = self.retry_attempts if retry else 1
        max_idp_sync = 5

        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                if self.verbose:
                    _LOGGER.debug("[%s] Retry %d/%d", self.device_id, attempt, max_attempts)
                await asyncio.sleep(self.retry_delay)

            for idp_sync_attempt in range(max_idp_sync):
                idp = await self._get_next_idp()
                cmd = {**cmd_dict, "idp": idp}

                if not await self._send_udp_packet(cmd):
                    continue

                response = await self._wait_for_response(idp, timeout=2.0)

                if response:
                    if idp_sync_attempt > 0 and self.verbose:
                        _LOGGER.debug(
                            "[%s] IDP synchronized after %d increments",
                            self.device_id, idp_sync_attempt,
                        )
                    return response

                if self.verbose:
                    _LOGGER.debug(
                        "[%s] No response for IDP %d — likely out of sync",
                        self.device_id, idp,
                    )

            # After all IDP sync attempts, reset
            if attempt < max_attempts:
                await self._reset_idp_counter()

        return None

    async def _wait_for_response(
        self, idp: int, timeout: float
    ) -> dict[str, Any] | None:
        """Wait for response matching the given IDP."""
        got_ack = False
        end_time = time.time() + timeout
        ack_timeout = 2.0
        ack_received_time = None

        while time.time() < end_time:
            remaining = end_time - time.time()
            if remaining <= 0:
                break

            if got_ack and ack_received_time:
                if time.time() - ack_received_time > ack_timeout:
                    return None

            try:
                response, addr = await asyncio.wait_for(
                    self._response_queue.get(),
                    timeout=min(remaining, 0.5),
                )

                if response.get("idp") != idp:
                    continue

                # ACK from device
                if response.get("res") == 99 and response.get("frm") == "mst":
                    got_ack = True
                    ack_received_time = time.time()

                # Data response
                elif response.get("res") != 99:
                    # Send ACK back
                    ack = {"idp": idp, "frm": "app", "res": 99}
                    await self._send_udp_packet(ack)
                    return response

            except asyncio.TimeoutError:
                continue

        return None


class PolarisApiError(Exception):
    """Error communicating with the Polaris device."""
