"""
POORI REEL BLENDER ME (demo v25) - EK DRISHYA KA RENDER. b3d_prep.py ka b3d_job/plan.json padhta hai.
Chalana: B3D_JOB=b3d_job B3D_SCENE=0 xvfb-run -a blender -b -t 2 --python b3d_reel.py
Nateeja: b3d_job/frames_<i>/f_0001.png ... (720x1280, 24 fps). Likhai/caption baad me (b3d_assemble.py).

Stage: post office counter (lakdi), peeche laal deewar + peeli India Post patti. Kirdaar = cutout tasveer
(2.5D, asli roshni/parchhai), counter ke peeche Bhaiya, saamne Golu. Har drishya ka apna camera + harkat.
"""
import json
import math
import os

import bpy

JOB = os.path.abspath(os.environ.get("B3D_JOB", "b3d_job"))
IDX = int(os.environ.get("B3D_SCENE", "0"))
PLAN = json.load(open(os.path.join(JOB, "plan.json"), encoding="utf-8"))
if IDX >= len(PLAN["scenes"]):
    print("B3D_SCENE_SKIP", IDX, "(itne drishya nahi)")
    raise SystemExit(0)
SC = PLAN["scenes"][IDX]
FPS = PLAN.get("fps", 24)
NF = max(2, int(SC["frames"]))
OUT = os.path.join(JOB, f"frames_{IDX}")
R = math.radians


def P(rel):
    return os.path.join(JOB, rel)


# ======================================================================= setup
bpy.ops.wm.read_factory_settings(use_empty=True)
S = bpy.context.scene
for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        S.render.engine = eng
        break
    except TypeError:
        continue
if hasattr(S, "eevee"):
    for k, v in (("taa_render_samples", 20), ("use_gtao", True), ("use_shadows", True)):
        if hasattr(S.eevee, k):
            try:
                setattr(S.eevee, k, v)
            except Exception:
                pass
try:
    S.view_settings.view_transform = "Standard"
except Exception:
    pass
S.render.resolution_x, S.render.resolution_y, S.render.resolution_percentage = 720, 1280, 100
S.render.fps = FPS
S.frame_start, S.frame_end = 1, NF
S.render.image_settings.file_format = "PNG"
S.render.filepath = os.path.join(OUT, "f_")
S.world = bpy.data.worlds.new("W")
S.world.use_nodes = True
_bg = S.world.node_tree.nodes.get("Background")
_bg.inputs["Color"].default_value = (0.05, 0.06, 0.1, 1)
_bg.inputs["Strength"].default_value = 0.7


def F(sec):
    return max(1, min(NF, int(round(sec * FPS)) + 1))


