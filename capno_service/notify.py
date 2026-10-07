"""Outbound messages to registered, consenting course participants (ER-8).

Messages are built only from fixed templates and alarm codes, so no free text
(and therefore no identifier) can reach a phone. Every attempt is logged with
its queue and send time, which is how notification latency is verified.
"""

import json
import os
import queue
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

TEMPLATES = {
    "CRITICAL": "EXSU620 bench monitor CRITICAL: {reason_text} at {clock}. Bench rig only.",
    "ADVISORY": "EXSU620 bench monitor advisory: {reason_text} at {clock}. Bench rig only.",
    "TECHNICAL": "EXSU620 bench monitor technical fault: {reason_text} at {clock}. "
                 "Patient status unknown, not apnoea. Bench rig only.",
}

REASON_TEXT = {
    "CO2_LOST": "exhaled CO2 lost with circuit connected",
    "NO_CO2": "no exhaled CO2 after airway placement",
    "CO2_NOT_SUSTAINED": "exhaled CO2 not sustained after placement",
    "ETCO2_LOW": "end-tidal CO2 low",
    "ETCO2_FALL": "end-tidal CO2 falling",
    "CO2_TREND_FALL": "CO2 trend falling",
    "RR_LOW": "breathing rate low",
    "RR_FALL": "breathing rate falling",
    "LINE_BLOCKED": "sampling line blocked",
    "LINE_OPEN": "sampling line open or disconnected at monitor",
    "LINE_SENSOR": "line pressure sensor not responding",
    "SENSOR_SILENT": "CO2 sensor not responding",
    "SENSOR_RANGE": "CO2 reading out of range",
    "SENSOR_COMMS": "CO2 sensor communication errors",
    "ZERO_DRIFT": "CO2 zero drift",
    "BASELINE_HIGH": "inspired CO2 high (zero drift or rebreathing)",
    "LINK_LOST": "laptop lost the serial link to the bedside unit",
}


def compose(level, reason, host_ts):
    parts = [REASON_TEXT.get(r, r) for r in (reason or "").split(",") if r]
    clock = datetime.fromtimestamp(host_ts).strftime("%H:%M:%S")
    return TEMPLATES[level].format(reason_text="; ".join(parts) or level.lower(), clock=clock)


def send_callmebot(address, apikey, text, timeout=10):
    q = urllib.parse.urlencode({"phone": address, "text": text, "apikey": apikey or ""})
    with urllib.request.urlopen("https://api.callmebot.com/whatsapp.php?" + q, timeout=timeout) as r:
        body = r.read(200).decode(errors="replace")
        return 200 <= r.status < 300, body


def send_twilio(address, apikey, text, timeout=10):
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    sender = os.environ["TWILIO_WHATSAPP_FROM"]
    data = urllib.parse.urlencode({"From": "whatsapp:" + sender, "To": "whatsapp:" + address,
                                   "Body": text}).encode()
    req = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data=data)
    import base64
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return 200 <= r.status < 300, json.loads(r.read()).get("sid", "")


def send_log(address, apikey, text, timeout=10):
    print(f"[notify -> {address}] {text}", flush=True)
    return True, "logged"


BACKENDS = {"log": send_log, "callmebot": send_callmebot, "twilio": send_twilio}


class Notifier:
    """Background sender. ``notify`` never blocks the ingest thread."""

    def __init__(self, db_path, backends=None):
        self.db_path = db_path
        self.backends = backends or BACKENDS
        self.q = queue.Queue()
        self.sent = []          # (level, message) for tests and the dashboard
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def notify(self, level, reason, event_id, event_host_ts):
        self.q.put((level, reason, event_id, event_host_ts, time.time()))

    def drain(self, timeout=5.0):
        end = time.time() + timeout
        while self.q.unfinished_tasks and time.time() < end:
            time.sleep(0.01)

    def _run(self):
        con = sqlite3.connect(self.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        while True:
            level, reason, event_id, event_ts, queued = self.q.get()
            try:
                text = compose(level, reason, event_ts)
                rows = con.execute(
                    "SELECT * FROM recipients WHERE revoked_at IS NULL").fetchall()
                for rcp in rows:
                    if level not in rcp["levels"].split(","):
                        continue
                    fn = self.backends.get(rcp["channel"], send_log)
                    try:
                        ok, detail = fn(rcp["address"], rcp["apikey"], text)
                    except Exception as exc:          # network, credentials, etc.
                        ok, detail = False, repr(exc)[:200]
                    con.execute(
                        "INSERT INTO notifications (event_id, recipient_id, level, message,"
                        " queued_ts, sent_ts, ok, detail) VALUES (?,?,?,?,?,?,?,?)",
                        (event_id, rcp["id"], level, text, event_ts, time.time(),
                         1 if ok else 0, str(detail)[:200]))
                    con.commit()
                self.sent.append((level, text))
            finally:
                self.q.task_done()
