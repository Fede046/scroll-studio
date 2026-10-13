/**
 * stage: someone comes into the light. The markup (engine/compile/templates/scene.html.j2, `stage`) holds every
 * word; this only moves the light. The scroll runs through:
 *   lines     one per screen, each set heavier than the last, the figure a little more lit each time
 *   platform  a stage rises under them, and the second half of the line comes up with it
 *   turn      the view swings round behind them to face the follow-spot, and the name comes up
 *   flood     the spot's light fills the screen; the page goes on in that light
 * Reduced motion keeps the same beats as fades (no movement).
 */
import type { PlayerFactory } from "../lib/types";
import { clamp, hexToRgb, reducedMotion, smooth } from "../lib/util";

const LINE = 1, PLATFORM = 1.3, TURN = 1.3, FLOOD = 1.1, HOLD = 0.7;   // share of the scroll, in lines

const factory: PlayerFactory = async (cfg, ctx) => {
  const el = ctx.section;
  const q = <T extends Element = HTMLElement>(s: string) => el.querySelector(s) as T;
  const front = q(".st-front"), back = q(".st-back"), flood = q(".st-flood");
  const upstage = q(".st-upstage"), pool = q(".st-pool"), actor = q(".st-actor"), riser = q<SVGSVGElement>(".st-riser");
  const rimFront = q<SVGSVGElement>(".st-fig--front .st-rim"), rimBack = q<SVGSVGElement>(".st-fig--back .st-rim");
  const shapeFront = q<SVGSVGElement>(".st-fig--front .st-shape"), mark = q(".st-mark"), lamp = q(".st-lamp"), beam = q(".st-beam");
  const title = q(".st-title"), special = q(".st-special");
  const lines = [...el.querySelectorAll<HTMLElement>(".st-line")];
  const platEm = [...el.querySelectorAll<HTMLElement>(".st-line--platform em")];
  const name = q(".st-name"), body = el.querySelector<HTMLElement>(".st-body"), btns = el.querySelector<HTMLElement>(".st-btns");
  const nav = document.getElementById("ss-nav");
  const n = cfg.lines as number, plat = cfg.platform ? PLATFORM : 0;
  const turnAt = n * LINE + plat, floodAt = turnAt + TURN, total = floodAt + FLOOD + HOLD;
  const [w0, w1] = cfg.weights as [number, number];
  const light = hexToRgb(cfg.light).map((v) => v * 255), ink = hexToRgb(cfg.ink).map((v) => v * 255);
  const mo = reducedMotion ? 0 : 1;
  let lift = 0;
  const measure = () => { lift = riser.getBoundingClientRect().height - innerHeight * 0.016; };
  el.classList.add("st-live");
  measure();

  // every line is set at its own weight once: the first thin and faint, the last (or the platform) the heaviest
  lines.forEach((ln, i) => {
    const k = lines.length > 1 ? i / (lines.length - 1) : 1;
    ln.style.fontWeight = String(Math.round(w0 + (w1 - w0) * k));
    ln.style.setProperty("--st-k", String(k));
  });
  name.style.fontWeight = String(w1);

  let onStage = false;
  const update = (p: number) => {
    const u = p * total;
    // 1. lines: in, held, out; the platform line stays until the turn
    lines.forEach((ln, i) => {
      const a = i * LINE, isPlat = cfg.platform && i === lines.length - 1;
      const kin = i === 0 ? 1 : smooth(a, a + 0.28, u);
      const kout = isPlat ? smooth(turnAt + 0.05, turnAt + 0.4, u) : smooth(a + LINE - 0.2, a + LINE, u);
      const k = lines.length > 1 ? i / (lines.length - 1) : 1;
      ln.style.opacity = String(kin * (1 - kout) * (0.5 + 0.5 * k));
      ln.style.transform = `translate3d(0, ${mo * ((1 - kin) * 22 - kout * 22)}px, 0)`;
      ln.style.visibility = kin * (1 - kout) > 0.002 ? "visible" : "hidden";
    });
    // 2. light on the figure: from a hint of an outline to fully lit from upstage
    const lit = 0.08 + 0.62 * clamp(u / Math.max(1, n * LINE)) + (plat ? 0.3 * smooth(n * LINE, turnAt, u) : 0.3 * smooth(n * LINE - 1, n * LINE, u));
    upstage.style.opacity = String(Math.pow(lit, 1.4));
    rimFront.style.opacity = String(clamp(lit * 1.15));
    shapeFront.style.opacity = String(smooth(0.06, 0.55, lit));   // a shape only once there is light behind it
    pool.style.opacity = String(0.9 * smooth(0.35, 1, lit));
    // 3. the platform rises under them
    const up = plat ? smooth(n * LINE + 0.1, n * LINE + plat * 0.75, u) : 0;
    actor.style.transform = `translateX(-50%) translate3d(0, ${-lift * up}px, 0)`;
    riser.style.opacity = String(plat ? smooth(n * LINE, n * LINE + 0.3, u) : 0);
    platEm.forEach((em) => { em.style.opacity = String(smooth(n * LINE + 0.45, n * LINE + plat * 0.85, u)); });
    // 4. the turn: round behind them, facing the light
    const t = smooth(turnAt, floodAt, u);
    // a moment of dark between the two shots, like a cut on a blackout: the spot comes up first, then them
    front.style.opacity = String(1 - smooth(0.05, 0.42, t));
    front.style.transform = `translate3d(${mo * -18 * t}vw, 0, 0)`;   // a swing, not a zoom: scaling soft light makes the browser redraw it every frame
    back.style.opacity = String(smooth(0.42, 0.7, t));
    back.style.transform = `translate3d(${mo * 14 * (1 - t)}vw, 0, 0)`;
    mark.style.opacity = String(smooth(0.6, 0.92, t));
    special.style.opacity = String(smooth(0.72, 1, t));
    rimBack.style.opacity = String(smooth(0.6, 1, t));
    const kn = smooth(0.5, 1, t);
    // 5. the light floods the screen
    const f = smooth(floodAt, floodAt + FLOOD, u);
    // the spot blooms and the room fills with its light
    const bright = smooth(0.2, 0.85, f);
    flood.style.opacity = String(bright);
    lamp.style.transform = `translate(-50%, -50%) scale(${1 + mo * 3 * smooth(0, 0.75, f)})`;
    beam.style.opacity = String(1 - f);
    mark.style.transform = `translateX(-50%) translate3d(0, ${mo * f * 10}vh, 0)`;
    title.style.transform = `translate3d(0, ${mo * smooth(0.3, 1, f) * 12}vh, 0)`;   // the name settles to the middle in the light
    name.style.opacity = String(kn);
    name.style.transform = `translate3d(0, ${mo * (1 - kn) * 26}px, 0)`;
    const c = smooth(0.38, 0.62, bright);   // the name turns to ink as the room passes mid-grey
    name.style.color = `rgb(${light.map((v, i) => Math.round(v + (ink[i] - v) * c)).join(",")})`;
    const kb = smooth(0.55, 1, f);
    for (const x of [body, btns]) {
      if (!x) continue;
      x.style.opacity = String(kb);
      x.style.transform = `translate3d(0, ${mo * (1 - kb) * 18}px, 0)`;
      x.style.visibility = kb > 0.01 ? "visible" : "hidden";
    }
    // the nav reads on the dark stage, and goes back to the page's colours once the light is in
    const r = el.getBoundingClientRect();
    const dark = r.top <= 1 && r.bottom > 80 && f < 0.5;
    if (dark !== onStage) { onStage = dark; nav?.classList.toggle("ss-surface-dark", dark); }
  };
  return { update: (s) => update(s.p), resize: measure };
};
export default factory;
