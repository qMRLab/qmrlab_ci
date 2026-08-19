import numpy as np

from scripts.derive_masks import finite_positive_mask


def test_voxel_must_be_positive_in_every_volume():
    a = np.array([1.0, 1.0, 1.0])
    b = np.array([1.0, 0.0, 1.0])

    np.testing.assert_array_equal(finite_positive_mask([a, b]), [1, 0, 1])


def test_nonfinite_voxels_are_excluded():
    a = np.array([1.0, np.nan, np.inf])

    np.testing.assert_array_equal(finite_positive_mask([a]), [1, 0, 0])


def test_negative_values_are_excluded():
    np.testing.assert_array_equal(finite_positive_mask([np.array([-1.0, 2.0])]), [0, 1])


def test_mask_is_uint8_so_it_round_trips_through_nifti():
    assert finite_positive_mask([np.array([1.0])]).dtype == np.uint8


def test_mask_bytes_are_reproducible(tmp_path):
    """masks/*.nii.gz are committed and masks/README.md invites a reviewer to
    regenerate and diff them, so two writes of the same mask must be byte-identical."""
    import numpy as np
    from scripts.derive_masks import write_mask_nifti

    a, b = tmp_path / "a.nii.gz", tmp_path / "b.nii.gz"
    mask = np.array([1, 0, 1, 1], dtype=np.uint8)
    write_mask_nifti(a, mask, (4,))
    write_mask_nifti(b, mask, (4,))

    assert a.read_bytes() == b.read_bytes()
