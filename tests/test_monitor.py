"""Scenario tests for the alarm logic against the clinical requirements."""

import pytest

from capno_core.config import make_config
from capno_core.device import Device
from capno_core.monitor import CO2_LOST, CRITICAL, Monitor, NO_CO2
from capno_sim.model import Segment
from capno_sim.scenarios import SCENARIOS

from helpers import alarm_events, marker_time, run_scenario


# ---------------------------------------------------------------- CR-1
def test_presence_confirmed_within_six_breaths_plus_instrument_lag():
    recs, _ = run_scenario(SCENARIOS["steady"](rr=12))
    conf = alarm_events(recs, "monitor", "CONFIRMED")[0]
    start = marker_time(recs, "normal")
    # six breaths at 12/min is 30 s; allow delay + one rise time
    assert conf["t"] - start <= 30000 + 1000 + 300 + 500


@pytest.mark.parametrize("scenario", ["no_co2", "oesophageal"])
def test_absence_is_called_not_silently_waited_on(scenario):
    recs, _ = run_scenario(SCENARIOS[scenario]())
    crit = alarm_events(recs, "alarm", "CRITICAL")
    assert crit and crit[0]["reason"] in (NO_CO2, "CO2_NOT_SUSTAINED")
    assert not alarm_events(recs, "monitor", "CONFIRMED")


def test_washout_of_gastric_co2_never_confirms():
    recs, _ = run_scenario(SCENARIOS["oesophageal"]())
    assert not alarm_events(recs, "monitor", "CONFIRMED")


# ---------------------------------------------------------------- CR-2
@pytest.mark.parametrize("t10_90,delay", [(0.3, 1.0), (2.0, 2.0), (5.0, 3.0)])
def test_disconnection_raises_critical_within_published_latency(t10_90, delay):
    from capno_core.capability import loss_alarm_latency_s
    recs, _ = run_scenario(SCENARIOS["disconnect"](), t10_90_s=t10_90, delay_s=delay,
                           fs=20 if t10_90 < 5 else 2)
    crit = alarm_events(recs, "alarm", "CRITICAL")
    assert crit and crit[0]["reason"] == CO2_LOST
    latency = (crit[0]["t"] - marker_time(recs, "disconnect")) / 1000
    assert latency <= loss_alarm_latency_s(delay, t10_90, 20.0)


def test_critical_latches_until_acknowledged_and_back_in_range():
    segs = SCENARIOS["disconnect"]() + [Segment(60, rr=12, et=5.0, label="normal")]
    recs, _ = run_scenario(segs)
    assert not alarm_events(recs, "alarm", "NORMAL")      # never acknowledged: stays latched
    segs[-1].command = "ACK"
    recs, _ = run_scenario(segs)
    cleared = alarm_events(recs, "alarm", "NORMAL")
    assert cleared and cleared[0]["reason"] == "acknowledged and back in range"


def test_ack_before_recovery_keeps_alarm_until_co2_returns():
    segs = SCENARIOS["disconnect"]()
    segs[-1].duration_s = 25
    segs.append(Segment(10, airway="room", label="disconnect", command="ACK"))
    segs.append(Segment(30, rr=12, et=5.0, label="recovering"))
    recs, _ = run_scenario(segs)
    ack_t = next(r["t"] for r in recs if r["type"] == "e" and r["kind"] == "ack")
    cleared = alarm_events(recs, "alarm", "NORMAL")[0]
    assert cleared["t"] >= marker_time(recs, "recovering") > ack_t


def test_disconnection_during_unacknowledged_no_co2_updates_reason():
    segs = [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(50, airway="room", label="no_co2"),
            Segment(45, rr=12, et=5.0, label="recovering"),
            Segment(30, airway="room", label="disconnect")]
    recs, _ = run_scenario(segs)
    reasons = [r["reason"] for r in alarm_events(recs, "alarm", "CRITICAL")]
    assert reasons == [NO_CO2, CO2_LOST]


