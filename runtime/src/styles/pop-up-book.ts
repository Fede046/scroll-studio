/**
 * Pop-up book: the page is a 90-degree stage pop-up book on a lamp-lit table (Kubasta's panoramas). Every section
 * is a spread: the back page stands upright (the wall, printed with the reading text), the base page lies flat (the
 * floor), and die-cut pieces stand between them on parallel folds. One scroll notch turns the board page a few
 * degrees, and the opening angle is the only input the paper has: the turning leaf folds the old scene flat against
 * the wall behind it while the new scene rises out of the gutter under it, every piece parallel to its wall (a
 * parallelogram linkage), casting shadows that lengthen as it stands. Once a spread is open, scrolling works its
 * mechanism (pull-tabs that push cards forward and raise figures out of slots, a wheel that turns the timeline
 * through a window, flaps that lift for answers, a sunburst that turns behind the call to action). Tabs and the wheel
 * can be dragged too; dragging moves the scroll, so the gesture and the page never disagree.
 * The first hero is the cloth cover, read straight down from above; the camera tilts to the stage as it opens.
 * Sections the book can't bind (scenes, galleries) sit between volumes as loose plates. Reduced motion: no binding;
 * each spread is the still, opened diorama the CSS draws on its own.
 */
import { $, $$, onFrame, reduced } from "./_kit";

const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const ease = (t: number) => (t < 0.5 ? 2 * t * t : 1 - 2 * (1 - t) * (1 - t));
const smooth = (t: number) => { t = clamp(t); return t * t * (3 - 2 * t); };
const bump = (x: number) => clamp(1 - Math.abs(x));
const TURN = 1.05;   // screens of scroll per page turn
const LIGHT = (() => { const v = [-0.32, 0.6, 0.73]; const l = Math.hypot(...v); return v.map((c) => c / l); })();

interface Spread {
  el: HTMLElement; kind: string; hold: number; wall: HTMLElement | null; floor: HTMLElement | null;
  mech: (h: number, live: boolean) => void; holdStart: number; holdLen: number; turnStart: number;
}
interface Run {
  root: HTMLElement; stage: HTMLElement; cam: HTMLElement; book: HTMLElement; cover: HTMLElement; spreads: Spread[];
  theta: number[]; vel: number[]; target: number[]; total: number; top: number; height: number; holds: number[];
  front: HTMLElement; visible: Set<number>; started?: boolean;
}

