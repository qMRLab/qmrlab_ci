"""Write a schema-valid adapter record from a shell adapter.

Native-lane adapters are shell scripts, and hand-rolling JSON in shell is how a
malformed record reaches `analyze`. This validates before writing, so a broken
adapter fails at the adapter rather than three jobs later.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib

from harness.record import AdapterRecord


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--software", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--error", default=None)
    parser.add_argument("--n-voxels", type=int, default=0)
    parser.add_argument("--fit-seconds", type=float, action="append", default=[])
    parser.add_argument(
        "--map", action="append", default=[],
        help="name:unit:path, repeatable",
    )
    args = parser.parse_args(argv)

    maps = []
    for entry in args.map:
        name, unit, path = entry.split(":", 2)
        maps.append({"name": name, "unit": unit, "path": path})

    doc = {
        "target": args.target, "software": args.software, "version": args.version,
        "model": args.model, "status": args.status,
        "environment": {
            "runner_os": os.environ.get("RUNNER_OS"),
            "harness_commit": os.environ.get("GITHUB_SHA"),
            "run_started_utc": os.environ.get("QMRLAB_CI_RUN_STARTED"),
        },
        "timing": {
            "repeats": len(args.fit_seconds),
            "fit_seconds": args.fit_seconds,
            "n_voxels_fitted": args.n_voxels,
        },
        "maps": maps,
    }
    if args.error:
        doc["error"] = args.error

    AdapterRecord.from_dict(doc)  # raises RecordError before anything is written

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
