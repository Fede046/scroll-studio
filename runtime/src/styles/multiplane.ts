/**
 * Multiplane: Disney's multiplane camera on a page. Every section is a stack of painted glass plates (a sky, far and
 * middle plates, a mist, foreground plates and a fat plate to sweep past) at real distances from the lens, and the
 * words are a plate too. One camera looks down through the stack; scrolling is the crank that moves it. Between
 * sections the camera trucks in through the stack (everything grows by 1/distance, the near plates and the words
 * pass the lens and leave, the next stack's plates emerge from the mist), and the focus is pulled to the plate the
 * words are on, so the others go soft by how far they are from it. Between the items of a list the camera barely
 * moves and a foreground plate (trunks) is swept past at speed, covering the change of words. The pointer trucks
 * the camera a little sideways (near plates slide more than far ones) and, when it rests on the painted glass,
 * pulls focus to that plate. Scrolling is never intercepted: the page keeps its native scroll; the copy planes are
 * fixed over it. Reduced motion: no camera; each section is the still diorama of layered plates the CSS draws.
 * Research: docs/styles/styles-30-31.md, section 2.
 */
import { $, $$, onFrame, reduced } from "./_kit";
import { PCtx, PlateDef, RECIPES } from "./_mp-plates";
import { clamp, colourScript, hash, lerp, rng, smooth, themeColor } from "./_brush";

const mobile = () => innerWidth < 760;
const LEN = 1.2;        // camera travel between two stacks (units: the distance from lens to the words)
const SUB = 0.05;       // camera travel between two items of one list (all of a list together stays under 0.16, so the words never pass a plate)
const K_BLUR = 8;       // how soft a plate goes per unit of 1/distance away from the focus
const smoothAB = smooth;

interface Plate { def: PlateDef; wrap: HTMLElement; sharp: HTMLCanvasElement; soft: HTMLCanvasElement; z: number; state: string; w: number; h: number; offx: number; offy: number; built: boolean; s: number; tx: number; ty: number; d: number; shown: boolean; opa: string }
interface Stack { side: number; g: number; z0: number; z1: number; n: number; plates: Plate[]; builtAt: number; building: boolean; pal: ReturnType<typeof colourScript>[number]; recipe: number }
interface Plane { moved: number; dirty: boolean; rewc: boolean; el: HTMLElement; d0: number; a: number; s: number; vis: boolean; z: number; live: boolean; tx: number; ty: number; blur: number }
interface Beat { el: HTMLElement; group: number; sub: number; n: number; Z: number; R: number; planes: Plane[]; kind: string; label: string }

export default function start() {
  const world = $<HTMLElement>(".mp-world");
  const els = $$<HTMLElement>("main [data-mp]");
  if (!world || !els.length) return;
  const root = document.documentElement;
  try { run(world, els, root); } catch (e) { root.classList.remove("mp-live"); console.warn("multiplane:", e); }
}

