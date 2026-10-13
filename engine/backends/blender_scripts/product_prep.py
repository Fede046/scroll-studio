"""Normalise a product model into one GLB: fix axes and units, centre it on its base, apply part materials,
decimate only if absurdly heavy, and report its parts.

  blender -b --factory-startup -P product_prep.py -- --model SRC --fmt step --opts opts.json --out OUT.glb --report OUT.json

SRC is a GLB/glTF, OBJ, FBX, STL or PLY (STEP and 3MF arrive here already converted to GLB by engine/product.py;
--fmt names the original format so its axis and unit conventions apply). opts.json:
  {"up": "auto"|"z"|"-y"..., "units": "auto"|"mm"..., "rotation": [x, y, z], "parts": [PartMaterial...],
   "max_triangles": 1500000, "textures": {"<spec path>": "<absolute file>"}}

The GLB is Y-up (glTF), in metres, with the base centre at the origin and the front facing +Z (-Y in Blender).
Each explodable part (a mesh with no mesh above it) carries node extras: ss_part (its index in the report) and
ss_explode (its exploded offset in metres, glTF axes), so stills, sequences and the live viewer explode alike.
"""
import argparse
import fnmatch
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--fmt", required=True)
ap.add_argument("--opts", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--report", required=True)
a = ap.parse_args(argv)
with open(a.opts, encoding="utf-8") as f:
    O = json.load(f)
FMT = a.fmt.lower().lstrip(".")
if FMT == "stp":
    FMT = "step"

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------------------------------------------------------------- import
ext = os.path.splitext(a.model)[1].lower()
if ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=a.model)
elif ext == ".obj":
    bpy.ops.wm.obj_import(filepath=a.model, forward_axis="Y", up_axis="Z")     # file axes as they are
elif ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=a.model)
elif ext == ".stl":
    bpy.ops.wm.stl_import(filepath=a.model, forward_axis="Y", up_axis="Z")
elif ext == ".ply":
    bpy.ops.wm.ply_import(filepath=a.model, forward_axis="Y", up_axis="Z")
else:
    raise SystemExit(f"unsupported model format {ext}")

for o in list(scene.objects):          # cameras, lights and helpers in the file are not the product
    if o.type not in ("MESH", "EMPTY"):
        bpy.data.objects.remove(o, do_unlink=True)
def _names(o):
    out, p = [o.name.lower()] + ([o.data.name.lower()] if o.type == "MESH" else []), o.parent
    while p:
        out.append(p.name.lower())
        p = p.parent
    return out


dropped = 0
for pat in [x.lower() for x in O.get("exclude", [])]:
    for o in [o for o in scene.objects if o.type == "MESH" and any(fnmatch.fnmatchcase(n, pat) for n in _names(o))]:
        bpy.data.objects.remove(o, do_unlink=True)
        dropped += 1
if dropped:
    print(f"IMPORTED excluded {dropped} meshes", flush=True)
meshes = [o for o in scene.objects if o.type == "MESH" and len(o.data.polygons)]
if not meshes:
    raise SystemExit("the model has no meshes" + (" left after `exclude`" if dropped else ""))
print(f"IMPORTED {len(meshes)} meshes", flush=True)

# ---------------------------------------------------------------- axes, units, rotation, base
# Importers already turn glTF/FBX (y-up) into Blender's z-up. STL, PLY and OBJ are imported with their file axes;
# STEP and 3MF were converted from their z-up files to y-up GLB, which the importer turns back: file axes again.
YUP = FMT in ("glb", "gltf", "fbx")


def file_to_blender(v):
    x, y, z = v
    return Vector((x, -z, y)) if YUP else Vector((x, y, z))


up = O.get("up", "auto")
if up == "auto":
    up = "y" if FMT == "obj" else None
R_up = Matrix.Identity(4)
if up:
    sign = -1 if up.startswith("-") else 1
    axis = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[up.lstrip("-")]
    b = file_to_blender(tuple(sign * c for c in axis))
    if (b - Vector((0, 0, -1))).length < 1e-6:
        R_up = Matrix.Rotation(math.pi, 4, "X")
    else:
        R_up = b.rotation_difference(Vector((0, 0, 1))).to_matrix().to_4x4()

root = bpy.data.objects.new("Product", None)
scene.collection.objects.link(root)
for o in list(scene.objects):
    if o.parent is None and o is not root:
        o.parent = root


def world_bounds(objs):
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


