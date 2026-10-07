"""Copy the bundle straight onto a mounted CIRCUITPY drive.

    python tools/deploy_firmware.py /media/$USER/CIRCUITPY      (Linux)
    python tools/deploy_firmware.py /Volumes/CIRCUITPY          (macOS)
    python tools/deploy_firmware.py E:\\                        (Windows)

Keeps the config.py already on the board (your sensor choice and measured
profile) unless you add --overwrite-config. You can also simply unzip
firmware/pico-firmware.zip and drag the files across.
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pico_bundle import bundle_files  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    dest = Path(args[0])
    if not (dest / "boot_out.txt").exists():
        sys.exit(f"{dest} does not look like a CIRCUITPY drive (no boot_out.txt)")
    files = bundle_files()
    # code.py last: saving it restarts the board
    for rel in sorted(files, key=lambda r: r == "code.py"):
        target = dest / rel
        if rel == "config.py" and target.exists() and "--overwrite-config" not in sys.argv:
            print("keeping the config.py already on the board")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(files[rel], target)
    print("deployed to", dest)


if __name__ == "__main__":
    main()
