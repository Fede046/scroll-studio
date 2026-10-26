/**
 * Pinscreen: Alexeieff and Parker's board of pins. One fixed WebGL board draws every pin and the shadow it casts under
 * a raking lamp, from a texture of pin depths (and how hard each pin is moving, so moving pins catch the light).
 * Every section is a plate (or a run of plates), and every plate is a full tonal picture composed at pin resolution
 * from its own stage: a lamp pool with smoky grain falling off to deep black, sculpted relief (numerals, words, the
 * phone, the CTA slab) modelled by the lamp from a distance-field height, theme.art and images in tone, with the pins
 * behind the copy standing fully out so crisp ivory HTML text always sits on black, and a soft lit relief of each
 * headline's words behind it. Between plates a wave rolls through the board from the next picture's subject: a tall
 * wall of pins with ripples trailing behind it, the old picture ahead of it and the new one behind, the lamp lowering
 * so the moving pins throw long shadows; the copy is revealed by the same circle. The mouse moves the lamp; pressing
 * draws lines the board slowly pushes back; touch leaves a trail. Film and image-sequence scenes play on the board.
 * Reduced motion: still plates swapped in one step. Research: docs/styles/styles-22-23.md, section 22.
 */
import { $, $$, onFrame, reduced } from "./_kit";
import { loadArt, type ArtFrames } from "./_art";
import { clamp } from "../lib/util";

const DEG = Math.PI / 180;
const sstep = (a: number, b: number, v: number) => { const t = clamp((v - a) / (b - a)); return t * t * (3 - 2 * t); };
const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const mobile = () => innerWidth < 760;
const hash = (i: number) => { let x = Math.imul(i ^ 0x9e3779b9, 0x85ebca6b); x ^= x >>> 13; x = Math.imul(x, 0xc2b2ae35); x ^= x >>> 16; return (x >>> 0) / 4294967296; };

type Src = { el: HTMLElement; kind: string; steps: number[] | null; on: number };
type Plate = {
  kind: "plate"; el: HTMLElement; stage: HTMLElement; type: string; n: number; idx: number;
  srcs: Src[]; calms: { el: HTMLElement; steps: number[] | null }[]; wraps: { el: HTMLElement; steps: number[]; clip: string }[];
  ons: HTMLElement[]; top: number; clip: string; low: boolean; sundial: boolean;
};
type Flow = { kind: "flow"; el: HTMLElement; idx: number; scene: boolean; vis: HTMLElement | null; top: number; h: number; sampled: boolean };
type Sec = Plate | Flow;
type State = {
  sec: Sec; step: number; h0: number; h1: number; anchor: number; ang: number; len: number; ox: number; oy: number;
  pic: Float32Array; dyn: ((out: Float32Array) => boolean) | null;
  slab: { m: Float32Array; h: Float32Array } | null;
};
type Rect = { x: number; y: number; w: number; h: number };

function stepsOf(el: HTMLElement, stage: HTMLElement): number[] | null {
  const s = el.closest<HTMLElement>("[data-step]");
  if (!s || !stage.contains(s)) return null;
  return (s.dataset.step || "").trim().split(/\s+/).filter(Boolean).map(Number);
}
function dims(m: any): [number, number] { return [m.naturalWidth || m.videoWidth || m.width || 0, m.naturalHeight || m.videoHeight || m.height || 0]; }

// ------------------------------------------------------------------------------------------------ the board (WebGL)
const VS = `attribute vec2 p; void main(){ gl_Position = vec4(p, 0., 1.); }`;
const FS = `precision highp float;
uniform sampler2D uH; uniform vec2 uGrid; uniform float uPitch; uniform vec2 uRes; uniform vec2 uOff;
uniform vec2 uDir; uniform float uLen; uniform vec3 uBoard;
vec2 HA(vec2 c){ if (c.x < 0. || c.y < 0. || c.x >= uGrid.x || c.y >= uGrid.y) return vec2(0.); return texture2D(uH, (c + .5) / uGrid).ra; }
void main(){
  vec2 px = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y);
  vec2 u = (px - uOff) / uPitch;
  vec2 ci = floor(u);
  vec2 perp = vec2(-uDir.y, uDir.x);
  float shade = 0., ao = 0.;
  for (int m = 0; m < 5; m++) {
    for (int l = -1; l <= 1; l++) {
      vec2 q = floor(ci + .5 - uDir * float(m) + perp * float(l) + .0001);
      float h = HA(q).x;
      ao += h;
      if (h < .015) continue;
      vec2 a = q + .5;
      float L = uLen * h;
      float along = dot(u - a, uDir);
      float t = clamp(along / L, 0., 1.);
      float d = length(u - (a + uDir * L * t));
      float w = .2 + .26 * h + .1 * t;
      float soft = .07 + .22 * t;
      float s = (1. - smoothstep(w - soft, w + soft, d)) * smoothstep(-.25, .05, along);
      s *= mix(1., .5, t * t);
      shade = max(shade, s);
    }
  }
  ao /= 15.;
  vec2 sc = px / uRes - .5;
  float lamp = 1.06 - .14 * dot(sc * 2., uDir) - .5 * dot(sc, sc);
  vec3 col = uBoard * lamp * (1. - .88 * shade) * (1. - .32 * ao * ao);
  // the pin in this cell: a dark steel head that catches the lamp on its near side; a moving pin flashes brighter
  vec2 me = HA(ci);
  float h0 = me.x, mv = me.y;
  vec2 f = u - ci - .5;
  float r = length(f);
  float rh = .17 + .06 * h0;
  float head = 1. - smoothstep(rh - .06, rh + .05, r);
  float glint = smoothstep(.1, .95, dot(f / max(r, 1e-3), -uDir)) * smoothstep(rh * .15, rh, r) * (h0 * .8 + mv * 1.6);
  vec3 pin = mix(vec3(.13, .135, .15), vec3(1., .97, .9), clamp(glint, 0., 1.));
  col = mix(col, pin, head * mix(.18, 1., smoothstep(.0, .3, h0)));
  col += vec3(1., .95, .86) * mv * mv * (head * .7 + .12);
  gl_FragColor = vec4(col, 1.);
}`;

