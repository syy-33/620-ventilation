# D8 — Failure modes and mitigation

Severity (S), occurrence (O) and detectability (D) each rated 1–5 (5 = worst:
most harmful, most frequent, least detectable); RPN = S × O × D, before and
after mitigation. Ratings are the group's engineering judgement for the bench
rig and should be revisited after VP-3 and VP-7 with measured data.
"Verified by" names the automated test or bench protocol that shows the
mitigation works.

## Hardware and gas path

| ID | Failure mode | Effect | S | O | D | RPN | Mitigation implemented | Verified by | S·O·D after |
|---|---|---|---|---|---|---|---|---|---|
| FM-01 | Sampling line kinked or blocked by water | CO2 trace goes flat; could look like apnoea | 5 | 4 | 4 | 80 | Line vacuum from 2 × DPS310; LINE BLOCKED technical within 1.5 s; loss-of-CO2 critical suppressed while active and its window restarted after | `test_line_and_sensor_faults…`, `test_blocked_line_with_patient_apnoea…`, VP-3 | 5·4·1 = 20 |
| FM-02 | Line off at the monitor inlet / leak | Room air sampled; looks like disconnection | 4 | 3 | 4 | 48 | Vacuum drops below 0.45 × nominal → LINE OPEN technical | `open_line` scenario test, VP-3 | 4·3·1 = 12 |
| FM-03 | Water trap full, water in the cell | Wrong readings, sensor damage | 4 | 2 | 3 | 24 | Water trap in line; trap restricts flow when full → LINE BLOCKED; check before each session (README checklist) | VP-3 (clamp emulates) | 4·2·2 = 16 |
| FM-04 | Line pulled off at the **patient** end | Room air sampled; line resistance unchanged | 5 | 2 | 5 | 50 | Cannot be distinguished from circuit disconnection by gas or pressure. Raised as CRITICAL CO2 LOST, which is the safe direction for the patient; message says "check tube, circuit **and sampling line**". **Residual risk accepted and stated.** Possible future mitigation: airway pressure port at the T-piece. | `disconnect` scenario, VP-2 | 5·2·3 = 30 |
| FM-05 | Pump fails or stops | No sample flow; CO2 stagnant | 5 | 2 | 3 | 30 | Vacuum falls to ~0 → LINE OPEN technical | VP-3 (unplug pump: add to dataset) | 5·2·1 = 10 |
| FM-06 | CO2 module unplugged / UART fault | No readings | 5 | 2 | 2 | 20 | No frame for 2 s → SENSOR SILENT technical | `sensor_silent` scenario, VP-3 | 5·2·1 = 10 |
| FM-07 | Corrupt UART frames | Spurious values | 3 | 2 | 3 | 18 | Frame parse and checksum (MH-Z); errors counted, SENSOR COMMS technical; error count in `perf` | `firmware/sensors.py` review, VP-7 | 3·2·2 = 12 |
| FM-08 | Zero drift of NDIR | Baseline offset; mis-scaled end-tidal | 3 | 3 | 3 | 27 | Room-air check in standby (> 0.3 % for 60 s → ZERO DRIFT); negative readings; inspired-CO2 high check when breaths resolve; calibration gain/offset; drift test | `test_zero_drift_in_standby`, VP-6 | 3·3·2 = 18 |
| FM-09 | Pressure sensor fails | Line integrity unknown | 4 | 2 | 3 | 24 | Read failure → LINE SENSOR technical; if not fitted, boot record and dashboard say "line NOT monitored" | `test_unmonitored_line_makes_no_line_claims`, `compare_with_device` test | 4·2·1 = 8 |
| FM-10 | Speaker or amplifier fails | Silent alarm at bedside | 5 | 2 | 4 | 40 | Visual ring is independent; dashboard plays its own tone; phone notification for CRITICAL; power-up self-test cycles every colour and plays every tone so the operator checks light and sound before each case | VP-7 | 5·2·3 = 30 |
| FM-11 | Pico crash / brown-out (ring + pump on USB) | No monitoring at all | 5 | 2 | 2 | 20 | Laptop shows NO DATA within 3–5 s and notifies LINK LOST; current budget ≤ 500 mA (IF-16), ring brightness 0.3 | `test_link_loss_is_detected_and_logged`, VP-8 | 5·2·1 = 10 |

## Software

