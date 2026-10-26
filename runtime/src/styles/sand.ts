/**
 * Sand: one picture in sand on a light table, never cut. The table is a density field (cells of a few CSS px) shaded
 * as real grains lit from below: each grain-sized spot is covered or not by chance in proportion to the sand there,
 * so thin sand glows amber with single grains showing, thick sand goes dark, edges break up into scattered grains,
 * and a few grains catch the room light. Every section is a scene composed from its own stage in thin and thick sand:
 * dunes, finger-drawn ripples, a disc with a poured numeral, the phone's outline with its real screen glowing through,
 * silhouettes of images and theme.art, a poured path, an iris for the quote, a ring for the CTA. Copy sits on clean
 * glass; headlines are crisp HTML written on as the fingers go, with a little sand spilled along them. Scroll is the
 * hand: between scenes the side of a hand swings an arc across the table, the sand it meets piles into a moving front
 * and grains stream and roll ahead of it, the next scene is left behind it clean, and the copy is uncovered behind
 * the pile. The fingers then finish (pour, write, draw ripples). Nothing is a crossfade and nothing rewinds: scrolling
 * back sweeps again. The pointer is a fingertip: furrows with ridges either side that stay until a sweep passes.
 * Reduced motion: still sand pictures swapped in one step. Research: docs/styles/styles-22-23.md, section 23.
 */
import { $, $$, onFrame, reduced } from "./_kit";
import { loadArt, type ArtFrames } from "./_art";
import { clamp } from "../lib/util";

const sstep = (a: number, b: number, v: number) => { const t = clamp((v - a) / (b - a)); return t * t * (3 - 2 * t); };
const mobile = () => innerWidth < 760;
const hash = (i: number) => { let x = Math.imul(i ^ 0x9e3779b9, 0x85ebca6b); x ^= x >>> 13; x = Math.imul(x, 0xc2b2ae35); x ^= x >>> 16; return (x >>> 0) / 4294967296; };
const R2D = 180 / Math.PI;

type Src = { el: HTMLElement; kind: string; steps: number[] | null };
type Plate = {
  kind: "plate"; el: HTMLElement; stage: HTMLElement; type: string; n: number; draw: boolean; idx: number;
  srcs: Src[]; inks: { el: HTMLElement; steps: number[] | null }[]; wraps: { el: HTMLElement; steps: number[]; v: string }[];
  top: number; sv: { el: HTMLElement; v: string };
};
type Flow = { kind: "flow"; el: HTMLElement; idx: number; top: number; h: number };
type Sec = Plate | Flow;
type Ops = { idx: Int32Array; ord: Float32Array; val: Float32Array };
type Reveal = { el: HTMLElement; lo: number; hi: number; v: string };
type Scene = { sec: Sec; step: number; m: number; anchors: number[]; s0: number; s1: number; base: Float32Array; ops: Ops; fin: Float32Array | null; p: number; reveals: Reveal[] };
type Geo = { px: number; py: number; a0: number; span: number; U: Float32Array; R: Float32Array; rmin: number; rmax: number };
type Pos = { sweep: boolean; i: number; v: number };
type Rect = { x: number; y: number; w: number; h: number };

function stepsOf(el: HTMLElement, stage: HTMLElement): number[] | null {
  const s = el.closest<HTMLElement>("[data-step]");
  if (!s || !stage.contains(s)) return null;
  return (s.dataset.step || "").trim().split(/\s+/).filter(Boolean).map(Number);
}
function dims(m: any): [number, number] { return [m.naturalWidth || m.videoWidth || m.width || 0, m.naturalHeight || m.videoHeight || m.height || 0]; }

// ------------------------------------------------------------------------------------------------ the table (WebGL)
const VS = `attribute vec2 p; void main(){ gl_Position = vec4(p, 0., 1.); }`;
const FS = `precision highp float;
uniform sampler2D uD; uniform vec2 uGrid; uniform float uCell; uniform vec2 uRes; uniform vec2 uOff; uniform float uGrain;
float hash(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float vnoise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3. - 2. * f);
  return mix(mix(hash(i), hash(i + vec2(1., 0.)), f.x), mix(hash(i + vec2(0., 1.)), hash(i + vec2(1., 1.)), f.x), f.y); }
float dens(vec2 g){ return texture2D(uD, g / uGrid).r * 2.3; }
void main(){
  vec2 px = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y);
  vec2 g = (px - uOff) / uCell;
  float d = dens(g);
  // clumps: sand never lies perfectly even
  float cl = vnoise(px / (uGrain * 5.)) * .6 + vnoise(px / (uGrain * 17.)) * .4;
  float dd = max(0., d * (.72 + .56 * cl) + .006);
  vec2 gp = floor(px / uGrain);
  float r1 = hash(gp), r2 = hash(gp + 17.31), r3 = hash(gp + 41.7);
  // is this grain-sized spot covered by a grain? (more sand, more likely)
  float cov = 1. - exp(-2.5 * dd);
  float covered = smoothstep(r1 - .05, r1 + .05, cov);
  // the glass, lit from below: warm at the centre, deeper amber to the rim
  vec2 sc = px / uRes - .5;
  float r2c = dot(sc * vec2(1.15, 1.), sc * vec2(1.15, 1.));
  vec3 light = mix(vec3(1., .955, .80), vec3(.95, .64, .30), smoothstep(.0, .42, r2c));
  light *= 1. - .35 * smoothstep(.2, .55, r2c);
  // light that reaches between the grains, filtered by the layers below
  float tr = exp(-2.3 * max(0., dd - .12));
  vec3 gap = light * tr * mix(vec3(1.), vec3(1., .62, .3), clamp(dd * 1.4, 0., 1.));
  // a grain: translucent amber when it lies alone, dark where grains stack
  float stack = smoothstep(.22, 1.05, dd);
  vec3 grain = mix(light * vec3(.80, .44, .16), vec3(.12, .065, .03), stack) * (.62 + .7 * r2);
  vec3 col = mix(gap, grain, covered);
  // relief on thick sand: ridges catch the room light
  float gx = dens(g + vec2(.9, 0.)) - dens(g - vec2(.9, 0.)), gy = dens(g + vec2(0., .9)) - dens(g - vec2(0., .9));
  col += vec3(.32, .2, .1) * clamp(-(gx + gy) * .35, 0., 1.) * stack * covered;
  // sparkle: a few quartz grains glint
  col += vec3(1., .88, .6) * step(.9955, r3) * covered * smoothstep(.1, .6, dd) * .75;
  gl_FragColor = vec4(col, 1.);
}`;
const PVS = `attribute vec2 a; attribute vec3 b; uniform vec2 uView; uniform float uDpr; varying vec2 vb;
void main(){ gl_Position = vec4(a.x / uView.x * 2. - 1., 1. - a.y / uView.y * 2., 0., 1.); gl_PointSize = b.x * uDpr; vb = b.yz; }`;
const PFS = `precision mediump float; varying vec2 vb;
void main(){ vec2 q = gl_PointCoord - .5; float r = length(q); if (r > .5) discard;
  vec3 c = mix(vec3(.13, .07, .03), vec3(.62, .33, .12), vb.y);
  gl_FragColor = vec4(c, vb.x * smoothstep(.5, .25, r)); }`;

