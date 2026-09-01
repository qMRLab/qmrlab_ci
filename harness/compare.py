"""Pairwise agreement between two maps of the same model, in the same unit.

Reports rather than asserts. qmrust's ci/compare_maps.py uses the same two criteria
to gate its build; here they are columns on a site, because this repo measures
history rather than policing a pull request.

`frac_within` and `pearson_r` are kept for continuity — every published record and every
history.jsonl digest was computed with them. `rel_median_diff` and `ccc` are added beside
them because neither of the originals can carry a red flag: `frac_within`'s tolerance band
collapses to exact equality wherever the reference voxel is 0 (spec §7.1), and a
correlation is blind to the calibration offset that a cross-software comparison is mostly
looking for.

A caller may also ask for `scatter`, a sparse 2-D histogram of the two maps against each
other. It is built HERE, from the arrays the statistics on the same row were computed
from, and never beside the caller: the picture and the number must describe the same
voxels, and where they disagree it is the picture the reader remembers.
"""
from __future__ import annotations

import dataclasses

import numpy as np

# Bins per axis in a pair's scatter histogram. ONE number, because the grid is square:
# both axes carry the same quantity in the same unit and share one range, so y = x is a
# true 45-degree line and only a square grid keeps it at 45 degrees. The cost is paid by
# results.json, which every visitor to the site fetches whole and which a scatter can add
# up to bins**2 cells to, so this is the first knob to turn if that file grows too large.
SCATTER_BINS = 48

# Where the shared axis range is cut, per side, in percent. NOT min/max: one diverged
# voxel would squash the entire cloud into a corner, the same leverage failure that put
# six spurious red flags on the published site. What falls outside is counted as
# `n_clipped` rather than silently dropped, so the picture can say how much of the
# selection it is not showing.
SCATTER_PERCENTILE = 0.5


@dataclasses.dataclass(frozen=True)
class _Selected:
    """The voxels one pair is compared over, after every filter this module applies.

    Computed once, by `_select`, and read by every consumer: the statistics below and the
    scatter histogram beside them are the SAME two arrays. A second implementation of the
    same filtering is the failure this type exists to prevent -- two of them drift, and
    the visible result is a scatterplot that contradicts the statistic printed under it.
    """

    x: np.ndarray
    y: np.ndarray
    scale_ratio: float | None
    n_out_of_range: int
    # False when this selection cannot produce a statistic at all: no voxel survived, or
    # a zero masked median left nothing to normalise by. `x` and `y` then hold whatever
    # the selection had reached and NOTHING may be computed from them -- in the
    # zero-median case they are the raw, un-normalised values, which is the one thing a
    # scale-free comparison must never publish or plot.
    measurable: bool


def _select(
    a: np.ndarray,
    b: np.ndarray,
    mask: np.ndarray,
    *,
    scale_free: bool,
    scale_free_range: tuple[float, float] | None,
) -> _Selected:
    """Mask, finite-in-both, normalise, bound — in that order, exactly once."""
    sel = np.asarray(mask).astype(bool) & np.isfinite(a) & np.isfinite(b)
    x, y = a[sel], b[sel]

    if x.size == 0:
        return _Selected(x, y, None, 0, False)
    if not scale_free:
        return _Selected(x, y, None, 0, True)

    # Spec §7: normalise each map by its own masked median, for maps whose unit is
    # 'au' and whose amplitude is therefore a free scale (vfa_t1/M0, mono_t2/M0).
    # Default off, and applied PER UNIT by the caller that knows the unit, NEVER
    # globally: b1_afi's B1map is a genuine ratio in which 1.0 means the nominal flip
    # angle was reached, so normalising a 10% offset away there would delete the
    # finding instead of measuring it.
    mx, my = float(np.median(x)), float(np.median(y))
    # Reported, never thresholded — hence the key name it ends up under. For a free scale
    # the recovered amplitude ratio is not a disagreement, and a column called
    # `scale_ratio` sitting beside `rel_median_diff` would be read as one.
    scale_ratio = mx / my if my != 0.0 else None
    if mx == 0.0 or my == 0.0:
        # Nothing to normalise by. Dividing anyway publishes nan or inf in a column
        # that everything downstream reads as a measurement.
        return _Selected(x, y, scale_ratio, 0, False)
    x, y = x / mx, y / my

    if scale_free_range is None:
        return _Selected(x, y, scale_ratio, 0, True)

    # AFTER the medians and the normalisation, BEFORE any statistic. Both halves
    # of that order matter. The medians must come from the whole masked selection
    # or the normalisation would depend on a range that depends on the
    # normalisation; and every statistic must come after, because r and CCC are
    # variance-based and a diverged voxel decides them for all the others -- two
    # voxels at 219x the median take mono_t2/M0 from r 0.877 to 0.333.
    #
    # Both sides must be inside, exactly as comparison_range requires: a voxel one
    # implementation fitted at 219x its own median amplitude is not comparable to
    # the other's 7x whichever side produced it. `scale_ratio` above is measured
    # before this and stays measured over the full selection -- it is the recovered
    # amplitude ratio, not a statistic the outliers are allowed to distort.
    lo, hi = scale_free_range
    keep = (x >= lo) & (x <= hi) & (y >= lo) & (y <= hi)
    x, y = x[keep], y[keep]
    return _Selected(x, y, scale_ratio, int((~keep).sum()), bool(x.size))


