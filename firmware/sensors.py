# Hardware drivers for the bedside unit (CircuitPython only).

import time


def now_ms():
    return time.monotonic_ns() // 1000000


class GssCO2:
    """GSS SprintIR-WF-20 / ExplorIR-W in streaming mode (9600 8N1).

    Commands used (GSS user manual, verify against your module's datasheet):
      "K 1"  streaming mode
      "M 6"  output both filtered 'Z' and unfiltered 'z' CO2 fields
      "."    read the ppm multiplier (10 for 20 % modules)
    """

    def __init__(self, uart, unfiltered=True):
        self.uart = uart
        self.key = "z" if unfiltered else "Z"
        self.buf = b""
        self.multiplier = 10
        self.errors = 0
        self._send("K 2")       # polling while we configure
        time.sleep(0.1)
        self.uart.reset_input_buffer()
        self._send(".")
        time.sleep(0.2)
        line = self.uart.readline()
        if line:
            try:
                parts = line.decode().split()
                if parts and parts[0] == ".":
                    self.multiplier = int(parts[1])
            except (ValueError, IndexError, UnicodeError):
                pass
        self._send("M 6")
        time.sleep(0.1)
        self._send("K 1")
        self.uart.reset_input_buffer()

    def _send(self, cmd):
        self.uart.write((cmd + "\r\n").encode())

    def poll(self, t):
        """Return (latest CO2 % or None, comms_error flag)."""
        n = self.uart.in_waiting
        if n:
            self.buf += self.uart.read(n)
        value = None
        err = False
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            try:
                parts = line.decode().split()
            except UnicodeError:
                err = True
                continue
            for i in range(0, len(parts) - 1, 2):
                if parts[i] == self.key:
                    try:
                        ppm = int(parts[i + 1]) * self.multiplier
                        value = ppm / 10000.0
                    except ValueError:
                        err = True
        if len(self.buf) > 256:
            self.buf = b""
            err = True
        if err:
            self.errors += 1
        return value, err


class MhzCO2:
    """Winsen MH-Z16 / MH-Z19 family, 9600 8N1, command 0x86 read concentration."""

    CMD = bytes((0xFF, 0x01, 0x86, 0, 0, 0, 0, 0, 0x79))

    def __init__(self, uart, poll_ms=500):
        self.uart = uart
        self.poll_ms = poll_ms
        self.last_poll = -poll_ms
        self.errors = 0

    def poll(self, t):
        value = None
        err = False
        if self.uart.in_waiting >= 9:
            frame = self.uart.read(9)
            if frame and len(frame) == 9 and frame[0] == 0xFF and frame[1] == 0x86:
                csum = (0xFF - (sum(frame[1:8]) & 0xFF) + 1) & 0xFF
                if csum == frame[8]:
                    value = (frame[2] * 256 + frame[3]) / 10000.0
                else:
                    err = True
            else:
                err = True
                self.uart.reset_input_buffer()
        if t - self.last_poll >= self.poll_ms:
            self.last_poll = t
            self.uart.write(self.CMD)
        if err:
            self.errors += 1
        return value, err


class Scd30CO2:
    """Sensirion SCD30 (Adafruit STEMMA QT breakout), I2C address 0x61.

    A diffusion NDIR sensor: it must sit in a small sealed chamber at the end
    of the sampling line. It reports at most every 2 s, its range is 0-4 %
    (end-tidal CO2 around 5 % will clip) and it responds over tens of seconds.
    Expect the measured profile to say TREND_ONLY. Automatic self-calibration
    is switched off because it assumes the sensor regularly sees fresh air
    for days, which would pull the zero during a session.
    """

    def __init__(self, i2c):
        import adafruit_scd30
        self.scd = adafruit_scd30.SCD30(i2c)
        self.scd.self_calibration_enabled = False
        self.scd.measurement_interval = 2
        self.errors = 0

    def poll(self, t):
        try:
            if self.scd.data_available:
                return self.scd.CO2 / 10000.0, False
        except (OSError, RuntimeError):
            self.errors += 1
            return None, True
        return None, False


class LinePressure:
    """Sampling line vacuum from two DPS310 sensors (ambient minus pump inlet)."""

    def __init__(self, i2c, line_addr, ambient_addr, period_ms):
        self.line = None
        self.ambient = None
        self.period_ms = period_ms
        self.last_t = -period_ms
        self.value = None
        try:
            from adafruit_dps310.basic import DPS310
            self.line = DPS310(i2c, address=line_addr)
            self.ambient = DPS310(i2c, address=ambient_addr)
        except (OSError, ValueError, RuntimeError, ImportError):
            self.line = None
            self.ambient = None

    def poll(self, t):
        if self.line is None:
            return None
        if t - self.last_t >= self.period_ms:
            self.last_t = t
            try:
                # hPa -> kPa
                self.value = (self.ambient.pressure - self.line.pressure) / 10.0
            except (OSError, RuntimeError):
                self.value = None
        return self.value
