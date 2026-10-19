/**
 * More of the prop kit: the town's landmarks, the factory floor, the desk and the studio. Same conventions as kit.ts.
 */
import * as THREE from "three";
import { PAT, shade } from "./mesher";
import type { Mesher } from "./mesher";
import type { KitCtx } from "./kit";

type Builder = (c: KitCtx) => void;
const TRIM = "#fbf6ea", DARK = "#3a3f47", STONE = "#bdb6a9", WOOD = "#b98550", WOOD_D = "#8b6038", GLASS = "#a9dff0", STEEL = "#aeb6bf";

/** a lit screen: a panel with a few bars of "content" (emissive, so it glows against the sun) */
function screen(M: Mesher, w: number, h: number, x: number, y: number, z: number, accent: string, seed: number) {
  M.use("emit");
  M.box(w, h, 0.02, x, y, z, "#e9f2ff");
  const rows = Math.max(3, Math.round(h / 0.32));
  for (let i = 0; i < rows; i++) {
    const ww = w * (0.35 + ((i * 37 + seed * 11) % 50) / 100);
    M.box(ww, h / rows * 0.4, 0.025, x - (w - ww) / 2 + 0.06, y + h - (i + 0.8) * (h / rows), z + 0.005, i === 0 ? accent : i % 3 === 0 ? "#9db4d6" : "#c9d6ea");
  }
  M.use("main");
}

// ---------------------------------------------------------------- the town
const clocktower: Builder = (c) => {
  const M = c.M, roof = c.p.c?.[0] ?? "#b0463a";
  M.box(2.2, 0.35, 2.2, 0, 0, 0, "#9c9a95");
  M.box(1.9, 2.6, 1.9, 0, 0.3, 0, "#b8694f", { pat: PAT.brick });
  M.box(1.5, 3.3, 1.5, 0, 2.85, 0, "#efe3c8", { pat: PAT.plaster });
  M.box(1.75, 0.2, 1.75, 0, 2.85, 0, "#9c9a95"); M.box(1.7, 0.18, 1.7, 0, 6.1, 0, "#9c9a95");
  // the clock faces: a disc on each side, hands and tick marks
  for (let i = 0; i < 4; i++) {
    M.push(); M.yaw(i * Math.PI / 2); M.at(0, 4.6, 0.78); M.pitch(Math.PI / 2);
    M.cyl(0.5, 0.5, 0.04, 0, 0, 0, "#fffaf0", 24); M.cyl(0.55, 0.55, 0.03, 0, -0.01, 0, "#c4433a", 24);
    M.pop();
    M.push(); M.yaw(i * Math.PI / 2); M.at(0, 4.6, 0.81);
    M.box(0.05, 0.36, 0.02, 0, 0, 0, DARK); M.push(); M.roll(-1.2); M.box(0.05, 0.28, 0.02, 0, 0, 0, DARK); M.pop();
    M.pop();
  }
  // belfry with arched openings and a pointed roof
  M.box(1.4, 1.1, 1.4, 0, 6.25, 0, "#efe3c8");
  for (let i = 0; i < 4; i++) { M.push(); M.yaw(i * Math.PI / 2); M.use("glass"); M.box(0.5, 0.7, 0.05, 0, 6.35, 0.71, "#2b3a4a"); M.use("main"); M.pop(); }
  M.cone(1.15, 1.9, 0, 7.35, 0, roof, 4, { pat: PAT.tiles });
  M.cyl(0.02, 0.02, 0.9, 0, 9.0, 0, "#2f3a44", 6); M.sphere(0.07, 0, 9.9, 0, "#f2c95a", 8);
  c.part(0, 9.4, 0, (m) => { m.aoOn = false; m.box(0.5, 0.18, 0.02, 0.25, 0, 0, "#d9503a"); }, (o, t) => { o.rotation.y = Math.sin(t * 0.6) * 0.5; });
  // door
  M.box(0.55, 0.9, 0.08, 0, 0.3, 0.98, "#5b3a22", { pat: PAT.planks }); M.box(0.7, 0.07, 0.4, 0, 0.1, 1.15, "#9c9a95");
};
const fountain: Builder = (c) => {
  const M = c.M;
  M.cyl(1.9, 2.0, 0.5, 0, 0, 0, STONE, 24); M.cyl(1.7, 1.7, 0.04, 0, 0.49, 0, STONE, 24);
  M.use("glass"); M.cyl(1.62, 1.62, 0.05, 0, 0.44, 0, "#5fc0dc", 24); M.use("main");
  M.cyl(0.3, 0.38, 1.3, 0, 0.45, 0, STONE, 14); M.cyl(0.95, 0.35, 0.22, 0, 1.55, 0, STONE, 18);
  M.use("glass"); M.cyl(0.85, 0.85, 0.05, 0, 1.74, 0, "#5fc0dc", 18); M.use("main");
  M.cyl(0.12, 0.2, 0.9, 0, 1.7, 0, STONE, 10); M.sphere(0.2, 0, 2.65, 0, STONE, 10);
  // water falling from the upper bowl: little droplets that fall and reset
  const drop = new THREE.Mesh(new THREE.SphereGeometry(0.05, 6, 5), new THREE.MeshBasicMaterial({ color: "#d6f3ff" }));
  const g = new THREE.Group();
  for (let i = 0; i < 10; i++) { const d = drop.clone(); d.userData.ph = i / 10; d.userData.a = i * 0.63; g.add(d); }
  c.add(g, 0, 0, 0, (o, t) => o.children.forEach((d: any) => {
    const u = (t * 0.7 + d.userData.ph) % 1;
    const r = 0.25 + u * 0.8;
    d.position.set(Math.cos(d.userData.a) * r, 2.6 - 4 * u * (1 - u) * -0.6 - u * 0.9 - 0.6 * (1 - Math.pow(1 - u, 2)) * 0, Math.sin(d.userData.a) * r);
    d.position.y = 2.7 - u * u * 2.2;
    d.scale.setScalar(1 - u * 0.3);
  }));
};
const bridge: Builder = (c) => {
  const M = c.M, len = c.p.len ?? 4.2, w = 1.9;
  const seg = 7;
  for (let i = 0; i < seg; i++) {
    const t = i / (seg - 1), z = -len / 2 + t * len, y = 0.25 + 0.55 * Math.sin(t * Math.PI);
    M.box(w, 0.22, len / seg + 0.05, 0, y - 0.1, z, "#8a8e94", { pat: PAT.sand });
    for (const sx of [-w / 2 + 0.07, w / 2 - 0.07]) M.rbox(0.14, 0.38, len / seg + 0.04, sx, y + 0.1, z, STONE, 0.03);
    M.box(w - 0.1, 0.05, len / seg + 0.05, 0, y + 0.01, z, "#5e6268");
  }
  for (const sx of [-w / 2 + 0.07, w / 2 - 0.07]) for (const z of [-len / 2, len / 2]) M.cyl(0.12, 0.14, 0.7, sx, 0.15, z, "#9c9a95", 8);
};

