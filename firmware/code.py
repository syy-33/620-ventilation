# Project 06 bedside unit: Raspberry Pi Pico 2 W, CircuitPython 9.
#
# Hardware I/O only. All detection and alarm logic lives in lib/capno_core,
# which is the same code the laptop tests and simulator run. The bedside
# light and tone work with the laptop unplugged (ER-7).
#
# Pins (Grove Shield for Pi Pico):
#   UART0  GP0 TX -> sensor RX, GP1 RX <- sensor TX     CO2 module
#   I2C1   GP6 SDA, GP7 SCL                              2 x DPS310 (STEMMA QT)
#   D16    GP16                                          pushbutton to GND
#   D18    GP18                                          NeoPixel ring 16 data
#   D20    GP20 PWM -> 1k -> PAM8302 A+, GP21 -> SD      speaker amplifier
#   GP22 (breadboard) -> logic-level MOSFET gate         sampling pump (optional)
#
# config.py chooses the sensor ("demo" works with nothing connected).

import json
import sys

import board
import busio
import digitalio
import neopixel
import pwmio
import supervisor

import config
from capno_core.annunciator import AMBER, CYAN, GREEN, RED
from capno_core.button import ButtonClassifier
from capno_core.config import make_config
from capno_core.device import Device
from sensors import GssCO2, LinePressure, MhzCO2, Scd30CO2, now_ms

TICK_MS = 100   # evaluate timers at least this often even without a sample


def emit(rec):
    print(json.dumps(rec))


def self_test(pixels, tone):
    """Power-up check the operator watches and listens to (FM-10)."""
    import time
    for colour, hz in ((GREEN, 0), (AMBER, 660), (RED, 880), (CYAN, 1320)):
        pixels.fill(colour)
        pixels.show()
        if hz:
            tone.frequency = hz
            tone.duty_cycle = 32768
        time.sleep(0.4)
        tone.duty_cycle = 0
        time.sleep(0.1)
    pixels.fill((0, 0, 0))
    pixels.show()


class NoSensor:
    """Stands in when the configured sensor cannot be opened: the monitor then
    reports SENSOR_SILENT (cyan) instead of the program crashing."""
    errors = 0

    def poll(self, t):
        return None, False


def open_co2_sensor(i2c):
    try:
        if config.SENSOR == "demo":
            from capno_core.demo import DemoCO2
            return DemoCO2()
        if config.SENSOR == "scd30":
            return Scd30CO2(i2c)
        uart = busio.UART(board.GP0, board.GP1, baudrate=9600, timeout=0)
        if config.SENSOR == "mhz":
            return MhzCO2(uart, config.MHZ_POLL_MS)
        if config.SENSOR == "gss":
            return GssCO2(uart, config.GSS_UNFILTERED)
        emit({"type": "err", "t": 0, "msg": "config.SENSOR not recognised: " + str(config.SENSOR)})
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        emit({"type": "err", "t": 0, "msg": "CO2 sensor not found: " + repr(exc)})
    return NoSensor()


def main():
    if config.PUMP_SWITCHED:
        pump = digitalio.DigitalInOut(board.GP22)
        pump.switch_to_output(value=True)

    amp_sd = digitalio.DigitalInOut(board.GP21)
    amp_sd.switch_to_output(value=True)
    tone = pwmio.PWMOut(board.GP20, frequency=880, duty_cycle=0, variable_frequency=True)

    pixels = neopixel.NeoPixel(board.GP18, 16, brightness=config.PIXEL_BRIGHTNESS,
                               auto_write=False)
    self_test(pixels, tone)

    button_pin = digitalio.DigitalInOut(board.GP16)
    button_pin.switch_to_input(pull=digitalio.Pull.UP)
    button = ButtonClassifier()

    i2c = None
    if config.SENSOR == "scd30" or config.PRESSURE_SENSORS:
        try:
            i2c = busio.I2C(board.GP7, board.GP6)
        except RuntimeError as exc:      # nothing plugged into the I2C1 port
            emit({"type": "err", "t": 0, "msg": "I2C1 port: " + repr(exc)})

    co2_sensor = open_co2_sensor(i2c)

    line = None
    if config.PRESSURE_SENSORS and i2c is not None:
        line = LinePressure(i2c, config.PRESSURE_LINE_ADDR, config.PRESSURE_AMBIENT_ADDR,
                            config.PRESSURE_PERIOD_MS)

    cfg = make_config(config.MONITOR)
    dev = Device(cfg, {"sensor": config.SENSOR, "gain": config.CO2_GAIN,
                       "offset": config.CO2_OFFSET_PCT})
    boot = now_ms()
    emit(dev.hello(0))

    last_tick = 0
    loop_start = 0
    loop_max = 0
    last_perf = 0
    last_pixels = None
    last_hz = -1
    cmd_buf = ""

    while True:
        t = now_ms() - boot
        # Loop period bounds the time from a triggering sample to light and tone (ER-7).
        if loop_start:
            loop_max = max(loop_max, t - loop_start)
        loop_start = t
        if t - last_perf >= 5000:
            emit({"type": "perf", "t": t, "loop_max_ms": loop_max,
                  "co2_errors": co2_sensor.errors})
            last_perf = t
            loop_max = 0

        raw, err = co2_sensor.poll(t)
        co2 = None
        if raw is not None:
            co2 = raw * config.CO2_GAIN + config.CO2_OFFSET_PCT
        vac = line.poll(t) if line is not None else None

        if co2 is not None or err or t - last_tick >= TICK_MS:
            last_tick = t
            for r in dev.step(t, co2, vac, err):
                emit(r)

        ev = button.update(t, not button_pin.value)
        if ev:
            emit({"type": "btn", "t": t, "kind": ev})
            for r in dev.button(t, ev):
                emit(r)

        n = supervisor.runtime.serial_bytes_available
        if n:
            cmd_buf += sys.stdin.read(n)
            while "\n" in cmd_buf or "\r" in cmd_buf:
                cmd_buf = cmd_buf.replace("\r", "\n")
                line_in, cmd_buf = cmd_buf.split("\n", 1)
                for r in dev.command(t, line_in):
                    emit(r)
            if len(cmd_buf) > 128:
                cmd_buf = ""

        px, hz = dev.outputs(t)
        if px != last_pixels:
            for i in range(len(px)):
                pixels[i] = px[i]
            pixels.show()
            last_pixels = px
        if hz != last_hz:
            if hz:
                tone.frequency = hz
                tone.duty_cycle = 32768
            else:
                tone.duty_cycle = 0
            last_hz = hz


main()
