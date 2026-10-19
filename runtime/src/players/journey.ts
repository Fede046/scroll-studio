/** The one-take page (engine/journey.py): the film is one camera journey and every stop is a place on it.
 *  Scroll maps to film time through `map` (a move plays as you scroll through it, a hold is the page resting at a stop);
 *  each stop's blocks arrive as the camera slows into it and leave as it moves on; the rail names the places.
 *  Nothing here takes the scroll from the reader: the page scrolls as any page does, the film follows it. */
import { clamp, isMobile } from "../lib/util";

interface Stop {
  id: string; label: string; p0: number; p1: number; in: [number, number]; out: [number, number];
  focus?: [number, number] | null;
}
export interface JourneyCfg { duration: number; map: number[][]; stops: Stop[]; rail?: boolean }

/** Film time (seconds) at scroll progress p: linear between the map's points. */
export function timeAt(map: number[][], p: number): number {
  if (p <= map[0][0]) return map[0][1];
  for (let i = 1; i < map.length; i++) {
    if (p <= map[i][0]) {
      const [p0, t0] = map[i - 1], [p1, t1] = map[i];
      return p1 > p0 ? t0 + (t1 - t0) * (p - p0) / (p1 - p0) : t1;
    }
  }
  return map[map.length - 1][1];
}

/** 0 before `a`, 1 after `b`; a window with b <= a is a step (a stop that is there from the first frame). */
const ramp = (p: number, [a, b]: [number, number]) => (b > a ? clamp((p - a) / (b - a)) : p >= a ? 1 : 0);

export function attach(cfg: JourneyCfg, ctx: { section: HTMLElement; visual: HTMLElement }, video: HTMLVideoElement) {
  const sec = ctx.section;
  const track = sec.querySelector<HTMLElement>(".ss-track")!;
  const els = new Map<string, HTMLElement>();
  sec.querySelectorAll<HTMLElement>(".jy-stop").forEach((el) => els.set(el.dataset.stop!, el));
  const dots = new Map<string, HTMLElement>();
  sec.querySelectorAll<HTMLElement>(".jy-rail a").forEach((a) => dots.set(a.dataset.stop!, a));
  sec.classList.add("jy-live");

  const yOf = (p: number) => track.getBoundingClientRect().top + scrollY + p * (track.offsetHeight - innerHeight);
  const goTo = (p: number) => {
    const l = (window as any).__ssLenis;
    const y = yOf(p) + 1;
    if (l) l.scrollTo(y, { duration: 1.6 });
    else scrollTo({ top: y, behavior: "smooth" });
  };
  const stopOf = (id: string) => cfg.stops.find((s) => s.id === id);

  // the rail's links scroll to the stop's hold (captured before the page's own anchor handler, which would scroll to the
  // absolutely placed article instead)
  sec.querySelector(".jy-rail")?.addEventListener("click", (e) => {
    const a = (e.target as HTMLElement).closest<HTMLAnchorElement>("a[data-stop]");
    const s = a && stopOf(a.dataset.stop!);
    if (!s) return;
    e.preventDefault(); e.stopPropagation();
    goTo((s.p0 + s.p1) / 2);
  }, true);
  // keyboard: tabbing into a stop that is not on screen brings the page to it
  sec.addEventListener("focusin", (e) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>(".jy-stop");
    const s = el && stopOf(el.dataset.stop!);
    if (s && !el!.classList.contains("jy-on")) goTo((s.p0 + s.p1) / 2);
  });
  // a link to a stop (#hearth) lands on it
  const hash = decodeURIComponent(location.hash.slice(1));
  if (hash && stopOf(hash) && !new URLSearchParams(location.search).has("p")) setTimeout(() => goTo((stopOf(hash)!.p0 + stopOf(hash)!.p1) / 2), 400);

  let last = "";
  return {
    time: (p: number) => timeAt(cfg.map, p),
    update(p: number) {
      let cur = cfg.stops[0], best = 9;
      for (const s of cfg.stops) {
        const i = ramp(p, s.in), o = ramp(p, s.out);
        const el = els.get(s.id)!;
        const k = i * (1 - o);
        el.style.setProperty("--in", i.toFixed(3));
        el.style.setProperty("--out", o.toFixed(3));
        const on = k > 0.001;
        if (on !== el.classList.contains("jy-on")) el.classList.toggle("jy-on", on);
        const d = Math.abs(p - (s.p0 + s.p1) / 2);
        if (d < best) { best = d; cur = s; }
      }
      if (cur.id !== last) {
        last = cur.id;
        dots.forEach((a, id) => { a.classList.toggle("jy-here", id === cur.id); if (id === cur.id) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current"); });
      }
      // a portrait phone crops the wide picture: keep each stop's focus in view, travelling between them with the camera
      if (isMobile()) {
        let fx = 0.5, fy = 0.5;
        for (let i = 0; i < cfg.stops.length; i++) {
          const s = cfg.stops[i], f = s.focus || [0.5, 0.5];
          if (p >= s.p0 || i === 0) { fx = f[0]; fy = f[1]; }
          const n = cfg.stops[i + 1];
          if (n && p > s.p1 && p < n.p0) {
            const nf = n.focus || [0.5, 0.5], k = (p - s.p1) / (n.p0 - s.p1);
            fx = f[0] + (nf[0] - f[0]) * k; fy = f[1] + (nf[1] - f[1]) * k;
          }
        }
        video.style.objectPosition = `${(fx * 100).toFixed(1)}% ${(fy * 100).toFixed(1)}%`;
      } else if (video.style.objectPosition) video.style.objectPosition = "";
    },
  };
}
