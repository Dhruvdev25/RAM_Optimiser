"""Small, versioned JSON settings store with defensive defaults."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

APP_DIR_NAME = "RAM Optimiser"


def data_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / APP_DIR_NAME
    return Path.home() / ".local" / "share" / "ram-optimiser"


@dataclass
class Settings:
    version: int = 1
    refresh_seconds: int = 2
    drive_path: str = "C:/"
    accent: str = "#48b9ff"
    auto_boost_enabled: bool = False
    auto_boost_threshold: int = 85
    auto_boost_cooldown_minutes: int = 30
    auto_boost_interval_seconds: int = 60
    auto_boost_require_approval: bool = True
    tray_enabled: bool = True
    minimize_to_tray: bool = False
    minimize_during_game: bool = False
    notifications_enabled: bool = True
    start_with_windows: bool = False
    history_retention_days: int = 30
    protected_apps: list[str] = field(default_factory=list)
    eligible_apps: list[str] = field(default_factory=list)
    excluded_apps: list[str] = field(default_factory=list)
    game_executable: str = ""
    game_profiles: list[str] = field(default_factory=list)


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (data_directory() / "settings.json")
        self._lock = RLock()

    def load(self) -> Settings:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    return Settings()
                allowed = Settings.__dataclass_fields__.keys()
                clean = {key: value for key, value in raw.items() if key in allowed}
                settings = Settings(**clean)
                settings.refresh_seconds = max(1, min(30, int(settings.refresh_seconds)))
                settings.auto_boost_threshold = max(50, min(99, int(settings.auto_boost_threshold)))
                settings.auto_boost_cooldown_minutes = max(5, min(1440, int(settings.auto_boost_cooldown_minutes)))
                settings.auto_boost_interval_seconds = max(15, min(600, int(settings.auto_boost_interval_seconds)))
                settings.history_retention_days = max(1, min(365, int(settings.history_retention_days)))
                settings.protected_apps = list(map(str, settings.protected_apps))
                settings.eligible_apps = list(map(str, settings.eligible_apps))
                settings.excluded_apps = list(map(str, settings.excluded_apps))
                settings.game_profiles = list(map(str, settings.game_profiles))
                return settings
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                return Settings()

    def save(self, settings: Settings) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
            temporary.replace(self.path)

