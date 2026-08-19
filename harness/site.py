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
.failed { background: #fde8e8; }
.na { color: #999; }
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
            if record is None:
                cells.append('<td class="na">not applicable</td>')
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
        "<table><caption>Targets &times; models — cell shows each map's "
        f"equivalence hash</caption><tr><th></th>{head}</tr>{''.join(rows)}</table>"
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


def _stats_tables(doc: dict) -> str:
    out = []
    for record in sorted(doc["records"], key=lambda r: (r["model"], r["target"])):
        for m in record["maps"]:
            stats = m["stats"]
            out.append(
                "<tr>"
                f"<td>{html.escape(record['model'])}</td>"
                f"<td>{html.escape(m['name'])}</td>"
                f"<td>{html.escape(record['target'])}</td>"
                f"<td>{html.escape(m['stats_unit'])}</td>"
                f"<td>{_fmt(stats.get('mean'))}</td>"
                f"<td>{_fmt(stats.get('median'))}</td>"
                f"<td>{_fmt(stats.get('std'))}</td>"
                f"<td>{_fmt(stats.get('n'))}</td>"
                f"<td><code>{html.escape(m['voxel_sha256'][:8])}</code></td>"
                "</tr>"
            )
    return (
        "<table><caption>Masked statistics, in each model's canonical unit. The hash "
        "is over the unit the software produced, so it will not match across a unit "
        "difference — those outputs are genuinely not the same bytes.</caption>"
        "<tr><th>Model</th><th>Map</th><th>Target</th><th>Unit</th><th>Mean</th>"
        "<th>Median</th><th>Std</th><th>n</th><th>Hash</th></tr>"
        f"{''.join(out)}</table>"
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


def render(doc: dict) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>qMRLab benchmark</title>"
        f"<style>{_CSS}</style></head><body>"
        "<h1>qMRLab cross-version benchmark</h1>"
        f"<p>Reference target: <code>{html.escape(doc['reference'])}</code></p>"
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
