/**
 * Type for the world: a title typeset with the site's own fonts onto a canvas (Canvas 2D), packed with the other titles of
 * the scene into one atlas texture that the world shader samples through each title's per-frame matrix.
 *
 * The page's CSS is the source of the typography: the display font, weight, tracking and the way `<em>` words are set are read
 * from a probe element in the section, so a theme change (or a style's own fonts) carries over. Colours come from the theme
 * (`--ink` and `--bg`, whichever is lighter or darker) unless the spec names one.
 */
import { clamp } from "./util";

export interface WorldStyle {
  family: string; weight: number; emItalic: boolean; emColor: string; accent: string;
  light: string; dark: string; ink: string; paper: string; tracking: number; lead: number;
}

/** Read the display type of the page from a probe element placed where the section's captions are. */
export function probeStyle(host: HTMLElement): WorldStyle {
  const probe = document.createElement("h2");
  probe.className = "ss-display";
  probe.setAttribute("aria-hidden", "true");
  probe.style.cssText = "position:absolute;visibility:hidden;pointer-events:none;left:0;top:0;";
  probe.innerHTML = "A<em>b</em>";
  host.appendChild(probe);
  const cs = getComputedStyle(probe), em = getComputedStyle(probe.querySelector("em")!);
  const root = getComputedStyle(document.documentElement);
  const css = (n: string, d: string) => root.getPropertyValue(n).trim() || d;
  const ink = css("--ink", "#f2efe9"), bg = css("--bg", "#0b0b0b");
  const lum = (c: string) => { const [r, g, b] = rgbOf(c); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const [lightC, darkC] = lum(ink) >= lum(bg) ? [ink, bg] : [bg, ink];
  const fs = parseFloat(cs.fontSize) || 64;
  const out: WorldStyle = {
    family: cs.fontFamily || "serif", weight: parseInt(cs.fontWeight) || 500,
    emItalic: em.fontStyle === "italic", emColor: em.color, accent: css("--accent", em.color),
    light: lightC, dark: darkC, ink, paper: bg, tracking: (parseFloat(cs.letterSpacing) || 0) / fs, lead: parseFloat(cs.lineHeight) / fs || 1.02,
  };
  probe.remove();
  return out;
}

const canvas1 = document.createElement("canvas").getContext("2d")!;
/** A CSS colour (any form) as [r, g, b] in 0-1. */
export function rgbOf(c: string): [number, number, number] {
  canvas1.fillStyle = "#000";
  canvas1.fillStyle = c;
  const s = canvas1.fillStyle as string;
  if (s.startsWith("#")) { const n = parseInt(s.slice(1), 16); return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255]; }
  const m = s.match(/[\d.]+/g) || ["0", "0", "0"];
  return [+m[0] / 255, +m[1] / 255, +m[2] / 255];
}

export interface Run { text: string; em: boolean }
export interface Word { text: string; em: boolean }

/** `Cold from <em>the source.</em>` -> words with their emphasis. */
export function words(html: string): Word[] {
  const out: Word[] = [];
  let em = false;
  for (const part of html.split(/(<\/?em>)/i)) {
    if (/^<em>$/i.test(part)) { em = true; continue; }
    if (/^<\/em>$/i.test(part)) { em = false; continue; }
    const t = part.replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&nbsp;/g, " ");
    for (const w of t.split(/\s+/)) if (w) out.push({ text: w, em });
  }
  return out;
}

export interface Layout {
  lines: Word[][];
  fs: number;            // font size in plane widths
  wPlane: number; hPlane: number;   // the block's size in plane units (a unit is the plane's width)
  aspect: number;
}

function fontOf(st: WorldStyle, weight: number, em: boolean, px: number): string {
  return `${em && st.emItalic ? "italic " : ""}${weight} ${px}px ${st.family}`;
}

