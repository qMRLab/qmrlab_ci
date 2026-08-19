# qmrlab_ci — Cross-version, cross-implementation qMRI benchmark

**Date:** 2026-08-19
**Status:** Design approved, pending implementation plan
**Author:** Mathieu Boudreau (with Claude)

## 1. Purpose

`qmrlab_ci` runs a fixed set of qMRI fitting models against fixed input data across
every qMRLab release and every participating software implementation, then publishes
the resulting maps' statistics, byte-equivalence, and processing times as a browsable
record.

It serves two goals:

1. **Longitudinal benchmark record.** How qMRLab's outputs and runtimes have evolved
   across its release history, published so a reader can see it.
2. **Cross-implementation equivalence.** Evidence that qmrust — and future ports —
   reproduce qMRLab's numbers.

It is explicitly **not** a pull-request regression gate. It runs weekly and on manual
trigger. Nothing in this design forbids adding a gate later, but no requirement here
is justified by one.

Prior art: `axondeepseg/seg_ci`, which does the same for AxonDeepSeg, itself derived
from `QSMxT/QSM-CI`.

## 2. Scope

### 2.1 Models

Eight, to start: `qmt_spgr`, `inversion_recovery`, `vfa_t1`, `b1_dam`, `b1_afi`,
`mono_t2`, `mt_ratio`, `mt_sat`.

### 2.2 Softwares and versions

Fifteen targets: every published qMRLab release, plus `master`, plus qmrust.

| Target | Ref | Notes |
|---|---|---|
| qMRLab V1 | `V1` | qMTLab, 2016. See §2.4 |
| qMRLab v2.0.0 … v2.0.5 | `v2.0.0`, `2.0.1`, `2.0.2`, `v2.0.3`, `v2.0.5` | 2017 |
| qMRLab v2.1.0 … v3.0.0 | `v2.1.0`, `v2.2.0`, `v2.3.0`, `v2.4.0`, `v2.4.1`, `v2.5.0`, `v3.0.0` | 2018–2026 |
| qMRLab `master` | `master` | Moves; recomputed every run |
| qmrust `main` | `main` | Rust reimplementation |

`v2.4.1-zenodo` is an archival duplicate of `v2.4.1` and is excluded.

**Tag names are not uniform.** `2.0.1` and `2.0.2` carry no `v` prefix while every
other tag does. This is why `source.ref` is declared per target (§5) rather than
derived from the version string.

Several tags exist without a corresponding published release: `v2.0.4`, `v2.0.14`,
`v2.3.1`, `v2.4.2`, `v2.5.0b`, `ismrm2022`. "Every release" is read here as every
*published release*. Each of those tags is one additional directory if wanted (§13).

### 2.3 Three API eras

The 15 targets span three incompatible qMRLab APIs. This is the main reason install
and drive logic lives per-target (§5) rather than in shared code.

| Era | Releases | Layout | Model API |
|---|---|---|---|
| **1. qMTLab** | V1 | `Common/`, `SPGR/`, `SIRFSE/`, `bSSFP/`, `qMTLab.m` | No model objects, no `FitData`. GUI-era |
| **2. CamelCase** | v2.0.0 – v2.0.5 | `Models/`, `Common/FitData.m` | `Model = SPGR(); FitData(data, Model, ...)` |
| **3. snake_case** | v2.1.0 – v3.0.0, master | `src/Models/` | Current API |

**Era 1 is the significant risk in this scope.** V1 has no `Models/` tree and no
`FitData.m` at all — it is a GUI application (`qMTLab.m` + `qMTLab.fig`) with three
qMT method directories beside it. It contributes exactly **one** model, `qmt_spgr`, and
driving it headlessly means calling into `SPGR/` directly with hand-constructed
protocol and fit-option structs. It is scoped in deliberately, but it is archaeology,
and it is the target most likely to end a run as `status: failed`. Nothing else depends
on it: it is one directory, and its failure is one red cell (§10).

### 2.4 Model availability by version

Not every model exists in every release. This is declared data (§5), not something the
harness discovers. Verified by inspecting each tag's tree.

