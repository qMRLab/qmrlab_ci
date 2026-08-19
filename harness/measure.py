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
