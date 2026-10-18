"""Early Windows DLL search paths for frozen PySide6 builds."""
import os
import sys

if sys.platform == "win32" and hasattr(sys, "_MEIPASS"):
    for _name in ("PySide6", "shiboken6"):
        _path = os.path.join(sys._MEIPASS, _name)
        if os.path.isdir(_path):
            os.add_dll_directory(_path)
            os.environ["PATH"] = _path + os.pathsep + os.environ.get("PATH", "")