| Model | V1 | 2.0.0–2.0.5 | 2.1.0 | 2.2.0 | 2.3.0 | 2.4.0 | 2.4.1 | 2.5.0 | 3.0.0 | master | qmrust |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `qmt_spgr` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `inversion_recovery` | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `vfa_t1` | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `b1_dam` | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `mt_sat` | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `mt_ratio` | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `mono_t2` | — | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `b1_afi` | — | — | — | — | — | — | — | ✓ | ✓ | ✓ | ✓ |

In eras 1 and 2 the file names differ from the canonical model id: `SPGR.m`,
`InversionRecovery.m`, `VFA_T1.m`, `B1_DAM.m`, `MTSAT.m`. The canonical id is what the
record and the site use; the mapping is the adapter's business.

A missing combination renders as `not_applicable` — a hole, never a failure.

## 3. Constraints established during design

These are findings, not assumptions. Each one shaped a decision below.

### 3.1 MATLAB licensing dictates the execution model

MATLAB is auto-licensed **only** through the `matlab-actions/*` actions, on
GitHub-hosted runners, for **public** repositories. The licensing happens inside the
`matlab-batch` wrapper that `matlab-actions/run-command` invokes — not in the MATLAB
installation itself. Invoking the `matlab` binary directly, or running MATLAB inside a
`mathworks/matlab` Docker container, bypasses that wrapper and fails with
"Unable to find a license for MATLAB". qMRLab's own `.github/workflows/matlab.yml`
carries a comment documenting this exact failure on its GUI job.

Consequences:

- **`qmrlab_ci` must be a public repository.** No token or secret is then required.
  `qMRLab/qMRLab` has zero Actions secrets and its workflow references none, confirming
  the free grant is what it already runs on.
- **The seg_ci container-per-target pattern cannot carry the MATLAB legs.**
- Should the repo ever need to be private, or need pre-R2021a MATLAB, the escape hatch
  is an `MLM_LICENSE_TOKEN` from the MATLAB Batch Licensing Pilot (see §12).

### 3.2 R2021a is the floor

`matlab-actions/setup-matlab@v2` supports R2021a and later. (`mathworks/matlab` Docker
images reach R2020b, but need a license per §3.1.) Since qMRLab v2.1.0 (2018) through
v2.4.1 (Sep 2020) all predate R2021a, "pin each version to its era" collapses to:

| Target | MATLAB release |
|---|---|
| V1, v2.0.0 – v2.0.5, v2.1.0 – v2.4.1 | R2021a |
| v2.5.0, v3.0.0 | R2026a |
| `master` | latest |

**R2021a is the oldest MATLAB this design can reach**, and every target older than
v2.5.0 gets it. Reaching R2020b — one release further back — requires the container
route and an `MLM_LICENSE_TOKEN` (§12), which is not worth one release. Nothing older
than R2020b is available on hosted runners at all, so era-appropriate MATLAB for the
2016–2017 targets does not exist as an option; R2021a is the floor in practice as well
as in principle.

Running 2016-era code on R2021a is expected to need fixes. That is what each target's
`setup.sh` is for (§5). If a target proves genuinely unrunnable on R2021a, the fallback
is an Octave lane — qMRLab ships `qmrlab/octaveci` and `qmrlab/octjn` images — added as
a third `lane` value. That is a per-target escape hatch, not a plan, and it carries a
real cost: Octave-vs-MATLAB numerical differences would confound that target's
comparison, so it must be recorded in the environment block and shown on the site.

The MATLAB release is recorded as a first-class field on every result so the
version/runtime confound stays visible rather than baked in.

### 3.3 Per-version data URLs are a trap

Each qMRLab model object carries its own `onlineData_url`, so each version would
download its own vintage of the demo data. Comparing versions that way varies input
and output simultaneously. The harness therefore fetches data **once**, centrally, and
feeds byte-identical inputs to every target (§6.1).

### 3.4 Docker buys nothing here

seg_ci inherited containers from QSM-CI, which needs them because contributors submit
algorithms with mutually incompatible dependency trees. `qmrlab_ci` controls every
target, has few of them, cannot containerize the MATLAB legs anyway, and builds qmrust
with a stock Rust toolchain action. No Docker in phase 1.

## 4. Architecture

```
prepare-data ──> plan ──┬──> fit-matlab (matrix)  ──┐
                        └──> fit-native (matrix)  ──┴──> analyze ──> publish
```

