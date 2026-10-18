/** Match cut: the end of one section and the start of the next share a shape. Each side is scaled about a pivot until
 * the two shapes sit at the same place at the same size, and the picture swaps on the shape. */
import type { Anchor, Cut, Fx, FxResult, Helpers, Metrics } from "./cuts-types";

interface Box { x: number; y: number; w: number; h: number }

const FRAMES = [".ss-visual", ".ss-hero__media img, .ss-hero__media video", ".ss-hero__media", ".ss-backdrop", "section"];

function frameEl(pin: HTMLElement, a: Anchor): HTMLElement | null {
  if (a.of) return pin.querySelector<HTMLElement>(a.of);
  for (const s of FRAMES) {
    const el = pin.querySelector<HTMLElement>(s);
    if (el) return el;
  }
  return null;
}

/** An anchor as a box in screen pixels, with the pin's own styles off (the held layout). */
export function anchorBox(pin: HTMLElement, a: Anchor | undefined): Box | null {
  if (!a) return null;
  if (a.sel) {
    const el = pin.querySelector<HTMLElement>(a.sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 ? { x: r.left, y: r.top, w: r.width, h: r.height } : null;
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
  return { x: px(x0), y: py(y0), w: (x1 - x0) * iw * s, h: (y1 - y0) * ih * s };
}

interface Plan { sA: number; sB: number; fA: [number, number]; fB: [number, number]; mismatch: number }

/** Choose the two scales and the screen point the shapes meet at. Both sides only ever zoom in (a picture scaled below
 * 1 would show its edges), the pivot of each zoom stays on screen (so the picture still covers it), and the bigger
 * ratio goes to whichever side has the smaller shape. */
export function planMatch(A: Box, B: Box, W: number, H: number, zoom: number): Plan {
  const sizeA = Math.sqrt(A.w * A.h), sizeB = Math.sqrt(B.w * B.h);
  const ratio = sizeB / sizeA;
  const P = 1.07;   // both sides push in a little even when the shapes already agree
  let sA = P, sB = P;
  if (ratio >= 1) { sA = P * Math.min(zoom, ratio); sB = Math.max(1.02, sA * sizeA / sizeB); }
  else { sB = P * Math.min(zoom, 1 / ratio); sA = Math.max(1.02, sB * sizeB / sizeA); }
  const cA = [A.x + A.w / 2, A.y + A.h / 2], cB = [B.x + B.w / 2, B.y + B.h / 2];
  const T: [number, number] = [0, 0];
  const dim = [W, H];
  for (let i = 0; i < 2; i++) {
    // the pivot of a zoom by s that carries c to t is (s c - t) / (s - 1); it must stay inside [0, dim]
    const lo = Math.max(sA * cA[i] - (sA - 1) * dim[i], sB * cB[i] - (sB - 1) * dim[i]);
    const hi = Math.min(sA * cA[i], sB * cB[i]);
    const mid = (cA[i] + cB[i]) / 2;
    T[i] = lo <= hi ? Math.min(hi, Math.max(lo, mid)) : (lo + hi) / 2;
  }
  const piv = (s: number, c: number[]): [number, number] => [(s * c[0] - T[0]) / (s - 1), (s * c[1] - T[1]) / (s - 1)];
  return { sA, sB, fA: piv(sA, cA), fB: piv(sB, cB), mismatch: (sA * sizeA) / (sB * sizeB) };
}

export function measureMatch(c: Cut, m: Metrics) {
  const A = anchorBox(c.pinA, c.cfg.anchors?.a), B = anchorBox(c.pinB, c.cfg.anchors?.b);
  const seen = (b: Box | null) => !!b && b.x + b.w > 0 && b.x < m.W && b.y + b.h > 0 && b.y < m.H;
  if (!A || !B || !seen(A) || !seen(B)) { c.data.match = null; return; }
  const p = planMatch(A, B, m.W, m.H, c.cfg.zoom || 3);
  const ra = c.pinA.getBoundingClientRect(), rb = c.pinB.getBoundingClientRect();
  c.data.match = { ...p, oA: `${p.fA[0] - ra.left}px ${p.fA[1] - ra.top}px`, oB: `${p.fB[0] - rb.left}px ${p.fB[1] - rb.top}px`, A, B };
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
    return {
      a: { vis: k < at + w / 2, t: `scale(${sA.toFixed(4)})`, origin: M.oA },
      b: { vis: k >= at - w / 2, t: `scale(${sB.toFixed(4)})`, origin: M.oB, o },
      live: k < at ? "a" : "b",
    };
  };
}
