import re

import pytest

from harness.site import _ordered, _text_width, render

DOC = {
    "reference": "b@1",
    "records": [
        {"target": "a@1", "software": "x", "version": "1", "model": "vfa_t1",
         "status": "ok", "environment": {"matlab_release": "R2021a"},
         "timing": {"repeats": 2, "fit_seconds": [2.0, 4.0], "n_voxels_fitted": 100},
         "error": None,
         "maps": [{"name": "T1", "unit": "s", "voxel_sha256": "abc123",
                   "stats_unit": "s", "stats": {"n": 100, "mean": 1.0}}]},
        {"target": "b@1", "software": "y", "version": "1", "model": "vfa_t1",
         "status": "failed", "environment": {}, "timing": {}, "maps": [],
         "error": "install failed: patch rejected"},
    ],
    "equivalence": {"vfa_t1": {"T1": {"abc123": ["a@1"]}}},
    "comparisons": {"vfa_t1": {"T1": []}},
}


def test_page_is_self_contained_html():
    html = render(DOC)

    assert html.startswith("<!doctype html>")
    assert "<script src=" not in html and "<link rel=\"stylesheet\" href=" not in html


def test_failed_targets_are_shown_not_omitted():
    """A missing row reads as 'not run'; a failure must read as a failure."""
    html = render(DOC)

    assert "install failed: patch rejected" in html
    assert "failed" in html


def test_timing_rows_carry_the_matlab_release():
    """Otherwise a version-to-version time difference silently conflates the two."""
    assert "R2021a" in render(DOC)


def test_median_fit_time_is_derived_not_stored():
    """Median of [2.0, 4.0] is 3 and is computed here, not read from the record."""
    assert ">3s<" in render(DOC)


def test_equivalence_class_hash_is_shown_abbreviated():
    assert "abc123"[:8] in render(DOC)


def test_pairwise_agreement_is_rendered():
    """Spec §9: the per-model view shows delta vs reference and voxelwise agreement."""
    doc = {**DOC, "comparisons": {"vfa_t1": {"T1": [
        {"a": "a@1", "b": "b@1", "n": 100, "frac_within": 0.97,
         "pearson_r": 0.999, "mean_delta": 0.01, "median_delta": 0.0,
         "max_abs_delta": 0.4},
    ]}}}

    html = render(doc)

    assert "0.97" in html
    assert "0.999" in html


# C3, final review: a declared-but-unrun combination ("missing") must be visibly
# distinct from both a reported failure ("failed") and a genuine capability gap
# ("not applicable", rendered by the absence of any record for that cell).
FOUR_STATE_DOC = {
    "reference": "t1",
    "records": [
        {"target": "t1", "software": "x", "version": "1", "model": "m1",
         "status": "ok", "environment": {}, "timing": {}, "error": None,
         "maps": [{"name": "T1", "unit": "s", "voxel_sha256": "aaaa1111",
                   "stats_unit": "s", "stats": {"n": 1, "mean": 1.0}}]},
        {"target": "t1", "software": "x", "version": "1", "model": "m2",
         "status": "failed", "environment": {}, "timing": {}, "maps": [],
         "error": "install failed"},
        {"target": "t1", "software": "", "version": "", "model": "m3",
         "status": "missing", "environment": {}, "timing": {}, "maps": [],
         "error": "no record found for this declared target/model combination"},
        # t2/m4 exists solely so "m4" appears as a column; t1 never declared it,
        # so the (t1, m4) cell is a genuine "not applicable" hole.
        {"target": "t2", "software": "x", "version": "1", "model": "m4",
         "status": "ok", "environment": {}, "timing": {}, "error": None,
         "maps": [{"name": "T1", "unit": "s", "voxel_sha256": "bbbb2222",
                   "stats_unit": "s", "stats": {"n": 1, "mean": 1.0}}]},
    ],
    "equivalence": {},
    "comparisons": {},
}


def test_four_cell_states_render_distinctly():
    html = render(FOUR_STATE_DOC)

    assert 'class="failed"' in html
    assert 'class="missing"' in html
    assert 'class="na"' in html
    assert "not applicable" in html
    assert "failed: install failed" in html
    assert "missing: no record found" in html
    # The ok cell's hash renders plainly, not wrapped in any status class.
    assert "aaaa1111" in html


