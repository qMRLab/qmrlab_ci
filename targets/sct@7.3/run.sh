#!/usr/bin/env bash
# Fit mt_ratio and mt_sat with SCT and emit one adapter record per model.
#
# Everything below was measured by running SCT 7.3 against these archives, not read from
# its docs. Three of its argument conventions produce a silently WRONG answer rather than
# an error, and each is defended here:
#
#   -mt0 IS THE MT-OFF IMAGE and -mt1 the MT-ON one (0/1 counts saturation pulses, it is
#   not an index). compute_mtr evaluates 100*(mt0 - mt1)/mt0. Swapped, the masked median
#   goes from +45.76 to -84.25 with r = -0.937 -- and it does NOT simply negate, because
#   the denominator swaps too. Asserted below via the sign of the median.
#
#   -thr DEFAULTS TO 100 and clips MTR to +/-100. qMRLab does not clip. On the mtr archive
#   only 2 in-mask voxels are materially clipped, but those 2 of 41,778 drop pearson_r
#   from 0.9999999999999897 to 0.999542 and blow max_abs_delta from 1.1e-05 to 50.0. On the
#   mtsat archive, where MTR is derived from PDw/MTw, 44,670 in-mask voxels exceed |100|
#   and the default drops ccc from 1.0 to 0.628. A large threshold is mandatory on both.
#
#   -trmt/-trpd/-trt1 ARE SECONDS for this command, unlike sct_compute_ernst_angle -tr
#   which is milliseconds. Passing ms puts 93% of in-mask voxels under SCT's hardcoded
#   r1_threshold, so T1 = 0 almost everywhere -- and BOTH runs exit 0 with identical log
#   text, so only the values distinguish them. protocols/mtsat.yml is already in seconds,
#   so the values are rendered from it unconverted rather than retyped here.
#
# All six -tr/-fa must be passed. Omitting any one sends SCT looking for a JSON sidecar
# these archives do not ship, and it raises FileNotFoundError -- loud, so not a risk.
set -uo pipefail

DATA_ROOT="$(cd "$1" && pwd)"; shift
OUT_ROOT_ARG="$1"; shift
TARGET_ID="$1"; shift
mkdir -p "$OUT_ROOT_ARG"
OUT_ROOT="$(cd "$OUT_ROOT_ARG" && pwd)"
REPO_ROOT="$PWD"
# Written by scripts/mat_to_nifti in prepare-data. mt_ratio's archive is .mat-only, and
# this is the shared converted tree every non-MATLAB lane consumes, so SCT and qmrust
# provably fit the same bytes.
CONVERTED="${QMRLAB_CI_CONVERTED:-$REPO_ROOT/converted}"

