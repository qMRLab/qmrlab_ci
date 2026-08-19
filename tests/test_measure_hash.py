import numpy as np

from harness.measure import voxel_sha256
from harness.nifti import read_nifti
from tests.helpers import write_nifti


def test_float32_and_float64_storage_hash_identically(tmp_path):
    """Same numbers, different storage dtype — the fit is the same, so the hash is."""
    a, b = tmp_path / "a.nii.gz", tmp_path / "b.nii.gz"
    write_nifti(a, [1.5, 2.25, 3.0], shape=(3,), datatype=16)
    write_nifti(b, [1.5, 2.25, 3.0], shape=(3,), datatype=64)

    assert voxel_sha256(read_nifti(a).values) == voxel_sha256(read_nifti(b).values)


def test_scaled_integer_storage_hashes_as_its_real_values(tmp_path):
    a, b = tmp_path / "a.nii.gz", tmp_path / "b.nii.gz"
    write_nifti(a, [2, 4], shape=(2,), datatype=4, scl_slope=0.5)
    write_nifti(b, [1.0, 2.0], shape=(2,), datatype=64)

    assert voxel_sha256(read_nifti(a).values) == voxel_sha256(read_nifti(b).values)


def test_nan_payloads_are_normalized():
    quiet = np.array([np.nan], dtype=np.float64)
    signalling = np.frombuffer(np.uint64(0x7FF8000000000001).tobytes(), dtype=np.float64)

    assert voxel_sha256(quiet) == voxel_sha256(signalling.copy())


def test_signed_zero_is_not_normalized():
    """A sign difference on zero is real, so it must remain visible."""
    assert voxel_sha256(np.array([0.0])) != voxel_sha256(np.array([-0.0]))


def test_hash_is_stable_and_hex():
    h = voxel_sha256(np.array([1.0, 2.0, 3.0]))

    assert len(h) == 64 and h == h.lower()
    assert h == voxel_sha256(np.array([1.0, 2.0, 3.0]))
