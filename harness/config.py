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
