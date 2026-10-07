# Is the patient ventilating? — exhaled CO2 monitor

EXSU 620 Digital Prototyping, Project 06 (Fall 2026). A bench instrument that
samples airway gas, confirms that exhaled CO2 is present, tracks the breathing
rate it implies, tells a blocked sampling line apart from a patient who has
stopped breathing, and **measures and publishes its own response time rather
than pretending to be a capnograph**.

> Bench only. The rig is a test lung or phantom. Nothing built here goes near
> a patient or clinical equipment in service. No patient-identifiable
> information is stored or sent.

## How the honesty works

1. You measure the response of *your* sensor on *your* sampling line with gas
   step tests (`capno_analysis.response_time`).
2. `capno_analysis.profile` turns those measurements into a published profile:
   transport delay, 10–90 % response, delay per metre of line, the highest
   breathing rate resolved breath by breath, and the worst-case delay before a
   "CO2 lost" alarm.
3. That profile is shown on the dashboard and compiled into the bedside unit.
   Above the resolvable rate, end-tidal values are labelled *attenuated* (with
   the expected fraction captured) or *breath-averaged trend*. With no
   measurement, the device says "not measured — not a capnograph" and claims
   nothing more.

## Repository layout

| Path | What |
|---|---|
| `capno_core/` | Detection, alarm state machine, annunciation patterns, response model. CircuitPython-compatible; runs on the Pico **and** in tests |
| `firmware/` | Pico 2 W hardware I/O: `code.py`, sensor drivers, `config.py` |
| `capno_service/` | Laptop service: serial ingest, SQLite, notification rules, FastAPI REST + SSE, dashboard |
| `capno_analysis/` | Step-response analysis, response profile, calibration, fault-dataset scoring |
| `capno_sim/` | Modelled airway + sampling line + slow NDIR sensor driving the same `capno_core` |
| `config/response_profile.json` | Published response profile (ships as UNMEASURED) |
| `tests/` | pytest suite: every clinical requirement as scenarios |
| `tools/` | firmware deploy, simulation verification report |
| `docs/` | D1–D9 deliverables |

## Deliverables

| ID | Document |
|---|---|
| D1 | [Engineering requirements](docs/01_engineering_requirements.md) |
| D2 | [System design](docs/02_system_design.md) (architecture, sensing, alarm rules, data model, rejected alternatives, rationale for added parts) |
| D3 | [Component, module and system chart + interface table](docs/03_components_interfaces.md) |
| D4 | [Diagram set](docs/04_diagrams.md): block, wiring, alarm state chart, sequence |
| D5 | This repository + the deployment steps below |
| D6 | [Verification plan](docs/06_verification_plan.md) |
| D7 | [Verification report](docs/07_verification_report.md) (bench results pending) and [simulation results](docs/sim_results.md) |
| D8 | [Failure modes and mitigation](docs/08_failure_modes.md) |
| D9 | [Traceability matrix and technical memorandum](docs/09_traceability_and_memo.md) |

## Quick start without hardware

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest                                            # logic verification
python -m capno_service --simulate figure2        # the sedation case of Figure 2
# open http://127.0.0.1:8000
```

Other scenarios: `steady`, `disconnect`, `apnoea`, `blocked_line`,
`open_line`, `sensor_silent`, `oesophageal`, `no_co2`, `bradypnoea`,
`fault_dataset`, `step_test`. Try a slow module to see the honest labelling:

```bash
python -m capno_service --simulate steady --t10-90 4 --delay 2
```

`--speed 10` runs faster than real time. Simulated profiles are labelled
SIMULATED on the dashboard.

## Hardware build

Kit parts plus a small diaphragm pump, a logic-level MOSFET with flyback
diode, and two Adafruit DPS310 pressure sensors (rationale in
[D2 §7](docs/02_system_design.md#7-design-rationale-for-items-not-in-the-kit)).
Pin map and wiring: [D4 §2](docs/04_diagrams.md#2-wiring-diagram).

Gas path: mask / T-piece → sampling line → water trap → CO2 cell → pump
(DPS310 "line" teed into the pump inlet) → exhaust. Second DPS310 open to room.

## Deploying the bedside unit

1. Install CircuitPython 9.2 or later for the Raspberry Pi Pico 2 W.
2. Install libraries: `pip install circup && circup install neopixel adafruit_dps310`.
3. Edit `firmware/config.py`: sensor type, pressure sensors fitted, and — once
   measured — the response profile block and calibration gain/offset.
4. `python tools/deploy_firmware.py /media/$USER/CIRCUITPY` (copies
   `capno_core` to `lib/` and the firmware to the root; keeps an existing
   `config.py` on the board unless `--overwrite-config`).
5. On power-up the ring cycles green, amber, red, cyan with tones: check you
   see and hear each one. Then it shows dim white (standby).
6. Read `vac` in the serial output with a clear line and the pump running; put
   that value in `line_vac_nominal_kpa`.

Bedside button: short press acknowledge · hold 2–5 s arm (airway placed) ·
hold 5 s disarm (end of case) · double press marker.

## Running with the bedside unit

```bash
python -m capno_service --serial /dev/ttyACM0     # Windows: COM5; macOS: /dev/cu.usbmodem*
```

Set the laptop not to sleep during sessions. The bedside light and tone do
not depend on the laptop; the laptop adds logging, the dashboard and phone
messages, and shows NO DATA if the link drops.

Phone notifications: register opted-in course participants on the dashboard
(consent tick box required; the time is stored). Channels: `log` (console
only), `callmebot` (API key per recipient), `twilio` (set
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`).

## Bench workflow (in this order)

1. **Response time (VP-5).** For each line length (0.5, 1, 2, 3 m): step the
   line inlet between room air and a gas bag with a 3-way stopcock, pressing
   Marker (or double-pressing the button) at each switch. Then

   ```bash
   python -m capno_analysis.response_time --db data/capno.db --session N \
       --line-length 2.0 --append results/steps.csv --plot results/steps_2m.png
   python -m capno_analysis.profile build results/steps.csv --line-length 2.0 \
       --sensor "SprintIR-WF-20" --plot results/profile.png
   ```

   Paste the printed block into `firmware/config.py`, redeploy, restart the
   service. The dashboard mismatch banner disappears when firmware and
   published profile agree.
2. **Calibration (VP-6):** `python -m capno_analysis.calibration fit results/cal.csv --plot results/cal.png`.
3. **Fault dataset (VP-3):** create each fault and send a marker
   `truth=<label>` (blocked, open, sensor_off, disconnect, normal), then
   `python -m capno_analysis.fault_eval --db data/capno.db --session N`.
4. Remaining protocols in [D6](docs/06_verification_plan.md); record results in
   [D7](docs/07_verification_report.md).

Rehearse the whole pipeline on simulated data first:

```bash
python -m capno_sim step_test --t10-90 1.2 --delay 1.2 > /tmp/steps.jsonl
python -m capno_analysis.response_time --jsonl /tmp/steps.jsonl --line-length 2 --marker-filter step
python -m capno_analysis.fault_eval --simulate fault_dataset --t10-90 2
python tools/run_sim_verification.py               # regenerates docs/sim_results.md
```

## Pre-session checklist

- [ ] Water trap empty, line length matches the published profile
- [ ] Power-up self-test seen and heard
- [ ] Room-air reading 0.0–0.1 % and no ZERO DRIFT
- [ ] Line vacuum near nominal; clamp the line once: cyan within 2 s
- [ ] Dashboard shows the measured profile, no mismatch banner
- [ ] Reference capnograph connected only for calibration or validation runs
