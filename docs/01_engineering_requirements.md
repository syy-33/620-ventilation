# D1 — Engineering requirements

Project 06, "Is the patient ventilating". Eight engineering requirements (ER)
derived from the four clinical requirements (CR) on the project card. Each one
states a range, a rate, a latency or an accuracy, names the CR it serves, and
has an acceptance criterion that a test can pass or fail. The verification
method for each is in [D6](06_verification_plan.md); results go in
[D7](07_verification_report.md). Every numeric threshold below lives in
`capno_core/config.py` under the key named in brackets.

Units: CO2 in percent by volume (1 % ≈ 7.6 mmHg at sea level), time in
seconds, rate in breaths per minute (/min).

## Clinical requirements (from the card)

| ID | Requirement |
|---|---|
| CR-1 | The presence or absence of exhaled carbon dioxide shall be confirmed within a stated number of breaths and displayed unambiguously. |
| CR-2 | Loss of carbon dioxide while the circuit is reported as connected shall raise an immediate alarm, since it is the signature of a misplaced tube or a disconnection. |
| CR-3 | A blocked or disconnected sampling line shall be reported as a fault and shall never present as apnoea. |
| CR-4 | Breathing rate derived from the carbon dioxide signal shall be recorded through the procedure, with alarms on a sustained fall. |

## Engineering requirements

### ER-1 — Confirm presence or absence of exhaled CO2 within six breaths (CR-1)

* **Definition.** A *CO2 breath* is a detected breath whose peak reaches
  ≥ 1.0 % CO2 [`co2_breath_min_pct`]. After the operator arms the monitor
  (airway placed), placement is **confirmed** after **6 consecutive CO2
  breaths** [`confirm_breaths`] whose last three peaks are each ≥ 50 % of the
  largest of the first three [`confirm_sustain_frac`] — decaying gastric CO2
  fails this test. Where the hardware cannot resolve breaths, a breath-averaged
  mean ≥ 1.0 % held for 30 s also confirms [`trend_confirm_ms`].
* **Absence.** If placement is not confirmed within
  40 s + transport delay + 2 × t10-90 of arming [`confirm_timeout_ms`], a
  CRITICAL **NO EXHALED CO2** alarm is raised.
* **Display.** Exactly one of STANDBY (dim white), CONFIRMING *n*/6 (white
  progress ring), CONFIRMED/NORMAL (green), NO CO2 (red, flashing, 10-pulse
  tone) is shown on the ring and the dashboard at any time.
* **Acceptance.** On the test lung at 10 and 20 /min with exhaled-gas CO2:
  confirmation in 20/20 trials within 6 breath periods + delay + t10-90 + 1 s
  of the first CO2 breath reaching the line inlet. With room-air ventilation
  (simulated oesophageal intubation) and with a decaying CO2 bolus: NO CO2
  raised in 20/20 trials within the stated timeout, and CONFIRMED shown in 0/20.

### ER-2 — Loss of CO2 while connected raises a latched critical alarm within 20 s (CR-2)

* **Definition.** Once placement is confirmed the circuit is *reported as
  connected*. If, with no technical fault active, no reading reaches 1.0 % for
  the loss window W = 2 × median breath interval, clamped to 10–20 s
  [`loss_window_*`], a CRITICAL **CO2 LOST** alarm is raised. It is latched
  until acknowledged *and* at least 2 CO2 breaths have returned [`recover_breaths`].
* **Published latency.** Worst case = transport delay + lag for the reading to
  fall from end-tidal to 1.0 % + W, computed from the measured response profile
  (`capno_core.capability.loss_alarm_latency_s`) and shown on the dashboard.
* **Acceptance.** 20 circuit disconnections at 12 /min on the deployed 2 m line:
  CRITICAL in 20/20, each ≤ 20 s from disconnection and ≤ the published worst
  case. Alarm still active (latched) 60 s after reconnection without
  acknowledgement in 5/5 trials.

