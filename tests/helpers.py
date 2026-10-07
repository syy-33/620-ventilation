from capno_analysis.data import from_records
from capno_sim.run import records


def run_scenario(segments, **kw):
    recs = list(records(segments, **kw))
    return recs, from_records(recs)


def alarm_events(recs, kind=None, to=None):
    out = []
    for r in recs:
        if r["type"] != "e":
            continue
        if kind and r["kind"] != kind:
            continue
        if to and r["to"] != to:
            continue
        out.append(r)
    return out


def marker_time(recs, label):
    return next(r["t"] for r in recs if r["type"] == "m" and r["note"] == "truth=" + label)
