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
import dataclasses
import html
import json
import math
import pathlib
import statistics

# Chronological, so every version axis reads left-to-right as history rather than
# alphabetically (which would put v2.0.10 before v2.0.2 and master in the middle).
TARGET_ORDER = [
    "qmrlab@V1", "qmrlab@v2.0.0", "qmrlab@v2.0.1", "qmrlab@v2.0.2", "qmrlab@v2.0.3",
    "qmrlab@v2.0.5", "qmrlab@v2.1.0", "qmrlab@v2.2.0", "qmrlab@v2.3.0", "qmrlab@v2.4.0",
    "qmrlab@v2.4.1", "qmrlab@v2.5.0", "qmrlab@v3.0.0", "qmrlab@master", "qmrust@main",
]

# Versions that track a branch instead of naming a release, so "the latest" of a family
# is not one target but two: the newest tag AND the moving stream. qMRLab publishes both
# (v3.0.0 and master) and the benchmark reports both; qmrust ships only `main`, and SCT
# and QUIT only a tag, so those families contribute one each. A family is never reduced
# to its tag alone here -- dropping qmrlab@master would delete the one qMRLab row that
# can move between runs, which is half of what the cross-software tab is for.
MOVING_VERSIONS = frozenset({"master", "main"})

# The families the five version-history tabs keep (spec §8). Derived from TARGET_ORDER
# rather than listed a second time: TARGET_ORDER is where this repo declares which
# targets have a chronology at all, and a family that gains one gets these tabs by
# being placed there instead of by editing a second constant that could disagree with it.
HISTORY_SOFTWARE = frozenset(t.partition("@")[0] for t in TARGET_ORDER)

# Models whose fit is iterative, and therefore sensitive to the MATLAB build.
#
# An earlier reading of this project's data concluded these fits were not run-to-run
# deterministic. That was WRONG and is retracted: all five models are bit-stable across
# same-session, separate-session and single-threaded runs on a fixed MATLAB build. The
# real cause of the observed difference is that `master` pins matlab_release: latest
# while v3.0.0 pins R2026a, so the same qMRLab source ran on two different MATLAB
# builds -- and a different build shifts lsqcurvefit's converged optimum by ~1e-7.
# That is the confound spec §3.2 records matlab_release for, not nondeterminism.
# Both qMT streams belong here: Ramani and SledPikeRP are the same iterative
# lsqcurvefit, so they carry the same sensitivity to the MATLAB build that this set
# exists to caveat.
ITERATIVE = {"qmt_spgr", "qmt_spgr_ramani", "mono_t2", "inversion_recovery"}

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
/* Reasons and disclosures are sentences, and th,td above is nowrap so a table full of
   them would scroll sideways forever instead of wrapping -- which for text nobody has
   to read is fine and for text the site exists to make readable is not. */
td.txt{white-space:normal;max-width:62ch}
td.txt b{color:var(--ink)}
.legend{display:flex;gap:.9rem;flex-wrap:wrap;font-size:.8rem;color:var(--ink2);margin:.1rem 0 .8rem}
.legend i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:.3rem;vertical-align:-1px}
.note{background:var(--panel);border-left:3px solid var(--warn);padding:.6rem .85rem;
border-radius:0 6px 6px 0;font-size:.86rem;color:var(--ink2);margin:0 0 1.1rem;max-width:76ch}
.note b{color:var(--ink)}
/* Orientation, not data. Every tab opens with one of these, so it has to read as a
   different kind of object from the chart beneath it -- panel fill and a full rule,
   where .note is a warning bar and .tile is a figure card. The figures sit between two
   hairlines because the block is a lede: the sentence, then the count, then the catch. */
.lede{background:var(--panel);border:1px solid var(--rule);border-radius:8px;
padding:.8rem 1rem;margin:0 0 1.4rem;max-width:84ch}
.lede p{margin:0;color:var(--ink2);font-size:.9rem;max-width:78ch}
.lede p+p{margin-top:.5rem}
.lede b,.lede code{color:var(--ink)}
.lede .figs{display:flex;flex-wrap:wrap;gap:.3rem 1.15rem;margin:.6rem 0;padding:.5rem 0;
border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);max-width:none}
.lede .figs span{font-size:.8rem;color:var(--ink2);white-space:nowrap}
.lede .figs b{font-size:1.05rem;font-weight:650;margin-right:.3rem;
font-variant-numeric:tabular-nums}
.lede .figs i{display:inline-block;width:9px;height:9px;border-radius:2px;
margin-right:.35rem;vertical-align:-1px}
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
/* Scatter cards. The plots are read side by side, so they are fixed-width cards in a
   wrap rather than one chart per row. The SVG scales with its card and keeps its own
   aspect (viewBox + height:auto) because the square is load-bearing: the identity line
   is at 45 degrees only while the two axes are the same length in pixels, and a squashed
   plot shows the reader a bias that is not in the data. */
.plots{display:flex;flex-wrap:wrap;gap:1rem 1.1rem;margin:0 0 1.3rem}
.plot{flex:0 1 316px;min-width:248px;margin:0}
.plot svg{width:100%;height:auto}
.plot h3{font:inherit;font-size:.85rem;font-weight:600;margin:0 0 .3rem}
.plot p{margin:.3rem 0 0;font-size:.78rem;color:var(--ink2)}
.plot p b{color:var(--ink)}
/* The flag beside a plot never travels as colour alone -- same rule as the legends. */
.plot i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:.3rem;
vertical-align:-1px}
svg .frame{fill:none;stroke:var(--rule);stroke-width:1}
svg .idl{fill:none;stroke:var(--ink3);stroke-width:1;stroke-dasharray:4 3}
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
    """`software@version` as a label: the '@' becomes a space, and nothing is dropped.

    The two hardcoded replaces this rule replaces ("qmrlab@" -> "", "qmrust@main" ->
    "qmrust") were each a special case for one family, and a third family got neither:
    `sct@7.3` rendered with the '@' still in it, and `quit@v3.4` stayed the longest label
    on the page precisely because it kept the prefix everything else had dropped -- which
    is what pushed it past the fixed label gutters and off the left edge of the SVG.
    A per-family rule cannot be right for a family it has never seen, so there is one
    rule for every family. Keeping the software name costs width on the qMRLab version
    axis, and width is now measured (`_gutter`) instead of assumed, so it costs pixels
    rather than a silently clipped label.
    """
    software, sep, version = str(t).partition("@")
    return f"{software} {version}" if sep and version else str(t)


def _ordered(targets):
    known = [t for t in TARGET_ORDER if t in targets]
    return known + sorted(t for t in targets if t not in TARGET_ORDER)


# Advance widths for the page's sans-serif stack, as a fraction of the font size. An
# estimate, deliberately GENEROUS: over-estimating spends a few pixels of white space,
# while under-estimating silently clips a label at negative x, which is the bug this
# replaces. There is no font metric available at render time -- the page ships no
# assets and runs no measuring pass -- so the estimate is the honest option.
_WIDE_CHARS = "@%MW&mw—"
_NARROW_CHARS = " .,:;'\"|!ijlt()[]·-"


def _text_width(text: str, size: float = 11.0) -> float:
    """Approximate rendered width of one SVG label, in pixels."""
    ems = 0.0
    for ch in str(text):
        if ch in _WIDE_CHARS:
            ems += 1.0
        elif ch in _NARROW_CHARS:
            ems += 0.36
        elif ch.isupper():
            ems += 0.72
        elif ch.isdigit():
            ems += 0.62
        else:
            ems += 0.58
    return ems * size


def _gutter(labels, *, size: float = 11.0, margin: float = 12.0) -> int:
    """Left label gutter wide enough for the longest label, plus breathing room.

    Every caller draws its labels `text-anchor="end"` a few pixels inside this, so the
    margin has to exceed that inset: with the old fixed constants (108, 116, 210) a label
    longer than the constant was drawn at NEGATIVE x and clipped away by the viewport
    with no error, no warning and no gap in the chart to notice.
    """
    return math.ceil(max((_text_width(t, size) for t in labels), default=0.0) + margin)


def _facets(doc):
    """target -> (software, version), from the records' own declared fields.

    `software` and `version` are required non-empty fields on a real adapter record, so
    they are the source of truth for which family a target belongs to -- never the text
    before the '@' in its id, which target.yml owns and could disagree with.

    The exception is analyze.py's synthesized records: a `missing` cell and an
    `analysis failed` cell both carry empty facets. Falling back to the id there is not
    cosmetic -- a target whose every record is `missing` (a killed lane) would otherwise
    have no family at all and vanish from the coverage table, i.e. a dead lane would read
    as a declared hole, the exact confusion the `missing` marker exists to prevent. The
    fallback never overrides a declared field.
    """
    out = {}
    for r in doc["records"]:
        target = r["target"]
        software, version = r.get("software") or "", r.get("version") or ""
        if software and version:
            out[target] = (software, version)
        elif target not in out:
            head, _, tail = target.partition("@")
            out[target] = (head, tail)
    return out


def _families(doc, targets):
    """The software families present, in the target axis' order."""
    facets = _facets(doc)
    out = []
    for t in _ordered(targets):
        software = facets[t][0]
        if software not in out:
            out.append(software)
    return out


