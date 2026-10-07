# Flashing the Raspberry Pi Pico 2 W (beginner guide)

This guide assumes no electronics or programming background. It takes about
20 minutes the first time.

**What you need:** the Pico 2 W (headers already soldered), the 2 m micro USB
cable, a laptop, and the file `firmware/pico-firmware.zip` from this
repository. On GitHub, open the file and click the download button (↓), or use
the green **Code → Download ZIP** button for the whole repository.

> "Flashing" means putting software onto the board. The Pico runs
> **CircuitPython**, which makes the board appear as a USB drive (like a memory
> stick). Our program is a set of ordinary files you copy onto that drive.

---

## Step 1 — Install CircuitPython (once per board)

1. On the laptop, open https://circuitpython.org/board/raspberry_pi_pico2_w/
   and download the latest stable **.UF2** file, English version.
   Make sure the page says **Pico 2 W**: the files for Pico, Pico W and Pico 2
   do not work on this board.
2. Find the small white **BOOTSEL** button on the Pico. **Hold it down**, plug
   the USB cable into the Pico and then the laptop, and let go.
3. A new drive called **RP2350** appears on the laptop.
4. Drag the .UF2 file onto **RP2350**. After a few seconds that drive
   disappears and a new one called **CIRCUITPY** appears. CircuitPython is now
   installed.

If CIRCUITPY appears straight away without holding BOOTSEL, CircuitPython was
already installed. Skip to step 2.

## Step 2 — Copy the project files

1. Unzip `pico-firmware.zip`. Inside is a folder called `CIRCUITPY`.
2. Open that folder, select **everything** in it (`code.py`, `config.py`,
   `sensors.py`, `README_FIRST.txt` and the `lib` folder), and drag it onto the
   **CIRCUITPY** drive. If asked, choose **Replace** or **Merge**.
3. The board restarts by itself after the copy.

On a Mac you may see "the disk was not ejected properly" when the board
restarts. That is normal.

## Step 3 — Check it is running

With nothing wired yet there is no light or sound to see. Instead, look at
the board's text output:

* **Easiest:** install the free **Mu Editor** (https://codewith.mu), choose
  *CircuitPython* mode, and click **Serial**.
* **Or:** install **Thonny** and choose *Tools → Options → Interpreter →
  CircuitPython (generic)*.

You should see lines like these scrolling by, about 20 per second:

```
{"type": "hello", "t": 0, "fw": "0.1.0", "sensor": "demo", ...}
{"type": "s", "t": 1050, "co2": 4.812, "vac": null, "d": "STANDBY"}
```

After about 30 seconds the `"d"` value changes from `STANDBY` to `NORMAL`:
the demo "patient" has been confirmed. Close Mu or Thonny before starting the
laptop dashboard, because only one program can use the connection at a time.

## Step 4 — Wire the light, speaker and button

The standard kit is enough. Keep the Grove shield's power switch on **3V3**
for these first tests.

Seat the Pico in the **Grove Shield for Pi Pico**, with the USB end matching
the outline printed on the shield. Each Grove socket has four pins:

| Grove wire colour | What it is |
|---|---|
| yellow | first signal pin (the GP number on the label) |
| white | second signal pin (the next GP number) |
| red | power (3.3 V) |
| black | ground (GND) |

| Part | Grove port | Connections |
|---|---|---|
| **NeoPixel ring** | **D18** | ring *Data In* to yellow (GP18); ring *PWR / 5V* to red; ring *GND* to black. A 330 Ω resistor from the kit in the data wire is good practice. |
| **PAM8302 amplifier** | **D20** | yellow (GP20) through a **1 kΩ** resistor to **A+**; **A−** to black (GND); white (GP21) to **SD**; **VIN** to red; **GND** to black. Speaker to the two speaker terminals. |
| **Pushbutton** | **D16** | one leg to yellow (GP16), the other leg to black (GND). It does not matter which leg is which. |

The ring and amplifier have solder pads. Solder short wires to them (the kit
includes heat shrink to cover the joints), or use alligator clips for a quick
first test. Use the breadboard and jumper wires between the parts and the
Grove sockets.

Unplug USB while wiring. Plug back in when done. You should now see and hear
the **power-up self-test**: green, amber with a beep, red with a beep, cyan
with a beep. Then the ring goes dim white.

## Step 5 — Watch the demo

`config.py` starts with `SENSOR = "demo"`. A built-in fake breathing signal
runs a 5-minute cycle:

| Time in cycle | You should see |
|---|---|
| 0–30 s | white ring filling up as "breaths" are counted |
| about 30 s | **green**, silent: CO2 confirmed |
| about 3:50 | **amber**, 3 beeps every 20 s: CO2 falling |
| about 4:10 | **red**, flashing, 10 beeps every 10 s: CO2 lost |
| after 4:30 | breathing returns. **Press the button briefly** to acknowledge, and it goes **green** |

Button: short press = acknowledge · hold 2–5 s = arm (airway placed) · hold
5 s = disarm (end of case) · two quick presses = marker.

## Step 6 — Switch to the real CO2 sensor

1. Find the model name printed on your CO2 sensor.
2. Connect it:
   * **SCD30** (has a STEMMA QT socket): the Grove to STEMMA QT cable goes into
     the **I2C1** Grove port.
   * **SprintIR / ExplorIR / MH-Z16 / MH-Z19** (serial wires TX/RX): sensor
     **TX** goes to the Grove **UART0** *white* wire (GP1), sensor **RX** to the
     *yellow* wire (GP0), plus power and ground. Check the sensor's supply
     voltage on its datasheet first, and measure with the multimeter.
3. Open `config.py` **on the CIRCUITPY drive** in a text editor (Notepad,
   TextEdit, Mu or Thonny). Change `SENSOR = "demo"` to `"scd30"`, `"gss"` or
   `"mhz"`, and save. The board restarts with the new setting.
4. If the sensor isn't found, the ring turns **cyan** and the text output
   includes a line like `{"type": "err", "msg": "CO2 sensor not found ..."}`.
   Check the cable and the port.

## Step 7 — Connect the laptop dashboard

See the README section *Running with the bedside unit*. In short:

```bash
python -m capno_service --serial COM5          # Windows (check Device Manager for the COM number)
python -m capno_service --serial /dev/cu.usbmodem1101   # macOS (ls /dev/cu.usbmodem*)
```

Then open http://127.0.0.1:8000. In demo mode the dashboard shows a **DEMO
DATA** warning, so demo data cannot be mistaken for a measurement.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No RP2350 drive appears | Hold BOOTSEL *before* plugging in. Try another cable: some micro USB cables only carry power, not data. |
| CIRCUITPY never appears after copying the .UF2 | Wrong .UF2: it must be the **Pico 2 W** file. |
| Text output shows `ImportError: no module named ...` | The `lib` folder was not copied. Copy everything from the zip's `CIRCUITPY` folder again. |
| Text output shows `SyntaxError` in config.py | A typo while editing. Copy `config.py` from the zip again and redo the change. Quotes must be straight `"`, not curly `“`. |
| Ring stays dark | Check the data wire is on GP18, power and ground are connected, and the arrow on the ring points away from Data In. |
| No sound | Check the 1 kΩ resistor goes to A+, A− to ground, SD to GP21, and turn up the little volume screw on the PAM8302. |
| Ring is **cyan** with a chirp | A technical fault: usually the CO2 sensor is not found or not answering. Read the `err` line in the text output. |
| Dashboard says NO DATA | Mu or Thonny is still connected to the board: close it. Check the port name. |
| Board seems frozen | Unplug and replug USB. The program always restarts from the beginning. |

## For the group's programmer

* Rebuild the zip after changing any firmware or `capno_core` file:
  `python tools/build_pico_bundle.py`. The test `tests/test_pico_bundle.py`
  fails if the committed zip is out of date.
* `python tools/deploy_firmware.py <path to CIRCUITPY>` copies the files and
  keeps the board's existing `config.py`.
* The Adafruit libraries in `firmware/vendor/` are plain `.py` files, so they
  work on any CircuitPython 9 or 10 build. Versions and MIT licences are in
  `firmware/vendor/VERSIONS.txt` and `LICENSES/`.
* `tests/test_firmware_smoke.py` runs `code.py` against fake hardware on the
  laptop. It catches crashes before flashing, but it is not a substitute for
  running on the board.