// ---------------------------------------------------------------- the factory floor
const tank: Builder = (c) => {
  const M = c.M, col = c.p.c?.[0] ?? "#e9edf1";
  M.cyl(1.9, 1.95, 0.25, 0, 0, 0, "#7d838b", 22);
  M.cyl(1.7, 1.7, 3.6, 0, 0.25, 0, col, 28, { pat: PAT.metal });
  M.cyl(1.72, 1.72, 0.1, 0, 1.3, 0, "#9aa2ab", 28); M.cyl(1.72, 1.72, 0.1, 0, 2.5, 0, "#9aa2ab", 28);
  M.sphere(1.7, 0, 3.85, 0, col, 24, { pat: PAT.metal });
  // ladder, pipes and a stripe in the accent colour
  M.cyl(1.72, 1.72, 0.35, 0, 1.75, 0, shade(c.pick(c.palette, 3), 1.0), 28);
  for (let i = 0; i < 12; i++) M.box(0.5, 0.04, 0.04, 1.45, 0.5 + i * 0.28, 0.9, DARK);
  M.box(0.04, 3.4, 0.04, 1.2, 0.4, 0.9, DARK); M.box(0.04, 3.4, 0.04, 1.7, 0.4, 0.9, DARK);
  M.cyl(0.14, 0.14, 1.6, -1.9, 0.0, 0, "#8d96a0", 10); M.pitch(0);
  M.box(1.6, 0.22, 0.22, -1.1, 1.55, 0.4, "#8d96a0"); M.cyl(0.11, 0.11, 1.5, -1.95, 0.05, 0.4, "#8d96a0", 10);
};
const silo: Builder = (c) => {
  const M = c.M, col = c.p.c?.[0] ?? "#d6dbe0";
  M.cyl(1.55, 1.6, 0.2, 0, 0, 0, "#7d838b", 22);
  for (let i = 0; i < 5; i++) M.cyl(1.4, 1.4, 1.05, 0, 0.2 + i * 1.04, 0, i % 2 ? shade(col, 0.95) : col, 26, { pat: PAT.ribs });
  M.cone(1.45, 1.1, 0, 5.4, 0, "#b9c0c8", 26, { pat: PAT.metal });
  M.cyl(0.18, 0.18, 0.4, 0, 6.4, 0, "#7d838b", 10);
  M.box(0.06, 5.6, 0.06, 1.38, 0.3, 0.3, DARK); M.box(0.06, 5.6, 0.06, 1.38, 0.3, -0.3, DARK);
  for (let i = 0; i < 18; i++) M.box(0.05, 0.04, 0.6, 1.4, 0.5 + i * 0.3, 0, DARK);
};
const chimney: Builder = (c) => {
  const M = c.M;
  M.box(1.8, 0.4, 1.8, 0, 0, 0, "#8d96a0");
  M.cyl(0.62, 0.9, 8.4, 0, 0.35, 0, "#b0614a", 18, { pat: PAT.brick });
  M.cyl(0.66, 0.66, 0.5, 0, 8.4, 0, "#f4efe4", 18); M.cyl(0.7, 0.7, 0.35, 0, 7.4, 0, "#d9503a", 18); M.cyl(0.68, 0.68, 0.35, 0, 5.4, 0, "#d9503a", 18);
  M.cyl(0.6, 0.6, 0.12, 0, 8.9, 0, "#2f3a44", 18);
  const mat = new THREE.MeshStandardMaterial({ color: "#f6f4ef", roughness: 1, transparent: true, opacity: 0.8 });
  const g = new THREE.Group();
  for (let i = 0; i < 6; i++) { const s = new THREE.Mesh(new THREE.IcosahedronGeometry(0.5, 1), mat.clone()); s.userData.ph = i / 6; g.add(s); }
  c.add(g, 0, 9.0, 0, (o, t) => o.children.forEach((s: any) => {
    const u = (t * 0.12 + s.userData.ph) % 1;
    s.position.set(u * 2.4 + Math.sin(u * 7 + s.userData.ph * 6) * 0.15, u * 3.6, Math.cos(u * 5 + s.userData.ph * 6) * 0.15);
    s.scale.setScalar(0.4 + u * 1.5); s.material.opacity = 0.75 * (1 - u) * Math.min(1, u * 8);
  }));
};
const conveyor: Builder = (c) => {
  const M = c.M, L = 7.0, W = 1.3;
  for (const sx of [-W / 2 + 0.05, W / 2 - 0.05]) M.box(0.1, 0.34, L, sx, 0.62, 0, "#5c636b");
  M.box(W - 0.1, 0.1, L, 0, 0.72, 0, "#2f3338", { pat: PAT.ribs });
  for (let i = 0; i < 8; i++) { const z = -L / 2 + 0.4 + i * (L - 0.8) / 7; for (const sx of [-W / 2 + 0.2, W / 2 - 0.2]) M.box(0.12, 0.62, 0.12, sx, 0, z, "#8d96a0"); }
  const box = c.pick(c.palette, 3);
  const boxes = Array.from({ length: 5 }, (_, i) => i);
  c.part(0, 0.82, 0, (m) => {
    m.aoOn = false;
    boxes.forEach((i) => { m.local(0, 0, i * (L / 5), 0, () => m.rbox(0.72, 0.52, 0.72, 0, 0, 0, i % 2 ? "#c9914f" : box, 0.05, { pat: PAT.planks })); });
  }, (o, t) => { o.position.z = ((t * 0.9) % (L / 5)) - L / 2 + 0.3; });
  M.box(0.5, 1.2, 0.5, 0, 0.0, L / 2 + 0.5, "#e8a23a");
};
const robot: Builder = (c) => {
  const M = c.M, col = c.p.c?.[0] ?? "#e8a23a";
  M.cyl(1.0, 1.15, 0.35, 0, 0, 0, "#5c636b", 20); M.cyl(0.8, 0.9, 0.3, 0, 0.35, 0, "#8d96a0", 20);
  c.part(0, 0.7, 0, (m) => {
    m.aoOn = false;
    m.cyl(0.55, 0.6, 0.5, 0, 0, 0, col, 18);
    m.sphere(0.45, 0, 0.9, 0, shade(col, 0.9), 14);
  }, (o, t) => { o.rotation.y = Math.sin(t * 0.5) * 0.9; });
  c.part(0, 1.6, 0, (m) => {
    m.aoOn = false;
    m.local(0, 0, 0, 0, () => { m.sphere(0.4, 0, 0, 0, col, 14); m.box(0.46, 1.9, 0.46, 0, 0, 0, col); m.sphere(0.36, 0, 2.0, 0, shade(col, 0.88), 12); });
    m.local(0, 2.0, 0, 0, () => { m.pitch(0.0); m.box(0.36, 0.36, 1.8, 0, -0.18, 0.9, col); m.cyl(0.24, 0.24, 0.5, 0, -0.45, 1.8, "#5c636b", 10); m.box(0.5, 0.1, 0.1, 0, -0.5, 1.9, DARK); });
  }, (o, t) => { o.rotation.y = Math.sin(t * 0.5) * 0.9 + 0.4; o.rotation.x = Math.sin(t * 0.9 + 1.0) * 0.18; });
};

