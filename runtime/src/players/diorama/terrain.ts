/**
 * The base the world stands on: a polar-meshed terrain wearing the painted ground, still water over its sunken
 * beds, the cut edge of the diorama (grass lip, soil, stone, with the sea in section where the bay reaches the
 * edge), a wooden plinth, and the table with a soft contact shadow.
 */
import * as THREE from "three";
import type { Plan } from "./types";
import { Mesher } from "./mesher";
import { terrainMaterial, type TerrainUniforms } from "./materials";

export interface Terrain {
  group: THREE.Group;
  heightAt(x: number, z: number): number;
  outline(theta: number): number;
  water: THREE.ShaderMaterial | null;
  floorY: number;
  tableY: number;
  wallMesher: Mesher;
}

const FLOOR_Y = -1.9, PLINTH = 0.6, TABLE_Y = FLOOR_Y - PLINTH;

export function buildTerrain(plan: Plan, ground: THREE.Texture, uni: TerrainUniforms, mobile: boolean): Terrain {
  const R = plan.size / 2, n = plan.grid, S = plan.size;
  const hs = Float32Array.from(plan.heights);
  const heightAt = (x: number, z: number) => {
    const fx = Math.min(n - 1.001, Math.max(0, (x + R) / S * (n - 1)));
    const fz = Math.min(n - 1.001, Math.max(0, (z + R) / S * (n - 1)));
    const j = Math.floor(fx), i = Math.floor(fz), tx = fx - j, tz = fz - i;
    const a = hs[i * n + j] * (1 - tx) + hs[i * n + j + 1] * tx;
    const b = hs[(i + 1) * n + j] * (1 - tx) + hs[(i + 1) * n + j + 1] * tx;
    return a * (1 - tz) + b * tz;
  };
  const outline = (th: number) => {
    if (plan.base === "round") return R;
    const c = Math.abs(Math.cos(th)), s = Math.abs(Math.sin(th));
    return R / Math.pow(Math.pow(c, 8) + Math.pow(s, 8), 1 / 8);
  };
  const group = new THREE.Group();
  const segs = mobile ? 160 : 288, rings = mobile ? 64 : 110;
  const level = plan.water.level;

  // ---- terrain + water share the polar grid
  const nv = (rings + 1) * (segs + 1);
  const pos = new Float32Array(nv * 3), uv = new Float32Array(nv * 2), depth = new Float32Array(nv);
  const wpos = new Float32Array(nv * 3);
  let k = 0;
  for (let i = 0; i <= rings; i++) {
    for (let j = 0; j <= segs; j++, k++) {
      const th = (j % segs) / segs * Math.PI * 2;
      const rho = outline(th) * (i / rings);
      const x = Math.cos(th) * rho, z = Math.sin(th) * rho;
      const h = heightAt(x, z);
      pos.set([x, h, z], k * 3);
      wpos.set([x, level, z], k * 3);
      uv.set([(x + R) / S, (z + R) / S], k * 2);
      depth[k] = Math.max(0, level - h);
    }
  }
  const idx: number[] = [];
  for (let i = 0; i < rings; i++) for (let j = 0; j < segs; j++) {
    const a = i * (segs + 1) + j, b = a + 1, c = a + segs + 1, d = c + 1;
    idx.push(a, c, b, b, c, d);
  }
  const tg = new THREE.BufferGeometry();
  tg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  tg.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  tg.setIndex(idx);
  tg.computeVertexNormals();
  const terrain = new THREE.Mesh(tg, terrainMaterial(ground, S, uni));
  terrain.receiveShadow = true;
  terrain.castShadow = true;
  group.add(terrain);

  let water: THREE.ShaderMaterial | null = null;
  if (plan.water.has) {
    const wg = new THREE.BufferGeometry();
    wg.setAttribute("position", new THREE.BufferAttribute(wpos, 3));
    wg.setAttribute("aDepth", new THREE.BufferAttribute(depth, 1));
    wg.setIndex(idx);
    water = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false,
      uniforms: {
        uTime: uni.uTime, uSun: { value: new THREE.Vector3(0.5, 0.7, 0.4) },
        uShallow: { value: new THREE.Color("#7fdde6") }, uDeep: { value: new THREE.Color("#1f78b0") },
        uSky: { value: new THREE.Color("#cfe9f7") }, uSunCol: { value: new THREE.Color("#fff1d0") },
      },
      vertexShader: /* glsl */ `
        attribute float aDepth; varying float vDepth; varying vec3 vWPos;
        void main(){ vDepth = aDepth; vec4 w = modelMatrix * vec4(position, 1.0); vWPos = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }`,
      fragmentShader: /* glsl */ `
        uniform float uTime; uniform vec3 uSun, uShallow, uDeep, uSky, uSunCol; varying float vDepth; varying vec3 vWPos;
        void main(){
          vec2 q = vWPos.xz;
          float t = uTime;
          float w1 = sin(q.x * 2.3 + t * 1.1) + sin(q.y * 2.9 - t * 0.9) + sin((q.x + q.y) * 1.7 + t * 0.7) + sin((q.x - q.y) * 3.7 - t * 1.3) * 0.6;
          vec2 g = vec2(cos(q.x * 2.3 + t * 1.1) * 2.3 + cos((q.x + q.y) * 1.7 + t * 0.7) * 1.7 + cos((q.x - q.y) * 3.7 - t * 1.3) * 2.2,
                        cos(q.y * 2.9 - t * 0.9) * 2.9 + cos((q.x + q.y) * 1.7 + t * 0.7) * 1.7 - cos((q.x - q.y) * 3.7 - t * 1.3) * 2.2);
          vec3 N = normalize(vec3(-g.x * 0.018, 1.0, -g.y * 0.018));
          vec3 V = normalize(cameraPosition - vWPos);
          float d = vDepth;
          vec3 base = mix(uShallow, uDeep, smoothstep(0.0, 1.0, d));
          float fres = pow(1.0 - max(dot(N, V), 0.0), 3.0);
          vec3 R = reflect(-V, N);
          float glint = pow(max(dot(R, normalize(uSun)), 0.0), 140.0) * 2.5 + pow(max(dot(R, normalize(uSun)), 0.0), 24.0) * 0.12;
          vec3 col = mix(base, uSky, fres * 0.55) + uSunCol * glint;
          col *= 0.96 + 0.05 * w1 * 0.25;
          float foamLine = smoothstep(0.17 + 0.05 * sin(t * 0.8 + q.x * 3.0 + q.y * 2.0), 0.02, d);
          col = mix(col, vec3(1.0), foamLine * 0.8);
          float a = mix(0.62, 0.94, smoothstep(0.0, 0.5, d));
          a = max(a, foamLine);
          gl_FragColor = vec4(col, a);
        }`,
    });
    const wm = new THREE.Mesh(wg, water);
    wm.renderOrder = 2;
    group.add(wm);
  }

  // ---- the cut edge: bands of grass, soil, clay and stone (the sea in section), then the plinth
  const M = new Mesher();
  M.aoOn = false;
  const rings2 = segs;
  const col = { lip: "#7cbb4a", soil: "#8d5f3b", clay: "#6f4630", stone: "#8c8984", sea: "#2c93c9", seaDeep: "#1d6fa6", wood: "#7a5434", woodTop: "#9a7048" };
  const V = (th: number, rho: number, y: number) => new THREE.Vector3(Math.cos(th) * rho, y, Math.sin(th) * rho);
  const band = (th0: number, th1: number, r0: number, r1: number, y0: number, y1: number, color: string) => {
    if (y0 - y1 < 1e-4) return;
    // outer wall quad, facing outwards
    M.quad(V(th0, r0, y1), V(th0, r0, y0), V(th1, r1, y0), V(th1, r1, y1), color, { ao: false });
  };
  for (let j = 0; j < rings2; j++) {
    const th0 = j / rings2 * Math.PI * 2, th1 = (j + 1) / rings2 * Math.PI * 2;
    const r0 = outline(th0), r1 = outline(th1);
    const h0 = heightAt(Math.cos(th0) * r0, Math.sin(th0) * r0), h1 = heightAt(Math.cos(th1) * r1, Math.sin(th1) * r1);
    const sea = Math.min(h0, h1) < level;
    if (sea) {
      band(th0, th1, r0, r1, level, -0.45, col.sea);
      band(th0, th1, r0, r1, -0.45, -1.25, col.seaDeep);
      band(th0, th1, r0, r1, -1.25, FLOOR_Y, col.stone);
    } else {
      const top = Math.max(h0, h1), bot = Math.min(h0, h1);
      band(th0, th1, r0, r1, top, bot - 0.12, col.lip);
      band(th0, th1, r0, r1, bot - 0.12, -0.75, col.soil);
      band(th0, th1, r0, r1, -0.75, -1.25, col.clay);
      band(th0, th1, r0, r1, -1.25, FLOOR_Y, col.stone);
    }
    // the plinth: top ring and its outer wall
    const e = 0.38;
    const pr0 = r0 + e, pr1 = r1 + e;
    M.quad(V(th0, r0, FLOOR_Y), V(th1, r1, FLOOR_Y), V(th1, pr1, FLOOR_Y - 0.08), V(th0, pr0, FLOOR_Y - 0.08), col.woodTop, { ao: false });
    band(th0, th1, pr0, pr1, FLOOR_Y - 0.08, TABLE_Y, col.wood);
  }
  const wg = M.geometries().main!;
  const wallMesh = new THREE.Mesh(wg, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.8, side: THREE.DoubleSide }));
  wallMesh.castShadow = true; wallMesh.receiveShadow = true;
  group.add(wallMesh);

  return { group, heightAt, outline, water, floorY: FLOOR_Y, tableY: TABLE_Y, wallMesher: M };
}

export function buildTable(color: string, tableY: number, rho: number): THREE.Group {
  const g = new THREE.Group();
  const table = new THREE.Mesh(new THREE.PlaneGeometry(600, 600), new THREE.MeshStandardMaterial({ color, roughness: 0.95, metalness: 0 }));
  table.rotation.x = -Math.PI / 2; table.position.y = tableY; table.receiveShadow = true;
  g.add(table);
  // a soft dark halo where the base touches the table
  const c = document.createElement("canvas"); c.width = c.height = 256;
  const x = c.getContext("2d")!;
  const gr = x.createRadialGradient(128, 128, 128 * 0.62, 128, 128, 128);
  gr.addColorStop(0, "rgba(40,28,20,0.5)"); gr.addColorStop(0.55, "rgba(40,28,20,0.16)"); gr.addColorStop(1, "rgba(40,28,20,0)");
  x.fillStyle = gr; x.fillRect(0, 0, 256, 256);
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  const s = rho * 2 + 9;
  const halo = new THREE.Mesh(new THREE.PlaneGeometry(s, s), new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false }));
  halo.rotation.x = -Math.PI / 2; halo.position.y = tableY + 0.01; halo.renderOrder = 1;
  g.add(halo);
  return g;
}
