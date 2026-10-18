"""RAM Optimiser desktop entry point."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME, __version__
from .window import MainWindow


def main() -> int:
    smoke_test = os.environ.get("RAM_OPTIMISER_SMOKE_TEST") == "1"
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("RAM Optimiser")
    app.setStyle("Fusion")
    try:
        from pathlib import Path
        icon_path = Path(__file__).resolve().parent / "assets" / "ram_optimiser.svg"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))
        window = MainWindow()
        window.show()
        if smoke_test:
            def finish_smoke_test() -> None:
                window._force_exit = True
                window.close()
                app.quit()

            QTimer.singleShot(1500, finish_smoke_test)
        return app.exec()
    except Exception as exc:
        QMessageBox.critical(None, APP_NAME, f"RAM Optimiser could not start:\n\n{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
