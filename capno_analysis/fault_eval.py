"""Score a labelled fault dataset (ER-2, ER-3, VP-2, VP-3).

Ground truth comes from markers whose note is ``truth=<label>``: the simulator
writes them automatically; on the bench the operator sends them from the
dashboard Marker button at the moment each condition is created (for example
clamping the line: ``truth=blocked``). Each label runs until the next truth
marker.

Expected outcome per label:
  disconnect, apnoea, no_co2  -> CRITICAL (latency measured)
  blocked, open, sensor_off   -> TECHNICAL, and CRITICAL is forbidden (CR-3)
  hypovent                    -> ADVISORY
  normal                      -> no new alarm of any kind
  standby, recovering         -> not scored

    python -m capno_analysis.fault_eval --db data/capno.db --session 7
    python -m capno_analysis.fault_eval --simulate fault_dataset --t10-90 2.0
"""

import argparse
import json

import numpy as np

from .data import from_db, from_jsonl, from_records

EXPECT = {
    "disconnect": ("CRITICAL", set()),
    "apnoea": ("CRITICAL", set()),
    "no_co2": ("CRITICAL", set()),
    "blocked": ("TECHNICAL", {"CRITICAL"}),
    "open": ("TECHNICAL", {"CRITICAL"}),
    "sensor_off": ("TECHNICAL", {"CRITICAL"}),
    "hypovent": ("ADVISORY", {"CRITICAL"}),
    "normal": (None, {"CRITICAL", "TECHNICAL", "ADVISORY"}),
}


def _new_alarms(events, start, end):
    """(time, level) of every alarm or technical onset in [start, end)."""
    out = []
    for e in events:
        t = e.get("t")
        if t is None or not (start <= t < end):
            continue
        if e.get("kind") == "alarm" and e.get("to") in ("CRITICAL", "ADVISORY"):
            out.append((t, e["to"]))
        elif e.get("kind") == "technical" and e.get("to"):
            out.append((t, "TECHNICAL"))
    return out


def segments(run):
    truth = [(t, n.split("=", 1)[1].strip()) for t, n in run.markers if n.startswith("truth=")]
    end_t = float(run.t[-1]) if len(run.t) else (truth[-1][0] if truth else 0.0)
    segs = []
    for i, (t, label) in enumerate(truth):
        t_end = truth[i + 1][0] if i + 1 < len(truth) else end_t
        segs.append((label, t, t_end))
    return segs


def evaluate(run):
    rows = []
    for label, start, end in segments(run):
        if label not in EXPECT:
            continue
        want, forbidden = EXPECT[label]
        alarms = _new_alarms(run.events, start, end)
        hit = next((t for t, lvl in alarms if lvl == want), None) if want else None
        bad = [lvl for t, lvl in alarms if lvl in forbidden]
        rows.append({"label": label, "start_s": round(start, 2), "duration_s": round(end - start, 1),
                     "expected": want, "detected": hit is not None if want else None,
                     "latency_s": None if hit is None else round(hit - start, 2),
                     "forbidden": bad, "ok": (hit is not None or want is None) and not bad})
    return rows


def summarise(rows):
    def frac(num, den):
        return None if den == 0 else round(num / den, 3)

    crit = [r for r in rows if r["expected"] == "CRITICAL"]
    not_crit = [r for r in rows if r["expected"] != "CRITICAL"]
    tech = [r for r in rows if r["expected"] == "TECHNICAL"]
    not_tech = [r for r in rows if r["expected"] != "TECHNICAL"]
    s = {
        "segments": len(rows),
        "critical_sensitivity": frac(sum(r["detected"] for r in crit), len(crit)),
        "critical_specificity": frac(sum("CRITICAL" not in r["forbidden"] for r in not_crit), len(not_crit)),
        "technical_sensitivity": frac(sum(r["detected"] for r in tech), len(tech)),
        "technical_specificity": frac(sum("TECHNICAL" not in r["forbidden"] for r in not_tech), len(not_tech)),
        "faults_presented_as_critical": sum("CRITICAL" in r["forbidden"] for r in tech),
        "false_alarms_in_normal": sum(bool(r["forbidden"]) for r in rows if r["label"] == "normal"),
        "latency_s": {},
    }
    for label in sorted({r["label"] for r in rows if r["expected"]}):
        lat = [r["latency_s"] for r in rows if r["label"] == label and r["latency_s"] is not None]
        if lat:
            s["latency_s"][label] = {"n": len(lat), "median": round(float(np.median(lat)), 2),
                                     "max": round(float(np.max(lat)), 2)}
    return s


def markdown(rows, summary):
    lines = ["| label | n | detected | median latency s | max latency s | forbidden alarms |",
             "|---|---|---|---|---|---|"]
    for label in sorted({r["label"] for r in rows}):
        rs = [r for r in rows if r["label"] == label]
        det = "—" if rs[0]["expected"] is None else f"{sum(r['detected'] for r in rs)}/{len(rs)}"
        lat = summary["latency_s"].get(label, {})
        lines.append(f"| {label} | {len(rs)} | {det} | {lat.get('median', '—')} | {lat.get('max', '—')} |"
                     f" {sum(len(r['forbidden']) for r in rs)} |")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--db")
    src.add_argument("--jsonl")
    src.add_argument("--simulate", metavar="SCENARIO")
    p.add_argument("--session", type=int)
    p.add_argument("--t10-90", type=float, default=0.3)
    p.add_argument("--delay", type=float, default=1.0)
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    if a.db:
        run = from_db(a.db, a.session)
    elif a.jsonl:
        run = from_jsonl(a.jsonl)
    else:
        from capno_sim.run import records
        from capno_sim.scenarios import SCENARIOS
        run = from_records(records(SCENARIOS[a.simulate](), a.t10_90, a.delay))
    rows = evaluate(run)
    s = summarise(rows)
    if a.json:
        print(json.dumps({"summary": s, "segments": rows}, indent=2))
    else:
        print(markdown(rows, s))
        print()
        print(json.dumps({k: v for k, v in s.items() if k != "latency_s"}, indent=2))


if __name__ == "__main__":
    main()
