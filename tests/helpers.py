"""Synthetic NIfTI-1 construction, so tests need no network and no MATLAB."""
import gzip
import pathlib
import struct

import numpy as np

_NUMPY_DTYPE = {2: np.uint8, 4: np.int16, 8: np.int32, 16: np.float32, 64: np.float64}


def make_nifti_bytes(values, *, shape, datatype=16, scl_slope=1.0, scl_inter=0.0):
    """Return gzipped NIfTI-1 (single-file, magic 'n+1') holding `values`."""
    hdr = bytearray(348)
    struct.pack_into("<i", hdr, 0, 348)
    dim = [len(shape)] + list(shape) + [1] * (7 - len(shape))
    struct.pack_into("<8h", hdr, 40, *dim)
    struct.pack_into("<h", hdr, 70, datatype)
    struct.pack_into("<h", hdr, 72, np.dtype(_NUMPY_DTYPE[datatype]).itemsize * 8)
    struct.pack_into("<f", hdr, 108, 352.0)
    struct.pack_into("<2f", hdr, 112, scl_slope, scl_inter)
    hdr[344:348] = b"n+1\x00"
    body = np.asarray(values, dtype=_NUMPY_DTYPE[datatype]).tobytes()
    return gzip.compress(bytes(hdr) + b"\x00" * 4 + body)


def write_nifti(path, values, **kw):
    pathlib.Path(path).write_bytes(make_nifti_bytes(values, **kw))
