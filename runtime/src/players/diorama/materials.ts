/**
 * Materials. The props' paint is in vertex colours; `aPat` picks a procedural surface drawn from world position
 * (roof tiles, planks, brick, foliage, container ribs...), and a faint world-space mottling keeps flat colours from
 * looking like plastic renders. The terrain wears the painted ground texture and a drifting cloud shadow.
 */
import * as THREE from "three";

const NOISE = /* glsl */ `
float h21(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float h31(vec3 p){ return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
float vnoise(vec3 p){
  vec3 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  float a = h31(i), b = h31(i + vec3(1,0,0)), c = h31(i + vec3(0,1,0)), d = h31(i + vec3(1,1,0));
  float e = h31(i + vec3(0,0,1)), g = h31(i + vec3(1,0,1)), hh = h31(i + vec3(0,1,1)), k = h31(i + vec3(1,1,1));
  return mix(mix(mix(a, b, f.x), mix(c, d, f.x), f.y), mix(mix(e, g, f.x), mix(hh, k, f.x), f.y), f.z);
}
float vnoise2(vec2 p){
  vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(h21(i), h21(i + vec2(1,0)), f.x), mix(h21(i + vec2(0,1)), h21(i + vec2(1,1)), f.x), f.y);
}
`;

const PATTERNS = /* glsl */ `
float shade = 1.0;
{
  vec3 n = normalize(vWNor);
  vec2 hn = n.xz; float hl = length(hn); hn = hl > 1e-4 ? hn / hl : vec2(1.0, 0.0);
  vec2 hp = vec2(-hn.y, hn.x);
  float pat = vPat;
  vec3 wp = vWPos;
  if (pat > 0.5 && pat < 1.5) {                 // roof tiles
    float s = dot(wp.xz, hn) / 0.17;
    float row = floor(s);
    float col = dot(wp.xz, hp) / 0.24 + 0.5 * mod(row, 2.0);
    float fc = fract(col), fr = fract(s);
    float tile = h21(vec2(floor(col), row));
    shade *= (0.86 + 0.14 * smoothstep(0.0, 0.3, fr)) * (0.93 + 0.07 * smoothstep(0.0, 0.1, min(fc, 1.0 - fc))) * (0.94 + 0.1 * tile);
  } else if (pat > 1.5 && pat < 2.5) {          // plaster: fine mottling
    shade *= 0.95 + 0.1 * vnoise(wp * 16.0);
  } else if (pat > 2.5 && pat < 3.5) {          // vertical planks
    float t = (dot(wp.xz, hp) + wp.y * 0.0) / 0.2;
    float ft = fract(t);
    shade *= (0.82 + 0.18 * smoothstep(0.0, 0.12, ft)) * (0.9 + 0.12 * h21(vec2(floor(t), 3.0)));
  } else if (pat > 3.5 && pat < 4.5) {          // deck boards along direction par, grain
    vec2 d = vec2(cos(vPar), -sin(vPar));
    float t = dot(wp.xz, d) / 0.34;
    float along = dot(wp.xz, vec2(sin(vPar), cos(vPar))) * 0.5;
    float ft = fract(t);
    shade *= (0.8 + 0.2 * smoothstep(0.0, 0.1, ft)) * (0.88 + 0.16 * h21(vec2(floor(t), floor(along))));
  } else if (pat > 4.5 && pat < 5.5) {          // foliage: lumpy light and dark
    shade *= 0.82 + 0.34 * vnoise(wp * 7.0);
  } else if (pat > 5.5 && pat < 6.5) {          // brick
    float v = wp.y / 0.11;
    float row = floor(v);
    float u = (dot(wp.xz, hp)) / 0.3 + 0.5 * mod(row, 2.0);
    float fu = fract(u), fv = fract(v);
    float mortar = 1.0 - smoothstep(0.0, 0.1, min(min(fu, 1.0 - fu), min(fv, 1.0 - fv)));
    shade *= (1.0 - 0.25 * mortar) * (0.9 + 0.2 * h21(vec2(floor(u), row)));
  } else if (pat > 6.5 && pat < 7.5) {          // corrugated ribs (containers, sheds): vertical on walls
    float t = dot(wp.xz, hp) / 0.14;
    shade *= 0.9 + 0.1 * cos(t * 6.2832);
  } else if (pat > 7.5 && pat < 8.5) {          // painted stripes around a tower: nothing here, the colour carries it
    shade *= 0.98 + 0.04 * vnoise(wp * 10.0);
  } else if (pat > 8.5 && pat < 9.5) {          // metal: faint brushed streaks
    shade *= 0.94 + 0.08 * vnoise(vec3(wp.x * 40.0, wp.y * 4.0, wp.z * 40.0));
  } else if (pat > 9.5) {                       // sand / earth speckle
    shade *= 0.9 + 0.2 * vnoise(wp * 22.0);
  }
  shade *= 0.94 + 0.12 * vnoise(wp * 2.6);       // very slow mottling, so large flat colours are hand-painted
}
diffuseColor.rgb *= shade;
`;

