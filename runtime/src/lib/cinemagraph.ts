/**
 * Cinemagraphs: a still where only one thing moves. The compiler marks every place a cinemagraph's still is shown
 * (an <img>, or an element with it as a CSS background) with data-cine="{v, m, b, r}": the video (v) of the part that
 * moves, the soft mask (m) it is shown through, where it sits on the still (b: x, y, w, h as fractions) and the still's
 * aspect ratio (r). The still stays in the page. This lays the video over it, through the mask, so wherever the mask is
 * zero the picture is the still's own pixels and cannot change.
 *
 *   plays when in view, pauses off screen (and in a hidden tab); loads when it is a screen away, not before
 *   prefers-reduced-motion, data saver, a 2G connection, no CSS mask support: the still, nothing else
 *   never touches layout (the video is an absolutely positioned layer beside the image) and never joins the scroll's frame
 *   work except to copy the image's own transform (a hero's slow zoom) while it is on screen
 *
 * Every page is complete without this file.
 */
type Entry = { v: string; m: string; b: [number, number, number, number]; r: number; fps?: number };
type Item = {
  host: HTMLElement; e: Entry; layer: HTMLElement; video: HTMLVideoElement | null; img: boolean;
  near: boolean; seen: boolean; state: "idle" | "loading" | "playing" | "paused" | "failed"; tf: string; op: string;
};

const reduced = matchMedia("(prefers-reduced-motion: reduce)");

