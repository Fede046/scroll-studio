/**
 * film + world: type set inside the film. The film is drawn through a WebGL shader that also carries the scene's titles:
 *
 *   behind  the title sits at a depth. A depth map of the film (packed as a tile of a grayscale atlas video, encoded with the
 *           film's frame rate, frame count and GOP) says where every pixel is; the title shows only where the scene is
 *           farther than the title, so what is nearer passes in front of it as the camera moves.
 *   sky     the same, far away: type in the haze with fog in front of it.
 *   surface the title is painted on a surface. A tracked mask of the surface (another tile of the atlas) says where the paint
 *           may be, and a matrix per frame (planar tracking, built by engine/world.py) carries the letters with the surface
 *           in perspective; the surface's own light, grain and relief show through the paint, and it wears.
 *
 * The title's letters are typeset once with the site's own fonts (lib/worldText.ts) onto an atlas texture. For every frame
 * the build gives each title a 3x3 matrix from screen to the title's plane; the shader finds the letter under each pixel with
 * one multiply and one division. The film and the atlas are seeked together and drawn only when both have landed.
 *
 * Returns null (the caller plays the plain film, with the titles as ordinary captions) when WebGL2 is missing, with reduced
 * motion, or if anything about it fails. A title that would be cropped off a narrow screen is left to its caption.
 */
import type { Player, PlayerContext } from "../lib/types";
import { clamp, follow, isMobile, reducedMotion } from "../lib/util";
import { loadVideo, makeVideo, PairedSeeker } from "../lib/film";
import { contrastWith, inkFor, layout, PAD, probeStyle, rasterize, type Layout, type WorldStyle } from "../lib/worldText";

const N = 3;                                      // titles drawn at once (the build keeps overlapping titles within this)
const KIND = { behind: 0, sky: 1, surface: 2 } as const;

interface TextCfg {
  i: number; kind: keyof typeof KIND; f0: number; f1: number; anchor: number; m: number[][]; c: number[];
  plane: [number, number]; box: [number, number, number]; slot: string;
  depth?: number; soft?: number; blur?: number; tone?: number; ppp?: number; quad?: number[][];
  style: { align: "left" | "center" | "right"; caps: boolean; track: number; weight: number | null; color: string; haze: number; fog: number; wear: number; relief: number; lines: number | null };
}
interface Cfg {
  video: string; videoMobile?: string; poster?: string;
  world: { fps: number; frames: number; atlas: { video: string; mobile?: string; cols: number; rows: number; tile: [number, number]; slots: string[] } | null; texts: TextCfg[] };
}

const VERT = `#version 300 es
in vec2 aPos; out vec2 vUv;
void main() { vUv = vec2(aPos.x * 0.5 + 0.5, 0.5 - aPos.y * 0.5); gl_Position = vec4(aPos, 0.0, 1.0); }`;

