/**
 * Cut-paper decoration for the paper-cut-out style: a leafy branch whose leaves hang on hinges, a bird whose wings are hinged
 * at the shoulder, stars cut out of a night sheet, and the jointed arm. Everything is a flat vector shape in the sheet's own
 * "cut" colour (CSS var --sil) with a thin cut line (--paper) where a vein would be; nothing here depends on a particular site.
 */
const NS = "http://www.w3.org/2000/svg";
const rnd = (seed: number) => { let s = seed >>> 0 || 1; return () => { s ^= s << 13; s >>>= 0; s ^= s >> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; }; };
function el<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number> = {}, parent?: Element): SVGElementTagNameMap[K] {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, String(attrs[k]));
  parent?.appendChild(e);
  return e;
}

export interface Leaf { g: SVGGElement; base: number; ph: number; amp: number; x: number; y: number; s: number }
export interface Branch { svg: SVGSVGElement; leaves: Leaf[]; root: SVGGElement }

/** A branch rising from the bottom edge: a stem and leaves, each leaf pinned at its base so it can swing. */
export function branch(w: number, h: number, seed: number, count = 14): Branch {
  const r = rnd(seed);
  const svg = el("svg", { viewBox: `0 0 ${w} ${h}`, width: w, height: h, "aria-hidden": "true" });
  const root = el("g", {}, svg);
  const p0 = { x: w * 0.12, y: h }, p1 = { x: w * 0.1, y: h * 0.55 }, p2 = { x: w * 0.5, y: h * 0.5 }, p3 = { x: w * 0.88, y: h * 0.12 };
  const at = (t: number) => { const u = 1 - t; return { x: u * u * u * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t * t * t * p3.x, y: u * u * u * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t * t * t * p3.y }; };
  const ang = (t: number) => { const a = at(Math.max(0, t - 0.01)), b = at(Math.min(1, t + 0.01)); return Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI; };
  el("path", { d: `M${p0.x} ${p0.y} C${p1.x} ${p1.y} ${p2.x} ${p2.y} ${p3.x} ${p3.y}`, fill: "none", stroke: "var(--sil)", "stroke-width": 5, "stroke-linecap": "round" }, root);
  const leaves: Leaf[] = [];
  for (let k = 0; k < count; k++) {
    const t = 0.14 + 0.84 * (k / (count - 1));
    const side = k % 2 ? 1 : -1;
    const a = ang(t) + side * (52 + r() * 24);
    const len = (h * 0.3) * (1.05 - t * 0.55) * (0.85 + r() * 0.3);
    const p = at(t);
    const g = el("g", { transform: `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)}) rotate(${a.toFixed(1)})` }, root);
    const s = el("g", { transform: `scale(${len.toFixed(1)})` }, g);
    el("path", { d: "M0 0 C.27 -.2 .31 -.66 0 -1 C-.31 -.66 -.27 -.2 0 0Z", fill: "var(--sil)" }, s);
    el("path", { d: "M0 -.1 L0 -.84", fill: "none", stroke: "var(--paper)", "stroke-width": 1.5, "vector-effect": "non-scaling-stroke", "stroke-linecap": "round" }, s);
    leaves.push({ g, base: a, ph: r() * 6.28, amp: 3 + r() * 5, x: p.x, y: p.y, s: 1 });
  }
  // a berry or two on thin stalks
  for (let k = 0; k < 3; k++) { const t = 0.35 + r() * 0.55, p = at(t), a = ang(t) - 80; const g = el("g", { transform: `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)}) rotate(${a.toFixed(1)})` }, root); el("path", { d: "M0 0 L0 -26", stroke: "var(--sil)", "stroke-width": 2, fill: "none" }, g); el("circle", { cx: 0, cy: -32, r: 7, fill: "var(--sil)" }, g); }
  return { svg, leaves, root };
}

export function swayBranch(b: Branch, t: number, gust: number) {
  for (const l of b.leaves) l.g.setAttribute("transform", `translate(${l.x.toFixed(1)} ${l.y.toFixed(1)}) rotate(${(l.base + gust * l.amp * Math.sin(t * 1.6 + l.ph) * 3).toFixed(2)})`);
}

