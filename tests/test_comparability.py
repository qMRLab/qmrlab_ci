"""The declaration layer: what may be compared, and what a colour is allowed to mean.

Spec §5.5, §7 and §7.3. Almost everything is written against a synthetic
comparability.yml, for test_config.py's reason — asserting what the committed file says
today would only hold until the next entry lands. The exceptions are the two claims the
committed file exists to make, which are asserted against the file itself.
"""
import itertools
import pathlib

import pytest
import yaml

from harness.comparability import (
    DEFAULT_THRESHOLDS,
    Comparability,
    Thresholds,
    comparability_for,
    flag_for,
    load_comparability,
)
from harness.config import ConfigError

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _entry(**doc):
    return {
        "model": "m", "maps": ["T1"], "pairs": [["alpha", "beta"]],
        "class": "same-estimator", **doc,
    }


def _load(tmp_path, *entries):
    """Write one comparability.yml and load it."""
    (tmp_path / "comparability.yml").write_text(
        yaml.safe_dump({"entries": [_entry(**e) for e in entries]})
    )
    return load_comparability(tmp_path)


def _lookup(entries, *, model="m", map_name="T1", a="alpha@1", b="beta@1"):
    return comparability_for(
        entries, model, map_name,
        a_target=a, a_software=a.split("@")[0],
        b_target=b, b_software=b.split("@")[0],
    )


def _same_estimator(**kw):
    doc = {
        "model": "m", "map_name": "T1", "members": ("alpha", "beta"),
        "estimator_class": "same-estimator", "reason": None,
        "input_domain": "satisfied", "input_domain_reason": None, **kw,
    }
    return Comparability(**doc)


# --- the loader, as strict as config.py (spec §5.5) ----------------------------------

def test_an_unknown_class_is_a_config_error_naming_the_entry(tmp_path):
    with pytest.raises(ConfigError, match=r"entries\[0\].*class.*'probably-fine'"):
        _load(tmp_path, {"class": "probably-fine"})


def test_a_related_estimator_entry_without_a_reason_is_refused(tmp_path):
    """The reason is rendered as visible text on the site. Without it the entry is a bare
    colour a reader can neither check nor argue with — a silent downgrade, not a default."""
    with pytest.raises(ConfigError, match=r"entries\[0\].*requires a reason"):
        _load(tmp_path, {"class": "related-estimator"})


def test_an_incomparable_entry_without_a_reason_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="requires a reason"):
        _load(tmp_path, {"class": "incomparable"})


def test_a_blank_reason_is_refused_like_a_missing_one(tmp_path):
    with pytest.raises(ConfigError, match="reason must be non-empty"):
        _load(tmp_path, {"class": "related-estimator", "reason": "   "})


def test_a_same_estimator_entry_needs_no_reason(tmp_path):
    """It claims nothing beyond the default, so there is nothing to justify."""
    entries = _load(tmp_path, {})

    assert entries[0].estimator_class == "same-estimator"
    assert entries[0].reason is None


def test_an_unknown_input_domain_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match=r"input_domain.*'unchecked'"):
        _load(tmp_path, {"input_domain": "unchecked"})


def test_a_violated_input_domain_without_its_own_reason_is_refused(tmp_path):
    """Spec §7.3 requires the flag to name whose requirement is broken and how."""
    with pytest.raises(ConfigError, match="requires an input_domain_reason"):
        _load(tmp_path, {"input_domain": "violated"})


def test_a_violated_input_domain_on_an_incomparable_entry_is_a_contradiction(tmp_path):
    """One of the two lines is a mistake: an incomparable pair is never built, so the red
    flag the field asks for could never be rendered."""
    with pytest.raises(ConfigError, match="never runs"):
        _load(tmp_path, {
            "class": "incomparable", "reason": "no",
            "input_domain": "violated", "input_domain_reason": "magnitude data",
        })


def test_maps_and_pairs_are_expanded_into_one_entry_each(tmp_path):
    entries = _load(tmp_path, {
        "maps": ["T1", "M0"], "pairs": [["alpha", "beta"], ["alpha", "gamma"]],
    })

    assert len(entries) == 4
    assert {(e.map_name, e.members) for e in entries} == {
        ("T1", ("alpha", "beta")), ("T1", ("alpha", "gamma")),
        ("M0", ("alpha", "beta")), ("M0", ("alpha", "gamma")),
    }


def test_a_pair_is_stored_sorted_so_lookup_order_cannot_miss_it(tmp_path):
    entries = _load(tmp_path, {"pairs": [["quit", "alpha"]]})

    assert entries[0].members == ("alpha", "quit")


