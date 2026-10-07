"""Monitoring and alarm state machine (Figure 3 of the project card).

Two independent dimensions are tracked:

* the patient alarm: NORMAL, ADVISORY (amber, 3 pulse) or CRITICAL (red,
  10 pulse, latched until acknowledged and back in range), and
* technical faults (cyan, chirp): blocked or open sampling line, silent or
  out-of-range sensor, zero drift.

A technical fault means the CO2 signal cannot be trusted, so while one is
active the loss-of-CO2 critical alarm is *not* raised and the evidence clock is
restarted when the fault clears. That is what keeps a blocked line from ever
presenting as a patient who has stopped breathing (CR-3).

Monitoring has three phases: STANDBY (not connected), CONFIRMING (armed by the
operator after placing the tube or mask, waiting for exhaled CO2) and CONFIRMED
(exhaled CO2 seen on enough consecutive breaths; the circuit is now "reported
as connected" and loss of CO2 is a critical alarm, CR-2).
"""

from .breath import BreathDetector
from .capability import captured_fraction
from .ring import Ring, median

STANDBY = "STANDBY"
CONFIRMING = "CONFIRMING"
CONFIRMED = "CONFIRMED"

NORMAL = "NORMAL"
ADVISORY = "ADVISORY"
CRITICAL = "CRITICAL"
TECHNICAL = "TECHNICAL"

# Technical fault codes
LINE_BLOCKED = "LINE_BLOCKED"
LINE_OPEN = "LINE_OPEN"
LINE_SENSOR = "LINE_SENSOR"
SENSOR_SILENT = "SENSOR_SILENT"
SENSOR_RANGE = "SENSOR_RANGE"
SENSOR_COMMS = "SENSOR_COMMS"
ZERO_DRIFT = "ZERO_DRIFT"
BASELINE_HIGH = "BASELINE_HIGH"

# Critical reasons
NO_CO2 = "NO_CO2"                  # armed, exhaled CO2 never confirmed
CO2_NOT_SUSTAINED = "CO2_NOT_SUSTAINED"
CO2_LOST = "CO2_LOST"              # was confirmed, now absent with a healthy line

AMBIENT_PCT = 0.04


