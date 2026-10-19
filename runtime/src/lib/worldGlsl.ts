/**
 * The look of type in the world, as GLSL shared by the players that draw it (film: players/world.ts, photo: players/parallax.ts).
 * Everything here takes values, not textures: the caller samples the film (or photo), the type atlas, the depth and the
 * surface mask, and hands them in. The point of each function is to make the type belong to the picture it is in:
 *
 *   behind / sky   shown where the scene is farther than the type (a soft depth step); lit by the light at that spot; mixed with
 *                  the air there (haze) and, in the sky, a fog in front; the picture's own grain runs through the letters.
 *   surface        paint: the surface's light, grain and relief show through it, its edge is ragged by the grain, it wears,
 *                  and it is laid on from left to right as the section arrives.
 */
export const WORLD_GLSL = `
const vec3 LW = vec3(0.2126, 0.7152, 0.0722);
float hash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float vnoise(vec2 p) {
  vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}
float fbm(vec2 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++) { s += a * vnoise(p); p *= 2.03; a *= 0.5; } return s / 0.9375; }

// A = (type depth, soft, haze, blur lod), B = (fog, wear, relief, tone of the footage behind the type)
vec3 worldBehindSky(vec3 col, vec3 ink, float cov, vec3 film, vec3 near, vec3 locl, vec3 air, float dep, vec4 A, vec4 B,
                    float on, float intro, int kind, float vy) {
  float vis = 1.0 - smoothstep(A.x - A.y, A.x + A.y, dep);
  float lumLoc = dot(locl, LW), Lf = dot(film, LW), Ln = dot(near, LW);
  vec3 lit = ink * mix(1.0, clamp(lumLoc / max(B.w, 0.02), 0.55, 1.25), 0.55);
  float hz = clamp(A.z * (1.0 + (1.0 - intro) * 1.4), 0.0, 0.95);
  lit = mix(lit, air, hz);
  lit += (Lf - Ln) * 0.9;                                   // the grain of the picture runs through the letters
  float a = cov * vis * on * (1.0 - 0.3 * hz);
  if (kind == 1) {
    // fog in front: thicker low in the picture, and over the far things that stand just in front of the type (a ridge in haze)
    float ridge = smoothstep(A.x - 0.02, A.x + 0.03, dep) * (1.0 - smoothstep(A.x + 0.05, A.x + 0.4, dep));
    float fog = B.x * (0.14 + 0.5 * smoothstep(0.1, 0.9, vy) + 0.45 * ridge);
    lit = mix(lit, air, clamp(fog * 0.7, 0.0, 1.0));
    a *= 1.0 - clamp(fog * 0.4, 0.0, 0.6);
  }
  return mix(col, lit, clamp(a, 0.0, 1.0));
}

// pl: the plane's coordinates (noise sticks to the surface), m: the surface's mask here, lx: 0-1 across the type (the paint-on wipe)
vec3 worldSurface(vec3 col, vec3 ink, float cov, vec3 film, vec3 near, vec3 locl, vec2 pl, float m, vec4 B,
                  float on, float intro, float lx) {
  float vis = smoothstep(0.35, 0.65, m);
  float lumLoc = dot(locl, LW), Lf = dot(film, LW), Ln = dot(near, LW);
  float wipe = smoothstep(lx - 0.18, lx + 0.02, intro * 1.3 - 0.1);
  float n = fbm(pl * 52.0) * 0.75 + (0.5 - (Lf - Ln) * 5.0) * 0.25;
  float th = 1.0 - B.y * 0.9;
  float worn = 1.0 - smoothstep(th - 0.1, th + 0.14, n) * step(0.001, B.y);
  float lightK = clamp(lumLoc / max(B.w, 0.03), 0.35, 1.5);
  vec3 paint = ink * mix(1.0, lightK, 0.9);
  float texK = clamp(Lf / max(Ln, 0.03), 0.55, 1.5);
  paint *= mix(1.0, texK * texK, B.z);
  float inkL = dot(ink, LW);
  vec3 bleed = inkL < 0.5 ? film * ink * 1.8 : 1.0 - (1.0 - film) * (1.0 - ink * 0.9);
  paint = mix(paint, bleed, 0.2 + 0.25 * B.z);
  paint += (Lf - Ln) * 0.8 * B.z;
  // paint does not stop in a clean vector edge: the grain of the surface ragged-edges every letter
  float rough = fbm(pl * 230.0 + Lf * 3.0);
  float thr = 0.5 + (rough - 0.5) * 0.9 * B.z;
  float edge = smoothstep(thr - 0.22, thr + 0.22, cov);
  float a = edge * vis * on * worn * wipe * 0.97;
  return mix(col, paint, clamp(a, 0.0, 1.0));
}
`;
