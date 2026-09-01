"""The four schema extensions the cross-software design adds (§4.1, §5.2, §7.2).

Kept apart from test_config_models.py and test_config_targets.py, which assert what the
committed catalog says. Every field is optional, so almost everything here is written
against a synthetic catalog: what the shipped files happen to declare belongs in the
catalog tests, which move when the catalog does.
"""
import pathlib

import pytest
import yaml

from harness.config import (
    DEFAULT_SCALE_FREE_RANGE,
    KNOWN_LANES,
    ConfigError,
    load_models,
    load_targets,
)

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


# --- MapSpec.comparison_range (spec §7.2) --------------------------------------------

def test_a_map_that_declares_no_comparison_range_gets_none(tmp_path):
    """Additive like `transform`: a map that says nothing about it is compared over
    exactly the voxels it was compared over before the field existed."""
    models = _model(tmp_path, maps=[{"name": "T1", "unit": "s"}])

    assert models["m"].maps[0].comparison_range is None


def test_a_declared_range_is_carried_onto_the_map_as_floats(tmp_path):
    """Floats, not the ints the YAML says: the bound is compared against float64 voxel
    values, and a mixed-type tuple would make `[0, 10]` and `[0.0, 10.0]` two different
    declarations of one range."""
    models = _model(
        tmp_path, maps=[{"name": "T1", "unit": "s", "comparison_range": [0, 10]}]
    )

    assert models["m"].maps[0].comparison_range == (0.0, 10.0)


def test_a_range_that_is_not_two_bounds_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match=r"broken\.yml.*'T1'.*comparison_range.*two"):
        _model(
            tmp_path, id="broken",
            maps=[{"name": "T1", "unit": "s", "comparison_range": [0, 5, 10]}],
        )


def test_a_range_declared_backwards_is_a_config_error(tmp_path):
    """lo >= hi selects nothing, and an empty comparison publishes as "no comparable
    voxels" — a typo that reads on the site as two maps having nothing in common."""
    with pytest.raises(ConfigError, match=r"broken\.yml.*'T1'.*lo < hi"):
        _model(
            tmp_path, id="broken",
            maps=[{"name": "T1", "unit": "s", "comparison_range": [10, 0]}],
        )


def test_a_non_numeric_bound_is_a_config_error_naming_the_file_and_the_map(tmp_path):
    with pytest.raises(ConfigError, match=r"broken\.yml.*'T1'.*numbers.*'ten'"):
        _model(
            tmp_path, id="broken",
            maps=[{"name": "T1", "unit": "s", "comparison_range": [0, "ten"]}],
        )


def test_a_boolean_bound_is_refused_rather_than_read_as_zero(tmp_path):
    """bool is an int subclass, so `[false, 10]` would otherwise pass as [0, 10] — a
    YAML typo that reads as a deliberate physical bound and silently is one."""
    with pytest.raises(ConfigError, match=r"broken\.yml.*'T1'.*numbers"):
        _model(
            tmp_path, id="broken",
            maps=[{"name": "T1", "unit": "s", "comparison_range": [False, 10]}],
        )


def test_a_nan_bound_is_refused(tmp_path):
    """Every comparison with NaN is False, so a NaN bound excludes every voxel while
    looking like a declared range. It is refused by the same `lo < hi` check, which is
    written in that direction for exactly this reason."""
    (tmp_path / "models").mkdir(exist_ok=True)
    (tmp_path / "models" / "broken.yml").write_text(
        "id: broken\ndataset: ir\nmask: masks/m.nii.gz\n"
        "maps: [{name: T1, unit: s, comparison_range: [.nan, 10]}]\n"
    )

    with pytest.raises(ConfigError, match=r"broken\.yml.*'T1'.*lo < hi"):
        load_models(tmp_path)


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


# --- MapSpec.scale_free_range (spec §7) ----------------------------------------------

def test_the_scale_free_predicate_is_the_canonical_unit_and_lives_on_the_map(tmp_path):
    """One predicate, one place. analyze keys the normalisation on it and config keys
    the validation of scale_free_range on it, and if those two ever disagreed a map
    could be normalised without being allowed a normalised bound, or the reverse."""
    models = _model(
        tmp_path,
        maps=[{"name": "M0", "unit": "au"}, {"name": "T1", "unit": "s"}],
    )

    assert models["m"].maps[0].scale_free is True
    assert models["m"].maps[1].scale_free is False


