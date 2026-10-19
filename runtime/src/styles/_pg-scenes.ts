/**
 * The paintings paint-on-glass aims at: small colour maps (a few hundred cells across) composed from a palette of the
 * colour script, the side the copy sits on and the beat's place in its section. The brush then paints toward them, so
 * these only need broad value structure: a luminous place, dark masses, a quiet area under the words.
 * Kinds: sea, hills, forest, village, swirl, field. A picture the page supplies is drawn instead (see `image`).
 */
import { Palette, RGB, clamp, fbm, hash, lerp, mix, rgba, rng, smooth, vnoise } from "./_brush";

export interface SceneSpec {
  kind: string; pal: Palette; seed: number; /** varies the details (clouds, stars) between the items of one list while the landscape stays */ dseed: number; w: number; h: number;
  /** where the words sit, 0..1 of the screen (they get a quiet, darker ground) */
  copy: { x0: number; y0: number; x1: number; y1: number };
  /** where the light is, 0..1 */
  lx: number; ly: number;
  /** item k of n in a list: the light moves along the horizon with it */
  k: number; n: number;
}
export const KINDS = ["sea", "hills", "swirl", "village", "forest", "field"];

type Ctx = CanvasRenderingContext2D;
const grad = (c: Ctx, x0: number, y0: number, x1: number, y1: number, stops: [number, RGB, number?][]) => {
  const g = c.createLinearGradient(x0, y0, x1, y1);
  for (const [t, col, a] of stops) g.addColorStop(clamp(t), rgba(col, a ?? 1));
  return g;
};
const radial = (c: Ctx, x: number, y: number, r: number, stops: [number, RGB, number][]) => {
  const g = c.createRadialGradient(x, y, 0, x, y, r);
  for (const [t, col, a] of stops) g.addColorStop(clamp(t), rgba(col, a));
  return g;
};
/** A ridge line: y positions across the width from layered noise. */
function ridge(w: number, y0: number, amp: number, seed: number, freq = 3): number[] {
  const out: number[] = [];
  for (let x = 0; x <= w; x += 2) out.push(y0 + (fbm((x / w) * freq, seed, seed, 4) - 0.5) * 2 * amp);
  return out;
}
function fillRidge(c: Ctx, ys: number[], w: number, h: number, fill: string | CanvasGradient) {
  c.beginPath(); c.moveTo(0, h);
  ys.forEach((y, i) => c.lineTo(i * 2, y));
  c.lineTo(w, h); c.closePath(); c.fillStyle = fill; c.fill();
}

function sky(c: Ctx, s: SceneSpec, hy: number) {
  const { pal: p, w, h } = s;
  c.fillStyle = grad(c, 0, 0, 0, h * hy, [[0, p.skyTop], [0.55, mix(p.skyTop, p.skyLow, 0.7)], [1, p.skyLow]]);
  c.fillRect(0, 0, w, h);
  // the luminous place: a glow that the whole picture is lit from
  const gx = s.lx * w, gy = s.ly * h;
  c.fillStyle = radial(c, gx, gy, Math.max(w, h) * 0.55, [[0, p.light, 0.95], [0.12, p.glow, 0.8], [0.45, mix(p.glow, p.skyLow, 0.6), 0.32], [1, p.skyLow, 0]]);
  c.fillRect(0, 0, w, h);
  // clouds: long soft lozenges, lit on their underside by the glow
  const r = rng(s.dseed + 11);
  for (let i = 0; i < 7; i++) {
    const cx = r() * w, cy = r() * h * hy * 0.8, rw = w * (0.1 + r() * 0.2), rh = h * (0.015 + r() * 0.03);
    const near = clamp(1 - Math.hypot(cx - gx, cy - gy) / (w * 0.6));
    c.save(); c.translate(cx, cy); c.rotate((r() - 0.5) * 0.25); c.scale(rw, rh);
    c.fillStyle = radial(c, 0, 0, 1, [[0, mix(p.skyTop, p.glow, near * 0.8), 0.7], [1, p.skyTop, 0]]);
    c.beginPath(); c.arc(0, 0, 1, 0, Math.PI * 2); c.fill(); c.restore();
  }
}
function stars(c: Ctx, s: SceneSpec, hy: number, n: number) {
  const r = rng(s.dseed + 5);
  for (let i = 0; i < n; i++) {
    const x = r() * s.w, y = r() * s.h * hy * 0.8, rad = 0.7 + r() * 1.6;
    c.fillStyle = rgba(s.pal.light, 0.35 + r() * 0.5);
    c.beginPath(); c.arc(x, y, rad, 0, Math.PI * 2); c.fill();
  }
}
function disc(c: Ctx, s: SceneSpec, x: number, y: number, rad: number) {
  c.fillStyle = radial(c, x, y, rad * 3.4, [[0, s.pal.light, 0.55], [0.3, s.pal.glow, 0.25], [1, s.pal.glow, 0]]);
  c.beginPath(); c.arc(x, y, rad * 3.4, 0, Math.PI * 2); c.fill();
  c.fillStyle = rgba(s.pal.light, 1); c.beginPath(); c.arc(x, y, rad, 0, Math.PI * 2); c.fill();
}