def _latest_of_each_software(doc):
    """The cross-software set: every family's current stream(s) and nothing older.

    Derived from the records' `software`/`version` fields, never from a list of target
    ids: SCT is here today and QUIT lands next, and a hardcoded set would render the new
    family as absent rather than as a column -- silently, since nothing would raise.

    A family contributes its moving branch (if it has one) and its newest release (if it
    has one), because for qMRLab both are current and the page reports both. "Newest" is
    TARGET_ORDER's chronology where it knows the target; for a family it does not know,
    it is the alphabetically last id, which is exact while such a family pins exactly one
    release -- every one of them does today. The day a family pins two, its chronology
    belongs in TARGET_ORDER, which is where this repo already declares that fact.
    """
    facets = _facets(doc)
    families = {}
    for target in _ordered(set(facets)):
        families.setdefault(facets[target][0], []).append(target)
    keep = []
    for targets in families.values():
        moving = [t for t in targets if facets[t][1] in MOVING_VERSIONS]
        released = [t for t in targets if facets[t][1] not in MOVING_VERSIONS]
        keep += moving + released[-1:]
    return _ordered(keep)


def _history(doc):
    """`doc` narrowed to the families the version axis is about (spec §8).

    Returns the narrowed doc and the targets it dropped, so the page can say so where a
    reader would otherwise read an absence as a target that did not run.

    Dropping nothing when nothing would be left is not a special case being tidy: the
    filter exists to keep a version-history story readable, and a run with no qMRLab and
    no qmrust records is not that story being crowded out -- it is some other run
    entirely, and filtering it to nothing would publish five empty tabs instead of the
    data it does have.
    """
    facets = _facets(doc)
    keep = {t for t, (software, _) in facets.items() if software in HISTORY_SOFTWARE}
    dropped = _ordered(set(facets) - keep)
    if not keep or not dropped:
        return doc, []

    equivalence = {}
    for model, by_map in doc.get("equivalence", {}).items():
        for map_name, classes in by_map.items():
            kept = {h: [t for t in g if t in keep] for h, g in classes.items()}
            kept = {h: g for h, g in kept.items() if g}
            if kept:
                equivalence.setdefault(model, {})[map_name] = kept

    comparisons = {}
    for model, by_map in doc.get("comparisons", {}).items():
        for map_name, pairs in by_map.items():
            comparisons.setdefault(model, {})[map_name] = [
                p for p in pairs if p.get("a") in keep and p.get("b") in keep
            ]

    narrowed = {
        **doc,
        "records": [r for r in doc["records"] if r["target"] in keep],
        "equivalence": equivalence,
        "comparisons": comparisons,
    }
    return narrowed, dropped


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
        # Counted over the WHOLE run, including the families the five tabs below filter
        # out, because a summary that quietly counted 15 of 17 targets would be the one
        # number on the page a reader has no way to check.
        (len(_families(doc, {r["target"] for r in recs})), "software families"),
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
        '<div class="scroll"><table><caption>Every declared target &times; model in this '
        "view. A status "
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
            # Cell width follows the longest label rather than a constant: these labels
            # are centred, so an over-long one is not clipped but overprints its
            # neighbours, which is the same lost label by another route.
            gap, hgt = 3, 34
            w = max(78, _gutter([_short(t) for t in tg], margin=8))
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
                cap += (" <b>Caveat:</b> this fit is iterative, so its converged optimum "
                        "shifts by around 1e-7 between MATLAB builds. Where two targets "
                        "differ only in MATLAB release — <code>master</code> tracks the "
                        "latest release while tagged versions are pinned — a colour change "
                        "can be the build rather than the software. Check the MATLAB column "
                        "on the Timing tab, and read the agreement matrix, before concluding "
                        "qMRLab changed.")
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
            c = 34
            labels = [_short(t) for t in tg]
            widest = max((_text_width(t) for t in labels), default=0.0)
            pad = _gutter(labels)
            # The column labels are the same strings rotated -60 degrees, so the room
            # they need ABOVE the grid is their length times sin(60) and the room they
            # need to the RIGHT of the last column is their length times cos(60) --
            # neither of which is the left gutter. Sharing one constant for all three,
            # as this chart did, is only ever right by accident.
            top = math.ceil(widest * 0.87) + 10
            right = math.ceil(widest * 0.5) + 10
            n = len(tg)
            svg = [f'<svg width="{pad + n * c + right}" height="{top + n * c + 10}" role="img">']
            for j, tb in enumerate(tg):
                svg.append(f'<text x="{pad - 6}" y="{top + j * c + c / 2 + 4}" '
                           f'text-anchor="end">{_e(_short(tb))}</text>')
                svg.append(f'<text transform="translate({pad + j * c + c / 2},{top - 6}) rotate(-60)" '
                           f'text-anchor="start">{_e(_short(tb))}</text>')
            for i, ta in enumerate(tg):
                for j, tb in enumerate(tg):
                    if j > i:
                        continue
                    x, y = pad + j * c, top + i * c
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

def _value_rows(doc):
    """(model, map, [(target, stats, unit)]) for every chart the Values tab draws.

    Shared with that tab's summary rather than counted a second time there: a summary
    that selected its own rows would be free to disagree with the charts underneath it,
    and a headline count that contradicts the thing it introduces is worse than no
    headline at all.
    """
    out = []
    for model in _models(doc):
        for map_name in _maps_of(doc, model):
            rows = []
            for r in doc["records"]:
                if r["model"] != model or r["status"] != "ok":
                    continue
                for m in r["maps"]:
                    if m["name"] == map_name and m["stats"].get("median") is not None:
                        rows.append((r["target"], m["stats"], m["stats_unit"]))
            if not rows:
                continue
            order = {t: i for i, t in enumerate(_ordered([t for t, _, _ in rows]))}
            rows.sort(key=lambda x: order[x[0]])
            out.append((model, map_name, rows))
    return out


def _skewed(stats):
    """A mean orders of magnitude from its median, i.e. a few voxels dominating it.

    One definition, used by the mark on the chart and by the count in the tab summary,
    so the summary can never say ten rows are skewed above a chart that marks nine.
    """
    mean, median = stats.get("mean"), stats.get("median")
    return (mean is not None and median is not None
            and abs(mean - median) > 10 * abs(median))


def _ranges(doc):
    out, keys = [], []
    for model, mp, rows in _value_rows(doc):
        keys.append(f'<option value="{_e(model + "/" + mp)}">{_e(model)} / {_e(mp)}</option>')
        lo = min(s["p05"] for _, s, _ in rows)
        hi = max(s["p95"] for _, s, _ in rows)
        span = (hi - lo) or 1.0
        w, rh = 620, 26
        # margin 14, because these labels are drawn 8px inside the gutter below.
        pad = _gutter([_short(t) for t, _, _ in rows], margin=14)
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
            if _skewed(s):
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

def _timing_rows(doc):
    """(model, target, median seconds, MATLAB release) for every bar the Timing tab draws.

    Shared with that tab's summary for the reason _value_rows is: the fastest and slowest
    figures in the lede have to be the fastest and slowest bars in the chart, and the only
    way to guarantee that is for both to read the same list.
    """
    rows = []
    for r in doc["records"]:
        seconds = (r.get("timing") or {}).get("fit_seconds") or []
        if r["status"] == "ok" and seconds:
            rows.append((r["model"], r["target"], statistics.median(seconds),
                         r["environment"].get("matlab_release") or "—"))
    return rows


def _timing(doc):
    rows = _timing_rows(doc)
    if not rows:
        return "<p>No timing data.</p>"
    lo = min(v for _, _, v, _ in rows)
    hi = max(v for _, _, v, _ in rows)
    l0, l1 = math.log10(max(lo, 1e-4)), math.log10(hi)
    span = (l1 - l0) or 1.0
    w, rh = 560, 21
    rows.sort(key=lambda x: (x[0], -x[2]))
    # This axis carries "model · target", the longest label on the page, so it is the
    # first one a longer target id pushes off the left edge.
    pad = _gutter([f"{model} · {_short(t)}" for model, t, _, _ in rows], margin=14)
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

_STATS_HEAD = ("<tr><th>Model</th><th>Map</th><th>Target</th><th>Unit</th><th>Median</th>"
               "<th>Mean</th><th>p05</th><th>p95</th><th>n</th><th>non-finite</th>"
               "<th>Hash</th></tr>")


def _stats_rows(records):
    """The masked-statistics rows for a set of records.

    Shared with the cross-software tab rather than written twice: the two tabs show
    different targets, and the day a column is added to one of them is the day the other
    one would quietly stop matching it.
    """
    rows = []
    for r in sorted(records, key=lambda r: (r["model"], r["target"])):
        for m in r["maps"]:
            s = m["stats"]
            rows.append(
                f"<tr><td>{_e(r['model'])}</td><td>{_e(m['name'])}</td>"
                f"<td>{_e(_short(r['target']))}</td><td>{_e(m['stats_unit'])}</td>"
                f"<td>{_fmt(s.get('median'))}</td><td>{_fmt(s.get('mean'))}</td>"
                f"<td>{_fmt(s.get('p05'))}</td><td>{_fmt(s.get('p95'))}</td>"
                f"<td>{_fmt(s.get('n'))}</td><td>{_fmt(s.get('n_nonfinite'))}</td>"
                f"<td><code>{_e(m['voxel_sha256'][:8])}</code></td></tr>")
    return rows


def _tables(doc):
    rows = _stats_rows(doc["records"])
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
        '<p class="sub">Machine-readable: <a href="data/results.json">results.json</a> · '
        '<a href="data/history.jsonl">history.jsonl</a> (per-run digests).</p>'
        '<div class="scroll"><table><caption>Masked statistics in each model\'s canonical unit. '
        "The hash is over the unit the software produced, so it will not match across a unit "
        "difference — those outputs genuinely are not the same bytes.</caption>"
        + _STATS_HEAD
        + "".join(rows) + "</table></div>"
        '<div class="scroll"><table><caption>Provenance.</caption>'
        "<tr><th>Target</th><th>MATLAB</th><th>Runner</th><th>Harness</th><th>Run started</th></tr>"
        + "".join(prov) + "</table></div>")


