"""One line per run recording each target's digest-of-digests.

Sorted before hashing so the digest is a property of the outputs, not of the order
the artifacts happened to be downloaded in.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


def target_digests(doc: dict) -> dict[str, str]:
    per_target: dict[str, list[str]] = {}
    for record in doc["records"]:
        entries = per_target.setdefault(record["target"], [])
        for m in record.get("maps") or ():
            entries.append(f"{record['model']}/{m['name']}={m['voxel_sha256']}")
        if not record.get("maps"):
            entries.append(f"{record['model']}={record['status']}")

    return {
        target: hashlib.sha256("\n".join(sorted(entries)).encode()).hexdigest()
        for target, entries in per_target.items()
    }


def append_run(history_path, doc: dict, *, run_started_utc: str) -> None:
    path = pathlib.Path(history_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"run_started_utc": run_started_utc, "digests": target_digests(doc)},
        sort_keys=True,
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--history", required=True)
    parser.add_argument("--run-started-utc", required=True)
    args = parser.parse_args(argv)

    doc = json.loads(pathlib.Path(args.results).read_text())
    append_run(args.history, doc, run_started_utc=args.run_started_utc)
    print(f"appended run {args.run_started_utc} to {args.history}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
