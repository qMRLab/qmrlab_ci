#!/usr/bin/env bash
# Fit five models with the QUIT CLI and emit one adapter record per model.
#
# Every invocation and every filename below was measured by running qi v3.4 against these
# archives. Four things bit during that spike and are defended here:
#
#   GEOMETRY ABORTS THE PROCESS. ITK raises "Inputs do not occupy the same physical space!"
#   and dies with SIGABRT whenever two inputs disagree on origin/spacing/direction.
#   masks/*.nii.gz carry NO geometry at all (qform_code=0, sform_code=0, pixdim 0), so they
#   may be passed only alongside the harness-written converted/stacks/*, never alongside an
#   osf-data/ volume. Measured mitigation: -m NEVER changes an in-mask value in any of
#   these commands -- it only zeroes outside-mask voxels -- so it is simply omitted where
#   the geometry forbids it. The harness masks in Python anyway.
#
#   BARE `qi mtr` RETURNS THE WRONG QUANTITY. v3.4's qi_mtr.cpp:87 is
#   `contrasts.push_back({"MTR", {0}, {}, {1}, true})`, and against MTContrast's member
#   order that trailing `true` initialises `scale`, NOT `reverse` -- which stays false. The
#   kernel then emits 100*vol0/vol1 instead of MTR. Measured: masked median 54.235 against
#   qMRLab's 45.747, and pearson_r EXACTLY -1. An explicit contrasts JSON is necessary --
#   and NOT sufficient: a JSON without "ref" leaves ref_indices empty, ref = 0, and every
#   voxel non-finite with exit 0. The JSON below carries "ref".
#
#   `qi afi` WITHOUT --flip IS OFF BY 60/55 AND LANDS IN AMBER, NOT RED. QUIT's default
#   nominal flip is 55 and ours is 60, so omitting it scales B1 by exactly 1.0909. Measured
#   on the comparison mask that reads rel_median_diff +9.09% with ccc 0.9467 and r = 1.0 --
#   inside amber on both columns and red on neither, i.e. it would read as a plausible
#   calibration finding rather than a misconfiguration. AFI_angle is IDENTICAL either way,
#   so only a B1-side assertion catches it.
#
#   `qi multiecho --algo=n` IS UNUSABLE ON THIS ARCHIVE. 17,143 of 27,434 in-mask voxels
#   (62.5%) sit exactly at the 5 s upper bound, exit 0. Log-linear is the only viable
#   algorithm here, which is a genuine estimator difference against qMRLab's nonlinear
#   exponential and is declared in comparability.yml rather than hidden.
set -uo pipefail

DATA_ROOT="$(cd "$1" && pwd)"; shift
OUT_ROOT_ARG="$1"; shift
TARGET_ID="$1"; shift
mkdir -p "$OUT_ROOT_ARG"
OUT_ROOT="$(cd "$OUT_ROOT_ARG" && pwd)"
REPO_ROOT="$PWD"
BIN="$REPO_ROOT/qi"
CONVERTED="${QMRLAB_CI_CONVERTED:-$REPO_ROOT/converted}"
# Unset, every call warns on stderr and defaults to this anyway. Set so the logs are clean.
export QUIT_EXT=NIFTI_GZ

# One acquisition parameter out of protocols/, with its unit asserted at the point of use.
proto() {
  python3 -c "
import yaml
node = yaml.safe_load(open('protocols/$1.yml'))['parameters']['$2']
if node['unit'] != '$3':
    raise SystemExit(f\"protocols/$1.yml: $2 is in {node['unit']!r}, this flag needs '$3'\")
v = node.get('value', node.get('values'))
print(v if not isinstance(v, list) else ' '.join(str(x) for x in v))
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

  # Per-model input prep and JSON, built once -- data prep is not part of what is timed.
  case "$model" in
    vfa_t1)
      python3 -c "
import yaml, json
p = yaml.safe_load(open('protocols/vfa_t1.yml'))['parameters']
json.dump({'SPGR': {'TR': p['repetition_time']['value'],
                    'FA': p['flip_angle']['values']}}, open('$work/in.json','w'))"
      # The ONLY file rewrite in this adapter, and it is two bytes. osf-data's B1map is a
      # 2-D NIfTI (dim[0] == 2); ITK loses its out-of-plane direction reading that into a
      # 3-D image, so it clashes with VFAData even though their srow bytes are identical.
      # Patching dim[0] 2 -> 3 was verified bit-identical in-mask to a full header rewrite.
      python3 -c "
import gzip, pathlib, struct
src = pathlib.Path('$DATA_ROOT/vfa_t1/B1map.nii.gz')
b = bytearray(gzip.decompress(src.read_bytes()))
struct.pack_into('<h', b, 40, 3)
pathlib.Path('$work/B1_dim3.nii.gz').write_bytes(gzip.compress(bytes(b), mtime=0))" \
        || failed="could not patch the vfa_t1 B1 map header"
      ;;
    mono_t2)
      # TR is REQUIRED by QUIT's MultiEcho parser and PROVABLY INERT: T2 and PD are
      # bit-identical (equal voxel_sha256) at TR = 0.05, 0.5, 1.0, 2.0, 5.0 and 1e6 s, for
      # each of --algo l, a and n. protocols/mono_t2.yml therefore carries no TR -- none
      # exists in the archive either -- and 1.0 is passed here as an explicit placeholder.
      python3 -c "
