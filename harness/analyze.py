"""Artifact trees in, results.json out.

Deliberately knows nothing about MATLAB or Rust. It reads maps and adapter records,
so a software added later needs no change here — that is the seam the target contract
exists to create (spec §9).
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import pathlib

import numpy as np

from harness.comparability import comparability_for, flag_for, load_comparability
from harness.compare import compare_maps
from harness.config import (
    RECIPROCAL_UNIT,
    ConfigError,
    MapSpec,
    load_models,
    load_targets,
)
from harness.measure import masked_stats, voxel_sha256
from harness.nifti import read_nifti
from harness.record import load_adapter_record
from harness.units import scale_between


def _load_mask(root: pathlib.Path, path: str) -> np.ndarray:
    return read_nifti(pathlib.Path(root) / path).values


def _comparison_selection(
    a: np.ndarray, b: np.ndarray, mask: np.ndarray, spec: MapSpec
) -> tuple[np.ndarray, int]:
    """The voxels one pair is compared over, plus how many a declared range removed.

    The range is a claim about physics, so a voxel enters only if BOTH sides lie in it:
    one implementation's 7.75e15 p.u. MTsat is not comparable to the other's 2.3 whichever
    side produced it (spec §7.2's argument for comparison_mask, at a resolution a mask on
    the INPUT intensities cannot reach).

    The finite-in-both rule is applied here as well as inside compare_maps, which is not
    redundant: it is what makes the returned count mean "voxels that would have been
    compared and were not". Taken against the bare mask it would also count every
    background NaN — voxels the range did not exclude and that were never in a comparison
    — and an inflated exclusion count is exactly the thing this count exists to prevent
    someone inventing. Reported for masked_stats' n_nonfinite reason: an exclusion nobody
    can see is indistinguishable from a mask that never had those voxels.
    """
    selected = np.asarray(mask).astype(bool)
    if spec.comparison_range is None:
        return selected, 0
    lo, hi = spec.comparison_range
    comparable = selected & np.isfinite(a) & np.isfinite(b)
    in_range = comparable & (a >= lo) & (a <= hi) & (b >= lo) & (b <= hi)
    return in_range, int((comparable & ~in_range).sum())


def _canonical_values(values: np.ndarray, produced: str, spec: MapSpec) -> np.ndarray:
    """One map's voxels in the model's canonical unit, transform included.

    A `transform` is declared on the model's map but applies per RECORD, and only to
    the records that need it: models/mt_sat.yml declares T1 in seconds, all 14 qMRLab
    targets report seconds, and QUIT reports that same map as MTSat_R1 in s^-1. So the
    linear conversion is tried first and the transform is the fallback for exactly the
    pair units.py refuses — an unconditional inversion would turn 14 correct T1 maps
    into rates. With no transform declared the ValueError propagates untouched, so a
    genuinely wrong unit still fails as loudly as it does today (spec §5.2).
    """
    out = np.asarray(values, dtype=np.float64)
    try:
        return out * scale_between(produced, spec.unit)
    except ValueError:
        if spec.transform is None:
            raise

    # Order is load-bearing: the scale runs FIRST, in the rate domain, and the inversion
    # second — T1 = 1/(R1*k), never (1/R1)*k. It is also the only order the linear table
    # can check, since ('s^-1', 's') is the pair it exists to refuse while ('Hz', 's^-1')
    # it converts. RECIPROCAL_UNIT[spec.unit] cannot KeyError here: load_models rejects
    # `reciprocal` on any unit missing from it.
    rate = out * scale_between(produced, RECIPROCAL_UNIT[spec.unit])
    # 1/0 is inf, and inf is the answer rather than an error: a zero rate IS an infinite
    # relaxation time, and that is what a background voxel looks like when a software
    # writes 0 instead of NaN. It then leaves through masked_stats' existing non-finite
    # path — dropped from mean/median, counted in n_nonfinite — so "this target produced
    # 40000 infinite T1s where that one produced none" stays the finding it is instead
    # of poisoning every statistic with inf. errstate silences numpy's divide warning
    # only; nothing about the value changes.
    with np.errstate(divide="ignore"):
        return 1.0 / rate


def _analysis_failure(target: str, model: str, exc: Exception) -> dict:
    """A record analyze itself could not process, rendered as that target's cell.

    Distinct from an adapter-reported failure: the fit may have been fine and the
    problem downstream. Spec §10 permits exactly two run-aborting failures and this
    is neither, so it degrades to one red cell instead of destroying the run.
    """
    return {
        "target": target, "software": "", "version": "", "model": model,
        "status": "failed", "environment": {}, "timing": {},
        "error": f"analysis failed: {type(exc).__name__}: {exc}", "maps": [],
    }


def _missing_record(target: str, model: str) -> dict:
    """A declared (target, model) combination for which no record exists at all.

    Distinct from both `failed` (the adapter ran and reported a problem) and the
    absence of a cell entirely (a target that never declared this model — a genuine
    capability hole, spec §2.4). `missing` means the catalog says this combination
    should have been attempted and nothing — not even a failure record — came back:
    the classic signature of a killed or never-started CI job (C2/C3, final review).
    Rendered by site.py as visibly distinct from both `failed` and "not applicable"
    (spec §10: "failure is data" — a lost job must not silently read as a hole).
    """
    return {
        "target": target, "software": "", "version": "", "model": model,
        "status": "missing", "environment": {}, "timing": {},
        "error": (
            "no record found for this declared target/model combination — the job "
            "likely did not run or was killed before it could write output"
        ),
        "maps": [],
    }


def analyze(
    results_dir, root, *, models_root=None, targets_root=None,
    reference: str = "qmrlab@v3.0.0",
) -> dict:
    results_dir = pathlib.Path(results_dir)
    root = pathlib.Path(root)
    models = load_models(pathlib.Path(models_root or root))
    targets = load_targets(pathlib.Path(targets_root or root))

    records: list[dict] = []
    # model -> map name -> target -> canonical-unit values, for the comparison pass.
    canonical: dict = collections.defaultdict(lambda: collections.defaultdict(dict))
    masks: dict = {}

    for record_path in sorted(results_dir.glob("*/records/*.json")):
        target_dir = record_path.parent.parent
        # Identity from the path, so a record too malformed to parse still gets a cell.
        fallback_target, fallback_model = target_dir.name, record_path.stem
        try:
            record = load_adapter_record(record_path)
            model = models[record.model]

            enriched = {
                "target": record.target, "software": record.software,
                "version": record.version, "model": record.model,
                "status": record.status, "environment": record.environment,
                "timing": record.timing, "error": record.error, "maps": [],
            }
            # Staged, not written straight into `canonical`: a target that fails on its
            # third map must not leave its first two in the comparison set.
            staged = {}
            for entry in record.maps:
                spec = next((m for m in model.maps if m.name == entry["name"]), None)
                if spec is None:
                    raise ValueError(
                        f"map {entry['name']!r} is not declared in models/{record.model}.yml"
                    )
                img = read_nifti(target_dir / entry["path"])
                values = _canonical_values(img.values, entry["unit"], spec)

                if record.model not in masks:
                    masks[record.model] = _load_mask(root, model.mask)
                mask = masks[record.model]
                if img.values.size != mask.size:
                    raise ValueError(
                        f"map {entry['name']!r} has {img.values.size} voxels but the "
                        f"{record.model} mask has {mask.size}"
                    )

                enriched["maps"].append({
                    "name": entry["name"], "unit": entry["unit"], "path": entry["path"],
                    # Produced unit, never scaled AND never transformed. The transform
                    # is a reading of the numbers, not a correction to them, so it has
                    # no more business in the hash than the unit scale does.
                    "voxel_sha256": voxel_sha256(img.values),
                    "dtype": int(img.datatype), "shape": list(img.shape),
                    "stats_unit": spec.unit,
                    # Handed finished canonical values instead of masked_stats' own
                    # `scale=`, because a reciprocal has to run BEFORE the non-finite
                    # filter: 1/0 is exactly the inf that filter exists to count. A
                    # linear scale commutes with it, so no published number moves.
                    "stats": masked_stats(values, mask),
                })
                staged[entry["name"]] = values
        except ConfigError:
            raise  # schema-invalid config IS a permitted run-aborting failure
        except Exception as exc:
            records.append(_analysis_failure(fallback_target, fallback_model, exc))
            continue

        for name, values in staged.items():
            canonical[record.model][name][record.target] = values
        records.append(enriched)

    # Every (target, model) the catalog declares must produce a cell, even when the
    # job that should have written it never ran or was killed. Without this, a wiped
    # target simply has no records at all and vanishes from the matrix rather than
    # showing as the failure it is (C3, final review; spec §2.4/§10).
    seen = {(r["target"], r["model"]) for r in records}
    for target_id, target_spec in sorted(targets.items()):
        for model_id in target_spec.models:
            if (target_id, model_id) not in seen:
                records.append(_missing_record(target_id, model_id))

    equivalence: dict = collections.defaultdict(dict)
    for record in records:
        for m in record["maps"]:
            bucket = equivalence[record["model"]].setdefault(m["name"], {})
            bucket.setdefault(m["voxel_sha256"], []).append(record["target"])

    # Read once, and from `root` rather than the results tree: comparability is a
    # property of the implementations, not of any one run's artifacts. An absent file is
    # an empty declaration (not an error), which leaves every pair on the undeclared
    # same-estimator default — exactly what the fourteen qMRLab-versus-qMRLab pairs have
    # always been scored as.
    declarations = load_comparability(root)
    # target -> the software it belongs to. Seeded from the records, because a results
    # tree can hold a target the catalog does not declare and every record carries a
    # non-empty `software` by schema; then overridden by targets/*/target.yml, which OWNS
    # that fact (harness/comparability.py resolves a declared member against the target's
    # declared software rather than the text before its '@', so that the two cannot become
    # two sources of truth).
    software = {r["target"]: r["software"] for r in records if r["software"]}
    software.update({tid: spec.software for tid, spec in targets.items()})

    comparisons: dict = collections.defaultdict(dict)
    for model_id, by_map in canonical.items():
        # The comparison mask is the ONLY place a stricter selection is allowed to act
        # (spec §7.2). Statistics and hashes above stay on the model's published mask,
        # so declaring one changes what "substantial disagreement" is measured over
        # without moving a single number already on the site.
        mask = (
            _load_mask(root, models[model_id].comparison_mask)
            if models[model_id].comparison_mask
            else masks[model_id]
        )
        if mask.size != masks[model_id].size:
            raise ConfigError(
                f"models/{model_id}.yml: comparison_mask "
                f"{models[model_id].comparison_mask!r} has {mask.size} voxels but the "
                f"model mask has {masks[model_id].size}"
            )
        for map_name, by_target in by_map.items():
            # Cannot miss: `canonical` is only ever filled with a map name that was
            # matched against this model's catalog entry on the way in.
            spec = next(m for m in models[model_id].maps if m.name == map_name)
            # MapSpec owns the rule and its justification: it is keyed on the CANONICAL
            # unit, never on the unit a record says it produced, and config.py's
            # validation of scale_free_range depends on the same predicate.
            scale_free = spec.scale_free
            pairs = []
            for a, b in itertools.combinations(sorted(by_target), 2):
                entry = comparability_for(
                    declarations, model_id, map_name,
                    a_target=a, a_software=software[a],
                    b_target=b, b_software=software[b],
                )
                if not entry.comparable:
                    # Not a row with a caveat: the declaration says these two do not
                    # answer the same question, so any number here would be read as an
                    # answer to it. site.py already renders an absent pair as "no
                    # comparable voxels" (spec §5.5).
                    continue
                selection, n_out_of_physical_range = _comparison_selection(
                    by_target[a], by_target[b], mask, spec
                )
                # The scale-free range cannot be applied out here with the physical one:
                # it is expressed in units of each map's own masked median, and those
                # medians are not known until compare_maps has taken them over this very
                # selection. So the physical range narrows the selection and the
                # normalised range narrows the normalised values inside.
                compared = compare_maps(
                    by_target[a], by_target[b], selection,
                    scale_free=scale_free, scale_free_range=spec.scale_free_range,
                )
                row = {
                    "a": a, "b": b,
                    **compared,
                    # All three keys on every row, declared or not, for _unmeasurable's
                    # reason: rows of two different shapes move the failure into
                    # whichever renderer reads the short one.
                    #
                    # Two range keys rather than one, because they are in two different
                    # domains -- comparison_range in the map's canonical unit,
                    # scale_free_range in multiples of that map's own masked median. A
                    # reader must never have to work out which, and the key name is the
                    # only place that can be said without a legend. config.py refuses
                    # either on the wrong kind of map, so at most one is ever non-None.
                    "comparison_range": (
                        None if spec.comparison_range is None
                        else list(spec.comparison_range)
                    ),
                    "scale_free_range": (
                        None if spec.scale_free_range is None
                        else list(spec.scale_free_range)
                    ),
                    # One count, because a voxel excluded is a voxel excluded and the
                    # reader wants to know how many left the comparison, not which
                    # mechanism took them. Which one it was is legible from whichever
                    # range key is non-None; summing rather than choosing keeps this
                    # honest if the two ever stop being mutually exclusive.
                    "n_out_of_range": (
                        n_out_of_physical_range + compared["n_out_of_range"]
                    ),
                }
                # The colour is never computed from the numbers alone. Red is only
                # assignable inside same-estimator, and `estimator_class` travels with the
                # row so the site can say that rather than leaving a permanently-amber
                # cell looking like a fit that never quite passed (spec §7, §7.3).
                flag = flag_for(
                    entry,
                    rel_median_diff=row["rel_median_diff"],
                    ccc=row["ccc"],
                )
                row["estimator_class"] = entry.estimator_class
                row["flag"] = flag.colour
                row["flag_reason"] = flag.reason
                pairs.append(row)
            comparisons[model_id][map_name] = pairs

    return {
        "reference": reference,
        "records": records,
        "equivalence": {k: dict(v) for k, v in equivalence.items()},
        "comparisons": {k: dict(v) for k, v in comparisons.items()},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", required=True)
    parser.add_argument("--reference", default="qmrlab@v3.0.0")
    args = parser.parse_args(argv)

    doc = analyze(args.results_dir, args.root, reference=args.reference)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, sort_keys=True))
    print(f"wrote {out} ({len(doc['records'])} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
