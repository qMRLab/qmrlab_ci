import pathlib

from harness.config import load_models, load_targets

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_all_fifteen_targets_are_declared():
    assert len(load_targets(ROOT)) == 15


def test_every_declared_model_exists_in_the_catalog():
    models = load_models(ROOT)

    for target in load_targets(ROOT).values():
        for model in target.models:
            assert model in models, f"{target.id} declares unknown model {model}"


def test_model_availability_matches_the_spec_matrix():
    """Spec §2.4. These holes are declared facts; discovering them at runtime would
    make a missing model indistinguishable from a broken install."""
    t = load_targets(ROOT)

    assert t["qmrlab@V1"].models == ("qmt_spgr",)
    assert "b1_afi" not in t["qmrlab@v2.4.1"].models
    assert "b1_afi" in t["qmrlab@v2.5.0"].models
    assert "mono_t2" not in t["qmrlab@v2.3.0"].models
    assert "mono_t2" in t["qmrlab@v2.4.0"].models
    assert "mt_ratio" not in t["qmrlab@v2.2.0"].models
    assert "mt_ratio" in t["qmrlab@v2.3.0"].models
    assert len(t["qmrlab@v2.0.0"].models) == 5


def test_every_matlab_target_declares_which_era_driver_runs_it():
    t = load_targets(ROOT)

    assert t["qmrlab@V1"].era == 1
    assert t["qmrlab@v2.0.5"].era == 2
    assert t["qmrlab@v2.1.0"].era == 3
    assert t["qmrust@main"].era is None


def test_matlab_release_pinning_follows_the_spec():
    t = load_targets(ROOT)

    assert t["qmrlab@V1"].matlab_release == "R2021a"
    assert t["qmrlab@v2.4.1"].matlab_release == "R2021a"
    assert t["qmrlab@v2.5.0"].matlab_release == "R2026a"
    assert t["qmrlab@master"].matlab_release == "latest"


def test_non_uniform_tag_names_are_declared_not_derived():
    """2.0.1 and 2.0.2 carry no v prefix while every other tag does."""
    t = load_targets(ROOT)

    assert t["qmrlab@v2.0.1"].source_ref == "2.0.1"
    assert t["qmrlab@v2.0.3"].source_ref == "v2.0.3"


def test_repeats_default_applies_and_qmt_is_overridden():
    target = load_targets(ROOT)["qmrlab@v3.0.0"]

    assert target.repeats_for("vfa_t1") == 5
    assert target.repeats_for("qmt_spgr") == 1