export interface Bird { svg: SVGSVGElement; wingA: SVGGElement; wingB: SVGGElement; root: SVGGElement }
/** A bird in flight: body, head, tail and two wings pinned at the shoulder. */
export function bird(): Bird {
  const svg = el("svg", { viewBox: "-90 -90 190 150", width: 190, height: 150, "aria-hidden": "true" });
  const root = el("g", {}, svg);
  const wing = (extra: string) => {
    const g = el("g", { transform: `translate(2 -6) ${extra}` }, root);
    el("path", { d: "M0 0 C-12 -32 -34 -58 -70 -72 C-56 -48 -48 -26 -38 -2Z", fill: "var(--sil)" }, g);
    el("path", { d: "M-8 -6 C-24 -26 -38 -44 -56 -58", stroke: "var(--paper)", "stroke-width": 1.4, fill: "none", "vector-effect": "non-scaling-stroke" }, g);
    return g;
  };
  const wingB = wing("");
  el("path", { d: "M-34 4 C-20 -12 18 -12 34 -2 C40 0 44 -2 52 -6 L48 2 C44 10 36 14 20 14 C0 14 -20 12 -34 4Z", fill: "var(--sil)" }, root);
  el("path", { d: "M-34 4 L-74 -6 L-68 6 L-76 16 L-34 10Z", fill: "var(--sil)" }, root);
  el("path", { d: "M44 -8 L62 -4 L44 -1Z", fill: "var(--sil)" }, root);
  el("circle", { cx: 38, cy: -6, r: 9, fill: "var(--sil)" }, root);
  el("circle", { cx: 41, cy: -8, r: 2, fill: "var(--paper)" }, root);
  const wingA = wing("");
  return { svg, wingA, wingB, root };
}
export function flap(b: Bird, phase: number) {
  b.wingA.setAttribute("transform", `translate(2 -6) rotate(${(-8 + 48 * Math.sin(phase)).toFixed(1)})`);
  b.wingB.setAttribute("transform", `translate(2 -6) rotate(${(-22 + 40 * Math.sin(phase + 0.7)).toFixed(1)})`);
}

/** Stars cut from a night sheet: the sheet's backlit glow shows through. */
export function stars(w: number, h: number, seed: number, n = 26): SVGSVGElement {
  const r = rnd(seed);
  const svg = el("svg", { viewBox: `0 0 ${w} ${h}`, width: w, height: h, "aria-hidden": "true" });
  for (let i = 0; i < n; i++) {
    const x = r() * w, y = r() * h * 0.7, s = 4 + r() * 9;
    el("path", { d: `M${x} ${y - s} L${x + s * 0.28} ${y - s * 0.28} L${x + s} ${y} L${x + s * 0.28} ${y + s * 0.28} L${x} ${y + s} L${x - s * 0.28} ${y + s * 0.28} L${x - s} ${y} L${x - s * 0.28} ${y - s * 0.28}Z`, fill: "var(--amber, #f0b45a)", opacity: (0.55 + r() * 0.45).toFixed(2) }, svg);
  }
  return svg;
}

