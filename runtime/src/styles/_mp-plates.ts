/**
 * The painted glass of the multiplane: plates of gouache on clear glass (transparent canvases), drawn once with the
 * brush from _brush.ts. A plate is painted as if the screen were looking at it from rest (screen fractions X(0..1),
 * Y(0..1)); its depth d decides how big the camera sees it. Atmosphere is painted in, as the Disney painters did:
 * the farther a plate, the paler and bluer, the nearer, the darker and warmer-edged. Recipes (village, forest,
 * mountains, meadow) say which plates a stack has; the runtime puts them on the glass.
 */
import { Palette, RGB, brush, clamp, fbm, hash, lerp, mix, rgba, rng, smooth } from "./_brush";

export interface PCtx {
  ctx: CanvasRenderingContext2D; cw: number; ch: number; W: number; H: number; d: number; pal: Palette; r: () => number; seed: number;
  /** where the words sit: -1 left, 1 right, 0 centred (the moon and the open sky go on the other side) */
  side: number;
  X: (xs: number) => number; Y: (ys: number) => number;
}
export interface PlateDef {
  role: "sky" | "far" | "mid" | "near" | "mist" | "sweep";
  d: number;
  /** plate-space extent as fractions of the screen (W, H), relative to the screen centre: the glass is bigger than the view */
  xl: number; xr: number; yt: number; yb: number;
  draw: (p: PCtx) => void;
}
const LIGHT: [number, number] = [-0.5, -0.86];

// ------------------------------------------------------------------------------------------------ painting helpers
/** Fill the clipped region with a flat colour gradient, then lay brush strokes in it for the hand-painted surface. */
function paintRegion(p: PCtx, region: (c: CanvasRenderingContext2D) => void, bbox: [number, number, number, number], colourAt: (x: number, y: number) => RGB, o: { w?: number; n?: number; angle?: number; jitter?: number; alpha?: number } = {}) {
  const c = p.ctx, [x0, y0, x1, y1] = bbox;
  c.save(); c.beginPath(); region(c); c.clip();
  // flat ground colour first, in vertical bands, so strokes never leave a hole
  const bands = 10, hh = (y1 - y0) / bands;
  for (let i = 0; i < bands; i++) { c.fillStyle = rgba(colourAt((x0 + x1) / 2, y0 + (i + 0.5) * hh)); c.fillRect(x0 - 2, y0 + i * hh - 1, x1 - x0 + 4, hh + 2); }
  const w = o.w ?? 22, n = o.n ?? Math.round(((x1 - x0) * (y1 - y0)) / (w * w * 5));
  const r = p.r, jit = o.jitter ?? 0.1;
  for (let i = 0; i < n; i++) {
    const x = lerp(x0, x1, r()), y = lerp(y0, y1, r()), base = colourAt(x, y), k = 1 + (r() - 0.5) * 2 * jit;
    const col: RGB = [clamp(base[0] * k, 0, 255), clamp(base[1] * k, 0, 255), clamp(base[2] * k * (1 + (r() - 0.5) * 0.04), 0, 255)];
    const a = (o.angle ?? 0) + (r() - 0.5) * 0.5, len = w * (1.6 + r() * 2.2);
    const ww = w * (0.6 + r() * 0.7);
    brush(c, [[x - Math.cos(a) * len / 2, y - Math.sin(a) * len / 2], [x, y], [x + Math.cos(a) * len / 2, y + Math.sin(a) * len / 2]], ww, col, col, { alpha: o.alpha ?? 0.55, seed: p.seed * 31 + i, light: LIGHT, streaks: 1, tail: 0.15 });
  }
  c.restore();
}
/** Feather the left and right edges of a plate to nothing so no hard edge shows while the glass is smaller than the view. */
function feather(p: PCtx, frac = 0.09) {
  const c = p.ctx; c.save(); c.globalCompositeOperation = "destination-out";
  for (const side of [0, 1]) {
    const x0 = side ? p.cw : 0, x1 = side ? p.cw * (1 - frac) : p.cw * frac;
    const g = c.createLinearGradient(x0, 0, x1, 0); g.addColorStop(0, "rgba(0,0,0,1)"); g.addColorStop(1, "rgba(0,0,0,0)");
    c.fillStyle = g; c.fillRect(Math.min(x0, x1), 0, Math.abs(x1 - x0), p.ch);
  }
  c.restore();
}
const ridgeLine = (p: PCtx, base: number, amp: number, freq: number, seed: number, sharp = 0): ((xs: number) => number) => (xs) => {
  const n = fbm(xs * freq, seed, seed, 4);
  const v = sharp ? 1 - Math.abs(n * 2 - 1) * (0.6 + sharp * 0.4) : n;
  return p.Y(base - amp * (sharp ? v - 0.45 : v - 0.5) * 2);
};
/** A ridge silhouette (screen-fraction x from xa to xb) closed down to `bottom` (screen fraction y). */
function ridgeRegion(p: PCtx, line: (xs: number) => number, xa: number, xb: number, bottom: number) {
  return (c: CanvasRenderingContext2D) => {
    c.moveTo(p.X(xa), p.Y(bottom));
    for (let xs = xa; xs <= xb; xs += 0.006) c.lineTo(p.X(xs), line(xs));
    c.lineTo(p.X(xb), p.Y(bottom)); c.closePath();
  };
}
/** The thin bright line where a lit edge meets the sky. */
function rim(p: PCtx, line: (xs: number) => number, xa: number, xb: number, col: RGB, a = 0.4, wd = 2.4) {
  const c = p.ctx; c.save(); c.strokeStyle = rgba(col, a); c.lineWidth = wd; c.lineJoin = "round"; c.beginPath();
  for (let xs = xa; xs <= xb; xs += 0.006) { const y = line(xs); xs === xa ? c.moveTo(p.X(xs), y) : c.lineTo(p.X(xs), y); }
  c.stroke(); c.restore();
}
/** Atmospheric perspective: a plate's colour at a given screen height, between its top tone and bottom tone. */
const tone = (top: RGB, bottom: RGB, y0: number, y1: number) => (_x: number, y: number): RGB => mix(top, bottom, clamp((y - y0) / Math.max(1, y1 - y0)));

