"""
Postal Wala ka 3D SAAMAAN (Blender, v26) - baar-baar kaam aane wali cheezen, cartoon cel-shading + rekha.
Har function ek root empty deta hai (jagah/ghumaav/scale animate karo):
  post_office(): kamra - deewar (do rang), farsh, khidki, INDIA POST board, counter, letter box
  counter, letter_box, parcel, lifaafa(tex), mohar, taraazu, globe, sahi (✓), galat (❌), sikka, board(text)
English likhai hi (Hindi bigadti hai) - Hindi chahiye to PIL tasveer -> img_plane.
"""
import math
import os

import bpy

import b3d_chars as C

R = math.radians
cel, flat, ball, cyl, cube, tube, empty, K = C.cel, C.flat, C.ball, C.cyl, C.cube, C.tube, C.empty, C.K

POST_RED = (0.86, 0.1, 0.1)
POST_YEL = (1.0, 0.78, 0.1)
WOOD = (0.55, 0.32, 0.14)
CREAM = (0.98, 0.94, 0.84)


def img_plane(path, height, parent, loc=(0, 0, 0), rot=(R(90), 0, 0), emit=1.0, name="chitra"):
    """Tasveer (alpha ke saath) - Hindi likhai/sticker. Saamne (-Y) ki taraf."""
    im = bpy.data.images.load(os.path.abspath(path))
    w_, h_ = im.size
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    m = bpy.data.materials.new(name + "_m")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = im
    em = nt.nodes.new("ShaderNodeEmission")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    em.inputs["Strength"].default_value = emit
    nt.links.new(tx.outputs["Color"], em.inputs["Color"])
    nt.links.new(tx.outputs["Alpha"], mx.inputs["Fac"])
    nt.links.new(tr.outputs["BSDF"], mx.inputs[1])
    nt.links.new(em.outputs["Emission"], mx.inputs[2])
    nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])
    for attr, val in (("surface_render_method", "DITHERED"), ("blend_method", "HASHED")):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    o.data.materials.append(m)
    o.parent = parent
    o.location, o.rotation_euler = loc, rot
    o.scale = (height * w_ / max(1, h_), height, 1)
    return o


def counter(parent=None, loc=(0, -0.6, 0), w=6.0):
    r = empty("counter", parent, loc)
    wood, dark = cel("lakdi", WOOD), cel("lakdi_d", (0.4, 0.22, 0.09))
    cube("counter_upar", wood, r, (0, 0, 1.0), (w, 1.1, 0.12), bevel=0.03)
    cube("counter_aage", dark, r, (0, -0.48, 0.5), (w - 0.1, 0.1, 0.95))
    for i in range(int(w / 1.2)):                                        # lakdi ke panne
        cube(f"panna{i}", wood, r, (-w / 2 + 0.6 + i * 1.2, -0.54, 0.5), (1.0, 0.03, 0.75), bevel=0.02)
    cube("patti", cel("laal_patti", POST_RED), r, (0, -0.545, 0.93), (w - 0.1, 0.04, 0.1))
    return r


def letter_box(parent=None, loc=(0, 0, 0)):
    """India Post ka laal letter box (pillar) + peeli patti + chhed."""
    r = empty("letterbox", parent, loc)
    red = cel("post_laal", POST_RED)
    cyl("lb_tan", 0.38, 1.5, red, r, (0, 0, 0.75))
    ball("lb_topi", 0.4, red, r, (0, 0, 1.52), (1, 1, 0.55))
    cyl("lb_topi_patti", 0.41, 0.08, cel("post_laal_d", (0.6, 0.05, 0.05)), r, (0, 0, 1.48))
    cyl("lb_patti", 0.385, 0.12, cel("post_peela", POST_YEL), r, (0, 0, 0.95))
    cube("lb_chhed", flat("kaala", (0.03, 0.03, 0.03)), r, (0, -0.36, 1.28), (0.34, 0.06, 0.06), line=False)
    cyl("lb_paaya", 0.45, 0.12, cel("post_laal_d2", (0.5, 0.04, 0.04)), r, (0, 0, 0.06))
    return r


