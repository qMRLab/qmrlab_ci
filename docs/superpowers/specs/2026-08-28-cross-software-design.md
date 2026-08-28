# Cross-software qMRI comparison — design

Extends `qmrlab_ci` from a cross-*version* benchmark of one software family into a
cross-*software* one. Adds QUIT and SCT as targets, runs them on the same bytes, scores
them with the same code, and publishes where they disagree — flagging substantial
disagreement in red only where a red flag would mean something.

Companion to [the original design](2026-08-19-qmrlab-ci-design.md), whose §13 listed
"Additional softwares" as deferred and additive. This spec is the cash-in of that claim,
and it tests it: most of what follows is new declaration, not new machinery.

## 1. Purpose

**Does independent software, given the same data and the closest settings each permits,
produce the same quantitative maps?** Where it does not, is that an implementation
difference or a modelling difference?

That second question is the whole design problem. A benchmark that reports "QUIT's `kr`
is 32% higher than qMRLab's" without saying *why* is worse than no benchmark, because
the number is real and the implication is false. Every mechanism below exists to keep
those two cases apart.

The repo's existing posture holds: it reports, it does not assert, and it is not a
pull-request gate.

## 2. Scope

### 2.1 New targets

| Target | Lane | Pin | Models |
|---|---|---|---|
| `quit@v3.4` | `native` | tag `v3.4` = `28d6a8e2`, installed from `qi-linux.tar.gz` | `vfa_t1`, `mono_t2`, `b1_afi`, `mt_ratio`, `mt_sat`, `qmt_spgr_ramani` |
| `sct@7.3` | `native` | tag `7.3` (2026-05-09) | `mt_ratio`, `mt_sat` |

### 2.2 New model: `qmt_spgr_ramani`

A second qMT stream. `qmt_spgr` (SledPikeRP) is untouched and QUIT is simply absent from
it. `qmt_spgr_ramani` is run by all 14 qMRLab targets, qmrust, and QUIT.

It shares `qmt_spgr`'s dataset (`qmt`), mask and map set (`F`, `kr`, `R1f`, `R1r`, `T2f`,
`T2r`, same units) — only the fitted sub-model differs. `models/qmt_spgr_ramani.yml` is
therefore `qmt_spgr.yml` with a different `id` and the same `dataset`/`mask`.

This exists because QUIT's `qi qmt` implements *only* Ramani, while every current target
fits SledPikeRP. Without a Ramani stream there is no three-way qMT comparison at all;
with one, there is a good one. See §6.3 for what it costs.

Selecting it is cheap on our side: `Model.options.Model = 'Ramani'` in eras 2 and 3,
`FitOpt.model = 'Ramani'` (lowercase) in era 1 — verified selectable at all 14 qMRLab
refs — and on the qmrust side a swap to `qmt_config_ramani.yaml`, which already exists and
is byte-identical to the SledPikeRP recipe but for one token. Ramani is in fact qmrust's
own default. Per-version `st`/`lb`/`ub`/`fx` defaults are left alone: that drift is what
the benchmark measures.

### 2.3 New dataset: `sct_mt`

`mt0.nii.gz` / `mt1.nii.gz` / `t1w.nii.gz`, 192×192×22, from `sct_example_data`. Feeds
`mt_ratio` and `mt_sat`. Pinned by release-asset URL and SHA-256, **not** by
`sct_download_data`: that dataset key exists in `DATASET_DICT` at tag 7.3 but has been
deleted on SCT master, so the command is a moving target in the worst direction.

```
https://github.com/spinalcordtoolbox/sct_example_data/releases/download/r20180525/20180525_sct_example_data.zip
44,331,290 bytes
sha256 dd21fb0c92feae5650ac2aa05977aae1f87ce941e806426690568bafd43f92e6
```

Protocol (TR 30/30/15 ms, FA 9/9/15°) is published in SCT's own `batch_processing.sh` at
tag 7.3 — which is 404 on master, so the values are transcribed into `protocols/` rather
than referenced.

