# D7 — Verification report

**Status: bench verification not yet performed.** This file is the report
skeleton with the analysis commands wired in. Only the software/simulation
evidence below exists today; every bench cell reads *pending* until the
protocol in [D6](06_verification_plan.md) has been run. Do not fill a cell
from the simulator.

Run identification for each bench session: date, commit hash, sensor module
and serial, line length, pump, database file, operator roles.

## Summary

| ER | Requirement (short) | Simulation / software evidence | Bench result | Pass / fail |
|---|---|---|---|---|
| ER-1 | confirm in 6 breaths; NO CO2 on absence | `test_presence_confirmed…`, `test_absence_is_called…`, `test_washout…`; [sim §3](sim_results.md) | pending | pending |
| ER-2 | CO2 LOST ≤ 20 s, latched | `test_disconnection_raises_critical…` (3 sensor speeds), `test_critical_latches…`; sim median 11.8–15.0 s | pending | pending |
| ER-3 | faults technical ≤ 3 s, 0 as critical | `test_line_and_sensor_faults…`, `test_blocked_line_with_patient_apnoea…`; sim: 0 of 15 fault segments critical at each of 4 sensor speeds | pending | pending |
| ER-4 | rate ±1 /min; advisory on sustained fall | `tests/test_breath.py`, `test_figure2_sequence`, `test_brief_dip…`; [sim §1](sim_results.md) | pending | pending |
| ER-5 | response time measured, published | analysis recovers simulated delay and t10-90 (`test_step_analysis…`); profile pipeline (`test_profile_build…`) | pending | pending |
| ER-6 | ±(0.43 % + 8 %); drift ≤ 0.1 %/4 h | `test_calibration_*` (fit maths only) | pending | pending |
| ER-7 | annunciation ≤ 0.5 s; laptop independent | `tests/test_annunciator_button.py` (patterns) | pending | pending |
| ER-8 | complete log; notify ≤ 10 s | `tests/test_service.py` | pending | pending |

## ER-5 Response time (do this first: every other result depends on it)

| Line length (m) | n up / down | Delay mean ± SD (s) | t10-90 rise mean ± SD (s) | t90-10 fall mean ± SD (s) | CV max |
|---|---|---|---|---|---|
| 0.5 | | | | | |
| 1.0 | | | | | |
| 2.0 | | | | | |
| 3.0 | | | | | |

Delay vs length fit: slope ___ s/m, intercept ___ s, R² ___ (insert `results/profile.png`).

Published profile (`config/response_profile.json`): t_response ___ s, delay ___ s,
breath-by-breath limit ___ /min, mode ___, loss-of-CO2 worst-case latency ___ s.

**Statement for the dossier** (copy the `statement` field verbatim): ___

VP-5b model check:

| Rate (/min) | Reference EtCO2 (%) | Device median peak (%) | Measured fraction | Predicted `et_capture` | Difference (points) |
|---|---|---|---|---|---|
| 10 | | | | | |
| 20 | | | | | |
| 30 | | | | | |

## ER-6 Calibration curve and residuals

Insert `results/cal.png`. n = ___, device = ___ × reference + ___ %, corrected
RMSE ___ %, max |error| ___ %, ___/___ within limit. Firmware `CO2_GAIN` ___,
`CO2_OFFSET_PCT` ___. Drift over 4 h: ___ %/h.

## ER-1 / ER-2 / ER-3 Labelled fault dataset, alarm latency, sensitivity and specificity

Paste the output of `python -m capno_analysis.fault_eval --db … --session …`:

| label | n | detected | median latency s | max latency s | forbidden alarms |
|---|---|---|---|---|---|
| | | | | | |

critical sensitivity ___, critical specificity ___, technical sensitivity ___,
faults presented as critical ___, false alarms in normal ___.

Confirmation (VP-1): positive ___/20 within limit, slowest ___ s; room air NO CO2 ___/10;
washout NO CO2 ___/10; CONFIRMED in negatives ___/20.

## ER-4 Rate

| Set rate (/min) | Breaths | Device median (/min) | Reference (/min) | Max error | Pass |
|---|---|---|---|---|---|
| 6 | | | | | |
| 12 | | | | | |
| 20 | | | | | |
| 30 | | | | | |

Advisory on sustained fall ___/10 (latency ___ s); on 15 s dip ___/10.

## ER-7 Annunciation

Latency by transition (video): ___. Loop max over 30 min ___ ms. Laptop unplugged ___/10.

## ER-8 Logging and notification

Samples ___ vs expected ___ (___ %). Notification latency median ___ s, p95 ___ s
(n = ___). NO DATA after unplug ___ s (5/5?). Schema review: ___.

## Requirements not met

For each: evidence, stated cause, and what would fix it. Do not reword the
requirement to match the result.
