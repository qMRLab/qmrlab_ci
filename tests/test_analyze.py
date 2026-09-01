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


def _target(results, target_id, values, unit="s", model="vfa_t1", *,
            name="T1", software="x"):
    """Write one adapter's artifact tree: one map plus its record."""
    d = results / target_id
    (d / "maps" / model).mkdir(parents=True, exist_ok=True)
    (d / "records").mkdir(parents=True, exist_ok=True)
    write_nifti(d / "maps" / model / f"{name}.nii.gz", values, shape=(len(values),))
    (d / "records" / f"{model}.json").write_text(json.dumps({
        "target": target_id, "software": software, "version": "1", "model": model,
        "status": "ok", "environment": {},
        "timing": {"repeats": 1, "fit_seconds": [1.0], "n_voxels_fitted": len(values)},
        "maps": [{"name": name, "unit": unit, "path": f"maps/{model}/{name}.nii.gz"}],
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


def _local_catalog(root, *, maps, model="vfa_t1", comparison_mask=None):
    """Write a models/ tree inside the tmp root and use it as THE catalog.

    Needed because no committed models/*.yml declares a transform or a comparison
    mask, and neither field may be added to one here: they are optional precisely so
    the shipped catalog does not move.
    """
    d = pathlib.Path(root) / "models"
    d.mkdir(parents=True, exist_ok=True)
    doc = {
        "id": model, "dataset": "ir", "mask": f"masks/{model}.nii.gz", "maps": maps,
    }
    if comparison_mask is not None:
        doc["comparison_mask"] = comparison_mask
    (d / f"{model}.yml").write_text(yaml.safe_dump(doc))


def _write_mask(root, name, values):
    (root / "masks").mkdir(parents=True, exist_ok=True)
    write_nifti(
        root / "masks" / f"{name}.nii.gz", values, shape=(len(values),), datatype=2
    )


_RECIPROCAL_T1 = [{"name": "T1", "unit": "s", "transform": "reciprocal"}]


def test_a_rate_map_is_inverted_for_stats_but_not_for_the_hash(tmp_path):
    """Spec §5.2. QUIT reports MTSat_R1 in s^-1 where the model declares T1 in s; the
    hash stays on the produced values, exactly as the unit scale already does."""
    from harness.measure import voxel_sha256

    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "rate@1", [0.5, 0.25], unit="s^-1")
    _mask(root, 2)
    _local_catalog(root, maps=_RECIPROCAL_T1)

    doc = analyze(results, root, reference="rate@1")
    m = doc["records"][0]["maps"][0]

    assert m["stats"]["mean"] == 3.0  # 1/0.5 = 2 s and 1/0.25 = 4 s
    assert m["stats_unit"] == "s"
    assert m["unit"] == "s^-1"
    assert m["voxel_sha256"] == voxel_sha256(np.array([0.5, 0.25]))


def test_the_transform_applies_only_to_the_records_that_actually_need_it(tmp_path):
    """The transform is declared per MAP but must act per RECORD: an unconditional
    inversion would turn every already-correct T1 map into a rate."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "sec@1", [2.0, 4.0], unit="s")
    _target(results, "rate@1", [0.5, 0.25], unit="s^-1")
    _mask(root, 2)
    _local_catalog(root, maps=_RECIPROCAL_T1)

    doc = analyze(results, root, reference="sec@1")
    by_target = {r["target"]: r for r in doc["records"]}

    assert by_target["sec@1"]["maps"][0]["stats"]["mean"] == 3.0
    assert by_target["rate@1"]["maps"][0]["stats"]["mean"] == 3.0
    assert doc["comparisons"]["vfa_t1"]["T1"][0]["max_abs_delta"] == 0.0


def test_hz_reaches_seconds_through_the_reciprocal_of_the_canonical_unit(tmp_path):
    """The scale runs first, in the rate domain: Hz -> s^-1 is a factor the linear
    table has, and only the inversion after it is the part units.py refuses."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "hz@1", [0.5, 0.25], unit="Hz")
    _mask(root, 2)
    _local_catalog(root, maps=_RECIPROCAL_T1)

    doc = analyze(results, root, reference="hz@1")

    assert doc["records"][0]["maps"][0]["stats"]["mean"] == 3.0


def test_a_zero_rate_becomes_a_counted_non_finite_voxel_not_a_poisoned_mean(tmp_path):
    """1/0 is inf and inf is the right answer — a zero rate is an infinite time. It
    leaves through masked_stats' existing non-finite path so the background-convention
    difference of §7.2 is reported rather than averaged into the headline."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "rate@1", [0.5, 0.0], unit="s^-1")
    _mask(root, 2)
    _local_catalog(root, maps=_RECIPROCAL_T1)

    doc = analyze(results, root, reference="rate@1")
    stats = doc["records"][0]["maps"][0]["stats"]

    assert stats["n"] == 1
    assert stats["mean"] == 2.0
    assert stats["n_nonfinite"] == 1


def test_a_wrong_unit_still_fails_the_target_when_a_transform_is_declared(tmp_path):
    """The transform is a fallback for the one pair units.py refuses, never a catch-all
    that swallows a genuinely wrong unit."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "bad@1", [1.0, 2.0], unit="percent")
    _mask(root, 2)
    _local_catalog(root, maps=_RECIPROCAL_T1)

    doc = analyze(results, root, reference="bad@1")

    assert doc["records"][0]["status"] == "failed"
    assert "analysis failed" in doc["records"][0]["error"]


def test_a_wrong_unit_on_an_untransformed_map_fails_exactly_as_before(tmp_path):
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "bad@1", [1.0, 2.0], unit="percent")
    _mask(root, 2)
    _local_catalog(root, maps=[{"name": "T1", "unit": "s"}])

    doc = analyze(results, root, reference="bad@1")

    assert doc["records"][0]["status"] == "failed"
    assert "no conversion from 'percent' to 's'" in doc["records"][0]["error"]


def test_a_comparison_mask_narrows_the_pairwise_statistics_and_nothing_else(tmp_path):
    """Spec §7.2: the stricter mask scores agreement; `stats` and the hash keep the
    model's published mask so no number already on the site moves."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 1.0, 1.0])
    _target(results, "b@1", [1.0, 1.0, 2.0])
    _write_mask(root, "vfa_t1", [1, 1, 1])
    _write_mask(root, "vfa_t1_interior", [1, 1, 0])
    _local_catalog(
        root, maps=[{"name": "T1", "unit": "s"}],
        comparison_mask="masks/vfa_t1_interior.nii.gz",
    )

    doc = analyze(results, root, reference="a@1")
    pair = doc["comparisons"]["vfa_t1"]["T1"][0]
    by_target = {r["target"]: r for r in doc["records"]}

    assert pair["n"] == 2
    assert pair["max_abs_delta"] == 0.0
    # The voxel the comparison mask drops is still in the published statistics.
    assert by_target["b@1"]["maps"][0]["stats"]["n"] == 3
    assert by_target["b@1"]["maps"][0]["stats"]["max"] == 2.0


def test_no_comparison_mask_means_the_model_mask_scores_the_comparison(tmp_path):
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 1.0, 1.0])
    _target(results, "b@1", [1.0, 1.0, 2.0])
    _write_mask(root, "vfa_t1", [1, 1, 1])
    _local_catalog(root, maps=[{"name": "T1", "unit": "s"}])

    pair = analyze(results, root, reference="a@1")["comparisons"]["vfa_t1"]["T1"][0]

    assert pair["n"] == 3
    assert pair["max_abs_delta"] == 1.0


def test_a_comparison_mask_of_the_wrong_size_aborts_the_run(tmp_path):
    """A mask that does not fit the grid is a schema violation, and spec §10 lets a
    schema violation take the whole run — quietly comparing the wrong voxels would be
    a published number computed over a selection nobody declared."""
    import pytest

    from harness.config import ConfigError

    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 1.0])
    _write_mask(root, "vfa_t1", [1, 1])
    _write_mask(root, "vfa_t1_interior", [1, 1, 0])
    _local_catalog(
        root, maps=[{"name": "T1", "unit": "s"}],
        comparison_mask="masks/vfa_t1_interior.nii.gz",
    )

    with pytest.raises(ConfigError, match="comparison_mask.*3 voxels.*mask has 2"):
        analyze(results, root, reference="a@1")


# --- comparability wiring (spec §5.5, §7, §7.3) --------------------------------------

def _comparability(root, entries):
    """Write the tmp root's comparability.yml.

    Written per test rather than pointed at the repo's own file: the shipped
    declarations are about qMRLab, QUIT and SCT, and a test that depended on them would
    fail the day one of those entries is re-measured.
    """
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "comparability.yml").write_text(yaml.safe_dump({"entries": entries}))


def test_an_incomparable_pair_is_never_built_at_all(tmp_path):
    """Spec §5.5: not a row with a caveat. A number here would be read as an answer to
    a question the declaration says these two are not both answering."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 2.0], software="alpha")
    _target(results, "b@1", [1.0, 2.0], software="beta")
    _mask(root, 2)
    _local_catalog(root, maps=[{"name": "T1", "unit": "s"}])
    _comparability(root, [{
        "model": "vfa_t1", "maps": ["T1"], "pairs": [["alpha", "beta"]],
        "class": "incomparable",
        "reason": "different physical quantity under the same name",
    }])

    doc = analyze(results, root, reference="a@1")

    assert doc["comparisons"]["vfa_t1"]["T1"] == []
    # The records themselves are untouched: an incomparable PAIR is not a failed target.
    assert [r["status"] for r in doc["records"]] == ["ok", "ok"]


def test_a_related_estimator_pair_is_amber_however_good_the_numbers_are(tmp_path):
    """Two bit-identical maps, and the flag is still amber: red is only assignable
    inside same-estimator, and green would claim an agreement the declaration says
    cannot be read as one (spec §7)."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 2.0], software="alpha")
    _target(results, "b@1", [1.0, 2.0], software="beta")
    _mask(root, 2)
    _local_catalog(root, maps=[{"name": "T1", "unit": "s"}])
    _comparability(root, [{
        "model": "vfa_t1", "maps": ["T1"], "pairs": [["alpha", "beta"]],
        "class": "related-estimator",
        "reason": "beta fits three parameters where alpha fits two",
    }])

    pair = analyze(results, root, reference="a@1")["comparisons"]["vfa_t1"]["T1"][0]

    assert pair["max_abs_delta"] == 0.0
    assert pair["estimator_class"] == "related-estimator"
    assert pair["flag"] == "amber"
    # The declared cause travels onto the row, because the site renders it as visible
    # text beside the colour rather than as a tooltip (spec §7.3).
    assert pair["flag_reason"] == "beta fits three parameters where alpha fits two"


def test_the_software_a_declaration_names_is_the_one_target_yml_declares(tmp_path):
    """comparability.yml names softwares, analyze compares TARGETS, and target.yml owns
    the mapping between them. Resolving it from the id's text before '@' would be a
    second source of truth for a fact the catalog already states."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "one@1", [1.0, 2.0])
    _target(results, "two@1", [1.0, 2.0])
    _mask(root, 2)
    _local_catalog(root, maps=[{"name": "T1", "unit": "s"}])
    _write_target(root, "one@1", models=["vfa_t1"], software="quit")
    _write_target(root, "two@1", models=["vfa_t1"], software="qmrlab")
    _comparability(root, [{
        "model": "vfa_t1", "maps": ["T1"], "pairs": [["quit", "qmrlab"]],
        "class": "related-estimator", "reason": "qi irtse fits two parameters",
    }])

    pair = analyze(results, root, reference="one@1")["comparisons"]["vfa_t1"]["T1"][0]

    assert pair["flag"] == "amber"
    assert pair["flag_reason"] == "qi irtse fits two parameters"


def test_an_undeclared_pair_is_same_estimator_and_the_numbers_decide(tmp_path):
    """The default is the assignable one. Making the safe-looking class the default
    would silence red everywhere by saying nothing (spec §5.5)."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 2.0, 3.0])
    _target(results, "b@1", [1.5, 3.0, 4.5])
    _mask(root, 3)
    _local_catalog(root, maps=[{"name": "T1", "unit": "s"}])
    _comparability(root, [{
        "model": "vfa_t1", "maps": ["T1"], "pairs": [["other", "software"]],
        "class": "incomparable", "reason": "about two entirely different targets",
    }])

    pair = analyze(results, root, reference="a@1")["comparisons"]["vfa_t1"]["T1"][0]

    assert pair["estimator_class"] == "same-estimator"
    assert pair["flag"] == "red"
    assert "relative median difference" in pair["flag_reason"]


def test_no_comparability_file_leaves_every_pair_scored_as_it_always_was(tmp_path):
    """An absent declaration is an empty one, not an error: the fourteen qMRLab-versus-
    qMRLab pairs predate the file and must keep being built and scored."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 2.0, 3.0])
    _target(results, "b@1", [1.0, 2.0, 3.0])
    _mask(root, 3)
    _local_catalog(root, maps=[{"name": "T1", "unit": "s"}])

    doc = analyze(results, root, reference="a@1")
    pair = doc["comparisons"]["vfa_t1"]["T1"][0]

    assert not (root / "comparability.yml").exists()
    assert pair["n"] == 3
    assert pair["estimator_class"] == "same-estimator"
    assert pair["flag"] == "green"


# --- scale-free maps (spec §7) -------------------------------------------------------

def test_an_au_map_is_compared_scale_free_because_its_amplitude_is_arbitrary(tmp_path):
    """vfa_t1/M0 and mono_t2/M0. The ratio of two arbitrary scales is arbitrary, so it
    is reported beside the row and explicitly not treated as a disagreement."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 2.0, 3.0], unit="au", name="M0")
    _target(results, "b@1", [10.0, 20.0, 30.0], unit="au", name="M0")
    _mask(root, 3)
    _local_catalog(root, maps=[{"name": "M0", "unit": "au"}])

    pair = analyze(results, root, reference="a@1")["comparisons"]["vfa_t1"]["M0"][0]

    assert pair["scale_free"] is True
    assert pair["scale_ratio_not_a_disagreement"] == 0.1
    assert pair["rel_median_diff"] == 0.0
    assert pair["flag"] == "green"


def test_a_b1_map_is_never_scale_free_even_though_its_records_say_au(tmp_path):
    """The trap spec §7 names outright. Every adapter reports B1map in 'au' while
    models/b1_*.yml declares 'fraction' (spec §5.3), so keying scale_free on the
    RECORD's unit would median-normalise a genuine ratio in which 1.0 means the nominal
    flip angle was reached — deleting a 10% transmit-calibration difference instead of
    measuring it."""
    results, root = tmp_path / "results", tmp_path / "root"
    # b@1 reports the same field 10% higher — a calibration difference, not a free scale.
    _target(results, "a@1", [1.0, 1.20, 1.40], unit="au", name="B1map")
    _target(results, "b@1", [1.1, 1.32, 1.54], unit="au", name="B1map")
    _mask(root, 3)
    _local_catalog(root, maps=[{"name": "B1map", "unit": "fraction"}])

    pair = analyze(results, root, reference="a@1")["comparisons"]["vfa_t1"]["B1map"][0]

    assert pair["scale_free"] is False
    assert pair["scale_ratio_not_a_disagreement"] is None
    # Normalised, this pair is rel_median_diff 0.0 and CCC 1.0 — green, the finding
    # deleted. Unnormalised it is the 9.1% offset it is, and CCC 0.8 flags it red.
    # 6 digits, not exact: the fixtures are float32 NIfTIs like a real adapter's.
    assert round(pair["rel_median_diff"], 6) == round(-0.1 / 1.1, 6)
    assert round(pair["ccc"], 6) == 0.8
    assert pair["flag"] == "red"


# --- MapSpec.comparison_range (spec §7.2) --------------------------------------------

_RANGED_T1 = [{"name": "T1", "unit": "s", "comparison_range": [0, 10]}]


def test_a_comparison_range_narrows_the_pair_and_nothing_else(tmp_path):
    """The same guarantee comparison_mask carries: statistics and the hash are computed
    over the model's published mask on the produced values, whatever the range says."""
    from harness.measure import voxel_sha256

    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 2.0, 1e6])
    _target(results, "b@1", [1.0, 2.0, 1e6])
    _mask(root, 3)
    _local_catalog(root, maps=_RANGED_T1)

    doc = analyze(results, root, reference="a@1")
    pair = doc["comparisons"]["vfa_t1"]["T1"][0]
    m = doc["records"][0]["maps"][0]

    assert pair["n"] == 2
    assert pair["n_out_of_range"] == 1
    assert pair["comparison_range"] == [0, 10]
    assert m["stats"]["n"] == 3
    assert m["stats"]["max"] == 1e6
    assert m["voxel_sha256"] == voxel_sha256(np.array([1.0, 2.0, 1e6]))


