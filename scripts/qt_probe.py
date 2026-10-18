"""Tiny frozen Qt import probe used to validate the local PyInstaller toolchain."""
import sys
from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QApplication, QLabel

app = QApplication(sys.argv)
label = QLabel(f"Qt {qVersion()} loaded")
label.show()
app.processEvents()
print(label.text())