// ---------------------------------------------------------------- the desk
const laptop: Builder = (c) => {
  const M = c.M, col = c.p.c?.[0] ?? "#c9ced6";
  M.rbox(4.4, 0.22, 3.0, 0, 0, 0, col, 0.07, { pat: PAT.metal });
  for (let r = 0; r < 4; r++) for (let k = 0; k < 12; k++) M.rbox(0.28, 0.07, 0.26, -1.78 + k * 0.325, 0.2, -1.05 + r * 0.32, "#2a2f36", 0.02);
  M.rbox(1.4, 0.04, 0.9, 0, 0.2, 0.75, shade(col, 0.92), 0.02);
  M.push(); M.at(0, 0.18, -1.45); M.pitch(-0.32);
  M.rbox(4.4, 3.0, 0.14, 0, 0, 0, col, 0.07, { pat: PAT.metal });
  M.box(4.1, 2.72, 0.02, 0, 0.14, 0.08, "#10151c");
  screen(M, 3.9, 2.5, 0, 0.2, 0.1, c.pick(c.palette, 1), 2);
  M.pop();
};
const monitor: Builder = (c) => {
  const M = c.M, col = "#2a2f36";
  M.cyl(0.9, 1.0, 0.18, 0, 0, 0, "#9aa2ab", 20); M.rbox(0.36, 1.3, 0.3, 0, 0.1, -0.15, "#9aa2ab", 0.05);
  M.push(); M.at(0, 1.05, -0.2); M.pitch(-0.06);
  M.rbox(3.6, 2.2, 0.18, 0, 0, 0, col, 0.07);
  screen(M, 3.4, 2.0, 0, 0.1, 0.1, c.pick(c.palette, 5), 4);
  M.pop();
};
const mug: Builder = (c) => {
  const M = c.M, col = c.p.c?.[0] ?? "#f4efe4";
  M.cyl(0.62, 0.55, 1.2, 0, 0, 0, col, 24);
  M.use("glass"); M.cyl(0.52, 0.52, 0.03, 0, 1.12, 0, "#5a3a24", 22); M.use("main");
  M.torus(0.34, 0.08, 0.72, 0.62, 0, col, 0, 14);
  M.cyl(0.63, 0.63, 0.2, 0, 0.4, 0, c.pick(c.palette, 2), 24);
  const puffs = new THREE.Group();
  const mat = new THREE.MeshBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0.4, depthWrite: false });
  for (let i = 0; i < 5; i++) { const s = new THREE.Mesh(new THREE.SphereGeometry(0.16, 8, 6), mat.clone()); s.userData.ph = i / 5; puffs.add(s); }
  c.add(puffs, 0, 1.2, 0, (o, t) => o.children.forEach((s: any) => {
    const u = (t * 0.22 + s.userData.ph) % 1;
    s.position.set(Math.sin(u * 6 + s.userData.ph * 9) * 0.12, u * 1.6, Math.cos(u * 5 + s.userData.ph * 7) * 0.1);
    s.scale.setScalar(0.6 + u * 1.2); s.material.opacity = 0.42 * (1 - u) * Math.min(1, u * 6);
  }));
};
const books: Builder = (c) => {
  const M = c.M, cols = [c.pick(c.palette, 1), c.pick(c.palette, 2), "#f4efe4", c.pick(c.palette, 3), "#2d3a4a"];
  let y = 0;
  cols.forEach((col, i) => {
    const h = 0.26 + (i % 3) * 0.06, w = 2.6 - (i % 2) * 0.35, d = 1.9 - (i % 3) * 0.12;
    M.push(); M.at(0, 0, 0); M.yaw((i - 2) * 0.12);
    M.rbox(w, h, d, 0, y, 0, col, 0.04);
    M.box(w - 0.06, h - 0.08, 0.02, 0, y + 0.04, d / 2 - 0.02 + 0.02, "#fffaf0");
    M.pop();
    y += h;
  });
};
const plant: Builder = (c) => {
  const M = c.M, g = "#4f9d45";
  M.cyl(0.8, 0.55, 1.0, 0, 0, 0, "#c4633a", 18); M.cyl(0.86, 0.86, 0.14, 0, 0.9, 0, "#d9784a", 18); M.cyl(0.7, 0.7, 0.05, 0, 0.98, 0, "#4b3424", 16);
  for (let i = 0; i < 9; i++) {
    const a = i / 9 * Math.PI * 2, tilt = 0.35 + (i % 3) * 0.22;
    M.push(); M.at(0, 1.0, 0); M.yaw(a); M.roll(-tilt);
    M.ico(0.4, 0, 0.8 + (i % 3) * 0.25, 0, i % 2 ? shade(g, 1.1) : g, 1, 2.1);
    M.pop();
  }
};
const deskLamp: Builder = (c) => {
  const M = c.M, col = c.p.c?.[0] ?? "#2d3a4a";
  M.cyl(0.8, 0.9, 0.16, 0, 0, 0, col, 20);
  M.push(); M.at(0, 0.1, 0); M.roll(-0.35); M.box(0.12, 2.2, 0.12, 0, 0, 0, col); M.pop();
  M.push(); M.at(-0.76, 2.28, 0); M.roll(0.9); M.box(0.12, 1.9, 0.12, 0, 0, 0, col); M.pop();
  M.sphere(0.14, -0.76, 2.28, 0, "#9aa2ab", 10);
  M.push(); M.at(0.4, 3.75, 0); M.roll(2.3); M.cone(0.55, 0.8, 0, 0, 0, c.pick(c.palette, 4), 18); M.use("emit"); M.sphere(0.18, 0, 0.1, 0, "#fff0c0", 10); M.use("main"); M.pop();
};
const notebook: Builder = (c) => {
  const M = c.M, col = c.p.c?.[0] ?? c.pick(c.palette, 2);
  M.rbox(2.4, 0.18, 3.2, 0, 0, 0, col, 0.05);
  M.box(2.2, 0.06, 3.0, 0.04, 0.17, 0, "#fffaf0");
  for (let i = 0; i < 9; i++) M.torus(0.07, 0.015, -1.15, 0.17, -1.2 + i * 0.3, "#9aa2ab", 0, 8);
  for (let i = 0; i < 8; i++) M.box(1.7, 0.01, 0.02, 0.1, 0.235, -1.1 + i * 0.28, "#bcd2ea");
  M.push(); M.at(0.5, 0.24, 0.4); M.yaw(0.5); M.cyl(0.05, 0.05, 2.0, 0, 0, 0, "#e8b23a", 6); M.pop();
};

