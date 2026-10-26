/**
 * Flipbook: the site is one pad of animation paper held by a peg bar. Each wheel notch (one page step of scroll) lets
 * go of one page: it curls up towards the viewer and over the top, and the page beneath has moved on a little. Every
 * section is a run of pages: its pencil drawing animates page by page, its headline is lettered in a few characters per
 * page, its body a few words per page, and each item gets its own run. Scroll fast and pages riffle, several in the air
 * at once; scroll back and they fall back in order. Grab the lower corner to lift and flip a page by hand; hold it to
 * riffle.
 *
 * Drawing: the resting page is painted on one canvas under its real, live HTML text; pages in flight are painted on a
 * second canvas above it, with their text baked in from the DOM so a flying page carries exactly what it showed.
 * Reduced motion: no pad; each section is one finished page in the reading flow, its last drawing in the field.
 */
import { $, $$, chars, onFrame, reduced } from "./_kit";
import { loadArt, type ArtFrames } from "./_art";
import { drawField, pageFurniture, PAPER, type Device, type Rect, type Run } from "./_flipbook-draw";

const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const smooth = (a: number, b: number, v: number) => { const t = clamp((v - a) / (b - a)); return t * t * (3 - 2 * t); };
const phone = () => innerWidth <= 760;
const text = (el: Element | null) => (el?.textContent || "").replace(/\s+/g, " ").trim();

interface Unit { els: HTMLElement[]; page: number }
interface Item { el: HTMLElement; start: number; end: number }
interface Sec {
  el: HTMLElement;
  face: HTMLElement | null;
  field: HTMLElement | null;
  type: string;
  pause: boolean;
  tab: number;
  units: Unit[];
  items: Item[];
  pages: number;
  start: number;          // global index of its first page
  top: number;            // document y of the section
  run: Run | null;
  shown: number;          // the local page its face currently shows (-1 = never)
}

let lastInput = -1e9;
for (const ev of ["wheel", "touchmove", "keydown", "pointerdown"]) addEventListener(ev, () => { lastInput = performance.now(); }, { passive: true, capture: true });
const byUser = () => performance.now() - lastInput < 1000;

/** The writing schedule of one face: which characters, words and whole pieces appear on which page. */
function schedule(s: Sec) {
  const face = s.face!;
  const units: Unit[] = [];
  let page = 0;
  const write = (root: Element, perChars: number, perWords: number) => {
    const nodes = [...root.querySelectorAll<HTMLElement>("[data-fb-write], [data-fb-unit]")].filter((n) => !n.parentElement?.closest("[data-fb-unit]"));
    if (root.matches?.("[data-fb-write], [data-fb-unit]")) nodes.unshift(root as HTMLElement);
    for (const n of nodes) {
      if (n.hasAttribute("data-fb-unit")) { units.push({ els: [n], page }); page += 1; continue; }
      const spans = chars(n);
      if (n.dataset.fbWrite === "words") {
        const words = new Map<Element, HTMLElement[]>();
        spans.forEach((sp) => { const w = sp.parentElement!; if (!words.has(w)) words.set(w, []); words.get(w)!.push(sp); });
        let i = 0;
        for (const w of words.values()) { units.push({ els: w, page: page + Math.floor(i / perWords) }); i++; }
        page += Math.max(1, Math.ceil(words.size / perWords));
      } else {
        spans.forEach((sp, i) => units.push({ els: [sp], page: page + Math.floor(i / perChars) }));
        page += Math.max(1, Math.ceil(spans.length / perChars));
      }
    }
  };
  const itemEls = $$("[data-fb-item]", face);
  // the lead: everything outside the items
  const lead = face.querySelector(".fb-text")!;
  const leadNodes = [...lead.querySelectorAll<HTMLElement>("[data-fb-write], [data-fb-unit]")].filter((n) => !n.closest("[data-fb-item]") && !n.parentElement?.closest("[data-fb-unit]"));
  for (const n of leadNodes) write(n, n.matches(".fb-h--hero") ? 4 : 5, 6);
  const leadPages = page;
  if (itemEls.length) page += 1;
  const items: Item[] = [];
  for (const it of itemEls) {
    const start = page;
    write(it, 6, 7);
    let end = Math.max(page + 2, start + 5);
    if (s.type === "stats") {
      const n = parseFloat((it.dataset.fbValue || "").replace(/[^0-9.\-]/g, ""));
      const unit = it.dataset.fbUnitLabel || "";
      const count = !/%/.test(unit) && Number.isInteger(n) && n >= 1 && n <= 30 ? n : 6;
      end = Math.max(end, start + Math.min(count, 12) + 3);
    }
    if (s.type === "timeline") end = Math.max(end, start + 6);
    if (s.type === "faq") end = Math.max(end, start + 6);
    items.push({ el: it, start, end });
    page = end;
  }
  const MIN: Record<string, number> = { hero: 16, intro: 14, product: 18, quote: 12, cta: 14, features: 8, stats: 6, timeline: 8, faq: 8 };
  const hold = itemEls.length ? 2 : 4;
  const pages = Math.max(page + hold, MIN[s.type] || 10);
  return { units, items, pages, leadPages };
}

