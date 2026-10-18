# Troubleshooting RAM Optimiser

## The app does not start

- Source installs need Python 3.10+, PySide6, and psutil. Reinstall with `python -m pip install -e ".[gpu]"`.
- If Windows blocks an unsigned executable, use the source setup in `README.md` or build from this source. This project does not claim digital signing.
- Check `%LOCALAPPDATA%\RAM Optimiser\ram-optimiser.log` if the GUI recorded a startup or operation failure.

## A reading says Unavailable

Temperature values appear only when the OS or driver exposes a supported sensor. GPU readings currently use NVIDIA NVML and require a supported NVIDIA GPU/driver plus `nvidia-ml-py`; other GPU vendors remain unavailable. Storage can be unavailable if the selected drive is disconnected or inaccessible.

## A Boost request fails or available memory does not increase

Windows can refuse a process handle because of process protection or permissions. The result reports API calls accepted and failed, plus measured available memory before and after. A successful trim API call does not prove that a specific amount of physical RAM was reclaimed. Windows can keep, discard, or later reload pages.

## Process actions

Refresh Process Manager when an app exits or restarts. Actions compare both PID and process start time to reduce the risk of acting on a reused PID. Graceful close sends `WM_CLOSE` to top-level windows; a background process without a window is left running. Force terminate can discard unsaved data and always has a separate warning.

## Startup entries

Only standard Windows Run-key entries are listed. Publisher and impact data are not inferred. Editing a machine-wide entry may be refused without administrator access; the entry remains unchanged when that happens. Disable operations are reversible through the disabled entry's Enable action.

