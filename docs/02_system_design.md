# D2 — System design

## 1. Architecture

```
 airway / mask / test lung
        │ gas (sidestream, pump-drawn)
 sampling line ── water trap ── NDIR CO2 cell ── pump ── exhaust
                                   │ UART            │ inlet pressure (I²C)
                                   ▼                 ▼
                 ┌──────────── Raspberry Pi Pico 2 W ────────────┐
                 │ firmware/code.py   (hardware I/O only)         │
                 │ lib/capno_core     (detection + alarms)        │──► NeoPixel ring, PAM8302 speaker
                 │                                                │◄── pushbutton
                 └────────────────────────┬───────────────────────┘
                                 USB serial, JSON lines (both ways)
                 ┌────────────────────────▼───────────────────────┐
                 │ laptop: capno_service                           │
                 │  ingest ─► SQLite   rules ─► notifier ─► phones │
                 │  FastAPI REST + SSE ─► browser dashboard        │
                 └─────────────────────────────────────────────────┘
 capno_analysis (offline): step tests → response profile; calibration; fault scoring
 capno_sim: modelled airway + line + sensor driving the same capno_core code
```

Full diagrams (block, wiring, alarm state chart, sequence) are in
[D4](04_diagrams.md).

### Key decision: one copy of the alarm logic, on the bedside unit

All detection and alarm decisions run on the Pico in `capno_core`, a package
written in the subset of Python that CircuitPython supports (integer
milliseconds, no dataclasses, no `statistics`, own ring buffer). The same files
are imported by the laptop tests, the simulator and the service's simulate
mode. Consequences:

* The bedside light and tone work with the laptop unplugged (ER-7). The laptop
  can be lost without losing an alarm; its loss is itself shown (ER-8).
* What is tested (the pytest suite, the simulated fault dataset) is the code
  that runs at the bedside, not a re-implementation.
* The service does not re-decide alarms. It logs, applies a notification
  policy, and watches the link.

## 2. Sensing approach

**Sidestream NDIR.** A pump draws airway gas through a sampling line and water
trap into the sensor's flow-through cell. Mainstream (sensor at the airway)
would remove the transport delay but needs a heated, fast, airway-rated cell
that is not in the kit.

**Sensor choice.** Firmware supports two families behind one interface
(`firmware/sensors.py`):

| Module | Range | Output rate | Response | Notes |
|---|---|---|---|---|
| GSS SprintIR-WF-20 (preferred) | 0–20 % | 20 Hz streaming | fast; flow-through adapter | UART ASCII `Z`/`z` frames; unfiltered `z` used for speed |
| GSS ExplorIR-W 20 % | 0–20 % | 2 Hz | seconds | same protocol |
| Winsen MH-Z16 / MH-Z19 5 % or 10 % versions | 0–5/10 % | ~1 Hz polled | tens of seconds | cheap; only a trend monitor; 5 % range clips end-tidal |

The design does not assume which one the group ends up with. The response
time is **measured** (ER-5) and the claims the device makes follow from the
measurement, not from the datasheet.

**Line integrity sensing.** CO2 alone cannot tell a blocked line from a
patient who has stopped breathing (Figure 2: both go flat). Two DPS310
barometric sensors measure ambient pressure and pump-inlet pressure; their
difference is the line vacuum. A blocked line raises it (the pump pulls
against a closed tube); a line off at the monitor inlet lowers it (no line
resistance). This is the signal that keeps CR-3's promise.

## 3. Signal processing and alarm rules

### Breath detection (`capno_core/breath.py`)

* The signal envelope (min, max) is tracked over 15 s in 250 ms blocks.
* Hysteresis thresholds adapt to it: a rise through min + 60 % of the swing
  starts expiration, a fall through min + 35 % ends it. A swing < 0.3 % is
  "flat": no breaths are reported.
* A breath counts as exhaled CO2 if its peak ≥ 1.0 %. Intervals < 1 s are
  artefacts; intervals > 20 s are apnoeas and reset the rate history.
* Rate = median of the last 6 intervals; reported as unknown if the last
  breath is older than 2.5 median intervals.