function makeBoard(canvas: HTMLCanvasElement) {
  const gl = (canvas.getContext("webgl", { antialias: false, alpha: false }) || canvas.getContext("experimental-webgl")) as WebGLRenderingContext | null;
  if (!gl) return null;
  const sh = (type: number, src: string) => { const s = gl.createShader(type)!; gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || "shader"); return s; };
  const prog = gl.createProgram()!;
  try { gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS)); } catch { return null; }
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;
  gl.useProgram(prog);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "p");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.NEAREST], [gl.TEXTURE_MAG_FILTER, gl.NEAREST], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
  const U = (n: string) => gl.getUniformLocation(prog, n);
  const u = { H: U("uH"), grid: U("uGrid"), pitch: U("uPitch"), res: U("uRes"), off: U("uOff"), dir: U("uDir"), len: U("uLen"), board: U("uBoard") };
  gl.uniform1i(u.H, 0);
  gl.uniform3f(u.board, 0.935, 0.905, 0.85);
  let cols = 0, rows = 0;
  return {
    size(w: number, h: number, dpr: number, c: number, r: number, pitch: number, ox: number, oy: number) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(u.res, canvas.width, canvas.height);
      gl.uniform1f(u.pitch, pitch * dpr);
      gl.uniform2f(u.off, ox * dpr, oy * dpr);
      gl.uniform2f(u.grid, c, r);
      cols = c; rows = r;
    },
    draw(data: Uint8Array, ang: number, len: number) {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.LUMINANCE_ALPHA, cols, rows, 0, gl.LUMINANCE_ALPHA, gl.UNSIGNED_BYTE, data);
      gl.uniform2f(u.dir, Math.cos(ang), Math.sin(ang));
      gl.uniform1f(u.len, len);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    },
  };
}

