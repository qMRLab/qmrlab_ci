import pathlib

from harness.config import load_targets
from harness.matrix import build_matrices

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_matrices_are_split_by_lane():
    m = build_matrices(load_targets(ROOT))

    assert {e["id"] for e in m["native"]} == {"qmrust@main"}
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