class Monitor:
    def __init__(self, cfg):
        self.cfg = cfg
        self.det = BreathDetector(cfg)
        n_trend = max(2, cfg["trend_mean_ms"] // cfg["block_ms"])
        self.trend_blocks = Ring(n_trend)
        self.recent_peaks = Ring(32)
        self.confirm_peaks = Ring(cfg["confirm_breaths"])
        self._reset_state()

    # ------------------------------------------------------------------ setup
    def _reset_state(self):
        self.mon = STANDBY
        self.alarm = NORMAL
        self.alarm_reason = None
        self.alarm_t = None
        self.acked = False
        self.audio_paused_until = None
        self.technical = {}
        self._tech_seen = {}
        self._tech_gone = {}
        self.last_sample_t = None
        self.last_co2 = None
        self.last_vac = None
        self.last_co2_t = None
        self.evidence_floor_t = None
        self.arm_t = None
        self.confirmed_t = None
        self.trend_ok_since = None
        self.trend_max = 0.0
        self._tb_t = None
        self._tb_sum = 0.0
        self._tb_n = 0
        self.breaths_since_alarm = 0
        self.baseline_et = None
        self.baseline_rr = None
        self._bl_et = []
        self._bl_rr = []
        self._bl_last_t = None
        self.adv_since = None
        self.adv_clear_since = None
        self.adv_reasons = []
        self._zero_since = None
        self._neg_since = None
        self._high_base_since = None
        self.et = None
        self.et_kind = None
        self.rr = None
        self.n_breaths = 0
        self.det.reset()
        self.trend_blocks.clear()
        self.recent_peaks.clear()
        self.confirm_peaks.clear()

    # --------------------------------------------------------------- commands
    def arm(self, t):
        """Operator has placed the airway: start the confirmation clock."""
        out = []
        if self.mon == STANDBY:
            self._set_mon(t, CONFIRMING, "armed", out)
            self.arm_t = t
            self.confirm_peaks.clear()
            self.trend_ok_since = None
            self.trend_max = 0.0
        return out

    def disarm(self, t):
        """End of case. Clears every patient alarm."""
        out = []
        prev_mon, prev_alarm = self.mon, self.alarm
        tech = self.technical
        self._reset_state()
        self.technical = tech
        self.last_sample_t = t
        if prev_alarm != NORMAL:
            out.append(_event(t, "alarm", prev_alarm, NORMAL, "disarmed"))
        if prev_mon != STANDBY:
            out.append(_event(t, "monitor", prev_mon, STANDBY, "disarmed"))
        return out

    def acknowledge(self, t):
        out = []
        if self.alarm in (CRITICAL, ADVISORY) or self.technical:
            self.audio_paused_until = t + self.cfg["audio_pause_ms"]
            out.append(_event(t, "ack", self.alarm, self.alarm, "acknowledged"))
        if self.alarm == CRITICAL:
            self.acked = True
            self._try_clear_critical(t, out)
        return out

    def rebaseline(self, t):
        self.baseline_et = None
        self.baseline_rr = None
        self._bl_et = []
        self._bl_rr = []
        self.confirmed_t = t
        return [_event(t, "baseline", None, None, "restarted")]

    # ------------------------------------------------------------- main step
    def update(self, t, co2=None, vac=None, comms_error=False):
        """Advance the monitor to time ``t`` (ms).

        co2:  new CO2 reading in percent, or None if no new sample arrived.
        vac:  sampling line vacuum in kPa (ambient minus pump inlet), or None.
        comms_error: the driver saw a corrupt frame since the last call.
        Returns a list of breath and event records.
        """
        cfg = self.cfg
        out = []

        # --- sensor validity ---------------------------------------------
        valid = False
        if co2 is not None:
            in_range = cfg["co2_valid_min_pct"] <= co2 <= cfg["co2_valid_max_pct"]
            self._tech(t, SENSOR_RANGE, not in_range, 500, out)
            if in_range:
                valid = True
                self.last_sample_t = t
                self.last_co2 = co2
        if self.last_sample_t is None:
            self.last_sample_t = t
        self._tech(t, SENSOR_SILENT, t - self.last_sample_t > cfg["sensor_timeout_ms"], 0, out)
        self._tech(t, SENSOR_COMMS, comms_error, 0, out)

        # --- sampling line ------------------------------------------------
        if cfg["line_monitored"]:
            self.last_vac = vac
            if vac is None:
                self._tech(t, LINE_SENSOR, True, cfg["line_fault_debounce_ms"], out)
            else:
                self._tech(t, LINE_SENSOR, False, 0, out)
                nom = cfg["line_vac_nominal_kpa"]
                d = cfg["line_fault_debounce_ms"]
                self._tech(t, LINE_BLOCKED, vac > nom * cfg["line_block_factor"], d, out)
                self._tech(t, LINE_OPEN, vac < nom * cfg["line_open_factor"], d, out)

        # --- signal processing --------------------------------------------
        if valid:
            self._zero_checks(t, co2, out)
            self._trend(t, co2)
            b = self.det.update(t, co2)
            if b is not None:
                self._on_breath(t, b, out)
            if co2 >= cfg["co2_breath_min_pct"] and not self.technical:
                self.last_co2_t = t

        self.rr = self.det.rate(t)
        self._update_et(t)

        # --- state machine ------------------------------------------------
        if self.mon == CONFIRMING:
            self._confirming(t, out)
        elif self.mon == CONFIRMED:
            self._confirmed(t, out)
        elif self.mon == STANDBY:
            self._standby(t, out)

        if self.alarm == CRITICAL:
            self._try_clear_critical(t, out)
        return out

    # ------------------------------------------------------------- internals
    def _tech(self, t, code, condition, debounce_ms, out):
        if condition:
            self._tech_gone.pop(code, None)
            if code in self.technical:
                return
            first = self._tech_seen.get(code)
            if first is None:
                first = t
                self._tech_seen[code] = t
            if t - first >= debounce_ms:
                was_clear = not self.technical
                self.technical[code] = t
                out.append(_event(t, "technical", None, code, "fault"))
                if was_clear:
                    self.audio_paused_until = None
        else:
            self._tech_seen.pop(code, None)
            if code not in self.technical:
                return
            gone = self._tech_gone.get(code)
            if gone is None:
                self._tech_gone[code] = t
                return
            if t - gone >= self.cfg["technical_clear_ms"]:
                del self.technical[code]
                del self._tech_gone[code]
                out.append(_event(t, "technical", code, None, "cleared"))
                if not self.technical:
                    # Signal is trustworthy again from now: give the patient a
                    # fresh window instead of alarming on stale evidence.
                    self.evidence_floor_t = t
                    self.trend_ok_since = None

    def _zero_checks(self, t, co2, out):
        cfg = self.cfg
        if co2 < -0.2:
            if self._neg_since is None:
                self._neg_since = t
        else:
            self._neg_since = None
        drift = self._neg_since is not None and t - self._neg_since >= 5000
        if self.mon == STANDBY and self.det.phase == "flat":
            if abs(co2 - AMBIENT_PCT) > cfg["zero_tol_pct"]:
                if self._zero_since is None:
                    self._zero_since = t
            else:
                self._zero_since = None
        else:
            self._zero_since = None
        if self._zero_since is not None and t - self._zero_since >= cfg["zero_check_ms"]:
            drift = True
        self._tech(t, ZERO_DRIFT, drift, 0, out)

        # Inspired CO2 that never returns to zero while breaths are resolved:
        # zero drift or rebreathing. Only meaningful below the rate at which
        # this hardware can resolve breaths (trough is legitimately high above it).
        high = False
        rr = self.det.rate(t)
        if (self.mon == CONFIRMED and rr is not None and cfg["max_resolvable_rr"] > 0
                and rr <= cfg["max_resolvable_rr"]):
            lo, _hi = self.det._envelope()
            if lo > cfg["baseline_high_pct"]:
                if self._high_base_since is None:
                    self._high_base_since = t
                high = t - self._high_base_since >= cfg["zero_check_ms"]
            else:
                self._high_base_since = None
        else:
            self._high_base_since = None
        self._tech(t, BASELINE_HIGH, high, 0, out)

    def _trend(self, t, co2):
        cfg = self.cfg
        if self._tb_t is None:
            self._tb_t = t
        if t - self._tb_t >= cfg["block_ms"] and self._tb_n:
            self.trend_blocks.append(self._tb_sum / self._tb_n)
            self._tb_t, self._tb_sum, self._tb_n = t, 0.0, 0
        self._tb_sum += co2
        self._tb_n += 1

    def trend_mean(self):
        n = len(self.trend_blocks)
        if n < self.trend_blocks._cap // 2:
            return None
        s = 0.0
        for i in range(n):
            s += self.trend_blocks[i]
        return s / n

    def _on_breath(self, t, b, out):
        rec = {"type": "b", "t": b["t"], "end": b["end"], "peak": round(b["peak"], 3),
               "co2": b["co2"], "interval_ms": b["interval_ms"]}
        out.append(rec)
        if not b["co2"] or self.technical:
            return
        self.n_breaths += 1
        self.recent_peaks.append((b["t"], b["peak"]))
        self.confirm_peaks.append(b["peak"])
        if self.alarm == CRITICAL:
            self.breaths_since_alarm += 1

    def _update_et(self, t):
        peaks = [p for (bt, p) in self.recent_peaks.items() if t - bt <= 30000]
        if self.rr is not None and len(peaks) >= 2:
            self.et = median(peaks)
            lim = self.cfg["max_resolvable_rr"]
            # Breaths are detected, but above the published resolution limit
            # the peaks under-read end-tidal CO2: say so instead of hiding it.
            self.et_kind = "breath" if (lim > 0 and self.rr <= lim) else "attenuated"
        else:
            # Breaths not resolved: report the breath-averaged peak of the trace
            # and label it as such. It under-reads true end-tidal CO2.
            if self.det.block_hi is None:
                self.et = None
            else:
                self.et = self.det._envelope()[1]
            self.et_kind = "trend"

    def _sustained_confirm(self):
        n = self.cfg["confirm_breaths"]
        if len(self.confirm_peaks) < n:
            return None
        peaks = self.confirm_peaks.items()
        half = n // 2
        early = max(peaks[:half])
        late = min(peaks[half:])
        return late >= self.cfg["confirm_sustain_frac"] * early

    def _trend_confirm(self, t):
        cfg = self.cfg
        m = self.trend_mean()
        if m is None or self.technical:
            self.trend_ok_since = None
            return False
        if m > self.trend_max:
            self.trend_max = m
        ok = m >= cfg["trend_present_pct"] and m >= cfg["confirm_sustain_frac"] * self.trend_max
        if not ok:
            self.trend_ok_since = None
            return False
        if self.trend_ok_since is None:
            self.trend_ok_since = t
        return t - self.trend_ok_since >= cfg["trend_confirm_ms"]

    def _confirm_now(self, t, how, out):
        self._set_mon(t, CONFIRMED, how, out)
        self.confirmed_t = t
        self._bl_et = []
        self._bl_rr = []
        self.baseline_et = None
        self.baseline_rr = None

    def _standby(self, t, out):
        # A patient already breathing CO2 into the line confirms itself.
        if self._sustained_confirm() or self._trend_confirm(t):
            self._confirm_now(t, "auto", out)

    def _confirming(self, t, out):
        cfg = self.cfg
        sustained = self._sustained_confirm()
        if sustained or self._trend_confirm(t):
            self._confirm_now(t, "co2 confirmed", out)
            return
        if self.alarm == CRITICAL or self.technical:
            return
        if sustained is False:
            self._raise(t, CRITICAL, CO2_NOT_SUSTAINED, out)
            return
        start = self.arm_t
        if self.evidence_floor_t is not None and self.evidence_floor_t > start:
            start = self.evidence_floor_t
        if t - start > self.confirm_timeout_ms():
            self._raise(t, CRITICAL, NO_CO2, out)

    def confirm_timeout_ms(self):
        """Confirmation window stretched by the instrument's own delay and lag."""
        cfg = self.cfg
        return (cfg["confirm_timeout_ms"] + (cfg["delay_ms"] or 0)
                + 2 * (cfg["t10_90_ms"] or 0))

    def loss_window_ms(self):
        cfg = self.cfg
        m = self.det.median_interval_ms()
        if m is None:
            return cfg["loss_window_default_ms"]
        w = int(cfg["loss_window_breaths"] * m)
        if w < cfg["loss_window_min_ms"]:
            w = cfg["loss_window_min_ms"]
        if w > cfg["loss_window_max_ms"]:
            w = cfg["loss_window_max_ms"]
        return w

    def evidence_age_ms(self, t):
        ref = self.last_co2_t
        if self.evidence_floor_t is not None and (ref is None or self.evidence_floor_t > ref):
            ref = self.evidence_floor_t
        if ref is None:
            ref = self.confirmed_t if self.confirmed_t is not None else t
        return t - ref

    def _confirmed(self, t, out):
        cfg = self.cfg
        if not self.technical and self.alarm_reason != CO2_LOST:
            # Also re-raise over a latched NO_CO2 so a stale reason never masks
            # a disconnection that happens later.
            if self.evidence_age_ms(t) > self.loss_window_ms():
                self._raise(t, CRITICAL, CO2_LOST, out)
                return
        self._baseline(t)
        if self.alarm == CRITICAL or self.technical:
            self.adv_since = None
            return

        reasons = []
        et = self.et
        if et is not None:
            # An absolute end-tidal threshold is only meaningful when breaths
            # are resolved. An attenuated or breath-averaged value under-reads,
            # so there only a fall relative to its own baseline is judged.
            if self.et_kind == "breath" and et < cfg["et_low_pct"]:
                reasons.append("ETCO2_LOW")
            elif self.baseline_et is not None and et < (1.0 - cfg["et_fall_frac"]) * self.baseline_et:
                reasons.append("ETCO2_FALL" if self.et_kind == "breath" else "CO2_TREND_FALL")
        rr = self.rr
        if rr is not None:
            if rr < cfg["rr_low_per_min"]:
                reasons.append("RR_LOW")
            elif self.baseline_rr is not None and rr < (1.0 - cfg["rr_fall_frac"]) * self.baseline_rr:
                reasons.append("RR_FALL")

        if reasons:
            self.adv_clear_since = None
            if self.adv_since is None:
                self.adv_since = t
            if self.alarm == NORMAL and t - self.adv_since >= cfg["advisory_sustain_ms"]:
                self.adv_reasons = reasons
                self._raise(t, ADVISORY, ",".join(reasons), out)
        else:
            self.adv_since = None
            if self.alarm == ADVISORY:
                if self.adv_clear_since is None:
                    self.adv_clear_since = t
                if t - self.adv_clear_since >= cfg["advisory_clear_ms"]:
                    self._set_alarm(t, NORMAL, "back in range", out)

    def _baseline(self, t):
        cfg = self.cfg
        if self.baseline_et is not None or self.confirmed_t is None:
            return
        if self._bl_last_t is None or t - self._bl_last_t >= 1000:
            self._bl_last_t = t
            if self.et is not None:
                self._bl_et.append(self.et)
            if self.rr is not None:
                self._bl_rr.append(self.rr)
        if t - self.confirmed_t >= cfg["baseline_ms"]:
            self.baseline_et = median(self._bl_et)
            self.baseline_rr = median(self._bl_rr)

    def _raise(self, t, level, reason, out):
        if level == CRITICAL:
            self.acked = False
            self.breaths_since_alarm = 0
            self.audio_paused_until = None
        self._set_alarm(t, level, reason, out)

    def _set_alarm(self, t, level, reason, out):
        prev = self.alarm
        self.alarm = level
        self.alarm_reason = None if level == NORMAL else reason
        self.alarm_t = t
        if level == NORMAL:
            self.adv_since = None
            self.adv_clear_since = None
        out.append(_event(t, "alarm", prev, level, reason))

    def _set_mon(self, t, state, reason, out):
        prev = self.mon
        self.mon = state
        out.append(_event(t, "monitor", prev, state, reason))

    def _try_clear_critical(self, t, out):
        if not self.acked or self.technical:
            return
        cfg = self.cfg
        recovered = False
        if self.alarm_reason == CO2_LOST:
            recent = self.last_co2_t is not None and t - self.last_co2_t < self.loss_window_ms()
            m = self.trend_mean()
            recovered = recent and (self.breaths_since_alarm >= cfg["recover_breaths"]
                                    or (m is not None and m >= cfg["trend_present_pct"]))
        else:
            # NO_CO2 / CO2_NOT_SUSTAINED: back in range means placement confirmed.
            recovered = self.mon == CONFIRMED
        if recovered:
            self._set_alarm(t, NORMAL, "acknowledged and back in range", out)
            self.acked = False

    # ---------------------------------------------------------------- output
    def display(self):
        if self.alarm == CRITICAL:
            return CRITICAL
        if self.technical:
            return TECHNICAL
        if self.alarm == ADVISORY:
            return ADVISORY
        if self.mon == CONFIRMED:
            return NORMAL
        return self.mon

    def audio_paused(self, t):
        return self.audio_paused_until is not None and t < self.audio_paused_until

    def status(self, t):
        cfg = self.cfg
        rr = self.rr
        rr_note = None
        lim = cfg["max_resolvable_rr"]
        if rr is None and self.et_kind == "trend" and self.mon == CONFIRMED:
            rr_note = "unresolved"
        elif rr is not None and lim <= 0:
            rr_note = "unverified"
        elif rr is not None and rr > lim:
            rr_note = "beyond_limit"
        elif rr is not None and rr > 0.9 * lim:
            rr_note = "near_limit"
        capture = None
        if rr is not None and cfg["t10_90_ms"]:
            capture = round(captured_fraction(rr, cfg["t10_90_ms"] / 1000.0), 2)
        return {
            "display": self.display(),
            "mon": self.mon,
            "alarm": self.alarm,
            "reason": self.alarm_reason,
            "tech": sorted(self.technical.keys()),
            "acked": self.acked,
            "paused": self.audio_paused(t),
            "co2": None if self.last_co2 is None else round(self.last_co2, 3),
            "vac": None if self.last_vac is None else round(self.last_vac, 2),
            "et": None if self.et is None else round(self.et, 2),
            "et_kind": self.et_kind,
            "et_capture": capture,
            "rr": None if rr is None else round(rr, 1),
            "rr_note": rr_note,
            "base_et": None if self.baseline_et is None else round(self.baseline_et, 2),
            "base_rr": None if self.baseline_rr is None else round(self.baseline_rr, 1),
            "confirm": len(self.confirm_peaks),
            "evidence_age_ms": self.evidence_age_ms(t) if self.mon != STANDBY else None,
            "loss_window_ms": self.loss_window_ms(),
        }


def _event(t, kind, frm, to, reason):
    return {"type": "e", "t": t, "kind": kind, "from": frm, "to": to, "reason": reason}
