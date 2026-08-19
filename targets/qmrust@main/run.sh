#!/usr/bin/env bash
# Fit each model with the qmrust CLI and emit one adapter record per model.
#
# qmrust's `fit` subcommand takes --data/--mat-data/--mat-dir, NOT the --nii-data/
# --nii-dir/--aux family (those belong to `qmrust bidsify`, a separate subcommand).
# Four models (b1_afi, b1_dam, mt_ratio, mt_sat) declare a `Named`/`Series`
# measurement of more than one acquisition, and `fit --data` only accepts ONE
# already-stacked 4D volume -- there is no per-volume flag. So for those four,
# prepare_input() builds a stacked 4D NIfTI once per model (outside the timed
# repeat loop: it is data prep, not part of what is being timed) in the volume
# order each model's Rust source declares (see the ROLES/AXIS comments below).
#
# mt_ratio's own archive ships .mat (MTon.mat/MToff.mat/Mask.mat, not NIfTI), and
# this repo's Python dependencies are numpy+PyYAML only (scipy is a dev extra,
# not installed in the rust-lane CI job) -- so this script never reads a .mat
# file in Python. Where qmrust itself reads .mat natively (--mat-data/--mat-dir,
# both Rust), that is used directly. For mt_ratio, `qmrust bidsify --mat-dir` is
# used purely as a .mat -> NIfTI converter (letting Rust parse the .mat), and the
# resulting NIfTIs are stacked the same way as the pure-NIfTI models.
#
# Output filenames and units below are the ones qmrust actually writes, verified
# by running each model against the real archives (they are not all what a
# canonical map name would suggest -- b1_afi/b1_dam write B1.nii.gz, not
# B1map.nii.gz; mt_sat writes MTSAT.nii.gz, not MTsat.nii.gz; MTsat's canonical
# unit is percent, matching what qmrust actually produces here).
set -uo pipefail

DATA_ROOT="$(cd "$1" && pwd)"; shift
OUT_ROOT_ARG="$1"; shift
TARGET_ID="$1"; shift
mkdir -p "$OUT_ROOT_ARG"
OUT_ROOT="$(cd "$OUT_ROOT_ARG" && pwd)"
REPO_ROOT="$PWD"
QMRUST_HOME="$REPO_ROOT/qmrust"
BIN="$QMRUST_HOME/target/release/qmrust"
RECIPES="$QMRUST_HOME/recipes/non-bids"

# Locate an INPUT file within an unpacked archive. Deliberately blind to
# FitResults/: that directory holds qMRLab's own fitted output, and several
# archives ship files there under names identical to the inputs. Mirrors
# scripts/derive_masks.py::_find -- ambiguity raises rather than picking, because
# there is no ordering rule here that is right by construction.
find_one() {
  local dir="$DATA_ROOT/$1" name="$2" hits count
  hits="$(find "$dir" -name "$name" -not -path '*/FitResults/*' 2>/dev/null | sort)"
  count="$(printf '%s\n' "$hits" | grep -c '^.' || true)"
  if [ "$count" -eq 0 ]; then
    echo "find_one: $name not found under $dir (excluding FitResults/)" >&2
    return 1
  fi
  if [ "$count" -gt 1 ]; then
    echo "find_one: $name is ambiguous under $dir: $hits" >&2
    return 1
  fi
  printf '%s\n' "$hits"
}

# Stack N same-shape 3D volumes (or 2D single-slice volumes) into one 4D NIfTI,
# in the given order, via harness.nifti (no scipy -- see the file header). Must
# be called with cwd = REPO_ROOT so `harness` is importable.
stack4d() {
  local out="$1"; shift
  mkdir -p "$(dirname "$out")"
  python3 - "$out" "$@" <<'PYEOF'
import gzip
import pathlib
import struct
import sys

import numpy as np

from harness.nifti import read_nifti

out, paths = sys.argv[1], sys.argv[2:]
vols = []
for p in paths:
    n = read_nifti(p)
    v = n.values.reshape(n.shape, order="F")
    while v.ndim < 3:
        v = v.reshape(v.shape + (1,))
    vols.append(v.astype(np.float32))

shape3 = vols[0].shape
for v in vols:
    if v.shape != shape3:
        raise SystemExit(f"stack4d: shape mismatch {v.shape} != {shape3}")

shape = shape3 + (len(vols),)
hdr = bytearray(348)
struct.pack_into("<i", hdr, 0, 348)
dim = [4] + list(shape) + [1] * (7 - len(shape))
struct.pack_into("<8h", hdr, 40, *dim)
struct.pack_into("<h", hdr, 70, 16)   # float32
struct.pack_into("<h", hdr, 72, 32)
struct.pack_into("<f", hdr, 108, 352.0)
struct.pack_into("<8f", hdr, 76, *([1.0] * 8))
struct.pack_into("<2f", hdr, 112, 1.0, 0.0)
hdr[344:348] = b"n+1\x00"
body = b"".join(np.asfortranarray(v).tobytes(order="F") for v in vols)
pathlib.Path(out).write_bytes(gzip.compress(bytes(hdr) + b"\x00" * 4 + body, mtime=0))
print(f"stack4d: wrote {out} shape={shape}", file=sys.stderr)
PYEOF
}

