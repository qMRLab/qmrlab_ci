import pathlib

from harness.config import load_models, load_targets

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_every_declared_target_is_loadable_and_the_families_are_what_we_think():
    """Counted by software family rather than as one total.

    A bare `== 15` was fine while every target was qMRLab plus qmrust, but it says nothing
    about WHICH target went missing, and a cross-software benchmark's interesting failure
    is a whole family vanishing rather than the count being off by one.
    """
    targets = load_targets(ROOT)

    families: dict[str, int] = {}
    for target in targets.values():
        families[target.software] = families.get(target.software, 0) + 1

    assert families["qmrlab"] == 14
    assert families["qmrust"] == 1
    assert families["sct"] == 1
    assert len(targets) == sum(families.values())


def test_every_declared_model_exists_in_the_catalog():
    models = load_models(ROOT)

    for target in load_targets(ROOT).values():
        for model in target.models:
            assert model in models, f"{target.id} declares unknown model {model}"


def test_model_availability_matches_the_spec_matrix():
    """Spec §2.4. These holes are declared facts; discovering them at runtime would
    make a missing model indistinguishable from a broken install."""
    t = load_targets(ROOT)

    # V1 contributes qMT and nothing else, but BOTH sub-model streams of it. The Ramani
    # stream is not a capability V1 gained -- 'Model' has been selectable since qMTLab --
    # it is a second fit of the same data this benchmark now asks every target for.
    assert t["qmrlab@V1"].models == ("qmt_spgr", "qmt_spgr_ramani")
    assert "b1_afi" not in t["qmrlab@v2.4.1"].models
    assert "b1_afi" in t["qmrlab@v2.5.0"].models
    assert "mono_t2" not in t["qmrlab@v2.3.0"].models
    assert "mono_t2" in t["qmrlab@v2.4.0"].models
    assert "mt_ratio" not in t["qmrlab@v2.2.0"].models
    assert "mt_ratio" in t["qmrlab@v2.3.0"].models
    assert len(t["qmrlab@v2.0.0"].models) == 6

    # Every target that fits qMT fits both streams. Asserted as a pair rather than per
    # target: the streams differ only in FitOpt.model, so a target carrying one without
    # the other is a wiring slip, and it would surface as an unexplained hole in the
    # cross-software qMT comparison rather than as the mistake it is.
    for target in t.values():
        assert ("qmt_spgr" in target.models) == ("qmt_spgr_ramani" in target.models), (
            f"{target.id} declares only one of the two qMT streams"
        )


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
