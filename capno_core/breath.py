"""Breath detection on a CO2 signal of unknown speed (ER-1, ER-4).

Thresholds adapt to the recent signal envelope, so a slow sensor whose trace
never returns to zero between breaths is still segmented as long as its swing
is larger than ``min_swing_pct``. When the swing collapses (fast breathing on a
slow sensor) no breaths are reported; the monitor then falls back to the
breath-averaged trend rather than inventing a rate.
"""

from .ring import Ring, median


class BreathDetector:
    def __init__(self, cfg):
        self.cfg = cfg
        n_blocks = max(2, cfg["envelope_ms"] // cfg["block_ms"])
        self.blocks = Ring(n_blocks)          # (lo, hi) per closed block
        self.block_t = None
        self.block_lo = None
        self.block_hi = None
        self.phase = "unknown"                # "high" expiring, "low" inspiring
        self.rise_t = None
        self.peak = None
        self.last_rise_t = None               # last accepted CO2 breath start
        self.intervals = Ring(cfg["rr_intervals"])
        self.last_breath_end_t = None
        self.swing = 0.0

    def reset(self):
        self.__init__(self.cfg)

    def _envelope(self):
        lo = self.block_lo
        hi = self.block_hi
        for i in range(len(self.blocks)):
            b = self.blocks[i]
            if b[0] < lo:
                lo = b[0]
            if b[1] > hi:
                hi = b[1]
        return lo, hi

    def update(self, t, x):
        """Feed one sample. Returns a breath dict when a breath completes."""
        cfg = self.cfg
        if self.block_t is None:
            self.block_t, self.block_lo, self.block_hi = t, x, x
        elif t - self.block_t >= cfg["block_ms"]:
            self.blocks.append((self.block_lo, self.block_hi))
            self.block_t, self.block_lo, self.block_hi = t, x, x
        else:
            if x < self.block_lo:
                self.block_lo = x
            if x > self.block_hi:
                self.block_hi = x

        lo, hi = self._envelope()
        swing = hi - lo
        self.swing = swing
        if swing < cfg["min_swing_pct"]:
            self.phase = "flat"
            return None
        up = lo + cfg["rise_frac"] * swing
        down = lo + cfg["fall_frac"] * swing

        if self.phase == "high":
            if x > self.peak:
                self.peak = x
            if x <= down:
                self.phase = "low"
                return self._complete(t)
        elif x >= up:
            if self.phase == "low":
                self.rise_t = t
            else:
                # Started mid-expiration or after a flat stretch: track it but
                # do not time an interval from an unknown start.
                self.rise_t = None
            self.phase = "high"
            self.peak = x
        elif x <= down:
            self.phase = "low"
        return None

    def _complete(self, t):
        cfg = self.cfg
        peak = self.peak
        rise_t = self.rise_t
        co2 = peak >= cfg["co2_breath_min_pct"]
        interval = None
        if rise_t is not None and co2:
            if self.last_rise_t is not None:
                interval = rise_t - self.last_rise_t
                if interval < cfg["min_breath_interval_ms"]:
                    return None   # artefact inside the refractory period
                if interval > cfg["max_breath_interval_ms"]:
                    # A gap this long is an apnoea or a disconnection, not a
                    # breathing rate: rebuild the rate from fresh breaths.
                    self.intervals.clear()
                    interval = None
                else:
                    self.intervals.append(interval)
            self.last_rise_t = rise_t
        self.last_breath_end_t = t
        return {
            "t": rise_t if rise_t is not None else t,
            "end": t,
            "peak": peak,
            "co2": co2,
            "interval_ms": interval,
        }

    def median_interval_ms(self):
        return median(self.intervals.items())

    def rate(self, t):
        """Median breathing rate per minute, or None when it is not known."""
        if len(self.intervals) < 2 or self.last_rise_t is None:
            return None
        m = median(self.intervals.items())
        if t - self.last_rise_t > 2.5 * m:
            return None
        return 60000.0 / m