def test_stats_table_shows_percentiles_and_nonfinite_count():
    doc = {**DOC, "records": [{
        **DOC["records"][0],
        "maps": [{
            "name": "T1", "unit": "s", "voxel_sha256": "abc123", "stats_unit": "s",
            "stats": {"n": 90, "mean": 1.0, "median": 1.1, "std": 0.2,
                      "p05": 0.5, "p95": 1.8, "min": 0.1, "max": 2.0,
                      "n_nonfinite": 10, "n_zero": 0},
        }],
    }]}

    html = render(doc)

    assert "<th>p05</th>" in html and "<th>p95</th>" in html
    assert "0.5" in html and "1.8" in html
    assert "non-finite" in html


def test_outlier_dominated_mean_is_flagged_with_a_legend():
    """I3, final review: mt_sat/MTsat's real published numbers (mean -5.41e13,
    median 2.56) must not present the mean unflagged as the headline figure."""
    doc = {**DOC, "records": [{
        **DOC["records"][0],
        "maps": [{
            "name": "MTsat", "unit": "percent", "voxel_sha256": "deadbeef",
            "stats_unit": "percent",
            "stats": {"n": 100, "mean": -5.41e13, "median": 2.56, "std": 3.6e15,
                      "p05": -5.23, "p95": 35.71, "min": -9.18e17, "max": 6.78e16,
                      "n_nonfinite": 0, "n_zero": 0},
        }],
    }]}

    html = render(doc)

    assert '<span class="outlier-flag"' in html
    assert "outlier-dominated" in html
    assert "median" in html.lower()


def test_stats_table_does_not_flag_a_well_behaved_mean():
    html = render(DOC)  # DOC's only map stat is {"n": 100, "mean": 1.0} -- no median

    assert '<span class="outlier-flag"' not in html
    assert "outlier-dominated" not in html  # legend only appears when a row is flagged


def test_href_links_to_raw_data_files():
    html = render(DOC)

    assert '<a href="data/results.json">' in html
    assert '<a href="data/history.jsonl">' in html


def test_reference_header_shown_when_reference_target_has_records():
    """DOC's reference is b@1, which has a real (if failed) record."""
    assert "Reference target" in render(DOC)


def test_reference_header_hidden_when_reference_target_has_no_records():
    doc = {**DOC, "reference": "ghost@1"}

    assert "Reference target" not in render(doc)


def test_reference_header_hidden_when_reference_target_is_entirely_missing():
    doc = {**DOC, "reference": "gone@1", "records": DOC["records"] + [
        {"target": "gone@1", "software": "", "version": "", "model": "vfa_t1",
         "status": "missing", "environment": {}, "timing": {}, "maps": [],
         "error": "no record found"},
    ]}

    assert "Reference target" not in render(doc)


# --- three software families ---------------------------------------------------------
#
# a@1/b@1 above match neither TARGET_ORDER nor any label rule, so ordering and labelling
# -- precisely what a third software family breaks -- had no coverage at all. These
# fixtures are the real shape: qMRLab's release history, qmrust, and two families that
# pin one version each, one of which (hmri) is in no constant anywhere in site.py.

def _rec(target, software, version, model, maps, *, status="ok", error=None, seconds=1.0):
    return {
        "target": target, "software": software, "version": version, "model": model,
        "status": status, "error": error,
        "environment": {"matlab_release": "R2026a" if software == "qmrlab" else None},
        "timing": {"repeats": 2, "fit_seconds": [seconds, seconds], "n_voxels_fitted": 10},
        "maps": [{"name": name, "unit": unit, "voxel_sha256": digest, "stats_unit": unit,
                  "stats": {"n": 1391756, "mean": 1.0, "median": 1.1, "std": 0.2,
                            "p05": 0.5, "p95": 1.8, "min": 0.1, "max": 2.0,
                            "n_nonfinite": nonfinite, "n_zero": 0}}
                 for name, unit, digest, nonfinite in maps],
    }


def _pair(a, b, **kw):
    """One comparison row in the shape analyze.py writes it: flat flag, flat reason."""
    row = {"a": a, "b": b, "n": 219412, "frac_within": 0.93, "pearson_r": 0.999,
           "mean_delta": 0.01, "median_delta": 0.0, "max_abs_delta": 0.4,
           "rel_median_diff": 0.0, "ccc": 1.0, "scale_free": False,
           "scale_ratio_not_a_disagreement": None,
           "comparison_range": None, "n_out_of_range": 0,
           "estimator_class": "same-estimator",
           "flag": "green", "flag_reason": "within the same-estimator thresholds"}
    row.update(kw)
    return row