import yaml, json
te = yaml.safe_load(open('protocols/mono_t2.yml'))['parameters']['echo_time']['values']
esp = te[1] - te[0]
# QUIT's model is a uniformly spaced train and cannot express anything else; asserting it
# here stops a non-uniform protocol being silently resampled onto an even one.
assert all(abs((te[i+1]-te[i]) - esp) < 1e-9 for i in range(len(te)-1)), te
json.dump({'MultiEcho': {'TR': 1.0, 'TE1': te[0], 'ESP': esp, 'ETL': len(te)}},
          open('$work/in.json','w'))" || failed="mono_t2 echo train is not uniformly spaced"
      ;;
    b1_afi)
      # --flip is mandatory: QUIT defaults to 55 and ours is 60, and omitting it scales B1
      # by exactly 60/55 into AMBER rather than red (measured rmd +9.09%, ccc 0.9467).
      # --ratio is TR2/TR1, derived rather than hardcoded -- it happens to equal QUIT's
      # own default of 5 on this archive, which is a fact about the data, not the tool.
      afi_flip="$(proto b1_afi nominal_flip_angle degree)"
      afi_ratio="$(python3 -c "
import yaml
tr = yaml.safe_load(open('protocols/b1_afi.yml'))['parameters']['repetition_time']
assert tr['unit'] == 's', tr
lo, hi = tr['values']
print(hi / lo)")" || failed="could not derive the b1_afi TR ratio"
      ;;
    mt_ratio)
      # Indices into converted/stacks/mt_ratio.nii.gz, whose order is (MTon, MToff) per
      # scripts/mat_to_nifti.py::STACK_ORDER. "ref" is mandatory -- see the header.
      cat > "$work/in.json" <<'JSON'
{"contrasts":[{"name":"MTR","add":[0],"sub":[],"ref":[1],"reverse":true}]}
JSON
      ;;
    mt_sat)
      python3 -c "
