import os
import sys
import traceback


def _smoke_note(message):
    diagnostics = os.environ.get("RAM_OPTIMISER_SMOKE_DIAGNOSTICS")
    if diagnostics:
        try:
            with open(diagnostics, "a", encoding="utf-8") as stream:
                stream.write(message + "\n")
        except OSError:
            pass


if __name__ == "__main__":
    _smoke_note("entry point started")
    try:
        from ram_optimiser.app import main
        _smoke_note("application module imported")
    except BaseException:
        details = traceback.format_exc()
        _smoke_note(details)
        if sys.stderr:
            sys.stderr.write(details)
        raise
    raise SystemExit(main())