THREE_FAMILY = {
    "reference": "qmrlab@v3.0.0",
    "records": [
        # qMRLab: an old release, the latest release and the moving branch.
        _rec("qmrlab@V1", "qmrlab", "V1", "mt_ratio", [("MTR", "percent", "a" * 64, 0)]),
        _rec("qmrlab@v3.0.0", "qmrlab", "v3.0.0", "mt_ratio",
             [("MTR", "percent", "a" * 64, 0)]),
        _rec("qmrlab@master", "qmrlab", "master", "mt_ratio",
             [("MTR", "percent", "a" * 64, 0)]),
        _rec("qmrlab@v3.0.0", "qmrlab", "v3.0.0", "mt_sat",
             [("T1", "s", "b" * 64, 40132)], seconds=9.0),
        _rec("qmrlab@master", "qmrlab", "master", "mt_sat", [("T1", "s", "b" * 64, 40132)]),
        _rec("qmrlab@V1", "qmrlab", "V1", "mt_sat", [("T1", "s", "b" * 64, 40132)]),
        _rec("qmrust@main", "qmrust", "main", "mt_ratio", [("MTR", "percent", "c" * 64, 0)]),
        # A different count of unusable voxels is a legitimate difference, not a
        # defect: qMRLab leaves an infinite T1 where qmrust writes a finite one.
        _rec("qmrust@main", "qmrust", "main", "mt_sat", [("T1", "s", "d" * 64, 0)]),
        # SCT declares two models and no others; here it runs one and fails the other.
        _rec("sct@7.3", "sct", "7.3", "mt_ratio", [("MTR", "percent", "e" * 64, 0)]),
        _rec("sct@7.3", "sct", "7.3", "mt_sat", [], status="failed",
             error="sct_compute_mtsat exited 1"),
        # QUIT's only cell in this run never came back at all.
        {"target": "quit@v3.4", "software": "", "version": "", "model": "mt_ratio",
         "status": "missing", "environment": {}, "timing": {}, "maps": [],
         "error": "no record found for this declared target/model combination"},
    ],
    "equivalence": {"mt_ratio": {"MTR": {
        "a" * 64: ["qmrlab@V1", "qmrlab@v3.0.0", "qmrlab@master"],
        "c" * 64: ["qmrust@main"], "e" * 64: ["sct@7.3"]}}},
    "comparisons": {
        "mt_ratio": {"MTR": [
            _pair("qmrlab@master", "qmrlab@v3.0.0"),
            _pair("qmrlab@v3.0.0", "qmrust@main", rel_median_diff=0.001, ccc=0.998),
            # compare_maps divides by |b|, and `b` here is the alphabetically later id,
            # so this row's difference is the reference MINUS sct and its denominator is
            # sct -- the asymmetry the Difference column exists to print.
            _pair("qmrlab@v3.0.0", "sct@7.3", rel_median_diff=-0.132, ccc=0.712,
                  pearson_r=0.998, comparison_range=[-100, 100], n_out_of_range=34087,
                  flag="red", flag_reason="relative median difference -13.2% exceeds "
                                          "10%; CCC 0.712 is below 0.9"),
            # Two old releases against each other: version history, not cross-software.
            _pair("qmrlab@V1", "qmrlab@master", rel_median_diff=0.4, ccc=0.2,
                  flag="red", flag_reason="V1 against master is not this tab"),
        ]},
        "mt_sat": {"T1": [
            _pair("qmrlab@v3.0.0", "qmrust@main", rel_median_diff=0.02, ccc=0.97,
                  estimator_class="related-estimator", flag="amber",
                  flag_reason="SCT clips R1 below 0.01 s^-1 to give T1 = 0"),
        ]},
    },
}


def _cross_pane(page):
    return page.split('<section data-pane="cross"')[1].split("</section>")[0]


def _visible(page):
    """The page with every tooltip removed, i.e. what a reader who never hovers sees."""
    return re.sub(r'data-tip="[^"]*"', "", page)