def parcel(parent=None, loc=(0, 0, 0), size=(0.7, 0.5, 0.45)):
    r = empty("parcel", parent, loc)
    cube("parcel_dibba", cel("gatta", (0.78, 0.58, 0.34)), r, (0, 0, size[2] / 2), size, bevel=0.02)
    tape = cel("tape", (0.86, 0.72, 0.45))
    cube("tape1", tape, r, (0, 0, size[2] / 2), (0.12, size[1] + 0.01, size[2] + 0.01), line=False)
    cube("tape2", tape, r, (0, 0, size[2] / 2), (size[0] + 0.01, 0.12, size[2] + 0.01), line=False)
    cube("parcel_label", flat("label", (1, 1, 1)), r, (0.18, -size[1] / 2 - 0.006, size[2] * 0.55),
         (0.22, 0.01, 0.14), line=False)
    return r


def lifaafa(tex=None, parent=None, loc=(0, 0, 0), w=1.2):
    """Lifaafa: kaagaz + saamne pata wali tasveer (tex) ya saada + laal ticket."""
    r = empty("lifaafa", parent, loc)
    h = w * 0.62
    cube("lif_kaagaz", cel("kaagaz", CREAM), r, (0, 0, 0), (w, 0.025, h), bevel=0.006)
    if tex and os.path.exists(tex):
        f = img_plane(tex, h * 0.97, r, (0, -0.0135, 0), name="lif_pata", emit=1.0)
        f.scale = (w * 0.97, h * 0.97, 1)
    else:
        cube("lif_ticket", cel("ticket", POST_RED), r, (w * 0.36, -0.016, h * 0.3), (w * 0.14, 0.006, h * 0.22),
             line=False)
        for i in range(3):
            cube(f"lif_line{i}", flat("lif_syahi", (0.15, 0.2, 0.45)), r, (-w * 0.05, -0.016, -h * 0.08 - i * h * 0.13),
                 (w * 0.45, 0.004, h * 0.04), line=False)
    return r


def mohar(parent=None, loc=(0, 0, 0)):
    """Rubber mohar: lakdi ka handle (gol ghundi) + kaala rubber."""
    r = empty("mohar", parent, loc)
    cyl("mohar_rubber", 0.22, 0.08, cel("rubber", (0.12, 0.1, 0.12)), r, (0, 0, 0.04))
    cyl("mohar_aadhar", 0.24, 0.12, cel("mohar_lakdi", WOOD), r, (0, 0, 0.14))
    cyl("mohar_danda", 0.06, 0.35, cel("mohar_lakdi", WOOD), r, (0, 0, 0.37))
    ball("mohar_ghundi", 0.13, cel("mohar_laal", POST_RED), r, (0, 0, 0.6))
    return r


def taraazu(parent=None, loc=(0, 0, 0)):
    """Digital taraazu (parcel tolna): safed dibba + chaandi patra + hara screen."""
    r = empty("taraazu", parent, loc)
    cube("tz_dibba", cel("tz_safed", (0.92, 0.93, 0.95)), r, (0, 0, 0.09), (0.7, 0.55, 0.18), bevel=0.03)
    cube("tz_patra", cel("tz_chaandi", (0.7, 0.72, 0.76)), r, (0, 0.03, 0.2), (0.6, 0.45, 0.03), bevel=0.01)
    cube("tz_screen", flat("tz_hara", (0.3, 1.0, 0.45), 1.3), r, (0, -0.28, 0.1), (0.36, 0.01, 0.08), line=False)
    return r


def globe(parent=None, loc=(0, 0, 0), rr=0.5):
    r = empty("globe", parent, loc)
    gl = ball("globe_gola", rr, cel("samudra", (0.15, 0.45, 0.95)), r, (0, 0, rr + 0.5), seg=48)
    for i, (a, b, s) in enumerate(((20, 40, 0.42), (-30, 160, 0.35), (55, -60, 0.3), (-10, -150, 0.28))):
        x = math.cos(R(a)) * math.cos(R(b)) * rr * 0.92
        y = math.cos(R(a)) * math.sin(R(b)) * rr * 0.92
        z = math.sin(R(a)) * rr * 0.92
        ball(f"mahadweep{i}", rr * s, cel("zameen", (0.25, 0.75, 0.3)), gl, (x / 1.0, y, z), (1, 1, 0.5),
             (R(90 - a), 0, R(b + 90)), line=False)
    gold = cel("sona", (1.0, 0.72, 0.2))
    cyl("globe_ghera", rr * 1.12, 0.04, gold, r, (0, 0, rr + 0.5), rot=(R(90), R(23), 0), r2=None)
    cyl("globe_danda", 0.04, 0.5, gold, r, (0, 0, 0.25))
    cyl("globe_aadhar", 0.3, 0.06, gold, r, (0, 0, 0.03))
    r["gola"] = gl.name
    return r, gl


