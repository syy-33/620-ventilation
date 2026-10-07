# Bedside unit configuration. This is the only file you normally edit on the Pico.
# Open it from the CIRCUITPY drive in any text editor, change a value, save:
# the board restarts by itself with the new setting.

# ---------------------------------------------------------------------------
# 1. WHICH CO2 SENSOR IS CONNECTED
# ---------------------------------------------------------------------------
#   "demo"  - no sensor needed. Built-in fake breathing signal that cycles
#             through green, amber and red so you can check the lights, the
#             speaker, the button and the laptop link. Every record says
#             "demo" and the dashboard shows DEMO DATA. Never use for tests.
#   "scd30" - Sensirion / Adafruit SCD30, plugged into the Grove I2C1 port
#             with the Grove to STEMMA QT cable.
#   "gss"   - GSS SprintIR-WF-20 or ExplorIR-W, wired to the Grove UART0 port.
#   "mhz"   - Winsen MH-Z16 / MH-Z19 family, wired to the Grove UART0 port.
SENSOR = "demo"

GSS_UNFILTERED = True        # gss only: faster unfiltered 'z' readings
MHZ_POLL_MS = 500            # mhz only

# Static calibration, from: python -m capno_analysis.calibration fit (ER-6)
CO2_GAIN = 1.0
CO2_OFFSET_PCT = 0.0

# ---------------------------------------------------------------------------
# 2. OPTIONAL PARTS NOT IN THE STANDARD KIT
# ---------------------------------------------------------------------------
# Two DPS310 pressure sensors measure suction in the sampling line, which is
# how a blocked line is told apart from apnoea (CR-3). Without them the device
# says "line NOT monitored" and CR-3 must be reported as not met.
PRESSURE_SENSORS = False
PRESSURE_LINE_ADDR = 0x77
PRESSURE_AMBIENT_ADDR = 0x76
PRESSURE_PERIOD_MS = 200

# Sampling pump switched by a MOSFET on GP22. Leave False if the pump is
# wired straight to 5 V (always on) or there is no pump.
PUMP_SWITCHED = False

PIXEL_BRIGHTNESS = 0.3

# ---------------------------------------------------------------------------
# 3. MEASURED RESPONSE (fill in after the step tests, VP-5)
# ---------------------------------------------------------------------------
# Run: python -m capno_analysis.profile build <results.csv> --line-length <m> ...
# and paste the three lines it prints. Until then they stay None / 0.0 and the
# device makes no breath-by-breath claim.
MONITOR = {
    "t10_90_ms": None,
    "delay_ms": None,
    "max_resolvable_rr": 0.0,
    # --- sampling line (only used when PRESSURE_SENSORS = True) ---
    "line_monitored": PRESSURE_SENSORS,
    "line_vac_nominal_kpa": 10.0,   # read "vac" from the serial output with a clear line
}