function slowConnection(): boolean {
  const c = (navigator as unknown as { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  return !!c && (!!c.saveData || /(^|-)2g$/.test(c.effectiveType || ""));
}

const canMask = () => CSS.supports("mask-image", "url(x.webp)") || CSS.supports("-webkit-mask-image", "url(x.webp)");

/** The rectangle the still occupies inside its host's box (px, relative to the box), by object-fit / background-size. */
function stillRect(item: Item): { x: number; y: number; w: number; h: number } | null {
  const { host, e } = item;
  const cs = getComputedStyle(host);
  const W = item.img ? host.offsetWidth : host.clientWidth, H = item.img ? host.offsetHeight : host.clientHeight;
  if (!W || !H) return null;
  const fit = item.img ? cs.objectFit : cs.backgroundSize;
  const pos = (item.img ? cs.objectPosition : cs.backgroundPosition).split(/\s+/);
  const px = parsePos(pos[0] ?? "50%"), py = parsePos(pos[1] ?? pos[0] ?? "50%");
  let w: number, h: number;
  if (fit === "cover") { const s = Math.max(W / e.r, H) ; h = s; w = s * e.r; }
  else if (fit === "contain" || fit === "scale-down") { const s = Math.min(W / e.r, H); h = s; w = s * e.r; }
  else if (fit === "fill" || fit === "100% 100%") { w = W; h = H; }
  else return null;                                   // a size this does not know: leave the still alone
  return { x: (W - w) * px, y: (H - h) * py, w, h };
}

function parsePos(v: string): number {
  if (v === "left" || v === "top") return 0;
  if (v === "right" || v === "bottom") return 1;
  if (v === "center") return 0.5;
  const n = parseFloat(v);
  return Number.isFinite(n) ? n / 100 : 0.5;
}

export function start(): void {
  const hosts = [...document.querySelectorAll<HTMLElement>("[data-cine]")];
  if (!hosts.length || !canMask() || reduced.matches || slowConnection()) return;

  const items: Item[] = [];
  for (const host of hosts) {
    let e: Entry;
    try { e = JSON.parse(host.dataset.cine || ""); } catch { continue; }
    if (!e.v || !e.m || !e.b || !e.r) continue;
    const img = host instanceof HTMLImageElement;
    const layer = document.createElement("div");
    layer.setAttribute("aria-hidden", "true");
    layer.className = "ss-cine";
    layer.style.cssText = "position:absolute;overflow:hidden;pointer-events:none;display:none;contain:strict";
    if (img) {
      host.insertAdjacentElement("afterend", layer);
      const z = getComputedStyle(host).zIndex;
      if (z !== "auto") layer.style.zIndex = z;
    } else {
      // a background: the layer is the first child, behind the section's content, over its background
      if (getComputedStyle(host).position === "static") host.style.position = "relative";
      host.style.isolation = "isolate";
      layer.style.inset = "0";
      layer.style.zIndex = "-1";
      host.prepend(layer);
    }
    items.push({ host, e, layer, video: null, img, near: false, seen: false, state: "idle", tf: "", op: "" });
  }
  if (!items.length) return;
  (window as unknown as { __ssCine: Item[] }).__ssCine = items;

  // ---- framing: a photograph cropped to fill a narrow screen (object-fit: cover) can crop the moving part away. Slide the crop
  // (object-position / background-position) so it stays in view: the one thing that moves is the point of the picture.
  function frame(it: Item) {
    const r = stillRect(it);
    if (!r) return;
    const { host, e } = it;
    const W = it.img ? host.offsetWidth : host.clientWidth, H = it.img ? host.offsetHeight : host.clientHeight;
    const pos: number[] = [];
    let moved = false;
    for (const [axis, size, span, b0, bw] of [[0, W, r.w, e.b[0], e.b[2]], [1, H, r.h, e.b[1], e.b[3]]] as [number, number, number, number, number][]) {
      const cur = axis === 0 ? r.x : r.y;
      const lo = cur + b0 * span, hi = cur + (b0 + bw) * span;
      const visible = Math.max(0, Math.min(hi, size) - Math.max(lo, 0)) / Math.max(1, hi - lo);
      let p = span > size ? cur / (size - span) : 0.5;                    // where the crop is now, as a 0-1 position
      if (span > size + 1 && visible < 0.75) {
        const centre = b0 + bw / 2;
        p = Math.min(1, Math.max(0, (size / 2 - centre * span) / (size - span)));
        moved = true;
      }
      pos.push(Math.round(p * 1000) / 10);
    }
    if (!moved) return;
    const css = `${pos[0]}% ${pos[1]}%`;
    if (it.img) host.style.objectPosition = css; else host.style.backgroundPosition = css;
  }

  // ---- layout: the layer takes the still's box; the video sits where the moving part is on the still
  function layout(it: Item) {
    frame(it);
    const r = stillRect(it);
    if (!r) { it.layer.style.display = "none"; return; }
    const { host, layer, e } = it;
    const cs = getComputedStyle(host);
    if (it.img) {
      layer.style.left = host.offsetLeft + "px"; layer.style.top = host.offsetTop + "px";
      layer.style.width = host.offsetWidth + "px"; layer.style.height = host.offsetHeight + "px";
      layer.style.borderRadius = cs.borderRadius;
      layer.style.transformOrigin = cs.transformOrigin;
      layer.style.clipPath = cs.clipPath === "none" ? "" : cs.clipPath;
    }
    layer.style.display = "block";
    if (it.video) {
      const v = it.video.style;
      v.left = (r.x + e.b[0] * r.w).toFixed(2) + "px"; v.top = (r.y + e.b[1] * r.h).toFixed(2) + "px";
      v.width = (e.b[2] * r.w).toFixed(2) + "px"; v.height = (e.b[3] * r.h).toFixed(2) + "px";
    }
    it.tf = ""; it.op = "";            // re-copy the image's own transform and opacity on the next frame
  }

  function load(it: Item) {
    if (it.video || it.state === "failed") return;
    const v = document.createElement("video");
    v.muted = true; v.loop = true; v.playsInline = true; v.preload = "auto"; v.controls = false;
    v.setAttribute("muted", ""); v.setAttribute("playsinline", ""); v.setAttribute("aria-hidden", "true"); v.tabIndex = -1;
    v.disablePictureInPicture = true;
    const m = `url("${it.e.m}")`;
    v.style.cssText = `position:absolute;opacity:0;transition:opacity .9s ease;pointer-events:none;-webkit-mask-image:${m};mask-image:${m};` +
      "-webkit-mask-size:100% 100%;mask-size:100% 100%;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;object-fit:fill";
    v.src = it.e.v;
    v.addEventListener("error", () => { it.state = "failed"; v.remove(); it.video = null; });
    v.addEventListener("playing", () => {
      it.state = "playing";
      // fade in once a frame is really on screen, so there is never a blank video over the still
      const show = () => { v.style.opacity = "1"; };
      if ("requestVideoFrameCallback" in v) (v as HTMLVideoElement & { requestVideoFrameCallback: (cb: () => void) => void }).requestVideoFrameCallback(show);
      else show();
    });
    it.layer.appendChild(v);
    it.video = v;
    it.state = "loading";
    layout(it);
  }

  function sync(it: Item) {
    const v = it.video;
    if (!v || it.state === "failed") return;
    const want = it.seen && !document.hidden && !reduced.matches;
    if (want && v.paused) v.play().catch(() => { /* low-power mode, or autoplay refused: the still stays */ });
    else if (!want && !v.paused) { v.pause(); if (it.state === "playing") it.state = "paused"; }
  }

  // ---- when to load and when to play
  const nearIO = new IntersectionObserver((es) => {
    for (const en of es) {
      const it = items.find((i) => i.host === en.target)!;
      it.near = en.isIntersecting;
      if (it.near) load(it);
    }
  }, { rootMargin: "100% 0px 100% 0px" });
  let kick = () => {};
  const seenIO = new IntersectionObserver((es) => {
    for (const en of es) {
      const it = items.find((i) => i.host === en.target)!;
      it.seen = en.isIntersecting;
      if (it.seen) load(it);
      sync(it);
    }
    kick();
  }, { rootMargin: "0px" });
  for (const it of items) { nearIO.observe(it.host); seenIO.observe(it.host); }

  const relayout = () => items.forEach(layout);
  const ro = new ResizeObserver(relayout);
  items.forEach((it) => { ro.observe(it.host); if (it.img) (it.host as HTMLImageElement).addEventListener("load", relayout); });
  addEventListener("resize", relayout, { passive: true });

  document.addEventListener("visibilitychange", () => items.forEach(sync));
  reduced.addEventListener("change", () => items.forEach((it) => {
    sync(it);
    if (reduced.matches && it.video) it.video.style.opacity = "0";    // back to the still
  }));

  // ---- the still's own transform (a hero's slow zoom, a drift) is copied to the layer while it is on screen
  let running = false;
  function follow() {
    let any = false;
    for (const it of items) {
      if (!it.img || !it.seen || it.state === "failed") continue;
      any = true;
      const cs = getComputedStyle(it.host);
      if (cs.transform !== it.tf) { it.tf = cs.transform; it.layer.style.transform = it.tf === "none" ? "" : it.tf; }
      if (cs.opacity !== it.op) { it.op = cs.opacity; it.layer.style.opacity = it.op; }
    }
    if (any) requestAnimationFrame(follow); else running = false;      // nothing on screen: no work at all
  }
  kick = () => { if (!running) { running = true; requestAnimationFrame(follow); } };
}
