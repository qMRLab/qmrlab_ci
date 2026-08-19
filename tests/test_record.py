import pytest

from harness.record import AdapterRecord, RecordError

OK = {
    "target": "qmrlab@v3.0.0", "software": "qmrlab", "version": "v3.0.0",
    "model": "vfa_t1", "status": "ok",
    "environment": {"matlab_release": "R2026a"},
    "timing": {"repeats": 2, "fit_seconds": [1.5, 1.4], "n_voxels_fitted": 10},
    "maps": [{"name": "T1", "unit": "s", "path": "maps/vfa_t1/T1.nii.gz"}],
}


def test_parses_a_well_formed_record():
    r = AdapterRecord.from_dict(OK)

    assert r.target == "qmrlab@v3.0.0"
    assert r.maps[0]["unit"] == "s"


def test_rejects_an_unknown_status():
    with pytest.raises(RecordError, match="status"):
        AdapterRecord.from_dict({**OK, "status": "green"})


def test_rejects_a_map_without_a_declared_unit():
    """An undeclared unit cannot be converted, and guessing would publish wrong numbers."""
    bad = {**OK, "maps": [{"name": "T1", "path": "maps/vfa_t1/T1.nii.gz"}]}

    with pytest.raises(RecordError, match="unit"):
        AdapterRecord.from_dict(bad)


def test_failed_records_need_no_maps_but_must_explain():
    r = AdapterRecord.from_dict(
        {**OK, "status": "failed", "maps": [], "error": "install failed: patch rejected"}
    )

    assert r.status == "failed"
    assert "patch rejected" in r.error


def test_failed_record_without_an_error_is_rejected():
    with pytest.raises(RecordError, match="error"):
        AdapterRecord.from_dict({**OK, "status": "failed", "maps": []})


def test_timing_repeat_count_must_match_the_samples_recorded():
    bad = {**OK, "timing": {"repeats": 5, "fit_seconds": [1.0], "n_voxels_fitted": 10}}

    with pytest.raises(RecordError, match="repeats"):
        AdapterRecord.from_dict(bad)
