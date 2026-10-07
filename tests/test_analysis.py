import csv

import numpy as np
import pytest

from capno_analysis import calibration, fault_eval, profile, response_time
from capno_analysis.data import from_records
from capno_sim.run import records
from capno_sim.scenarios import SCENARIOS


@pytest.mark.parametrize("t10_90,delay", [(0.3, 0.8), (1.5, 2.0), (4.0, 1.0)])
def test_step_analysis_recovers_simulated_delay_and_rise(t10_90, delay):
    run = from_records(records(SCENARIOS["step_test"](cycles=3), t10_90, delay))
    rows = response_time.analyse_run(run, 2.0, marker_filter="step")
    ok = [r for r in rows if r["ok"]]
    assert len(ok) == 6
    tau = t10_90 / np.log(9)
    for r in ok:
        assert r["t10_90_s"] == pytest.approx(t10_90, rel=0.1, abs=0.06)
        # first-order lag reaches 10 % at tau * ln(10/9) after the delay
        assert r["delay_s"] == pytest.approx(delay + tau * np.log(10 / 9), abs=0.08)
    assert {r["direction"] for r in ok} == {"up", "down"}


def test_step_rejected_when_gas_not_held_long_enough():
    t = np.arange(0, 30, 0.05)
    y = np.where(t < 10, 0.04, 0.04 + 5 * (1 - np.exp(-(t - 10) / 20)))
    r = response_time.analyse_step(t, y, 10.0, 14.0)
    assert not r["ok"]


def test_profile_build_and_delay_fit(tmp_path):
    out = tmp_path / "steps.csv"
    for L in (0.5, 1.0, 2.0, 3.0):
        run = from_records(records(SCENARIOS["step_test"](cycles=3), 1.0, 0.2 + 0.5 * L))
        response_time.append_csv(str(out), response_time.analyse_run(run, L, marker_filter="step"))
    prof = profile.build(str(out), 2.0, "sim")
    assert prof["status"] == "MEASURED"
    assert prof["delay_vs_length"]["slope_s_per_m"] == pytest.approx(0.5, abs=0.02)
    assert prof["delay_vs_length"]["r2"] > 0.99
    assert prof["t_response_s"] == pytest.approx(1.0, abs=0.1)
    assert prof["mode"] == "PARTIAL"
    assert all(v["pass"] for v in prof["repeatability"].values())
    assert '"t10_90_ms"' in profile.firmware_block(prof)
    with open(out) as f:
        assert len(list(csv.DictReader(f))) == 24


def test_profile_refuses_without_data_at_deployed_length(tmp_path):
    out = tmp_path / "steps.csv"
    run = from_records(records(SCENARIOS["step_test"](cycles=1), 1.0, 1.0))
    response_time.append_csv(str(out), response_time.analyse_run(run, 1.0, marker_filter="step"))
    with pytest.raises(SystemExit):
        profile.build(str(out), 2.0, "sim")


def test_calibration_fit_recovers_gain_and_offset():
    ref = np.array([0.0, 1.0, 2.5, 5.0, 7.5])
    dev = 0.9 * ref + 0.2
    r = calibration.fit(ref, dev)
    assert r["gain"] == pytest.approx(1 / 0.9)
    assert r["offset_pct"] == pytest.approx(-0.2 / 0.9)
    assert r["max_abs_error_pct"] < 1e-9 and r["pass"]


def test_calibration_fails_on_nonlinear_sensor():
    ref = np.array([0.0, 1.0, 2.5, 5.0, 7.5, 10.0])
    dev = ref + 0.12 * ref ** 2
    assert not calibration.fit(ref, dev)["pass"]


def test_drift_slope():
    r = calibration.drift([0, 1, 2, 3], [5, 5, 5, 5], [5.0, 5.1, 5.2, 5.3])
    assert r["error_slope_pct_per_h"] == pytest.approx(0.1)


def test_fault_dataset_scores_perfectly_in_simulation():
    run = from_records(records(SCENARIOS["fault_dataset"]()))
    s = fault_eval.summarise(fault_eval.evaluate(run))
    assert s["critical_sensitivity"] == 1.0
    assert s["technical_sensitivity"] == 1.0
    assert s["faults_presented_as_critical"] == 0
    assert s["false_alarms_in_normal"] == 0


def test_fault_eval_catches_a_fault_presented_as_apnoea():
    # Without line monitoring a blocked line cannot be told apart: the scorer must say so.
    run = from_records(records(SCENARIOS["fault_dataset"](),
                               cfg_overrides={"line_monitored": False}))
    s = fault_eval.summarise(fault_eval.evaluate(run))
    assert s["technical_sensitivity"] < 1.0
