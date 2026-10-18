/** Shared shapes for the cut runtime (cuts.ts and its match/carry parts). */

/** Where a shape sits on one side of a match cut: a box in the picture's own 0-1 coordinates (mapped to the screen the
 * way the picture is fitted), or a page element measured in the browser. */
export interface Anchor {
  box?: [number, number, number, number];
  /** width / height of the picture the box is in */
  aspect?: number;
  fit?: "cover" | "contain";
  /** extra scale the section's player applies about the picture's centre at this end (a slow dolly) */
  scale?: number;
  /** CSS selector (inside the section's pin) of the element the picture fills; default: the section's visual */
  of?: string;
  /** a page element instead of a picture */
  sel?: string;
}

export interface CutCfg {
  n: number; a: number; b: number; type: string; length: number; label: string;
  at?: number; hold?: number; direction?: "left" | "right" | "up" | "down"; angle?: number; soft?: number; origin?: [number, number];
  closing?: boolean; blur?: number; zoom?: number; blend?: number;
  anchors?: { a?: Anchor; b?: Anchor };
  carry?: { from: string; to: string; via: string };
}

export interface Cut {
  cfg: CutCfg;
  wIn: HTMLElement; wOut: HTMLElement; pinA: HTMLElement; pinB: HTMLElement; gap: HTMLElement;
  secA: HTMLElement | null; secB: HTMLElement | null;
  state: string; k: number;
  /** viewport top and height of the pinned section above, measured with the cut's own styles off */
  topA: number; hA: number;
  live: string;
  /** elements a cut has styled besides the two pins, to be cleared when it ends */
  touched?: Set<HTMLElement>;
  /** per-activation scratch: what match and carry measured */
  data: any;
}

/** What one layer (a pin) looks like at a moment of the cut. */
export interface Layer {
  /** false: out of the picture (and out of reach) */
  vis?: boolean;
  t?: string; o?: number; clip?: string;
  mask?: string; maskSize?: string; maskPos?: string;
  /** directional blur, standard deviation in px along x and y */
  blur?: [number, number];
  origin?: string;
  /** a part of the section that moves on its own (the picture of a match cut) */
  inner?: { el: HTMLElement; t: string; origin: string };
  /** parts of the section faded to this opacity (the words, while a match cut scales the picture) */
  fade?: { els: HTMLElement[]; o: number };
}

export interface Metrics { W: number; H: number; small: boolean }

export interface FxResult { a: Layer; b: Layer; live: "a" | "b" | ""; front?: "a" | "b" }
export type Fx = (k: number, c: Cut, m: Metrics) => FxResult;
export interface Helpers { ease: (x: number) => number; win: (k: number, a: number, b: number) => number }