function sea(c: Ctx, s: SceneSpec) {
  const { pal: p, w, h } = s; const hy = 0.6;
  sky(c, s, hy);
  const sx = s.lx * w, sy = h * (hy - 0.09);
  disc(c, s, sx, sy, h * 0.055);
  // water: dark, with the sun's road of broken light
  c.fillStyle = grad(c, 0, h * hy, 0, h, [[0, mix(p.skyLow, p.far, 0.5)], [0.5, p.mid], [1, p.near]]);
  c.fillRect(0, h * hy, w, h * (1 - hy));
  const r = rng(s.seed + 3);
  for (let i = 0; i < 70; i++) {
    const t = i / 70, y = h * hy + t * t * h * (1 - hy) + 2;
    const half = lerp(w * 0.05, w * 0.22, t) * (0.4 + r() * 0.8);
    const x = sx + (r() - 0.5) * half * 1.6;
    c.fillStyle = rgba(mix(p.glow, p.light, r()), (0.65 - t * 0.35) * (0.5 + r() * 0.5));
    c.fillRect(x - half * 0.5, y, half, Math.max(1, h * (0.003 + t * 0.006)));
  }
  // swell lines catching the sky
  for (let i = 0; i < 18; i++) {
    const t = r(), y = h * hy + t * t * h * (1 - hy) * 0.9 + 4, x = r() * w, len = w * (0.06 + r() * 0.12 * (0.4 + t));
    c.fillStyle = rgba(mix(p.far, p.skyLow, 0.5), 0.35);
    c.fillRect(x, y, len, Math.max(1, h * 0.004 * (0.5 + t)));
  }
  stars(c, s, hy, 26);
}
function hills(c: Ctx, s: SceneSpec) {
  const { pal: p, w, h } = s; const hy = 0.66;
  sky(c, s, hy);
  stars(c, s, hy, 40);
  disc(c, s, s.lx * w, s.ly * h * 0.9, h * 0.04);
  const layers: [RGB, number, number, number][] = [[p.far, 0.6, 0.07, 2.2], [mix(p.far, p.mid, 0.55), 0.7, 0.07, 3], [p.mid, 0.8, 0.06, 3.6], [p.near, 0.92, 0.04, 4.4]];
  layers.forEach(([col, y0, amp, f], i) => {
    const ys = ridge(w, h * y0, h * amp, s.seed + i * 7, f).map((y) => y);
    fillRidge(c, ys, w, h, grad(c, 0, h * (y0 - amp), 0, h, [[0, mix(col, p.glow, 0.28 * (1 - i / 4))], [0.35, col], [1, mix(col, p.deep, 0.5)]]));
  });
}
function swirl(c: Ctx, s: SceneSpec) {
  const { pal: p, w, h } = s; const hy = 0.78;
  sky(c, s, hy);
  const cx = s.lx * w, cy = s.ly * h;
  // rings of cloud around the light
  const r = rng(s.dseed + 9);
  for (let ring = 0; ring < 5; ring++) {
    const rad = h * (0.12 + ring * 0.11), col = mix(p.skyLow, p.glow, 0.7 - ring * 0.13);
    for (let a = 0; a < Math.PI * 2; a += 0.09) {
      const wob = 1 + (vnoise(a * 2 + ring, s.seed) - 0.5) * 0.35;
      const x = cx + Math.cos(a + ring * 0.7) * rad * wob * 1.25, y = cy + Math.sin(a + ring * 0.7) * rad * wob * 0.8;
      c.fillStyle = rgba(ring % 2 ? mix(col, p.skyTop, 0.5) : col, 0.34);
      c.beginPath(); c.arc(x, y, h * (0.025 + r() * 0.03), 0, Math.PI * 2); c.fill();
    }
  }
  disc(c, s, cx, cy, h * 0.045);
  stars(c, s, hy, 22);
  const ys = ridge(w, h * hy, h * 0.05, s.seed + 21, 3);
  fillRidge(c, ys, w, h, grad(c, 0, h * 0.72, 0, h, [[0, p.mid], [1, p.deep]]));
}
function village(c: Ctx, s: SceneSpec) {
  const { pal: p, w, h } = s; const hy = 0.64;
  sky(c, s, hy);
  stars(c, s, hy, 30);
  fillRidge(c, ridge(w, h * 0.62, h * 0.06, s.seed + 4, 2.4), w, h, grad(c, 0, h * 0.55, 0, h, [[0, p.far], [1, p.mid]]));
  const base = h * 0.8, r = rng(s.seed + 13);
  fillRidge(c, ridge(w, base, h * 0.025, s.seed + 8, 3), w, h, grad(c, 0, base - 20, 0, h, [[0, p.mid], [1, p.near]]));
  // houses: dark blocks with pitched roofs; windows lit near the light
  const hx = s.lx * w;
  for (let i = 0; i < 26; i++) {
    const bw = w * (0.025 + r() * 0.03), bh = h * (0.04 + r() * 0.06), x = r() * w, y = base + (r() - 0.3) * h * 0.04 - bh * 0.3;
    const col = mix(p.near, p.mid, r() * 0.5);
    c.fillStyle = rgba(col);
    c.fillRect(x, y, bw, bh);
    c.beginPath(); c.moveTo(x - bw * 0.08, y); c.lineTo(x + bw / 2, y - bh * 0.45); c.lineTo(x + bw * 1.08, y); c.closePath(); c.fill();
    const lit = Math.exp(-Math.pow((x - hx) / (w * 0.32), 2)) * 0.85 + 0.12;
    for (let k = 0; k < 2; k++) if (r() < lit) {
      c.fillStyle = rgba(mix(p.glow, p.light, r()), 0.9);
      c.fillRect(x + bw * (0.2 + k * 0.4), y + bh * (0.25 + r() * 0.3), bw * 0.2, bh * 0.2);
    }
  }
  fillRidge(c, ridge(w, h * 0.93, h * 0.03, s.seed + 31, 4), w, h, rgba(p.deep));
}
function forest(c: Ctx, s: SceneSpec) {
  const { pal: p, w, h } = s;
  sky(c, s, 0.9);
  // mist rising off the floor in the clearing
  c.fillStyle = grad(c, 0, h * 0.5, 0, h, [[0, p.glow, 0], [0.8, mix(p.skyLow, p.glow, 0.5), 0.5], [1, p.mid, 0.9]]);
  c.fillRect(0, h * 0.5, w, h * 0.5);
  const r = rng(s.seed + 2);
  // trunks in three depths, the near ones darkest and widest; the clearing (where the light is) stays open
  for (let layer = 0; layer < 3; layer++) {
    const n = 5 + layer * 2, col = mix(p.far, p.deep, layer / 2.2);
    for (let i = 0; i < n; i++) {
      let x = ((i + r() * 0.8) / n) * w;
      if (Math.abs(x - s.lx * w) < w * 0.12) x += (x < s.lx * w ? -1 : 1) * w * 0.16;
      const tw = w * (0.012 + layer * 0.018) * (0.7 + r() * 0.8);
      c.fillStyle = rgba(col, 0.95);
      c.beginPath(); c.moveTo(x - tw / 2, h); c.bezierCurveTo(x - tw * 0.5, h * 0.6, x - tw * 0.4, h * 0.3, x - tw * 0.3 + (r() - 0.5) * tw, 0); c.lineTo(x + tw * 0.3, 0); c.bezierCurveTo(x + tw * 0.4, h * 0.3, x + tw * 0.5, h * 0.6, x + tw / 2, h); c.closePath(); c.fill();
    }
  }
  // canopy shadows at the top
  for (let i = 0; i < 16; i++) {
    c.fillStyle = radial(c, r() * w, r() * h * 0.12, w * 0.12, [[0, p.deep, 0.8], [1, p.deep, 0]]);
    c.fillRect(0, 0, w, h * 0.3);
  }
  c.fillStyle = grad(c, 0, h * 0.86, 0, h, [[0, p.near, 0], [1, p.deep, 1]]);
  c.fillRect(0, h * 0.86, w, h * 0.14);
}
function field(c: Ctx, s: SceneSpec) {
  const { pal: p, w, h } = s; const hy = 0.5;
  sky(c, s, hy);
  stars(c, s, hy, 14);
  disc(c, s, s.lx * w, h * (hy - 0.05), h * 0.05);
  const r = rng(s.seed + 6);
  // bands of field, each a little lighter toward the horizon, with tufts of grass along their edges
  const bands = 6;
  for (let b = 0; b < bands; b++) {
    const t = b / bands, y0 = h * (hy + t * (1 - hy)), col = mix(mix(p.far, p.glow, 0.18 * (1 - t)), p.near, t * 0.95);
    fillRidge(c, ridge(w, y0, h * (0.01 + t * 0.03), s.seed + b * 3, 4 + b), w, h, rgba(col));
    for (let i = 0; i < 40 + b * 30; i++) {
      const x = r() * w, y = y0 + (r() - 0.2) * h * 0.04, hh = h * (0.01 + t * 0.045);
      c.strokeStyle = rgba(mix(col, p.light, r() * 0.18 * (1 - t)), 0.7); c.lineWidth = 1 + t * 2;
      c.beginPath(); c.moveTo(x, y); c.lineTo(x + (r() - 0.5) * hh * 0.7, y - hh); c.stroke();
    }
  }
}