One GitHub Actions workflow. Triggers: weekly `schedule`, `workflow_dispatch`, and
pushes touching the harness or `targets/`.

`fail-fast: false` throughout — one version failing to install must not discard the
other seven results.

## 5. The target contract

A **target** is one thing that produces maps: a qMRLab release, qMRLab master, qmrust,
or a future software. One directory each.

```
targets/
  qmrlab@v2.1.0/target.yml
  qmrlab@v2.4.1/{target.yml, setup.sh}
  qmrlab@master/target.yml
  qmrust@main/{target.yml, setup.sh}
```

```yaml
id: qmrlab@v2.4.1
software: qmrlab
version: v2.4.1
lane: matlab              # matlab | native
matlab_release: R2021a    # matlab lane only
matlab_products: [Image_Processing_Toolbox, Optimization_Toolbox, Statistics_and_Machine_Learning_Toolbox]
source: {repo: qMRLab/qMRLab, ref: v2.4.1}
models: [qmt_spgr, inversion_recovery, vfa_t1, b1_dam, mono_t2, mt_ratio, mt_sat]
repeats: {default: 5, qmt_spgr: 1}
```

What the contract buys:

- **Model availability is declared, not discovered.** `b1_afi` absent from v2.4.1 is a
  fact in the file, so a missing map reads as `not_applicable`.
- **Install archaeology is local.** An optional `setup.sh` beside `target.yml` holds
  version-specific install fixes, pinned to the version that needs them rather than
  leaking into shared code. This is the analogue of the manual fixes required for old
  AxonDeepSeg versions in seg_ci.
- **Adding a target is adding a directory.** The Actions matrix globs
  `targets/*/target.yml`; a third software needs no workflow edit.

### 5.1 Why the lanes differ at the fit step

`matlab-actions/run-command` is a workflow *step*, not a CLI, so the MATLAB lane's fit
must be a step invoking a shared driver that loops over all of that target's models in
one MATLAB session. This is the right shape regardless: one MATLAB startup per target
rather than one per model, and MATLAB startup plus install dominates job wall-clock.

The native lane runs the target's own script.

If a future target genuinely needs a frozen environment, `lane: container` is a third
value in a field that already exists. No scaffolding is built for it now.

### 5.2 Adapter output contract

Both lanes write an identical tree, uploaded as artifact `results-<target-id>`:

```
results/<target-id>/
  maps/<model>/<mapname>.nii.gz
  records/<model>.json      # thin: status, timing, units, environment
  logs/<model>.log
```

Adapters emit maps **exactly as the software produced them** — no unit conversion, no
renaming beyond the canonical map name — and declare the unit in the record. See §7.

**Adapters do not compute statistics or hashes.** They report what they ran, how long
it took, and where the maps are. Every derived number is computed once, in `analyze`
(§9). The alternative — each adapter computing its own masked mean — would mean the
same statistic implemented in MATLAB, Rust, and Python, and any drift between those
three implementations would be indistinguishable from a real difference between the
softwares. That is precisely the measurement this repo exists to make, so it cannot be
left to the thing being measured.

## 6. Data

### 6.1 Canonical inputs

`data/sources.yml` pins each OSF archive by URL-with-`?version=` **and SHA-256**. The
URLs are lifted from qmrust's `ci/datasets.sh`, which already pins versions:

| Dataset | URL |
|---|---|
| ir | `https://osf.io/cmg9z/download?version=3` |
| qmt | `https://osf.io/pzqyn/download?version=2` |
| mono_t2 | `https://osf.io/kujp3/download?version=3` |
| mtr | `https://osf.io/erm2s/download?version=2` |
| mtsat | `https://osf.io/c5wdb/download?version=4` |
| vfa_t1 | `https://osf.io/7wcvh/download?version=3` |
| b1_dam | `https://osf.io/mw3sq/download?version=3` |
| b1_afi | `https://osf.io/csjgx/download?version=9` |

`prepare-data` verifies both URL pin and checksum, unpacks into one canonical input
tree, adds the repo-owned masks, and uploads it as a single artifact that every fit job
downloads. A silent OSF re-upload fails the run loudly rather than quietly shifting
every number.

### 6.2 Masks are reproducible, not magic

`masks/<model>.nii.gz` is committed. So is `scripts/derive_masks.py`, which regenerates
those bytes from the pinned archives, and `masks/README.md`, which states the rule per
model.

