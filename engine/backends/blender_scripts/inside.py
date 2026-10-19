"""Render the camera route of an `inside` scene (engine/inside.py plans it; this only draws it).

  blender -b --factory-startup -P inside.py -- --job job.json

job.json
  glb       the normalised product GLB (engine/product.py)
  size      [W, H]            samples   Cycles samples (denoised)
  hdri, ambient, lamp, lamp_color, rim, exposure, background   the look (see InsideScene)
  cutaway   dissolve the parts between the camera and the stop's part
  stops     [{"match": [globs], "focus": [globs], "extent": metres}]   for the dissolve and the focus
  frames    the whole route, one entry per frame (cam, target, focus, lens, fstop, roll, explode, stop, p), in metres
  render    [{"k": frame index, "out": png path}]   the frames to draw now (the dissolve is worked out over all `frames`)

Everything is scaled to a product of unit radius, like the product stills, so the lights are the same for a watch or
a car; the aperture is scaled back so the blur is the real product's. Output: opaque RGB PNGs.
"""
import argparse
import fnmatch
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--job", required=True)
a = ap.parse_args(argv)
with open(a.job, encoding="utf-8") as f:
    J = json.load(f)
W, H = J["size"]
FR = J["frames"]
STOPS = J["stops"]

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=J["glb"])
meshes = [o for o in scene.objects if o.type == "MESH"]
if not meshes:
    raise SystemExit("the product GLB has no meshes")
bpy.context.view_layer.update()


def bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


lo, hi = bounds(meshes)
radius = max((hi - lo).length / 2, 1e-6)
S = 1.0 / radius
root = bpy.data.objects.new("Root", None)
scene.collection.objects.link(root)
for o in list(scene.objects):
    if o.parent is None and o is not root:
        o.parent = root
root.matrix_world = Matrix.Scale(S, 4)
bpy.context.view_layer.update()
base = {o.name: o.matrix_world.copy() for o in meshes}
spread = {o.name: (Vector((o["ss_explode"][0], -o["ss_explode"][2], o["ss_explode"][1])) * S) for o in meshes if o.get("ss_explode") is not None}


def set_explode(ex):
    for o in meshes:
        v = spread.get(o.name)
        o.matrix_world = Matrix.Translation(v * ex) @ base[o.name] if v is not None and ex else base[o.name]
    bpy.context.view_layer.update()


def names_of(o):
    out, p = [o.name, o.data.name], o.parent
    path = [o.name]
    while p and p is not root:
        out.append(p.name)
        path.insert(0, p.name)
        p = p.parent
    out.append("/".join(path))
    return [n.lower() for n in out]


def select(patterns):
    pats = [p.lower() for p in patterns]
    return {o.name for o in meshes if any(fnmatch.fnmatchcase(n, p) for n in names_of(o) for p in pats)}


STOP_OBJ = []
for i, st in enumerate(STOPS):
    mt = select(st["match"]) if st.get("match") else set()
    fo = select(st["focus"]) if st.get("focus") else mt
    STOP_OBJ.append({"match": mt, "focus": fo})
    print(f"STOP {i + 1}: {len(mt)} meshes matched", flush=True)

# ---------------------------------------------------------------- the dissolve: what stands between camera and stop
FADE = {}          # object name -> [fade per frame]
vec = lambda v: Vector(v) * S


def forward_of(cam, tgt):
    return (tgt - cam).normalized()


