"""The two derived-number primitives: canonical hashing and masked statistics."""
from __future__ import annotations

import hashlib

import numpy as np

_QUIET_NAN = np.uint64(0x7FF8000000000000)


def canonical_bytes(values: np.ndarray) -> bytes:
    """Serialize voxel values so equal numbers give equal bytes.

    float64 little-endian in C order, with every NaN collapsed to one quiet-NaN
    pattern because NaN payloads are not required to be reproducible across
    implementations. Signed zero is deliberately left alone: -0.0 and +0.0 are a
    real difference and hiding it would be a lie about the fit.
    """
    out = np.ascontiguousarray(values, dtype=np.float64)
    bits = out.view(np.uint64).copy()
    bits[np.isnan(out)] = _QUIET_NAN
    return bits.astype("<u8").tobytes()


def voxel_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(canonical_bytes(values)).hexdigest()


def masked_stats(values: np.ndarray, mask: np.ndarray, *, scale: float = 1.0) -> dict:
    """Summary statistics over the repo-owned mask, in the canonical unit.

    `scale` is applied before computing so that statistics are comparable across
    softwares that disagree on units. It is never applied to the hash — see
    canonical_bytes.

    Non-finite voxels are excluded from the statistics but counted, because "this
    version produced 4000 NaNs where that one produced none" is a finding, not noise.
    """
    values = np.asarray(values, dtype=np.float64)
    selected = values[np.asarray(mask).astype(bool)]

    finite = np.isfinite(selected)
    n_nonfinite = int((~finite).sum())
    kept = selected[finite] * scale

    if kept.size == 0:
        return {
            "n": 0, "mean": None, "std": None, "median": None,
            "p05": None, "p95": None, "min": None, "max": None,
            "n_nonfinite": n_nonfinite, "n_zero": 0,
        }

    return {
        "n": int(kept.size),
        "mean": float(kept.mean()),
        "std": float(kept.std(ddof=0)),
        "median": float(np.median(kept)),
        "p05": float(np.percentile(kept, 5)),
        "p95": float(np.percentile(kept, 95)),
        "min": float(kept.min()),
        "max": float(kept.max()),
        "n_nonfinite": n_nonfinite,
        "n_zero": int((kept == 0.0).sum()),
    }
