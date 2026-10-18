/**
 * Stop-motion: the page is a miniature set shot one exposure at a time. One camera is locked off on a stage; every
 * section is a set (a painted-card wall, a floor, and a cast of felt, card and clay pieces), and the scroll is the
 * animator's hand on the shutter: every few pixels is one exposure, the world holds perfectly still between exposures,
 * and nothing moves when you stop. Poses change on twos (a new pose every second exposure), the picture is never
 * taken faster than 12 times a second, and the clay letters, the felt and the props boil a little with every exposure,
 * the way surfaces shift when a hand has touched them. Between sections the set is struck and dressed: the cast is
 * lifted away in jumpy steps, the new wall drops in, the floor slides across, and the new cast is placed piece by
 * piece. Reversing the scroll runs the film backwards, frame for frame. Inside a set the scroll keeps shooting its
 * business (the speaker steps forward, the peg hops to the next stone, the cupboard doors open, the film strip
 * advances). The pointer is the animator's hand: a click or tap pokes a piece and it hops, a piece with no copy on it
 * can be picked up and posed, and the onion-skin switch shows where each moving piece stood in the last exposure.
 * theme.art becomes a felt puppet whose frames are replaced one exposure at a time.
 * Reduced motion: no stage, no counting; each set is the finished tableau the CSS draws on its own.
 * Research: docs/styles/styles-28-29.md, section 1.
 */
import { $, $$, chars, onFrame, reduced } from "./_kit";
import { loadArt, type ArtFrames } from "./_art";

