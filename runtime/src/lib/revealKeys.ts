/**
 * Reveal keys: section scroll progress -> how revealed each region is (0-1). No DOM here, so the engine's tests run it
 * against its Python twin (engine/reveal.py `amounts_at`): they must agree.
 */
export type RevealKey = { at: number } & Record<string, number>;

/**
 * A region's keys are the keys that name it. Before the first it holds that key's value, after the last it holds that
 * one, between two it eases (smoothstep or linear). `reduced` (prefers-reduced-motion): no easing; a region jumps to the
 * end value of a change as soon as the change begins.
 */
export function amountsAt(keys: RevealKey[], ids: string[], p: number, ease = "smooth", reduced = false): Record<string, number> {
  const out: Record<string, number> = {};
  for (const id of ids) {
    const ks: [number, number][] = [];
    for (const k of keys) if (id in k) ks.push([k.at, k[id]]);
    ks.sort((a, b) => a[0] - b[0]);
    if (!ks.length) { out[id] = 0; continue; }
    if (p <= ks[0][0]) { out[id] = ks[0][1]; continue; }
    let v = ks[ks.length - 1][1];
    for (let i = 0; i + 1 < ks.length; i++) {
      const [a0, v0] = ks[i], [a1, v1] = ks[i + 1];
      if (p < a1) {
        if (reduced) v = v1 !== v0 ? v1 : v0;
        else {
          let t = (p - a0) / Math.max(a1 - a0, 1e-9);
          if (ease === "smooth") t = t * t * (3 - 2 * t);
          v = v0 + (v1 - v0) * t;
        }
        break;
      }
    }
    out[id] = v;
  }
  return out;
}