if J.get("cutaway", True) and len(FR) > 0:
    deps = bpy.context.evaluated_depsgraph_get()
    occ = []
    last_ex = None
    for fr in FR:
        ex = fr.get("explode", 0.0)
        if ex != last_ex:
            set_explode(ex)
            deps = bpy.context.evaluated_depsgraph_get()
            last_ex = ex
        cam, tgt = vec(fr["cam"]), vec(fr["target"])
        d = (tgt - cam).length
        fwd = (tgt - cam).normalized()
        right = fwd.cross(Vector((0, 0, 1)))
        right = right.normalized() if right.length > 1e-6 else Vector((1, 0, 0))
        up = right.cross(fwd).normalized()
        st = STOP_OBJ[fr["stop"]] if fr["stop"] >= 0 else None
        exempt = (st["match"] | st["focus"]) if st else set()
        ext = (STOPS[fr["stop"]].get("extent", 0.05) * S * 0.5) if st else 0.2
        slack = max(ext * 0.9, 0.01 * d)
        r = max(ext * 0.8, 0.1 * d)
        goals = [tgt, tgt + right * r, tgt - right * r, tgt + up * r * 0.7, tgt - up * r * 0.7]
        hits = set()
        for g in goals:
            ray = (g - cam)
            L = ray.length
            ray.normalize()
            origin, travelled = cam.copy(), 0.0
            for _ in range(12):
                ok, loc, nor, idx, obj, mat = scene.ray_cast(deps, origin, ray, distance=L - travelled)
                if not ok:
                    break
                step = (loc - origin).length
                travelled += step
                nm = obj.original.name if hasattr(obj, "original") else obj.name
                if nm not in exempt and travelled < L - slack:
                    hits.add(nm)
                origin = loc + ray * 1e-4 * max(1.0, d)
                travelled += 1e-4 * max(1.0, d)
        # a camera standing inside a part: the part around it is in the way too
        ok, loc, nor, idx, obj, mat = scene.ray_cast(deps, cam, fwd, distance=0.02 * d)
        if ok:
            nm = obj.original.name if hasattr(obj, "original") else obj.name
            if nm not in exempt:
                hits.add(nm)
        occ.append(hits)
    set_explode(0.0)
    names = set().union(*occ) if occ else set()
    n = len(FR)
    ahead, behind, sigma = 8, 3, 2.5
    kern = [math.exp(-0.5 * (j / sigma) ** 2) for j in range(-int(3 * sigma), int(3 * sigma) + 1)]
    ksum = sum(kern)
    for nm in names:
        raw = [1.0 if nm in occ[k] else 0.0 for k in range(n)]
        wide = [max(raw[max(0, k - behind):min(n, k + ahead + 1)]) for k in range(n)]
        sm = []
        for k in range(n):
            acc = 0.0
            for j, w in zip(range(-int(3 * sigma), int(3 * sigma) + 1), kern):
                acc += w * wide[min(n - 1, max(0, k + j))]
            sm.append(min(1.0, acc / ksum * 1.15))
        FADE[nm] = sm
    print(f"DISSOLVE {len(names)} parts ever stand in the way", flush=True)

# every material mixes in a transparent shader by the object's ss_fade (all ray types, so light passes too)
for o in meshes:
    o["ss_fade"] = 0.0
done = set()
for o in meshes:
    for slot in o.material_slots:
        mat = slot.material
        if mat is None or mat.name in done:
            continue
        done.add(mat.name)
        if not mat.use_nodes:
            mat.use_nodes = True
        nt = mat.node_tree
        out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None) or \
            next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
        if out is None or not out.inputs["Surface"].links:
            continue
        src = out.inputs["Surface"].links[0].from_socket
        attr = nt.nodes.new("ShaderNodeAttribute")
        attr.attribute_type = "OBJECT"
        attr.attribute_name = '["ss_fade"]'
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(attr.outputs["Fac"], mix.inputs[0])
        nt.links.new(src, mix.inputs[1])
        nt.links.new(tr.outputs["BSDF"], mix.inputs[2])
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])

# ---------------------------------------------------------------- look
scene.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
for dev_type in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
    try:
        prefs.compute_device_type = dev_type
        prefs.get_devices()
        if any(d.type == dev_type for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type == dev_type
            scene.cycles.device = "GPU"
            break
    except TypeError:
        continue
scene.cycles.samples = int(J["samples"])
scene.cycles.use_adaptive_sampling = True
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 8
scene.cycles.transparent_max_bounces = 16
scene.cycles.seed = 7
scene.cycles.use_animated_seed = False
scene.render.film_transparent = False
scene.render.resolution_x, scene.render.resolution_y = W, H
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = "AgX"
try:
    scene.view_settings.look = "AgX - Medium High Contrast"
except TypeError:
    pass
scene.view_settings.exposure = float(J.get("exposure", 0))
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.image_settings.compression = 6


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))


world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
nt = world.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
env = nt.nodes.new("ShaderNodeTexEnvironment")
hdri = next((p for p in (os.path.join(bpy.utils.resource_path(k), "datafiles", "studiolights", "world", f"{J['hdri']}.exr")
                          for k in ("LOCAL", "SYSTEM", "USER")) if os.path.exists(p)), None)
