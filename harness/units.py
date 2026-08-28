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
    # A B1 map written as 'au' in this repo is a ratio in which 1.0 means the nominal
    # flip angle was achieved, so it is dimensionally a fraction: this pair is an
    # identity, not a rescale. It has to be in the table BEFORE any model declares
    # 'fraction', because every adapter record already in results/ declares 'au' —
    # flipping models/b1_*.yml first would leave ('au', 'fraction') missing and fail
    # both B1 models on every target at once. The pair exists so a second software
    # that reports B1 as percent-of-nominal (100 = nominal, which is what hMRI writes)
    # can declare 'percent' and be scaled, instead of declaring 'au' and publishing a
    # 100x error as though it were a fit difference.
    ("au", "fraction"): 1.0,
    ("fraction", "au"): 1.0,
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
