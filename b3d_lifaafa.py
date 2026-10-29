"""
Blender 3D shot (v24.6 demo): post office counter par Air Mail lifaafa ghoom ke aata hai, peeche ghoomta globe,
camera pate ki taraf badhta hai, 3D hara ✓ uchhalta hai. Sahi jawab (videshi pata) ke drishya ke liye.
Chalana (GitHub, animation-special jaisa setup):
  B3D_TEX=lifaafa_tex.png B3D_OUT=/tmp/b3d/ xvfb-run -a blender -b -t 2 --python b3d_lifaafa.py
Nateeja: B3D_OUT/f_0001.png ... (720x1280, 24 fps). Kirdaar Blender me NAHI (putle jaise lagte) - sirf cheezein.
"""
import math
import os

import bpy

TEX = os.environ.get("B3D_TEX", "lifaafa_tex.png")
OUT = os.environ.get("B3D_OUT", "/tmp/b3d/")
FPS = 24
N_FR = int(float(os.environ.get("B3D_SEC", "3.4")) * FPS)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        sc.render.engine = eng
        break
    except TypeError:
        continue
if hasattr(sc, "eevee"):
    for k, v in (("taa_render_samples", 24), ("use_gtao", True), ("use_shadows", True), ("use_soft_shadows", True)):
        if hasattr(sc.eevee, k):
            setattr(sc.eevee, k, v)
try:
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "Medium High Contrast"
except Exception:
    pass
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 720, 1280, 100
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N_FR
sc.render.image_settings.file_format = "PNG"
sc.render.filepath = os.path.join(OUT, "f_")
if sc.world is None:
    sc.world = bpy.data.worlds.new("W")
sc.world.use_nodes = True
bgn = sc.world.node_tree.nodes.get("Background")
if bgn:
    bgn.inputs["Color"].default_value = (0.05, 0.06, 0.1, 1)
    bgn.inputs["Strength"].default_value = 0.6


def mat(name, color, rough=0.5, metal=0.0, emit=None, emit_s=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = color + (1,)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit is not None:
        for nm in ("Emission Color", "Emission"):
            if nm in b.inputs:
                b.inputs[nm].default_value = emit + (1,)
                break
        b.inputs["Emission Strength"].default_value = emit_s
    return m


def obj_add(o, m):
    o.data.materials.append(m)
    return o


def key(o, attr, frame, val):
    setattr(o, attr, val)
    o.keyframe_insert(data_path=attr, frame=frame)


# ---------------- counter (lakdi) + peeche post office ki laal deewar ----------------
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.6, -1.25))
ctr = bpy.context.object
ctr.scale = (9, 4, 0.5)
obj_add(ctr, mat("lakdi", (0.36, 0.2, 0.09), 0.45))
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -1.38, -1.25))
edge = bpy.context.object
edge.scale = (9, 0.08, 0.52)
obj_add(edge, mat("kinara", (0.25, 0.13, 0.05), 0.4))
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 7, 2.5), rotation=(math.radians(90), 0, 0))
wall = bpy.context.object
wall.scale = (24, 14, 1)
obj_add(wall, mat("deewar", (0.55, 0.08, 0.08), 0.8))
# deewar par peeli India Post patti (dhundhli dikhegi)
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 6.95, 4.2), rotation=(math.radians(90), 0, 0))
strip = bpy.context.object
strip.scale = (24, 1.0, 1)
obj_add(strip, mat("patti", (0.95, 0.72, 0.1), 0.6))

# ---------------- globe (stand ke saath), peeche baayen ----------------
bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=0.95, location=(-1.35, 2.6, 0.95))
globe = bpy.context.object
bpy.ops.object.shade_smooth()
gm = bpy.data.materials.new("globe")
gm.use_nodes = True
nt = gm.node_tree
bs = nt.nodes.get("Principled BSDF")
bs.inputs["Roughness"].default_value = 0.35
tc = nt.nodes.new("ShaderNodeTexCoord")
nz = nt.nodes.new("ShaderNodeTexNoise")
nz.inputs["Scale"].default_value = 2.2
nz.inputs["Detail"].default_value = 6.0
cr = nt.nodes.new("ShaderNodeValToRGB")
cr.color_ramp.interpolation = "CONSTANT"
cr.color_ramp.elements[0].position = 0.0
cr.color_ramp.elements[0].color = (0.05, 0.28, 0.75, 1)
cr.color_ramp.elements[1].position = 0.53
cr.color_ramp.elements[1].color = (0.18, 0.62, 0.22, 1)
nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
nt.links.new(nz.outputs["Fac"], cr.inputs["Fac"])
nt.links.new(cr.outputs["Color"], bs.inputs["Base Color"])
globe.data.materials.append(gm)
gold = mat("sona", (0.85, 0.62, 0.18), 0.25, 0.9)
bpy.ops.mesh.primitive_torus_add(major_radius=1.1, minor_radius=0.045, location=(-1.35, 2.6, 0.95),
                                 rotation=(0, math.radians(90), math.radians(20)))
obj_add(bpy.context.object, gold)
bpy.ops.mesh.primitive_cylinder_add(radius=0.07, depth=1.0, location=(-1.35, 2.6, -0.5))
obj_add(bpy.context.object, gold)
bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=0.12, location=(-1.35, 2.6, -0.95))
obj_add(bpy.context.object, gold)
globe.rotation_euler = (math.radians(23), 0, 0)
key(globe, "rotation_euler", 1, (math.radians(23), 0, 0))
key(globe, "rotation_euler", N_FR, (math.radians(23), 0, math.radians(150)))