- Archives shipping a `Mask` (ir, qmt, mono_t2, vfa_t1): that mask **is** the mask.
- Archives shipping none (b1_dam, b1_afi, mt_sat): the mask is the set of voxels
  **finite and strictly positive across every input volume** for that model. This is
  the rule qmrust's `compare_maps.py` already applies implicitly at comparison time;
  making it an explicit committed mask means it is applied identically to every target
  and is reviewable rather than incidental.

Every software and version is scored over this one region, so a difference in means
isolates the fit rather than the masking.

### 6.3 Model catalog

`models/<id>.yml` declares canonical identity, independent of any software:

```yaml
id: vfa_t1
dataset: vfa_t1
mask: masks/vfa_t1.nii.gz
maps:
  - {name: T1, unit: s}
  - {name: M0, unit: au}
```

`dataset` is a separate field because the two namespaces do not coincide: the model
`inversion_recovery` draws on dataset `ir`, `qmt_spgr` on `qmt`, `mt_ratio` on `mtr`,
and `mt_sat` on `mtsat`. The remaining four match by coincidence, not by rule.

## 7. Units: why hashing and statistics are computed differently

qmrust reports T2 in **seconds**, qMRLab in **milliseconds** — qmrust's
`ci/compare_maps.py` already carries `--scale 1000` for exactly this — and qMRLab's own
conventions may have shifted between versions.

Therefore:

- **Hashes are SHA-256 over the raw decompressed voxel bytes**, as the software
  produced them. Byte-equivalence then means "bit-identical output", uncontaminated by
  a conversion multiply the harness introduced. Hashing the *file* would be wrong
  regardless: NIfTI headers and `.mat` files carry timestamps and descriptions that
  differ every run.
- **Statistics are computed in the canonical unit** declared in `models/<id>.yml`, over
  the repo-owned mask, so they are comparable across softwares.

Consequence, to be stated on the site rather than hidden: hashes never match across a
unit difference. Those outputs genuinely are not the same bytes.

## 8. Results schema

Two records, written at two different stages. Keeping them separate is what keeps
§5.2's rule enforceable.

**Adapter record** — written by the target, one per (target, model). Facts only:

```json
{
  "target": "qmrlab@v2.4.1", "software": "qmrlab", "version": "v2.4.1",
  "model": "vfa_t1", "status": "ok",
  "environment": {
    "matlab_release": "R2021a", "runner_cpu": "AMD EPYC 7763",
    "runner_os": "ubuntu-24.04", "harness_commit": "<sha>",
    "run_started_utc": "2026-08-19T04:00:00Z"
  },
  "timing": {"repeats": 5, "fit_seconds": [12.1, 11.8, 12.0, 11.9, 12.2],
             "n_voxels_fitted": 12043},
  "maps": [{"name": "T1", "unit": "s", "path": "maps/vfa_t1/T1.nii.gz"}]
}
```

**Analysis record** — written by `analyze`, the adapter record enriched with every
derived number:

```json
{
  "...": "all adapter record fields, verbatim",
  "inputs": {"archive_sha256": "<sha256>", "mask_sha256": "<sha256>"},
  "maps": [
    {"name": "T1", "unit": "s", "path": "maps/vfa_t1/T1.nii.gz",
     "voxel_sha256": "<sha256>", "dtype": "float32", "shape": [128, 128, 1],
     "stats_unit": "s",
     "stats": {"n": 12043, "mean": 1.02, "std": 0.31, "median": 0.98,
               "p05": 0.61, "p95": 1.71, "n_nonfinite": 0, "n_zero": 3}}
  ]
}
```

`unit` is what the software produced; `stats_unit` is the canonical unit from
`models/<id>.yml` that `stats` are expressed in. When they differ, a conversion was
applied to the statistics and never to the hash (§7).

`status` is `ok` | `failed` | `not_applicable`.

**Raw per-repeat times are stored, never a pre-computed median.** Repeat counts are
declared per model (`repeats` in `target.yml`; default 5, `qmt_spgr` starts at 1
because its fit is slow), and the right values are not yet known — they will be tuned
after a calibration run. Storing raw times plus `n_voxels_fitted` means retuning
repeats, or switching the headline metric to time-per-voxel, requires no schema change.

