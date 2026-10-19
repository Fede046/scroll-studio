/**
 * Paint on glass: the whole page is one wet painting on a pane lit from behind (Petrov's finger-painted glass, the
 * reworked frames of Loving Vincent). Every beat of the page (a section, or one item of a list) has a painting it
 * wants to be, composed from the colour script and the place of its words (or the picture the page supplies). The
 * painting is never cut and never rewound: scrolling is the painter's hand. As the visitor scrolls from one beat
 * toward the next the brush lays strokes, coarse ones first, each one starting in the old paint and dragging it
 * into the new colour, always where the picture disagrees most with what it is becoming; scrolling back paints
 * toward the earlier beat with new strokes. Stop and the brush stops with a half-reworked picture on the glass; at a
 * beat the picture settles and only a slow boil of tiny strokes keeps it alive. The pointer is a finger in the wet
 * paint: it drags colour and leaves the smear until a stroke paints over it. Nothing here blocks scrolling.
 * Reduced motion: each beat's finished painting is laid in one step, no boil, no smear.
 * Research: docs/styles/styles-30-31.md, section 1.
 */
import { $, $$, onFrame, reduced } from "./_kit";
import { RGB, brush, clamp, colourScript, hash, lerp, lum, mix, parseColor, rgba, rng, smooth, themeColor } from "./_brush";
import { KINDS, SceneSpec, composeImage, composeScene } from "./_pg-scenes";

const mobile = () => innerWidth < 760;
type Flow = (x: number, y: number) => number;
interface Target { rgb: Uint8Array; lum: Float32Array; flow: Flow; fromImage: boolean }
interface Beat {
  el: HTMLElement; copy: HTMLElement | null; img: HTMLImageElement | null; kind: string; side: string; group: number;
  k: number; n: number; scene: string; swatch: HTMLElement | null; target: Target | null; top: number; mid: number; pal: ReturnType<typeof colourScript>[number];
}

export default function start() {
  const canvas = $<HTMLCanvasElement>(".pg-canvas");
  const els = $$<HTMLElement>("main [data-pg]");
  if (!canvas || !els.length) return;
  const ctx = canvas.getContext("2d", { alpha: false });
  if (!ctx) return;
  const root = document.documentElement;
  try { run(canvas, ctx, els, root); } catch (e) { root.classList.remove("pg-live"); console.warn("paint-on-glass:", e); }
}

