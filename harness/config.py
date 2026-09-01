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

# The canonical unit that means "this map's amplitude is arbitrary". A map declared on it
# is compared after each side is divided by its own masked median (spec §7), which is why
# it is the one unit whose bounds are read in normalised rather than physical units --
# see MapSpec.scale_free, which is this test and the only place it should be written.
SCALE_FREE_UNIT = "au"

# The bound a scale-free comparison gets when a map declares none, in units of that map's
# own masked median. It is a claim about physics, not a bound chosen to make agreement
# look good: an M0 is a signal amplitude, so 10 is a voxel whose fitted amplitude is an
# order of magnitude above the median amplitude of the tissue it sits in. Measured on the
# published maps, that is far outside anything a converged fit reaches: vfa_t1/M0 spans
# 0.087 to 2.45 across all 4,668 of its voxels and all fifteen targets, and no mono_t2/M0
# target has a 99th percentile above 1.74. So 10 is loose by better than 4x and reaches
# only fits that ran away. The lower bound is 0 rather than a symmetric 1/10 because a
# SMALL amplitude is a real edge voxel and not a divergence (mono_t2/M0's 5th percentile
# is 0.50 and its 1st is 0.041), while a NEGATIVE amplitude fitted from magnitude data is
# a solver excursion whatever its size.
DEFAULT_SCALE_FREE_RANGE = (0.0, 10.0)


@dataclasses.dataclass(frozen=True)
class MapSpec:
    name: str
    unit: str
    # None means "the produced value already IS this quantity", which is every map in
    # the catalog today. Defaulted rather than required so no models/*.yml has to move.
    transform: str | None = None
    # [lo, hi] in this map's canonical unit, bounding which voxels may enter a PAIRWISE
    # COMPARISON -- never the statistics, never the hash, never masked_stats (spec §7.2's
    # rule for comparison_mask, one level finer). It exists because a mask cannot express
    # it: masks/mt_sat_interior.nii.gz is an Otsu threshold on PDw INTENSITY, and no
    # threshold on the input can exclude a voxel whose FITTED value exploded. 34 interior
    # voxels hold |MTsat| > 1000 (max 7.75e15) and 10 hold |T1| > 1000 (max 34,683 s).
    # Against a software that clips them, those 44 voxels alone take the CCC of two
    # otherwise-agreeing maps to zero -- 0.0012 on T1, order 1e-16 on MTsat -- while the
    # relative median difference stays exactly 0.0: they destroy the second criterion
    # without moving the first one that would have shown why. A range is a claim about
    # physics -- 10 s is not a T1 -- so it is declared per map with its reason, and never
    # inferred from the data it will then be used to judge.
    comparison_range: tuple[float, float] | None = None
    # [lo, hi] in units of this map's OWN MASKED MEDIAN, not of `unit` -- the two range
    # fields are separate rather than one field read two ways precisely so that nobody
    # reading a models/*.yml has to work out which domain a pair of numbers is in.
    # Non-None on exactly the scale-free maps and None on every other, enforced in
    # _map_spec, so the field that carries the bounds is itself the statement of the
    # domain they are in -- on the site row as much as in the catalog.
    #
    # It exists because comparison_range CANNOT be given here. An 'au' amplitude has no
    # physical bound to declare: the amplitude is arbitrary, which is the whole reason
    # scale-free normalisation exists. But the leverage problem is identical to the one
    # comparison_range fixes for mt_sat, and Pearson r and CCC are variance-based, so a
    # handful of diverged voxels decide the number for all the others. Measured on the
    # published mono_t2/M0 maps (qmrlab@master vs qmrlab@v2.4.0, 27,417 voxels): TWO
    # voxels reaching 219x the median take r from 0.877 to 0.333 and CCC from 0.861 to
    # 0.129, and put a red flag on the site while the relative median difference reads
    # -0.3%.
    scale_free_range: tuple[float, float] | None = None

    @property
    def scale_free(self) -> bool:
        """Whether this map's amplitude is arbitrary, so its comparison normalises it.

        Keyed on the CANONICAL unit, never on the unit a record says it produced, and
        that is load-bearing rather than incidental: every adapter reports B1map as 'au'
        while models/b1_*.yml declares 'fraction' (spec §5.3), so keying on the produced
        unit would median-normalise a genuine ratio in which 1.0 means the nominal flip
        angle was reached -- deleting a 10% B1 calibration offset instead of measuring
        it, which spec §7 forbids by name. Living here rather than being spelled out at
        each use keeps the rule and the validation that depends on it from drifting apart.
        """
        return self.unit == SCALE_FREE_UNIT


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