# ---------------------------------------------------------------- cross-software

# Four states, and the fourth is the point (spec §2.4): a model a family never declared
# is a HOLE, declared by omission from its target.yml, and it must not read as a failure.
# SCT covers 2 of 9 models, so without this distinction its column is seven red-looking
# blanks instead of a declared scope. `missing` stays separate from `failed` for
# analyze.py's reason: a killed job and a reported failure are different facts.
_COVERAGE = {
    "ran": ("var(--good)", "ran"),
    "failed": ("var(--crit)", "failed"),
    "missing": ("var(--serious)", "missing"),
    "hole": ("var(--uniq)", "declared hole"),
}

# The three statuses an analyze record may carry. `not_applicable` is NOT among them:
# it is this page's name for the absence of a record, never a value one holds.
_RECORD_STATUSES = frozenset({"ok", "failed", "missing"})

_FLAG_COLOUR = {"green": "var(--good)", "amber": "var(--warn)", "red": "var(--crit)"}

_UNFLAGGED = ("no comparability class reached this row, so no colour is assignable to it. "
              "An unclassified pair is not a passing one.")


def _pct(v, *, signed: bool = True) -> str:
    """A measured difference keeps its sign, so the row reads as a sentence."""
    if v is None:
        return '<span class="na">—</span>'
    text = f"{100.0 * v:.3g}%"
    return "+" + text if signed and v > 0 else text


def _count(v) -> str:
    return '<span class="na">—</span>' if v is None else f"{int(v):,}"


def _flag_of(pair, where):
    """(colour, reason, estimator class) for one pair row, however analyze spelled it.

    analyze writes the flag flat (`flag`, `flag_reason`); a nested `{colour, reason}` --
    comparability.flag_for's own dataclass, and the other obvious spelling of it -- is
    read as well. Every field is read with .get, because this renderer and the
    analyze-side wiring of flag_for land independently: a page that rendered only once
    the other half existed would take the whole site down in between.

    An ABSENT flag renders as "not classified", never as green -- an unclassified pair is
    not a passing one, which is the rule flag_for already applies to an unmeasured number.
    A flag that is PRESENT but names a colour this page has no meaning for is the opposite
    case and raises: quietly greying out a red pair would publish exactly what the flag
    exists to prevent, and two halves disagreeing about the vocabulary is a bug to fix
    rather than a value to degrade.
    """
    flag = pair.get("flag")
    if isinstance(flag, dict):
        colour, reason = flag.get("colour"), flag.get("reason")
    else:
        colour, reason = flag or pair.get("flag_colour"), pair.get("flag_reason")
    if colour is not None and colour not in _FLAG_COLOUR:
        raise ValueError(
            f"{where}: unknown flag colour {colour!r}; "
            f"expected one of {sorted(_FLAG_COLOUR)}"
        )
    return colour, reason, pair.get("estimator_class")


def _coverage_states(doc, cross):
    """(families, {(model, family): state}) for the cross-software set.

    Generated from the records, never transcribed from spec §2.4, so it cannot drift from
    what actually ran -- a coverage table copied by hand is a claim about the run that no
    run can contradict.
    """
    facets = _facets(doc)
    families = _families(doc, cross)
    by = {}
    for r in doc["records"]:
        if r["target"] in cross:
            by.setdefault((r["model"], facets[r["target"]][0]), []).append(r)

    states = {}
    for model in _models(doc):
        for family in families:
            recs = by.get((model, family), [])
            statuses = {r["status"] for r in recs}
            unknown = statuses - _RECORD_STATUSES
            if unknown:
                # This table is a claim about what ran, and a status nobody has defined
                # cannot be turned into one of four cells without guessing -- a guess here
                # is a wrong claim that looks like a right one. `not_applicable` is
                # refused along with the rest, and deliberately: a hole is declared by
                # omission from target.yml and by nothing else, so a record ASSERTING one
                # would make a killed job indistinguishable from a declared hole (spec
                # §2.4), which is the whole reason the `missing` marker exists.
                raise ValueError(
                    f"{model} / {family}: unknown record status(es) {sorted(unknown)}; "
                    f"expected one of {sorted(_RECORD_STATUSES)}"
                )
            if not recs:
                state = "hole"
            elif "failed" in statuses:
                state = "failed"
            elif "missing" in statuses:
                state = "missing"
            else:
                state = "ran"
            states[(model, family)] = state
    return families, states


def _coverage(doc, cross):
    families, states = _coverage_states(doc, cross)
    facets = _facets(doc)
    rows = []
    for model in _models(doc):
        cells = []
        for family in families:
            colour, label = _COVERAGE[states[(model, family)]]
            targets = ", ".join(
                _short(t) for t in _ordered(cross) if facets[t][0] == family)
            cells.append(f'<td style="color:{colour};font-weight:600" '
                         f'data-tip="{_e(f"{model} / {family} ({targets}): {label}")}">'
                         f"{_e(label)}</td>")
        rows.append(f"<tr><th>{_e(model)}</th>{''.join(cells)}</tr>")
    head = "".join(f"<th>{_e(f)}</th>" for f in families)
    legend = " ".join(f'<span><i style="background:{c}"></i>{_e(l)}</span>'
                      for c, l in _COVERAGE.values())
    # Same precedent as "What did not run": a reason a reader has to hover to find is a
    # reason most readers never see, and a red cell without one is unarguable.
    probs = [f'<li><code>{_e(_short(r["target"]))}</code> / {_e(r["model"])} — '
             f'{_e(r["status"])}: {_e(r.get("error") or "no reason recorded")}</li>'
             for r in doc["records"]
             if r["target"] in cross and r["status"] in ("failed", "missing")]
    problems = ("" if not probs else
                '<p class="sub" style="margin:.2rem 0 .2rem">Why a cell is not '
                '<i>ran</i>:</p>'
                f'<ul class="sub" style="margin:0 0 1rem;padding-left:1.1rem">'
                f'{"".join(probs)}</ul>')
    return (
        '<div class="scroll"><table><caption>Which model each software family covers, '
        "generated from the records this run produced rather than transcribed. "
        "<b>A declared hole is not a failure:</b> a family declares the models it "
        "supports in its <code>target.yml</code> and omission is the only way this repo "
        "declares a gap, so a family covering two models of nine has seven empty cells "
        "by design, not seven broken runs.</caption>"
        f"<tr><th>Model</th>{head}</tr>{''.join(rows)}</table></div>"
        f'<div class="legend">{legend}</div>{problems}')


def _cross_rows(doc, cross):
    """One row per (model, map, cross-software target) compared with the reference."""
    ref = doc.get("reference")
    rows = []
    for model in _models(doc):
        for map_name in _maps_of(doc, model):
            for pair in doc.get("comparisons", {}).get(model, {}).get(map_name, []):
                a, b = pair.get("a"), pair.get("b")
                if ref is None or ref not in (a, b):
                    continue
                other = b if a == ref else a
                if other == ref or other not in cross:
                    continue
                rows.append(
                    {"model": model, "map": map_name, "target": other, "pair": pair})
    order = {t: i for i, t in enumerate(_ordered(cross))}
    rows.sort(key=lambda r: (r["model"], r["map"], order.get(r["target"], len(order))))
    return rows


def _cross_pairs(doc, cross, rows):
    ref = doc.get("reference")
    if not rows:
        return ('<p class="note">No cross-software pair in this run: '
                + ("no reference target is declared, and every row here is measured "
                   "against one." if not ref else
                   "either only one software family produced records, or the reference "
                   f"target <code>{_e(_short(ref))}</code> has none.") + "</p>")
    body = []
    for row in rows:
        pair = row["pair"]
        where = f"{row['model']}/{row['map']} {pair.get('a')} vs {pair.get('b')}"
        colour, reason, estimator_class = _flag_of(pair, where)
        swatch, label = _FLAG_COLOUR.get(colour, "var(--ink3)"), colour or "not classified"
        text = reason or _UNFLAGGED
        if estimator_class:
            # Carried when analyze publishes it, because it is the rule behind the
            # colour: `related-estimator` cannot go red however bad the numbers look.
            text += f" [{estimator_class}]"
        # Printed, not assumed: compare_maps measures `a - b` and divides by |b|, and `b`
        # is whichever id sorted later until analyze declares an orientation (spec §5.6).
        # The measure is not symmetric, so a table that implied "target minus reference"
        # for every row would invert the sign of half of them. The column says which way
        # round each row was actually computed.
        a, b = pair.get("a"), pair.get("b")
        direction = f"{_short(a)} &minus; {_short(b)}"
        declared = pair.get("reference")
        if declared and declared != b:
            # The numbers are divided by |b| whatever the row declares, so a declared
            # reference on the other side is not a labelling detail: it means this row is
            # measured against the side it did not mean to measure against.
            direction += (f'<br><span class="na">declared reference '
                          f"{_e(_short(declared))}, measured against "
                          f"{_e(_short(b))}</span>")
        diff = _pct(pair.get("rel_median_diff"))
        if pair.get("scale_free"):
            # Every number in this row was computed on median-normalised maps, and the
            # recovered ratio is explicitly not a disagreement (spec §7).
            ratio = pair.get("scale_ratio_not_a_disagreement")
            diff += ('<br><span class="na">normalised'
                     + ("" if ratio is None else f"; scale &times;{ratio:.4g}")
                     + " — not a disagreement</span>")
        # An exclusion nobody can see is indistinguishable from a mask that never had
        # those voxels, and this one is a declared physical range rather than anatomy.
        voxels = _count(pair.get("n"))
        out_of_range = pair.get("n_out_of_range")
        if out_of_range:
            bounds = pair.get("comparison_range")
            voxels += (f'<br><span class="na">{out_of_range:,} outside'
                       + ("" if not bounds else f" [{bounds[0]:g}, {bounds[1]:g}]")
                       + "</span>")
        body.append(
            f"<tr><td>{_e(row['model'])}</td><td>{_e(row['map'])}</td>"
            f"<td>{_e(_short(row['target']))}</td>"
            f'<td class="txt">{direction}</td>'
            f'<td class="txt">{diff}</td>'
            f"<td>{_fmt(pair.get('ccc'), 4)}</td><td>{_fmt(pair.get('pearson_r'), 4)}</td>"
            f'<td class="txt">{voxels}</td>'
            f'<td class="txt"><span style="color:{swatch};font-weight:600">'
            f"&#9679; {_e(label)}</span> — {_e(text)}</td></tr>")
    return (
        '<div class="scroll"><table><caption>Every latest-of-each-software target paired '
        f"with the reference <code>{_e(_short(ref))}</code>. <b>Relative median "
        "difference</b> is the median of the difference named in the <i>Difference</i> "
        "column, over the median absolute value of the <b>second</b> name in it — the "
        "measure is not symmetric, so that column is the only thing that says which way "
        'round a &minus;3% reads. <b>CCC</b> is Lin\'s concordance; the diagnostic row is '
        "a high <i>r</i> beside a low CCC, two softwares that rank voxels identically and "
        "calibrate differently. The flag is the colour those two numbers earned "
        "<i>through</i> the declared comparability class, and its reason is printed "
        "rather than hidden in a tooltip. Voxels are the comparison selection, which is "
        "not the set the published statistics use — see below.</caption>"
        "<tr><th>Model</th><th>Map</th><th>Target</th><th>Difference</th>"
        "<th>Rel. median diff</th><th>CCC</th><th>r</th><th>Voxels</th>"
        "<th>Flag, and why</th></tr>"
        + "".join(body) + "</table></div>")


