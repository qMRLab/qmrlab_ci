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

from harness.compare import compare_maps
from harness.config import ConfigError, load_models
from harness.measure import masked_stats, voxel_sha256
from harness.nifti import read_nifti
from harness.record import load_adapter_record
from harness.units import scale_between


def _load_mask(root: pathlib.Path, model) -> np.ndarray:
    return read_nifti(pathlib.Path(root) / model.mask).values


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


def analyze(
    results_dir, root, *, models_root=None, reference: str = "qmrlab@v3.0.0"
) -> dict:
    results_dir = pathlib.Path(results_dir)
    root = pathlib.Path(root)
    models = load_models(pathlib.Path(models_root or root))

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
                scale = scale_between(entry["unit"], spec.unit)
                img = read_nifti(target_dir / entry["path"])

                if record.model not in masks:
                    masks[record.model] = _load_mask(root, model)
                mask = masks[record.model]
                if img.values.size != mask.size:
                    raise ValueError(
                        f"map {entry['name']!r} has {img.values.size} voxels but the "
                        f"{record.model} mask has {mask.size}"
                    )

                enriched["maps"].append({
                    "name": entry["name"], "unit": entry["unit"], "path": entry["path"],
                    "voxel_sha256": voxel_sha256(img.values),  # produced unit, never scaled
                    "dtype": int(img.datatype), "shape": list(img.shape),
                    "stats_unit": spec.unit,
                    "stats": masked_stats(img.values, mask, scale=scale),
                })
                staged[entry["name"]] = img.values * scale
        except ConfigError:
            raise  # schema-invalid config IS a permitted run-aborting failure
        except Exception as exc:
            records.append(_analysis_failure(fallback_target, fallback_model, exc))
            continue

        for name, values in staged.items():
            canonical[record.model][name][record.target] = values
        records.append(enriched)

    equivalence: dict = collections.defaultdict(dict)
    for record in records:
        for m in record["maps"]:
            bucket = equivalence[record["model"]].setdefault(m["name"], {})
            bucket.setdefault(m["voxel_sha256"], []).append(record["target"])

    comparisons: dict = collections.defaultdict(dict)
    for model_id, by_map in canonical.items():
        for map_name, by_target in by_map.items():
            pairs = []
            for a, b in itertools.combinations(sorted(by_target), 2):
                pairs.append({
                    "a": a, "b": b,
                    **compare_maps(by_target[a], by_target[b], masks[model_id]),
                })
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
