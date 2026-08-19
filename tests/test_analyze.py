import json
import pathlib

import numpy as np

from harness.analyze import analyze
from tests.helpers import write_nifti

ROOT = pathlib.Path(__file__).resolve().parents[1]


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
