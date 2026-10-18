"""System, process, boost, game-session, and Windows startup services."""

from __future__ import annotations

import ctypes
import os
import platform
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:  # A clear UI error is preferable to an import-time crash.
    psutil = None

from .core import MIB, ProcessIdentity, format_bytes, identity_matches, is_protected_process


def _require_psutil():
    if psutil is None:
        raise RuntimeError("The psutil package is missing. Reinstall RAM Optimiser to restore monitoring.")


def _current_username() -> str | None:
    try:
        return str(psutil.Process(os.getpid()).username()).strip()
    except Exception:
        return None


def _same_user(username: str | None, current_username: str | None) -> bool:
    return bool(username and current_username and
                username.strip().casefold() == current_username.strip().casefold())


def _cpu_name() -> str:
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                value = str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
                if value:
                    return value
        except (OSError, ImportError):
            pass
    value = platform.processor().strip()
    if value:
        return value
    return "Unavailable"


def _cpu_temperature() -> float | None:
    if psutil is None or not hasattr(psutil, "sensors_temperatures"):
        return None
    try:
        sensors = psutil.sensors_temperatures(fahrenheit=False) or {}
        for preferred in ("coretemp", "cpu_thermal", "k10temp", "zenpower", "acpitz"):
            for name, entries in sensors.items():
                if preferred in name.lower():
                    for entry in entries:
                        if entry.current is not None and 0 <= entry.current <= 150:
                            return float(entry.current)
        for entries in sensors.values():
            for entry in entries:
                label = f"{entry.label or ''}".lower()
                if "cpu" in label and entry.current is not None and 0 <= entry.current <= 150:
                    return float(entry.current)
    except Exception:
        return None
    return None


class NvidiaProbe:
    """Optional NVML reader. Absence is represented as unavailable values."""
    def __init__(self):
        self._nvml = None
        self._device = None
        try:
            import pynvml
            pynvml.nvmlInit()
            if pynvml.nvmlDeviceGetCount() > 0:
                self._nvml = pynvml
                self._device = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:
            self._nvml = None

    def snapshot(self) -> dict[str, Any]:
        if self._nvml is None or self._device is None:
            return {"name": "Unavailable", "utilization": None, "vram_total": None,
                    "vram_used": None, "temperature": None, "available": False}
        try:
            nv = self._nvml
            memory = nv.nvmlDeviceGetMemoryInfo(self._device)
            util = nv.nvmlDeviceGetUtilizationRates(self._device)
            try:
                temp = nv.nvmlDeviceGetTemperature(self._device, nv.NVML_TEMPERATURE_GPU)
            except Exception:
                temp = None
            name = nv.nvmlDeviceGetName(self._device)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            return {"name": str(name), "utilization": float(util.gpu),
                    "vram_total": int(memory.total), "vram_used": int(memory.used),
                    "temperature": float(temp) if temp is not None else None, "available": True}
        except Exception:
            return {"name": "Unavailable", "utilization": None, "vram_total": None,
                    "vram_used": None, "temperature": None, "available": False}


_GPU = None


def collect_snapshot(drive_path: str = "C:/") -> dict[str, Any]:
    _require_psutil()
    global _GPU
    if _GPU is None:
        _GPU = NvidiaProbe()
    memory = psutil.virtual_memory()
    try:
        drive = psutil.disk_usage(drive_path)
        storage = {"path": drive_path, "total": drive.total, "used": drive.used,
                   "free": drive.free, "percent": drive.percent}
    except (OSError, PermissionError, ValueError):
        storage = {"path": drive_path, "total": None, "used": None, "free": None, "percent": None}
    gpu = _GPU.snapshot()
    return {
        "computer_name": platform.node() or "Unavailable",
        "windows_version": f"Windows {platform.release()} ({platform.version()})" if os.name == "nt" else f"{platform.system()} {platform.release()}",
        "cpu_name": _cpu_name(), "cpu_percent": float(psutil.cpu_percent(interval=None)),
        "cpu_temperature": _cpu_temperature(),
        "ram_total": int(memory.total), "ram_used": int(memory.used),
        "ram_available": int(memory.available), "ram_percent": float(memory.percent),
        "storage": storage, "gpu": gpu, "process_count": len(psutil.pids()),
        "sampled_at": time.time(),
    }


