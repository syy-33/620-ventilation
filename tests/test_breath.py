import pytest

from capno_core.breath import BreathDetector
from capno_core.config import make_config
from capno_sim.model import Rig, Segment


def detect(rr, t10_90, seconds=90, et=5.0, fs=20.0):
    cfg = make_config()
    det = BreathDetector(cfg)
    rig = Rig(t10_90_s=t10_90, delay_s=1.0, fs=fs)
    breaths = []
    last_t = 0
    for t, co2, vac, seg, first in rig.run([Segment(seconds, rr=rr, et=et)]):
        b = det.update(t, co2)
        if b:
            breaths.append(b)
        last_t = t
    return det, breaths, last_t


@pytest.mark.parametrize("rr", [6, 10, 12, 20, 30, 40])
def test_rate_within_one_breath_per_minute_fast_sensor(rr):
    det, breaths, t = detect(rr, 0.3)
    assert det.rate(t) == pytest.approx(rr, abs=1.0)
    assert all(b["co2"] for b in breaths[1:])


@pytest.mark.parametrize("rr", [8, 12, 20])
def test_rate_still_tracked_on_slow_sensor(rr):
    # The swing shrinks but stays above min_swing, so rate survives even where
    # end-tidal amplitude does not.
    det, breaths, t = detect(rr, 3.0)
    assert det.rate(t) == pytest.approx(rr, abs=1.0)


def test_no_breaths_in_room_air():
    det, breaths, t = detect(12, 0.3, et=0.0)
    assert breaths == []
    assert det.rate(t) is None


def test_small_oscillation_is_not_exhaled_co2():
    det, breaths, t = detect(12, 0.3, et=0.6)
    assert not any(b["co2"] for b in breaths)
    assert det.rate(t) is None


def test_very_slow_sensor_collapses_to_flat_and_reports_no_rate():
    det, breaths, t = detect(30, 30.0, seconds=120)
    assert det.rate(t) is None
