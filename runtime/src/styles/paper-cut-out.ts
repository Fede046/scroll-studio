/**
 * Paper cut-out: the page is a stack of coloured paper sheets on an animation stand, shot from above (Lotte Reiniger's
 * silhouettes, Terry Gilliam's cut-outs). Every section is a sheet held to the stack by one brass brad in a corner. Scrolling
 * swings the top sheet aside on its brad like a card on a pin (a quarter turn, with the weight of paper: a spring with a
 * little overshoot, and a shadow that lengthens as it lifts), and the sheet underneath comes alive as it is uncovered: the
 * pieces on it were folded away on their own pins and swing into place, overshooting and settling. The headline is words on paper
 * strips, each hung from its own pin; hanging pieces (words, tags, the balloon, snapshots, the rod of the mobile) sway with the
 * speed you scroll and settle when you stop, a paper bird crosses the sheet with its wings flapping as you scroll, and a branch's
 * leaves rustle on their hinges. What scrolling does inside a sheet is a linkage: the feature cards fan out from one pin and the
 * next one swings forward, a folding rule opens one hinge at a time along the timeline, the flaps over the answers swing ajar,
 * the spokes of the wheel turn on the hub. A jointed paper arm (shoulder, elbow, wrist, solved with two-bone IK) points at what
 * the scroll has reached; hover an item and it points there, take the hand and move it. Words, tags and snapshots can be taken
 * and swung by hand; nothing traps the scroll.
 * Reduced motion: no stand; the sheets are laid down as flat paper with their pieces at rest, decoration drawn still.
 * Research: docs/styles/styles-28-29.md, section 2.
 */
import { $, $$, onFrame, reduced } from "./_kit";
import { loadArt, type ArtFrames } from "./_art";
import { arm as makeArm, bird as makeBird, branch as makeBranch, flap, poseArm, stars as makeStars, swayBranch, type Arm, type Bird, type Branch } from "./_papercut-decor";