### ER-3 — Sampling-line and sensor faults are technical, never apnoea (CR-3)

* **Definition.** With the pump running, line vacuum (ambient minus pump inlet
  pressure) is compared to its value with a clear line [`line_vac_nominal_kpa`]:
  above 1.8 × nominal for 1.5 s → **LINE BLOCKED**; below 0.45 × nominal for
  1.5 s → **LINE OPEN** (disconnected or leaking at the monitor)
  [`line_block_factor`, `line_open_factor`, `line_fault_debounce_ms`]. No CO2
  frame for 2 s → **SENSOR SILENT**; reading outside −0.5…20 % → **SENSOR
  RANGE**; room air reading off by > 0.3 % for 60 s in standby, or below
  −0.2 % for 5 s → **ZERO DRIFT**.
* **Behaviour.** A technical fault is shown cyan with a chirp and the text
  "patient status unknown — not apnoea". While any technical fault is active,
  the loss-of-CO2 critical alarm is not raised, and when the fault clears the
  loss window restarts from that moment.
* **Acceptance.** Labelled fault dataset on the bench (≥ 10 line clamps,
  ≥ 10 disconnections at the monitor inlet, ≥ 5 sensor unplugs, interleaved
  with normal ventilation): technical sensitivity ≥ 95 %, latency ≤ 3 s, and
  **0** fault segments presented as CRITICAL (zero tolerance).
* **Stated limitation.** A sampling line pulled off at the *patient* end leaves
  line resistance unchanged and is physically indistinguishable from a circuit
  disconnection; it raises CRITICAL CO2 LOST (the fail-safe direction). See
  [D8](08_failure_modes.md) FM-04.

### ER-4 — Breathing rate ±1 /min, logged throughout, advisory on a sustained fall (CR-4)

* **Rate.** 60 000 / median of the last 6 CO2-breath intervals [`rr_intervals`];
  an interval > 20 s is an apnoea and resets the history.
* **Recording.** Every breath (start time, peak, interval) and a 1 Hz status
  row (state, CO2, end-tidal, rate, line vacuum) are stored for the whole
  session.
* **Advisory.** ADVISORY when, for ≥ 30 s [`advisory_sustain_ms`]: rate
  < 8 /min or ≥ 40 % below its baseline; or end-tidal < 3.0 % (only when
  breaths are resolved) or ≥ 30 % below its baseline. Baseline = median over the
  first 120 s after confirmation. Clears after 30 s back in range (Figure 3).
* **Acceptance.** Rate error ≤ ±1 /min against the ventilator / test-lung set
  rate and the reference capnograph at 6, 12, 20 and 30 /min (≥ 60 breaths
  each). 100 % of breaths in a 30 min run present in the database. Advisory in
  10/10 sustained-fall runs no later than 60 s after the threshold is crossed,
  and in 0/10 runs with a 15 s dip.

### ER-5 — Response time measured, published and enforced (CR-1, CR-2, CR-4)

* **Measurement.** Transport delay (switch → 10 %), rise t10-90 and fall
  t90-10 from gas step tests at line lengths 0.5, 1, 2 and 3 m, ≥ 10 steps per
  direction per length.
* **Repeatability.** Coefficient of variation ≤ 10 % for each quantity at the
  deployed length.
* **Line length.** Delay versus length fitted by least squares; slope (s/m),
  intercept and R² reported.
* **Claim.** The highest rate resolved breath by breath (displayed peak
  ≥ 90 % and trough ≤ 10 % of true end-tidal, I:E 1:2, first-order model)
  is computed from the slower of rise and fall and published as one of
  BREATH_BY_BREATH (≥ 30 /min), PARTIAL or TREND_ONLY (< 6 /min) in
  `config/response_profile.json`, on the dashboard, in the firmware boot record
  and in the dossier. Above that rate end-tidal values are labelled
  *attenuated* or *trend*. With no measurement the device claims nothing.