def test_a_declaration_repeated_for_the_same_slot_is_refused(tmp_path):
    """Two classes for one cell would make the site's flag depend on file order."""
    with pytest.raises(ConfigError, match="duplicate declaration for m/T1"):
        _load(tmp_path, {}, {"pairs": [["beta", "alpha"]]})


def test_a_pair_that_does_not_name_two_sides_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="exactly two sides"):
        _load(tmp_path, {"pairs": [["alpha"]]})


def test_a_pair_against_itself_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="on both sides"):
        _load(tmp_path, {"pairs": [["alpha", "alpha"]]})


def test_a_missing_field_is_a_config_error_not_a_keyerror(tmp_path):
    (tmp_path / "comparability.yml").write_text(
        yaml.safe_dump(
            {"entries": [{"model": "m", "maps": ["T1"], "class": "same-estimator"}]}
        )
    )

    with pytest.raises(ConfigError, match=r"entries\[0\].*'pairs'"):
        load_comparability(tmp_path)


def test_an_absent_file_declares_nothing_rather_than_failing(tmp_path):
    """Nothing declared is the state the repo ran in for fourteen qMRLab targets."""
    assert load_comparability(tmp_path) == ()


# --- lookup (spec §5.5, §2.2) --------------------------------------------------------

def test_an_undeclared_pair_is_same_estimator(tmp_path):
    """Making the safe-looking class the default would silence red everywhere by saying
    nothing, so silence has to mean the class that CAN go red."""
    entry = _lookup(load_comparability(tmp_path))

    assert entry.estimator_class == "same-estimator"
    assert entry.input_domain == "satisfied"
    assert entry.comparable


def test_a_software_level_declaration_matches_every_target_of_that_software(tmp_path):
    entries = _load(tmp_path, {"class": "related-estimator", "reason": "different fit"})

    assert _lookup(entries, a="alpha@9").reason == "different fit"
    assert _lookup(entries, a="alpha@1", b="beta@2").reason == "different fit"


def test_lookup_is_order_insensitive(tmp_path):
    """The class is a property of the two implementations, not of which one analyze
    picked as the reference — spec §5.6 fixes the orientation separately."""
    entries = _load(tmp_path, {"class": "related-estimator", "reason": "different fit"})

    assert _lookup(entries, a="beta@1", b="alpha@1").reason == "different fit"


def test_a_declaration_for_one_target_does_not_paint_its_siblings(tmp_path):
    """Spec §2.2: qmrlab@V1 ignores the B1 map for Ramani and the other thirteen targets
    do not. Painting them all would hide the version drift the benchmark measures."""
    entries = _load(tmp_path, {
        "pairs": [["alpha@1", "beta"]],
        "class": "related-estimator", "reason": "era-1 only",
    })

    assert _lookup(entries, a="alpha@1").reason == "era-1 only"
    assert _lookup(entries, a="alpha@2").reason is None


def test_the_more_specific_declaration_wins(tmp_path):
    entries = _load(tmp_path,
        {"class": "related-estimator", "reason": "software wide"},
        {"pairs": [["alpha@1", "beta"]], "class": "related-estimator",
         "reason": "this target only"},
    )

    assert _lookup(entries, a="alpha@1").reason == "this target only"
    assert _lookup(entries, a="alpha@2").reason == "software wide"


def test_two_declarations_of_equal_specificity_refuse_to_be_guessed(tmp_path):
    """Picking one would make the flag depend on file order; the file has to say which."""
    entries = _load(tmp_path,
        {"pairs": [["alpha@1", "beta"]], "class": "related-estimator", "reason": "one"},
        {"pairs": [["alpha", "beta@1"]], "class": "related-estimator", "reason": "two"},
    )

    with pytest.raises(ConfigError, match="matched equally"):
        _lookup(entries, a="alpha@1", b="beta@1")


def test_a_target_id_is_matched_against_the_declared_software_not_its_prefix(tmp_path):
    """target.yml owns which software a target is; inferring it from the text before '@'
    would be a second source of truth for it."""
    entries = _load(tmp_path, {"class": "related-estimator", "reason": "different fit"})

    entry = comparability_for(
        entries, "m", "T1",
        a_target="renamed-id", a_software="alpha",
        b_target="beta@1", b_software="beta",
    )

    assert entry.reason == "different fit"


def test_a_declaration_for_another_map_does_not_leak(tmp_path):
    entries = _load(tmp_path, {"class": "related-estimator", "reason": "T1 only"})

    assert _lookup(entries, map_name="M0").estimator_class == "same-estimator"


# --- the flag (spec §7) --------------------------------------------------------------

