"""Report imports whose named symbols are missing from bundled local DLL candidates."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pefile


def main(root: str) -> None:
    base = Path(root)
    binaries = list(base.rglob("*.dll")) + list(base.rglob("*.pyd"))
    by_name = defaultdict(list)
    for path in binaries:
        by_name[path.name.casefold()].append(path)
    exports = {}
    for path in binaries:
        try:
            pe = pefile.PE(str(path), fast_load=True)
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
            exports[path] = {symbol.name.decode(errors="replace") for symbol in getattr(pe, "DIRECTORY_ENTRY_EXPORT", ()).symbols if symbol.name}
        except Exception:
            exports[path] = set()
    for path in binaries:
        try:
            pe = pefile.PE(str(path), fast_load=True)
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        except Exception:
            continue
        for imported in getattr(pe, "DIRECTORY_ENTRY_IMPORT", ()):
            candidates = by_name.get(imported.dll.decode(errors="replace").casefold(), [])
            if not candidates:
                continue
            missing = [entry.name.decode(errors="replace") for entry in imported.imports if entry.name and not any(entry.name.decode(errors="replace") in exports[candidate] for candidate in candidates)]
            if missing:
                print(f"{path.relative_to(base)} -> {imported.dll.decode(errors='replace')}: {missing[:20]}")


if __name__ == "__main__":
    main(sys.argv[1])