def test_one_side_out_of_range_removes_the_voxel_from_both(tmp_path):
    """A range is a claim about which values are physical, so a voxel only enters a
    comparison if BOTH maps put it inside: 34,683 s is not comparable to 0.9 s whichever
    implementation produced it."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 2.0, 0.9])
    _target(results, "b@1", [1.0, 2.0, 34683.0])
    _mask(root, 3)
    _local_catalog(root, maps=_RANGED_T1)

    pair = analyze(results, root, reference="a@1")["comparisons"]["vfa_t1"]["T1"][0]

    assert pair["n"] == 2
    assert pair["n_out_of_range"] == 1
    assert pair["max_abs_delta"] == 0.0


def test_the_exclusion_count_counts_only_what_the_range_excluded(tmp_path):
    """Not "every voxel the comparison did not use". A non-finite voxel was never in a
    comparison to begin with — compare_maps has always dropped it — and counting it
    here would report an exclusion the range did not make."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, float("nan"), 1e6, 2.0])
    _target(results, "b@1", [1.0, 5.0, 3.0, 2.0])
    _mask(root, 4)
    _local_catalog(root, maps=_RANGED_T1)

    pair = analyze(results, root, reference="a@1")["comparisons"]["vfa_t1"]["T1"][0]

    assert pair["n"] == 2
    assert pair["n_out_of_range"] == 1


