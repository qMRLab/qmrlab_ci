import numpy as np

from harness.nifti import read_nifti
from tests.helpers import write_nifti


def test_reads_float32_values_and_shape(tmp_path):
    p = tmp_path / "m.nii.gz"
    write_nifti(p, [1.0, 2.0, 3.0, 4.0], shape=(2, 2))

    img = read_nifti(p)

    assert img.shape == (2, 2)
    assert img.datatype == 16
    np.testing.assert_allclose(img.values, [1.0, 2.0, 3.0, 4.0])


def test_applies_scl_slope_and_inter(tmp_path):
    p = tmp_path / "m.nii.gz"
    write_nifti(p, [1, 2, 3, 4], shape=(4,), datatype=4, scl_slope=0.5, scl_inter=10.0)

    np.testing.assert_allclose(read_nifti(p).values, [10.5, 11.0, 11.5, 12.0])


def test_zero_slope_means_no_scaling(tmp_path):
    """The NIfTI spec says an unset (zero) slope is identity, not a multiply by zero."""
    p = tmp_path / "m.nii.gz"
    write_nifti(p, [3.0, 4.0], shape=(2,), scl_slope=0.0, scl_inter=0.0)

    np.testing.assert_allclose(read_nifti(p).values, [3.0, 4.0])


def test_zero_slope_disables_the_intercept_too(tmp_path):
    """A zero slope disables the whole transform. Applying the intercept anyway would
    mean multiplying the data by zero, which is precisely what the spec forbids."""
    p = tmp_path / "m.nii.gz"
    write_nifti(p, [3.0, 4.0], shape=(2,), scl_slope=0.0, scl_inter=5.0)

    np.testing.assert_allclose(read_nifti(p).values, [3.0, 4.0])
