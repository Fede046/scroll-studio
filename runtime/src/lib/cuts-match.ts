/** Match cut: the end of one section and the start of the next share a shape. Each side is scaled about a pivot until
 * the two shapes sit at the same place at the same size, and the picture swaps on the shape.
 *
 * A side that is a picture (a scene's visual, a hero's photo) scales only that picture: the rest of the section (captions,
 * shade, copy) fades out before the cut and back in after it, so words never zoom with the image. A side that is a page
 * element, or a picture the rest of the section sits inside (a backdrop), scales the whole section. */
import type { Anchor, Cut, Fx, FxResult, Helpers, Layer, Metrics } from "./cuts-types";

export interface Box { x: number; y: number; w: number; h: number }

const FRAMES = [".ss-visual", ".ss-hero__media img, .ss-hero__media video", ".ss-hero__media", ".ss-backdrop", "section"];
/** The element that scales when the picture does (the picture's own wrapper, so the page's styles on the picture itself stay). */
const SCALERS = ".ss-visual, .ss-hero__media";

function frameEl(pin: HTMLElement, a: Anchor): HTMLElement | null {
  if (a.of) return pin.querySelector<HTMLElement>(a.of);
  for (const s of FRAMES) {
    const el = pin.querySelector<HTMLElement>(s);
    if (el) return el;
  }
  return null;
}

