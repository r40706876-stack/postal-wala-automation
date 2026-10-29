"""
POORI REEL - 3D KIRDAARON SE (v27, 2026-10-29). b3d_prep.py ka b3d_job/plan.json padhta hai.
Har drishya me asli 3D Bhaiya + Golu (b3d_chars) - bolte (munh), bhaav badalte, haath hilaate, uchhalte.
Render TUKDON me (B3D_CHUNK = 0,1,2... har tukda <= CHUNK frame) - kai runner ek saath -> tez.
  B3D_JOB=b3d_job B3D_CHUNK=3 xvfb-run -a blender -b -t 2 --python b3d_reel3d.py
Nateeja: b3d_job/frames_<drishya>/f_####.png (720x1280, 24fps). Likhai/caption baad me (b3d_assemble.py).
"""
import json
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b3d_chars as C
import b3d_assets as A

R = math.radians
JOB = os.path.abspath(os.environ.get("B3D_JOB", "b3d_job"))
CHUNK = int(os.environ.get("B3D_CHUNK_FRAMES", "40"))
IDX = int(os.environ.get("B3D_CHUNK", "0"))
PLAN = json.load(open(os.path.join(JOB, "plan.json"), encoding="utf-8"))
FPS = PLAN.get("fps", 24)

# ---- kaunsa drishya + kaunse frame (tukda) ----
chunks = []
for si, sc_ in enumerate(PLAN["scenes"]):
    n = int(sc_["frames"])
    for f0 in range(1, n + 1, CHUNK):
        chunks.append((si, f0, min(n, f0 + CHUNK - 1)))
if IDX >= len(chunks):
    print("B3D_CHUNK_SKIP", IDX, "kul tukde", len(chunks))
    raise SystemExit(0)
SI, F0, F1 = chunks[IDX]
SC = PLAN["scenes"][SI]
T = SC["dur"]
OUT = os.path.join(JOB, f"frames_{SI}")
print("B3D_CHUNK", IDX, "/", len(chunks), "drishya", SI, SC["name"], SC["kind"], "frame", F0, "-", F1)


def P(rel):
    return os.path.join(JOB, rel)


# ======================================================================= setup
bpy.ops.wm.read_factory_settings(use_empty=True)
S = bpy.context.scene
C.init(S, FPS)
for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        S.render.engine = eng
        break
    except TypeError:
        continue
if hasattr(S, "eevee"):
    for k, v in (("taa_render_samples", 8), ("use_gtao", False), ("use_shadows", True)):
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
S.frame_start, S.frame_end = F0, F1
S.render.image_settings.file_format = "PNG"
S.render.filepath = os.path.join(OUT, "f_")
S.world = bpy.data.worlds.new("W")
S.world.use_nodes = True
_bg = S.world.node_tree.nodes.get("Background")
_bg.inputs["Color"].default_value = (0.6, 0.8, 1.0, 1)
_bg.inputs["Strength"].default_value = 1.0
K = C.K


def sun(rot=(R(55), 0, R(-25)), energy=3.0):
    ld = bpy.data.lights.new("suraj", "SUN")
    ld.energy = energy
    try:
        ld.angle = R(5)
    except Exception:
        pass
    lo = bpy.data.objects.new("suraj", ld)
    S.collection.objects.link(lo)
    lo.rotation_euler = rot


def camera(keys, lens=35):
    cd = bpy.data.cameras.new("cam")
    cd.lens = lens
    cam = bpy.data.objects.new("cam", cd)
    S.collection.objects.link(cam)
    S.camera = cam
    tgt = C.empty("cam_tgt", None, keys[0][2])
    c = cam.constraints.new("TRACK_TO")
    c.target, c.track_axis, c.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    for sec, loc, look in keys:
        K(cam, "location", sec, loc)
        K(tgt, "location", sec, look)
    return cam


def shake(cam, sec, amp=0.06, d=0.28):
    base = tuple(cam.location)
    K(cam, "location", max(0, sec - 0.02), base)
    for i in range(1, 7):
        a = amp * (1 - i / 6)
        K(cam, "location", sec + d * i / 6,
          (base[0] + a * (1 if i % 2 else -1), base[1], base[2] + a * 0.6 * (-1 if i % 2 else 1)))


