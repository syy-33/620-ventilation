"""Everything the bedside unit does that is not hardware I/O.

The firmware (firmware/code.py) and the simulator (capno_sim) both drive this
class, so the records on the serial line and the alarm behaviour are identical
whether the gas comes from a test lung or from a model.

Wire protocol: one JSON object per line, ``type`` says what it is.
  hello  boot banner with firmware version and the response profile in force
  s      one CO2 sample: t (ms since boot), co2 (%), vac (kPa), d (display state)
  b      one breath: t (start), end, peak, co2 (counts as exhaled CO2), interval_ms
  e      state change: kind (alarm / technical / monitor / ack / baseline), from, to, reason
  st     status summary, once a second
  m      operator marker (button double-press or MARK command), used for step tests
Commands accepted on the same serial line: ARM, DISARM, ACK, BASELINE, MARK <note>.
"""

from . import VERSION
from .annunciator import Annunciator
from .monitor import Monitor


class Device:
    def __init__(self, cfg, info=None):
        self.cfg = cfg
        self.monitor = Monitor(cfg)
        self.ann = Annunciator()
        self.info = info or {}
        self._last_status_t = None

    def hello(self, t):
        rec = {
            "type": "hello",
            "t": t,
            "fw": VERSION,
            "profile": {
                "t10_90_ms": self.cfg["t10_90_ms"],
                "delay_ms": self.cfg["delay_ms"],
                "max_resolvable_rr": self.cfg["max_resolvable_rr"],
                "line_monitored": self.cfg["line_monitored"],
            },
        }
        for k in self.info:
            rec[k] = self.info[k]
        return rec

    def command(self, t, line):
        line = line.strip()
        if not line:
            return []
        word = line.split(" ", 1)[0].upper()
        m = self.monitor
        if word == "ARM":
            return m.arm(t)
        if word == "DISARM":
            return m.disarm(t)
        if word == "ACK":
            return m.acknowledge(t)
        if word == "BASELINE":
            return m.rebaseline(t)
        if word == "MARK":
            note = line[5:] if len(line) > 5 else ""
            return [{"type": "m", "t": t, "note": note}]
        if word == "STATUS":
            return [self.status_record(t)]
        return [{"type": "err", "t": t, "msg": "unknown command: " + word}]

    def button(self, t, kind):
        """kind: 'short' (acknowledge), 'long' (arm), 'hold' (disarm), 'double' (marker)."""
        if kind == "short":
            return self.monitor.acknowledge(t)
        if kind == "long":
            return self.monitor.arm(t)
        if kind == "hold":
            return self.monitor.disarm(t)
        if kind == "double":
            return [{"type": "m", "t": t, "note": "button"}]
        return []

    def step(self, t, co2=None, vac=None, comms_error=False):
        out = []
        if co2 is not None:
            # Sample record first: it is the input the events below were derived from.
            out.append(None)
        events = self.monitor.update(t, co2, vac, comms_error)
        if co2 is not None:
            v = None if vac is None else round(vac, 2)
            out[0] = {"type": "s", "t": t, "co2": round(co2, 3), "vac": v,
                      "d": self.monitor.display()}
        out.extend(events)
        if self._last_status_t is None or t - self._last_status_t >= 1000:
            self._last_status_t = t
            out.append(self.status_record(t))
        return out

    def status_record(self, t):
        rec = self.monitor.status(t)
        rec["type"] = "st"
        rec["t"] = t
        return rec

    def outputs(self, t):
        m = self.monitor
        return self.ann.update(t, m.display(), m.audio_paused(t),
                               len(m.confirm_peaks), self.cfg["confirm_breaths"])