import yaml, json
p = yaml.safe_load(open('protocols/mtsat.yml'))['parameters']
json.dump({'MTSat': {'TR_PDw': p['pdw_repetition_time']['value'],
                     'TR_T1w': p['t1w_repetition_time']['value'],
                     'TR_MTw': p['mtw_repetition_time']['value'],
                     'FA_PDw': p['pdw_flip_angle']['value'],
                     'FA_T1w': p['t1w_flip_angle']['value'],
                     'FA_MTw': p['mtw_flip_angle']['value']}}, open('$work/in.json','w'))"
      ;;
  esac

  times=()
  if [ -z "$failed" ]; then
    for r in $(seq 1 "$repeats"); do
      start=$(python3 -c 'import time; print(time.perf_counter())')
      ( cd "$work/out" && case "$model" in
          vfa_t1)
            "$BIN" despot1 "$DATA_ROOT/vfa_t1/VFAData.nii.gz" --json="$work/in.json" \
              --algo=l -T 1 -b "$work/B1_dim3.nii.gz" -o "" ;;
          mono_t2)
            "$BIN" multiecho "$DATA_ROOT/mono_t2/SEdata.nii.gz" --json="$work/in.json" \
              --algo=l -T 1 -o "" ;;
          mt_ratio)
            "$BIN" mtr "$CONVERTED/stacks/mt_ratio.nii.gz" --json="$work/in.json" \
              -T 1 -m "$REPO_ROOT/masks/mt_ratio.nii.gz" -o "" ;;
          b1_afi)
            "$BIN" afi "$CONVERTED/stacks/b1_afi.nii.gz" -T 1 \
              --flip="$afi_flip" --ratio="$afi_ratio" -o "" ;;
          mt_sat)
            "$BIN" mtsat "$DATA_ROOT/mtsat/PDw.nii.gz" "$DATA_ROOT/mtsat/T1w.nii.gz" \
              "$DATA_ROOT/mtsat/MTw.nii.gz" --json="$work/in.json" -T 1 -o "" &&
            "$BIN" mtr "$CONVERTED/stacks/mt_sat.nii.gz" --json=<(printf '%s' \
              '{"contrasts":[{"name":"MTRS","add":[0],"sub":[],"ref":[1],"reverse":true}]}') \
              -T 1 -o "" ;;
        esac ) 1>&2
      status=$?
      end=$(python3 -c 'import time; print(time.perf_counter())')
      if [ "$status" -ne 0 ]; then failed="qi exited non-zero for $model"; break; fi
      times+=(--fit-seconds "$(python3 -c "print($end - $start)")")
    done
  fi

  # canonical map name -> qi output file : produced unit. MTSat_R1 is s^-1, NOT T1 in s --
  # models/mt_sat.yml declares `transform: reciprocal` on that map so the inversion is done
  # once in Python rather than here (spec §5.2). MTSat_PD has no canonical map; dropped.
  case "$model" in
    vfa_t1)   specs="D1_T1.nii.gz:T1:s D1_PD.nii.gz:M0:au" ;;
    mono_t2)  specs="ME_T2.nii.gz:T2:s ME_PD.nii.gz:M0:au" ;;
    mt_ratio) specs="MTR.nii.gz:MTR:percent" ;;
    b1_afi)   specs="AFI_B1.nii.gz:B1map:fraction" ;;
    mt_sat)   specs="MTSat_delta.nii.gz:MTsat:percent MTSat_R1.nii.gz:T1:s^-1 MTRS.nii.gz:MTR:percent" ;;
  esac

  if [ -z "$failed" ]; then
    case "$model" in
      mt_ratio)
        # A sign check does NOT catch the bare-default trap: 100*MTon/MToff keeps the sign.
        # Recomputing the contrast in Python and requiring the medians to agree catches both
        # that (median off by 8.47) and any add/ref transposition.
        check="$(python3 -c "
import numpy as np
from harness.nifti import read_nifti
st = read_nifti('$CONVERTED/stacks/mt_ratio.nii.gz')
v = st.values.reshape(st.shape, order='F')
mton, mtoff = v[..., 0].ravel(order='F'), v[..., 1].ravel(order='F')
mask = read_nifti('masks/mt_ratio.nii.gz').values.astype(bool)
with np.errstate(divide='ignore', invalid='ignore'):
    want = 100.0 * (mtoff - mton) / mtoff
got = read_nifti('$work/out/MTR.nii.gz').values
sel = mask & np.isfinite(want) & np.isfinite(got)
print('ok' if abs(np.median(got[sel]) - np.median(want[sel])) < 1e-3 else 'mismatch')")"
        [ "$check" = "ok" ] || failed="qi mtr output does not match 100*(MToff-MTon)/MToff -- the contrasts JSON is wrong or was ignored"
        ;;
      b1_afi)
        # B1 must equal angle/nominal. AFI_angle is identical with and without --flip, so
        # only this catches a missing or wrong --flip.
        check="$(python3 -c "
import numpy as np
from harness.nifti import read_nifti
b1 = read_nifti('$work/out/AFI_B1.nii.gz').values
mask = read_nifti('masks/b1_afi_interior.nii.gz').values.astype(bool)
sel = mask & np.isfinite(b1)
m = float(np.median(b1[sel]))
print('ok' if 0.5 < m < 1.5 else f'suspect median B1 {m:.4f}')")"
        [ "$check" = "ok" ] || failed="qi afi B1 median is not near 1.0 ($check) -- --flip is probably wrong"
        ;;
    esac
  fi

  if [ -n "$failed" ]; then
    python3 -m scripts.emit_record --out "$OUT_ROOT/records/$model.json" \
      --target "$TARGET_ID" --software quit --version v3.4 --model "$model" \
      --status failed --error "$failed"
    continue
  fi

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
      --target "$TARGET_ID" --software quit --version v3.4 --model "$model" \
      --status failed --error "$missing"
    continue
  fi

  voxels=$(python3 -c "
from harness.nifti import read_nifti
from harness.config import load_models
import numpy as np
print(int(np.count_nonzero(read_nifti(load_models('.')['$model'].mask).values)))")

  python3 -m scripts.emit_record --out "$OUT_ROOT/records/$model.json" \
    --target "$TARGET_ID" --software quit --version v3.4 --model "$model" \
    --status ok --n-voxels "$voxels" "${times[@]}" "${map_args[@]}"
done

rm -rf "$OUT_ROOT/.work"
