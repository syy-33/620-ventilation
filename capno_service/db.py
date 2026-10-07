"""SQLite schema and access (ER-8).

No patient identifiers are stored anywhere: the bench rig has no patient.
Recipients are opted-in course participants, each with a consent timestamp.
"""

import json
import sqlite3
import time
from datetime import datetime, timezone

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    source TEXT NOT NULL,
    fw TEXT,
    device_profile TEXT,
    published_profile TEXT
);
CREATE TABLE IF NOT EXISTS samples (
    session_id INTEGER NOT NULL, t_ms INTEGER NOT NULL, host_ts REAL NOT NULL,
    co2 REAL, vac REAL, display TEXT
);
CREATE INDEX IF NOT EXISTS samples_t ON samples(session_id, t_ms);
CREATE TABLE IF NOT EXISTS breaths (
    session_id INTEGER NOT NULL, t_ms INTEGER NOT NULL, end_ms INTEGER, host_ts REAL,
    peak REAL, is_co2 INTEGER, interval_ms INTEGER
);
CREATE TABLE IF NOT EXISTS status (
    session_id INTEGER NOT NULL, t_ms INTEGER NOT NULL, host_ts REAL NOT NULL,
    display TEXT, mon TEXT, alarm TEXT, reason TEXT, tech TEXT,
    co2 REAL, et REAL, et_kind TEXT, et_capture REAL, rr REAL, rr_note TEXT, vac REAL,
    base_et REAL, base_rr REAL
);
CREATE INDEX IF NOT EXISTS status_t ON status(session_id, t_ms);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, t_ms INTEGER, host_ts REAL NOT NULL,
    kind TEXT, from_state TEXT, to_state TEXT, reason TEXT
);
CREATE TABLE IF NOT EXISTS markers (
    session_id INTEGER NOT NULL, t_ms INTEGER, host_ts REAL NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS perf (
    session_id INTEGER NOT NULL, t_ms INTEGER, host_ts REAL NOT NULL,
    loop_max_ms INTEGER, co2_errors INTEGER
);
CREATE TABLE IF NOT EXISTS recipients (
    id INTEGER PRIMARY KEY,
    alias TEXT NOT NULL UNIQUE,
    channel TEXT NOT NULL,
    address TEXT NOT NULL,
    apikey TEXT,
    levels TEXT NOT NULL DEFAULT 'CRITICAL,TECHNICAL',
    consent_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY, event_id INTEGER, recipient_id INTEGER,
    level TEXT, message TEXT, queued_ts REAL, sent_ts REAL, ok INTEGER, detail TEXT
);
"""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path):
    con = sqlite3.connect(path, check_same_thread=False, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


class Writer:
    """Owned by the ingest thread. Batches inserts and commits twice a second."""

    def __init__(self, path, commit_every_s=0.5):
        self.con = connect(path)
        self.session_id = None
        self.commit_every_s = commit_every_s
        self._last_commit = time.monotonic()

    def new_session(self, source, published_profile):
        cur = self.con.execute(
            "INSERT INTO sessions (started_at, source, published_profile) VALUES (?, ?, ?)",
            (utc_now(), source, json.dumps(published_profile)))
        self.con.commit()
        self.session_id = cur.lastrowid
        return self.session_id

    def hello(self, rec):
        self.con.execute("UPDATE sessions SET fw = ?, device_profile = ? WHERE id = ?",
                         (rec.get("fw"), json.dumps(rec.get("profile")), self.session_id))

    def write(self, rec, host_ts):
        """Store one device record. Returns the event row id for 'e' records."""
        s = self.session_id
        typ = rec.get("type")
        if typ == "s":
            self.con.execute("INSERT INTO samples VALUES (?,?,?,?,?,?)",
                             (s, rec["t"], host_ts, rec.get("co2"), rec.get("vac"), rec.get("d")))
        elif typ == "b":
            self.con.execute("INSERT INTO breaths VALUES (?,?,?,?,?,?,?)",
                             (s, rec["t"], rec.get("end"), host_ts, rec.get("peak"),
                              1 if rec.get("co2") else 0, rec.get("interval_ms")))
        elif typ == "st":
            self.con.execute(
                "INSERT INTO status VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (s, rec["t"], host_ts, rec.get("display"), rec.get("mon"), rec.get("alarm"),
                 rec.get("reason"), ",".join(rec.get("tech") or []), rec.get("co2"), rec.get("et"),
                 rec.get("et_kind"), rec.get("et_capture"), rec.get("rr"), rec.get("rr_note"),
                 rec.get("vac"), rec.get("base_et"), rec.get("base_rr")))
        elif typ == "e":
            cur = self.con.execute(
                "INSERT INTO events (session_id, t_ms, host_ts, kind, from_state, to_state, reason)"
                " VALUES (?,?,?,?,?,?,?)",
                (s, rec.get("t"), host_ts, rec.get("kind"), rec.get("from"), rec.get("to"),
                 rec.get("reason")))
            self.maybe_commit(force=True)
            return cur.lastrowid
        elif typ == "m":
            self.con.execute("INSERT INTO markers VALUES (?,?,?,?)",
                             (s, rec.get("t"), host_ts, rec.get("note")))
        elif typ == "perf":
            self.con.execute("INSERT INTO perf VALUES (?,?,?,?,?)",
                             (s, rec.get("t"), host_ts, rec.get("loop_max_ms"), rec.get("co2_errors")))
        elif typ == "hello":
            self.hello(rec)
        self.maybe_commit()
        return None

    def maybe_commit(self, force=False):
        now = time.monotonic()
        if force or now - self._last_commit >= self.commit_every_s:
            self.con.commit()
            self._last_commit = now

    def close(self):
        self.con.commit()
        self.con.close()
