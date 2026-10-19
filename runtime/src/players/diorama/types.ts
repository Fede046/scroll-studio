export interface PropRec {
  k: string; x: number; y: number; z: number; r: number; s: number; v: number;
  c?: string[]; text?: string; wall?: string; place?: number; len?: number;
}
export interface PlaceRec { name: string; kind: string; x: number; y: number; z: number; yaw: number; h: number; r: number; sign: string }
export interface Beat {
  kind: "wide" | "place"; place?: number; yaw: number; pitch: number; dist: number | null;
  target: [number, number, number]; side: number; a: number; b: number;
}
export interface CameraPlan { fov: number; pitch: number; dive_pitch: number; hold: number; drift: number; fit: number; beats: Beat[] }
export interface Plan {
  v: number; kind: string; size: number; base: "round" | "square"; table: string;
  water: { level: number; has: boolean }; grid: number; heights: number[];
  palette?: string[]; edge?: Record<string, string> | null;
  props: PropRec[]; places: PlaceRec[]; steps: (number | null)[]; camera: CameraPlan;
}
export interface DioramaCfg {
  plan: string; ground: string; poster?: string; map?: string;
  look: { tilt_shift: number; saturation: number; sun: string; table: string; grain: number; vignette: number };
  side: number; layout: string; credits?: string[];
}
