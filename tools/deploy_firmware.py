"""Copy the firmware and the shared capno_core package onto a mounted CIRCUITPY drive.

    python tools/deploy_firmware.py /media/$USER/CIRCUITPY
Also install the Adafruit bundle libraries neopixel and adafruit_dps310 into
CIRCUITPY/lib (circup install neopixel adafruit_dps310).
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    dest = Path(args[0])
    if not (dest / "boot_out.txt").exists():
        sys.exit(f"{dest} does not look like a CIRCUITPY drive (no boot_out.txt)")
    lib = dest / "lib" / "capno_core"
    if lib.exists():
        shutil.rmtree(lib)
    lib.mkdir(parents=True)
    for f in (ROOT / "capno_core").glob("*.py"):
        shutil.copy2(f, lib / f.name)
    for name in ("sensors.py", "config.py", "code.py"):   # code.py last: it restarts the board
        target = dest / name
        if name == "config.py" and target.exists() and "--overwrite-config" not in sys.argv:
            print("keeping existing config.py on the board")
            continue
        shutil.copy2(ROOT / "firmware" / name, target)
    print("deployed to", dest)


if __name__ == "__main__":
    main()