const FRAG = `#version 300 es
precision highp float;
in vec2 vUv; out vec4 o;
#define N ${N}
#define PAD ${PAD.toFixed(3)}
const vec3 LW = vec3(0.2126, 0.7152, 0.0722);
uniform sampler2D uFilm, uAtlas, uText;
uniform vec2 uGrid, uInset, uTexel;
uniform float uOn[N], uIn[N];
uniform int uKind[N];
uniform mat3 uM[N];
uniform vec4 uBox[N], uCell[N], uA[N], uB[N];
uniform vec2 uSlot[N];
uniform float uHasAtlas;

float hash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float vnoise(vec2 p) {
  vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}
float fbm(vec2 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++) { s += a * vnoise(p); p *= 2.03; a *= 0.5; } return s / 0.9375; }
float atlasAt(vec2 slot, vec2 uv) {
  vec2 t = clamp(uv, uInset, 1.0 - uInset);
  return texture(uAtlas, (slot + t) / uGrid).r;
}
// the scene's depth here; the nearest of a few taps, so an occluder's edge is not eaten by the type's halo
float depthAt(vec2 slot, vec2 uv) {
  float d = atlasAt(slot, uv);
  d = max(d, atlasAt(slot, uv + vec2(uTexel.x, 0.0)));
  d = max(d, atlasAt(slot, uv - vec2(uTexel.x, 0.0)));
  d = max(d, atlasAt(slot, uv + vec2(0.0, uTexel.y)));
  d = max(d, atlasAt(slot, uv - vec2(0.0, uTexel.y)));
  return d;
}

void main() {
  vec3 film = texture(uFilm, vUv).rgb;
  vec3 col = film;
  vec3 near = textureLod(uFilm, vUv, 1.6).rgb;      // the picture without its grain
  vec3 locl = textureLod(uFilm, vUv, 3.6).rgb;      // the light right here
  vec3 air = textureLod(uFilm, vUv, 6.5).rgb;       // the colour of the air here
  for (int s = 0; s < N; s++) {
    if (uOn[s] < 0.002) continue;
    vec3 q = uM[s] * vec3(vUv, 1.0);
    vec2 pl = q.xy / q.z;
    vec2 lc = (pl - uBox[s].xy) / (uBox[s].zw * (1.0 + 2.0 * PAD)) + 0.5;
    vec2 dx = dFdx(lc), dy = dFdy(lc);
    vec2 inb = step(vec2(0.0), lc) * step(lc, vec2(1.0));
    float inside = inb.x * inb.y * step(0.0, q.z);
    vec2 tuv = uCell[s].xy + clamp(lc, 0.0, 1.0) * uCell[s].zw;
    float bl = exp2(uA[s].w);
    vec4 t = textureGrad(uText, tuv, dx * uCell[s].zw * bl, dy * uCell[s].zw * bl);      // premultiplied
    float cov = t.a * inside;
    if (cov < 0.002) continue;
    vec3 ink = t.rgb / max(t.a, 1e-4);
    float lumLoc = dot(locl, LW), Lf = dot(film, LW), Ln = dot(near, LW);
    float tone = uB[s].w;
    if (uKind[s] != 2) {
      // behind / sky: shown where the scene is farther than the type
      float dep = depthAt(uSlot[s], vUv);
      float vis = 1.0 - smoothstep(uA[s].x - uA[s].y, uA[s].x + uA[s].y, dep);
      vec3 lit = ink * mix(1.0, clamp(lumLoc / max(tone, 0.08), 0.55, 1.25), 0.55);
      float hz = clamp(uA[s].z * (1.0 + (1.0 - uIn[s]) * 1.4), 0.0, 0.95);
      lit = mix(lit, air, hz);
      lit += (Lf - Ln) * 0.9;                       // the film's grain runs through the letters
      float a = cov * vis * uOn[s] * (1.0 - 0.3 * hz);
      if (uKind[s] == 1) {
        float fog = uB[s].x * (0.2 + 0.8 * smoothstep(0.05, 0.95, vUv.y));
        fog += uB[s].x * 0.5 * (1.0 - smoothstep(0.0, 0.3, abs(dep - uA[s].x)));
        lit = mix(lit, air, clamp(fog * 0.85, 0.0, 1.0));
        a *= 1.0 - clamp(fog * 0.5, 0.0, 0.75);
      }
      col = mix(col, lit, clamp(a, 0.0, 1.0));
    } else {
      // surface: paint on the thing, in its light, worn by its grain
      float m = atlasAt(uSlot[s], vUv);
      float vis = smoothstep(0.35, 0.65, m);
      float wipe = smoothstep(lc.x - 0.18, lc.x + 0.02, uIn[s] * 1.3 - 0.1);   // painted on, left to right
      float n = fbm(pl * 52.0) * 0.75 + (0.5 - (Lf - Ln) * 5.0) * 0.25;
      float th = 1.0 - uB[s].y * 0.9;
      float worn = 1.0 - smoothstep(th - 0.1, th + 0.14, n) * step(0.001, uB[s].y);
      float lightK = clamp(lumLoc / max(tone, 0.06), 0.35, 1.5);
      vec3 paint = ink * mix(1.0, lightK, 0.9);
      float texK = clamp(Lf / max(Ln, 0.03), 0.55, 1.5);
      paint *= mix(1.0, texK * texK, uB[s].z);
      float inkL = dot(ink, LW);
      vec3 bleed = inkL < 0.5 ? film * ink * 1.8 : 1.0 - (1.0 - film) * (1.0 - ink * 0.9);
      paint = mix(paint, bleed, 0.2 + 0.25 * uB[s].z);
      paint += (Lf - Ln) * 0.8 * uB[s].z;
      // paint does not stop in a clean vector edge: the grain of the surface ragged-edges every letter
      float rough = fbm(pl * 230.0 + Lf * 3.0);
      float thr = 0.5 + (rough - 0.5) * 0.9 * uB[s].z;
      float edge = smoothstep(thr - 0.22, thr + 0.22, cov);
      float a = edge * vis * uOn[s] * worn * wipe * 0.97;
      col = mix(col, paint, clamp(a, 0.0, 1.0));
    }
  }
  o = vec4(col, 1.0);
}`;