def _scatter(x: np.ndarray, y: np.ndarray, bins: int = SCATTER_BINS) -> dict | None:
    """A sparse square histogram of one pair, over the arrays it was measured on.

    Sparse -- only non-empty bins -- because a dense grid per pair would add megabytes to
    a file that already runs to 1.5 MB and is fetched by every visitor to the site.

    Both axes get ONE range, the union of the two maps' percentile cuts, so that the two
    quantities are drawn on the same scale and y = x is the identity line. That is the
    whole reason to draw this next to a concordance coefficient: the eye reads distance
    from the diagonal, and it can only do that if the diagonal means equality.
    """
    upper = 100.0 - SCATTER_PERCENTILE
    lo = float(min(np.percentile(x, SCATTER_PERCENTILE),
                   np.percentile(y, SCATTER_PERCENTILE)))
    hi = float(max(np.percentile(x, upper), np.percentile(y, upper)))
    # Spelled as `not lo < hi` so a NaN bound is refused too, config.py's `_range` rule.
    # A selection whose middle 99% is a single value has no picture to draw: numpy would
    # happily widen a zero-width range to [lo-0.5, lo+0.5] and bin against THAT, which
    # would publish an x_range the cells were not computed in -- a plot whose axis labels
    # are wrong, which is worse than no plot.
    if not lo < hi:
        return None

    counts, _, _ = np.histogram2d(x, y, bins=bins, range=((lo, hi), (lo, hi)))
    # np.nonzero walks row-major, so the cell list is ordered and a rerun over the same
    # maps produces byte-identical JSON -- which is what makes results.json diffable.
    ix, iy = np.nonzero(counts)
    n = int(counts.sum())
    return {
        "bins": bins,
        # Equal by construction today and separate keys anyway: the reader of the file
        # must not have to know that they are equal to draw the axes.
        "x_range": [lo, hi],
        "y_range": [lo, hi],
        "cells": [[int(i), int(j), int(counts[i, j])] for i, j in zip(ix, iy)],
        "n": n,
        # Counted, for masked_stats' n_nonfinite reason: voxels outside the percentile
        # cut are real comparisons the picture does not show, and an omission nobody can
        # see reads as a cloud with nothing outside it. `n + n_clipped` is the row's own
        # `n`, so a reader can check the picture against the statistic.
        "n_clipped": int(x.size) - n,
    }


def _unmeasurable(
    n: int,
    *,
    scale_free: bool,
    scale_ratio: float | None,
    n_out_of_range: int = 0,
) -> dict:
    """Every measure absent, with every key still present.

    analyze.py spreads this dict into a site row with **, so a branch that dropped keys
    would emit rows of two different shapes and move the failure into whichever renderer
    read the short one. None means "not measurable here", which is what the site already
    renders as "no comparable voxels" rather than as agreement.
    """
    return {
        "n": n,
        "frac_within": None,
        "pearson_r": None,
        "mean_delta": None,
        "median_delta": None,
        "max_abs_delta": None,
        "rel_median_diff": None,
        "ccc": None,
        "scale_free": scale_free,
        "scale_ratio_not_a_disagreement": scale_ratio,
        # Carried even here, and especially here: a range that excluded every voxel
        # produces exactly this dict, and without the count "no comparable voxels" would
        # read as a mask that never held any rather than as a range that emptied it.
        "n_out_of_range": n_out_of_range,
    }