# Build any derived input a model's fit_args() needs, once per model (not once
# per repeat -- this is data prep, and its cost must not be charged to fit time).
# No-op for models that fit their archive's native files directly.
prepare_input() {
  case "$1" in
    b1_afi)
      # Series, rows = repetition_times: [0.02, 0.10] -> [TR1, TR2] order.
      stack4d "$work/input/stacked.nii.gz" \
        "$(find_one b1_afi AFIData1.nii.gz)" "$(find_one b1_afi AFIData2.nii.gz)" ;;
    b1_dam)
      # Series, rows = flip_angles: [60, 120] -> [alpha, 2*alpha] order.
      stack4d "$work/input/stacked.nii.gz" \
        "$(find_one b1_dam SFalpha.nii.gz)" "$(find_one b1_dam SF2alpha.nii.gz)" ;;
    mt_sat)
      # Named, ROLES = ["MTw", "PDw", "T1w"] (qmrust-core mt_sat/model.rs).
      stack4d "$work/input/stacked.nii.gz" \
        "$(find_one mtsat MTw.nii.gz)" "$(find_one mtsat PDw.nii.gz)" "$(find_one mtsat T1w.nii.gz)"
      ;;
    mt_ratio)
      # Named, ROLES = ["MTon", "MToff"] (qmrust-core mt_ratio/model.rs). Archive
      # ships .mat; bidsify (Rust) converts to NIfTI without needing scipy here.
      local mtr_dir mton mtoff mask
      mtr_dir="$(dirname "$(find_one mtr MTon.mat)")" || return 1
      rm -rf "$work/bids"
      "$BIN" bidsify --model mt_ratio --mat-dir "$mtr_dir" \
        --config "$RECIPES/mt_ratio_config.yaml" --subject 01 --out "$work/bids" 1>&2 || return 1
      mton="$(find "$work/bids" -name 'sub-*_mt-on_MTR.nii.gz' | head -1)"
      mtoff="$(find "$work/bids" -name 'sub-*_mt-off_MTR.nii.gz' | head -1)"
      mask="$(find "$work/bids" -name 'sub-*_desc-brain_mask.nii.gz' | head -1)"
      if [ -z "$mton" ] || [ -z "$mtoff" ]; then
        echo "prepare_input(mt_ratio): bidsify did not produce mt-on/mt-off NIfTIs" >&2
        return 1
      fi
      stack4d "$work/input/stacked.nii.gz" "$mton" "$mtoff"
      if [ -n "$mask" ]; then cp "$mask" "$work/input/mask.nii.gz"; fi
      ;;
  esac
}

# canonical map name -> qmrust output file : unit, as verified by actually
# running each model (see the header comment for the two surprises).
map_outputs() {
  case "$1" in
    inversion_recovery) echo "T1.nii.gz:T1:s" ;;
    qmt_spgr)           echo "F.nii.gz:F:fraction kr.nii.gz:kr:s^-1 R1f.nii.gz:R1f:s^-1 R1r.nii.gz:R1r:s^-1 T2f.nii.gz:T2f:s T2r.nii.gz:T2r:s" ;;
    mono_t2)            echo "T2.nii.gz:T2:s M0.nii.gz:M0:au" ;;
    vfa_t1)             echo "T1.nii.gz:T1:s M0.nii.gz:M0:au" ;;
    mt_ratio)           echo "MTR.nii.gz:MTR:percent" ;;
    mt_sat)             echo "MTSAT.nii.gz:MTsat:percent T1.nii.gz:T1:s MTR.nii.gz:MTR:percent" ;;
    b1_dam)             echo "B1.nii.gz:B1map:au" ;;
    b1_afi)             echo "B1.nii.gz:B1map:au" ;;
  esac
}

