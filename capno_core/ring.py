"""Small fixed-size containers that behave the same on CPython and CircuitPython."""


class Ring:
    """Fixed capacity FIFO with indexing from oldest (0) to newest (-1)."""

    def __init__(self, capacity):
        self._buf = [None] * capacity
        self._cap = capacity
        self._start = 0
        self._len = 0

    def append(self, item):
        if self._len < self._cap:
            self._buf[(self._start + self._len) % self._cap] = item
            self._len += 1
        else:
            self._buf[self._start] = item
            self._start = (self._start + 1) % self._cap

    def clear(self):
        self._start = 0
        self._len = 0

    def __len__(self):
        return self._len

    def __getitem__(self, i):
        if i < 0:
            i += self._len
        if i < 0 or i >= self._len:
            raise IndexError("ring index out of range")
        return self._buf[(self._start + i) % self._cap]

    def items(self):
        return [self[i] for i in range(self._len)]


def median(values):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return 0.5 * (s[mid - 1] + s[mid])