## 9. Analysis, site, and drift

`analyze` is one Python package, stdlib-first — qmrust's `compare_maps.py` demonstrates
that reading NIfTI needs only `gzip` and `struct`. It is deliberately **lane-agnostic
and language-agnostic**: it reads maps and JSON records and knows nothing about MATLAB
or Rust. That is the seam a future software plugs into.

It computes every derived number: the voxel-data hashes, the masked statistics in
canonical units, and then, within each model, **all-pairs** comparisons across targets (cheap at
fewer than ten targets): hash equality, mean and median deltas, and voxelwise agreement
(fraction within tolerance, Pearson r) reusing `compare_maps.py`'s logic. The site
defaults to `qmrlab@v3.0.0` as the reference column; the underlying data is the full
matrix.

Four views, no framework:

- **Matrix** — targets × models; each cell shows status and hash-equivalence class, so
  "these five versions are bit-identical" is visible at a glance.
- **Per model** — one table per output map: masked statistics, equivalence class,
  delta vs. reference, voxelwise agreement.
- **Timing** — median and spread per target, plus time-per-voxel, with the MATLAB
  release on every row so the confound stays legible.
- **Provenance** — run timestamp, runner CPU, harness commit, every input checksum.

`site/data/results.json` is published beside the HTML so the data is reusable without
scraping.

### 9.1 Drift log

Results are recomputed in full every run and not committed. To keep environment drift
visible without a caching layer, `publish` carries forward `history.jsonl` from the
previous Pages deployment and appends **one line per run**: timestamp plus a
digest-of-digests per target. An immutable release should produce an identical digest
forever; if `qmrlab@v2.4.1`'s digest moves, the environment shifted, and the file
records which week.

## 10. Failure handling

**Failure is data.** A target that will not install records `status: failed` with its
captured log; the site renders a red cell and every other target still publishes.

Two failures are deliberately **not** per-target and abort the whole run, because both
mean every downstream number is untrustworthy:

- an input checksum mismatch (§6.1)
- a schema-invalid `target.yml` or `models/<id>.yml`

Per-job timeouts prevent a wedged MATLAB from burning six hours.

## 11. Testing

The harness is Python, shell, and one MATLAB driver. Correctness lives in the Python,
and TDD applies there:

- NIfTI voxel reading
- hash determinism
- masked statistics
- comparison math
- `target.yml` / `models/*.yml` schema validation
- Actions matrix generation

End-to-end tests run `analyze` over **committed synthetic fixtures** — tiny hand-built
maps with known statistics — so the whole pipeline is testable with no MATLAB and no
network.

A **smoke path** on every push runs one target × one model end-to-end. Without it a
harness bug sits undetected for six days between weekly runs.

## 12. Rejected approaches, kept as fallbacks

**Uniform containers, licensed via token.** Every target including MATLAB runs in a
container, seg_ci-style, using `mathworks/matlab:R20XX` images. One execution contract,
fully pinned images, and it reaches back to R2020b. Rejected because it depends on a
MATLAB Batch Licensing Pilot approval and puts a license secret in the repo — a
dependency on someone else's approval queue in exchange for one extra MATLAB release.
**This is the escape hatch if `qmrlab_ci` ever must be private, or must reach
pre-R2021a MATLAB.**

**Containers for non-MATLAB targets only.** The original proposal, a direct lift of
seg_ci. Rejected per §3.4: it solves a problem this repo does not have.

## 13. Deferred

- **Tag-only versions.** `v2.0.4`, `v2.0.14`, `v2.3.1`, `v2.4.2`, `v2.5.0b` and
  `ismrm2022` are tags without published releases. Each is one additional target
  directory if the extra resolution is wanted.
- **Mid-era MATLAB pins.** The era axis currently has only two real values (R2021a,
  R2026a). Adding intermediate pins (e.g. R2023b) would widen the MATLAB axis at
  roughly linear cost.
- **Timing methodology.** Repeat counts, and whether time-per-voxel is the right
  headline metric, are to be settled empirically after a calibration run. The schema
  accommodates either outcome without change.
- **Additional softwares.** The target contract and the language-agnostic `analyze`
  step are what make this additive.
- **Regression gating.** Not required now; nothing here precludes it.
