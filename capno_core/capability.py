"""What the measured response time allows the instrument to claim (ER-5).

The sensor plus sampling line is modelled as a pure transport delay followed by
a first-order lag. The lag time constant is recovered from the measured 10-90 %
rise time (t10-90 = tau * ln 9). A capnogram is approximated as a square wave
between 0 (inspiration) and the end-tidal value (expiration). For a first-order
lag driven by a square wave the steady state peak and trough, as fractions of
the true end-tidal value, are

    peak   = (1 - a) / (1 - a b)      a = exp(-Te / tau)
    trough = peak * b                 b = exp(-Ti / tau)

with Te and Ti the expiratory and inspiratory times. Individual breaths are
called "resolved" when the displayed peak reaches at least ``peak_min`` of the
true end-tidal value and the trough returns below ``trough_max`` of it. The
highest breathing rate that still satisfies both is published as the limit of
breath-by-breath operation; above it the device is a breath-averaged trend
monitor and says so.

The model ignores alveolar plateau slope and line dispersion beyond what the
measured t10-90 already contains, which is why t10-90 must be measured at the
end of the actual sampling line, and why the prediction is checked against the
reference capnograph in the verification plan (VP-5b).
"""

import math

LN9 = math.log(9.0)


def tau_from_t10_90(t10_90_s):
    return t10_90_s / LN9


def periodic_response(rr_per_min, tau_s, exp_frac=2.0 / 3.0):
    """Return (peak, trough) as fractions of the true end-tidal value."""
    period = 60.0 / rr_per_min
    te = period * exp_frac
    ti = period - te
    if tau_s <= 0:
        return 1.0, 0.0
    a = math.exp(-te / tau_s)
    b = math.exp(-ti / tau_s)
    peak = (1.0 - a) / (1.0 - a * b)
    return peak, peak * b


def resolves(rr_per_min, t10_90_s, peak_min=0.9, trough_max=0.1, exp_frac=2.0 / 3.0):
    peak, trough = periodic_response(rr_per_min, tau_from_t10_90(t10_90_s), exp_frac)
    return peak >= peak_min and trough <= trough_max


def max_resolvable_rr(t10_90_s, peak_min=0.9, trough_max=0.1, exp_frac=2.0 / 3.0, rr_ceiling=120.0):
    """Highest breathing rate (per minute) resolved breath by breath.

    Returns 0.0 if the response time is unknown or too slow to resolve even
    one breath per minute.
    """
    if t10_90_s is None or t10_90_s <= 0:
        return 0.0
    lo, hi = 1.0, rr_ceiling
    if not resolves(lo, t10_90_s, peak_min, trough_max, exp_frac):
        return 0.0
    if resolves(hi, t10_90_s, peak_min, trough_max, exp_frac):
        return hi
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        if resolves(mid, t10_90_s, peak_min, trough_max, exp_frac):
            lo = mid
        else:
            hi = mid
    return lo


def captured_fraction(rr_per_min, t10_90_s, exp_frac=2.0 / 3.0):
    """Displayed peak as a fraction of true end-tidal CO2 at this rate."""
    if t10_90_s is None or t10_90_s <= 0:
        return None
    return periodic_response(rr_per_min, tau_from_t10_90(t10_90_s), exp_frac)[0]


def operating_mode(max_rr, clinical_max_rr=30.0, clinical_min_rr=6.0):
    """Plain statement of what the hardware supports."""
    if max_rr <= 0:
        return "UNMEASURED"
    if max_rr >= clinical_max_rr:
        return "BREATH_BY_BREATH"
    if max_rr >= clinical_min_rr:
        return "PARTIAL"
    return "TREND_ONLY"


def loss_alarm_latency_s(delay_s, t10_90_s, loss_window_s, et_pct=5.0, threshold_pct=1.0):
    """Worst-case time from disconnection to the loss-of-CO2 alarm.

    transport delay + lag to fall from et_pct to the presence threshold + the
    no-CO2 window the monitor waits before calling the loss.
    """
    if delay_s is None or t10_90_s is None:
        return None
    fall = tau_from_t10_90(t10_90_s) * math.log(max(et_pct / threshold_pct, 1.0))
    return delay_s + fall + loss_window_s
