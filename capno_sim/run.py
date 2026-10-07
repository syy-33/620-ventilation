"""Drive capno_core.Device with the simulated rig and yield wire records."""

import json
import sys
import time

from capno_core.capability import max_resolvable_rr
from capno_core.config import make_config
from capno_core.device import Device

from .model import Rig
from .scenarios import SCENARIOS


def sim_config(t10_90_s, delay_s, overrides=None):
    o = {"t10_90_ms": int(t10_90_s * 1000), "delay_ms": int(delay_s * 1000),
         "max_resolvable_rr": round(max_resolvable_rr(t10_90_s), 1)}
    if overrides:
        o.update(overrides)
    return make_config(o)


def records(segments, t10_90_s=0.3, delay_s=1.0, fs=20.0, cfg_overrides=None,
            seed=1, device=None, label_markers=True):
    """Yield every record the device would print, plus ground-truth markers."""
    cfg = sim_config(t10_90_s, delay_s, cfg_overrides)
    dev = device or Device(cfg, {"sensor": "sim", "fs": fs})
    yield dev.hello(0)
    rig = Rig(t10_90_s=t10_90_s, delay_s=delay_s, fs=fs, seed=seed,
              vac_nominal=cfg["line_vac_nominal_kpa"])
    for t, co2, vac, seg, first in rig.run(segments):
        if first:
            if label_markers and seg.label:
                yield {"type": "m", "t": t, "note": "truth=" + seg.label}
            if seg.command:
                for r in dev.command(t, seg.command):
                    yield r
            if seg.button:
                for r in dev.button(t, seg.button):
                    yield r
        for r in dev.step(t, co2, vac):
            yield r


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Print simulated monitor records as JSON lines.")
    p.add_argument("scenario", choices=sorted(SCENARIOS))
    p.add_argument("--t10-90", type=float, default=0.3, help="sensor 10-90 %% rise time, s")
    p.add_argument("--delay", type=float, default=1.0, help="sampling line transport delay, s")
    p.add_argument("--fs", type=float, default=20.0)
    p.add_argument("--realtime", action="store_true")
    a = p.parse_args(argv)
    start = time.monotonic()
    for r in records(SCENARIOS[a.scenario](), a.t10_90, a.delay, a.fs):
        if a.realtime:
            wait = start + r["t"] / 1000.0 - time.monotonic()
            if wait > 0:
                time.sleep(wait)
        sys.stdout.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
