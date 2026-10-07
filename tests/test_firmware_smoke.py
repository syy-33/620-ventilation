"""Run firmware/code.py on the laptop with fake CircuitPython hardware modules.

This cannot prove the firmware works on a real Pico, but it catches typos,
wrong names and crashes in the start-up and main-loop paths before flashing.
"""

import json
import sys
import types
from pathlib import Path

import pytest

FIRMWARE = Path(__file__).resolve().parent.parent / "firmware"


class StopLoop(Exception):
    pass


class Pin:
    def __init__(self, name):
        self.name = name


class DigitalInOut:
    def __init__(self, pin):
        self.value = True            # button not pressed (pull-up)

    def switch_to_output(self, value=False):
        self.value = value

    def switch_to_input(self, pull=None):
        self.value = True


class PWMOut:
    def __init__(self, pin, frequency=0, duty_cycle=0, variable_frequency=False):
        self.frequency = frequency
        self.duty_cycle = duty_cycle


class NeoPixel(list):
    def __init__(self, pin, n, brightness=1.0, auto_write=True):
        super().__init__([(0, 0, 0)] * n)
        self.shows = 0

    def fill(self, c):
        for i in range(len(self)):
            self[i] = c

    def show(self):
        self.shows += 1


class UART:
    def __init__(self, *a, **k):
        self.in_waiting = 0

    def write(self, b):
        pass

    def read(self, n):
        return b""

    def readline(self):
        return None

    def reset_input_buffer(self):
        pass


class I2C:
    def __init__(self, scl, sda):
        raise RuntimeError("No pull up found on SDA or SCL; check your wiring")


def install_fakes(monkeypatch, clock):
    board = types.ModuleType("board")
    for n in ("GP0", "GP1", "GP6", "GP7", "GP16", "GP18", "GP20", "GP21", "GP22"):
        setattr(board, n, Pin(n))
    busio = types.ModuleType("busio")
    busio.UART = UART
    busio.I2C = I2C
    digitalio = types.ModuleType("digitalio")
    digitalio.DigitalInOut = DigitalInOut
    digitalio.Pull = types.SimpleNamespace(UP="up")
    neopixel = types.ModuleType("neopixel")
    neopixel.NeoPixel = NeoPixel
    pwmio = types.ModuleType("pwmio")
    pwmio.PWMOut = PWMOut
    supervisor = types.ModuleType("supervisor")
    supervisor.runtime = types.SimpleNamespace(serial_bytes_available=0)
    for name, mod in (("board", board), ("busio", busio), ("digitalio", digitalio),
                      ("neopixel", neopixel), ("pwmio", pwmio), ("supervisor", supervisor)):
        monkeypatch.setitem(sys.modules, name, mod)

    import time as real_time

    def monotonic_ns():
        clock["t"] += 5_000_000          # each call advances 5 ms
        if clock["t"] > clock["limit"]:
            raise StopLoop()
        return clock["t"]

    monkeypatch.setattr(real_time, "monotonic_ns", monotonic_ns)
    monkeypatch.setattr(real_time, "sleep", lambda s: None)


def run_firmware(monkeypatch, capsys, sensor, seconds):
    clock = {"t": 0, "limit": seconds * 1_000_000_000}
    install_fakes(monkeypatch, clock)
    monkeypatch.syspath_prepend(str(FIRMWARE))
    for m in ("config", "sensors", "code"):
        sys.modules.pop(m, None)
    import config
    monkeypatch.setattr(config, "SENSOR", sensor)
    with pytest.raises(StopLoop):
        import code  # noqa: F401  (runs main() at import, as CircuitPython does)
    out = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    for m in ("config", "sensors", "code"):
        sys.modules.pop(m, None)
    return out


def test_demo_mode_runs_and_confirms(monkeypatch, capsys):
    out = run_firmware(monkeypatch, capsys, "demo", 60)
    assert out[0]["type"] == "hello" and out[0]["sensor"] == "demo"
    assert out[0]["profile"]["line_monitored"] is False
    assert any(r["type"] == "s" for r in out)
    assert any(r["type"] == "e" and r.get("to") == "CONFIRMED" for r in out)
    assert any(r["type"] == "perf" for r in out)


def test_missing_scd30_reports_and_goes_technical(monkeypatch, capsys):
    out = run_firmware(monkeypatch, capsys, "scd30", 5)
    assert any(r["type"] == "err" for r in out)
    assert any(r["type"] == "e" and r.get("to") == "SENSOR_SILENT" for r in out)


def test_silent_uart_sensor_goes_technical(monkeypatch, capsys):
    out = run_firmware(monkeypatch, capsys, "mhz", 5)
    assert any(r["type"] == "e" and r.get("to") == "SENSOR_SILENT" for r in out)