SCALES = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254, "ft": 0.3048}
units = O.get("units", "auto")
R_user = Euler([math.radians(v) for v in O.get("rotation", (0, 0, 0))], "XYZ").to_matrix().to_4x4()
root.matrix_world = R_user @ R_up
lo, hi = world_bounds(meshes)
largest = max(hi - lo)
note = units
if units == "auto":
    base = "mm" if FMT == "stl" else "m"      # STEP and 3MF are converted to metres already
    scale = SCALES[base]
    note = f"{base} (auto)"
    if largest * scale > 20:
        scale *= 0.001
        note = f"mm (auto: {largest * SCALES[base]:.0f} m would be too big)"
    elif base == "mm" and largest * scale < 0.002:
        scale = 1.0
        note = "m (auto: under 2 mm in millimetres)"
else:
    scale = SCALES[units]
root.matrix_world = R_user @ R_up @ Matrix.Scale(scale, 4)
lo, hi = world_bounds(meshes)
root.matrix_world = Matrix.Translation(-Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))) @ root.matrix_world
lo, hi = world_bounds(meshes)
print(f"NORMALISED size {hi.x - lo.x:.4f} x {hi.y - lo.y:.4f} x {hi.z - lo.z:.4f} m ({note})", flush=True)

# ---------------------------------------------------------------- materials


def names_of(o):
    out = [o.name, o.data.name]
    p = o.parent
    path = [o.name]
    while p and p is not root:
        out.append(p.name)
        path.insert(0, p.name)
        p = p.parent
    out.append("/".join(path))
    return [n.lower() for n in out]


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hexlin(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4)) + (1.0,)


def principled(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return nt, bsdf


def unlink(nt, sock):
    for l in list(sock.links):
        nt.links.remove(l)


def ensure_uv(o, scale):
    """Box-project UVs (world metres / scale) onto a mesh that has none, so a texture can be exported."""
    me = o.data
    if me.uv_layers:
        return
    if me.users > 1:
        o.data = me = me.copy()
    bm = bmesh.new()
    bm.from_mesh(me)
    uv = bm.loops.layers.uv.verify()
    M = o.matrix_world
    N = M.to_3x3()
    for f in bm.faces:
        n = N @ f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for l in f.loops:
            p = M @ l.vert.co
            u, v = ((p.y, p.z), (p.x, p.z), (p.x, p.y))[ax]
            l[uv].uv = (u / scale, v / scale)
    bm.to_mesh(me)
    bm.free()


derived = {}


def override(mat, ri, rule, o):
    key = (mat.name if mat else None, ri)
    if key in derived:
        return derived[key]
    new = mat.copy() if mat else bpy.data.materials.new(rule.get("match", "part").strip("*") or "part")
    new.name = f"{(mat.name if mat else new.name)}~{ri + 1}"
    nt, bsdf = principled(new)
    I = bsdf.inputs
    if rule.get("color"):
        unlink(nt, I["Base Color"])
        I["Base Color"].default_value = hexlin(rule["color"])
        new.diffuse_color = hexlin(rule["color"])
    if rule.get("metallic") is not None:
        unlink(nt, I["Metallic"])
        I["Metallic"].default_value = float(rule["metallic"])
    if rule.get("roughness") is not None:
        unlink(nt, I["Roughness"])
        I["Roughness"].default_value = float(rule["roughness"])
    if rule.get("emission"):
        unlink(nt, I["Emission Color"])
        I["Emission Color"].default_value = hexlin(rule["emission"])
        I["Emission Strength"].default_value = float(rule.get("emission_strength", 1.0))
    if rule.get("transmission") is not None:
        I["Transmission Weight"].default_value = float(rule["transmission"])
        if rule.get("roughness") is None:
            I["Roughness"].default_value = 0.05
    if rule.get("texture"):
        path = O.get("textures", {}).get(rule["texture"], rule["texture"])
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(path)
        unlink(nt, I["Base Color"])
        nt.links.new(tex.outputs["Color"], I["Base Color"])
    derived[key] = new
    return new


def vertex_colour_material(o):
    mat = bpy.data.materials.new("VertexColour")
    nt, bsdf = principled(mat)
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = o.data.color_attributes[0].name
    bsdf.inputs["Roughness"].default_value = 0.6
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    o.data.materials.clear()
    o.data.materials.append(mat)


for o in meshes:
    if not o.data.materials and o.data.color_attributes:      # scans / TRELLIS: show the vertex colours
        vertex_colour_material(o)
    if not o.data.materials:
        m = bpy.data.materials.new("Default")
        nt, bsdf = principled(m)
        bsdf.inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1)
        bsdf.inputs["Roughness"].default_value = 0.5
        o.data.materials.append(m)

