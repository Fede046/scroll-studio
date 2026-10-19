/**
 * Mesher: builds a whole diorama as a few big meshes. Every prop is drawn with box / cylinder / sphere / roof
 * primitives into buckets (main, glass, emit); positions are baked to world space, vertex colours carry the paint and a
 * cheap baked ambient occlusion (darker near the ground), and two attributes (aPat, aPar) pick a procedural surface
 * (roof tiles, planks, brick, foliage...) that the material draws from world position, so nothing needs a texture.
 */
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

export const PAT = { none: 0, tiles: 1, plaster: 2, planks: 3, deck: 4, foliage: 5, brick: 6, ribs: 7, stripes: 8, metal: 9, sand: 10 } as const;
export type BucketName = "main" | "glass" | "emit";
export type ColorIn = string | number | THREE.Color;
export interface Opts { pat?: number; par?: number; ao?: boolean; flat?: boolean }

class Bucket {
  pos: number[] = []; nor: number[] = []; col: number[] = []; pat: number[] = []; par: number[] = [];
  get count() { return this.pos.length / 3; }
  geometry(): THREE.BufferGeometry | null {
    if (!this.pos.length) return null;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute("normal", new THREE.Float32BufferAttribute(this.nor, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(this.col, 3));
    g.setAttribute("aPat", new THREE.Float32BufferAttribute(this.pat, 1));
    g.setAttribute("aPar", new THREE.Float32BufferAttribute(this.par, 1));
    g.computeBoundingSphere(); g.computeBoundingBox();
    return g;
  }
}

const _c = new THREE.Color();
const _v = new THREE.Vector3(), _n = new THREE.Vector3();
const geoCache = new Map<string, THREE.BufferGeometry>();
function cached(key: string, make: () => THREE.BufferGeometry) {
  let g = geoCache.get(key);
  if (!g) { g = make(); geoCache.set(key, g); }
  return g;
}
const q = (v: number) => Math.round(v * 1000) / 1000;

export class Mesher {
  buckets: Record<BucketName, Bucket> = { main: new Bucket(), glass: new Bucket(), emit: new Bucket() };
  cur: Bucket = this.buckets.main;
  m = new THREE.Matrix4();
  private nm = new THREE.Matrix3();
  private stack: THREE.Matrix4[] = [];
  baseY = 0;
  aoOn = true;
  aoHeight = 1.3;

  use(b: BucketName) { this.cur = this.buckets[b]; return this; }
  reset() { this.m.identity(); this.stack.length = 0; this.cur = this.buckets.main; return this; }
  begin(x: number, y: number, z: number, yaw = 0, s = 1) {
    this.reset();
    this.m.makeTranslation(x, y, z).multiply(new THREE.Matrix4().makeRotationY(yaw)).multiply(new THREE.Matrix4().makeScale(s, s, s));
    this.baseY = y;
    return this;
  }
  push() { this.stack.push(this.m.clone()); return this; }
  pop() { this.m.copy(this.stack.pop()!); return this; }
  at(x: number, y: number, z: number) { this.m.multiply(new THREE.Matrix4().makeTranslation(x, y, z)); return this; }
  yaw(a: number) { this.m.multiply(new THREE.Matrix4().makeRotationY(a)); return this; }
  pitch(a: number) { this.m.multiply(new THREE.Matrix4().makeRotationX(a)); return this; }
  roll(a: number) { this.m.multiply(new THREE.Matrix4().makeRotationZ(a)); return this; }
  scale(x: number, y = x, z = x) { this.m.multiply(new THREE.Matrix4().makeScale(x, y, z)); return this; }
  /** run fn inside a pushed transform */
  local(x: number, y: number, z: number, yaw: number, fn: () => void) {
    this.push(); this.at(x, y, z); if (yaw) this.yaw(yaw); fn(); this.pop();
  }