export function propMaterial(kind: "main" | "glass" | "emit"): THREE.Material {
  if (kind === "emit") return new THREE.MeshBasicMaterial({ vertexColors: true, toneMapped: true });
  const m = new THREE.MeshStandardMaterial({
    vertexColors: true,
    roughness: kind === "glass" ? 0.16 : 0.78,
    metalness: kind === "glass" ? 0.05 : 0.0,
    envMapIntensity: kind === "glass" ? 1.6 : 0.9,
  });
  m.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader
      .replace("#include <common>", `#include <common>
attribute float aPat; attribute float aPar; varying float vPat; varying float vPar; varying vec3 vWPos; varying vec3 vWNor;`)
      .replace("#include <begin_vertex>", `#include <begin_vertex>
vPat = aPat; vPar = aPar;
vWPos = (modelMatrix * vec4(position, 1.0)).xyz;
vWNor = normalize(mat3(modelMatrix) * normal);`);
    sh.fragmentShader = sh.fragmentShader
      .replace("#include <common>", `#include <common>
varying float vPat; varying float vPar; varying vec3 vWPos; varying vec3 vWNor;
${NOISE}`)
      .replace("#include <color_fragment>", `#include <color_fragment>
${PATTERNS}`);
  };
  return m;
}

export interface TerrainUniforms { uTime: { value: number }; uCloud: { value: number } }

/** The ground: the painted plan as a texture, grass and stone grain drawn on top, clouds drifting over it. */
export function terrainMaterial(map: THREE.Texture, size: number, uniforms: TerrainUniforms): THREE.Material {
  const m = new THREE.MeshStandardMaterial({ map, roughness: 0.92, metalness: 0, envMapIntensity: 0.7 });
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, uniforms);
    sh.vertexShader = sh.vertexShader
      .replace("#include <common>", `#include <common>
varying vec3 vWPos;`)
      .replace("#include <begin_vertex>", `#include <begin_vertex>
vWPos = (modelMatrix * vec4(position, 1.0)).xyz;`);
    sh.fragmentShader = sh.fragmentShader
      .replace("#include <common>", `#include <common>
varying vec3 vWPos; uniform float uTime; uniform float uCloud;
${NOISE}`)
      .replace("#include <map_fragment>", `#include <map_fragment>
{
  float g1 = vnoise2(vWPos.xz * 9.0), g2 = vnoise2(vWPos.xz * 31.0);
  float gl = dot(diffuseColor.rgb, vec3(0.3, 0.59, 0.11));
  float grassy = smoothstep(0.02, 0.12, diffuseColor.g - max(diffuseColor.r, diffuseColor.b));
  diffuseColor.rgb *= 1.0 + (g1 - 0.5) * 0.14 + (g2 - 0.5) * 0.10 * (0.4 + 0.6 * grassy);
  float cl = vnoise2(vWPos.xz * 0.075 + vec2(uTime * 0.012, uTime * 0.006)) * 0.65 + vnoise2(vWPos.xz * 0.16 - vec2(uTime * 0.02, 0.0)) * 0.35;
  diffuseColor.rgb *= 1.0 - uCloud * smoothstep(0.56, 0.78, cl) * 0.22;
}`);
  };
  return m;
}
