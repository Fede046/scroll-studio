/** sequence and inside: pre-rendered frames drawn to a canvas (Apple-style product scrolls, flights inside a product).
 *
 * Every frame is downloaded and decoded to an ImageBitmap before the page unlocks, so drawing never stalls.
 * Between two rendered frames the canvas cross-fades by the fractional scroll position, which turns a
 * 96-frame render into continuous motion instead of visible steps.
 *
 * With reduced motion, a scene that has stops (`inside`) shows one still per stop instead of the flight: the opening
 * frame, each stop's resting frame (switched when its copy arrives), and the closing frame, with no cross-fade, so
 * only those frames are downloaded. */
import type { PlayerFactory } from "../lib/types";
import { follow, isMobile, loadBitmap, reducedMotion } from "../lib/util";

type Frame = ImageBitmap | HTMLImageElement;

const factory: PlayerFactory = async (cfg, ctx) => {
  const set = isMobile() && cfg.mobile ? cfg.mobile : cfg.desktop;
  const count: number = cfg.count;
  const canvas = document.createElement("canvas");
  ctx.visual.appendChild(canvas);
  ctx.visual.style.background = cfg.background || "transparent";
  const g = canvas.getContext("2d", { alpha: true })!;
  g.imageSmoothingQuality = "high";
  const url = (i: number) => `${set.base}${String(i + 1).padStart(4, "0")}.${set.ext}`;
  const frames: (Frame | null)[] = new Array(count).fill(null);

  // Reduced motion: one still per stop (the stop's copy window starts at `at[0]`), the opening and the closing frame.
  const stops: { frame: number; at: [number, number] }[] = Array.isArray(cfg.stops) ? cfg.stops : [];
  const stills = reducedMotion && stops.length > 0
    ? [{ frame: 0, from: 0 }, ...stops.map((st) => ({ frame: st.frame, from: st.at[0] })), { frame: count - 1, from: Math.max(...stops.map((st) => st.at[1])) }]
    : null;

  // Load everything, 8 at a time, in an order that fills the timeline evenly (every 16th, then 8th, ...).
  const order: number[] = [];
  if (stills) { for (const st of stills) if (!order.includes(st.frame)) order.push(st.frame); }
  else for (let step = 16; step >= 1; step /= 2) for (let i = 0; i < count; i += step) if (!order.includes(i)) order.push(i);
  let done = 0;
  await new Promise<void>((resolve) => {
    let next = 0, active = 0;
    const pump = () => {
      while (active < 8 && next < order.length) {
        const i = order[next++];
        active++;
        loadBitmap(url(i)).then((b) => { frames[i] = b; }).catch(() => {}).finally(() => {
          active--; done++;
          ctx.progress(done / order.length);
          if (done === order.length) resolve(); else pump();
        });
      }
    };
    pump();
  });

  let dpr = 1;
  function resize() {
    dpr = Math.min(devicePixelRatio || 1, 2);
    const r = canvas.getBoundingClientRect();
    canvas.width = Math.round(r.width * dpr);
    canvas.height = Math.round(r.height * dpr);
    last = -1;
  }
  let last = -1, cur = 0;
  resize();
  const size = (f: Frame) => [(f as any).width || (f as HTMLImageElement).naturalWidth, (f as any).height || (f as HTMLImageElement).naturalHeight];
  function draw(f: Frame, alpha: number, idx: number) {
    const cw = canvas.width, ch = canvas.height, [fw, fh] = size(f);
    const fit = cfg.fit === "contain" ? Math.min : Math.max;
    let k = fit(cw / fw, ch / fh), x = (cw - fw * k) / 2, y = (ch - fh * k) / 2;
    if (Array.isArray(cfg.off) && cw < ch) {
      // inside, on a phone: the subject sits off-centre in the frame (for the copy), so pan the crop to it; the wide
      // shots (off near 0.5) are drawn smaller so the whole product is in view
      const o = cfg.off[idx] ?? 1, wide = Math.max(0, Math.min(1, (1 - o) / 0.5));
      const cover = Math.max(cw / fw, ch / fh), kw = Math.min(cover, (cw * 0.94) / (fw * (cfg.wideFill || 0.8)));
      k = cover + (kw - cover) * wide;
      x = cw / 2 - (0.5 + (cfg.offset || 0) * o) * fw * k;
      y = (ch - fh * k) / 2;
    }
    const shift = isMobile() ? 0 : (cfg.shift || 0) * cw;
    g.globalAlpha = alpha;
    g.drawImage(f as CanvasImageSource, x + shift, y, fw * k, fh * k);
  }

  return {
    resize,
    update(s) {
      if (stills) {
        let pick = stills[0];
        for (const st of stills) if (s.p >= st.from) pick = st;
        const f = frames[pick.frame];
        if (!f || pick.frame === last) return;
        last = pick.frame;
        g.clearRect(0, 0, canvas.width, canvas.height);
        draw(f, 1, pick.frame);
        return;
      }
      cur += (s.p * (count - 1) - cur) * follow;
      if (Math.abs(cur - last) < 0.002) return;
      last = cur;
      const i = Math.min(count - 1, Math.floor(cur)), t = cur - i;
      const a = frames[i], b = frames[Math.min(count - 1, i + 1)];
      if (!a) return;
      g.clearRect(0, 0, canvas.width, canvas.height);
      draw(a, 1, i);
      if (b && b !== a && t > 0.01) draw(b, t, Math.min(count - 1, i + 1));
      g.globalAlpha = 1;
    },
  };
};
export default factory;