def mat(name, color, rough=0.5, metal=0.0, emit=None, es=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = tuple(color) + (1,)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit is not None:
        for nm in ("Emission Color", "Emission"):
            if nm in b.inputs:
                b.inputs[nm].default_value = tuple(emit) + (1,)
                break
        b.inputs["Emission Strength"].default_value = es
    return m


def box(loc, scale, m, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = scale
    o.data.materials.append(m)
    return o


_IMG = {}


def img_plane(rel, height, loc, rot=(R(90), 0, 0), emit=0.0, name="img"):
    """Tasveer wala plane (alpha ke saath) - kirdaar/likhai. Saamne -Y ki taraf."""
    path = P(rel)
    if path not in _IMG:
        _IMG[path] = bpy.data.images.load(path)
    im = _IMG[path]
    w_, h_ = im.size
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = (height * w_ / max(1, h_), height, 1)
    m = bpy.data.materials.new(name + "_m")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    b.inputs["Roughness"].default_value = 0.8
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = im
    tx.interpolation = "Cubic"
    nt.links.new(tx.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(tx.outputs["Alpha"], b.inputs["Alpha"])
    if emit > 0:
        for nm in ("Emission Color", "Emission"):
            if nm in b.inputs:
                nt.links.new(tx.outputs["Color"], b.inputs[nm])
                break
        b.inputs["Emission Strength"].default_value = emit
    for attr, val in (("surface_render_method", "DITHERED"), ("blend_method", "HASHED"),
                      ("shadow_method", "HASHED")):
        if hasattr(m, attr):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    o.data.materials.append(m)
    return o


def empty(loc=(0, 0, 0)):
    o = bpy.data.objects.new("e", None)
    S.collection.objects.link(o)
    o.location = loc
    return o


def parent(ch, par):
    bpy.context.view_layer.update()                 # warna matrix_world purana -> bachcha dugni jagah
    ch.parent = par
    ch.matrix_parent_inverse = par.matrix_world.inverted()


def K(o, attr, sec, val):
    setattr(o, attr, val)
    o.keyframe_insert(data_path=attr, frame=F(sec))


def pop_in(o, sec, d=0.3, over=1.18):
    """0 se uchhal ke aana (overshoot)."""
    full = tuple(o.scale)
    tiny = tuple(x * 0.0005 for x in full)
    K(o, "scale", 0, tiny)
    if F(sec) > 1:
        K(o, "scale", sec, tiny)
    K(o, "scale", sec + d * 0.6, tuple(x * over for x in full))
    K(o, "scale", sec + d, full)


def alive(o, phase=0.0, amp=0.03, start=0.0):
    """Kirdaar zinda: saans (z-scale) + halka jhoolna - har 0.25s keyframe."""
    base_s, base_r = tuple(o.scale), tuple(o.rotation_euler)
    t = start
    while t <= SC["dur"] + 0.01:
        k = math.sin(t * 2.4 + phase)
        K(o, "scale", t, (base_s[0], base_s[1] * (1 + amp * 0.6 * k), base_s[2]))
        K(o, "rotation_euler", t, (base_r[0], base_r[1] + R(1.4) * math.sin(t * 1.7 + phase), base_r[2]))
        t += 0.25


def light(kind, loc, energy, color=(1, 1, 1), size=3.0, rot=(0, 0, 0)):
    ld = bpy.data.lights.new(kind + str(len(bpy.data.lights)), kind)
    ld.energy = energy
    ld.color = color
    if kind == "AREA":
        ld.size = size
    lo = bpy.data.objects.new(ld.name, ld)
    S.collection.objects.link(lo)
    lo.location, lo.rotation_euler = loc, rot
    return lo


def camera(keys, tkeys, lens=40, focus=None, fstop=2.8):
    cd = bpy.data.cameras.new("cam")
    cd.lens = lens
    cam = bpy.data.objects.new("cam", cd)
    S.collection.objects.link(cam)
    S.camera = cam
    tgt = empty()
    c = cam.constraints.new("TRACK_TO")
    c.target, c.track_axis, c.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    for sec, loc in keys:
        K(cam, "location", sec, loc)
    for sec, loc in tkeys:
        K(tgt, "location", sec, loc)
    if focus is not None:
        cd.dof.use_dof = True
        cd.dof.focus_object = focus
        cd.dof.aperture_fstop = fstop
    return cam, tgt


def shake(cam, sec, amp=0.08, d=0.3):
    """Takkar par camera jhatka."""
    base = tuple(cam.location)
    K(cam, "location", sec - 0.02, base)
    n = 6
    for i in range(1, n + 1):
        a = amp * (1 - i / n)
        K(cam, "location", sec + d * i / n, (base[0] + a * (1 if i % 2 else -1), base[1], base[2] + a * 0.6 * (-1 if i % 2 else 1)))


def stage():
    """Post office: lakdi ka counter, laal deewar, peeli patti, roshni."""
    wood = mat("lakdi", (0.38, 0.21, 0.09), 0.45)
    box((0, -0.6, -1.25), (9, 1.6, 0.5), wood)                      # counter (oopar z=-1.0)
    box((0, -1.42, -1.25), (9, 0.06, 0.54), mat("kinara", (0.26, 0.13, 0.05), 0.4))
    box((0, -0.6, -2.4), (9, 1.5, 1.8), mat("counter_neeche", (0.3, 0.16, 0.07), 0.6))
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 5.0, 2.5), rotation=(R(90), 0, 0))
    w = bpy.context.object
    w.scale = (30, 16, 1)
    w.data.materials.append(mat("deewar", (0.55, 0.09, 0.08), 0.85))
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 4.95, 4.0), rotation=(R(90), 0, 0))
    p = bpy.context.object
    p.scale = (30, 0.9, 1)
    p.data.materials.append(mat("patti", (0.96, 0.74, 0.1), 0.6))
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 1.5, -2.6))
    fl = bpy.context.object
    fl.scale = (30, 20, 1)
    fl.data.materials.append(mat("farsh", (0.32, 0.3, 0.28), 0.7))
    # deewar par letter box (laal dabba) - post office ki pehchaan
    box((3.4, 4.4, 0.6), (0.9, 0.6, 1.3), mat("letterbox", (0.8, 0.05, 0.05), 0.35))
    box((3.4, 4.08, 0.95), (0.6, 0.02, 0.08), mat("chhed", (0.05, 0.05, 0.05), 0.8))
    light("AREA", (3.5, -5, 5), 1500, (1.0, 0.93, 0.82), 6, (R(50), 0, R(35)))
    light("AREA", (-4.5, -3.5, 2.5), 600, (0.75, 0.85, 1.0), 5, (R(70), 0, R(-50)))
    light("AREA", (0, 3.5, 5), 700, (1.0, 0.85, 0.6), 5, (R(-40), 0, 0))


