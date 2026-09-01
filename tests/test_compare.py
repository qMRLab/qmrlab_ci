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


# --- the scale-free range (spec §7) --------------------------------------------------

def test_a_diverged_amplitude_stops_deciding_the_statistics_for_every_other_voxel():
    """The measured failure, in miniature. On the published mono_t2/M0 maps two voxels
    of 27,417 reach 219x their map's median and take r from 0.877 to 0.333 and CCC from
    0.861 to 0.129 — while the relative median difference reads -0.3%. Normalising does
    not help: r and CCC are variance-based, so the outlier survives the division by the
    median and then dominates the variance it lands in."""
    y = np.concatenate([np.linspace(0.5, 1.5, 40), [1.0]])
    a = y.copy()
    a[-1] = 219.0
    mask = np.ones(y.size)

    loose = compare_maps(a, y, mask, scale_free=True)
    bounded = compare_maps(a, y, mask, scale_free=True, scale_free_range=(0.0, 10.0))

    assert loose["pearson_r"] < 0.2
    assert loose["ccc"] < 0.2
    assert bounded["pearson_r"] > 0.999
    assert bounded["ccc"] > 0.99
    assert bounded["n"] == 40
    assert bounded["n_out_of_range"] == 1
    # Not perfect agreement, and deliberately not asserted as such: dropping the voxel
    # does not put it back in the median the two maps were normalised by, exactly as on
    # the real pair where the recovered scale ratio is 1.003 rather than 1.
    assert bounded["scale_ratio_not_a_disagreement"] != 1.0


def test_the_bound_is_read_in_median_normalised_units_not_in_the_produced_ones():
    """The entire reason the field is separate from comparison_range. These voxels are
    thousands in whatever unit the software wrote, and 0.5 to 1.5 in multiples of their
    own median, so a bound of 10 excludes none of them."""
    y = np.linspace(500.0, 1500.0, 40)

    c = compare_maps(y, y, np.ones(y.size), scale_free=True, scale_free_range=(0.0, 10.0))

    assert c["n"] == 40
    assert c["n_out_of_range"] == 0


def test_both_sides_must_be_inside_exactly_as_a_physical_range_requires():
    """One implementation's 219x-the-median amplitude is not comparable to the other's
    1.0 whichever side produced it — the voxel is a diverged fit either way."""
    y = np.ones(9)
    a = np.concatenate([np.ones(8), [219.0]])

    c = compare_maps(a, y, np.ones(9), scale_free=True, scale_free_range=(0.0, 10.0))
    flipped = compare_maps(y, a, np.ones(9), scale_free=True,
                           scale_free_range=(0.0, 10.0))

    assert c["n"] == flipped["n"] == 8
    assert c["n_out_of_range"] == flipped["n_out_of_range"] == 1


def test_the_medians_come_from_the_whole_selection_so_the_range_cannot_move_them():
    """Order is the design. If the range narrowed the maps before the medians were
    taken, the normalisation would depend on a bound that depends on the normalisation,
    and the published scale ratio would be measured over a selection it did not
    describe. Here the outlier does not shift the median, and the ratio stays exactly
    the 2.0 the two maps differ by."""
    y = np.concatenate([np.linspace(0.5, 1.5, 40), [50.0]])
    a = 2.0 * y

    c = compare_maps(a, y, np.ones(y.size), scale_free=True,
                     scale_free_range=(0.0, 10.0))

    assert c["scale_ratio_not_a_disagreement"] == pytest.approx(2.0)
    assert c["n_out_of_range"] == 1


def test_a_normalised_bound_without_normalisation_raises_rather_than_thresholding():
    """It would compare PHYSICAL values against bounds meant for multiples of a median
    — on a T1 in seconds, "keep 0 to 10" would look entirely plausible and mean
    something else. A caller bug, so it fails loudly at the call rather than on the
    site."""
    v = np.array([1.0, 2.0, 3.0, 4.0])

    with pytest.raises(ValueError, match="masked median"):
        compare_maps(v, v, ALL, scale_free_range=(0.0, 10.0))


def test_a_range_that_empties_the_comparison_still_reports_what_it_removed():
    """"No comparable voxels" and "a range removed all of them" are different findings
    and must not render as the same one."""
    y = np.concatenate([np.full(4, 1.0), np.full(4, 1000.0)])
    a = y.copy()

    c = compare_maps(a, y, np.ones(8), scale_free=True, scale_free_range=(50.0, 100.0))

    assert c["n"] == 0
    assert c["n_out_of_range"] == 8
    assert c["ccc"] is None
    assert c["scale_ratio_not_a_disagreement"] == pytest.approx(1.0)


def test_every_row_carries_the_exclusion_count_whether_a_range_applied_or_not():
    """_unmeasurable's rule: rows of two different shapes move the failure into
    whichever renderer reads the short one."""
    v = np.array([1.0, 2.0, 3.0, 4.0])

    assert compare_maps(v, v, ALL)["n_out_of_range"] == 0
    assert compare_maps(v, v, ALL, scale_free=True)["n_out_of_range"] == 0
    assert compare_maps(np.array([1.0]), np.array([np.nan]),
                        np.array([1]))["n_out_of_range"] == 0