rules = O.get("parts", [])
hits = [0] * len(rules)
FACING = {"front": (0, -1, 0), "back": (0, 1, 0), "left": (-1, 0, 0), "right": (1, 0, 0), "top": (0, 0, 1), "bottom": (0, 0, -1)}
size = Vector((max(hi.x - lo.x, 1e-9), max(hi.y - lo.y, 1e-9), max(hi.z - lo.z, 1e-9)))


def cut_region(o, region):
    """Cut the mesh along the region's six planes so faces never straddle its edge (CAD tessellation makes long
    thin triangles across flat faces; classifying those by centre gives jagged wedges)."""
    me = o.data
    M = o.matrix_world
    Minv = M.inverted_safe()
    N = M.to_3x3().transposed()            # world plane normal -> local: n_local = M^T n_world (up to scale)
    bm = bmesh.new()
    bm.from_mesh(me)
    for i in range(3):
        for k in (region[i], region[i + 3]):
            if not 0.0 < k < 1.0:
                continue
            co_w = lo.copy()
            co_w[i] = lo[i] + k * size[i]
            n_w = Vector((0, 0, 0))
            n_w[i] = 1.0
            geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
            bmesh.ops.bisect_plane(bm, geom=geom, plane_co=Minv @ co_w, plane_no=(N @ n_w).normalized(), dist=1e-7)
    bm.to_mesh(me)
    bm.free()


def face_filter(o, rule):
    """Polygon indices of o inside rule.region and facing rule.facing (None: no face filter)."""
    region, facing = rule.get("region"), rule.get("facing")
    if not region and not facing:
        return None
    if region:
        if o.data.users > 1:
            o.data = o.data.copy()
        cut_region(o, region)
    M = o.matrix_world
    N = M.to_3x3().inverted_safe().transposed()
    want = Vector(FACING[facing]) if facing else None
    keep = set()
    for p in o.data.polygons:
        if region:
            c = M @ p.center
            u = [(c[i] - lo[i]) / size[i] for i in range(3)]
            if not all(region[i] <= u[i] <= region[i + 3] for i in range(3)):
                continue
        if want is not None and (N @ p.normal).normalized().dot(want) < 0.6:
            continue
        keep.add(p.index)
    return keep


for ri, rule in enumerate(rules):
    pat = rule.get("match", "*").lower()
    mpat = (rule.get("material") or "").lower()
    for o in meshes:
        if not any(fnmatch.fnmatchcase(n, pat) for n in names_of(o)):
            continue
        slots = [i for i, s in enumerate(o.data.materials)
                 if not mpat or (s and fnmatch.fnmatchcase(s.name.lower(), mpat))]
        if not slots:
            continue
        faces = face_filter(o, rule)
        if faces is not None:
            faces = {i for i in faces if o.data.polygons[i].material_index in slots}
            if not faces:
                continue
        if o.data.users > 1:            # a shared mesh: this object gets its own copy before its materials change
            o.data = o.data.copy()
        if rule.get("texture"):
            ensure_uv(o, float(rule.get("texture_scale", 0.05)))
        if faces is None:
            for i in slots:
                o.data.materials[i] = override(o.data.materials[i], ri, rule, o)
        else:                           # only some faces: they move to new slots holding the overridden materials
            remap = {}
            for i in slots:
                new = override(o.data.materials[i], ri, rule, o)
                o.data.materials.append(new)
                remap[i] = len(o.data.materials) - 1
            for i in faces:
                poly = o.data.polygons[i]
                poly.material_index = remap[poly.material_index]
        hits[ri] += 1

# ---------------------------------------------------------------- decimate (only when absurdly heavy)


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


total = sum(tris(o) for o in meshes)
limit = int(O.get("max_triangles", 1_500_000))
ratio = 1.0
if total > limit:
    # only the heavy meshes are thinned: a 20k-triangle housing keeps its edges while 400k-triangle fillets on
    # screws and switches give way. Instances share their mesh, so a mesh's weight counts every instance.
    weight = {}
    for o in meshes:
        weight[o.data.name] = weight.get(o.data.name, 0) + tris(o)
    per_mesh = {o.data.name: tris(o) for o in meshes}
    light_cap = 4000
    light = sum(w for n, w in weight.items() if per_mesh[n] <= light_cap)
    heavy = total - light
    ratio = max((limit - light) / max(heavy, 1), 0.02) if limit > light else max(limit / total, 0.02)
    done = set()
    for o in meshes:
        if o.data.name in done or (limit > light and per_mesh[o.data.name] <= light_cap):
            continue
        done.add(o.data.name)
        mod = o.modifiers.new("Decimate", "DECIMATE")
        mod.ratio = ratio
        mod.use_collapse_triangulate = True
    print(f"DECIMATE {total} triangles -> about {limit} (heavy meshes at ratio {ratio:.3f})", flush=True)
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    for name in done:
        o = next(x for x in meshes if x.data.name == name)
        users = [x for x in meshes if x.data.name == name]
        new = bpy.data.meshes.new_from_object(o.evaluated_get(deps))
        for x in users:
            x.modifiers.clear()
            x.data = new

