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
"""
from __future__ import annotations

import numpy as np


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

    sel = np.asarray(mask).astype(bool) & np.isfinite(a) & np.isfinite(b)
    x, y = a[sel], b[sel]

    if x.size == 0:
        return _unmeasurable(0, scale_free=scale_free, scale_ratio=None)

    scale_ratio = None
    n_out_of_range = 0
    if scale_free:
        # Spec §7: normalise each map by its own masked median, for maps whose unit is
        # 'au' and whose amplitude is therefore a free scale (vfa_t1/M0, mono_t2/M0).
        # Default off, and applied PER UNIT by the caller that knows the unit, NEVER
        # globally: b1_afi's B1map is a genuine ratio in which 1.0 means the nominal flip
        # angle was reached, so normalising a 10% offset away there would delete the
        # finding instead of measuring it.
        mx, my = float(np.median(x)), float(np.median(y))
        # Reported, never thresholded — hence the key name. For a free scale the recovered
        # amplitude ratio is not a disagreement, and a column called `scale_ratio` sitting
        # beside `rel_median_diff` would be read as one.
        if my != 0.0:
            scale_ratio = mx / my
        if mx == 0.0 or my == 0.0:
            # Nothing to normalise by. Dividing anyway publishes nan or inf in a column
            # that everything downstream reads as a measurement.
            return _unmeasurable(
                int(x.size), scale_free=scale_free, scale_ratio=scale_ratio
            )
        x, y = x / mx, y / my

        if scale_free_range is not None:
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
            n_out_of_range = int((~keep).sum())
            x, y = x[keep], y[keep]
            if x.size == 0:
                return _unmeasurable(
                    0, scale_free=scale_free, scale_ratio=scale_ratio,
                    n_out_of_range=n_out_of_range,
                )

    delta = x - y
    # Relative to the reference `b`, matching compare_maps.py. Where b is exactly
    # zero the tolerance band collapses, so only an exact match counts — correct,
    # since a relative tolerance around zero has no meaning.
    within = np.abs(delta) <= rel_tol * np.abs(y)

    if x.size > 1 and x.std() > 0 and y.std() > 0:
        pearson_r = float(np.corrcoef(x, y)[0, 1])
    else:
        pearson_r = None

    # The headline (spec §7). Directly interpretable — "QUIT reads 3% lower T1" — and the
    # median keeps it clear of the outliers that already force a skew warning on the
    # Values tab. It is MEANINGLESS for a map whose unit is 'au', where the amplitude is a
    # free scale and the ratio of two arbitrary scales is arbitrary; that case is what
    # scale_free=True exists for.
    median_abs_y = float(np.median(np.abs(y)))
    if median_abs_y > 0:
        rel_median_diff = float(np.median(delta) / median_abs_y)
    else:
        # A zero median |y| is `frac_within`'s trap one level up: a relative measure has no
        # meaning around zero. "Not measurable" is the honest answer, not a division by it.
        rel_median_diff = None

    # Lin's concordance. CCC = pearson_r * C_b, so publishing it beside pearson_r
    # decomposes agreement into correlation and calibration: the diagnostic cell is high r
    # with low CCC, two softwares that rank voxels identically and calibrate differently,
    # which a correlation alone cannot show. Population moments (ddof=0) to match how
    # masked_stats already computes std — on sample moments this would no longer be
    # r * C_b of the r published next to it.
    xbar, ybar = float(x.mean()), float(y.mean())
    covariance = float(((x - xbar) * (y - ybar)).mean())
    ccc_denominator = float(x.var() + y.var() + (xbar - ybar) ** 2)
    # size > 1 for pearson_r's reason: one voxel has no variance to concord, and the
    # formula would still return a number (0, from the mean offset alone) if allowed to.
    if x.size > 1 and ccc_denominator > 0:
        ccc = float(2.0 * covariance / ccc_denominator)
    else:
        ccc = None

    return {
        "n": int(x.size),
        "frac_within": float(within.mean()),
        "pearson_r": pearson_r,
        "mean_delta": float(delta.mean()),
        "median_delta": float(np.median(delta)),
        "max_abs_delta": float(np.abs(delta).max()),
        "rel_median_diff": rel_median_diff,
        "ccc": ccc,
        # Carried on the row because every other number in it changes meaning when this is
        # true: they were computed on median-normalised maps. A row of normalised numbers
        # that does not say so is exactly the misreading spec §7.3 exists to prevent.
        "scale_free": scale_free,
        "scale_ratio_not_a_disagreement": scale_ratio,
        # Reported for masked_stats' n_nonfinite reason: an exclusion nobody can see is
        # indistinguishable from a mask that never had those voxels. 0 whenever no range
        # was applied, so the key means the same thing on every row.
        "n_out_of_range": n_out_of_range,
    }