function run(world: HTMLElement, els: HTMLElement[], root: HTMLElement) {
  // ------------------------------------------------------------------ the beats and their place on the camera's track
  let group = -1, lastSec: Element | null = null;
  const beats: Beat[] = [];
  const counts = new Map<number, number>();
  els.forEach((el) => {
    const sec = el.closest("section");
    if (sec !== lastSec) { group++; lastSec = sec; }
    counts.set(group, (counts.get(group) || 0) + 1);
    beats.push({ el, group, sub: 0, n: 1, Z: 0, R: 0, planes: [], kind: el.dataset.mp || "", label: "" });
  });
  let z = 0, prevG = -1, sub = 0;
  beats.forEach((b, i) => {
    b.n = counts.get(b.group) || 1;
    if (b.group !== prevG) { z += i === 0 ? 0 : LEN; sub = 0; prevG = b.group; }
    else { sub++; z += Math.min(SUB, 0.16 / Math.max(1, b.n - 1)); }
    b.sub = sub; b.Z = z;
    b.planes = $$<HTMLElement>(".mp-plane", b.el).map((el) => ({ moved: 0, dirty: false, rewc: false, el, d0: Number(el.dataset.mpD || 1), a: 0, s: 1, vis: false, z: 0, live: false, tx: 0, ty: 0, blur: 0 }));
    b.label = (b.el.querySelector("h1, h2, h3, blockquote, summary, .mp-fig") as HTMLElement | null)?.textContent?.trim().replace(/\s+/g, " ").slice(0, 44) || b.kind;
  });
  const nG = group + 1;
  const accent = themeColor("--accent", [236, 160, 92]);
  const pals = colourScript(nG, accent, 0.8, 0.18);
  const siteSeed = Math.floor(hash(document.title.split("").reduce((a, c) => a * 31 + c.charCodeAt(0), 11)) * 4);
  const stacks: Stack[] = [];
  for (let g = 0; g < nG; g++) {
    const mine = beats.filter((b) => b.group === g);
    const sd = mine[0].el.querySelector<HTMLElement>(".mp-copy")?.dataset.side || "c";
    stacks.push({ side: sd === "l" ? -1 : sd === "r" ? 1 : 0, g, z0: mine[0].Z, z1: mine[mine.length - 1].Z, n: mine.length, plates: [], builtAt: 0, building: false, pal: pals[g], recipe: (g + siteSeed) % RECIPES.length });
  }
  // ------------------------------------------------------------------ geometry
  let W = innerWidth, H = innerHeight, rs = 0.7;
  function size() {
    W = innerWidth; H = Math.max(innerHeight, Math.round(screen.height * 0.6));
    rs = mobile() ? Math.min(devicePixelRatio || 1, 2) * 0.58 : Math.min(devicePixelRatio || 1, 1.5) * 0.72;
  }
  size();

  // ------------------------------------------------------------------ the still (reduced motion): each section's plates composed once, at rest
  function still(st: Stack, sec: HTMLElement) {
    const defs = RECIPES[st.recipe](st.pal);
    const cv = document.createElement("canvas");
    const k = Math.min(devicePixelRatio || 1, 1.5) * 0.8;
    cv.width = Math.round(W * k); cv.height = Math.round(H * k); cv.className = "mp-still"; cv.setAttribute("aria-hidden", "true");
    const c = cv.getContext("2d")!; c.scale(k, k);
    defs.forEach((def, i) => {
      const q = drawPlate(st, def, i), s = def.role === "sky" ? 1 : 1 / def.d;
      const m = def.role === "sky" || def.role === "sweep" ? 0 : clamp(Math.abs(1 / def.d - 1) * K_BLUR / 5.5);
      if (def.role === "sweep") return;
      c.save(); c.translate(W / 2 + q.offx * s, H / 2 + q.offy * s); c.scale(s, s);
      c.drawImage(q.sharp, -q.cw / 2, -q.ch / 2, q.cw, q.ch);
      if (m > 0.04) { c.globalAlpha = m; c.drawImage(q.soft, -q.cw / 2, -q.ch / 2, q.cw, q.ch); }
      c.restore();
    });
    sec.insertBefore(cv, sec.firstChild); sec.classList.add("has-still");
  }
  if (reduced) {
    const secs = beats.map((b) => b.el.closest("section") as HTMLElement);
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      const sec = e.target as HTMLElement;
      if (e.isIntersecting && !sec.classList.contains("has-still")) { const g = secs.indexOf(sec); const bg = beats.find((b) => b.el.closest("section") === sec)!; still(stacks[bg.group], sec); void g; }
    }), { rootMargin: "60% 0px" });
    [...new Set(secs)].forEach((sec) => io.observe(sec));
    return;
  }
  root.classList.add("mp-live");

  // ------------------------------------------------------------------ painting the glass (one plate at a time, between frames)
  /** Paint one plate of a stack onto its own canvas (nothing touches the page). */
  function drawPlate(st: Stack, def: PlateDef, idx: number) {
    const dm = def.role === "sky" ? 1 : def.d;
    const cw = Math.round((def.xr - def.xl) * W), ch = Math.round((def.yb - def.yt) * H);
    let r2 = rs; while ((cw * r2 > 3600 || ch * r2 > 3600) && r2 > 0.2) r2 *= 0.8;
    const sharp = document.createElement("canvas");
    sharp.width = Math.max(2, Math.round(cw * r2)); sharp.height = Math.max(2, Math.round(ch * r2));
    const c = sharp.getContext("2d")!;
    c.scale(sharp.width / cw, sharp.height / ch);
    const seed = st.g * 101 + idx * 17 + siteSeed;
    const p: PCtx = {
      ctx: c, cw, ch, W, H, d: dm, pal: st.pal, r: rng(seed), seed, side: st.side,
      X: (xs) => ((xs - 0.5) * dm - def.xl) / (def.xr - def.xl) * cw,
      Y: (ys) => ((ys - 0.5) * dm - def.yt) / (def.yb - def.yt) * ch,
    };
    def.draw(p);
    const soft = document.createElement("canvas");
    const k = def.role === "sky" ? 5 : 6;
    soft.width = Math.max(2, Math.round(sharp.width / k)); soft.height = Math.max(2, Math.round(sharp.height / k));
    const sc = soft.getContext("2d")!; sc.imageSmoothingQuality = "high"; sc.drawImage(sharp, 0, 0, soft.width, soft.height);
    return { sharp, soft, cw, ch, offx: ((def.xl + def.xr) / 2) * W, offy: ((def.yt + def.yb) / 2) * H };
  }
  function paintPlate(st: Stack, def: PlateDef, idx: number): Plate {
    const { sharp, soft, cw, ch, offx, offy } = drawPlate(st, def, idx);
    const wrap = document.createElement("div");
    wrap.className = `mp-plate mp-plate--${def.role}`;
    wrap.style.cssText = `width:${cw}px;height:${ch}px;margin:${-ch / 2}px 0 0 ${-cw / 2}px;`;
    sharp.style.opacity = "0";
    sharp.className = "mp-sharp"; soft.className = "mp-soft";
    wrap.appendChild(sharp); wrap.appendChild(soft);
    world.appendChild(wrap);
    return { def, wrap, sharp, soft, z: -1, state: "", w: cw, h: ch, offx, offy, built: true, s: 1, tx: 0, ty: 0, d: def.d, shown: false, opa: "" };
  }
  function build(st: Stack) {
    if (st.building || st.plates.length) return;
    st.building = true;
    const defs = RECIPES[st.recipe](st.pal);
    let i = 0;
    const step = () => {
      if (i >= defs.length) { st.building = false; st.builtAt = performance.now(); return; }
      st.plates.push(paintPlate(st, defs[i], i)); i++;
      (window.requestIdleCallback ? window.requestIdleCallback(step, { timeout: 120 }) : setTimeout(step, 8));
    };
    step();
  }
  function release(st: Stack) { for (const p of st.plates) p.wrap.remove(); st.plates = []; st.building = false; }

  // ------------------------------------------------------------------ the track: scroll -> where the camera is
  const R: number[] = [];
  function layout() {
    const sy = scrollY;
    beats.forEach((b, i) => { const r = b.el.getBoundingClientRect(); b.R = r.top + sy; R[i] = b.R; });
  }
  /** Words that are taller or wider than the glass are scaled to fit it (the planes are fixed, so nothing may be cut off). */
  function fit() {
    for (const b of beats) for (const pn of b.planes) {
      const c = pn.el.firstElementChild as HTMLElement | null;
      if (!c) continue;
      const h = c.offsetHeight, w = c.offsetWidth;
      const k = Math.min(1, (innerHeight * 0.8) / Math.max(1, h), (innerWidth * 0.94) / Math.max(1, w));
      c.style.setProperty("--fit", k.toFixed(3));
    }
  }
  layout(); fit();
  function phaseAt(y: number): number {
    const n = beats.length;
    if (y <= R[0]) return 0;
    if (y >= R[n - 1]) return n - 1;
    let i = 0; while (i < n - 2 && y >= R[i + 1]) i++;
    const f = (y - R[i]) / Math.max(1, R[i + 1] - R[i]);
    return i + smoothAB(0.38, 0.9, f);
  }
  const zAt = (p: number) => { const i = clamp(Math.floor(p), 0, beats.length - 1), j = Math.min(beats.length - 1, i + 1); return lerp(beats[i].Z, beats[j].Z, p - i); };

  // ------------------------------------------------------------------ the camera: focus, sideways truck, readouts
  let camX = 0, camY = 0, tx = 0, ty = 0, focus = 1, focusTo = 1, rack = 0, rackHold = 0, lastMove = 0;
  const fine = matchMedia("(pointer: fine)").matches;
  let mx = 0, my = 0, overWords = false, dwellDone = 0, restX = 0, restY = 0;
  addEventListener("pointermove", (e) => {
    if (e.pointerType === "touch") return;
    tx = (e.clientX / innerWidth - 0.5) * 2; ty = (e.clientY / innerHeight - 0.5) * 2; lastMove = performance.now();
    mx = e.clientX; my = e.clientY;
    overWords = !!(e.target as HTMLElement).closest?.(".mp-card, .mp-top, a, button, summary, .ss-phone");
    // a rack ends when the pointer leaves the spot it rested on
    if (rack && Math.hypot(mx - restX, my - restY) > 36) { rack = 0; rackHold = 0; }
  }, { passive: true });
  /** The plate under a point of the screen (nearest to the lens first) whose paint is there, or 0. */
  function plateAt(x: number, y: number): number {
    let best = 0, bestD = 1e9;
    for (const st of stacks) for (const pl of st.plates) {
      if (!pl.shown || pl.def.role === "sky" || pl.def.role === "sweep") continue;
      const lx = (x - W / 2 - pl.tx) / pl.s + pl.w / 2, ly = (y - H / 2 - pl.ty) / pl.s + pl.h / 2;
      if (lx < 0 || ly < 0 || lx >= pl.w || ly >= pl.h || pl.d >= bestD) continue;
      try {
        const k = pl.sharp.width / pl.w, c = pl.sharp.getContext("2d")!;
        if (c.getImageData(Math.floor(lx * k), Math.floor(ly * k), 1, 1).data[3] > 90) { best = pl.d; bestD = pl.d; }
      } catch { /* canvas not readable */ }
    }
    return best;
  }

  const gauge = $<HTMLElement>(".mp-gauge");
  const gTicks = new Map<string, HTMLElement>();
  ["near", "text", "mid", "far"].forEach((role) => { const t = document.createElement("i"); t.className = "mp-tick"; t.dataset.role = role; gauge?.appendChild(t); gTicks.set(role, t); });
  const gFocus = document.createElement("b"); gFocus.className = "mp-focus"; gauge?.appendChild(gFocus);
  const hudSet = $<HTMLElement>("[data-mp-set]"), hudTruck = $<HTMLElement>("[data-mp-truck]"), hudFocus = $<HTMLElement>("[data-mp-focus]");

  // a link focused in a plane that is not on show brings its beat to the lens
  addEventListener("focusin", (e) => {
    const t = e.target as HTMLElement;
    const b = beats.find((x) => x.el.contains(t));
    if (!b) return;
    const cur = Math.round(phaseAt(scrollY));
    if (beats[cur] !== b) scrollTo({ top: b.R + 2, behavior: "auto" });
  });

  // scenes the page carries sit above the glass: the stacks step aside while one is on screen
  const scenes = $$<HTMLElement>("main [data-scene]");
  if (scenes.length) {
    const seen = new Set<Element>();
    const io = new IntersectionObserver((es) => { es.forEach((e) => { e.isIntersecting ? seen.add(e.target) : seen.delete(e.target); }); root.classList.toggle("mp-scene", seen.size > 0); }, { threshold: 0.04 });
    scenes.forEach((s) => io.observe(s));
  }

  // ------------------------------------------------------------------ the frame
  const fade = (d: number, rest: number) => {
    // a plate is solid near its resting distance, emerges from the mist beyond it and is gone before it reaches the lens
    const k = d / rest;
    return (k > 1 ? 1 - smoothAB(1.1, 1.5, k) : smoothAB(0.38, 0.8, k));
  };
  let layoutAt = 0, hudAt = 0, lastP = 0;
  size(); layout();
  let resizeT = 0;
  addEventListener("resize", () => {
    clearTimeout(resizeT);
    resizeT = window.setTimeout(() => {
      if (Math.abs(innerWidth - W) < 2 && Math.abs(innerHeight - H) < 140) { layout(); return; }
      size(); layout(); fit(); for (const st of stacks) release(st);
    }, 180);
  });
  addEventListener("load", () => { layout(); fit(); });
  (window as any).__mp = { plateAt, stacks, get state() { return { p: lastP, focus, beats: beats.length, stacks: stacks.map((s) => s.plates.length) }; } };

  onFrame(({ y, t, dt }) => {
    if (t - layoutAt > 1.2) { layoutAt = t; layout(); }
    const p = phaseAt(y); lastP = p;
    const cz = zAt(p);
    const i = clamp(Math.floor(p + 1e-6), 0, beats.length - 1), j = Math.min(beats.length - 1, i + 1);
    const fp = p - i;
    const dolly = beats[i].group !== beats[j].group;
    const here = clamp(Math.round(p), 0, beats.length - 1);
    const stHere = beats[here].group;

    // sideways truck: the pointer moves the camera (a little); with no pointer it drifts, so the glass is never dead still
    const drift = fine && performance.now() - lastMove < 4000 ? 0 : 1;
    const gx = (fine ? tx : 0) * (1 - drift) + Math.sin(t * 0.31) * 0.28 * drift, gy = (fine ? ty : 0) * (1 - drift) + Math.cos(t * 0.23) * 0.16 * drift;
    camX += (gx - camX) * Math.min(1, dt * 3); camY += (gy - camY) * Math.min(1, dt * 3);
    const kx = camX * W * 0.05, ky = camY * H * 0.03;

    // focus: pulled to the plane the words are on (it lags a little, which is the pull); a rack to a plate overrides it
    const owner = fp < 0.5 ? beats[i] : beats[j];
    focusTo = 1 + (owner.Z - cz);
    if (fine && !rack && lastMove && performance.now() - lastMove > 600 && dwellDone !== lastMove && !overWords && !root.classList.contains("mp-scene")) {
      dwellDone = lastMove;
      const d = plateAt(mx, my);
      if (d) { rack = d; restX = mx; restY = my; rackHold = 0; }
    }
    if (rackHold > 0) { rackHold -= dt; if (rackHold <= 0) rack = 0; }
    const aim = rack ? rack : focusTo;
    focus += (aim - focus) * Math.min(1, dt * (rack ? 5 : 4.5));
    const invF = 1 / Math.max(0.2, focus);

    // ---- stacks: build the ones the camera is near, drop the ones it left
    for (const st of stacks) {
      const near = Math.abs(cz - (cz < st.z0 ? st.z0 : cz > st.z1 ? st.z1 : cz)) < 2.4 || st.g === stHere;
      if (near && !st.plates.length && !st.building) build(st);
      else if (!near && st.plates.length && Math.abs(st.g - stHere) > 1) release(st);
      if (!st.plates.length) continue;
      const base = st.z0;
      for (const pl of st.plates) {
        const def = pl.def, built = performance.now() - st.builtAt;
        let d = def.d - (cz - base), a = 1, s = 1 / d, px = kx * (1 / d), py = ky * (1 / d), vis = true;
        let zi = 10 + Math.round((6 - d) * 100);
        if (def.role === "sky") {
          s = 1; px = kx * 0.2; py = ky * 0.2; zi = 10 + st.g;
          a = st.g === 0 ? 1 : smoothAB(st.z0 - 0.75 * LEN, st.z0 - 0.15 * LEN, cz);
          d = 6;
        } else if (def.role === "sweep") {
          // the fat foreground plate: swept across the glass while a list changes its words, covering the change
          const sw = (beats[i].group === st.g && beats[j].group === st.g && !dolly) ? smoothAB(0.12, 0.88, fp) : -1;
          if (sw < 0) { vis = false; a = 0; }
          else {
            const dir = (i % 2 ? -1 : 1), span = (def.xr - def.xl) * W * s * 0.5 + W * 0.5 + 40;
            px += dir * (1 - 2 * sw) * span; a = 1;
          }
        } else if (st.g === stHere || Math.abs(cz - base) < 2.3) {
          a = fade(d, def.d);
          if (def.role === "far" || def.role === "mid") { const ahead = d > def.d; a = ahead ? 1 - smoothAB(def.d + 0.18, def.d + 0.75, d) : smoothAB(0.38, 0.7, d); }
        } else vis = false;
        if (d < 0.22) vis = false;
        a *= smoothAB(0, 700, built);
        pl.wrap.style.visibility = vis && a > 0.004 ? "visible" : "hidden";
        pl.shown = vis && a > 0.3;
        if (!vis || a <= 0.004) continue;
        pl.s = s; pl.tx = pl.offx * s + px; pl.ty = pl.offy * s + py; pl.d = d;
        const tf = `translate(${pl.tx.toFixed(1)}px,${pl.ty.toFixed(1)}px) scale(${s.toFixed(4)})`;
        pl.wrap.style.transform = tf;
        // opacity goes on the canvases themselves: on the wrapper it would make the compositor draw each plate into a
        // surface its full (huge) size first
        const as = a.toFixed(2);
        if (as !== pl.opa) { pl.opa = as; pl.sharp.style.opacity = as; if (pl.def.role === "sky") pl.soft.style.opacity = "0"; }
        if (zi !== pl.z) { pl.wrap.style.zIndex = String(zi); pl.z = zi; }
        // depth of field: the farther a plate is from the plane in focus, the more of its soft twin shows
        if (def.role !== "sky") {
          const m = clamp(Math.abs(1 / d - invF) * K_BLUR / 5.5);
          const sm = m < 0.04 ? "0" : (m * a).toFixed(2);
          if (sm !== pl.state) { pl.soft.style.opacity = sm; pl.state = sm; }
        }
      }
    }

    // ---- the words: planes on the glass, each at its own distance
    beats.forEach((b, bi) => {
      const near = bi === i || bi === j || (bi === here);
      for (const pn of b.planes) {
        // planes off the lens are fully transparent and not layers (so they cost nothing) but stay in the tab order:
        // a link focused in one brings its beat to the lens (see focusin)
        if (!near) { if (pn.vis) { pn.el.style.opacity = "0"; pn.el.style.willChange = "auto"; pn.vis = false; pn.live = false; pn.rewc = false; pn.dirty = false; pn.el.classList.remove("is-live"); } continue; }
        const d = pn.d0 + (b.Z - cz);
        let a: number, s: number, x = kx / pn.d0 * 0.6, yy = ky / pn.d0 * 0.6;
        if (dolly) {
          const k = d / pn.d0;
          s = 1 / Math.max(0.3, k);
          a = k > 1 ? 1 - smoothAB(1.08, 1.5, k) : smoothAB(0.42, 0.82, k);
        } else {
          s = 1 / Math.max(0.5, d / pn.d0);
          // a swap inside a stack: the old words leave as the plate sweeps across, the new ones arrive behind it
          const sw = smoothAB(0.12, 0.88, fp);
          a = bi === i ? 1 - smoothAB(0.38, 0.52, sw) : smoothAB(0.48, 0.62, sw);
          if (i === j) a = 1;
          x += bi === i ? -sw * W * 0.04 : (1 - sw) * W * 0.04;
        }
        const tfm = `translate(${x.toFixed(1)}px,${yy.toFixed(1)}px) scale(${s.toFixed(4)})`;
        // defocus: only while the plane is far from where the lens is focused
        const bl = Math.round(clamp(Math.abs(1 / Math.max(0.3, d) - invF) * K_BLUR * 0.7, 0, rack ? 3 : 9));
        if (!pn.vis) { pn.el.style.willChange = "transform, opacity"; pn.vis = true; }
        pn.el.style.transform = tfm;
        pn.el.style.opacity = a.toFixed(3);
        if (bl !== pn.blur) { pn.el.style.filter = bl > 0 ? `blur(${bl * 0.6}px)` : "none"; pn.blur = bl; }
        // a plane is its own compositor layer, so moving it costs no repaint; but a layer keeps the scale it was
        // painted at, so when the words have come to rest the layer is released for one frame and painted again, crisp
        if (Math.abs(s - 1) > 0.004) { pn.moved = t; pn.dirty = true; }
        else if (pn.dirty && t - pn.moved > 0.15) { pn.dirty = false; pn.rewc = true; pn.el.style.willChange = "auto"; }
        else if (pn.rewc) { pn.rewc = false; pn.el.style.willChange = "transform, opacity"; }
        const live = a > 0.7;
        if (live !== pn.live) { pn.live = live; pn.el.classList.toggle("is-live", live); }
        const zi = 10 + Math.round((6 - d) * 100);
        if (zi !== pn.z) { pn.el.style.zIndex = String(zi); pn.z = zi; }
      }
    });

    // ---- readouts
    if (t - hudAt > 0.1) {
      hudAt = t;
      if (hudSet) hudSet.textContent = `${String(beats[here].group + 1).padStart(2, "0")}/${String(nG).padStart(2, "0")}`;
      if (hudTruck) hudTruck.textContent = cz.toFixed(2);
      if (hudFocus) hudFocus.textContent = focus.toFixed(2);
      if (gauge) {
        const mapY = (d: number) => clamp((d - 0.25) / 1.9) * 100;
        const st = stacks[stHere];
        const base = st.z0, dd = (d: number) => d - (cz - base);
        gTicks.get("near")!.style.top = `${mapY(dd(0.7))}%`;
        gTicks.get("text")!.style.top = `${mapY(1 + (beats[here].Z - cz))}%`;
        gTicks.get("mid")!.style.top = `${mapY(dd(1.3))}%`;
        gTicks.get("far")!.style.top = `${mapY(dd(1.55))}%`;
        gFocus.style.top = `${mapY(focus)}%`;
      }
    }
  });
  void SUB;
}