Because thresholds are relative to the envelope, a slow sensor whose trace
never returns to zero still yields a correct rate as long as it swings
≥ 0.3 %. End-tidal amplitude is what degrades first, and the device says so.

### What the response time allows (`capno_core/capability.py`)

Line + sensor ≈ transport delay + first-order lag, τ = t10-90 / ln 9. For a
square-wave capnogram (I:E 1:2) the steady-state displayed peak and trough are
closed-form. Breaths are *resolved* when the peak ≥ 90 % and the trough ≤ 10 %
of the true value; the highest such rate is the published breath-by-breath
limit. Status records carry:

* `et_kind = breath` — breaths resolved, end-tidal is meaningful;
* `et_kind = attenuated` — breaths detected above the limit; the peak
  under-reads, and `et_capture` gives the expected fraction;
* `et_kind = trend` — no breaths resolved; the value is the breath-averaged peak.

The simulator shows the model is optimistic by 1–9 points for a realistic
capnogram ([sim_results](sim_results.md)), so VP-5b checks the limit against
the reference capnograph.

### Monitoring phases and alarms (`capno_core/monitor.py`)

| Phase | Entered by | Loss of CO2 means |
|---|---|---|
| STANDBY | power-up, disarm | nothing (not connected) |
| CONFIRMING | operator arms (button 2–5 s, or dashboard) | NO CO2 critical after timeout |
| CONFIRMED | 6 sustained CO2 breaths (or 30 s trend), also automatically from standby | CO2 LOST critical after the loss window |

Patient alarm levels and technical faults follow Figure 3 and are listed in
[D1](01_engineering_requirements.md) (ER-1 to ER-4) with their thresholds.
Rules that are easy to get wrong:

1. **Technical suppresses critical, not the other way round.** While a
   technical fault is active the signal is untrusted, so loss of CO2 is not
   called. When it clears, the loss window restarts *from the clear time*:
   a real loss behind a fault is still caught one window later
   (test `test_after_fault_clears_a_real_loss_is_still_caught`).
2. **A latched critical keeps its reason current.** If NO CO2 is latched and
   unacknowledged, then CO2 appears and is lost again, the reason changes to
   CO2 LOST rather than silently staying stale.
3. **Absolute end-tidal thresholds only when breaths are resolved.** An
   attenuated peak would trip "EtCO2 < 3 %" on a slow sensor with a healthy
   patient; there only the fall relative to its own baseline is judged
   (reason `CO2_TREND_FALL`).
4. **Confirmation timeout includes the instrument's own delay and lag**, so a
   slow module does not call NO CO2 on a correctly placed tube.

### Annunciation (`capno_core/annunciator.py`)

Priority on the ring and the dashboard: CRITICAL > TECHNICAL > ADVISORY >
NORMAL/CONFIRMING/STANDBY. Patterns follow IEC 60601-1-8 conventions
(10-pulse high priority, 3-pulse medium). Button: short = acknowledge,
2–5 s = arm, hold 5 s = disarm, double = marker (`capno_core/button.py`).

### Service rules (`capno_service/rules.py`)

* CRITICAL → notify at once, repeat every 60 s until acknowledged.
* ADVISORY → notify recipients who chose advisories.
* TECHNICAL → notify only if it persists 10 s (a brief kink pages nobody).
* No record for 3 s → LINK_LOST event, dashboard NO DATA, technical notify.
* Same level + reason not repeated within 60 s, except critical escalation.

## 4. Data model (`capno_service/db.py`)

| Table | One row per | Key fields |
|---|---|---|
| sessions | service start or bedside reboot | source, firmware, device profile, published profile |
| samples | CO2 sample (20 Hz) | t_ms (device), host_ts, co2, vac, display |
| breaths | detected breath | t_ms, end_ms, peak, is_co2, interval_ms |
| status | second | display, phase, alarm, reason, tech, co2, et, et_kind, et_capture, rr, rr_note, vac, baselines |
| events | state change | kind (alarm / technical / monitor / ack / baseline / link), from, to, reason |
| markers | operator marker | note (≤ 40 plain chars; `truth=<label>` for fault datasets) |
| perf | 5 s | firmware loop_max_ms, CO2 frame errors |
| recipients | opted-in participant | alias, channel, address, levels, consent_at, revoked_at |
| notifications | send attempt | event, recipient, message, queued_ts, sent_ts, ok |