// ------------------------------------------------------------------------------------------------ the arm
export const ARM = { L1: 250, L2: 215, HAND: 140 };
export interface Arm { svg: SVGSVGElement; upper: SVGGElement; fore: SVGGElement; hand: SVGGElement; shadow: SVGGElement }
/** A jointed paper arm in a black silhouette sleeve with a white lace cuff and a pointing hand: three parts pinned at shoulder, elbow and wrist. */
export function arm(): Arm {
  const svg = el("svg", { class: "pc-arm", "aria-hidden": "true" });
  const mk = (parent: Element, cls: string) => el("g", { class: cls }, parent);
  const shadow = mk(svg, "pc-arm__sh");
  const parts = (layer: Element, tone: boolean) => {
    const fill = tone ? "rgba(0,0,0,.28)" : "var(--arm, #1b1715)";
    const edge = tone ? "none" : "#f7f0de";
    const upper = mk(layer, "pc-arm__up");
    el("path", { d: `M0 -25 C60 -32 160 -30 ${ARM.L1} -19 L${ARM.L1} 19 C160 30 60 32 0 25Z`, fill, stroke: edge, "stroke-width": 3, "stroke-linejoin": "round" }, upper);
    if (!tone) { for (const x of [58, 118, 178]) el("path", { d: `M${x} -26 C${x + 6} -8 ${x + 6} 8 ${x} 26`, stroke: "#f7f0de", "stroke-width": 2, fill: "none", opacity: 0.55 }, upper); }
    const fore = mk(layer, "pc-arm__fo");
    el("path", { d: `M0 -20 C70 -22 150 -18 ${ARM.L2} -15 L${ARM.L2} 15 C150 18 70 22 0 20Z`, fill, stroke: edge, "stroke-width": 3, "stroke-linejoin": "round" }, fore);
    // the cuff: a white lace edge at the wrist
    const cuff = el("g", {}, fore);
    el("path", { d: `M${ARM.L2 - 26} -22 L${ARM.L2 + 10} -24 L${ARM.L2 + 10} 24 L${ARM.L2 - 26} 22Z`, fill: tone ? fill : "#f7f0de", stroke: tone ? "none" : "#1b1715", "stroke-width": 1.5 }, cuff);
    if (!tone) for (let i = -2; i <= 2; i++) el("circle", { cx: ARM.L2 + 10, cy: i * 9.2, r: 4.6, fill: "#f7f0de", stroke: "#1b1715", "stroke-width": 1.2 }, cuff);
    const hand = mk(layer, "pc-arm__hand");
    if (!tone) hand.setAttribute("data-hand", "");
    // a glove with one finger out
    el("path", { d: "M0 -17 C22 -22 46 -22 62 -16 L82 -13 C100 -12 116 -6 128 -3 C139 -1 139 5 128 6 C114 8 100 9 84 10 L74 11 C82 20 78 31 62 29 C46 26 38 20 26 19 C14 19 6 18 0 17Z", fill, stroke: edge, "stroke-width": 3, "stroke-linejoin": "round" }, hand);
    if (!tone) { el("path", { d: "M70 -10 C86 -8 104 -4 120 -1", stroke: "#f7f0de", "stroke-width": 1.6, fill: "none", opacity: 0.6 }, hand); el("path", { d: "M52 10 C60 16 66 22 68 24", stroke: "#f7f0de", "stroke-width": 1.6, fill: "none", opacity: 0.6 }, hand); }
    // brads at the joints
    if (!tone) for (const [p, x] of [[upper, 0], [upper, ARM.L1], [fore, ARM.L2]] as [Element, number][]) { el("circle", { cx: x, cy: 0, r: 9, fill: "#d9a82e", stroke: "#7d5a10", "stroke-width": 1.5 }, p); el("path", { d: `M${x - 5} -3 L${x + 5} 3`, stroke: "#7d5a10", "stroke-width": 1.6 }, p); }
    return { upper, fore, hand };
  };
  const sh = parts(shadow, true);
  const fg = parts(svg, false);
  void sh;
  return { svg, upper: fg.upper, fore: fg.fore, hand: fg.hand, shadow };
}
/** Pose the arm: shoulder at (sx, sy), the fingertip at (tx, ty). Two-bone inverse kinematics, the elbow bending towards `bend` (+1 or -1). */
export function poseArm(a: Arm, sx: number, sy: number, tx: number, ty: number, bend: number, scale: number) {
  const L1 = ARM.L1 * scale, L2 = (ARM.L2 + ARM.HAND * 0.82) * scale;
  let dx = tx - sx, dy = ty - sy;
  let d = Math.hypot(dx, dy);
  const dMax = L1 + L2 - 2, dMin = Math.abs(L1 - L2) + 2;
  const base = Math.atan2(dy, dx);
  if (d > dMax) { dx *= dMax / d; dy *= dMax / d; d = dMax; }
  if (d < dMin) { d = dMin; }
  const a1 = Math.acos(Math.min(1, Math.max(-1, (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d))));
  const th1 = base + bend * a1;
  const ex = sx + Math.cos(th1) * L1, ey = sy + Math.sin(th1) * L1;
  const th2 = Math.atan2(ty - ey, tx - ex);
  const deg = (r: number) => (r * 180 / Math.PI).toFixed(2);
  const set = (layer: Element, x: number, y: number, th: number, s: number, off = 0) => (layer as SVGGElement).setAttribute("transform", `translate(${(x + off).toFixed(1)} ${(y + off).toFixed(1)}) rotate(${deg(th)}) scale(${s})`);
  const pose = (up: SVGGElement, fo: SVGGElement, ha: SVGGElement, off: number) => {
    set(up, sx, sy, th1, scale, off); set(fo, ex, ey, th2, scale, off);
    set(ha, ex + Math.cos(th2) * ARM.L2 * scale, ey + Math.sin(th2) * ARM.L2 * scale, th2, scale, off);
  };
  pose(a.upper, a.fore, a.hand, 0);
  const sh = a.shadow.children;
  pose(sh[0] as SVGGElement, sh[1] as SVGGElement, sh[2] as SVGGElement, 7);
}
