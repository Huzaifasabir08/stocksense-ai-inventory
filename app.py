"""Compatibility entry point for the complete StockSense project."""
from pathlib import Path
import importlib.util
import runpy
import sys

SOURCE = Path(__file__).resolve().parent / "AI Inventory for a shoping mall" / "app.py"

if __name__ == "__main__":
    runpy.run_path(str(SOURCE), run_name="__main__")
else:
    # Preserve the original import API, including test overrides of app.DB.
    spec = importlib.util.spec_from_file_location(__name__, SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[__name__] = module
    spec.loader.exec_module(module)