  // ------------------------------------------------------------ low level
  add(g: THREE.BufferGeometry, color: ColorIn, o: Opts = {}) {
    const b = this.cur;
    _c.set(color as any);
    const pa = g.getAttribute("position"), na = g.getAttribute("normal");
    const idx = g.index;
    this.nm.getNormalMatrix(this.m);
    const n = idx ? idx.count : pa.count;
    const pat = o.pat ?? 0, par = o.par ?? 0;
    for (let k = 0; k < n; k++) {
      const i = idx ? idx.getX(k) : k;
      _v.fromBufferAttribute(pa, i).applyMatrix4(this.m);
      _n.fromBufferAttribute(na, i).applyMatrix3(this.nm).normalize();
      b.pos.push(_v.x, _v.y, _v.z);
      b.nor.push(_n.x, _n.y, _n.z);
      let f = 1;
      if (this.aoOn && o.ao !== false && this.cur !== this.buckets.emit) {
        const t = Math.min(1, Math.max(0, (_v.y - this.baseY) / this.aoHeight));
        f = 0.74 + 0.26 * (t * t * (3 - 2 * t));
        if (_n.y < -0.5) f *= 0.72;
      }
      b.col.push(_c.r * f, _c.g * f, _c.b * f);
      b.pat.push(pat); b.par.push(par);
    }
    return this;
  }

  /** a flat triangle (normal from the winding) */
  tri(a: THREE.Vector3Like, bb: THREE.Vector3Like, c: THREE.Vector3Like, color: ColorIn, o: Opts = {}) {
    const g = new THREE.BufferGeometry();
    const p = new Float32Array([a.x, a.y, a.z, bb.x, bb.y, bb.z, c.x, c.y, c.z]);
    const e1 = new THREE.Vector3(bb.x - a.x, bb.y - a.y, bb.z - a.z), e2 = new THREE.Vector3(c.x - a.x, c.y - a.y, c.z - a.z);
    const n = e1.cross(e2).normalize();
    g.setAttribute("position", new THREE.BufferAttribute(p, 3));
    g.setAttribute("normal", new THREE.BufferAttribute(new Float32Array([n.x, n.y, n.z, n.x, n.y, n.z, n.x, n.y, n.z]), 3));
    this.add(g, color, o);
    g.dispose();
    return this;
  }
  quad(a: THREE.Vector3Like, b: THREE.Vector3Like, c: THREE.Vector3Like, d: THREE.Vector3Like, color: ColorIn, o: Opts = {}) {
    this.tri(a, b, c, color, o); this.tri(a, c, d, color, o);
    return this;
  }