export default function start() {
  const main = $("main");
  if (!main) return;
  const tops = [...main.children] as HTMLElement[];
  const els = tops.map((t) => (t.tagName === "SECTION" ? t : t.querySelector("section")) as HTMLElement).filter(Boolean);
  const secs: Sec[] = els.map((el, i) => {
    const type = el.dataset.fb || "";
    const face = el.querySelector<HTMLElement>(".fb-page");
    return { el, face, field: face?.querySelector<HTMLElement>(".fb-field") || null, type, pause: !type || !face, tab: i, units: [], items: [], pages: 0, start: 0, top: 0, run: null, shown: -1 };
  });
  const blocks = secs.filter((s) => !s.pause);
  if (!blocks.length) return;

  const artReady: Promise<ArtFrames | null> = blocks.some((s) => s.type === "hero") ? loadArt() : Promise.resolve(null);
  const runOf = (s: Sec, items: Item[], lead: number, pages: number): Run => {
    const face = s.face!;
    const run: Run = { type: s.type, pages, items: items.map((i) => ({ start: i.start, end: i.end })), lead };
    if (s.type === "product") { try { run.device = JSON.parse(text(face.querySelector(".fb-device")) || "null") as Device; } catch { run.device = null; } }
    if (s.type === "stats") run.stats = items.map((i) => ({ value: i.el.dataset.fbValue || "", unit: i.el.dataset.fbUnitLabel || "" }));
    if (s.type === "timeline") run.whens = items.map((i) => i.el.dataset.fbWhen || "");
    if (s.type === "features") run.tags = items.map((i) => i.el.dataset.fbTag || "");
    if (s.type === "cta") run.word = text(face.querySelector(".fb-box"));
    const img = face.querySelector<HTMLImageElement>("[data-fb-img]");
    if (img && (s.type === "hero" || s.type === "product") && !run.device) {
      run.img = img;
      if (!img.complete) img.addEventListener("load", () => { texCache.clear(); backCache.clear(); underKey = ""; }, { once: true });
    }
    return run;
  };

  if (reduced) { stills(blocks, artReady, runOf); return; }

  // ---------------------------------------------------------------- build the pad
  document.documentElement.classList.add("fb-on");
  let total = 0;
  for (const s of blocks) {
    const sc = schedule(s);
    s.units = sc.units; s.items = sc.items; s.pages = sc.pages;
    s.start = total; total += s.pages;
    s.run = runOf(s, sc.items, sc.leadPages, sc.pages);
  }
  artReady.then((a) => { const h = blocks.find((s) => s.type === "hero"); if (h?.run && a) { h.run.art = a; texCache.clear(); underKey = ""; } });

  const under = document.createElement("canvas"); under.className = "fb-cv fb-cv--under";
  const fly = document.createElement("canvas"); fly.className = "fb-cv fb-cv--fly";
  document.body.append(under, fly);
  const uctx = under.getContext("2d")!, fctx = fly.getContext("2d")!;
  const counter = $(".fb-count__p"), counterOf = $(".fb-count__of");
  const tabs = $$<HTMLElement>("[data-fb-tab]");
  const grip = $(".fb-grip");

  let step = 100, vw = innerWidth, vh = innerHeight, dpr = 1;
  const pad = { x: 0, y: 0, w: 0, h: 0 };
  let field: Rect = { x: 0, y: 0, w: 10, h: 10 };

  function layout() {
    vw = innerWidth; vh = innerHeight;
    step = phone() ? 80 : 100;
    if (phone()) {
      pad.y = 76; pad.x = 12; pad.w = vw - 24; pad.h = Math.min(vh - 76 - 52, pad.w * 1.78);
    } else {
      pad.y = 100;
      pad.h = Math.min(vh - pad.y - 70, 680);
      pad.w = Math.min(vw - 2 * Math.max(70, vw * 0.06) - 150, pad.h * 1.62, 1120);
      pad.x = Math.round((vw - pad.w) / 2 - 50);
    }
    const root = document.documentElement.style;
    root.setProperty("--fb-x", `${pad.x}px`); root.setProperty("--fb-y", `${pad.y}px`);
    root.setProperty("--fb-w", `${pad.w}px`); root.setProperty("--fb-h", `${pad.h}px`);
    dpr = Math.min(devicePixelRatio || 1, 2);
    for (const c of [under, fly]) { c.width = Math.round(vw * dpr); c.height = Math.round(vh * dpr); }
    for (const s of blocks) {
      const last = s === blocks[blocks.length - 1];
      s.el.style.height = `${s.pages * step + (last ? Math.round(vh * 0.45) : 0)}px`;
    }
    for (const s of secs) s.top = s.el.getBoundingClientRect().top + scrollY;
    const f = blocks[0].face!, fr = f.getBoundingClientRect(), r = blocks[0].field!.getBoundingClientRect();
    field = { x: r.left - fr.left, y: r.top - fr.top, w: r.width, h: r.height };
    texCache.clear(); backCache.clear(); underKey = "";
    if (counterOf) counterOf.textContent = `of ${total}`;
  }

  // ---------------------------------------------------------------- page state (what a face shows on local page f)
  function apply(s: Sec, f: number) {
    if (s.shown === f) return;
    s.shown = f;
    for (const u of s.units) {
      const on = u.page <= f;
      for (const e of u.els) if (e.classList.contains("on") !== on) e.classList.toggle("on", on);
    }
    s.items.forEach((it, i) => {
      const last = i === s.items.length - 1;
      const cur = f >= it.start && (f < it.end || last);
      it.el.classList.toggle("is-future", f < it.start);
      it.el.classList.toggle("is-cur", cur);
      it.el.classList.toggle("is-past", !cur && f >= it.end);
      it.el.classList.toggle("is-ticked", f >= it.start + 2);
    });
  }
  const secOf = (p: number) => { for (const s of blocks) if (p < s.start + s.pages) return s; return blocks[blocks.length - 1]; };

  // ---------------------------------------------------------------- page textures
  const texCache = new Map<number, HTMLCanvasElement>();
  const backCache = new Map<number, HTMLCanvasElement>();
  const styleCache = new WeakMap<Element, { font: string; color: string }>();
  function paint(ctx: CanvasRenderingContext2D, p: number, withText: boolean) {
    const s = secOf(p), f = p - s.start;
    pageFurniture(ctx, pad.w, pad.h, field, p, total, blocks.indexOf(s) + 1, f, s.pages);
    if (s.run) drawField(ctx, s.run, f, field, blocks.indexOf(s) + 1);
    if (withText) bake(ctx, s, f);
  }
  function bake(ctx: CanvasRenderingContext2D, s: Sec, f: number) {
    const keep = s.shown;
    apply(s, f);
    const face = s.face!, fr = face.getBoundingClientRect();
    ctx.textBaseline = "alphabetic";
    const st = (el: Element) => {
      let v = styleCache.get(el);
      if (!v) { const c = getComputedStyle(el); v = { font: `${c.fontStyle} ${c.fontWeight} ${c.fontSize} ${c.fontFamily}`, color: c.color }; styleCache.set(el, v); }
      return v;
    };
    for (const u of s.units) {
      if (u.page > f) continue;
      for (const e of u.els) {
        if (e.closest(".is-future")) continue;
        const r = e.getBoundingClientRect();
        if (!r.width) continue;
        if (e.classList.contains("sx-ch")) {
          const v = st(e.parentElement!.parentElement || e);
          ctx.font = v.font; ctx.fillStyle = v.color;
          const fs = parseFloat(v.font.split(" ").find((t) => t.endsWith("px")) || "16");
          ctx.fillText(e.textContent || "", r.left - fr.left, r.top - fr.top + r.height * 0.5 + fs * 0.32);
        } else {
          // whole pieces: labels, tags, drawn boxes
          const boxes = e.matches("[data-fb-box]") ? [e] : [...e.querySelectorAll<HTMLElement>("[data-fb-box]")];
          for (const b of boxes) {
            const br = b.getBoundingClientRect(), c = getComputedStyle(b);
            if (c.backgroundColor && !/rgba\(0, 0, 0, 0\)|transparent/.test(c.backgroundColor)) { ctx.fillStyle = c.backgroundColor; ctx.fillRect(br.left - fr.left, br.top - fr.top, br.width, br.height); }
            ctx.strokeStyle = c.borderTopColor; ctx.lineWidth = parseFloat(c.borderTopWidth) || 1.5;
            ctx.strokeRect(br.left - fr.left, br.top - fr.top, br.width, br.height);
            ctx.font = `${c.fontStyle} ${c.fontWeight} ${c.fontSize} ${c.fontFamily}`; ctx.fillStyle = c.color;
            ctx.fillText(text(b), br.left - fr.left + parseFloat(c.paddingLeft), br.top - fr.top + br.height * 0.5 + parseFloat(c.fontSize) * 0.34);
          }
          if (!boxes.length) {
            const c = getComputedStyle(e);
            ctx.font = `${c.fontStyle} ${c.fontWeight} ${c.fontSize} ${c.fontFamily}`; ctx.fillStyle = c.color;
            const label = c.textTransform === "uppercase" ? text(e).toUpperCase() : text(e);
            try { (ctx as any).letterSpacing = c.letterSpacing === "normal" ? "0px" : c.letterSpacing; } catch { /* older canvas */ }
            ctx.fillText(label, r.left - fr.left, r.top - fr.top + parseFloat(c.fontSize) * 0.95);
            try { (ctx as any).letterSpacing = "0px"; } catch { /* older canvas */ }
            if (e.classList.contains("fb-label")) { ctx.fillRect(r.left - fr.left, r.bottom - fr.top - 1.5, r.width, 1.5); }
          }
        }
      }
    }
    // ticks of finished items
    for (const it of s.items) {
      const t = it.el.querySelector<HTMLElement>(".fb-tick");
      if (!t || f < it.start + 2) continue;
      const r = t.getBoundingClientRect(); const v = st(t);
      ctx.font = v.font; ctx.fillStyle = v.color; ctx.fillText("✓", r.left - fr.left, r.top - fr.top + r.height * 0.8);
    }
    if (keep >= 0) apply(s, keep); else s.shown = -1;
  }
  const TEX_DPR = () => (phone() ? 1.5 : 1.25);
  function tex(p: number) {
    let c = texCache.get(p);
    if (c) return c;
    c = document.createElement("canvas");
    const k = TEX_DPR();
    c.width = Math.round(pad.w * k); c.height = Math.round(pad.h * k);
    const x = c.getContext("2d")!; x.scale(k, k);
    paint(x, p, true);
    texCache.set(p, c);
    if (texCache.size > 14) texCache.delete(texCache.keys().next().value!);
    return c;
  }
  function back(p: number) {
    let c = backCache.get(p);
    if (c) return c;
    const front = tex(p);
    c = document.createElement("canvas"); c.width = front.width; c.height = front.height;
    const x = c.getContext("2d")!;
    x.fillStyle = "#efe9dc"; x.fillRect(0, 0, c.width, c.height);
    x.globalAlpha = 0.07; x.drawImage(front, 0, 0); x.globalAlpha = 1;
    backCache.set(p, c);
    if (backCache.size > 10) backCache.delete(backCache.keys().next().value!);
    return c;
  }

  // ---------------------------------------------------------------- the resting page and the stack
  let underKey = "";
  function drawUnder(rest: number) {
    const key = `${rest}|${pad.w}|${pad.h}|${vw}|${vh}`;
    if (key === underKey) return;
    underKey = key;
    const c = uctx;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, vw, vh);
    if (rest >= total) return;
    const left = total - rest;
    const thick = Math.round(clamp(left * 0.09, 2, 13));
    // the stack's edges
    for (let i = thick; i >= 1; i--) {
      c.fillStyle = i % 2 ? "#d8d1c0" : "#bfb7a6";
      c.fillRect(pad.x + i * 0.7, pad.y + pad.h + i * 1.5 - 1.5, pad.w - i * 0.3, 1.6);
      c.fillRect(pad.x + pad.w + i * 0.7 - 1, pad.y + 2 + i * 0.6, 1.2, pad.h);
    }
    c.save();
    c.shadowColor = "rgba(0, 0, 0, .55)"; c.shadowBlur = 34; c.shadowOffsetY = 16 + thick;
    c.fillStyle = PAPER; c.fillRect(pad.x, pad.y, pad.w, pad.h);
    c.restore();
    c.save(); c.translate(pad.x, pad.y);
    c.beginPath(); c.rect(0, 0, pad.w, pad.h); c.clip();
    paint(c, rest, false);
    c.restore();
  }

  // ---------------------------------------------------------------- pages in flight
  /**
   * A page in the air, drawn as a peel: the sheet folds along a line that starts across the lower right corner (where
   * the thumb holds it) and sweeps up to the peg bar, turning level as it goes. The part beyond the fold is reflected
   * over it and shows the back of the sheet; when the fold reaches the hinge the whole page lies over the top.
   */
  function fold(a: number) {
    const e = 1 - Math.pow(1 - clamp(a), 1.7);
    const phi = (phone() ? 0.5 : 0.62) * (1 - e) + 0.0001;
    const Q = { x: pad.x + pad.w, y: pad.y + pad.h - (pad.h + 2) * e };
    const u = { x: -Math.cos(phi), y: Math.sin(phi) };       // along the fold, leftwards and down
    const n = { x: Math.sin(phi), y: Math.cos(phi) };        // towards the corner (the folded side)
    return { Q, u, n };
  }
  function halfPlane(c: CanvasRenderingContext2D, Q: { x: number; y: number }, u: { x: number; y: number }, n: { x: number; y: number }, side: number) {
    const B = 5000;
    c.moveTo(Q.x + u.x * B, Q.y + u.y * B); c.lineTo(Q.x - u.x * B, Q.y - u.y * B);
    c.lineTo(Q.x - u.x * B + n.x * B * side, Q.y - u.y * B + n.y * B * side); c.lineTo(Q.x + u.x * B + n.x * B * side, Q.y + u.y * B + n.y * B * side);
    c.closePath();
  }
  function flatPart(p: number, a: number) {
    const c = fctx, { Q, u, n } = fold(a);
    c.save();
    c.beginPath(); c.rect(pad.x, pad.y, pad.w, pad.h); c.clip();
    // the page beneath, where the sheet has lifted: a soft shadow along the fold
    c.save(); c.beginPath(); halfPlane(c, Q, u, n, 1); c.clip();
    const g = c.createLinearGradient(Q.x, Q.y, Q.x + n.x * 60, Q.y + n.y * 60);
    g.addColorStop(0, `rgba(25, 25, 30, ${0.3 * Math.sin(Math.PI * Math.min(1, a * 1.2)) + 0.05})`); g.addColorStop(1, "rgba(25, 25, 30, 0)");
    c.fillStyle = g; c.fillRect(pad.x, pad.y, pad.w, pad.h);
    c.restore();
    // the part of the sheet still lying flat
    c.beginPath(); halfPlane(c, Q, u, n, -1); c.clip();
    c.drawImage(tex(p), pad.x, pad.y, pad.w, pad.h);
    c.restore();
  }
  /** The corner of the top page bent up under the thumb: the next page shows beneath it. */
  function corner(p: number, a: number) {
    const c = fctx, { Q, u, n } = fold(a);
    c.save();
    c.beginPath(); c.rect(pad.x, pad.y, pad.w, pad.h); c.clip();
    c.beginPath(); halfPlane(c, Q, u, n, 1); c.clip();
    if (p + 1 < total) c.drawImage(tex(p + 1), pad.x, pad.y, pad.w, pad.h);
    else c.clearRect(pad.x, pad.y, pad.w, pad.h);
    const g = c.createLinearGradient(Q.x, Q.y, Q.x + n.x * 40, Q.y + n.y * 40);
    g.addColorStop(0, "rgba(25, 25, 30, .32)"); g.addColorStop(1, "rgba(25, 25, 30, 0)");
    c.fillStyle = g; c.fillRect(pad.x, pad.y, pad.w, pad.h);
    c.restore();
    flap(p, a);
  }
  function flap(p: number, a: number) {
    const c = fctx, { Q, u, n } = fold(a);
    const th = Math.atan2(u.y, u.x), ca = Math.cos(2 * th), sa = Math.sin(2 * th);
    // reflection over the fold line, in CSS px, then the canvas scale
    const m = { a: ca, b: sa, c: sa, d: -ca, e: Q.x - (ca * Q.x + sa * Q.y), f: Q.y - (sa * Q.x - ca * Q.y) };
    // the folded part of the sheet: the page rectangle cut by the fold, reflected over it
    let poly = [[pad.x, pad.y], [pad.x + pad.w, pad.y], [pad.x + pad.w, pad.y + pad.h], [pad.x, pad.y + pad.h]];
    const side = (q: number[]) => (q[0] - Q.x) * n.x + (q[1] - Q.y) * n.y;
    const cut: number[][] = [];
    for (let i = 0; i < poly.length; i++) {
      const A = poly[i], B = poly[(i + 1) % poly.length], sa1 = side(A), sb = side(B);
      if (sa1 >= 0) cut.push(A);
      if ((sa1 >= 0) !== (sb >= 0)) { const t = sa1 / (sa1 - sb); cut.push([A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t]); }
    }
    poly = cut.map(([x, y]) => [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f]);
    if (poly.length < 3) return;
    c.save();
    c.globalAlpha = 1 - smooth(0.86, 1, a);
    // its shadow on whatever lies under it
    c.beginPath(); poly.forEach(([x, y], i) => (i ? c.lineTo(x, y) : c.moveTo(x, y))); c.closePath();
    c.shadowColor = `rgba(0, 0, 0, ${0.38 * c.globalAlpha})`; c.shadowBlur = 24; c.shadowOffsetX = -n.x * 5 * dpr; c.shadowOffsetY = -n.y * 5 * dpr;
    c.fillStyle = "#efe9dc"; c.fill();
    c.shadowColor = "transparent";
    c.setTransform(dpr * m.a, dpr * m.b, dpr * m.c, dpr * m.d, dpr * m.e, dpr * m.f);
    c.beginPath(); c.rect(pad.x, pad.y, pad.w, pad.h); c.clip();
    c.beginPath(); halfPlane(c, Q, u, n, 1); c.clip();
    c.drawImage(back(p), pad.x, pad.y, pad.w, pad.h);
    // the roll: light along the fold, falling off towards the free edge
    const g = c.createLinearGradient(Q.x, Q.y, Q.x + n.x * pad.h * 0.7, Q.y + n.y * pad.h * 0.7);
    g.addColorStop(0, "rgba(255, 255, 255, .5)"); g.addColorStop(0.08, "rgba(255, 255, 255, .06)"); g.addColorStop(1, "rgba(60, 50, 40, .16)");
    c.fillStyle = g; c.fillRect(pad.x - pad.w, pad.y - pad.h, pad.w * 3, pad.h * 3);
    c.restore();
  }

  // ---------------------------------------------------------------- flight dynamics
  let A = new Float32Array(total);
  let T = 0, frac = 0, bend = 0, dragA = -1, forceUp = -1, forceUntil = 0, inited = false;
  let lastT = -1, flyDrawn = false, lastPeel = "";

  function targetFromScroll(y: number) {
    let t = 0, fr = 0;
    for (const s of secs) {
      if (s.pause) {
        // a scene covers the pad while it holds the middle of the screen
        if (y + vh * 0.5 >= s.top && y + vh * 0.5 < s.top + s.el.offsetHeight) {
          const next = blocks.find((b) => b.top > s.top);
          t = next ? next.start : total - 1; fr = 0;
          return { t, fr, away: true };
        }
        continue;
      }
      if (y < s.top) break;
      const local = (y - s.top) / step;
      if (local < s.pages) { t = s.start + Math.floor(local); fr = local - Math.floor(local); }
      else { t = s.start + s.pages - 1; fr = 0; }
    }
    return { t, fr, away: false };
  }
  function scrollSteps(n: number) {
    if (document.documentElement.classList.contains("lenis")) dispatchEvent(new WheelEvent("wheel", { deltaY: step * n, bubbles: true, cancelable: true }));
    else scrollBy(0, step * n);
  }

  // ---------------------------------------------------------------- the corner grip
  if (grip) {
    let sx = 0, sy = 0, held = 0, riffle = 0, moved = false;
    grip.addEventListener("pointerdown", (e) => {
      sx = e.clientX; sy = e.clientY; moved = false; dragA = 0;
      grip.setPointerCapture(e.pointerId); grip.classList.add("is-grab");
      document.documentElement.classList.add("fb-moved");
      held = window.setTimeout(() => {
        if (moved) return;
        dragA = -1;
        riffle = window.setInterval(() => { forceUp = T; forceUntil = performance.now() + 500; scrollSteps(1); }, 85);
      }, 420);
    });
    grip.addEventListener("pointermove", (e) => {
      if (dragA < 0) return;
      const dy = sy - e.clientY, dx = sx - e.clientX;
      if (Math.hypot(dx, dy) > 6) moved = true;
      dragA = clamp(dy / (pad.h * 0.9) + dx / (pad.w * 2.2), 0, 0.97);
    });
    const end = () => {
      clearTimeout(held); clearInterval(riffle); grip.classList.remove("is-grab");
      if (dragA >= 0) {
        if (T < total) A[T] = Math.max(A[T], dragA);
        if (dragA > 0.3 || (!moved && dragA >= 0)) { forceUp = T; forceUntil = performance.now() + 700; scrollSteps(1); }
      }
      dragA = -1;
    };
    grip.addEventListener("pointerup", end);
    grip.addEventListener("pointercancel", end);
  }
  $$<HTMLElement>("[data-fb-go]").forEach((a) => a.addEventListener("click", (e) => {
    const s = secs[+(a.dataset.fbGo || 0)];
    if (!s || s.el.id) return;
    e.preventDefault(); scrollTo({ top: s.top + 2, behavior: "smooth" });
  }));

  layout();
  addEventListener("resize", layout);
  document.fonts?.ready.then(() => { layout(); for (const s of blocks) s.shown = -1; });

  onFrame(({ y, dt }) => {
    if (A.length !== total) A = new Float32Array(total);
    const tg = targetFromScroll(y);
    const now = performance.now();
    if (forceUp >= 0 && (tg.t > forceUp || now > forceUntil)) forceUp = -1;
    T = Math.max(tg.t, forceUp >= 0 ? forceUp + 1 : 0);
    frac = tg.fr;
    if (y > 8) document.documentElement.classList.add("fb-moved");
    // a jump nobody made by hand: show the pad as it stands, no riffle
    const user = byUser();
    if (!inited || (!user && Math.abs(T - lastT) > 2)) { for (let i = 0; i < total; i++) A[i] = i < T ? 1 : 0; inited = true; }
    lastT = T;
    // flights: forwards in order, backwards in reverse order
    let queue = 0;
    for (let i = 0; i < total; i++) if ((i < T ? 1 : 0) !== A[i]) queue++;
    if (queue > 26) {   // a long jump: settle all but the last few
      for (let i = 0; i < total; i++) { const t = i < T ? 1 : 0; if (Math.abs(i - T) > 7) A[i] = t; }
    }
    const rate = (1 / 0.27) * (1 + Math.min(queue, 12) / 5);
    for (let i = 0; i < total; i++) {
      if (i < T && A[i] < 1 && (i === 0 || A[i - 1] >= 0.2)) A[i] = Math.min(1, A[i] + dt * rate);
    }
    for (let i = total - 1; i >= 0; i--) {
      if (i >= T && A[i] > 0 && (i === total - 1 || A[i + 1] <= 0.8)) A[i] = Math.max(0, A[i] - dt * rate);
    }
    // the next page lifts a little under the thumb as a notch builds up
    const bendT = tg.away ? 0 : 0.014 + (user ? 0.07 * smooth(0.25, 1, frac) : 0);   // a dog-ear that invites the thumb
    bend += (bendT - bend) * clamp(dt * 14);
    const disp = (i: number) => (i === T && dragA >= 0 ? Math.max(A[i], dragA) : i === T ? Math.max(A[i], bend) : A[i]);

    // the resting page: the first one lying flat
    // (a page only bent under the thumb still counts as lying flat: its text stays live)
    let rest = 0;
    while (rest < total && (A[rest] > 0.001 || (rest === T && dragA > 0.001))) rest++;
    const peel = rest === T && T < total && dragA < 0 && A[T] <= 0.001 && bend > 0.001;
    const s = secOf(Math.min(rest, total - 1));
    for (const b of blocks) if (b.face) b.face.classList.toggle("is-on", b === s && !tg.away);
    apply(s, Math.min(rest, total - 1) - s.start);
    drawUnder(rest);
    document.documentElement.classList.toggle("fb-away", tg.away);

    // pages in the air
    const flying: number[] = [];
    for (let i = Math.max(0, rest - 30); i < Math.min(total, rest + 30); i++) { const a = disp(i); if (a > 0.001 && a < 0.999 && !(peel && i === T)) flying.push(i); }
    const peelKey = peel ? `${T}:${bend.toFixed(4)}` : "";
    if (flying.length || flyDrawn || peelKey !== lastPeel) {
      lastPeel = peelKey;
      fctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      fctx.clearRect(0, 0, vw, vh);
      // flat parts from the bottom of the stack up, then the flaps in the order they went over
      for (const i of [...flying].sort((a, b) => b - a)) flatPart(i, disp(i));
      for (const i of [...flying].sort((a, b) => a - b)) flap(i, disp(i));
      if (peel) corner(T, bend);
      flyDrawn = flying.length > 0;
    }

    // furniture
    if (counter) counter.textContent = `p. ${Math.min(rest, total - 1) + 1}`;
    tabs.forEach((t) => {
      const sec = secs[+(t.dataset.fbTab || 0)];
      t.classList.toggle("is-gone", sec.start + sec.pages - 1 < rest && sec !== s);
      t.classList.toggle("is-on", sec === s);
    });
  });
}

