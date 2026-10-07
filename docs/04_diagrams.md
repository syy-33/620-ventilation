# D4 — System diagram set

Four diagrams: block, wiring, alarm state chart, and the sequence from sample
to notification. They are written in Mermaid so they render on GitHub and stay
in version control next to the code they describe; export to draw.io or PNG
for the dossier.

## 1. Block diagram

```mermaid
flowchart LR
  subgraph Patient side
    A[Airway, mask or test lung]
  end
  subgraph S1[Bedside unit]
    L[Sampling line + water trap] --> C[NDIR CO2 cell]
    C --> P[Pump]
    P -. inlet pressure .-> PL[DPS310 line]
    PA[DPS310 ambient]
    C -- UART --> MCU[Pico 2 W<br/>capno_core]
    PL -- I2C --> MCU
    PA -- I2C --> MCU
    MCU --> RING[NeoPixel ring]
    MCU --> SPK[PAM8302 + speaker]
    BTN[Pushbutton] --> MCU
  end
  A -- gas --> L
  REF[Simulation lab capnograph] -. calibration and validation only .-> L
  MCU <-- USB serial JSON lines --> SVC
  subgraph S2[Laptop]
    SVC[capno_service<br/>ingest + rules] --> DB[(SQLite)]
    SVC --> API[FastAPI REST + SSE]
    SVC --> NTF[Notifier]
  end
  API -- HTTP --> UI[Browser dashboard<br/>audible alert]
  NTF -- HTTPS --> PH[Registered phones]
  DB --> AN[capno_analysis] --> PROF[response_profile.json]
  PROF --> API
  PROF -. pasted into config.py .-> MCU
```

## 2. Wiring diagram

```mermaid
flowchart LR
  subgraph PICO[Pico 2 W on Grove shield]
    GP0[GP0 UART0 TX]
    GP1[GP1 UART0 RX]
    GP6[GP6 I2C1 SDA]
    GP7[GP7 I2C1 SCL]
    GP16[GP16 D16]
    GP18[GP18 D18]
    GP20[GP20 D20 PWM]
    GP21[GP21 D20 second pin]
    GP22[GP22 breadboard]
    V3[3V3]
    VB[VBUS 5 V]
    G[GND]
  end
  GP0 --> SRX[CO2 module RX]
  STX[CO2 module TX] --> GP1
  VB --> SV[CO2 module VCC 3.3-5.5 V]
  GP6 <--> D1[DPS310 line 0x77]
  GP7 --> D1
  D1 <--> D2[DPS310 ambient 0x76<br/>SDO jumper to GND]
  V3 --> D1
  BT[Pushbutton] --> GP16
  BT --> G
  GP18 --> NP[NeoPixel DIN]
  VB --> NPV[NeoPixel 5V]
  GP20 --> R1[1 kΩ] --> AP[PAM8302 A+]
  G --> AM[PAM8302 A-]
  GP21 --> SD[PAM8302 SD]
  VB --> AV[PAM8302 VIN]
  AP --> SPK[Speaker 8 Ω]
  GP22 --> R2[100 Ω] --> Q[MOSFET gate]
  Q -.10 kΩ pull-down.- G
  VB --> PMP[Pump +] --> Q
  Dfly[1N5819 across pump] --- PMP
```

| Pico pin | Grove port | Connects to | Notes |
|---|---|---|---|
| GP0 / GP1 | UART0 | CO2 module RX / TX | 3.3 V logic. Check the module's pinout; SprintIR TX is 3.3 V |
| GP6 / GP7 | I2C1 | Both DPS310 via STEMMA QT daisy chain | Second DPS310: SDO to GND → address 0x76 |
| GP16 | D16 | Pushbutton to GND | internal pull-up |
| GP18 | D18 | NeoPixel ring DIN | ring 5 V from VBUS; add 330 Ω in series and 470 µF across 5 V if flicker |
| GP20 | D20 | 1 kΩ → PAM8302 A+ | A− to GND; volume trim on the PAM8302 |
| GP21 | D20 (2nd pin) | PAM8302 SD | high = enabled |
| GP22 | breadboard | 100 Ω → MOSFET gate | 10 kΩ gate pull-down; pump between VBUS and drain; Schottky across pump |
| VBUS / GND | — | ring, amplifier, pump, CO2 module | total ≤ 500 mA from USB; measure with the multimeter |