def test_cross_software_is_a_tab_of_its_own():
    page = render(THREE_FAMILY)

    assert '<button data-tab="cross"' in page
    assert 'data-pane="cross"' in page


def test_cross_software_shows_the_latest_of_each_software_only():
    """Spec §8: qmrlab@v3.0.0 and master, qmrust, and every other family present."""
    pane = _cross_pane(render(THREE_FAMILY))

    for label in ("qmrlab v3.0.0", "qmrlab master", "qmrust main", "sct 7.3", "quit v3.4"):
        assert label in pane, label
    assert "qmrlab V1" not in pane


def test_the_cross_software_set_is_derived_from_the_software_field():
    """A family named in no constant in site.py must still get a column of its own.

    Hardcoding the target list would render a new software as absent rather than as a
    column, and nothing would raise while it did.
    """
    doc = {**THREE_FAMILY, "records": THREE_FAMILY["records"] + [
        _rec("hmri@v1.0.0", "hmri", "v1.0.0", "mt_sat", [("T1", "s", "f" * 64, 0)])]}

    pane = _cross_pane(render(doc))

    assert "hmri v1.0.0" in pane
    assert "<th>hmri</th>" in pane


def test_coverage_table_separates_a_declared_hole_from_a_failure():
    """SCT covers 2 of 9 models. Without this the empty cells read as broken runs."""
    pane = _cross_pane(render(THREE_FAMILY))

    assert "declared hole" in pane
    assert "failed" in pane and "missing" in pane
    # mt_sat is a hole for QUIT here (no record at all) and a failure for SCT.
    assert "sct_compute_mtsat exited 1" in _visible(pane)
    assert "no record found" in _visible(pane)


def test_coverage_table_is_generated_from_the_records():
    """Transcribing spec §2.4 would let the table survive a run that contradicts it."""
    doc = {**THREE_FAMILY, "records": [r for r in THREE_FAMILY["records"]
                                       if r["target"] != "sct@7.3"]}

    pane = _cross_pane(render(doc))

    assert "<th>sct</th>" not in pane


def test_a_missing_only_target_still_lands_in_a_family():
    """analyze's `missing` records carry empty software/version.

    A target whose every record is one would otherwise have no family at all and drop out
    of the coverage table, making a killed lane read as a declared hole.
    """
    pane = _cross_pane(render(THREE_FAMILY))

    assert "<th>quit</th>" in pane


def test_pair_rows_carry_all_three_disagreement_metrics():
    pane = _cross_pane(render(THREE_FAMILY))

    assert "-13.2%" in pane      # rel_median_diff, signed
    assert "0.712" in pane       # ccc
    assert "0.998" in pane       # pearson_r


def test_the_flag_reason_is_visible_text_not_a_tooltip():
    """Spec §7.3, following the "What did not run" precedent."""
    pane = _visible(_cross_pane(render(THREE_FAMILY)))

    assert "relative median difference -13.2% exceeds 10%; CCC 0.712 is below 0.9" in pane
    assert "SCT clips R1 below 0.01 s^-1 to give T1 = 0" in pane
    assert "related-estimator" in pane


def test_only_pairs_against_the_reference_are_shown():
    """The tab asks how each software compares with the reference, not all-pairs."""
    pane = _cross_pane(render(THREE_FAMILY))

    assert "V1 against master is not this tab" not in pane


def test_an_unflagged_pair_is_not_green():
    """This slice and the analyze-side flag wiring land independently; an absent flag
    must read as unclassified, never as a pair that passed."""
    doc = {**THREE_FAMILY, "comparisons": {"mt_ratio": {"MTR": [
        {"a": "qmrlab@v3.0.0", "b": "sct@7.3", "n": 10, "pearson_r": 0.9},
    ]}}}

    pane = _visible(_cross_pane(render(doc)))

    assert "not classified" in pane
    assert "not a passing one" in pane


def test_a_nested_flag_shape_is_read_too():
    """analyze writes the flag flat today. A {"colour": .., "reason": ..} row is the
    other shape flag_for's own dataclass suggests, and this renderer lands separately
    from the code that writes it -- so both are read rather than one being assumed."""
    doc = {**THREE_FAMILY, "comparisons": {"mt_ratio": {"MTR": [
        {"a": "qmrlab@v3.0.0", "b": "sct@7.3", "n": 10, "rel_median_diff": 0.2,
         "ccc": 0.5, "flag": {"colour": "red", "reason": "nested rows are read as well"}},
    ]}}}

    pane = _visible(_cross_pane(render(doc)))

    assert "nested rows are read as well" in pane


