# D6 — Verification plan

One protocol per engineering requirement. "Signs off" names the role in the
group who checks the evidence and initials the result in D7. Bench only: the
rig is a test lung or phantom; nothing touches a patient or in-service
clinical equipment. The reference capnograph is connected in parallel during
calibration and validation sessions only and is never a live channel during a
logging run.

## Common apparatus

* Bedside unit with the sampling line under test, pump on, water trap fitted.
* Test lung (or bag) ventilated by a self-inflating bag or the lab ventilator
  at a set rate; CO2 source: exhaled alveolar gas collected in a 3 L bag
  (≈ 4–5 %) or a certified calibration gas if the lab has one.
* Simulation lab capnograph sampling from the same T-piece (reference).
* Laptop running `python -m capno_service --serial <port>`; markers sent from
  the dashboard. Each session's database is archived with the report.
* Phone with high-frame-rate video (≥ 120 fps) for annunciation timing.

Group roles: **R1** hardware lead, **R2** firmware lead, **R3** service/data
lead, **R4** verification lead, **R5** documentation and safety lead.

## Protocols

| VP | ER | Method | Apparatus | Sample size | Acceptance criterion | Signs off |
|---|---|---|---|---|---|---|
| VP-1 | ER-1 | Arm, then start ventilation with CO2 at 10 and 20 /min; read time from arm to CONFIRMED from `events`. Repeat with room-air ventilation (oesophageal surrogate) and with a single 5 % bolus followed by room air (gastric washout). | Test lung, bag of exhaled gas, 3-way valve | 10 + 10 positive; 10 room air; 10 washout | Positive: 20/20 confirmed within 6 breath periods + delay + t10-90 + 1 s of CO2 at the inlet. Negative: NO CO2 raised 20/20 within timeout; CONFIRMED 0/20 | R4 |
| VP-2 | ER-2 | During confirmed ventilation at 12 /min, disconnect the circuit at the Y-piece (sampling line stays on the patient side T-piece, now in room air). Send marker `truth=disconnect` at the instant. Reconnect after 30 s; acknowledge only in the second half of trials. | Test lung, 2 m line | 20 disconnections | CRITICAL CO2_LOST 20/20; latency ≤ 20 s and ≤ published worst case; without ack still CRITICAL 60 s after reconnect (5/5) | R4 |
| VP-3 | ER-3 | Labelled fault dataset: clamp the line mid-way with a hose clamp (`truth=blocked`), pull the line off the monitor inlet (`truth=open`), unplug the CO2 module UART (`truth=sensor_off`), interleaved with normal ventilation (`truth=normal`) and real disconnections (`truth=disconnect`). Score with `python -m capno_analysis.fault_eval --db data/capno.db --session N`. Include ≥ 5 clamps with the test lung *stopped* (blocked line in front of apnoea). | Hose clamp, test lung | ≥ 10 blocked, ≥ 10 open, ≥ 5 sensor, ≥ 10 normal, ≥ 5 disconnect | Technical sensitivity ≥ 95 %, latency ≤ 3 s; faults presented as CRITICAL = 0 | R4, R2 |
| VP-4 | ER-4 | Ventilate at 6, 12, 20, 30 /min, 5 min each; compare median device rate with the set rate and the reference capnograph reading (transcribed each minute). Audit breaths table for a 30 min run. Sustained fall: reduce rate from 14 to 6 /min and hold 90 s (10 runs); brief dip: 15 s at 6 /min (10 runs). | Ventilator or metronome-paced bag, reference | ≥ 60 breaths per rate; 10 + 10 runs | Error ≤ ±1 /min at each rate; breath count matches set rate × time ±2 %; advisory 10/10 within 60 s of the change, 0/10 for dips | R3 |
| VP-5 | ER-5 | Step tests: line inlet in room air, then into the gas bag via a 3-way stopcock; press marker at the switch; hold ≥ 20 s (or until flat); switch back with a marker. `python -m capno_analysis.response_time --db … --session … --line-length L --append results/steps.csv --plot …` per length; then `python -m capno_analysis.profile build results/steps.csv --line-length 2.0 --sensor … --plot results/profile.png`. | Lines cut to 0.5, 1, 2, 3 m; 3-way stopcock; gas bag | ≥ 10 up + 10 down per length (80+ steps) | All quantities measured with CV ≤ 10 % at 2 m; fit R² reported; profile file published and shown on dashboard; firmware boot record matches (no mismatch banner) | R4, R1 |
| VP-5b | ER-5 | Model check: ventilate with CO2 at 10, 20, 30 /min alongside the reference; compare device median breath peak / reference end-tidal with `et_capture` predicted by the profile. | Test lung, reference | 2 min per rate | Within ±10 points at each rate; if not, derate `max_resolvable_rr` to the highest rate with measured fraction ≥ 0.9 and republish | R4 |
| VP-6 | ER-6 | Static: settle the line in each gas level (room air, and dilutions of exhaled gas or certified gas giving ≥ 5 levels to ~8 %) with the reference; record device median over 10 s and reference value into `results/cal.csv`; 3 repeats. `python -m capno_analysis.calibration fit results/cal.csv --plot results/cal.png`. Drift: room air and one span level every hour for 4 h → `calibration drift`. | Gas bags, reference | 5 levels × 3; 5 drift points | All corrected residuals within ±(0.43 % + 8 %); drift ≤ 0.1 % over 4 h | R1 |
| VP-7 | ER-7 | Film the ring and record audio at ≥ 120 fps while triggering each transition (disconnect, clamp, slow fall, recovery); align with the device `e` record time (send a marker with a visible LED flash first to align clocks). Check `perf` loop_max_ms for a 30 min run. Repeat disconnect and clamp with the USB data cable replaced by a power bank. Listen to and photograph each pattern. | Phone camera, power bank | 10 per transition type; 5 + 5 unplugged | ≤ 0.5 s in 40/40; loop max ≤ 100 ms; 10/10 annunciate unplugged; patterns as specified | R2, R5 |
| VP-8 | ER-8 | After the 30 min VP-4 run: count samples, breaths, status rows; export CSVs. Register two opted-in participants (one CallMeBot, one log); trigger 20 CRITICAL events (VP-2 run); read `/api/notifications` latency. Unplug USB 5 times; time to NO DATA on the dashboard (video). Review schema and API validators for identifier-capable fields. `pytest tests/test_service.py`. | Laptop, two phones | 30 min; 20 events; 5 unplugs | Samples within 1 % of 20 Hz × duration; notification latency median ≤ 10 s, p95 ≤ 20 s; NO DATA ≤ 5 s 5/5; no free-text identifier field | R3, R5 |

## Software verification (every commit)

`pytest` runs the logic against simulated scenarios that correspond to the
figures on the card and to each CR (see `tests/`). `python
tools/run_sim_verification.py` regenerates [sim_results.md](sim_results.md).
These verify the logic, not the hardware; they are necessary, not sufficient.

## Recording rules

* Every run's database file, CSVs, plots and the git commit hash of the
  firmware and service go in `results/<date>_<VP>/`.
* A requirement that is not met is reported as not met, with the evidence and
  a stated cause. Thresholds are not changed after seeing the result; if a
  threshold is changed for a reason, the old and new value and the reason are
  recorded and the test is repeated.
