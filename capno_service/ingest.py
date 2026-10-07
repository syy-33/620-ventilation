"""Read device records, log them, keep live state, apply the notification rules."""

import collections
import json
import threading
import time

from .db import Writer
from .profile import compare_with_device
from .rules import Rules

LIVE_SAMPLES = 20 * 300     # five minutes at 20 Hz


class Live:
    """In-memory view for the dashboard. Guarded by ``lock``."""

    def __init__(self, published_profile, source_name):
        self.lock = threading.Lock()
        self.seq = 0
        self.samples = collections.deque(maxlen=LIVE_SAMPLES)
        self.events = collections.deque(maxlen=300)
        self.breaths = collections.deque(maxlen=300)
        self.status = {}
        self.hello = None
        self.profile = published_profile
        self.mismatch = []
        self.source = source_name
        self.session_id = None
        self.last_rx = None
        self.link_ok = False
        self.event_seq = 0

    def add_event(self, rec, host_ts):
        self.event_seq += 1
        e = dict(rec)
        e["host_ts"] = host_ts
        e["seq"] = self.event_seq
        self.events.append(e)


class Ingestor:
    def __init__(self, source, db_path, published_profile, notifier=None, rules=None):
        self.source = source
        self.db_path = db_path
        self.live = Live(published_profile, source.name)
        self.rules = rules or Rules(notifier)
        self.writer = None
        self._lock = threading.Lock()        # writer + rules
        self._stop = threading.Event()
        self.rx_count = 0
        self.bad_lines = 0

    # ----------------------------------------------------------------- threads
    def open(self):
        self.writer = Writer(self.db_path)
        with self._lock:
            self.live.session_id = self.writer.new_session(self.source.name, self.live.profile)

    def start(self):
        self.open()
        threading.Thread(target=self._read_loop, daemon=True).start()
        threading.Thread(target=self._tick_loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _read_loop(self):
        for line in self.source.lines():
            if self._stop.is_set():
                break
            if line:
                self.handle_line(line, time.time())
        with self._lock:
            self.writer.maybe_commit(force=True)

    def _tick_loop(self):
        while not self._stop.is_set():
            self.tick(time.time())
            time.sleep(0.5)

    # ------------------------------------------------------------- processing
    def handle_line(self, line, host_ts):
        if not line.startswith("{"):
            return                      # REPL chatter, tracebacks: ignored, not stored
        try:
            rec = json.loads(line)
        except ValueError:
            self.bad_lines += 1
            return
        with self._lock:
            self._handle(rec, host_ts)

    def _handle(self, rec, host_ts):
        live = self.live
        typ = rec.get("type")
        self.rx_count += 1
        if typ == "hello":
            if live.hello is not None:
                # Bedside unit restarted: device clock restarted, start a new session.
                live.session_id = self.writer.new_session(self.source.name, live.profile)
                with live.lock:
                    live.samples.clear()
            with live.lock:
                live.hello = rec
                live.mismatch = compare_with_device(live.profile, rec.get("profile"))
                if rec.get("sensor") == "demo":
                    live.mismatch.insert(0, "DEMO DATA: the bedside unit is in demo mode "
                                            "(config.py SENSOR = \"demo\"). Not a measurement.")
        event_id = self.writer.write(rec, host_ts)
        with live.lock:
            live.last_rx = host_ts
            live.link_ok = True
            if typ == "s":
                live.seq += 1
                live.samples.append((live.seq, rec["t"], rec.get("co2"), rec.get("vac"),
                                     rec.get("d")))
            elif typ == "st":
                live.status = rec
            elif typ == "b":
                live.breaths.append(rec)
            elif typ in ("e", "m"):
                live.add_event(rec, host_ts)
        if typ == "e":
            self.rules.on_event(rec, event_id, host_ts)

    def tick(self, now):
        with self._lock:
            change = self.rules.tick(now, self.live.last_rx)
            if change:
                rec = {"type": "e", "t": None, "kind": "link",
                       "from": None if change == "lost" else "LINK_LOST",
                       "to": "LINK_LOST" if change == "lost" else None,
                       "reason": "no data from bedside unit for "
                                 f"{self.rules.link_timeout_s:.0f} s" if change == "lost"
                                 else "restored"}
                self.writer.write(rec, now)
                with self.live.lock:
                    self.live.link_ok = change == "restored"
                    self.live.add_event(rec, now)
            self.writer.maybe_commit()

    def send(self, cmd):
        self.source.send(cmd)
