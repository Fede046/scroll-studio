/**
 * Film helpers shared by the players that draw a film themselves in WebGL (world: type in the world): a muted video that
 * is scrubbed rather than played, loaded completely first, and a group of videos that are seeked to the middle of the same
 * frame and only drawn when every one of them has landed there (so an atlas frame is never drawn over a different film frame).
 */
import { fetchBlobURL } from "./util";

export function makeVideo(): HTMLVideoElement {
  const v = document.createElement("video");
  v.muted = true; v.playsInline = true; v.preload = "auto";
  return v;
}

export async function loadVideo(v: HTMLVideoElement, url: string, onProgress: (f: number) => void): Promise<void> {
  try { v.src = await fetchBlobURL(url, onProgress, "video/mp4"); } catch { v.src = url; }
  await new Promise<void>((resolve) => {
    if (v.readyState >= 2) return resolve();
    v.addEventListener("loadeddata", () => resolve(), { once: true });
    v.addEventListener("error", () => resolve(), { once: true });
  });
}

export class PairedSeeker {
  busy = false;
  shown = -1;
  private id = 0;
  private timer = 0;
  constructor(private videos: HTMLVideoElement[], private fps: number, private onLanded: (frame: number) => void) {}

  seek(frame: number): void {
    this.busy = true;
    const id = ++this.id;
    let finished = false;
    const t = (frame + 0.5) / this.fps;
    let pending = this.videos.length;
    const finish = () => {
      if (finished || id !== this.id) return;
      finished = true; clearTimeout(this.timer);
      this.busy = false; this.shown = frame;
      this.onLanded(frame);
    };
    const landed = () => { if (--pending <= 0) finish(); };
    this.timer = window.setTimeout(finish, 800);      // never deadlock on a seek that does not report
    for (const v of this.videos) {
      if (Math.abs(v.currentTime - t) < 1e-4) { queueMicrotask(landed); continue; }
      v.addEventListener("seeked", landed, { once: true });
      v.currentTime = t;
    }
  }
}
