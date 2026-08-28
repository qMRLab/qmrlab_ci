"""Convert the .mat-only archives to NIfTI once, centrally, for every non-MATLAB lane.

Three archives ship their inputs as MATLAB `.mat` and nothing else -- `ir`, `qmt` and
`mtr` -- and `mt_ratio`, the single best-matched comparison SCT offers, is one of them
(spec 6.2).

The only converter that exists today is `qmrust bidsify --mat-dir`, invoked from
targets/qmrust@main/run.sh. Reusing it would make a QUIT or SCT job depend on a cargo
build of an unrelated target, and would make SCT's inputs a function of a qmrust commit:
a change in one target could then move another target's numbers, which is the single
thing a cross-software benchmark must never allow. Hence a harness-owned converter, run
once in prepare-data, whose output every non-MATLAB lane reads -- the same principle as
the shared canonical-inputs artifact and the harness-owned qmrlab_ci_write_nii.m.

The pure-NIfTI archives are deliberately NOT copied through this tree. Their bytes are
already identical for every lane that opens them, so a copy would add no determinism;
mtsat alone would duplicate 55 MB to add none. Only converted `.mat` volumes and the 4D
stacks land here.

Needs scipy, which is a main dependency for this reason and no other (pyproject.toml).
"""
from __future__ import annotations

import argparse
import gzip
import pathlib
import struct

import numpy as np
import scipy.io

from harness.config import load_models
from harness.nifti import read_nifti

# Same rule, one copy. scripts/derive_masks.py::_find already encodes "an INPUT file,
# never its FitResults/ shadow, and ambiguity raises rather than picking". A second copy
# here would be somewhere for the two to drift while both kept passing their own tests --
# and this script and that one have to agree about which file is the input, or the mask
# cross-check below would compare a mask to a volume it was not derived from.
from scripts.derive_masks import _find

# Which .mat inputs each .mat-only archive carries. Explicit rather than a glob, for
# SHIPPED_MASK's reason in derive_masks.py: this tree is what the non-MATLAB lanes fit,
# and an archive re-uploaded with an extra file must not quietly gain a converted input.
# Undeclared .mat inputs raise (see _undeclared) rather than being skipped, because a
# skipped input reaches a lane as a missing file at fit time, far from its cause.
MAT_INPUTS: dict[str, tuple[str, ...]] = {
    "ir": ("IRData.mat", "Mask.mat"),
    "qmt": ("MTdata.mat", "R1map.mat", "B1map.mat", "B0map.mat", "Mask.mat"),
    "mtr": ("MTon.mat", "MToff.mat", "Mask.mat"),
}

# Volume order for each model whose fitter takes ONE stacked 4D input instead of N named
# volumes. These orders are load-bearing and they are NOT re-derived here: each is the
# order targets/qmrust@main/run.sh::prepare_input() already established, from each
# model's Rust source and against the real archives. A swapped pair does not fail -- it
# fits the reciprocal, or the negative, of the intended quantity and reports it as a
# number, which is exactly the failure this benchmark exists to catch rather than commit.
STACK_ORDER: dict[str, tuple[str, tuple[str, ...]]] = {
    # Series, rows = repetition_times [0.02, 0.10] -> [TR1, TR2].
    "b1_afi": ("b1_afi", ("AFIData1", "AFIData2")),
    # Series, rows = flip_angles [60, 120] -> [alpha, 2*alpha].
    "b1_dam": ("b1_dam", ("SFalpha", "SF2alpha")),
    # Named, ROLES = ["MTw", "PDw", "T1w"] (qmrust-core mt_sat/model.rs).
    "mt_sat": ("mtsat", ("MTw", "PDw", "T1w")),
    # Named, ROLES = ["MTon", "MToff"] (qmrust-core mt_ratio/model.rs). An SCT adapter
    # must read these two by NAME and not by position: sct_compute_mtr's -mt0 is the
    # MT-OFF image and -mt1 the MT-on one (spec 9), the reverse of this order.
    "mt_ratio": ("mtr", ("MTon", "MToff")),
}

# The one converted input that has something committed to check it against: masks/ was
# derived from exactly this file, so a conversion that reproduces it voxel for voxel has
# read the archive in the memory order derive_masks.py did. See check_mask.
MASK_INPUT = "Mask.mat"

# NIfTI-1 datatype code and bitpix for the two types this converter may write.
_NIFTI_TYPE = {"float32": (16, 32), "float64": (64, 64)}

# Output dtype per source dtype, explicit and exhaustive-by-raising. The claim this
# script makes is that several lanes fit the SAME bytes; a source type nobody considered
# must not be silently rounded into one of the two written here. Every integer listed has
# a range the float32 mantissa covers exactly, so those widenings are lossless -- int32
# and uint32 are absent for precisely that reason, not by oversight.
_OUT_DTYPE = {
    "float32": "float32",
    "float64": "float64",
    "int8": "float32",
    "uint8": "float32",
    "int16": "float32",
    "uint16": "float32",
}


