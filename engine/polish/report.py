"""The readable HTML of a polish report: a timeline strip, the worst moments with pictures, scores per beat."""
from __future__ import annotations

import html
import json

from .explain import LABELS, WHAT

METRICS = ("pops", "softness", "halos", "drift", "morphs")


def _t(x: float) -> str:
    m, s = divmod(max(0.0, x), 60)
    return f"{int(m)}:{s:04.1f}"


def _heat(sev: float) -> str:
    """Fill for a severity: green (fine) through amber to red."""
    sev = max(0.0, min(1.0, sev))
    hue = 145 - 140 * sev
    return f"hsl({hue:.0f} 70% {48 - 8 * sev:.0f}%)"


def _score_cell(score: int) -> str:
    sev = 1 - score / 100
    cls = "ok" if score >= 75 else "warn" if score >= 50 else "bad"
    return f'<td class="sc {cls}" style="--h:{_heat(sev)}"><b>{score}</b></td>'


CSS = """
:root{--bg:#f7f6f2;--fg:#1b1a17;--mute:#6d6a62;--card:#fff;--line:#e3e0d6;--cell:#e9e6dc;--accent:#2b5fd9;
--ok:#1f8a5b;--slight:#b58a00;--visible:#d4691a;--bad:#c4281c}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--mute:#9a978d;--card:#1d1d1b;--line:#33322e;--cell:#2a2927;--accent:#7ea3ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}h2{font-size:18px;margin:36px 0 12px}
.sub{color:var(--mute);margin:0 0 18px}
.chip{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600;color:#fff;vertical-align:middle}
.chip.clean{background:var(--ok)}.chip.slight{background:var(--slight)}.chip.visible{background:var(--visible)}.chip.bad{background:var(--bad)}
.strip{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 12px 6px;overflow-x:auto}
.strip svg{display:block;width:100%;min-width:760px;height:auto}
.strip text{fill:var(--mute);font:11px system-ui,sans-serif}.strip .lab{fill:var(--fg);font-weight:600}
.legend{display:flex;gap:14px;align-items:center;color:var(--mute);font-size:12px;margin:8px 2px 0}
.legend i{display:inline-block;width:46px;height:8px;border-radius:4px;background:linear-gradient(90deg,hsl(145 70% 48%),hsl(75 70% 46%),hsl(5 70% 40%))}
.grid{display:grid;grid-template-columns:1fr;gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;scroll-margin-top:16px}
.card:target{outline:2px solid var(--accent)}
.card img{display:block;max-width:100%;height:auto;background:#000;margin:0 auto}
.card .noimg{height:90px;display:flex;align-items:center;justify-content:center;color:var(--mute);background:var(--cell);font-size:13px}
.card .b{padding:12px 14px 14px}.card .h{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
.card .h .t{font-variant-numeric:tabular-nums;font-weight:600}.card .h .bt{color:var(--mute)}
.card p{margin:4px 0}.card .fix{color:var(--mute);font-size:13px}.card .fix b{color:var(--fg)}
.bar{height:5px;border-radius:3px;background:var(--cell);margin:8px 0 2px;overflow:hidden}.bar i{display:block;height:100%}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:14px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.04em;font-weight:600}
tr:last-child td{border-bottom:0}td.sc{text-align:center;width:78px;background:color-mix(in srgb,var(--h) 22%,var(--card))}
td.sc b{font-variant-numeric:tabular-nums}.mute{color:var(--mute)}.mono{font-variant-numeric:tabular-nums}
details{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-top:10px}
summary{cursor:pointer;font-weight:600}dl{margin:10px 0 2px}dt{font-weight:600;margin-top:10px}dd{margin:2px 0 0;color:var(--mute)}
.none{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:22px;color:var(--mute)}
@media (max-width:640px){main{padding:18px 14px 60px}}
"""


