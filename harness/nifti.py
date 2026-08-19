"""NIfTI-1 parsing, stdlib plus numpy.

Only what the benchmark needs: shape, datatype, the intensity transform, and the
voxel array. Orientation and affine are irrelevant here because every target fits
the same input grid, so a map is comparable to another map by index.
"""
from __future__ import annotations

import dataclasses
import gzip
import pathlib
import struct

import numpy as np

_DTYPES = {2: "u1", 4: "i2", 8: "i4", 16: "f4", 64: "f8"}


@dataclasses.dataclass(frozen=True)
class Nifti:
    shape: tuple[int, ...]
    datatype: int
    scl_slope: float
    scl_inter: float
    raw: np.ndarray

    @property
    def values(self) -> np.ndarray:
        """Voxels as float64 with the NIfTI intensity transform applied.

        A zero slope means "unset" per the spec, so it is identity rather than a
        multiply by zero.
        """
        out = self.raw.astype(np.float64)
        if self.scl_slope not in (0.0, 1.0) or self.scl_inter != 0.0:
            out = self.scl_slope * out + self.scl_inter
        return out


def _open(path: pathlib.Path) -> bytes:
    data = path.read_bytes()
    if data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    return data


def read_nifti(path: str | pathlib.Path) -> Nifti:
    b = _open(pathlib.Path(path))
    # sizeof_hdr is 348 in the file's own byte order; a mismatch means the other one.
    endian = "<" if struct.unpack_from("<i", b, 0)[0] == 348 else ">"

    dim = struct.unpack_from(endian + "8h", b, 40)
    shape = tuple(int(d) for d in dim[1 : dim[0] + 1])
    datatype = struct.unpack_from(endian + "h", b, 70)[0]
    if datatype not in _DTYPES:
        raise ValueError(f"unsupported NIfTI datatype {datatype} in {path}")
    scl_slope, scl_inter = struct.unpack_from(endian + "2f", b, 112)
    vox_offset = int(struct.unpack_from(endian + "f", b, 108)[0])

    n = int(np.prod(shape)) if shape else 0
    dtype = np.dtype(endian + _DTYPES[datatype])
    raw = np.frombuffer(b, dtype=dtype, count=n, offset=vox_offset)

    return Nifti(
        shape=shape,
        datatype=datatype,
        scl_slope=float(scl_slope),
        scl_inter=float(scl_inter),
        raw=raw,
    )
