"""Run the laptop service.

    python -m capno_service --serial /dev/ttyACM0          # real bedside unit
    python -m capno_service --simulate figure2             # no hardware
    python -m capno_service --simulate steady --t10-90 4   # see what a slow module would do
    python -m capno_service --replay run.jsonl
Then open http://127.0.0.1:8000
"""

import argparse
from pathlib import Path

import uvicorn

from .app import create_app
from .ingest import Ingestor
from .notify import Notifier
from .profile import load_profile
from .sources import ReplaySource, SerialSource, SimSource

ROOT = Path(__file__).resolve().parent.parent


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--serial", metavar="PORT")
    src.add_argument("--simulate", metavar="SCENARIO")
    src.add_argument("--replay", metavar="JSONL")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--t10-90", type=float, default=0.3, help="simulated sensor 10-90 %% time, s")
    p.add_argument("--delay", type=float, default=1.0, help="simulated line delay, s")
    p.add_argument("--speed", type=float, default=1.0, help="simulation / replay speed factor")
    p.add_argument("--db", default=str(ROOT / "data" / "capno.db"))
    p.add_argument("--profile", default=str(ROOT / "config" / "response_profile.json"))
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()

    Path(a.db).parent.mkdir(parents=True, exist_ok=True)
    if a.serial:
        source = SerialSource(a.serial, a.baud)
        profile = load_profile(a.profile)
    elif a.simulate:
        source = SimSource(a.simulate, a.t10_90, a.delay, speed=a.speed)
        profile = simulated_profile(a.t10_90, a.delay)
    else:
        source = ReplaySource(a.replay, a.speed)
        profile = load_profile(a.profile)

    ingestor = Ingestor(source, a.db, profile, Notifier(a.db))
    app = create_app(ingestor, a.db)
    ingestor.start()
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


def simulated_profile(t10_90, delay):
    """Profile of the simulated rig: labelled SIMULATED so it is never mistaken for a measurement."""
    from capno_core.capability import loss_alarm_latency_s, max_resolvable_rr, operating_mode
    rr = round(max_resolvable_rr(t10_90), 1)
    return {
        "status": "MEASURED",
        "source": "SIMULATED (capno_sim) - not a bench measurement",
        "sensor": "simulated first-order NDIR",
        "t_response_s": t10_90,
        "delay_s": delay,
        "max_resolvable_rr": rr,
        "mode": operating_mode(rr),
        "loss_alarm_latency_s": round(loss_alarm_latency_s(delay, t10_90, 20.0), 1),
        "statement": "Simulated instrument. Numbers describe the model, not hardware.",
    }


if __name__ == "__main__":
    main()