def test_same_estimator_agreement_is_green():
    flag = flag_for(_same_estimator(), rel_median_diff=0.01, ccc=0.99)

    assert flag.colour == "green"
    assert "1%" in flag.reason and "0.990" in flag.reason


def test_same_estimator_goes_amber_above_five_percent():
    flag = flag_for(_same_estimator(), rel_median_diff=-0.06, ccc=0.99)

    assert flag.colour == "amber"
    assert "-6%" in flag.reason


def test_same_estimator_goes_red_above_ten_percent():
    flag = flag_for(_same_estimator(), rel_median_diff=0.11, ccc=0.99)

    assert flag.colour == "red"
    assert "+11%" in flag.reason


def test_the_thresholds_are_exclusive_so_a_cell_exactly_on_one_stays_below_it():
    assert flag_for(_same_estimator(), rel_median_diff=0.05, ccc=1.0).colour == "green"
    assert flag_for(_same_estimator(), rel_median_diff=0.10, ccc=1.0).colour == "amber"


def test_a_low_ccc_alone_earns_the_flag():
    """The diagnostic case: voxels ranked identically, calibrated differently, so the
    headline difference can sit at zero while the pair does not agree."""
    assert flag_for(_same_estimator(), rel_median_diff=0.0, ccc=0.94).colour == "amber"
    assert flag_for(_same_estimator(), rel_median_diff=0.0, ccc=0.89).colour == "red"


def test_the_worse_of_the_two_measures_decides():
    flag = flag_for(_same_estimator(), rel_median_diff=0.06, ccc=0.10)

    assert flag.colour == "red"


def test_an_unmeasurable_pair_is_amber_and_never_green():
    """Green is a measured agreement. An absent measure has measured nothing, and
    painting it green publishes an unmeasured cell as a passing one."""
    flag = flag_for(_same_estimator(), rel_median_diff=None, ccc=None)

    assert flag.colour == "amber"
    assert "could not be computed" in flag.reason


def test_a_missing_measure_does_not_hide_a_red_from_the_other_one():
    flag = flag_for(_same_estimator(), rel_median_diff=None, ccc=0.4)

    assert flag.colour == "red"


def test_thresholds_are_a_parameter_so_models_can_declare_their_own():
    """Spec §7 puts them in models/*.yml rather than in Python; the rule does not move
    when the numbers do."""
    strict = Thresholds(
        amber_rel_median_diff=0.001, red_rel_median_diff=0.002,
        amber_ccc=0.999, red_ccc=0.998,
    )

    assert flag_for(_same_estimator(), rel_median_diff=0.01, ccc=1.0).colour == "green"
    assert flag_for(
        _same_estimator(), rel_median_diff=0.01, ccc=1.0, thresholds=strict
    ).colour == "red"


def test_related_estimator_is_amber_with_its_declared_cause():
    entry = _same_estimator(estimator_class="related-estimator", reason="log-linear")

    flag = flag_for(entry, rel_median_diff=0.0, ccc=1.0)

    assert flag.colour == "amber"
    assert flag.reason == "log-linear"


def test_related_estimator_can_never_go_red_whatever_the_numbers():
    """The core rule of spec §7. Red on a different estimator would report a modelling
    difference as an implementation defect, which spec §1 calls worse than no benchmark."""
    entry = _same_estimator(estimator_class="related-estimator", reason="different fit")
    extremes = [None, 0.0, 0.049, 0.05, 0.1, 0.11, -0.999, 12.0, 1e9, -1e9]
    cccs = [None, 1.0, 0.95, 0.9, 0.899, 0.0, -1.0, -1e9]

    for rmd, ccc in itertools.product(extremes, cccs):
        flag = flag_for(entry, rel_median_diff=rmd, ccc=ccc)
        assert flag.colour == "amber", f"rmd={rmd} ccc={ccc} produced {flag.colour}"
        assert flag.reason == "different fit"


def test_related_estimator_stays_amber_under_any_thresholds():
    """Not even a per-model declaration may open a route to red for it."""
    entry = _same_estimator(estimator_class="related-estimator", reason="different fit")
    absurd = Thresholds(
        amber_rel_median_diff=0.0, red_rel_median_diff=0.0, amber_ccc=2.0, red_ccc=2.0
    )

    assert flag_for(
        entry, rel_median_diff=0.0, ccc=1.0, thresholds=absurd
    ).colour == "amber"


