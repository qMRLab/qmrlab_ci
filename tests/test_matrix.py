import pathlib

from harness.config import load_targets
from harness.matrix import build_matrices

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_matrices_are_split_by_lane():
    m = build_matrices(load_targets(ROOT))

    assert {e["id"] for e in m["rust"]} == {"qmrust@main"}
    assert len(m["matlab"]) == 14


def test_matlab_entries_carry_what_setup_matlab_needs():
    m = build_matrices(load_targets(ROOT))
    entry = next(e for e in m["matlab"] if e["id"] == "qmrlab@v2.5.0")

    assert entry["matlab_release"] == "R2026a"
    assert "Optimization_Toolbox" in entry["matlab_products"]
    assert entry["source_ref"] == "v2.5.0"


def test_matlab_entries_carry_the_era_and_serialized_repeats():
    import json

    m = build_matrices(load_targets(ROOT))
    entry = next(e for e in m["matlab"] if e["id"] == "qmrlab@V1")

    assert entry["era"] == 1
    assert json.loads(entry["repeats_json"])["qmt_spgr"] == 1


def test_entries_are_json_safe_scalars():
    """GitHub Actions matrix values must survive a JSON round trip through fromJSON."""
    import json

    json.dumps(build_matrices(load_targets(ROOT)))


def test_every_known_lane_has_a_key_even_when_empty():
    """The workflow guards each fit job on `<lane> != '[]'`, so a lane with no targets
    must still produce an empty list rather than a missing output."""
    from harness.config import KNOWN_LANES

    m = build_matrices(load_targets(ROOT))

    assert set(m) == set(KNOWN_LANES)
    assert m["python"] == []
    # `native` is in that set from the moment the lane is named, before any target
    # declares it: an absent output reads to the workflow as a skipped job, which is
    # indistinguishable from a lane that simply has no work (spec §4.1).
    assert "native" in m


def test_a_native_target_lands_in_its_own_lane_carrying_no_toolchain_fields():
    """§4.1: the native lane supplies checkout, Python, data and a cache — nothing
    else — so an entry must not smuggle in the MATLAB-only setup fields."""
    from harness.config import TargetSpec

    quit_target = TargetSpec(
        id="quit@v3.4", software="quit", version="v3.4", lane="native",
        era=None, matlab_release=None, matlab_products=(),
        source_repo="spinicist/QUIT", source_ref="v3.4",
        models=("mt_ratio", "mt_sat"), repeats={"default": 1},
    )

    m = build_matrices({quit_target.id: quit_target})
    entry = m["native"][0]

    assert entry["id"] == "quit@v3.4"
    assert entry["source_ref"] == "v3.4"
    assert entry["models"] == ["mt_ratio", "mt_sat"]
    assert "era" not in entry
    assert "matlab_release" not in entry
    assert "matlab_products" not in entry
