"""Pairwise agreement between two maps of the same model, in the same unit.

Reports rather than asserts. qmrust's ci/compare_maps.py uses the same two criteria
to gate its build; here they are columns on a site, because this repo measures
history rather than policing a pull request.
"""
from __future__ import annotations

import numpy as np


def compare_maps(
    a: np.ndarray, b: np.ndarray, mask: np.ndarray, *, rel_tol: float = 0.01
) -> dict:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError(f"voxel count mismatch: {a.shape} vs {b.shape}")

    sel = np.asarray(mask).astype(bool) & np.isfinite(a) & np.isfinite(b)
    x, y = a[sel], b[sel]

    if x.size == 0:
        return {
            "n": 0, "frac_within": None, "pearson_r": None,
            "mean_delta": None, "median_delta": None, "max_abs_delta": None,
        }

    delta = x - y
    # Relative to the reference `b`, matching compare_maps.py. Where b is exactly
    # zero the tolerance band collapses, so only an exact match counts — correct,
    # since a relative tolerance around zero has no meaning.
    within = np.abs(delta) <= rel_tol * np.abs(y)

    if x.size > 1 and x.std() > 0 and y.std() > 0:
        pearson_r = float(np.corrcoef(x, y)[0, 1])
    else:
        pearson_r = None

    return {
        "n": int(x.size),
        "frac_within": float(within.mean()),
        "pearson_r": pearson_r,
        "mean_delta": float(delta.mean()),
        "median_delta": float(np.median(delta)),
        "max_abs_delta": float(np.abs(delta).max()),
    }