if hdri is None:
    raise SystemExit(f"studio light '{J['hdri']}' not found in Blender's datafiles")
env.image = bpy.data.images.load(hdri)
bg_env = nt.nodes.new("ShaderNodeBackground")
bg_env.inputs["Strength"].default_value = float(J.get("ambient", 0.25))
bg_void = nt.nodes.new("ShaderNodeBackground")
bg_void.inputs["Color"].default_value = (*hex_rgb(J.get("background", "#050608")), 1.0)
path = nt.nodes.new("ShaderNodeLightPath")
mixw = nt.nodes.new("ShaderNodeMixShader")
outw = nt.nodes.new("ShaderNodeOutputWorld")
nt.links.new(env.outputs["Color"], bg_env.inputs["Color"])
nt.links.new(path.outputs["Is Camera Ray"], mixw.inputs["Fac"])
nt.links.new(bg_env.outputs["Background"], mixw.inputs[1])
nt.links.new(bg_void.outputs["Background"], mixw.inputs[2])
nt.links.new(mixw.outputs["Shader"], outw.inputs["Surface"])


def area(name, size, shadow=True):
    d = bpy.data.lights.new(name, "AREA")
    d.size = size
    d.use_shadow = shadow
    o = bpy.data.objects.new(name, d)
    scene.collection.objects.link(o)
    return o


lamp = area("Lamp", 0.5)
rim = area("Rim", 0.8)
fill = area("Fill", 1.0, shadow=False)
lamp.data.color = hex_rgb(J.get("lamp_color", "#ffe8d0"))
rim.data.color = (0.75, 0.85, 1.0)
fill.data.color = lamp.data.color

cam_data = bpy.data.cameras.new("Cam")
cam_data.sensor_fit = "HORIZONTAL"
cam_data.sensor_width = 36.0
cam = bpy.data.objects.new("Cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam_data.clip_start, cam_data.clip_end = 0.002, 200
cam_data.dof.use_dof = True
cam.rotation_mode = "QUATERNION"


def aim_light(o, loc, target):
    o.location = loc
    o.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()


def place(fr, k):
    set_explode(fr.get("explode", 0.0))
    c, t, fp = vec(fr["cam"]), vec(fr["target"]), vec(fr["focus"])
    fwd = (t - c).normalized()
    right = fwd.cross(Vector((0, 0, 1)))
    right = right.normalized() if right.length > 1e-6 else Vector((1, 0, 0))
    up = right.cross(fwd).normalized()
    q = (t - c).to_track_quat("-Z", "Y")
    cam.rotation_quaternion = q @ Quaternion(Vector((0, 0, 1)), math.radians(fr.get("roll", 0)))
    cam.location = c
    cam_data.lens = fr["lens"]
    cam_data.dof.focus_distance = max(0.002, (fp - c).dot(fwd))
    cam_data.dof.aperture_fstop = fr["fstop"] * radius
    d = max((fp - c).length, 0.01)
    k2 = (d / 3.2) ** 2          # the lamps keep the exposure of a subject at any distance
    aim_light(lamp, c + right * 0.34 * d + up * 0.3 * d - fwd * 0.05 * d, fp)
    lamp.data.size = 0.35 * d
    lamp.data.energy = 330 * k2 * float(J.get("lamp", 1.0))
    aim_light(rim, t + fwd * 0.9 * d + up * 0.55 * d - right * 0.35 * d, t)
    rim.data.size = 0.5 * d
    rim.data.energy = 520 * k2 * float(J.get("rim", 1.0))
    aim_light(fill, c - right * 0.2 * d - up * 0.1 * d, fp)
    fill.data.size = 0.5 * d
    fill.data.energy = 36 * k2 * float(J.get("lamp", 1.0))
    for o in meshes:
        o["ss_fade"] = FADE[o.name][k] if o.name in FADE else 0.0
    bpy.context.view_layer.update()


jobs = J["render"]
for n, job in enumerate(jobs, 1):
    k = job["k"]
    place(FR[k], k)
    scene.render.filepath = os.path.abspath(job["out"])
    bpy.ops.render.render(write_still=True)
    print(f"FRAME {n}/{len(jobs)} {k}", flush=True)