# ---------------- lifaafa (body + saamne ka chitra) ----------------
bpy.ops.object.empty_add(location=(0, 0, 0))
env = bpy.context.object
env.name = "lifaafa"
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.012, 0))
body = bpy.context.object
body.scale = (2.2, 0.02, 1.4)
obj_add(body, mat("kaagaz", (0.95, 0.93, 0.88), 0.7))
body.parent = env
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, -0.001, 0), rotation=(math.radians(90), 0, 0))
front = bpy.context.object
front.scale = (2.2, 1.4, 1)
fm = bpy.data.materials.new("pata")
fm.use_nodes = True
fb = fm.node_tree.nodes.get("Principled BSDF")
fb.inputs["Roughness"].default_value = 0.6
tx = fm.node_tree.nodes.new("ShaderNodeTexImage")
tx.image = bpy.data.images.load(os.path.abspath(TEX))
fm.node_tree.links.new(tx.outputs["Color"], fb.inputs["Base Color"])
front.data.materials.append(fm)
front.parent = env

# rasta: neeche-daayen se ghoomta hua aata hai -> counter ke upar khada -> halka tairna
f_land = int(N_FR * 0.36)
key(env, "location", 1, (2.6, -1.5, -2.6))
key(env, "rotation_euler", 1, (math.radians(-60), math.radians(-200), math.radians(40)))
key(env, "location", f_land, (0.15, 0.0, 0.05))
key(env, "rotation_euler", f_land, (math.radians(8), math.radians(4), math.radians(-6)))
key(env, "location", f_land + 6, (0.15, 0.0, 0.0))
key(env, "rotation_euler", f_land + 6, (0, 0, 0))
key(env, "location", N_FR, (0.15, 0.0, 0.08))
key(env, "rotation_euler", N_FR, (0, 0, math.radians(-2)))

# ---------------- 3D hara ✓ (do dande) - pate ke bagal me uchhalta ----------------
bpy.ops.object.empty_add(location=(1.05, -0.35, -0.32))
chk = bpy.context.object
green = mat("hara", (0.1, 0.75, 0.3), 0.3, emit=(0.1, 0.9, 0.35), emit_s=1.5)
bpy.ops.mesh.primitive_cube_add(size=1, location=(-0.12, 0, -0.06), rotation=(0, math.radians(45), 0))
a = bpy.context.object
a.scale = (0.32, 0.09, 0.09)
obj_add(a, green)
a.parent = chk
bpy.ops.mesh.primitive_cube_add(size=1, location=(0.15, 0, 0.1), rotation=(0, math.radians(-55), 0))
b = bpy.context.object
b.scale = (0.6, 0.09, 0.09)
obj_add(b, green)
b.parent = chk
f_chk = int(N_FR * 0.62)
key(chk, "scale", 1, (0.001, 0.001, 0.001))
key(chk, "scale", f_chk, (0.001, 0.001, 0.001))
key(chk, "scale", f_chk + 5, (1.35, 1.35, 1.35))
key(chk, "scale", f_chk + 10, (1.0, 1.0, 1.0))
key(chk, "rotation_euler", f_chk, (0, 0, math.radians(-30)))
key(chk, "rotation_euler", N_FR, (0, 0, math.radians(8)))

# ---------------- roshni ----------------
def light(kind, loc, energy, color=(1, 1, 1), size=3.0, rot=(0, 0, 0)):
    ld = bpy.data.lights.new(kind + str(len(bpy.data.lights)), kind)
    ld.energy = energy
    ld.color = color
    if kind == "AREA":
        ld.size = size
    lo = bpy.data.objects.new(ld.name, ld)
    sc.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = rot
    return lo


light("AREA", (3.5, -5, 4.5), 1400, (1.0, 0.93, 0.82), 5, (math.radians(50), 0, math.radians(35)))
light("AREA", (-4, -3, 2), 500, (0.75, 0.85, 1.0), 4, (math.radians(70), 0, math.radians(-50)))
light("AREA", (0, 4, 5), 900, (1.0, 0.85, 0.6), 4, (math.radians(-40), 0, 0))       # peeche se kinara
light("POINT", (-1.0, 1.3, 2.0), 120, (0.6, 0.8, 1.0))                              # globe par chamak

# ---------------- camera: dheere pate ki taraf (DOF - globe dhundhla) ----------------
cd = bpy.data.cameras.new("cam")
cd.lens = 42
cam = bpy.data.objects.new("cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam
tgt = bpy.data.objects.new("tgt", None)
sc.collection.objects.link(tgt)
tgt.location = (0.15, 0, 0)
tc_ = cam.constraints.new("TRACK_TO")
tc_.target = tgt
tc_.track_axis = "TRACK_NEGATIVE_Z"
tc_.up_axis = "UP_Y"
cd.dof.use_dof = True
cd.dof.focus_object = env
cd.dof.aperture_fstop = 2.2
key(cam, "location", 1, (0.9, -6.6, 1.4))
key(cam, "location", f_land, (0.5, -6.0, 1.0))
key(cam, "location", N_FR, (0.35, -4.7, 0.6))
key(tgt, "location", 1, (0.0, 0.5, 0.2))
key(tgt, "location", N_FR, (0.4, 0.0, -0.1))

os.makedirs(OUT, exist_ok=True)
print("B3D_START", N_FR, "frames", sc.render.engine)
bpy.ops.render.render(animation=True)
print("B3D_DONE", OUT)