def test_a_map_with_no_range_reports_the_absence_rather_than_omitting_it(tmp_path):
    """Both keys on every row whether declared or not: rows of two different shapes
    move the failure into whichever renderer reads the short one."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 1e6])
    _target(results, "b@1", [1.0, 1e6])
    _mask(root, 2)
    _local_catalog(root, maps=[{"name": "T1", "unit": "s"}])

    pair = analyze(results, root, reference="a@1")["comparisons"]["vfa_t1"]["T1"][0]

    assert pair["comparison_range"] is None
    assert pair["n_out_of_range"] == 0
    assert pair["n"] == 2


def test_the_range_acts_inside_the_comparison_mask_not_instead_of_it(tmp_path):
    """Two independent narrowings of one selection. Applying either alone would score
    a different voxel set than the one both declarations describe."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 2.0, 1e6, 4.0])
    _target(results, "b@1", [1.0, 2.0, 1e6, 4.0])
    _write_mask(root, "vfa_t1", [1, 1, 1, 1])
    _write_mask(root, "vfa_t1_interior", [1, 1, 1, 0])
    _local_catalog(
        root, maps=_RANGED_T1, comparison_mask="masks/vfa_t1_interior.nii.gz",
    )

    doc = analyze(results, root, reference="a@1")
    pair = doc["comparisons"]["vfa_t1"]["T1"][0]

    assert pair["n"] == 2  # 4 voxels, minus the one the mask drops and the one the range does
    assert pair["n_out_of_range"] == 1
    assert doc["records"][0]["maps"][0]["stats"]["n"] == 4