function makeTable(canvas: HTMLCanvasElement) {
  const gl = (canvas.getContext("webgl", { antialias: false, alpha: false }) || canvas.getContext("experimental-webgl")) as WebGLRenderingContext | null;
  if (!gl) return null;
  const sh = (type: number, src: string) => { const s = gl.createShader(type)!; gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || "shader"); return s; };
  const link = (vs: string, fs: string) => { const p = gl.createProgram()!; gl.attachShader(p, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(p); if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error("link"); return p; };
  let prog: WebGLProgram, pprog: WebGLProgram;
  try { prog = link(VS, FS); pprog = link(PVS, PFS); } catch { return null; }
  const quad = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, quad);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const pbuf = gl.createBuffer();
  const loc = gl.getAttribLocation(prog, "p"), la = gl.getAttribLocation(pprog, "a"), lb = gl.getAttribLocation(pprog, "b");
  gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
  const U = (n: string) => gl.getUniformLocation(prog, n), UP = (n: string) => gl.getUniformLocation(pprog, n);
  const u = { D: U("uD"), grid: U("uGrid"), cell: U("uCell"), res: U("uRes"), off: U("uOff"), grain: U("uGrain"), view: UP("uView"), dpr: UP("uDpr") };
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  let cols = 0, rows = 0;
  return {
    size(w: number, h: number, dpr: number, c: number, r: number, cell: number, ox: number, oy: number) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.useProgram(prog);
      gl.uniform1i(u.D, 0);
      gl.uniform2f(u.res, canvas.width, canvas.height);
      gl.uniform1f(u.cell, cell * dpr);
      gl.uniform2f(u.off, ox * dpr, oy * dpr);
      gl.uniform2f(u.grid, c, r);
      gl.uniform1f(u.grain, Math.max(1, 1.15 * dpr));
      gl.useProgram(pprog);
      gl.uniform2f(u.view, w, h);
      gl.uniform1f(u.dpr, dpr);
      cols = c; rows = r;
    },
    draw(d: Uint8Array, parts: Float32Array, np: number) {
      gl.useProgram(prog);
      gl.disable(gl.BLEND);
      gl.bindBuffer(gl.ARRAY_BUFFER, quad);
      gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.LUMINANCE, cols, rows, 0, gl.LUMINANCE, gl.UNSIGNED_BYTE, d);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.disableVertexAttribArray(loc);
      if (!np) return;
      gl.useProgram(pprog);
      gl.enable(gl.BLEND);
      gl.bindBuffer(gl.ARRAY_BUFFER, pbuf);
      gl.bufferData(gl.ARRAY_BUFFER, parts.subarray(0, np * 5), gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(la); gl.vertexAttribPointer(la, 2, gl.FLOAT, false, 20, 0);
      gl.enableVertexAttribArray(lb); gl.vertexAttribPointer(lb, 3, gl.FLOAT, false, 20, 8);
      gl.drawArrays(gl.POINTS, 0, np);
      gl.disableVertexAttribArray(la); gl.disableVertexAttribArray(lb);
    },
  };
}