def _range(doc: dict, key: str, where: str, name: str) -> tuple[float, float] | None:
    """Validate an optional [lo, hi] as strictly as a unit, and for the same reason.

    A range silently ignored or read backwards would not fail: it would publish a red
    flag computed over a voxel selection nobody declared, which is indistinguishable on
    the site from the fit disagreeing. So every way of getting it wrong raises, naming
    the file, the map and the field -- the field because there are two range fields in
    two different domains and "which range is malformed" is half the answer.
    """
    if key not in doc:
        return None
    value = doc[key]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError(
            f"{where} ({name!r}): {key} must be a two-item [lo, hi], got {value!r}"
        )
    for bound in value:
        # bool is an int subclass, so `comparison_range: [false, 10]` would otherwise
        # pass as [0, 10] -- a YAML typo that reads as a deliberate physical bound.
        if isinstance(bound, bool) or not isinstance(bound, (int, float)):
            raise ConfigError(
                f"{where} ({name!r}): {key} bounds must be numbers, got {bound!r}"
            )
    lo, hi = float(value[0]), float(value[1])
    # Spelled as `not lo < hi` rather than `lo >= hi` so a NaN bound is refused too:
    # every comparison with NaN is False, so a NaN range would silently exclude every
    # voxel and report an empty comparison as a measured one.
    if not lo < hi:
        raise ConfigError(
            f"{where} ({name!r}): {key} must have lo < hi, got [{lo}, {hi}]"
        )
    return (lo, hi)


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
    comparison_range = _range(doc, "comparison_range", where, name)
    scale_free_range = _range(doc, "scale_free_range", where, name)
    # MapSpec.scale_free's test, spelled out because the MapSpec does not exist yet. It
    # is the same predicate deliberately: the map that gets normalised is exactly the map
    # whose bounds are read in normalised units, and a validation keyed on anything else
    # could admit a bound the comparison then reads in the other domain.
    scale_free = unit == SCALE_FREE_UNIT
    # Each range belongs to exactly one kind of map, and declaring the wrong one raises
    # instead of being ignored. Ignoring it is the failure both fields exist to prevent:
    # a physical bound on an arbitrary amplitude would exclude voxels for the scale the
    # software happened to choose, and a normalised bound on a physical map would exclude
    # them for being far from the median rather than for being unphysical. Either reaches
    # the site as a voxel selection nobody declared, wearing a fit disagreement's clothes.
    if scale_free and comparison_range is not None:
        raise ConfigError(
            f"{where} ({name!r}): comparison_range cannot be declared on unit "
            f"{SCALE_FREE_UNIT!r}, whose amplitude is arbitrary; the bound a scale-free "
            "comparison takes is scale_free_range, in units of the map's own masked "
            "median"
        )
    if not scale_free and scale_free_range is not None:
        raise ConfigError(
            f"{where} ({name!r}): scale_free_range is in units of the map's own masked "
            f"median and applies only to unit {SCALE_FREE_UNIT!r}; {unit!r} is a "
            "physical unit, so its bound is comparison_range"
        )
    if scale_free and scale_free_range is None:
        # Unlike comparison_range, an absent declaration is a DEFAULT and not "no bound".
        # Every scale-free map is normalised, and normalising does nothing about
        # leverage, so a map added later without a declaration would silently reintroduce
        # exactly the failure this field was written to remove. Resolved here rather than
        # at the point of use, so MapSpec.scale_free_range is always the range that will
        # actually be applied: a None meaning "declared nothing, ask someone else what
        # happens" would put the effective bound in one place and the published bound in
        # another, and those are the two a reader compares when an exclusion count
        # surprises them.
        scale_free_range = DEFAULT_SCALE_FREE_RANGE
    return MapSpec(
        name=name,
        unit=unit,
        transform=transform,
        comparison_range=comparison_range,
        scale_free_range=scale_free_range,
    )


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
