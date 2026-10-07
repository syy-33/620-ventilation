# D9 — Traceability matrix and technical memorandum

## Traceability: clinical requirement → engineering requirement → verification → result

Every ER names the CR it serves; every verification names the ER it closes.
Results are entered from [D7](07_verification_report.md) only.

| CR | ER | What is measured | Verification | Automated logic check | Bench result |
|---|---|---|---|---|---|
| CR-1 | ER-1 | breaths to confirm; time to NO CO2; negatives never confirm | VP-1 | `test_presence_confirmed…`, `test_absence_is_called…` (no_co2, oesophageal), `test_washout…` | pending |
| CR-1 | ER-5 | response time behind the "stated number of breaths" | VP-5, VP-5b | `test_step_analysis…`, `test_profile_build…`, `tests/test_capability.py` | pending |
| CR-1 | ER-6 | CO2 accuracy at the 1 % presence threshold | VP-6 | `test_calibration_*` | pending |
| CR-1 | ER-7 | unambiguous display, annunciation ≤ 0.5 s | VP-7 | `tests/test_annunciator_button.py` | pending |
| CR-2 | ER-2 | latency disconnection → CRITICAL; latch | VP-2 | `test_disconnection_raises_critical…`, `test_critical_latches…`, `test_ack_before_recovery…`, `test_disconnection_during_unacknowledged…` | pending |
| CR-2 | ER-5 | published worst-case loss latency | VP-5 | `test_loss_latency_adds_delay_lag_and_window` | pending |
| CR-2 | ER-7 | bedside alarm with laptop unplugged | VP-7 | — (hardware) | pending |
| CR-2 | ER-8 | phone notification ≤ 10 s; link loss shown | VP-8 | `test_ingest_logs_everything_and_notifies_critical`, `test_link_loss…` | pending |
| CR-3 | ER-3 | fault latency; faults shown as critical = 0 | VP-3 | `test_line_and_sensor_faults…`, `test_blocked_line_with_patient_apnoea…`, `test_after_fault_clears…`, `test_fault_dataset_scores…` | pending |
| CR-3 | ER-7 | cyan + chirp distinct from red + 10-pulse | VP-7 | `test_technical_is_a_single_chirp`, `test_colours_and_flashing` | pending |
| CR-4 | ER-4 | rate ±1 /min; advisory on sustained fall; logging | VP-4 | `tests/test_breath.py`, `test_figure2_sequence`, `test_bradypnoea…`, `test_brief_dip…`, `test_breaths_are_recorded…`, `test_no_false_rate_advisory…` | pending |
| CR-4 | ER-5 | rate above which end-tidal is attenuated | VP-5b | `test_status_labels_rate_beyond_limit`, `test_slow_sensor_does_not_raise…` | pending |
| CR-4 | ER-8 | complete identifier-free record | VP-8 | `tests/test_service.py` | pending |

Failure modes trace to the ER whose mitigation they rely on in
[D8](08_failure_modes.md).

## Technical memorandum (for a non-specialist reader)

**To:** sedation and procedure-room leads  **From:** EXSU 620 Project 06 group
**Re:** What our exhaled-CO2 bench monitor can and cannot tell you

**Why it exists.** When a breathing tube ends up in the gullet instead of the
windpipe, or a patient under sedation starts breathing too little, the first
sign is in the carbon dioxide the patient breathes out. Oxygen saturation
falls minutes later. Many procedure rooms only have the oxygen monitor.

**What it does.** The monitor draws a small stream of gas from the mask or
tube through a thin tube to an infrared CO2 sensor. It answers three questions
with a coloured light, a tone, a laptop screen and, for the most serious
alarm, a phone message:

1. *Is breathed-out CO2 there?* After the airway is placed, the light shows
   progress breath by breath and turns green after six breaths with CO2.
   If CO2 never appears, or appears and fades (the pattern of a tube in the
   gullet), it alarms red.
2. *Has it disappeared?* If CO2 stops while the circuit should be connected,
   it alarms red with ten beeps and stays red until someone acknowledges it
   and CO2 has returned.
3. *Is breathing slowing or getting shallower?* A sustained fall in breathing
   rate or CO2 gives an amber three-beep warning.

**What makes the alarm trustworthy.** A kinked or blocked sampling tube looks
just like a patient who has stopped breathing. Our monitor measures the
suction in the sampling tube, so it can tell the two apart: a blocked or
loose tube gives a *cyan* light with a short chirp and the words "patient
status unknown — not apnoea". It never turns that into the red "no CO2" alarm.
One case it cannot separate: if the thin tube is pulled off at the patient
end, it alarms red, because it cannot tell that apart from the breathing
circuit coming off. We chose to fail toward the louder alarm.

**What it is not.** A hospital capnograph shows the shape of every breath and
an accurate end-tidal CO2 number. Whether our low-cost sensor can do that
depends on how fast it responds, so we measured that instead of assuming it.
The dashboard states the measured response time, the longest delay before a
"CO2 lost" alarm, and the fastest breathing rate at which individual breaths
are shown faithfully. Above that rate, the CO2 number is labelled as
under-reading and the device describes itself as a trend monitor. If the
response time has not been measured, it says so and makes no claim.

**Limits.** Bench prototype for teaching. It has only been tested with a test
lung; it has not been near a patient and must not be. No patient information
is stored or sent; phone messages go only to course participants who opted in.