/** Reduced motion: each section one finished page, its last drawing in the field. */
async function stills(blocks: Sec[], artReady: Promise<ArtFrames | null>, runOf: (s: Sec, items: Item[], lead: number, pages: number) => Run) {
  try { await document.fonts.ready; } catch { /* draw with fallbacks */ }
  const art = await artReady;
  blocks.forEach((s, i) => {
    if (!s.field) return;
    const items = $$<HTMLElement>("[data-fb-item]", s.face!).map((el, j) => ({ el, start: 2 + j * 10, end: 2 + j * 10 + 10 }));
    const pages = items.length ? 2 + items.length * 10 : 24;
    const run = runOf(s, items, 2, pages);
    if (s.type === "hero" && art) run.art = art;
    const r = s.field.getBoundingClientRect();
    const k = Math.min(devicePixelRatio || 1, 2);
    const c = document.createElement("canvas");
    c.width = Math.max(10, Math.round(r.width * k)); c.height = Math.max(10, Math.round(r.height * k));
    const x = c.getContext("2d")!; x.scale(k, k);
    drawField(x, run, pages - 1, { x: 0, y: 0, w: r.width, h: r.height }, i + 1);
    c.setAttribute("role", "img");
    c.setAttribute("aria-label", "Pencil drawing");
    s.field.appendChild(c);
  });
}