def compare_maps(
    a: np.ndarray,
    b: np.ndarray,
    mask: np.ndarray,
    *,
    rel_tol: float = 0.01,
    scale_free: bool = False,
    scale_free_range: tuple[float, float] | None = None,
    scatter: bool = False,
) -> dict:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError(f"voxel count mismatch: {a.shape} vs {b.shape}")
    if scale_free_range is not None and not scale_free:
        # A caller bug, and one that would otherwise silently threshold PHYSICAL values
        # against bounds meant for median-normalised ones -- excluding voxels for how the
        # software scaled the map, which is the one thing normalisation exists to stop
        # being a finding. Bounds themselves are validated once, in config.py.
        raise ValueError(
            "scale_free_range is in units of each map's own masked median and has no "
            "meaning without scale_free=True"
        )

    selected = _select(
        a, b, mask, scale_free=scale_free, scale_free_range=scale_free_range
    )

    if not selected.measurable:
        row = _unmeasurable(
            int(selected.x.size),
            scale_free=scale_free,
            scale_ratio=selected.scale_ratio,
            n_out_of_range=selected.n_out_of_range,
        )
    else:
        x, y = selected.x, selected.y
        delta = x - y
        # Relative to the reference `b`, matching compare_maps.py. Where b is exactly
        # zero the tolerance band collapses, so only an exact match counts — correct,
        # since a relative tolerance around zero has no meaning.
        within = np.abs(delta) <= rel_tol * np.abs(y)

        if x.size > 1 and x.std() > 0 and y.std() > 0:
            pearson_r = float(np.corrcoef(x, y)[0, 1])
        else:
            pearson_r = None

        # The headline (spec §7). Directly interpretable — "QUIT reads 3% lower T1" — and
        # the median keeps it clear of the outliers that already force a skew warning on
        # the Values tab. It is MEANINGLESS for a map whose unit is 'au', where the
        # amplitude is a free scale and the ratio of two arbitrary scales is arbitrary;
        # that case is what scale_free=True exists for.
        median_abs_y = float(np.median(np.abs(y)))
        if median_abs_y > 0:
            rel_median_diff = float(np.median(delta) / median_abs_y)
        else:
            # A zero median |y| is `frac_within`'s trap one level up: a relative measure
            # has no meaning around zero. "Not measurable" is the honest answer, not a
            # division by it.
            rel_median_diff = None

        # Lin's concordance. CCC = pearson_r * C_b, so publishing it beside pearson_r
        # decomposes agreement into correlation and calibration: the diagnostic cell is
        # high r with low CCC, two softwares that rank voxels identically and calibrate
        # differently, which a correlation alone cannot show. Population moments (ddof=0)
        # to match how masked_stats already computes std — on sample moments this would no
        # longer be r * C_b of the r published next to it.
        xbar, ybar = float(x.mean()), float(y.mean())
        covariance = float(((x - xbar) * (y - ybar)).mean())
        ccc_denominator = float(x.var() + y.var() + (xbar - ybar) ** 2)
        # size > 1 for pearson_r's reason: one voxel has no variance to concord, and the
        # formula would still return a number (0, from the mean offset alone) if allowed
        # to.
        if x.size > 1 and ccc_denominator > 0:
            ccc = float(2.0 * covariance / ccc_denominator)
        else:
            ccc = None

        row = {
            "n": int(x.size),
            "frac_within": float(within.mean()),
            "pearson_r": pearson_r,
            "mean_delta": float(delta.mean()),
            "median_delta": float(np.median(delta)),
            "max_abs_delta": float(np.abs(delta).max()),
            "rel_median_diff": rel_median_diff,
            "ccc": ccc,
            # Carried on the row because every other number in it changes meaning when
            # this is true: they were computed on median-normalised maps. A row of
            # normalised numbers that does not say so is exactly the misreading spec §7.3
            # exists to prevent.
            "scale_free": scale_free,
            "scale_ratio_not_a_disagreement": selected.scale_ratio,
            # Reported for masked_stats' n_nonfinite reason: an exclusion nobody can see
            # is indistinguishable from a mask that never had those voxels. 0 whenever no
            # range was applied, so the key means the same thing on every row.
            "n_out_of_range": selected.n_out_of_range,
        }

    if scatter:
        # Attached in ONE place, after both branches, so the key can never be present on
        # a measured row and missing from an unmeasured one -- _unmeasurable's rule. None
        # rather than an omission for the same reason: a caller that asked for a picture
        # and got no key cannot tell that apart from a pair nobody asked about.
        row["scatter"] = _scatter(selected.x, selected.y) if selected.measurable else None
    return row