const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const hash = (a: number, b: number) => {
  let x = Math.imul(a ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul((b | 0) + 0x7f4a7c15, 0xc2b2ae35);
  x ^= x >>> 15; x = Math.imul(x, 0x2c1b3c6d); x ^= x >>> 12; x = Math.imul(x, 0x297a2d39); x ^= x >>> 15;
  return ((x >>> 0) / 4294967296) * 2 - 1;   // -1 .. 1
};
/** Position of el inside root from layout alone (offsetLeft/Top), so poses (transforms) never move it. */
function offsetIn(el: HTMLElement, root: HTMLElement) {
  let x = 0, y = 0, n: HTMLElement | null = el;
  while (n && n !== root) { x += n.offsetLeft; y += n.offsetTop; n = n.offsetParent as HTMLElement | null; }
  return { x, y, w: el.offsetWidth, h: el.offsetHeight };
}
const PRE = 8;        // exposures in which the old cast is lifted away
const FLATS = 12;     // exposures in which the new wall and floor arrive
const ARR = 26;       // exposures over which the new cast is placed
const INTRO = ARR;   // exposures the clock shoots by itself on load, so the first set is already standing
const SHOT = 83;      // ms: the picture is never taken faster than 12 a second

interface Pose { x?: number; y?: number; r?: number; sx?: number; sy?: number }
// Arrival poses, one per two exposures (on twos). x and y are fractions of the screen, r is degrees; the last pose is rest.
const IN: Record<string, Pose[]> = {
  drop: [{ y: -0.95, r: -7 }, { y: -0.6, r: 5 }, { y: -0.28, r: -3 }, { y: -0.07, r: 2 }, { y: 0.012, r: -1, sx: 1.05, sy: 0.93 }, {}],
  "slide-l": [{ x: -0.55, r: -3 }, { x: -0.34, r: 2 }, { x: -0.17, r: -1.5 }, { x: -0.05, r: 1 }, { x: 0.012, sx: 1.03, sy: 0.97 }, {}],
  "slide-r": [{ x: 0.55, r: 3 }, { x: 0.34, r: -2 }, { x: 0.17, r: 1.5 }, { x: 0.05, r: -1 }, { x: -0.012, sx: 1.03, sy: 0.97 }, {}],
  rise: [{ y: 0.6 }, { y: 0.36, r: 1.5 }, { y: 0.16, r: -1.5 }, { y: 0.045, r: 1 }, { y: -0.012, sx: 0.97, sy: 1.04 }, {}],
  pop: [{ sx: 0.15, sy: 0.15, r: -8 }, { sx: 0.62, sy: 0.7, r: 6 }, { sx: 1.16, sy: 1.12, r: -3 }, { sx: 0.93, sy: 0.9, r: 2 }, { sx: 1.04, sy: 1.05, r: -1 }, {}],
  hang: [{ y: -0.4, r: -22 }, { y: -0.16, r: 15 }, { y: -0.03, r: -9 }, { r: 5 }, { r: -2 }, {}],
};
const OUT: Pose[] = [{}, { y: -0.035, r: 3 }, { y: -0.17, r: -4 }, { y: -0.43, r: 5 }, { y: -0.95, r: -6 }];
const WALL: Pose[] = [{ y: -1.02 }, { y: -0.64 }, { y: -0.31 }, { y: -0.09 }, { y: 0.018 }, {}];
const FLOOR: Pose[] = [{ x: 1.02 }, { x: 0.64 }, { x: 0.31 }, { x: 0.09 }, { x: -0.018 }, {}];
// A hop (a poke, or a card stepping forward): anticipation, lift, apex, fall, land, settle. px / scale.
const HOP: Pose[] = [{ sx: 1.04, sy: 0.93 }, { y: -22, sx: 0.97, sy: 1.05 }, { y: -34, sy: 1.03 }, { y: -13 }, { sx: 1.05, sy: 0.92 }, {}];
const SWING = [-9, 7, -5, 3.2, -1.6, 0];   // a hung piece, poked: degrees about its pin

interface Piece {
  el: HTMLElement; anim: string; delay: number; id: number; kind: string;
  letters: HTMLElement[]; amp: number; grab: boolean;
  vis: boolean; key: string; restS: number; pokeAt: number; poke: "hop" | "swing" | "";
  ux: number; uy: number; held: boolean; top: number; late: number; hop: Pose | null;
}
interface SetX {
  el: HTMLElement; kind: string; idx: number; wall: HTMLElement | null; floor: HTMLElement | null; cast: HTMLElement;
  pieces: Piece[]; S: number; A: number; hold0: number; holdLen: number; end: number; h: number; overflow: number; panFrom: number; panLen: number;
  mech: (E: number, set: SetX) => void; shown: boolean; spikes: HTMLElement[]; id: string;
}
interface Run { root: HTMLElement; stage: HTMLElement; sets: SetX[]; top: number; total: number }

export default function start() {
  const main = $<HTMLElement>("main");
  if (!main || !$(".sm-set", main)) return;
  const html = document.documentElement;
  // ------------------------------------------------------------ the puppet: theme.art as felt, a new frame each exposure
  const puppets = new Map<HTMLElement, HTMLCanvasElement>();
  let art: ArtFrames | null = null;
  loadArt().then((a) => { art = a; if (reduced) puppets.forEach((c) => drawPuppet(c, 0)); else dirty = true; });
  $$<HTMLElement>("[data-sm-art]").forEach((p) => { const c = $<HTMLCanvasElement>("canvas", p); if (c) puppets.set(p, c); });
  // The picture is cut from layers of felt: each art frame is classified once (thick regions become felt in four tones by
  // brightness, thin soft wisps become cotton wool, a dark hole the felt encloses becomes dark felt), and every exposure
  // only redraws the boiling edge. Nothing here is specific to one picture.
  interface Cls { kind: Uint8Array; lit: Float32Array; edge: Uint8Array }
  const clsCache = new Map<number, Cls>();
  const FELT: [number, number, number][] = [[98, 63, 37], [178, 129, 79], [237, 209, 161], [252, 241, 216]];
  function boxMin(src: Uint8Array, w: number, h: number, r: number, max = false): Uint8Array {
    const tmp = new Uint8Array(w * h), out = new Uint8Array(w * h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      let v = max ? 0 : 1;
      for (let k = -r; k <= r; k++) { const xx = x + k; const t = xx < 0 || xx >= w ? (max ? 0 : 0) : src[y * w + xx]; v = max ? (t > v ? t : v) : (t < v ? t : v); }
      tmp[y * w + x] = v;
    }
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      let v = max ? 0 : 1;
      for (let k = -r; k <= r; k++) { const yy = y + k; const t = yy < 0 || yy >= h ? 0 : tmp[yy * w + x]; v = max ? (t > v ? t : v) : (t < v ? t : v); }
      out[y * w + x] = v;
    }
    return out;
  }
  function classify(a: ArtFrames, f: number): Cls {
    const hit = clsCache.get(f);
    if (hit) return hit;
    const m = a.mask[f], w = a.w, h = a.h;
    const u = new Float32Array(w * h);
    for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      u[i] = (m[i] * 2 + m[i - 1] + m[i + 1] + m[i - w] + m[i + w] + m[i - w - 1] + m[i - w + 1] + m[i + w - 1] + m[i + w + 1]) / 10;
    }
    const sol = new Uint8Array(w * h);
    for (let i = 0; i < w * h; i++) sol[i] = u[i] > 0.12 ? 1 : 0;
    const r = Math.max(4, Math.round(w * 0.055));
    const thick = boxMin(boxMin(sol, w, h, r), w, h, r, true);
    const kind = new Uint8Array(w * h), lit = new Float32Array(w * h), edge = new Uint8Array(w * h);
    for (let i = 0; i < w * h; i++) {
      if (!sol[i]) continue;
      if (!thick[i]) { kind[i] = 5; continue; }
      const v = u[i];
      kind[i] = v > 0.84 ? 4 : v > 0.62 ? 3 : v > 0.38 ? 2 : 1;
    }
    // a dark hole the felt encloses (the coffee in a cup) is dark felt
    const seen = new Uint8Array(w * h), st: number[] = [];
    const push = (i: number) => { if (!seen[i] && !sol[i]) { seen[i] = 1; st.push(i); } };
    for (let x = 0; x < w; x++) { push(x); push((h - 1) * w + x); }
    for (let y = 0; y < h; y++) { push(y * w); push(y * w + w - 1); }
    while (st.length) { const i = st.pop()!, x = i % w, y = (i / w) | 0; if (x > 0) push(i - 1); if (x < w - 1) push(i + 1); if (y > 0) push(i - w); if (y < h - 1) push(i + w); }
    for (let i = 0; i < w * h; i++) if (!sol[i] && !seen[i]) kind[i] = 6;
    for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      lit[i] = u[i - w - 1] - u[i + w + 1];
      if (kind[i] && kind[i] !== 5 && (!kind[i - 1] || !kind[i + 1] || !kind[i - w] || !kind[i + w])) edge[i] = 1;
    }
    const c = { kind, lit, edge };
    clsCache.set(f, c);
    return c;
  }
  function drawPuppet(c: HTMLCanvasElement, E: number) {
    if (!art) return;
    const frame = ((Math.floor(E / 2) % art.n) + art.n) % art.n;
    const cl = classify(art, frame);
    const w = art.w, h = art.h;
    if (c.width !== w) { c.width = w; c.height = h; }
    const ctx = c.getContext("2d")!;
    const img = ctx.createImageData(w, h);
    const d = img.data, seed = E | 0;
    for (let i = 0; i < w * h; i++) {
      const k = cl.kind[i];
      const o = i * 4, x = i % w, y = (i / w) | 0;
      // the patch is cut with scissors: its border wavers by a pixel or two, differently each exposure
      const bx = Math.min(x, w - 1 - x, y, h - 1 - y);
      if (bx < 4 && hash(i * 3, seed + 2) * 0.5 + 0.5 > (bx + 1) / 5) continue;
      let r = 34, g = 24, b = 17;                       // the dark ground felt
      let a = 255;
      if (k === 6) { r = 70; g = 41; b = 25; }
      else if (k >= 1 && k <= 4) { [r, g, b] = FELT[k - 1]; }
      const lit = k ? clamp(0.9 + cl.lit[i] * 0.45 + hash(i * 7, 3) * 0.04, 0.5, 1.1) : 1 + hash(i * 7, 3) * 0.05;
      r = Math.min(255, r * lit); g = Math.min(255, g * lit); b = Math.min(255, b * lit);
      if (k === 5) {
        // cotton wool laid over the felt: soft tufts, different every exposure
        const t = hash((x >> 1) * 977 + (y >> 1) * 31, seed + 5) * 0.5 + 0.5;
        const q = clamp(0.5 + t * 0.7 - 0.25, 0, 1);
        r = r + (253 - r) * q; g = g + (249 - g) * q; b = b + (240 - b) * q;
      }
      d[o] = r; d[o + 1] = g; d[o + 2] = b; d[o + 3] = a;
    }
    ctx.putImageData(img, 0, 0);
    // the stitching round the patch
    ctx.save();
    ctx.setLineDash([5, 4]);
    ctx.lineDashOffset = (seed % 3);
    ctx.strokeStyle = "rgba(255,244,220,.85)";
    ctx.lineWidth = 1.6;
    ctx.strokeRect(6.5, 6.5, w - 13, h - 13);
    ctx.restore();
  }

  if (reduced) return;                            // the finished tableaux are the reduced-motion page (the felt puppet is drawn once, above)
  html.classList.add("sm-live");
  const phoneQ = matchMedia("(max-width: 760px)");

  // ------------------------------------------------------------ bind runs of sets into stages; everything else is loose
  const blocks = [...main.children] as HTMLElement[];
  const setOf = (el: HTMLElement) => (el.matches("section.sm-set") ? el : el.querySelector<HTMLElement>(":scope > section.sm-set"));
  const groups: HTMLElement[][] = [];
  let cur: HTMLElement[] | null = null;
  for (const b of blocks) {
    if (setOf(b) && !b.querySelector("[data-scene]")) { if (!cur) groups.push((cur = [])); cur.push(b); }
    else { cur = null; b.classList.add("sm-loose"); }
  }
  let pid = 0;
  const runs: Run[] = groups.map((g) => {
    const root = document.createElement("div");
    root.className = "sm-run";
    g[0].before(root);
    const stage = document.createElement("div");
    stage.className = "sm-stage";
    root.appendChild(stage);
    const sets: SetX[] = g.map((b, idx) => {
      const el = setOf(b)!;
      stage.appendChild(el);
      if (b !== el) b.remove();
      el.style.zIndex = String(idx + 1);
      const wall = $<HTMLElement>(".sm-wall", el), floor = $<HTMLElement>(".sm-floor", el), cast = $<HTMLElement>(".sm-cast", el)!;
      // titles: every letter its own piece of clay
      $$<HTMLElement>(".sm-title", el).forEach((t) => { chars(t, "sm-ch"); });
      let order = 0;
      const pieces: Piece[] = $$<HTMLElement>(".sm-p", el).map((p) => {
        const anim = p.dataset.sm || "drop";
        const isFlag = p.classList.contains("sm-flag");
        const t = Number(p.dataset.smT) || 0;
        const delay = isFlag ? (Number(p.style.getPropertyValue("--i")) || 0) * 0.9 : Math.min(order++ * 0.8, 6) + t;
        const letters = p.classList.contains("sm-title") ? $$<HTMLElement>(".sm-ch", p) : [];
        const grab = p.matches(".sm-frame, .sm-puppet, .sm-stand, .sm-easel, .sm-cube, .sm-sun, .sm-flag");
        if (grab) p.classList.add("sm-grab");
        return {
          el: p, anim, delay, id: pid++, kind: isFlag ? "flag" : "", letters, grab,
          amp: letters.length ? 0 : p.matches(".sm-card, .sm-sign, .sm-door, .sm-btn") ? 0.55 : 1, vis: false, key: "", restS: 1,
          pokeAt: -1e9, poke: "", ux: 0, uy: 0, held: false, top: 0, late: 0, hop: null,
        } as Piece;
      });
      return { el, kind: el.dataset.kind || "", idx, wall, floor, cast, pieces, S: 0, A: 0, hold0: 0, holdLen: 1, end: 0, h: 0, overflow: 0, panFrom: 0, panLen: 1,
        mech: () => {}, shown: false, spikes: [], id: el.id || "" } as SetX;
    });
    return { root, stage, sets, top: 0, total: 0 } as Run;
  });
  if (!runs.length) return;

  // ------------------------------------------------------------ the animator's readout
  const hud = $<HTMLElement>(".sm-hud");
  const cue = $<HTMLElement>(".sm-cue");
  const lightEl = $<HTMLElement>(".sm-light");
  const countEl = $<HTMLElement>('[data-sm="count"]');
  const fpsEl = $<HTMLElement>('[data-sm="fps"]');
  const onionBtn = $<HTMLButtonElement>(".sm-onion");
  hud?.removeAttribute("hidden");
  cue?.removeAttribute("hidden");
  let onion = false;
  onionBtn?.addEventListener("click", () => { onion = !onion; onionBtn.setAttribute("aria-pressed", String(onion)); if (!onion) clearGhosts(); });

  // ------------------------------------------------------------ geometry and the schedule (in exposures)
  let vw = innerWidth, vh = innerHeight, STEP = 36;
  const hopLen = 10;
  function layout() {
    vw = innerWidth; vh = innerHeight;
    STEP = clamp(vh / 22, 26, 42);
    for (const run of runs) {
      let S = 0;
      run.sets.forEach((set, i) => {
        // measure the set at rest: poses are transforms and never change layout
        set.h = set.el.offsetHeight;
        set.overflow = Math.max(0, set.h - vh);
        const base = Number(set.el.dataset.hold) || 5;
        const panLen = set.overflow > 0 ? Math.ceil(set.overflow / (STEP * 1.35)) : 0;
        set.S = S;
        set.A = i === 0 ? 0 : S + PRE + FLATS - 6;
        set.panFrom = set.A + 8;
        set.panLen = Math.max(1, panLen);
        set.hold0 = set.A + ARR;
        set.holdLen = Math.max(base * 2, panLen + 6) + (i === 0 && run === runs[0] ? INTRO : 0);
        set.end = set.hold0 + set.holdLen;
        S = set.end;
        // pieces whose rest position is below the first view arrive when the camera reaches them
        set.pieces.forEach((p) => {
          const o = offsetIn(p.el, set.el);
          p.top = o.y + o.h / 2;
          const below = p.top - vh * 0.82;
          p.late = set.overflow > 0 && below > 0 ? (below / set.overflow) * panLen : 0;
        });
        spikesFor(set);
      });
      run.total = S + 6;
      run.root.style.height = `${(run.total * STEP + vh).toFixed(0)}px`;
    }
    measure();
    dirty = true;
  }
  function measure() { for (const r of runs) r.top = r.root.getBoundingClientRect().top + scrollY; }
  // a run after the first starts placing its cast a little before the stage is pinned, so the arrival is seen
  const lead = (r: Run) => (r === runs[0] ? 0 : vh * 0.4);

  // spike marks: tape crosses on the floor where each prop will stand, which show while the set is empty
  function spikesFor(set: SetX) {
    set.spikes.forEach((s) => s.remove());
    set.spikes = [];
    if (!set.floor) return;
    const hzY = set.floor.offsetTop;
    for (const p of set.pieces) {
      if (!p.el.matches(".sm-card, .sm-feature, .sm-cube, .sm-stand, .sm-easel, .sm-puppet, .sm-sign")) continue;
      const o = offsetIn(p.el, set.el);
      const s = document.createElement("i");
      s.className = "sm-spike";
      const y = clamp(o.y + o.h - 6, hzY + 14, set.h - 14);
      s.style.left = `${(o.x + o.w / 2).toFixed(0)}px`;
      s.style.top = `${y.toFixed(0)}px`;
      set.el.appendChild(s);
      set.spikes.push(s);
    }
  }

  // ------------------------------------------------------------ mechanisms: what the scroll shoots while a set is open
  for (const run of runs) for (const set of run.sets) set.mech = mechanism(set);

  function hopPose(tau: number): Pose | null {
    if (tau < 0) return null;
    const q = Math.floor(tau / 2);
    return q < HOP.length - 1 ? HOP[q] : null;
  }
  function mechanism(set: SetX): (E: number, s: SetX) => void {
    const el = set.el;
    const pieceOf = (e: Element) => set.pieces.find((p) => p.el === e);
    if (set.kind === "features") {
      const cards = $$<HTMLElement>(".sm-feature", el).map(pieceOf).filter(Boolean) as Piece[];
      const n = cards.length;
      return (E, s) => {
        const h = (E - s.hold0) / s.holdLen;
        const act = h < 0 ? -1 : Math.min(n - 1, Math.floor(h * n));
        cards.forEach((p, i) => {
          p.restS = act === i && n > 1 ? 1.06 : 1;
          p.el.classList.toggle("is-off", act >= 0 && act !== i && n > 1);
          // the one that steps forward hops as it does
          const t0 = s.hold0 + (i / n) * s.holdLen;
          p.hop = act >= 0 && i === act ? hopPose(E - t0) : null;
        });
      };
    }
    if (set.kind === "product") {
      const opts = $$<HTMLElement>(".ss-app__opt", el);
      return (E, s) => {
        if (opts.length < 2) return;
        const h = clamp((E - s.hold0) / s.holdLen);
        const k = Math.min(opts.length - 1, Math.floor(h * opts.length));
        opts.forEach((o, i) => o.classList.toggle("is-on", i === k));
      };
    }
    if (set.kind === "timeline") {
      const stones = $$<HTMLElement>(".sm-stone", el);
      const peg = $<HTMLElement>(".sm-peg", el);
      const n = stones.length;
      let pts: { x: number; y: number }[] = [];
      const place = () => { pts = stones.map((s) => { const o = offsetIn(s, set.cast); return { x: o.x + o.w / 2, y: o.y + o.h * 0.3 }; }); };
      return (E, s) => {
        if (!peg || !n) return;
        place();
        const h = (E - s.hold0) / s.holdLen;
        const cur = h < 0 ? 0 : Math.min(n - 1, Math.floor(h * n));
        const t0 = s.hold0 + (cur / n) * s.holdLen;
        const tau = E - t0;
        const from = Math.max(0, cur - 1);
        const to = cur;
        let x = pts[to].x, y = pts[to].y, sx = 1, sy = 1, lift = 0;
        if (cur > 0 && tau < 8) {
          const q = Math.floor(tau / 2);   // four poses: crouch, leap, fall, land
          const f = [0.0, 0.34, 0.72, 1][q];
          x = pts[from].x + (pts[to].x - pts[from].x) * f;
          y = pts[from].y + (pts[to].y - pts[from].y) * f;
          lift = [0, 38, 38, 0][q]; sx = [1.08, 0.94, 0.96, 1.06][q]; sy = [0.9, 1.08, 1.05, 0.92][q];
        }
        const pc = pieceOf(peg);
        if (!pc) return;
        peg.style.left = `${(x - peg.offsetWidth / 2).toFixed(1)}px`;
        peg.style.top = `${(y - peg.offsetHeight - lift).toFixed(1)}px`;
        pc.hop = { sx, sy };
      };
    }
    if (set.kind === "faq") {
      const doors = $$<HTMLDetailsElement>("details.sm-door", el);
      const n = doors.length;
      let touched = false;
      const openAt = new Map<HTMLDetailsElement, number>();
      doors.forEach((d) => {
        d.addEventListener("toggle", () => { if (d.open) openAt.set(d, lastShown); else openAt.delete(d); });
        d.querySelector("summary")?.addEventListener("click", () => { touched = true; });
      });
      let last = -1;
      return (E, s) => {
        const h = (E - s.hold0) / s.holdLen;
        if (!touched) {
          const k = h < 0 ? 0 : Math.floor(h * n + 0.4);
          if (k !== last) { last = k; doors.forEach((d, i) => { const want = i < k; if (d.open !== want) { d.open = want; if (want) openAt.set(d, E); else openAt.delete(d); } }); }
        }
        doors.forEach((d) => {
          if (!d.open) { d.style.removeProperty("--open"); return; }
          const t0 = openAt.get(d);
          const q = t0 === undefined ? 5 : Math.floor((E - t0) / 2);
          d.style.setProperty("--open", String([0.34, 0.67, 1][clamp(q, 0, 2)]));
        });
      };
    }
    if (set.kind === "strip") {
      const reel = $<HTMLElement>(".sm-film__reel", el);
      const frames = $$<HTMLElement>(".sm-frame35", el);
      return (E, s) => {
        if (!reel || !frames.length) return;
        const stride = frames[0].offsetWidth + 16;
        const room = reel.scrollWidth - reel.parentElement!.clientWidth + 40;
        const maxShift = Math.max(0, Math.ceil(room / stride));
        const h = clamp((E - s.hold0) / s.holdLen);
        const k = Math.round(h * maxShift);
        const x = -Math.min(room, k * stride);
        const v = `${x.toFixed(0)}px`;
        if (reel.dataset.x !== v) { reel.dataset.x = v; reel.style.translate = `${v} 0`; }
      };
    }
    if (set.kind === "orbit") {
      const ring = $<HTMLElement>(".sm-orbit__ring", el);
      return (E, s) => {
        if (!ring) return;
        const h = clamp((E - s.hold0) / s.holdLen);
        const n = ring.children.length || 1;
        const step = 360 / n;
        const deg = Math.round(h * n * 0.7) * step * 0.5;
        ring.style.setProperty("--rot", `${deg}deg`);
      };
    }
    return () => {};
  }
  let lastShown = 0;

  // ------------------------------------------------------------ the exposure clock
  let shownE = -1, shownRun = -1, lastShot = 0, dirty = true;
  let introE = 0, introStart = -1;
  const introDone = scrollY > 40;
  const pokes = new Set<Piece>();
  let lastPokeFrame = -1;

  function poseOf(tab: Pose[], q: number): Pose { return tab[Math.min(tab.length - 1, Math.max(0, q))]; }

  function applyPiece(set: SetX, p: Piece, E: number, next: SetX | null) {
    const el = p.el;
    const tin = E - (set.A + p.delay + p.late);
    const tout = next ? E - (next.S + (set.pieces.length - 1 - set.pieces.indexOf(p)) * 0.25) : -1;
    let show = tin >= 0;
    let x = 0, y = 0, r = 0, sx = 1, sy = 1;
    let moving = false;
    if (tout >= 0 && next) {
      const q = Math.floor(tout / 2);
      if (q >= OUT.length) show = false;
      else { const o = OUT[q]; y = (o.y || 0) * vh; r = o.r || 0; moving = q > 0; }
    } else if (tin >= 0) {
      const tab = IN[p.anim] || IN.drop;
      const q = Math.floor(tin / 2);
      if (q < tab.length - 1) {
        const o = poseOf(tab, q);
        x = (o.x || 0) * vw; y = (o.y || 0) * vh; r = o.r || 0; sx = o.sx || 1; sy = o.sy || 1; moving = true;
      }
    }
    if (!show) { if (p.vis) { p.vis = false; el.classList.remove("sm-on"); } return; }
    if (p.letters.length) { x = y = r = 0; sx = sy = 1; }   // the clay letters move, the heading's box stays
    // a hop (a scroll step or a poke) rides on top
    let hp: Pose | null = p.hop;
    if (p.poke) {
      const q = Math.floor(Math.floor((performance.now() - p.pokeAt) / SHOT) / 2);
      if (p.poke === "hop") { hp = q < HOP.length - 1 ? HOP[q] : null; if (!hp) p.poke = ""; }
      else if (q < SWING.length - 1) { r += SWING[q]; moving = true; } else p.poke = "";
    }
    if (hp) { y += (hp.y || 0) * (p.kind === "flag" ? 0.5 : 1); sx *= hp.sx || 1; sy *= hp.sy || 1; moving = moving || !!hp.y; }
    sx *= p.restS; sy *= p.restS;
    // the hand-made part: every exposure the piece is a hair off where it was, more while it is being moved
    const a = moving ? 2.4 * p.amp : 0;
    if (a > 0) { x += hash(p.id, E * 3 + 1) * a; y += hash(p.id, E * 3 + 2) * a; r += hash(p.id, E * 3 + 3) * a * 0.5; }
    x += p.ux; y += p.uy;
    if (!p.vis) { p.vis = true; el.classList.add("sm-on"); }
    const key = `${x.toFixed(1)}|${y.toFixed(1)}|${r.toFixed(2)}|${sx.toFixed(3)}|${sy.toFixed(3)}`;
    if (key !== p.key) {
      p.key = key;
      const s = el.style;
      s.setProperty("--px", `${x.toFixed(1)}px`); s.setProperty("--py", `${y.toFixed(1)}px`);
      s.setProperty("--pr", `${r.toFixed(2)}deg`); s.setProperty("--psx", sx.toFixed(3)); s.setProperty("--psy", sy.toFixed(3));
    }
    // letters of clay: placed one by one, then forever a little alive
    if (p.letters.length) {
      const n = p.letters.length;
      p.letters.forEach((l, i) => {
        const lt = tin - Math.min(i * 0.45, 7);
        let lx = 0, ly = 0, lr = 0, lsx = 1, lsy = 1, lv = lt >= 0;
        let amp = 0.55;
        if (tout >= 0 && next) {
          const q = Math.max(0, Math.floor((tout - (n - 1 - i) * 0.12) / 2));
          if (q >= OUT.length) lv = false; else { const o = OUT[q]; ly = (o.y || 0) * vh; lr = (o.r || 0) * 1.5; amp = 1.6; }
        } else if (lt >= 0) {
          const q = Math.floor(lt / 2);
          if (q < IN.drop.length - 1) { const o = IN.drop[q]; ly = (o.y || 0) * vh * 0.6; lr = (o.r || 0) * 1.4; lsx = o.sx || 1; lsy = o.sy || 1; amp = 2.2; }
        }
        l.style.visibility = lv ? "inherit" : "hidden";
        if (lv) {
          lx += hash(p.id * 131 + i, E * 5 + 1) * amp; ly += hash(p.id * 131 + i, E * 5 + 2) * amp;
          lr += hash(p.id * 131 + i, E * 5 + 3) * amp * 0.9;
          l.style.setProperty("--cx", `${lx.toFixed(1)}px`); l.style.setProperty("--cy", `${ly.toFixed(1)}px`);
          l.style.setProperty("--cr", `${lr.toFixed(2)}deg`);
          l.style.scale = lsx === 1 && lsy === 1 ? "" : `${lsx} ${lsy}`;
        }
      });
    }
  }

  function renderRun(run: Run, E: number) {
    run.sets.forEach((set, i) => {
      const next = run.sets[i + 1] || null;
      // on the stage from the moment its wall starts to arrive until the next set's wall has landed over it
      const show = i === 0 ? E >= 0 : E >= set.S + PRE - 2;
      const gone = next ? E >= next.S + PRE + FLATS : false;
      const vis = show && !gone;
      if (vis !== set.shown) { set.shown = vis; set.el.style.visibility = vis ? "visible" : "hidden"; }
      if (!vis) return;
      // the flats: the wall drops in, the floor slides across behind it, spike marks show where the cast will stand
      if (i > 0) {
        const tw = E - (set.S + PRE - 2);
        const q = Math.floor(tw / 2);
        const w = poseOf(WALL, q), f = poseOf(FLOOR, q - 1);
        if (set.wall) set.wall.style.translate = q >= WALL.length - 1 ? "" : `0 ${((w.y || 0) * vh).toFixed(0)}px`;
        if (set.floor) set.floor.style.translate = q - 1 >= FLOOR.length - 1 ? "" : `${((f.x || 0) * vw).toFixed(0)}px 0`;
        const on = q >= FLOOR.length && tw < FLATS + 12;
        set.spikes.forEach((s) => { s.style.opacity = on ? "1" : "0"; });
      } else set.spikes.forEach((s) => { s.style.opacity = "0"; });
      // the camera: a set taller than the screen is panned down, on twos, while it is open
      const pe = 2 * Math.floor(E / 2);
      const pan = set.overflow > 0 ? -Math.round(set.overflow * clamp((pe - set.panFrom) / set.panLen)) : 0;
      set.el.style.translate = pan ? `0 ${pan}px` : "";
      set.mech(E, set);
      set.pieces.forEach((p) => applyPiece(set, p, E, next));
    });
  }

  // ------------------------------------------------------------ onion skin: where each moving piece stood in the last exposure
  const ghosts: HTMLElement[] = [];
  function clearGhosts() { ghosts.forEach((g) => g.remove()); ghosts.length = 0; }
  function showGhosts(run: Run, before: Map<Piece, DOMRect>) {
    clearGhosts();
    const sr = run.stage.getBoundingClientRect();
    for (const set of run.sets) {
      if (!set.shown) continue;
      for (const p of set.pieces) {
        const b = before.get(p);
        if (!b || !p.vis) continue;
        const a = p.el.getBoundingClientRect();
        if (Math.abs(a.left - b.left) + Math.abs(a.top - b.top) < 3 && Math.abs(a.width - b.width) < 3) continue;
        const g = document.createElement("i");
        g.className = "sm-ghost";
        g.style.cssText = `left:${(b.left - sr.left).toFixed(0)}px;top:${(b.top - sr.top).toFixed(0)}px;width:${b.width.toFixed(0)}px;height:${b.height.toFixed(0)}px`;
        run.stage.appendChild(g);
        ghosts.push(g);
      }
    }
  }

  // ------------------------------------------------------------ the pointer is the animator's hand
  function pieceAt(target: EventTarget | null): Piece | null {
    const el = (target as HTMLElement | null)?.closest?.<HTMLElement>(".sm-p");
    if (!el) return null;
    for (const r of runs) for (const s of r.sets) { const p = s.pieces.find((q) => q.el === el); if (p) return p; }
    return null;
  }
  const fine = matchMedia("(pointer: fine)").matches;
  let drag: { p: Piece; x0: number; y0: number; ux0: number; uy0: number; moved: boolean } | null = null;
  function pokePiece(p: Piece) {
    if (performance.now() - p.pokeAt < 700) return;
    p.poke = p.anim === "hang" ? "swing" : "hop";
    p.pokeAt = performance.now();
    pokes.add(p);
    dirty = true;
  }
  main.addEventListener("pointerdown", (e) => {
    const p = pieceAt(e.target);
    if (p && p.grab && e.pointerType === "mouse" && e.button === 0) {
      drag = { p, x0: e.clientX, y0: e.clientY, ux0: p.ux, uy0: p.uy, moved: false };
      p.el.setPointerCapture?.(e.pointerId);
    }
  });
  main.addEventListener("click", (e) => {
    if (drag?.moved) return;
    if ((e.target as HTMLElement).closest("a, button, summary")) return;
    const p = pieceAt(e.target);
    if (p) pokePiece(p);
  });
  addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x0, dy = e.clientY - drag.y0;
    if (!drag.moved && Math.hypot(dx, dy) < 6) return;
    drag.moved = true;
    drag.p.el.classList.add("is-held");
    drag.p.ux = drag.ux0 + dx; drag.p.uy = drag.uy0 + dy;
    dirty = true;
  });
  const endDrag = () => {
    if (!drag) return;
    drag.p.el.classList.remove("is-held");
    setTimeout(() => { drag = null; }, 0);
  };
  addEventListener("pointerup", endDrag);
  addEventListener("pointercancel", endDrag);
  // brushing past a piece with copy on it nudges it one step, the way a hand does
  if (fine) main.addEventListener("pointerover", (e) => {
    const p = pieceAt(e.target);
    if (!p || p.grab || p.kind === "flag") return;
    if ((e.relatedTarget as HTMLElement | null)?.closest?.(".sm-p") === p.el) return;
    if (p.el.matches(".sm-feature, .sm-cube, .sm-pill, .sm-snap, .sm-marble")) pokePiece(p);
  });

  // ------------------------------------------------------------ links open the right set
  function setY(id: string): number | null {
    for (const run of runs) {
      const set = run.sets.find((s) => s.id === id);
      if (set) return Math.round(run.top - lead(run) + (set.hold0 + 2 - (run === runs[0] ? INTRO : 0)) * STEP);
    }
    return null;
  }
  (window as any).__smY = (id: string) => setY(id);   // for review captures
  document.addEventListener("click", (e) => {
    const a = (e.target as HTMLElement).closest<HTMLAnchorElement>('a[href^="#"]');
    if (!a) return;
    const id = a.getAttribute("href")!.slice(1);
    if (!id) return;
    const y = setY(id);
    if (y == null) return;
    e.preventDefault(); e.stopPropagation();
    const from = scrollY, dist = y - from, dur = Math.min(1800, 500 + Math.abs(dist) / vh * 220), t0 = performance.now();
    const step = (now: number) => { const q = clamp((now - t0) / dur); const k = q < 0.5 ? 2 * q * q : 1 - 2 * (1 - q) * (1 - q); scrollTo(0, from + dist * k); if (q < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }, { capture: true });
  // keyboard focus that lands in a set the camera isn't on takes the camera there
  document.addEventListener("focusin", (e) => {
    const set = (e.target as HTMLElement).closest?.<HTMLElement>(".sm-set");
    if (!set) return;
    for (const run of runs) { const s = run.sets.find((x) => x.el === set); if (s && !s.shown) scrollTo(0, Math.round(run.top - lead(run) + (s.hold0 + 1 - (run === runs[0] ? INTRO : 0)) * STEP)); }
  });

  // ------------------------------------------------------------ run
  layout();
  addEventListener("resize", layout);
  phoneQ.addEventListener?.("change", layout);
  document.fonts?.ready.then(() => { layout(); });
  setTimeout(layout, 900);
  addEventListener("load", layout);
  if (location.hash.length > 1) { const y = setY(location.hash.slice(1)); if (y != null) requestAnimationFrame(() => scrollTo(0, y)); }

  const navLinks = $$<HTMLAnchorElement>(".sm-head__nav a");
  let lastScroll = 0, lastY = scrollY, lastId = "";
  onFrame(() => {
    const now = performance.now();
    if (introStart < 0) introStart = now;
    introE = introDone ? INTRO : Math.min(INTRO, Math.floor((now - introStart) / SHOT));
    if (scrollY !== lastY) { lastY = scrollY; lastScroll = now; if (cue) cue.hidden = true; }
    // the exposure the scroll has reached in the run the camera is on (the first set is placed by the clock on load)
    let wantE = -1, wantRun = -1;
    runs.forEach((run, ri) => {
      const local = scrollY - run.top + lead(run);
      if (local > -vh * 1.2 && local < run.total * STEP + vh * 1.2) { wantRun = ri; wantE = Math.max(0, Math.floor(local / STEP)) + (ri === 0 ? introE : 0); }
    });
    if ((wantE !== shownE || wantRun !== shownRun) && now - lastShot >= SHOT) { shownE = wantE; shownRun = wantRun; lastShot = now; dirty = true; }
    const pf = Math.floor(now / SHOT);
    if ((pokes.size || drag?.moved) && pf !== lastPokeFrame) { lastPokeFrame = pf; dirty = true; }
    if (!dirty || shownRun < 0) return;
    dirty = false;
    lastShown = shownE;
    const run = runs[shownRun];
    const before = new Map<Piece, DOMRect>();
    if (onion) for (const set of run.sets) if (set.shown) for (const p of set.pieces) if (p.vis) before.set(p, p.el.getBoundingClientRect());
    // the boil and the lamp are set on their own elements, never on the root: a custom property changed on <html> restyles the whole page
    run.stage.dataset.b = String(((shownE % 4) + 4) % 4);
    lightEl?.style.setProperty("--lamp", (1 + hash(7, shownE) * 0.045).toFixed(3));
    renderRun(run, shownE);
    for (const p of [...pokes]) if (!p.poke) pokes.delete(p);
    puppets.forEach((c, host) => { if (host.classList.contains("sm-on")) drawPuppet(c, shownE); });
    if (onion) showGhosts(run, before); else if (ghosts.length) clearGhosts();
    if (countEl) countEl.textContent = String(Math.max(0, shownE)).padStart(4, "0");
    let on = "";
    for (const s of run.sets) if (s.shown && s.id && shownE >= s.S + PRE) on = s.id;
    if (on !== lastId) { lastId = on; navLinks.forEach((a) => a.classList.toggle("is-on", !!on && a.getAttribute("href") === `#${on}`)); }
  });
  // the readout says when the shutter is idle
  setInterval(() => { if (fpsEl) fpsEl.textContent = performance.now() - lastScroll < 350 ? "on twos" : "held"; }, 200);
}