def collect_process_names() -> dict[str, Any]:
    """Lightweight process-name scan used for prompt game detection."""
    _require_psutil()
    names = []
    for proc in psutil.process_iter(["name"]):
        try:
            names.append((proc.info.get("name") or "Unknown").lower())
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
            continue
    return {"process_names": names, "sampled_at": time.time()}


def collect_top_processes() -> dict[str, Any]:
    """Read process working sets separately from the quick metric refresh."""
    _require_psutil()
    top = []
    current_username = _current_username()
    for proc in psutil.process_iter(["pid", "name", "memory_info", "username"]):
        try:
            info = proc.info
            rss = int(info["memory_info"].rss) if info.get("memory_info") else 0
            name = info.get("name") or "Unknown"
            pid = int(info["pid"])
            top.append({"pid": pid, "name": name, "rss": rss,
                        "protected": is_protected_process(name, pid, os.getpid()) or
                                    not _same_user(info.get("username"), current_username)})
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError, KeyError, TypeError):
            continue
    top.sort(key=lambda item: item["rss"], reverse=True)
    return {"top_processes": top[:8], "sampled_at": time.time()}


@dataclass
class ProcessRecord:
    pid: int
    name: str
    rss: int
    cpu_percent: float
    status: str
    protected: bool
    create_time: float
    executable: str
    username: str

    @property
    def identity(self) -> ProcessIdentity:
        return ProcessIdentity(self.pid, self.create_time)


def list_processes(protected_names=(), excluded_names=()) -> list[ProcessRecord]:
    _require_psutil()
    excluded = {str(name).lower().strip() for name in excluded_names}
    current_username = _current_username()
    records = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "status", "create_time", "exe", "username"]):
        try:
            info = proc.info
            name = info.get("name") or "Unknown"
            pid = int(info["pid"])
            created = float(info["create_time"])
            rss = int(info["memory_info"].rss) if info.get("memory_info") else 0
            try:
                cpu = float(proc.cpu_percent(interval=None))
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                cpu = 0.0
            records.append(ProcessRecord(
                pid=pid, name=name, rss=rss, cpu_percent=cpu,
                status=info.get("status") or "Unknown",
                protected=(is_protected_process(name, pid, os.getpid(), protected_names) or
                           name.lower() in excluded or
                           not _same_user(info.get("username"), current_username)),
                create_time=created, executable=info.get("exe") or "Unavailable",
                username=info.get("username") or "Unavailable",
            ))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError, KeyError, TypeError, ValueError):
            continue
    records.sort(key=lambda record: record.rss, reverse=True)
    return records


def _validate_identity(identity: ProcessIdentity):
    _require_psutil()
    proc = psutil.Process(identity.pid)
    created = proc.create_time()
    if not identity_matches(identity, identity.pid, created):
        raise RuntimeError("The process identity changed. Refresh the list before trying again.")
    name = proc.name()
    if is_protected_process(name, identity.pid, os.getpid()):
        raise PermissionError(f"{name} is protected by RAM Optimiser safety rules.")
    if not _same_user(proc.username(), _current_username()):
        raise PermissionError(f"{name} does not belong to the current Windows user or its owner could not be verified.")
    return proc, name