def test_a_scale_free_map_that_declares_no_range_still_gets_one(tmp_path):
    """Unlike comparison_range, an absent declaration is a default rather than "no
    bound". Every 'au' map is normalised, and normalising does nothing about leverage:
    an undefaulted map added later would silently reintroduce the failure the field
    exists to remove — two diverged voxels deciding r and CCC for 27,000 others."""
    models = _model(tmp_path, maps=[{"name": "M0", "unit": "au"}])

    assert models["m"].maps[0].scale_free_range == DEFAULT_SCALE_FREE_RANGE


def test_a_declared_scale_free_range_wins_and_is_carried_as_floats(tmp_path):
    """Floats for comparison_range's reason: the bound is compared against float64
    voxel values, and [0, 5] and [0.0, 5.0] must not be two declarations of one range."""
    models = _model(
        tmp_path, maps=[{"name": "M0", "unit": "au", "scale_free_range": [0, 5]}]
    )

    assert models["m"].maps[0].scale_free_range == (0.0, 5.0)


def test_a_physical_map_carries_no_scale_free_range_at_all(tmp_path):
    """Non-None on exactly the maps the range will be applied to. A physical map
    holding a normalised bound nothing reads is a field waiting to be read by mistake."""
    models = _model(tmp_path, maps=[{"name": "T1", "unit": "s"}])

    assert models["m"].maps[0].scale_free_range is None


def test_a_physical_range_on_an_arbitrary_amplitude_is_a_config_error(tmp_path):
    """The bound would be a bound on whichever scale the software chose, so it would
    exclude voxels for a reason the normalisation exists to stop being a finding.
    Refused rather than ignored: an ignored range publishes a red flag computed over a
    voxel selection nobody declared."""
    with pytest.raises(
        ConfigError, match=r"broken\.yml.*'M0'.*comparison_range cannot.*'au'"
    ):
        _model(
            tmp_path, id="broken",
            maps=[{"name": "M0", "unit": "au", "comparison_range": [0, 10]}],
        )


def test_a_normalised_range_on_a_physical_map_is_a_config_error(tmp_path):
    """The mirror, and the more dangerous direction: [0, 10] on a T1 in seconds reads
    as a physical bound and would silently become "within 10x the median T1"."""
    with pytest.raises(
        ConfigError, match=r"broken\.yml.*'T1'.*scale_free_range.*masked median.*'s'"
    ):
        _model(
            tmp_path, id="broken",
            maps=[{"name": "T1", "unit": "s", "scale_free_range": [0, 10]}],
        )


def test_a_malformed_scale_free_range_names_that_field_and_not_the_other_one(tmp_path):
    """Two range fields in two domains, so "which range is malformed" is half the
    answer; a message naming comparison_range would send the reader to the wrong line."""
    with pytest.raises(
        ConfigError, match=r"broken\.yml.*'M0'.*scale_free_range must have lo < hi"
    ):
        _model(
            tmp_path, id="broken",
            maps=[{"name": "M0", "unit": "au", "scale_free_range": [10, 0]}],
        )


def test_a_non_numeric_scale_free_bound_is_a_config_error(tmp_path):
    with pytest.raises(
        ConfigError, match=r"broken\.yml.*'M0'.*scale_free_range bounds.*'ten'"
    ):
        _model(
            tmp_path, id="broken",
            maps=[{"name": "M0", "unit": "au", "scale_free_range": [0, "ten"]}],
        )


def test_a_nan_scale_free_bound_is_refused(tmp_path):
    """Every comparison with NaN is False, so a NaN bound would exclude every voxel
    while looking like a declared range — and on a scale-free map that reads as two
    softwares having no comparable voxels rather than as a typo."""
    (tmp_path / "models").mkdir(exist_ok=True)
    (tmp_path / "models" / "broken.yml").write_text(
        "id: broken\ndataset: ir\nmask: masks/m.nii.gz\n"
        "maps: [{name: M0, unit: au, scale_free_range: [0, .nan]}]\n"
    )

    with pytest.raises(ConfigError, match=r"broken\.yml.*'M0'.*lo < hi"):
        load_models(tmp_path)