def lifaafa(rel, loc, w=2.0):
    """3D lifaafa: kaagaz ki body + saamne pata wali tasveer."""
    root = empty(loc)
    h = w * 0.636
    b = box(loc, (w, 0.025, h), mat("kaagaz", (0.95, 0.93, 0.88), 0.7))
    parent(b, root)
    fr = img_plane(rel, h, (loc[0], loc[1] - 0.015, loc[2]), name="pata")
    fr.scale = (w, h, 1)
    parent(fr, root)
    return root


def bhaiya_at(rel, x=1.5, h=3.4):
    o = img_plane(rel, h, (x, 0.9, -1.55 + h / 2), name="bhaiya")         # counter ke peeche (kamar chhupi)
    return o


def golu_at(rel, x=-1.6, h=3.6):
    o = img_plane(rel, h, (x, -2.3, -2.2 + h / 2), name="golu")           # saamne, grahak
    return o


stage()
T = SC["dur"]

# ======================================================================= drishya
if SC["kind"] == "ruko":
    board = img_plane(SC["board"], 2.9, (0.0, -0.4, 0.55), rot=(R(84), 0, 0), name="board")
    box((0, -0.32, -0.95), (2.6, 0.5, 0.1), mat("stand", (0.2, 0.2, 0.25), 0.4))
    st = img_plane(SC["stamp"], 0.75, (0.1, -0.6, 1.95), rot=(R(84), 0, R(-6)), name="stamp")
    K(st, "location", 0, (0.1, -1.6, 3.4))
    K(st, "rotation_euler", 0, (R(60), 0, R(25)))
    K(st, "location", 0.22, (0.1, -0.62, 1.95))
    K(st, "rotation_euler", 0.22, (R(84), 0, R(-6)))
    bh = bhaiya_at(SC["bhaiya"], x=2.45, h=3.0)
    K(bh, "location", 0, (4.6, 0.9, -0.05))
    K(bh, "location", 0.9, (4.6, 0.9, -0.05))
    K(bh, "location", 1.35, (2.45, 0.9, -0.05))
    alive(bh, 0.7, start=1.4)
    cam, _ = camera([(0, (0.0, -7.6, 0.7)), (T, (0.15, -6.0, 0.55))], [(0, (0, 0, 0.45)), (T, (0.1, 0, 0.5))],
                    lens=38, focus=board, fstop=4.0)
    shake(cam, 0.23, 0.05, 0.25)

elif SC["kind"] == "story":
    who = SC.get("who", "customer")
    bh = bhaiya_at(SC["bhaiya"], x=1.45)
    go = golu_at(SC["golu"], x=-1.55)
    alive(bh, 0.4)
    alive(go, 1.9)
    env = lifaafa(SC["env"], (-0.6, -0.9, -0.62), w=1.5)
    K(env, "rotation_euler", 0, (R(-70), 0, R(-20)))
    K(env, "location", 0, (-1.2, -1.6, -0.9))
    K(env, "location", 0.6, (0.0, -0.95, -0.35))
    K(env, "rotation_euler", 0.6, (R(-8), 0, R(4)))
    K(env, "location", T, (0.05, -0.95, -0.28))
    sx = -1.0 if who != "postman" else 1.2
    bub = img_plane(SC["bubble"], 1.25, (sx, -0.3, 1.75), name="bubble")
    pop_in(bub, 0.25)
    if SC.get("mark"):
        mk = img_plane(SC["mark"], 1.0, (1.45, -1.2, 0.2), name="mark", emit=0.6)
        pop_in(mk, max(0.4, SC.get("t_mark", T * 0.7)), 0.3, 1.3)
    # camera: bolne wale ki taraf halka ghoomna (har drishya alag)
    side = 1 if who == "postman" else -1
    cam, _ = camera([(0, (-side * 1.0, -7.4, 0.9)), (T, (side * 0.6, -6.3, 0.75))],
                    [(0, (0, 0, 0.3)), (T, (side * 0.35, 0, 0.35))], lens=36, focus=env, fstop=3.2)

