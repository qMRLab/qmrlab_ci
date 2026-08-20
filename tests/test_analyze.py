import json
import pathlib

import numpy as np
import yaml

from harness.analyze import analyze
from tests.helpers import write_nifti

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _write_target(root, target_id, *, models, lane="rust", **extra):
    """Write a minimal targets/<id>/target.yml declaring MODELS."""
    path = pathlib.Path(root) / "targets" / target_id / "target.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "id": target_id, "software": "x", "version": "1", "lane": lane,
        "source": {"repo": "x/y", "ref": "main"}, "models": models,
    }
    doc.update(extra)
    path.write_text(yaml.safe_dump(doc))


def _target(results, target_id, values, unit="s", model="vfa_t1"):
    """Write one adapter's artifact tree: a T1 map plus its record."""
    d = results / target_id
    (d / "maps" / model).mkdir(parents=True, exist_ok=True)
    (d / "records").mkdir(parents=True, exist_ok=True)
    write_nifti(d / "maps" / model / "T1.nii.gz", values, shape=(len(values),))
    (d / "records" / f"{model}.json").write_text(json.dumps({
        "target": target_id, "software": "x", "version": "1", "model": model,
        "status": "ok", "environment": {},
        "timing": {"repeats": 1, "fit_seconds": [1.0], "n_voxels_fitted": len(values)},
        "maps": [{"name": "T1", "unit": unit, "path": f"maps/{model}/T1.nii.gz"}],
    }))


def _mask(root, n):
    (root / "masks").mkdir(parents=True, exist_ok=True)
    write_nifti(root / "masks" / "vfa_t1.nii.gz", [1] * n, shape=(n,), datatype=2)


def test_identical_maps_land_in_one_equivalence_class(tmp_path):
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 2.0, 3.0])
    _target(results, "b@1", [1.0, 2.0, 3.0])
    _mask(root, 3)

    doc = analyze(results, root, models_root=ROOT, reference="a@1")

    classes = doc["equivalence"]["vfa_t1"]["T1"]
    assert len(classes) == 1
    assert sorted(next(iter(classes.values()))) == ["a@1", "b@1"]


def test_unit_difference_is_scaled_for_stats_but_not_for_the_hash(tmp_path):
    """The whole point of separating the two: same fit, different unit."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "sec@1", [1.0, 2.0], unit="s")
    _target(results, "ms@1", [1000.0, 2000.0], unit="ms")
    _mask(root, 2)

    doc = analyze(results, root, models_root=ROOT, reference="sec@1")
    by_target = {r["target"]: r for r in doc["records"]}

    assert by_target["sec@1"]["maps"][0]["stats"]["mean"] == 1.5
    assert by_target["ms@1"]["maps"][0]["stats"]["mean"] == 1.5
    assert by_target["ms@1"]["maps"][0]["stats_unit"] == "s"
    assert (by_target["sec@1"]["maps"][0]["voxel_sha256"]
            != by_target["ms@1"]["maps"][0]["voxel_sha256"])


def test_comparisons_are_made_in_canonical_units(tmp_path):
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "sec@1", [1.0, 2.0], unit="s")
    _target(results, "ms@1", [1000.0, 2000.0], unit="ms")
    _mask(root, 2)

    doc = analyze(results, root, models_root=ROOT, reference="sec@1")
    pair = doc["comparisons"]["vfa_t1"]["T1"][0]

    assert pair["mean_delta"] == 0.0
    assert pair["frac_within"] == 1.0


def test_failed_targets_appear_in_records_without_maps(tmp_path):
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0])
    _mask(root, 1)
    d = results / "broken@1" / "records"
    d.mkdir(parents=True)
    (d / "vfa_t1.json").write_text(json.dumps({
        "target": "broken@1", "software": "x", "version": "1", "model": "vfa_t1",
        "status": "failed", "environment": {}, "timing": {}, "maps": [],
        "error": "install failed",
    }))

    doc = analyze(results, root, models_root=ROOT, reference="a@1")
    broken = next(r for r in doc["records"] if r["target"] == "broken@1")

    assert broken["status"] == "failed"
    assert broken["maps"] == []


def _write_record(results, target_id, model, status, maps, **extra):
    d = results / target_id / "records"
    d.mkdir(parents=True, exist_ok=True)
    doc = {
        "target": target_id, "software": "x", "version": "1", "model": model,
        "status": status, "environment": {},
        "timing": {"repeats": 1, "fit_seconds": [1.0], "n_voxels_fitted": 1},
        "maps": maps,
        **extra,
    }
    (d / f"{model}.json").write_text(json.dumps(doc))


def test_an_undeclared_map_name_isolates_to_that_target_only(tmp_path):
    """A map name absent from the catalog must not abort the whole run (spec §10)."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "good@1", [1.0, 2.0])
    _mask(root, 2)

    (results / "broken@1" / "maps" / "vfa_t1").mkdir(parents=True)
    write_nifti(results / "broken@1" / "maps" / "vfa_t1" / "T1.nii.gz", [1.0, 2.0], shape=(2,))
    _write_record(
        results, "broken@1", "vfa_t1", "ok",
        [{"name": "T99", "unit": "s", "path": "maps/vfa_t1/T1.nii.gz"}],
    )

    doc = analyze(results, root, models_root=ROOT, reference="good@1")
    by_target = {r["target"]: r for r in doc["records"]}

    assert by_target["good@1"]["status"] == "ok"
    assert by_target["broken@1"]["status"] == "failed"
    assert "analysis failed" in by_target["broken@1"]["error"]