// ------------------------------------------------------------------------------------------------ plates
function sky(p: PCtx) {
  const { ctx: c, cw, ch, pal, r } = p;
  const g = c.createLinearGradient(0, 0, 0, ch);
  g.addColorStop(0, rgba(pal.skyTop)); g.addColorStop(0.5, rgba(mix(pal.skyTop, pal.skyLow, 0.75))); g.addColorStop(0.78, rgba(pal.skyLow)); g.addColorStop(1, rgba(mix(pal.skyLow, pal.glow, 0.55)));
  c.fillStyle = g; c.fillRect(0, 0, cw, ch);
  // broad flat strokes of sky, as a background painter lays them
  for (let i = 0; i < Math.round(cw * ch / 14000); i++) {
    const y = r() * ch, x = r() * cw, t = y / ch, base = mix(mix(pal.skyTop, pal.skyLow, smooth(0.1, 0.8, t)), pal.glow, smooth(0.65, 1, t) * 0.55);
    const k = 1 + (r() - 0.5) * 0.18, col: RGB = [clamp(base[0] * k, 0, 255), clamp(base[1] * k, 0, 255), clamp(base[2] * k, 0, 255)], L = 90 + r() * 200;
    brush(c, [[x - L / 2, y + (r() - 0.5) * 6], [x, y], [x + L / 2, y + (r() - 0.5) * 6]], 14 + r() * 26, col, col, { alpha: 0.38, seed: i + p.seed, light: LIGHT, streaks: 1, tail: 0.3 });
  }
  // the moon (or sun) and its halo, low in the sky, away from where the words sit
  const away = p.side ? -p.side : (hash(p.seed, 2) < 0.5 ? -1 : 1);
  const mx = p.X(0.5 + away * (p.side ? 0.16 + hash(p.seed, 3) * 0.14 : 0.34 + hash(p.seed, 3) * 0.08)), my = p.Y(0.22 + hash(p.seed, 4) * 0.16), mr = Math.min(cw, ch) * 0.055;
  const h = c.createRadialGradient(mx, my, mr * 0.4, mx, my, mr * 7);
  h.addColorStop(0, rgba(pal.light, 0.55)); h.addColorStop(0.18, rgba(pal.glow, 0.3)); h.addColorStop(1, rgba(pal.glow, 0));
  c.fillStyle = h; c.fillRect(mx - mr * 8, my - mr * 8, mr * 16, mr * 16);
  c.fillStyle = rgba(mix(pal.light, [255, 250, 235], 0.5)); c.beginPath(); c.arc(mx, my, mr, 0, Math.PI * 2); c.fill();
  // stars and a few clouds
  for (let i = 0; i < 44; i++) { c.fillStyle = rgba(pal.light, 0.25 + r() * 0.6); c.beginPath(); c.arc(r() * cw, r() * ch * 0.5, 0.6 + r() * 1.3, 0, Math.PI * 2); c.fill(); }
  for (let i = 0; i < 6; i++) {
    const x = r() * cw, y = ch * (0.2 + r() * 0.35), L = cw * (0.12 + r() * 0.16);
    const col = mix(pal.skyLow, pal.glow, 0.35 + r() * 0.3);
    brush(c, [[x - L / 2, y], [x, y - 4 + r() * 8], [x + L / 2, y + 3]], 14 + r() * 12, col, col, { alpha: 0.4, seed: i * 7 + p.seed, light: LIGHT, tail: 0.5 });
  }
}
function ridge(top: RGB, bottom: RGB, base: number, amp: number, freq: number, seedOff: number, opt: { sharp?: number; rim?: number; w?: number } = {}) {
  return (p: PCtx) => {
    const line = ridgeLine(p, base, amp, freq, p.seed + seedOff, opt.sharp ?? 0);
    const ya = p.Y(base - amp * 1.2), yb = p.Y(1.2);
    paintRegion(p, ridgeRegion(p, line, -0.9, 1.9, 1.2), [0, ya, p.cw, yb], tone(top, bottom, ya, yb), { w: opt.w ?? 24, angle: 0.05 });
    rim(p, line, -0.9, 1.9, mix(p.pal.light, top, 0.4), opt.rim ?? 0.28);
    feather(p);
  };
}
function mist(p: PCtx) {
  const { ctx: c, cw, ch, pal, r } = p;
  for (let i = 0; i < 16; i++) {
    const x = r() * cw, y = ch * (0.45 + r() * 0.42), rx = cw * (0.1 + r() * 0.2), ry = ch * (0.02 + r() * 0.05);
    c.save(); c.translate(x, y); c.scale(rx, ry);
    const g = c.createRadialGradient(0, 0, 0, 0, 0, 1);
    const col = mix(pal.skyLow, pal.glow, 0.25 + r() * 0.4);
    g.addColorStop(0, rgba(col, 0.2 + r() * 0.14)); g.addColorStop(1, rgba(col, 0));
    c.fillStyle = g; c.beginPath(); c.arc(0, 0, 1, 0, Math.PI * 2); c.fill(); c.restore();
  }
}
/** Conifers in a row along a ridge; each is three tiers of strokes and a trunk. */
function conifers(base: number, n: number, hgt: number, dark: RGB, light: RGB, seedOff: number) {
  return (p: PCtx) => {
    const { ctx: c, r } = p;
    const ground = ridgeLine(p, base, 0.025, 3, p.seed + seedOff);
    for (let i = 0; i < n; i++) {
      const xs = -0.3 + (i + r() * 0.8) / n * 1.6, gy = ground(xs) + p.H * 0.02, th = p.H * hgt * (0.65 + r() * 0.7) * p.d * 0.55, tw = th * (0.32 + r() * 0.1);
      const x = p.X(xs), col = mix(dark, light, r() * 0.4);
      c.fillStyle = rgba(mix(col, p.pal.deep, 0.4)); c.fillRect(x - tw * 0.04, gy - th * 0.12, tw * 0.08, th * 0.14);
      for (let t = 0; t < 3; t++) {
        const k = t / 3, wd = tw * (1 - k * 0.5), y1 = gy - th * 0.08 - th * k * 0.3, y0 = y1 - th * 0.42;
        paintRegion(p, (cc) => { cc.moveTo(x, y0); cc.lineTo(x + wd / 2, y1); cc.lineTo(x - wd / 2, y1); cc.closePath(); }, [x - wd / 2, y0, x + wd / 2, y1], (_x, y) => mix(col, mix(col, light, 0.5), (y1 - y) / (y1 - y0) * 0.5), { w: 10, n: 12, angle: 0.5 * (r() < 0.5 ? 1 : -1), alpha: 0.6 });
      }
    }
    feather(p);
  };
}
/** Houses on a ground line, windows lit near the glow. */
function village(base: number, n: number, ground: RGB, wall: RGB, seedOff: number) {
  return (p: PCtx) => {
    const { ctx: c, r, pal } = p;
    const line = ridgeLine(p, base, 0.03, 2.4, p.seed + seedOff);
    const ya = p.Y(base - 0.08), yb = p.Y(1.2);
    paintRegion(p, ridgeRegion(p, line, -0.9, 1.9, 1.2), [0, ya, p.cw, yb], tone(ground, mix(ground, pal.deep, 0.6), ya, yb), { w: 22, angle: 0.04 });
    const glowX = pal.hue;   // only to vary house lighting a little
    void glowX;
    for (let i = 0; i < n; i++) {
      const xs = -0.2 + (i + r() * 0.7) / n * 1.4, gy = line(xs), bw = p.W * p.d * (0.045 + r() * 0.04), bh = p.H * p.d * (0.06 + r() * 0.07), x = p.X(xs);
      const col = mix(wall, pal.far, r() * 0.25);
      paintRegion(p, (cc) => { cc.rect(x, gy - bh, bw, bh + 4); }, [x, gy - bh, x + bw, gy + 4], tone(mix(col, pal.glow, 0.08), col, gy - bh, gy), { w: 8, n: 8, angle: 0 });
      paintRegion(p, (cc) => { cc.moveTo(x - bw * 0.08, gy - bh); cc.lineTo(x + bw / 2, gy - bh - bh * 0.55); cc.lineTo(x + bw * 1.08, gy - bh); cc.closePath(); }, [x - bw * 0.1, gy - bh * 1.6, x + bw * 1.1, gy - bh], () => mix(col, pal.deep, 0.35), { w: 8, n: 8, angle: 0.3 });
      const nw = r() < 0.5 ? 1 : 2;
      for (let k = 0; k < nw; k++) if (r() < 0.78) {
        const wx = x + bw * (nw === 1 ? 0.38 : 0.16 + k * 0.5), wy = gy - bh * (0.72 - r() * 0.2), ww = bw * 0.22, wh = bh * 0.26;
        const g = c.createRadialGradient(wx + ww / 2, wy + wh / 2, 0, wx + ww / 2, wy + wh / 2, ww * 2.4);
        g.addColorStop(0, rgba(pal.glow, 0.55)); g.addColorStop(1, rgba(pal.glow, 0));
        c.fillStyle = g; c.fillRect(wx - ww * 2, wy - wh * 2, ww * 5, wh * 5);
        c.fillStyle = rgba(mix(pal.light, pal.glow, 0.3)); c.fillRect(wx, wy, ww, wh);
      }
    }
    feather(p);
  };
}
/** Tall trunks that stand in the foreground; a fat plate to be swept past at speed, or to stand at the edges. */
function trunks(n: number, xsPick: (i: number, r: () => number) => number, col: RGB, seedOff: number, wide = 0.07) {
  return (p: PCtx) => {
    const { ctx: c, r, pal } = p;
    for (let i = 0; i < n; i++) {
      const xs = xsPick(i, r), x = p.X(xs), tw = p.W * p.d * wide * (0.6 + r() * 0.8), lean = (r() - 0.5) * tw * 0.8;
      const top = p.Y(-0.4), bot = p.Y(1.3);
      const edge = (side: number, y: number) => x + side * tw / 2 * (0.9 + 0.2 * fbm(y / 90, i, p.seed + seedOff, 2)) + lean * (1 - (y - top) / (bot - top)) + (fbm(y / 140, i + 9, p.seed) - 0.5) * tw * 0.35;
      paintRegion(p, (cc) => {
        for (let y = top; y <= bot; y += 14) y === top ? cc.moveTo(edge(-1, y), y) : cc.lineTo(edge(-1, y), y);
        for (let y = bot; y >= top; y -= 14) cc.lineTo(edge(1, y), y);
        cc.closePath();
      }, [x - tw, top, x + tw, bot], (xx, yy) => mix(col, pal.near, 0.5 * (1 - (yy - top) / (bot - top))), { w: 18, angle: Math.PI / 2, n: Math.round((bot - top) * tw / 700) });
      // lit edge on the side the light falls from
      c.save(); c.strokeStyle = rgba(mix(pal.light, col, 0.5), 0.35); c.lineWidth = 2.6; c.beginPath();
      for (let y = top; y <= bot; y += 14) y === top ? c.moveTo(edge(-1, y) + 3, y) : c.lineTo(edge(-1, y) + 3, y);
      c.stroke(); c.restore();
      // a branch or two
      for (let b = 0; b < 2; b++) if (r() < 0.8) {
        const by = lerp(top, bot, 0.15 + r() * 0.5), dir = r() < 0.5 ? -1 : 1, L = p.W * p.d * (0.12 + r() * 0.1);
        const bx = edge(dir, by), pts = [[bx, by], [bx + dir * L * 0.5, by - L * 0.18], [bx + dir * L, by - L * 0.5]];
        brush(c, pts, tw * 0.34, col, col, { alpha: 0.95, seed: i * 5 + b, light: LIGHT, tail: 0.2 });
      }
    }
  };
}
/** Leaves hanging in from a corner of the picture: a foreground plate with dark, rimmed clusters of strokes. */
function leaves(vert: "t" | "b", col: RGB, seedOff: number, size = 0.36) {
  return (p: PCtx) => {
    const corner = vert + (p.side > 0 ? "l" : p.side < 0 ? "r" : (hash(p.seed, 9) < 0.5 ? "l" : "r"));
    const { ctx: c, r, pal } = p;
    const sx = corner[1] === "l" ? 1 : -1, sy = corner[0] === "t" ? 1 : -1;
    const cx = corner[1] === "l" ? p.X(-0.02) : p.X(1.02), cy = corner[0] === "t" ? p.Y(-0.02) : p.Y(1.02);
    const reach = Math.min(p.W, p.H * 1.3) * p.d * size;
    for (let i = 0; i < 150; i++) {
      const a = r() * Math.PI / 2, dist = reach * Math.pow(r(), 0.65);
      const x = cx + sx * Math.cos(a) * dist * 1.15, y = cy + sy * Math.sin(a) * dist * 0.9;
      const L = reach * (0.1 + r() * 0.14), ang = Math.atan2(y - cy, x - cx) + (r() - 0.5) * 1.1;
      const k = 1 + (r() - 0.5) * 0.4, base = mix(col, pal.mid, r() * 0.5), cc: RGB = [clamp(base[0] * k, 0, 255), clamp(base[1] * k, 0, 255), clamp(base[2] * k, 0, 255)];
      brush(c, [[x - Math.cos(ang) * L / 2, y - Math.sin(ang) * L / 2], [x, y], [x + Math.cos(ang) * L / 2, y + Math.sin(ang) * L / 2]], L * 0.42, cc, mix(cc, pal.light, 0.1), { alpha: 0.96, seed: i * 13 + p.seed + seedOff, light: LIGHT, streaks: 1, tail: 0.1 });
    }
  };
}
/** Foreground grass and a few flowers along the foot of the picture. */
function grass(col: RGB, flower: RGB, seedOff: number) {
  return (p: PCtx) => {
    const { ctx: c, r, pal } = p;
    const line = ridgeLine(p, 0.96, 0.03, 5, p.seed + seedOff);
    paintRegion(p, ridgeRegion(p, line, -0.9, 1.9, 1.3), [0, p.Y(0.9), p.cw, p.Y(1.3)], tone(mix(col, pal.mid, 0.3), pal.deep, p.Y(0.92), p.Y(1.2)), { w: 20, angle: 0 });
    for (let i = 0; i < 160; i++) {
      const xs = -0.2 + r() * 1.4, x = p.X(xs), y = line(xs) + p.H * 0.01, hh = p.H * p.d * (0.04 + r() * 0.11), bend = (r() - 0.5) * hh * 0.6;
      const k = 1 + (r() - 0.5) * 0.3, cc: RGB = [clamp(col[0] * k, 0, 255), clamp(col[1] * k, 0, 255), clamp(col[2] * k, 0, 255)];
      brush(c, [[x, y], [x + bend * 0.4, y - hh * 0.5], [x + bend, y - hh]], 3 + r() * 5, cc, cc, { alpha: 0.95, seed: i + p.seed, light: LIGHT, streaks: 0, tail: 0.4 });
      if (r() < 0.07) { c.fillStyle = rgba(flower, 0.9); c.beginPath(); c.arc(x + bend, y - hh, 2.5 + r() * 3.5, 0, Math.PI * 2); c.fill(); }
    }
    feather(p, 0.05);
  };
}
function rocks(col: RGB, seedOff: number, side: "l" | "r") {
  return (p: PCtx) => {
    const { r, pal } = p;
    const x0 = side === "l" ? -0.1 : 0.55, w = 0.55;
    const line = (xs: number) => p.Y(0.72 + 0.28 * smooth(0, 1, side === "l" ? (xs - x0) / w : 1 - (xs - x0) / w) + (fbm(xs * 9, seedOff, p.seed, 3) - 0.5) * 0.12);
    const ya = p.Y(0.6), yb = p.Y(1.3);
    paintRegion(p, ridgeRegion(p, line, x0, x0 + w, 1.3), [p.X(x0), ya, p.X(x0 + w), yb], tone(mix(col, pal.mid, 0.4), col, ya, yb), { w: 20, angle: 0.4 });
    rim(p, line, x0, x0 + w, pal.light, 0.22);
    void r;
  };
}

