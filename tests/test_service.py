import json
import time

import pytest
from fastapi.testclient import TestClient

from capno_service.app import create_app
from capno_service.ingest import Ingestor
from capno_service.notify import Notifier, compose
from capno_service.profile import UNMEASURED, compare_with_device, load_profile
from capno_service.rules import Rules
from capno_sim.run import records
from capno_sim.scenarios import SCENARIOS


class FakeSource:
    name = "fake"

    def __init__(self):
        self.sent = []

    def lines(self):
        return iter(())

    def send(self, cmd):
        self.sent.append(cmd)


class RecordingNotifier:
    def __init__(self):
        self.calls = []

    def notify(self, level, reason, event_id, host_ts):
        self.calls.append((level, reason))


@pytest.fixture
def setup(tmp_path):
    db = str(tmp_path / "t.db")
    src = FakeSource()
    notifier = RecordingNotifier()
    ing = Ingestor(src, db, load_profile(None), rules=Rules(notifier))
    ing.open()
    client = TestClient(create_app(ing, db))
    return ing, client, src, notifier, db


def feed(ing, scenario, t0=1000.0):
    """Replay a scenario with host time following device time, ticking the rules at 2 Hz."""
    next_tick = t0
    for r in records(SCENARIOS[scenario]()):
        now = t0 + r["t"] / 1000.0
        ing.handle_line(json.dumps(r), now)
        if now >= next_tick:
            ing.tick(now)
            next_tick += 0.5
    ing.writer.maybe_commit(force=True)


def test_ingest_logs_everything_and_notifies_critical(setup):
    ing, client, src, notifier, db = setup
    feed(ing, "disconnect")
    st = client.get("/api/status").json()
    assert st["status"]["display"] == "CRITICAL"
    assert ("CRITICAL", "CO2_LOST") in notifier.calls
    csv_text = client.get("/api/export/events.csv").text
    assert "CO2_LOST" in csv_text
    samples = client.get("/api/export/samples.csv").text.splitlines()
    assert len(samples) > 20 * 100
    assert len(client.get("/api/samples?limit=50").json()) == 50
    assert any(e.get("to") == "CRITICAL" for e in client.get("/api/events").json())
    assert client.get("/api/trend?minutes=60").json()


def test_technical_notifies_only_if_it_persists(setup):
    ing, client, src, notifier, db = setup
    feed(ing, "blocked_line")
    # blocked for 60 s: exactly one TECHNICAL message once the 10 s persistence passes
    assert notifier.calls.count(("TECHNICAL", "LINE_BLOCKED")) == 1
    assert not any(c[0] == "CRITICAL" for c in notifier.calls)


def test_link_loss_is_detected_and_logged(setup):
    ing, client, src, notifier, db = setup
    ing.handle_line(json.dumps({"type": "hello", "t": 0, "fw": "x", "profile": {}}), 100.0)
    ing.tick(101.0)
    assert ing.live.link_ok
    ing.tick(104.5)
    assert not ing.live.link_ok
    assert ("TECHNICAL", "LINK_LOST") in notifier.calls
    ing.handle_line(json.dumps({"type": "st", "t": 5000, "display": "NORMAL"}), 105.0)
    ing.tick(105.2)
    assert ing.live.link_ok
    kinds = [e["kind"] for e in client.get("/api/events").json()]
    assert kinds.count("link") == 2


def test_device_restart_starts_new_session(setup):
    ing, client, src, notifier, db = setup
    first = ing.live.session_id
    ing.handle_line(json.dumps({"type": "hello", "t": 0, "fw": "x", "profile": {}}), 1.0)
    ing.handle_line(json.dumps({"type": "hello", "t": 0, "fw": "x", "profile": {}}), 2.0)
    assert ing.live.session_id == first + 1


def test_non_json_lines_are_ignored(setup):
    ing, *_ = setup
    ing.handle_line("Traceback (most recent call last):", 1.0)
    ing.handle_line("{not json", 1.0)
    assert ing.bad_lines == 1 and ing.rx_count == 0


def test_commands_are_validated_and_forwarded(setup):
    ing, client, src, *_ = setup
    assert client.post("/api/command", json={"cmd": "ack"}).status_code == 200
    assert client.post("/api/command", json={"cmd": "MARK", "note": "step up L=2"}).status_code == 200
    assert client.post("/api/command", json={"cmd": "reboot"}).status_code == 400
    assert client.post("/api/command", json={"cmd": "MARK", "note": "patient <b>"}).status_code == 400
    assert src.sent == ["ACK", "MARK step up L=2"]


def test_recipients_require_consent_and_are_masked(setup):
    ing, client, *_ = setup
    bad = client.post("/api/recipients", json={"alias": "nurse_a", "address": "+15195550100"})
    assert bad.status_code == 400
    ok = client.post("/api/recipients", json={"alias": "nurse_a", "address": "+15195550100",
                                               "consent": True})
    assert ok.status_code == 201
    dup = client.post("/api/recipients", json={"alias": "nurse_a", "address": "+15195550101",
                                                "consent": True})
    assert dup.status_code == 409
    rows = client.get("/api/recipients").json()
    assert rows[0]["address"].endswith("100") and "519555" not in rows[0]["address"]
    assert rows[0]["consent_at"]
    assert client.delete(f"/api/recipients/{rows[0]['id']}").status_code == 200
    assert client.delete(f"/api/recipients/{rows[0]['id']}").status_code == 404


def test_profile_endpoint_says_unmeasured_by_default(setup):
    ing, client, *_ = setup
    p = client.get("/api/profile").json()
    assert p["status"] == "UNMEASURED"
    assert "not a capnograph" in p["mode_text"]


def test_profile_mismatch_and_unmonitored_line_are_reported():
    issues = compare_with_device({"max_resolvable_rr": 20.0, "t_response_s": 1.0},
                                 {"max_resolvable_rr": 0.0, "t10_90_ms": None,
                                  "line_monitored": False})
    assert len(issues) == 3


def test_unmeasured_file_never_upgrades_itself(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"status": "DRAFT", "max_resolvable_rr": 40}))
    p = load_profile(str(f))
    assert p["status"] == "UNMEASURED"


def test_notifier_delivers_to_consenting_recipients_and_logs_latency(tmp_path):
    from capno_service.db import connect
    db = str(tmp_path / "n.db")
    con = connect(db)
    con.execute("INSERT INTO recipients (alias, channel, address, levels, consent_at) VALUES"
                " ('a', 'log', '+1555', 'CRITICAL', 'now'), ('b', 'log', '+1666', 'ADVISORY', 'now')")
    con.execute("INSERT INTO recipients (alias, channel, address, levels, consent_at, revoked_at)"
                " VALUES ('c', 'log', '+1777', 'CRITICAL', 'now', 'later')")
    con.commit()
    sent = []
    n = Notifier(db, backends={"log": lambda a, k, t: (sent.append(a) or True, "ok")})
    n.notify("CRITICAL", "CO2_LOST", 1, time.time())
    n.drain()
    assert sent == ["+1555"]
    row = con.execute("SELECT queued_ts, sent_ts, ok FROM notifications").fetchone()
    assert row[2] == 1 and row[1] >= row[0]


def test_messages_contain_no_free_text():
    msg = compose("TECHNICAL", "LINE_BLOCKED", 0)
    assert "not apnoea" in msg and "sampling line blocked" in msg
    assert "Bench rig only" in compose("CRITICAL", "CO2_LOST", 0)
