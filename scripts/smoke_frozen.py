"""Launch the packaged Windows executable offscreen and require a clean exit."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import psutil


def main():
    root = Path(__file__).resolve().parents[1]
    executable = root / "release" / "RAM Optimiser.exe"
    if not executable.exists():
        raise FileNotFoundError(executable)
    with tempfile.TemporaryDirectory(prefix="ram-optimiser-frozen-") as local_data:
        environment = os.environ.copy()
        diagnostics = Path(local_data) / "smoke-diagnostics.txt"
        environment.update({
            "QT_QPA_PLATFORM": "offscreen",
            "LOCALAPPDATA": local_data,
            "RAM_OPTIMISER_SMOKE_TEST": "1",
            "RAM_OPTIMISER_SMOKE_DIAGNOSTICS": str(diagnostics),
        })
        process = subprocess.Popen([str(executable)], env=environment)
        try:
            exit_code = process.wait(timeout=30)
        except subprocess.TimeoutExpired as exc:
            try:
                parent = psutil.Process(process.pid)
                children = parent.children(recursive=True)
                for child in children:
                    child.terminate()
                psutil.wait_procs(children, timeout=5)
                parent.terminate()
                parent.wait(5)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            diagnostic_text = diagnostics.read_text(encoding="utf-8") if diagnostics.exists() else "No in-app diagnostics were written."
            raise RuntimeError(f"Frozen app did not finish its timed smoke test within 30 seconds. Diagnostics:\n{diagnostic_text}") from exc
        if exit_code != 0:
            raise RuntimeError(f"Frozen app exited with code {exit_code}")
    print(f"Frozen launch passed: {executable}")


if __name__ == "__main__":
    main()
