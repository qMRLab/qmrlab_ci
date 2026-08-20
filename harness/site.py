"""Render results.json as one self-contained page.

No framework and no external requests: the page must render from a file:// URL and
from GitHub Pages identically, and must still open in five years.
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import statistics

_CSS = """
body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; line-height: 1.5; }
table { border-collapse: collapse; margin-bottom: 2rem; font-size: 0.9rem; }
th, td { border: 1px solid #ccc; padding: 0.3rem 0.6rem; text-align: left; }
th { background: #f4f4f4; }
/* failed: the adapter ran and reported a problem. */
.failed { background: #fde8e8; }
/* missing: the catalog declared this (target, model) but no record at all came
   back -- not even a failure -- the signature of a killed/never-run CI job. Must
   read as distinctly alarming as failed, not as a benign hole. */
.missing { background: #fff3cd; color: #7a5800; font-weight: 600; }
/* na: a target never declared this model. A genuine, expected capability gap. */
.na { color: #999; font-style: italic; }
.outlier-row { background: #fff8e1; }
.outlier-flag { cursor: help; }
.legend { font-size: 0.85rem; color: #555; max-width: 60rem; }
code { font-family: ui-monospace, monospace; }
caption { text-align: left; font-weight: 600; padding-bottom: 0.4rem; }
"""


def _median_seconds(timing: dict):
    samples = timing.get("fit_seconds") or []
    return statistics.median(samples) if samples else None


def _fmt(value):
    if value is None:
        return '<span class="na">—</span>'
    if isinstance(value, float):
        return f"{value:.6g}"
    return html.escape(str(value))


def _matrix_table(doc: dict) -> str:
    targets = sorted({r["target"] for r in doc["records"]})
    models = sorted({r["model"] for r in doc["records"]})
    by_key = {(r["target"], r["model"]): r for r in doc["records"]}

    rows = []
    for target in targets:
        cells = []
        for model in models:
            record = by_key.get((target, model))
            if record is None or record["status"] == "not_applicable":
                # A hole, never a failure (spec §2.4): this target never declared
                # the model, or declared it does not apply.
                cells.append('<td class="na">not applicable</td>')
            elif record["status"] == "missing":
                # The catalog declared this combination and nothing came back for
                # it -- not even a failure. Failure is data (spec §10); a run that
                # lost part of its matrix must be visible, not silently a hole.
                cells.append(f'<td class="missing">missing: {_fmt(record["error"])}</td>')
            elif record["status"] == "failed":
                cells.append(f'<td class="failed">failed: {_fmt(record["error"])}</td>')
            else:
                hashes = " ".join(
                    f'<code>{html.escape(m["voxel_sha256"][:8])}</code>'
                    for m in record["maps"]
                )
                cells.append(f"<td>{hashes or 'ok'}</td>")
        rows.append(f"<tr><th>{html.escape(target)}</th>{''.join(cells)}</tr>")

    head = "".join(f"<th>{html.escape(m)}</th>" for m in models)
    return (
        "<table><caption>Targets &times; models — cell shows each map's equivalence "
        "hash. \"not applicable\" means this target never declared the model (a real "
        "capability gap); \"missing\" means the catalog declared it but the run "
        "produced no record at all for it — the signature of a job that was killed "
        "or never ran, and is a failure of the run, not a property of the software."
        f"</caption><tr><th></th>{head}</tr>{''.join(rows)}</table>"
    )


def _timing_table(doc: dict) -> str:
    rows = []
    for record in sorted(doc["records"], key=lambda r: (r["model"], r["target"])):
        if record["status"] != "ok":
            continue
        timing = record["timing"]
        median = _median_seconds(timing)
        voxels = timing.get("n_voxels_fitted") or 0
        per_voxel = (median / voxels * 1e3) if median and voxels else None
        rows.append(
            "<tr>"
            f"<td>{html.escape(record['model'])}</td>"
            f"<td>{html.escape(record['target'])}</td>"
            f"<td>{_fmt(record['environment'].get('matlab_release'))}</td>"
            f"<td>{_fmt(median)}</td>"
            f"<td>{_fmt(timing.get('repeats'))}</td>"
            f"<td>{_fmt(voxels)}</td>"
            f"<td>{_fmt(per_voxel)}</td>"
            "</tr>"
        )
    return (
        "<table><caption>Fit time — median of repeats. The MATLAB release is shown "
        "because a version-to-version difference otherwise conflates qMRLab changes "
        "with MATLAB changes.</caption>"
        "<tr><th>Model</th><th>Target</th><th>MATLAB</th><th>Median (s)</th>"
        "<th>Repeats</th><th>Voxels</th><th>ms/voxel</th></tr>"
        f"{''.join(rows)}</table>"
    )


_OUTLIER_FACTOR = 10


def _mean_is_outlier_dominated(stats: dict) -> bool:
    """True when the mean is not a trustworthy summary for this row.

    A mask can legitimately contain a handful of voxels with near-zero
    denominators (e.g. mt_sat's PDw dropping to ~1), which sends the mean to
    astronomical values while the median stays physically plausible. That is
    correct arithmetic and a misleading headline; this only decides which rows
    need the visible caveat (I3, final review).
    """
    mean, median = stats.get("mean"), stats.get("median")
    if mean is None or median is None:
        return False
    return abs(mean - median) > _OUTLIER_FACTOR * abs(median)


def _stats_tables(doc: dict) -> str:
    out = []
    any_flagged = False
    for record in sorted(doc["records"], key=lambda r: (r["model"], r["target"])):
        for m in record["maps"]:
            stats = m["stats"]
            flagged = _mean_is_outlier_dominated(stats)
            any_flagged = any_flagged or flagged

            mean_cell = _fmt(stats.get("mean"))
            mean_class = ""
            if flagged:
                mean_class = ' class="outlier-row"'
                mean_cell = (
                    '<span class="outlier-flag" title="mean is outlier-dominated — '
                    f'see legend below">&#9888;</span> {mean_cell}'
                )

            n_cell = _fmt(stats.get("n"))
            n_nonfinite = stats.get("n_nonfinite")
            if n_nonfinite:
                n_cell = f'{n_cell} <span class="na">({_fmt(n_nonfinite)} non-finite)</span>'

            out.append(
                "<tr>"
                f"<td>{html.escape(record['model'])}</td>"
                f"<td>{html.escape(m['name'])}</td>"
                f"<td>{html.escape(record['target'])}</td>"
                f"<td>{html.escape(m['stats_unit'])}</td>"
                f"<td{mean_class}>{mean_cell}</td>"
                f"<td>{_fmt(stats.get('median'))}</td>"
                f"<td>{_fmt(stats.get('p05'))}</td>"
                f"<td>{_fmt(stats.get('p95'))}</td>"
                f"<td>{_fmt(stats.get('std'))}</td>"
                f"<td>{n_cell}</td>"
                f"<td><code>{html.escape(m['voxel_sha256'][:8])}</code></td>"
                "</tr>"
            )

    legend = ""
    if any_flagged:
        legend = (
            '<p class="legend">&#9888; the mean is outlier-dominated for this row '
            f"(|mean &minus; median| &gt; {_OUTLIER_FACTOR}&times;|median|): a small "
            "number of extreme voxels (e.g. near-zero denominators) pull the mean far "
            "from the bulk of the data even though the arithmetic is correct. The "
            "median, p05 and p95 are the robust figures for these rows.</p>"
        )
    return (
        "<table><caption>Masked statistics, in each model's canonical unit. The hash "
        "is over the unit the software produced, so it will not match across a unit "
        "difference — those outputs are genuinely not the same bytes.</caption>"
        "<tr><th>Model</th><th>Map</th><th>Target</th><th>Unit</th><th>Mean</th>"
        "<th>Median</th><th>p05</th><th>p95</th><th>Std</th><th>n</th><th>Hash</th></tr>"
        f"{''.join(out)}</table>{legend}"
    )


def _comparison_table(doc: dict) -> str:
    rows = []
    for model, by_map in sorted(doc.get("comparisons", {}).items()):
        for map_name, pairs in sorted(by_map.items()):
            for pair in pairs:
                rows.append(
                    "<tr>"
                    f"<td>{html.escape(model)}</td>"
                    f"<td>{html.escape(map_name)}</td>"
                    f"<td>{html.escape(pair['a'])}</td>"
                    f"<td>{html.escape(pair['b'])}</td>"
                    f"<td>{_fmt(pair.get('n'))}</td>"
                    f"<td>{_fmt(pair.get('frac_within'))}</td>"
                    f"<td>{_fmt(pair.get('pearson_r'))}</td>"
                    f"<td>{_fmt(pair.get('mean_delta'))}</td>"
                    f"<td>{_fmt(pair.get('max_abs_delta'))}</td>"
                    "</tr>"
                )
    if not rows:
        return "<p>No comparable pairs.</p>"
    return (
        "<table><caption>Pairwise agreement, in canonical units. Deltas are signed "
        "(a &minus; b) so direction is visible; fraction-within is relative to "
        "b.</caption>"
        "<tr><th>Model</th><th>Map</th><th>a</th><th>b</th><th>n</th>"
        "<th>Within 1%</th><th>Pearson r</th><th>Mean &Delta;</th>"
        "<th>Max |&Delta;|</th></tr>"
        f"{''.join(rows)}</table>"
    )


def _reference_has_records(doc: dict) -> bool:
    """False when the declared reference target's own run produced nothing.

    A `missing` record (C3) means the job never ran or was killed; presenting such
    a target as "the reference" would claim it contributed data it did not.
    """
    reference = doc.get("reference")
    return any(
        r["target"] == reference and r["status"] != "missing"
        for r in doc.get("records", [])
    )


def render(doc: dict) -> str:
    reference_html = ""
    if _reference_has_records(doc):
        reference_html = (
            f"<p>Reference target: <code>{html.escape(doc['reference'])}</code></p>"
        )
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>qMRLab benchmark</title>"
        f"<style>{_CSS}</style></head><body>"
        "<h1>qMRLab cross-version benchmark</h1>"
        f"{reference_html}"
        "<p>Raw data: <a href=\"data/results.json\">results.json</a> &middot; "
        "<a href=\"data/history.jsonl\">history.jsonl</a></p>"
        f"<h2>Matrix</h2>{_matrix_table(doc)}"
        f"<h2>Statistics</h2>{_stats_tables(doc)}"
        f"<h2>Agreement</h2>{_comparison_table(doc)}"
        f"<h2>Timing</h2>{_timing_table(doc)}"
        "</body></html>"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)

    doc = json.loads(pathlib.Path(args.results).read_text())
    out_dir = pathlib.Path(args.out_dir)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(render(doc))
    (out_dir / "data" / "results.json").write_text(json.dumps(doc, indent=2, sort_keys=True))
    print(f"wrote {out_dir}/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
