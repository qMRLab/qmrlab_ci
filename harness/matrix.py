"""Turn declared targets into the two GitHub Actions job matrices.

Split by lane rather than emitted as one matrix with conditional steps: the MATLAB
lane needs setup-matlab and run-command, the native lane needs neither, and a job
full of `if:` guards hides which steps actually run for a given target.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib

from harness.config import TargetSpec, load_targets


def build_matrices(targets: dict[str, TargetSpec]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {"matlab": [], "native": []}
    for target in targets.values():
        entry = {
            "id": target.id,
            "software": target.software,
            "version": target.version,
            "source_repo": target.source_repo,
            "source_ref": target.source_ref,
            "models": list(target.models),
        }
        if target.lane == "matlab":
            entry["era"] = target.era
            entry["matlab_release"] = target.matlab_release
            entry["matlab_products"] = "\n".join(target.matlab_products)
        # Passed straight into the driver as a MATLAB string literal, so it is
        # serialized here rather than reassembled in YAML.
        entry["repeats_json"] = json.dumps(target.repeats)
        out[target.lane].append(entry)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)

    matrices = build_matrices(load_targets(pathlib.Path(args.root)))
    lines = [f"{lane}={json.dumps(entries)}" for lane, entries in matrices.items()]

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
