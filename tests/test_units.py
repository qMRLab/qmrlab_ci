import json
import pathlib

import pytest

from harness.analyze import analyze
from harness.config import load_models
from harness.units import scale_between
from tests.helpers import write_nifti

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_same_unit_is_identity():
    assert scale_between("s", "s") == 1.0


def test_milliseconds_to_seconds():
    assert scale_between("ms", "s") == 0.001


def test_seconds_to_milliseconds():
    assert scale_between("s", "ms") == 1000.0


def test_percent_to_fraction():
    assert scale_between("percent", "fraction") == 0.01


def test_fraction_to_percent():
    assert scale_between("fraction", "percent") == 100.0


def test_au_to_fraction_is_identity():
    """'au' on a B1 map already means "1.0 = nominal flip achieved", i.e. a fraction.

    An identity here, not a rescale: the number does not change, only the name it is
    published under. The pair exists so a software reporting percent-of-nominal can
    declare 'percent' and be scaled by 0.01 rather than declaring 'au' and shipping a
    100x error dressed up as a fit difference.
    """
    assert scale_between("au", "fraction") == 1.0


def test_fraction_to_au_is_identity():
    assert scale_between("fraction", "au") == 1.0


def test_unknown_unit_raises_rather_than_passing_through():
    with pytest.raises(ValueError, match="unknown unit 'nT'"):
        scale_between("nT", "fraction")

    with pytest.raises(ValueError, match="unknown unit 'nT'"):
        scale_between("fraction", "nT")


def test_unknown_conversion_raises_rather_than_assuming_identity():
    """Silently assuming 1.0 would publish wrong numbers that look right."""
    with pytest.raises(ValueError, match="no conversion"):
        scale_between("s", "percent")


def test_known_units_that_share_no_dimension_have_no_pair():
    """Both units are known and both are B1-adjacent, but 'au' is not seconds."""
    with pytest.raises(ValueError, match="no conversion"):
        scale_between("au", "s")


def test_both_b1_models_declare_a_unit_reachable_from_au():
    """The ordering guarantee, asserted against the shipped catalog.

    Adapters emit B1map as 'au' (matlab/qmrlab_ci_unit_for.m falls through to it), so
    whatever unit models/b1_*.yml declares must be reachable from 'au' or every target
    fails both B1 models at once. This fails if the yml is changed to a unit the table
    cannot convert from — which is precisely what adding the pair first prevents.
    """
    models = load_models(ROOT)

    for model_id in ("b1_dam", "b1_afi"):
        spec = next(m for m in models[model_id].maps if m.name == "B1map")
        assert spec.unit == "fraction"
        assert scale_between("au", spec.unit) == 1.0


def test_a_record_declaring_au_still_analyzes_against_the_fraction_model(tmp_path):
    """The backward-compatibility case: every record already written says 'au'.

    Run analyze over an artifact tree exactly as the MATLAB lane writes it, against
    the real models/b1_dam.yml, and the values must arrive unscaled — 0.9 stays 0.9,
    not 0.009 and not 90.
    """
    results, root = tmp_path / "results", tmp_path / "root"
    values = [0.8, 0.9, 1.0, 1.1]

    maps_dir = results / "legacy@1" / "maps" / "b1_dam"
    maps_dir.mkdir(parents=True)
    (results / "legacy@1" / "records").mkdir(parents=True)
    write_nifti(maps_dir / "B1map.nii.gz", values, shape=(len(values),))
    (results / "legacy@1" / "records" / "b1_dam.json").write_text(json.dumps({
        "target": "legacy@1", "software": "qmrlab", "version": "3.0.0",
        "model": "b1_dam", "status": "ok", "environment": {},
        "timing": {"repeats": 1, "fit_seconds": [1.0], "n_voxels_fitted": len(values)},
        "maps": [{"name": "B1map", "unit": "au", "path": "maps/b1_dam/B1map.nii.gz"}],
    }))
    (root / "masks").mkdir(parents=True)
    write_nifti(root / "masks" / "b1_dam.nii.gz", [1] * len(values),
                shape=(len(values),), datatype=2)

    doc = analyze(results, root, models_root=ROOT, reference="legacy@1")
    record = next(r for r in doc["records"] if r["target"] == "legacy@1")

    assert record["status"] == "ok", record.get("error")
    assert record["maps"][0]["unit"] == "au"
    assert record["maps"][0]["stats_unit"] == "fraction"
    assert record["maps"][0]["stats"]["mean"] == pytest.approx(0.95)
    assert record["maps"][0]["stats"]["max"] == pytest.approx(1.1)