# ---------------------------------------------------------------- CR-3
@pytest.mark.parametrize("scenario,code", [("blocked_line", "LINE_BLOCKED"),
                                           ("open_line", "LINE_OPEN"),
                                           ("sensor_silent", "SENSOR_SILENT")])
def test_line_and_sensor_faults_are_technical_never_critical(scenario, code):
    recs, _ = run_scenario(SCENARIOS[scenario]())
    tech = alarm_events(recs, "technical", code)
    assert tech
    assert not alarm_events(recs, "alarm", "CRITICAL")


def test_fault_reported_within_debounce():
    recs, _ = run_scenario(SCENARIOS["blocked_line"]())
    t_fault = alarm_events(recs, "technical", "LINE_BLOCKED")[0]["t"]
    assert t_fault - marker_time(recs, "blocked") <= 2000


def test_blocked_line_with_patient_apnoea_behind_it_is_still_technical():
    segs = [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(60, rr=12, et=5.0, label="normal"),
            Segment(60, rr=0, line="blocked", label="blocked")]
    recs, _ = run_scenario(segs)
    assert alarm_events(recs, "technical", "LINE_BLOCKED")
    assert not alarm_events(recs, "alarm", "CRITICAL")


def test_after_fault_clears_a_real_loss_is_still_caught():
    segs = [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(60, rr=12, et=5.0, label="normal"),
            Segment(20, rr=12, et=5.0, line="blocked", label="blocked"),
            Segment(40, airway="room", label="disconnect")]
    recs, _ = run_scenario(segs)
    crit = alarm_events(recs, "alarm", "CRITICAL")
    assert crit and crit[0]["reason"] == CO2_LOST


def test_unmonitored_line_makes_no_line_claims():
    recs, _ = run_scenario(SCENARIOS["blocked_line"](), cfg_overrides={"line_monitored": False})
    assert not alarm_events(recs, "technical")
    hello = recs[0]
    assert hello["profile"]["line_monitored"] is False


def test_out_of_range_reading_is_a_sensor_fault():
    m = Monitor(make_config())
    out = []
    for t in range(0, 2000, 50):
        out += m.update(t, 25.0, 10.0)
    assert "SENSOR_RANGE" in m.technical


def test_zero_drift_in_standby():
    m = Monitor(make_config())
    for t in range(0, 65000, 100):
        m.update(t, 0.6, 10.0)
    assert "ZERO_DRIFT" in m.technical


# ---------------------------------------------------------------- CR-4
def test_figure2_sequence():
    recs, _ = run_scenario(SCENARIOS["figure2"]())
    seq = [(r["to"], r["reason"]) for r in alarm_events(recs, "alarm")]
    assert [s[0] for s in seq] == ["ADVISORY", "CRITICAL", "NORMAL"]
    adv_t = alarm_events(recs, "alarm", "ADVISORY")[0]["t"]
    assert marker_time(recs, "hypovent") < adv_t < marker_time(recs, "disconnect")


def test_bradypnoea_advisory_after_sustained_fall():
    recs, _ = run_scenario(SCENARIOS["bradypnoea"]())
    adv = alarm_events(recs, "alarm", "ADVISORY")
    assert adv and "RR" in adv[0]["reason"]
    assert adv[0]["t"] - marker_time(recs, "hypovent") >= 30000


def test_brief_dip_does_not_alarm():
    segs = [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(150, rr=12, et=5.0, label="normal"),
            Segment(15, rr=12, et=2.0, label="normal"),
            Segment(60, rr=12, et=5.0, label="normal")]
    recs, _ = run_scenario(segs)
    assert not alarm_events(recs, "alarm")


