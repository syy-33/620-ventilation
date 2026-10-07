"""REST API and dashboard (ER-8).

Read endpoints use their own SQLite connection; only the ingest thread writes
device data.
"""

import asyncio
import csv
import io
import json
import re
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from capno_core.capability import captured_fraction

from .db import connect, utc_now
from .profile import MODE_TEXT

STATIC = Path(__file__).parent / "static"
COMMANDS = {"ARM", "DISARM", "ACK", "BASELINE", "MARK"}
NOTE_RE = re.compile(r"^[A-Za-z0-9=._, +\-]{0,40}$")
ALIAS_RE = re.compile(r"^[A-Za-z0-9_\-]{2,24}$")
ADDRESS_RE = re.compile(r"^\+?[0-9]{6,15}$")
EXPORT_TABLES = {"samples", "breaths", "status", "events", "markers", "perf", "notifications"}


class Command(BaseModel):
    cmd: str
    note: str = ""


class Recipient(BaseModel):
    alias: str
    channel: str = "log"
    address: str
    apikey: str | None = None
    levels: str = "CRITICAL,TECHNICAL"
    consent: bool = False


def mask(address):
    return "*" * max(0, len(address) - 3) + address[-3:]


def capability_view(profile):
    rr = profile.get("max_resolvable_rr") or 0.0
    mode = profile.get("mode", "UNMEASURED")
    view = dict(profile)
    view["mode_text"] = MODE_TEXT.get(mode, MODE_TEXT["UNMEASURED"]).format(rr=rr)
    t = profile.get("t_response_s")
    if t:
        view["captured_at"] = {str(r): round(captured_fraction(r, t), 2) for r in (6, 12, 20, 30)}
    return view