def _strip(r: dict) -> str:
    dur = r["film"]["seconds"]
    step = r["timeline"]["step"]
    X0, W = 96.0, 1000.0
    k = W / max(dur, 0.1)
    rowh, top = 20, 34
    H = top + rowh * len(METRICS) + 26
    out = [f'<svg viewBox="0 0 {X0 + W + 10:.0f} {H}" role="img" aria-label="Timeline of problems by second">']
    # beats on top
    for i, b in enumerate(r["beats"]):
        x, w = X0 + b["start"] * k, (b["end"] - b["start"]) * k
        out.append(f'<rect x="{x:.1f}" y="6" width="{w:.1f}" height="20" rx="4" fill="var(--cell)" stroke="var(--line)"/>')
        if w > 40:
            out.append(f'<text x="{x + 6:.1f}" y="20" class="lab">{html.escape(b["id"])}</text>')
        if i:
            out.append(f'<rect x="{x:.1f}" y="{top - 4}" width="{r["fade"] * k:.1f}" height="{rowh * len(METRICS) + 4}" fill="var(--accent)" opacity=".10"/>')
    for j, m in enumerate(METRICS):
        y = top + j * rowh
        out.append(f'<text x="{X0 - 8}" y="{y + 14}" text-anchor="end" class="lab">{LABELS[m]}</text>')
        out.append(f'<rect x="{X0}" y="{y + 2}" width="{W}" height="{rowh - 4}" rx="3" fill="var(--cell)"/>')
        for bi, sev in enumerate(r["timeline"][m]):
            if sev < 0.15:
                continue
            x = X0 + bi * step * k
            out.append(f'<rect x="{x:.1f}" y="{y + 2}" width="{max(step * k, 1.2):.1f}" height="{rowh - 4}" fill="{_heat(sev)}">'
                       f'<title>{LABELS[m]} {_t(bi * step)}: {sev:.2f}</title></rect>')
    for n, x_ in enumerate(r["issues"]):
        j = METRICS.index(x_["metric"])
        y = top + j * rowh
        x, w = X0 + x_["t0"] * k, max((x_["t1"] - x_["t0"]) * k, 4)
        out.append(f'<a href="#i{n}"><rect x="{x:.1f}" y="{y + 1}" width="{w:.1f}" height="{rowh - 2}" rx="3" fill="none" '
                   f'stroke="var(--fg)" stroke-width="1.2" opacity=".55"><title>{html.escape(x_["reason"])}</title></rect></a>')
    ay = top + rowh * len(METRICS) + 14
    for s in range(0, int(dur) + 1, 1 if dur <= 40 else 5):
        out.append(f'<text x="{X0 + s * k:.1f}" y="{ay}" text-anchor="middle">{s}s</text>')
    out.append("</svg>")
    return "".join(out)


def _card(n: int, x: dict) -> str:
    img = (f'<a href="{html.escape(x["thumb"])}"><img src="{html.escape(x["thumb"])}" loading="lazy" alt="{html.escape(LABELS[x["metric"]])} at {_t(x["t"])}"></a>'
           if x.get("thumb") else '<div class="noimg">no picture</div>')
    return (f'<article class="card" id="i{n}">{img}<div class="b"><div class="h">'
            f'<span class="chip {x["level"]}">{html.escape(LABELS[x["metric"]])}</span>'
            f'<span class="t">{_t(x["t0"])} to {_t(x["t1"])}</span><span class="bt">beat {html.escape(x["beat"])}</span></div>'
            f'<div class="bar"><i style="width:{x["severity"] * 100:.0f}%;background:{_heat(x["severity"])}"></i></div>'
            f'<p>{html.escape(x["reason"])}</p><p class="fix"><b>Try:</b> {html.escape(x["hint"])}</p></div></article>')


