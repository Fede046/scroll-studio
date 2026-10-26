/**
 * map: a non-interactive MapLibre map whose camera and routes follow scroll. Each step's `state`:
 * {center: [lng, lat], zoom, pitch, bearing, routes: {id: 0-1}}. Between steps the camera eases from the
 * previous state, dipping out when the two places are far apart (like flyTo, but scrubbable).
 */
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { PlayerFactory } from "../lib/types";
import { clamp, easeInOut, isMobile, lerp } from "../lib/util";

interface Cam { center: [number, number]; zoom: number; pitch: number; bearing: number; routes: Record<string, number> }

const factory: PlayerFactory = async (cfg, ctx) => {
  const el = document.createElement("div");
  Object.assign(el.style, { position: "absolute", inset: "0" });
  ctx.visual.appendChild(el);
  if (cfg.dark) el.style.filter = "brightness(.62) saturate(.55) contrast(1.08)";

  const steps = ctx.data.steps;
  const cams: Cam[] = [];
  let prev: Cam = { center: [0, 20], zoom: 1.5, pitch: 0, bearing: 0, routes: {} };
  for (const s of steps as any[]) {
    const st = s.state || {};
    const cur: Cam = { center: st.center ?? prev.center, zoom: st.zoom ?? prev.zoom, pitch: st.pitch ?? 0, bearing: st.bearing ?? 0,
      routes: { ...prev.routes, ...(st.routes || {}) } };
    cams.push(cur);
    prev = cur;
  }

  const map = new maplibregl.Map({
    container: el, style: cfg.style, interactive: false, attributionControl: { compact: true },
    center: cams[0]?.center ?? [0, 20], zoom: cams[0]?.zoom ?? 1.5, pitch: cams[0]?.pitch ?? 0, bearing: cams[0]?.bearing ?? 0,
    canvasContextAttributes: { preserveDrawingBuffer: true }, maxPitch: 75,
    // the whole flight is fetched while the page loads (below), so keep every tile it fetched, draw labels without a
    // fade-in, and never cancel a tile because the camera is zooming: scrolling then only ever draws cached tiles
    maxTileCacheSize: isMobile() ? 600 : 2000, maxTileCacheZoomLevels: 8, fadeDuration: 0,
    cancelPendingTileRequestsWhileZooming: false, refreshExpiredTiles: false,
  } as any);
  // icons the hosted style names but its sprite lacks (e.g. "circle-11"): a blank stands in, no console noise
  map.on("styleimagemissing", (e: any) => {
    if (!map.hasImage(e.id)) map.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) });
  });
  let ready = false;
  // each route is added once, whole, and drawn up to how far the scroll has got with a gradient on line-progress:
  // changing a paint property costs a repaint, where replacing the line's data every frame re-tiled it in the worker
  // and made the basemap lay itself out again (that, not the network, was what made the flight stutter)
  const hidden = "rgba(0,0,0,0)";
  const reveal = (color: string, f: number): any =>
    f >= 1 ? ["step", ["line-progress"], color, 1, color] : ["step", ["line-progress"], color, Math.max(1e-4, f), hidden];
  map.on("load", () => {
    for (const r of cfg.routes) {
      map.addSource(`route-${r.id}`, { type: "geojson", lineMetrics: true,
        data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: r.coords } } } as any);
      map.addLayer({ id: `route-${r.id}-glow`, type: "line", source: `route-${r.id}`, layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
        paint: { "line-gradient": reveal(r.color, 0), "line-width": 10, "line-opacity": 0.25, "line-blur": 6 } as any });
      map.addLayer({ id: `route-${r.id}`, type: "line", source: `route-${r.id}`, layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
        paint: { "line-gradient": reveal(r.color, 0), "line-width": 3.2 } as any });
    }
    for (const m of cfg.markers) {
      const dot = document.createElement("div");
      dot.className = "ss-map-marker";
      dot.innerHTML = `<i></i><span>${m.label}</span>`;
      new maplibregl.Marker({ element: dot, anchor: "left" }).setLngLat([m.lng, m.lat]).addTo(map);
    }
    ready = true;
  });
  const style = document.createElement("style");
  style.textContent = `
    .ss-map-marker { display: flex; align-items: center; gap: 8px; font-family: var(--font-mono); font-size: 11px; letter-spacing: .12em;
      text-transform: uppercase; color: #fff; text-shadow: 0 1px 6px rgba(0,0,0,.7); pointer-events: none; }
    .ss-map-marker i { width: 10px; height: 10px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 4px rgba(var(--accent-rgb), .3), 0 0 14px var(--accent); margin-left: -5px; }
    .maplibregl-ctrl-attrib { font-size: 10px; }`;
  ctx.visual.appendChild(style);

  // ready = style loaded and the first view's tiles drawn (capped, so a slow tile server can't block the page)
  // (polls tile state instead of waiting for "idle", which also needs painting and stalls in background tabs)
  await new Promise<void>((resolve) => {
    const t0 = performance.now();
    const check = () => {
      if ((map.isStyleLoaded() && map.areTilesLoaded()) || performance.now() - t0 > 12000) return resolve();
      setTimeout(check, 150);
    };
    map.once("load", check);
  });
  ctx.progress(0.5);

  const drawn: Record<string, number> = {};

  // the camera at step k, `t` (0-1) of the way from the step before: exactly what update() shows
  const camAt = (k: number, t: number) => {
    const a = cams[Math.max(0, k - 1)], b = cams[k];
    const far = Math.hypot(b.center[0] - a.center[0], b.center[1] - a.center[1]);
    const dip = Math.min(4, Math.log2(1 + far / 4)) * Math.sin(Math.PI * t);
    let db = b.bearing - a.bearing;
    if (db > 180) db -= 360; else if (db < -180) db += 360;
    // keep the subject clear of the text cards: shift the camera's centre into the open side
    const w = el.clientWidth, cards = ctx.data.layout === "cards" && !isMobile();
    const left = ctx.section.className.includes("ss-side-left");
    return {
      padding: cards ? { left: left ? 0 : w * 0.36, right: left ? w * 0.36 : 0, top: 0, bottom: 0 } : { left: 0, right: 0, top: 0, bottom: 0 },
      center: [lerp(a.center[0], b.center[0], t), lerp(a.center[1], b.center[1], t)] as [number, number],
      zoom: lerp(a.zoom, b.zoom, t) - dip,
      pitch: lerp(a.pitch, b.pitch, t), bearing: a.bearing + db * t,
    };
  };

  // Preload the flight: while the loading screen is up, walk the camera along the path the scroll will take and wait
  // for each view's tiles, so scrolling never waits on the network. Capped per view and in total, so a slow tile
  // server costs a few seconds of loading, never a blocked page.
  // a view's tiles are in once the map has drawn the new camera (so it has asked for them) and none are pending
  const tilesIn = (cap: number) => new Promise<boolean>((resolve) => {
    const t0 = performance.now();
    let drawn = false;
    map.once("render", () => { drawn = true; });
    map.triggerRepaint();
    const check = () => {
      if (drawn && map.areTilesLoaded()) return resolve(true);
      if (performance.now() - t0 > cap) return resolve(false);
      setTimeout(check, 60);
    };
    setTimeout(check, 60);
  });
  const report = { views: 0, loaded: 0, slow: 0, ms: 0 };   // what the preload did (read by recordings and checks)
  (window as any).__ssMapPreload = report;
  if (cams.length) {
    const views: [number, number][] = [];
    // each move: the far point of the dip (low zoom, cheap) and the arrival, plus the quarters on a long move
    for (let k = 0; k < cams.length; k++) {
      if (k === 0) { views.push([0, 1]); continue; }
      const far = Math.hypot(cams[k].center[0] - cams[k - 1].center[0], cams[k].center[1] - cams[k - 1].center[1]);
      if (far > 8) views.push([k, 0.5]);       // the far point of a long move's dip (low zoom, cheap)
      views.push([k, 1]);
    }
    report.views = views.length;
    const t0 = performance.now(), budget = isMobile() ? 6000 : 10000;
    for (let i = 0; i < views.length; i++) {
      if (performance.now() - t0 > budget) break;
      map.jumpTo(camAt(...views[i]));
      if (await tilesIn(2000)) report.loaded++; else report.slow++;
      ctx.progress(0.5 + 0.5 * (i + 1) / views.length);
    }
    map.jumpTo(camAt(0, 0));
    await tilesIn(5000);
    report.ms = Math.round(performance.now() - t0);
  }

  return {
    resize: () => map.resize(),
    update(s) {
      if (!ready || !cams.length) return;
      let k = 0;
      for (let i = 0; i < steps.length; i++) if ((s.steps[i] ?? 0) > 0) k = i;
      const a = cams[Math.max(0, k - 1)], b = cams[k];
      map.jumpTo(camAt(k, easeInOut(clamp((s.steps[k] ?? 0) / 0.7))));
      for (const r of cfg.routes) {
        const f = lerp(a.routes[r.id] ?? 0, b.routes[r.id] ?? 0, clamp((s.steps[k] ?? 0) / 0.85));
        if (Math.abs((drawn[r.id] ?? -1) - f) < 1e-4) continue;
        drawn[r.id] = f;
        for (const id of [`route-${r.id}`, `route-${r.id}-glow`]) {
          map.setLayoutProperty(id, "visibility", f > 0 ? "visible" : "none");
          if (f > 0) map.setPaintProperty(id, "line-gradient", reveal(r.color, f));
        }
      }
    },
  };
};
export default factory;