/** Paint the scene into `c` (w x h), then give the words a quiet ground. Returns the base flow angle function. */
export function composeScene(c: Ctx, s: SceneSpec): (x: number, y: number) => number {
  c.save();
  c.globalAlpha = 1; c.globalCompositeOperation = "source-over";
  ({ sea, hills, swirl, village, forest, field } as Record<string, (c: Ctx, s: SceneSpec) => void>)[s.kind]?.(c, s);
  quiet(c, s);
  c.restore();
  const { w, h } = s, ph = hash(s.seed) * 6;
  if (s.kind === "swirl") {
    const cx = s.lx * w, cy = s.ly * h;
    return (x, y) => Math.atan2(y - cy, x - cx) + Math.PI / 2 + (y > h * 0.75 ? 1.2 : 0);
  }
  if (s.kind === "forest") return (x, y) => Math.PI / 2 + Math.sin(x * 0.03 + ph) * 0.2 + (y < h * 0.3 ? 0.9 : 0);
  return (x, y) => Math.sin(x / w * 5 + ph) * 0.28 + Math.sin(y / h * 4 + ph * 1.3) * 0.2 + (y > h * 0.6 ? 0.08 : 0);
}

/** A quiet ground under the words: darker and lower in contrast, feathered, so type sits on the picture legibly. */
export function quiet(c: Ctx, s: SceneSpec) {
  const { w, h, copy: b } = s;
  const cx = ((b.x0 + b.x1) / 2) * w, cy = ((b.y0 + b.y1) / 2) * h;
  const rx = ((b.x1 - b.x0) / 2 + 0.16) * w, ry = ((b.y1 - b.y0) / 2 + 0.18) * h;
  c.save(); c.translate(cx, cy); c.scale(rx, ry);
  const g = c.createRadialGradient(0, 0, 0, 0, 0, 1);
  g.addColorStop(0, rgba(s.pal.deep, 0.6)); g.addColorStop(0.55, rgba(s.pal.deep, 0.34)); g.addColorStop(1, rgba(s.pal.deep, 0));
  c.fillStyle = g; c.beginPath(); c.arc(0, 0, 1, 0, Math.PI * 2); c.fill(); c.restore();
}