def render_html(r: dict) -> str:
    s = r["summary"]
    c = s["counts"]
    name = html.escape(r.get("section") or r["name"])
    worst = s["worst"]
    lines = [f'<h1>Polish report: {name}</h1>',
             f'<p class="sub"><span class="chip {s["verdict"]}">{s["verdict"]}</span> &nbsp;'
             f'{s["issues"]} problem{"s" if s["issues"] != 1 else ""} found'
             + (f' ({c["bad"]} bad, {c["visible"]} visible, {c["slight"]} slight)' if s["issues"] else "")
             + f' &middot; film {r["film"]["seconds"]:.1f} s, {r["film"]["fps"]:g} fps, {r["film"]["size"][0]}x{r["film"]["size"][1]}'
             f' &middot; {html.escape(r["generated"])} &middot; <a href="{name}.json">json</a></p>']
    lines.append('<h2>Second by second</h2><div class="strip">' + _strip(r) + '</div>'
                 '<div class="legend"><i></i> fine to clearly visible &nbsp;&middot;&nbsp; outlined = a problem below (click) '
                 '&nbsp;&middot;&nbsp; shaded columns = crossfades</div>')
    lines.append('<h2>Worst moments</h2>')
    if r["issues"]:
        lines.append('<div class="grid">' + "".join(_card(n, x) for n, x in enumerate(r["issues"])) + '</div>')
    else:
        lines.append('<div class="none">Nothing here reaches the threshold: no pops, softness, halos, drift or morphs a viewer would '
                     'notice. The timeline above still shows the small stuff.</div>')
    # per-beat table
    th = "".join(f"<th>{LABELS[m]}</th>" for m in METRICS)
    rows = []
    for b in r["beats"]:
        w = b.get("worst")
        wt = (f'<span class="chip {w["level"]}">{html.escape(LABELS[w["metric"]])}</span> {html.escape(w["reason"])}' if w
              else '<span class="mute">nothing found</span>')
        rows.append(f'<tr><td><b>{html.escape(b["id"])}</b><div class="mute mono">{_t(b["start"])} to {_t(b["end"])}'
                    f'{" &middot; frozen moment" if b["kind"] == "freeze" else ""}</div></td>'
                    + "".join(_score_cell(b["scores"][m]) for m in METRICS) + f'<td>{wt}</td></tr>')
    lines.append(f'<h2>Beat by beat</h2><table><thead><tr><th>Beat</th>{th}<th>Worst</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
                 '<p class="mute" style="font-size:13px">Scores are 100 minus 100 times the worst severity inside the beat (100 = clean).</p>')
    if r["joins"]:
        def lvl(v):
            return "clean" if v < .25 else "slight" if v < .5 else "visible" if v < .75 else "bad"
        jr = "".join(f'<tr><td>{html.escape(j["from"])} &rarr; {html.escape(j["to"])}</td><td class="mono">{_t(j["t0"])}</td>'
                     f'<td>{"one scene (a continuation)" if j.get("related", True) else "scene change, dissolve on purpose"}</td>'
                     f'<td class="mono">{j.get("disp", 0):.0f} px</td><td class="mono">{j["chroma"]:.1f}</td>'
                     f'<td><span class="chip {lvl(j["sev"])}">{j["sev"]:.2f}</span></td></tr>' for j in r["joins"])
        lines.append('<h2>Joins</h2><table><thead><tr><th>Join</th><th>At</th><th>Kind</th><th>Out of line at mid-fade</th><th>Colour change</th>'
                     f'<th>Severity</th></tr></thead><tbody>{jr}</tbody></table>'
                     f'<p class="mute" style="font-size:13px">Measured at the middle of the {r["fade"]:.1f} s crossfade, where both pictures show at half '
                     'strength. A join between frames that look nothing alike is a scene change: that dissolve is intended and is not scored.</p>')
    mt = r.get("measures", {})
    dl = "".join(f"<dt>{LABELS[m]}</dt><dd>{html.escape(WHAT[m])}</dd>" for m in METRICS)
    lines.append('<details><summary>How these are measured</summary><dl>' + dl + '</dl>'
                 f'<p class="mute" style="font-size:13px">Severity runs from 0 (fine) to 1 (clearly visible); a stretch is listed from {mt.get("min_severity", 0.4):.1f}. '
                 f'The section\'s own sharpest edges are {mt.get("width_ref") or 0:.1f} px wide. Measured on the CPU in {mt.get("seconds_taken", 0):.0f} s'
                 f'{" with CLIP embeddings" if mt.get("embed") else ""}.</p></details>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Polish report: {name}</title><style>{CSS}</style></head><body><main>' + "".join(lines) + '</main></body></html>')