* **Model check (VP-5b).** Displayed peak / reference end-tidal at 10, 20 and
  30 /min within ±10 points of the model's prediction; otherwise the published
  limit is derated to the highest rate where the measured fraction ≥ 0.9.

### ER-6 — Static CO2 accuracy within ±(0.43 % + 8 % of reading) (CR-1, CR-4)

* **Range** 0–10 % CO2. After a two-point (gain/offset) calibration against the
  reference, every residual within ±(0.43 % + 8 % of reading), the
  ISO 80601-2-55 limit for CO2 measurement.
* **Drift.** Zero error change ≤ 0.1 % CO2 over 4 h.
* **Acceptance.** ≥ 5 concentrations × 3 repeats, all within the limit; drift
  test with ≥ 5 readings over 4 h.

### ER-7 — Bedside annunciation within 0.5 s, independent of the laptop (CR-1, CR-2, CR-3)

* **Patterns (Figure 3).** NORMAL green, silent. ADVISORY amber flashing
  0.7 Hz, 3-pulse 660 Hz burst every 20 s. CRITICAL red flashing 2 Hz, 10-pulse
  880 Hz burst every 10 s, latched. TECHNICAL cyan, single 1320 Hz chirp every
  15 s. Short button press pauses audio for 120 s; light continues.
* **Latency.** Light and tone change ≤ 0.5 s after the sample that changes
  the state; firmware main-loop period ≤ 100 ms (logged as `perf` records).
* **Independence.** All patient and technical alarms annunciate with the USB
  data link to the laptop disconnected (unit on a USB power bank).
* **Acceptance.** 10 transitions of each type filmed at ≥ 120 fps with the
  serial record time: ≤ 0.5 s in 40/40. Loop max ≤ 100 ms across a 30 min run.
  Laptop-unplugged disconnection and line-clamp tests annunciate in 5/5 each.

### ER-8 — Complete, identifier-free log and notification within 10 s (CR-2, CR-4)

* **Logging.** Every sample, breath, 1 Hz status, event, marker and
  notification is stored in SQLite with device time and host time.
* **Privacy.** No field can hold patient information: marker notes are limited
  to 40 plain characters, recipients are aliases with phone numbers of opted-in
  course participants and a stored consent timestamp; messages are built only
  from fixed templates.
* **Notification.** CRITICAL sent to all consenting recipients ≤ 10 s after
  the event reaches the laptop (median over 20; 95th percentile ≤ 20 s);
  re-sent every 60 s while unacknowledged. TECHNICAL sent only if it persists
  10 s.
* **Link loss.** Laptop shows NO DATA within 5 s of the serial link stopping.
* **Acceptance.** Database audit after a 30 min run: sample count within 1 %
  of 20 Hz × duration; 20 CRITICAL events with logged send latency meeting the
  limits; 5/5 USB unplugs shown within 5 s; schema review finds no
  identifier-capable free-text field.

## Summary

| ER | Serves | Quantity | Limit |
|---|---|---|---|
| ER-1 | CR-1 | breaths to confirm / timeout to absence | 6 breaths / 40 s + delay + 2·t10-90 |
| ER-2 | CR-2 | latency, disconnection → CRITICAL | ≤ 20 s and ≤ published worst case |
| ER-3 | CR-3 | fault detection latency; faults shown as critical | ≤ 3 s; 0 |
| ER-4 | CR-4 | rate accuracy; advisory sustain | ±1 /min; 30 s |
| ER-5 | CR-1, 2, 4 | delay, t10-90, CV, resolvable rate | measured, CV ≤ 10 %, published |
| ER-6 | CR-1, 4 | static accuracy; drift | ±(0.43 % + 8 %); ≤ 0.1 %/4 h |
| ER-7 | CR-1, 2, 3 | annunciation latency; laptop independence | ≤ 0.5 s; yes |
| ER-8 | CR-2, 4 | logging completeness; notification latency | 100 %; ≤ 10 s median |
