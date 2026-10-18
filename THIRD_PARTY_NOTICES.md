# Third-party notices

RAM Optimiser depends on the following projects:

- **PySide6 / Qt for Python 6.8.3** — LGPLv3/GPLv2/GPLv3 and commercial licensing options. The application uses the Python bindings dynamically and does not modify Qt. Qt has additional third-party notices; see the [Qt for Python license list](https://doc.qt.io/qtforpython-6/licenses.html) and [Qt for Python licensing overview](https://doc.qt.io/qtforpython-6/). Qt libraries in the frozen build remain subject to their applicable licenses and relinking requirements.
- **psutil 7.2.2** — BSD 3-Clause license. The exact license text used for this build is in `LICENSES/psutil-BSD-3-Clause.txt`.
- **nvidia-ml-py 13.615.71** (optional) — NVIDIA Python bindings for NVML under BSD 3-Clause; the text used for this build is in `LICENSES/nvidia-ml-py-BSD-3-Clause.txt`.
- **PyInstaller 6.22.3** (build-only) — GPL-2.0-or-later with the bootloader exception; its runtime hooks and additional runtime modules are Apache-2.0, and the isolated submodule is MIT, as detailed in `LICENSES/PyInstaller-COPYING.txt`. Frozen applications may be distributed under the application's chosen license provided dependency terms are met; see [PyInstaller's license explanation](https://pyinstaller.org/en/stable/license.html).

The source project license is MIT (see `LICENSE`). The checked-in version strings and texts describe the development build; regenerate dependency notices from the exact wheel versions used for any later release. The PyInstaller executable is not digitally signed. This notice is an inventory, not legal advice; public redistribution should verify the selected Qt license and the final Qt DLL/plugin set.