def _published_n(doc):
    """(target, model, map) -> the voxel count behind the published statistics."""
    return {(r["target"], r["model"], m["name"]): m["stats"].get("n")
            for r in doc["records"] for m in r["maps"]}


def _disclosures(doc, cross, rows, dropped, plotted=()):
    """Spec §7.3, every row, as visible text -- with its numbers generated, not typed.

    Each entry is a decision this benchmark made that changes a published number. A
    reader who does not know about it will misread the page, which is why none of them is
    a tooltip, a code comment or a line in the design document.
    """
    facets = _facets(doc)
    families, states = _coverage_states(doc, cross)
    models = _models(doc)
    published = _published_n(doc)
    items = []

    covered = "; ".join(
        f"<b>{_e(f)}</b> {sum(1 for m in models if states[(m, f)] != 'hole')} of "
        f"{len(models)}" for f in families)
    items.append((
        "Coverage is declared, not broken",
        "Models covered by each family in this run: " + covered + ". A model a family "
        "never declared has no record at all, because omission from its "
        "<code>target.yml</code> is the only way this repo declares a capability gap — "
        "so an empty cell above is a scope decision, and only <i>failed</i> and "
        "<i>missing</i> are things that went wrong."))

    nonfinite = []
    for model in models:
        for map_name in _maps_of(doc, model):
            counts = {r["target"]: m["stats"].get("n_nonfinite")
                      for r in doc["records"] if r["target"] in cross
                      and r["model"] == model for m in r["maps"]
                      if m["name"] == map_name}
            if len({v for v in counts.values() if v is not None}) > 1:
                nonfinite.append(
                    f"{_e(model)} / {_e(map_name)}: "
                    + ", ".join(f"{_e(_short(t))} {v:,}"
                                for t, v in sorted(counts.items()) if v is not None))
    items.append((
        "1/0 = inf on reciprocal maps",
        "Where a software reports a rate and the model declares a time, the harness "
        "inverts it once (<code>transform: reciprocal</code>). A background voxel where "
        "that software wrote R1 = 0 becomes T1 = inf: it drops out of every statistic "
        "and is counted under <i>non-finite</i> instead. Two targets may therefore "
        "legitimately differ in <i>how many</i> voxels are unusable, and that difference "
        "is not a defect."
        + (" Non-finite counts that differ across this set: " + "; ".join(nonfinite) + "."
           if nonfinite else "")))

    quit_targets = [t for t in cross if facets[t][0] == "quit"]
    items.append((
        "QUIT is v3.4, not master",
        "QUIT is pinned to the v3.4 release (2023-11-29). Upstream CI has been red since "
        "2025-03-17, publishes no master binary at all, and a master pin would be a "
        "source build no upstream test has validated in 17 months. It matters for the "
        "numbers: v3.4's <code>qi mtsat</code> uses the small-flip-angle approximation, "
        "which current master made optional, so every claim here is scoped to QUIT v3.4 "
        "and never to QUIT. "
        + (f"In this run: {_e(', '.join(_short(t) for t in quit_targets))}."
           if quit_targets else "No QUIT target has produced records in this run yet.")))

    items.append((
        "Cross-software hashes can never match",
        "<code>voxel_sha256</code> is computed on the values a software produced and is "
        "never scaled, and QUIT writes float32 where qMRLab writes float64 — so a hash "
        "match across families is impossible even for bit-identical mathematics. Read "
        "the equivalence bands and the hash column down one family's column only; across "
        f"the {len(families)} families here ({_e(', '.join(families))}) <i>unique</i> "
        "means nothing."))

    # Grouped per (model, map) rather than per row: the count is a property of the
    # selection, and six rows repeating one pair of numbers reads as six findings.
    excluded = []
    for model in models:
        for map_name in _maps_of(doc, model):
            compared = {r["target"]: r["pair"].get("n") for r in rows
                        if r["model"] == model and r["map"] == map_name
                        and r["pair"].get("n") is not None}
            full = published.get((doc.get("reference"), model, map_name))
            if not compared or full is None:
                continue
            counts = set(compared.values())
            where = f"{_e(model)} / {_e(map_name)}: {full:,} voxels behind the published " \
                    "statistics"
            if len(counts) == 1:
                n = counts.pop()
                if n < full:
                    excluded.append(
                        f"{where}, {n:,} compared, {full - n:,} excluded")
            else:
                excluded.append(where + ", compared on " + ", ".join(
                    f"{n:,} against {_e(_short(t))}"
                    for t, n in sorted(compared.items())))
    items.append((
        "Two masks, and which produced which number",
        "The statistics and hashes on the Data tab use each model's full published mask. "
        "The flags above use the comparison selection: the model's "
        "<code>comparison_mask</code> where it declares one — an Otsu interior mask, "
        "because the near-background region the full mask keeps is where softwares "
        "differ by clipping convention rather than by fit — intersected with the voxels "
        "that are finite in both maps, and with the declared range in the row below. A "
        "mean on the Values tab and a flag above are therefore two different voxel sets."
        + ("<br>" + "; ".join(excluded) + "." if excluded else "")))

    ranges = []
    for model in models:
        for map_name in _maps_of(doc, model):
            bounds, excluded_here = None, {}
            for row in rows:
                if row["model"] != model or row["map"] != map_name:
                    continue
                bounds = row["pair"].get("comparison_range") or bounds
                if row["pair"].get("n_out_of_range"):
                    excluded_here[row["target"]] = row["pair"]["n_out_of_range"]
            if bounds is None:
                continue
            where = f"{_e(model)} / {_e(map_name)} [{bounds[0]:g}, {bounds[1]:g}]"
            ranges.append(where + ": " + (
                ", ".join(f"{n:,} excluded against {_e(_short(t))}"
                          for t, n in sorted(excluded_here.items()))
                if excluded_here else "nothing excluded"))
    items.append((
        "Values outside a declared range are excluded, and counted",
        "A model may declare a <code>comparison_range</code>, and a voxel enters the "
        "comparison only if <b>both</b> sides fall inside it: one implementation's "
        "7.75e15 p.u. MTsat is not comparable to the other's 2.3 whichever side produced "
        "it. That is a claim about physics rather than about anatomy, so the count is "
        "published beside the number it changed — an exclusion nobody can see is "
        "indistinguishable from a mask that never held those voxels."
        + ("<br>" + "; ".join(ranges) + "." if ranges else "")))

    violations = []
    for row in rows:
        if row["pair"].get("input_domain") == "violated":
            violations.append(
                f"{_e(row['model'])} / {_e(row['map'])} vs "
                f"{_e(_short(row['target']))} — "
                f"{_e(row['pair'].get('input_domain_reason') or 'no reason recorded')}")
    items.append((
        "Input-domain violations, named",
        "Where a dataset breaks a tool's own documented input requirements the pair "
        "flags red regardless of its estimator class, because amber means \"expected to "
        "differ\" and would understate a tool being fed data its model cannot represent. "
        "The data is passed unmodified on purpose: repairing it first would report what "
        "the tool does after we fixed its input for it, which is not what a user gets."
        + ("<br>" + "<br>".join(violations)
           if violations else " No pair in this run carries one.")))

    if plotted:
        clipped = sum(s.n_clipped or 0 for _, s in plotted)
        items.append((
            "The scatterplots crop their axes, and count what they cropped",
            "Each plot's axes span the 0.5th to 99.5th percentile of its two maps "
            "together, not their minimum and maximum: one diverged voxel would otherwise "
            "squash the whole cloud into a corner, which is the same leverage failure "
            "that put six spurious red flags on this site. The numbers beside each plot "
            "are computed over every selected voxel, including the "
            f"{clipped:,} the axes of the {len(plotted)} plots leave out — so the crop "
            "changes the picture and never the statistic, and each plot prints how much "
            "of its own selection it is not showing."))

    if dropped:
        items.append((
            "The other five tabs are version history only",
            "Agreement, Values, Timing and Data show qMRLab's release history and "
            "qmrust, so that axis stays readable. "
            f"{_e(', '.join(_short(t) for t in dropped))} "
            + ("appears" if len(dropped) == 1 else "appear")
            + " on this tab only — an absence there is a filter, not a target that did "
            "not run."))

    body = "".join(f'<tr><th>{_e(t)}</th><td class="txt">{b}</td></tr>' for t, b in items)
    return ('<div class="scroll"><table><caption>Every decision below changes a number '
            "published on this site. Spec §7.3 requires each one as visible text, on the "
            "page, beside the number it qualifies — the same reason the "
            '"What did not run" list prints its reasons instead of hiding them in a '
            "tooltip.</caption>"
            "<tr><th>Disclosure</th><th>What it does to the number you are reading</th>"
            f"</tr>{body}</table></div>")