// ------------------------------------------------------------------------------------------------ the experience
export default function start() {
  const canvas = $<HTMLCanvasElement>(".sd-canvas");
  if (!canvas) return;
  const table = makeTable(canvas);
  if (!table) return;   // no WebGL: the printed table (static CSS) stays
  const root = document.documentElement;

  const secs: Sec[] = [];
  $$<HTMLElement>("main section").filter((s) => !s.parentElement?.closest("section")).forEach((el, idx) => {
    if (el.classList.contains("sd-scene")) {
      const stage = $<HTMLElement>(".sd-stage", el)!;
      secs.push({
        kind: "plate", el, stage, type: el.dataset.sd || "", n: Math.max(1, +(el.dataset.steps || 1)), draw: el.dataset.mode === "draw", idx,
        srcs: $$<HTMLElement>("[data-sand]", stage).map((s) => ({ el: s, kind: s.dataset.sand || "", steps: stepsOf(s, stage) })),
        inks: $$<HTMLElement>(".sd-ink, .sd-head", stage).map((s) => ({ el: s, steps: stepsOf(s, stage) })),
        wraps: $$<HTMLElement>("[data-step]", stage).map((s) => ({ el: s, steps: (s.dataset.step || "").trim().split(/\s+/).filter(Boolean).map(Number), v: "" })),
        top: 0, sv: { el: stage, v: "" },
      });
    } else secs.push({ kind: "flow", el, idx, top: 0, h: 0 });
  });
  if (!secs.length) return;
  root.classList.add("sd-live");

  // words of written, poured and carved text become spans, so each can be drawn in sand at its measured place
  secs.forEach((s) => s.kind === "plate" && s.srcs.forEach((src) => {
    if (src.kind !== "write" && src.kind !== "pour" && src.kind !== "carve") return;
    const walk = (node: Node) => {
      if (node.nodeType === 3) {
        const frag = document.createDocumentFragment();
        (node.textContent || "").split(/(\s+)/).forEach((part) => {
          if (!part) return;
          if (/^\s+$/.test(part)) { frag.appendChild(document.createTextNode(" ")); return; }
          // hyphenated words can break after the hyphen: each piece is measured where it lands
          part.split(/(?<=[-‐–])/).forEach((piece) => { const w = document.createElement("span"); w.className = "sd-w"; w.textContent = piece; frag.appendChild(w); });
        });
        node.parentNode!.replaceChild(frag, node);
      } else if (!(node as HTMLElement).classList?.contains("sd-w")) [...node.childNodes].forEach(walk);
    };
    [...src.el.childNodes].forEach(walk);
  }));

  // ---------------------------------------------------------------- grid
  let W = 0, Hh = 0, C = 2.5, cols = 0, rows = 0, OX = 0, OY = 0, N = 0, L = 0;
  let F = new Float32Array(0), RG = new Float32Array(0), U8 = new Uint8Array(0);
  let touched: number[] = [];
  const cc = document.createElement("canvas");
  const cx = cc.getContext("2d", { willReadFrequently: true })!;
  const tmp = document.createElement("canvas");
  const tx = tmp.getContext("2d", { willReadFrequently: true })!;
  let scenes: Scene[] = [];
  const geos = new Map<number, Geo>();
  let art: ArtFrames | null = null;
  // grains in flight (x, y, vx, vy, life, size, shade)
  const PMAX = mobile() ? 1600 : 4200;
  const pX = new Float32Array(PMAX), pY = new Float32Array(PMAX), pVX = new Float32Array(PMAX), pVY = new Float32Array(PMAX), pL = new Float32Array(PMAX), pL0 = new Float32Array(PMAX), pS = new Float32Array(PMAX), pC = new Float32Array(PMAX);
  let np = 0;
  const pbuf = new Float32Array(PMAX * 5);

  function geometry() {
    W = innerWidth; Hh = innerHeight;
    C = mobile() ? 2.2 : clamp(W / 576, 2.2, 3.2);
    cols = Math.ceil(W / C) + 1; rows = Math.ceil(Hh / C) + 1;
    OX = (W - cols * C) / 2; OY = (Hh - rows * C) / 2;
    N = cols * rows;
    F = new Float32Array(N); RG = new Float32Array(N); U8 = new Uint8Array(N); touched = [];
    cc.width = cols; cc.height = rows;
    table!.size(W, Hh, Math.min(devicePixelRatio || 1, mobile() ? 1.75 : 2), cols, rows, C, OX, OY);
    geos.clear(); np = 0;
  }

  // ---------------------------------------------------------------- composing a scene
  const rel = (el: Element, stage: Element): Rect => { const a = el.getBoundingClientRect(), b = stage.getBoundingClientRect(); return { x: a.left - b.left, y: a.top - b.top, w: a.width, h: a.height }; };
  const SCALE = 1.4;   // canvas 255 = this much sand
  const grey = (d: number) => { const g = Math.round(clamp(d / SCALE) * 255); return `rgb(${g},${g},${g})`; };
  const cssT = () => cx.setTransform(1 / C, 0, 0, 1 / C, -OX / C, -OY / C);
  const reset = () => { cx.setTransform(1, 0, 0, 1, 0, 0); cx.globalCompositeOperation = "source-over"; cx.filter = "none"; cx.clearRect(0, 0, cols, rows); };
  const blur = (px: number) => { cx.filter = `blur(${Math.max(0.6, px / C).toFixed(2)}px)`; };

  function wordsOf(el: HTMLElement) { return $$<HTMLElement>(".sd-w", el); }
  function fillWord(w: HTMLElement, stage: HTMLElement) {
    const r = rel(w, stage);
    const cs = getComputedStyle(w), size = parseFloat(cs.fontSize);
    cx.font = `${cs.fontStyle} ${cs.fontWeight} ${size}px ${cs.fontFamily}`;
    const m = cx.measureText(w.textContent || "");
    const asc = m.fontBoundingBoxAscent ?? size * 0.8, desc = m.fontBoundingBoxDescent ?? size * 0.25;
    cx.fillText(w.textContent || "", r.x, r.y + (r.h - (asc + desc)) / 2 + asc);
    return r;
  }
  /** A wavy contour (for dune tops and ripple lines). */
  function wave(x0: number, x1: number, y: number, amp: number, ph: number, f = 1) {
    const pts: [number, number][] = [];
    for (let x = x0; x <= x1 + 1; x += 6) pts.push([x, y + Math.sin((x / W) * 5.3 * f + ph) * amp + Math.sin((x / W) * 13.1 * f + ph * 1.7) * amp * 0.3]);
    return pts;
  }

  type Group = { kind: "carve" | "pour" | "groove"; draw: () => void; region: Rect; order: (gx: number, gy: number) => number; el?: HTMLElement; spill?: number };

  function compose(sec: Plate, step: number): { base: Float32Array; ops: Ops; reveals: Reveal[] } {
    const stage = sec.stage;
    const vis = (s: { steps: number[] | null }) => sec.draw || !s.steps || s.steps.includes(step);
    const groups: { g: Group; step: number }[] = [];
    reset(); cssT();
    cx.globalCompositeOperation = "lighten";
    let seed = sec.idx * 7.1 + step * 3.3;
    for (const s of sec.srcs) {
      if (!vis(s)) continue;
      const el = s.el, gstep = sec.draw ? (s.steps ? s.steps[0] : 0) : 0;
      seed += 1.7;
      const r = rel(el, stage);
      if (s.kind === "write") textGroups(el, stage, "pour", gstep, groups, 0.55, true);
      else if (s.kind === "pour") textGroups(el, stage, "pour", gstep, groups, 1.25, false);
      else if (s.kind === "carve") textGroups(el, stage, "carve", gstep, groups, 1, false);
      else if (s.kind === "dunes") {
        // dunes along the foot of the table: thin sand thickening toward the rim, with grooves along their contour
        cx.save();
        [[0.35, 0.0, 1.0], [0.7, 2.1, 0.66], [1.15, 4.2, 0.34]].forEach(([d, ph, top]) => {
          blur(6); cx.fillStyle = grey(d);
          cx.beginPath(); cx.moveTo(r.x - 20, r.y + r.h + 20);
          for (const [x, y] of wave(r.x - 20, r.x + r.w + 20, r.y + r.h * (1 - top) + r.h * 0.12, r.h * 0.2, ph)) cx.lineTo(x, Math.max(r.y, y));
          cx.lineTo(r.x + r.w + 20, r.y + r.h + 20); cx.closePath(); cx.fill();
        });
        cx.restore(); cssT(); cx.globalCompositeOperation = "lighten";
        for (let k = 0; k < 3; k++) {
          const pts = wave(r.x, r.x + r.w, r.y + r.h * (0.55 + k * 0.15), r.h * 0.08, 1.3 + k * 0.9);
          grooveGroup(pts, Math.max(3, r.h * 0.025), gstep, groups);
        }
      } else if (s.kind === "ripples") {
        // a bed of thin sand with finger-drawn ripples, as in a sand garden, kept below the copy
        let low = 0;
        for (const ik of sec.inks) if (vis(ik)) for (const q of ik.el.getClientRects()) low = Math.max(low, q.bottom - stage.getBoundingClientRect().top);
        const top0 = Math.max(r.y, low + 36);
        if (r.y + r.h - top0 < 70) continue;
        r.h = r.y + r.h - top0; r.y = top0;
        cx.save(); blur(16); cx.fillStyle = grey(0.5);
        cx.beginPath(); const top = wave(r.x - 30, r.x + r.w + 30, r.y + r.h * 0.12, r.h * 0.07, seed);
        cx.moveTo(r.x - 30, r.y + r.h + 30); for (const [x, y] of top) cx.lineTo(x, y); cx.lineTo(r.x + r.w + 30, r.y + r.h + 30); cx.closePath(); cx.fill();
        cx.restore(); cssT(); cx.globalCompositeOperation = "lighten";
        const n = mobile() ? 5 : 7;
        for (let k = 0; k < n; k++) {
          const pts = wave(r.x, r.x + r.w, r.y + r.h * (0.24 + (k * 0.7) / n), r.h * 0.06, seed + k * 0.55, 1 + k * 0.04);
          grooveGroup(pts, Math.max(3, r.h * 0.018), gstep, groups);
        }
      } else if (s.kind === "disc") {
        // a disc of thin sand, rings drawn round it with a fingertip, the numeral poured into it
        const R = Math.min(r.w, r.h) / 2, x = r.x + r.w / 2, y = r.y + r.h / 2;
        cx.save(); blur(R * 0.08); cx.fillStyle = grey(0.42); cx.beginPath(); cx.arc(x, y, R, 0, Math.PI * 2); cx.fill(); cx.restore(); cssT(); cx.globalCompositeOperation = "lighten";
        for (const f of [0.93, 0.8]) {
          const pts: [number, number][] = [];
          for (let a = 0; a <= Math.PI * 2 + 0.01; a += 0.05) pts.push([x + Math.cos(a - 1.2) * R * f, y + Math.sin(a - 1.2) * R * f]);
          grooveGroup(pts, Math.max(3, R * 0.022), gstep, groups);
        }
      } else if (s.kind === "phone") {
        const ph = $<HTMLElement>(".ss-phone", el);
        if (ph) {
          const q = rel(ph, stage), rr = q.w * 0.15;
          const rrect = (x: number, y: number, w: number, h: number, rad: number) => { cx.beginPath(); (cx as any).roundRect ? (cx as any).roundRect(x, y, w, h, rad) : cx.rect(x, y, w, h); };
          cx.save(); blur(4); cx.fillStyle = grey(0.5); rrect(q.x - 6, q.y - 6, q.w + 12, q.h + 12, rr + 6); cx.fill();
          cx.globalCompositeOperation = "destination-out"; cx.fillStyle = "#000";
          const sc = $(".ss-phone__screen", ph); if (sc) { const z = rel(sc, stage); rrect(z.x, z.y, z.w, z.h, z.w * 0.1); cx.fill(); }
          cx.restore(); cssT(); cx.globalCompositeOperation = "lighten";
          // the outline poured thick around it
          groups.push({ step: gstep, g: { kind: "pour", region: { x: q.x - 20, y: q.y - 20, w: q.w + 40, h: q.h + 40 }, spill: 0.6,
            draw: () => { cx.strokeStyle = "#fff"; cx.lineWidth = Math.max(5, q.w * 0.04); rrect(q.x - 4, q.y - 4, q.w + 8, q.h + 8, rr + 4); cx.stroke(); },
            order: (gx, gy) => { const px = OX + (gx + 0.5) * C - (q.x + q.w / 2), py = OY + (gy + 0.5) * C - (q.y + q.h / 2); return ((Math.atan2(py, px) / (Math.PI * 2)) + 1.25) % 1; } } });
        }
      } else if (s.kind === "sil") {
        const m = $<HTMLImageElement>("img", el);
        if (m) { const [iw, ih] = dims(m); if (iw && ih) silLayer(m, iw, ih, r); }
      } else if (s.kind === "art" && art) artLayer(r);
      else if (s.kind === "iris") {
        // the table covered in thin sand, an oval swept clear for the words
        const fig = $(".sd-quote__fig", stage);
        cx.save(); cx.fillStyle = grey(0.55); cx.fillRect(0, 0, W, Hh);
        if (fig) {
          const q = rel(fig, stage);
          blur(34); cx.globalCompositeOperation = "destination-out"; cx.fillStyle = "#000";
          cx.beginPath(); cx.ellipse(q.x + q.w / 2, q.y + q.h / 2, q.w * 0.68 + 40, q.h * 0.82 + 46, 0, 0, Math.PI * 2); cx.fill();
          cx.globalCompositeOperation = "lighten"; blur(10);
          cx.strokeStyle = grey(1.15); cx.lineWidth = 16;
          cx.beginPath(); cx.ellipse(q.x + q.w / 2, q.y + q.h / 2, q.w * 0.68 + 52, q.h * 0.82 + 58, 0, 0, Math.PI * 2); cx.stroke();
        }
        cx.restore(); cssT(); cx.globalCompositeOperation = "lighten";
      } else if (s.kind === "column") {
        // a drift of thin sand, thicker at its heart, for the question mark to be cleared through
        cx.save();
        for (const [k, d, bl] of [[1.0, 0.32, 40], [0.72, 0.5, 24], [0.45, 0.7, 14]] as const) {
          blur(bl); cx.fillStyle = grey(d); cx.beginPath();
          for (let a = 0; a <= Math.PI * 2 + 0.01; a += 0.1) {
            const wob = 1 + 0.08 * Math.sin(a * 3 + seed) + 0.05 * Math.sin(a * 7 + seed * 2);
            const px = r.x + r.w / 2 + Math.cos(a) * r.w * 0.5 * k * wob, py = r.y + r.h / 2 + Math.sin(a) * r.h * 0.5 * k * wob;
            a ? cx.lineTo(px, py) : cx.moveTo(px, py);
          }
          cx.closePath(); cx.fill();
        }
        cx.restore(); cssT(); cx.globalCompositeOperation = "lighten";
      } else if (s.kind === "spiral") {
        // a disc of thin sand with a spiral drawn into it by one fingertip, from the middle out
        const R = Math.min(r.w, r.h) / 2, x = r.x + r.w / 2, y = r.y + r.h / 2;
        cx.save(); blur(R * 0.1); cx.fillStyle = grey(0.5); cx.beginPath(); cx.arc(x, y, R, 0, Math.PI * 2); cx.fill(); cx.restore(); cssT(); cx.globalCompositeOperation = "lighten";
        const pts: [number, number][] = [], turns = 4.2;
        for (let t = 0; t <= 1.0001; t += 0.003) { const a = t * turns * Math.PI * 2 + seed, rr = R * (0.06 + 0.8 * t); pts.push([x + Math.cos(a) * rr, y + Math.sin(a) * rr]); }
        grooveGroup(pts, Math.max(4, R * 0.04), gstep, groups);
      } else if (s.kind === "ring") {
        cx.save(); blur(10); cx.strokeStyle = grey(1.25); cx.lineWidth = Math.max(14, Math.min(r.w, r.h) * 0.16);
        cx.beginPath(); cx.ellipse(r.x + r.w / 2, r.y + r.h / 2, r.w * 0.46, r.h * 0.4, 0, 0, Math.PI * 2); cx.stroke();
        blur(26); cx.strokeStyle = grey(0.4); cx.lineWidth = Math.max(30, Math.min(r.w, r.h) * 0.36);
        cx.beginPath(); cx.ellipse(r.x + r.w / 2, r.y + r.h / 2, r.w * 0.56, r.h * 0.5, 0, 0, Math.PI * 2); cx.stroke();
        cx.restore(); cssT(); cx.globalCompositeOperation = "lighten";
      } else if (s.kind === "path") pathGroups(el, stage, groups);
    }
    // ink on clean glass; the top labels too
    cx.setTransform(1, 0, 0, 1, 0, 0); cssT();
    cx.globalCompositeOperation = "destination-out"; blur(10); cx.fillStyle = "#000";
    const b = stage.getBoundingClientRect();
    for (const ik of sec.inks) {
      if (!vis(ik)) continue;
      for (const q of ik.el.getClientRects()) cx.fillRect(q.left - b.left - 14, q.top - b.top - 10, q.width + 28, q.height + 20);
    }
    const top = $(".sd-top");
    if (top) { const q = top.getBoundingClientRect(); cx.fillRect(q.left - 16, q.top - 12, q.width + 32, q.height + 24); }
    cx.filter = "none";
    const base = readAll();
    const reveals: Reveal[] = [];
    const ops = buildOps(base, groups, sec.draw ? sec.n : 1, reveals);
    return { base, ops, reveals };
  }

  function readAll(): Float32Array {
    cx.setTransform(1, 0, 0, 1, 0, 0);
    const d = cx.getImageData(0, 0, cols, rows).data;
    const out = new Float32Array(N);
    for (let i = 0; i < N; i++) out[i] = (d[i * 4] * d[i * 4 + 3]) / 65025 * SCALE;
    return out;
  }

  function textGroups(el: HTMLElement, stage: HTMLElement, kind: "carve" | "pour", step: number, groups: { g: Group; step: number }[], amount: number, write: boolean) {
    const ws = wordsOf(el).filter((w) => w.getBoundingClientRect().width);
    const all = ws.map((w) => rel(w, stage));
    if (!all.length) return;
    const x0 = Math.min(...all.map((r) => r.x)), y0 = Math.min(...all.map((r) => r.y));
    const x1 = Math.max(...all.map((r) => r.x + r.w)), y1 = Math.max(...all.map((r) => r.y + r.h));
    const n = ws.length;
    const size = parseFloat(getComputedStyle(ws[0]).fontSize) || 40;
    groups.push({ step, g: { kind, region: { x: x0 - 12, y: y0 - 12, w: x1 - x0 + 24, h: y1 - y0 + 24 }, el: write ? el : undefined, spill: amount,
      // written headlines: the sand lies just along the strokes (a slight blur), poured numerals: solid
      draw: () => { cx.fillStyle = "#fff"; if (write) blur(size * 0.035); ws.forEach((w) => fillWord(w, stage)); cx.filter = "none"; },
      order: (gx, gy) => {
        const px = OX + (gx + 0.5) * C, py = OY + (gy + 0.5) * C;
        let k = 0, best = 1e9;
        for (let j = 0; j < n; j++) { const r = all[j]; const dx = Math.max(r.x - px, 0, px - r.x - r.w), dy = Math.max(r.y - py, 0, py - r.y - r.h); const d = dx + dy * 2; if (d < best) { best = d; k = j; } }
        const r = all[k];
        return (k + clamp((px - r.x) / Math.max(1, r.w))) / n;
      } } });
  }
  function grooveGroup(pts: [number, number][], width: number, step: number, groups: { g: Group; step: number }[]) {
    if (pts.length < 2) return;
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const lens = [0]; for (let k = 1; k < pts.length; k++) lens.push(lens[k - 1] + Math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]));
    const total = lens[lens.length - 1] || 1;
    groups.push({ step, g: { kind: "groove", region: { x: Math.min(...xs) - 10, y: Math.min(...ys) - 10, w: Math.max(...xs) - Math.min(...xs) + 20, h: Math.max(...ys) - Math.min(...ys) + 20 },
      draw: () => { cx.strokeStyle = "#fff"; cx.lineWidth = width; cx.lineCap = "round"; cx.lineJoin = "round"; cx.beginPath(); pts.forEach(([x, y], k) => k ? cx.lineTo(x, y) : cx.moveTo(x, y)); cx.stroke(); },
      order: (gx, gy) => {
        const px = OX + (gx + 0.5) * C, py = OY + (gy + 0.5) * C;
        let best = 1e9, at = 0;
        for (let k = 0; k < pts.length; k += 2) { const d = (pts[k][0] - px) ** 2 + (pts[k][1] - py) ** 2; if (d < best) { best = d; at = lens[k]; } }
        return at / total;
      } } });
  }
  function pathGroups(el: HTMLElement, stage: HTMLElement, groups: { g: Group; step: number }[]) {
    const stops = $$<HTMLElement>(".sd-stop", el).map((s) => { const r = rel(s, stage); return { x: r.x + r.w / 2, y: r.y + r.h / 2, r: r.w / 2 }; });
    if (!stops.length) return;
    const vertical = stops.length > 1 && Math.abs(stops[1].y - stops[0].y) > Math.abs(stops[1].x - stops[0].x);
    const start = vertical ? { x: stops[0].x, y: stops[0].y - stops[0].r * 3, r: 0 } : { x: Math.max(30, stops[0].x - stops[0].r * 4), y: stops[0].y, r: 0 };
    stops.forEach((s, k) => {
      const a = k ? stops[k - 1] : start;
      const pts: [number, number][] = [];
      const len = Math.hypot(s.x - a.x, s.y - a.y), nx = -(s.y - a.y) / (len || 1), ny = (s.x - a.x) / (len || 1);
      for (let t = 0; t <= 1.0001; t += 0.02) {
        const ox = a.x + (s.x - a.x) * t, oy = a.y + (s.y - a.y) * t;
        const w = Math.sin(t * Math.PI * 2 + k * 1.3) * Math.min(26, len * 0.08) * Math.sin(t * Math.PI);
        if (Math.hypot(ox - a.x, oy - a.y) < a.r * 1.4 || Math.hypot(ox - s.x, oy - s.y) < s.r * 1.4) continue;
        pts.push([ox + nx * w, oy + ny * w]);
      }
      const lw = Math.max(4, s.r * 0.2);
      groups.push({ step: k, g: { kind: "pour", spill: 0.9, region: { x: Math.min(a.x, s.x) - 60, y: Math.min(a.y, s.y) - 60, w: Math.abs(s.x - a.x) + 120, h: Math.abs(s.y - a.y) + 120 },
        draw: () => {
          cx.strokeStyle = "#fff"; cx.lineWidth = lw; cx.lineCap = "round"; cx.lineJoin = "round";
          if (pts.length > 1) { cx.beginPath(); pts.forEach(([px, py], j) => j ? cx.lineTo(px, py) : cx.moveTo(px, py)); cx.stroke(); }
          cx.lineWidth = lw * 1.35; cx.beginPath(); cx.arc(s.x, s.y, s.r, 0, Math.PI * 2); cx.stroke();
        },
        order: (gx, gy) => {
          const px = OX + (gx + 0.5) * C, py = OY + (gy + 0.5) * C;
          if (Math.hypot(px - s.x, py - s.y) < s.r * 1.6) return 0.75 + 0.25 * ((Math.atan2(py - s.y, px - s.x) / (Math.PI * 2) + 1.25) % 1);
          return 0.75 * clamp(((px - a.x) * (s.x - a.x) + (py - a.y) * (s.y - a.y)) / (len * len || 1));
        } } });
    });
  }

  function buildOps(base: Float32Array, groups: { g: Group; step: number }[], m: number, reveals: Reveal[]): Ops {
    const I: number[] = [], O: number[] = [], V: number[] = [];
    for (let st = 0; st < m; st++) {
      const rank = (q: { g: Group }) => (q.g.el ? 0 : q.g.kind === "pour" ? 1 : 2);
      const gs = groups.filter((q) => q.step === st).sort((a, b) => rank(a) - rank(b));
      gs.forEach((q, k) => {
        const g = q.g, lo = st + k / gs.length, span = 1 / gs.length;
        if (g.el) reveals.push({ el: g.el, lo, hi: lo + span, v: "" });
        reset(); cssT(); g.draw();
        const gx0 = clamp(Math.floor((g.region.x - OX) / C) - 3, 0, cols - 1), gy0 = clamp(Math.floor((g.region.y - OY) / C) - 3, 0, rows - 1);
        const gx1 = clamp(Math.ceil((g.region.x + g.region.w - OX) / C) + 3, 0, cols - 1), gy1 = clamp(Math.ceil((g.region.y + g.region.h - OY) / C) + 3, 0, rows - 1);
        const w = gx1 - gx0 + 1, h = gy1 - gy0 + 1;
        cx.setTransform(1, 0, 0, 1, 0, 0);
        const d = cx.getImageData(gx0, gy0, w, h).data;
        const mv = new Float32Array(w * h);
        for (let k2 = 0; k2 < w * h; k2++) mv[k2] = (d[k2 * 4] * d[k2 * 4 + 3]) / 65025;
        const lip = new Float32Array(w * h), lipOrd = new Float32Array(w * h).fill(-1);
        const amt = g.spill ?? 1;
        for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
          const v = mv[y * w + x];
          if (v < 0.06) continue;
          const gi = (gy0 + y) * cols + gx0 + x;
          const o = lo + span * g.order(gx0 + x, gy0 + y);
          const b0 = base[gi];
          let val: number;
          if (g.kind === "pour") val = Math.max(b0, v * amt);
          else val = b0 * (1 - 0.96 * v);   // carve and groove: cleared to the glass
          I.push(gi); O.push(o); V.push(val);
          if (g.kind === "pour" && amt < 1) continue;   // written headlines: no spill beyond their strokes
          for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) {
            const xx = x + dx, yy = y + dy;
            if (xx < 0 || yy < 0 || xx >= w || yy >= h || (dx === 0 && dy === 0)) continue;
            const j = yy * w + xx;
            if (mv[j] > 0.3) continue;
            const a = (g.kind === "pour" ? 0.18 : 0.22) * v * (Math.abs(dx) + Math.abs(dy) <= 2 ? 1 : 0.45);
            if (a > lip[j]) { lip[j] = a; lipOrd[j] = o; }
          }
        }
        for (let j = 0; j < w * h; j++) {
          if (lipOrd[j] < 0) continue;
          const gi = (gy0 + Math.floor(j / w)) * cols + gx0 + (j % w);
          const b0 = base[gi];
          if (g.kind !== "pour" && b0 < 0.12) continue;
          const spill = g.kind === "pour" ? lip[j] * (hash(gi) > 0.6 ? 1.5 : 0.25) : lip[j] * (0.6 + b0);
          I.push(gi); O.push(lipOrd[j]); V.push(Math.min(1.9, b0 + spill));
        }
      });
    }
    const perm = O.map((_, k) => k).sort((a, b) => O[a] - O[b]);
    return { idx: Int32Array.from(perm.map((k) => I[k])), ord: Float32Array.from(perm.map((k) => O[k])), val: Float32Array.from(perm.map((k) => V[k])) };
  }

  function silLayer(source: CanvasImageSource, sw: number, sh: number, r: Rect) {
    const gx = Math.floor((r.x - OX) / C), gy = Math.floor((r.y - OY) / C), gw = Math.max(1, Math.ceil(r.w / C)), gh = Math.max(1, Math.ceil(r.h / C));
    tmp.width = gw; tmp.height = gh;
    const s = Math.min(gw / sw, gh / sh), dw = sw * s, dh = sh * s;
    tx.fillStyle = "#fff"; tx.fillRect(0, 0, gw, gh);
    try { tx.drawImage(source, (gw - dw) / 2, (gh - dh) / 2, dw, dh); } catch { return; }
    let d: ImageData;
    try { d = tx.getImageData(0, 0, gw, gh); } catch { return; }
    const px = d.data;
    for (let k = 0; k < gw * gh; k++) {
      const lum = (px[k * 4] * 0.299 + px[k * 4 + 1] * 0.587 + px[k * 4 + 2] * 0.114) / 255;
      const g = Math.round(clamp(Math.pow(1 - lum, 1.2) * 1.2 / SCALE) * 255);
      px[k * 4] = px[k * 4 + 1] = px[k * 4 + 2] = g; px[k * 4 + 3] = 255;
    }
    tx.putImageData(d, 0, 0);
    cx.save(); cx.setTransform(1, 0, 0, 1, 0, 0); cx.globalCompositeOperation = "lighten"; cx.filter = `blur(${(1.5 / C).toFixed(2)}px)`; cx.drawImage(tmp, gx, gy); cx.restore();
  }
  /** theme.art as a sand silhouette: the subject in thick sand, wisps (steam, smoke) as thin, glowing sand. */
  function artLayer(r: Rect) {
    if (!art) return;
    const m = art.mask[0];
    const gx = Math.floor((r.x - OX) / C), gy = Math.floor((r.y - OY) / C), gw = Math.max(1, Math.ceil(r.w / C)), gh = Math.max(1, Math.ceil(r.h / C));
    tmp.width = gw; tmp.height = gh;
    const d = tx.createImageData(gw, gh), px = d.data;
    const s = Math.min(gw / art.w, gh / art.h), ox = (gw - art.w * s) / 2, oy = (gh - art.h * s) / 2;
    for (let y = 0; y < gh; y++) for (let x = 0; x < gw; x++) {
      const ax = Math.floor((x - ox) / s), ay = Math.floor((y - oy) / s);
      const mv = ax >= 0 && ay >= 0 && ax < art.w && ay < art.h ? m[ay * art.w + ax] : 0;
      const ex = (x + 0.5) / gw * 2 - 1, ey = (y + 0.5) / gh * 2 - 1;
      const v = Math.pow(sstep(0.06, 0.9, mv), 0.8) * 1.3 * (1 - sstep(0.55, 0.98, Math.sqrt(ex * ex + ey * ey)));
      const o = (y * gw + x) * 4, g = Math.round(clamp(v / SCALE) * 255);
      px[o] = px[o + 1] = px[o + 2] = g; px[o + 3] = 255;
    }
    tx.putImageData(d, 0, 0);
    cx.save(); cx.setTransform(1, 0, 0, 1, 0, 0); cx.globalCompositeOperation = "lighten"; cx.filter = `blur(${(2 / C).toFixed(2)}px)`; cx.drawImage(tmp, gx, gy); cx.restore();
  }
  /** A frame of thin poured sand around a section in default markup (or a scene with its own player). */
  function frameOnly(): Float32Array {
    const out = new Float32Array(N), m = Math.round(Math.min(cols, rows) * 0.05) + 3;
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
      const e = Math.min(x, y, cols - 1 - x, rows - 1 - y);
      out[y * cols + x] = e < m ? 0.8 * Math.pow(1 - e / m, 1.5) : 0;
    }
    return out;
  }

  // ---------------------------------------------------------------- the schedule
  const emptyOps: Ops = { idx: new Int32Array(0), ord: new Float32Array(0), val: new Float32Array(0) };
  function schedule() {
    L = Hh * (mobile() ? 0.85 : 0.92);
    secs.forEach((s, i) => {
      if (s.kind !== "plate") return;
      const last = secs.slice(i + 1).every((q) => q.kind !== "plate");
      s.el.style.setProperty("--sd-h", `${Math.round(last ? Math.max(s.n * L, Hh) : s.n * L)}px`);
    });
    secs.forEach((s) => { const r = s.el.getBoundingClientRect(); s.top = r.top + scrollY; if (s.kind === "flow") s.h = r.height; });
    const out: Scene[] = [];
    for (const s of secs) {
      if (s.kind === "plate") {
        if (s.draw) {
          const anchors = Array.from({ length: s.n }, (_, j) => s.top + j * L);
          const c = compose(s, 0);
          out.push({ sec: s, step: 0, m: s.n, anchors, s0: anchors[0] - 0.35 * L, s1: anchors[s.n - 1] + 0.12 * L, base: c.base, ops: c.ops, fin: null, p: 0, reveals: c.reveals });
        } else for (let j = 0; j < s.n; j++) {
          const a = s.top + j * L;
          const c = compose(s, j);
          out.push({ sec: s, step: j, m: 1, anchors: [a], s0: a - 0.35 * L, s1: a + 0.12 * L, base: c.base, ops: c.ops, fin: null, p: 0, reveals: c.reveals });
        }
      } else {
        const s0 = s.top - 0.45 * Hh;
        out.push({ sec: s, step: 0, m: 0, anchors: [s.top], s0, s1: Math.max(s0, s.top + s.h - 0.55 * Hh), base: frameOnly(), ops: emptyOps, fin: null, p: 0, reveals: [] });
      }
    }
    for (let k = 1; k < out.length; k++) if (out[k].s0 < out[k - 1].s1 + 20) { const mid = (out[k].s0 + out[k - 1].s1) / 2; out[k].s0 = mid + 10; out[k - 1].s1 = mid - 10; }
    if (out.length) out[0].s0 = Math.min(out[0].s0, -1);
    scenes = out;
  }
  function progressAt(sc: Scene, y: number): number {
    if (!sc.m) return 0;
    for (let j = 0; j < sc.m; j++) {
      const st = j === 0 ? sc.s0 : sc.anchors[j - 1] + 0.12 * L;
      if (y < st) return j;
      const end = sc.anchors[j] - 0.06 * L;
      if (y <= sc.anchors[j]) return j + sstep(0, 1, (y - st) / Math.max(1, end - st));
    }
    return sc.m;
  }
  function locate(y: number): Pos {
    for (let i = 0; i < scenes.length; i++) {
      const sc = scenes[i];
      if (y <= sc.s1) return y < sc.s0 && i > 0 ? { sweep: true, i: i - 1, v: (y - scenes[i - 1].s1) / Math.max(1, sc.s0 - scenes[i - 1].s1) } : { sweep: false, i, v: progressAt(sc, y) };
    }
    const l = scenes.length - 1;
    return { sweep: false, i: l, v: scenes[l].m };
  }

  // ---------------------------------------------------------------- the hand
  const PIVOTS: [number, number, boolean][] = [[-0.45, 1.35, false], [1.45, -0.3, true], [1.4, 1.4, true], [-0.4, -0.35, false]];
  function geo(i: number): Geo {
    let g = geos.get(i);
    if (g) return g;
    const [fx, fy, flip] = PIVOTS[i % PIVOTS.length];
    const px = fx * W, py = fy * Hh;
    const corners = [[0, 0], [W, 0], [0, Hh], [W, Hh]].map(([x, y]) => Math.atan2(y - py, x - px));
    const mid = Math.atan2(Hh / 2 - py, W / 2 - px);
    const relA = corners.map((a) => { let d = a - mid; while (d > Math.PI) d -= Math.PI * 2; while (d < -Math.PI) d += Math.PI * 2; return d; });
    let a0 = mid + Math.min(...relA) - 0.08, a1 = mid + Math.max(...relA) + 0.08;
    if (flip) [a0, a1] = [a1, a0];
    const span = a1 - a0;
    const U = new Float32Array(N), R = new Float32Array(N);
    let rmin = 1e9, rmax = 0;
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
      const i2 = y * cols + x, X = OX + (x + 0.5) * C - px, Y = OY + (y + 0.5) * C - py;
      let d = Math.atan2(Y, X) - a0;
      while (d > Math.PI) d -= Math.PI * 2; while (d < -Math.PI) d += Math.PI * 2;
      const r = Math.hypot(X, Y);
      U[i2] = d / span + (Math.sin(r / 41 + i) * 0.006 + Math.sin(r / 13.7) * 0.003 + (hash(i2) - 0.5) * 0.006) * Math.sign(span);
      R[i2] = r; if (r < rmin) rmin = r; if (r > rmax) rmax = r;
    }
    g = { px, py, a0, span, U, R, rmin, rmax };
    geos.set(i, g);
    if (geos.size > 4) geos.delete(geos.keys().next().value!);
    return g;
  }
  const BINS = 96;
  const load = new Float32Array(BINS);
  let ridgeDir = 1, frameDt = 1 / 60;

  function finalOf(sc: Scene): Float32Array {
    if (sc.fin) return sc.fin;
    const f = sc.base.slice();
    for (let k = 0; k < sc.ops.idx.length; k++) f[sc.ops.idx[k]] = sc.ops.val[k];
    return (sc.fin = f);
  }
  function setProgress(sc: Scene, p: number) {
    const { idx, ord, val } = sc.ops;
    if (p > sc.p) { for (let k = lowerBound(ord, sc.p); k < ord.length && ord[k] < p; k++) F[idx[k]] = val[k]; }
    else if (p < sc.p) { for (let k = lowerBound(ord, p); k < ord.length && ord[k] < sc.p; k++) F[idx[k]] = sc.base[idx[k]]; }
    if (p !== sc.p) dirty = true;
    sc.p = p;
  }
  function lowerBound(a: Float32Array, v: number) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] < v) lo = m + 1; else hi = m; } return lo; }

  function spawn(x: number, y: number, vx: number, vy: number) {
    if (np >= PMAX) return;
    const k = np++;
    pX[k] = x; pY[k] = y; pVX[k] = vx; pVY[k] = vy;
    pL[k] = pL0[k] = 0.25 + Math.random() * 0.75; pS[k] = 1.4 + Math.random() * 2.2; pC[k] = Math.random() < 0.3 ? 1 : Math.random() * 0.35;
  }
  /** The side of the hand moves from sweep progress a to b over transition i (scene i -> i + 1). */
  function sweep(i: number, a: number, b: number) {
    if (a === b) return;
    const g = geo(i);
    const fwd = b > a;
    ridgeDir = fwd ? 1 : -1;
    const T = fwd ? scenes[i + 1].base : finalOf(scenes[i]);
    const lo = Math.min(a, b), hi = Math.max(a, b);
    const { U, R } = g, rr = g.rmax - g.rmin || 1;
    const big = hi - lo > 0.25;   // a jump (an anchor link, a fresh load): no grains in the air
    const speed = ((hi - lo) * Math.abs(g.span)) / Math.max(1 / 120, frameDt);   // radians per second
    const sgn = Math.sign(g.span) * ridgeDir;
    for (let k = 0; k < N; k++) {
      const u = U[k];
      if (u <= lo || u > hi) continue;
      const bin = Math.min(BINS - 1, Math.floor(((R[k] - g.rmin) / rr) * BINS));
      const t = T[k], ex = F[k] - t;
      if (ex > 0) {
        load[bin] += ex;
        // some of what the hand gathers is thrown ahead: grains rolling and streaming off the front
        if (!big && !reduced && Math.random() < Math.min(0.9, ex * 0.55)) {
          const x = OX + ((k % cols) + 0.5) * C, y = OY + (Math.floor(k / cols) + 0.5) * C;
          const ang = Math.atan2(y - g.py, x - g.px), v = speed * R[k];
          const tx2 = -Math.sin(ang) * sgn, ty2 = Math.cos(ang) * sgn;
          const f = 0.9 + Math.random() * 1.1, side = (Math.random() - 0.5) * 0.7;
          spawn(x, y, (tx2 * f + Math.cos(ang) * side) * v, (ty2 * f + Math.sin(ang) * side) * v);
        }
      } else { const pay = Math.min(load[bin], -ex * 0.5); load[bin] -= pay; }
      F[k] = t;   // the hand leaves the next scene clean
    }
    for (let k = 1; k < BINS - 1; k++) load[k] = load[k] * 0.9 + (load[k - 1] + load[k + 1]) * 0.05;
    dirty = true;
  }
  /** The pile of gathered sand just ahead of the hand (redrawn every frame). */
  function drawRidge(i: number, s: number) {
    for (const k of touched) RG[k] = 0;
    touched = [];
    if (s <= 0 || s >= 1 || reduced) return;
    const g = geo(i), { U, R } = g, rr = g.rmax - g.rmin || 1, spanPx = Math.abs(g.span);
    const reach = 90 / (spanPx * Math.max(1, g.rmin));
    for (let k = 0; k < N; k++) {
      const du = (U[k] - s) * ridgeDir;
      if (du < -0.002 || du > reach) continue;
      const dpx = du * spanPx * R[k];
      const bin = Math.min(BINS - 1, Math.floor(((R[k] - g.rmin) / rr) * BINS));
      const l = load[bin], th = Math.min(80, 30 + 3.4 * Math.sqrt(l));
      if (dpx > th) continue;
      // a mound: steep against the hand, a long granular slope in front of it
      const q = Math.max(0, dpx) / th;
      const prof = Math.pow(1 - q, 1.6) * Math.min(1, (dpx + 3) / 6);
      const v = Math.min(1.9, 0.42 + 0.19 * Math.sqrt(l)) * prof * (0.65 + 0.7 * hash(k));
      RG[k] = v; touched.push(k);
    }
    dirty = true;
  }
  function stepGrains(dt: number) {
    if (!np) return;
    let w = 0;
    const fr = Math.exp(-dt * 6);
    for (let k = 0; k < np; k++) {
      pVX[k] *= fr; pVY[k] *= fr;
      pX[k] += pVX[k] * dt; pY[k] += pVY[k] * dt;
      pL[k] -= dt;
      const slow = pVX[k] * pVX[k] + pVY[k] * pVY[k] < 400;
      if (pL[k] <= 0 || slow) {
        // it settles: a grain of sand on the glass
        const gx = Math.floor((pX[k] - OX) / C), gy = Math.floor((pY[k] - OY) / C);
        if (gx >= 0 && gy >= 0 && gx < cols && gy < rows) F[gy * cols + gx] = Math.min(1.9, F[gy * cols + gx] + 0.12);
        continue;
      }
      if (w !== k) { pX[w] = pX[k]; pY[w] = pY[k]; pVX[w] = pVX[k]; pVY[w] = pVY[k]; pL[w] = pL[k]; pL0[w] = pL0[k]; pS[w] = pS[k]; pC[w] = pC[k]; }
      w++;
    }
    np = w;
    for (let k = 0; k < np; k++) { const o = k * 5; pbuf[o] = pX[k]; pbuf[o + 1] = pY[k]; pbuf[o + 2] = pS[k]; pbuf[o + 3] = 0.85 * Math.min(1, pL[k] / (pL0[k] * 0.3)); pbuf[o + 4] = pC[k]; }
    dirty = true;
  }

  // ---------------------------------------------------------------- moving through the timeline
  let cur: Pos = { sweep: false, i: 0, v: 0 };
  function nominal(pos: Pos) {
    if (pos.sweep) {
      const g = geo(pos.i), A = finalOf(scenes[pos.i]), B = scenes[pos.i + 1].base;
      for (let k = 0; k < N; k++) F[k] = g.U[k] <= pos.v ? B[k] : A[k];
      scenes.forEach((s) => (s.p = 0));
      scenes[pos.i].p = scenes[pos.i].m;
    } else {
      F.set(scenes[pos.i].base);
      scenes.forEach((s) => (s.p = 0));
      setProgress(scenes[pos.i], pos.v);
    }
    load.fill(0); np = 0;
    cur = { ...pos };
    dirty = true;
  }
  function seek(to: Pos) {
    for (let guard = 0; guard < 400; guard++) {
      if (cur.sweep) {
        if (to.sweep && to.i === cur.i) { sweep(cur.i, cur.v, to.v); cur.v = to.v; return; }
        if (to.i > cur.i) { sweep(cur.i, cur.v, 1); cur = { sweep: false, i: cur.i + 1, v: 0 }; scenes[cur.i].p = 0; continue; }
        sweep(cur.i, cur.v, 0); cur = { sweep: false, i: cur.i, v: scenes[cur.i].m }; scenes[cur.i].p = scenes[cur.i].m; continue;
      }
      const sc = scenes[cur.i];
      if (!to.sweep && to.i === cur.i) { setProgress(sc, to.v); cur.v = to.v; return; }
      if (to.i >= cur.i) { setProgress(sc, sc.m); load.fill(0); cur = { sweep: true, i: cur.i, v: 0 }; continue; }
      setProgress(sc, 0);
      if (cur.i === 0) return;
      load.fill(0); cur = { sweep: true, i: cur.i - 1, v: 1 };
    }
  }

  // ---------------------------------------------------------------- the fingertip
  function furrow(x0: number, y0: number, x1: number, y1: number, strength: number, Rpx: number) {
    const R = Rpx, R2 = R * 1.9;
    const gx0 = Math.max(0, Math.floor((Math.min(x0, x1) - R2 - OX) / C)), gx1 = Math.min(cols - 1, Math.ceil((Math.max(x0, x1) + R2 - OX) / C));
    const gy0 = Math.max(0, Math.floor((Math.min(y0, y1) - R2 - OY) / C)), gy1 = Math.min(rows - 1, Math.ceil((Math.max(y0, y1) + R2 - OY) / C));
    const dx = x1 - x0, dy = y1 - y0, ll = dx * dx + dy * dy || 1;
    let total = 0, wsum = 0;
    const ring: number[] = [], rw: number[] = [];
    for (let gy = gy0; gy <= gy1; gy++) for (let gx = gx0; gx <= gx1; gx++) {
      const px = OX + (gx + 0.5) * C, py = OY + (gy + 0.5) * C;
      const t = clamp(((px - x0) * dx + (py - y0) * dy) / ll);
      const d = Math.hypot(px - (x0 + dx * t), py - (y0 + dy * t));
      const i = gy * cols + gx;
      if (d < R) { const rem = F[i] * strength * (1 - (d / R) * (d / R)); F[i] -= rem; total += rem; }
      else if (d < R2) { const w = 1 - Math.abs(d - R * 1.4) / (R * 0.5); if (w > 0) { ring.push(i); rw.push(w); wsum += w; } }
    }
    if (wsum > 0) for (let k = 0; k < ring.length; k++) F[ring[k]] = Math.min(1.9, F[ring[k]] + (total * rw[k]) / wsum);
    dirty = true;
  }
  const busy = (el: EventTarget | null) => !!(el as HTMLElement)?.closest?.("a, button, summary, input, textarea, select, .sd-top, .ss-looks");
  let last: { x: number; y: number } | null = null, down = false;
  addEventListener("pointermove", (e) => {
    if (e.pointerType === "touch") return;
    const p = { x: e.clientX, y: e.clientY };
    if (last && !busy(e.target)) furrow(last.x, last.y, p.x, p.y, down ? 0.92 : 0.18, down ? Math.max(7, C * 3.2) : Math.max(4, C * 1.8));
    last = p;
  }, { passive: true });
  addEventListener("pointerdown", (e) => {
    if (e.pointerType === "touch" || e.button !== 0 || busy(e.target)) return;
    if (!(e.target as HTMLElement)?.closest?.(".sd-ink, .sd-head")) e.preventDefault();
    down = true; furrow(e.clientX, e.clientY, e.clientX + 0.5, e.clientY, 0.92, Math.max(7, C * 3.2));
  });
  addEventListener("pointerup", () => { down = false; }, { passive: true });
  addEventListener("pointerleave", () => { last = null; }, { passive: true });
  let tp: { x: number; y: number } | null = null;
  addEventListener("touchstart", (e) => { const t = e.touches[0]; tp = t && !busy(e.target) ? { x: t.clientX, y: t.clientY } : null; }, { passive: true });
  addEventListener("touchmove", (e) => { const t = e.touches[0]; if (!t || !tp) return; furrow(tp.x, tp.y, t.clientX, t.clientY, 0.85, Math.max(8, C * 3.6)); tp = { x: t.clientX, y: t.clientY }; }, { passive: true });
  addEventListener("touchend", () => { tp = null; }, { passive: true });
  document.addEventListener("focusin", (e) => {
    const el = e.target as HTMLElement;
    const sc = scenes.find((s) => s.sec.kind === "plate" && s.sec.stage.contains(el) && (s.sec.draw || (stepsOf(el, s.sec.stage)?.includes(s.step) ?? true)));
    if (sc && (scrollY < sc.s0 || scrollY > sc.s1)) scrollTo({ top: sc.anchors[0], behavior: "auto" });
  });

  // ---------------------------------------------------------------- the copy, uncovered behind the pile
  const HIDE = "hide";
  /** A soft conic mask: the sector the hand has swept (in) or the rest (out), offset so the seam lies under the pile. */
  function maskFor(el: HTMLElement, i: number, s: number, side: "in" | "out", fixed: boolean) {
    const g = geo(i);
    let ox = 0, oy = 0;
    if (!fixed) { const b = el.getBoundingClientRect(); ox = b.left; oy = b.top; }
    // offsets from the hand line, along the sweep: the new copy starts just behind the pile, the old ends at its front
    const r = Math.max(240, Math.hypot(W / 2 - g.px, Hh / 2 - g.py));
    const small = 4 / r, pile = 50 / r;
    const off = side === "in" ? (ridgeDir > 0 ? -small : -pile) : (ridgeDir > 0 ? pile : small);
    const e = Math.max(0, s * Math.abs(g.span) + off);
    const start = (g.span > 0 ? g.a0 : g.a0 - e) * R2D + 90;
    const ed = e * R2D, f = 1.4;
    const at = `at ${(g.px - ox).toFixed(1)}px ${(g.py - oy).toFixed(1)}px`;
    if (side === "in") return g.span > 0
      ? `conic-gradient(from ${start.toFixed(2)}deg ${at}, #000 0deg, #000 ${Math.max(0, ed - f).toFixed(2)}deg, transparent ${ed.toFixed(2)}deg)`
      : `conic-gradient(from ${start.toFixed(2)}deg ${at}, transparent 0deg, #000 ${Math.min(ed, f).toFixed(2)}deg, #000 ${ed.toFixed(2)}deg, transparent ${ed.toFixed(2)}deg)`;
    return g.span > 0
      ? `conic-gradient(from ${start.toFixed(2)}deg ${at}, transparent 0deg, transparent ${ed.toFixed(2)}deg, #000 ${(ed + f).toFixed(2)}deg)`
      : `conic-gradient(from ${start.toFixed(2)}deg ${at}, transparent 0deg, transparent ${ed.toFixed(2)}deg, #000 ${ed.toFixed(2)}deg, #000 ${(360 - f).toFixed(2)}deg, transparent 360deg)`;
  }
  function setV(o: { el: HTMLElement; v: string }, v: string) {
    if (o.v === v) return;
    o.v = v;
    const st = o.el.style;
    if (v === HIDE) { st.clipPath = "inset(0 0 100% 0)"; st.webkitMaskImage = st.maskImage = ""; }
    else if (v === "none") { st.clipPath = "none"; st.webkitMaskImage = st.maskImage = ""; }
    else if (v.startsWith("inset")) { st.clipPath = v; st.webkitMaskImage = st.maskImage = ""; }
    else { st.clipPath = "none"; st.webkitMaskImage = st.maskImage = v; }
  }

  function dom(pos: Pos) {
    const A = scenes[pos.i], B = pos.sweep ? scenes[pos.i + 1] : null;
    const s = pos.v;
    for (const sec of secs) {
      if (sec.kind !== "plate") continue;
      const inA = A.sec === sec, inB = !!B && B.sec === sec;
      let on = inA || inB;
      if (!on) setV(sec.sv, HIDE);
      else if (B && !reduced && inA !== inB) setV(sec.sv, maskFor(sec.stage, pos.i, s, inB ? "in" : "out", true));
      else if (B && reduced) { on = s < 0.5 ? inA : inB; setV(sec.sv, on ? "none" : HIDE); }
      else setV(sec.sv, "none");
      sec.stage.classList.toggle("is-on", on);
      if (!on) continue;
      for (const wr of sec.wraps) {
        let v = HIDE;
        if (sec.draw) {
          const k = clamp(((inA ? A : B!).p - wr.steps[0]) * 1.5);
          v = k >= 1 ? "none" : k <= 0 ? HIDE : `inset(-30px ${((1 - k) * 100).toFixed(1)}% -30px -30px)`;
        } else {
          const ina = inA && wr.steps.includes(A.step), inb = !!B && inB && wr.steps.includes(B.step);
          if (ina && inb) v = "none";
          else if (B && !reduced && inA && inB) v = ina ? maskFor(wr.el, pos.i, s, "out", false) : inb ? maskFor(wr.el, pos.i, s, "in", false) : HIDE;
          else if (B && reduced) v = (s < 0.5 ? ina : inb) ? "none" : HIDE;
          else v = (ina || inb) ? "none" : HIDE;
        }
        setV(wr, v);
      }
    }
    // headlines are written on as the fingers go (left to right, in step with their sand)
    for (const sc of [A, B]) {
      if (!sc) continue;
      for (const rv of sc.reveals) {
        const k = sc === B ? 0 : clamp((sc.p - rv.lo) / Math.max(1e-3, rv.hi - rv.lo) * 1.15);
        const v = k >= 1 ? "none" : k <= 0 ? "inset(-20% 100% -20% -20px)" : `inset(-20% ${((1 - k) * 100).toFixed(1)}% -20% -20px)`;
        if (rv.v !== v) { rv.v = v; rv.el.style.clipPath = v; }
      }
    }
    const cnt = $("[data-sd-scene]");
    const curSec = (B && s > 0.5 ? B : A).sec;
    if (cnt && cnt.textContent !== String(curSec.idx + 1)) cnt.textContent = String(curSec.idx + 1);
  }

  // ---------------------------------------------------------------- per frame
  let dirty = true, ready = false, introP = 1, introT0 = 0;
  function frame(dt: number) {
    if (!ready) return;
    frameDt = dt;
    let to = locate(scrollY);
    if (reduced && to.sweep) to = to.v < 0.5 ? { sweep: false, i: to.i, v: scenes[to.i].m } : { sweep: false, i: to.i + 1, v: 0 };
    if (reduced && !to.sweep) to = { sweep: false, i: to.i, v: scenes[to.i].m };
    if (introP < 1) {
      introP = clamp((performance.now() - introT0) / 1800);
      if (!to.sweep && to.i === 0) to = { sweep: false, i: 0, v: Math.min(to.v, sstep(0, 1, introP) * scenes[0].m) };
      else introP = 1;
    }
    if (reduced && (to.sweep !== cur.sweep || to.i !== cur.i)) nominal(to); else seek(to);
    if (cur.sweep) drawRidge(cur.i, cur.v); else if (touched.length) drawRidge(0, 0);
    stepGrains(dt);
    dom(cur);
    if (dirty && !document.hidden) {
      for (let k = 0; k < N; k++) { const v = (F[k] + RG[k]) * 110; U8[k] = v > 255 ? 255 : v; }
      table!.draw(U8, pbuf, np);
      dirty = false;
    }
  }

  let resizeT = 0;
  function rebuild() { geometry(); schedule(); nominal(locate(scrollY)); }
  addEventListener("resize", () => {
    clearTimeout(resizeT);
    resizeT = window.setTimeout(() => { if (Math.abs(innerWidth - W) > 2 || Math.abs(innerHeight - Hh) > 120) rebuild(); }, 180);
  });
  const go = () => {
    if (ready) return;
    rebuild();
    const at = locate(scrollY);
    if (!reduced && !at.sweep && at.i === 0 && scenes[0].m) { introP = 0; introT0 = performance.now(); setProgress(scenes[0], 0); cur.v = 0; }
    ready = true;
  };
  Promise.all([
    document.fonts.load('700 100px "Caveat"').catch(() => null),
    document.fonts.load('italic 900 100px "Alegreya"').catch(() => null),
    document.fonts.ready,
    loadArt().then((a) => { art = a; }),
    ...$$<HTMLImageElement>(".sd-pic img").map((im) => im.complete ? null : new Promise((r) => { im.onload = im.onerror = r; })),
  ]).then(go);
  setTimeout(go, 2500);
  onFrame(({ dt }) => frame(dt || 1 / 60));
}