# --- MapSpec.scale_free_range (spec §7) ----------------------------------------------

_BOUNDED_M0 = [{"name": "M0", "unit": "au", "scale_free_range": [0, 10]}]


def test_a_scale_free_range_narrows_the_pair_and_nothing_else(tmp_path):
    """comparison_range's guarantee, on the other kind of map: the published statistics
    and the hash are computed over the model's full mask on the produced values, and a
    normalised bound may not touch either. This is what keeps declaring one from moving
    a number already on the site or a history.jsonl digest."""
    from harness.measure import voxel_sha256

    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 1.0, 1.0, 4000.0], unit="au", name="M0")
    _target(results, "b@1", [1.0, 1.0, 1.0, 4000.0], unit="au", name="M0")
    _mask(root, 4)
    _local_catalog(root, maps=_BOUNDED_M0)

    doc = analyze(results, root, reference="a@1")
    pair = doc["comparisons"]["vfa_t1"]["M0"][0]
    m = doc["records"][0]["maps"][0]

    assert pair["n"] == 3
    assert pair["n_out_of_range"] == 1
    assert m["stats"]["n"] == 4
    assert m["stats"]["max"] == 4000.0
    assert m["voxel_sha256"] == voxel_sha256(np.array([1.0, 1.0, 1.0, 4000.0]))