export default function start() {
  const main = $<HTMLElement>("main");
  if (!main || !$(".pb-spread", main)) return;
  if (reduced) return;   // the still, opened dioramas are the reduced-motion book
  const root = document.documentElement;
  root.classList.add("pb-live");
  const phoneQ = matchMedia("(max-width: 760px)");
  const fine = matchMedia("(pointer: fine)").matches;

  // ------------------------------------------------------------ bind runs of spreads into books
  const blocks = [...main.children] as HTMLElement[];
  const spreadOf = (el: HTMLElement) => (el.matches("section.pb-spread") ? el : el.querySelector<HTMLElement>(":scope > section.pb-spread"));
  const groups: HTMLElement[][] = [];
  let cur: HTMLElement[] | null = null;
  for (const b of blocks) {
    const sp = spreadOf(b);
    if (sp && !b.querySelector("[data-scene]")) { if (!cur) groups.push((cur = [])); cur.push(b); }
    else { cur = null; b.classList.add("pb-loose"); }
  }
  const tpl = $<HTMLTemplateElement>("#pb-gencover");
  const runs: Run[] = groups.map((g) => {
    const rootEl = document.createElement("div");
    rootEl.className = "pb-run";
    g[0].before(rootEl);
    rootEl.innerHTML = `<div class="pb-stage"><div class="pb-cam"><div class="pb-book"><div class="pb-tableshadow"></div><div class="pb-board"></div><div class="pb-block pb-block--front"></div></div></div></div>`;
    const book = $(".pb-book", rootEl)!;
    const secs = g.map((b) => { const s = spreadOf(b)!; book.appendChild(s); if (b !== s) b.remove(); return s; });
    let cover: HTMLElement;
    if (secs[0].classList.contains("pb-spread--cover")) cover = secs.shift()!;
    else {
      cover = document.createElement("div");
      cover.className = "pb-spread pb-spread--cover";
      cover.setAttribute("aria-hidden", "true");
      if (tpl) cover.appendChild(tpl.content.cloneNode(true));
      book.insertBefore(cover, secs[0]);
    }
    const spreads: Spread[] = secs.map((el) => ({
      el, kind: el.dataset.kind || "", hold: Math.max(0.3, Number(el.dataset.hold) || 0.4),
      wall: el.querySelector<HTMLElement>(":scope > .pb-wall"), floor: el.querySelector<HTMLElement>(":scope > .pb-floor"),
      mech: () => {}, holdStart: 0, holdLen: 0, turnStart: 0,
    }));
    const n = spreads.length;
    return {
      root: rootEl, stage: $(".pb-stage", rootEl)!, cam: $(".pb-cam", rootEl)!, book, cover, spreads,
      theta: new Array(n + 1).fill(0), vel: new Array(n + 1).fill(0), target: new Array(n + 1).fill(0),
      total: 0, top: 0, height: 0, holds: new Array(n).fill(0),
      front: $(".pb-block--front", rootEl)!, visible: new Set<number>(),
    } as Run;
  });
  if (!runs.length) return;

  // ------------------------------------------------------------ mechanisms
  for (const run of runs) for (const sp of run.spreads) sp.mech = mechanism(sp);

  function mechanism(sp: Spread): (h: number, live: boolean) => void {
    const el = sp.el;
    const tabs = $$<HTMLElement>(".pb-tab", el);
    const setPull = (t: HTMLElement, k: number) => t.style.setProperty("--pull", k.toFixed(3));
    if (sp.kind === "features") {
      const cards = $$<HTMLElement>(".pb-card", el);
      const n = cards.length;
      return (h) => {
        const m = h * n - 0.5;
        const stack = phoneQ.matches;
        cards.forEach((c, i) => {
          if (stack) {
            c.style.setProperty("--dz", "0px");
            c.style.setProperty("--af", i < n - 1 ? `${(90 * (1 - smooth((m - i - 0.15) / 0.7))).toFixed(2)}deg` : "90deg");
          } else {
            c.style.removeProperty("--af");
            c.style.setProperty("--dz", `calc(var(--u) * ${(bump(m - i) * 7).toFixed(3)})`);
          }
        });
        tabs.forEach((t) => setPull(t, h));
      };
    }
    if (sp.kind === "product") {
      const opts = $$<HTMLElement>(".ss-app__opt", el);
      return (h) => {
        if (opts.length > 1) { const k = Math.min(opts.length - 1, Math.floor(h * opts.length)); opts.forEach((o, i) => o.classList.toggle("is-on", i === k)); }
        tabs.forEach((t) => setPull(t, h));
      };
    }
    if (sp.kind === "stats") {
      const slots = $$<HTMLElement>(".pb-slot", el);
      const n = slots.length;
      return (h) => slots.forEach((s, i) => {
        const k = smooth((h * (n + 0.6) - i * 0.95) / 1.1);
        s.style.setProperty("--k", k.toFixed(3));
        if (tabs[i]) setPull(tabs[i], k);
      });
    }
    if (sp.kind === "timeline") {
      const items = $$<HTMLElement>(".pb-step", el);
      const flags = $$<HTMLElement>(".pb-flag", el);
      const n = items.length;
      const sec = n <= 6 ? 60 : 360 / n;
      const host = $(".pb-print--split", el);
      let disc: HTMLElement | null = null;
      if (host && n) {
        const wheel = document.createElement("div");
        wheel.className = "pb-wheel";
        wheel.setAttribute("aria-hidden", "true");
        wheel.style.setProperty("--sec", `${sec}deg`);
        wheel.innerHTML = `<div class="pb-wheel__disc"><div class="pb-wheel__face"></div></div><div class="pb-wheel__win"></div><i class="pb-wheel__ptr"></i><span class="pb-wheel__hint">Turn the wheel</span><span class="pb-wheel__thumb" data-pull></span>`;
        disc = $(".pb-wheel__face", wheel)!;
        items.forEach((it, i) => {
          const s = document.createElement("div");
          s.className = "pb-wheel__sec";
          s.style.setProperty("--i", String(i));
          s.innerHTML = `<div class="pb-wheel__in">${it.innerHTML}</div>`;
          disc!.appendChild(s);
        });
        host.appendChild(wheel);
      }
      return (h) => {
        const raw = h * (n - 1 + 0.6) - 0.3;
        const i0 = Math.floor(raw), f = raw - i0;
        const m = clamp(i0 + smooth((f - 0.25) / 0.5), 0, n - 1);
        disc?.style.setProperty("--rot", `${(-m * sec).toFixed(2)}deg`);
        const on = Math.round(m);
        flags.forEach((fl, i) => { fl.classList.toggle("is-on", i === on); fl.style.setProperty("--dz", `calc(var(--u) * ${(-bump(m - i) * 3).toFixed(2)})`); });
      };
    }
    if (sp.kind === "faq") {
      const boxes = $$<HTMLDetailsElement>("details.pb-flapbox", el);
      let touched = false;
      boxes.forEach((d) => d.querySelector("summary")?.addEventListener("click", () => { touched = true; }));
      let last = -1;
      return (h, live) => {
        if (touched || !live) return;
        const k = Math.floor(h * boxes.length + 0.35);
        if (k === last) return;
        last = k;
        boxes.forEach((d, i) => { d.open = i < k; });
      };
    }
    if (sp.kind === "cta") {
      const burst = $(".pb-burst", el);
      return (h) => burst?.style.setProperty("--spin", `${(h * 150 - 30).toFixed(1)}deg`);
    }
    return () => {};
  }

  // ------------------------------------------------------------ layout: book size, track lengths
  let vw = innerWidth, vh = innerHeight, W = 0, D = 0, U = 0, PHI = 58, headH = 58, P = 2200;
  function layout() {
    vw = innerWidth; vh = innerHeight;
    const phone = phoneQ.matches;
    headH = phone ? 50 : 58;
    const avail = vh - headH - (phone ? 30 : 40);
    PHI = phone ? 61 : 57;
    P = Math.max(1700, vh * 2.7);
    D = Math.min(avail / 1.4, 660);
    for (let i = 0; i < 6; i++) {
      if (phone) { W = vw - 22; D = Math.min(D, W * 1.55); }
      else { W = Math.min(vw - 96, D * 1.62); D = Math.min(D, W / 1.25); }
      const f = fit(PHI, 1, D, D / 100);
      D *= clamp(avail / Math.max(1, f.h), 0.6, 1.5);
    }
    if (phone) { W = vw - 22; D = Math.min(D, W * 1.55); }
    else { W = Math.min(vw - 96, D * 1.62); D = Math.min(D, W / 1.25); }
    U = D / 100;
    for (const run of runs) {
      run.stage.style.perspective = `${P.toFixed(0)}px`;
      run.root.style.setProperty("--W", `${W.toFixed(1)}px`);
      run.root.style.setProperty("--D", `${D.toFixed(1)}px`);
      run.root.style.setProperty("--u", `${U.toFixed(3)}px`);
      let s = 0;
      run.spreads.forEach((sp) => {
        sp.turnStart = s; s += TURN;
        sp.holdStart = s; sp.holdLen = sp.hold; s += sp.hold;
      });
      run.total = s + 0.15;
      run.root.style.height = `${(run.total * vh + vh).toFixed(0)}px`;
    }
    measure();
  }
  // where the open book lands on screen: project the wall's top and the tabs at the front edge through the
  // stage's perspective, and find the vertical shift that centres them in the space under the running head
  function fit(phi: number, open: number, d: number, u: number, scale = 1) {
    const r = phi * Math.PI / 180, c = Math.cos(r), sn = Math.sin(r);
    const proj = (y: number, z: number, ty: number) => { const yy = y * c - z * sn, zz = y * sn + z * c; return (ty + scale * yy) * P / (P - scale * zz); };
    const top = [-d / 2, d * open] as const, bot = [d / 2 + u * 8 * open, 0] as const;
    const lo = headH + 10 - vh / 2, hi = vh / 2 - (phoneQ.matches ? 16 : 22), mid = (lo + hi) / 2;
    let ty = 0;
    for (let i = 0; i < 8; i++) {
      const a = proj(top[0], top[1], ty), b = proj(bot[0], bot[1], ty);
      ty -= ((a + b) / 2 - mid) * 0.9;
    }
    const a = proj(top[0], top[1], ty), b = proj(bot[0], bot[1], ty);
    return { ty, h: b - a };
  }
  function measure() {
    for (const run of runs) { const r = run.root.getBoundingClientRect(); run.top = r.top + scrollY; run.height = r.height; }
  }

  // ------------------------------------------------------------ per-frame: page angles (sprung), camera, faces
  let yaw = 0, tilt = 0, yawT = 0, tiltT = 0;
  if (fine) addEventListener("pointermove", (e) => { yawT = (e.clientX / vw - 0.5) * 7; tiltT = (e.clientY / vh - 0.5) * -4; }, { passive: true });
  const pagesEl = $<HTMLElement>('[data-pb="pages"]');
  const ribbons = $$<HTMLAnchorElement>(".pb-head__ribbons a");
  let lastLabel = "";

  function frame(dt: number) {
    yaw += (yawT - yaw) * Math.min(1, dt * 4);
    tilt += (tiltT - tilt) * Math.min(1, dt * 4);
    let label = "";
    let onId = "";
    for (const run of runs) {
      const local = (scrollY - run.top) / vh;   // screens into the run
      const n = run.spreads.length;
      if (local < -1.2 || local > run.total + 1.2) continue;
      // targets: each leaf's angle, each spread's mechanism
      for (let k = 0; k < n; k++) {
        const sp = run.spreads[k];
        run.target[k] = 90 * ease(clamp((local - sp.turnStart) / TURN));
        run.holds[k] = clamp((local - sp.holdStart) / sp.holdLen);
      }
      run.target[n] = 0;
      // paper has a little spring in it: the board settles with a small overshoot (none on the first frame)
      if (!run.started) { run.started = true; for (let k = 0; k <= n; k++) run.theta[k] = run.target[k]; }
      const K = 150, C = 2 * Math.sqrt(K) * 0.72;
      for (let k = 0; k <= n; k++) {
        const a = K * (run.target[k] - run.theta[k]) - C * run.vel[k];
        run.vel[k] += a * dt;
        run.theta[k] = clamp(run.theta[k] + run.vel[k] * dt, -1, 96);
        if (Math.abs(run.target[k] - run.theta[k]) < 0.01 && Math.abs(run.vel[k]) < 0.01) { run.theta[k] = run.target[k]; run.vel[k] = 0; }
      }
      const th = run.theta;
      // which leaf is moving (or last moved): show the spreads on either side of it, hide the rest
      let moving = -1;
      for (let k = 0; k < n; k++) if (th[k] > 0.3) moving = k;
      const show = new Set<number>();
      if (moving >= 0) {
        show.add(moving);
        if (th[moving] < 89.5 || Math.abs(run.vel[moving]) > 0.5) show.add(moving - 1);
        if (moving + 1 < n && th[moving + 1] > 0.01) show.add(moving + 1);
      }
      const showCover = moving < 0 || show.has(-1);
      run.cover.classList.toggle("pb-off", !showCover);
      const ez = U * 0.6, ey = U * 0.45;
      run.cover.style.setProperty("--tf", `${th[0].toFixed(3)}deg`);
      run.cover.style.setProperty("--zf", `${(n * ez).toFixed(2)}px`);
      run.cover.style.setProperty("--shade", shadeFloor(th[0]).toFixed(3));
      run.spreads.forEach((sp, s) => {
        const vis = show.has(s);
        sp.el.classList.toggle("pb-off", !vis);
        if (!vis) return;
        const tw = th[s], tf = th[s + 1];
        const st = sp.el.style;
        st.setProperty("--tw", `${tw.toFixed(3)}deg`);
        st.setProperty("--tf", `${tf.toFixed(3)}deg`);
        st.setProperty("--zw", `${((n - s) * ez - ez * 0.4).toFixed(2)}px`);
        st.setProperty("--zf", `${((n - s - 1) * ez).toFixed(2)}px`);
        sp.wall?.style.setProperty("--shade", shadeWall(tw).toFixed(3));
        sp.floor?.style.setProperty("--shade", shadeFloor(tf).toFixed(3));
        sp.mech(run.holds[s], true);
      });
      // the page block: unturned leaves stacked at the front, turned ones along the top of the wall
      let turned = 0;
      for (let k = 0; k < n; k++) if (th[k] >= 45) turned++;
      run.book.style.setProperty("--sf", `${((n + 1 - turned) * ez).toFixed(2)}px`);
      run.book.style.setProperty("--sw", `${(Math.max(0, turned) * ey + (turned ? U * .4 : 0)).toFixed(2)}px`);
      // camera: straight down onto the closed cover, tilting to the stage as the cover rises; a small pull-back mid-turn
      const open = clamp(th[0] / 90);
      const phi = lerp(9, PHI, smooth(open * 1.08)) + tilt;
      let mid = 0;
      for (let k = 0; k < n; k++) mid = Math.max(mid, Math.sin(Math.PI * clamp(th[k] / 90)));
      const scale = 1 - mid * 0.045;
      const ty = fit(phi, open, D, U, scale).ty;
      run.cam.style.transform = `translate3d(0, ${ty.toFixed(1)}px, 0) scale(${scale.toFixed(4)}) rotateX(${phi.toFixed(3)}deg) rotateZ(${(yaw * open).toFixed(3)}deg)`;
      // running head and the page count
      if (local > -0.1 && local < run.total + 0.3) {
        const k = moving < 0 ? -1 : (th[moving] > 45 ? moving : moving - 1);
        if (k < 0) label = "Cover";
        else {
          const sp = run.spreads[k];
          const f = sp.el.querySelector(".pb-folio--wall")?.textContent?.trim();
          label = f ? `pp. ${f}–${Number(f) + 1}` : "";
          onId = sp.el.id || "";
        }
      }
    }
    if (pagesEl && label !== lastLabel) { pagesEl.textContent = label; lastLabel = label; }
    ribbons.forEach((a) => a.classList.toggle("is-on", !!onId && a.getAttribute("href") === `#${onId}`));
  }
  function shadeFloor(t: number) {   // front face of a leaf at angle t (0 flat on the table, 90 upright facing the gutter)
    const r = t * Math.PI / 180;
    const d = -Math.sin(r) * LIGHT[1] + Math.cos(r) * LIGHT[2];
    return clamp(0.36 - d * 0.46, 0, 0.4);
  }
  function shadeWall(t: number) {    // back face (the wall side)
    const r = t * Math.PI / 180;
    const d = Math.sin(r) * LIGHT[1] - Math.cos(r) * LIGHT[2];
    return clamp(0.34 - d * 0.46, 0, 0.4);
  }

  // ------------------------------------------------------------ dragging a tab or the wheel moves the scroll
  let drag: { y0: number; s0: number; run: Run; sp: Spread; dir: number } | null = null;
  main.addEventListener("pointerdown", (e) => {
    const t = (e.target as HTMLElement).closest<HTMLElement>(".pb-tab, [data-pull]");
    if (!t) return;
    const sec = t.closest<HTMLElement>(".pb-spread");
    const run = runs.find((r) => r.spreads.some((s) => s.el === sec));
    const sp = run?.spreads.find((s) => s.el === sec);
    if (!run || !sp) return;
    e.preventDefault();
    t.setPointerCapture(e.pointerId);
    drag = { y0: e.clientY, s0: scrollY, run, sp, dir: t.matches("[data-pull]") ? -1 : 1 };
  });
  addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dy = (e.clientY - drag.y0) * drag.dir;
    const span = drag.sp.holdLen * vh;
    const lo = drag.run.top + drag.sp.holdStart * vh, hi = lo + span;
    const y = clamp(drag.s0 + dy * (span / (U * 26)), lo - 2, hi + 2);
    scrollTo(0, y);
  });
  const endDrag = () => { drag = null; };
  addEventListener("pointerup", endDrag);
  addEventListener("pointercancel", endDrag);

  // ------------------------------------------------------------ contents ribbons and in-page links open the right spread
  function spreadY(id: string): number | null {
    for (const run of runs) {
      const i = run.spreads.findIndex((s) => s.el.id === id);
      if (i >= 0) return run.top + (run.spreads[i].holdStart + 0.02) * vh;
      if (run.cover.id === id) return run.top;
    }
    return null;
  }
  document.addEventListener("click", (e) => {
    const a = (e.target as HTMLElement).closest<HTMLAnchorElement>('a[href^="#"]');
    if (!a) return;
    const id = a.getAttribute("href")!.slice(1);
    if (!id) return;
    const y = spreadY(id);
    if (y == null) return;
    e.preventDefault();
    e.stopPropagation();
    const from = scrollY, dist = y - from, dur = Math.min(2200, 500 + Math.abs(dist) / vh * 260), t0 = performance.now();
    const step = (now: number) => { const q = clamp((now - t0) / dur); scrollTo(0, from + dist * ease(q)); if (q < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }, { capture: true });

  layout();
  addEventListener("resize", () => { layout(); });
  phoneQ.addEventListener?.("change", layout);
  document.fonts?.ready.then(measure);
  setTimeout(measure, 800);
  // a hash on load opens that spread
  if (location.hash.length > 1) { const y = spreadY(location.hash.slice(1)); if (y != null) requestAnimationFrame(() => scrollTo(0, y)); }

  let last = performance.now();
  onFrame(() => {
    const now = performance.now();
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    frame(dt);
  });
}
