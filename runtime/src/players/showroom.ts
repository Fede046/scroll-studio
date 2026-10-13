/**
 * showroom: the real product, live. three.js renders the product's normalised GLB (y up, metres, base at the
 * origin, front towards +z) with an environment light, a key light and a soft shadow on an invisible floor.
 * Scroll progress runs through `keys` ({t, yaw, pitch, explode, zoom}); explodable parts carry their own offsets
 * (node extras ss_explode, metres) from the engine, so the live explode matches the rendered stills.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import type { PlayerFactory } from "../lib/types";
import { cssVar, follow, isMobile } from "../lib/util";

type Key = { t: number; yaw?: number; pitch?: number; explode?: number; zoom?: number };
const FIELDS = ["yaw", "pitch", "explode", "zoom"] as const;
const DEFAULTS: Record<string, number> = { yaw: -35, pitch: 18, explode: 0, zoom: 1 };

function at(keys: Key[], t: number): Record<string, number> {
  const val = (k: Key, f: string) => ((k as any)[f] ?? DEFAULTS[f]) as number;
  const out: Record<string, number> = {};
  if (!keys.length) return { ...DEFAULTS };
  if (t <= keys[0].t) { FIELDS.forEach((f) => (out[f] = val(keys[0], f))); return out; }
  for (let i = 1; i < keys.length; i++) {
    const a = keys[i - 1], b = keys[i];
    if (t <= b.t) {
      let u = (t - a.t) / Math.max(b.t - a.t, 1e-6);
      u = u * u * (3 - 2 * u);
      FIELDS.forEach((f) => (out[f] = val(a, f) + (val(b, f) - val(a, f)) * u));
      return out;
    }
  }
  FIELDS.forEach((f) => (out[f] = val(keys[keys.length - 1], f)));
  return out;
}

const LIGHTING: Record<string, { env: number; key: number; rim: number }> = {
  studio: { env: 1.0, key: 2.2, rim: 0.8 },
  soft: { env: 1.25, key: 0.9, rim: 0.3 },
  contrast: { env: 0.45, key: 3.4, rim: 2.2 },
};

const factory: PlayerFactory = async (cfg, ctx) => {
  const canvas = document.createElement("canvas");
  ctx.visual.appendChild(canvas);
  const transparent = cfg.background === "transparent";
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: transparent, powerPreference: "high-performance", preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  if (!transparent) renderer.setClearColor(new THREE.Color(cfg.background || cssVar("--bg") || "#111"), 1);
  else renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.NeutralToneMapping;   // Khronos PBR Neutral: product colours stay true
  renderer.toneMappingExposure = cfg.exposure ?? 1;
  renderer.shadowMap.enabled = cfg.shadow !== false;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  const L = LIGHTING[cfg.lighting] || LIGHTING.studio;
  scene.environmentIntensity = L.env;

  const gltf = await new GLTFLoader().loadAsync(cfg.model, (e) => { if (e.total) ctx.progress(e.loaded / e.total * 0.9); });
  const model = gltf.scene;
  scene.add(model);
  model.updateMatrixWorld(true);
  model.traverse((o: any) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });

  // explodable parts: their world offset turned into each parent's local space once
  const parts: { o: THREE.Object3D; base: THREE.Vector3; delta: THREE.Vector3 }[] = [];
  model.traverse((o) => {
    const off = o.userData?.ss_explode;
    if (!Array.isArray(off) || !o.parent) return;
    const wp = o.getWorldPosition(new THREE.Vector3());
    const p0 = o.parent.worldToLocal(wp.clone());
    const p1 = o.parent.worldToLocal(wp.clone().add(new THREE.Vector3(off[0], off[1], off[2])));
    parts.push({ o, base: o.position.clone(), delta: p1.sub(p0) });
  });

  const box = new THREE.Box3().setFromObject(model);
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const R = Math.max(sphere.radius, 1e-4), C = sphere.center.clone();

  // lights scale with the product, so a watch and a laptop are lit alike
  const key = new THREE.DirectionalLight(0xffffff, L.key);
  key.castShadow = cfg.shadow !== false;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.radius = 6;
  key.shadow.bias = -0.0004;
  const sc = key.shadow.camera as THREE.OrthographicCamera;
  sc.left = sc.bottom = -R * 2.2; sc.right = sc.top = R * 2.2; sc.near = R * 0.1; sc.far = R * 12;
  scene.add(key, key.target);
  const rim = new THREE.DirectionalLight(0xffffff, L.rim);
  scene.add(rim, rim.target);
  if (cfg.shadow !== false) {
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(R * 12, R * 12), new THREE.ShadowMaterial({ opacity: 0.22 }));
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = box.min.y - R * 0.002;
    floor.receiveShadow = true;
    scene.add(floor);
  }

  const camera = new THREE.PerspectiveCamera(30, 1, R * 0.02, R * 60);
  const side = ctx.section.className.includes("ss-side-left") ? -1 : 1;
  let fitDist = 1;
  function resize() {
    const w = canvas.clientWidth || 1, h = canvas.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    const shift = !isMobile() ? (cfg.shift || 0) * w : 0;
    camera.setViewOffset(w, h, -shift, 0, w, h);
    camera.updateProjectionMatrix();
    // the bounding sphere fills ~90% of the shorter side: the silhouette lands near two thirds of the frame
    const vfov = THREE.MathUtils.degToRad(camera.fov);
    const fov = Math.min(vfov, 2 * Math.atan(Math.tan(vfov / 2) * camera.aspect));
    fitDist = R / Math.sin(fov / 2) / 0.9;
    if (isMobile()) fitDist *= 1.05;
    last = "";
  }
  resize();

  const cur = at(cfg.keys || [], 0);
  let last = "";
  const dir = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
  function frame(t: number, mx: number, my: number) {
    const yaw = THREE.MathUtils.degToRad(cur.yaw + mx * 8 + (cfg.spin || 0) * t);
    const pitch = THREE.MathUtils.degToRad(Math.max(-10, Math.min(89, cur.pitch - my * 5)));
    const ex = cur.explode;
    const sig = [yaw, pitch, ex, cur.zoom].map((v) => v.toFixed(4)).join();
    if (sig === last) return;
    last = sig;
    for (const p of parts) p.o.position.copy(p.base).addScaledVector(p.delta, ex);
    dir.set(Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), Math.cos(yaw) * Math.cos(pitch));
    const target = C.clone();
    target.y += ex * R * 0.12;                 // parts rise as they explode; keep them centred
    const dist = fitDist * (1 + ex * 0.25) / Math.max(cur.zoom, 0.05);
    camera.position.copy(target).addScaledVector(dir, dist);
    camera.up.copy(up);
    camera.lookAt(target);
    // key from the camera's front-left and above, rim from behind: every angle reads like a product shoot
    const right = new THREE.Vector3().crossVectors(dir, up).normalize();
    key.position.copy(target).addScaledVector(dir, R * 3).addScaledVector(right, R * 2.5).add(new THREE.Vector3(0, R * 4.5, 0));
    key.target.position.copy(target);
    rim.position.copy(target).addScaledVector(dir, -R * 3).addScaledVector(right, -R * 1.5).add(new THREE.Vector3(0, R * 2.5, 0));
    rim.target.position.copy(target);
    renderer.render(scene, camera);
  }
  renderer.compile(scene, camera);
  frame(0, 0, 0);
  ctx.progress(1);

  let mxs = 0, mys = 0;
  return {
    resize,
    update(s) {
      const k = at(cfg.keys || [], s.p);
      for (const f of FIELDS) cur[f] += (k[f] - cur[f]) * follow;
      mxs += (s.mx - mxs) * 0.05; mys += (s.my - mys) * 0.05;
      frame(cfg.spin ? s.t : 0, mxs, mys);
    },
  };
};
export default factory;
