/**
 * A brush for the painted styles (paint-on-glass, multiplane): bristle strokes on a 2D canvas, a seeded random, value
 * noise, colour helpers and a colour script. Nothing here knows about the page; each style decides what to paint.
 */
export type RGB = [number, number, number];
export const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const smooth = (a: number, b: number, v: number) => { const t = clamp((v - a) / (b - a)); return t * t * (3 - 2 * t); };

/** mulberry32: a small seeded random in [0, 1). */
export function rng(seed: number) {
  let a = (seed | 0) + 0x6d2b79f5;
  return () => { a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
export const hash = (i: number, s = 0) => { let x = Math.imul((i | 0) ^ 0x9e3779b9 ^ Math.imul(s | 0, 0x85ebca6b), 0x85ebca6b); x ^= x >>> 13; x = Math.imul(x, 0xc2b2ae35); x ^= x >>> 16; return (x >>> 0) / 4294967296; };
/** Value noise in [0, 1). */
export function vnoise(x: number, y: number, s = 0) {
  const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const h = (a: number, b: number) => hash(a * 73856093 ^ b * 19349663, s);
  return lerp(lerp(h(xi, yi), h(xi + 1, yi), u), lerp(h(xi, yi + 1), h(xi + 1, yi + 1), u), v);
}
/** Fractal value noise, roughly 0..1. */
export function fbm(x: number, y: number, s = 0, oct = 3) {
  let a = 0.5, f = 1, o = 0, n = 0;
  for (let i = 0; i < oct; i++) { o += a * vnoise(x * f, y * f, s + i * 17); n += a; a *= 0.5; f *= 2.02; }
  return o / n;
}

// ------------------------------------------------------------------------------------------------ colour
export function hsl(h: number, s: number, l: number): RGB {
  h = ((h % 360) + 360) % 360; s = clamp(s); l = clamp(l);
  const k = (n: number) => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [f(0) * 255, f(8) * 255, f(4) * 255];
}
export function toHsl([r, g, b]: RGB): [number, number, number] {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, d = mx - mn;
  if (!d) return [0, 0, l];
  const s = d / (1 - Math.abs(2 * l - 1));
  const h = mx === r ? ((g - b) / d + (g < b ? 6 : 0)) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h * 60, s, l];
}
export const mix = (a: RGB, b: RGB, t: number): RGB => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
export const rgba = (c: RGB, a = 1) => `rgba(${Math.round(c[0])},${Math.round(c[1])},${Math.round(c[2])},${a})`;
export const lum = (c: RGB) => (c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114) / 255;
/** Any CSS colour (#hex, rgb(), hsl(), a name) to RGB; falls back to `def`. */
export function parseColor(str: string, def: RGB = [200, 160, 90]): RGB {
  const s = (str || "").trim();
  let m = /^#([0-9a-f]{3,8})$/i.exec(s);
  if (m) { let h = m[1]; if (h.length < 6) h = h.split("").map((c) => c + c).join(""); return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]; }
  m = /^rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)/i.exec(s);
  if (m) return [+m[1], +m[2], +m[3]];
  try { const c = document.createElement("canvas").getContext("2d")!; c.fillStyle = "#000"; c.fillStyle = s; if (c.fillStyle !== "#000000" || /^(black|#000)/i.test(s)) return parseColor(c.fillStyle as string, def); } catch { /* ignore */ }
  return def;
}
/** A CSS custom property of the page (the theme's), as a colour. */
export function themeColor(name: string, def: RGB): RGB {
  return parseColor(getComputedStyle(document.documentElement).getPropertyValue(name), def);
}

// ------------------------------------------------------------------------------------------------ the brush
export interface BrushOpts {
  alpha?: number;            // body opacity
  seed?: number;
  light?: [number, number];  // direction the studio light comes from (streak highlights on that side)
  streaks?: number;          // bristle streaks along the stroke (0..4)
  tail?: number;             // 0..1: how much the end of the stroke breaks into separate bristles
  taper?: boolean;           // false: a stroke of even width with round ends (a thumb, a dab)
}

/** Catmull-Rom through the points, resampled about every `gap` px. */
function smoothPath(pts: number[][], gap: number): number[][] {
  if (pts.length < 3) {
    const out: number[][] = [];
    const a = pts[0], b = pts[pts.length - 1], n = Math.max(2, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / gap));
    for (let i = 0; i <= n; i++) out.push([lerp(a[0], b[0], i / n), lerp(a[1], b[1], i / n)]);
    return out;
  }
  const out: number[][] = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
    const seg = Math.max(1, Math.ceil(Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / gap));
    for (let k = 0; k < seg; k++) {
      const t = k / seg, t2 = t * t, t3 = t2 * t;
      out.push([0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)]);
    }
  }
  out.push(pts[pts.length - 1]);
  return out;
}
const lighter = (c: RGB, k: number): RGB => [Math.min(255, c[0] * (1 + k) + 14 * k * 4), Math.min(255, c[1] * (1 + k) + 12 * k * 4), Math.min(255, c[2] * (1 + k) + 8 * k * 4)];
const darker = (c: RGB, k: number): RGB => [c[0] * (1 - k), c[1] * (1 - k * 0.9), c[2] * (1 - k * 0.7)];