def out_dtype(source_dtype, where: str) -> np.dtype:
    name = np.dtype(source_dtype).name
    if name not in _OUT_DTYPE:
        raise ValueError(
            f"{where}: no output dtype is declared for source dtype {name!r}; add one to "
            f"scripts/mat_to_nifti.py::_OUT_DTYPE deliberately rather than letting the "
            f"value round into float32"
        )
    return np.dtype(_OUT_DTYPE[name])


def write_nifti(path, array: np.ndarray) -> None:
    """Write `array` as a single-file gzipped NIfTI-1.

    Deliberately the same shape of code as scripts/derive_masks.py::write_mask_nifti --
    stdlib struct plus gzip, no nibabel -- including its mtime=0: gzip stamps the current
    time into its header by default, so two runs over the same archive would produce
    identical content in different bytes. That would break the one property this file
    exists to provide, which is that a QUIT lane and an SCT lane fit byte-identical
    inputs no matter when or where each was prepared.
    """
    if array.ndim < 2 or array.ndim > 4:
        raise ValueError(
            f"{path}: refusing to write a {array.ndim}-D NIfTI; these archives are 2-D "
            f"through 4-D and anything else means the array was reshaped by mistake"
        )
    code, bitpix = _NIFTI_TYPE[array.dtype.name]
    shape = array.shape
    hdr = bytearray(348)
    struct.pack_into("<i", hdr, 0, 348)
    dim = [len(shape)] + list(shape) + [1] * (7 - len(shape))
    struct.pack_into("<8h", hdr, 40, *dim)
    struct.pack_into("<h", hdr, 70, code)
    struct.pack_into("<h", hdr, 72, bitpix)
    # pixdim 1.0, where write_mask_nifti leaves zeros. The masks are only ever indexed by
    # this repo's own code, but these files are opened by QUIT and SCT, and to ITK or
    # nibabel a zero voxel size is not a neutral "unset" -- it propagates into the affine
    # and into anything that resamples or reports a volume. 1.0 is the same isotropic
    # placeholder run.sh::stack4d already writes; the archives carry no trustworthy
    # geometry to preserve, and every comparison in this repo is by index anyway.
    struct.pack_into("<8f", hdr, 76, *([1.0] * 8))
    struct.pack_into("<f", hdr, 108, 352.0)
    struct.pack_into("<2f", hdr, 112, 1.0, 0.0)
    hdr[344:348] = b"n+1\x00"
    body = np.asfortranarray(array).tobytes(order="F")
    pathlib.Path(path).write_bytes(
        gzip.compress(bytes(hdr) + b"\x00" * 4 + body, mtime=0)
    )


def load_mat(path) -> tuple[str, np.ndarray]:
    """The one array a qMRLab input .mat carries, and the name it carries it under.

    Exactly one non-private variable is required. derive_masks.py takes the first it
    finds, which is right for a mask it thresholds on the spot; here the array becomes a
    fit INPUT for three other softwares, and picking one of several by dict order would
    make which volume QUIT fits depend on scipy's insertion order.
    """
    mat = scipy.io.loadmat(str(path))
    names = sorted(k for k in mat if not k.startswith("__"))
    if len(names) != 1:
        raise ValueError(
            f"{path}: expected exactly one variable, found {names}"
        )
    return names[0], np.asarray(mat[names[0]])


def _pad_to_3d(volume: np.ndarray) -> np.ndarray:
    """Restore the slice axis a single-slice archive stores as 2-D.

    Same padding run.sh::stack4d does, so a stack this script writes has the same axis
    order as the one qmrust already fits -- otherwise the fourth axis of a b1_dam stack
    would be axis 2 here and axis 3 there.
    """
    while volume.ndim < 3:
        volume = volume.reshape(volume.shape + (1,))
    return volume


def stack4d(volumes: list[np.ndarray], names: tuple[str, ...]) -> np.ndarray:
    """Stack same-shape volumes along a new last axis, in the order given.

    Shape and dtype mismatches raise rather than being reconciled: numpy would happily
    broadcast one and promote the other, and both fixes would produce a plausible 4D
    volume that no longer holds the acquisition it claims to.
    """
    padded = [_pad_to_3d(v) for v in volumes]
    for name, volume in zip(names[1:], padded[1:]):
        if volume.shape != padded[0].shape:
            raise ValueError(
                f"stack4d: {name} has shape {volume.shape}, {names[0]} has "
                f"{padded[0].shape}; a stack must be one acquisition grid"
            )
        if volume.dtype != padded[0].dtype:
            raise ValueError(
                f"stack4d: {name} is {volume.dtype}, {names[0]} is {padded[0].dtype}; "
                f"declare the intended output dtype rather than letting numpy promote"
            )
    return np.stack(padded, axis=-1)


def _undeclared(data: pathlib.Path, dataset: str, declared: tuple[str, ...]) -> list[str]:
    found = {
        p.name
        for p in (data / dataset).rglob("*.mat")
        if "FitResults" not in p.parts
    }
    return sorted(found - set(declared))


