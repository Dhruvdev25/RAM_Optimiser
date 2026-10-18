# RAM Optimiser

RAM Optimiser is a local-first Windows desktop utility for system monitoring, cautious memory working-set requests, process inspection, startup review, game-session tracking, and local performance history.

## Install

See [INSTALLATION.md](INSTALLATION.md) for setup, launch, and uninstall steps. The installer is designed for the current Windows user and does not request administrator access. The desktop shortcut is optional. It does not configure automatic startup or launch the app after installation.

## Features and permissions

| Feature | What it does | Permissions and limits |
| --- | --- | --- |
| PC Monitor | Reads CPU, RAM, disk, process count, and available GPU data. | Ordinary monitoring does not require administrator access. CPU/GPU temperatures appear only when supported sensors expose them. NVIDIA GPU readings require a supported NVIDIA driver and NVML; other GPU vendors may show Unavailable. |
| Smart Boost | Requests Windows working-set trimming for eligible processes, then reports measured before/after memory and operation outcomes. | Does not terminate applications. Windows may deny access; a successful request does not prove physical RAM was reclaimed. Trimmed apps may reload data. Windows already manages memory automatically. |
| Automatic Boost | Optionally checks memory pressure and can request the conservative Boost mode after the configured threshold/cooldown. | Off by default. The user controls threshold, interval, cooldown, and approval-before-action. It never closes apps. |
| Process Manager | Inspects processes; supports explicit trim, graceful close, and separately confirmed force termination. | Process identity is checked before actions. Windows may deny operations. Force termination can lose unsaved work; use only for a process you selected and understand. Protected Windows processes and RAM Optimiser cannot be acted on. |
| Game Mode | Tracks a selected executable, measures supported system metrics, records sessions, and suggests high-memory background apps. | Suggestions do not close apps. Any close action requires user selection and confirmation. No FPS improvement is promised. |
| Startup Apps | Inspects standard Windows Run-key entries and can disable/restore supported entries using a reversible backup value. | Publisher and startup impact are not inferred. A machine-wide entry may require permissions Windows does not grant; the app does not silently elevate or edit services. |
| Start with Windows | Optional per-user sign-in entry. | Disabled by default; when enabled, writes a per-user Run-key value. |
| Tray mode and history | Offers tray access and stores bounded metric, Boost, and game-session history locally. | No account, analytics, ads, telemetry, or required network connection. Settings and history are stored in `%LOCALAPPDATA%\RAM Optimiser`. Uninstall leaves this personal data in place. |

## Requirements

- Windows 10 or Windows 11, 64-bit.
- No separate Python, Qt, or Visual C++ runtime installation is required for the packaged one-file build. GPU readings are optional and depend on supported hardware/driver support.

## Privacy

Measurements and application history stay on this computer. See [PRIVACY.md](PRIVACY.md) and [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Review logs before sharing them because they may contain device or process names.

## License and notices

The project source is licensed under MIT; see [LICENSE](LICENSE). Third-party components have their own terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the included `LICENSES` directory. Verify Qt licensing, notices, and relinking requirements for the final binary before public redistribution. This notice is not legal advice.

## Release status

This is version 1.0.0. The executable is unsigned. It was smoke-tested on the development Windows 11 host; that does not establish clean-machine compatibility across Windows 10/11 or hardware. See [TESTING.md](TESTING.md) for the exact verification status and remaining checks.


## Run from source

Requires Windows 10/11 x64 and Python 3.10 or later.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[gpu,test]"
python -m ram_optimiser
```

NVIDIA GPU metrics are optional. Install the `gpu` extra only if you need them. Settings and history are written under `%LOCALAPPDATA%\RAM Optimiser`.

## Build from source

```powershell
python -m pip install -e ".[build,gpu,test]"
python scripts\generate_icon.py
python -m unittest discover -s tests -v
python -m PyInstaller --noconfirm --distpath release pyinstaller.spec
```

This creates `release\RAM Optimiser.exe`. The Windows setup installer is distributed separately as a GitHub Release asset; do not commit installer or application binaries to the source repository.