/**
 * One brush stroke along `pts`, w px wide, colour c0 at the start running into c1 at the end (wet paint carries
 * the old colour into the new one). The body is a ribbon that is full at the start (the brush pressed down), swells
 * a little and thins as it is lifted, with a ragged edge; bristle streaks run along it, light on the side the
 * studio light falls on and dark on the other; the tail breaks into separate bristles.
 */
export function brush(ctx: CanvasRenderingContext2D, pts: number[][], w: number, c0: RGB, c1: RGB, o: BrushOpts = {}) {
  if (pts.length < 2) return;
  const alpha = o.alpha ?? 0.94, seed = o.seed ?? 1;
  const r = rng(seed * 9301 + 49297);
  const path = smoothPath(pts, Math.max(3, w * 0.22));
  const n = path.length;
  if (n < 2) return;
  const taper = o.taper !== false;
  const tailK = o.tail ?? 0.35;
  const bodyEnd = taper ? 1 - tailK * 0.5 : 1;
  // normals and the width profile
  const nx: number[] = [], ny: number[] = [], prof: number[] = [];
  for (let i = 0; i < n; i++) {
    const a = path[Math.max(0, i - 1)], b = path[Math.min(n - 1, i + 1)];
    let tx = b[0] - a[0], ty = b[1] - a[1]; const l = Math.hypot(tx, ty) || 1; tx /= l; ty /= l;
    nx.push(-ty); ny.push(tx);
    const t = i / (n - 1);
    const press = taper ? (0.74 + 0.26 * Math.sin(Math.PI * Math.min(1, t * 1.15))) * (t > 0.55 ? 1 - Math.pow((t - 0.55) / 0.45, 2.2) * 0.72 : 1) : 1;
    const rough = 1 + (hash(i * 7 + seed, seed) - 0.5) * 0.14;
    prof.push(w * 0.5 * press * rough);
  }
  const iEnd = Math.max(2, Math.floor((n - 1) * bodyEnd));
  const g0 = path[0], gn = path[iEnd];
  const same = Math.abs(c0[0] - c1[0]) + Math.abs(c0[1] - c1[1]) + Math.abs(c0[2] - c1[2]) < 9;
  ctx.globalAlpha = alpha;
  if (same) ctx.fillStyle = rgba(c1);
  else { const g = ctx.createLinearGradient(g0[0], g0[1], gn[0], gn[1]); g.addColorStop(0, rgba(c0)); g.addColorStop(0.2, rgba(mix(c0, c1, 0.35))); g.addColorStop(0.75, rgba(c1)); ctx.fillStyle = g; }
  ctx.beginPath();
  for (let i = 0; i <= iEnd; i++) { const x = path[i][0] + nx[i] * prof[i], y = path[i][1] + ny[i] * prof[i]; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
  // round end
  const e = path[iEnd], ea = Math.atan2(ny[iEnd], nx[iEnd]);
  ctx.arc(e[0], e[1], prof[iEnd], ea, ea + Math.PI, true);
  for (let i = iEnd; i >= 0; i--) ctx.lineTo(path[i][0] - nx[i] * prof[i], path[i][1] - ny[i] * prof[i]);
  const s0 = path[0], sa = Math.atan2(-ny[0], -nx[0]);
  ctx.arc(s0[0], s0[1], prof[0], sa, sa + Math.PI, true);
  ctx.closePath(); ctx.fill();
  // bristle streaks along the body
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  const ns = o.streaks ?? (w > 30 ? 4 : w > 14 ? 3 : w > 6 ? 2 : 0);
  const lx = o.light ? o.light[0] : -0.55, ly = o.light ? o.light[1] : -0.83;
  const dx = path[iEnd][0] - path[0][0], dy = path[iEnd][1] - path[0][1], dl = Math.hypot(dx, dy) || 1;
  const litSign = (-dy / dl) * lx + (dx / dl) * ly >= 0 ? 1 : -1;
  const baseAt = (t: number) => (same ? c1 : mix(c0, c1, smooth(0, 0.6, t)));
  for (let k = 0; k < ns; k++) {
    const pos = (r() - 0.5) * 1.5, lit = pos * litSign >= 0;
    const from = Math.floor(r() * 0.3 * iEnd), to = Math.min(iEnd, Math.floor((0.6 + r() * 0.4) * iEnd));
    if (to - from < 2) continue;
    const mid = baseAt((from + to) / 2 / (n - 1));
    ctx.strokeStyle = rgba(lit ? lighter(mid, 0.18 + r() * 0.22) : darker(mid, 0.16 + r() * 0.2));
    ctx.globalAlpha = 0.42 + r() * 0.3;
    ctx.lineWidth = Math.max(1, w * (0.05 + r() * 0.09));
    ctx.beginPath();
    for (let i = from; i <= to; i++) { const q = pos * prof[i] * 0.86; const x = path[i][0] + nx[i] * q, y = path[i][1] + ny[i] * q; i === from ? ctx.moveTo(x, y) : ctx.lineTo(x, y); }
    ctx.stroke();
  }
  // the tail: the paint breaks into separate bristle lines as the brush lifts
  if (taper && tailK > 0 && w > 5) {
    const nb = 3 + Math.round(w / 12);
    for (let k = 0; k < nb; k++) {
      const pos = (k / (nb - 1) - 0.5) * 1.6 + (r() - 0.5) * 0.15;
      const from = Math.floor(iEnd * (0.82 + r() * 0.1)), to = Math.min(n - 1, iEnd + Math.floor((n - 1 - iEnd) * (0.4 + r() * 0.6)) + 1);
      if (to <= from) continue;
      ctx.strokeStyle = rgba(r() < 0.7 ? c1 : lighter(c1, 0.15));
      ctx.globalAlpha = 0.8;
      ctx.lineWidth = Math.max(1.2, w * (0.045 + r() * 0.06));
      ctx.beginPath();
      for (let i = from; i <= to; i++) { const q = pos * prof[Math.min(i, iEnd)] * 0.8; const x = path[i][0] + nx[i] * q, y = path[i][1] + ny[i] * q; i === from ? ctx.moveTo(x, y) : ctx.lineTo(x, y); }
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
}

// ------------------------------------------------------------------------------------------------ the colour script
/** One scene's palette, as an animation colour script has it: the sky, the glow at the horizon, planes receding into mist. */
export interface Palette { skyTop: RGB; skyLow: RGB; glow: RGB; far: RGB; mid: RGB; near: RGB; deep: RGB; accent: RGB; light: RGB; hue: number }

/**
 * A run of palettes for n scenes that moves through the day the way a colour script does (dawn, noon, dusk, night),
 * anchored on the site's own accent hue so the painting belongs to the brand. `warm` leans the glow warm.
 */
export function colourScript(n: number, accent: RGB, spread = 1, day = 0.25): Palette[] {
  const [h0] = toHsl(accent);
  /** hue a, moved toward hue b along the shorter way round the wheel (a plain lerp of 28 and 203 passes through green) */
  const hueMix = (a: number, b: number, t: number) => { const d = ((b - a + 540) % 360) - 180; return a + d * t; };
  const out: Palette[] = [];
  for (let i = 0; i < n; i++) {
    const t = n > 1 ? i / (n - 1) : 0;
    // time of day: dusk to night to a new dawn across the page
    const tod = (day + t * 0.85) % 1;
    const night = Math.cos((tod - 0.5) * Math.PI * 2) * 0.5 + 0.5;       // 1 at midnight
    const glowHue = h0 + Math.sin(t * Math.PI * 2 + 0.7) * 55 * spread;
    const skyHue = h0 + 205 + Math.sin(t * Math.PI * 1.4) * 32 * spread;
    const L = lerp(0.2, 0.08, night);
    out.push({
      hue: glowHue,
      skyTop: hsl(skyHue, 0.5, L * 0.9),
      skyLow: hsl(hueMix(skyHue, glowHue, 0.22), 0.6, lerp(0.34, 0.2, night)),
      glow: hsl(glowHue, 0.86, lerp(0.64, 0.58, night)),
      far: hsl(hueMix(skyHue, glowHue, 0.12), 0.4, lerp(0.3, 0.17, night)),
      mid: hsl(skyHue + 12, 0.38, lerp(0.2, 0.11, night)),
      near: hsl(skyHue + 24, 0.34, lerp(0.1, 0.055, night)),
      deep: hsl(skyHue + 30, 0.4, 0.035),
      accent: hsl(glowHue + 20, 0.8, 0.6),
      light: hsl(glowHue - 6, 0.9, 0.82),
    });
  }
  return out;
}
