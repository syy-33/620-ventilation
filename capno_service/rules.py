"""Service-side rules: who is told what, and when the bedside link is lost.

The patient alarm decision is made on the bedside unit (capno_core) so that it
works with the laptop unplugged. The service decides only:
  * which state changes become phone notifications (CRITICAL at once, ADVISORY
    at once, TECHNICAL only if it persists, so a brief kink does not page anyone),
  * re-notification of an unacknowledged CRITICAL,
  * a LINK_LOST technical state when the bedside unit goes silent.
"""

TECH_PERSIST_S = 10.0
ESCALATE_S = 60.0
LINK_TIMEOUT_S = 3.0
COOLDOWN_S = 60.0


class Rules:
    def __init__(self, notifier, tech_persist_s=TECH_PERSIST_S, escalate_s=ESCALATE_S,
                 link_timeout_s=LINK_TIMEOUT_S, cooldown_s=COOLDOWN_S):
        self.notifier = notifier
        self.tech_persist_s = tech_persist_s
        self.escalate_s = escalate_s
        self.link_timeout_s = link_timeout_s
        self.cooldown_s = cooldown_s
        self.tech_pending = {}       # code -> (host_ts, event_id)
        self.critical = None         # (reason, host_ts, event_id, last_notified)
        self.last_sent = {}          # (level, reason) -> host_ts
        self.link_lost = False

    def _send(self, level, reason, event_id, host_ts, force=False):
        key = (level, reason)
        last = self.last_sent.get(key)
        if not force and last is not None and host_ts - last < self.cooldown_s:
            return False
        self.last_sent[key] = host_ts
        if self.notifier is not None:
            self.notifier.notify(level, reason, event_id, host_ts)
        return True

    def on_event(self, rec, event_id, host_ts):
        kind = rec.get("kind")
        if kind == "alarm":
            to = rec.get("to")
            if to == "CRITICAL":
                self.critical = [rec.get("reason"), host_ts, event_id, host_ts]
                self._send("CRITICAL", rec.get("reason"), event_id, host_ts, force=True)
            elif to == "ADVISORY":
                self._send("ADVISORY", rec.get("reason"), event_id, host_ts)
            if to != "CRITICAL":
                self.critical = None
        elif kind == "ack":
            self.critical = None       # acknowledged at the bedside: stop re-notifying
        elif kind == "technical":
            if rec.get("to"):
                self.tech_pending[rec["to"]] = (host_ts, event_id)
            elif rec.get("from"):
                self.tech_pending.pop(rec["from"], None)

    def tick(self, now, last_rx_ts):
        """Call about twice a second. Returns 'lost', 'restored' or None for the link."""
        for code, (since, event_id) in list(self.tech_pending.items()):
            if now - since >= self.tech_persist_s:
                self._send("TECHNICAL", code, event_id, now)
                del self.tech_pending[code]
        if self.critical is not None and now - self.critical[3] >= self.escalate_s:
            self.critical[3] = now
            self._send("CRITICAL", self.critical[0], self.critical[2], now, force=True)
        if last_rx_ts is None:
            return None
        silent = now - last_rx_ts > self.link_timeout_s
        if silent and not self.link_lost:
            self.link_lost = True
            self._send("TECHNICAL", "LINK_LOST", None, now)
            return "lost"
        if not silent and self.link_lost:
            self.link_lost = False
            return "restored"
        return None
