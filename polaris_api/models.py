"""Data models for Polaris 5 devices.

Supports both local UDP (snake_case) and cloud API (PascalCase) response formats.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _parse_temp(value: Any) -> float | None:
    """Parse temperature from API/local response.

    Values >= 100 are integer-encoded (e.g. 195 = 19.5°C).
    """
    if value is None:
        return None
    try:
        v = float(str(value))
        if abs(v) >= 100:
            return v / 10.0
        return v
    except (ValueError, TypeError):
        return None


def _parse_bool(value: Any, default: bool = False) -> bool:
    """Parse boolean from various formats (int, str, bool)."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.lower() in ("true", "1")
    return default


def _parse_int(value: Any, default: int = 0) -> int:
    """Parse integer from various formats."""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    if isinstance(value, bool):
        return 1 if value else 0
    return default


@dataclass
class PolarisZone:
    """Represents a single HVAC zone in a Polaris CU."""

    zone_id: int = 0
    name: str = "Unknown"
    current_temp: float | None = None  # °C
    set_temp: float | None = None  # °C
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
    def from_local(cls, data: dict[str, Any]) -> PolarisZone:
        """Parse zone from local UDP response (snake_case fields).

        Local format uses fields like: id_zona, name, temp, t_set,
        is_off, is_cool, fan_set, shu_set, is_crono, umd, etc.
        """
        return cls(
            zone_id=_parse_int(data.get("id_zona", data.get("zone_id", 0))),
            name=str(data.get("name", data.get("Name", "Unknown"))),
            current_temp=_parse_temp(data.get("temp", data.get("Temp"))),
            set_temp=_parse_temp(data.get("t_set", data.get("SetTemp"))),
            is_off=_parse_bool(data.get("is_off", data.get("IsOFF"))),
            is_cooling=_parse_bool(data.get("is_cool", data.get("isCooling"))),
            fancoil=_parse_int(data.get("fancoil", data.get("Fancoil", -1)), -1),
            fancoil_set=_parse_int(data.get("fan_set", data.get("FancoilSet", -1)), -1),
            ev=_parse_int(data.get("ev", data.get("EV", 0))),
            serranda=_parse_int(data.get("serranda", data.get("Serranda", -1)), -1),
            serranda_set=_parse_int(data.get("shu_set", data.get("SerrandaSet", -1)), -1),
            man_crono=_parse_int(data.get("man_crono", data.get("ManCrono", 0))),
            is_crono_mode=_parse_bool(data.get("is_crono", data.get("isCronoMode"))),
            is_master=_parse_bool(data.get("is_master", data.get("isMaster"))),
            humidity=_parse_temp(data.get("umd", data.get("Umd"))),
            set_humidity=_parse_temp(data.get("set_umd", data.get("SetUmd"))),
            num_error=_parse_int(data.get("num_error", data.get("numError", 0))),
            c_badge=data.get("c_badge", data.get("CBadge")),
            c_win=data.get("c_win", data.get("CWin")),
            raw_data=data,
        )

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> PolarisZone:
        """Parse zone from cloud API response (PascalCase fields).

        Kept for backward compatibility but delegates to from_local
        which handles both formats.
        """
        return cls.from_local(data)


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
    def from_local(cls, data: dict[str, Any]) -> PolarisDevice:
        """Parse device from local UDP stato_sync response.

        Local format uses snake_case fields:
        is_off, is_cool, cool_mod, f_inv, f_est, serial, name, fw_ver, etc.
        """
        is_off = _parse_bool(data.get("is_off", data.get("IsOFF", False)))
        is_cooling = _parse_bool(data.get("is_cool", data.get("IsCooling", False)))

        # Operating mode: cool_mod in local, OperatingModeCooling in cloud
        if is_cooling:
            op_mode = _parse_int(
                data.get("cool_mod", data.get("OperatingModeCooling", 0))
            )
        else:
            op_mode = 0

        return cls(
            serial=str(data.get("serial", data.get("Serial", ""))),
            name=str(data.get("name", data.get("Name", "Unknown"))),
            fw_ver=str(data.get("fw_ver", data.get("FWVer", ""))),
            ip=str(data.get("ip", data.get("IP", ""))),
            is_off=is_off,
            is_cooling=is_cooling,
            operating_mode=op_mode,
            f_inv=_parse_int(data.get("f_inv", data.get("FInv", 0))),
            f_est=_parse_int(data.get("f_est", data.get("FEst", 0))),
            ir_present=_parse_int(data.get("ir_present", data.get("IrPresent", 0))),
            num_errors=_parse_int(data.get("num_errors", data.get("NumErrors", 0))),
        )

    @classmethod
    def from_get_home(cls, data: dict[str, Any]) -> PolarisDevice:
        """Parse device from cloud GetHome response (backward compat)."""
        return cls.from_local(data)