Two caveats recorded with the entry: the dataset is being retired upstream, and the repo
carries **no license file**. We fetch rather than vendor, which is the same posture as
the OSF archives.

`sct_testing_data` is rejected: its `t1w` is exactly `mt0 / 1.5`, so MTsat derived from it
is an algebraic transform of a single image, not a measurement.

### 2.4 Coverage, and holes

| Model | qMRLab | qmrust | QUIT | SCT |
|---|---|---|---|---|
| `vfa_t1` | ✓ | ✓ | `qi despot1` | — |
| `mono_t2` | ✓ | ✓ | `qi multiecho` | — |
| `b1_afi` | ✓ | ✓ | `qi afi` | — |
| `mt_ratio` | ✓ | ✓ | `qi mtr` | `sct_compute_mtr` |
| `mt_sat` | ✓ | ✓ | `qi mtsat` (partial) | `sct_compute_mtsat` |
| `qmt_spgr_ramani` | ✓ | ✓ | `qi qmt` | — |
| `qmt_spgr` | ✓ | ✓ | — | — |
| `b1_dam` | ✓ | ✓ | — | — |
| `inversion_recovery` | ✓ | ✓ | — | — |

**Holes are declared by omission from `target.yml`, and that stays the only mechanism.**
An explicit `not_applicable` *record* would stop `analyze` synthesizing a `missing` marker
for that slot, making a killed job indistinguishable from a declared hole — the exact
confusion the `missing` synthesis was written to prevent. With SCT covering 2 of 9 models
this matters more than it did.

Three holes are worth naming because they look like they should not be:

- **`b1_dam` / QUIT** — QUIT has no double-angle command. Its B1 module is `afi`, `dream`,
  `b1_papp`. `qi dream` is a different sequence, not DAM.
- **`inversion_recovery` / QUIT** — `qi irtse` implements Padormo 2023 IR-TSE: it needs
  ETL, ESP, TD1, per-TI TR, inversion-efficiency arrays, a navigator flip angle, and
  **signed** data that crosses zero. Our archive is magnitude with 9 TIs. Different model,
  different required metadata.
- **`qmt_spgr` (SledPikeRP) / QUIT** — covered by `qmt_spgr_ramani` instead.

### 2.5 Deferred

- **hMRI v1.0.0** — increment 2. Covers `b1_dam`, `b1_afi`, partial `mt_sat`/`vfa_t1`;
  more overlap than SCT. Needs a new `spm` lane and a driver. Pin
  `0ff28278f03ff931e0af72d4632272d1c3f22391` **by SHA**: `v1.0.0` is a lightweight tag,
  and master's `version.txt` still reads `v1.0.0`, so a master build self-reports as the
  release. Prefer the SPM-free entry points (`hmri_calc_R1`, `hmri_calc_A`,
  `hmri_calc_MTsat` — arrays in, arrays out) over `spm_jobman`; at stock defaults a
  3-image job runs Unified Segmentation against a 73 MB TPM and would dominate every
  timing number.
- **Synthetic phantoms** — increment 3. Both generators already exist: qmrust has forward
  models for all 8 models (`qmrust sim signal`), and every QUIT fitting command has a
  `--simulate=<noise_sigma>` forward mode with `qi newimage` for ground-truth ramps.
  Two independent generators is itself worth having.

## 3. Version pinning, and one rule that bent

The rule was "latest release, or master where master is healthy." It survived contact
with SCT and hMRI and broke on QUIT.

**SCT → tag `7.3`.** Releases often, LGPL-3.0, no license server. Pin 7.3, **not 7.2** —
7.2 shows a *later* publish date but is a yanked prerelease.

**hMRI → tag `v1.0.0`, by SHA.** No CI of any kind: no `.github/` directory, and
`hmri_code_tests/` is run by hand. Master is 3 commits ahead and numerically identical
today, but two live PRs (#140 rewrites error-map math in `hmri_calc_dMT/dPD/dR1`; #114
rewrites `hmri_calc_R2s.m`) would move numbers silently on merge, with no CI to signal it.

