"""Loading and validating the repository's declared configuration.

A schema violation here aborts the whole run (spec §10): every downstream number
depends on these files being right, so a partial run computed from a malformed
catalog would be worse than no run.
"""
from __future__ import annotations

import dataclasses
import pathlib

import yaml


class ConfigError(Exception):
    """A declared configuration file is missing a field or has a bad value."""


# The only transform a map may declare. It is not a unit conversion and must never
# become one: units.py's table is linear on purpose, and a reciprocal cannot be written
# as a factor. A second software reports the same physical quantity as its inverse --
# QUIT writes MTSat_R1 in s^-1 where models/mt_sat.yml declares T1 in s -- and without
# a name for that relation the mismatch reaches the site as "analysis failed:
# ValueError", i.e. a schema gap wearing a fit failure's clothes (spec §5.2).
KNOWN_TRANSFORMS = ("reciprocal",)

# The reciprocal-domain unit of each canonical unit a `reciprocal` map may be declared
# on. NOT a conversion table -- units.py owns those -- it names the domain the linear
# scale has to land in before the inversion happens. Only 's' is listed because 's' is
# the only canonical unit in the catalog whose reciprocal the unit table can even name
# ('s^-1', and 'Hz' through it); `reciprocal` on 'percent' or 'au' is a schema
# violation rather than a conversion the harness should invent.
RECIPROCAL_UNIT = {"s": "s^-1"}


@dataclasses.dataclass(frozen=True)
class MapSpec:
    name: str
    unit: str
    # None means "the produced value already IS this quantity", which is every map in
    # the catalog today. Defaulted rather than required so no models/*.yml has to move.
    transform: str | None = None


@dataclasses.dataclass(frozen=True)
class ModelSpec:
    id: str
    dataset: str
    mask: str
    maps: tuple[MapSpec, ...]
    # A second, stricter mask used ONLY for the cross-software comparison statistics
    # (spec §7.2). `mask` keeps producing the published stats and the hash, so
    # declaring one moves no number already on the site and no history.jsonl digest.
    # It exists because masks/mt_sat.nii.gz keeps 95.2% of voxels, and the near-
    # background region it keeps is where the softwares differ by convention rather
    # than by fit -- SCT clips R1 < 0.01 to T1 = 0, qMRLab leaves T1 = Inf. A red flag
    # computed there would be measuring three background conventions, not three fits.
    comparison_mask: str | None = None


@dataclasses.dataclass(frozen=True)
class SourceSpec:
    name: str
    url: str
    sha256: str
    bytes: int


def _require(doc: dict, key: str, where: str):
    if key not in doc:
        raise ConfigError(f"{where}: missing required field {key!r}")
    return doc[key]


def _optional_path(doc: dict, key: str, where: str) -> str | None:
    """An absent path is a declared default; a present but empty one is a typo.

    Silently treating `comparison_mask:` with no value as "unset" would publish the
    permissive-mask number under the strict mask's name, which is the failure mode this
    whole field exists to remove.
    """
    if key not in doc:
        return None
    value = doc[key]
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: {key} must be a non-empty path, got {value!r}")
    return value


def _map_spec(doc: dict, where: str) -> MapSpec:
    name = _require(doc, "name", where)
    unit = _require(doc, "unit", where)

    transform = doc.get("transform")
    if transform is not None:
        # Unknown values raise for units.py's reason, which applies verbatim here: an
        # ignored transform leaves numbers that look entirely plausible on a site and
        # are wrong by their own reciprocal.
        if transform not in KNOWN_TRANSFORMS:
            raise ConfigError(
                f"{where} ({name!r}): transform must be one of {KNOWN_TRANSFORMS}, "
                f"got {transform!r}"
            )
        if transform == "reciprocal" and unit not in RECIPROCAL_UNIT:
            raise ConfigError(
                f"{where} ({name!r}): transform 'reciprocal' cannot be declared on "
                f"unit {unit!r}; only {sorted(RECIPROCAL_UNIT)} have a reciprocal the "
                "unit table can name"
            )
    return MapSpec(name=name, unit=unit, transform=transform)


