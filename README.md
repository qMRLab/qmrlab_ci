# qmrlab_ci

Fits the same eight qMRI models against the same fixed data using **every published
qMRLab release**, qMRLab `master`, and [qmrust](https://github.com/qMRLab/qmrust) — then
publishes each output map's statistics, byte-equivalence, and processing time.

> **Status: live.** The benchmark runs weekly (and on demand) and publishes to
> **[qmrlab.org/qmrlab_ci](https://qmrlab.org/qmrlab_ci/)**. The full machine-readable
> output backing that page is at
> [`data/results.json`](https://qmrlab.org/qmrlab_ci/data/results.json), and a
> run-over-run digest log at
> [`data/history.jsonl`](https://qmrlab.org/qmrlab_ci/data/history.jsonl).

## What it answers

**How have qMRLab's outputs and runtimes changed across its history?** Fifteen targets
spanning 2016 to today, all fitting byte-identical input data, so a difference between two
of them is a difference between the softwares rather than between two downloads.

**Does a reimplementation reproduce qMRLab's numbers?** qmrust sits in the same matrix as
every qMRLab release, scored the same way.

It is deliberately **not** a pull-request gate. It reports numbers; it does not assert
them. Runs weekly and on demand.

Modelled on [`axondeepseg/seg_ci`](https://github.com/axondeepseg/seg_ci), which does the
same for AxonDeepSeg.

## What gets compared

**Models:** `qmt_spgr`, `qmt_spgr_ramani`, `inversion_recovery`, `vfa_t1`, `b1_dam`,
`b1_afi`, `mono_t2`, `mt_ratio`, `mt_sat`.

`qmt_spgr` and `qmt_spgr_ramani` are the same acquisition fitted with two different qMT
sub-models. The second exists because QUIT implements only Ramani, so without it there is
no cross-software qMT comparison at all.

**Targets:** qMRLab `V1`, `v2.0.0`–`v2.0.5`, `v2.1.0`–`v3.0.0`, `master`, plus
`qmrust@main`. Not every model exists in every release — `mt_ratio` arrives in v2.3.0,
`mono_t2` in v2.4.0, `b1_afi` in v2.5.0 — so those combinations render as declared holes,
never as failures.

**Per output map:** masked statistics in the model's canonical unit, a hash of the fitted
values, and pairwise agreement against every other target. **Per fit:** wall-clock time
with the MATLAB release recorded beside it.

## Three things that are easy to get wrong

**MATLAB licensing dictates the architecture.** MATLAB is auto-licensed only through the
`matlab-actions/*` actions, on GitHub-hosted runners, for **public** repositories.
`setup-matlab` installs MATLAB but does *not* license it — licensing happens inside the
`matlab-batch` wrapper that `run-command` invokes. Calling the `matlab` binary directly, or
running MATLAB inside a container, bypasses that and fails with `Unable to find a license
for MATLAB`. **This repository must stay public**, and MATLAB is never invoked any other
way. `setup-matlab@v2` reaches back to R2021a, which is the floor for every pre-2.5.0
target.

**Every target fits the same bytes.** Each qMRLab version carries its own
`onlineData_url`, so letting versions fetch their own demo data would vary the input and
the output at the same time. Data is fetched once, centrally, verified against a committed
SHA-256, and shared. A silent re-upload fails the run rather than quietly moving every
number.

**Hashes cover canonicalized values, not file bytes.** NIfTI headers carry timestamps, and
implementations disagree about storage dtype and `scl_slope`. Hashing raw bytes would
compare serializers rather than fits. See `harness/measure.py`.

## Layout

| Path | What it is |
|---|---|
| `targets/<software>@<version>/` | One directory per target. `target.yml` declares it; `setup.sh` holds its install fixes |
| `models/*.yml` | Canonical model catalog: which maps, in which units |
| `masks/` | Repo-owned masks, one per model, regenerable via `scripts/derive_masks.py` |
| `data/sources.yml` | OSF archives pinned by version **and** SHA-256 |
| `harness/` | Every derived number: hashes, statistics, comparisons, site, drift log |
| `matlab/` | Three era drivers plus a harness-owned NIfTI writer |
| `.github/workflows/smoke.yml` | Push/PR gate: harness tests plus one MATLAB target per era |
| `docs/superpowers/` | Design spec and implementation plan |

## Adding a target

Add a directory under `targets/`. The Actions matrix globs `targets/*/target.yml`, so a new
version of an existing software needs no workflow edit.

A target declares its `lane` — the toolchain it needs (`matlab`, `rust`, and reserved
`python`, `julia`, `r`). A new *language* does need a new job in the workflow, because each
ecosystem has its own setup and cache action.

## Continuous integration

The full benchmark runs weekly. Without a faster check, a harness bug introduced on
Monday is invisible until the following Tuesday. `.github/workflows/smoke.yml` runs on
every push and pull request instead: the Python test suite, then one MATLAB target per
era — `qmrlab@V1` (era 1), `qmrlab@v2.0.5` (era 2), both pinned to **R2021a**, and
`qmrlab@v3.0.0` (era 3) on R2026a. R2021a is the floor `setup-matlab@v2` supports and
governs 11 of the 14 MATLAB targets, so smoke is what actually exercises that pin rather
than assuming it works.

Each leg fits one model, validates the resulting record against the schema, and — for
`b1_dam`, which is closed-form — asserts near-exact agreement with the archive's own
`FitResults`. `qmt_spgr` on `V1` is asserted only for a valid, complete record: `V1`'s
model equation genuinely differs from later eras' (v3.0.0 multiplies free-pool
saturation by `cos(alpha)`; `V1` does not), so comparing it against the shared archive
reference would misreport a real modeling difference as a bug. A final job runs
`harness.analyze` and `harness.site` over the three legs' real adapter output, so the
analysis stage is exercised on every push too, not only during the weekly run.

## Three qMRLab API eras

The fifteen targets span three incompatible APIs, which is why drive logic lives per era:

| Era | Releases | Fit entry point |
|---|---|---|
| qMTLab | `V1` | `FitData(data, Prot, FitOpt, 'SPGR', 0)` |
| CamelCase | `v2.0.0`–`v2.0.5` | `FitData(data, Model, wait)` with `Model = SPGR()` |
| snake_case | `v2.1.0`–`master` | current object API |

`V1` contributes only qMT — both sub-model streams of it — and its shipped default
protocol describes a *different*
acquisition than the canonical dataset, so its protocol is reconstructed to match. That
reconstruction is the least certain thing in the repo — see the spec.

## Running locally

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
python -m scripts.fetch_data --out osf-data     # downloads and verifies the 8 archives
```

## Design documents

- [Design spec](docs/superpowers/specs/2026-08-19-qmrlab-ci-design.md) — what is built and why
- [Implementation plan](docs/superpowers/plans/2026-08-19-qmrlab-ci.md) — how, task by task
