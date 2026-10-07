"""Measure transport delay and 10-90 % response from step tests (ER-5, VP-5).

Protocol (docs/06_verification_plan.md): with the pump running, hold the end of
the sampling line in room air, then move it into the calibration gas (or a bag
of exhaled alveolar gas) and press the marker at the same instant (double press
of the bedside button, or Marker on the dashboard). Hold for at least 20 s,
then move it back to room air with another marker. Each marker is one step.

For each step:
  t0      marker time (the switch)
  initial median of the 2 s before t0
  final   median of the last 3 s of the window (the plateau)
  delay   t0 -> 10 % of the change (transport delay plus the start of the lag)
  t10_90  10 % -> 90 % of the change (rise), or 90 % -> 10 % for a fall
Crossing times are linearly interpolated between samples.

    python -m capno_analysis.response_time --db data/capno.db --session 4 \
        --line-length 2.0 --append results/steps.csv --plot results/steps_s4.png
"""

import argparse
import csv
import os

import numpy as np

from .data import from_db, from_jsonl

FIELDS = ["source", "marker_s", "line_length_m", "direction", "initial_pct", "final_pct",
          "delay_s", "t10_90_s", "ok", "note"]


def _crossing(t, y, level, rising, start_idx):
    for i in range(max(start_idx, 1), len(y)):
        a, b = y[i - 1], y[i]
        if (rising and a < level <= b) or (not rising and a > level >= b):
            if b == a:
                return t[i]
            return t[i - 1] + (level - a) * (t[i] - t[i - 1]) / (b - a)
    return None


def analyse_step(t, y, t0, t_end, min_change_pct=0.5):
    """Return a dict for the step at t0, using data up to t_end."""
    pre = (t >= t0 - 2.0) & (t < t0)
    win = (t >= t0) & (t <= t_end)
    if pre.sum() < 2 or win.sum() < 5:
        return {"ok": False, "note": "not enough samples"}
    initial = float(np.median(y[pre]))
    tail = win & (t >= t_end - 3.0)
    final = float(np.median(y[tail]))
    change = final - initial
    if abs(change) < min_change_pct:
        return {"ok": False, "note": f"change {change:.2f} % too small", "initial_pct": initial,
                "final_pct": final}
    rising = change > 0
    tw, yw = t[win], y[win]
    l10 = initial + 0.1 * change
    l90 = initial + 0.9 * change
    t10 = _crossing(tw, yw, l10, rising, 0)
    if t10 is None:
        return {"ok": False, "note": "never reached 10 %"}
    i10 = int(np.searchsorted(tw, t10))
    t90 = _crossing(tw, yw, l90, rising, i10)
    if t90 is None:
        return {"ok": False, "note": "never reached 90 %: hold the gas longer"}
    # the plateau must really be a plateau
    settle = float(np.std(y[tail]))
    note = "" if settle < 0.1 * abs(change) else "plateau not flat"
    return {"ok": note == "", "direction": "up" if rising else "down", "initial_pct": initial,
            "final_pct": final, "delay_s": t10 - t0, "t10_90_s": t90 - t10, "note": note}


def analyse_run(run, line_length_m, source="", marker_filter=None, max_window_s=60.0):
    marks = [m for m in run.markers if not marker_filter or marker_filter in m[1]]
    out = []
    for i, (t0, note) in enumerate(marks):
        t_next = marks[i + 1][0] if i + 1 < len(marks) else run.t[-1] if len(run.t) else t0
        t_end = min(t_next - 0.2, t0 + max_window_s)
        r = analyse_step(run.t, run.co2, t0, t_end)
        r.update({"source": source, "marker_s": round(t0, 3), "line_length_m": line_length_m})
        r["note"] = (note + " " + r.get("note", "")).strip()
        out.append(r)
    return out


def append_csv(path, rows):
    new = not os.path.exists(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: (round(r[k], 4) if isinstance(r.get(k), float) else r.get(k, ""))
                        for k in FIELDS})


def plot_steps(run, rows, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    good = [r for r in rows if r.get("ok")]
    if not good:
        return
    fig, ax = plt.subplots(figsize=(7, 4))
    for r in good:
        t0 = r["marker_s"]
        m = (run.t >= t0 - 2) & (run.t <= t0 + 30)
        y = (run.co2[m] - r["initial_pct"]) / (r["final_pct"] - r["initial_pct"])
        ax.plot(run.t[m] - t0, y, lw=1, label=f"{r['direction']} @ {t0:.0f} s")
    ax.axhline(0.1, ls=":", c="grey")
    ax.axhline(0.9, ls=":", c="grey")
    ax.set_xlabel("time from switch (s)")
    ax.set_ylabel("normalised CO2 response")
    ax.set_title(f"Step response, {rows[0]['line_length_m']} m line")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=130)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--db")
    src.add_argument("--jsonl")
    p.add_argument("--session", type=int)
    p.add_argument("--line-length", type=float, required=True, help="sampling line length, m")
    p.add_argument("--marker-filter", default=None, help="only markers whose note contains this")
    p.add_argument("--append", help="append step results to this CSV")
    p.add_argument("--plot", help="save an overlay plot of the normalised steps")
    a = p.parse_args(argv)
    if a.db:
        if a.session is None:
            p.error("--session is required with --db")
        run = from_db(a.db, a.session)
        source = f"{a.db}#{a.session}"
    else:
        run = from_jsonl(a.jsonl)
        source = a.jsonl
    rows = analyse_run(run, a.line_length, source, a.marker_filter)
    for r in rows:
        if r.get("ok"):
            print(f"{r['marker_s']:9.2f} s  {r['direction']:4s} delay {r['delay_s']:.2f} s"
                  f"  t10-90 {r['t10_90_s']:.2f} s  {r['initial_pct']:.2f} -> {r['final_pct']:.2f} %")
        else:
            print(f"{r['marker_s']:9.2f} s  rejected: {r.get('note')}")
    if a.append:
        append_csv(a.append, rows)
    if a.plot:
        plot_steps(run, rows, a.plot)


if __name__ == "__main__":
    main()
