# qmrlab_ci

Fits the same eight qMRI models against the same fixed data using **every published
qMRLab release**, qMRLab `master`, and [qmrust](https://github.com/qMRLab/qmrust) — then
publishes each output map's statistics, byte-equivalence, and processing time.

> **Status: under construction.** The harness and its test suite are in place; the MATLAB
> drivers, data fetch, and workflows are still being built. Nothing is published yet.

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

**Models:** `qmt_spgr`, `inversion_recovery`, `vfa_t1`, `b1_dam`, `b1_afi`, `mono_t2`,
`mt_ratio`, `mt_sat`.

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
| `docs/superpowers/` | Design spec and implementation plan |

## Adding a target

Add a directory under `targets/`. The Actions matrix globs `targets/*/target.yml`, so a new
version of an existing software needs no workflow edit.

A target declares its `lane` — the toolchain it needs (`matlab`, `rust`, and reserved
`python`, `julia`, `r`). A new *language* does need a new job in the workflow, because each
ecosystem has its own setup and cache action.

## Three qMRLab API eras

The fifteen targets span three incompatible APIs, which is why drive logic lives per era:

| Era | Releases | Fit entry point |
|---|---|---|
| qMTLab | `V1` | `FitData(data, Prot, FitOpt, 'SPGR', 0)` |
| CamelCase | `v2.0.0`–`v2.0.5` | `FitData(data, Model, wait)` with `Model = SPGR()` |
| snake_case | `v2.1.0`–`master` | current object API |

`V1` contributes only `qmt_spgr`, and its shipped default protocol describes a *different*
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
