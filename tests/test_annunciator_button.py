from capno_core.annunciator import AMBER, CYAN, GREEN, OFF, RED, Annunciator, tone_at, CRITICAL_TONE
from capno_core.button import ButtonClassifier


def tones(display, ms=12000, paused=False):
    a = Annunciator()
    hz = [a.update(t, display, paused)[1] for t in range(0, ms, 5)]
    pulses, prev = 0, 0
    for h in hz:
        if h and not prev:
            pulses += 1
        prev = h
    return pulses


def test_critical_burst_has_ten_pulses():
    assert tones("CRITICAL", 9000) == 10


def test_advisory_burst_has_three_pulses():
    assert tones("ADVISORY", 15000) == 3


def test_technical_is_a_single_chirp():
    assert tones("TECHNICAL", 14000) == 1


def test_normal_is_silent_and_green():
    a = Annunciator()
    px, hz = a.update(0, "NORMAL")
    assert hz == 0 and px[0] == GREEN


def test_paused_audio_is_silent_but_light_continues():
    a = Annunciator()
    px, hz = a.update(0, "CRITICAL", paused=True)
    assert hz == 0 and px[0] == RED


def test_colours_and_flashing():
    a = Annunciator()
    assert a.update(0, "TECHNICAL")[0][0] == CYAN
    a = Annunciator()
    assert a.update(0, "ADVISORY")[0][0] == AMBER
    assert a.update(1000, "ADVISORY")[0][0] == OFF


def test_confirming_shows_progress():
    a = Annunciator()
    px, _ = a.update(0, "CONFIRMING", confirm_count=3, confirm_needed=6)
    assert sum(1 for p in px if p != OFF) == 8


def test_tone_repeats():
    assert tone_at(CRITICAL_TONE, 0) and tone_at(CRITICAL_TONE, 10000)


def press(b, t0, dur):
    events = []
    for t in range(t0, t0 + dur, 10):
        e = b.update(t, True)
        if e:
            events.append(e)
    for t in range(t0 + dur, t0 + dur + 1000, 10):
        e = b.update(t, False)
        if e:
            events.append(e)
    return events


def test_short_long_hold_and_ignored():
    assert press(ButtonClassifier(), 0, 200) == ["short"]
    assert press(ButtonClassifier(), 0, 3000) == ["long"]
    assert press(ButtonClassifier(), 0, 6000) == ["hold"]
    assert press(ButtonClassifier(), 0, 1500) == []


def test_double_press():
    b = ButtonClassifier()
    ev = []
    for t in range(0, 2000, 10):
        down = 0 <= t < 150 or 300 <= t < 450
        e = b.update(t, down)
        if e:
            ev.append(e)
    assert ev == ["double"]


def test_bounce_is_ignored():
    b = ButtonClassifier()
    ev = []
    for t in range(0, 1500, 5):
        down = (t < 20 and t % 10 < 5)       # 20 ms of chatter
        e = b.update(t, down)
        if e:
            ev.append(e)
    assert ev == []