def pop(o, sec, d=0.3, over=1.2):
    full = tuple(o.scale)
    tiny = tuple(x * 0.0005 for x in full)
    K(o, "scale", 0, tiny)
    if C.F(sec) > 1:
        K(o, "scale", sec, tiny)
    K(o, "scale", sec + d * 0.6, tuple(x * over for x in full))
    K(o, "scale", sec + d, full)


def bubble(rel, x, z, sec=0.15, h=0.75):
    b = A.img_plane(P(rel), h, None, (x, -1.6, z), name="gubbara", emit=1.0)
    pop(b, sec)
    t = sec + 0.4
    while t < T:                                   # halka tairna
        K(b, "location", t, (x, -1.6, z + 0.025 * math.sin(t * 3)))
        t += 0.3
    return b


# ======================================================================= stage (sab drishyon me ek jaisa)
sun()
A.post_office()
A.counter(None, (0, -0.15, 0), w=8.0)
A.taraazu(None, (2.2, -0.25, 1.06))
A.mohar(None, (-2.3, -0.3, 1.06))
A.parcel(None, (3.1, -1.4, 0), (0.6, 0.45, 0.4))
BH_POS, GO_POS = (0.75, 0.55, 0), (-0.85, -1.55, 0)
kind = SC["kind"]
lead, vd = SC.get("lead", 0.1), SC.get("vd", 1.0)

# ======================================================================= drishya
if kind == "ruko":
    # sawal ka board counter par (bada) + mohar girti; Bhaiya sochte, Golu sir khujaata
    bd = A.img_plane(P(SC["board"]), 1.75, None, (-0.15, -0.75, 1.95), rot=(R(86), 0, 0), name="board", emit=1.0)
    A.cube("board_stand", A.cel("stand", (0.25, 0.25, 0.3)), None, (-0.15, -0.68, 1.12), (0.5, 0.25, 0.12))
    st = A.img_plane(P(SC["stamp"]), 0.42, None, (-0.1, -0.9, 2.95), rot=(R(86), 0, R(-6)), name="mohar_img", emit=1.0)
    K(st, "location", 0, (-0.1, -2.2, 4.4))
    K(st, "rotation_euler", 0, (R(60), 0, R(30)))
    K(st, "location", 0.22, (-0.1, -0.9, 2.95))
    K(st, "rotation_euler", 0.22, (R(86), 0, R(-6)))
    bh = C.build_bhaiya(1.35, 0.55, face=-22)
    go = C.build_golu(-1.3, -1.3, face=25)
    C.emotion(bh, "sochta", 0.0)
    C.emotion(go, "chauka", 0.05)
    C.emotion(go, "sochta", 1.2)
    C.idle(bh, 0, T, 0.4)
    C.idle(go, 0, T, 1.6)
    C.talk(bh, lead, lead + vd)
    cam = camera([(0, (0.0, -7.0, 2.35), (0.0, -0.6, 2.0)), (T, (0.1, -6.2, 2.25), (0.0, -0.6, 2.0))], lens=31)
    shake(cam, 0.23)