**QUIT → tag `v3.4`, not master.** The intent was to track master and document the commit.
Master does not support it:

- CI has been red since 2025-03-17. Commit `cba3d0d3` replaced the `cmake` git submodule
  with a plain directory; `build.yml` still points at `cmake/toolchain.cmake` and every
  run since dies in 21 seconds at `Could not find toolchain file`. Zero green runs in the
  retained window. The macOS leg sits queued 24 hours and is cancelled — `macos-12` no
  longer exists.
- **There is no master binary and no way to obtain one.** No `upload-artifact` step
  anywhere in the workflow; the only publishing path is gated on `tags/v` and creates a
  *draft* release. Repo-wide artifact count is 1, an expired Copilot blob.
- So pinning master means a cold vcpkg source build (ITK 5.4.4 + Ceres + VXL + GDCM,
  realistically 45–90 min on a 4-vCPU runner) **with no evidence master compiles**, since
  nothing has built in 17 months. Six code commits have landed in that window, including
  changes to `ModelFitFilter.h` and `FitScaledAuto.h` — core fitting code, unvalidated by
  upstream's own test suite.

Consequences to state on the site rather than bury: we benchmark a 2023-11-29 build, and
v3.4's `qi mtsat` uses the small-flip-angle approximation, which is right for qMRLab
comparability but is **not** what current QUIT master does. Any claim is scoped to
"QUIT v3.4", never "QUIT".

Release assets are mutable (`ncipollo/release-action` runs with `allowUpdates: true`), so
the tarball is checksum-asserted at install. The binary needs glibc ≥ 2.34 and is x86-64
only: pin the runner, and never an arm64 image.

## 4. Architecture

The seam the original design created is the one being used. `analyze.py` reads records and
maps and knows nothing about MATLAB or Rust; a new software needs no change there. What
changes is declaration, plus six contract extensions that the new tools genuinely require.

```
prepare-data ──┬─> plan ──┬──> fit-matlab (matrix)  ──┐
  (+ NIfTI     │          ├──> fit-rust   (matrix)  ──┤
   conversion) │          └──> fit-native (matrix)  ──┴──> analyze ──> publish
```

### 4.1 One new lane, not two

`native` — **the target's `setup.sh` provisions its own toolchain; the workflow supplies
only checkout, Python, the data artifact, and an optional cache.**

