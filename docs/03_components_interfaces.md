# D3 — Component, module and system chart

## Component → module → system

| System | Module | Component | Role |
|---|---|---|---|
| **S1 Bedside unit** | M1 Gas path | Mask or T-piece, sampling line (0.5–3 m), water trap | Carries airway gas to the cell |
| | | Diaphragm pump + MOSFET driver + flyback diode | Draws a steady sample flow |
| | M2 Measurement | NDIR CO2 module (SprintIR-WF-20, ExplorIR-W or MH-Z16/19) | CO2 concentration |
| | | 2 × DPS310 (pump inlet, ambient) | Line vacuum: blocked / open line |
| | M3 Controller | Raspberry Pi Pico 2 W + Grove shield, CircuitPython 9 | Runs `firmware/` and `capno_core` |
| | M4 Annunciation | NeoPixel 16 ring + frosted dome | Green / amber / red / cyan state light |
| | | PAM8302 amplifier + 3 W 8 Ω speaker | 10-pulse, 3-pulse, chirp tones |
| | | Panel pushbutton | Acknowledge, arm, disarm, marker |
| | M5 Enclosure | 3D-printed sensor mount, enclosure, indicator panel | Mechanical |
| **S2 Laptop service** | M6 Ingest + log | `capno_service.ingest`, `db` (SQLite, WAL) | Parse, store, live state |
| | M7 Rules + notify | `capno_service.rules`, `notify` (log, CallMeBot, Twilio) | Who is told what, link watchdog |
| | M8 API + dashboard | FastAPI, uvicorn, `static/index.html` | REST, SSE, browser UI |
| **S3 Verification toolchain** | M9 Analysis | `capno_analysis` (response time, profile, calibration, fault scoring) | Produces the published claims |
| | M10 Simulator | `capno_sim` | Logic verification, demos, rehearsal |
| **External** | — | Simulation lab capnograph | Reference for calibration and validation only |
| | — | Registered phones (opted-in participants) | Receive notifications |

## Software modules

| Module | Runs on | Depends on | Tested by |
|---|---|---|---|
| `capno_core.breath` | Pico, laptop | `ring` | `tests/test_breath.py` |
| `capno_core.monitor` | Pico, laptop | `breath`, `capability`, `ring` | `tests/test_monitor.py` |
| `capno_core.capability` | Pico, laptop | `math` | `tests/test_capability.py` |
| `capno_core.annunciator`, `button` | Pico, laptop | — | `tests/test_annunciator_button.py` |
| `capno_core.device` | Pico, laptop | all of the above | `tests/test_monitor.py`, service tests |
| `firmware/code.py`, `sensors.py` | Pico | `board`, `busio`, `neopixel`, `adafruit_dps310` | bench VP-7 |
| `capno_service.*` | laptop | FastAPI, sqlite3, pyserial | `tests/test_service.py` |
| `capno_analysis.*` | laptop | numpy, matplotlib | `tests/test_analysis.py` |
| `capno_sim.*` | laptop | `capno_core` | used by every scenario test |

## Interface table

Every interface with its signal, direction and range.

| ID | From → To | Signal | Physical / format | Range / rate |
|---|---|---|---|---|
| IF-01 | Airway → sampling line | Airway gas, CO2 0–8 % | Luer port on T-piece / mask | Sample flow ≈ 150–250 mL/min |
| IF-02 | Water trap → NDIR cell | Dried sample gas | 3 mm ID silicone, flow-through adapter | Same flow |
| IF-03 | NDIR cell → pump | Sample gas | Silicone tube; DPS310 tapped at pump inlet | Vacuum 5–30 kPa |
| IF-04 | NDIR module → Pico | CO2 concentration | UART0 9600 8N1, 3.3 V logic, GP0 TX / GP1 RX | GSS: `Z`/`z` frames 20 Hz (SprintIR) or 2 Hz; MH-Z: 9-byte frames polled 2 Hz; 0–20 % |
| IF-05 | DPS310 × 2 → Pico | Absolute pressure | I²C1 GP6 SDA / GP7 SCL, addresses 0x77 (line) 0x76 (ambient), STEMMA QT | 300–1200 hPa, read at 5 Hz |
| IF-06 | Pico → pump driver | Pump enable | GP22 → 100 Ω → MOSFET gate, 10 kΩ pull-down | 0 / 3.3 V |
| IF-07 | Pico → NeoPixel ring | Pixel colours | GP18, WS2812 800 kHz; ring powered from VBUS 5 V | 16 × RGB, brightness 0.3 |
| IF-08 | Pico → PAM8302 | Tone | GP20 PWM 50 % duty → 1 kΩ → A+; GP21 → SD (enable) | 660, 880, 1320 Hz or silent |
| IF-09 | Pushbutton → Pico | Operator input | GP16, internal pull-up, switch to GND | debounced 30 ms; short / long / hold / double |
| IF-10 | Pico ↔ laptop | Records ↑, commands ↓ | USB CDC serial 115200, one JSON object per line | ~25 lines/s up; `ARM`, `DISARM`, `ACK`, `BASELINE`, `MARK <note>` down |
| IF-11 | Service ↔ browser | Status, samples, commands | HTTP REST + SSE, JSON, localhost:8000 | SSE every 250 ms |
| IF-12 | Service → phone | Alarm message | HTTPS to CallMeBot or Twilio WhatsApp API | ≤ 1 per level+reason per 60 s; critical repeat 60 s |
| IF-13 | Service ↔ SQLite | Log | sqlite3 file `data/capno.db`, WAL | ~25 inserts/s, commit 2 Hz |
| IF-14 | Analysis → profile file → service, firmware | Response profile | `config/response_profile.json`; pasted block in `firmware/config.py` | t10-90, delay, max resolvable rate |
| IF-15 | Reference capnograph → analysis | Reference CO2, rate | Manual transcription to CSV (never a live channel) | calibration and validation sessions only |
| IF-16 | USB 5 V → Pico, ring, pump | Power | VBUS | ≤ 500 mA total (ring at 0.3 brightness ≈ 150 mA, pump ≈ 150–250 mA) |

### Serial record types (IF-10)

| `type` | Fields | When |
|---|---|---|
| `hello` | fw, sensor, profile {t10_90_ms, delay_ms, max_resolvable_rr, line_monitored} | boot |
| `s` | t, co2, vac, d (display state) | every CO2 sample |
| `b` | t (start), end, peak, co2 (bool), interval_ms | every breath |
| `e` | t, kind, from, to, reason | every state change |
| `st` | display, mon, alarm, reason, tech[], co2, et, et_kind, et_capture, rr, rr_note, base_et, base_rr, confirm, evidence_age_ms, loss_window_ms, paused, acked | 1 Hz |
| `m` | t, note | marker |
| `perf` | loop_max_ms, co2_errors | every 5 s |
| `btn` | kind | button press classified |
| `err` | msg | unknown command |
