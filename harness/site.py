"""Render results.json as one self-contained page.

No framework, no CDN, no fetch: inline SVG, inline CSS, vanilla JS. The page must
render identically from a file:// URL and from GitHub Pages, and must still open in
five years (spec §9).

Colour follows the validated palette in the dataviz reference: categorical slots are
used in fixed order and never cycled, and never more than three in a matrix-style
context, because past three the palette cannot clear the all-pairs colour-vision
floors. Anything beyond three shared classes folds into one "other" slot rather than
inventing a ninth hue. Magnitude uses one hue light->dark. Status colours are reserved
and always ship with a text label, never colour alone.
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import statistics

# Chronological, so every version axis reads left-to-right as history rather than
# alphabetically (which would put v2.0.10 before v2.0.2 and master in the middle).
TARGET_ORDER = [
    "qmrlab@V1", "qmrlab@v2.0.0", "qmrlab@v2.0.1", "qmrlab@v2.0.2", "qmrlab@v2.0.3",
    "qmrlab@v2.0.5", "qmrlab@v2.1.0", "qmrlab@v2.2.0", "qmrlab@v2.3.0", "qmrlab@v2.4.0",
    "qmrlab@v2.4.1", "qmrlab@v2.5.0", "qmrlab@v3.0.0", "qmrlab@master", "qmrust@main",
]

# Models whose fit is iterative. qMRLab's qMT fit is NOT run-to-run deterministic
# (verified: master and v3.0.0 are the same commit and produced different hashes in
# one run, differing by ~5e-7 relative), so for these a hash difference does not
# imply a real difference and the page must say so.
ITERATIVE = {"qmt_spgr", "mono_t2", "inversion_recovery"}

SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
       "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]

_CSS = """
:root{--surface:#fcfcfb;--panel:#f4f3f0;--ink:#0b0b0b;--ink2:#52514e;--ink3:#86847d;
--rule:#dbd9d3;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--other:#8a8880;--uniq:#c9c7c0;
--good:#0ca30c;--warn:#fab219;--serious:#ec835a;--crit:#d03b3b;}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme=light])){
--surface:#1a1a19;--panel:#242422;--ink:#fff;--ink2:#c3c2b7;--ink3:#8d8b82;
--rule:#3a3a37;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--other:#7d7b74;--uniq:#4a4945;}}
:root[data-theme=dark]{--surface:#1a1a19;--panel:#242422;--ink:#fff;--ink2:#c3c2b7;
--ink3:#8d8b82;--rule:#3a3a37;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--other:#7d7b74;
--uniq:#4a4945;}
*{box-sizing:border-box}
body{margin:0;background:var(--surface);color:var(--ink);
font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:1.5rem 1.25rem 4rem}
h1{font-size:1.5rem;margin:0 0 .2rem}
.sub{color:var(--ink2);margin:0 0 1.25rem;font-size:.92rem}
.tabs{display:flex;gap:.35rem;flex-wrap:wrap;border-bottom:1px solid var(--rule);margin-bottom:1.25rem}
.tabs button{background:none;border:0;border-bottom:2px solid transparent;color:var(--ink2);
font:inherit;font-size:.93rem;padding:.55rem .85rem;cursor:pointer}
.tabs button[aria-selected=true]{color:var(--ink);border-bottom-color:var(--s1);font-weight:600}
.tiles{display:flex;gap:.75rem;flex-wrap:wrap;margin-bottom:1.5rem}
.tile{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:.7rem .95rem;min-width:118px}
.tile .n{font-size:1.6rem;font-weight:650;line-height:1.1}
.tile .l{font-size:.78rem;color:var(--ink2)}
table{border-collapse:collapse;font-size:.85rem;margin-bottom:1.4rem}
th,td{border:1px solid var(--rule);padding:.3rem .55rem;text-align:left;white-space:nowrap}
th{background:var(--panel);font-weight:600}
caption{text-align:left;color:var(--ink2);font-size:.85rem;padding:.15rem 0 .5rem;max-width:70ch;white-space:normal}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.85em}
.na{color:var(--ink3)}
.legend{display:flex;gap:.9rem;flex-wrap:wrap;font-size:.8rem;color:var(--ink2);margin:.1rem 0 .8rem}
.legend i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:.3rem;vertical-align:-1px}
.note{background:var(--panel);border-left:3px solid var(--warn);padding:.6rem .85rem;
border-radius:0 6px 6px 0;font-size:.86rem;color:var(--ink2);margin:0 0 1.1rem;max-width:76ch}
.note b{color:var(--ink)}
select{font:inherit;font-size:.86rem;padding:.25rem .4rem;background:var(--panel);
color:var(--ink);border:1px solid var(--rule);border-radius:5px}
.ctl{display:flex;gap:.7rem;align-items:center;margin-bottom:.9rem;flex-wrap:wrap}
.scroll{overflow-x:auto;max-width:100%}
#tip{position:fixed;pointer-events:none;opacity:0;transition:opacity .08s;background:var(--ink);
color:var(--surface);padding:.35rem .55rem;border-radius:5px;font-size:.78rem;z-index:9;max-width:280px}
#theme{position:absolute;top:1.5rem;right:1.25rem;background:var(--panel);color:var(--ink2);
border:1px solid var(--rule);border-radius:5px;font:inherit;font-size:.8rem;padding:.25rem .55rem;cursor:pointer}
svg{display:block;max-width:100%}
svg text{fill:var(--ink2);font-size:11px}
svg .ax{stroke:var(--rule);stroke-width:1}
"""

_JS = """
(function(){
 var t=document.getElementById('tip');
 document.querySelectorAll('.tabs button').forEach(function(b){
  b.onclick=function(){
   document.querySelectorAll('.tabs button').forEach(function(x){x.setAttribute('aria-selected','false')});
   document.querySelectorAll('section[data-pane]').forEach(function(p){p.hidden=true});
   b.setAttribute('aria-selected','true');
   document.querySelector('section[data-pane="'+b.dataset.tab+'"]').hidden=false;};});
 document.addEventListener('mouseover',function(e){
  var el=e.target.closest('[data-tip]'); if(!el){t.style.opacity=0;return;}
  t.textContent=el.dataset.tip; t.style.opacity=1;});
 document.addEventListener('mousemove',function(e){
  t.style.left=Math.min(e.clientX+14,innerWidth-292)+'px'; t.style.top=(e.clientY+16)+'px';});
 document.querySelectorAll('select[data-controls]').forEach(function(s){
  s.onchange=function(){
   document.querySelectorAll('[data-group="'+s.dataset.controls+'"]').forEach(function(g){
    g.hidden = g.dataset.key !== s.value;});};
  s.onchange();});
 var th=document.getElementById('theme');
 th.onclick=function(){
  var d=document.documentElement.getAttribute('data-theme')==='dark';
  document.documentElement.setAttribute('data-theme',d?'light':'dark');};
})();
"""


def _e(s):
    return html.escape(str(s))


def _fmt(v, sig=6):
    if v is None:
        return '<span class="na">—</span>'
    if isinstance(v, float):
        return f"{v:.{sig}g}"
    return _e(v)


def _short(t):
    return t.replace("qmrlab@", "").replace("qmrust@main", "qmrust")


def _ordered(targets):
    known = [t for t in TARGET_ORDER if t in targets]
    return known + sorted(t for t in targets if t not in TARGET_ORDER)


def _by(doc):
    return {(r["target"], r["model"]): r for r in doc["records"]}


def _models(doc):
    return sorted({r["model"] for r in doc["records"]})


def _maps_of(doc, model):
    out = []
    for r in doc["records"]:
        if r["model"] == model:
            for m in r["maps"]:
                if m["name"] not in out:
                    out.append(m["name"])
    return out


# ---------------------------------------------------------------- overview

def _tiles(doc):
    recs = doc["records"]
    ok = [r for r in recs if r["status"] == "ok"]
    bad = [r for r in recs if r["status"] == "failed"]
    tiles = [
        (len({r["target"] for r in recs}), "targets"),
        (len({r["model"] for r in recs}), "models"),
        (len(ok), "successful fits"),
        (len(bad), "failed fits"),
    ]
    return ('<div class="tiles">' + "".join(
        f'<div class="tile"><div class="n">{n}</div><div class="l">{_e(l)}</div></div>'
        for n, l in tiles) + "</div>")


_STATUS = {
    "ok": ("var(--good)", "✓", "ok", "ok"),
    "failed": ("var(--crit)", "✕", "failed", "failed"),
    "missing": ("var(--serious)", "!", "missing", "missing"),
    "not_applicable": ("var(--uniq)", "·", "not applicable", "na"),
}


def _status_matrix(doc):
    tg = _ordered({r["target"] for r in doc["records"]})
    ms = _models(doc)
    by = _by(doc)
    rows = []
    for t in tg:
        cells = []
        for m in ms:
            r = by.get((t, m))
            st = r["status"] if r else "not_applicable"
            col, icon, lab, cls = _STATUS.get(st, _STATUS["not_applicable"])
            tip = f"{_short(t)} / {m}: {lab}"
            if r and r.get("error"):
                tip += f" — {r['error'][:120]}"
            cells.append(
                f'<td class="{cls}" data-tip="{_e(tip)}" '
                f'style="text-align:center;color:{col};font-weight:600">{icon}</td>')
        rows.append(f"<tr><th>{_e(_short(t))}</th>{''.join(cells)}</tr>")
    head = "".join(f"<th>{_e(m)}</th>" for m in ms)
    legend = " ".join(
        f'<span><i style="background:{c}"></i>{_e(l)}</span>'
        for c, _, l, _cls in _STATUS.values())
    # Errors rendered visibly, not tooltip-only: spec §10 makes failure data, and a
    # reason a reader has to hover to find is a reason most readers never see.
    probs = [f'<li><code>{_e(_short(r["target"]))}</code> / {_e(r["model"])} — '
             f'{_e(_STATUS.get(r["status"], _STATUS["not_applicable"])[2])}: '
             f'{_e(r.get("error") or "no reason recorded")}</li>'
             for r in doc["records"] if r["status"] in ("failed", "missing")]
    problems = ("" if not probs else
                '<h2 style="font-size:1rem;margin:.4rem 0 .3rem">What did not run</h2>'
                f'<ul class="sub" style="margin:0 0 1rem;padding-left:1.1rem">{"".join(probs)}</ul>')
    return (
        '<div class="scroll"><table><caption>Every declared target &times; model. A status '
        "colour never carries meaning alone — each cell has an icon, and hovering gives the "
        "reason a cell failed.</caption>"
        f"<tr><th></th>{head}</tr>{''.join(rows)}</table></div>"
        f'<div class="legend">{legend}</div>{problems}')


# ---------------------------------------------------------------- agreement

def _bands(doc):
    """Equivalence bands: which versions produced identical values.

    Hash identity is arbitrary, so colour encodes *sharing*, not which class. The
    three largest shared classes take the validated categorical slots; further shared
    classes fold into one "other" slot rather than inventing a ninth hue; singletons
    are muted, because "this version is unique" is the expected case and sharing is
    the finding. Every band is direct-labelled, which is also the documented relief
    for the light-mode contrast warning on slot 3.
    """
    out = []
    for model in _models(doc):
        for mp in _maps_of(doc, model):
            classes = doc.get("equivalence", {}).get(model, {}).get(mp, {})
            if not classes:
                continue
            tg = _ordered([t for grp in classes.values() for t in grp])
            shared = sorted((h for h, g in classes.items() if len(g) > 1),
                            key=lambda h: -len(classes[h]))
            colour = {}
            for i, h in enumerate(shared):
                colour[h] = f"var(--s{i + 1})" if i < 3 else "var(--other)"
            w, gap, hgt = 78, 3, 34
            svg = [f'<svg width="{len(tg) * (w + gap)}" height="{hgt + 30}" role="img">']
            for i, t in enumerate(tg):
                h = next((k for k, g in classes.items() if t in g), None)
                fill = colour.get(h, "var(--uniq)")
                n = len(classes.get(h, []))
                lab = f"×{n}" if n > 1 else "unique"
                tip = f"{_short(t)} — {'shares with ' + str(n - 1) + ' other(s)' if n > 1 else 'unique'} · {h[:12] if h else ''}"
                x = i * (w + gap)
                svg.append(
                    f'<g data-tip="{_e(tip)}"><rect x="{x}" y="0" width="{w}" height="{hgt}" '
                    f'rx="4" fill="{fill}"/>'
                    f'<text x="{x + w / 2}" y="{hgt / 2 + 4}" text-anchor="middle" '
                    f'style="fill:#fff;font-weight:600">{_e(lab)}</text>'
                    f'<text x="{x + w / 2}" y="{hgt + 16}" text-anchor="middle">'
                    f"{_e(_short(t))}</text></g>")
            svg.append("</svg>")
            cap = (f"<b>{_e(model)} / {_e(mp)}</b> — cells with the same colour produced "
                   "byte-identical maps; muted cells are unique to that version.")
            if model in ITERATIVE:
                cap += (" <b>Caveat:</b> this fit is iterative and not run-to-run "
                        "deterministic (~5e-7 relative), so a colour change here can be "
                        "noise rather than a real difference — read the agreement matrix "
                        "instead.")
            out.append(
                f'<div data-group="band" data-key="{_e(model + "/" + mp)}">'
                f'<p class="sub" style="margin:.2rem 0 .4rem">{cap}</p>'
                f'<div class="scroll">{"".join(svg)}</div></div>')
    keys = [f'<option value="{_e(m + "/" + mp)}">{_e(m)} / {_e(mp)}</option>'
            for m in _models(doc) for mp in _maps_of(doc, m)
            if doc.get("equivalence", {}).get(m, {}).get(mp)]
    return ('<div class="ctl"><label>Map <select data-controls="band">'
            + "".join(keys) + "</select></label></div>" + "".join(out))


def _matrices(doc):
    """Triangular target x target heatmap, shaded by fraction-within-tolerance."""
    out, keys = [], []
    for model in _models(doc):
        for mp in _maps_of(doc, model):
            pairs = doc.get("comparisons", {}).get(model, {}).get(mp, [])
            if not pairs:
                continue
            keys.append(f'<option value="{_e(model + "/" + mp)}">{_e(model)} / {_e(mp)}</option>')
            tg = _ordered({p["a"] for p in pairs} | {p["b"] for p in pairs})
            look = {(p["a"], p["b"]): p for p in pairs}
            look.update({(p["b"], p["a"]): p for p in pairs})
            c, pad = 34, 108
            n = len(tg)
            svg = [f'<svg width="{pad + n * c + 10}" height="{pad + n * c + 10}" role="img">']
            for j, tb in enumerate(tg):
                svg.append(f'<text x="{pad - 6}" y="{pad + j * c + c / 2 + 4}" '
                           f'text-anchor="end">{_e(_short(tb))}</text>')
                svg.append(f'<text transform="translate({pad + j * c + c / 2},{pad - 6}) rotate(-60)" '
                           f'text-anchor="start">{_e(_short(tb))}</text>')
            for i, ta in enumerate(tg):
                for j, tb in enumerate(tg):
                    if j > i:
                        continue
                    x, y = pad + j * c, pad + i * c
                    if ta == tb:
                        svg.append(f'<rect x="{x}" y="{y}" width="{c - 2}" height="{c - 2}" '
                                   f'rx="3" fill="{SEQ[-1]}" data-tip="{_e(_short(ta))} vs itself"/>')
                        continue
                    p = look.get((ta, tb))
                    if p is None or p.get("frac_within") is None:
                        svg.append(f'<rect x="{x}" y="{y}" width="{c - 2}" height="{c - 2}" '
                                   f'rx="3" fill="var(--uniq)" data-tip="no comparable voxels"/>')
                        continue
                    fw = p["frac_within"]
                    fill = SEQ[min(len(SEQ) - 1, int(fw * (len(SEQ) - 1)))]
                    r = p.get("pearson_r")
                    tip = (f"{_short(ta)} vs {_short(tb)} — within 1%: {fw:.4g}"
                           f" · r: {'—' if r is None else format(r, '.6g')}")
                    svg.append(f'<rect x="{x}" y="{y}" width="{c - 2}" height="{c - 2}" rx="3" '
                               f'fill="{fill}" data-tip="{_e(tip)}"/>')
            svg.append("</svg>")
            out.append(f'<div data-group="mat" data-key="{_e(model + "/" + mp)}" hidden>'
                       f'<div class="scroll">{"".join(svg)}</div></div>')
    ramp = "".join(f'<i style="background:{c};border-radius:0;width:16px"></i>' for c in SEQ)
    return ('<div class="ctl"><label>Map <select data-controls="mat">' + "".join(keys)
            + "</select></label></div>" + "".join(out)
            + f'<div class="legend"><span>fraction of voxels agreeing within 1%: 0 {ramp} 1</span></div>')


# ---------------------------------------------------------------- values

def _ranges(doc):
    out, keys = [], []
    for model in _models(doc):
        for mp in _maps_of(doc, model):
            rows = []
            for r in doc["records"]:
                if r["model"] != model or r["status"] != "ok":
                    continue
                for m in r["maps"]:
                    if m["name"] == mp and m["stats"].get("median") is not None:
                        rows.append((r["target"], m["stats"], m["stats_unit"]))
            if not rows:
                continue
            keys.append(f'<option value="{_e(model + "/" + mp)}">{_e(model)} / {_e(mp)}</option>')
            order = {t: i for i, t in enumerate(_ordered([t for t, _, _ in rows]))}
            rows.sort(key=lambda x: order[x[0]])
            lo = min(s["p05"] for _, s, _ in rows)
            hi = max(s["p95"] for _, s, _ in rows)
            span = (hi - lo) or 1.0
            pad, w, rh = 116, 620, 26
            svg = [f'<svg width="{pad + w + 60}" height="{len(rows) * rh + 34}" role="img">']
            outlier = False
            for i, (t, s, unit) in enumerate(rows):
                y = i * rh + 20
                sx = lambda v: pad + (v - lo) / span * w  # noqa: E731
                x0, x1 = max(pad, sx(s["p05"])), min(pad + w, sx(s["p95"]))
                svg.append(f'<text x="{pad - 8}" y="{y + 5}" text-anchor="end">{_e(_short(t))}</text>')
                tip = (f"{_short(t)} — median {s['median']:.6g} {unit} · "
                       f"p05 {s['p05']:.4g} · p95 {s['p95']:.4g} · n {s['n']}")
                svg.append(f'<g data-tip="{_e(tip)}">'
                           f'<rect x="{x0}" y="{y - 7}" width="{max(2, x1 - x0)}" height="14" '
                           f'rx="4" fill="var(--s1)" opacity=".38"/>'
                           f'<circle cx="{max(pad, min(pad + w, sx(s["median"])))}" cy="{y}" '
                           f'r="4.5" fill="var(--s1)"/></g>')
                if s["mean"] is not None and abs(s["mean"] - s["median"]) > 10 * abs(s["median"]):
                    outlier = True
                    svg.append(f'<text x="{pad + w + 8}" y="{y + 4}" '
                               f'style="fill:var(--warn);font-weight:600">skewed</text>')
            svg.append(f'<text x="{pad}" y="{len(rows) * rh + 26}">{lo:.4g}</text>'
                       f'<text x="{pad + w}" y="{len(rows) * rh + 26}" text-anchor="end">{hi:.4g}</text>'
                       "</svg>")
            cap = (f"<b>{_e(model)} / {_e(mp)}</b> — box spans p05&ndash;p95, dot is the median, "
                   f"in {_e(rows[0][2])}. Distributions are summarised from stored quantiles; "
                   "raw voxel histograms are not published.")
            if outlier:
                cap += ('  <span class="outlier-flag" style="color:var(--warn);font-weight:600">'
                        "&#9888; outlier-dominated mean</span> — rows marked <i>skewed</i> have a "
                        "mean orders of magnitude from their median, because a few extreme voxels "
                        "dominate it. The median is the figure to read.")
            out.append(f'<div data-group="rng" data-key="{_e(model + "/" + mp)}" hidden>'
                       f'<p class="sub" style="margin:.2rem 0 .5rem">{cap}</p>'
                       f'<div class="scroll">{"".join(svg)}</div></div>')
    return ('<div class="ctl"><label>Map <select data-controls="rng">' + "".join(keys)
            + "</select></label></div>" + "".join(out))


# ---------------------------------------------------------------- timing

def _timing(doc):
    import math
    rows = []
    for r in doc["records"]:
        s = (r.get("timing") or {}).get("fit_seconds") or []
        if r["status"] == "ok" and s:
            rows.append((r["model"], r["target"], statistics.median(s),
                         r["environment"].get("matlab_release") or "—"))
    if not rows:
        return "<p>No timing data.</p>"
    lo = min(v for _, _, v, _ in rows)
    hi = max(v for _, _, v, _ in rows)
    l0, l1 = math.log10(max(lo, 1e-4)), math.log10(hi)
    span = (l1 - l0) or 1.0
    pad, w, rh = 210, 560, 21
    rows.sort(key=lambda x: (x[0], -x[2]))
    svg = [f'<svg width="{pad + w + 80}" height="{len(rows) * rh + 34}" role="img">']
    for i, (model, t, v, rel) in enumerate(rows):
        y = i * rh + 16
        bw = max(2, (math.log10(max(v, 1e-4)) - l0) / span * w)
        svg.append(f'<text x="{pad - 8}" y="{y + 4}" text-anchor="end">'
                   f"{_e(model)} · {_e(_short(t))}</text>")
        svg.append(f'<g data-tip="{_e(f"{_short(t)} / {model}: {v:.4g} s (MATLAB {rel})")}">'
                   f'<rect x="{pad}" y="{y - 6}" width="{bw}" height="12" rx="4" '
                   f'fill="var(--s1)"/></g>')
        svg.append(f'<text x="{pad + bw + 6}" y="{y + 4}">{v:.3g}s</text>')
    svg.append("</svg>")
    return ('<p class="note"><b>These lanes do not measure the same thing.</b> The MATLAB lane '
            "times the fit call in-process; the Rust lane times the whole <code>qmrust fit</code> "
            "process, which includes roughly 30&nbsp;ms of start-up. Cross-lane comparison is "
            "unsound below about a second, and per-voxel rates are deliberately not shown. "
            "Runners are shared hardware, so treat all figures as indicative.</p>"
            f'<div class="scroll">{"".join(svg)}</div>'
            '<div class="legend"><span>median of repeats · log scale</span></div>')


# ---------------------------------------------------------------- data

def _tables(doc):
    rows = []
    for r in sorted(doc["records"], key=lambda r: (r["model"], r["target"])):
        for m in r["maps"]:
            s = m["stats"]
            rows.append(
                f"<tr><td>{_e(r['model'])}</td><td>{_e(m['name'])}</td>"
                f"<td>{_e(_short(r['target']))}</td><td>{_e(m['stats_unit'])}</td>"
                f"<td>{_fmt(s.get('median'))}</td><td>{_fmt(s.get('mean'))}</td>"
                f"<td>{_fmt(s.get('p05'))}</td><td>{_fmt(s.get('p95'))}</td>"
                f"<td>{_fmt(s.get('n'))}</td><td>{_fmt(s.get('n_nonfinite'))}</td>"
                f"<td><code>{_e(m['voxel_sha256'][:8])}</code></td></tr>")
    prov = []
    seen = set()
    for r in doc["records"]:
        e = r["environment"]
        k = (r["target"], e.get("matlab_release"))
        if k in seen:
            continue
        seen.add(k)
        prov.append(f"<tr><td>{_e(_short(r['target']))}</td>"
                    f"<td>{_e(e.get('matlab_release') or '—')}</td>"
                    f"<td>{_e(e.get('runner_os') or '—')}</td>"
                    f"<td><code>{_e((e.get('harness_commit') or '—')[:10])}</code></td>"
                    f"<td>{_e(e.get('run_started_utc') or '—')}</td></tr>")
    return (
        '<p class="sub">The full numbers, and the accessible fallback for every chart above. '
        'Machine-readable: <a href="data/results.json">results.json</a> · '
        '<a href="data/history.jsonl">history.jsonl</a> (per-run digests).</p>'
        '<div class="scroll"><table><caption>Masked statistics in each model\'s canonical unit. '
        "The hash is over the unit the software produced, so it will not match across a unit "
        "difference — those outputs genuinely are not the same bytes.</caption>"
        "<tr><th>Model</th><th>Map</th><th>Target</th><th>Unit</th><th>Median</th><th>Mean</th>"
        "<th>p05</th><th>p95</th><th>n</th><th>non-finite</th><th>Hash</th></tr>"
        + "".join(rows) + "</table></div>"
        '<div class="scroll"><table><caption>Provenance.</caption>'
        "<tr><th>Target</th><th>MATLAB</th><th>Runner</th><th>Harness</th><th>Run started</th></tr>"
        + "".join(prov) + "</table></div>")


# ---------------------------------------------------------------- page

def render(doc: dict) -> str:
    ref = doc.get("reference")
    # A target present only as a `missing` record produced nothing, so naming it as the
    # reference would promise a comparison the page cannot show.
    has_ref = any(r["target"] == ref and r["status"] != "missing" for r in doc["records"])
    tabs = [("overview", "Overview"), ("agree", "Agreement"), ("values", "Values"),
            ("timing", "Timing"), ("data", "Data")]
    nav = "".join(
        f'<button data-tab="{k}" aria-selected="{"true" if i == 0 else "false"}">{_e(l)}</button>'
        for i, (k, l) in enumerate(tabs))
    panes = {
        "overview": _tiles(doc) + _status_matrix(doc),
        "agree": ('<p class="sub">Which versions produced identical maps, and how closely any '
                  "two agree.</p>" + _bands(doc) + "<h2>Pairwise agreement</h2>" + _matrices(doc)),
        "values": _ranges(doc),
        "timing": _timing(doc),
        "data": _tables(doc),
    }
    body = "".join(
        f'<section data-pane="{k}"{"" if i == 0 else " hidden"}>{panes[k]}</section>'
        for i, (k, _) in enumerate(tabs))
    subtitle = ("Eight qMRI models fitted against identical, checksum-pinned data across every "
                "qMRLab release and qmrust.")
    if has_ref:
        subtitle += f" Reference target: {_e(_short(ref))}."
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>qMRLab cross-version benchmark</title>"
            f"<style>{_CSS}</style></head><body>"
            '<button id="theme">theme</button><div id="tip"></div>'
            '<div class="wrap"><h1>qMRLab cross-version benchmark</h1>'
            f'<p class="sub">{subtitle}</p>'
            f'<nav class="tabs">{nav}</nav>{body}</div>'
            f"<script>{_JS}</script></body></html>")


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