def load_models(root: pathlib.Path) -> dict[str, ModelSpec]:
    models: dict[str, ModelSpec] = {}
    for path in sorted((pathlib.Path(root) / "models").glob("*.yml")):
        doc = yaml.safe_load(path.read_text()) or {}
        where = str(path)
        maps = _require(doc, "maps", where)
        spec = ModelSpec(
            id=_require(doc, "id", where),
            dataset=_require(doc, "dataset", where),
            mask=_require(doc, "mask", where),
            # Routed through _require, not raw indexing: a malformed map must raise
            # ConfigError like every other schema violation. A bare KeyError escaping
            # here is an unhandled crash with no location, and this is one of only two
            # failures allowed to abort a whole run — it has to say where and what.
            maps=tuple(
                _map_spec(m, f"{where}: maps[{i}]") for i, m in enumerate(maps)
            ),
            comparison_mask=_optional_path(doc, "comparison_mask", where),
        )
        if spec.id != path.stem:
            raise ConfigError(f"{where}: id {spec.id!r} does not match filename")
        models[spec.id] = spec
    return models


def load_sources(root: pathlib.Path) -> dict[str, SourceSpec]:
    path = pathlib.Path(root) / "data" / "sources.yml"
    doc = yaml.safe_load(path.read_text()) or {}
    sources: dict[str, SourceSpec] = {}
    for name, entry in _require(doc, "datasets", str(path)).items():
        sources[name] = SourceSpec(
            name=name,
            url=_require(entry, "url", f"{path}:{name}"),
            sha256=_require(entry, "sha256", f"{path}:{name}"),
            bytes=_require(entry, "bytes", f"{path}:{name}"),
        )
    return sources


# A lane names the TOOLCHAIN a target needs, not merely "MATLAB or not". Each lane gets
# its own job in benchmark.yml, because each ecosystem has its own setup and cache action:
# a Rust target wants dtolnay/rust-toolchain + Swatinem/rust-cache, a Python one would want
# actions/setup-python. So adding a LANGUAGE means adding a job; adding a target in a
# language that already has a lane is still just adding a directory.
#
# 'native' amends that rule rather than breaking it: it names the ABSENCE of a shared
# toolchain step. The target's own setup.sh provisions everything it needs and the
# workflow supplies only checkout, Python, the data artifact and an optional cache
# (spec §4.1). That is a real category, not a dumping ground — QUIT's setup is
# `curl | tar` plus a checksum and SCT's is `install_sct -iyc`, so a shared step would
# have to be one of them wrapped in an `if:`, which is the exact thing splitting by
# lane exists to prevent.
KNOWN_LANES = ("matlab", "rust", "python", "julia", "r", "native")

MATLAB_PRODUCTS = (
    "Image_Processing_Toolbox",
    "Optimization_Toolbox",
    "Statistics_and_Machine_Learning_Toolbox",
)


@dataclasses.dataclass(frozen=True)
class TargetSpec:
    id: str
    software: str
    version: str
    lane: str
    era: int | None
    matlab_release: str | None
    matlab_products: tuple[str, ...]
    source_repo: str
    source_ref: str
    models: tuple[str, ...]
    repeats: dict[str, int]

    def repeats_for(self, model: str) -> int:
        return int(self.repeats.get(model, self.repeats.get("default", 1)))


def load_targets(root: pathlib.Path) -> dict[str, TargetSpec]:
    targets: dict[str, TargetSpec] = {}
    for path in sorted((pathlib.Path(root) / "targets").glob("*/target.yml")):
        doc = yaml.safe_load(path.read_text()) or {}
        where = str(path)
        lane = _require(doc, "lane", where)
        if lane not in KNOWN_LANES:
            raise ConfigError(
                f"{where}: lane must be one of {KNOWN_LANES}, got {lane!r}"
            )
        source = _require(doc, "source", where)
        spec = TargetSpec(
            id=_require(doc, "id", where),
            software=_require(doc, "software", where),
            version=_require(doc, "version", where),
            lane=lane,
            era=doc.get("era"),
            matlab_release=doc.get("matlab_release"),
            matlab_products=tuple(doc.get("matlab_products", MATLAB_PRODUCTS)),
            source_repo=_require(source, "repo", where),
            source_ref=_require(source, "ref", where),
            models=tuple(_require(doc, "models", where)),
            repeats=dict(doc.get("repeats", {"default": 1})),
        )
        if lane == "matlab" and not spec.matlab_release:
            raise ConfigError(f"{where}: matlab lane requires matlab_release")
        if lane == "matlab" and spec.era not in (1, 2, 3):
            raise ConfigError(
                f"{where}: matlab lane requires era 1, 2 or 3 (got {spec.era!r}); "
                "the era selects which driver runs"
            )
        if spec.id in targets:
            raise ConfigError(f"{where}: duplicate target id {spec.id!r}")
        targets[spec.id] = spec
    return targets