# ------------------------------------------------------- cross-software scatterplots

# One plot is 232 px square. The square is load-bearing rather than decorative: the
# identity line is at 45 degrees only while both axes carry the same range AND the same
# number of pixels, and a reader looking at a diagonal drawn at 40 degrees reads a bias
# the data does not contain.
_PLOT_SIDE = 232

# The faintest a populated bin is ever drawn. A bin holding one voxel must still be
# visible: the sparse halo is where two implementations disagree, so an encoding that
# faded it to nothing would hide the very voxels the plot is drawn to show.
_CELL_FLOOR = 0.14


@dataclasses.dataclass(frozen=True)
class _Scatter:
    """One pair's 2-D density, as analyze.py publishes it, validated once here.

    Sparse: `cells` holds only non-empty bins, as (ix, iy, n) with 0-based indices into a
    `bins` x `bins` grid. `n` is how many voxels entered the histogram and `n_clipped` how
    many were inside the comparison selection but outside the axis range -- excluded from
    the picture and counted, never silently dropped.
    """

    bins: int
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    cells: tuple[tuple[int, int, int], ...]
    n: int | None
    n_clipped: int | None


def _pair_where(row):
    """Where an error in one pair row is, as a reader of results.json would find it."""
    pair = row["pair"]
    return (f"results.json comparisons.{row['model']}.{row['map']}: "
            f"{pair.get('a')} vs {pair.get('b')}")


def _scatter_int(value, where, field, *, minimum=0):
    """One whole-number field of a scatter block, or an error naming file and field.

    An integral float is accepted because a count that has been through a float column on
    its way to JSON arrives as 27417.0, and refusing that would take the whole page down
    over a serialisation detail. A genuinely fractional value is refused: a fractional bin
    index or a fractional voxel count is a bug in the writer, and rounding it here would
    draw the wrong cell in a place that looks entirely right.
    """
    ok = isinstance(value, int) and not isinstance(value, bool)
    if not ok and isinstance(value, float) and math.isfinite(value) and value.is_integer():
        value, ok = int(value), True
    if not ok or value < minimum:
        raise ValueError(f"{where}: scatter.{field} must be a whole number "
                         f">= {minimum}, got {value!r}")
    return value