def trim_process(identity: ProcessIdentity) -> tuple[bool, str]:
    """Ask Windows to trim one selected process working set; never terminates it."""
    if os.name != "nt":
        return False, "Working-set trimming is supported only on Windows."
    try:
        _, name = _validate_identity(identity)
        access = 0x0100 | 0x0400  # PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(access, False, identity.pid)
        if not handle:
            code = ctypes.get_last_error()
            return False, f"Windows denied access to {name} (error {code})."
        try:
            ok = bool(psapi.EmptyWorkingSet(ctypes.c_void_p(handle)))
            if not ok:
                return False, f"Windows could not trim {name} (error {ctypes.get_last_error()})."
            return True, f"Windows accepted a working-set trim request for {name}. Reclaimed bytes are not guaranteed."
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return False, "The process exited before the operation began."
    except (psutil.AccessDenied, PermissionError) as exc:
        return False, str(exc) or "Permission denied."
    except Exception as exc:
        return False, f"Trim failed: {exc}"


def _safe_candidates(mode: str, protected_names=(), excluded_names=(), eligible_names=()) -> list[ProcessRecord]:
    protected_names = list(protected_names)
    excluded_names = {str(name).strip().lower() for name in excluded_names}
    eligible_names = {str(name).strip().lower() for name in eligible_names}
    processes = list_processes(protected_names, excluded_names)
    eligible = [p for p in processes if not p.protected and p.name.lower() not in excluded_names]
    # The thresholds limit pointless API calls. A working-set trim is still only
    # a hint to Windows; it is not a promise of reclaimed physical memory.
    if mode == "Quick Boost":
        eligible = [p for p in eligible if p.rss >= (25 if p.name.lower() in eligible_names else 100) * MIB][:6]
    elif mode == "Deep Boost":
        eligible = [p for p in eligible if p.rss >= (20 if p.name.lower() in eligible_names else 35) * MIB][:60]
    else:
        eligible = [p for p in eligible if p.rss >= (25 if p.name.lower() in eligible_names else 80) * MIB][:18]
    return eligible


def run_boost(mode: str, protected_names=(), excluded_names=(), eligible_names=()) -> dict[str, Any]:
    """Trim eligible process working sets and measure actual system availability."""
    _require_psutil()
    started = time.perf_counter()
    before = int(psutil.virtual_memory().available)
    candidates = _safe_candidates(mode, protected_names, excluded_names, eligible_names)
    details = []
    succeeded = failed = 0
    for candidate in candidates:
        # Identity is checked immediately before opening a process handle.
        ok, message = trim_process(candidate.identity)
        succeeded += int(ok)
        failed += int(not ok)
        details.append({"pid": candidate.pid, "name": candidate.name, "success": ok, "message": message})
    after = int(psutil.virtual_memory().available)
    return {"mode": mode, "before_available": before, "after_available": after,
            "available_delta": after - before, "attempted": len(candidates),
            "succeeded": succeeded, "failed": failed,
            "duration": time.perf_counter() - started, "details": details}


def close_process(identity: ProcessIdentity, force: bool = False) -> tuple[bool, str]:
    """Close a validated, explicitly selected process; force is separate."""
    try:
        proc, name = _validate_identity(identity)
        if force:
            proc.kill()
            return True, f"Force termination was sent to {name}. Unsaved work may be lost."
        if os.name != "nt":
            proc.terminate()
            return True, f"A graceful termination request was sent to {name}."
        # Deliver WM_CLOSE to top-level windows belonging to this process.
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        enum_windows = user32.EnumWindows
        enum_windows.argtypes = [ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p), ctypes.c_void_p]
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
        user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        user32.PostMessageW.restype = ctypes.c_bool
        found = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        @callback_type
        def visit(hwnd, _):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == identity.pid:
                found.append(hwnd)
            return True
        enum_windows(visit, None)
        if not found:
            return False, f"No top-level window was found for {name}; RAM Optimiser left it running."
        for hwnd in found:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        return True, f"A close request was sent to {name}. The application can prompt to save work."
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return False, "The process has already exited."
    except (psutil.AccessDenied, PermissionError) as exc:
        return False, str(exc) or "Windows denied access."
    except Exception as exc:
        return False, f"The process action failed: {exc}"