elif kind == "story":
    who = SC.get("who", "customer")
    bh = C.build_bhaiya(*BH_POS[:2], face=-20)
    go = C.build_golu(*GO_POS[:2], face=24)
    C.idle(bh, 0, T, 0.4)
    C.idle(go, 0, T, 1.6)
    wrong = SC.get("mark", "").endswith("mark_x.png")
    right = SC.get("mark", "").endswith("mark_ok.png")
    if who == "postman":
        C.emotion(bh, "batata", 0.05)
        C.emotion(go, "sochta" if wrong else "khush", 0.1)
        C.talk(bh, lead, lead + vd)
        bubble(SC["bubble"], 0.55, 3.45)
    else:
        C.emotion(go, "dikhao", 0.05)
        C.emotion(bh, "sochta", 0.15)
        C.talk(go, lead, lead + vd)
        bubble(SC["bubble"], -0.3, 3.45)
    lf = A.lifaafa(P(SC["env"]), None, (-0.1, -0.75, 1.4), w=0.95)
    lf.rotation_euler = (R(-6), 0, R(4))
    pop(lf, 0.2, 0.3, 1.15)
    tm = SC.get("t_mark", T * 0.7)
    if wrong:
        g = A.galat(None, (0.55, -1.0, 1.6), 0.8)
        pop(g, tm, 0.3, 1.35)
        C.emotion(bh, "gussa", tm)
        C.emotion(go, "chauka", tm + 0.05)
    elif right:
        s_ = A.sahi(None, (0.55, -1.0, 1.65), 0.8)
        pop(s_, tm, 0.3, 1.35)
        C.emotion(bh, "shabaash", tm)
        C.emotion(go, "khush", tm + 0.05)
    side = 1 if who == "postman" else -1
    camera([(0, (-side * 0.4, -7.6, 2.4), (-0.05, -0.5, 2.05)),
            (T, (side * 0.3, -6.9, 2.35), (side * 0.15, -0.5, 2.05))], lens=30)

elif kind == "galti":
    bh = C.build_bhaiya(*BH_POS[:2], face=-20)
    go = C.build_golu(*GO_POS[:2], face=24)
    C.idle(bh, 0, T, 0.4)
    C.idle(go, 0, T, 1.6)
    T_OUT, T_BACK, T_HIT = 0.55, 1.0, 1.45
    lf = A.lifaafa(P(SC["env"]), None, (0, -0.8, 1.55), w=1.05)
    K(lf, "location", 0.35, (0, -0.8, 1.55))
    K(lf, "location", T_OUT, (-0.3, -0.8, 1.5))
    K(lf, "rotation_euler", T_OUT, (0, 0, R(8)))
    K(lf, "location", T_BACK - 0.02, (5.5, -0.4, 2.6))
    K(lf, "rotation_euler", T_BACK - 0.02, (R(30), R(-90), R(-40)))
    K(lf, "location", T_HIT, (0, -0.8, 1.55))
    K(lf, "rotation_euler", T_HIT, (0, 0, 0))
    K(lf, "scale", T_HIT, (1, 1, 1))
    K(lf, "scale", T_HIT + 0.08, (1.12, 1, 0.88))
    K(lf, "scale", T_HIT + 0.2, (1, 1, 1))
    st = A.img_plane(P(SC["stamp"]), 0.36, None, (0.1, -0.86, 1.58), rot=(R(90), 0, R(-8)), name="galti_mohar")
    full = tuple(st.scale)
    K(st, "scale", 0, (0.0005, 0.0005, 0.0005))
    K(st, "scale", T_HIT - 0.04, (0.0005, 0.0005, 0.0005))
    K(st, "scale", T_HIT, tuple(x * 2.4 for x in full))
    K(st, "scale", T_HIT + 0.14, full)
    C.emotion(bh, "dikhao", 0.0)
    C.emotion(go, "khush", 0.0)
    C.emotion(bh, "chauka", T_HIT + 0.02)
    C.jump(bh, T_HIT + 0.02, 0.25, 0.4)
    C.emotion(go, "udaas", T_HIT + 0.15)
    C.talk(bh, lead, lead + vd)
    cam = camera([(0, (0.1, -6.0, 2.15), (0, -0.8, 1.8)), (T_HIT, (0.0, -5.6, 2.1), (0, -0.8, 1.8)),
                  (T, (0.0, -7.0, 2.4), (0, -0.4, 2.0))], lens=31)
    shake(cam, T_HIT, 0.09)

