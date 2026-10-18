"""Offscreen construction/render smoke check for local UI development."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QWidget

from ram_optimiser.window import MainWindow


def main():
    with tempfile.TemporaryDirectory(prefix="ram-optimiser-ui-") as local_data:
        os.environ["LOCALAPPDATA"] = local_data
        app = QApplication.instance() or QApplication(sys.argv)
        window = MainWindow()
        window.show()
        deadline = time.monotonic() + 12
        while window._snapshot_busy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.05)
        app.processEvents()
        window._monitor_timer.stop()
        root = Path(__file__).resolve().parents[1]
        window.resize(1040, 720)
        app.processEvents()
        small_geometry = (window.width(), window.height(), window.sidebar.width(),
                          window.pages[0][0].width(), window.pages[0][1].width(),
                          window.pages[0][1].minimumSizeHint().width(), window.pages[0][1].layout().minimumSize().width())
        wide_widgets = sorted(((widget.minimumSizeHint().width(), widget.width(), type(widget).__name__, widget.objectName())
                               for widget in window.pages[0][1].findChildren(QWidget)
                               if widget.minimumSizeHint().width() > 300), reverse=True)[:12]
        pixmap = window.grab()
        output = root / "ui-preview-small.png"
        if not pixmap.save(str(output)):
            raise RuntimeError("Could not save offscreen UI preview")
        for index in range(window.stack.count()):
            window._navigate(index)
            app.processEvents()
            window.grab()
        window._navigate(0)
        window.resize(1440, 900)
        app.processEvents()
        full_output = root / "ui-preview.png"
        if not window.grab().save(str(full_output)):
            raise RuntimeError("Could not save full-size UI preview")
        home_container = window.pages[0][1]
        print(f"pages={window.stack.count()} snapshot={'ready' if window._last_snapshot else 'unavailable'} "
              f"small={small_geometry} window={window.size().width()}x{window.size().height()} sidebar={window.sidebar.width()} "
              f"min={window.minimumWidth()}x{window.minimumHeight()} hint={window.minimumSizeHint().width()} "
              f"content={window.findChild(QWidget, 'mainContent').width()} stackMin={window.stack.minimumSizeHint().width()} "
              f"scrollMin={window.pages[0][0].minimumSizeHint().width()} containerMin={home_container.minimumSizeHint().width()} page={home_container.width()} "
              f"wideWidgets={wide_widgets} previews={output},{full_output}")
        window.close()
        QThreadPool.globalInstance().waitForDone(5000)
        app.processEvents()
        app.quit()


if __name__ == "__main__":
    main()
