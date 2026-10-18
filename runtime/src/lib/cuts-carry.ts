/** Carry: an element travels from its place in one section to its place in the next (FLIP). The browser measures both
 * places; a baked copy of the element (computed styles inline) flies over the cut in a fixed layer while the pictures
 * underneath do whatever `via` says. */
import type { Cut, Fx, FxResult, Helpers, Metrics } from "./cuts-types";

let layer: HTMLElement | null = null;

function bake(el: HTMLElement): HTMLElement {
  const clone = el.cloneNode(true) as HTMLElement;
  const src = [el, ...el.querySelectorAll<HTMLElement>("*")];
  const dst = [clone, ...clone.querySelectorAll<HTMLElement>("*")];
  src.forEach((s, i) => {
    const cs = getComputedStyle(s), d = dst[i];
    d.removeAttribute("id");
    d.removeAttribute("class");
    for (let j = 0; j < cs.length; j++) {
      const p = cs[j];
      d.style.setProperty(p, cs.getPropertyValue(p), cs.getPropertyPriority(p));
    }
    d.style.setProperty("transition", "none");   // the copy is moved every frame: nothing may ease it
    d.style.setProperty("animation", "none");
    d.style.setProperty("pointer-events", "none");
  });
  return clone;
}

function pick(root: HTMLElement, sel: string, last: boolean, H: number): HTMLElement | null {
  const all = [...root.querySelectorAll<HTMLElement>(sel)].filter((e) => {
    const r = e.getBoundingClientRect();
    return r.width > 4 && r.height > 4 && r.bottom > 0 && r.top < H;
  });
  return (last ? all[all.length - 1] : all[0]) || null;
}

export function endCarry(c: Cut) {
  const d = c.data?.carry;
  if (d) {
    d.a?.classList.remove("ss-cut-carried"); d.b?.classList.remove("ss-cut-carried");
    d.ghostA?.remove(); d.ghostB?.remove();
  }
  if (c.data) c.data.carry = null;
}

export function measureCarry(c: Cut, m: Metrics) {
  endCarry(c);
  const spec = c.cfg.carry || { from: "h1, h2", to: "h1, h2", via: "dissolve" };
  const a = pick(c.pinA, spec.from, true, m.H), b = pick(c.pinB, spec.to, false, m.H);
  if (!a || !b) { c.data.carry = null; return; }
  const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
  if (!layer) {
    layer = document.createElement("div");
    layer.className = "ss-cutghost";
    layer.setAttribute("aria-hidden", "true");
    document.body.appendChild(layer);
  }
  const ghostA = bake(a), ghostB = bake(b);
  for (const [g, r] of [[ghostA, ra], [ghostB, rb]] as [HTMLElement, DOMRect][]) {
    Object.assign(g.style, { position: "absolute", left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px",
      margin: "0", transform: "none", opacity: "0", visibility: "visible", transformOrigin: "0 0" });
    layer.appendChild(g);
  }
  c.data.carry = { a, b, ra, rb, ghostA, ghostB, same: (a.textContent || "").trim() === (b.textContent || "").trim() };
}

export function carryFx(fx: Record<string, Fx>, { ease, win }: Helpers): Fx {
  return (k, c, m): FxResult => {
    const D = c.data.carry;
    const via = c.cfg.carry?.via || "dissolve";
    const base = (fx[via] || fx.dissolve)(k, c, m);
    if (!D) return base;
    D.a.classList.add("ss-cut-carried"); D.b.classList.add("ss-cut-carried");
    const e0 = k, e = ease(e0);
    const { ra, rb } = D;
    const cax = ra.left + ra.width / 2, cay = ra.top + ra.height / 2, cbx = rb.left + rb.width / 2, cby = rb.top + rb.height / 2;
    const px = cax + (cbx - cax) * e, py = cay + (cby - cay) * e;
    const f = Math.sqrt((rb.width / ra.width) * (rb.height / ra.height));   // A's footprint to B's
    const place = (g: HTMLElement, r: DOMRect, s: number, o: number) => {
      g.style.transform = `translate(${(px - (s * r.width) / 2 - r.left).toFixed(2)}px, ${(py - (s * r.height) / 2 - r.top).toFixed(2)}px) scale(${s.toFixed(4)})`;
      g.style.opacity = o.toFixed(3);
    };
    // the next copy comes in over this one, which leaves only once it is whole (the picture never dips)
    const [i0, i1] = D.same ? [0.1, 0.4] : [0.35, 0.55];
    const sA = 1 + (f - 1) * e, sB = 1 / f + (1 - 1 / f) * e;
    place(D.ghostA, ra, sA, 1 - ease(win(e0, i1, i1 + 0.25)));
    place(D.ghostB, rb, sB, ease(win(e0, i0, i1)));
    return base;
  };
}
