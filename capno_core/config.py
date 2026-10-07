"""Default tuning for the monitor.

Every value here is referenced by an engineering requirement in
docs/01_engineering_requirements.md. Change a value there and here together.
Times are milliseconds, concentrations are percent CO2 by volume, pressures kPa.
"""

DEFAULTS = {
    # --- breath detection (ER-1, ER-4) ---
    "block_ms": 250,              # envelope block length
    "envelope_ms": 15000,         # window over which min and max are tracked
    "min_swing_pct": 0.3,         # smaller peak-to-trough swing is not a breath
    "rise_frac": 0.60,            # upward crossing at lo + 0.60 * swing
    "fall_frac": 0.35,            # downward crossing at lo + 0.35 * swing
    "min_breath_interval_ms": 1000,   # refractory, i.e. 60 /min plausible maximum
    "max_breath_interval_ms": 20000,  # longer gap is apnoea, not a rate (3 /min)
    "co2_breath_min_pct": 1.0,    # a breath counts as exhaled CO2 if its peak reaches this
    "rr_intervals": 6,            # breaths in the rate median

    # --- presence / absence confirmation (ER-1) ---
    "confirm_breaths": 6,         # breaths needed to confirm placement
    "provisional_breaths": 3,     # breaths shown as "CO2 detected, confirming"
    "confirm_sustain_frac": 0.5,  # later peaks must stay above this fraction of early peaks
    "confirm_timeout_ms": 40000,  # no confirmation in this time -> NO CO2 critical
    "trend_present_pct": 1.0,     # breath-averaged mean that counts as CO2 present
    "trend_mean_ms": 10000,       # averaging window for the trend fallback
    "trend_confirm_ms": 30000,    # trend must be sustained this long to confirm

    # --- loss of CO2 (ER-2) ---
    "loss_window_min_ms": 10000,
    "loss_window_max_ms": 20000,
    "loss_window_breaths": 2.0,   # window = this many median breath intervals, clamped
    "loss_window_default_ms": 15000,
    "recover_breaths": 2,         # breaths after a loss alarm before "back in range"

    # --- hypoventilation advisory (ER-4) ---
    "et_low_pct": 3.0,            # absolute low end-tidal (or trend peak)
    "et_fall_frac": 0.30,         # fall below baseline that is "beyond threshold"
    "rr_low_per_min": 8.0,
    "rr_fall_frac": 0.40,
    "baseline_ms": 120000,        # baseline collected after confirmation
    "advisory_sustain_ms": 30000, # a fall must last this long
    "advisory_clear_ms": 30000,   # values back in range for this long (Figure 3)

    # --- technical faults (ER-3) ---
    "line_monitored": True,       # False if the pressure sensors are not fitted
    "line_vac_nominal_kpa": 10.0, # measured with a clear 2 m line, see docs
    "line_block_factor": 1.8,     # vacuum above nominal * factor -> blocked
    "line_open_factor": 0.45,     # vacuum below nominal * factor -> open / disconnected
    "line_fault_debounce_ms": 1500,
    "sensor_timeout_ms": 2000,
    "co2_valid_min_pct": -0.5,
    "co2_valid_max_pct": 20.0,
    "zero_tol_pct": 0.3,          # room air must read within 0.04 +/- this in standby
    "zero_check_ms": 60000,
    "baseline_high_pct": 0.8,     # inspired CO2 above this while breaths resolve
    "technical_clear_ms": 3000,

    # --- annunciation (ER-7) ---
    "audio_pause_ms": 120000,

    # --- instrument response (ER-5), overwritten from response_profile.json ---
    "t10_90_ms": None,            # None means "not measured": trend-only claims
    "delay_ms": None,
    "max_resolvable_rr": 0.0,
}


def make_config(overrides=None):
    cfg = dict(DEFAULTS)
    if overrides:
        for k in overrides:
            if k not in DEFAULTS:
                raise KeyError("unknown config key: " + str(k))
            cfg[k] = overrides[k]
    return cfg