fit_args() {
  case "$1" in
    inversion_recovery) echo "--mat-data $(find_one ir IRData.mat) --mask $(find_one ir Mask.mat) --config $RECIPES/irt1_config.yaml" ;;
    # SledPikeRP, NOT Ramani. qMRLab's qmt_spgr declares
    # 'Model',{'SledPikeRP','SledPikeCW','Yarnykh','Ramani'} and takes the FIRST as its
    # default, so all 14 MATLAB targets fit SledPikeRP -- and so did the archive's own
    # FitResults. Using qmrust's Ramani recipe here would compare two different models and
    # publish the difference as a cross-implementation result.
    qmt_spgr)           echo "--mat-dir $(dirname "$(find_one qmt MTdata.mat)") --config $RECIPES/qmt_config_sledpikerp.yaml" ;;
    mono_t2)             echo "--data $(find_one mono_t2 SEdata.nii.gz) --mask $(find_one mono_t2 Mask.nii.gz) --config $RECIPES/mono_t2_config.yaml" ;;
    vfa_t1)              echo "--data $(find_one vfa_t1 VFAData.nii.gz) --mask $(find_one vfa_t1 Mask.nii.gz) --b1map $(find_one vfa_t1 B1map.nii.gz) --config $RECIPES/vfa_t1_config.yaml" ;;
    b1_dam)               echo "--data $work/input/stacked.nii.gz --config $RECIPES/b1_dam_config.yaml" ;;
    b1_afi)                echo "--data $work/input/stacked.nii.gz --config $RECIPES/b1_afi_config.yaml" ;;
    mt_sat)                 echo "--data $work/input/stacked.nii.gz --config $RECIPES/mt_sat_config.yaml" ;;
    mt_ratio)
      if [ -f "$work/input/mask.nii.gz" ]; then
        echo "--data $work/input/stacked.nii.gz --mask $work/input/mask.nii.gz --config $RECIPES/mt_ratio_config.yaml"
      else
        echo "--data $work/input/stacked.nii.gz --config $RECIPES/mt_ratio_config.yaml"
      fi
      ;;
  esac
}

for model in "$@"; do
  repeats="$(python3 -c "
from harness.config import load_targets
print(load_targets('.')['$TARGET_ID'].repeats_for('$model'))
")"
  work="$OUT_ROOT/.work/$model"
  rm -rf "$work"; mkdir -p "$work/out"

  failed=""
  prepare_input "$model" || failed="preparing input for $model failed"

  times=()
  if [ -z "$failed" ]; then
    for r in $(seq 1 "$repeats"); do
      start=$(python3 -c 'import time; print(time.perf_counter())')
      "$BIN" fit $(fit_args "$model") --output-dir "$work/out" 1>&2
      status=$?
      end=$(python3 -c 'import time; print(time.perf_counter())')
      if [ "$status" -ne 0 ]; then failed="qmrust fit exited non-zero"; break; fi
      times+=(--fit-seconds "$(python3 -c "print($end - $start)")")
    done
  fi

  if [ -n "$failed" ]; then
    python3 -m scripts.emit_record --out "$OUT_ROOT/records/$model.json" \
      --target "$TARGET_ID" --software qmrust --version main --model "$model" \
      --status failed --error "$failed"
    continue
  fi

  map_args=(); missing=""
  for spec in $(map_outputs "$model"); do
    src="${spec%%:*}"; rest="${spec#*:}"; name="${rest%%:*}"; unit="${rest##*:}"
    found="$work/out/$src"
    if [ ! -f "$found" ]; then missing="expected output $src not produced for $model"; break; fi
    rel="maps/$model/$name.nii.gz"
    mkdir -p "$OUT_ROOT/maps/$model"
    cp "$found" "$OUT_ROOT/$rel"
    map_args+=(--map "$name:$unit:$rel")
  done

  if [ -n "$missing" ]; then
    python3 -m scripts.emit_record --out "$OUT_ROOT/records/$model.json" \
      --target "$TARGET_ID" --software qmrust --version main --model "$model" \
      --status failed --error "$missing"
    continue
  fi

  voxels=$(python3 -c "
from harness.nifti import read_nifti
import numpy as np
print(int(np.count_nonzero(read_nifti('masks/$model.nii.gz').values)))")

  python3 -m scripts.emit_record --out "$OUT_ROOT/records/$model.json" \
    --target "$TARGET_ID" --software qmrust --version main --model "$model" \
    --status ok --n-voxels "$voxels" "${times[@]}" "${map_args[@]}"
done

rm -rf "$OUT_ROOT/.work"
