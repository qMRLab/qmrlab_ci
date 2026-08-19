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


@dataclasses.dataclass(frozen=True)
class MapSpec:
    name: str
    unit: str


@dataclasses.dataclass(frozen=True)
class ModelSpec:
    id: str
    dataset: str
    mask: str
    maps: tuple[MapSpec, ...]


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
                MapSpec(
                    name=_require(m, "name", f"{where}: maps[{i}]"),
                    unit=_require(m, "unit", f"{where}: maps[{i}]"),
                )
                for i, m in enumerate(maps)
            ),
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
KNOWN_LANES = ("matlab", "rust", "python", "julia", "r")

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