/** Draw a supplied picture as the scene: cover-fit, deepened a little, with the quiet ground for the words. */
export function composeImage(c: Ctx, s: SceneSpec, img: CanvasImageSource, iw: number, ih: number) {
  const { w, h } = s;
  const k = Math.max(w / iw, h / ih), dw = iw * k, dh = ih * k;
  c.save();
  c.fillStyle = rgba(s.pal.deep); c.fillRect(0, 0, w, h);
  try { c.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh); } catch { /* tainted or not loaded */ }
  // a bright picture is deepened until the words can sit on it
  let mean = 0.4;
  try { const d = c.getImageData(0, 0, w, h).data; let t = 0, n = 0; for (let i = 0; i < d.length; i += 40) { t += d[i] * 0.299 + d[i + 1] * 0.587 + d[i + 2] * 0.114; n++; } mean = t / n / 255; } catch { /* unreadable */ }
  c.fillStyle = rgba(s.pal.deep, clamp(0.2 + (mean - 0.3) * 1.5, 0.2, 0.72)); c.fillRect(0, 0, w, h);
  quiet(c, s); quiet(c, s);
  c.restore();
  return (x: number, y: number) => Math.sin(x / w * 4 + s.seed) * 0.35 + Math.sin(y / h * 3) * 0.25;
}
export { smooth };
