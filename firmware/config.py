# Bedside unit configuration. Copied to the root of CIRCUITPY by tools/deploy_firmware.py.
#
# The four "instrument response" numbers below MUST come from your own step
# tests (docs/06_verification_plan.md, VP-5). Run
#     python -m capno_analysis.profile build <results.csv> --line-length <m>
# and paste the block it prints. Until then they stay None / 0.0, and the
# monitor and dashboard both state that the response time is unmeasured and
# make no breath-by-breath claim.

# Which CO2 module is fitted:
#   "gss" - GSS SprintIR-WF-20 or ExplorIR-W (0-20 %, UART streaming, ASCII "Z"/"z" frames)
#   "mhz" - Winsen MH-Z16 / MH-Z19 family (binary 0x86 polling; check the range covers 5-8 %)
SENSOR = "gss"
GSS_UNFILTERED = True        # use the faster unfiltered 'z' field instead of 'Z'
MHZ_POLL_MS = 500

# Static calibration, from python -m capno_analysis.calibration (ER-6)
CO2_GAIN = 1.0
CO2_OFFSET_PCT = 0.0

# Two DPS310 barometric sensors: one at the pump inlet, one open to room (ER-3).
# Set False if they are not fitted: the monitor will then say line integrity is unmonitored.
PRESSURE_SENSORS = True
PRESSURE_LINE_ADDR = 0x77
PRESSURE_AMBIENT_ADDR = 0x76
PRESSURE_PERIOD_MS = 200

PIXEL_BRIGHTNESS = 0.3

MONITOR = {
    # --- instrument response (paste from capno_analysis.profile) ---
    "t10_90_ms": None,
    "delay_ms": None,
    "max_resolvable_rr": 0.0,
    # --- sampling line ---
    "line_monitored": PRESSURE_SENSORS,
    "line_vac_nominal_kpa": 10.0,   # read "vac" from the serial output with a clear line
}
