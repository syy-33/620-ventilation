"""On-board demonstration signal: no CO2 sensor needed.

Produces a believable CO2 trace so the lights, tones, button and laptop link
can be checked before the sensor is wired. Every record it produces carries
sensor "demo", and the dashboard shows a DEMO DATA banner, so demo data can
never be mistaken for a measurement.

The 5-minute cycle shows each alarm in turn:
  0-150 s   normal breathing, 12 /min, 5 % (green once 6 breaths are seen)
  150-240 s CO2 falls to 2.5 % (amber "falling" advisory)
  240-270 s circuit disconnected (red CO2 LOST; press the button to acknowledge)
  270-300 s breathing returns (red clears once acknowledged, then green)
"""

import math

CYCLE_MS = 300000
ROOM = 0.04


def capnogram(phase, et):
    """CO2 at the airway for breath phase in [0, 1). Expiration is the first 2/3."""
    exp_frac = 2.0 / 3.0
    if phase < exp_frac:
        x = phase / exp_frac
        return et * (1.0 - math.exp(-x / 0.06)) * (0.88 + 0.12 * x)
    x = (phase - exp_frac) / (1.0 - exp_frac)
    return et * math.exp(-x / 0.03)


def demo_airway(t_ms):
    """(CO2 at the airway, label) at time t_ms."""
    c = t_ms % CYCLE_MS
    rr = 12.0
    phase = (t_ms * rr / 60000.0) % 1.0
    if c < 150000:
        return ROOM + capnogram(phase, 5.0), "normal"
    if c < 240000:
        et = 5.0 - 2.5 * min(1.0, (c - 150000) / 60000.0)
        return ROOM + capnogram(phase, et), "falling"
    if c < 270000:
        return ROOM, "disconnected"
    return ROOM + capnogram(phase, 4.5), "recovering"


class DemoCO2:
    """Same interface as the hardware drivers: poll(t) -> (value or None, error)."""

    period_ms = 50          # 20 Hz, like a fast sidestream module
    tau_ms = 300.0          # sensor lag

    def __init__(self):
        self.errors = 0
        self.last_t = None
        self.reading = ROOM
        self.label = None

    def poll(self, t):
        if self.last_t is not None and t - self.last_t < self.period_ms:
            return None, False
        dt = 0 if self.last_t is None else t - self.last_t
        self.last_t = t
        air, self.label = demo_airway(t)
        self.reading += (air - self.reading) * (1.0 - math.exp(-dt / self.tau_ms))
        return self.reading, False