elif SC["kind"] == "galti":
    bh = bhaiya_at(SC["bhaiya"], x=1.5)
    go = golu_at(SC["golu"], x=-1.6)
    env = lifaafa(SC["env"], (0, -0.95, -0.2), w=1.8)
    T_OUT, T_BACK, T_HIT = 0.55, 1.0, 1.45
    K(env, "location", 0, (0, -0.95, -0.2))
    K(env, "location", 0.35, (0, -0.95, -0.2))
    K(env, "location", T_OUT, (-0.3, -0.95, -0.25))                  # anticipation
    K(env, "rotation_euler", T_OUT, (0, 0, R(6)))
    K(env, "location", T_BACK - 0.02, (6.0, -0.4, 1.2))              # ud ke bahar
    K(env, "rotation_euler", T_BACK - 0.02, (R(30), R(-90), R(-40)))
    K(env, "location", T_HIT, (0, -0.95, -0.2))                      # laut ke dhadaam
    K(env, "rotation_euler", T_HIT, (0, 0, 0))
    K(env, "location", T, (0, -0.95, -0.16))
    st = img_plane(SC["stamp"], 0.7, (0.15, -1.05, -0.15), rot=(R(90), 0, R(-8)), name="stamp", emit=0.3)
    full = tuple(st.scale)
    K(st, "scale", 0, (0.0005, 0.0005, 0.0005))
    K(st, "scale", T_HIT - 0.05, (0.0005, 0.0005, 0.0005))
    K(st, "scale", T_HIT, tuple(x * 2.3 for x in full))
    K(st, "scale", T_HIT + 0.14, full)
    # kirdaar: takkar ke baad - Bhaiya uchhle, Golu jhuke
    K(bh, "location", 0, (1.5, 0.9, -3.6))
    K(bh, "location", T_HIT + 0.05, (1.5, 0.9, -3.6))
    K(bh, "location", T_HIT + 0.3, (1.5, 0.9, 0.55))
    K(bh, "location", T_HIT + 0.5, (1.5, 0.9, 0.15))
    K(go, "location", 0, (-1.6, -2.3, -4.0))
    K(go, "location", T_HIT + 0.1, (-1.6, -2.3, -4.0))
    K(go, "location", T_HIT + 0.45, (-1.6, -2.3, -0.4))
    K(go, "location", T, (-1.6, -2.3, -0.5))
    K(go, "rotation_euler", T_HIT + 0.45, (R(90), R(0), 0))
    K(go, "rotation_euler", T, (R(90), R(-4), 0))
    cam, _ = camera([(0, (0.2, -6.4, 0.6)), (T_HIT, (0.1, -6.0, 0.5)), (T, (0.0, -6.6, 0.7))],
                    [(0, (0, -0.9, -0.1)), (T, (0, 0, 0.2))], lens=36, focus=env, fstop=3.5)
    shake(cam, T_HIT, 0.1, 0.28)