/** Measure the words at 100px (letter-spaced), for choosing the line breaks. */
function measureWords(ctx: CanvasRenderingContext2D, ws: Word[], st: WorldStyle, weight: number, track: number, caps: boolean) {
  const widths: number[] = [];
  for (const w of ws) {
    ctx.font = fontOf(st, weight, w.em, 100);
    setSpacing(ctx, track * 100);
    widths.push(ctx.measureText(caps ? w.text.toUpperCase() : w.text).width + (hasSpacing ? 0 : track * 100 * w.text.length));
  }
  ctx.font = fontOf(st, weight, false, 100);
  setSpacing(ctx, 0);
  const space = ctx.measureText(" ").width + track * 100;
  return { widths, space };
}

const hasSpacing = "letterSpacing" in CanvasRenderingContext2D.prototype;
function setSpacing(ctx: CanvasRenderingContext2D, px: number) { if (hasSpacing) (ctx as any).letterSpacing = `${px}px`; }

/** The partition of the words into `n` lines with the narrowest widest line (balanced lines, no widows). */
function breakLines(widths: number[], space: number, n: number): number[][] {
  const N = widths.length;
  n = Math.min(n, N);
  const pre = [0]; for (const w of widths) pre.push(pre[pre.length - 1] + w);
  const span = (i: number, j: number) => pre[j] - pre[i] + space * (j - i - 1);
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(N + 1).fill(Infinity));
  const cut: number[][] = Array.from({ length: n + 1 }, () => new Array(N + 1).fill(0));
  dp[0][0] = 0;
  for (let k = 1; k <= n; k++) for (let j = k; j <= N; j++) for (let i = k - 1; i < j; i++) {
    const c = Math.max(dp[k - 1][i], span(i, j));
    if (c < dp[k][j]) { dp[k][j] = c; cut[k][j] = i; }
  }
  const out: number[][] = [];
  let j = N;
  for (let k = n; k >= 1; k--) { const i = cut[k][j]; out.unshift([i, j]); j = i; }
  return out;
}

export interface LayoutOpts { size: number; hMax: number; lines?: number; caps: boolean; track: number; weight: number; align: "left" | "center" | "right" }

/** Set the title in a block `size` plane widths wide. More lines make larger type for the same width, so the number of lines
 * is the largest whose block still stands no taller than `hMax` (plane widths); if even one line is too tall the type is
 * cut down to fit. `lines` fixes the number. */
export function layout(html: string, st: WorldStyle, o: LayoutOpts): Layout {
  const ws = words(html);
  const { widths, space } = measureWords(canvas1, ws, st, o.weight, o.track, o.caps);
  const lead = st.lead * (o.caps ? 1.04 : 1);
  let best: { lines: Word[][]; maxW: number } | null = null;
  for (const n of o.lines ? [o.lines] : [1, 2, 3, 4, 5]) {
    if (!o.lines && n > ws.length) break;
    const parts = breakLines(widths, space, n);
    const lines = parts.map(([i, j]) => ws.slice(i, j));
    const maxW = Math.max(...parts.map(([i, j]) => widths.slice(i, j).reduce((a, b) => a + b, 0) + space * (j - i - 1))) / 100;   // em
    const h = (o.size / maxW) * lead * lines.length;
    if (o.lines || !best || h <= o.hMax) best = { lines, maxW };
    else break;
  }
  const b = best!;
  let fs = o.size / b.maxW;
  const h = fs * lead * b.lines.length;
  if (h > o.hMax) fs *= o.hMax / h;
  const wPlane = fs * b.maxW, hPlane = fs * lead * b.lines.length;
  return { lines: b.lines, fs, wPlane, hPlane, aspect: wPlane / hPlane };
}

export interface Cell { x: number; y: number; w: number; h: number }   // 0-1 of the atlas

export interface Raster { canvas: HTMLCanvasElement; cells: Cell[] }

export const PAD = 0.1;       // the cell is the block plus this much of its size on every side (room for blur)

