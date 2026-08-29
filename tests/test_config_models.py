import pathlib

import pytest

from harness.config import ConfigError, load_models, load_sources

ROOT = pathlib.Path(__file__).resolve().parents[1]

EXPECTED_MODELS = {
    "qmt_spgr", "qmt_spgr_ramani", "inversion_recovery", "vfa_t1", "b1_dam",
    "b1_afi", "mono_t2", "mt_ratio", "mt_sat",
}


def test_catalog_declares_exactly_the_nine_models():
    assert set(load_models(ROOT)) == EXPECTED_MODELS


def test_the_two_qmt_streams_are_one_question_asked_twice():
    """Spec §2.2: qmt_spgr_ramani is qmt_spgr's dataset, mask and maps under a second
    id, because QUIT's `qi qmt` implements only Ramani while every qMRLab target and
    qmrust default to SledPikeRP. The sub-model is the ONLY difference, and it lives in
    the drivers — if these ever diverge here, the two streams stop being comparable and
    a sub-model result would be reporting a dataset or unit change instead."""
    models = load_models(ROOT)
    sledpike, ramani = models["qmt_spgr"], models["qmt_spgr_ramani"]

    assert ramani.id != sledpike.id
    assert ramani.dataset == sledpike.dataset
    assert ramani.mask == sledpike.mask
    assert ramani.maps == sledpike.maps


def test_every_model_maps_to_a_declared_dataset():
    models, sources = load_models(ROOT), load_sources(ROOT)

    for model in models.values():
        assert model.dataset in sources, f"{model.id} -> unknown dataset {model.dataset}"


def test_dataset_names_differ_from_model_ids_where_expected():
    """Five of nine differ; the coincidences must not be mistaken for a rule."""
    models = load_models(ROOT)

    assert models["inversion_recovery"].dataset == "ir"
    assert models["qmt_spgr"].dataset == "qmt"
    assert models["qmt_spgr_ramani"].dataset == "qmt"
    assert models["mt_ratio"].dataset == "mtr"
    assert models["mt_sat"].dataset == "mtsat"


def test_all_eight_archives_are_checksummed():
    # Still eight: nine models draw on eight datasets, because both qMT streams
    # fit the same `qmt` archive.
    for source in load_sources(ROOT).values():
        assert len(source.sha256) == 64
        assert source.bytes > 0


def test_map_missing_a_unit_is_a_config_error_not_a_keyerror(tmp_path):
    """A schema violation aborts the whole run, so it must arrive as the declared
    error type with a location — never as a bare KeyError from dict indexing."""
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "broken.yml").write_text(
        "id: broken\ndataset: ir\nmask: masks/broken.nii.gz\nmaps: [{name: T1}]\n"
    )

    with pytest.raises(ConfigError, match="maps\\[0\\].*unit"):
        load_models(tmp_path)


def test_model_missing_a_required_field_is_a_config_error(tmp_path):
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "broken.yml").write_text(
        "id: broken\ndataset: ir\nmaps: []\n"
    )

    with pytest.raises(ConfigError, match="mask"):
        load_models(tmp_path)


def test_no_scale_free_map_declares_a_comparison_range():
    """A map whose unit is 'au' has a free amplitude, so its comparison normalises each
    side by its own masked median (spec §7). A bound on an arbitrary scale would bound
    the arbitrariness, not the physics, and would exclude voxels for having been written
    by a software that scales M0 differently — which is the one thing the normalisation
    exists to stop being a finding."""
    for model in load_models(ROOT).values():
        for m in model.maps:
            if m.unit == "au":
                assert m.comparison_range is None, f"{model.id}/{m.name}"


def test_every_map_that_can_carry_a_range_declares_one():
    """The catalog is complete, not partially migrated. A map with no declared range is
    compared over every voxel of its mask including the diverged ones, so a model added
    later without one would quietly reintroduce the failure of spec §7.2 — CCC destroyed
    by a few voxels while the median difference reads 0.0. If some future map genuinely
    has no physical bound, this test is where that decision gets recorded."""
    undeclared = [
        f"{model.id}/{m.name}"
        for model in load_models(ROOT).values()
        for m in model.maps
        if m.unit != "au" and m.comparison_range is None
    ]

    assert undeclared == []


def test_every_declared_range_is_ordered_and_contains_a_physical_value():
    """A range that excluded its own model's typical value would be a selection nobody
    could read as physical. Anchored on one plausible in-vivo value per unit rather
    than on measured data, so this checks the DECLARATION and not whichever run happens
    to be sitting in results/."""
    plausible = {
        "s": 0.9,          # a T1/T2 in seconds, well inside every declared bound
        "s^-1": 1.1,       # its rate
        "percent": 2.5,    # MTsat p.u. / MTR percent
        "fraction": 0.16,  # bound-pool fraction, B1 near nominal
    }
    for model in load_models(ROOT).values():
        for m in model.maps:
            if m.comparison_range is None:
                continue
            lo, hi = m.comparison_range
            assert lo < hi, f"{model.id}/{m.name}"
            # T2r's microseconds are the one map whose physical value is nowhere near
            # any of the above, and its bound is three orders smaller for that reason.
            value = 1.2e-5 if m.name == "T2r" else plausible[m.unit]
            assert lo <= value <= hi, f"{model.id}/{m.name} excludes {value}"


def test_only_the_derived_models_declare_a_comparison_mask():
    """Spec §7.2, and it must agree with scripts/derive_masks.py's INTERIOR_FROM: an
    interior mask exists only where that script writes one. Five models ship the
    archive's own mask, which is already anatomical, and b1_dam is derived but
    deliberately has none — a single 64x64 slice the phantom fills has no background to
    cut, and Otsu on SFalpha would keep an annulus. Declaring a comparison_mask that no
    run produces would fail the whole analysis at the comparison pass, i.e. after every
    fit in the matrix had already run."""
    declared = {
        model.id for model in load_models(ROOT).values()
        if model.comparison_mask is not None
    }

    assert declared == {"mt_sat", "b1_afi"}