function run(canvas: HTMLCanvasElement, ctx: CanvasRenderingContext2D, els: HTMLElement[], root: HTMLElement) {
  // ------------------------------------------------------------------ beats and the colour script
  const accent = themeColor("--accent", [226, 156, 62]);
  const siteSeed = Math.floor(hash(document.title.split("").reduce((a, c) => a * 31 + c.charCodeAt(0), 7)) * 6);
  const pals = colourScript(els.length, accent, 1, 0.22);
  let group = -1, lastSec: Element | null = null;
  const beats: Beat[] = els.map((el, i) => {
    const sec = el.closest("section");
    if (sec !== lastSec) { group++; lastSec = sec; }
    return {
      el, copy: $<HTMLElement>(".pg-copy", el), img: $<HTMLImageElement>("img.pg-src", el), kind: el.dataset.pg || "", side: el.dataset.side || "l",
      group, k: Number(el.dataset.k || 0), n: Number(el.dataset.n || 1), scene: KINDS[(group + siteSeed) % KINDS.length], swatch: null, target: null, top: 0, mid: 0, pal: pals[i],
    };
  });
  root.classList.add("pg-live");

  // ------------------------------------------------------------------ geometry
  let W = 0, H = 0, dpr = 1, GC = 5, gw = 0, gh = 0, cur = new Float32Array(0);
  let wMax = 100, wMin = 9, N = 300, pending: number[] = [];
  const R = rng(20250);
  const cap = () => (mobile() ? 11 : 26);

  function size() {
    const mw = innerWidth, mh = Math.max(innerHeight, Math.round(screen.height * 0.6));
    W = mw; H = mh;
    dpr = Math.min(devicePixelRatio || 1, mobile() ? 1.25 : 1.5);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    GC = mobile() ? 6 : clamp(W / 280, 4, 7);
    gw = Math.ceil(W / GC); gh = Math.ceil(H / GC);
    cur = new Float32Array(gw * gh * 3);
    const m = Math.min(W, H);
    wMax = m * (mobile() ? 0.15 : 0.12); wMin = Math.max(6, m * 0.008);
    N = mobile() ? 260 : 520;
    for (const b of beats) b.target = null;
  }
  /** The ground the painting starts on: the middle of what it is about to become (a painter's imprimatura). */
  function ground(i: number): RGB {
    const t = target(i); let r = 0, g = 0, b = 0;
    for (let k = 0; k < gw * gh; k += 7) { r += t.rgb[k * 3]; g += t.rgb[k * 3 + 1]; b += t.rgb[k * 3 + 2]; }
    const n = Math.ceil(gw * gh / 7);
    return mix([r / n, g / n, b / n], beats[i].pal.deep, 0.35);
  }
  function wipe() {
    const d = ground(heading);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.globalAlpha = 1;
    ctx.fillStyle = rgba(d); ctx.fillRect(0, 0, W, H);
    for (let i = 0; i < gw * gh; i++) { cur[i * 3] = d[0]; cur[i * 3 + 1] = d[1]; cur[i * 3 + 2] = d[2]; }
  }

  // ------------------------------------------------------------------ the painting a beat wants to be
  const tc = document.createElement("canvas");
  function measureCopy(b: Beat) {
    const box = (b.copy || b.el).getBoundingClientRect(), br = b.el.getBoundingClientRect();
    const dy = innerHeight / 2 - (br.top + br.height / 2);      // where it sits when the beat is centred
    const y0 = (box.top + dy) / innerHeight, y1 = (box.bottom + dy) / innerHeight;
    return { x0: clamp(box.left / W), x1: clamp(box.right / W), y0: clamp(y0), y1: clamp(y1) };
  }
  function target(i: number): Target {
    const b = beats[i];
    if (b.target) return b.target;
    tc.width = gw; tc.height = gh;
    const t = tc.getContext("2d", { willReadFrequently: true })!;
    t.setTransform(1, 0, 0, 1, 0, 0); t.clearRect(0, 0, gw, gh);
    const side = b.side === "r" ? 1 : b.side === "c" ? 0 : -1;
    const spread = b.n > 1 ? (b.k / (b.n - 1) - 0.5) * 0.42 : 0;
    const lx = clamp((side === 1 ? 0.27 : side === -1 ? 0.7 : 0.5 + (hash(i) - 0.5) * 0.4) + spread, 0.12, 0.88);
    const ly = 0.3 + hash(i, 3) * 0.12;
    const spec: SceneSpec = { kind: b.scene, pal: b.pal, seed: b.group * 13 + 5, dseed: b.group * 13 + 5 + b.k * 37, w: gw, h: gh, copy: measureCopy(b), lx, ly, k: b.k, n: b.n };
    let flow: Flow, fromImage = false;
    const im = b.img;
    if (im && im.complete && im.naturalWidth) {
      try {
        flow = composeImage(t, spec, im, im.naturalWidth, im.naturalHeight);
        t.getImageData(0, 0, 1, 1); fromImage = true;
      } catch { t.clearRect(0, 0, gw, gh); flow = composeScene(t, spec); }
    } else flow = composeScene(t, spec);
    const d = t.getImageData(0, 0, gw, gh).data, rgb = new Uint8Array(gw * gh * 3), l = new Float32Array(gw * gh);
    for (let k = 0; k < gw * gh; k++) {
      rgb[k * 3] = d[k * 4]; rgb[k * 3 + 1] = d[k * 4 + 1]; rgb[k * 3 + 2] = d[k * 4 + 2];
      l[k] = (d[k * 4] * 0.299 + d[k * 4 + 1] * 0.587 + d[k * 4 + 2] * 0.114);
    }
    // the picture may load after the first look: rebuild it then
    if (im && !fromImage) im.addEventListener("load", () => { b.target = null; }, { once: true });
    return (b.target = { rgb, lum: l, flow, fromImage });
  }

  // ------------------------------------------------------------------ the brush
  let strokes = 0, lastStrokeAt = 0;
  const px = (g: number) => g * GC + GC / 2;
  const cell = (x: number, y: number) => (clamp((y / GC) | 0, 0, gh - 1) * gw + clamp((x / GC) | 0, 0, gw - 1)) * 3;
  const tgtAt = (t: Target, x: number, y: number): RGB => { const i = cell(x, y); return [t.rgb[i], t.rgb[i + 1], t.rgb[i + 2]]; };
  const curAt = (x: number, y: number): RGB => { const i = cell(x, y); return [cur[i], cur[i + 1], cur[i + 2]]; };

  function direction(t: Target, x: number, y: number): number {
    const gx = clamp((x / GC) | 0, 1, gw - 2), gy = clamp((y / GC) | 0, 1, gh - 2), i = gy * gw + gx;
    const dx = t.lum[i + 1] - t.lum[i - 1], dy = t.lum[i + gw] - t.lum[i - gw];
    const mag = Math.hypot(dx, dy), s = clamp(mag * 0.02);
    const phi = t.flow(gx, gy);
    let psi = Math.atan2(dy, dx) + Math.PI / 2;
    if (Math.cos(psi - phi) < 0) psi += Math.PI;
    const vx = Math.cos(phi) * (1 - s) + Math.cos(psi) * s, vy = Math.sin(phi) * (1 - s) + Math.sin(psi) * s;
    return Math.atan2(vy, vx);
  }
  function deposit(x: number, y: number, rad: number, c: RGB, a: number) {
    const r = Math.max(1, rad / GC), gx0 = Math.floor((x - rad) / GC), gx1 = Math.ceil((x + rad) / GC), gy0 = Math.floor((y - rad) / GC), gy1 = Math.ceil((y + rad) / GC);
    for (let gy = Math.max(0, gy0); gy <= Math.min(gh - 1, gy1); gy++) for (let gx = Math.max(0, gx0); gx <= Math.min(gw - 1, gx1); gx++) {
      const d2 = ((gx + 0.5) * GC - x) ** 2 + ((gy + 0.5) * GC - y) ** 2, rr = rad * rad;
      if (d2 > rr) continue;
      const k = a * (1 - 0.35 * d2 / rr), i = (gy * gw + gx) * 3;
      cur[i] += (c[0] - cur[i]) * k; cur[i + 1] += (c[1] - cur[i + 1]) * k; cur[i + 2] += (c[2] - cur[i + 2]) * k;
    }
  }
  /** One stroke toward the heading's painting. u (0..1) is how far through the transition's strokes we are: coarse to fine. */
  function stroke(u: number, minErr = 8): boolean {
    const t = target(heading);
    let bi = 0, be = -1;
    for (let k = 0; k < 8; k++) {
      const gx = (R() * gw) | 0, gy = (R() * gh) | 0, i = (gy * gw + gx) * 3;
      const e = (Math.abs(cur[i] - t.rgb[i]) + Math.abs(cur[i + 1] - t.rgb[i + 1]) + Math.abs(cur[i + 2] - t.rgb[i + 2])) / 3;
      if (e > be) { be = e; bi = i; }
    }
    strokes++; lastStrokeAt = performance.now();
    if (be < minErr) return false;
    const gi = bi / 3;
    let x = px(gi % gw), y = px(Math.floor(gi / gw));
    const w = wMax * Math.pow(wMin / wMax, Math.pow(u, 0.7)) * (0.78 + R() * 0.44);
    const len = w * lerp(5.2, 2.4, u) * (0.7 + R() * 0.6), step = Math.max(5, w * 0.5), n = Math.max(3, Math.round(len / step));
    const pts: number[][] = [[x, y]];
    const c0 = curAt(x, y), cs = tgtAt(t, x, y);
    let ang = direction(t, x, y);
    for (let s = 1; s <= n; s++) {
      const want = direction(t, x, y);
      let da = want - ang; while (da > Math.PI) da -= Math.PI * 2; while (da < -Math.PI) da += Math.PI * 2;
      if (Math.abs(da) > Math.PI / 2) { da -= Math.sign(da) * Math.PI; }   // brush strokes have no front
      ang += clamp(da, -0.4, 0.4);
      x += Math.cos(ang) * step; y += Math.sin(ang) * step;
      if (x < -w || y < -w || x > W + w || y > H + w) break;
      pts.push([x, y]);
      const c = tgtAt(t, x, y);
      if (s >= 2 && Math.abs(c[0] - cs[0]) + Math.abs(c[1] - cs[1]) + Math.abs(c[2] - cs[2]) > 90 + 160 * u) break;   // stop at an edge
    }
    if (pts.length < 2) pts.push([pts[0][0] + 2, pts[0][1] + 1]);
    const ce = tgtAt(t, pts[Math.min(pts.length - 1, Math.ceil(pts.length * 0.6))][0], pts[Math.min(pts.length - 1, Math.ceil(pts.length * 0.6))][1]);
    const j = () => 1 + (R() - 0.5) * 0.1;
    const c1: RGB = [clamp(ce[0] * j(), 0, 255), clamp(ce[1] * j(), 0, 255), clamp(ce[2] * j(), 0, 255)];
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    brush(ctx, pts, w, c0, c1, { seed: strokes, light: [-0.55, -0.83], alpha: 0.94 });
    for (let k = 0; k < pts.length; k++) deposit(pts[k][0], pts[k][1], w * 0.5, mix(c0, c1, smooth(0, 0.35, k / Math.max(1, pts.length - 1))), 0.88);
    return true;
  }
  function error(samples = 80): number {
    const t = target(heading); let s = 0;
    for (let k = 0; k < samples; k++) {
      const i = (((R() * gw * gh) | 0)) * 3;
      s += (Math.abs(cur[i] - t.rgb[i]) + Math.abs(cur[i + 1] - t.rgb[i + 1]) + Math.abs(cur[i + 2] - t.rgb[i + 2])) / 3;
    }
    return s / samples;
  }

  // ------------------------------------------------------------------ the page as a phase: 0 .. beats - 1
  let heading = 0, startPhase = 0, done = 0, moveDir = 1, lastP = 0, settledFor = 0, settled = false;
  const mids: number[] = [];
  function layout() {
    const sy = scrollY;
    beats.forEach((b, i) => { const r = b.el.getBoundingClientRect(); b.top = r.top + sy; b.mid = r.top + sy + r.height / 2; mids[i] = b.mid; });
  }
  function phaseAt(y: number): number {
    const c = y + innerHeight / 2, n = mids.length;
    if (c <= mids[0]) return 0;
    if (c >= mids[n - 1]) return n - 1;
    let i = 0; while (i < n - 2 && c >= mids[i + 1]) i++;
    const f = (c - mids[i]) / Math.max(1, mids[i + 1] - mids[i]);
    return i + smooth(0.16, 0.84, f);
  }
  const ease = (c: number) => c * c * (3 - 2 * c);

  function setHeading(h: number, p: number) {
    heading = h; startPhase = p; done = 0; settled = false; settledFor = 0;
    target(h);
    setTimeout(() => { if (h + 1 < beats.length) target(h + 1); if (h > 0) target(h - 1); }, 60);
  }

  // ------------------------------------------------------------------ chrome: the colour script rail, counter, reveals
  const rail = $<HTMLElement>(".pg-script");
  if (rail) {
    rail.innerHTML = "";
    rail.style.setProperty("--n", String(beats.length));
    let g = -1;
    beats.forEach((b, i) => {
      if (b.group !== g) { g = b.group; }
      const a = document.createElement("button");
      a.type = "button"; a.className = "pg-sw" + (b.k > 0 ? " pg-sw--sub" : "");
      const t = (b.el.querySelector("h1, h2, h3, h4, blockquote, .pg-fig") as HTMLElement | null)?.textContent?.trim().replace(/\s+/g, " ") || b.kind;
      a.setAttribute("aria-label", `Scene ${i + 1}: ${t.slice(0, 48)}`);
      a.style.setProperty("--c1", rgba(b.pal.skyLow)); a.style.setProperty("--c2", rgba(b.pal.glow)); a.style.setProperty("--c3", rgba(b.pal.far));
      a.addEventListener("click", () => b.el.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" }));
      rail.appendChild(a); b.swatch = a;
    });
  }
  const countEl = $<HTMLElement>("[data-pg-count]"), stateEl = $<HTMLElement>("[data-pg-state]"), sceneEl = $<HTMLElement>("[data-pg-scene]");
  let hud = 0, here = -1;
  function markHere(i: number) {
    if (i === here) return;
    here = i;
    beats.forEach((b, k) => { b.swatch?.classList.toggle("is-here", k === i); b.el.classList.toggle("is-here", k === i); });
    beats[i].el.classList.add("is-on");
    if (sceneEl) sceneEl.textContent = String(i + 1).padStart(2, "0");
    root.style.removeProperty("--pg-none");
  }
  // a reveal that does not depend on the phase: anything on screen is shown (words are never held back for long)
  const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) (e.target as HTMLElement).classList.add("is-on"); }), { threshold: 0.35 });
  beats.forEach((b) => io.observe(b.el));

  // ------------------------------------------------------------------ the finger
  let last: [number, number] | null = null, lastMove = 0;
  const queue: number[][] = [];
  const fine = matchMedia("(pointer: fine)").matches;
  const tmpCur = new Float32Array(3 * 900);
  /** A finger dragged through wet paint: what is under it is carried along (the canvas copied onto itself, shifted by the move). */
  function smear(x0: number, y0: number, x1: number, y1: number, press: number) {
    const dx = x1 - x0, dy = y1 - y0, sp = Math.hypot(dx, dy);
    if (sp < 1.5) return;
    const r = (mobile() ? 30 : 44) * (0.85 + Math.min(1, sp / 70) * 0.4) * press;
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    for (const [k, a] of [[1, 0.62], [0.66, 0.5]] as const) {
      const rr = r * k;
      ctx.save(); ctx.beginPath(); ctx.arc(x1, y1, rr, 0, Math.PI * 2); ctx.clip(); ctx.globalAlpha = a;
      ctx.drawImage(canvas, (x0 - rr) * dpr, (y0 - rr) * dpr, 2 * rr * dpr, 2 * rr * dpr, x1 - rr, y1 - rr, 2 * rr, 2 * rr);
      ctx.restore();
    }
    ctx.restore();
    // the colour map follows: each cell under the finger takes what was behind it
    const gx0 = Math.max(0, Math.floor((x1 - r) / GC)), gx1 = Math.min(gw - 1, Math.ceil((x1 + r) / GC)), gy0 = Math.max(0, Math.floor((y1 - r) / GC)), gy1 = Math.min(gh - 1, Math.ceil((y1 + r) / GC));
    let n = 0;
    for (let gy = gy0; gy <= gy1 && n < 300; gy++) for (let gx = gx0; gx <= gx1 && n < 300; gx++) {
      if (((gx + 0.5) * GC - x1) ** 2 + ((gy + 0.5) * GC - y1) ** 2 > r * r) continue;
      const sx = clamp(Math.round(gx - dx / GC), 0, gw - 1), sy = clamp(Math.round(gy - dy / GC), 0, gh - 1), si = (sy * gw + sx) * 3;
      tmpCur[n * 3] = cur[si]; tmpCur[n * 3 + 1] = cur[si + 1]; tmpCur[n * 3 + 2] = cur[si + 2]; n++;
    }
    n = 0;
    for (let gy = gy0; gy <= gy1 && n < 300; gy++) for (let gx = gx0; gx <= gx1 && n < 300; gx++) {
      if (((gx + 0.5) * GC - x1) ** 2 + ((gy + 0.5) * GC - y1) ** 2 > r * r) continue;
      const i = (gy * gw + gx) * 3;
      cur[i] += (tmpCur[n * 3] - cur[i]) * 0.55; cur[i + 1] += (tmpCur[n * 3 + 1] - cur[i + 1]) * 0.55; cur[i + 2] += (tmpCur[n * 3 + 2] - cur[i + 2]) * 0.55; n++;
    }
    strokes++;
  }
  if (!reduced) {
    addEventListener("pointermove", (e) => {
      if (e.pointerType === "touch") { /* a drag that stays a drag smears; one that becomes a scroll is cancelled by the browser */ }
      if (last) { const d = Math.hypot(e.clientX - last[0], e.clientY - last[1]); if (d > 9) { queue.push([last[0], last[1], e.clientX, e.clientY, e.pressure > 0 && e.buttons ? 1.35 : 1]); last = [e.clientX, e.clientY]; } }
      else last = [e.clientX, e.clientY];
      lastMove = performance.now();
    }, { passive: true });
    addEventListener("pointerdown", (e) => { if (e.pointerType !== "mouse" || e.button === 0) { last = [e.clientX, e.clientY]; queue.push([e.clientX, e.clientY, e.clientX + 1, e.clientY + 1, 1.6]); } }, { passive: true });
    addEventListener("pointerleave", () => { last = null; });
    addEventListener("pointercancel", () => { last = null; });
  }

  // ------------------------------------------------------------------ start, loop
  size(); layout();
  const p0 = phaseAt(scrollY);
  heading = Math.round(p0); startPhase = p0; lastP = p0;
  wipe();
  target(heading);
  const flush = () => { let g = 0; while (done < N && g++ < N * 2) { stroke(done / N, 6); done++; } for (let k = 0; k < 160 && error(60) > 9; k++) stroke(1, 6); settled = true; };
  if (reduced) flush();
  else { done = Math.round(N * 0.0); }   // the first picture paints itself in as the page opens
  let boilAt = 0, booting = !reduced;
  let resizeT = 0;
  addEventListener("resize", () => {
    clearTimeout(resizeT);
    resizeT = window.setTimeout(() => {
      if (Math.abs(innerWidth - W) < 2 && Math.abs(innerHeight - H) < 140) { layout(); return; }
      size(); layout(); wipe(); done = 0; settled = false; if (reduced) flush();
    }, 160);
  });
  addEventListener("load", () => { layout(); beats.forEach((b) => { if (b.img && b.target && !b.target.fromImage) b.target = null; }); });
  let layoutAt = 0;
  (window as any).__pg = {
    /** debugging: the painting beat i aims at, as a data URL */
    target(i: number) { const t = target(i), c = document.createElement("canvas"); c.width = gw; c.height = gh; const x = c.getContext("2d")!, d = x.createImageData(gw, gh); for (let k = 0; k < gw * gh; k++) { d.data[k * 4] = t.rgb[k * 3]; d.data[k * 4 + 1] = t.rgb[k * 3 + 1]; d.data[k * 4 + 2] = t.rgb[k * 3 + 2]; d.data[k * 4 + 3] = 255; } x.putImageData(d, 0, 0); return c.toDataURL(); },
    get state() { return { heading, startPhase, done, N, strokes, settled, phase: lastP, err: error(60) }; } };

  onFrame(({ y, t }) => {
    if (t - layoutAt > 1.2) { layoutAt = t; layout(); }
    const p = phaseAt(y);
    const dp = p - lastP;
    if (Math.abs(dp) > 1e-4) moveDir = Math.sign(dp);
    lastP = p;
    const desired = moveDir > 0 ? Math.ceil(p - 1e-3) : Math.floor(p + 1e-3);
    if (desired !== heading) setHeading(clamp(desired, 0, beats.length - 1), p);
    markHere(clamp(Math.round(p), 0, beats.length - 1));

    const span = Math.abs(heading - startPhase);
    const c = span < 1e-3 ? 1 : clamp(Math.abs(p - startPhase) / span);
    const want = Math.floor(N * ease(c));
    let budget = (booting && t < 3 ? 4 : cap()) * (want - done > 150 ? 2 : 1);
    if (booting && done >= N) booting = false;
    if (reduced) { while (done < want) { stroke(done / N, 6); done++; } if (c >= 1 && !settled) flush(); }
    else {
      while (done < want && budget-- > 0) { stroke(done / N); done++; }
      if (done >= N || (c >= 1 && done >= want)) {
        // arrived: finish what the brush left undone, then stop
        if (!settled) {
          let b2 = Math.max(6, Math.floor(cap() / 2));
          while (b2-- > 0) stroke(0.92, 8);
          if (++settledFor > 8 && error(48) < 10) settled = true;
          if (settledFor > 150) settled = true;
        }
      }
      // the boil: tiny strokes keep the settled picture alive (Loving Vincent's every frame is repainted)
      if (settled && t - boilAt > 0.32) {
        boilAt = t;
        for (let k = 0; k < 2; k++) {
          const x = R() * W, y2 = R() * H, c0 = curAt(x, y2), w = wMin * (1 + R());
          const a = R() * 6.28, l = w * 2.2;
          const j = () => 1 + (R() - 0.5) * 0.07;
          const c1: RGB = [clamp(c0[0] * j(), 0, 255), clamp(c0[1] * j(), 0, 255), clamp(c0[2] * j(), 0, 255)];
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          brush(ctx, [[x, y2], [x + Math.cos(a) * l, y2 + Math.sin(a) * l]], w, c0, c1, { alpha: 0.55, streaks: 1, tail: 0, seed: strokes++ });
        }
      }
      // the finger
      let q = 6;
      while (queue.length && q-- > 0) { const m = queue.shift()!; smear(m[0], m[1], m[2], m[3], m[4]); }
    }
    // readouts at a gentle rate
    if (t - hud > 0.12) {
      hud = t;
      if (countEl) countEl.textContent = String(strokes).padStart(5, "0");
      if (stateEl) stateEl.textContent = performance.now() - lastStrokeAt < 700 && !settled ? "wet" : "set";
      root.classList.toggle("pg-wet", performance.now() - lastStrokeAt < 700 && !settled);
    }
  });
  void fine; void lum; void parseColor;
}