# Read one acquisition parameter out of protocols/, so the numbers live in exactly one
# place. A missing key raises rather than defaulting -- a silently absent flip angle is
# how this adapter would produce plausible, wrong numbers.
# Also asserts the unit, because the whole reason these values live in protocols/ is that
# sct_compute_mtsat wants seconds while sct_compute_ernst_angle wants milliseconds, and a
# value silently arriving in the wrong one produces T1 = 0 across 93% of the mask with a
# clean exit code. protocols/*.yml is seconds-only by construction; this checks that the
# file still says so at the moment the number is used.
proto() {
  python3 -c "
import sys, yaml
doc = yaml.safe_load(open('protocols/$1.yml'))
node = doc['parameters']['$2']
if node['unit'] != '$3':
    raise SystemExit(f\"protocols/$1.yml: $2 is in {node['unit']!r}, this flag needs '$3'\")
print(node['value'])
"
}

for model in "$@"; do
  repeats="$(python3 -c "
from harness.config import load_targets
print(load_targets('.')['$TARGET_ID'].repeats_for('$model'))
")"
  work="$OUT_ROOT/.work/$model"
  rm -rf "$work"; mkdir -p "$work/out"
  failed=""

  case "$model" in
    mt_ratio)
      mton="$CONVERTED/mtr/MTon.nii.gz"; mtoff="$CONVERTED/mtr/MToff.nii.gz"
      [ -f "$mton" ] && [ -f "$mtoff" ] || failed="converted mt_ratio inputs not found under $CONVERTED"
      ;;
    mt_sat)
      mtw="$DATA_ROOT/mtsat/MTw.nii.gz"; pdw="$DATA_ROOT/mtsat/PDw.nii.gz"
      t1w="$DATA_ROOT/mtsat/T1w.nii.gz"
      for f in "$mtw" "$pdw" "$t1w"; do
        [ -f "$f" ] || failed="mt_sat input $f not found"
      done
      ;;
  esac

  times=()
  if [ -z "$failed" ]; then
    for r in $(seq 1 "$repeats"); do
      start=$(python3 -c 'import time; print(time.perf_counter())')
      case "$model" in
        mt_ratio)
          sct_compute_mtr -mt0 "$mtoff" -mt1 "$mton" -thr 1000000 \
            -o "$work/out/MTR.nii.gz" -v 0 1>&2
          ;;
        mt_sat)
          sct_compute_mtsat -mt "$mtw" -pd "$pdw" -t1 "$t1w" \
            -trmt "$(proto mtsat mtw_repetition_time s)" \
            -trpd "$(proto mtsat pdw_repetition_time s)" \
            -trt1 "$(proto mtsat t1w_repetition_time s)" \
            -famt "$(proto mtsat mtw_flip_angle degree)" \
            -fapd "$(proto mtsat pdw_flip_angle degree)" \
            -fat1 "$(proto mtsat t1w_flip_angle degree)" \
            -omtsat "$work/out/MTsat.nii.gz" -ot1map "$work/out/T1.nii.gz" -v 0 1>&2 &&
          # SCT emits no MTR from mtsat, but qMRLab's mt_sat MTR is exactly
          # 100*(PDw - MTw)/PDw and this reproduces it at ccc = 1.0. -mt0 is PDw.
          sct_compute_mtr -mt0 "$pdw" -mt1 "$mtw" -thr 1000000 \
            -o "$work/out/MTR.nii.gz" -v 0 1>&2
          ;;
      esac
      status=$?
      end=$(python3 -c 'import time; print(time.perf_counter())')
      if [ "$status" -ne 0 ]; then failed="sct exited non-zero for $model"; break; fi
      # Wall clock includes ~1.2-1.7 s of Python interpreter startup per invocation, which
      # is most of it: SCT self-reports 0.619 s (mtr) and 1.222 s (mtsat) for the real
      # work. This number is honest about what running the CLI costs; it is NOT a fit-time
      # comparison against a compiled target, and the site must not read it as one.
      times+=(--fit-seconds "$(python3 -c "print($end - $start)")")
    done
  fi

  # The one silent failure mode left. MTR is positive everywhere real; a negative masked
  # median means -mt0/-mt1 went in backwards, which no exit code would report.
  if [ -z "$failed" ] && [ -f "$work/out/MTR.nii.gz" ]; then
    sign="$(python3 -c "
import numpy as np
from harness.nifti import read_nifti
from harness.config import load_models
m = load_models('.')['$model']
mask = read_nifti(m.mask).values.astype(bool)
v = read_nifti('$work/out/MTR.nii.gz').values[mask]
v = v[np.isfinite(v)]
print('ok' if np.median(v) > 0 else 'negative')
")"
    if [ "$sign" != "ok" ]; then
      failed="MTR masked median is negative -- -mt0/-mt1 are almost certainly swapped"
    fi
  fi

  if [ -n "$failed" ]; then
    python3 -m scripts.emit_record --out "$OUT_ROOT/records/$model.json" \
      --target "$TARGET_ID" --software sct --version 7.3 --model "$model" \
      --status failed --error "$failed"
    continue
  fi

  # Units verified by value, not by documentation: MTsat percent (masked median 2.23),
  # T1 seconds (0.854), MTR percent (43.71). SCT writes float64 for mtsat/t1map and
  # float32 for mtr, all with scl_slope 1.0.
  case "$model" in
    mt_ratio) specs="MTR.nii.gz:MTR:percent" ;;
    mt_sat)   specs="MTsat.nii.gz:MTsat:percent T1.nii.gz:T1:s MTR.nii.gz:MTR:percent" ;;
  esac

  map_args=(); missing=""
  for spec in $specs; do
    src="${spec%%:*}"; rest="${spec#*:}"; name="${rest%%:*}"; unit="${rest##*:}"
    if [ ! -f "$work/out/$src" ]; then missing="expected output $src not produced for $model"; break; fi
    rel="maps/$model/$name.nii.gz"
    mkdir -p "$OUT_ROOT/maps/$model"
    cp "$work/out/$src" "$OUT_ROOT/$rel"
    map_args+=(--map "$name:$unit:$rel")
  done

  if [ -n "$missing" ]; then
    python3 -m scripts.emit_record --out "$OUT_ROOT/records/$model.json" \
      --target "$TARGET_ID" --software sct --version 7.3 --model "$model" \
      --status failed --error "$missing"
    continue
  fi

  voxels=$(python3 -c "
from harness.nifti import read_nifti
from harness.config import load_models
import numpy as np
print(int(np.count_nonzero(read_nifti(load_models('.')['$model'].mask).values)))")

  python3 -m scripts.emit_record --out "$OUT_ROOT/records/$model.json" \
    --target "$TARGET_ID" --software sct --version 7.3 --model "$model" \
    --status ok --n-voxels "$voxels" "${times[@]}" "${map_args[@]}"
done

rm -rf "$OUT_ROOT/.work"
