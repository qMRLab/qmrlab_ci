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
