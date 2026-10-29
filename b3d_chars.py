"""
Postal Wala ke 3D KIRDAAR (Blender, v26 2026-10-29) - cartoon (chibi) style, cel-shading + kaala outline.
  build_bhaiya(x, y)  -> Postal Wala Bhaiya: khaki vardi, topi, ghani moonchh, bhoora jhola + patta
  build_golu(x, y)    -> Golu: neeli check shirt, kaale khade baal, laal jhola
Har kirdaar ek dict (rig): root / head empty / baahen (kandha -> kohni -> haath) / aankh / bhauhen / munh.
Bhaav (emotion), keyframe ke saath:  emotion(c, "khush", sec)
  khush, shabaash (angootha), batata (ungli upar), sochta (thodi par haath), chauka (haath gaal par),
  udaas (sir jhuka), gussa
Harkat: blink(c, sec), talk(c, t0, t1), idle(c, t0, t1), wave(c, t0, t1), jump(c, sec), walk_in(c, ...)
Hindi likhai Blender me nahi - sirf English (zaroorat ho to).
"""
import math

import bpy

R = math.radians
FPS = 24
S = None                      # scene (init me)
_MATS = {}


def init(scene, fps=24):
    global S, FPS
    S, FPS = scene, fps


def F(sec):
    return max(1, int(round(sec * FPS)) + 1)


def K(o, attr, sec, val, interp=None):
    setattr(o, attr, tuple(val))
    o.keyframe_insert(data_path=attr, frame=F(sec))


# ======================================================================= saamagri (cel shading)
def _shade(c, k):
    return tuple(max(0.0, min(1.0, v * k)) for v in c)