def test_an_unknown_flag_colour_raises():
    """Greying out a red pair would publish exactly what the flag exists to prevent."""
    doc = {**THREE_FAMILY, "comparisons": {"mt_ratio": {"MTR": [
        {"a": "qmrlab@v3.0.0", "b": "sct@7.3", "n": 10, "flag": "purple"},
    ]}}}

    with pytest.raises(ValueError, match="purple"):
        render(doc)


def test_every_disclosure_row_renders_as_visible_text():
    """Spec §7.3: each of these changes a published number, and a reader who does not
    know about it misreads the page."""
    pane = _visible(_cross_pane(render(THREE_FAMILY)))

    assert "declared hole is not a failure" in pane          # coverage and holes
    assert "1/0 = inf" in pane and "non-finite" in pane      # the reciprocal rule
    assert "QUIT is v3.4, not master" in pane                # the pin
    assert "float32" in pane and "float64" in pane           # hashes never match
    assert "Two masks" in pane and "comparison_mask" in pane  # which mask, which number
    assert "Input-domain violations" in pane


def test_the_reciprocal_disclosure_names_the_counts_that_differ():
    """State the rule and the counts, or "this target has 40,132 unusable voxels and
    that one has none" reads as a defect rather than as 1/0 = inf."""
    pane = _visible(_cross_pane(render(THREE_FAMILY)))

    assert "qmrlab v3.0.0 40,132" in pane
    assert "qmrust main 0" in pane


def test_the_mask_disclosure_says_how_many_voxels_were_excluded():
    pane = _visible(_cross_pane(render(THREE_FAMILY)))

    assert "219,412 compared" in pane
    assert "1,172,344 excluded" in pane


def test_an_input_domain_violation_is_named_where_one_exists():
    doc = {**THREE_FAMILY, "comparisons": {"mt_ratio": {"MTR": [
        _pair("qmrlab@v3.0.0", "sct@7.3", input_domain="violated",
              input_domain_reason="qi irtse applies no abs() to its residuals",
              flag="red", flag_reason="input domain violated"),
    ]}}}

    pane = _visible(_cross_pane(render(doc)))

    assert "qi irtse applies no abs() to its residuals" in pane


# --- the version-history tabs --------------------------------------------------------

def test_the_five_tabs_filter_to_qmrlab_and_qmrust():
    """Spec §8: one pinned version has no history to read, and putting it on a version
    axis says nothing while stretching every chart to fit it."""
    page = render(THREE_FAMILY)
    panes = dict(re.findall(r'<section data-pane="([a-z]+)"[^>]*>(.*?)</section>',
                            page, re.S))

    for name in ("overview", "agree", "values", "timing", "data"):
        body = panes[name].replace("on the Cross-software tab", "")
        # The one mention left is the note naming where those targets went.
        assert body.count("sct 7.3") <= 1, name
        assert "e" * 64 not in body, name  # sct's hash, i.e. a real sct row


def test_a_run_with_no_version_history_is_not_filtered_to_nothing():
    """DOC's targets are x@1 and y@1: no qMRLab, no qmrust. Filtering that to nothing
    would publish five empty tabs instead of the data the run does have."""
    page = render(DOC)

    assert "install failed: patch rejected" in page
    assert "R2021a" in page


# --- labels and gutters --------------------------------------------------------------

def test_labels_keep_the_software_family():
    """Two hardcoded replaces could not label a family they had never seen."""
    page = render(THREE_FAMILY)

    assert "qmrlab v3.0.0" in page and "qmrust main" in page and "sct 7.3" in page
    assert "qmrlab@v3.0.0" not in page  # the id is never rendered as a label


def _end_anchored(page):
    return [(float(x), label) for x, label in re.findall(
        r'<text x="([-\d.]+)"[^>]*text-anchor="end"[^>]*>([^<]*)</text>', page)]


