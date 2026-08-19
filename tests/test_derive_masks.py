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


def test_find_ignores_fitresults_shadow(tmp_path):
    """FitResults/ holds qMRLab's own fitted output. A mask derived from a fitted map
    would be a function of the thing being measured -- and 'FitResults/X' sorts before
    'X', so a naive first-hit would pick the shadow every time."""
    from scripts.derive_masks import _find

    ds = tmp_path / "ir"
    (ds / "FitResults").mkdir(parents=True)
    (ds / "Mask.mat").write_bytes(b"input")
    (ds / "FitResults" / "Mask.mat").write_bytes(b"fitted output")

    assert _find(tmp_path, "ir", "Mask.mat").read_bytes() == b"input"


def test_find_raises_when_a_name_is_ambiguous(tmp_path):
    """No ordering rule here is right by construction, so guessing is worse than failing."""
    import pytest
    from scripts.derive_masks import _find

    ds = tmp_path / "ir"
    (ds / "a").mkdir(parents=True)
    (ds / "b").mkdir(parents=True)
    (ds / "a" / "Mask.mat").write_bytes(b"one")
    (ds / "b" / "Mask.mat").write_bytes(b"two")

    with pytest.raises(ValueError, match="ambiguous"):
        _find(tmp_path, "ir", "Mask.mat")


def test_find_raises_when_the_input_is_missing(tmp_path):
    import pytest
    from scripts.derive_masks import _find

    (tmp_path / "ir").mkdir()

    with pytest.raises(FileNotFoundError, match="Mask.mat"):
        _find(tmp_path, "ir", "Mask.mat")