  // ------------------------------------------------------------ primitives (base-centred: x, y, z is the middle of the bottom)
  box(w: number, h: number, d: number, x: number, y: number, z: number, color: ColorIn, o: Opts = {}) {
    const g = cached(`b${q(w)},${q(h)},${q(d)}`, () => new THREE.BoxGeometry(w, h, d));
    this.push(); this.at(x, y + h / 2, z); this.add(g, color, o); this.pop();
    return this;
  }
  /** rounded box: toy edges that catch the light */
  rbox(w: number, h: number, d: number, x: number, y: number, z: number, color: ColorIn, r = 0, o: Opts = {}) {
    const rr = Math.min(r || Math.min(w, h, d) * 0.14, Math.min(w, h, d) * 0.48);
    const g = cached(`r${q(w)},${q(h)},${q(d)},${q(rr)}`, () => new RoundedBoxGeometry(w, h, d, 2, rr));
    this.push(); this.at(x, y + h / 2, z); this.add(g, color, o); this.pop();
    return this;
  }
  cyl(rTop: number, rBot: number, h: number, x: number, y: number, z: number, color: ColorIn, seg = 16, o: Opts = {}) {
    const g = cached(`c${q(rTop)},${q(rBot)},${q(h)},${seg}`, () => new THREE.CylinderGeometry(rTop, rBot, h, seg, 1));
    this.push(); this.at(x, y + h / 2, z); this.add(g, color, o); this.pop();
    return this;
  }
  cone(r: number, h: number, x: number, y: number, z: number, color: ColorIn, seg = 14, o: Opts = {}) {
    return this.cyl(0.0001, r, h, x, y, z, color, seg, o);
  }
  /** sphere centred at y */
  sphere(r: number, x: number, y: number, z: number, color: ColorIn, seg = 14, o: Opts = {}) {
    const g = cached(`s${q(r)},${seg}`, () => new THREE.SphereGeometry(r, seg, Math.max(6, seg >> 1)));
    this.push(); this.at(x, y, z); this.add(g, color, o); this.pop();
    return this;
  }
  /** a faceted blob (rocks, bushes, tree crowns) */
  ico(r: number, x: number, y: number, z: number, color: ColorIn, detail = 1, squash = 1, o: Opts = {}) {
    const g = cached(`i${q(r)},${detail}`, () => {
      const ig = new THREE.IcosahedronGeometry(r, detail).toNonIndexed();
      ig.computeVertexNormals();
      return ig;
    });
    this.push(); this.at(x, y, z); if (squash !== 1) this.scale(1, squash, 1); this.add(g, color, o); this.pop();
    return this;
  }
  torus(R: number, r: number, x: number, y: number, z: number, color: ColorIn, rotX = Math.PI / 2, seg = 20, o: Opts = {}) {
    const g = cached(`t${q(R)},${q(r)},${seg}`, () => new THREE.TorusGeometry(R, r, 8, seg));
    this.push(); this.at(x, y, z); this.pitch(rotX); this.add(g, color, o); this.pop();
    return this;
  }
  /** a gable roof over a w x d footprint (ridge along z), eaves at y, ridge `h` above; overhang `ov`; gable ends in `endColor` */
  gable(w: number, d: number, h: number, ov: number, x: number, y: number, z: number, color: ColorIn, endColor?: ColorIn, o: Opts = {}) {
    const hw = w / 2 + ov, hd = d / 2 + ov;
    const T = (px: number, py: number, pz: number) => new THREE.Vector3(px, py, pz);
    const P = (px: number, py: number, pz: number) => {
      const v = T(px, py, pz).applyMatrix4(new THREE.Matrix4().makeTranslation(x, y, z));
      return v;
    };
    const ridge = h;
    const eave = -h * (ov / (w / 2));
    const a = P(-hw, eave, hd), b = P(0, ridge, hd), c = P(0, ridge, -hd), dd = P(-hw, eave, -hd);
    const e = P(hw, eave, hd), f = P(hw, eave, -hd);
    this.quad(a, b, c, dd, color, { pat: PAT.tiles, ...o });
    this.quad(e, f, c, b, color, { pat: PAT.tiles, ...o });
    const under = new THREE.Color(color as any).multiplyScalar(0.7);
    this.quad(a, dd, f, e, under, { ao: false });
    const ec = endColor ?? color;
    this.tri(P(-w / 2, 0, d / 2), P(w / 2, 0, d / 2), P(0, h, d / 2), ec, { pat: PAT.plaster });
    this.tri(P(w / 2, 0, -d / 2), P(-w / 2, 0, -d / 2), P(0, h, -d / 2), ec, { pat: PAT.plaster });
    return this;
  }
  /** a pyramid / hip roof (apex over the middle) */
  hip(w: number, d: number, h: number, ov: number, x: number, y: number, z: number, color: ColorIn, o: Opts = {}) {
    const hw = w / 2 + ov, hd = d / 2 + ov;
    const P = (px: number, py: number, pz: number) => new THREE.Vector3(px + x, py + y, pz + z);
    const ap = P(0, h, 0);
    const c1 = P(-hw, 0, hd), c2 = P(hw, 0, hd), c3 = P(hw, 0, -hd), c4 = P(-hw, 0, -hd);
    this.tri(c1, c2, ap, color, { pat: PAT.tiles, ...o }); this.tri(c2, c3, ap, color, { pat: PAT.tiles, ...o });
    this.tri(c3, c4, ap, color, { pat: PAT.tiles, ...o }); this.tri(c4, c1, ap, color, { pat: PAT.tiles, ...o });
    return this;
  }

  // ------------------------------------------------------------ output
  geometries() {
    return { main: this.buckets.main.geometry(), glass: this.buckets.glass.geometry(), emit: this.buckets.emit.geometry() };
  }
  get triangles() { return (this.buckets.main.count + this.buckets.glass.count + this.buckets.emit.count) / 3; }
}

export function shade(hex: string, k: number): string {
  const c = new THREE.Color(hex);
  c.multiplyScalar(k);
  return "#" + c.getHexString();
}
export function hash(n: number) { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); }
