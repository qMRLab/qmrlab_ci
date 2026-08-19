"""Fetch the pinned OSF archives once, verify them, and build the canonical input tree.

Every target fits the output of this script, so that a difference between two targets
is a difference between the softwares and not between two downloads.
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import urllib.request
import zipfile

from harness.config import load_sources


class ChecksumError(Exception):
    """A downloaded archive does not match its pin. This aborts the whole run."""


def verify(path, expected_sha256: str, expected_bytes: int) -> None:
    path = pathlib.Path(path)
    actual_bytes = path.stat().st_size
    if actual_bytes != expected_bytes:
        raise ChecksumError(
            f"{path.name}: expected {expected_bytes} bytes, got {actual_bytes}"
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ChecksumError(
            f"{path.name}: sha256 mismatch\n  expected {expected_sha256}\n  actual   {digest}"
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for source in load_sources(root).values():
        archive = out / f"{source.name}.zip"
        print(f"fetching {source.name} from {source.url}")
        urllib.request.urlretrieve(source.url, archive)
        verify(archive, source.sha256, source.bytes)
        print(f"  verified {source.sha256[:12]}…")

        target_dir = out / source.name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(target_dir)

    # Masks are deliberately NOT copied here. They are produced by
    # scripts/derive_masks.py FROM this tree, so copying them in would make this
    # script depend on its own downstream output and fail on a clean checkout.
    # Every consumer reads them from the repo root instead: harness/analyze.py via
    # models/<id>.yml, and targets/qmrust@main/run.sh directly.
    print(f"canonical input tree ready at {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
