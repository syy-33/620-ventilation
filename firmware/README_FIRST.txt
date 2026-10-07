EXSU 620 Project 06 - files for the Raspberry Pi Pico 2 W
==========================================================

Everything in this folder goes onto the CIRCUITPY drive, exactly as it is.

1. Install CircuitPython on the Pico 2 W (once only):
   - Download the .UF2 file for "Raspberry Pi Pico 2 W" from
     https://circuitpython.org/board/raspberry_pi_pico2_w/
   - Hold the white BOOTSEL button on the Pico, plug it into the computer,
     then let go. A drive called RP2350 appears.
   - Drag the .UF2 file onto that drive. The Pico restarts and a drive
     called CIRCUITPY appears.

2. Copy ALL files and the "lib" folder from here onto CIRCUITPY.
   Say "Replace" if asked. The Pico restarts by itself.

3. You should see the light ring flash green, amber, red, cyan with beeps,
   then dim white. In demo mode it turns green after about 30 seconds, and
   goes amber then red during each 5-minute demo cycle. Press the button
   briefly to acknowledge the red alarm.

4. To use the real CO2 sensor, open config.py on CIRCUITPY in a text editor,
   change SENSOR = "demo" to your sensor, and save.

Full guide with pictures of the wiring: docs/10_flashing_guide.md in the repository.
