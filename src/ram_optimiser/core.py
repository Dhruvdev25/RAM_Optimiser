"""Dependency-light calculations and safety rules used by the application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from threading import Lock

GIB = 1024**3
MIB = 1024**2

# This denylist is deliberately conservative. The application and core Windows
# processes remain protected even when a user edits their own protection list.
PROTECTED_NAMES = frozenset({
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe",
    "fontdrvhost.exe", "dwm.exe", "sihost.exe", "winlogon.exe",
    "runtimebroker.exe", "securityhealthservice.exe", "msmpeng.exe",
    "logonui.exe", "lsaiso.exe", "memcompression", "trustedinstaller.exe",
    "tiworker.exe", "wmiprvse.exe", "taskhostw.exe", "usocoreworker.exe",
    "mousocoreworker.exe",
})


def clamp_percent(value: float | int | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(100.0, float(value)))


def format_bytes(value: int | float | None, suffix: str = "B") -> str:
    if value is None:
        return "Unavailable"
    amount = max(0.0, float(value))
    for unit in (suffix, "KiB", "MiB", "GiB", "TiB"):
        if unit == suffix:
            scale = 1.0
        else:
            scale = 1024 ** (1 + ("KiB", "MiB", "GiB", "TiB").index(unit))
        if amount < scale * 1024 or unit == "TiB":
            return f"{amount / scale:.1f} {unit}"
    return f"{amount:.1f} TiB"


def memory_percent(total: int | float | None, used: int | float | None) -> float | None:
    if total is None or used is None or float(total) <= 0:
        return None
    return clamp_percent(float(used) / float(total) * 100.0)


def is_protected_process(name: str | None, pid: int | None, own_pid: int,
                         protected_names: Iterable[str] = ()) -> bool:
    """Return True for this app, Windows essentials, or a user-protected name."""
    if pid is not None and int(pid) in {0, 4, own_pid}:
        return True
    normalized = (name or "").strip().lower()
    custom = {str(item).strip().lower() for item in protected_names if str(item).strip()}
    return normalized in PROTECTED_NAMES or normalized in custom


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    create_time: float


def identity_matches(expected: ProcessIdentity, actual_pid: int,
                     actual_create_time: float | None) -> bool:
    """PID reuse is rejected by comparing the process creation timestamp."""
    return (expected.pid == int(actual_pid) and actual_create_time is not None
            and abs(expected.create_time - float(actual_create_time)) < 0.01)


@dataclass(frozen=True)
class MemoryMeasurement:
    before_available: int | None
    after_available: int | None

    @property
    def available_delta(self) -> int | None:
        if self.before_available is None or self.after_available is None:
            return None
        return self.after_available - self.before_available


class OperationGate:
    """Thread-safe guard against overlapping memory operations."""
    def __init__(self):
        self._lock = Lock()
        self._active = False

    def try_enter(self) -> bool:
        with self._lock:
            if self._active:
                return False
            self._active = True
            return True

    def leave(self) -> None:
        with self._lock:
            self._active = False

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