/** An anchor as a box in screen pixels, with the pin's own styles off (the held layout). */
export function anchorBox(pin: HTMLElement, a: Anchor | undefined): { box: Box; frame: HTMLElement | null } | null {
  if (!a) return null;
  if (a.sel) {
    const el = pin.querySelector<HTMLElement>(a.sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 ? { box: { x: r.left, y: r.top, w: r.width, h: r.height }, frame: null } : null;
  }
  if (!a.box) return null;
  const fr = frameEl(pin, a);
  if (!fr) return null;
  const r = fr.getBoundingClientRect();
  const aspect = a.aspect || r.width / r.height;
  const cover = (a.fit || "cover") === "cover";
  let iw: number, ih: number;
  if ((r.width / r.height > aspect) === cover) { iw = r.width; ih = r.width / aspect; } else { ih = r.height; iw = r.height * aspect; }
  const s = a.scale || 1;
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const ix = cx - iw / 2, iy = cy - ih / 2;
  const [x0, y0, x1, y1] = a.box;
  const px = (u: number) => cx + (ix + u * iw - cx) * s, py = (v: number) => cy + (iy + v * ih - cy) * s;
  return { box: { x: px(x0), y: py(y0), w: (x1 - x0) * iw * s, h: (y1 - y0) * ih * s }, frame: fr };
}

/** The part of a section that is not the picture: for each ancestor of the picture up to the pin, its other children. */
function restOf(scaler: HTMLElement, pin: HTMLElement): HTMLElement[] {
  const out: HTMLElement[] = [];
  for (let n: HTMLElement | null = scaler; n && n !== pin; n = n.parentElement) {
    const parent: HTMLElement | null = n.parentElement;
    if (!parent) break;
    for (const sib of parent.children) if (sib !== n && sib instanceof HTMLElement && !(sib instanceof HTMLScriptElement)) out.push(sib);
  }
  return out;
}

interface Plan { sA: number; sB: number; fA: [number, number]; fB: [number, number]; mismatch: number }

/** Choose the two scales and the screen point the shapes meet at. Both sides only ever zoom in (a picture scaled below
 * 1 would show its edges), the pivot of each zoom stays inside its picture (so the picture still covers what it covered),
 * and the bigger ratio goes to whichever side has the smaller shape. Shapes too far apart for that return null. */
export function planMatch(A: Box, B: Box, boundsA: Box, boundsB: Box, zoom: number): Plan | null {
  const sizeA = Math.sqrt(A.w * A.h), sizeB = Math.sqrt(B.w * B.h);
  const ratio = sizeB / sizeA;
  const cA = [A.x + A.w / 2, A.y + A.h / 2], cB = [B.x + B.w / 2, B.y + B.h / 2];
  const lim = (b: Box, i: number) => (i === 0 ? [b.x, b.x + b.w] : [b.y, b.y + b.h]);
  // Both sides push in a little even when the shapes already agree (P). Shapes far apart need more push: a picture can only
  // travel as far as its zoom lets it (the pivot must stay in the picture), so P grows until the two can meet.
  for (let P = 1.07; P <= 2.4; P *= 1.04) {
    let sA = P, sB = P;
    if (ratio >= 1) { sA = P * Math.min(zoom, ratio); sB = Math.max(1.02, sA * sizeA / sizeB); }
    else { sB = P * Math.min(zoom, 1 / ratio); sA = Math.max(1.02, sB * sizeB / sizeA); }
    const T: [number, number] = [0, 0];
    let feasible = true;
    for (let i = 0; i < 2; i++) {
      // the pivot of a zoom by s that carries c to t is (s c - t) / (s - 1); it must stay inside [lo, hi] of its picture
      const [a0, a1] = lim(boundsA, i), [b0, b1] = lim(boundsB, i);
      const lo = Math.max(sA * cA[i] - (sA - 1) * a1, sB * cB[i] - (sB - 1) * b1);
      const hi = Math.min(sA * cA[i] - (sA - 1) * a0, sB * cB[i] - (sB - 1) * b0);
      const mid = (cA[i] + cB[i]) / 2;
      if (lo <= hi) T[i] = Math.min(hi, Math.max(lo, mid)); else { T[i] = (lo + hi) / 2; feasible = false; }
    }
    const piv = (s: number, c: number[]): [number, number] => [(s * c[0] - T[0]) / (s - 1), (s * c[1] - T[1]) / (s - 1)];
    if (feasible) return { sA, sB, fA: piv(sA, cA), fB: piv(sB, cB), mismatch: (sA * sizeA) / (sB * sizeB) };
  }
  return null;   // too far apart to meet without showing the edge of a picture: the cut dissolves instead
}

interface Side { el: HTMLElement; origin: string; rest: HTMLElement[] | null }

/** What scales on one side: the picture alone (with the rest of the section to fade) or the whole section. */
function pickSide(pin: HTMLElement, found: { box: Box; frame: HTMLElement | null }): { scaler: HTMLElement | null; bounds: Box | null } {
  const scaler = found.frame?.closest<HTMLElement>(SCALERS) || null;
  // the picture alone scales when it has a wrapper of its own and the rest of the section is not inside it
  if (scaler && scaler !== pin && !scaler.querySelector("h1, h2, .ss-caption, .ss-step")) {
    const r = scaler.getBoundingClientRect();
    return { scaler, bounds: { x: r.left, y: r.top, w: r.width, h: r.height } };
  }
  return { scaler: null, bounds: null };
}

export function measureMatch(c: Cut, m: Metrics) {
  const A = anchorBox(c.pinA, c.cfg.anchors?.a), B = anchorBox(c.pinB, c.cfg.anchors?.b);
  const seen = (b: Box) => b.x + b.w > 0 && b.x < m.W && b.y + b.h > 0 && b.y < m.H;
  if (!A || !B || !seen(A.box) || !seen(B.box)) { c.data.match = null; return; }
  const view: Box = { x: 0, y: 0, w: m.W, h: m.H };
  const sa = pickSide(c.pinA, A), sb = pickSide(c.pinB, B);
  const p = planMatch(A.box, B.box, sa.bounds || view, sb.bounds || view, c.cfg.zoom || 3);
  if (!p) { c.data.match = null; return; }
  const make = (pin: HTMLElement, s: { scaler: HTMLElement | null }, pivot: [number, number]): Side => {
    const el = s.scaler || pin;
    const r = el.getBoundingClientRect();
    return { el, origin: `${pivot[0] - r.left}px ${pivot[1] - r.top}px`, rest: s.scaler ? restOf(s.scaler, pin) : null };
  };
  c.data.match = { ...p, A: make(c.pinA, sa, p.fA), B: make(c.pinB, sb, p.fB) };
}

export function matchFx(fx: Record<string, Fx>, { ease, win }: Helpers): Fx {
  return (k, c, m): FxResult => {
    const M = c.data.match;
    if (!M) return fx.dissolve(k, c, m);   // no shape to meet on at this size: a soft cut instead
    const at = c.cfg.at ?? 0.5, w = c.cfg.blend ?? 0;
    const u = Math.min(1, k / at);                        // A pushes in, accelerating into the cut
    const v = Math.max(0, (k - at) / (1 - at));           // B settles, decelerating out of it
    const sA = Math.pow(M.sA, u * u), sB = Math.pow(M.sB, (1 - v) * (1 - v));
    const o = w > 0 ? ease(win(k, at - w / 2, at + w / 2)) : 1;
    const A = M.A as Side, B = M.B as Side;
    const place = (S: Side, pin: HTMLElement, s: number, base: Layer): Layer => {
      const t = `scale(${s.toFixed(4)})`;
      return S.el === pin ? { ...base, t, origin: S.origin } : { ...base, inner: { el: S.el, t, origin: S.origin } };
    };
    const a = place(A, c.pinA, sA, { vis: k < at + w / 2 });
    const b = place(B, c.pinB, sB, { vis: k >= at - w / 2, o });
    if (A.rest) a.fade = { els: A.rest, o: 1 - ease(win(k, 0, at * 0.7)) };
    if (B.rest) b.fade = { els: B.rest, o: ease(win(k, at + (1 - at) * 0.3, 1)) };
    return { a, b, live: k < at ? "a" : "b" };
  };
}