def _scatter_axis(value, where, field):
    """One [lo, hi] axis range, validated. Bounds are drawn on the page, so they are
    checked here rather than assumed: an inverted or non-finite range would put every
    cell of the plot at a nonsense coordinate and label the axis with it."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{where}: scatter.{field} must be [lo, hi], got {value!r}")
    lo, hi = value
    for name, bound in ((f"{field}[0]", lo), (f"{field}[1]", hi)):
        if (isinstance(bound, bool) or not isinstance(bound, (int, float))
                or not math.isfinite(bound)):
            raise ValueError(
                f"{where}: scatter.{name} must be a finite number, got {bound!r}")
    if hi < lo:
        raise ValueError(f"{where}: scatter.{field} is inverted: [{lo!r}, {hi!r}]")
    return float(lo), float(hi)


def _scatter_of(pair, where):
    """The validated density block for one pair, or None where the pair carries none.

    ABSENT is the normal case and never an error, for _flag_of's first reason: this
    renderer and the analyze-side writer land independently, and a page that rendered only
    once the other half existed would take the site down in between. Same-family pairs and
    every historical version pair are deliberately without one — that data is heavy, and
    the version story is the other five tabs' subject — so "no scatter here" is also what
    a correct, complete run looks like on most rows.

    PRESENT-but-unusable raises, for _flag_of's other reason: a bin index outside the grid
    or an inverted range cannot be drawn without guessing, and the guess would be a
    picture that contradicts the statistics printed beside it. When a picture and a number
    disagree, the picture is what the reader remembers, so it must not be drawn at all.
    """
    scatter = pair.get("scatter")
    if scatter is None:
        return None
    if not isinstance(scatter, dict):
        raise ValueError(
            f"{where}: scatter must be an object, got {type(scatter).__name__}")
    bins = _scatter_int(scatter.get("bins"), where, "bins", minimum=1)
    x_range = _scatter_axis(scatter.get("x_range"), where, "x_range")
    y_range = _scatter_axis(scatter.get("y_range"), where, "y_range")
    raw = scatter.get("cells")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ValueError(
            f"{where}: scatter.cells must be a list, got {type(raw).__name__}")
    cells = []
    for i, cell in enumerate(raw):
        if not isinstance(cell, (list, tuple)) or len(cell) != 3:
            raise ValueError(
                f"{where}: scatter.cells[{i}] must be [ix, iy, n], got {cell!r}")
        ix = _scatter_int(cell[0], where, f"cells[{i}][0]")
        iy = _scatter_int(cell[1], where, f"cells[{i}][1]")
        count = _scatter_int(cell[2], where, f"cells[{i}][2]", minimum=1)
        if ix >= bins or iy >= bins:
            # Clamping an out-of-grid index would put those voxels in a bin they are not
            # in and draw it with total confidence.
            raise ValueError(f"{where}: scatter.cells[{i}] indexes ({ix}, {iy}) outside "
                             f"the {bins}x{bins} grid")
        cells.append((ix, iy, count))
    total, clipped = scatter.get("n"), scatter.get("n_clipped")
    return _Scatter(
        bins=bins, x_range=x_range, y_range=y_range, cells=tuple(cells),
        n=None if total is None else _scatter_int(total, where, "n"),
        n_clipped=None if clipped is None else _scatter_int(clipped, where, "n_clipped"),
    )


def _scatter_rows(doc, rows):
    """(row, density) for every pair this run published a scatter for, in draw order.

    Shared with the tab's summary and with the disclosure under it, for _value_rows'
    reason: a summary that selected its own rows would be free to claim more plots than
    the tab draws, and a headline that contradicts the thing it introduces is worse than
    no headline.
    """
    out = []
    for row in rows:
        scatter = _scatter_of(row["pair"], _pair_where(row))
        if scatter is not None:
            out.append((row, scatter))
    return out


def _cross_family_rows(doc, rows):
    """The rows pairing the reference with a DIFFERENT software family.

    The set that is supposed to carry a scatter. Used only to say how many of them do not:
    a plot missing from a grid of plots reads as a comparison that was never made, and
    this page has a rule about exclusions nobody can see.
    """
    facets = _facets(doc)
    ref = doc.get("reference")
    ref_family = facets.get(ref, ("", ""))[0]
    return [r for r in rows if facets.get(r["target"], ("", ""))[0] != ref_family]


def _canonical_units(doc):
    """(model, map) -> the unit its statistics, and therefore its scatter axes, are in.

    Read from the records' `stats_unit`, because the pair row carries no unit at all:
    analyze converts every map to the model's canonical unit before comparing anything. An
    axis labelled with the unit a software PRODUCED would print 'ms' under numbers that
    are seconds, which is the misreading an unlabelled axis invites and a wrongly labelled
    one guarantees.
    """
    out = {}
    for record in doc["records"]:
        for entry in record["maps"]:
            unit = entry.get("stats_unit") or entry.get("unit")
            if unit:
                out.setdefault((record["model"], entry["name"]), unit)
    return out


def _shared_axis(scatter):
    """The one range BOTH axes get: the union of the two, never one axis each.

    The two ranges are the same percentile cut union-ed across both maps and so are equal
    in practice; union-ing them again here is what guarantees y = x is drawable as the
    exact diagonal of the square whatever arrives. A degenerate range — every selected
    voxel identical — is widened rather than refused, because that is real data and not a
    writer bug, and dividing by a zero span would place every cell at x = nan.
    """
    lo = min(scatter.x_range[0], scatter.y_range[0])
    hi = max(scatter.x_range[1], scatter.y_range[1])
    if hi <= lo:
        pad = abs(lo) * 0.05 or 0.5
        return lo - pad, hi + pad
    return lo, hi


def _scatter_ticks(scatter):
    """(lo, hi, tick values, tick labels) for one plot, from the one shared range.

    Two callers: the pass that measures a single label gutter for the whole tab, and the
    draw itself. They read the same strings for _gutter's reason -- a gutter measured for
    a label other than the one printed clips the one printed.
    """
    lo, hi = _shared_axis(scatter)
    ticks = (lo, lo + (hi - lo) / 2.0, hi)
    return lo, hi, ticks, [f"{v:.4g}" for v in ticks]


def _scatter_svg(scatter, *, left, x_title, y_title, alt):
    """One density plot: identity line, count-weighted cells, both axes labelled.

    `left` is the label gutter, and it is passed in rather than measured here so that
    every plot on the tab is the same size to the pixel. Plots that differ by a few per
    cent because one axis label is a digit longer cannot be compared side by side, which
    is the whole reason they are laid out side by side.
    """
    lo, hi, ticks, labels = _scatter_ticks(scatter)
    span = hi - lo
    side = _PLOT_SIDE
    top, right, bottom = 12, 12, 34
    width, height = left + side + right, top + side + bottom

    def px(value):
        return left + (value - lo) / span * side

    def py(value):
        return top + side - (value - lo) / span * side

    out = [f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
           f'role="img" aria-label="{_e(alt)}">',
           f'<rect class="frame" x="{left}" y="{top}" width="{side}" height="{side}" '
           'rx="3"/>']
    peak = max((n for _, _, n in scatter.cells), default=1)
    x_bin = (scatter.x_range[1] - scatter.x_range[0]) / scatter.bins
    y_bin = (scatter.y_range[1] - scatter.y_range[0]) / scatter.bins
    # Every cell is the same size, because the bins are uniform and both axes are drawn
    # on one range, so the size is computed once and only the corner varies.
    cell_w = max(px(scatter.x_range[0] + x_bin) - px(scatter.x_range[0]), 0.8)
    cell_h = max(py(scatter.y_range[0]) - py(scatter.y_range[0] + y_bin), 0.8)
    steps = {}
    for ix, iy, n in scatter.cells:
        # Square root, and the caption says so. These are density cells and not points, so
        # the count has to be encoded; linear opacity against a core bin holding thousands
        # would render every other bin invisible, i.e. a plot showing its own mode and
        # nothing else. The floor keeps the single-voxel halo drawn.
        opacity = _CELL_FLOOR + (1.0 - _CELL_FLOOR) * math.sqrt(n / peak)
        # Quantised to 1/24 of the range so that cells sharing a shade share one element.
        # A step is well under what the eye resolves, and rounding keeps the encoding
        # monotonic in n -- a denser bin can tie with a lighter one, never overtake it.
        corner = (f"M{px(scatter.x_range[0] + ix * x_bin):.1f} "
                  f"{py(scatter.y_range[0] + (iy + 1) * y_bin):.1f}")
        steps.setdefault(round(opacity * 24) / 24.0, []).append(corner)
    # One path per shade rather than one rect per cell. A cell costs ~25 bytes of path
    # data against ~105 as its own element: across the 36 plots the published run draws,
    # of some 460 cells each, that is a megabyte on a page every visitor fetches and
    # 16,000 SVG nodes for a phone to lay out. Sorted, so the file is diffable.
    for opacity, corners in sorted(steps.items()):
        path = "".join(f"{c}h{cell_w:.1f}v{cell_h:.1f}h-{cell_w:.1f}z" for c in corners)
        out.append(f'<path class="cells" fill="var(--s1)" '
                   f'fill-opacity="{opacity:.3f}" d="{path}"/>')
    # Corner to corner, which IS the line y = x — but only because both axes were given
    # one range above and the plot area is square. Both are enforced, neither is a
    # coincidence, and the line is the whole argument: agreement is the diagonal.
    out.append(f'<path class="idl" d="M{left} {top + side}L{left + side} {top}"/>')
    out.append(f'<text x="{left + 6}" y="{top + 12}" text-anchor="start" '
               'style="font-size:9px">y = x</text>')
    for value, text, anchor in zip(ticks, labels, ("start", "middle", "end")):
        out.append(f'<text x="{px(value):.1f}" y="{top + side + 13}" '
                   f'text-anchor="{anchor}" style="font-size:10px">{_e(text)}</text>')
        out.append(f'<text x="{left - 5}" y="{py(value) + 3:.1f}" text-anchor="end" '
                   f'style="font-size:10px">{_e(text)}</text>')
    # Both axes name the map AND its unit. An unlabelled quantitative axis is how a reader
    # mistakes seconds for milliseconds, and these two axes hold different softwares.
    out.append(f'<text x="{width / 2:.1f}" y="{height - 6}" text-anchor="middle" '
               f'style="font-size:10px">{_e(x_title)}</text>')
    out.append(f'<text transform="translate(11,{top + side / 2:.1f}) rotate(-90)" '
               f'text-anchor="middle" style="font-size:10px">{_e(y_title)}</text>')
    out.append("</svg>")
    return "".join(out)


def _scatters(doc, rows, plotted):
    """The scatterplots: a model dropdown, then every (map x software) plot inside it.

    Returns "" when the run published no density at all, rather than a heading over an
    apology. analyze writes the scatter and this renderer landed separately, and an empty
    section on the live site would be one half of the work announcing the other half's
    absence to every visitor. Pairs that are missing a plot while their neighbours have
    one are named instead, because a gap in a grid of plots otherwise reads as a
    comparison nobody made.

    The dropdown is the page's existing control: a `<select data-controls=...>` over
    `data-group`/`data-key` panes, toggled by the same six lines of inline JS that already
    drive the Agreement and Values tabs. A second mechanism for the same job is a second
    thing to keep working.
    """
    if not plotted:
        return ""
    units = _canonical_units(doc)
    ref = doc.get("reference")
    # One gutter for every plot on the tab, measured over every label any of them draws:
    # the tick numbers are drawn 5 px inside it and the rotated axis title takes its first
    # ~14 px, so the margin has to clear both, and a per-plot gutter would leave the plots
    # a few pixels apart in size for no reason a reader could see.
    gutter = max(_gutter(_scatter_ticks(sc)[3], size=10, margin=20) for _, sc in plotted)
    groups = {}
    for row, scatter in plotted:
        pair = row["pair"]
        model, map_name = row["model"], row["map"]
        # Falls back rather than raising: a map no record declared a unit for is a
        # different bug on a different tab, and it must not cost the page its plots.
        unit = units.get((model, map_name)) or "unit not recorded"
        if pair.get("scale_free"):
            # Spec §7: both maps were divided by their own masked median before anything
            # was measured, so these axes are multiples of a median and emphatically not
            # 'au'. Printing the raw unit here would be the same class of error as
            # labelling seconds as milliseconds.
            unit = "× own masked median"
        colour, _reason, _estimator = _flag_of(pair, _pair_where(row))
        # The colour never travels alone: it ships beside the word it stands for, here and
        # in every legend on this page.
        swatch = _FLAG_COLOUR.get(colour, "var(--ink3)")
        # x is the REFERENCE and y is the other software, per the data contract, so every
        # plot on the tab is read the same way round: "what does this software do to
        # qMRLab's number". Nothing in the row states the orientation -- the axes are the
        # contract's, and the writer builds the histogram from (a, b) in that order, which
        # is the same thing only while the reference id sorts first in the pair. It does
        # for every family here (qmrust, quit, sct all sort after qmrlab); a family whose
        # id sorted BEFORE it would transpose every one of its plots against these labels,
        # silently. If that day comes the orientation belongs in the row, as a field.
        x_title = (f"{map_name} ({unit}) — reference {_short(ref)}" if ref
                   else f"{map_name} ({unit})")
        y_title = f"{map_name} ({unit}) — {_short(row['target'])}"
        parts = [
            f'<h3>{_e(map_name)} · {_e(_short(row["target"]))}</h3>',
            _scatter_svg(scatter, left=gutter, x_title=x_title, y_title=y_title,
                         alt=f"{model} / {map_name}: {_short(ref)} on x against "
                             f"{_short(row['target'])} on y, voxel density"),
            # The flag and the two numbers it was earned from, beside the picture: read
            # apart, a cloud that looks tight and a CCC of 0.71 are two different stories.
            f'<p><i style="background:{swatch}"></i><b>{_e(colour or "not classified")}'
            f'</b> · rel. median diff {_pct(pair.get("rel_median_diff"))} · CCC '
            f'{_fmt(pair.get("ccc"), 4)}</p>',
            # A cloud that silently dropped its tail is a lie of omission.
            f'<p>{_count(scatter.n)} voxels drawn · {_count(scatter.n_clipped)} outside '
            'the axes</p>',
        ]
        if pair.get("scale_free"):
            parts.append("<p>Axes are multiples of each map's own masked median, not raw "
                         "values.</p>")
        groups.setdefault(model, []).append(
            f'<figure class="plot">{"".join(parts)}</figure>')

    models = [m for m in _models(doc) if m in groups]
    options = "".join(f'<option value="{_e(m)}">{_e(m)}</option>' for m in models)
    panes = "".join(
        f'<div data-group="scat" data-key="{_e(m)}" hidden><div class="plots">'
        + "".join(groups[m]) + "</div></div>" for m in models)

    sizes = sorted({s.bins for _, s in plotted})
    grid = f"{sizes[0]}&times;{sizes[0]}" if len(sizes) == 1 else "square"
    drawn = {(row["model"], row["map"], row["target"]) for row, _ in plotted}
    absent = [r for r in _cross_family_rows(doc, rows)
              if (r["model"], r["map"], r["target"]) not in drawn]
    caption = (
        "<b>Agreement is the dashed diagonal.</b> Each plot bins its pair's voxels into a "
        f"{grid} grid and draws one cell per non-empty bin, so a cell is a density and not "
        "a voxel: <b>opacity rises with the square root of the voxel count in the cell</b>,"
        " from the faintest single-voxel bin to the opaque core. Both axes carry the same "
        "range — the 0.5th to 99.5th percentile of the two maps together, so that one "
        "diverged voxel cannot squash the cloud into a corner — which is what puts the "
        "identity line at 45°. Voxels outside that range are excluded from the picture and "
        "counted under each plot. The voxels drawn are the ones the row above was measured "
        "on: same mask, same finite filter, same declared range.")
    if absent:
        caption += (" Not plotted: "
                    + _e("; ".join(f"{r['model']} / {r['map']} vs {_short(r['target'])}"
                                   for r in absent))
                    + " — measured above, but this run published no density for them.")
    return ('<h2 style="font-size:1rem;margin:.4rem 0 .3rem">Voxel by voxel, against the '
            "reference</h2>"
            '<div class="ctl"><label>Model <select data-controls="scat">' + options
            + "</select></label></div>"
            f'<p class="sub" style="max-width:84ch">{caption}</p>' + panes)


def _cross_software(doc, dropped):
    cross = _latest_of_each_software(doc)
    ref = doc.get("reference")
    if ref and ref not in cross and any(r["target"] == ref for r in doc["records"]):
        # The reference is the denominator of every row below, so it belongs on the tab
        # even where it is not its family's current stream -- otherwise the table names a
        # target the page never shows.
        cross = _ordered(set(cross) | {ref})
    rows = _cross_rows(doc, cross)
    # Validated once and passed on: the lede counts the plots, the plots are drawn from
    # it, and the disclosure adds up what they clipped. Three readers of one list, for
    # _value_rows' reason -- a second selection could disagree with the first.
    plotted = _scatter_rows(doc, rows)
    return (
        # The paragraph that used to open this tab said what the lede's first two
        # sentences say, and said it after the reader had already scrolled past nothing:
        # two paragraphs making the same point is what "impossible to parse" is made of.
        _lede_cross(doc, cross, rows, plotted)
        + '<h2 style="font-size:1rem;margin:.4rem 0 .3rem">Coverage, and holes</h2>'
        + _coverage(doc, cross)
        + '<h2 style="font-size:1rem;margin:.4rem 0 .3rem">Agreement with the reference'
          "</h2>"
        + _cross_pairs(doc, cross, rows)
        # The pictures directly under the numbers they belong to, so a reader meets both
        # in one place; the plots carry their pair's flag, difference and CCC for the same
        # reason. "" until a run publishes density data, so nothing announces its absence.
        + _scatters(doc, rows, plotted)
        + '<h2 style="font-size:1rem;margin:.4rem 0 .3rem">What this page decided for you'
          "</h2>"
        + _disclosures(doc, cross, rows, dropped, plotted)
        + '<h2 style="font-size:1rem;margin:.4rem 0 .3rem">Masked statistics</h2>'
        + '<div class="scroll"><table><caption>The same statistics the Data tab '
          "publishes, for these targets. Each is computed on its model's full mask, "
          "which is not the selection the flags above use.</caption>"
        + _STATS_HEAD
        + "".join(_stats_rows([r for r in doc["records"] if r["target"] in cross]))
        + "</table></div>")


# ---------------------------------------------------------------- tab summaries

# Every tab used to open straight into a dense matrix or a wide table, with the
# explanation absent or buried in a caption, so a reader had to reverse-engineer what
# they were looking at before they could read it. Each tab now opens with a lede: the
# question it answers, the figures that answer it today, and the misreading it invites.
#
# The six live together rather than beside the charts they introduce because they have
# to read as one voice; six blocks written months apart beside six different charts is
# how a page ends up explaining the same word two ways.
#
# Every figure below is COUNTED from the document being rendered -- the narrowed history
# doc for the five version tabs, the whole run for the cross-software tab -- and several
# of them are counted by the same helper that draws the thing they describe. A
# transcribed number is the one failure that matters here: a summary claiming seventy
# pairs agree above a table showing forty-three is worse than no summary, and this page
# is published.


def _lede(paragraphs, figures):
    """One tab's orientation block: the question, then the figures, then the catch.

    The order is fixed here rather than left to each caller. The first paragraph is the
    question the tab answers; the figures follow it; everything after them is what to
    read first and what readers get wrong. A tab that opened with its caveat, or that put
    its numbers last, is back to being a chart the reader has to decode before reading,
    which is the complaint this block exists to answer.

    `paragraphs` carry markup their callers build, and every value interpolated into one
    is escaped there. `figures` are (value, label, colour-or-None); a colour is a status
    swatch and always ships beside its own label, never as colour alone.
    """
    cells = []
    for value, label, colour in figures:
        swatch = "" if colour is None else f'<i style="background:{colour}"></i>'
        cells.append(f"<span>{swatch}<b>{_e(value)}</b> {_e(label)}</span>")
    rest = "".join(f"<p>{p}</p>" for p in paragraphs[1:])
    return ('<div class="lede">'
            f"<p>{paragraphs[0]}</p>"
            f'<p class="figs">{"".join(cells)}</p>'
            f"{rest}</div>")


def _lede_overview(history, dropped):
    """Counted over the grid the tab actually draws, which is `history`, not the run.

    The whole run is what the tiles under this block count, and the two disagree whenever
    a family is filtered out -- so the last paragraph says which is which. A summary that
    quietly counted 15 targets above five tiles counting 17 would be the second number on
    this page a reader has no way to check.
    """
    targets = {r["target"] for r in history["records"]}
    models = _models(history)
    declared = {(r["target"], r["model"]) for r in history["records"]}
    ran = sum(1 for r in history["records"] if r["status"] == "ok")
    failed = sum(1 for r in history["records"] if r["status"] == "failed")
    gone = sum(1 for r in history["records"] if r["status"] == "missing")
    holes = len(targets) * len(models) - len(declared)

    figures = [(f"{len(targets)} × {len(models)}", "targets × models", None),
               (f"{ran:,}", "produced maps", None),
               (f"{failed:,}", "failed", None)]
    if gone:
        figures.append((f"{gone:,}", "never came back", None))
    figures.append((f"{holes:,}", "not applicable", None))

    paragraphs = [
        "Did every fit this benchmark declares actually run? The grid below is one "
        "target per row, one model per column, and one fit per cell.",
        "Every cell that is not a tick prints its reason in <i>What did not run</i>, "
        "under the grid, rather than in a tooltip — read that list first."
        if failed or gone else
        "Nothing failed in this view, so the grid is ticks and declared holes only.",
        "The most common misreading is the muted <i>not applicable</i> cells. A target "
        "declares the models it supports in its <code>target.yml</code>, and omission is "
        "the only way this repo declares a gap, so those cells are a scope decision and "
        "not a fit that broke.",
    ]
    if dropped:
        paragraphs.append(
            "The tiles that follow count the whole run; the grid under them is version "
            "history only, which is why it holds fewer targets. The note between them "
            "names what that leaves out.")
    return _lede(paragraphs, figures)


def _lede_cross(doc, cross, rows, plotted=()):
    families, states = _coverage_states(doc, cross)
    models = _models(doc)
    holes = sum(1 for m in models for f in families if states[(m, f)] == "hole")
    counts = {}
    for row in rows:
        pair = row["pair"]
        where = f"{row['model']}/{row['map']} {pair.get('a')} vs {pair.get('b')}"
        colour = _flag_of(pair, where)[0]
        counts[colour] = counts.get(colour, 0) + 1

    figures = [
        (f"{len(families):,}", "software families", None),
        (f"{len(models):,}", "models", None),
        (f"{len(rows):,}", "comparisons", None),
        (f"{counts.get('green', 0):,}", "agree within tolerance", "var(--good)"),
        (f"{counts.get('amber', 0):,}", "differ for a declared reason", "var(--warn)"),
        (f"{counts.get('red', 0):,}", "flagged", "var(--crit)"),
    ]
    if counts.get(None):
        # An unclassified pair is not a passing one, so it is never folded into green.
        figures.append((f"{counts[None]:,}", "not classified", None))
    if plotted:
        figures.append((f"{len(plotted):,}", "scatterplots", None))

    ref = doc.get("reference")
    opening = "Do independent implementations of the same model agree today?"
    if rows and ref:
        opening += (" Each row below pairs the current version of one software with the "
                    f"reference <code>{_e(_short(ref))}</code>, on one map.")
    opening += (" How qMRLab itself changed over time is the other five tabs' subject, "
                "not this one.")

    second = "Read the coverage table first: it says which family attempts which "
    second += (f"model at all, and its {holes} <i>declared hole</i> cells are gaps a "
               "family declared by leaving that model out of its "
               "<code>target.yml</code>, not runs that broke." if holes else
               "model at all. Every family here declares every model, so nothing "
               "on it is a hole.")
    if cross:
        second += (" Compared today: "
                   + _e(", ".join(_short(t) for t in _ordered(cross))) + ".")

    plots = ""
    if plotted:
        maps = len({(row["model"], row["map"]) for row, _ in plotted})
        plots = (
            "Under that table the same comparisons are drawn: one scatterplot per map and "
            f"per software — {len(plotted)} of them across {maps} "
            + ("map" if maps == 1 else "maps")
            + ", the model chosen with the dropdown — with the reference on the "
            "horizontal axis and the other software on the vertical one. Agreement is the "
            "dashed diagonal: a cloud sitting parallel to it is a calibration offset, "
            "which is the disagreement a correlation alone cannot show, and one that fans "
            "out around it is noise.")

    third = ("The most common misreading is amber. It means the two implementations were "
             "never expected to produce the same number — a different estimator, a "
             "different convention, a different unit — and not that one of them nearly "
             "failed. Red is the colour to read as a finding.")
    return _lede([opening, second] + ([plots] if plots else []) + [third], figures)


def _lede_agree(doc):
    equivalence = doc.get("equivalence", {})
    identical = 0
    charts = 0
    for by_map in equivalence.values():
        for classes in by_map.values():
            if not classes:
                continue
            charts += 1
            for group in classes.values():
                # Pairs, not classes: "301 pairs are byte-identical" is a claim about the
                # matrix under the bands, where a reader counts pairs and not hashes.
                identical += len(group) * (len(group) - 1) // 2
    pairs = sum(len(ps) for by_map in doc.get("comparisons", {}).values()
                for ps in by_map.values())
    targets = {r["target"] for r in doc["records"]}

    figures = [(f"{len(targets):,}", "targets", None),
               (f"{charts:,}", "maps", None),
               (f"{pairs:,}", "pairs measured", None),
               (f"{identical:,}", "pairs byte-identical", None)]

    if not charts and not pairs:
        # A summary that promised bands and a matrix over an empty tab would be the
        # orientation block causing the confusion it exists to remove.
        return _lede([
            "Which of these versions produced exactly the same map, and how far apart "
            "are the ones that did not? Nothing in this view was compared, so there is "
            "nothing here to read.",
            "Both the bands and the matrix come from the analyze step, which recorded "
            "no equivalence class and no pair for these targets.",
            "The most common misreading is an empty tab read as disagreement. No two "
            "maps were compared at all.",
        ], figures)

    iterative = [m for m in _models(doc) if m in ITERATIVE]
    catch = ("The most common misreading is reading a colour change as a change in "
             "qMRLab. "
             + ("The one iterative fit here (" if len(iterative) == 1
                else "The iterative fits here (")
             + _e(", ".join(iterative)) + ") "
             + ("shifts" if len(iterative) == 1 else "shift")
             + " their converged optimum by around 1e-7 between MATLAB builds, and "
             "<code>master</code> tracks the latest release while the tags are pinned. "
             "Check the MATLAB column on the Timing tab before concluding the software "
             "changed." if iterative else
             "The most common misreading is reading <i>unique</i> as far away. It means "
             "only that no other version produced these exact bytes; the matrix below is "
             "where you find out how far apart they actually are.")
    return _lede([
        "Which of these versions produced exactly the same map, and how far apart are "
        "the ones that did not? The bands are hash identity: two cells share a colour "
        "when their maps are byte-identical, and the colour marks that sharing rather "
        "than naming which class it is.",
        "Byte-identical is exact — one voxel differing in its last bit makes both maps "
        "unique — so read the bands for what is shared at all, then the matrix below, "
        "which shades every pair by the fraction of voxels agreeing within 1%.",
        catch,
    ], figures)


def _lede_values(doc):
    charts = _value_rows(doc)
    rows = sum(len(r) for _, _, r in charts)
    skewed = sum(1 for _, _, r in charts for _t, s, _u in r if _skewed(s))
    units = {unit for _, _, r in charts for _t, _s, unit in r}

    figures = [(f"{len(charts):,}", "maps", None),
               (f"{rows:,}", "target rows", None),
               (f"{len(units):,}", "units", None),
               (f"{skewed:,}", "rows skewed", None)]

    if not charts:
        return _lede([
            "What values did each version actually produce? No map in this view "
            "published the quantiles these charts are drawn from, so there is nothing "
            "to chart.",
            "A row appears here only for a fit that succeeded and stored a median. The "
            "Overview tab is where the fits that did not are listed.",
            "The most common misreading is an empty tab read as a run with no output. "
            "What is absent here is the stored summary statistics, not necessarily the "
            "maps themselves.",
        ], figures)

    catch = (f"The most common misreading is the mean. On {skewed} "
             + ("row" if skewed == 1 else "rows")
             + " here a handful of extreme voxels drags it orders of magnitude from the "
             "median; those rows are marked <i>skewed</i>, and the median is the figure "
             "to read." if skewed else
             "The most common misreading is a wide box read as disagreement. It is the "
             "spread of voxels inside one map, which is anatomy, not the spread between "
             "versions.")
    return _lede([
        "What values did each version actually produce? One chart per model and map: the "
        "box spans p05 to p95, the dot is the median, and the unit is that model's "
        "canonical one.",
        "Compare down a chart, never across two. Each chart is scaled to its own map's "
        "range, so two of them share an axis only by coincidence.",
        catch,
    ], figures)


def _lede_timing(doc):
    rows = _timing_rows(doc)
    if not rows:
        return _lede([
            "How long did each fit take on the runner that ran it? No fit in this view "
            "recorded a time, so there is nothing to chart.",
            "A fit records a time only when it succeeded, so read the Overview tab "
            "first: an empty chart here is that tab's failures, seen from the other end.",
            "The most common misreading is an empty chart read as a run that took no "
            "time. Nothing here was measured, which is a different fact.",
        ], [("0", "fits timed", None)])

    fast = min(rows, key=lambda r: r[2])
    slow = max(rows, key=lambda r: r[2])
    releases = sorted({rel for _m, _t, _v, rel in rows if rel != "—"})
    figures = [(f"{len(rows):,}", "fits timed", None),
               (f"{fast[2]:.3g} s", "fastest", None),
               (f"{slow[2]:.3g} s", "slowest", None)]
    if releases:
        figures.append((f"{len(releases):,}", "MATLAB builds", None))

    return _lede([
        "How long did each fit take on the runner that ran it? One bar per model and "
        "target, the median of that cell's repeats, on a logarithmic axis.",
        f"The fastest is {_e(fast[0])} on {_e(_short(fast[1]))} at {fast[2]:.3g} s; the "
        f"slowest is {_e(slow[0])} on {_e(_short(slow[1]))} at {slow[2]:.3g} s. The axis "
        "is logarithmic because of that spread, so a bar twice as long is not twice the "
        "time.",
        "The most common misreading is a version-to-version difference read as a "
        "speed-up. These are shared runners with few repeats, and the MATLAB build "
        "changes down the axis. The note below is the harder limit: the MATLAB and Rust "
        "lanes do not time the same thing at all.",
    ], figures)


def _lede_data(doc):
    records = doc["records"]
    rows = sum(len(r["maps"]) for r in records)
    targets = {r["target"] for r in records}
    units = {m["stats_unit"] for r in records for m in r["maps"]}
    figures = [(f"{rows:,}", "statistic rows", None),
               (f"{len(targets):,}", "targets", None),
               (f"{len(_models(doc)):,}", "models", None),
               (f"{len(units):,}", "units", None)]
    return _lede([
        "What is every chart on this page drawn from? These two tables: the statistic "
        "behind each mark, and the provenance of the run that produced it.",
        "This is the accessible fallback for the charts — whatever a chart encodes as "
        "colour or length is here as text — and the two links below are the same data, "
        "machine-readable.",
        "The most common misreading is the hash column. <code>voxel_sha256</code> is "
        "taken over the values a software produced, in the unit and the float width it "
        "produced them, so two rows that differ in nothing else can still never share a "
        "hash. Read it down one family's rows and no further.",
    ], figures)


# ---------------------------------------------------------------- page

def render(doc: dict) -> str:
    ref = doc.get("reference")
    # A target present only as a `missing` record produced nothing, so naming it as the
    # reference would promise a comparison the page cannot show.
    has_ref = any(r["target"] == ref and r["status"] != "missing" for r in doc["records"])
    # The version-history tabs read one family's releases left to right, and a family
    # that pins a single version has no history to read: putting SCT's one target on that
    # axis says nothing and stretches every chart to fit it (spec §8). They get the
    # narrowed doc; the tiles and the cross-software tab keep the whole run, so no target
    # is countable on one tab and absent from the site.
    history, dropped = _history(doc)
    filtered = ("" if not dropped else
                '<p class="sub" style="margin:.1rem 0 .8rem">Version history: qMRLab '
                "releases and qmrust. "
                f"{_e(', '.join(_short(t) for t in dropped))} "
                + ("is" if len(dropped) == 1 else "are")
                + " on the Cross-software tab, and so is anything of theirs that failed."
                "</p>")
    # Second, not sixth by position: the coverage table is the first thing a reader needs
    # in order to read anything else here correctly.
    tabs = [("overview", "Overview"), ("cross", "Cross-software"), ("agree", "Agreement"),
            ("values", "Values"), ("timing", "Timing"), ("data", "Data")]
    nav = "".join(
        f'<button data-tab="{k}" aria-selected="{"true" if i == 0 else "false"}">{_e(l)}</button>'
        for i, (k, l) in enumerate(tabs))
    # Each lede is built from the doc its own tab renders: `history` for the five
    # version tabs, whose charts never show the families it drops, and the whole run for
    # the cross-software tab and the tiles, which do. Handing every lede `doc` would
    # publish a summary counting targets its own tab does not draw.
    panes = {
        "overview": (_lede_overview(history, dropped) + _tiles(doc) + filtered
                     + _status_matrix(history)),
        "cross": _cross_software(doc, dropped),
        "agree": (_lede_agree(history) + filtered + _bands(history)
                  + "<h2>Pairwise agreement</h2>" + _matrices(history)),
        "values": _lede_values(history) + filtered + _ranges(history),
        "timing": _lede_timing(history) + filtered + _timing(history),
        "data": _lede_data(history) + filtered + _tables(history),
    }
    body = "".join(
        f'<section data-pane="{k}"{"" if i == 0 else " hidden"}>{panes[k]}</section>'
        for i, (k, _) in enumerate(tabs))
    # Counted, not spelled out: "Eight qMRI models" was already one model out of date when
    # qmt_spgr_ramani landed, and a subtitle nobody recomputes is a number nobody trusts.
    families = _families(doc, {r["target"] for r in doc["records"]})
    subtitle = (f"{len(_models(doc))} qMRI models fitted against identical, "
                "checksum-pinned data across "
                f"{len({r['target'] for r in doc['records']})} targets from "
                f"{len(families)} software families ({_e(', '.join(families))}).")
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
