"""Data models for Polaris 5 devices."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PolarisZone:
    """Represents a single HVAC zone in a Polaris CU."""

    zone_id: int = 0
    name: str = "Unknown"
    current_temp: float | None = None  # °C (divided by 10 from API)
    set_temp: float | None = None  # °C (divided by 10 from API)
    is_off: bool = False
    is_cooling: bool = False
    fancoil: int = -1
    fancoil_set: int = -1
    ev: int = 0
    serranda: int = -1
    serranda_set: int = -1
    man_crono: int = 0
    is_crono_mode: bool = False
    is_master: bool = False
    humidity: float | None = None
    set_humidity: float | None = None
    num_error: int = 0
    c_badge: Any = None
    c_win: Any = None
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_on(self) -> bool:
        return not self.is_off

    @property
    def has_error(self) -> bool:
        return self.num_error > 0

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> PolarisZone:
        """Parse zone from GetCUState API response (PascalCase fields)."""

        def parse_temp(value: Any) -> float | None:
            if value is None:
                return None
            try:
                v = float(str(value))
                # Values >= 100 are integer-encoded (e.g. "195" = 19.5°C)
                if abs(v) >= 100:
                    return v / 10.0
                return v
            except (ValueError, TypeError):
                return None

        def parse_bool(value: Any, default: bool = False) -> bool:
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            if isinstance(value, int):
                return value != 0
            if isinstance(value, str):
                return value.lower() in ("true", "1")
            return default

        def parse_int(value: Any) -> int:
            if value is None:
                return 0
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    return 0
            if isinstance(value, bool):
                return 1 if value else 0
            return 0

        return cls(
            zone_id=parse_int(data.get("ZoneId", data.get("zoneId", data.get("id_zona", 0)))),
            name=str(data.get("Name", data.get("name", "Unknown"))),
            current_temp=parse_temp(data.get("Temp", data.get("temp"))),
            set_temp=parse_temp(data.get("SetTemp", data.get("setTemp"))),
            is_off=parse_bool(data.get("IsOFF", data.get("isOff", data.get("IsOff")))),
            is_cooling=parse_bool(data.get("isCooling", data.get("IsCooling"))),
            fancoil=parse_int(data.get("Fancoil", -1)),
            fancoil_set=parse_int(data.get("FancoilSet", -1)),
            ev=parse_int(data.get("EV", 0)),
            serranda=parse_int(data.get("Serranda", -1)),
            serranda_set=parse_int(data.get("SerrandaSet", -1)),
            man_crono=parse_int(data.get("ManCrono", 0)),
            is_crono_mode=parse_bool(data.get("isCronoMode", data.get("IsCronoMode"))),
            is_master=parse_bool(data.get("isMaster", data.get("IsMaster"))),
            humidity=parse_temp(data.get("Umd")),
            set_humidity=parse_temp(data.get("SetUmd")),
            num_error=parse_int(data.get("numError", data.get("NumError", 0))),
            c_badge=data.get("CBadge"),
            c_win=data.get("CWin"),
            raw_data=data,
        )


@dataclass
class PolarisDevice:
    """Represents a Polaris Control Unit (CU) with its zones."""

    serial: str = ""
    name: str = "Unknown"
    fw_ver: str = ""
    ip: str = ""
    is_off: bool = False
    is_cooling: bool = False
    operating_mode: int = 0  # 0=heating, 1=raffrescamento, 2=deumidificazione, 3=ventilazione
    f_inv: int = 0
    f_est: int = 0
    ir_present: int = 0
    num_errors: int = 0
    zones: list[PolarisZone] = field(default_factory=list)

    @property
    def is_on(self) -> bool:
        return not self.is_off

    @property
    def cooling_mode_name(self) -> str:
        """Human-readable cooling mode name."""
        return {
            0: "Riscaldamento",
            1: "Raffrescamento",
            2: "Deumidificazione",
            3: "Ventilazione",
        }.get(self.operating_mode, "Sconosciuto")

    @classmethod
    def from_get_home(cls, data: dict[str, Any]) -> PolarisDevice:
        """Parse device from GetHome API response."""
        is_off = data.get("IsOFF", False)
        if isinstance(is_off, str):
            is_off = is_off.lower() == "true"
        is_cooling = data.get("IsCooling", False)
        if isinstance(is_cooling, str):
            is_cooling = is_cooling.lower() == "true"

        return cls(
            serial=str(data.get("Serial", "")),
            name=str(data.get("Name", "Unknown")),
            fw_ver=str(data.get("FWVer", "")),
            ip=str(data.get("IP", "")),
            is_off=bool(is_off),
            is_cooling=bool(is_cooling),
            operating_mode=int(data.get("OperatingModeCooling", 0)) if is_cooling else 0,
            f_inv=int(data.get("FInv", 0)),
            f_est=int(data.get("FEst", 0)),
            ir_present=int(data.get("IrPresent", 0)),
            num_errors=int(data.get("NumErrors", 0)),
        )