// ------------------------------------------------------------------------------------------------ the experience
export default function start() {
  const canvas = $<HTMLCanvasElement>(".pn-canvas");
  if (!canvas) return;
  const board = makeBoard(canvas);
  if (!board) return;   // no WebGL: the printed plates (static CSS) stay
  const root = document.documentElement;

  const secs: Sec[] = [];
  $$<HTMLElement>("main section").filter((s) => !s.parentElement?.closest("section")).forEach((el, idx) => {
    if (el.classList.contains("pn-plate")) {
      const stage = $<HTMLElement>(".pn-stage", el)!;
      secs.push({
        kind: "plate", el, stage, type: el.dataset.pn || "", n: Math.max(1, +(el.dataset.steps || 1)), idx,
        srcs: $$<HTMLElement>("[data-pin]", stage).map((s) => ({ el: s, kind: s.dataset.pin || "", steps: stepsOf(s, stage), on: s.dataset.on ? +s.dataset.on : -1 })),
        calms: $$<HTMLElement>(".pn-calm", stage).map((s) => ({ el: s, steps: stepsOf(s, stage) })),
        wraps: $$<HTMLElement>(".pn-step-wrap", stage).map((s) => ({ el: s, steps: (s.dataset.step || "").trim().split(/\s+/).filter(Boolean).map(Number), clip: "" })),
        ons: $$<HTMLElement>("[data-on]:not([data-pin])", stage),
        top: 0, clip: "", low: el.dataset.lamp === "low", sundial: el.hasAttribute("data-sundial"),
      });
    } else secs.push({ kind: "flow", el, idx, scene: el.classList.contains("ss-scene"), vis: $<HTMLElement>(".ss-visual", el), top: 0, h: 0, sampled: false });
  });
  if (!secs.length) return;
  root.classList.add("pn-live");

  // a sculpted word is sized to fit the board, whatever its length
  $$<HTMLElement>(".pn-sculpt--word, .pn-sculpt--when").forEach((el) => el.style.setProperty("--len", String(Math.max(3, (el.textContent || "").trim().length))));
  // words of sculpted and haloed text become spans, so each can be set in pins at its measured place
  secs.forEach((s) => s.kind === "plate" && s.srcs.forEach((src) => {
    if (src.kind !== "sculpt" && src.kind !== "halo") return;
    const walk = (node: Node) => {
      if (node.nodeType === 3) {
        const frag = document.createDocumentFragment();
        (node.textContent || "").split(/(\s+)/).forEach((part) => {
          if (!part) return;
          if (/^\s+$/.test(part)) { frag.appendChild(document.createTextNode(" ")); return; }
          const w = document.createElement("span"); w.className = "pn-w"; w.textContent = part; frag.appendChild(w);
        });
        node.parentNode!.replaceChild(frag, node);
      } else if (!(node as HTMLElement).classList?.contains("pn-w")) [...node.childNodes].forEach(walk);
    };
    [...src.el.childNodes].forEach(walk);
  }));

  // ---------------------------------------------------------------- grid
  let W = 0, Hh = 0, P = 6, cols = 0, rows = 0, OX = 0, OY = 0, N = 0, L = 0;
  let D = new Float32Array(0), V = new Float32Array(0), Pr = new Float32Array(0), U8 = new Uint8Array(0), black = new Float32Array(0);
  let PX = new Float32Array(0), PY = new Float32Array(0);
  const cc = document.createElement("canvas");
  const cx = cc.getContext("2d", { willReadFrequently: true })!;
  const tmp = document.createElement("canvas");
  const tx = tmp.getContext("2d", { willReadFrequently: true })!;
  let states: State[] = [];
  let art: ArtFrames | null = null;
  const t0 = performance.now();

  function geometry() {
    W = innerWidth; Hh = innerHeight;
    P = mobile() ? 3.8 : clamp(W / 250, 4.6, 6.6);
    cols = Math.ceil(W / P) + 1; rows = Math.ceil(Hh / P) + 1;
    OX = (W - cols * P) / 2; OY = (Hh - rows * P) / 2;
    N = cols * rows;
    D = new Float32Array(N); V = new Float32Array(N); Pr = new Float32Array(N); U8 = new Uint8Array(N * 2);
    black = new Float32Array(N).fill(0.9);
    PX = new Float32Array(N); PY = new Float32Array(N);
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) { PX[y * cols + x] = OX + (x + 0.5) * P; PY[y * cols + x] = OY + (y + 0.5) * P; }
    cc.width = cols; cc.height = rows;
    board!.size(W, Hh, Math.min(devicePixelRatio || 1, mobile() ? 1.75 : 2), cols, rows, P, OX, OY);
    const pins = $("[data-pn-pins]");
    if (pins) pins.textContent = N.toLocaleString("en-US");
  }

  // ---------------------------------------------------------------- composing a plate (in tone: 0 black .. 1 lit)
  const rel = (el: Element, stage: Element): Rect => { const a = el.getBoundingClientRect(), b = stage.getBoundingClientRect(); return { x: a.left - b.left, y: a.top - b.top, w: a.width, h: a.height }; };
  const cssT = () => cx.setTransform(1 / P, 0, 0, 1 / P, -OX / P, -OY / P);
  const reset = () => { cx.setTransform(1, 0, 0, 1, 0, 0); cx.globalCompositeOperation = "source-over"; cx.filter = "none"; cx.clearRect(0, 0, cols, rows); };
  const gbox = (r: Rect, pad = 2) => {
    const x0 = clamp(Math.floor((r.x - OX) / P) - pad, 0, cols - 1), y0 = clamp(Math.floor((r.y - OY) / P) - pad, 0, rows - 1);
    const x1 = clamp(Math.ceil((r.x + r.w - OX) / P) + pad, 0, cols - 1), y1 = clamp(Math.ceil((r.y + r.h - OY) / P) + pad, 0, rows - 1);
    return { x0, y0, w: x1 - x0 + 1, h: y1 - y0 + 1 };
  };
  function readBox(b: { x0: number; y0: number; w: number; h: number }) {
    cx.setTransform(1, 0, 0, 1, 0, 0);
    const d = cx.getImageData(b.x0, b.y0, b.w, b.h).data, m = new Float32Array(b.w * b.h);
    for (let i = 0; i < m.length; i++) m[i] = (d[i * 4] * d[i * 4 + 3]) / 65025;
    return m;
  }
  function fillWords(el: HTMLElement, stage: HTMLElement) {
    let box: Rect | null = null;
    for (const w of $$<HTMLElement>(".pn-w", el)) {
      const r = rel(w, stage);
      if (!r.w) continue;
      const cs = getComputedStyle(w), size = parseFloat(cs.fontSize);
      cx.font = `${cs.fontStyle} ${cs.fontWeight} ${size}px ${cs.fontFamily}`;
      const m = cx.measureText(w.textContent || "");
      const asc = m.fontBoundingBoxAscent ?? size * 0.8, desc = m.fontBoundingBoxDescent ?? size * 0.2;
      cx.fillText(w.textContent || "", r.x, r.y + (r.h - (asc + desc)) / 2 + asc);
      box = box ? { x: Math.min(box.x, r.x), y: Math.min(box.y, r.y), w: Math.max(box.x + box.w, r.x + r.w) - Math.min(box.x, r.x), h: Math.max(box.y + box.h, r.y + r.h) - Math.min(box.y, r.y) } : r;
    }
    return box;
  }

  /** Value noise, a few octaves, for the smoky grain of a pinscreen picture. */
  function fbm(seed: number, x: number, y: number) {
    let v = 0, a = 0.5, f = 1 / 90;
    for (let o = 0; o < 4; o++) {
      const X = x * f, Y = y * f, xi = Math.floor(X), yi = Math.floor(Y), xf = X - xi, yf = Y - yi;
      const h = (i: number, j: number) => hash((i * 73856093) ^ (j * 19349663) ^ (seed * 83492791 + o * 2654435761));
      const sx = xf * xf * (3 - 2 * xf), sy = yf * yf * (3 - 2 * yf);
      const n = h(xi, yi) * (1 - sx) * (1 - sy) + h(xi + 1, yi) * sx * (1 - sy) + h(xi, yi + 1) * (1 - sx) * sy + h(xi + 1, yi + 1) * sx * sy;
      v += a * n; a *= 0.5; f *= 2.1;
    }
    return v;   // ~0..1, mean .47
  }

  let smokes: Float32Array[] = [];
  function smokeField(seed: number) {
    const k = ((seed % 3) + 3) % 3;
    if (!smokes[k] || smokes[k].length !== N) { const f = new Float32Array(N); for (let i = 0; i < N; i++) f[i] = fbm(k * 17 + 5, PX[i], PY[i]); smokes[k] = f; }
    return smokes[k];
  }
  /** The lamp's pool falling off into black, with smoke in the light. */
  function background(B: Float32Array, ox: number, oy: number, seed: number, ang: number) {
    const lx = ox - Math.cos(ang) * W * 0.12, ly = oy - Math.sin(ang) * Hh * 0.12;
    const s2 = Math.pow(Math.max(W, Hh) * (mobile() ? 0.62 : 0.46), 2);
    for (let i = 0; i < N; i++) {
      const dx = PX[i] - lx, dy = (PY[i] - ly) * 1.15;
      const pool = Math.exp(-(dx * dx + dy * dy) / s2);
      const smoke = smokeField(seed)[i] - 0.47;
      const edge = Math.min(PX[i], PY[i], W - PX[i], Hh - PY[i]) / Math.min(W, Hh);
      B[i] = clamp((0.012 + 0.5 * pool) * (0.7 + 1.5 * smoke) * sstep(0, 0.2, edge) + Math.max(0, smoke) * 0.04 * pool);
    }
  }

  /** Sculpt a mask into lit relief: distance-field height, normals, lamp shading, and the shape's cast shadow. */
  function sculpt(B: Float32Array, m: Float32Array, b: { x0: number; y0: number; w: number; h: number }, ang: number, strength: number) {
    const { w, h } = b, n = w * h;
    const dist = new Float32Array(n);
    const INF = 1e6;
    for (let i = 0; i < n; i++) dist[i] = m[i] > 0.5 ? INF : 0;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {   // two-pass chamfer distance
      const i = y * w + x; if (!dist[i]) continue;
      let v = dist[i];
      if (x > 0) v = Math.min(v, dist[i - 1] + 1);
      if (y > 0) { v = Math.min(v, dist[i - w] + 1); if (x > 0) v = Math.min(v, dist[i - w - 1] + 1.414); if (x < w - 1) v = Math.min(v, dist[i - w + 1] + 1.414); }
      dist[i] = v;
    }
    let mx = 0;
    for (let y = h - 1; y >= 0; y--) for (let x = w - 1; x >= 0; x--) {
      const i = y * w + x; if (!dist[i]) continue;
      let v = dist[i];
      if (x < w - 1) v = Math.min(v, dist[i + 1] + 1);
      if (y < h - 1) { v = Math.min(v, dist[i + w] + 1); if (x < w - 1) v = Math.min(v, dist[i + w + 1] + 1.414); if (x > 0) v = Math.min(v, dist[i + w - 1] + 1.414); }
      dist[i] = v; if (v > mx) mx = v;
    }
    const R = Math.max(2, mx * 0.85);
    const H = new Float32Array(n);
    for (let i = 0; i < n; i++) H[i] = m[i] > 0.02 ? Math.pow(Math.min(1, (dist[i] + m[i] * 0.6) / R), 0.55) * Math.min(1, m[i] * 1.4) : 0;
    const ldx = -Math.cos(ang), ldy = -Math.sin(ang), lz = 1.05, ll = Math.hypot(ldx, ldy, lz);
    const sdx = Math.cos(ang) * R * 0.9, sdy = Math.sin(ang) * R * 0.9;   // the cast shadow's offset, in cells
    const k = 2.4;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = y * w + x, gi = (b.y0 + y) * cols + b.x0 + x;
      const sx = Math.round(x - sdx), sy = Math.round(y - sdy);
      const caster = sx >= 0 && sy >= 0 && sx < w && sy < h ? m[sy * w + sx] : 0;
      const bg = B[gi] * (1 - 0.85 * caster * strength);
      if (m[i] < 0.02) { B[gi] = bg; continue; }
      const gx = ((x < w - 1 ? H[i + 1] : H[i]) - (x > 0 ? H[i - 1] : H[i])) * k;
      const gy = ((y < h - 1 ? H[i + w] : H[i]) - (y > 0 ? H[i - w] : H[i])) * k;
      const nl = Math.hypot(gx, gy, 1);
      const sh = Math.max(0, (-gx * ldx - gy * ldy + lz) / (nl * ll));
      const lit = (0.02 + 1.05 * Math.pow(sh, 2.1)) * strength;
      const a = Math.min(1, m[i] * 1.3);
      B[gi] = bg * (1 - a) + Math.max(bg * 0.3, lit) * a;
    }
  }

  function maskOf(draw: () => Rect | null, pad = 3) {
    reset(); cssT(); cx.fillStyle = "#fff";
    const r = draw();
    if (!r) return null;
    const b = gbox(r, pad);
    return { m: readBox(b), b };
  }

  function artInto(B: Float32Array, r: Rect, frame: number) {
    if (!art) return;
    const m = art.mask[((frame % art.n) + art.n) % art.n];
    const b = gbox(r, 0);
    const s = Math.min(b.w / art.w, b.h / art.h) * 1.04, ox = (b.w - art.w * s) / 2, oy = (b.h - art.h * s) / 2;
    for (let y = 0; y < b.h; y++) for (let x = 0; x < b.w; x++) {
      const ax = Math.floor((x - ox) / s), ay = Math.floor((y - oy) / s);
      const mv = ax >= 0 && ay >= 0 && ax < art.w && ay < art.h ? m[ay * art.w + ax] : 0;
      const ex = (x + 0.5) / b.w * 2 - 1, ey = (y + 0.5) / b.h * 2 - 1;
      const vig = 1 - sstep(0.5, 1.0, Math.sqrt(ex * ex * 0.9 + ey * ey));
      const gi = (b.y0 + y) * cols + b.x0 + x;
      const v = Math.pow(clamp(mv * 1.12), 0.9) * 0.97;
      B[gi] = Math.max(B[gi] * (1 - 0.7 * vig), v * vig + B[gi] * (1 - vig));
    }
  }
  function lumInto(B: Float32Array, src: CanvasImageSource, sw: number, sh: number, r: Rect, vig: boolean, gamma = 1): boolean {
    const b = gbox(r, 0);
    tmp.width = b.w; tmp.height = b.h;
    const sA = sw / sh, dA = b.w / b.h;
    let dw = b.w, dh = b.h, dx = 0, dy = 0;
    if (sA > dA) { dw = b.h * sA; dx = (b.w - dw) / 2; } else { dh = b.w / sA; dy = (b.h - dh) / 2; }
    tx.fillStyle = "#000"; tx.fillRect(0, 0, b.w, b.h);
    try { tx.drawImage(src, dx, dy, dw, dh); } catch { return false; }
    let d: Uint8ClampedArray;
    try { d = tx.getImageData(0, 0, b.w, b.h).data; } catch { return false; }
    let sum = 0;
    for (let y = 0; y < b.h; y++) for (let x = 0; x < b.w; x++) {
      const o = (y * b.w + x) * 4, lum = (d[o] * 0.299 + d[o + 1] * 0.587 + d[o + 2] * 0.114) / 255;
      sum += lum;
      let v = Math.pow(lum, gamma);
      const gi = (b.y0 + y) * cols + b.x0 + x;
      if (vig) { const ex = (x + 0.5) / b.w * 2 - 1, ey = (y + 0.5) / b.h * 2 - 1, k = 1 - sstep(0.55, 1.0, Math.sqrt(ex * ex + ey * ey)); v = v * k + B[gi] * (1 - k); }
      B[gi] = v;
    }
    return sum > 0.5;
  }
  function phoneInto(B: Float32Array, el: HTMLElement, stage: HTMLElement, ang: number) {
    const ph = $<HTMLElement>(".ss-phone", el);
    if (!ph) return;
    const r = rel(ph, stage);
    const mk = maskOf(() => { cx.beginPath(); (cx as any).roundRect ? (cx as any).roundRect(r.x, r.y, r.w, r.h, r.w * 0.15) : cx.rect(r.x, r.y, r.w, r.h); cx.fill(); return r; });
    if (mk) sculpt(B, mk.m, mk.b, ang, 0.85);
    const sc = $<HTMLElement>(".ss-phone__screen", ph);
    if (!sc) return;
    const s = rel(sc, stage);
    const img = $<HTMLImageElement>("img, video", sc);
    // the screen glows (pins pushed in), its rows set back into it
    const sb = gbox(s, 0);
    for (let y = 0; y < sb.h; y++) for (let x = 0; x < sb.w; x++) { const gi = (sb.y0 + y) * cols + sb.x0 + x; const e = Math.min(x, y, sb.w - 1 - x, sb.h - 1 - y); B[gi] = e < 1 ? 0.15 : 0.78 - 0.16 * (y / sb.h) - 0.08 * Math.abs(x / sb.w - 0.5); }
    if (img) { const [iw, ih] = dims(img); if (iw && ih) lumInto(B, img, iw, ih, s, false); return; }
    const dark = (el2: Element | null, v: number, frac = 0.6) => {
      if (!el2) return;
      const q = rel(el2, stage);
      if (q.y + q.h > s.y + s.h || q.y < s.y) return;
      const qb = gbox({ x: q.x, y: q.y + q.h * (1 - frac) / 2, w: q.w, h: q.h * frac }, 0);
      for (let y = 0; y < qb.h; y++) for (let x = 0; x < qb.w; x++) B[(qb.y0 + y) * cols + qb.x0 + x] = v;
    };
    $$(".ss-app__name, .ss-app__label, .ss-phone__bar span", ph).forEach((e2) => dark(e2, 0.5, 0.4));
    dark($(".ss-app__title", ph), 0.32, 0.55);
    $$<HTMLElement>(".ss-app__opt", ph).forEach((o) => dark(o, o.classList.contains("is-on") ? 0.3 : 0.6, 0.82));
    dark($(".ss-app__btn", ph), 0.22, 0.85);
  }

  function compose(sec: Plate, step: number, ang: number, seed: number): { pic: Float32Array; ox: number; oy: number; slab: State["slab"]; art: Rect | null } {
    const stage = sec.stage;
    const vis = (s: { steps: number[] | null }) => !s.steps || s.steps.includes(step);
    // the subject (where the lamp falls and the wave starts)
    const org = sec.srcs.find((s) => vis(s) && s.el.hasAttribute("data-origin"));
    let ox = W * 0.66, oy = Hh * 0.45;
    if (org) { const r = rel(org.el, stage); if (r.w) { ox = r.x + r.w / 2; oy = r.y + r.h / 2; } }
    const B = new Float32Array(N);
    background(B, ox, oy, seed, ang);
    let artRect: Rect | null = null, slab: State["slab"] = null;
    for (const s of sec.srcs) {
      if (!vis(s)) continue;
      const el = s.el;
      if (s.kind === "sculpt") {
        const mk = maskOf(() => fillWords(el, stage));
        const word = el.classList.contains("pn-sculpt--word");
        if (mk) sculpt(B, mk.m, mk.b, ang, s.el.dataset.step || !word ? 0.95 : 0.78);
      } else if (s.kind === "art") { artRect = rel(el, stage); artInto(B, artRect, 0); }
      else if (s.kind === "img") { const m = $<HTMLImageElement>("img, video", el); if (m) { const [iw, ih] = dims(m); if (iw && ih) lumInto(B, m, iw, ih, rel(el, stage), true, 1.1); } }
      else if (s.kind === "phone") phoneInto(B, el, stage, ang);
      else if (s.kind === "boss" || s.kind === "ridge") {
        const r = rel(el, stage), on = s.on < 0 || s.on === step;
        const mk = maskOf(() => { if (s.kind === "boss") { cx.beginPath(); cx.arc(r.x + r.w / 2, r.y + r.h / 2, r.w / 2, 0, Math.PI * 2); cx.fill(); } else cx.fillRect(r.x, r.y - 2, r.w, Math.max(r.h + 4, P * 2.2)); return r; });
        if (mk) sculpt(B, mk.m, mk.b, ang, on ? 0.95 : 0.55);
      }
    }
    // the copy: pins behind it stand out to black, feathered so it reads as shadow, not a box
    for (const c of sec.calms) {
      if (!vis(c)) continue;
      const rs: Rect[] = [];
      for (const ch of c.el.querySelectorAll<HTMLElement>("h1, h2, h3, p, li, dd, dt, blockquote, figcaption, summary, a, .pn-btns, .pn-meter")) {
        const r = rel(ch, stage); if (r.w && r.h) rs.push(r);
      }
      if (!rs.length) { const r = rel(c.el, stage); if (r.w) rs.push(r); }
      const fe = mobile() ? 26 : 46, pad = mobile() ? 10 : 18;
      for (const r of rs) {
        const b = gbox({ x: r.x - pad - fe, y: r.y - pad - fe, w: r.w + (pad + fe) * 2, h: r.h + (pad + fe) * 2 }, 0);
        for (let y = 0; y < b.h; y++) for (let x = 0; x < b.w; x++) {
          const gi = (b.y0 + y) * cols + b.x0 + x;
          const dx = Math.max(r.x - pad - PX[gi], 0, PX[gi] - (r.x + r.w + pad)), dy = Math.max(r.y - pad - PY[gi], 0, PY[gi] - (r.y + r.h + pad));
          const k = 1 - sstep(0, fe, Math.hypot(dx, dy));
          B[gi] *= 1 - 0.94 * k;
        }
      }
    }
    // the CTA slab, raised after the shadows of the copy so it stands on its own
    for (const s of sec.srcs) {
      if (s.kind !== "slab" || !vis(s)) continue;
      const el = s.el;
        const r = rel(el, stage);
        const mk = maskOf(() => { cx.beginPath(); (cx as any).roundRect ? (cx as any).roundRect(r.x, r.y, r.w, r.h, 8) : cx.rect(r.x, r.y, r.w, r.h); cx.fill(); return r; });
        if (mk) {
          const before = B.slice();
          sculpt(B, mk.m, mk.b, ang, 0.9);
          const m = new Float32Array(N), h = new Float32Array(N);
          for (let y = 0; y < mk.b.h; y++) for (let x = 0; x < mk.b.w; x++) { const gi = (mk.b.y0 + y) * cols + mk.b.x0 + x; m[gi] = mk.m[y * mk.b.w + x]; h[gi] = before[gi]; }
          slab = { m, h };
        }
    }
    // headlines: a soft lit relief of their words behind the crisp type (kept dim so ivory stays legible)
    for (const s of sec.srcs) {
      if (s.kind !== "halo" || !vis(s)) continue;
      reset(); cssT(); cx.fillStyle = "#fff";
      const size = parseFloat(getComputedStyle(s.el).fontSize) || 60;
      cx.filter = `blur(${Math.max(1, (size * 0.09) / P)}px)`;
      const r = fillWords(s.el, stage);
      cx.filter = "none";
      if (!r) continue;
      const b = gbox(r, Math.ceil((size * 0.3) / P));
      const m = readBox(b);
      const sdx = Math.round(Math.cos(ang) * size * 0.05 / P), sdy = Math.round(Math.sin(ang) * size * 0.05 / P);
      for (let y = 0; y < b.h; y++) for (let x = 0; x < b.w; x++) {
        const gx = b.x0 + x + sdx, gy = b.y0 + y + sdy;
        if (gx < 0 || gy < 0 || gx >= cols || gy >= rows) continue;
        const gi = gy * cols + gx;
        B[gi] = Math.max(B[gi], m[y * b.w + x] * 0.3);
      }
    }
    const pic = new Float32Array(N);
    for (let i = 0; i < N; i++) pic[i] = Math.pow(1 - clamp(B[i]), 0.78);
    if (slab) { const sl = slab as { m: Float32Array; h: Float32Array }; for (let i = 0; i < N; i++) if (sl.m[i] > 0) sl.h[i] = Math.pow(1 - clamp(sl.h[i] * 0.4 + 0.5), 0.85); }
    return { pic, ox, oy, slab, art: artRect };
  }

  /** A dark field with a quiet relief border for sections in default markup (or a scene the board can't play). */
  function frameOnly(seed: number): Float32Array {
    const B = new Float32Array(N);
    background(B, W / 2, Hh / 2, seed, 45 * DEG);
    const out = new Float32Array(N), m = Math.round(Math.min(cols, rows) * 0.035) + 2;
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
      const i = y * cols + x, e = Math.min(x, y, cols - 1 - x, rows - 1 - y);
      out[i] = Math.pow(1 - B[i] * 0.3 - (e === m || e === m + 2 ? 0.5 : 0), 0.85);
    }
    return out;
  }

  // ---------------------------------------------------------------- the schedule
  const LAMPS = [48, 132, 60, 118, 40, 140, 72, 108];
  function schedule() {
    L = Hh * (mobile() ? 0.85 : 0.95);
    secs.forEach((s, i) => {
      if (s.kind !== "plate") return;
      const last = secs.slice(i + 1).every((q) => q.kind !== "plate");
      s.el.style.setProperty("--pn-h", `${Math.round(last ? Math.max(s.n * L, Hh) : s.n * L)}px`);
    });
    secs.forEach((s) => { const r = s.el.getBoundingClientRect(); s.top = r.top + scrollY; if (s.kind === "flow") s.h = r.height; });
    const out: State[] = [];
    let plateNo = 0;
    for (const s of secs) {
      if (s.kind === "plate") {
        const base = LAMPS[plateNo++ % LAMPS.length];
        for (let j = 0; j < s.n; j++) {
          const anchor = s.top + j * L;
          const ang = (s.sundial ? (s.n > 1 ? 32 + (116 * j) / (s.n - 1) : 90) : base) * DEG;
          const c = compose(s, j, ang, s.idx * 31 + j * 7 + 3);
          const st: State = { sec: s, step: j, anchor, h0: anchor - 0.18 * L, h1: anchor + 0.18 * L, ang, len: (s.low ? 3.3 : 2.5) * (mobile() ? 0.8 : 1), ox: c.ox, oy: c.oy, pic: c.pic, dyn: null, slab: c.slab };
          if (c.art && art) {
            const basePic = c.pic, ar = c.art;
            st.dyn = (o) => {
              const B = new Float32Array(N); for (let i = 0; i < N; i++) B[i] = 1 - Math.pow(basePic[i], 1 / 0.85);
              artInto(B, ar, Math.floor(((performance.now() - t0) / 1000) * art!.fps));
              const b = gbox(ar, 0); o.set(basePic);
              for (let y = 0; y < b.h; y++) for (let x = 0; x < b.w; x++) { const gi = (b.y0 + y) * cols + b.x0 + x; o[gi] = Math.pow(1 - clamp(B[gi]), 0.85); }
              return true;
            };
          }
          out.push(st);
        }
      } else {
        const h0 = s.top - 0.45 * Hh, h1 = Math.max(h0, s.top + s.h - 0.55 * Hh);
        const st: State = { sec: s, step: 0, anchor: Math.max(0, s.top), h0, h1, ang: LAMPS[plateNo++ % LAMPS.length] * DEG, len: 2.5, ox: W / 2, oy: Hh / 2, pic: frameOnly(s.idx * 31), dyn: null, slab: null };
        if (s.scene && s.vis) {
          const flow = s, frame = st.pic;
          st.dyn = (o) => {
            const vis = flow.vis!, m = vis.querySelector<HTMLVideoElement>("video") || vis.querySelector<HTMLCanvasElement>("canvas") || vis.querySelector<HTMLImageElement>("img");
            if (!m) { o.set(frame); return false; }
            const [vw, vh] = dims(m);
            if (!vw || !vh || (m instanceof HTMLVideoElement && m.readyState < 2)) { o.set(frame); return false; }
            const B = new Float32Array(N);
            const ok = lumInto(B, m, vw, vh, { x: 0, y: 0, w: W, h: Hh }, false, 1.2);
            if (!ok) { o.set(frame); if (flow.sampled) { flow.sampled = false; flow.el.classList.remove("pn-pinned"); } return false; }
            for (let i = 0; i < N; i++) o[i] = Math.pow(1 - B[i], 0.85);
            if (!flow.sampled) { flow.sampled = true; flow.el.classList.add("pn-pinned"); }
            return true;
          };
        }
        out.push(st);
      }
    }
    for (let k = 1; k < out.length; k++) if (out[k].h0 < out[k - 1].h1) { const m = (out[k].h0 + out[k - 1].h1) / 2; out[k].h0 = out[k - 1].h1 = m; }
    if (out.length) out[0].h0 = Math.min(out[0].h0, 0);
    states = out;
  }

  // ---------------------------------------------------------------- pointer: the lamp and the burin
  let lampOff = 0, lampOffT = 0, lastPt: { x: number; y: number } | null = null, slabK = 0, slabT = 0;
  function stamp(x0: number, y0: number, x1: number, y1: number, strength = 1.7) {
    const R = Math.max(P * 1.5, 9);
    const gx0 = Math.max(0, Math.floor((Math.min(x0, x1) - R - OX) / P)), gx1 = Math.min(cols - 1, Math.ceil((Math.max(x0, x1) + R - OX) / P));
    const gy0 = Math.max(0, Math.floor((Math.min(y0, y1) - R - OY) / P)), gy1 = Math.min(rows - 1, Math.ceil((Math.max(y0, y1) + R - OY) / P));
    const dx = x1 - x0, dy = y1 - y0, ll = dx * dx + dy * dy || 1;
    for (let gy = gy0; gy <= gy1; gy++) for (let gx = gx0; gx <= gx1; gx++) {
      const i = gy * cols + gx, px = PX[i], py = PY[i];
      const t = clamp(((px - x0) * dx + (py - y0) * dy) / ll);
      const d = Math.hypot(px - (x0 + dx * t), py - (y0 + dy * t)) / R;
      if (d >= 1) continue;
      const v = strength * (1 - d * d);
      if (v > Pr[i]) Pr[i] = v;
    }
    dirty = true;
  }
  const busy = (el: EventTarget | null) => !!(el as HTMLElement)?.closest?.("a, button, summary, input, textarea, select, .pn-rail, .ss-looks");
  addEventListener("pointermove", (e) => {
    if (e.pointerType === "touch") return;
    lampOffT = (e.clientX / innerWidth - 0.5) * 0.7;
    if (e.buttons & 1 && lastPt && !busy(e.target)) stamp(lastPt.x, lastPt.y, e.clientX, e.clientY);
    lastPt = (e.buttons & 1) ? { x: e.clientX, y: e.clientY } : null;
  }, { passive: true });
  addEventListener("pointerdown", (e) => {
    if (e.pointerType === "touch" || e.button !== 0 || busy(e.target)) return;
    if (!(e.target as HTMLElement)?.closest?.(".pn-copy")) e.preventDefault();
    lastPt = { x: e.clientX, y: e.clientY }; stamp(e.clientX, e.clientY, e.clientX + 0.1, e.clientY);
  });
  addEventListener("pointerup", () => { lastPt = null; }, { passive: true });
  let touchPt: { x: number; y: number } | null = null;
  addEventListener("touchstart", (e) => { const t = e.touches[0]; touchPt = t && !busy(e.target) ? { x: t.clientX, y: t.clientY } : null; }, { passive: true });
  addEventListener("touchmove", (e) => { const t = e.touches[0]; if (!t || !touchPt) return; stamp(touchPt.x, touchPt.y, t.clientX, t.clientY, 1.5); touchPt = { x: t.clientX, y: t.clientY }; }, { passive: true });
  addEventListener("touchend", () => { touchPt = null; }, { passive: true });
  document.addEventListener("pointerover", (e) => { slabT = (e.target as HTMLElement)?.closest?.(".pn-cta__slab") ? 1 : 0; }, { passive: true });
  document.addEventListener("focusin", (e) => {
    const el = e.target as HTMLElement;
    const st = states.find((s) => s.sec.kind === "plate" && s.sec.stage.contains(el) && (stepsOf(el, s.sec.stage)?.includes(s.step) ?? true));
    if (st && (scrollY < st.h0 - 2 || scrollY > st.h1 + 2)) scrollTo({ top: st.anchor, behavior: "auto" });
  });

  // ---------------------------------------------------------------- the copy follows the wave
  const HIDE = "inset(0 0 100% 0)";
  function circlePath(cxp: number, cyp: number, r: number, ox: number, oy: number) {
    let d = "";
    for (let k = 0; k <= 48; k++) { const a = (k / 48) * Math.PI * 2; d += `${k ? " L" : "M"} ${(cxp + Math.cos(a) * r - ox).toFixed(1)} ${(cyp + Math.sin(a) * r - oy).toFixed(1)}`; }
    return d + " Z";
  }
  function clipFor(el: HTMLElement, wx: number, wy: number, r: number, side: "in" | "out", fixed: boolean) {
    let ox = 0, oy = 0, w = W, h = Hh;
    if (!fixed) { const b = el.getBoundingClientRect(); ox = b.left; oy = b.top; w = b.width; h = b.height; }
    if (side === "in") return `circle(${r.toFixed(1)}px at ${(wx - ox).toFixed(1)}px ${(wy - oy).toFixed(1)}px)`;
    return `path(evenodd, "M -40 -40 H ${(w + 40).toFixed(0)} V ${(h + 40).toFixed(0)} H -40 Z ${circlePath(wx, wy, r, ox, oy)}")`;
  }
  function setClip(o: { el: HTMLElement; clip: string }, v: string) { if (o.clip !== v) { o.clip = v; o.el.style.clipPath = v; } }

  // ---------------------------------------------------------------- per frame
  let dirty = true, ready = false, curAng = 48 * DEG, curLen = 2.5;
  let bufA = new Float32Array(0), bufB = new Float32Array(0);
  const plateEl = $("[data-pn-plate]"), lampEl = $("[data-pn-lamp]"), azEl = $("[data-pn-azimuth]");
  const COMPASS = ["E", "SE", "S", "SW", "W", "NW", "N", "NE"];
  let hudKey = "";

  function blendAt(y: number): { a: State; b: State; t: number } {
    const n = states.length;
    if (y <= states[0].h1) return { a: states[0], b: states[0], t: 0 };
    for (let k = 0; k < n; k++) {
      const s = states[k];
      if (y >= s.h0 && y <= s.h1) return { a: s, b: s, t: 0 };
      const nx = states[k + 1];
      if (nx && y > s.h1 && y < nx.h0) return { a: s, b: nx, t: (y - s.h1) / Math.max(1, nx.h0 - s.h1) };
    }
    return { a: states[n - 1], b: states[n - 1], t: 0 };
  }
  function picOf(st: State, which: 0 | 1): Float32Array {
    let buf = which ? bufB : bufA;
    if (buf.length !== N) { buf = new Float32Array(N); if (which) bufB = buf; else bufA = buf; }
    let base = st.pic;
    if (st.dyn && st.dyn(buf)) base = buf;
    if (st.slab) {
      if (base === st.pic) { buf.set(st.pic); base = buf; }
      const { m, h } = st.slab;
      for (let i = 0; i < N; i++) if (m[i] > 0) base[i] = base[i] * (1 - m[i]) + (h[i] * slabK + base[i] * (1 - slabK)) * m[i];
    }
    return base;
  }

  function dom(a: State, b: State, t: number, wx: number, wy: number, r: number) {
    const tw = reduced ? (t < 0.5 ? 0 : 1) : t;
    for (const sec of secs) {
      if (sec.kind !== "plate") continue;
      const inA = a.sec === sec, inB = b !== a && b.sec === sec;
      const o = { el: sec.stage, get clip() { return sec.clip; }, set clip(v: string) { sec.clip = v; } };
      let on = inA || inB;
      if (!on) setClip(o, HIDE);
      else if (b !== a && inA !== inB) {
        if (reduced) { on = tw < 0.5 ? inA : inB; setClip(o, on ? "none" : HIDE); }
        else setClip(o, clipFor(sec.stage, wx, wy, r, inB ? "in" : "out", true));
      } else setClip(o, "none");
      sec.stage.classList.toggle("is-on", on);
      if (!on) continue;
      const cur = tw < 0.5 ? (inA ? a : b) : (inB ? b : a);
      for (const el of sec.ons) el.classList.toggle("is-active", +(el.dataset.on || -1) === cur.step);
      for (const wr of sec.wraps) {
        const ina = inA && wr.steps.includes(a.step), inb = inB && wr.steps.includes(b.step);
        let v = HIDE;
        if (ina && inb) v = "none";
        else if (b !== a && inA && inB && !reduced) v = ina ? clipFor(wr.el, wx, wy, r, "out", false) : inb ? clipFor(wr.el, wx, wy, r, "in", false) : HIDE;
        else if (b !== a && inA && inB && reduced) v = (tw < 0.5 ? ina : inb) ? "none" : HIDE;
        else if (b !== a && !reduced) v = ina || inb ? "none" : HIDE;
        else v = (tw < 0.5 ? ina : inb) || (a === b && ina) ? "none" : HIDE;
        setClip(wr, v);
      }
    }
  }

  function frame(dt: number) {
    if (!ready || !states.length) return;
    let { a, b, t } = blendAt(scrollY);
    if (reduced) t = t < 0.5 ? 0 : 1;
    // the opening: the board starts as a wall of black pins and the first wave reveals the hero
    const intro = reduced ? 1 : clamp((performance.now() - t0 - 200) / 1700);
    let A = picOf(a, 0), B = b === a ? A : picOf(b, 1), tt = t, wave = a !== b;
    let wx = b.ox, wy = b.oy;
    if (a === states[0] && b === states[0] && intro < 1) { B = A; A = black; tt = intro; wave = true; wx = a.ox; wy = a.oy; }
    const Rmax = Math.max(Math.hypot(wx, wy), Math.hypot(W - wx, wy), Math.hypot(wx, Hh - wy), Math.hypot(W - wx, Hh - wy)) + 80;
    const r = ease(tt) * Rmax;
    const env = wave && !reduced ? Math.pow(Math.sin(Math.PI * clamp(tt)), 0.6) : 0;
    const wd = mobile() ? 16 : 24, lam = mobile() ? 30 : 44, k2 = (Math.PI * 2) / lam;
    // lamp: the plates' angles, the pointer, and a lower lamp while the wave runs so the moving pins throw long shadows
    lampOff += (lampOffT - lampOff) * (1 - Math.exp(-dt * 6));
    slabK += (slabT - slabK) * (1 - Math.exp(-dt * 9));
    const s = sstep(0, 1, t);
    const ang = a.ang + (b.ang - a.ang) * s + lampOff;
    const len = (a.len + (b.len - a.len) * s) * (1 + 0.55 * env);
    if (Math.abs(ang - curAng) > 1e-4 || Math.abs(len - curLen) > 1e-4) { curAng = ang; curLen = len; dirty = true; }
    const kk = reduced ? 1 : 1 - Math.exp(-dt * 26);
    const decay = dt * 0.34;
    let moved = false;
    for (let i = 0; i < N; i++) {
      let tg: number;
      if (!wave) tg = A[i];
      else {
        const x = r - Math.hypot(PX[i] - wx, PY[i] - wy);
        const base = x < -6 ? A[i] : x > 6 ? B[i] : A[i] + (B[i] - A[i]) * sstep(-6, 6, x);
        let add = 0;
        if (env > 0) {
          // the front: a trough the lamp floods with light, then the wall of pins pushed out behind it, then ripples
          const xa = x + wd * 0.7, xb = x - wd * 0.7;
          add = env * (0.95 * Math.exp(-(xb * xb) / (wd * wd)) - 0.9 * Math.exp(-(xa * xa) / (wd * wd * 0.6)));
          if (x > wd) add += env * 0.42 * Math.exp(-(x - wd) / 210) * Math.sin((x - wd) * k2);
        }
        tg = base + add; tg = tg < 0 ? 0 : tg > 1 ? 1 : tg;
      }
      let pr = Pr[i];
      if (pr > 0) {
        const pc = pr > 1 ? 1 : pr;
        tg = tg > 0.55 ? tg * (1 - pc * 0.95) : tg + (0.95 - tg) * pc;
        pr -= decay; Pr[i] = pr > 0 ? pr : 0;
        moved = true;
      }
      const d = tg - D[i];
      if (d > 0.002 || d < -0.002) { D[i] += d * kk; moved = true; V[i] = Math.min(1, V[i] * 0.85 + Math.abs(d * kk) * 6); }
      else if (V[i] > 0.001) { V[i] *= 0.85; moved = true; } else V[i] = 0;
    }
    if (moved) dirty = true;
    dom(a, b, t, wx, wy, r);
    // HUD
    const cur = t < 0.5 ? a : b;
    const from = Math.atan2(-Math.sin(curAng), -Math.cos(curAng));
    const key = `${cur.sec.idx}|${Math.round(from * 60)}`;
    if (key !== hudKey) {
      hudKey = key;
      if (plateEl) plateEl.textContent = String(cur.sec.idx + 1).padStart(2, "0");
      if (lampEl) lampEl.setAttribute("transform", `rotate(${(from / DEG + 90).toFixed(1)})`);
      if (azEl) azEl.textContent = COMPASS[((Math.round(from / (Math.PI / 4)) % 8) + 8) % 8];
    }
    if (dirty && !document.hidden) {
      for (let i = 0; i < N; i++) { U8[i * 2] = D[i] * 255; U8[i * 2 + 1] = V[i] * 255; }
      board!.draw(U8, curAng, curLen);
      dirty = false;
    }
  }

  // ---------------------------------------------------------------- go
  let resizeT = 0;
  function rebuild() {
    geometry();
    schedule();
    const { a, b, t } = blendAt(scrollY);
    const st = t < 0.5 || a === b ? a : b;
    D.set(st === states[0] && scrollY < states[0].h1 + 1 && performance.now() - t0 < 1900 ? black : picOf(st, 0));
    dirty = true;
  }
  addEventListener("resize", () => {
    clearTimeout(resizeT);
    resizeT = window.setTimeout(() => { if (Math.abs(innerWidth - W) > 2 || Math.abs(innerHeight - Hh) > 120) rebuild(); }, 180);
  });
  const go = () => { if (ready) return; rebuild(); ready = true; };
  Promise.all([
    document.fonts.load('100px "Yeseva One"').catch(() => null),
    document.fonts.ready,
    loadArt().then((x) => { art = x; }),
    ...$$<HTMLImageElement>(".pn-pic img").map((im) => im.complete ? null : new Promise((r) => { im.onload = im.onerror = r; })),
  ]).then(go);
  setTimeout(go, 2500);
  onFrame(({ dt }) => frame(dt || 1 / 60));
}
