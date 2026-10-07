"""Published response profile: what this hardware has been measured to do (ER-5).

The file is written by ``python -m capno_analysis.profile build`` from step-test
results. If it is missing or says UNMEASURED, the service and dashboard say so
plainly and claim nothing beyond a breath-averaged trend.
"""

import json
from pathlib import Path

UNMEASURED = {
    "status": "UNMEASURED",
    "statement": ("Response time has not been measured on this hardware. Treat every value "
                  "as a breath-averaged trend. This is not a capnograph."),
    "mode": "UNMEASURED",
    "max_resolvable_rr": 0.0,
    "t_response_s": None,
    "delay_s": None,
}

MODE_TEXT = {
    "BREATH_BY_BREATH": "Breath-by-breath capnography up to {rr:.0f} breaths/min.",
    "PARTIAL": ("Breath-by-breath only up to {rr:.0f} breaths/min. Faster than that the peak "
                "under-reads end-tidal CO2 and the display is a breath-averaged trend."),
    "TREND_ONLY": ("Breath-averaged CO2 trend only: this hardware cannot resolve individual "
                   "breaths at clinical rates. It confirms CO2 presence and tracks rate, "
                   "it is not a capnograph."),
    "UNMEASURED": UNMEASURED["statement"],
}


def load_profile(path):
    p = Path(path) if path else None
    if p is None or not p.exists():
        return dict(UNMEASURED)
    with open(p) as f:
        prof = json.load(f)
    if prof.get("status") != "MEASURED":
        merged = dict(UNMEASURED)
        merged.update({k: v for k, v in prof.items() if v is not None})
        merged["status"] = "UNMEASURED"
        return merged
    return prof


def compare_with_device(published, device_profile):
    """List of human-readable mismatches between the file and the firmware config."""
    if not device_profile:
        return []
    issues = []
    pub_rr = published.get("max_resolvable_rr") or 0.0
    dev_rr = device_profile.get("max_resolvable_rr") or 0.0
    if abs(pub_rr - dev_rr) > 0.5:
        issues.append(f"firmware max_resolvable_rr {dev_rr} differs from published {pub_rr}")
    pub_t = published.get("t_response_s")
    dev_t = device_profile.get("t10_90_ms")
    if (pub_t is None) != (dev_t is None) or (
            pub_t is not None and dev_t is not None and abs(pub_t * 1000 - dev_t) > 50):
        issues.append(f"firmware t10_90_ms {dev_t} differs from published t_response_s {pub_t}")
    if device_profile.get("line_monitored") is False:
        issues.append("sampling line integrity is NOT monitored: a blocked line cannot be "
                      "told apart from loss of CO2")
    return issues
