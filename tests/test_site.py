from harness.site import render

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
    """Median of [2.0, 4.0]; %.6g renders it as "3", so match the cell not the float."""
    assert "<td>3</td>" in render(DOC)


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
