import pathlib

import pytest

from harness.config import ConfigError, load_models, load_sources

ROOT = pathlib.Path(__file__).resolve().parents[1]

EXPECTED_MODELS = {
    "qmt_spgr", "inversion_recovery", "vfa_t1", "b1_dam",
    "b1_afi", "mono_t2", "mt_ratio", "mt_sat",
}


def test_catalog_declares_exactly_the_eight_models():
    assert set(load_models(ROOT)) == EXPECTED_MODELS


def test_every_model_maps_to_a_declared_dataset():
    models, sources = load_models(ROOT), load_sources(ROOT)

    for model in models.values():
        assert model.dataset in sources, f"{model.id} -> unknown dataset {model.dataset}"


def test_dataset_names_differ_from_model_ids_where_expected():
    """Four of eight differ; the coincidences must not be mistaken for a rule."""
    models = load_models(ROOT)

    assert models["inversion_recovery"].dataset == "ir"
    assert models["qmt_spgr"].dataset == "qmt"
    assert models["mt_ratio"].dataset == "mtr"
    assert models["mt_sat"].dataset == "mtsat"


def test_all_eight_archives_are_checksummed():
    for source in load_sources(ROOT).values():
        assert len(source.sha256) == 64
        assert source.bytes > 0


def test_model_missing_a_required_field_is_a_config_error(tmp_path):
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "broken.yml").write_text(
        "id: broken\ndataset: ir\nmaps: []\n"
    )

    with pytest.raises(ConfigError, match="mask"):
        load_models(tmp_path)
