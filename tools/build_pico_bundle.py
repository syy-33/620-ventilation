"""Assemble everything that goes on the Pico's CIRCUITPY drive.

    python tools/build_pico_bundle.py            # writes dist/CIRCUITPY/ and firmware/pico-firmware.zip

Layout produced (copy the contents of dist/CIRCUITPY onto the drive):
    code.py  config.py  sensors.py  README_FIRST.txt
    lib/capno_core/*.py                  shared detection and alarm logic
    lib/neopixel.py, adafruit_scd30.py, adafruit_dps310/, adafruit_bus_device/,
    adafruit_register/                   Adafruit libraries (MIT, see lib/LICENSES)
"""

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FW = ROOT / "firmware"
ZIP_PATH = FW / "pico-firmware.zip"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def bundle_files():
    """Map of path on CIRCUITPY -> source file."""
    files = {}
    for name in ("code.py", "config.py", "sensors.py", "README_FIRST.txt"):
        files[name] = FW / name
    for f in sorted((ROOT / "capno_core").glob("*.py")):
        files[f"lib/capno_core/{f.name}"] = f
    vendor = FW / "vendor"
    for f in sorted(vendor.rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts:
            files["lib/" + f.relative_to(vendor).as_posix()] = f
    return files


def build_dir(dest):
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    for rel, src in bundle_files().items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    return dest


def build_zip(path=ZIP_PATH):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, src in bundle_files().items():
            info = zipfile.ZipInfo("CIRCUITPY/" + rel, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, src.read_bytes())
    return path


def main():
    out = build_dir(ROOT / "dist" / "CIRCUITPY")
    z = build_zip()
    print(f"wrote {out}/ and {z} ({z.stat().st_size // 1024} KB, {len(bundle_files())} files)")


if __name__ == "__main__":
    sys.exit(main())
