import math

import pytest

from capno_core import capability as cap


def test_tau_from_t10_90_matches_first_order_definition():
    tau = cap.tau_from_t10_90(2.0)
    # 10 % at tau ln(10/9), 90 % at tau ln 10
    assert tau * (math.log(10) - math.log(10 / 9)) == pytest.approx(2.0)


def test_fast_sensor_resolves_every_clinical_rate():
    assert cap.max_resolvable_rr(0.2) > 60
    assert cap.operating_mode(cap.max_resolvable_rr(0.2)) == "BREATH_BY_BREATH"


def test_slow_sensor_is_trend_only():
    rr = cap.max_resolvable_rr(10.0)
    assert rr < 6
    assert cap.operating_mode(rr) == "TREND_ONLY"


def test_unmeasured_makes_no_claim():
    assert cap.max_resolvable_rr(None) == 0.0
    assert cap.operating_mode(0.0) == "UNMEASURED"


def test_limit_is_monotonic_in_response_time():
    limits = [cap.max_resolvable_rr(t) for t in (0.3, 0.6, 1.0, 2.0, 4.0)]
    assert limits == sorted(limits, reverse=True)


def test_limit_is_the_boundary_of_the_criterion():
    t = 1.0
    rr = cap.max_resolvable_rr(t)
    assert cap.resolves(rr * 0.99, t)
    assert not cap.resolves(rr * 1.02, t)


def test_captured_fraction_falls_with_rate():
    f = [cap.captured_fraction(r, 2.0) for r in (6, 12, 20, 30)]
    assert f == sorted(f, reverse=True)
    assert 0 < f[-1] < 1


def test_loss_latency_adds_delay_lag_and_window():
    lat = cap.loss_alarm_latency_s(1.0, 0.0001, 15.0)
    assert lat == pytest.approx(16.0, abs=0.01)
    assert cap.loss_alarm_latency_s(None, 1.0, 15.0) is None