const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const smooth = (a: number, b: number, v: number) => { const t = clamp((v - a) / (b - a)); return t * t * (3 - 2 * t); };
const ease = (t: number) => (t < 0.5 ? 2 * t * t : 1 - 2 * (1 - t) * (1 - t));
const hash = (a: number, b = 0) => { let x = Math.imul(a ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul((b | 0) + 0x7f4a7c15, 0xc2b2ae35); x ^= x >>> 15; x = Math.imul(x, 0x2c1b3c6d); x ^= x >>> 12; return ((x >>> 0) / 4294967296) * 2 - 1; };
const SW = 0.95;      // screens of scroll to swing a sheet off its brad
const ANG = 100;      // degrees it turns (90 clears the screen)

class Spring {
  x = 0; v = 0;
  step(dt: number, target: number, k: number, c: number) {
    const n = Math.max(1, Math.ceil(dt / 0.008)), h = dt / n;
    for (let i = 0; i < n; i++) { const a = k * (target - this.x) - c * this.v; this.v += a * h; this.x += this.v * h; }
  }
}

interface Piece {
  el: HTMLElement; kind: string; from: string; idx: number; d: number; q: Spring; w: Spring; phase: number; tilt: number;
  ux: number; uy: number; vis: boolean; grab: boolean; ctrl: boolean; baseX: number; baseY: number; extra: { r: number; x: number; y: number };
  rot0: number; key: string; ox: number; oy: number;
}
interface Sheet {
  el: HTMLElement; kind: string; idx: number; id: string; pin: string; dir: number; paper: HTMLElement; cast: HTMLElement; inner: HTMLElement; shadow: HTMLElement;
  pieces: Piece[]; hold: number; hStart: number; hEnd: number; sStart: number; sEnd: number; overflow: number;
  sw: Spring; mech: (h: number, dt: number, S: Sheet) => void; targets: HTMLElement[]; armG: Arm | null; hx: Spring; hy: Spring; armOn: Spring;
  branch: Branch | null; bird: Bird | null; shown: boolean; side: number;
}
interface Run { root: HTMLElement; stage: HTMLElement; sheets: Sheet[]; top: number; total: number }

export default function start() {
  const main = $<HTMLElement>("main");
  if (!main || !$(".pc-sheet", main)) return;
  const html = document.documentElement;
  const phoneQ = matchMedia("(max-width: 760px)");
  const fine = matchMedia("(pointer: fine)").matches;

  // ------------------------------------------------------------ group sheets into stands; everything else is loose
  const blocks = [...main.children] as HTMLElement[];
  const sheetOf = (el: HTMLElement) => (el.matches("section.pc-sheet") ? el : el.querySelector<HTMLElement>(":scope > section.pc-sheet"));
  const groups: HTMLElement[][] = [];
  let cur: HTMLElement[] | null = null;
  for (const b of blocks) {
    if (sheetOf(b) && !b.querySelector("[data-scene]")) { if (!cur) groups.push((cur = [])); cur.push(b); }
    else { cur = null; b.classList.add("pc-loose"); }
  }

  // headlines: every word its own strip of paper, hung from a pin
  function splitWords(h: HTMLElement) {
    const words: { t: string; em: boolean }[] = [];
    const walk = (n: Node, em: boolean) => {
      if (n.nodeType === 3) (n.textContent || "").split(/\s+/).filter(Boolean).forEach((t) => words.push({ t, em }));
      else n.childNodes.forEach((c) => walk(c, em || (n as Element).tagName === "EM"));
    };
    h.childNodes.forEach((c) => walk(c, false));
    const label = h.textContent?.replace(/\s+/g, " ").trim() || "";
    h.textContent = "";
    h.setAttribute("aria-label", label);
    return words.map((w, i) => {
      const s = document.createElement("span");
      s.className = "pc-word pc-p" + (w.em ? " pc-word--e" : "");
      s.textContent = w.t;
      s.setAttribute("aria-hidden", "true");
      s.dataset.pc = "word";
      h.appendChild(s);
      if (i < words.length - 1) h.appendChild(document.createTextNode(" "));
      return s;
    });
  }

  let pid = 0;
  const runs: Run[] = groups.map((g) => {
    const root = document.createElement("div");
    root.className = "pc-run";
    g[0].before(root);
    const stage = document.createElement("div");
    stage.className = "pc-stage";
    root.appendChild(stage);
    const sheets: Sheet[] = g.map((b, idx) => {
      const el = sheetOf(b)!;
      stage.appendChild(el);
      if (b !== el) b.remove();
      el.style.zIndex = String(g.length - idx);
      const pin = el.dataset.pin || "tl";
      const shadow = document.createElement("i");
      shadow.className = "pc-shadow";
      shadow.setAttribute("aria-hidden", "true");
      el.prepend(shadow);
      return {
        el, kind: el.dataset.kind || "", idx, id: el.id || "", pin, dir: pin === "tl" || pin === "br" ? 1 : -1, paper: $<HTMLElement>(".pc-paper", el)!, cast: $<HTMLElement>(".pc-cast", el)!,
        inner: $<HTMLElement>(".pc-in", el)!, shadow, pieces: [], hold: Number(el.dataset.hold) || 0.8, hStart: 0, hEnd: 0, sStart: 0, sEnd: 0, overflow: 0,
        sw: new Spring(), mech: () => {}, targets: [], armG: null, hx: new Spring(), hy: new Spring(), armOn: new Spring(), branch: null, bird: null, shown: true, side: idx % 2,
      } as Sheet;
    });
    return { root, stage, sheets, top: 0, total: 0 };
  });
  if (!runs.length) return;

  // pieces
  for (const run of runs) for (const S of run.sheets) {
    $$<HTMLElement>("[data-pc='words']", S.el).forEach((t) => splitWords(t));
    let order = 0;
    S.pieces = $$<HTMLElement>(".pc-p", S.el).map((el) => {
      const kind = el.dataset.pc || "note";
      const isWord = kind === "word";
      const ctrl = kind === "spoke";
      const id = pid++;
      return {
        el, kind, from: el.dataset.from || "b", idx: order++, d: 0, q: new Spring(), w: new Spring(), phase: (hash(id) > 0 ? 1 : -1) * (0.6 + Math.abs(hash(id, 3)) * 0.7),
        tilt: kind === "tag" || kind === "rod" || kind === "link" ? 0 : hash(id, 7) * (isWord ? 1.6 : 1.2), ux: 0, uy: 0, vis: true, grab: isWord || kind === "tag" || kind === "photo" || kind === "rod",
        ctrl, baseX: 0, baseY: 0, extra: { r: 0, x: 0, y: 0 }, rot0: (hash(id, 11) > 0 ? 1 : -1) * (22 + Math.abs(hash(id, 13)) * 22), key: "", ox: 0, oy: 0,
      } as Piece;
    });
    S.pieces.forEach((p) => { if (p.grab) p.el.classList.add("pc-grab"); });
    // staggered arrival: words one after another, the rest in order
    let wi = 0, oi = 0;
    for (const p of S.pieces) p.d = p.kind === "word" ? Math.min(wi++ * 0.07, 0.36) : Math.min(0.1 + oi++ * 0.06, 0.45);
  }

  // ------------------------------------------------------------ the art: black paper cut with a stencil of every frame
  const arts = $$<HTMLElement>("[data-pc-art]");
  let art: ArtFrames | null = null;
  const artFrame = new Map<HTMLElement, number>();
  function drawArt(host: HTMLElement, f: number) {
    if (!art) return;
    const c = $<HTMLCanvasElement>("canvas", host);
    if (!c) return;
    const k = ((f % art.n) + art.n) % art.n;
    if (artFrame.get(host) === k) return;
    artFrame.set(host, k);
    const w = art.w, h = art.h, m = art.mask[k];
    if (c.width !== w) { c.width = w; c.height = h; }
    const ctx = c.getContext("2d")!;
    const img = ctx.createImageData(w, h), d = img.data;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = y * w + x;
      let v = m[i] * 4;
      if (x > 0 && x < w - 1 && y > 0 && y < h - 1) v = (m[i] * 4 + m[i - 1] + m[i + 1] + m[i - w] + m[i + w]) / 8 * 2;
      const hole = smooth(0.34, 0.5, v);      // bright parts are cut away, so the sheet shows through
      const border = Math.min(x, y, w - 1 - x, h - 1 - y) < 5;
      const o = i * 4;
      if (border) { d[o] = 247; d[o + 1] = 240; d[o + 2] = 222; d[o + 3] = 255; continue; }
      d[o] = 27; d[o + 1] = 23; d[o + 2] = 21; d[o + 3] = Math.round(255 * (1 - hole));
    }
    ctx.putImageData(img, 0, 0);
  }
  loadArt().then((a) => { art = a; arts.forEach((h) => drawArt(h, 0)); });

  // ------------------------------------------------------------ decoration
  const mkDecor = (S: Sheet) => {
    const night = S.el.dataset.tone === "night";
    const nodes: HTMLElement[] = [];
    const place = (svg: SVGSVGElement, css: string) => { const d = document.createElement("div"); d.className = "pc-decor"; d.setAttribute("aria-hidden", "true"); d.style.cssText = css; d.appendChild(svg); S.cast.before(d); nodes.push(d); return d; };
    const dense = ["timeline", "faq", "gallery", "strip", "orbit", "features", "stats"].includes(S.kind);
    const left = S.idx % 2 === 0;
    const bw = dense ? 300 : 420, bh = dense ? 230 : 330;
    const br = makeBranch(bw, bh, 11 + S.idx * 7, dense ? 11 : 15);
    place(br.svg, `${left ? "left" : "right"}: ${left ? -10 : -10}px; bottom: -6px; width: ${bw}px; height: ${bh}px; ${left ? "" : "transform: scaleX(-1);"} --sil: ${night ? "#efe3c6" : "#1b1715"}`);
    S.branch = br;
    if (S.kind === "hero" || S.kind === "intro" || S.kind === "product" || S.kind === "quote" || S.kind === "cta" || S.idx % 3 === 0) {
      const bd = makeBird();
      place(bd.svg, `left: 0; top: 0; width: 190px; height: 150px; --sil: ${night ? "#efe3c6" : "#1b1715"}`);
      S.bird = bd;
      (bd.svg.parentElement as HTMLElement).dataset.bird = "1";
    }
    if (night) place(makeStars(900, 520, 3 + S.idx, 30), "left: 0; top: 0; width: 100%; height: 60%; --amber: #f0b45a");
    void nodes;
  };
  for (const run of runs) for (const S of run.sheets) mkDecor(S);
  html.classList.add("pc-decor-on");
  if (reduced) { for (const run of runs) for (const S of run.sheets) { if (S.bird) { flap(S.bird, 1.2); const d = S.bird.svg.parentElement as HTMLElement; d.style.left = "58%"; d.style.top = "16%"; } } loadArt().then(() => arts.forEach((h) => drawArt(h, 0))); return; }

  // ------------------------------------------------------------ live
  html.classList.add("pc-live");
  const cue = $<HTMLElement>(".pc-cue");
  cue?.removeAttribute("hidden");
  let vw = innerWidth, vh = innerHeight;
  const sc = () => clamp(Math.min(vw / 1100, vh / 760), 0.55, 1.15);

  // arms
  for (const run of runs) for (const S of run.sheets) {
    const a = makeArm();
    S.paper.after(a.svg);
    S.armG = a;
    a.svg.style.setProperty("--arm", S.el.dataset.tone === "night" ? "#0d0b0a" : "#1b1715");
    a.svg.style.visibility = "hidden";
  }

  // ------------------------------------------------------------ mechanisms
  const piece = (S: Sheet, el: Element) => S.pieces.find((p) => p.el === el);
  for (const run of runs) for (const S of run.sheets) S.mech = mechanism(S);

  function mechanism(S: Sheet): (h: number, dt: number, S: Sheet) => void {
    const el = S.el;
    if (S.kind === "features") {
      const cards = $$<HTMLElement>(".pc-feature", el).map((c) => piece(S, c)!).filter(Boolean);
      const n = cards.length;
      const sp = cards.map(() => new Spring());
      const ys = cards.map(() => new Spring());
      let sel = -1, lastIdx = -1;
      cards.forEach((p, i) => p.el.addEventListener("click", () => { sel = i; }));
      S.targets = cards.map((p) => p.el);
      return (h, dt) => {
        const idx = sel >= 0 ? sel : Math.min(n - 1, Math.floor(clamp(h) * n));
        const open = smooth(0, 0.1, h) * 0.85 + 0.15;
        const spread = phoneQ.matches ? 20 : 30;
        cards.forEach((p, i) => {
          const dist = i - idx;
          const rank = i - (n - 1) / 2;   // the hand of cards stays symmetrical; the speaker stands up out of it
          sp[i].step(dt, rank * spread * open * (dist === 0 ? 0.3 : 1), 120, 15);
          ys[i].step(dt, dist === 0 ? -44 : 0, 120, 16);
          p.extra.r = sp[i].x; p.extra.y = ys[i].x;
          p.baseX = -p.el.offsetWidth / 2;
          if (idx !== lastIdx) p.el.style.zIndex = String(10 - Math.abs(dist));
          p.el.classList.toggle("is-front", dist === 0);
        });
        lastIdx = idx;
      };
    }
    if (S.kind === "timeline") {
      const links = $$<HTMLElement>(".pc-link", el).map((c) => piece(S, c)!).filter(Boolean);
      const n = links.length;
      const rule = $<HTMLElement>(".pc-rule", el)!;
      const fold = links.map(() => new Spring());
      S.targets = links.map((p) => p.el);
      let L = 220, lh = 150;
      const size = () => {
        if (phoneQ.matches) { rule.style.height = ""; links.forEach((p) => { p.el.style.removeProperty("--lw"); p.el.style.removeProperty("--lh"); }); return; }
        const wAvail = rule.parentElement!.clientWidth - 10;
        L = Math.min(280, wAvail / n);
        links.forEach((p) => { p.el.style.setProperty("--lw", `${(L - 3).toFixed(0)}px`); p.el.style.setProperty("--lh", "0px"); });
        lh = Math.max(...links.map((p) => p.el.offsetHeight), 120);
        links.forEach((p) => p.el.style.setProperty("--lh", `${lh}px`));
        rule.style.height = `${lh + 50}px`;
      };
      (S as any).resize = size;
      return (h, dt) => {
        if (phoneQ.matches) {
          links.forEach((p, i) => { fold[i].step(dt, smooth(i / n * 0.7, i / n * 0.7 + 0.25, h), 70, 9); const o = 1 - clamp(fold[i].x, -0.2, 1.3); p.extra.r = -9 * o; p.extra.x = 150 * o; p.baseX = 0; p.baseY = 0; });
          return;
        }
        let x = 0, y = (lh + 50) / 2, a = 0;
        links.forEach((p, i) => {
          const t = i === 0 ? 1 : clamp((h * (n + 0.3) - (i - 1) * 1.0) / 1.0);
          fold[i].step(dt, ease(t), 60, 8);
          const fo = i === 0 ? 1 : fold[i].x;
          a += i === 0 ? 0 : (i % 2 ? -1 : 1) * 168 * (1 - fo);
          p.baseX = x; p.baseY = y - lh / 2; p.extra.r = a;
          p.el.style.zIndex = String(i + 1);
          // the next hinge is at the far end of this link
          x += L * Math.cos(a * Math.PI / 180); y += L * Math.sin(a * Math.PI / 180);
        });
      };
    }
    if (S.kind === "faq") {
      const flaps = $$<HTMLDetailsElement>("details.pc-flap", el);
      const n = flaps.length;
      const ajar = flaps.map(() => new Spring());
      let touched = false;
      flaps.forEach((d) => d.querySelector("summary")?.addEventListener("click", () => { touched = true; }));
      S.targets = flaps;
      let last = -1;
      return (h, dt) => {
        if (!touched) {
          const k = h < 0.05 ? 0 : Math.floor(h * n + 0.35);
          if (k !== last) { last = k; flaps.forEach((d, i) => { d.open = i < k; }); }
        }
        flaps.forEach((d, i) => {
          const s = d.querySelector("summary") as HTMLElement;
          ajar[i].step(dt, d.open ? 1 : 0, 110, 11);
          s.style.transformOrigin = "16px 16px";
          s.style.rotate = `${(-ajar[i].x * 9).toFixed(2)}deg`;
          s.style.translate = `${(ajar[i].x * 10).toFixed(1)}px ${(-ajar[i].x * 5).toFixed(1)}px`;
        });
      };
    }
    if (S.kind === "stats") {
      const rod = piece(S, $<HTMLElement>(".pc-rod", el)!);
      const tags = $$<HTMLElement>(".pc-tag", el).map((c) => piece(S, c)!).filter(Boolean);
      S.targets = tags.map((p) => p.el);
      return () => { void rod; void tags; };
    }
    if (S.kind === "orbit") {
      const spokes = $$<HTMLElement>(".pc-spoke", el).map((c) => piece(S, c)!).filter(Boolean);
      const n = spokes.length;
      const wheel = new Spring();
      S.targets = spokes.map((p) => $<HTMLElement>(".pc-spoke__disc", p.el)!);
      return (h, dt) => {
        wheel.step(dt, h * 72, 40, 8);
        spokes.forEach((p, i) => {
          const base = (i / n) * 360 - 90;
          const q = clamp(p.q.x, -0.3, 1.3);
          const a = -90 + (base + 90) * q + wheel.x;
          p.el.style.rotate = `${a.toFixed(2)}deg`;
          const disc = $<HTMLElement>(".pc-spoke__disc", p.el);
          if (disc) disc.style.rotate = `${(-a).toFixed(2)}deg`;
        });
      };
    }
    if (S.kind === "strip") {
      const reel = $<HTMLElement>(".pc-band__reel", el);
      const sp = new Spring();
      S.targets = $$<HTMLElement>(".pc-cut", el);
      return (h, dt) => {
        if (!reel) return;
        const room = Math.max(0, reel.scrollWidth - reel.parentElement!.clientWidth);
        sp.step(dt, -room * clamp(h * 1.05), 50, 10);
        reel.style.translate = `${sp.x.toFixed(1)}px 0`;
      };
    }
    if (S.kind === "gallery") { S.targets = $$<HTMLElement>(".pc-snap", el); return () => {}; }
    if (S.kind === "product") {
      const opts = $$<HTMLElement>(".ss-app__opt", el);
      S.targets = $$<HTMLElement>(".pc-pill", el).concat($$<HTMLElement>(".pc-btn", el));
      return (h) => { if (opts.length > 1) { const k = Math.min(opts.length - 1, Math.floor(clamp(h) * opts.length)); opts.forEach((o, i) => o.classList.toggle("is-on", i === k)); } };
    }
    if (S.kind === "quote") { S.targets = $$<HTMLElement>(".pc-balloon", el); return () => {}; }
    S.targets = $$<HTMLElement>(".pc-btn", el).concat($$<HTMLElement>(".pc-note", el));
    return () => {};
  }

  // ------------------------------------------------------------ layout: pin positions, tracks
  function layout() {
    vw = innerWidth; vh = innerHeight;
    for (const run of runs) {
      let P = 0;
      run.sheets.forEach((S, i) => {
        const pad = 26;
        S.el.style.transformOrigin = S.pin === "tl" ? `${pad}px ${pad}px` : S.pin === "tr" ? `calc(100% - ${pad}px) ${pad}px` : S.pin === "br" ? `calc(100% - ${pad}px) calc(100% - ${pad}px)` : `${pad}px calc(100% - ${pad}px)`;
        S.overflow = Math.max(0, S.inner.scrollHeight - vh);
        (S as any).resize?.();
        S.overflow = Math.max(0, S.inner.scrollHeight - vh);
        S.hStart = P; S.hEnd = P + S.hold + S.overflow / vh * 0.8;
        S.sStart = S.hEnd; S.sEnd = S.sStart + (i < run.sheets.length - 1 ? SW : 0.25);
        P = S.sEnd;
        S.pieces.forEach((p) => {
          const cs = getComputedStyle(p.el);
          const o = cs.transformOrigin.split(" ");
          p.ox = parseFloat(o[0]) || 0; p.oy = parseFloat(o[1]) || 0;
        });
        // the birds and branches are sized to the sheet
        const sz = sc();
        if (S.branch) { const d = S.branch.svg.parentElement as HTMLElement; d.style.scale = String(sz); d.style.transformOrigin = S.idx % 2 === 0 ? "0 100%" : "100% 100%"; }
      });
      run.total = P + 0.1;
      run.root.style.height = `${((run.total + 1) * vh).toFixed(0)}px`;
    }
    measure();
  }
  function measure() { for (const r of runs) r.top = r.root.getBoundingClientRect().top + scrollY; }

  // ------------------------------------------------------------ the frame
  let t0 = performance.now(), started = false, gust = 0, gustSp = new Spring();
  let lastY = scrollY, lastScroll = 0, lastId = "";
  const navLinks = $$<HTMLAnchorElement>(".pc-head__nav a");
  let armOverride: { S: Sheet; el: HTMLElement | null; x?: number; y?: number; until: number } | null = null;
  let dragArm: { S: Sheet; px: number; py: number } | null = null;

  function placePiece(S: Sheet, p: Piece, u: number, dt: number, gustNow: number) {
    const tgt = ease(clamp((u - p.d) / 0.5));
    p.q.step(dt, tgt, 78, 8.5);
    const q = p.q.x;
    // hanging things sway with the speed of the scroll
    const hang = p.kind === "word" || p.kind === "tag" || p.kind === "rod" || p.el.classList.contains("pc-snap") || p.el.classList.contains("pc-balloon");
    if (!p.el.classList.contains("is-held")) { p.w.step(dt, 0, 55, 3.2); if (hang) p.w.v += p.phase * gustNow * 420 * dt; }
    if (p.ctrl) return;
    const k = 1 - q;
    let x0 = 0, y0 = 0, r0 = p.rot0;
    const f = p.from;
    if (p.kind === "link" || p.kind === "fan") { y0 = 0.7 * vh; r0 = 0; }
    else if (p.kind === "word" || p.kind === "tag" || p.kind === "rod" || f === "t") { y0 = -0.55 * vh; r0 = p.rot0 * 1.1; }
    else if (f === "l") { x0 = -0.5 * vw; r0 *= 0.8; }
    else if (f === "r") { x0 = 0.5 * vw; r0 *= 0.8; }
    else { y0 = 0.7 * vh; r0 *= 0.7; }
    if (p.kind === "rod") { x0 = 0; r0 = 0; }
    const x = x0 * k + p.ux + p.baseX + p.extra.x, y = y0 * k + p.uy + p.baseY + p.extra.y;
    const r = p.tilt + r0 * k + p.w.x + p.extra.r;
    const key = `${x.toFixed(1)}|${y.toFixed(1)}|${r.toFixed(2)}`;
    if (key !== p.key) { p.key = key; p.el.style.translate = `${x.toFixed(1)}px ${y.toFixed(1)}px`; p.el.style.rotate = `${r.toFixed(2)}deg`; }
  }

  function frame(f: { y: number; v: number; dt: number; t: number }) {
    const dt = Math.min(0.04, f.dt || 0.016);
    const now = performance.now();
    if (!started && now - t0 > 250) started = true;
    if (scrollY !== lastY) { lastY = scrollY; lastScroll = now; if (cue) cue.hidden = true; }
    // gust: how fast the page is being scrolled (signed)
    gustSp.step(dt, clamp(f.v / 26, -1.6, 1.6), 30, 9);
    const gustNow = gustSp.x;
    let curId = "";
    runs.forEach((run) => {
      const L = (scrollY - run.top) / vh;
      if (L < -1.3 || L > run.total + 1.3) return;
      const n = run.sheets.length;
      const ss = run.sheets.map((S) => clamp((L - S.sStart) / Math.max(0.01, S.sEnd - S.sStart)));
      let tIdx = ss.findIndex((v, i) => i < n - 1 && v < 1);
      if (tIdx < 0) tIdx = n - 1;
      run.sheets.forEach((S, i) => {
        // a sheet that was not on the stand and is already behind the camera simply isn't there: it doesn't swing past
        if (!S.shown && i < tIdx) { S.sw.x = 1; S.sw.v = 0; }
        else S.sw.step(dt, i < n - 1 ? ease(ss[i]) : 0, 46, 8.2);
      });
      run.sheets.forEach((S, i) => {
        const near = i <= tIdx + 1 && S.sw.x < 0.995 && L > -1.2;
        if (near !== S.shown) { S.shown = near; S.el.classList.toggle("pc-off", !near); }
        if (!near) return;
        const h = (L - S.hStart) / Math.max(0.01, S.hEnd - S.hStart);
        const prev = run.sheets[i - 1];
        const u = i === 0 ? (started ? 1 : 0) : smooth(0.02, 0.9, clamp((L - prev.sStart) / Math.max(0.01, prev.sEnd - prev.sStart)));
        const ang = S.dir * ANG * S.sw.x;
        S.el.style.rotate = Math.abs(ang) < 0.02 ? "" : `${ang.toFixed(2)}deg`;
        const lift = clamp(Math.abs(S.sw.x) * 1.6);
        S.shadow.style.translate = `${(lift * 18).toFixed(1)}px ${(lift * 26).toFixed(1)}px`;
        S.shadow.style.opacity = (lift * 0.32).toFixed(3);
        // pan a sheet taller than the screen
        const pan = S.overflow > 0 ? -S.overflow * smooth(0.04, 0.96, clamp(h)) : 0;
        S.inner.style.translate = pan ? `0 ${pan.toFixed(1)}px` : "";
        const hh = clamp(h);
        S.mech(hh, dt, S);
        S.pieces.forEach((p) => placePiece(S, p, u, dt, gustNow));
        // decoration
        if (S.branch) swayBranch(S.branch, f.t, gustNow);
        if (S.bird) {
          const d = S.bird.svg.parentElement as HTMLElement;
          const pr = clamp((L - S.hStart + 0.2) / (S.hEnd - S.hStart + 0.6 + (i < n - 1 ? SW : 0)));
          const x = -240 + (vw + 480) * pr, y = vh * (0.1 + 0.05 * Math.sin(pr * 5 + i)) + Math.sin(pr * 11) * 14;
          d.style.translate = `${x.toFixed(1)}px ${y.toFixed(1)}px`;
          d.style.rotate = `${(-8 + Math.cos(pr * 11) * 6).toFixed(1)}deg`;
          d.style.scale = String(sc() * 0.85);
          flap(S.bird, scrollY * 0.07 + i);
        }
        // the arm
        if (S.armG) updateArm(S, h, u, dt, now);
        S.el.querySelectorAll?.("[data-pc-art]");
        if (i === tIdx && S.id && u > 0.8) curId = S.id;
      });
      arts.forEach((hst) => { const sh = hst.closest<HTMLElement>(".pc-sheet"); if (sh && !sh.classList.contains("pc-off")) drawArt(hst, Math.floor(scrollY / 85)); });
    });
    if (curId !== lastId) { lastId = curId; navLinks.forEach((a) => a.classList.toggle("is-on", !!curId && a.getAttribute("href") === `#${curId}`)); }
  }

  function updateArm(S: Sheet, h: number, u: number, dt: number, now: number) {
    const a = S.armG!;
    const left = S.side === 0;
    const sz = sc();
    const sx = left ? vw * 0.1 : vw * 0.9, sy = vh + 40 * sz;
    const hold = h > -0.05 && h < 1.05 && u > 0.85 && S.sw.x < 0.02;
    S.armOn.step(dt, hold && !phoneQ.matches ? 1 : 0, 40, 10);
    if (S.armOn.x < 0.02 && S.armOn.v < 0.01 && !hold) { a.svg.style.visibility = "hidden"; return; }
    a.svg.style.visibility = "visible";
    // the item the scroll has reached
    let el: HTMLElement | null = null;
    const tg = S.targets;
    if (armOverride && armOverride.S === S && now < armOverride.until) el = armOverride.el;
    else if (tg.length) el = tg[Math.min(tg.length - 1, Math.max(0, Math.floor(clamp(h) * tg.length)))];
    let tx = sx + (left ? 30 : -30) * sz, ty = vh + 10;
    if (dragArm && dragArm.S === S) { tx = dragArm.px; ty = dragArm.py; }
    else if (el) {
      const r = el.getBoundingClientRect(), sr = S.el.getBoundingClientRect();
      if (sr.width > 0) { tx = clamp(r.left - sr.left + r.width * (left ? 0.3 : 0.7), 30, vw - 30); ty = Math.min(vh - 6, r.bottom - sr.top + 6); }
    }
    const on = S.armOn.x;
    S.hx.step(dt, sx + (tx - sx) * clamp(on, 0, 1), 36, 8);
    S.hy.step(dt, sy + (ty - sy) * clamp(on, 0, 1), 36, 8);
    poseArm(a, sx, sy, S.hx.x, S.hy.x, left ? -1 : 1, sz);
  }

  // ------------------------------------------------------------ the hand: pick pieces up and swing them, take the arm's hand
  function pieceAt(target: EventTarget | null): { S: Sheet; p: Piece } | null {
    const el = (target as HTMLElement | null)?.closest?.<HTMLElement>(".pc-p");
    if (!el) return null;
    for (const r of runs) for (const S of r.sheets) { const p = S.pieces.find((q) => q.el === el); if (p) return { S, p }; }
    return null;
  }
  let drag: { S: Sheet; p: Piece; x0: number; moved: boolean } | null = null;
  main.addEventListener("pointerdown", (e) => {
    const hit = pieceAt(e.target);
    const hand = (e.target as Element).closest?.("[data-hand]");
    if (hand && e.pointerType === "mouse") {
      const S = runs.flatMap((r) => r.sheets).find((s) => s.armG && s.armG.svg.contains(hand));
      if (S) { dragArm = { S, px: e.clientX, py: e.clientY }; S.armG!.svg.classList.add("is-held"); (hand as Element).setPointerCapture?.(e.pointerId); e.preventDefault(); }
      return;
    }
    if (hit && hit.p.grab && e.pointerType === "mouse" && e.button === 0) { drag = { S: hit.S, p: hit.p, x0: e.clientX, moved: false }; hit.p.el.classList.add("is-held"); }
  });
  addEventListener("pointermove", (e) => {
    if (dragArm) { dragArm.px = e.clientX; dragArm.py = e.clientY; return; }
    if (!drag) return;
    const dx = e.clientX - drag.x0;
    if (!drag.moved && Math.abs(dx) < 5) return;
    drag.moved = true;
    drag.p.w.x = clamp(dx * 0.35, -55, 55); drag.p.w.v = 0;
  });
  const endDrag = () => {
    if (dragArm) { dragArm.S.armG?.svg.classList.remove("is-held"); dragArm = null; }
    if (drag) { drag.p.el.classList.remove("is-held"); const d = drag; setTimeout(() => { if (drag === d) drag = null; }, 0); }
  };
  addEventListener("pointerup", endDrag);
  addEventListener("pointercancel", endDrag);
  // a tap flicks a hanging piece; hovering an item sends the arm to it
  main.addEventListener("click", (e) => {
    if (drag?.moved) return;
    const hit = pieceAt(e.target);
    if (hit && !(e.target as Element).closest("a, button, summary")) hit.p.w.v += (hit.p.phase > 0 ? 1 : -1) * 240;
  });
  if (fine) main.addEventListener("pointerover", (e) => {
    const t = (e.target as HTMLElement).closest<HTMLElement>(".pc-p, .pc-spoke__disc");
    if (!t) return;
    for (const r of runs) for (const S of r.sheets) if (S.shown && S.targets.some((x) => x === t || x.contains(t))) armOverride = { S, el: S.targets.find((x) => x === t || x.contains(t)) || null, until: performance.now() + 1600 };
  });

  // ------------------------------------------------------------ links open the right sheet
  function sheetY(id: string): number | null {
    for (const run of runs) { const S = run.sheets.find((s) => s.id === id); if (S) return Math.round(run.top + (S.hStart + 0.25) * vh); }
    return null;
  }
  (window as any).__pcY = (id: string) => sheetY(id);   // for review captures
  document.addEventListener("click", (e) => {
    const a = (e.target as HTMLElement).closest<HTMLAnchorElement>('a[href^="#"]');
    if (!a) return;
    const id = a.getAttribute("href")!.slice(1);
    if (!id) return;
    const y = sheetY(id);
    if (y == null) return;
    e.preventDefault(); e.stopPropagation();
    const from = scrollY, dist = y - from, dur = Math.min(2200, 600 + Math.abs(dist) / vh * 280), t1 = performance.now();
    const step = (now: number) => { const q = clamp((now - t1) / dur); scrollTo(0, from + dist * ease(q)); if (q < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }, { capture: true });
  document.addEventListener("focusin", (e) => {
    const sh = (e.target as HTMLElement).closest?.<HTMLElement>(".pc-sheet");
    if (!sh) return;
    for (const run of runs) { const S = run.sheets.find((x) => x.el === sh); if (S && !S.shown) scrollTo(0, Math.round(run.top + (S.hStart + 0.3) * vh)); }
  });

  layout();
  addEventListener("resize", layout);
  phoneQ.addEventListener?.("change", layout);
  document.fonts?.ready.then(layout);
  setTimeout(layout, 900);
  addEventListener("load", layout);
  if (location.hash.length > 1) { const y = sheetY(location.hash.slice(1)); if (y != null) requestAnimationFrame(() => scrollTo(0, y)); }
  setInterval(() => { void lastScroll; }, 1000);
  onFrame(frame);
}