LONG_LABELS = {
    "reference": "sct@7.3",
    "records": [
        _rec("sct@7.3", "sct", "7.3", "inversion_recovery", [("T1", "s", "a" * 64, 0)]),
        _rec("quit@v3.4-release-candidate-2", "quit", "v3.4-release-candidate-2",
             "inversion_recovery", [("T1", "s", "b" * 64, 0)], seconds=44.0),
    ],
    "equivalence": {"inversion_recovery": {"T1": {
        "a" * 64: ["sct@7.3"], "b" * 64: ["quit@v3.4-release-candidate-2"]}}},
    "comparisons": {"inversion_recovery": {"T1": [
        _pair("quit@v3.4-release-candidate-2", "sct@7.3", frac_within=0.5,
              flag="amber", flag_reason="long labels")]}},
}


@pytest.mark.parametrize("doc", [DOC, FOUR_STATE_DOC, THREE_FAMILY, LONG_LABELS])
def test_no_label_is_drawn_outside_the_svg(doc):
    """The bug this replaces: the gutters were fixed pixel constants and the labels were
    drawn text-anchor="end" just inside them, so a longer label landed at NEGATIVE x and
    the viewport clipped it away with no error and no gap to notice."""
    page = render(doc)

    assert re.findall(r'(?:x|y|width|height)="(-[\d.]+)"', page) == []


def test_the_gutter_is_measured_from_the_longest_label():
    """`quit@v3.4-release-candidate-2` is longer than all three old constants."""
    page = render(LONG_LABELS)
    labels = _end_anchored(page)

    assert labels
    for x, label in labels:
        assert x >= _text_width(label), f"{label!r} would be clipped at x={x}"


def test_ordering_puts_an_unknown_family_after_the_known_targets():
    """TARGET_ORDER is chronology; a family it does not know has none to place."""
    assert _ordered({"sct@7.3", "qmrust@main", "qmrlab@v3.0.0", "quit@v3.4"}) == [
        "qmrlab@v3.0.0", "qmrust@main", "quit@v3.4", "sct@7.3"]


def test_a_record_asserting_not_applicable_raises():
    """A hole is declared by omission from target.yml and by nothing else. A record
    ASSERTING one would make a killed job indistinguishable from a declared hole, which
    is the confusion the `missing` marker exists to prevent (spec §2.4)."""
    doc = {**THREE_FAMILY, "records": THREE_FAMILY["records"] + [
        {"target": "sct@7.3", "software": "sct", "version": "7.3", "model": "vfa_t1",
         "status": "not_applicable", "environment": {}, "timing": {}, "maps": [],
         "error": None}]}

    with pytest.raises(ValueError, match="not_applicable"):
        render(doc)


def test_a_page_with_no_records_still_renders():
    """A wiped run must publish an empty page, not a traceback."""
    page = render({"reference": None, "records": [], "equivalence": {}, "comparisons": {}})

    assert "No cross-software pair in this run" in page


def test_the_difference_column_says_which_way_round_it_was_measured():
    """compare_maps measures a - b over |b|, and `b` is only the alphabetically later
    id: a table that implied "target minus reference" everywhere would invert the sign
    of every row where the reference sorted first (spec §5.6)."""
    pane = _cross_pane(render(THREE_FAMILY))

    assert "qmrlab v3.0.0 &minus; sct 7.3" in pane


def test_a_declared_reference_that_is_not_the_denominator_is_shown():
    """The numbers are divided by |b| whatever the row declares, so a reference declared
    on the other side means the row is measured against the side it did not mean to."""
    doc = {**THREE_FAMILY, "comparisons": {"mt_ratio": {"MTR": [
        _pair("qmrlab@v3.0.0", "sct@7.3", reference="qmrlab@v3.0.0"),
    ]}}}

    pane = _visible(_cross_pane(render(doc)))

    assert "declared reference qmrlab v3.0.0, measured against sct 7.3" in pane


def test_voxels_excluded_by_a_declared_range_are_counted_in_the_row():
    """An exclusion nobody can see is indistinguishable from a mask that never held
    those voxels, and this one is a claim about physics rather than anatomy."""
    pane = _visible(_cross_pane(render(THREE_FAMILY)))

    assert "34,087 outside [-100, 100]" in pane


def test_the_disclosure_names_the_declared_range_and_what_it_removed():
    pane = _visible(_cross_pane(render(THREE_FAMILY)))

    assert "comparison_range" in pane
    assert "mt_ratio / MTR [-100, 100]: 34,087 excluded against sct 7.3" in pane
