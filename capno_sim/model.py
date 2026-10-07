"""Physical model of airway -> sampling line -> sensor cell -> NDIR reading.

* Airway: square-ish capnogram (phase II upstroke, sloped plateau, fast
  inspiratory downstroke), I:E 1:2, end-tidal value and rate per segment.
* Sampling line: pure transport delay (line volume / pump flow). Blocked: gas
  in the cell stops being replaced. Open at the instrument: the cell samples
  room air directly.
* Sensor: first-order lag with time constant tau = t10-90 / ln 9, white noise,
  fixed sample rate. "silent" emits nothing.
* Pump inlet vacuum: nominal, high when blocked, low when open.
"""

import math
import random

ROOM = 0.04


def _interp(v, frac):
    if isinstance(v, (tuple, list)):
        return v[0] + (v[1] - v[0]) * frac
    return v


class Segment:
    """One stretch of a scenario.

    rr, et may be scalars or (start, end) tuples for linear ramps.
    airway: "patient" (exhaled gas reaches the line), "room" (disconnected
            circuit or oesophageal tube with no CO2), "gastric" (decaying CO2),
            "gas" (line inlet held in a constant concentration ``et``: step tests).
    line:   "ok", "blocked", "open".
    sensor: "ok", "silent".
    """

    def __init__(self, duration_s, rr=12.0, et=5.0, airway="patient", line="ok",
                 sensor="ok", label=None, command=None, button=None):
        self.duration_s = duration_s
        self.rr = rr
        self.et = et
        self.airway = airway
        self.line = line
        self.sensor = sensor
        self.label = label
        self.command = command
        self.button = button


def capnogram(phase, et):
    """CO2 at the airway for breath phase in [0, 1). Expiration first 2/3."""
    exp_frac = 2.0 / 3.0
    if phase < exp_frac:
        x = phase / exp_frac
        rise = 1.0 - math.exp(-x / 0.06)          # phase II upstroke
        plateau = 0.88 + 0.12 * x                 # phase III slope
        return et * rise * plateau
    x = (phase - exp_frac) / (1.0 - exp_frac)
    return et * math.exp(-x / 0.03)               # inspiratory downstroke


class Rig:
    def __init__(self, t10_90_s=0.3, delay_s=1.0, fs=20.0, noise_pct=0.02,
                 vac_nominal=10.0, seed=1):
        self.tau = t10_90_s / math.log(9.0)
        self.delay_s = delay_s
        self.fs = fs
        self.noise = noise_pct
        self.vac_nominal = vac_nominal
        self.rng = random.Random(seed)
        self.phase = 0.0
        self.gastric = 0.0
        self.history = []        # (t, airway co2) for the transport delay
        self.cell = ROOM
        self.reading = ROOM

    def run(self, segments, dt_s=0.005):
        """Yield (t_ms, co2_or_None, vac, segment, segment_start_flag)."""
        t = 0.0
        next_sample = 0.0
        period = 1.0 / self.fs
        for seg in segments:
            start = t
            first = True
            if seg.airway == "gastric":
                self.gastric = 1.0
            while t < start + seg.duration_s - 1e-9:
                frac = (t - start) / seg.duration_s
                rr = _interp(seg.rr, frac)
                et = _interp(seg.et, frac)
                if rr > 0:
                    self.phase = (self.phase + dt_s * rr / 60.0) % 1.0
                if seg.airway == "patient" and rr > 0:
                    air = ROOM + capnogram(self.phase, et)
                elif seg.airway == "gastric" and rr > 0:
                    air = ROOM + capnogram(self.phase, et * self.gastric)
                    if self.phase < dt_s * rr / 60.0:
                        self.gastric *= 0.6              # washout per breath
                elif seg.airway == "gas":
                    air = ROOM + et
                else:
                    air = ROOM
                self.history.append((t, air))
                while len(self.history) > 2 and self.history[1][0] <= t - self.delay_s:
                    self.history.pop(0)
                delayed = self.history[0][1] if self.history[0][0] <= t - self.delay_s else ROOM

                if seg.line == "ok":
                    self.cell = delayed
                    vac = self.vac_nominal
                elif seg.line == "blocked":
                    vac = self.vac_nominal * 3.0         # cell gas is stagnant
                else:
                    self.cell = ROOM
                    vac = self.vac_nominal * 0.2
                self.reading += (self.cell - self.reading) * (1.0 - math.exp(-dt_s / self.tau))

                if t >= next_sample - 1e-9:
                    next_sample += period
                    co2 = None
                    if seg.sensor == "ok":
                        co2 = self.reading + self.rng.gauss(0.0, self.noise)
                    v = vac + self.rng.gauss(0.0, 0.1)
                    yield int(round(t * 1000)), co2, v, seg, first
                    first = False
                t += dt_s
