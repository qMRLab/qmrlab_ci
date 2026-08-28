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
