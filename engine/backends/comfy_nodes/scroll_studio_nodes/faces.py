"""Face restoration for generated video: GFPGAN v1.4 (Apache-2.0, architecture vendored in gfpgan_arch/) on faces found
and aligned by facexlib (MIT; RetinaFace detection, ParseNet face mask).

Per frame: every face above `min_face` pixels is cut out and aligned to 512x512, restored, and pasted back through the
inverse of that alignment with facexlib's soft face mask. Flicker is held down in the aligned space (where a moving face
is stable): the change GFPGAN makes to a face (restored minus input) is smoothed over the frames that face has been
tracked for, then scaled by `strength` and applied to the current frame's own crop. A face that is found for the first time
fades its repair in over a few frames, so nothing pops.
"""
from __future__ import annotations

import os
import time

import numpy as np
import torch

import folder_paths

_DET = "retinaface_resnet50"


def _model_path(name: str) -> str:
    for d in folder_paths.get_folder_paths("facerestore_models") if "facerestore_models" in folder_paths.folder_names_and_paths else []:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    p = os.path.join(folder_paths.models_dir, "facerestore_models", name)
    if not os.path.exists(p):
        raise FileNotFoundError(f"{p} is missing: download GFPGANv1.4.pth (https://github.com/TencentARC/GFPGAN/releases/tag/v1.3.4) "
                                "into ComfyUI/models/facerestore_models/ (see engine/models.yaml)")
    return p


def _load_gfpgan(name: str, device):
    from .gfpgan_arch.gfpganv1_clean_arch import GFPGANv1Clean
    net = GFPGANv1Clean(out_size=512, num_style_feat=512, channel_multiplier=2, decoder_load_path=None, fix_decoder=False,
                        num_mlp=8, input_is_latent=True, different_w=True, narrow=1, sft_half=True)
    sd = torch.load(_model_path(name), map_location="cpu", weights_only=True)
    net.load_state_dict(sd.get("params_ema") or sd["params"], strict=True)
    return net.eval().to(device)


def restore_batch(images: torch.Tensor, model_name: str, strength: float, min_face: int, smooth: float, pbar):
    """images: (N, H, W, 3) float 0-1 RGB. Returns the repaired frames (same shape) and a mask of where they changed."""
    import cv2
    import comfy.model_management as mm
    from facexlib.utils.face_restoration_helper import FaceRestoreHelper
    device = mm.get_torch_device()
    net = _load_gfpgan(model_name, device)
    helper = FaceRestoreHelper(1, face_size=512, crop_ratio=(1, 1), det_model=_DET, save_ext="png", use_parse=True, device=device)
    out = torch.empty_like(images)
    changed = torch.zeros(images.shape[:3])
    T = {"detect": 0.0, "restore": 0.0, "paste": 0.0}
    tracks: list[dict] = []          # {"c": centre, "size": px, "delta": smoothed change in aligned space, "age": frames}
    for i in range(len(images)):
        bgr = cv2.cvtColor((images[i].numpy() * 255 + 0.5).clip(0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
        helper.clean_all()
        helper.read_image(bgr)
        t0 = time.perf_counter()
        n = helper.get_face_landmarks_5(only_center_face=False, resize=640, eye_dist_threshold=5)
        T["detect"] += time.perf_counter() - t0
        used, fresh, todo = set(), [], []
        if n:
            helper.align_warp_face()
            for k, crop in enumerate(helper.cropped_faces):
                box = np.asarray(helper.det_faces[k], dtype=np.float32)
                size = float(min(box[2] - box[0], box[3] - box[1]))
                lm = np.asarray(helper.all_landmarks_5[k], dtype=np.float32)
                centre = lm.mean(axis=0)
                if size < min_face:
                    continue
                t = torch.from_numpy(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)).permute(2, 0, 1).float().div(255).sub(0.5).div(0.5)
                t0 = time.perf_counter()
                with torch.no_grad():
                    y = net(t.unsqueeze(0).to(device), return_rgb=False, weight=0.5)[0]
                res = ((y.squeeze(0).clamp(-1, 1) * 0.5 + 0.5).permute(1, 2, 0).cpu().numpy() * 255).astype(np.float32)
                res = cv2.cvtColor(res, cv2.COLOR_RGB2BGR)
                T["restore"] += time.perf_counter() - t0
                delta = res - crop.astype(np.float32)
                tr = None
                best = size * 0.6
                for j, c in enumerate(tracks):                       # the same face as in the last frame: nearest centre
                    d = float(np.linalg.norm(c["c"] - centre))
                    if j not in used and d < best:
                        best, tr = d, c
                        used.add(j)
                if tr is None:
                    tr = {"delta": delta, "age": 0}
                    tracks.append(tr)
                    used.add(len(tracks) - 1)
                else:
                    tr["delta"] = smooth * tr["delta"] + (1 - smooth) * delta
                tr["c"], tr["age"] = centre, tr.get("age", 0) + 1
                fade = min(1.0, tr["age"] / 4.0)
                fresh.append(tr)
                todo.append((lm, box, np.clip(crop.astype(np.float32) + tr["delta"] * strength * fade, 0, 255).astype(np.uint8)))
        tracks = fresh
        result = bgr
        if todo:
            t0 = time.perf_counter()
            result = bgr.copy()
            H, W = result.shape[:2]
            for lm, box, restored in todo:        # paste through facexlib, but only inside a window around each face
                m = 1.1 * max(box[2] - box[0], box[3] - box[1])
                cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                x0, y0, x1, y1 = max(0, int(cx - m)), max(0, int(cy - m)), min(W, int(cx + m)), min(H, int(cy + m))
                off = np.array([x0, y0], dtype=np.float32)
                helper.clean_all()
                helper.read_image(np.ascontiguousarray(result[y0:y1, x0:x1]))
                helper.all_landmarks_5 = [lm - off]
                helper.det_faces = [np.array([box[0] - x0, box[1] - y0, box[2] - x0, box[3] - y0, 1.0], dtype=np.float32)]
                helper.align_warp_face()
                helper.add_restored_face(restored)
                helper.get_inverse_affine(None)
                result[y0:y1, x0:x1] = helper.paste_faces_to_input_image()
            T["paste"] += time.perf_counter() - t0
        rgb = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)
        out[i] = torch.from_numpy(rgb.astype(np.float32) / 255)
        changed[i] = (torch.from_numpy(np.abs(rgb.astype(np.int16) - cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.int16)).max(axis=2)) > 2).float()
        pbar.update(1)
    print(f"[scroll-studio] faces: {len(images)} frames, seconds: " + ", ".join(f"{k} {v:.1f}" for k, v in T.items()), flush=True)
    del net, helper
    return out, changed
