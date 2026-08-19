import numpy as np

from harness.measure import masked_stats


def test_statistics_use_only_masked_voxels():
    values = np.array([1.0, 2.0, 3.0, 1000.0])
    mask = np.array([1, 1, 1, 0])

    s = masked_stats(values, mask)

    assert s["n"] == 3
    assert s["mean"] == 2.0
    assert s["median"] == 2.0
    assert s["max"] == 3.0


def test_scale_expresses_statistics_in_canonical_units():
    """qMRLab reports T2 in ms, the catalog's canonical unit is seconds."""
    s = masked_stats(np.array([1000.0, 2000.0]), np.array([1, 1]), scale=0.001)

    assert s["mean"] == 1.5
    assert s["min"] == 1.0


def test_nonfinite_voxels_are_counted_and_excluded():
    values = np.array([1.0, np.nan, np.inf, 3.0])
    mask = np.array([1, 1, 1, 1])

    s = masked_stats(values, mask)

    assert s["n"] == 2
    assert s["n_nonfinite"] == 2
    assert s["mean"] == 2.0


def test_zero_voxels_are_counted_but_still_included():
    """Zeros are a real fit outcome (b1_afi pins unphysical ratios to 0), not absence."""
    s = masked_stats(np.array([0.0, 2.0]), np.array([1, 1]))

    assert s["n"] == 2
    assert s["n_zero"] == 1
    assert s["mean"] == 1.0


def test_empty_mask_yields_zero_count_and_none_statistics():
    s = masked_stats(np.array([1.0, 2.0]), np.array([0, 0]))

    assert s["n"] == 0
    assert s["mean"] is None
