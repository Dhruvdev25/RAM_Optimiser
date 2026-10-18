"""Inspect DLL imports and exports for a selected PE file."""
import sys
from pathlib import Path

import pefile

pe = pefile.PE(sys.argv[1], fast_load=True)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
for dependency in getattr(pe, "DIRECTORY_ENTRY_IMPORT", ()):
    print(dependency.dll.decode(errors="replace"))
    for entry in dependency.imports:
        if entry.name:
            print("  " + entry.name.decode(errors="replace"))
