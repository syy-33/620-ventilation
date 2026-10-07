"""Load samples, markers and events from the service database or a JSON-lines capture."""

import json
import sqlite3

import numpy as np


class Run:
    def __init__(self, t_ms, co2, markers, events, display=None):
        self.t = np.asarray(t_ms, dtype=float) / 1000.0      # seconds
        self.co2 = np.asarray(co2, dtype=float)
        self.markers = markers                               # [(t_s, note)]
        self.events = events                                 # [dict] with t in seconds
        self.display = display                               # list of str per sample


def from_db(path, session):
    con = sqlite3.connect(path)
    rows = con.execute("SELECT t_ms, co2, display FROM samples WHERE session_id = ? AND co2 IS NOT"
                       " NULL ORDER BY t_ms", (session,)).fetchall()
    markers = [(t / 1000.0, n) for t, n in con.execute(
        "SELECT t_ms, note FROM markers WHERE session_id = ? ORDER BY t_ms", (session,))]
    events = [{"t": None if t is None else t / 1000.0, "kind": k, "from": f, "to": to, "reason": r}
              for t, k, f, to, r in con.execute(
                  "SELECT t_ms, kind, from_state, to_state, reason FROM events WHERE session_id = ?"
                  " ORDER BY id", (session,))]
    con.close()
    return Run([r[0] for r in rows], [r[1] for r in rows], markers, events, [r[2] for r in rows])


def from_records(records):
    t, c, d, markers, events = [], [], [], [], []
    for r in records:
        typ = r.get("type")
        if typ == "s" and r.get("co2") is not None:
            t.append(r["t"])
            c.append(r["co2"])
            d.append(r.get("d"))
        elif typ == "m":
            markers.append((r["t"] / 1000.0, r.get("note", "")))
        elif typ == "e":
            e = dict(r)
            e["t"] = r["t"] / 1000.0 if r.get("t") is not None else None
            events.append(e)
    return Run(t, c, markers, events, d)


def from_jsonl(path):
    with open(path) as f:
        return from_records(json.loads(line) for line in f if line.startswith("{"))