def test_an_incomparable_pair_has_no_flag_because_it_has_no_pair():
    """Spec §5.5 says do not run it. Reaching here means a pair exists that the file says
    should not, and a plausible-looking colour would hide that."""
    entry = _same_estimator(estimator_class="incomparable", reason="different sequence")

    assert not entry.comparable
    with pytest.raises(ValueError, match="declared incomparable"):
        flag_for(entry, rel_median_diff=0.0, ccc=1.0)


def test_an_input_domain_violation_is_red_whatever_the_class_and_the_numbers():
    """Spec §7.3: amber means "expected to differ" and would understate a tool being fed
    data its documented model cannot represent."""
    for estimator_class in ("same-estimator", "related-estimator"):
        entry = _same_estimator(
            estimator_class=estimator_class,
            reason="different fit",
            input_domain="violated",
            input_domain_reason="magnitude data, no polarity restoration",
        )

        flag = flag_for(entry, rel_median_diff=0.0, ccc=1.0)

        assert flag.colour == "red"
        assert flag.reason == "magnitude data, no polarity restoration"


def test_a_flag_decided_by_declaration_refuses_to_render_without_its_text():
    """The loader already refuses to build one. Checked again where the colour is made,
    because that is the one place the omission would survive as a bare colour."""
    entry = _same_estimator(estimator_class="related-estimator", reason="")

    with pytest.raises(ValueError, match="reason is required"):
        flag_for(entry, rel_median_diff=0.0, ccc=1.0)


def test_a_declared_reason_on_a_same_estimator_cell_travels_with_the_numbers():
    entry = _same_estimator(reason="settings aligned with --algo=l")

    flag = flag_for(entry, rel_median_diff=0.2, ccc=0.5)

    assert flag.colour == "red"
    assert "settings aligned with --algo=l" in flag.reason


# --- the committed file (spec §6.3, §7.3) --------------------------------------------

def test_the_committed_declarations_load():
    assert load_comparability(ROOT)


def test_every_committed_declaration_can_state_its_case():
    """Nothing in the file may reach the site as a bare colour."""
    for entry in load_comparability(ROOT):
        assert entry.reason, f"{entry.model}/{entry.map_name} {entry.members}"
        if entry.input_domain == "violated":
            assert entry.input_domain_reason


def test_quit_qmt_cannot_go_red_however_far_its_kr_is_from_qmrlabs():
    """Spec §6.3 measured kr +31.8% from the lineshape alone. Under the default
    thresholds that is red three times over, and it would be reporting a declared
    modelling difference as a defect."""
    entry = comparability_for(
        load_comparability(ROOT), "qmt_spgr_ramani", "kr",
        a_target="qmrlab@v3.0.0", a_software="qmrlab",
        b_target="quit@v3.4", b_software="quit",
    )

    flag = flag_for(entry, rel_median_diff=0.318, ccc=0.2)

    assert entry.estimator_class == "related-estimator"
    assert flag.colour == "amber"
    assert "1500 Hz" in flag.reason


def test_qi_irtse_on_magnitude_data_is_red_even_when_the_numbers_agree():
    """The worked input-domain case of spec §7.3, and the reason the field is orthogonal
    to the estimator class: this entry is related-estimator, which can never go red."""
    entry = comparability_for(
        load_comparability(ROOT), "inversion_recovery", "T1",
        a_target="qmrust@main", a_software="qmrust",
        b_target="quit@v3.4", b_software="quit",
    )

    flag = flag_for(entry, rel_median_diff=0.0, ccc=1.0, thresholds=DEFAULT_THRESHOLDS)

    assert entry.estimator_class == "related-estimator"
    assert entry.input_domain == "violated"
    assert flag.colour == "red"
    assert "abs()" in flag.reason


def test_the_shipped_mt_sat_declaration_covers_the_two_clipped_maps():
    """MTsat and T1 both carry SCT's hardcoded clips; MTR does not.

    Measured 2026-08-28 against osf-data/mtsat: SCT clips R1 < 0.01 to T1 = 0 and zeroes
    |MTsat| > 1, which is 100% of the T1 disagreement and most of the MTsat one. MTR comes
    from a separate sct_compute_mtr call, agrees at ccc = 1.0 and frac_within = 1.0, and
    must therefore stay red-assignable — a disagreement there would be a real finding.
    """
    entries = load_comparability(ROOT)
    lookup = dict(a_target="qmrlab@v3.0.0", a_software="qmrlab",
                  b_target="sct@7.3", b_software="sct")

    for clipped in ("T1", "MTsat"):
        assert comparability_for(
            entries, "mt_sat", clipped, **lookup
        ).estimator_class == "related-estimator"
    assert comparability_for(
        entries, "mt_sat", "MTR", **lookup
    ).estimator_class == "same-estimator"
