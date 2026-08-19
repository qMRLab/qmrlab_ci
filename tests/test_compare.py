import numpy as np

from harness.compare import compare_maps

ALL = np.array([1, 1, 1, 1])


def test_identical_maps_agree_completely():
    v = np.array([1.0, 2.0, 3.0, 4.0])

    c = compare_maps(v, v, ALL)

    assert c["n"] == 4
    assert c["frac_within"] == 1.0
    assert c["mean_delta"] == 0.0
    assert c["max_abs_delta"] == 0.0
    assert c["pearson_r"] == 1.0


def test_fraction_within_tolerance_is_relative_to_the_reference():
    a = np.array([100.0, 100.0, 100.0, 200.0])
    b = np.array([100.5, 105.0, 100.0, 200.0])

    c = compare_maps(a, b, ALL, rel_tol=0.01)

    assert c["frac_within"] == 0.75


def test_nonfinite_voxels_are_excluded_pairwise():
    a = np.array([1.0, np.nan, 3.0, 4.0])
    b = np.array([1.0, 2.0, np.inf, 4.0])

    c = compare_maps(a, b, ALL)

    assert c["n"] == 2


def test_mean_delta_is_signed_so_direction_is_visible():
    c = compare_maps(np.array([2.0, 2.0]), np.array([1.0, 1.0]), np.array([1, 1]))

    assert c["mean_delta"] == 1.0


def test_no_comparable_voxels_reports_none_rather_than_raising():
    c = compare_maps(np.array([1.0]), np.array([np.nan]), np.array([1]))

    assert c["n"] == 0
    assert c["pearson_r"] is None