// ---------------------------------------------------------------- the studio
const easel: Builder = (c) => {
  const M = c.M;
  for (const [sx, sz, a] of [[-0.9, -0.2, 0.3], [0.9, -0.2, -0.3], [0, -1.0, 0]] as const) {
    M.push(); M.at(sx, 0, sz); M.roll(a); M.pitch(sz < -0.5 ? 0.28 : -0.12); M.box(0.12, 4.4, 0.12, 0, 0, 0, WOOD, { pat: PAT.planks }); M.pop();
  }
  M.box(2.6, 0.1, 0.2, 0, 1.1, 0.1, WOOD_D);
  M.push(); M.at(0, 1.2, 0.2); M.pitch(-0.1);
  M.rbox(2.5, 3.1, 0.12, 0, 0, 0, "#fffaf0", 0.03);
  // a painting on the canvas: sky, hills, a sun
  M.box(2.3, 1.4, 0.02, 0, 1.55, 0.08, "#9fd0ea"); M.box(2.3, 1.1, 0.02, 0, 0.2, 0.08, "#7fb760");
  M.ico(0.6, -0.5, 0.85, 0.09, "#5e9a4a", 1, 0.5); M.ico(0.75, 0.55, 0.8, 0.09, "#4d8a42", 1, 0.45);
  M.cyl(0.26, 0.26, 0.02, 0.6, 2.2, 0.09, "#f2c230", 18).pitch(0);
  M.pop();
  // palette and brushes on the ledge
  M.rbox(0.7, 0.05, 0.45, 0.7, 1.22, 0.45, "#c9914f", 0.02);
  for (let i = 0; i < 4; i++) M.sphere(0.07, 0.5 + i * 0.12, 1.3, 0.42, ["#d9503a", "#2f6fa8", "#f2c230", "#3aa06a"][i], 8);
};
const softbox: Builder = (c) => {
  const M = c.M;
  for (let i = 0; i < 3; i++) { const a = i / 3 * Math.PI * 2 + 0.5; M.push(); M.at(0, 0.0, 0); M.yaw(a); M.push(); M.at(0, 0, 0.5); M.pitch(-0.28); M.box(0.1, 3.2, 0.1, 0, 0, 0, DARK); M.pop(); M.pop(); }
  M.cyl(0.14, 0.14, 4.0, 0, 0.2, 0, STEEL, 10);
  M.push(); M.at(0, 4.2, 0); M.pitch(0.12);
  M.rbox(2.4, 2.4, 0.9, 0, -1.2, -0.2, "#2a2f36", 0.08);
  M.use("emit"); M.box(2.1, 2.1, 0.04, 0, -1.05, 0.28, "#fff6e0"); M.use("main");
  M.pop();
};
const camera: Builder = (c) => {
  const M = c.M;
  for (let i = 0; i < 3; i++) { const a = i / 3 * Math.PI * 2 + 0.2; M.push(); M.yaw(a); M.push(); M.at(0, 0, 0.55); M.pitch(-0.3); M.box(0.07, 2.4, 0.07, 0, 0, 0, DARK); M.pop(); M.pop(); }
  M.cyl(0.1, 0.1, 0.5, 0, 2.0, 0, STEEL, 10);
  M.rbox(1.3, 0.9, 1.0, 0, 2.5, 0, "#2a2f36", 0.1);
  M.cyl(0.38, 0.4, 0.7, 0, 2.55, 0.8, "#1c2026", 18); M.push(); M.at(0, 2.9, 0.85); M.pitch(Math.PI / 2); M.cyl(0.3, 0.3, 0.1, 0, 0, 0, "#3a4a6a", 18); M.cyl(0.33, 0.33, 0.04, 0, 0.0, 0.02, "#9fd0ea", 18); M.pop();
  M.use("emit"); M.sphere(0.06, 0.45, 2.85, 0.5, "#ff3b30", 8); M.use("main");
};
const speaker: Builder = (c) => {
  const M = c.M;
  M.rbox(1.5, 3.0, 1.2, 0, 0, 0, c.p.c?.[0] ?? "#2d3a4a", 0.08);
  M.cyl(0.5, 0.5, 0.1, 0, 0.5, 0.6, "#12161b", 22); M.cyl(0.26, 0.26, 0.12, 0, 0.5, 0.62, "#3a4350", 22);
  M.cyl(0.32, 0.32, 0.1, 0, 1.95, 0.6, "#12161b", 18); M.sphere(0.1, 0, 1.95, 0.66, "#3a4350", 8);
};
const sofa: Builder = (c) => {
  const M = c.M, col = c.p.c?.[0] ?? c.pick(c.palette, 3);
  M.rbox(4.6, 0.55, 2.0, 0, 0.12, 0, shade(col, 0.85), 0.1);
  M.rbox(4.6, 1.35, 0.6, 0, 0.12, -0.7, col, 0.14);
  for (const sx of [-2.1, 2.1]) M.rbox(0.5, 0.95, 2.0, sx, 0.12, 0, col, 0.14);
  for (const sx of [-0.9, 0.9]) { M.rbox(1.7, 0.3, 1.5, sx, 0.62, 0.1, shade(col, 1.1), 0.12); M.rbox(1.7, 0.9, 0.35, sx, 0.62, -0.45, shade(col, 1.1), 0.12); }
  for (const sx of [-2.0, 2.0]) for (const sz of [-0.8, 0.8]) M.cyl(0.07, 0.05, 0.14, sx, 0, sz, WOOD_D, 6);
  M.rbox(0.8, 0.8, 0.22, 1.4, 0.95, 0.35, c.pick(c.palette, 2), 0.08);
};
const shelf: Builder = (c) => {
  const M = c.M;
  M.box(3.4, 0.12, 1.0, 0, 0, 0, WOOD); M.box(0.12, 4.2, 1.0, -1.64, 0, 0, WOOD); M.box(0.12, 4.2, 1.0, 1.64, 0, 0, WOOD); M.box(3.4, 0.12, 1.0, 0, 4.1, 0, WOOD);
  for (const y of [1.35, 2.75]) M.box(3.2, 0.1, 0.95, 0, y, 0, WOOD);
  M.box(3.2, 4.0, 0.06, 0, 0.1, -0.48, shade(WOOD, 0.8));
  const cols = [c.pick(c.palette, 1), c.pick(c.palette, 2), "#f4efe4", c.pick(c.palette, 3), "#2d3a4a", c.pick(c.palette, 4)];
  [0.12, 1.45, 2.85].forEach((y, r) => {
    let x = -1.4;
    for (let i = 0; i < 6; i++) { const h = 0.8 + ((i * 7 + r * 3) % 5) * 0.08; M.rbox(0.22, h, 0.6, x, y, 0, cols[(i + r) % cols.length], 0.02); x += 0.26; }
    M.rbox(0.8, 0.55, 0.6, 0.55, y, 0, cols[(r + 2) % cols.length], 0.04);
    M.ico(0.28, 1.2, y + 0.3, 0, "#4f9d45", 1, 1);
  });
};
const rug: Builder = (c) => {
  const M = c.M, col = c.p.c?.[0] ?? c.pick(c.palette, 3);
  M.rbox(5.0, 0.06, 3.6, 0, 0, 0, col, 0.03);
  M.rbox(4.4, 0.07, 3.0, 0, 0, 0, "#f4efe4", 0.02);
  M.rbox(3.9, 0.08, 2.5, 0, 0, 0, shade(col, 1.12), 0.02);
  M.cyl(0.8, 0.8, 0.09, 0, 0, 0, "#f4efe4", 24);
};
const pencils: Builder = (c) => {
  const M = c.M;
  M.cyl(0.5, 0.45, 0.9, 0, 0, 0, "#2d3a4a", 18);
  ["#e8b23a", "#d9503a", "#2f6fa8", "#3aa06a", "#f4efe4"].forEach((col, i) => {
    const a = i / 5 * Math.PI * 2;
    M.push(); M.at(Math.cos(a) * 0.15, 0.5, Math.sin(a) * 0.15); M.roll(Math.cos(a) * 0.2); M.pitch(Math.sin(a) * 0.2);
    M.cyl(0.05, 0.05, 1.2, 0, 0, 0, col, 6); M.cone(0.05, 0.14, 0, 1.2, 0, "#e9d3a6", 6); M.pop();
  });
};
const forklift: Builder = (c) => {
  const M = c.M, col = c.p.c?.[0] ?? "#f2b21c";
  M.rbox(1.4, 0.7, 2.2, 0, 0.35, -0.2, col, 0.08);
  M.box(0.9, 0.12, 0.9, 0, 1.05, -0.5, DARK);
  for (const sx of [-0.45, 0.45]) { M.box(0.07, 1.1, 0.07, sx, 1.05, -0.95, DARK); M.box(0.07, 1.1, 0.07, sx, 1.05, -0.05, DARK); }
  M.box(1.0, 0.07, 1.0, 0, 2.15, -0.5, DARK);
  for (const sx of [-0.35, 0.35]) M.box(0.09, 2.0, 0.09, sx, 0.2, 1.0, "#5c636b");
  for (const sx of [-0.35, 0.35]) M.box(0.12, 0.08, 1.0, sx, 0.15, 1.5, "#8d96a0");
  for (const sx of [-0.72, 0.72]) for (const sz of [-0.9, 0.5]) { M.cyl(0.32, 0.32, 0.26, sx, 0, sz, "#1c2026", 14); M.pitch(0); }
};

export const KIT2: Record<string, Builder> = {
  clocktower, fountain, bridge, tank, silo, chimney, conveyor, robot, forklift,
  laptop, monitor, mug, books, plant, deskLamp, notebook, pencils,
  easel, softbox, camera, speaker, sofa, shelf, rug,
};