function compile(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader {
  const s = gl.createShader(type)!;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error("world shader: " + gl.getShaderInfoLog(s));
  return s;
}

const smooth = (a: number, b: number, v: number) => { const t = clamp((v - a) / Math.max(b - a, 1e-9)); return t * t * (3 - 2 * t); };

function inv3(m: number[]): number[] | null {
  const [a, b, c, d, e, f, g, h, i] = m;
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C;
  if (Math.abs(det) < 1e-12) return null;
  const k = 1 / det;
  return [A * k, -(b * i - c * h) * k, (b * f - c * e) * k, B * k, (a * i - c * g) * k, -(a * f - c * d) * k, C * k, -(a * h - b * g) * k, (a * e - b * d) * k];
}

interface Live {
  cfg: TextCfg; step: number; at: [number, number]; lay: Layout; cell: { x: number; y: number; w: number; h: number };
  enabled: boolean; caption: HTMLElement | null; rgb: [number, number, number];
}

export default async function world(cfg: Cfg, ctx: PlayerContext): Promise<Player | null> {
  const wc = cfg.world;
  if (!wc || !wc.texts.length || reducedMotion) return null;
  const canvas = document.createElement("canvas");
  const gl = canvas.getContext("webgl2", { alpha: false, antialias: false, powerPreference: "high-performance" });
  if (!gl) return null;

  const mobile = isMobile();
  const film = makeVideo();
  const atlasV = wc.atlas ? makeVideo() : null;
  const videos = atlasV ? [film, atlasV] : [film];
  const got = [0, 0];
  const report = () => ctx.progress(0.95 * (got[0] * 0.75 + got[1] * 0.25));
  await Promise.all([
    loadVideo(film, mobile && cfg.videoMobile ? cfg.videoMobile : cfg.video, (f) => { got[0] = f; report(); }),
    atlasV && wc.atlas ? loadVideo(atlasV, mobile && wc.atlas.mobile ? wc.atlas.mobile : wc.atlas.video, (f) => { got[1] = f; report(); }) : Promise.resolve(),
  ]);
  if (videos.some((v) => v.readyState < 2)) return null;
  const fps = wc.fps || 24;
  const duration = Math.min(...videos.map((v) => v.duration || 0));
  const frames = Math.max(1, Math.min(wc.frames, Math.round(duration * fps)));

  // ---- the type: the site's fonts, laid out and drawn into one atlas
  try { await document.fonts.ready; } catch { /* ignore */ }
  const st: WorldStyle = probeStyle(ctx.section);
  try { await document.fonts.load(`${st.weight} 64px ${st.family}`); await document.fonts.load(`italic ${st.weight} 64px ${st.family}`); } catch { /* ignore */ }
  const w0 = film.videoWidth || 1920, h0 = film.videoHeight || 1080;
  const scale = Math.min(1, (mobile ? 1280 : 1920) / w0);
  canvas.width = Math.round(w0 * scale); canvas.height = Math.round(h0 * scale);

  const live: Live[] = [];
  const captions = [...ctx.section.querySelectorAll<HTMLElement>(".ss-caption[data-world]")];
  for (const t of wc.texts) {
    const step = ctx.data.steps[t.i];
    if (!step || !step.at) continue;
    const s = t.style, weight = s.weight ?? st.weight;
    const hMax = (t.quad ? 0.6 : 0.3) * t.plane[1];
    const lay = layout(step.title, st, { size: t.box[2], hMax, lines: s.lines ?? undefined, caps: s.caps, track: s.track, weight, align: s.align });
    live.push({ cfg: t, step: t.i, at: step.at, lay, cell: { x: 0, y: 0, w: 0, h: 0 }, enabled: true, rgb: [1, 1, 1],
               caption: captions.find((c) => c.dataset.world === String(t.i)) || null });
  }
  if (!live.length) return null;
  const colorOf = (L: Live, em: boolean): string => {
    const s = L.cfg.style, tone = L.cfg.tone ?? 0.5;
    let base: string;
    if (s.color === "ink") base = st.ink; else if (s.color === "paper") base = st.paper; else if (s.color === "accent") base = st.accent;
    else if (/^#|^rgb/i.test(s.color)) base = s.color;
    else base = inkFor(tone, st);
    if (!em || s.color !== "auto") return base;
    return contrastWith(st.emColor, tone, st);
  };
  const raster = rasterize(live.map((L) => {
    const px = L.lay.wPlane * (L.cfg.ppp ?? 1) * canvas.width * 1.2;
    return { layout: L.lay, px: Math.min(2600, Math.max(256, px)), colors: (em: boolean) => colorOf(L, em), weight: L.cfg.style.weight ?? st.weight,
             track: L.cfg.style.track, caps: L.cfg.style.caps, align: L.cfg.style.align, st };
  }));
  live.forEach((L, k) => { L.cell = raster.cells[k]; });

  // ---- program
  let prog: WebGLProgram;
  try {
    prog = gl.createProgram()!;
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) || "link failed");
  } catch (err) {
    console.warn("[scroll-studio] world: shader failed, playing the plain film", err);
    return null;
  }
  gl.useProgram(prog);
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "aPos");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

  const tex = (unit: number, mip: boolean) => {
    const t = gl.createTexture()!;
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, mip ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return t;
  };
  const tFilm = tex(0, true), tAtlas = tex(1, false), tText = tex(2, true);
  const U = (n: string) => gl.getUniformLocation(prog, n);
  gl.uniform1i(U("uFilm"), 0); gl.uniform1i(U("uAtlas"), 1); gl.uniform1i(U("uText"), 2);
  // the type atlas, premultiplied so its mip levels blend correctly
  gl.activeTexture(gl.TEXTURE2);
  gl.bindTexture(gl.TEXTURE_2D, tText);
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, raster.canvas);
  gl.generateMipmap(gl.TEXTURE_2D);
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
  const a = wc.atlas;
  const tile = a ? a.tile : [960, 544];
  gl.uniform2f(U("uGrid"), a?.cols ?? 1, a?.rows ?? 1);
  gl.uniform2f(U("uInset"), 0.5 / tile[0] * (mobile ? 2 : 1), 0.5 / tile[1] * (mobile ? 2 : 1));
  gl.uniform2f(U("uTexel"), 1.5 / tile[0] / (mobile ? 0.5 : 1), 1.5 / tile[1] / (mobile ? 0.5 : 1));
  gl.viewport(0, 0, canvas.width, canvas.height);
  ctx.visual.appendChild(canvas);

  const slotOf = (name: string): [number, number] => {
    const k = Math.max(0, a?.slots.indexOf(name) ?? 0), cols = a?.cols ?? 1;
    return [k % cols, Math.floor(k / cols)];
  };
  const u = {
    on: U("uOn[0]"), inn: U("uIn[0]"), kind: U("uKind[0]"), m: U("uM[0]"), box: U("uBox[0]"), cell: U("uCell[0]"),
    A: U("uA[0]"), B: U("uB[0]"), slot: U("uSlot[0]"),
  };
  const arr = {
    on: new Float32Array(N), inn: new Float32Array(N), kind: new Int32Array(N), m: new Float32Array(9 * N), box: new Float32Array(4 * N),
    cell: new Float32Array(4 * N), A: new Float32Array(4 * N), B: new Float32Array(4 * N), slot: new Float32Array(2 * N),
  };

  // ---- which titles fit the screen: one that would be cropped off a narrow screen stays an ordinary caption
  const FILM_ASPECT = w0 / h0;
  function fits() {
    const r = ctx.visual.getBoundingClientRect();
    const va = Math.max(0.1, r.width / Math.max(1, r.height));
    const vx = va < FILM_ASPECT ? va / FILM_ASPECT : 1, vy = va > FILM_ASPECT ? FILM_ASPECT / va : 1;
    const x0 = (1 - vx) / 2 + 0.01, x1 = 1 - (1 - vx) / 2 - 0.01, y0 = (1 - vy) / 2 + 0.01, y1 = 1 - (1 - vy) / 2 - 0.01;
    const shown = va < FILM_ASPECT ? r.height * FILM_ASPECT : r.width;      // css px across the whole film frame
    for (const L of live) {
      const t = L.cfg;
      let ok = true;
      for (const f of [t.anchor]) {          // the composed position: later the world moves it, and it may leave the screen
        const M = t.m[Math.min(t.m.length - 1, Math.max(0, f - t.f0))];
        const Mi = inv3(M);
        if (!Mi) { ok = false; break; }
        const [cx, cy] = [t.box[0], t.box[1]], hw = L.lay.wPlane / 2, hh = L.lay.hPlane / 2;
        for (const [px, py] of [[cx - hw, cy - hh], [cx + hw, cy - hh], [cx + hw, cy + hh], [cx - hw, cy + hh]]) {
          const wv = Mi[6] * px + Mi[7] * py + Mi[8];
          const sx = (Mi[0] * px + Mi[1] * py + Mi[2]) / wv, sy = (Mi[3] * px + Mi[4] * py + Mi[5]) / wv;
          if (!(sx > x0 && sx < x1 && sy > y0 && sy < y1)) ok = false;
        }
      }
      if (L.lay.fs * (t.ppp ?? 1) * shown < 22) ok = false;       // too small to read: the headline's size in css px
      L.enabled = ok && !reducedMotion;
      L.caption?.classList.toggle("ss-world-on", L.enabled);
    }
  }
  fits();
  const onResize = () => fits();
  const debug = ((window as any).__ssWorld ||= {}) as Record<string, any>;
  debug.live = live; debug.fits = fits;

  // ---- drawing
  let p = 0, fi = 0, lastKey = "";
  function fill(): string {
    let k = 0;
    const key: string[] = [String(fi)];
    arr.on.fill(0);
    for (const L of live) {
      if (k >= N || !L.enabled) continue;
      const t = L.cfg;
      const [a0, b0] = L.at;
      const inn = clamp((p - a0) / 0.07);
      const on = smooth(a0, a0 + 0.02, p) * (1 - smooth(b0 - 0.025, b0, p));
      if (on < 0.002 || fi < t.f0 || fi > t.f1) continue;
      const j = fi - t.f0;
      const conf = t.c[Math.min(t.c.length - 1, j)];
      const M = t.m[Math.min(t.m.length - 1, j)];
      // column-major for GL
      const o9 = k * 9;
      arr.m.set([M[0], M[3], M[6], M[1], M[4], M[7], M[2], M[5], M[8]], o9);
      const colCount = t.kind === "surface" ? smooth(0.1, 0.5, conf) : 1;
      arr.on[k] = on * colCount;
      arr.inn[k] = inn;
      arr.kind[k] = KIND[t.kind];
      arr.box.set([t.box[0], t.box[1], L.lay.wPlane, L.lay.hPlane], k * 4);
      arr.cell.set([L.cell.x, L.cell.y, L.cell.w, L.cell.h], k * 4);
      const blurPx = t.blur ?? (t.kind === "surface" ? 0.8 : 0);
      const texPerPx = (L.cell.w * raster.canvas.width) / Math.max(1, L.lay.wPlane * (t.ppp ?? 1) * (1 + 2 * PAD) * canvas.width);
      const lod = Math.log2(Math.max(1, 1 + blurPx * (canvas.width / 1920) * texPerPx));
      arr.A.set([t.depth ?? 0, t.soft ?? 0.04, t.style.haze, lod], k * 4);
      arr.B.set([t.style.fog, t.style.wear, t.style.relief, t.tone ?? 0.5], k * 4);
      arr.slot.set(slotOf(t.slot), k * 2);
      key.push(`${k}:${arr.on[k].toFixed(3)}:${inn.toFixed(2)}`);
      k++;
    }
    return key.join("|");
  }
  const bind = () => {
    gl!.uniform1fv(u.on, arr.on); gl!.uniform1fv(u.inn, arr.inn); gl!.uniform1iv(u.kind, arr.kind);
    gl!.uniformMatrix3fv(u.m, false, arr.m); gl!.uniform4fv(u.box, arr.box); gl!.uniform4fv(u.cell, arr.cell);
    gl!.uniform4fv(u.A, arr.A); gl!.uniform4fv(u.B, arr.B); gl!.uniform2fv(u.slot, arr.slot);
  };
  function upload() {
    gl!.activeTexture(gl!.TEXTURE0);
    gl!.bindTexture(gl!.TEXTURE_2D, tFilm);
    gl!.texImage2D(gl!.TEXTURE_2D, 0, gl!.RGBA, gl!.RGBA, gl!.UNSIGNED_BYTE, film);
    gl!.generateMipmap(gl!.TEXTURE_2D);
    if (atlasV) {
      gl!.activeTexture(gl!.TEXTURE1);
      gl!.bindTexture(gl!.TEXTURE_2D, tAtlas);
      gl!.texImage2D(gl!.TEXTURE_2D, 0, gl!.RGBA, gl!.RGBA, gl!.UNSIGNED_BYTE, atlasV);
    }
  }
  function draw() {
    lastKey = fill();
    bind();
    gl!.drawArrays(gl!.TRIANGLES, 0, 3);
  }
  const seeker = new PairedSeeker(videos, fps, (f) => {
    fi = f; upload(); draw();
    debug.frame = f; debug.times = videos.map((v) => v.currentTime);
    debug.onDraw?.(f);
  });
  seeker.seek(0);
  await new Promise<void>((resolve) => { const w = () => (seeker.busy ? requestAnimationFrame(w) : resolve()); w(); });
  addEventListener("touchstart", () => { videos.forEach((v) => v.play().then(() => v.pause()).catch(() => {})); }, { once: true, passive: true });

  // the plain captions of titles that are drawn in the world stay hidden only while the world is on
  ctx.section.classList.add("ss-world");
  let current = 0;
  return {
    resize() { onResize(); },
    update(s) {
      p = s.p;
      const target = s.p * (frames - 1) / fps;
      current += (target - current) * follow;
      const want = clamp(Math.round(current * fps), 0, frames - 1);
      debug.p = p;
      if (want !== seeker.shown && !seeker.busy) seeker.seek(want);
      else if (!seeker.busy) {
        const k = fill();
        if (k !== lastKey) { bind(); gl!.drawArrays(gl!.TRIANGLES, 0, 3); lastKey = k; }
      }
    },
  };
}
