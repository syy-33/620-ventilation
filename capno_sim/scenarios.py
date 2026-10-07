"""Named scenarios, each a list of Segments. Durations in seconds.

Segment labels are ground truth for capno_analysis.fault_eval:
normal, hypovent, disconnect, apnoea, no_co2, blocked, open, sensor_off,
standby, recovering (no expectation while the monitor settles).
"""

from .model import Segment


def figure2():
    """The sedation case of Figure 2: steady, slow fall, disconnection, recovery."""
    return [
        Segment(5, airway="room", label="standby", command="ARM"),
        Segment(150, rr=12, et=5.0, label="normal"),
        Segment(120, rr=(12, 9), et=(5.0, 2.2), label="hypovent"),
        Segment(15, rr=9, et=2.2, label="hypovent"),
        Segment(70, airway="room", label="disconnect"),
        Segment(5, rr=12, et=4.0, label="recovering", command="ACK"),
        Segment(60, rr=14, et=(4.0, 4.8), label="normal"),
    ]


def steady(rr=12, et=5.0, seconds=180):
    return [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(seconds, rr=rr, et=et, label="normal")]


def oesophageal():
    return [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(60, rr=10, et=4.0, airway="gastric", label="no_co2")]


def no_co2():
    return [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(60, rr=10, airway="room", label="no_co2")]


def disconnect():
    return [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(60, rr=12, et=5.0, label="normal"),
            Segment(40, airway="room", label="disconnect")]


def blocked_line():
    return [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(60, rr=12, et=5.0, label="normal"),
            Segment(60, rr=12, et=5.0, line="blocked", label="blocked"),
            Segment(40, rr=12, et=5.0, label="recovering")]


def open_line():
    return [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(60, rr=12, et=5.0, label="normal"),
            Segment(40, rr=12, et=5.0, line="open", label="open"),
            Segment(40, rr=12, et=5.0, label="recovering")]


def sensor_silent():
    return [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(60, rr=12, et=5.0, label="normal"),
            Segment(20, rr=12, et=5.0, sensor="silent", label="sensor_off"),
            Segment(30, rr=12, et=5.0, label="recovering")]


def apnoea():
    return [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(60, rr=12, et=5.0, label="normal"),
            Segment(40, rr=0, label="apnoea")]


def fault_dataset():
    """Labelled mix of every condition, for sensitivity / specificity."""
    segs = [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(60, rr=12, et=5.0, label="normal")]
    cycle = [
        Segment(30, rr=12, et=5.0, line="blocked", label="blocked"),
        Segment(40, rr=12, et=5.0, label="recovering"),
        Segment(30, airway="room", label="disconnect"),
        Segment(5, rr=12, et=5.0, label="recovering", command="ACK"),
        Segment(40, rr=12, et=5.0, label="normal"),
        Segment(25, rr=12, et=5.0, line="open", label="open"),
        Segment(40, rr=12, et=5.0, label="recovering"),
        Segment(30, rr=0, label="apnoea"),
        Segment(5, rr=16, et=5.0, label="recovering", command="ACK"),
        Segment(40, rr=16, et=5.0, label="normal"),
        Segment(10, rr=16, et=5.0, sensor="silent", label="sensor_off"),
        Segment(40, rr=16, et=5.0, label="recovering"),
        Segment(60, rr=20, et=4.8, label="normal"),
    ]
    for _ in range(5):
        segs.extend(cycle)
    return segs


def step_test(cycles=5, gas_pct=5.0):
    """Line inlet switched between room air and a constant gas (VP-5 rehearsal)."""
    segs = [Segment(10, airway="room", label="room")]
    for _ in range(cycles):
        segs.append(Segment(25, et=gas_pct, airway="gas", label="step up"))
        segs.append(Segment(25, airway="room", label="step down"))
    return segs


def bradypnoea():
    return [Segment(3, airway="room", label="standby", command="ARM"),
            Segment(150, rr=14, et=5.0, label="normal"),
            Segment(90, rr=6, et=5.5, label="hypovent")]


SCENARIOS = {
    "figure2": figure2,
    "steady": steady,
    "oesophageal": oesophageal,
    "no_co2": no_co2,
    "disconnect": disconnect,
    "blocked_line": blocked_line,
    "open_line": open_line,
    "sensor_silent": sensor_silent,
    "bradypnoea": bradypnoea,
    "apnoea": apnoea,
    "fault_dataset": fault_dataset,
    "step_test": step_test,
}
