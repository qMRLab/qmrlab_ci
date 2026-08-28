import numpy as np
import pytest

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


# --- rel_median_diff, the headline (spec §7) -----------------------------------------

def test_relative_median_difference_reads_as_a_sentence():
    """Spec §7 wants "QUIT reads 10% higher T1" to be readable straight off the number."""
    y = np.array([10.0, 20.0, 30.0, 40.0])

    c = compare_maps(1.1 * y, y, ALL)

    assert c["rel_median_diff"] == pytest.approx(0.1)


def test_relative_median_difference_is_signed_towards_the_reference():
    y = np.array([10.0, 20.0, 30.0, 40.0])

    c = compare_maps(0.9 * y, y, ALL)

    assert c["rel_median_diff"] == pytest.approx(-0.1)


def test_relative_median_difference_survives_an_outlier_that_moves_the_mean():
    """The reason it is the headline and mean_delta is not."""
    y = np.array([10.0, 10.0, 10.0, 10.0])
    a = np.array([10.0, 10.0, 10.0, 1e6])

    c = compare_maps(a, y, ALL)

    assert c["rel_median_diff"] == 0.0
    assert c["mean_delta"] > 1e5


def test_a_zero_median_reference_makes_the_relative_difference_unmeasurable():
    """Same trap as frac_within one level up: a relative measure around zero has no
    meaning, so it reports nothing rather than dividing by it. Everything that does not
    depend on the division still reports."""
    a = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
    b = np.array([0.0, 0.0, 0.0, 1.0, 2.0])

    c = compare_maps(a, b, np.ones(5))

    assert c["rel_median_diff"] is None
    assert c["n"] == 5
    assert c["median_delta"] == 1.0


# --- Lin's CCC (spec §7) -------------------------------------------------------------

def _bias_correction(x, y):
    """Lin's C_b, from population moments, computed independently of compare_maps."""
    sx, sy = x.std(), y.std()
    return 2 * sx * sy / (sx**2 + sy**2 + (x.mean() - y.mean()) ** 2)


def test_ccc_is_pearson_r_times_the_bias_correction_factor():
    """The decomposition is the reason both columns are published: CCC = r * C_b."""
    x = np.array([1.0, 2.0, 3.0, 4.0])
    y = np.array([1.0, 2.2, 2.9, 5.0])

    c = compare_maps(x, y, ALL)

    assert c["ccc"] == pytest.approx(c["pearson_r"] * _bias_correction(x, y))


def test_ccc_is_one_for_identical_maps():
    v = np.array([1.0, 2.0, 3.0, 4.0])

    assert compare_maps(v, v, ALL)["ccc"] == pytest.approx(1.0)


def test_high_correlation_with_low_ccc_is_the_diagnostic_case():
    """Spec §7: a constant offset ranks every voxel identically and calibrates nothing
    like it. pearson_r alone would call this perfect agreement."""
    y = np.array([1.0, 2.0, 3.0, 4.0])

    c = compare_maps(y + 10.0, y, ALL)

    assert c["pearson_r"] == pytest.approx(1.0)
    assert c["ccc"] < 0.05


def test_ccc_uses_population_moments_like_masked_stats():
    """ddof=0, so that the published CCC really is r * C_b of the published r. On four
    voxels the sample-moment version differs in the third decimal — enough to move a cell
    across the 0.95 amber line."""
    x = np.array([1.0, 2.0, 3.0, 4.0])
    y = np.array([1.4, 2.0, 3.0, 3.4])

    c = compare_maps(x, y, ALL)

    population = 2 * ((x - x.mean()) * (y - y.mean())).mean() / (
        x.var(ddof=0) + y.var(ddof=0) + (x.mean() - y.mean()) ** 2
    )
    sample = 2 * ((x - x.mean()) * (y - y.mean())).sum() / 3 / (
        x.var(ddof=1) + y.var(ddof=1) + (x.mean() - y.mean()) ** 2
    )

    assert c["ccc"] == pytest.approx(population)
    assert c["ccc"] != pytest.approx(sample)


