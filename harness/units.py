"""Unit conversions for expressing statistics in a model's canonical unit.

Deliberately tiny and deliberately strict. An unknown pair raises rather than
defaulting to identity, because a wrong scale produces numbers that look entirely
plausible on a site and are wrong by three orders of magnitude.
"""
from __future__ import annotations

_FACTORS: dict[tuple[str, str], float] = {
    ("ms", "s"): 0.001,
    ("s", "ms"): 1000.0,
    ("percent", "fraction"): 0.01,
    ("fraction", "percent"): 100.0,
    ("Hz", "s^-1"): 1.0,
    ("s^-1", "Hz"): 1.0,
}

KNOWN_UNITS = {"s", "ms", "percent", "fraction", "au", "Hz", "s^-1"}


def scale_between(produced: str, canonical: str) -> float:
    if produced not in KNOWN_UNITS:
        raise ValueError(f"unknown unit {produced!r}")
    if canonical not in KNOWN_UNITS:
        raise ValueError(f"unknown unit {canonical!r}")
    if produced == canonical:
        return 1.0
    try:
        return _FACTORS[(produced, canonical)]
    except KeyError:
        raise ValueError(f"no conversion from {produced!r} to {canonical!r}") from None