Fritzing or KiCad versions of this drawing go in `hardware/` when drawn.

## 3. Alarm state chart

Patient alarm (left) and technical faults (right) are independent; the display
shows the highest priority: CRITICAL > TECHNICAL > ADVISORY > NORMAL.

```mermaid
stateDiagram-v2
  direction LR
  state "Monitoring phase" as phase {
    STANDBY --> CONFIRMING: arm (button 2-5 s or dashboard)
    STANDBY --> CONFIRMED: 6 sustained CO2 breaths (auto)
    CONFIRMING --> CONFIRMED: 6 sustained CO2 breaths or 30 s trend >= 1 %
    CONFIRMED --> STANDBY: disarm (hold 5 s)
    CONFIRMING --> STANDBY: disarm
  }
  state "Patient alarm" as alarm {
    NORMAL --> ADVISORY: EtCO2 or rate falling beyond threshold for 30 s
    ADVISORY --> NORMAL: values back in range for 30 s
    NORMAL --> CRITICAL: CO2 absent while connected (CO2 LOST)\nor not confirmed in time (NO CO2)
    ADVISORY --> CRITICAL: CO2 absent while connected
    CRITICAL --> NORMAL: acknowledged AND back in range
    note right of CRITICAL: red, 10-pulse, latched.\nNot raised while a technical fault is active.
  }
  state "Technical" as tech {
    OK --> FAULT: line blocked / open, sensor silent / range, zero drift\n(debounced 0-1.5 s)
    FAULT --> OK: condition gone for 3 s\n(loss window restarts)
    note right of FAULT: cyan, chirp.\n"patient status unknown - not apnoea"
  }
```

## 4. Sequence: from sample to notification

Disconnection during a confirmed case.

```mermaid
sequenceDiagram
  autonumber
  participant Gas as Airway / line
  participant S as NDIR sensor
  participant MCU as Pico (capno_core)
  participant LED as Ring + speaker
  participant SVC as Laptop service
  participant DB as SQLite
  participant UI as Dashboard
  participant PH as Phone

  Gas->>S: circuit disconnected, line now sees room air (after transport delay)
  loop every sample (20 Hz)
    S->>MCU: UART frame "z 00412"
    MCU->>MCU: Monitor.update(): below 1.0 % since last CO2
    MCU->>SVC: {"type":"s","co2":0.04,"d":"NORMAL"}
    SVC->>DB: INSERT samples
  end
  Note over MCU: no CO2 for loss window W (10-20 s), line vacuum normal
  MCU->>LED: red flashing + 10-pulse burst (same loop pass)
  MCU->>SVC: {"type":"e","kind":"alarm","to":"CRITICAL","reason":"CO2_LOST"}
  SVC->>DB: INSERT events (commit now)
  SVC->>SVC: Rules.on_event: CRITICAL, notify at once
  SVC-)PH: HTTPS WhatsApp message (notifier thread)
  SVC->>DB: INSERT notifications (queued_ts, sent_ts, ok)
  SVC-->>UI: SSE status + event (<= 250 ms)
  UI->>UI: red banner, browser alarm tone
  Note over MCU,UI: operator presses Acknowledge (button or dashboard)
  UI->>SVC: POST /api/command {"cmd":"ACK"}
  SVC->>MCU: "ACK\n"
  MCU->>LED: audio paused 120 s, light stays red
  Gas->>S: circuit reconnected, CO2 breaths return
  MCU->>MCU: 2 CO2 breaths + acknowledged: back in range
  MCU->>SVC: {"type":"e","kind":"alarm","to":"NORMAL"}
  MCU->>LED: green, silent
```