elif SC["kind"] == "ans":
    # globe
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=0.8, location=(-1.9, 1.6, 0.4))
    gl = bpy.context.object
    bpy.ops.object.shade_smooth()
    gm = bpy.data.materials.new("globe")
    gm.use_nodes = True
    nt = gm.node_tree
    bs = nt.nodes.get("Principled BSDF")
    bs.inputs["Roughness"].default_value = 0.35
    tc, nz, cr = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeTexNoise"), nt.nodes.new("ShaderNodeValToRGB")
    nz.inputs["Scale"].default_value = 2.2
    nz.inputs["Detail"].default_value = 6.0
    cr.color_ramp.interpolation = "CONSTANT"
    cr.color_ramp.elements[0].color = (0.05, 0.28, 0.75, 1)
    cr.color_ramp.elements[1].position = 0.53
    cr.color_ramp.elements[1].color = (0.18, 0.62, 0.22, 1)
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], bs.inputs["Base Color"])
    gl.data.materials.append(gm)
    gold = mat("sona", (0.85, 0.62, 0.18), 0.25, 0.9)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.93, minor_radius=0.04, location=(-1.9, 1.6, 0.4),
                                     rotation=(0, R(90), R(20)))
    bpy.context.object.data.materials.append(gold)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.06, depth=1.0, location=(-1.9, 1.6, -0.5))
    bpy.context.object.data.materials.append(gold)
    gl.rotation_euler = (R(23), 0, 0)
    K(gl, "rotation_euler", 0, (R(23), 0, 0))
    K(gl, "rotation_euler", T, (R(23), 0, R(140)))
    bh = bhaiya_at(SC["bhaiya"], x=2.1, h=3.0)
    alive(bh, 0.3)
    go = golu_at(SC["golu"], x=-2.4, h=3.2)
    K(go, "location", 0, (-2.4, -2.3, -4.2))
    K(go, "location", 0.5, (-2.4, -2.3, -4.2))
    K(go, "location", 0.85, (-2.4, -2.3, -0.6))
    t = 0.85
    while t < T:                                                        # khushi me uchhalna
        K(go, "location", t + 0.15, (-2.4, -2.3, -0.35))
        K(go, "location", t + 0.3, (-2.4, -2.3, -0.6))
        t += 0.3
    env = lifaafa(SC["env"], (0.15, -0.9, -0.1), w=2.0)
    K(env, "location", 0, (2.4, -2.0, -2.4))
    K(env, "rotation_euler", 0, (R(-60), R(-200), R(40)))
    K(env, "location", 1.1, (0.15, -0.9, 0.0))
    K(env, "rotation_euler", 1.1, (R(6), R(3), R(-5)))
    K(env, "location", 1.35, (0.15, -0.9, -0.05))
    K(env, "rotation_euler", 1.35, (0, 0, 0))
    K(env, "location", T, (0.15, -0.9, 0.03))
    chk = empty((1.25, -1.25, -0.4))
    green = mat("hara", (0.1, 0.75, 0.3), 0.3, emit=(0.1, 0.9, 0.35), es=1.6)
    a_ = box((1.13, -1.25, -0.46), (0.3, 0.09, 0.09), green, rot=(0, R(45), 0))
    b_ = box((1.4, -1.25, -0.3), (0.56, 0.09, 0.09), green, rot=(0, R(-55), 0))
    parent(a_, chk)
    parent(b_, chk)
    K(chk, "scale", 0, (0.001, 0.001, 0.001))
    K(chk, "scale", 1.6, (0.001, 0.001, 0.001))
    K(chk, "scale", 1.8, (1.35, 1.35, 1.35))
    K(chk, "scale", 1.95, (1, 1, 1))
    light("POINT", (-1.4, 0.5, 1.6), 120, (0.6, 0.8, 1.0))
    camera([(0, (0.9, -6.8, 1.2)), (1.1, (0.5, -6.1, 0.8)), (T, (0.3, -4.9, 0.4))],
           [(0, (0, 0.3, 0.2)), (T, (0.35, -0.9, -0.05))], lens=40, focus=env, fstop=2.2)

elif SC["kind"] == "guide":
    # khuli kitaab counter par: baayan panna saada, daayan panna PO Guide ki line (highlight)
    root = empty((0, -0.6, -0.97))
    lp = box((-0.78, -0.6, -0.93), (1.5, 1.9, 0.04), mat("panna_l", (0.97, 0.95, 0.88), 0.8), rot=(0, R(-6), 0))
    parent(lp, root)
    rp = img_plane(SC["page"], 1.95, (0.78, -0.6, -0.9), rot=(0, R(6), 0), name="page")
    parent(rp, root)
    cov = box((0, -0.6, -0.97), (3.3, 2.1, 0.03), mat("jild", (0.1, 0.2, 0.45), 0.5))
    parent(cov, root)
    cam, _ = camera([(0, (-0.6, -3.8, 2.6)), (T, (0.7, -2.4, 1.2))], [(0, (0, -0.6, -0.95)), (T, (0.78, -0.6, -0.9))],
                    lens=38, focus=rp, fstop=4.0)

elif SC["kind"] == "end":
    y0 = -1.0
    cards = [(SC["notes"], 1.45, (0, y0, 1.55), 0.05), (SC["share"], 0.72, (0, y0, 0.35), 0.45),
             (SC["mock"], 0.6, (0, y0, -0.45), 0.9), (SC["follow"], 0.33, (-0.45, y0, -1.15), 1.3)]
    for rel, h, loc, t0 in cards:
        o = img_plane(rel, h, loc, name="card", emit=0.35)
        pop_in(o, t0, 0.32)
    bh = bhaiya_at(SC["bhaiya"], x=1.75, h=2.6)
    K(bh, "location", 0, (4.2, 0.9, -0.25))
    K(bh, "location", 1.3, (4.2, 0.9, -0.25))
    K(bh, "location", 1.65, (1.75, 0.9, -0.25))
    alive(bh, 0.9, start=1.7)
    camera([(0, (0, -6.8, 0.25)), (T, (0, -6.2, 0.2))], [(0, (0, 0, 0.2)), (T, (0, 0, 0.2))], lens=36)

os.makedirs(OUT, exist_ok=True)
print("B3D_SCENE_START", IDX, SC["name"], SC["kind"], NF, "frames", S.render.engine)
bpy.ops.render.render(animation=True)
print("B3D_SCENE_DONE", IDX, OUT)
