"""Regenerate masks/*.nii.gz from the pinned archives.

Committed output, reproducible script. A reviewer can rerun this and get the
committed bytes back, which is the difference between a documented mask and a
magic file nobody can justify.

Dev-only: needs scipy to read MATLAB .mat masks. CI never runs this.
"""
from __future__ import annotations

import argparse
import gzip
import pathlib
import struct

import numpy as np

# Where each model's mask comes from. Explicit per model, because "the archive that
# ships one" and "the archive that does not" is exactly the distinction being encoded.
SHIPPED_MASK = {
    "inversion_recovery": ("ir", "Mask.mat"),
    "qmt_spgr": ("qmt", "Mask.mat"),
    "mt_ratio": ("mtr", "Mask.mat"),
    "mono_t2": ("mono_t2", "Mask.nii.gz"),
    "vfa_t1": ("vfa_t1", "Mask.nii.gz"),
}
DERIVED_FROM = {
    "b1_dam": ("b1_dam", ["SFalpha.nii.gz", "SF2alpha.nii.gz"]),
    "b1_afi": ("b1_afi", ["AFIData1.nii.gz", "AFIData2.nii.gz"]),
    "mt_sat": ("mtsat", ["MTw.nii.gz", "PDw.nii.gz", "T1w.nii.gz"]),
}


def finite_positive_mask(volumes) -> np.ndarray:
    keep = np.ones(np.asarray(volumes[0]).size, dtype=bool)
    for volume in volumes:
        v = np.asarray(volume, dtype=np.float64).ravel()
        keep &= np.isfinite(v) & (v > 0.0)
    return keep.astype(np.uint8)


def write_mask_nifti(path, mask: np.ndarray, shape) -> None:
    hdr = bytearray(348)
    struct.pack_into("<i", hdr, 0, 348)
    dim = [len(shape)] + list(shape) + [1] * (7 - len(shape))
    struct.pack_into("<8h", hdr, 40, *dim)
    struct.pack_into("<h", hdr, 70, 2)   # uint8
    struct.pack_into("<h", hdr, 72, 8)
    struct.pack_into("<f", hdr, 108, 352.0)
    struct.pack_into("<2f", hdr, 112, 1.0, 0.0)
    hdr[344:348] = b"n+1\x00"
    body = np.asarray(mask, dtype=np.uint8).tobytes()
    # mtime=0 because these files are COMMITTED. gzip stamps the current time into its
    # header by default, so regenerating would rewrite all eight files with identical
    # content and different bytes -- turning "rerun this and diff it" from the check that
    # justifies the masks into noise that hides a real change.
    pathlib.Path(path).write_bytes(
        gzip.compress(bytes(hdr) + b"\x00" * 4 + body, mtime=0)
    )


def _find(root: pathlib.Path, dataset: str, name: str) -> pathlib.Path:
    hits = sorted((root / dataset).rglob(name))
    if not hits:
        raise FileNotFoundError(f"{name} not found under {root / dataset}")
    return hits[0]


def main(argv=None) -> int:
    import scipy.io

    from harness.config import load_models
    from harness.nifti import read_nifti

    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="output of scripts.fetch_data")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)

    data, root = pathlib.Path(args.data), pathlib.Path(args.root)
    (root / "masks").mkdir(exist_ok=True)

    for model_id in load_models(root):
        if model_id in SHIPPED_MASK:
            dataset, name = SHIPPED_MASK[model_id]
            path = _find(data, dataset, name)
            if name.endswith(".mat"):
                mat = scipy.io.loadmat(path)
                arr = next(v for k, v in mat.items() if not k.startswith("__"))
            else:
                img = read_nifti(path)
                arr = img.values.reshape(img.shape, order="F")
            shape, mask = arr.shape, (np.asarray(arr).ravel(order="F") > 0).astype(np.uint8)
        else:
            dataset, names = DERIVED_FROM[model_id]
            imgs = [read_nifti(_find(data, dataset, n)) for n in names]
            shape = imgs[0].shape
            mask = finite_positive_mask([i.values for i in imgs])

        out = root / "masks" / f"{model_id}.nii.gz"
        write_mask_nifti(out, mask, shape)
        print(f"{model_id}: {int(mask.sum())}/{mask.size} voxels -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