def test_the_two_ranges_are_published_under_their_own_names(tmp_path):
    """A reader must never have to work out which domain a pair of bounds is in, and
    the key name is the only place that can be said without a legend: comparison_range
    is in the map's canonical unit, scale_free_range in multiples of its masked median.
    Both keys on every row for _unmeasurable's reason, so a physical map says `null`
    here rather than omitting the field."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 1.0, 1.0, 4000.0], unit="au", name="M0")
    _target(results, "b@1", [1.0, 1.0, 1.0, 4000.0], unit="au", name="M0")
    _mask(root, 4)
    _local_catalog(root, maps=_BOUNDED_M0)

    free = analyze(results, root, reference="a@1")["comparisons"]["vfa_t1"]["M0"][0]

    assert free["scale_free"] is True
    assert free["scale_free_range"] == [0, 10]
    assert free["comparison_range"] is None

    results, root = tmp_path / "physical", tmp_path / "proot"
    _target(results, "a@1", [1.0, 2.0])
    _target(results, "b@1", [1.0, 2.0])
    _mask(root, 2)
    _local_catalog(root, maps=_RANGED_T1)

    physical = analyze(results, root, reference="a@1")["comparisons"]["vfa_t1"]["T1"][0]

    assert physical["scale_free"] is False
    assert physical["scale_free_range"] is None
    assert physical["comparison_range"] == [0, 10]


def test_an_au_map_that_declares_no_range_is_still_bounded(tmp_path):
    """The default is not "no bound". Every 'au' map is normalised and normalising does
    nothing about leverage, so a map added later without a declaration must not
    silently go back to letting two diverged voxels decide r and CCC."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 1.0, 1.0, 4000.0], unit="au", name="M0")
    _target(results, "b@1", [1.0, 1.0, 1.0, 4000.0], unit="au", name="M0")
    _mask(root, 4)
    _local_catalog(root, maps=[{"name": "M0", "unit": "au"}])

    pair = analyze(results, root, reference="a@1")["comparisons"]["vfa_t1"]["M0"][0]

    assert pair["scale_free_range"] == [0.0, 10.0]
    assert pair["n_out_of_range"] == 1


