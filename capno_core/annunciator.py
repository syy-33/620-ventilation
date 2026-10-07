"""Indicator and tone patterns (ER-7, Figure 3).

Pure timing logic: given the display state and the time, return the colour of
each ring pixel and the tone frequency to play right now (0 for silence). The
firmware applies these to the NeoPixel ring and the PAM8302 amplifier; the
tests check the patterns without hardware.

Pulse patterns follow the spirit of IEC 60601-1-8: a high priority burst has
ten pulses, a medium priority burst three, and a technical notice is a single
short chirp. The light flashes faster the higher the priority.
"""

N_PIXELS = 16

GREEN = (0, 255, 0)
AMBER = (255, 120, 0)
RED = (255, 0, 0)
CYAN = (0, 200, 255)
WHITE = (60, 60, 60)
OFF = (0, 0, 0)

# (pulse offsets in ms, pulse length ms, frequency Hz, burst repeat ms)
CRITICAL_TONE = ((0, 200, 400, 800, 1000, 1800, 2000, 2200, 2600, 2800), 125, 880, 10000)
ADVISORY_TONE = ((0, 250, 500), 200, 660, 20000)
TECHNICAL_TONE = ((0,), 60, 1320, 15000)

PATTERNS = {
    # state: (colour, flash period ms or 0 for steady, tone)
    "CRITICAL": (RED, 500, CRITICAL_TONE),
    "ADVISORY": (AMBER, 1400, ADVISORY_TONE),
    "TECHNICAL": (CYAN, 0, TECHNICAL_TONE),
    "NORMAL": (GREEN, 0, None),
    "STANDBY": (WHITE, 0, None),
    "CONFIRMING": (WHITE, 0, None),
}


def tone_at(tone, dt):
    """Frequency to play ``dt`` ms after the pattern started, or 0."""
    if tone is None:
        return 0
    offsets, length, freq, repeat = tone
    phase = dt % repeat
    for o in offsets:
        if o <= phase < o + length:
            return freq
    return 0


class Annunciator:
    def __init__(self):
        self.state = None
        self.since = 0

    def update(self, t, display, paused=False, confirm_count=0, confirm_needed=6):
        if display != self.state:
            self.state = display
            self.since = t
        colour, flash, tone = PATTERNS[display]
        dt = t - self.since
        if flash and (dt % flash) >= flash // 2:
            colour = OFF
        if display == "CONFIRMING":
            lit = max(1, (N_PIXELS * confirm_count) // max(1, confirm_needed))
            pixels = [colour if i < lit else OFF for i in range(N_PIXELS)]
        else:
            pixels = [colour] * N_PIXELS
        hz = 0 if paused else tone_at(tone, dt)
        return pixels, hz