def test_a_single_voxel_has_no_concordance_to_report():
    """Degenerate exactly like pearson_r: the formula still returns a number from the
    mean offset alone, and that number would be published as agreement."""
    c = compare_maps(np.array([1.0, 2.0]), np.array([5.0, np.nan]), np.array([1, 1]))

    assert c["n"] == 1
    assert c["ccc"] is None
    assert c["pearson_r"] is None


def test_two_constant_maps_have_no_variance_to_concord():
    c = compare_maps(np.array([2.0, 2.0]), np.array([2.0, 2.0]), np.array([1, 1]))

    assert c["ccc"] is None


def test_no_comparable_voxels_reports_none_for_the_new_measures_too():
    """analyze.py spreads this dict with **, so both branches must carry both keys."""
    c = compare_maps(np.array([1.0]), np.array([np.nan]), np.array([1]))

    assert c["rel_median_diff"] is None
    assert c["ccc"] is None
    assert c["scale_ratio_not_a_disagreement"] is None


# --- scale-free maps (spec §7) -------------------------------------------------------

def test_normalisation_is_off_by_default_so_a_real_ratio_keeps_its_offset():
    """The rule that makes this a per-unit flag: b1_afi's B1map is a genuine ratio where
    1.0 means nominal, and normalising a 10% offset away there would delete the finding."""
    y = np.array([1.0, 1.0, 1.0, 1.0])

    c = compare_maps(1.1 * y, y, ALL)

    assert c["scale_free"] is False
    assert c["scale_ratio_not_a_disagreement"] is None
    assert c["rel_median_diff"] == pytest.approx(0.1)


def test_a_free_amplitude_scale_stops_being_a_disagreement_when_asked():
    """vfa_t1/M0 and mono_t2/M0 are 'au': the amplitude is arbitrary, so two softwares
    that agree up to a factor agree."""
    y = np.array([1.0, 2.0, 3.0, 4.0])

    c = compare_maps(3.0 * y, y, ALL, scale_free=True)

    assert c["rel_median_diff"] == pytest.approx(0.0)
    assert c["ccc"] == pytest.approx(1.0)
    assert c["frac_within"] == 1.0


def test_the_recovered_scale_is_reported_and_named_as_not_a_disagreement():
    y = np.array([1.0, 2.0, 3.0, 4.0])

    c = compare_maps(3.0 * y, y, ALL, scale_free=True)

    assert c["scale_free"] is True
    assert c["scale_ratio_not_a_disagreement"] == pytest.approx(3.0)


def test_normalising_does_not_hide_a_shape_difference():
    """It removes the amplitude and nothing else — the point of doing it per unit."""
    y = np.array([1.0, 1.0, 1.0, 1.0])
    a = np.array([1.0, 1.0, 1.0, 4.0])

    c = compare_maps(a, y, ALL, scale_free=True)

    assert c["max_abs_delta"] == pytest.approx(3.0)
    assert c["ccc"] is not None


def test_a_zero_median_leaves_nothing_to_normalise_by():
    """0/0 would publish nan in a column everything downstream reads as a measurement."""
    a = np.array([1.0, 2.0, 3.0, 4.0])
    b = np.array([-2.0, 0.0, 0.0, 2.0])

    c = compare_maps(a, b, ALL, scale_free=True)

    assert c["n"] == 4
    assert c["rel_median_diff"] is None
    assert c["ccc"] is None
    assert c["scale_ratio_not_a_disagreement"] is None
    # Unmeasurable only because of the normalisation: the same voxels compare fine
    # without it, so the None is the guard talking and not the data.
    assert compare_maps(a, b, ALL)["rel_median_diff"] is not None


def test_existing_keys_are_untouched_by_the_new_ones():
    """analyze.py and site.py read the originals by name; adding measures must not move
    or drop one of them."""
    v = np.array([1.0, 2.0, 3.0, 4.0])

    keys = set(compare_maps(v, v, ALL))

    assert {
        "n", "frac_within", "pearson_r", "mean_delta", "median_delta", "max_abs_delta"
    } <= keys
    assert set(compare_maps(np.array([1.0]), np.array([np.nan]), np.array([1]))) == keys
