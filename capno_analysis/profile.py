"""Build and publish the response profile from step-test results (ER-5).

    python -m capno_analysis.profile build results/steps.csv --line-length 2.0 \
        --sensor "SprintIR-WF-20" --out config/response_profile.json

The profile states, for the line length actually used at the bedside:
  * transport delay and 10-90 % response (mean, SD, n), rise and fall separately
  * delay versus line length (least squares fit over every length tested)
  * the highest breathing rate resolved breath by breath, from the slower of
    rise and fall (capno_core.capability), and the operating mode that follows
  * worst-case loss-of-CO2 alarm latency
  * a plain-language statement for the dashboard
and prints the block to paste into firmware/config.py so the bedside unit
makes the same claims.
"""

import argparse
import csv
import json
from datetime import date

import numpy as np

from capno_core.capability import (captured_fraction, loss_alarm_latency_s, max_resolvable_rr,
                                   operating_mode)
from capno_core.config import DEFAULTS

REPEATABILITY_LIMIT = 0.10      # ER-5: SD within 10 % of the mean


def load_rows(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    good = []
    for r in rows:
        if r.get("ok") not in ("True", "true", "1"):
            continue
        good.append({"L": float(r["line_length_m"]), "dir": r["direction"],
                     "delay": float(r["delay_s"]), "t1090": float(r["t10_90_s"])})
    return rows, good


def stats(values):
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return None
    sd = float(np.std(v, ddof=1)) if len(v) > 1 else None
    return {"mean": round(float(v.mean()), 3), "sd": None if sd is None else round(sd, 3),
            "n": int(len(v)), "min": round(float(v.min()), 3), "max": round(float(v.max()), 3)}


def fit_delay(good):
    lengths = sorted({g["L"] for g in good})
    points = []
    for L in lengths:
        d = [g["delay"] for g in good if g["L"] == L]
        s = stats(d)
        points.append([L, s["mean"], s["sd"], s["n"]])
    if len(lengths) < 2:
        return {"points": points, "slope_s_per_m": None, "intercept_s": None, "r2": None}
    x = np.array([g["L"] for g in good])
    y = np.array([g["delay"] for g in good])
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None
    return {"points": points, "slope_s_per_m": round(float(slope), 4),
            "intercept_s": round(float(intercept), 4), "r2": None if r2 is None else round(r2, 4)}


def build(path, line_length, sensor, notes=""):
    all_rows, good = load_rows(path)
    at = [g for g in good if abs(g["L"] - line_length) < 1e-6]
    if not at:
        raise SystemExit(f"no accepted steps at line length {line_length} m in {path}")
    rise = stats([g["t1090"] for g in at if g["dir"] == "up"])
    fall = stats([g["t1090"] for g in at if g["dir"] == "down"])
    delay = stats([g["delay"] for g in at])
    if rise is None:
        raise SystemExit("need at least one rising step at the deployed line length")
    # Conservative: the slower of rise and fall governs whether breaths resolve.
    t_resp = max(rise["mean"], fall["mean"] if fall else 0.0)
    rr = round(max_resolvable_rr(t_resp), 1)
    mode = operating_mode(rr)
    latency = loss_alarm_latency_s(delay["mean"], t_resp, DEFAULTS["loss_window_max_ms"] / 1000.0)

    repeatability = {}
    for name, s in (("t10_90_rise", rise), ("t90_10_fall", fall), ("delay", delay)):
        if s and s["sd"] is not None and s["mean"] > 0:
            repeatability[name] = {"cv": round(s["sd"] / s["mean"], 3),
                                   "pass": s["sd"] / s["mean"] <= REPEATABILITY_LIMIT}

    if mode == "BREATH_BY_BREATH":
        statement = (f"Breath-by-breath capnography up to {rr:.0f} breaths/min on a "
                     f"{line_length} m line.")
    elif mode == "PARTIAL":
        statement = (f"Resolves individual breaths only up to {rr:.0f} breaths/min on a "
                     f"{line_length} m line; faster breathing is shown as a breath-averaged "
                     "trend that under-reads end-tidal CO2. Not a capnograph above that rate.")
    else:
        statement = ("Breath-averaged CO2 trend monitor. This hardware cannot resolve individual "
                     "breaths at clinical rates. It confirms that exhaled CO2 is present and "
                     "tracks the rate it implies. It is not a capnograph.")

    return {
        "status": "MEASURED",
        "measured_on": date.today().isoformat(),
        "sensor": sensor,
        "line_length_m": line_length,
        "source_csv": str(path),
        "steps_total": len(all_rows),
        "steps_accepted": len(good),
        "t10_90_s": rise,
        "t90_10_s": fall,
        "delay_s": delay["mean"],
        "delay_stats": delay,
        "t_response_s": round(t_resp, 3),
        "delay_vs_length": fit_delay(good),
        "repeatability": repeatability,
        "criterion": {"peak_min": 0.9, "trough_max": 0.1, "ie_ratio": "1:2",
                      "model": "transport delay + first-order lag"},
        "max_resolvable_rr": rr,
        "mode": mode,
        "captured_fraction": {str(r): round(captured_fraction(r, t_resp), 3) for r in (6, 12, 20, 30)},
        "loss_alarm_latency_s": round(latency, 1),
        "statement": statement,
        "notes": notes,
    }


def firmware_block(prof):
    return ("    \"t10_90_ms\": {t},\n    \"delay_ms\": {d},\n    \"max_resolvable_rr\": {rr},"
            .format(t=int(round(prof["t_response_s"] * 1000)), d=int(round(prof["delay_s"] * 1000)),
                    rr=prof["max_resolvable_rr"]))


def plot_profile(prof, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4))
    pts = prof["delay_vs_length"]["points"]
    L = [p[0] for p in pts]
    a1.errorbar(L, [p[1] for p in pts], yerr=[p[2] or 0 for p in pts], fmt="o", capsize=3)
    fit = prof["delay_vs_length"]
    if fit["slope_s_per_m"] is not None:
        xs = np.linspace(0, max(L) * 1.1, 10)
        a1.plot(xs, fit["slope_s_per_m"] * xs + fit["intercept_s"], "--",
                label=f"{fit['slope_s_per_m']:.2f} s/m + {fit['intercept_s']:.2f} s, R²={fit['r2']}")
        a1.legend(fontsize=8)
    a1.set_xlabel("sampling line length (m)")
    a1.set_ylabel("transport delay (s)")
    a1.set_title("Delay grows with line length")
    rr = np.linspace(4, 40, 200)
    cap = [captured_fraction(r, prof["t_response_s"]) for r in rr]
    a2.plot(rr, cap)
    a2.axhline(0.9, ls=":", c="grey")
    a2.axvline(prof["max_resolvable_rr"], ls="--", c="red",
               label=f"breath-by-breath limit {prof['max_resolvable_rr']:.0f}/min")
    a2.set_xlabel("breathing rate (/min)")
    a2.set_ylabel("displayed peak / true EtCO2")
    a2.set_ylim(0, 1.05)
    a2.set_title(f"t_response = {prof['t_response_s']:.2f} s")
    a2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("csv")
    b.add_argument("--line-length", type=float, required=True, help="line length used at the bedside, m")
    b.add_argument("--sensor", required=True)
    b.add_argument("--notes", default="")
    b.add_argument("--out", default="config/response_profile.json")
    b.add_argument("--plot")
    a = p.parse_args(argv)
    prof = build(a.csv, a.line_length, a.sensor, a.notes)
    with open(a.out, "w") as f:
        json.dump(prof, f, indent=2)
    print(json.dumps({k: prof[k] for k in ("t_response_s", "delay_s", "max_resolvable_rr", "mode",
                                           "loss_alarm_latency_s")}, indent=2))
    print("\n" + prof["statement"])
    print("\nPaste into firmware/config.py MONITOR:\n" + firmware_block(prof))
    if a.plot:
        plot_profile(prof, a.plot)


if __name__ == "__main__":
    main()