QUIT's setup is `curl | tar` + checksum (~2 s). SCT's is `install_sct -iyc` (124 s
measured on GitHub-hosted runners in SCT's own nightly; ~30 s with `$HOME/sct` cached).
The job body is otherwise identical, so it is one job.

This amends, rather than contradicts, `config.py`'s existing rationale. That comment says
a lane names the toolchain, because a Rust target wants `rust-toolchain` + `rust-cache`
and a Python one wants `setup-python`. `native` names the *absence* of a shared toolchain
step, which is a real and legible category — and it keeps a job full of `if:` guards from
appearing, which was the original reason to split by lane at all.

`fit-native` **must** be added to `analyze.needs`. Omitting it is the quietest possible way
to turn the whole lane into `missing` cells: `analyze` downloads with `pattern: results-*`
and would simply not find them.

## 5. Contract changes

Six. Each is required by a specific new tool; none is speculative.

### 5.1 Non-finite `scl_slope` (bug fix)

`harness/nifti.py` guards only `scl_slope == 0.0`. ITK — and therefore every file QUIT
writes — uses **NaN** for "no scaling". NaN fails that guard, so `values` computes
`NaN * out + NaN` and every voxel becomes NaN. **Nothing raises.** The record validates as
`ok`, `masked_stats` returns `n=0` with `None` for every statistic, and the map joins a
shared equivalence bucket. Reproduced in session:

```
itk_nan   slope=nan inter=nan   values=[nan nan nan nan]
          stats n=0 mean=None n_nonfinite=4    <-- record validates as 'ok'
```

The `missing`-record machinery cannot catch this, because the record exists.

```python
if not np.isfinite(self.scl_slope) or self.scl_slope == 0.0:
    return out
```

Matches nibabel. Verified safe: 0 of 63 NIfTI files in the repo (all committed maps, all
masks, all OSF inputs) have a non-finite slope, so no existing hash or statistic moves.

### 5.2 `MapSpec.transform: reciprocal`

QUIT emits `MTSat_R1` and hMRI emits `_R1`, both in `s^-1`, where `models/mt_sat.yml` and
`models/vfa_t1.yml` declare `T1` in `s`. `units.py::scale_between` raises on that pair, and
must: a reciprocal is not a scale factor, and the table is deliberately linear-only.

But `analyze` wraps each record in a broad `except Exception` and degrades it to one red
cell reading `analysis failed: ValueError` — so a schema gap presents as a fit failure.

Three options were considered. Inverting in the adapter breaks the stated invariant that
every derived number is computed once in Python. Declaring an extra `R1` map on the model
creates a per-map hole the schema cannot express, since omission is only declarable at
model granularity. So: extend `MapSpec` with an optional `transform`, applied once in
`analyze.py` beside `scale_between`. Only `reciprocal` is defined; an unknown transform
raises, like an unknown unit.

### 5.3 B1 canonical unit: `au` → `fraction`

`models/b1_dam.yml` and `models/b1_afi.yml` declare `B1map` with unit `au`, which converts
to nothing but itself. hMRI writes percent-of-nominal (100 = nominal flip achieved).
Declaring `au` there would publish a 100× error as a fit difference — the exact signature
`matlab/qmrlab_ci_unit_for.m` already records for MTsat across eras.

**Order is load-bearing.** Add `('au','fraction') = 1.0` and its inverse to `_FACTORS`
first, with a comment stating that a B1 map in `au` is a ratio where 1.0 = nominal. *Then*
change the model files. Reversed, all 15 existing targets fail both B1 models at once,
because their records declare `au`.

Not strictly needed until hMRI, but it also makes those maps eligible for a real relative
difference instead of the scale-invariant fallback (§7), so it lands now.

### 5.4 A dataset axis

Records gain `dataset`, defaulting to the model's canonical dataset. `models/*.yml` keeps
its `dataset:` as that default; a new `datasets/` catalog declares source, checksum, mask,
and protocol per dataset. Comparisons key on `(model, dataset, map)`.

**With one dataset per model the site renders exactly as it does today** — the axis
collapses when it has one value. It exists because `sct_mt` is real, and it is where
synthetic phantoms will land in increment 3.

### 5.5 `comparability.yml`

Per `(model, map, software-pair)`, one of:

- **`same-estimator`** — same model equation, settings aligned. Red is assignable.
- **`related-estimator`** — genuinely different estimator or a settings difference that
  cannot be closed. Amber, with the cause rendered as **visible text**, following the
  precedent of the "What did not run" list rather than hiding it in a tooltip.
- **`incomparable`** — do not run the pair at all.

You cannot fix a model-equation difference with a statistic; you can only declare it. This
repo already declares capability holes by omission, so declaring comparability is the same
move one level finer.

### 5.6 Reference orientation in `compare_maps`

`analyze` builds pairs with `itertools.combinations(sorted(by_target))`, so `b` is just the
alphabetically later id. `quit@` and `sct@` sort after every `qmrlab@` and `qmrust@` id —
and `compare_maps` computes `within = |x−y| <= rel_tol * |y|` against `b`. Cross-software
pairs would silently use the *external* tool as the tolerance denominator, an invisible,
name-driven asymmetry in a metric that is not symmetric.

Cross-software pairs get an explicit reference. `hmri@` would sort *before* `qmrlab@`,
flipping the asymmetry the other way, so this is fixed now rather than when it bites.

## 6. Holding settings the same, and admitting where we cannot

### 6.1 `protocols/<dataset>.yml`

Acquisition parameters currently live inside qMRLab's `.mat` archives and, separately, in
qmrust's recipe YAML. A third and fourth consumer makes that untenable: "the same
settings" needs one source of truth from which each adapter renders its own config.

`protocols/` holds it. Each adapter generates its config at run time; the values are
asserted against the archive where the archive carries them.

### 6.2 `scripts/mat_to_nifti.py`

Three archives are `.mat`-only (`ir`, `qmt`, `mtr`), and `mt_ratio` — the single
best-matched comparison SCT offers — needs NIfTI for both new tools.

The only converter today is `qmrust bidsify --mat-dir`, called from qmrust's `run.sh`.
Reusing it would make a QUIT or SCT job depend on a cargo build of an unrelated target,
and make SCT's inputs a function of a qmrust commit. So: a harness-owned converter, run
once in `prepare-data`, emitting a shared canonical-NIfTI artifact that every non-MATLAB
lane consumes — the same principle as the shared `canonical-inputs` artifact and the
harness-owned `qmrlab_ci_write_nii.m`.

Costs promoting scipy from a dev extra to a main dependency. Accepted: byte-identical
converted inputs across lanes is worth a wheel download.

### 6.3 Where "same settings" is impossible

Recorded here because each becomes a `related-estimator` entry with this text attached.

**`qmt_spgr_ramani`, qMRLab/qmrust vs QUIT.** The parameter mapping is exact and was
verified numerically against the real `qi` binary (recovered `f_b=0.13043`, `k=24.99996`,
`T2_f=0.0279997` against truth `F=0.15, kr=25, T2f=0.028`):

| qMRLab | QUIT | transform |
|---|---|---|
| `F` | `QMT_f_b` | `F = f_b/(1−f_b)` |
| `kr` | `QMT_k` | none |
| `R1f` | `QMT_T1_f` | `R1f = 1/T1_f` |
| `T2f` | `QMT_T2_f` | none |
| `T2r` | `QMT_T2_b` | none |
| `R1r` | `--R1b` scalar | fixed input; **defaults differ, 2.5 vs 1.0** |

Six things must be held on the QUIT side or the comparison is meaningless: `--R1b=1.0`;
`--lineshape=Superlorentzian` (lowercase `l` — qMRLab's `SuperLorentzian` spelling is
silently treated as a filename); `--T1` as a map of `1/R1map` in seconds, pre-floored at
`R1obs ≥ 0.1` to match `SPGR_fit.m`; `--B1` as the same ratio map; **omit `--f0`** and zero
qMRLab's B0 map; and pulse `p1=0.348364675, p2=0.249536344` for gausshann at Trf=0.0102 s,
**not** QUIT's documented Gaussian `p1=0.416, p2=0.295`.

Three differences remain irreducible and are reported, not papered over:

1. **The lineshape.** qMRLab and qmrust apply a near-resonance extrapolation to the
   super-Lorentzian for |Δ| ≤ 1500 Hz; QUIT computes the raw integral. This protocol's two
   lowest offsets are 443 and 1088 Hz, so **4 of 10 volumes are affected**. Measured on
   noise-free data: `kr` **+31.8%**, `T2f` **+34.9%**, `F` −6.7%. It cannot be closed with
   `--lineshape=<json>`: QUIT's interpolated lineshape indexes by `|f|·(T2/T2_nom)`, which
   presupposes a scaling law qMRLab's extrapolation breaks.
2. **Start point and bounds** are compile-time literals in `qi_qmt.cpp` with no CLI flag.
3. **An extra degree of freedom** — QUIT always fits `M0_f` (5 varying vs qMRLab's 4), and
   it cannot be disabled.

Also declare, on the qMRLab side, that `V1` alone ignores the B1 map for Ramani and alone
lacks the `max(0.1, R1obs)` floor: expect its `F` map to sit apart for a reason that is not
version drift.

**`mono_t2`, qMRLab/qmrust vs QUIT.** `qi multiecho --algo=n` (NLLS) pins T2 at its bound
on scanner-scaled data, and our `SEdata` has max 4095 — so log-linear is the only viable
QUIT algorithm, while qMRLab and qmrust fit nonlinear exponential. A genuine estimator
mismatch baked into the only configuration that runs.

**`mt_sat`, T1 map.** SCT's T1 is the Helms two-point rational approximation embedded in
MTsat, not a VFA fit. Same name, different estimator.

**`vfa_t1`, qMRLab vs QUIT.** Use `--algo=l`; qMRLab and qmrust default to the closed-form
Fram linearization. QUIT's docs favour `n`.

## 7. What "substantial disagreement" means

Red is **only ever assignable inside `same-estimator`**.

- **Headline** — relative median difference `rmd = median(x−y) / median(|y|)` over the
  mask-and-both-finite selection, `y` = declared reference. Red at |rmd| > 10%, amber > 5%.
  Robust to the outliers that already force a skew warning on the Values tab, and directly
  interpretable: *"QUIT reads 3% lower T1."*
- **Second column** — Lin's CCC beside the existing `pearson_r`. Red at CCC < 0.90, amber
  < 0.95. `CCC = r · C_b`, so publishing both makes the decomposition visible; the
  diagnostic cell is **high r, low CCC** — ranks voxels identically, calibrates differently.
- **Scale-free maps** (`au`: `vfa_t1/M0`, `mono_t2/M0`) — normalise each by its own masked
  median, then apply the above, and report the recovered scale ratio as a separate column
  explicitly labelled *not a disagreement*. Applied per unit, never globally: `b1_afi`'s B1
  is a genuine ratio where 1.0 means nominal, and normalising away a 10% offset there would
  be wrong.
- Thresholds are declared per model in `models/*.yml`, not buried in Python.

### 7.1 Two things red must never be built on

**Equivalence hashes.** `voxel_sha256` is computed on the produced unit and never scaled,
and QUIT writes float32 where qMRLab writes float64 — a cross-software hash match is
impossible even for bit-identical mathematics. "Unique" will mean nothing across families,
and the Agreement tab must say so.

**`frac_within`.** Its tolerance band collapses to exact equality wherever the reference
voxel is 0, and `masks/b1_afi.nii.gz` has 103,484 zero voxels of 300,140 (34%). On that map
`frac_within` measures exact-zero agreement, not the 1% tolerance.

### 7.2 Comparison masks

`masks/mt_sat.nii.gz` retains 95.2% of voxels (1,497,725 / 1,572,864). It is a
finite-and-positive derivation, and since MTw/PDw/T1w are int16 scanner images, background
noise is > 0 and survives. That near-background region is exactly where the softwares
disagree by construction: SCT clips `R1 < 0.01` → T1 = 0; qMRLab leaves `R1 = 0` → T1 = Inf;
hMRI clips R1 to [0,2]. Any headline `mt_sat`/T1 number computed there measures three
background conventions, not three fits.

`derive_masks.py` gains an **Otsu** threshold, producing a second mask per derived model:

```
models/mt_sat.yml
  mask:            masks/mt_sat.nii.gz            # stats + hashes, UNCHANGED
  comparison_mask: masks/mt_sat_interior.nii.gz   # red-flag statistic only
```

Otsu on PDw gives threshold 201.8 and retains 14.9%, and the result is spatially coherent —
0% at the end slices, 20–24% through the middle. Parameter-free, deterministic, ~12 lines
of numpy, so `derive_masks.py`'s own standard survives: *"a reviewer can rerun this and get
the committed bytes back."*

BET was considered and rejected: it needs FSL installed, its output shifts with FSL version
and the `-f` parameter, and it cannot be the general rule — `qmt_spgr` is a single 88×128
slice, and brain extraction on a 2D slice is not a thing. One derivation rule beats two.

Applied to the derived masks (`mt_sat`, `b1_afi`). Shipped masks are the archives' own and
are already anatomical. `b1_dam` stays full, for the reason `masks/README.md` already gives.

Keeping the stats mask means no published number and no `history.jsonl` digest moves. The
site carries both, and says which is which.

## 8. Site

A **Cross-software** tab showing latest-of-each-software; the existing five tabs filter to
`qmrlab` + `qmrust` so the version-history story stays readable. Every record already
carries `software` and `version` as required non-empty fields that `site.py` never reads,
so the facet data is present.

One pre-existing bug to fix while there: `_ordered` appends unknown targets alphabetically
at the tail, `_short` is two hardcoded string replaces, and the label gutters are fixed
pixel constants (`pad=108` in `_matrices`, 116 in `_ranges`, 210 in `_timing`) drawn
`text-anchor="end"` at `pad-6`. A longer label renders at **negative x and is silently
clipped** by the SVG viewport. `tests/test_site.py` uses `a@1`/`b@1` fixtures matching
neither `TARGET_ORDER` nor either `_short` branch, so ordering and labelling — precisely
what a third software family breaks — have no coverage today.

## 9. Traps, encoded as assertions

Each of these is a silent wrong answer, not an error:

- **`qi mtr` with no JSON returns `100 − MTR`.** Traced to `qi_mtr.cpp:87`, where a trailing
  `true` initialises `scale` rather than `reverse`; present in v3.4 **and** master. An
  explicit contrasts JSON is mandatory.
- **SCT `-thr` defaults to 100** and clips MTR to ±100; the clip fires on real data.
  qMRLab does not clip. Pass a large threshold and rely on the repo mask.
- **`qi afi --flip` defaults to 55**, ours is 60 — omitting it scales the map by 60/55.
- **SCT `-mt0` is the MT-*off* image**, `-mt1` MT-on (0/1 = number of saturation pulses).
- **SCT unit inconsistency**: `sct_compute_mtsat -trmt/-trpd/-trt1` are **seconds**;
  `sct_compute_ernst_angle -tr` is **milliseconds**.
- `QUIT_EXT=NIFTI_GZ` in the job env, or every invocation warns.
- SCT writes NaN where MToff == 0; qMRLab writes 0.
- Pin thread counts (`-T 1` / `$QUIT_THREADS`) so timings are not a function of runner core
  count.

## 10. Testing

Existing suite plus:

- `nifti.py` non-finite slope, beside `tests/test_analyze.py`.
- `transform: reciprocal`, including that an unknown transform raises.
- Unit-table migration: `au` ↔ `fraction` both directions.
- Comparability classes: that `related-estimator` cannot produce red, and that
  `incomparable` produces no pair at all.
- Site ordering and labelling with a third software family present — the coverage gap §8
  names.
- `matrix.py` lane shape assertions, which currently assert `set(m) == set(KNOWN_LANES)`
  and will break on `native`.

## 11. Verification before commitment

**Nothing in the QUIT or SCT research was run against these archives.** It comes from
source reading plus synthetic checks: SCT's `compute_mtsat` was reproduced against SCT's
own test data, and QUIT's numbers came from small synthetic volumes. The TR field QUIT's
`MultiEcho` parser wants is not in the `mono_t2` archive at all.

Budget a spike per tool to run it once against the real archive before committing a
`target.yml`. The repo's precedent is strong: the era-3 loader's map-field candidates and
the MTsat unit table were both settled by running against the real archives, not by reading
source.

## 12. Delivery

Pushed incrementally. Each step goes to GitHub as it is made and runs in CI, including
steps expected to fail — a visible trail of partial progress is worth more here than a
single green push at the end. Commit messages say which parts are expected to fail and why.

Note that pushes touching `targets/` or `harness/` start a real MATLAB matrix.

## 13. Rejected

**One flat 19×19 matrix.** External targets as ordinary targets everywhere. Zero new site
code, but most pairs (`qmrlab@v2.0.1` vs SCT) are noise and "substantial disagreement" has
no natural reference.

**A separate cross-software site section.** Cleanest conceptual split, but duplicates the
analysis plumbing and puts "qmrust vs qMRLab" in two places.

**Inverting R1→T1 in the adapter.** Simpler than `transform: reciprocal`, but breaks the
invariant that every derived number is computed once in Python — which is the reason the
harness owns hashing, statistics, unit conversion and comparison at all.

**Tracking QUIT master.** See §3. Kept as a fallback: if upstream fixes `build.yml`, a
master pin becomes a source build away rather than an unknown.
