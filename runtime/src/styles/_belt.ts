/**
 * A belt: a run of consecutive blocks moved into a pinned (sticky) stage and carried by a translated "belt" instead of
 * by the browser's own scroll. The belt's true offset is exactly where normal flow would put the content, so before the
 * stage pins and after it releases the page is indistinguishable from an ordinary one; while it is pinned a style may
 * show any offset it likes (stepped, held, smeared) and nothing mismatches, because nothing the belt carries is moved by
 * the compositor. Scenes (their own sticky players) are never put on a belt.
 *
 * Used by scratch-film (pull-down steps) and smears (poses sampled on twos). Native scroll still drives everything:
 * the stage's height is the belt's, anchors, hashes and keyboard focus are mapped back to a scroll position here, and a
 * find-in-page that scrolls the stage is turned into a page scroll.
 */
import { css } from "./_kit";

export interface Belt {
  root: HTMLElement; stage: HTMLElement; belt: HTMLElement; blocks: HTMLElement[];
  /** document y of the root's top (px) */ top: number;
  /** belt height (px) */ h: number;
  /** viewport height used for the last measure */ vh: number;
  /** how far the belt can travel: h - vh (>= 0) */ range: number;
  /** offset last written */ shown: number;
}

css(`.bt-root { position: relative; }
.bt-stage { position: sticky; top: 0; height: 100vh; height: 100svh; overflow: hidden; }
.bt-belt { position: absolute; left: 0; right: 0; top: 0; will-change: transform; }`);

/** Group consecutive children of main that pass isBlock into belts. Children that fail it stay where they are. */
export function makeBelts(main: HTMLElement, isBlock: (el: HTMLElement) => boolean): Belt[] {
  const groups: HTMLElement[][] = [];
  let cur: HTMLElement[] | null = null;
  for (const b of [...main.children] as HTMLElement[]) {
    if (isBlock(b)) { if (!cur) groups.push((cur = [])); cur.push(b); } else cur = null;
  }
  const belts = groups.map((g) => {
    const root = document.createElement("div"); root.className = "bt-root";
    const stage = document.createElement("div"); stage.className = "bt-stage";
    const belt = document.createElement("div"); belt.className = "bt-belt";
    g[0].before(root); root.appendChild(stage); stage.appendChild(belt);
    g.forEach((b) => belt.appendChild(b));
    return { root, stage, belt, blocks: g, top: 0, h: 0, vh: 0, range: 0, shown: 0 } as Belt;
  });
  // find-in-page and focus scroll an overflow:hidden box; turn that into a page scroll instead
  for (const b of belts) b.stage.addEventListener("scroll", () => {
    const d = b.stage.scrollTop;
    if (d) { b.stage.scrollTop = 0; scrollBy(0, d); }
  });
  return belts;
}

/** Re-measure every belt (call on resize, font load, and when content height changes). */
export function measure(belts: Belt[]) {
  const vh = innerHeight;
  for (const b of belts) {
    b.vh = vh;
    b.h = Math.max(b.belt.offsetHeight, 1);
    b.range = Math.max(0, b.h - vh);
    b.root.style.height = `${Math.max(b.h, vh)}px`;
    b.top = b.root.getBoundingClientRect().top + scrollY;
  }
}

/** Keep the measure fresh when the belt's content changes height (an FAQ opening, a font arriving). */
export function watch(belts: Belt[], onChange: () => void) {
  if (!("ResizeObserver" in window)) return;
  const ro = new ResizeObserver(() => { measure(belts); onChange(); });
  for (const b of belts) ro.observe(b.belt);
}

/** Where normal flow would put the belt: the scroll position inside the run, clamped to the belt's travel. */
export function trueOffset(b: Belt, y = scrollY): number {
  return Math.min(b.range, Math.max(0, y - b.top));
}

/** The belt a scroll position is in or nearest to (for the style's per-run bookkeeping). */
export function beltAt(belts: Belt[], y = scrollY): Belt | null {
  let best: Belt | null = null;
  for (const b of belts) if (y >= b.top - innerHeight && y <= b.top + Math.max(b.h, b.vh) + innerHeight) best = b;
  return best;
}

export function setOffset(b: Belt, off: number) {
  if (off === b.shown && b.belt.style.translate) return;
  b.shown = off;
  b.belt.style.translate = `0 ${(-off).toFixed(2)}px`;
}

/** y of el inside its belt from layout alone (offsetTop chain), unaffected by the belt's translate. */
export function yInBelt(b: Belt, el: HTMLElement): number {
  let y = 0; let n: HTMLElement | null = el;
  while (n && n !== b.belt) { y += n.offsetTop; n = n.offsetParent as HTMLElement | null; }
  return y;
}

export function beltOf(belts: Belt[], el: Element | null): Belt | null {
  if (!el) return null;
  return belts.find((b) => b.belt.contains(el)) || null;
}

/** The scroll position that puts el a little below the top of the screen (null if el is not on a belt). */
export function scrollTargetFor(belts: Belt[], el: HTMLElement, lead = 0.12): number | null {
  const b = beltOf(belts, el);
  if (!b) return null;
  const y = yInBelt(b, el);
  return Math.round(b.top + Math.min(b.range, Math.max(0, y - innerHeight * lead)));
}

/** In-page links to something on a belt scroll the page (the belt cannot be scrolled to by the browser). */
export function wireLinks(belts: Belt[], duration = (dist: number) => Math.min(1800, 500 + Math.abs(dist) / innerHeight * 220)) {
  const tween = (to: number) => {
    const from = scrollY, dist = to - from, dur = duration(dist), t0 = performance.now();
    const step = (now: number) => {
      const q = Math.min(1, (now - t0) / dur);
      scrollTo(0, from + dist * (q < 0.5 ? 2 * q * q : 1 - 2 * (1 - q) * (1 - q)));
      if (q < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  document.addEventListener("click", (e) => {
    const a = (e.target as HTMLElement).closest<HTMLAnchorElement>('a[href^="#"]');
    if (!a) return;
    const id = a.getAttribute("href")!.slice(1);
    if (!id) return;
    const el = document.getElementById(id);
    const y = el ? scrollTargetFor(belts, el) : null;
    if (y == null) return;
    e.preventDefault(); e.stopPropagation();
    tween(y);
  }, { capture: true });
  // keyboard focus inside a belt that the screen isn't showing takes the page there
  document.addEventListener("focusin", (e) => {
    const t = e.target as HTMLElement;
    const b = beltOf(belts, t);
    if (!b) return;
    const r = t.getBoundingClientRect();
    if (r.top >= 0 && r.bottom <= innerHeight) return;
    const y = scrollTargetFor(belts, t, 0.3);
    if (y != null) scrollTo(0, y);
  });
  if (location.hash.length > 1) {
    const el = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    const y = el ? scrollTargetFor(belts, el) : null;
    if (y != null) requestAnimationFrame(() => scrollTo(0, y));
  }
}

