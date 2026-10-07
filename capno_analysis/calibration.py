"""Static calibration against the reference capnograph or certified gas (ER-6, VP-6).

Input CSV columns: reference_pct, device_pct  (one row per settled reading;
take each device value as the median over 10 s once the reading is flat).

    python -m capno_analysis.calibration fit results/cal.csv --plot results/cal.png
    python -m capno_analysis.calibration drift results/drift.csv

``fit``   least squares device = a * reference + b, residuals, and the
          correction CO2_GAIN = 1/a, CO2_OFFSET_PCT = -b/a for firmware/config.py.
          Acceptance (after correction): every residual within
          +/-(0.43 % + 8 % of reading), the ISO 80601-2-55 CO2 accuracy limit.
``drift`` columns hours, reference_pct, device_pct: error slope per hour.
"""

import argparse
import csv

import numpy as np


def limit(ref):
    return 0.43 + 0.08 * np.abs(ref)


def fit(ref, dev):
    ref = np.asarray(ref, float)
    dev = np.asarray(dev, float)
    a, b = np.polyfit(ref, dev, 1)
    gain, offset = 1.0 / a, -b / a
    corrected = dev * gain + offset
    resid = corrected - ref
    lim = limit(ref)
    return {
        "n": int(len(ref)), "slope": float(a), "intercept_pct": float(b),
        "gain": float(gain), "offset_pct": float(offset),
        "rmse_pct": float(np.sqrt(np.mean(resid ** 2))),
        "max_abs_error_pct": float(np.max(np.abs(resid))),
        "raw_max_abs_error_pct": float(np.max(np.abs(dev - ref))),
        "within_limit": int(np.sum(np.abs(resid) <= lim)),
        "pass": bool(np.all(np.abs(resid) <= lim)),
        "residuals": resid.tolist(), "reference": ref.tolist(),
    }


def drift(hours, ref, dev):
    err = np.asarray(dev, float) - np.asarray(ref, float)
    slope, intercept = np.polyfit(np.asarray(hours, float), err, 1)
    return {"n": len(err), "error_slope_pct_per_h": float(slope), "error_at_0_pct": float(intercept),
            "max_abs_error_pct": float(np.max(np.abs(err)))}


def read(path, cols):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return [[float(r[c]) for r in rows] for c in cols]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit")
    f.add_argument("csv")
    f.add_argument("--plot")
    d = sub.add_parser("drift")
    d.add_argument("csv")
    a = p.parse_args(argv)
    if a.cmd == "fit":
        ref, dev = read(a.csv, ["reference_pct", "device_pct"])
        r = fit(ref, dev)
        print(f"n={r['n']}  device = {r['slope']:.4f} x reference + {r['intercept_pct']:.4f} %")
        print(f"after correction: RMSE {r['rmse_pct']:.3f} %, max |error| {r['max_abs_error_pct']:.3f} %,"
              f" {r['within_limit']}/{r['n']} within +/-(0.43 % + 8 %) -> {'PASS' if r['pass'] else 'FAIL'}")
        print(f"\nfirmware/config.py:\nCO2_GAIN = {r['gain']:.4f}\nCO2_OFFSET_PCT = {r['offset_pct']:.4f}")
        if a.plot:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4))
            refs = np.array(ref)
            a1.plot(ref, dev, "o", label="device (raw)")
            xs = np.linspace(0, max(ref) * 1.05, 10)
            a1.plot(xs, r["slope"] * xs + r["intercept_pct"], "--", label="fit")
            a1.plot(xs, xs, ":", c="grey", label="identity")
            a1.set_xlabel("reference CO2 (%)")
            a1.set_ylabel("device CO2 (%)")
            a1.legend()
            a2.plot(ref, r["residuals"], "o")
            order = np.argsort(refs)
            a2.plot(refs[order], limit(refs[order]), "r--", label="ISO 80601-2-55 limit")
            a2.plot(refs[order], -limit(refs[order]), "r--")
            a2.axhline(0, c="grey")
            a2.set_xlabel("reference CO2 (%)")
            a2.set_ylabel("corrected residual (%)")
            a2.legend()
            fig.tight_layout()
            fig.savefig(a.plot, dpi=130)
    else:
        h, ref, dev = read(a.csv, ["hours", "reference_pct", "device_pct"])
        r = drift(h, ref, dev)
        print(f"n={r['n']} error drift {r['error_slope_pct_per_h']:+.4f} %/h, max |error| "
              f"{r['max_abs_error_pct']:.3f} %")


if __name__ == "__main__":
    main()