Device time (`t_ms`) is monotonic from boot and is what the analyses use;
host time is wall clock and is what latency to the phone is measured in.

Wire protocol: one JSON object per line, documented at the top of
`capno_core/device.py`.

## 5. REST contract (`capno_service/app.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | /api/health | source, link state, counters |
| GET | /api/status | latest status, link, device boot record, profile mismatches |
| GET | /api/profile | published response profile + plain statement |
| GET | /api/samples?since_seq= | live samples (5 min buffer) |
| GET | /api/events, /api/breaths | recent events and breaths |
| GET | /api/trend?minutes= | 1 Hz status history from SQLite |
| GET | /api/stream | server-sent events: samples, events, status every 250 ms |
| POST | /api/command | ARM, DISARM, ACK, BASELINE, MARK (validated) |
| GET/POST/DELETE | /api/recipients | list (numbers masked), register (consent required), revoke |
| GET | /api/notifications | send log with latency |
| GET | /api/export/{table}.csv | CSV export for analysis |

## 6. Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| Alarm logic in the laptop service (the starter-kit layout) | A laptop sleep, crash or unplugged cable would silence the bedside alarm. Kept on the Pico; the laptop only adds logging and notification. |
| Two implementations (C on the Pico, Python on the laptop) | Doubles the test burden and invites divergence. One CircuitPython-compatible package instead. |
| Fixed absolute thresholds for breath detection (e.g. 1.0 % / 0.5 %) | Fails on a slow sensor whose trough never drops below 0.5 %: every breath disappears and a healthy patient alarms CO2 LOST. Adaptive envelope thresholds instead. |
| Infer a blocked line from the CO2 trace alone | Figure 2: a blocked line and an apnoea both go flat. Indistinguishable without a flow or pressure signal. Pressure sensing added. |
| Single pressure sensor, ambient captured at start | Weather and building HVAC move ambient by ~0.1 kPa per hour, comparable to the open-line threshold margin over a long case. Second sensor is cheap. |
| Thermal mass-flow sensor in the line | More direct, but more expensive, harder to source in Canada at kit prices, and dead volume adds to response time. |
| "Correcting" attenuated end-tidal values by dividing by the model fraction | That is pretending to be a capnograph: it amplifies noise and depends on a model whose error is ±10 points. Values are labelled, not corrected. |
| Chart.js / Plotly for the dashboard | Listed in the kit, but loaded from a CDN; the bench laptop may be offline. Two small canvas plots in plain JavaScript cover the need with no dependency. |
| Polling REST for the live trace | 20 Hz polling is wasteful; server-sent events push new samples every 250 ms. |

## 7. Design rationale for items not in the kit

The card asks for a line of rationale for anything not listed.

| Item | Why the kit option was not sufficient | Availability in Canada |
|---|---|---|
| Miniature 3–5 V diaphragm air pump (≈ 200–500 mL/min) | The kit lists sampling line and water trap but no pump; the card notes "a small pump or the patient's own breath". A spontaneously breathing patient on a mask cannot be relied on to push gas down 2 m of line, and the response time must be repeatable to be published. | DigiKey.ca, Adafruit via Canadian resellers |
| Logic-level N-MOSFET (e.g. AO3400 / IRLZ44N), 1N5819 diode, 10 kΩ, 100 Ω | Pump draws more current than a GPIO can source; flyback protection. | DigiKey.ca, Mouser.ca, Elmwood |
| 2 × Adafruit DPS310 barometric sensor (STEMMA QT) | Needed to tell a blocked line from apnoea (CR-3). STEMMA QT matches the kit's Grove-to-STEMMA cables. | Adafruit via DigiKey.ca, Elmwood |
| T-piece side port to the DPS310 | Short silicone tube from the pump inlet manifold. | lab stock |

If the pressure sensors are not fitted, set `PRESSURE_SENSORS = False` in
`firmware/config.py`. The device then reports "line integrity not monitored"
on the dashboard and in its boot record, and CR-3 is recorded as **not met**
(see the regression test `test_fault_eval_catches_a_fault_presented_as_apnoea`).