def test_two_diverged_voxels_no_longer_decide_the_flag_for_all_the_others(tmp_path):
    """The bug this fixed, at the shape it had on the published site: mono_t2/M0,
    qmrlab@master against qmrlab@v2.4.0, where two voxels of 27,417 reaching 219x their
    map's median took CCC to 0.129 and painted the pair red while the relative median
    difference read -0.3%. The exclusion is visible on the row, because an exclusion
    nobody can see is indistinguishable from a mask that never held those voxels."""
    results, root = tmp_path / "results", tmp_path / "root"
    # 41 voxels the two agree on exactly, plus the one where b's fit ran away. Enough of
    # them that the runaway barely moves b's median, which is the real map's situation:
    # the recovered scale ratio there is 1.003.
    agree = [round(0.80 + 0.01 * i, 2) for i in range(41)]
    _target(results, "a@1", agree + [1.0], unit="au", name="M0")
    _target(results, "b@1", agree + [219.0], unit="au", name="M0")
    _mask(root, 42)
    _local_catalog(root, maps=_BOUNDED_M0)

    doc = analyze(results, root, reference="a@1")
    pair = doc["comparisons"]["vfa_t1"]["M0"][0]

    assert pair["n"] == 41
    assert pair["n_out_of_range"] == 1
    assert pair["ccc"] > 0.9
    assert pair["flag"] == "green"


def test_the_scale_free_range_never_reaches_a_map_with_a_physical_unit(tmp_path):
    """The B1map trap one field further on. Every adapter reports B1map as 'au' while
    models/b1_*.yml declares 'fraction', so a range keyed on the RECORD's unit would
    threshold a genuine ratio against multiples of its median — and 1.0 there means the
    nominal flip angle was reached, not "the middle of this map"."""
    results, root = tmp_path / "results", tmp_path / "root"
    _target(results, "a@1", [1.0, 1.2, 40.0], unit="au", name="B1map")
    _target(results, "b@1", [1.0, 1.2, 40.0], unit="au", name="B1map")
    _mask(root, 3)
    _local_catalog(root, maps=[{"name": "B1map", "unit": "fraction"}])

    pair = analyze(results, root, reference="a@1")["comparisons"]["vfa_t1"]["B1map"][0]

    assert pair["scale_free"] is False
    assert pair["scale_free_range"] is None
    assert pair["n"] == 3
    assert pair["n_out_of_range"] == 0