def test_advisory_clears_after_thirty_seconds_in_range():
    segs = SCENARIOS["bradypnoea"]() + [Segment(90, rr=14, et=5.0, label="normal")]
    recs, _ = run_scenario(segs)
    adv = alarm_events(recs, "alarm", "ADVISORY")[0]
    back = alarm_events(recs, "alarm", "NORMAL")[0]
    assert back["t"] - marker_time(recs, "normal") >= 30000 - 1
    assert back["t"] > adv["t"]


def test_breaths_are_recorded_through_the_procedure():
    recs, _ = run_scenario(SCENARIOS["steady"](rr=15, seconds=120))
    co2_breaths = [r for r in recs if r["type"] == "b" and r["co2"]]
    assert 28 <= len(co2_breaths) <= 31
    status = [r for r in recs if r["type"] == "st"]
    assert len(status) >= 120


def test_slow_sensor_does_not_raise_absolute_low_advisory():
    # Attenuated peaks under-read: only a fall relative to baseline counts.
    recs, _ = run_scenario(SCENARIOS["steady"](rr=20, seconds=300), t10_90_s=6.0, fs=2)
    assert not alarm_events(recs, "alarm", "ADVISORY")
    st = [r for r in recs if r["type"] == "st"][-1]
    assert st["et_kind"] in ("attenuated", "trend")


def test_status_labels_rate_beyond_limit():
    recs, _ = run_scenario(SCENARIOS["steady"](rr=24, seconds=90), t10_90_s=2.0)
    st = [r for r in recs if r["type"] == "st"][-1]
    assert st["rr_note"] == "beyond_limit"
    assert st["et_kind"] == "attenuated"
    assert 0 < st["et_capture"] < 1


def test_unmeasured_profile_flags_rate_as_unverified():
    cfg = make_config()
    dev = Device(cfg)
    from capno_sim.model import Rig
    rig = Rig()
    st = None
    for t, co2, vac, seg, first in rig.run(SCENARIOS["steady"](seconds=60)):
        for r in dev.step(t, co2, vac):
            if r["type"] == "st":
                st = r
    assert st["rr_note"] == "unverified"


# ---------------------------------------------------------------- commands
def test_disarm_clears_patient_alarms(cfg):
    m = Monitor(cfg)
    m.arm(0)
    for t in range(0, 60000, 50):
        m.update(t, 0.04, 10.0)
    assert m.alarm == CRITICAL
    out = m.disarm(60000)
    assert m.alarm == "NORMAL" and m.mon == "STANDBY"
    assert any(e["kind"] == "alarm" for e in out)


def test_device_commands(cfg):
    d = Device(cfg)
    assert d.command(0, "ARM")[0]["to"] == "CONFIRMING"
    assert d.command(0, "MARK step up")[0] == {"type": "m", "t": 0, "note": "step up"}
    assert d.command(0, "BOGUS")[0]["type"] == "err"
    assert d.command(0, "   ") == []


def test_no_false_rate_advisory_after_apnoea_recovery_on_slow_sensor():
    # Regression: the apnoea gap and breaths missed while a slow sensor recovered
    # used to stay in the rate history and trip RR_LOW in the normal stretch after.
    segs = [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(90, rr=16, et=5.0, label="normal"),
            Segment(30, rr=0, label="apnoea"),
            Segment(5, rr=16, et=5.0, label="recovering", command="ACK"),
            Segment(120, rr=16, et=5.0, label="normal")]
    recs, _ = run_scenario(segs, t10_90_s=5.0, delay_s=1.5, fs=2)
    assert not alarm_events(recs, "alarm", "ADVISORY")
    assert alarm_events(recs, "alarm", "CRITICAL")


def test_long_gap_is_not_used_as_a_rate():
    from capno_core.breath import BreathDetector
    det = BreathDetector(make_config())
    det.intervals.append(4000)
    det.intervals.append(4000)
    det.last_rise_t = 0
    det.rise_t = 30000
    det.peak = 5.0
    b = det._complete(31000)
    assert b["interval_ms"] is None and len(det.intervals) == 0