def _read_volume(path: pathlib.Path) -> np.ndarray:
    """One archive volume, in this converter's output dtype, whatever it is stored as.

    `.values` applies the NIfTI intensity transform first, so an integer-stored,
    slope-scaled volume contributes its scaled values and not its raw codes -- the
    dtype is chosen from what the file STORES, which is what determines whether float32
    can hold the result without loss.
    """
    if path.suffix == ".mat":
        _, array = load_mat(path)
        return array.astype(out_dtype(array.dtype, str(path)))
    image = read_nifti(path)
    array = image.values.reshape(image.shape, order="F")
    return array.astype(out_dtype(image.raw.dtype, str(path)))


def _source(data: pathlib.Path, dataset: str, name: str) -> pathlib.Path:
    """The archive file for a stack member, .mat or .nii.gz, never both.

    Both extensions are tried because the four stacked models straddle the split this
    script exists for: mt_ratio's members are .mat, the other three models' are .nii.gz.
    An archive carrying both under one name is a genuine ambiguity -- which one qmrust
    already fits would then be a guess -- so it raises.
    """
    hits = []
    for suffix in (".mat", ".nii.gz"):
        try:
            hits.append(_find(data, dataset, name + suffix))
        except FileNotFoundError:
            continue
    if not hits:
        raise FileNotFoundError(
            f"stack member {name} not found under {data / dataset} as .mat or .nii.gz"
        )
    if len(hits) > 1:
        raise ValueError(
            f"stack member {name} exists as both .mat and .nii.gz under "
            f"{data / dataset}: {[str(h) for h in hits]}"
        )
    return hits[0]


def check_mask(converted: np.ndarray, committed: pathlib.Path) -> int:
    """Assert a converted archive mask reproduces the committed mask voxel for voxel.

    Not a count comparison. Reading a MATLAB array in C order instead of Fortran order
    leaves the number of nonzero voxels exactly as it was and puts every one of them
    somewhere else, so a count would pass on a tree that is silently transposed -- and
    every downstream number would then be computed over the wrong voxels while every
    checksum in the repo still matched.
    """
    image = read_nifti(committed)
    expected = image.values.reshape(image.shape, order="F") > 0
    actual = converted > 0
    if actual.shape != expected.shape:
        raise ValueError(
            f"{committed}: shape {expected.shape} but the converted mask is "
            f"{actual.shape}"
        )
    if not np.array_equal(actual, expected):
        raise ValueError(
            f"{committed}: the converted mask disagrees with the committed one in "
            f"{int(np.count_nonzero(actual != expected))} voxels; the array was read in "
            f"the wrong memory order or from the wrong file"
        )
    return int(np.count_nonzero(expected))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="output of scripts.fetch_data")
    parser.add_argument("--out", required=True, help="canonical NIfTI tree to write")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)

    data, out, root = (
        pathlib.Path(args.data),
        pathlib.Path(args.out),
        pathlib.Path(args.root),
    )
    models = load_models(root)

    for dataset, declared in MAT_INPUTS.items():
        extra = _undeclared(data, dataset, declared)
        if extra:
            raise ValueError(
                f"{data / dataset}: undeclared .mat inputs {extra}; add them to "
                f"scripts/mat_to_nifti.py::MAT_INPUTS or the non-MATLAB lanes will fit "
                f"an archive this converter has not seen"
            )
        (out / dataset).mkdir(parents=True, exist_ok=True)
        for filename in declared:
            path = _find(data, dataset, filename)
            name, array = load_mat(path)
            array = array.astype(out_dtype(array.dtype, str(path)))
            target = out / dataset / f"{pathlib.Path(filename).stem}.nii.gz"
            write_nifti(target, array)
            note = ""
            if filename == MASK_INPUT:
                # Every model fed by this dataset, not just the first: qmt feeds both
                # qMT streams, and the check is worth nothing if it silently checks none.
                consumers = [s for s in models.values() if s.dataset == dataset]
                if not consumers:
                    raise ValueError(
                        f"{path}: no models/*.yml declares dataset {dataset!r}, so this "
                        f"archive's mask cannot be cross-checked against a committed one"
                    )
                counts = sorted({check_mask(array, root / s.mask) for s in consumers})
                note = f" mask={counts[0] if len(counts) == 1 else counts} voxels"
            print(
                f"{dataset}/{filename} [{name}] {array.shape} {array.dtype}{note} "
                f"-> {target}"
            )

    for model, (dataset, names) in STACK_ORDER.items():
        volumes = [_read_volume(_source(data, dataset, n)) for n in names]
        stacked = stack4d(volumes, names)
        (out / "stacks").mkdir(parents=True, exist_ok=True)
        target = out / "stacks" / f"{model}.nii.gz"
        write_nifti(target, stacked)
        print(
            f"{model} stack {list(names)} {stacked.shape} {stacked.dtype} -> {target}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