def sahi(parent=None, loc=(0, 0, 0), s=1.0):
    """3D ✓ (hara, chamakdaar) - do mote dande."""
    r = empty("sahi", parent, loc)
    g = flat("sahi_hara", (0.15, 0.85, 0.35), 1.2)
    cube("sahi_chhota", g, r, (-0.14 * s, 0, -0.05 * s), (0.34 * s, 0.12 * s, 0.12 * s), (0, R(45), 0))
    cube("sahi_bada", g, r, (0.14 * s, 0, 0.1 * s), (0.62 * s, 0.12 * s, 0.12 * s), (0, R(-55), 0))
    return r


def galat(parent=None, loc=(0, 0, 0), s=1.0):
    """3D ❌ (laal)."""
    r = empty("galat", parent, loc)
    g = flat("galat_laal", (0.95, 0.15, 0.15), 1.2)
    cube("galat1", g, r, (0, 0, 0), (0.6 * s, 0.12 * s, 0.12 * s), (0, R(45), 0))
    cube("galat2", g, r, (0, 0, 0), (0.6 * s, 0.12 * s, 0.12 * s), (0, R(-45), 0))
    return r


def sikka(parent=None, loc=(0, 0, 0)):
    r = empty("sikka", parent, loc)
    cyl("sikka_gol", 0.18, 0.04, cel("sikka_sona", (1.0, 0.78, 0.25)), r, (0, 0, 0), rot=(R(90), 0, 0))
    return r


def board(text, parent=None, loc=(0, 0, 0), w=3.2, h=0.6, bg=POST_RED, fg=(1, 1, 1)):
    """English board (INDIA POST / POSTAL WALA)."""
    r = empty("board", parent, loc)
    cube("board_patti", cel("board_rang", bg), r, (0, 0, 0), (w, 0.06, h), bevel=0.02)
    t = C.text3d("board_text", text, h * 0.55, flat("board_akshar", fg, 1.1), r, (0, -0.05, -0.02))
    try:
        t.data.font = bpy.data.fonts.load("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    except Exception:
        pass
    return r


def post_office(parent=None):
    """Poora kamra: do rang ki deewar, farsh, khidki (aasmaan), INDIA POST board, letter box. Counter alag."""
    r = empty("post_office", parent, (0, 0, 0))
    wall_up, wall_dn = cel("deewar_upar", (1.0, 0.9, 0.72)), cel("deewar_neeche", (0.88, 0.32, 0.22))
    cube("deewar1", wall_up, r, (0, 4.0, 3.3), (24, 0.2, 4.6), line=False)
    cube("deewar2", wall_dn, r, (0, 3.95, 0.55), (24, 0.2, 1.1), line=False)
    cube("deewar_patti", cel("deewar_patti", POST_YEL), r, (0, 3.88, 1.12), (24, 0.06, 0.1), line=False)
    cube("farsh", cel("farsh", (0.72, 0.62, 0.52)), r, (0, 0, -0.05), (24, 10, 0.1), line=False)
    for i in range(-6, 7):                                                  # farsh ki tiles
        cube(f"tile{i}", cel("farsh_d", (0.64, 0.54, 0.45)), r, (i * 1.6, 0, 0.001), (0.03, 10, 0.004), line=False)
    win = empty("khidki", r, (-3.6, 3.85, 2.9))
    cube("khidki_frame", cel("khidki_frame", (0.35, 0.2, 0.1)), win, (0, 0, 0), (2.0, 0.12, 1.6), bevel=0.03)
    cube("aasmaan", flat("aasmaan", (0.55, 0.82, 1.0), 1.1), win, (0, -0.07, 0), (1.8, 0.02, 1.4), line=False)
    cube("khidki_beech", cel("khidki_frame", (0.35, 0.2, 0.1)), win, (0, -0.09, 0), (0.06, 0.04, 1.4), line=False)
    ball("baadal", 0.25, flat("baadal", (1, 1, 1)), win, (0.4, -0.09, 0.3), (1.6, 0.1, 0.7), line=False)
    board("INDIA POST", r, (1.2, 3.82, 4.4), 4.2, 0.75)
    lb = letter_box(r, (4.2, 2.8, 0))
    return r
