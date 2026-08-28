"""protocols/ is the one source of truth for acquisition parameters (spec §6.1).

These tests guard the two properties that make it worth having. First, coverage: a model
whose dataset has no protocol entry would send each adapter back to transcribing values
out of the archive on its own, which is the duplication the directory exists to end.
Second, units: every value states its own, because seconds-versus-milliseconds is a live
source of error across these tools rather than a hypothetical one — SCT 7.3 is
inconsistent with itself about it, `sct_compute_mtsat` taking seconds while
`sct_compute_ernst_angle` takes milliseconds.
"""
import pathlib

import pytest
import yaml

from harness.config import load_models, load_sources

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROTOCOLS = sorted((ROOT / "protocols").glob("*.yml"))

# Times are seconds throughout protocols/, so 'ms' is deliberately NOT here: an entry
# transcribed straight out of an archive that records milliseconds fails this test rather
# than reaching an adapter as a number a thousand times too large. Converting once, at the
# point of transcription, is the only place the conversion is reviewable against the
# archive's own Format string.
KNOWN_UNITS = {"s", "Hz", "degree", "none"}


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def _parameters(path: pathlib.Path):
    """Every (name, spec) pair in one protocol file. A dataset with no acquisition
    parameters at all — mt_ratio reads none — declares an empty mapping, which is a
    statement, where a missing `parameters:` key would be an omission."""
    doc = _load(path)
    params = doc.get("parameters")
    assert isinstance(params, dict), f"{path}: parameters must be a mapping"
    return sorted(params.items())


def test_the_protocols_directory_is_not_empty():
    """Every assertion below is a loop over PROTOCOLS, so an empty directory would make
    the whole file pass while proving nothing."""
    assert PROTOCOLS


def test_every_model_dataset_has_a_protocol_entry():
    """The coverage rule, and the reason this file exists: a future model cannot land
    without one. Keyed on the dataset rather than the model because two models can share
    an archive — both qMT streams fit `qmt` — and the acquisition is a property of the
    scan, not of the fit run over it."""
    covered = {_load(p)["dataset"] for p in PROTOCOLS}

    for model in load_models(ROOT).values():
        assert model.dataset in covered, (
            f"models/{model.id}.yml declares dataset {model.dataset!r} with no "
            f"protocols/{model.dataset}.yml"
        )


def test_each_file_declares_the_dataset_its_name_claims():
    """Adapters resolve a protocol by dataset id, so a file whose contents disagree with
    its filename would be silently unreachable — and the dataset it does declare would
    then have two entries, one of them never read."""
    for path in PROTOCOLS:
        assert _load(path)["dataset"] == path.stem


def test_every_protocol_names_a_dataset_the_repo_actually_fetches():
    """One-directional on purpose: data/sources.yml carries datasets whose parameters
    travel as sidecars inside the archive (the rrsg_* pair), so a source without a
    protocol is expected. A protocol without a source is a typo."""
    sources = load_sources(ROOT)

    for path in PROTOCOLS:
        dataset = _load(path)["dataset"]
        assert dataset in sources, f"{path}: no data/sources.yml entry for {dataset!r}"


def test_every_value_declares_a_known_unit():
    for path in PROTOCOLS:
        for name, spec in _parameters(path):
            unit = spec.get("unit")
            assert unit in KNOWN_UNITS, (
                f"{path} ({name}): unit must be one of {sorted(KNOWN_UNITS)}, "
                f"got {unit!r}"
            )


def test_every_parameter_carries_exactly_one_value_or_one_list():
    """Both would leave which one an adapter reads to that adapter; neither is a unit
    declaration with nothing under it."""
    for path in PROTOCOLS:
        for name, spec in _parameters(path):
            has = {"value", "values"} & set(spec)
            assert len(has) == 1, (
                f"{path} ({name}): declare exactly one of value/values, got {sorted(has)}"
            )


def test_no_parameter_declares_an_empty_list():
    """An empty list renders as a protocol with zero volumes, which fails at fit time far
    from the file that caused it."""
    for path in PROTOCOLS:
        for name, spec in _parameters(path):
            if "values" in spec:
                assert spec["values"], f"{path} ({name}): empty values list"


def test_dimensioned_values_are_numbers():
    """A quantity with a real unit that arrives as a string is a quoted number, and it
    would reach an adapter as one — YAML would hand `'0.028'` straight through to a
    config renderer that formats it back out unchanged. Categorical values (`unit: none`)
    are exempt: the qMT pulse shape is genuinely a name."""
    for path in PROTOCOLS:
        for name, spec in _parameters(path):
            if spec["unit"] == "none":
                continue
            values = spec["values"] if "values" in spec else [spec["value"]]
            for value in values:
                assert isinstance(value, (int, float)) and not isinstance(value, bool), (
                    f"{path} ({name}): {value!r} is not a number"
                )


def test_the_qmt_saturation_lists_stay_row_aligned():
    """The angle and offset lists are one table split in two, and index i of each is one
    measurement — the volume order of MTdata's 4th dimension. Lists of different lengths
    would silently pair the wrong angle with the wrong offset for every measurement after
    the first mismatch, and the fit would still produce six maps."""
    params = dict(_parameters(ROOT / "protocols" / "qmt.yml"))

    assert len(params["saturation_flip_angle"]["values"]) == len(
        params["saturation_offset"]["values"]
    )


def test_the_qmt_repetition_time_is_the_sum_of_its_four_intervals():
    """qmt_spgr.m re-imposes TR = Tmt + Ts + Tp + Tr in UpdateFields, so a TR transcribed
    here that does not satisfy it is one qMRLab would silently overwrite — leaving the
    adapters that trust this file rendering a TR no qMRLab target ever fits."""
    params = dict(_parameters(ROOT / "protocols" / "qmt.yml"))
    parts = [
        "mt_pulse_duration",
        "mt_to_excitation_delay",
        "excitation_pulse_duration",
        "post_excitation_delay",
    ]

    assert sum(params[p]["value"] for p in parts) == pytest.approx(
        params["repetition_time"]["value"]
    )


def test_the_b1_dam_second_angle_is_twice_the_first():
    """The double-angle identity is the entire estimate: B1 = acos(S2/(2*S1)) holds only
    when the second acquisition's nominal angle is exactly twice the first's. The archive
    records only the first angle, so the second one written here is the one thing in that
    file nothing upstream can contradict."""
    angles = dict(_parameters(ROOT / "protocols" / "b1_dam.yml"))["flip_angle"]["values"]

    assert angles[1] == 2 * angles[0]