/** Draw each layout into its own cell of one atlas canvas. `px[i]` is the width in pixels the block should be drawn at. */
export function rasterize(items: { layout: Layout; px: number; colors: (em: boolean) => string; weight: number; track: number; caps: boolean; align: string; st: WorldStyle }[], maxSide = 4096): Raster {
  const dims = items.map((it) => {
    const w = Math.round(it.px * (1 + 2 * PAD)), h = Math.round(w / it.layout.aspect);
    return { w, h };
  });
  let scale = 1;
  const total = () => dims.reduce((a, d) => a + Math.ceil(d.h * scale) + 2, 0);
  const wide = () => Math.max(...dims.map((d) => d.w)) * scale;
  while ((total() > maxSide || wide() > maxSide) && scale > 0.25) scale *= 0.9;
  const W = Math.ceil(wide());
  const H = Math.max(2, Math.ceil(total()));
  const canvas = document.createElement("canvas");
  canvas.width = W; canvas.height = H;
  const g = canvas.getContext("2d")!;
  g.textBaseline = "middle";
  const cells: Cell[] = [];
  let y = 0;
  items.forEach((it, i) => {
    const cw = Math.round(dims[i].w * scale), ch = Math.round(dims[i].h * scale);
    const block = cw / (1 + 2 * PAD);                        // the block's width in pixels
    const fsPx = it.layout.fs / it.layout.wPlane * block;
    const lh = fsPx * (it.st.lead * (it.caps ? 1.04 : 1));
    const ox = (cw - block) / 2, oy = (ch - lh * it.layout.lines.length) / 2;
    it.layout.lines.forEach((line, li) => {
      // measure the line, then draw its words one by one so emphasis can change the font and colour in the middle
      const meas = (w: Word) => { g.font = fontOf(it.st, it.weight, w.em, fsPx); setSpacing(g, it.track * fsPx); return g.measureText(it.caps ? w.text.toUpperCase() : w.text).width + (hasSpacing ? 0 : it.track * fsPx * w.text.length); };
      g.font = fontOf(it.st, it.weight, false, fsPx); setSpacing(g, 0);
      const sp = g.measureText(" ").width + it.track * fsPx;
      const ws = line.map(meas);
      const lw = ws.reduce((a, b) => a + b, 0) + sp * (line.length - 1);
      let x = ox + (it.align === "left" ? 0 : it.align === "right" ? block - lw : (block - lw) / 2);
      const yy = y + oy + (li + 0.5) * lh;
      line.forEach((w, wi) => {
        g.font = fontOf(it.st, it.weight, w.em, fsPx);
        setSpacing(g, it.track * fsPx);
        g.fillStyle = it.colors(w.em);
        const t = it.caps ? w.text.toUpperCase() : w.text;
        if (hasSpacing) g.fillText(t, x, yy);
        else { let cx = x; for (const ch2 of t) { g.fillText(ch2, cx, yy); cx += g.measureText(ch2).width + it.track * fsPx; } }
        x += ws[wi] + sp;
      });
    });
    cells.push({ x: 0, y: y / H, w: cw / W, h: ch / H });
    y += ch + 2;
  });
  return { canvas, cells };
}

/** WCAG-style contrast ratio of a colour against footage of mean (display) luminance `tone`. */
export function contrastOf(c: string, tone: number): number {
  const lin = (v: number) => (v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
  const [r, g, b] = rgbOf(c).map(lin);
  const l = 0.2126 * r + 0.7152 * g + 0.0722 * b, bg = Math.pow(tone, 2.2);
  const hi = Math.max(l, bg) + 0.05, lo = Math.min(l, bg) + 0.05;
  return hi / lo;
}

/** Whichever of the theme's light and dark reads better on footage of luminance `tone`. */
export function inkFor(tone: number, st: WorldStyle): string {
  return contrastOf(st.light, tone) >= contrastOf(st.dark, tone) ? st.light : st.dark;
}

/** The em colour, unless it would vanish into the footage (then the ink that reads). */
export function contrastWith(c: string, tone: number, st: WorldStyle): string {
  return contrastOf(c, tone) < 2.2 ? inkFor(tone, st) : c;
}

export { clamp };
