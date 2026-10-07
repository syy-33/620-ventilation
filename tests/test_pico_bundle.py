"""The committed firmware zip must match the sources, so what you flash is what was tested."""

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from build_pico_bundle import ZIP_PATH, bundle_files  # noqa: E402


def test_zip_is_up_to_date():
    files = bundle_files()
    with zipfile.ZipFile(ZIP_PATH) as z:
        names = {n[len("CIRCUITPY/"):] for n in z.namelist()}
        assert names == set(files), "run: python tools/build_pico_bundle.py"
        for rel, src in files.items():
            assert z.read("CIRCUITPY/" + rel) == src.read_bytes(), \
                f"{rel} is stale in the zip; run: python tools/build_pico_bundle.py"


def test_bundle_has_everything_code_py_imports():
    files = bundle_files()
    for needed in ("code.py", "config.py", "sensors.py", "lib/neopixel.py",
                   "lib/adafruit_scd30.py", "lib/adafruit_dps310/basic.py",
                   "lib/adafruit_bus_device/i2c_device.py", "lib/capno_core/device.py",
                   "lib/capno_core/demo.py"):
        assert needed in files