// ------------------------------------------------------------------------------------------------ recipes: what a stack is made of
export type Recipe = (pal: Palette) => PlateDef[];   // the side the words sit on reaches the painters through PCtx.side
const D = { far: 1.55, mid: 1.3, near: 0.7, mist: 1.12, sweep: 0.52 };
/** Glass for a plate at depth d: wide enough to cover the view at rest and a little more, only as tall as it needs to be. */
const plate = (role: PlateDef["role"], d: number, draw: PlateDef["draw"], yt?: number, yb?: number): PlateDef => {
  const sky = role === "sky";
  const half = sky ? 0.53 : 0.5 * d * 1.1 + 0.12;
  return { role, d, xl: -half, xr: half,
    yt: yt ?? (sky ? -0.53 : role === "far" ? (0.2 - 0.5) * d : role === "mid" ? (0.3 - 0.5) * d : -0.5 * d * 1.1),
    yb: yb ?? (sky ? 0.53 : 0.5 * d * 1.12), draw };
};

const villageSet: Recipe = (pal) => [
  plate("sky", 6, sky),
  plate("far", D.far, ridge(mix(pal.far, pal.skyLow, 0.45), mix(pal.far, pal.mid, 0.4), 0.58, 0.07, 2.6, 0)),
  plate("mid", D.mid, village(0.74, 20, mix(pal.mid, pal.far, 0.3), mix(pal.mid, pal.deep, 0.4), 5)),
  plate("mist", D.mist, mist),
  plate("near", D.near, leaves("t", pal.near, 3, 0.34)),
  plate("near", D.near, grass(pal.near, pal.accent, 7)),
  plate("sweep", D.sweep, trunks(6, (i, r) => 0.0 + i * 0.2 + r() * 0.08, mix(pal.near, pal.deep, 0.5), 11, 0.09)),
];
const forestSet: Recipe = (pal) => [
  plate("sky", 6, sky),
  plate("far", D.far, conifers(0.68, 26, 0.34, mix(pal.far, pal.skyLow, 0.5), mix(pal.far, pal.glow, 0.15), 4)),
  plate("mid", D.mid, conifers(0.8, 16, 0.5, mix(pal.mid, pal.far, 0.3), pal.far, 9)),
  plate("mist", D.mist, mist),
  plate("near", D.near, leaves("t", pal.near, 5, 0.36)),
  plate("near", D.near, grass(pal.near, pal.light, 2)),
  plate("sweep", D.sweep, trunks(5, (i, r) => 0.0 + i * 0.25 + r() * 0.08, mix(pal.near, pal.deep, 0.6), 17, 0.12)),
];
const mountainSet: Recipe = (pal) => [
  plate("sky", 6, sky),
  plate("far", D.far, ridge(mix(pal.far, pal.skyLow, 0.5), mix(pal.far, pal.mid, 0.5), 0.5, 0.2, 2.2, 3, { sharp: 1, rim: 0.4 })),
  plate("mid", D.mid, ridge(mix(pal.far, pal.mid, 0.55), pal.mid, 0.72, 0.1, 3.2, 8, { sharp: 0.6, rim: 0.3 })),
  plate("mist", D.mist, mist),
  plate("near", D.near, rocks(pal.near, 4, "l")),
  plate("near", D.near, rocks(pal.near, 6, "r")),
  plate("sweep", D.sweep, trunks(5, (i, r) => 0.0 + i * 0.22 + r() * 0.1, mix(pal.near, pal.deep, 0.55), 21, 0.1)),
];
const meadowSet: Recipe = (pal) => [
  plate("sky", 6, sky),
  plate("far", D.far, ridge(mix(pal.far, pal.skyLow, 0.5), mix(pal.far, pal.mid, 0.4), 0.56, 0.05, 2.4, 6)),
  plate("mid", D.mid, conifers(0.76, 10, 0.3, mix(pal.mid, pal.far, 0.3), pal.far, 13)),
  plate("mist", D.mist, mist),
  plate("near", D.near, grass(pal.near, pal.accent, 9)),
  plate("near", D.near, leaves("t", pal.near, 8, 0.28)),
  plate("sweep", D.sweep, trunks(6, (i, r) => 0.0 + i * 0.2 + r() * 0.08, mix(pal.near, pal.deep, 0.5), 25, 0.09)),
];
export const RECIPES: Recipe[] = [villageSet, forestSet, mountainSet, meadowSet];
export { rng };