def inspect_process(identity: ProcessIdentity) -> dict[str, Any]:
    proc, name = _validate_identity(identity)
    try:
        memory = proc.memory_info()
        return {"pid": proc.pid, "name": name, "executable": proc.exe() or "Unavailable",
                "username": proc.username() or "Unavailable", "status": proc.status(),
                "create_time": proc.create_time(), "rss": memory.rss,
                "vms": memory.vms, "threads": proc.num_threads(),
                "cmdline": " ".join(proc.cmdline()) or "Unavailable"}
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as exc:
        raise RuntimeError(f"Process details are no longer available: {exc}") from exc


def startup_entries() -> list[dict[str, Any]]:
    """Read standard Run keys; publisher and startup impact are not inferred."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    entries = []
    roots = ((winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM"))
    path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    for root, short in roots:
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as key:
                index = 0
                while True:
                    try:
                        name, value, kind = winreg.EnumValue(key, index)
                        entries.append({"name": name, "command": str(value), "kind": kind,
                                        "location": f"{short}\\{path}", "root": short,
                                        "enabled": True, "publisher": "Unavailable", "impact": "Unavailable"})
                        index += 1
                    except OSError:
                        break
        except OSError:
            continue
    for root, short in roots:
        try:
            with winreg.OpenKey(root, r"Software\RAM Optimiser\Disabled Startup", 0, winreg.KEY_READ) as key:
                index = 0
                while True:
                    try:
                        encoded_name, value, kind = winreg.EnumValue(key, index)
                        entries.append({"name": encoded_name, "command": str(value), "kind": kind,
                                        "location": f"{short}\\Software\\RAM Optimiser\\Disabled Startup",
                                        "root": short, "enabled": False, "publisher": "Unavailable", "impact": "Unavailable"})
                        index += 1
                    except OSError:
                        break
        except OSError:
            continue
    return entries


def set_startup_entry(entry: dict[str, Any], enable: bool) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Startup registry editing is available only on Windows."
    try:
        import winreg
        root = winreg.HKEY_CURRENT_USER if entry.get("root") == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        run_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        disabled_path = r"Software\RAM Optimiser\Disabled Startup"
        name = str(entry["name"])
        if enable:
            with winreg.OpenKey(root, disabled_path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as backup:
                value, kind = winreg.QueryValueEx(backup, name)
            with winreg.CreateKeyEx(root, run_path, 0, winreg.KEY_SET_VALUE) as run_key:
                winreg.SetValueEx(run_key, name, 0, kind, value)
            with winreg.OpenKey(root, disabled_path, 0, winreg.KEY_SET_VALUE) as backup:
                winreg.DeleteValue(backup, name)
            return True, f"Restored {name} to the Windows Run key."
        with winreg.OpenKey(root, run_path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as run_key:
            value, kind = winreg.QueryValueEx(run_key, name)
            with winreg.CreateKeyEx(root, disabled_path, 0, winreg.KEY_SET_VALUE) as backup:
                winreg.SetValueEx(backup, name, 0, kind, value)
            winreg.DeleteValue(run_key, name)
        return True, f"Moved {name} to RAM Optimiser's reversible disabled-startup backup."
    except (OSError, PermissionError) as exc:
        return False, f"Windows could not update this entry: {exc}"


def set_run_at_logon(enabled: bool) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Starting with Windows is available only on Windows."
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                if getattr(sys, "frozen", False):
                    command = f'"{sys.executable}"'
                else:
                    command = f'"{sys.executable}" -m ram_optimiser'
                winreg.SetValueEx(key, "RAM Optimiser", 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, "RAM Optimiser")
                except FileNotFoundError:
                    pass
        return True, "Windows sign-in preference updated."
    except (OSError, PermissionError) as exc:
        return False, f"Could not update the Windows sign-in setting: {exc}"