elif kind == "ans":
    if SC.get("foreign", True):                       # videshi niyam -> ghoomta globe
        gr, gl = A.globe(None, (-2.35, 0.2, 1.06), 0.38)
        K(gl, "rotation_euler", 0, (0, 0, 0))
        K(gl, "rotation_euler", T, (0, 0, R(160)))
    else:
        A.letter_box(None, (-2.6, 0.6, 0))
    bh = C.build_bhaiya(*BH_POS[:2], face=-20)
    go = C.build_golu(*GO_POS[:2], face=24)
    C.idle(bh, 0, T, 0.4)
    C.idle(go, 0, T, 1.6)
    lf = A.lifaafa(P(SC["env"]), None, (-0.05, -0.85, 1.55), w=1.15)
    K(lf, "location", 0, (2.6, -2.2, 0.4))
    K(lf, "rotation_euler", 0, (R(-60), R(-200), R(40)))
    K(lf, "location", 0.9, (-0.05, -0.85, 1.6))
    K(lf, "rotation_euler", 0.9, (R(6), R(3), R(-5)))
    K(lf, "location", 1.1, (-0.05, -0.85, 1.55))
    K(lf, "rotation_euler", 1.1, (0, 0, 0))
    K(lf, "location", T, (-0.05, -0.85, 1.6))
    s_ = A.sahi(None, (0.75, -1.05, 2.15), 0.9)
    pop(s_, 1.15, 0.3, 1.4)
    K(s_, "rotation_euler", 1.15, (0, 0, R(-25)))
    K(s_, "rotation_euler", T, (0, 0, R(8)))
    C.emotion(bh, "batata", 0.0)
    C.emotion(go, "sochta", 0.0)
    C.emotion(bh, "shabaash", 1.2)
    C.emotion(go, "khush", 1.25)
    C.jump(go, 1.3, 0.4, 0.5)
    C.jump(go, 1.9, 0.3, 0.45)
    C.talk(bh, lead, lead + vd)
    camera([(0, (0.4, -7.0, 2.4), (0, -0.7, 2.0)), (1.1, (0.2, -6.3, 2.25), (0, -0.8, 1.9)),
            (T, (0.0, -6.0, 2.2), (0, -0.8, 1.9))], lens=31)

elif kind == "guide":
    # khuli PO Guide kitaab counter par, Bhaiya ungli se dikhate
    root = C.empty("kitaab", None, (0, -0.55, 1.08))
    A.cube("panna_l", A.cel("panna_l", (0.97, 0.95, 0.88)), root, (-0.62, 0, 0.03), (1.2, 1.5, 0.03),
           rot=(0, R(-6), 0))
    pg = A.img_plane(P(SC["page"]), 1.55, root, (0.62, 0, 0.06), rot=(0, R(6), 0), name="panna", emit=1.0)
    A.cube("jild", A.cel("jild", (0.1, 0.2, 0.45)), root, (0, 0, 0.0), (2.6, 1.65, 0.03))
    bh = C.build_bhaiya(1.6, 0.55, face=-35)
    C.idle(bh, 0, T, 0.4)
    C.emotion(bh, "batata", 0.0)
    C.talk(bh, lead, lead + vd)
    camera([(0, (-0.5, -3.6, 3.4), (0.2, -0.55, 1.1)), (T, (0.5, -2.5, 2.4), (0.6, -0.55, 1.1))], lens=34)

elif kind == "end":
    bh = C.build_bhaiya(0.0, 0.4, face=0)
    go = C.build_golu(-1.7, -1.2, face=20)
    C.idle(bh, 0, T, 0.4)
    C.idle(go, 0, T, 1.6)
    C.emotion(bh, "khush", 0.0)
    C.wave(bh, 0.1, min(T, 2.2))
    C.emotion(bh, "shabaash", min(T - 0.3, 2.3))
    C.emotion(go, "khush", 0.0)
    C.jump(go, 0.6, 0.3, 0.45)
    C.talk(bh, lead, lead + vd)
    camera([(0, (0.0, -6.0, 3.1), (-0.3, -0.4, 2.85)), (T, (0.0, -5.5, 3.0), (-0.3, -0.4, 2.8))], lens=33)  # upar card (jodne me)

os.makedirs(OUT, exist_ok=True)
print("B3D_RENDER", IDX, S.frame_start, S.frame_end, S.render.engine)
bpy.ops.render.render(animation=True)
print("B3D_CHUNK_DONE", IDX, OUT)