def cel(name, color, outline=True):
    """Cartoon rang: roshni ke hisaab se 3 seedhi patti (andhera/rang/chamak) - Emission se, chamakdaar."""
    key = (name, tuple(round(v, 3) for v in color))
    if key in _MATS:
        return _MATS[key]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    try:
        dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
        s2r = nt.nodes.new("ShaderNodeShaderToRGB")
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        em = nt.nodes.new("ShaderNodeEmission")
        cr = ramp.color_ramp
        cr.interpolation = "CONSTANT"
        sh = (color[0] * 0.55, color[1] * 0.5, min(1.0, color[2] * 0.62 + 0.04))       # thandi chhaaya
        cr.elements[0].position = 0.0
        cr.elements[0].color = sh + (1,)
        cr.elements[1].position = 0.18
        cr.elements[1].color = tuple(color) + (1,)
        e3 = cr.elements.new(0.75)
        e3.color = _shade(color, 1.13) + (1,)
        nt.links.new(dif.outputs["BSDF"], s2r.inputs["Shader"])
        nt.links.new(s2r.outputs["Color"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
        em.inputs["Strength"].default_value = 1.0
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    except Exception as exc:                      # cel na chale -> saada rang
        print("CEL_FALLBACK", name, exc)
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        b.inputs["Base Color"].default_value = tuple(color) + (1,)
        nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    _MATS[key] = m
    return m


def flat(name, color, strength=1.0):
    """Bina chhaaya ka rang (aankh ka safed, kaala, chamak)."""
    key = ("flat", name, tuple(round(v, 3) for v in color))
    if key in _MATS:
        return _MATS[key]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = tuple(color) + (1,)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    _MATS[key] = m
    return m


def checker(name, c1, c2, scale=18.0):
    """Check wali shirt (Golu) - cel ke saath. Fail -> saada c1."""
    try:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
        s2r = nt.nodes.new("ShaderNodeShaderToRGB")
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        cr = ramp.color_ramp
        cr.interpolation = "CONSTANT"
        cr.elements[0].position = 0.0
        cr.elements[0].color = (0.62, 0.66, 0.8, 1)
        cr.elements[1].position = 0.18
        cr.elements[1].color = (1, 1, 1, 1)
        tc = nt.nodes.new("ShaderNodeTexCoord")
        ck = nt.nodes.new("ShaderNodeTexChecker")
        ck.inputs["Scale"].default_value = scale
        ck.inputs["Color1"].default_value = tuple(c1) + (1,)
        ck.inputs["Color2"].default_value = tuple(c2) + (1,)
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1.0
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(tc.outputs["Generated"], ck.inputs["Vector"])
        nt.links.new(dif.outputs["BSDF"], s2r.inputs["Shader"])
        nt.links.new(s2r.outputs["Color"], ramp.inputs["Fac"])
        nt.links.new(ck.outputs["Color"], mix.inputs[6])
        nt.links.new(ramp.outputs["Color"], mix.inputs[7])
        nt.links.new(mix.outputs[2], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        return m
    except Exception as exc:
        print("CHECKER_FALLBACK", exc)
        return cel(name + "_saada", c1)


_INK = None


def ink():
    """Outline ka kaala (sirf peeche ka chehra - 'inverted hull')."""
    global _INK
    if _INK is None:
        _INK = flat("ink", (0.04, 0.03, 0.05))
        for attr, val in (("use_backface_culling", True),):
            try:
                setattr(_INK, attr, val)
            except Exception:
                pass
    return _INK


def outline(o, th=0.018):
    """Cartoon ki kaali rekha: Solidify (ulti normals) + kaala material, saamne wala chehra chhupa."""
    try:
        if o.type != "MESH":
            return
        o.data.materials.append(ink())
        md = o.modifiers.new("rekha", "SOLIDIFY")
        md.thickness = th
        md.offset = 1.0
        md.use_flip_normals = True
        md.use_rim = False
        md.material_offset = len(o.data.materials) - 1
    except Exception as exc:
        print("OUTLINE_SKIP", exc)


# ======================================================================= aakar
def _link(o):
    if o.name not in S.collection.objects:
        try:
            S.collection.objects.link(o)
        except Exception:
            pass


def empty(name, parent=None, loc=(0, 0, 0)):
    o = bpy.data.objects.new(name, None)
    S.collection.objects.link(o)
    o.empty_display_size = 0.1
    if parent is not None:
        o.parent = parent
    o.location = loc
    return o


def ball(name, r, mat, parent, loc, scale=(1, 1, 1), rot=(0, 0, 0), line=True, seg=40):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=seg // 2, radius=r, location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    bpy.ops.object.shade_smooth()
    o.data.materials.append(mat)
    o.parent = parent
    o.location, o.scale, o.rotation_euler = loc, scale, rot
    if line:
        outline(o, 0.012 / max(0.3, min(scale)))          # duniya me ~0.012 moti rekha
    return o


def cyl(name, r, depth, mat, parent, loc, scale=(1, 1, 1), rot=(0, 0, 0), r2=None, line=True, verts=40):
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=(0, 0, 0))
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r2, depth=depth, location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    bpy.ops.object.shade_smooth()
    o.data.materials.append(mat)
    o.parent = parent
    o.location, o.scale, o.rotation_euler = loc, scale, rot
    if line:
        outline(o, 0.018)
    return o


def cube(name, mat, parent, loc, scale, rot=(0, 0, 0), bevel=0.0, line=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    o.data.materials.append(mat)
    if bevel > 0:
        try:
            b = o.modifiers.new("gol", "BEVEL")
            b.width = bevel
            b.segments = 3
        except Exception:
            pass
    o.parent = parent
    o.location, o.scale, o.rotation_euler = loc, scale, rot
    if line:
        outline(o, 0.015)
    return o


def tube(name, pts, r, mat, parent, loc=(0, 0, 0)):
    """Mudi hui rekha (bhauhen, munh, patta) - NURBS curve + gol mota."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 3
    try:
        cu.use_fill_caps = True
    except Exception:
        pass
    sp = cu.splines.new("NURBS")
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0], p[1], p[2], 1)
    sp.use_endpoint_u = True
    sp.order_u = min(4, len(pts))
    o = bpy.data.objects.new(name, cu)
    S.collection.objects.link(o)
    o.data.materials.append(mat)
    o.parent = parent
    o.location = loc
    return o


def arc(w, h, n=9, y=0.0):
    """Muskaan (h>0 = U), udaasi (h<0 = ∩): chaudai w, gehraai h."""
    return [(-w / 2 + w * i / (n - 1), y, -h * (1 - (2 * i / (n - 1) - 1) ** 2)) for i in range(n)]


def text3d(name, txt, size, mat, parent, loc, rot=(R(90), 0, 0), depth=0.02):
    """Sirf ENGLISH (Hindi Blender me bigadti hai)."""
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = txt
    cu.size = size
    cu.extrude = depth
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    o = bpy.data.objects.new(name, cu)
    S.collection.objects.link(o)
    o.data.materials.append(mat)
    o.parent = parent
    o.location, o.rotation_euler = loc, rot
    return o


# ======================================================================= kirdaar
SKIN_BH = (0.74, 0.47, 0.32)
SKIN_GO = (0.84, 0.6, 0.43)
KHAKI = (0.78, 0.66, 0.43)
KHAKI_D = (0.62, 0.51, 0.31)
BROWN = (0.42, 0.22, 0.09)
HAIR = (0.06, 0.05, 0.06)
NAVY = (0.08, 0.12, 0.32)
GOLD = (1.0, 0.75, 0.15)
RED = (0.85, 0.12, 0.12)


def _face(c, head, skin, eye_y=-0.47, big=1.0):
    """Aankhen (safed + putli + chamak), bhauhen, naak, kaan, munh ke saare roop."""
    white = flat("aankh_safed", (1, 1, 1))
    black = flat("putli", (0.03, 0.03, 0.05))
    shine = flat("chamak", (1, 1, 1), 1.4)
    c["eyes"], c["pupils"] = [], []
    for s in (-1, 1):
        e = ball(f"aankh{s}", 0.125 * big, white, head, (0.19 * s, eye_y, 0.07), (1, 0.55, 1.18), line=True)
        p = ball(f"putli{s}", 0.075 * big, black, e, (0.0, -0.12, -0.01), (1, 0.6, 1.1), line=False)
        ball(f"chamak{s}", 0.028 * big, shine, p, (0.03, -0.05, 0.035), line=False, seg=16)
        c["eyes"].append(e)
        c["pupils"].append(p)
    hair = flat("bhauh", HAIR)
    c["brows"] = []
    for s in (-1, 1):
        bw = empty(f"bhauh_e{s}", head, (0.19 * s, -0.46, 0.27 * big ** 0.5))
        tube(f"bhauh{s}", arc(0.2, -0.035), 0.026, hair, bw)
        c["brows"].append(bw)
    ball("naak", 0.075, cel("twacha_n", skin), head, (0, -0.56, -0.07), (1, 0.9, 0.9))
    for s in (-1, 1):
        ball(f"kaan{s}", 0.1, cel("twacha_k", skin), head, (0.53 * s, 0.02, -0.02), (0.6, 1, 1))
    # munh ke roop (scale 0 / 1 se badalte)
    lip = flat("hont", (0.35, 0.05, 0.07))
    mz = -0.3
    m = {}
    m["smile"] = tube("m_smile", arc(0.24, 0.07), 0.022, flat("rekha", (0.2, 0.05, 0.06)), empty("m_s", head, (0, -0.46, mz)))
    m["frown"] = tube("m_frown", arc(0.2, -0.06), 0.022, flat("rekha", (0.2, 0.05, 0.06)), empty("m_f", head, (0, -0.46, mz - 0.03)))
    m["flat"] = tube("m_flat", [(-0.08, 0, 0), (0, 0, 0.005), (0.08, 0, 0)], 0.02, flat("rekha", (0.2, 0.05, 0.06)),
                     empty("m_l", head, (0, -0.46, mz)))
    og = empty("m_open", head, (0, -0.47, mz - 0.03))
    ball("munh_khula", 0.14, lip, og, (0, 0, 0), (1, 0.35, 0.62), line=True)
    cube("daant", flat("daant", (1, 1, 1)), og, (0, -0.045, 0.045), (0.18, 0.02, 0.04), line=False)
    m["open"] = og
    oo = empty("m_O", head, (0, -0.48, mz - 0.03))
    ball("munh_O", 0.075, lip, oo, (0, 0, 0), (1, 0.4, 1.3), line=True)
    m["O"] = oo
    c["mouths"] = m
    for k, o in m.items():
        o.scale = (1, 1, 1) if k == "smile" else (0.001, 0.001, 0.001)
    # gaal ki laali
    blush = flat("laali", (1.0, 0.45, 0.45), 0.9)
    c["blush"] = []
    for s in (-1, 1):
        b = ball(f"laali{s}", 0.07, blush, head, (0.31 * s, -0.43, -0.13), (1.2, 0.3, 0.7), line=False, seg=16)
        b.scale = (0.001, 0.001, 0.001)
        c["blush"].append(b)


def _arms(c, body, skin, sleeve, sleeve_len=0.22, sx=0.43, sz=1.2, hand_r=0.1):
    c["arms"] = []
    sk = cel("twacha_b", skin)
    for s in (-1, 1):
        sh = empty(f"kandha{s}", body, (sx * s, 0, sz))
        cyl(f"aasteen{s}", 0.115, sleeve_len, sleeve, sh, (0, 0, -sleeve_len / 2 + 0.02))
        ball(f"baanh{s}", 0.085, sk, sh, (0, 0, -0.2), (1, 1, 2.3))
        el = empty(f"kohni{s}", sh, (0, 0, -0.36))
        ball(f"kalaai{s}", 0.075, sk, el, (0, 0, -0.15), (1, 1, 2.2))
        hd = empty(f"haath_e{s}", el, (0, 0, -0.33))
        ball(f"haath{s}", hand_r, sk, hd, (0, 0, 0), (1, 0.8, 1.05))
        th = empty(f"angootha_e{s}", hd, (0, -0.02, -0.02))          # shabaash: duniya me upar (hisaab se)
        th.rotation_euler = (R(148), R(-26 * s), 0)
        ball(f"angootha{s}", 0.04, sk, th, (0, 0, 0.08), (1, 1, 2.2))
        fi = empty(f"ungli_e{s}", hd, (0, -0.01, -0.07))             # batata: kalaai ki disha me
        ball(f"ungli{s}", 0.035, sk, fi, (0, 0, -0.09), (1, 1, 2.8))
        th.scale = fi.scale = (0.001, 0.001, 0.001)
        c["arms"].append({"s": s, "sh": sh, "el": el, "hand": hd, "thumb": th, "finger": fi})


def _legs(c, root, trouser, shoe, hip=0.55):
    for s in (-1, 1):
        lg = empty(f"taang_e{s}", root, (0.17 * s, 0, hip))
        ball(f"taang{s}", 0.13, trouser, lg, (0, 0, -0.24), (1, 1, 2.1))
        ball(f"joota{s}", 0.13, shoe, lg, (0, -0.07, -0.5), (1, 1.5, 0.55))
        c.setdefault("legs", []).append(lg)


def build_bhaiya(x=0.0, y=0.0, face=0.0):
    """Postal Wala Bhaiya: khaki vardi, topi (sunehra badge), ghani moonchh, bhoora patta + jhola."""
    c = {"name": "bhaiya"}
    root = empty("bhaiya", None, (x, y, 0))
    root.rotation_euler = (0, 0, R(face))
    c["root"] = root
    khaki, khaki_d = cel("khaki", KHAKI), cel("khaki_d", KHAKI_D)
    brown, skin = cel("bhoora", BROWN), cel("twacha", SKIN_BH)
    _legs(c, root, khaki_d, cel("joota", (0.1, 0.07, 0.06)))
    body = empty("dhad", root, (0, 0, 0))
    c["body"] = body
    ball("pet", 0.5, khaki, body, (0, 0, 0.98), (0.86, 0.66, 0.92))
    cyl("belt", 0.32, 0.08, brown, body, (0, 0, 0.66), (1, 0.76, 1))
    cube("bakkal", flat("pital", GOLD), body, (0, -0.25, 0.66), (0.11, 0.03, 0.08), line=True)
    for s in (-1, 1):                                                       # jeb + bataan + kandhe ki patti
        cube(f"jeb{s}", khaki_d, body, (0.18 * s, -0.31, 1.06), (0.16, 0.03, 0.15), bevel=0.01)
        cube(f"epaulet{s}", khaki_d, body, (0.32 * s, 0.0, 1.38), (0.2, 0.18, 0.03))
    for z in (0.78, 0.92, 1.06, 1.2):
        ball(f"bataan{z}", 0.02, flat("pital_b", GOLD), body, (0, -0.33, z), line=False, seg=12)
    cube("naam_patti", flat("navy", NAVY), body, (0.18, -0.335, 1.2), (0.17, 0.01, 0.05), line=False)
    tube("patta", [(-0.33, -0.3, 1.36), (-0.1, -0.36, 1.12), (0.15, -0.36, 0.88), (0.36, -0.28, 0.68)], 0.032,
         brown, body)
    bag = empty("jhola_e", body, (0.46, -0.08, 0.6))
    cube("jhola", brown, bag, (0, 0, 0), (0.15, 0.3, 0.26), bevel=0.03)
    cube("jhola_dhakkan", cel("bhoora_d", (0.32, 0.16, 0.06)), bag, (-0.005, -0.02, 0.07), (0.16, 0.31, 0.13),
         bevel=0.02)
    c["bag"] = bag
    _arms(c, body, SKIN_BH, khaki)
    head = empty("sir", body, (0, 0, 1.4))
    c["head"] = head
    ball("chehra", 0.55, skin, head, (0, 0, 0.36), (1, 0.95, 0.98))
    ball("baal", 0.53, cel("baal", HAIR), head, (0, 0.08, 0.5), (1.02, 0.97, 0.8))
    f = empty("chehra_e", head, (0, 0, 0.36))
    _face(c, f, SKIN_BH)
    must = cel("moonchh", HAIR)                                            # ghani moonchh (pehchaan)
    for s in (-1, 1):
        ball(f"moonchh{s}", 0.1, must, f, (0.1 * s, -0.53, -0.17), (1.45, 0.55, 0.62), (0, R(-18 * s), 0))
    cap = empty("topi_e", head, (0, 0, 0.82))
    cyl("topi", 0.47, 0.32, khaki, cap, (0, 0.02, 0.1), r2=0.56)
    cyl("topi_patti", 0.5, 0.09, brown, cap, (0, 0.02, -0.02), line=True)
    cyl("chhajja", 0.42, 0.045, cel("chhajja", (0.14, 0.09, 0.05)), cap, (0, -0.32, -0.06), (1, 0.62, 1),
        (R(-14), 0, 0))
    cyl("topi_badge", 0.07, 0.02, flat("pital_c", GOLD), cap, (0, -0.47, 0.12), rot=(R(90), 0, 0))
    c["cap"] = cap
    pose(c, "rest", 0.0)
    return c


def build_golu(x=0.0, y=0.0, face=0.0):
    """Golu (grahak): neeli check shirt, kaale khade baal, laal jhola, gehri patloon."""
    c = {"name": "golu"}
    root = empty("golu", None, (x, y, 0))
    root.rotation_euler = (0, 0, R(face))
    c["root"] = root
    shirt = checker("check_shirt", (0.55, 0.75, 1.0), (0.85, 0.93, 1.0), 22.0)
    skin = cel("twacha_g", SKIN_GO)
    _legs(c, root, cel("patloon", (0.12, 0.13, 0.2)), cel("joota_g", (0.35, 0.2, 0.1)), hip=0.6)
    body = empty("dhad", root, (0, 0, 0.05))
    c["body"] = body
    ball("pet", 0.48, shirt, body, (0, 0, 0.98), (0.8, 0.62, 0.92))
    for z in (0.8, 0.95, 1.1, 1.25):
        ball(f"bataan{z}", 0.018, flat("bataan_g", (0.95, 0.95, 1.0)), body, (0, -0.3, z), line=False, seg=12)
    cube("kalar", cel("kalar", (0.75, 0.87, 1.0)), body, (0, -0.15, 1.36), (0.32, 0.22, 0.05), (R(-15), 0, 0))
    tube("laal_patta", [(0.33, -0.28, 1.36), (0.1, -0.33, 1.12), (-0.15, -0.33, 0.88), (-0.36, -0.25, 0.7)], 0.03,
         cel("laal", RED), body)
    bag = empty("jhola_e", body, (-0.45, -0.05, 0.62))
    cube("laal_jhola", cel("laal_j", RED), bag, (0, 0, 0), (0.13, 0.28, 0.3), bevel=0.04)
    c["bag"] = bag
    _arms(c, body, SKIN_GO, shirt, sleeve_len=0.26, sx=0.41)
    head = empty("sir", body, (0, 0, 1.4))
    c["head"] = head
    ball("chehra", 0.54, skin, head, (0, 0, 0.36), (0.97, 0.95, 1.0))
    hair = cel("baal_g", HAIR)
    ball("baal", 0.53, hair, head, (0, 0.07, 0.52), (1.03, 0.98, 0.78))
    for i, (hx, hz, rx) in enumerate(((-0.28, 0.78, 25), (-0.1, 0.84, 18), (0.1, 0.85, 12), (0.27, 0.79, 6),
                                       (0.0, 0.7, 40))):
        cyl(f"lat{i}", 0.13, 0.32, hair, head, (hx, -0.12 - (0.12 if i == 4 else 0), hz + 0.05), r2=0.0,
            rot=(R(rx), R(hx * 30), 0))
    f = empty("chehra_e", head, (0, 0, 0.36))
    _face(c, f, SKIN_GO, big=1.08)
    pose(c, "rest", 0.0)
    return c


# ======================================================================= mudra (pose) + bhaav
# baanh: (aage-peeche rx, bahar ry) kandha + kohni rx;  s = +1 daayi (x+) / -1 baayi
POSES = {   # s: ((aage rx, bahar out, andar in), kohni rx) - haath kahan pahunchta hai, hisaab se jaancha
    "rest":     {+1: ((5, 9, 0), -12), -1: ((5, 9, 0), -12)},
    "khush":    {+1: ((-10, 38, 0), -35), -1: ((-10, 38, 0), -35)},
    "shabaash": {+1: ((-70, 22, 0), -75), -1: ((5, 9, 0), -12)},           # haath seene ke aage, angootha upar
    "batata":   {+1: ((-60, 30, 0), -100), -1: ((5, 9, 0), -15)},          # ungli upar, kandhe ki oonchai
    "sochta":   {+1: ((-60, 0, 30), -125), -1: ((-25, 18, 0), -95)},       # haath jabde/thodi par
    "chauka":   {+1: ((-20, 75, 0), -100), -1: ((-20, 75, 0), -100)},      # dono haath "arre!"
    "udaas":    {+1: ((8, 2, 0), -5), -1: ((8, 2, 0), -5)},
    "gussa":    {+1: ((-20, 28, 0), -110), -1: ((-20, 28, 0), -110)},
    "wave":     {+1: ((-10, 150, 0), -30), -1: ((5, 9, 0), -12)},
    "dikhao":   {+1: ((-80, 28, 0), -20), -1: ((5, 9, 0), -12)},           # haath aage - kuch dikhaana
}
EMO = {   # bhauh (ghumaav deg, oonchai), munh, aankh (scale), putli, sir (jhukaav, tedha), laali, mudra
    "khush":    ((-6, 0.03), "open", 1.0, 1.0, (-4, 0), True, "khush"),
    "shabaash": ((-8, 0.04), "open", 0.9, 1.0, (-6, 5), True, "shabaash"),
    "batata":   ((-4, 0.03), "smile", 1.0, 1.0, (-3, -4), False, "batata"),
    "sochta":   ((14, 0.05), "flat", 1.0, 0.85, (-2, 9), False, "sochta"),
    "chauka":   ((-14, 0.09), "O", 1.3, 0.62, (-8, 0), False, "chauka"),
    "udaas":    ((24, 0.0), "frown", 0.92, 1.0, (14, -6), False, "udaas"),
    "gussa":    ((-24, -0.03), "frown", 0.95, 0.9, (5, 0), False, "gussa"),
    "rest":     ((0, 0.0), "smile", 1.0, 1.0, (0, 0), False, "rest"),
}


def pose(c, name, sec):
    P = POSES.get(name, POSES["rest"])
    for a in c["arms"]:
        s = a["s"]
        (rx, out, inn), elb = P[s]
        K(a["sh"], "rotation_euler", sec, (R(rx), R(-s * out), R(-s * inn)))
        K(a["el"], "rotation_euler", sec, (R(elb), 0, 0))
        th = name == "shabaash" and s == 1
        fi = name == "batata" and s == 1
        K(a["thumb"], "scale", sec, (1, 1, 1) if th else (0.001, 0.001, 0.001))
        K(a["finger"], "scale", sec, (1, 1, 1) if fi else (0.001, 0.001, 0.001))


def emotion(c, name, sec, hold=None):
    """Bhaav: chehra + mudra ek saath (0.18s me badalta). hold = isse pehle ka bhaav thama rahe."""
    e = EMO.get(name, EMO["rest"])
    (bro, bz), mouth, eye, pup, (hx, hz), blush, pz = e
    t0 = max(0.0, sec - 0.001)
    for i, b in enumerate(c["brows"]):
        s = -1 if i == 0 else 1
        K(b, "rotation_euler", sec, (0, R(bro * s), 0))
        base = b.location
        K(b, "location", sec, (base[0], base[1], (0.27 if c["name"] == "bhaiya" else 0.28) + bz))
    for k, o in c["mouths"].items():
        K(o, "scale", sec, (1, 1, 1) if k == mouth else (0.001, 0.001, 0.001))
    for e_ in c["eyes"]:
        K(e_, "scale", sec, (eye, 0.55, 1.18 * eye))
    for p in c["pupils"]:
        K(p, "scale", sec, (pup, 0.6, 1.1 * pup))
    for b in c["blush"]:
        K(b, "scale", sec, (1.2, 0.3, 0.7) if blush else (0.001, 0.001, 0.001))
    K(c["head"], "rotation_euler", sec, (R(hx), 0, R(hz)))
    pose(c, pz, sec)
    c["emo"] = name


def blink(c, sec):
    eye = EMO.get(c.get("emo", "rest"), EMO["rest"])[2]
    for e_ in c["eyes"]:
        K(e_, "scale", sec, (eye, 0.55, 1.18 * eye))
        K(e_, "scale", sec + 0.06, (eye, 0.55, 0.08))
        K(e_, "scale", sec + 0.13, (eye, 0.55, 1.18 * eye))


def talk(c, t0, t1, rate=7.0):
    """Bolna: munh khula/band (awaaz ke saath) - ant me bhaav wala munh wapas."""
    mouth = EMO.get(c.get("emo", "rest"), EMO["rest"])[1]
    t, k = t0, 0
    while t < t1:
        op = (k % 2 == 0)
        for name, o in c["mouths"].items():
            want = ("open" if op else ("smile" if mouth in ("open", "O") else mouth))
            sc = (1, 1, 0.75 if op else 1) if name == want else (0.001, 0.001, 0.001)
            K(o, "scale", t, sc)
        t += 1.0 / rate * (0.85 + 0.3 * ((k * 37) % 7) / 7)
        k += 1
    for name, o in c["mouths"].items():
        K(o, "scale", t1, (1, 1, 1) if name == mouth else (0.001, 0.001, 0.001))
    # bolte waqt sir halka hile
    hx = EMO.get(c.get("emo", "rest"), EMO["rest"])[4]
    t = t0
    while t < t1:
        K(c["head"], "rotation_euler", t, (R(hx[0] + 3 * math.sin(t * 9)), 0, R(hx[1] + 2 * math.sin(t * 5))))
        t += 0.2


def idle(c, t0, t1, phase=0.0):
    """Zinda: saans (dhad upar-neeche) + halka jhoolna + har ~2.5s palak."""
    t = t0
    while t <= t1:
        K(c["body"], "location", t, (0, 0, (0.05 if c["name"] == "golu" else 0) + 0.015 * math.sin(t * 2.6 + phase)))
        K(c["body"], "rotation_euler", t, (0, R(1.5 * math.sin(t * 1.6 + phase)), 0))
        t += 0.25
    t = t0 + 0.8 + phase % 1.0
    while t < t1:
        blink(c, t)
        t += 2.4 + (phase * 7) % 0.9


def wave(c, t0, t1):
    pose(c, "wave", t0)
    a = [x for x in c["arms"] if x["s"] == 1][0]
    t, k = t0 + 0.2, 0
    while t < t1:
        K(a["el"], "rotation_euler", t, (R(-30), R(25 if k % 2 else -25), 0))
        t += 0.2
        k += 1


def jump(c, sec, h=0.45, d=0.5):
    r = c["root"]
    x, y, z = r.location
    K(r, "location", sec, (x, y, z))
    K(r, "scale", sec, (1, 1, 1))
    K(r, "scale", sec + 0.08, (1.08, 1.08, 0.88))            # baithna (taiyaari)
    K(r, "location", sec + d * 0.5, (x, y, z + h))
    K(r, "scale", sec + d * 0.5, (0.95, 0.95, 1.07))
    K(r, "location", sec + d, (x, y, z))
    K(r, "scale", sec + d, (1.08, 1.08, 0.9))                # zameen par dabna
    K(r, "scale", sec + d + 0.1, (1, 1, 1))


def walk_in(c, t0, t1, frm, to):
    """Chal ke aana: jagah badle + taangen aage-peeche + halka uchhal."""
    r = c["root"]
    K(r, "location", t0, frm)
    n = max(2, int((t1 - t0) / 0.18))
    for i in range(n + 1):
        t = t0 + (t1 - t0) * i / n
        k = i / n
        k = k * k * (3 - 2 * k)
        loc = tuple(frm[j] + (to[j] - frm[j]) * k for j in range(3))
        K(r, "location", t, (loc[0], loc[1], loc[2] + 0.05 * abs(math.sin(i * math.pi / 2))))
        for j, lg in enumerate(c["legs"]):
            K(lg, "rotation_euler", t, (R(25 * math.sin(i * math.pi / 2 + j * math.pi)), 0, 0))
    for lg in c["legs"]:
        K(lg, "rotation_euler", t1 + 0.1, (0, 0, 0))
