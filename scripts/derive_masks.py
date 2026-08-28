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

# Which volume each derived model's INTERIOR mask is thresholded on. Named per model
# rather than taken as DERIVED_FROM's first entry, because which volume shows anatomy is
# a fact about the contrast and not about list order -- a committed mask that changes
# when someone reorders an input list is precisely the surprise this script exists to
# rule out. None records a deliberate "no interior mask here"; a derived model absent
# from this dict raises, because "nobody decided yet" must not read as "decided against".
INTERIOR_FROM = {
    # A single 64x64 slice of a phantom that fills the frame: there is no background to
    # cut. Worse, SFalpha is bright at the rim and dark through the middle, so Otsu
    # separates rim from centre and would keep an ANNULUS -- discarding the interior of
    # the very object being measured. masks/README.md's existing point stands: 100% is
    # the honest answer for this archive, and an interior mask here would be a fiction.
    "b1_dam": None,
    # The two AFI volumes are one acquisition at two TRs, so the anatomy is the same in
    # both and the first is as good as the second.
    "b1_afi": "AFIData1.nii.gz",
    # PDw, NOT the MTw that heads DERIVED_FROM. MTw is the saturated image, so the tissue
    # with the strongest MT effect is its dimmest: thresholding it drops 152,804 voxels
    # whose median MTsat is 3.97 p.u. against 2.50 p.u. over the PDw interior. That is
    # the white matter the model is about, and losing it would tilt every cross-software
    # comparison toward CSF and grey matter.
    "mt_sat": "PDw.nii.gz",
}


def finite_positive_mask(volumes) -> np.ndarray:
    keep = np.ones(np.asarray(volumes[0]).size, dtype=bool)
    for volume in volumes:
        v = np.asarray(volume, dtype=np.float64).ravel()
        keep &= np.isfinite(v) & (v > 0.0)
    return keep.astype(np.uint8)


def otsu_threshold(values, nbins: int = 256) -> float:
    """Otsu's between-class-variance threshold, in the units of `values`.

    Written out in numpy rather than taken from skimage or scipy.ndimage on purpose:
    this script's whole claim is that a reviewer can rerun it and get the committed
    bytes back, and a threshold that moves with a library version breaks that. Otsu
    itself has no tuning knob -- unlike BET's `-f`, which would leave a number here for
    every later reader to wonder about, and which needs FSL installed besides.

    The bin count is the method's only quantity. 256 is Otsu's conventional resolution;
    on these archives it puts a handful of intensity counts in a bin, far below the noise
    floor the split is separating, so the answer is not sensitive to it.
    """
    v = np.asarray(values, dtype=np.float64).ravel()
    counts, edges = np.histogram(v, bins=nbins)
    centers = 0.5 * (edges[:-1] + edges[1:])
    # Split i puts bins 0..i below the threshold. Cumulative sums score all nbins-1
    # candidate splits at once, which is both the standard formulation and the reason
    # this is a dozen lines instead of a loop.
    below = np.cumsum(counts)[:-1]
    above = counts.sum() - below
    mass_below = np.cumsum(counts * centers)[:-1]
    mass_above = (counts * centers).sum() - mass_below
    # A split with an empty class has no between-class variance. Guarding it here rather
    # than dividing anyway keeps a nan out of argmax, which would otherwise pick the
    # degenerate split over every real one.
    both = (below > 0) & (above > 0)
    variance = np.zeros(below.shape, dtype=np.float64)
    variance[both] = (
        below[both]
        * above[both]
        * (mass_below[both] / below[both] - mass_above[both] / above[both]) ** 2
    )
    if not variance.any():
        raise ValueError(
            "otsu_threshold: no two-class split exists, the volume is constant"
        )
    return float(centers[int(np.argmax(variance))])


def interior_mask(reference, stats_mask) -> np.ndarray:
    """Voxels above Otsu on `reference` AND already in `stats_mask`.

    The AND is what makes the interior a strict SUBSET of the mask the published
    statistics use. A comparison number computed over a voxel the published numbers
    exclude would put two figures on the same site that describe different regions.
    """
    v = np.asarray(reference, dtype=np.float64).ravel()
    keep = v > otsu_threshold(v)
    return (keep & (np.asarray(stats_mask).ravel() > 0)).astype(np.uint8)


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
    """Locate an INPUT file within an unpacked archive.

    Deliberately blind to FitResults/: that directory holds qMRLab's own fitted output,
    and several archives ship files there under names identical to the inputs. Deriving a
    mask from a fitted map would make the mask a function of the thing being measured.
    sorted() is not a defence -- 'FitResults/Mask.mat' sorts BEFORE 'Mask.mat', so the
    shadow would win every time. Ambiguity raises rather than picking, because there is no
    ordering rule here that is right by construction.
    """
    hits = [
        p for p in sorted((root / dataset).rglob(name))
        if "FitResults" not in p.parts
    ]
    if not hits:
        raise FileNotFoundError(
            f"{name} not found under {root / dataset} (excluding FitResults/)"
        )
    if len(hits) > 1:
        raise ValueError(
            f"{name} is ambiguous under {root / dataset}: {[str(h) for h in hits]}"
        )
    return hits[0]


def _interior_reference(model_id: str) -> str | None:
    if model_id not in INTERIOR_FROM:
        # ValueError, not KeyError: KeyError renders its message with the repr quotes
        # around it, and this one has to be read, not just raised.
        raise ValueError(
            f"scripts/derive_masks.py: INTERIOR_FROM has no entry for derived model "
            f"{model_id!r}; name the volume its interior mask is thresholded on, or "
            f"None to record that it deliberately has none"
        )
    return INTERIOR_FROM[model_id]


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

    models = load_models(root)
    for model_id in models:
        # A model whose declared mask is not masks/<its own id>.nii.gz is scored on
        # another model's mask, so there is nothing here to derive for it. That is what
        # qmt_spgr_ramani does: it is the same acquisition as qmt_spgr fitted with a
        # different sub-model, so it shares the file rather than owning a byte-identical
        # copy. Keyed off the declaration rather than a name list, because the mask a
        # model is scored on is a fact models/*.yml already states -- and because the
        # alternative, falling through to DERIVED_FROM[model_id], is a bare KeyError that
        # says nothing about why.
        if models[model_id].mask != f"masks/{model_id}.nii.gz":
            print(f"{model_id}: shares {models[model_id].mask}, nothing to derive")
            continue

        interior = None
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
            imgs = {n: read_nifti(_find(data, dataset, n)) for n in names}
            shape = imgs[names[0]].shape
            mask = finite_positive_mask([imgs[n].values for n in names])
            reference = _interior_reference(model_id)
            if reference is not None:
                interior = interior_mask(imgs[reference].values, mask)

        out = root / "masks" / f"{model_id}.nii.gz"
        write_mask_nifti(out, mask, shape)
        print(f"{model_id}: {int(mask.sum())}/{mask.size} voxels -> {out}")

        if interior is not None:
            out = root / "masks" / f"{model_id}_interior.nii.gz"
            write_mask_nifti(out, interior, shape)
            print(
                f"{model_id}_interior: {int(interior.sum())}/{interior.size} voxels "
                f"-> {out}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
