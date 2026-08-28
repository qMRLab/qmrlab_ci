"""The three schema extensions the cross-software design adds (§4.1, §5.2, §7.2).

Kept apart from test_config_models.py and test_config_targets.py, which assert what the
committed catalog says. All three fields are optional, so almost everything here is
written against a synthetic catalog: asserting that no shipped file declares one would
only hold until the first one does.
"""
import pathlib

import pytest
import yaml

from harness.config import KNOWN_LANES, ConfigError, load_models, load_targets

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _model(tmp_path, **doc):
    """Write one models/<id>.yml and load the catalog it forms."""
    (tmp_path / "models").mkdir(exist_ok=True)
    doc = {"id": "m", "dataset": "ir", "mask": "masks/m.nii.gz", **doc}
    (tmp_path / "models" / f"{doc['id']}.yml").write_text(yaml.safe_dump(doc))
    return load_models(tmp_path)


def _target(tmp_path, **doc):
    doc = {
        "id": "t@1", "software": "s", "version": "1",
        "source": {"repo": "x/y", "ref": "main"}, "models": ["vfa_t1"], **doc,
    }
    path = tmp_path / "targets" / doc["id"] / "target.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc))
    return load_targets(tmp_path)


# --- MapSpec.transform (spec §5.2) ---------------------------------------------------

def test_a_map_that_declares_no_transform_gets_none(tmp_path):
    """The field is additive: a map that says nothing about it reads exactly as it did,
    which is why no committed models/*.yml had to move to add it."""
    models = _model(tmp_path, maps=[{"name": "T1", "unit": "s"}])

    assert models["m"].maps[0].transform is None


def test_a_reciprocal_transform_is_carried_onto_the_map(tmp_path):
    models = _model(
        tmp_path, maps=[{"name": "T1", "unit": "s", "transform": "reciprocal"}]
    )

    assert models["m"].maps[0].transform == "reciprocal"
    assert models["m"].maps[0].unit == "s"


def test_an_unknown_transform_is_a_config_error_naming_the_file_and_the_map(tmp_path):
    """Strict like an unknown unit: a transform quietly ignored publishes rates as
    times, and the numbers stay entirely plausible while being their own reciprocal."""
    with pytest.raises(ConfigError, match=r"broken\.yml.*maps\[1\].*'T1'.*'invert'"):
        _model(
            tmp_path, id="broken",
            maps=[{"name": "MTsat", "unit": "percent"},
                  {"name": "T1", "unit": "s", "transform": "invert"}],
        )


def test_reciprocal_on_a_unit_with_no_named_reciprocal_is_a_config_error(tmp_path):
    """'percent^-1' is not a unit units.py can name, so the declaration is refused
    rather than guessed at."""
    with pytest.raises(ConfigError, match=r"maps\[0\].*'MTsat'.*reciprocal.*'percent'"):
        _model(
            tmp_path, id="broken",
            maps=[{"name": "MTsat", "unit": "percent", "transform": "reciprocal"}],
        )


# --- ModelSpec.comparison_mask (spec §7.2) -------------------------------------------

def test_every_comparison_mask_the_catalog_declares_exists_on_disk():
    """Vacuous until a model declares one, and the point is that it stops being so.
    A typo in the path would otherwise surface only once analyze reached the
    comparison pass, i.e. after every fit in the matrix had already run."""
    for model in load_models(ROOT).values():
        if model.comparison_mask is not None:
            assert (ROOT / model.comparison_mask).is_file(), model.id


def test_a_model_that_declares_no_comparison_mask_gets_none(tmp_path):
    models = _model(tmp_path, maps=[{"name": "T1", "unit": "s"}])

    assert models["m"].comparison_mask is None


def test_a_declared_comparison_mask_is_loaded_alongside_the_stats_mask(tmp_path):
    models = _model(
        tmp_path, maps=[{"name": "T1", "unit": "s"}],
        comparison_mask="masks/m_interior.nii.gz",
    )

    assert models["m"].mask == "masks/m.nii.gz"
    assert models["m"].comparison_mask == "masks/m_interior.nii.gz"


def test_an_empty_comparison_mask_is_a_config_error_not_a_silent_fallback(tmp_path):
    """Falling back to `mask` here would publish the permissive-mask number under the
    strict mask's name — the exact confusion the field exists to remove."""
    with pytest.raises(ConfigError, match=r"broken\.yml.*comparison_mask"):
        _model(
            tmp_path, id="broken", maps=[{"name": "T1", "unit": "s"}],
            comparison_mask="",
        )


# --- the `native` lane (spec §4.1) ---------------------------------------------------

def test_native_is_a_known_lane():
    assert "native" in KNOWN_LANES


def test_a_native_target_needs_no_matlab_release_and_no_era(tmp_path):
    """The lane names the ABSENCE of a shared toolchain step, so the only fields it
    requires are the ones every target has: its own setup.sh does the rest."""
    targets = _target(tmp_path, lane="native")

    assert targets["t@1"].lane == "native"
    assert targets["t@1"].era is None
    assert targets["t@1"].matlab_release is None


def test_an_unknown_lane_is_still_refused(tmp_path):
    with pytest.raises(ConfigError, match="lane must be one of"):
        _target(tmp_path, lane="conda")