def create_app(ingestor, db_path):
    app = FastAPI(title="EXSU 620 Project 06 exhaled CO2 monitor", version="0.1.0")
    live = ingestor.live

    def ro():
        con = sqlite3.connect(db_path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    connect(db_path).close()      # make sure the schema exists before first read

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health():
        return {"ok": True, "source": live.source, "link_ok": live.link_ok,
                "rx": ingestor.rx_count, "bad_lines": ingestor.bad_lines}

    def status_payload():
        with live.lock:
            return {
                "status": live.status,
                "link_ok": live.link_ok,
                "last_rx": live.last_rx,
                "session_id": live.session_id,
                "source": live.source,
                "device": live.hello,
                "mismatch": list(live.mismatch),
            }

    @app.get("/api/status")
    def status():
        return status_payload()

    @app.get("/api/profile")
    def profile():
        return capability_view(live.profile)

    @app.get("/api/samples")
    def samples(since_seq: int = 0, limit: int = 2400):
        with live.lock:
            rows = [s for s in live.samples if s[0] > since_seq][-limit:]
        return [{"seq": s[0], "t": s[1], "co2": s[2], "vac": s[3], "d": s[4]} for s in rows]

    @app.get("/api/events")
    def events(limit: int = 100):
        with live.lock:
            return list(live.events)[-limit:]

    @app.get("/api/breaths")
    def breaths(limit: int = 100):
        with live.lock:
            return list(live.breaths)[-limit:]

    @app.get("/api/trend")
    def trend(minutes: float = 30.0):
        with ro() as con:
            rows = con.execute(
                "SELECT t_ms, host_ts, display, co2, et, et_kind, rr, vac FROM status"
                " WHERE session_id = ? AND host_ts >= (SELECT MAX(host_ts) FROM status"
                " WHERE session_id = ?) - ? ORDER BY t_ms",
                (live.session_id, live.session_id, minutes * 60)).fetchall()
        return [dict(r) for r in rows]

    @app.post("/api/command")
    def command(c: Command):
        cmd = c.cmd.upper()
        if cmd not in COMMANDS:
            raise HTTPException(400, f"cmd must be one of {sorted(COMMANDS)}")
        if cmd == "MARK":
            if not NOTE_RE.match(c.note):
                raise HTTPException(400, "marker notes are limited to 40 plain characters "
                                         "and must not identify anyone")
            line = f"MARK {c.note}".strip()
        else:
            line = cmd
        try:
            ingestor.send(line)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))
        return {"sent": line}

    @app.get("/api/recipients")
    def recipients():
        with ro() as con:
            rows = con.execute("SELECT id, alias, channel, address, levels, consent_at,"
                               " revoked_at FROM recipients ORDER BY id").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["address"] = mask(d["address"])
            out.append(d)
        return out

    @app.post("/api/recipients", status_code=201)
    def add_recipient(r: Recipient):
        if not r.consent:
            raise HTTPException(400, "recipient must opt in: consent must be true")
        if not ALIAS_RE.match(r.alias):
            raise HTTPException(400, "alias: 2-24 letters, digits, _ or - (no real names needed)")
        if not ADDRESS_RE.match(r.address):
            raise HTTPException(400, "address must be a phone number in international format")
        if r.channel not in ("log", "callmebot", "twilio"):
            raise HTTPException(400, "channel must be log, callmebot or twilio")
        levels = [x for x in r.levels.upper().split(",") if x]
        if not levels or any(x not in ("CRITICAL", "ADVISORY", "TECHNICAL") for x in levels):
            raise HTTPException(400, "levels: comma list of CRITICAL, ADVISORY, TECHNICAL")
        with ro() as con:
            try:
                cur = con.execute(
                    "INSERT INTO recipients (alias, channel, address, apikey, levels, consent_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (r.alias, r.channel, r.address, r.apikey, ",".join(levels), utc_now()))
            except sqlite3.IntegrityError:
                raise HTTPException(409, "alias already registered")
            con.commit()
            return {"id": cur.lastrowid}

    @app.delete("/api/recipients/{rid}")
    def revoke(rid: int):
        with ro() as con:
            cur = con.execute("UPDATE recipients SET revoked_at = ? WHERE id = ? AND"
                              " revoked_at IS NULL", (utc_now(), rid))
            con.commit()
            if cur.rowcount == 0:
                raise HTTPException(404, "no active recipient with that id")
        return {"revoked": rid}

    @app.get("/api/notifications")
    def notifications(limit: int = 50):
        with ro() as con:
            rows = con.execute(
                "SELECT n.id, n.level, n.message, n.queued_ts, n.sent_ts, n.ok, n.detail,"
                " r.alias FROM notifications n LEFT JOIN recipients r ON r.id = n.recipient_id"
                " ORDER BY n.id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["latency_s"] = None if d["sent_ts"] is None else round(d["sent_ts"] - d["queued_ts"], 3)
            out.append(d)
        return out

    @app.get("/api/export/{table}.csv")
    def export(table: str, session: int | None = None):
        if table not in EXPORT_TABLES:
            raise HTTPException(404, "unknown table")
        sid = session if session is not None else live.session_id
        with ro() as con:
            if table == "notifications":
                cur = con.execute("SELECT * FROM notifications ORDER BY id")
            else:
                cur = con.execute(f"SELECT * FROM {table} WHERE session_id = ? ORDER BY rowid",
                                  (sid,))
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([c[0] for c in cur.description])
            w.writerows(cur.fetchall())
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition":
                                          f"attachment; filename={table}_{sid}.csv"})

    @app.get("/api/stream")
    async def stream(since_seq: int = 0):
        async def gen():
            seq = since_seq
            ev_seq = 0
            while True:
                with live.lock:
                    new = [s for s in live.samples if s[0] > seq]
                    evs = [e for e in live.events if e["seq"] > ev_seq]
                if new:
                    seq = new[-1][0]
                if evs:
                    ev_seq = evs[-1]["seq"]
                payload = {"samples": [[s[0], s[1], s[2], s[3], s[4]] for s in new],
                           "events": evs, **status_payload()}
                yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(0.25)
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    return app
