"""Where device records come from: the Pico over USB serial, the simulator, or a replay."""

import json
import queue
import time

from capno_core.device import Device


class SerialSource:
    def __init__(self, port, baud=115200):
        self.port = port
        self.baud = baud
        self.name = f"serial:{port}"
        self.ser = None

    def _open(self):
        import serial
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.5)
        except serial.SerialException:
            self.ser = None

    def lines(self):
        import serial
        while True:
            if self.ser is None:
                self._open()
                if self.ser is None:
                    time.sleep(1.0)
                    yield None
                    continue
            try:
                raw = self.ser.readline()
            except serial.SerialException:
                self.ser = None
                yield None
                continue
            yield raw.decode(errors="replace").strip() or None

    def send(self, cmd):
        if self.ser is None:
            raise RuntimeError("bedside unit not connected")
        self.ser.write((cmd + "\n").encode())


class SimSource:
    """Runs a capno_sim scenario through capno_core.Device in (scaled) real time."""

    def __init__(self, scenario, t10_90_s=0.3, delay_s=1.0, fs=20.0, speed=1.0, loop=True):
        from capno_sim.scenarios import SCENARIOS
        self.scenario = scenario
        self.segments_fn = SCENARIOS[scenario]
        self.t10_90_s = t10_90_s
        self.delay_s = delay_s
        self.fs = fs
        self.speed = speed
        self.loop = loop
        self.name = f"sim:{scenario}:t10-90={t10_90_s}s:delay={delay_s}s"
        self.cmds = queue.Queue()

    def lines(self):
        from capno_sim.model import Rig
        from capno_sim.run import sim_config
        while True:
            cfg = sim_config(self.t10_90_s, self.delay_s)
            dev = Device(cfg, {"sensor": "sim", "scenario": self.scenario})
            yield json.dumps(dev.hello(0))
            rig = Rig(self.t10_90_s, self.delay_s, self.fs, vac_nominal=cfg["line_vac_nominal_kpa"])
            start = time.monotonic()
            for t, co2, vac, seg, first in rig.run(self.segments_fn()):
                wait = start + t / 1000.0 / self.speed - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                recs = []
                while not self.cmds.empty():
                    recs.extend(dev.command(t, self.cmds.get()))
                if first:
                    if seg.label:
                        recs.append({"type": "m", "t": t, "note": "truth=" + seg.label})
                    if seg.command:
                        recs.extend(dev.command(t, seg.command))
                recs.extend(dev.step(t, co2, vac))
                for r in recs:
                    yield json.dumps(r)
            if not self.loop:
                return

    def send(self, cmd):
        self.cmds.put(cmd)


class ReplaySource:
    def __init__(self, path, speed=1.0):
        self.path = path
        self.speed = speed
        self.name = f"replay:{path}"

    def lines(self):
        start = time.monotonic()
        t0 = None
        with open(self.path) as f:
            for line in f:
                try:
                    t = json.loads(line).get("t")
                except ValueError:
                    t = None
                if t is not None and self.speed > 0:
                    if t0 is None:
                        t0 = t
                    wait = start + (t - t0) / 1000.0 / self.speed - time.monotonic()
                    if wait > 0:
                        time.sleep(wait)
                yield line.strip()

    def send(self, cmd):
        raise RuntimeError("replay is read-only")