| ID | Failure mode | Effect | S | O | D | RPN | Mitigation implemented | Verified by | S·O·D after |
|---|---|---|---|---|---|---|---|---|---|
| FM-12 | Slow sensor: trace never returns to zero | Fixed thresholds miss every breath → false CO2 LOST | 5 | 4 | 4 | 80 | Envelope-relative thresholds; CO2 evidence is "any reading ≥ 1 %", not breath count | `test_rate_still_tracked_on_slow_sensor`, sim fault dataset at 5 s | 5·2·2 = 20 |
| FM-13 | Device claims capnography it cannot deliver | Clinician trusts an under-reading EtCO2 | 5 | 4 | 5 | 100 | Response measured (ER-5) and published; end-tidal labelled `attenuated` / `trend` above the limit with expected fraction; no claim when unmeasured; firmware/profile mismatch banner | `test_status_labels_rate_beyond_limit`, `test_unmeasured…`, `test_profile_mismatch…`, VP-5, VP-5b | 5·2·1 = 10 |
| FM-14 | Absolute EtCO2 threshold on attenuated peaks | False hypoventilation advisories | 3 | 4 | 3 | 36 | Absolute threshold only when breaths resolved; else relative fall | `test_slow_sensor_does_not_raise_absolute_low_advisory` | 3·1·2 = 6 |
| FM-15 | Apnoea gap kept in rate history | False RR LOW advisory after recovery | 3 | 3 | 3 | 27 | Intervals > 20 s reset the history (found in simulation, fixed) | `test_no_false_rate_advisory_after_apnoea_recovery…` | 3·1·2 = 6 |
| FM-16 | Latched NO CO2 masks a later disconnection | Stale reason shown | 4 | 2 | 4 | 32 | Reason updated to CO2 LOST while still latched | `test_disconnection_during_unacknowledged_no_co2…` | 4·1·2 = 8 |
| FM-17 | Gastric CO2 after oesophageal intubation confirms placement | Fatal misplacement missed | 5 | 2 | 4 | 40 | 6 breaths required, last 3 ≥ 50 % of first 3; timeout → NO CO2 | `test_washout_of_gastric_co2_never_confirms` | 5·1·2 = 10 |
| FM-18 | Technical fault hides a real loss of CO2 | Delayed critical | 5 | 2 | 4 | 40 | Loss window restarts at fault clear, so latency is bounded by one window after the line is restored; technical itself is annunciated and notified after 10 s | `test_after_fault_clears_a_real_loss_is_still_caught` | 5·2·2 = 20 |
| FM-19 | Laptop service down / sleeps | No logging, no phone alert | 3 | 3 | 2 | 18 | Alarms decided and annunciated on the Pico; laptop power settings in README; service restart starts a new session | VP-7 unplugged test | 3·3·1 = 9 |
| FM-20 | Notification provider down / rate-limited | Phone not alerted | 3 | 3 | 3 | 27 | Every attempt logged with ok/detail; two channels supported; bedside and dashboard alarms are primary | `test_notifier_delivers…`, VP-8 | 3·3·1 = 9 |
| FM-21 | Float precision on the Pico over long uptime | Timing errors | 3 | 3 | 4 | 36 | All core timing in integer milliseconds from `monotonic_ns()` | code review | 3·1·2 = 6 |

## Use and environment

| ID | Failure mode | Effect | S | O | D | RPN | Mitigation implemented | Verified by | S·O·D after |
|---|---|---|---|---|---|---|---|---|---|
| FM-22 | Operator forgets to arm | No NO CO2 alarm for a misplaced tube | 5 | 3 | 3 | 45 | Standby auto-confirms when CO2 appears, so loss is still caught afterwards; STANDBY shown dim white with "press Arm"; CONFIRMING progress ring | `test_device_commands`, demo | 5·2·2 = 20 |
| FM-23 | Accidental disarm during an alarm | Alarm cleared | 5 | 2 | 3 | 30 | Disarm needs a 5 s hold or a dashboard confirmation dialog; disarm logged as an event | `tests/test_annunciator_button.py` | 5·1·2 = 10 |
| FM-24 | Alarm fatigue from brief kinks | Alarms ignored | 3 | 3 | 2 | 18 | 1.5 s debounce; technical notified only after 10 s; advisory needs 30 s | `test_technical_notifies_only_if_it_persists`, `test_brief_dip_does_not_alarm` | 3·2·2 = 12 |
| FM-25 | Identifier typed into a marker or alias | Privacy breach | 4 | 2 | 3 | 24 | Notes limited to 40 plain characters; aliases restricted; messages from fixed templates only; numbers masked in API | `test_commands_are_validated…`, `test_messages_contain_no_free_text` | 4·1·2 = 8 |
| FM-26 | Reference capnograph left in the logging chain | Measurement integrity breached | 3 | 2 | 3 | 18 | Reference values only transcribed to CSV for calibration; no code path ingests it | design review | 3·1·2 = 6 |
| FM-27 | Wrong line length fitted after profiling | Published claims wrong | 4 | 3 | 4 | 48 | Profile records line length; README checklist; delay per metre shown on dashboard for a quick sanity check | VP-5 | 4·2·3 = 24 |

## Highest residual risks

1. **FM-04 / FM-27 / FM-10** carry the highest residual RPN. FM-04 is
   physics: without an airway pressure signal at the T-piece the device cannot
   say *which* end came off, only that CO2 is gone; it fails toward the
   critical alarm.
2. **FM-13** is the risk this project is about. Its mitigation is not a
   faster sensor but an honest one: the claim follows the measurement.
