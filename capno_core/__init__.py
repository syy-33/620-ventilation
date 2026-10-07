"""Shared detection and alarm logic for the Project 06 exhaled CO2 monitor.

This package is deliberately written in the subset of Python that runs under
CircuitPython 9 (no dataclasses, typing, enum, statistics or deque indexing) so
that exactly the same code drives the bedside alarm on the Pico and is unit
tested with pytest on the laptop. All times are integer milliseconds so that
CircuitPython's 30-bit floats never limit timing resolution.
"""

VERSION = "0.1.0"
