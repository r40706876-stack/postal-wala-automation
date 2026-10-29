"""
3D KIRDAAR + SAAMAAN ki jhalak (demo v26). Kuch post nahi hota.
  B3D_MODE=sheet  -> 7 frame (1280x720): Bhaiya + Golu, har frame ek bhaav
  B3D_MODE=props  -> 1 frame (1280x720): saara saamaan ek line me
  B3D_MODE=motion -> ~3.5s (540x960): post office me Golu chal ke aata, Bhaiya haath hilate/bolte, ✓, uchhal
Chalana: B3D_MODE=sheet B3D_OUT=/tmp/sheet xvfb-run -a blender -b -t 2 --python b3d_charsheet.py
"""
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b3d_chars as C
import b3d_assets as A

R = math.radians
MODE = os.environ.get("B3D_MODE", "sheet")
OUT = os.environ.get("B3D_OUT", f"/tmp/b3d_{MODE}")
EMOS = ["khush", "shabaash", "batata", "sochta", "chauka", "udaas", "gussa"]

bpy.ops.wm.read_factory_settings(use_empty=True)
S = bpy.context.scene
C.init(S, 24)
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
S.render.fps = 24
S.render.image_settings.file_format = "PNG"
S.render.filepath = os.path.join(OUT, "f_")
S.world = bpy.data.worlds.new("W")
S.world.use_nodes = True
bg = S.world.node_tree.nodes.get("Background")
bg.inputs["Color"].default_value = (0.55, 0.78, 1.0, 1)
bg.inputs["Strength"].default_value = 1.0


def sun(rot=(R(55), 0, R(-25)), energy=3.2):
    ld = bpy.data.lights.new("suraj", "SUN")
    ld.energy = energy
    try:
        ld.angle = R(4)
    except Exception:
        pass
    lo = bpy.data.objects.new("suraj", ld)
    S.collection.objects.link(lo)
    lo.rotation_euler = rot
    return lo


def camera(loc, look, lens=40, keys=None):
    cd = bpy.data.cameras.new("cam")
    cd.lens = lens
    cam = bpy.data.objects.new("cam", cd)
    S.collection.objects.link(cam)
    S.camera = cam
    tgt = C.empty("cam_tgt", None, look)
    c = cam.constraints.new("TRACK_TO")
    c.target, c.track_axis, c.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    cam.location = loc
    for sec, l_, t_ in (keys or []):
        C.K(cam, "location", sec, l_)
        C.K(tgt, "location", sec, t_)
    return cam


sun()
if MODE == "sheet":
    S.render.resolution_x, S.render.resolution_y = 1280, 720
    S.frame_start, S.frame_end = 1, len(EMOS)
    A.post_office()
    bh = C.build_bhaiya(-1.05, 0, face=-8)
    go = C.build_golu(1.05, 0, face=8)
    for i, e in enumerate(EMOS):
        for c in (bh, go):
            C.emotion(c, e, i / 24)
    camera((0, -7.2, 1.55), (0, 0, 1.35), lens=38)

elif MODE == "props":
    S.render.resolution_x, S.render.resolution_y = 1280, 720
    S.frame_start = S.frame_end = 1
    A.post_office()
    A.counter(None, (0, -0.2, 0), w=8.0)
    TOP = 1.06 - 0.2 * 0                                                   # counter ki sataha
    A.letter_box(None, (-3.4, -1.4, 0))
    A.parcel(None, (-2.1, -1.5, 0))
    A.taraazu(None, (-1.0, -0.45, TOP))
    A.mohar(None, (0.05, -0.5, TOP))
    A.globe(None, (1.2, -0.3, TOP), 0.42)
    A.sikka(None, (2.15, -0.6, TOP + 0.18))
    lf = A.lifaafa(None, None, (2.9, -0.55, 1.45), w=0.9)
    lf.rotation_euler = (0, 0, R(-12))
    s_ = A.sahi(None, (3.6, -1.0, 2.0), 1.1)
    g_ = A.galat(None, (-3.5, -1.0, 2.2), 1.0)
    camera((0, -8.6, 2.2), (0, 0, 1.1), lens=32)

else:   # motion
    S.render.resolution_x, S.render.resolution_y = 540, 960
    T = 3.6
    S.frame_start, S.frame_end = 1, int(T * 24)
    A.post_office()
    A.counter(None, (0, -0.25, 0), w=7.0)
    A.taraazu(None, (1.9, -0.35, 1.06))
    bh = C.build_bhaiya(0.85, 0.45, face=-18)
    go = C.build_golu(-3.6, -1.75, face=22)
    C.idle(bh, 0, T, 0.3)
    C.idle(go, 0, T, 1.7)
    C.walk_in(go, 0.0, 1.15, (-3.6, -1.75, 0), (-1.05, -1.75, 0))
    C.emotion(bh, "khush", 0.05)
    C.wave(bh, 0.2, 1.15)
    C.emotion(go, "khush", 0.05)
    C.emotion(bh, "batata", 1.25)
    C.talk(bh, 1.3, 2.15)
    C.emotion(go, "sochta", 1.3)
    lf = A.lifaafa(None, None, (0.0, -0.5, 1.4), w=0.8)
    lf.rotation_euler = (R(-8), 0, R(-6))
    C.K(lf, "scale", 0, (0.001, 0.001, 0.001))
    C.K(lf, "scale", 2.1, (0.001, 0.001, 0.001))
    C.K(lf, "scale", 2.3, (1.2, 1.2, 1.2))
    C.K(lf, "scale", 2.42, (1, 1, 1))
    C.emotion(go, "chauka", 2.2)
    C.emotion(bh, "shabaash", 2.6)
    C.emotion(go, "khush", 2.65)
    C.jump(go, 2.7)
    s_ = A.sahi(None, (0.55, -1.0, 2.55), 0.9)
    C.K(s_, "scale", 0, (0.001, 0.001, 0.001))
    C.K(s_, "scale", 2.75, (0.001, 0.001, 0.001))
    C.K(s_, "scale", 2.92, (1.35, 1.35, 1.35))
    C.K(s_, "scale", 3.05, (1, 1, 1))
    C.K(s_, "rotation_euler", 2.75, (0, 0, R(-25)))
    C.K(s_, "rotation_euler", T, (0, 0, R(10)))
    camera((0, -8.6, 2.0), (-0.1, 0, 1.5), lens=34,
           keys=[(0, (-0.6, -9.0, 2.1), (-0.6, 0, 1.5)), (1.2, (-0.2, -8.4, 1.95), (-0.1, 0, 1.5)),
                 (T, (0.1, -7.4, 1.8), (0.0, 0, 1.55))])

os.makedirs(OUT, exist_ok=True)
print("B3D_CHARS_START", MODE, S.frame_start, S.frame_end, S.render.engine)
bpy.ops.render.render(animation=True)
print("B3D_CHARS_DONE", MODE, OUT)
