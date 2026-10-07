"""Classify presses of the single bedside pushbutton.

short  (< 1 s, no second press within 0.4 s)  acknowledge
double (two short presses within 0.4 s)       marker for step tests
long   (2 s to 5 s, on release)               arm: tube or mask placed
hold   (held 5 s, fires while still held)     disarm: end of case
A press between 1 s and 2 s is ignored so a hesitant press does nothing.
"""

DEBOUNCE_MS = 30
SHORT_MAX_MS = 1000
DOUBLE_GAP_MS = 400
LONG_MIN_MS = 2000
HOLD_MS = 5000


class ButtonClassifier:
    def __init__(self):
        self.pressed = False
        self.raw = False
        self.raw_t = 0
        self.down_t = None
        self.hold_fired = False
        self.pending_short_t = None

    def update(self, t, is_pressed):
        """Feed the raw button level; returns an event name or None."""
        if is_pressed != self.raw:
            self.raw = is_pressed
            self.raw_t = t
        if self.raw != self.pressed and t - self.raw_t >= DEBOUNCE_MS:
            self.pressed = self.raw
            if self.pressed:
                self.down_t = t
                self.hold_fired = False
            else:
                return self._released(t)
        if self.pressed and not self.hold_fired and t - self.down_t >= HOLD_MS:
            self.hold_fired = True
            self.pending_short_t = None
            return "hold"
        if self.pending_short_t is not None and not self.pressed \
                and t - self.pending_short_t > DOUBLE_GAP_MS:
            self.pending_short_t = None
            return "short"
        return None

    def _released(self, t):
        dur = t - self.down_t
        if self.hold_fired:
            return None
        if dur < SHORT_MAX_MS:
            if self.pending_short_t is not None:
                self.pending_short_t = None
                return "double"
            self.pending_short_t = t
            return None
        if dur >= LONG_MIN_MS:
            self.pending_short_t = None
            return "long"
        return None