def test_a_missing_map_file_isolates_to_that_target_only(tmp_path):
    """A map file absent from disk must not abort the whole run (spec §10)."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "good@1", [1.0, 2.0])
    _mask(root, 2)

    (results / "broken@1" / "maps" / "vfa_t1").mkdir(parents=True)
    _write_record(
        results, "broken@1", "vfa_t1", "ok",
        [{"name": "T1", "unit": "s", "path": "maps/vfa_t1/MISSING.nii.gz"}],
    )

    doc = analyze(results, root, models_root=ROOT, reference="good@1")
    by_target = {r["target"]: r for r in doc["records"]}

    assert by_target["good@1"]["status"] == "ok"
    assert by_target["broken@1"]["status"] == "failed"
    assert "analysis failed" in by_target["broken@1"]["error"]


def test_a_voxel_count_mismatch_isolates_to_that_target_only(tmp_path):
    """A voxel count that disagrees with the mask must not abort the whole run (spec §10)."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "good@1", [1.0, 2.0])
    _mask(root, 2)

    (results / "broken@1" / "maps" / "vfa_t1").mkdir(parents=True)
    write_nifti(
        results / "broken@1" / "maps" / "vfa_t1" / "T1.nii.gz",
        [1.0, 2.0, 3.0], shape=(3,),
    )
    _write_record(
        results, "broken@1", "vfa_t1", "ok",
        [{"name": "T1", "unit": "s", "path": "maps/vfa_t1/T1.nii.gz"}],
    )

    doc = analyze(results, root, models_root=ROOT, reference="good@1")
    by_target = {r["target"]: r for r in doc["records"]}

    assert by_target["good@1"]["status"] == "ok"
    assert by_target["broken@1"]["status"] == "failed"
    assert "analysis failed" in by_target["broken@1"]["error"]


def test_a_declared_target_model_with_no_record_at_all_is_marked_missing(tmp_path):
    """C3, final review: a killed/never-started job must render as a failure of the
    RUN, never silently as a design hole (spec §2.4/§10)."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "good@1", [1.0, 2.0])
    _mask(root, 2)
    _write_target(root, "good@1", models=["vfa_t1"])
    # "gone@1" declares vfa_t1 but its job produced no record directory at all --
    # e.g. cancelled before it could write anything.
    _write_target(root, "gone@1", models=["vfa_t1"])

    doc = analyze(results, root, models_root=ROOT, reference="good@1")
    by_key = {(r["target"], r["model"]): r for r in doc["records"]}

    assert by_key[("good@1", "vfa_t1")]["status"] == "ok"
    missing = by_key[("gone@1", "vfa_t1")]
    assert missing["status"] == "missing"
    assert missing["maps"] == []
    assert "no record found" in missing["error"]


def test_an_undeclared_target_model_combination_is_not_marked_missing(tmp_path):
    """A model a target never declared is a real capability gap (not_applicable),
    never confused with a run that lost part of its matrix."""
    results, root = tmp_path / "results", tmp_path / "root"
    _mask(root, 2)
    # "narrow@1" declares only mono_t2 -- never vfa_t1.
    _write_target(root, "narrow@1", models=["mono_t2"])

    doc = analyze(results, root, models_root=ROOT, reference="narrow@1")
    by_key = {(r["target"], r["model"]): r for r in doc["records"]}

    assert ("narrow@1", "vfa_t1") not in by_key
    # mono_t2 IS declared and never produced a record, so that combination is missing.
    assert by_key[("narrow@1", "mono_t2")]["status"] == "missing"


def test_a_target_with_no_declared_models_directory_synthesizes_nothing(tmp_path):
    """Existing behaviour (no targets/ directory at all, as in every other test
    here) must be unaffected: load_targets on an absent tree is simply empty."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "good@1", [1.0, 2.0])
    _mask(root, 2)

    doc = analyze(results, root, models_root=ROOT, reference="good@1")

    assert [r["status"] for r in doc["records"]] == ["ok"]
