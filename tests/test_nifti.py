import numpy as np

from harness.measure import masked_stats
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


def test_nan_slope_means_no_scaling(tmp_path):
    """ITK writes NaN, not zero, for "no scaling" -- so every map QUIT produces
    arrives this way. NaN fails the spec's `== 0` test for "unset", so it has to be
    caught as non-finite or the transform turns every voxel into NaN."""
    p = tmp_path / "m.nii.gz"
    write_nifti(p, [3.0, 4.0], shape=(2,), scl_slope=float("nan"), scl_inter=float("nan"))

    np.testing.assert_allclose(read_nifti(p).values, [3.0, 4.0])


def test_infinite_slope_disables_the_intercept_too(tmp_path):
    """An infinite slope is unset for the same reason a NaN one is, and like a zero
    slope it disables the whole transform -- the intercept included."""
    p = tmp_path / "m.nii.gz"
    write_nifti(p, [3.0, 4.0], shape=(2,), scl_slope=float("inf"), scl_inter=5.0)

    np.testing.assert_allclose(read_nifti(p).values, [3.0, 4.0])


def test_nan_slope_does_not_silently_empty_the_statistics(tmp_path):
    """The regression that motivated the isfinite guard: an all-NaN map raises
    nothing anywhere. The record still validates as 'ok' and masked_stats just
    reports n=0 with None for every statistic, so a QUIT target would have scored
    as a clean run that measured nothing."""
    p = tmp_path / "m.nii.gz"
    write_nifti(p, [1.0, 2.0, 3.0, 4.0], shape=(4,),
                scl_slope=float("nan"), scl_inter=float("nan"))

    stats = masked_stats(read_nifti(p).values, np.ones(4))

    assert stats["n"] == 4
    assert stats["n_nonfinite"] == 0
    assert stats["mean"] == 2.5