# ---------------------------------------------------------------- parts and explode offsets


def has_mesh_parent(o):
    p = o.parent
    while p:
        if p.type == "MESH":
            return True
        p = p.parent
    return False


def bounds_of(o):
    w = [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo_ = Vector((min(p.x for p in w), min(p.y for p in w), min(p.z for p in w)))
    hi_ = Vector((max(p.x for p in w), max(p.y for p in w), max(p.z for p in w)))
    return lo_, hi_


bpy.context.view_layer.update()
parts = [o for o in meshes if not has_mesh_parent(o)]
lo, hi = world_bounds(meshes)
C, R = (lo + hi) / 2, max((hi - lo).length / 2, 1e-6)
anchor = None
if len(parts) > 1:
    def vol(o):
        l, h = bounds_of(o)
        d = h - l
        return max(d.x, 1e-6) * max(d.y, 1e-6) * max(d.z, 1e-6)
    anchor = max(parts, key=vol)


def explode_offset(o):
    if o is anchor or len(parts) < 2:
        return Vector((0, 0, 0))
    l, h = bounds_of(o)
    d = ((l + h) / 2 - C) / R
    if d.length < 0.06:
        d = Vector((0, 0, 1))
    # out along the line from the centre; parts near the middle move less than the outer ones, and everything
    # rises a little so stacked parts separate
    out = d.normalized() * (0.32 + 0.45 * min(d.length, 1.0))
    out.z += 0.12
    return out * R


def hexcol(mat):
    if not mat:
        return None
    try:
        _, bsdf = principled(mat)
        c = bsdf.inputs["Base Color"].default_value
        return "#" + "".join(f"{round(linear_to_srgb(c[i]) * 255):02x}" for i in range(3))
    except Exception:
        return None


report_parts = []
for i, o in enumerate(parts):
    off = explode_offset(o)
    o["ss_part"] = i
    o["ss_explode"] = [round(off.x, 6), round(off.z, 6), round(-off.y, 6)]       # glTF axes (y up, z front)
    sub = [o] + [c for c in o.children_recursive if c.type == "MESH"]
    l, h = None, None
    for s in sub:
        sl, sh = bounds_of(s)
        l = sl if l is None else Vector(map(min, l, sl))
        h = sh if h is None else Vector(map(max, h, sh))
    mats = []
    for s in sub:
        for m in s.data.materials:
            entry = {"name": m.name if m else None, "color": hexcol(m)}
            if entry not in mats:
                mats.append(entry)
    path = [o.name]
    p = o.parent
    while p and p is not root:
        path.insert(0, p.name)
        p = p.parent
    report_parts.append({
        "index": i, "name": o.name, "mesh": o.data.name, "path": "/".join(path),
        "triangles": sum(tris(s) for s in sub), "materials": mats,
        "size": [round(v, 5) for v in (h - l)], "centre": [round(v, 5) for v in (l + h) / 2],
        "explode": [round(off.x, 5), round(off.y, 5), round(off.z, 5)], "anchor": o is anchor,
    })

# ---------------------------------------------------------------- export
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=a.out, export_format="GLB", export_apply=True, export_extras=True,
                          export_yup=True, export_cameras=False, export_lights=False, export_animations=False)
report = {
    "size": [round(v, 5) for v in (hi - lo)], "height": round(hi.z - lo.z, 5), "units": note,
    "up": up or "as imported", "triangles": sum(tris(o) for o in meshes), "source_triangles": total,
    "decimated": ratio < 1.0, "meshes": len(meshes), "parts": report_parts,
    "rules": [{"match": r.get("match", "*"), "material": r.get("material"), "hits": n} for r, n in zip(rules, hits)],
}
with open(a.report, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=1, ensure_ascii=False)
print(f"EXPORTED {a.out} ({len(report_parts)} parts)", flush=True)
