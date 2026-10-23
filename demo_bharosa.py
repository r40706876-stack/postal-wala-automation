"""
DEMO (ek baar): "bharosa" series reel - Clause 26 Part 6 (प्रेषक का पता - नीचे बायाँ कोना).
Kram: asli paper scan (saboot) -> kitaab ki kathin bhasha vs hamari aasan bhasha -> 3 chitra (halaat / galti / sahi)
      -> yaad ki TRICK -> paper ke sawal ka jawab (B) -> guarantee + SAVE.  Puri reel me upar bharose ki patti.
Awaaz: main.make_voices (Gemini, wahi rotation) - na mile to chup (sirf visuals jaanch ke liye).
Chalana: python demo_bharosa.py   -> demo_out/bharosa/demo_bharosa_clause26_part6.mp4
Asli series code (main.py / naya_reel.py) ko ye chhoota bhi nahi.
"""
import json, math, os, re, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

import main as M

OUT = os.path.join("demo_out", "bharosa")
PAPER_PDF = os.path.join("pyq_papers", "HR-MTS-PM-MG-2022.pdf")
PAPER_PAGE, PAPER_Q = 4, "Q20."
PAPER_LABEL = ("असली पेपर में आया", "हरियाणा 2022  •  प्रश्न 20")
ANS = "B"

M.resolve_font()
EB = M.resolve_font()
MD = M.resolve_reg_font()
BD = EB
F = lambda p, s: ImageFont.truetype(p, s, layout_engine=ImageFont.Layout.RAQM)
FPS = 30
W, H = 1080, 1920
PW, PH = 880, 920
NAVY1, NAVY2 = (10, 18, 40), (18, 34, 72)
YEL, RED, GRN, INK = (255, 200, 30), (226, 52, 52), (34, 170, 90), (30, 40, 80)
CREAM, CREAM_D = (250, 243, 226), (226, 214, 188)
GOLD, NAVY = (255, 205, 40), (16, 24, 52)

def ease(t): t = max(0, min(1, t)); return 1 - (1 - t) ** 3
def back(t):
    t = max(0, min(1, t)); c = 1.7
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2

def ctext(d, cx, y, s, font, fill, stroke=0, sf=(0, 0, 0)):
    w = d.textlength(s, font=font)
    d.text((cx - w / 2, y), s, font=font, fill=fill, stroke_width=stroke, stroke_fill=sf)

def rrect(d, box, r, **kw): d.rounded_rectangle(box, r, **kw)

# ---------- lifafa (envelope) ----------
def envelope(w, h, t_stamp=1.0, recv_p=0.0, send_p=0.0, send_wrong_p=0.0,
             ring=None, ring_p=0.0, stamp_slot=True):
    """recv_p/send_p = likhawat kitni ho chuki (0..1). ring=('red'|'green', box)."""
    im = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((24, 30, w + 24, h + 30), 18, fill=(0, 0, 0, 120))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(im)
    rrect(d, (14, 14, w + 14, h + 14), 16, fill=CREAM, outline=CREAM_D, width=4)
    # halki dhaariyan (kagaz texture)
    for i in range(0, h, 26):
        d.line((30, 20 + i, w, 20 + i), fill=(244, 236, 216), width=1)
    ox, oy = 14, 14
    # stamp ki jagah (ooper daayaan)
    sx0, sy0, sx1, sy1 = ox + w - 160, oy + 24, ox + w - 30, oy + 174
    if stamp_slot:
        for k in range(0, 130, 16):  # dashed box
            d.line((sx0 + k, sy0, min(sx0 + k + 8, sx1), sy0), fill=(170, 150, 120), width=3)
            d.line((sx0 + k, sy1, min(sx0 + k + 8, sx1), sy1), fill=(170, 150, 120), width=3)
        for k in range(0, 150, 16):
            d.line((sx0, sy0 + k, sx0, min(sy0 + k + 8, sy1)), fill=(170, 150, 120), width=3)
            d.line((sx1, sy0 + k, sx1, min(sy0 + k + 8, sy1)), fill=(170, 150, 120), width=3)
        if t_stamp < 0.5 and send_wrong_p <= 0:
            ctext(d, (sx0 + sx1) / 2, sy0 + 46, "टिकट", F(BD, 30), (150, 130, 100))
            ctext(d, (sx0 + sx1) / 2, sy0 + 80, "यहाँ", F(BD, 30), (150, 130, 100))
    if t_stamp > 0:
        e = back(t_stamp)
        st = Image.new("RGBA", (130, 150), (0, 0, 0, 0))
        sd = ImageDraw.Draw(st)
        sd.rectangle((0, 0, 129, 149), fill=(255, 255, 255))
        for k in range(0, 150, 10):  # dant (perforation)
            sd.ellipse((-4, k - 4, 4, k + 4), fill=(0, 0, 0, 0)); sd.ellipse((125, k - 4, 133, k + 4), fill=(0, 0, 0, 0))
        sd.rectangle((10, 10, 119, 139), fill=(214, 70, 60))
        sd.ellipse((35, 28, 95, 88), fill=(255, 220, 120))
        ctext(sd, 65, 92, "भारत", F(EB, 24), (255, 255, 255))
        ctext(sd, 65, 114, "₹5", F(EB, 22), (255, 255, 255))
        sc = max(0.05, e)
        st2 = st.resize((max(1, int(130 * sc)), max(1, int(150 * sc))))
        st2 = st2.rotate(-6, expand=True, resample=Image.BICUBIC)
        dy = int((1 - ease(t_stamp)) * -120)
        im.alpha_composite(st2, (int((sx0 + sx1) / 2 - st2.width / 2), int((sy0 + sy1) / 2 - st2.height / 2 + dy)))
    # likhawat
    def write(lines, x, y, p, col, size=40, lh=50):
        tot = sum(len(l) for l in lines); n = int(tot * ease(p) + 0.999) if p > 0 else 0
        for l in lines:
            if n <= 0: break
            d.text((x, y), l[:n], font=F(MD, size), fill=col); n -= len(l); y += lh
    write(["सेवा में,", "श्री रमेश कुमार", "ग्राम - रामपुर", "जिला - रायपुर", "PIN 492001"],
          ox + int(w * 0.48), oy + int(h * 0.36), recv_p, (25, 45, 120), 42, 52)
    write(["प्रेषक: सुरेश", "बिलासपुर 495001"], ox + 34, oy + h - 128, send_p, (25, 45, 120), 36, 46)
    write(["प्रेषक:", "सुरेश,", "बिलासपुर"], sx0 + 8, sy0 + 10, send_wrong_p, (25, 45, 120), 34, 44)
    if ring and ring_p > 0:
        col = RED if ring[0] == "red" else GRN
        x0, y0, x1, y1 = ring[1]
        a = 360 * ease(ring_p)
        d.arc((x0, y0, x1, y1), -90, -90 + a, fill=col, width=10)
    return im

def badge(kind, size=120):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=RED if kind == "x" else GRN, outline=(255, 255, 255), width=8)
    c, r = size / 2, size * 0.22
    if kind == "x":
        d.line((c - r, c - r, c + r, c + r), fill="white", width=14); d.line((c - r, c + r, c + r, c - r), fill="white", width=14)
    else:
        d.line((c - r * 1.1, c, c - r * 0.2, c + r * 0.9, c + r * 1.2, c - r * 0.9), fill="white", width=14, joint="curve")
    return im

def paste_scaled(base, im, cx, cy, s):
    if s <= 0.02: return
    im2 = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BICUBIC)
    base.alpha_composite(im2, (int(cx - im2.width / 2), int(cy - im2.height / 2)))

def tag(text, col, font=None):
    font = font or F(EB, 44)
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    w = int(tmp.textlength(text, font=font)) + 56
    im = Image.new("RGBA", (w, 84), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    rrect(d, (0, 0, w - 1, 83), 42, fill=col, outline=(255, 255, 255), width=4)
    d.text((28, 6), text, font=font, fill="white")
    return im

def panel_bg(tint):
    im = Image.new("RGBA", (PW, PH), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    top, bot = (250, 238, 214), (232, 212, 178)
    for y in range(PH):
        k = y / PH; d.line((0, y, PW, y), fill=tuple(int(top[i] * (1 - k) + bot[i] * k) for i in range(3)))
    # mez (counter) ki lakdi
    d.rectangle((0, PH - 170, PW, PH), fill=(150, 96, 52)); d.rectangle((0, PH - 170, PW, PH - 150), fill=(178, 118, 66))
    for x in range(0, PW, 110): d.line((x, PH - 150, x + 40, PH), fill=(135, 86, 46), width=3)
    ov = Image.new("RGBA", (PW, PH), tint + (28,)); im.alpha_composite(ov)
    return im

def round_mask(w, h, r):
    m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255); return m

MASK = round_mask(PW, PH, 30)
EW, EH = 800, 500
EX, EY = (PW - EW) // 2 - 20, 205

def head(d, text, col):
    rrect(d, (40, 40, PW - 40, 150), 28, fill=(255, 255, 255), outline=col, width=6)
    ctext(d, PW / 2, 58, text, F(EB, 58), INK)

def panel_wrong(t):          # 9.60 -> 12.57  (2.97s)
    im = panel_bg((226, 52, 52)); d = ImageDraw.Draw(im)
    head(d, "ग्राहक ने पता कहाँ लिखा?", RED)
    shake = int(math.sin(t * 60) * 8 * max(0, 1 - (t - 1.55) * 4)) if t > 1.55 else 0
    env = envelope(EW, EH, t_stamp=0, send_wrong_p=min(1, t / 1.2),
                   ring=("red", (EW - 180, 14, EW + 34, 205)), ring_p=(t - 1.25) / 0.35)
    im.alpha_composite(env, (EX + shake, EY))
    ctext(d, PW / 2, EY + EH + 42, "लिफाफे की पता वाली साइड (Face)", F(BD, 34), (255, 240, 215))
    if t > 1.5:
        paste_scaled(im, badge("x", 130), EX + EW - 10 + shake, EY + 30, back((t - 1.5) / 0.3))
    if t > 1.75:
        tg = tag("गलत: यहाँ तो टिकट लगता है!", RED)
        e = ease((t - 1.75) / 0.3); im.alpha_composite(tg, (int(PW / 2 - tg.width / 2), int(EY + EH + 95 + (1 - e) * 60)))
    out = Image.new("RGBA", (PW, PH), (0, 0, 0, 0)); out.paste(im, (0, 0), MASK); return out

def panel_right(t):          # 12.57 -> 18.57 (6.0s)
    im = panel_bg((34, 170, 90)); d = ImageDraw.Draw(im)
    head(d, "सही तरीका", GRN)
    env = envelope(EW, EH, t_stamp=(t - 0.1) / 0.5, recv_p=(t - 0.6) / 1.4, send_p=(t - 2.2) / 1.2,
                   ring=("green", (4, EH - 150, 360, EH + 30)), ring_p=(t - 3.4) / 0.4)
    im.alpha_composite(env, (EX, EY))
    ctext(d, PW / 2, EY + EH + 42, "लिफाफे की पता वाली साइड (Face)", F(BD, 34), (255, 240, 215))
    if t > 0.7:  # chhote label: kis jagah kya
        a = ease((t - 0.7) / 0.3)
        lab = tag("टिकट", (200, 130, 20), F(EB, 34)); lab.putalpha(lab.getchannel("A").point(lambda v: int(v * a)))
        im.alpha_composite(lab, (EX + EW - 150, EY - 70))
    if t > 1.6:
        a = ease((t - 1.6) / 0.3)
        lab = tag("पाने वाला", (40, 70, 160), F(EB, 34)); lab.putalpha(lab.getchannel("A").point(lambda v: int(v * a)))
        im.alpha_composite(lab, (EX + int(EW * 0.5), EY + int(EH * 0.36) - 90))
    if t > 3.7:
        paste_scaled(im, badge("ok", 130), EX + 330, EY + EH - 120, back((t - 3.7) / 0.3))
    if t > 3.95:
        tg = tag("सही: प्रेषक = नीचे बायाँ कोना", GRN)
        e = ease((t - 3.95) / 0.3); im.alpha_composite(tg, (int(PW / 2 - tg.width / 2), int(EY + EH + 95 + (1 - e) * 60)))
    out = Image.new("RGBA", (PW, PH), (0, 0, 0, 0)); out.paste(im, (0, 0), MASK); return out


# ------------------------------------------------------------------ naye drishya

def bg_frame():
    im = Image.new("RGBA", (W, H)); d = ImageDraw.Draw(im)
    for y in range(H):
        k = y / H
        d.line((0, y, W, y), fill=(int(10 + 10 * k), int(16 + 18 * k), int(38 + 34 * k), 255))
    return im


BG = bg_frame()


def stroke_c(d, xy, t, f, fill, sw=7):
    d.text(xy, t, font=f, fill=fill, anchor="mm", stroke_width=sw, stroke_fill=(0, 0, 0))


def trust_strip(cv, piece):
    """Puri reel me upar: bharosa + aasaani (har pal dimaag me rahe)."""
    d = ImageDraw.Draw(cv)
    d.rectangle((0, 0, W, 150), fill=(8, 12, 30))
    d.rounded_rectangle((30, 40, 520, 112), 36, fill=GRN)
    d.text((275, 76), "100% परीक्षा वाला नियम", font=F(EB, 38), fill="white", anchor="mm")
    d.rounded_rectangle((550, 40, 1050, 112), 36, fill=GOLD)
    d.text((800, 76), f"चित्रों से आसान • टुकड़ा {piece}", font=F(EB, 36), fill=NAVY, anchor="mm")


def stamp_img(top, sub):
    f1, f2 = F(EB, 64), F(EB, 46)
    w = int(max(f1.getlength(top), f2.getlength(sub))) + 110
    im = Image.new("RGBA", (w, 182), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((4, 4, w - 5, 177), 26, fill=(255, 244, 240), outline=RED, width=10)
    d.rounded_rectangle((20, 20, w - 21, 161), 18, outline=RED, width=3)
    d.text((w / 2, 62), top, font=f1, fill=RED, anchor="mm")
    d.text((w / 2, 128), sub, font=f2, fill=NAVY, anchor="mm")
    return im.rotate(-5, expand=True, resample=Image.BICUBIC)


STAMP = stamp_img(*PAPER_LABEL)


def paper_crop():
    """Asli paper PDF se sawal ka hissa (scan) + sawal/jawab ki line ki jagah."""
    html = subprocess.run(["pdftotext", "-bbox", "-f", str(PAPER_PAGE), "-l", str(PAPER_PAGE), PAPER_PDF, "-"],
                          capture_output=True, text=True).stdout
    ws = re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', html)
    i0 = next(i for i, w in enumerate(ws) if w[4] == PAPER_Q)
    nxt = "Q%d." % (int(PAPER_Q[1:-1]) + 1)
    i1 = next(i for i, w in enumerate(ws) if w[4] == nxt)
    q = [tuple(map(float, w[:4])) + (w[4],) for w in ws[i0:i1]]
    ia = next(i for i, w in enumerate(q) if w[4] == "A.")
    il = next(i for i, w in enumerate(q) if w[4] == ANS + ".")
    inx = next((i for i, w in enumerate(q) if w[4] == chr(ord(ANS) + 1) + "."), len(q))
    x0, y0 = min(w[0] for w in q), min(w[1] for w in q)
    x1, y1 = max(w[2] for w in q), max(w[3] for w in q)
    dpi = 220
    base = os.path.join(OUT, "_pg")
    subprocess.run(["pdftoppm", "-f", str(PAPER_PAGE), "-l", str(PAPER_PAGE), "-r", str(dpi), "-png", "-singlefile",
                    PAPER_PDF, base], check=True)
    pg = Image.open(base + ".png").convert("RGB")
    k = dpi / 72.0
    pad = 10
    box = [int((x0 - pad) * k), int((y0 - pad) * k), int((x1 + pad) * k), int((y1 + pad) * k)]
    cr = pg.crop(box)
    sc = 940 / cr.width
    cr = cr.resize((940, int(cr.height * sc)), Image.LANCZOS)
    ty = lambda v: (v * k - box[1]) * sc
    qline = (ty(min(w[1] for w in q[:ia])), ty(max(w[3] for w in q[:ia])))
    aline = (ty(min(w[1] for w in q[il:inx])), ty(max(w[3] for w in q[il:inx])))
    return cr, qline, aline


CROP, QLINE, ALINE = paper_crop()


def paper_card(t_hl, t_ring):
    pc = CROP.copy()
    if t_hl > 0:
        hl = Image.new("RGB", pc.size, (255, 255, 255))
        ImageDraw.Draw(hl).rectangle((0, QLINE[0] - 4, pc.width * ease(t_hl), QLINE[1] + 4), fill=(255, 226, 70))
        pc = ImageChops.multiply(pc, hl)
    pc = pc.convert("RGBA")
    if t_ring > 0:
        d = ImageDraw.Draw(pc)
        d.ellipse((10, ALINE[0] - 16, 10 + (pc.width - 60) * ease(t_ring) + 40, ALINE[1] + 16), outline=(220, 20, 30), width=7)
    out = Image.new("RGBA", (pc.width + 40, pc.height + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((24, 28, pc.width + 24, pc.height + 28), fill=(0, 0, 0, 150))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    out.alpha_composite(pc, (10, 10))
    return out.rotate(1.5, expand=True, resample=Image.BICUBIC)


def sc_proof(t, dur):
    cv = BG.copy(); d = ImageDraw.Draw(cv)
    d.rounded_rectangle((300, 70, 780, 134), 32, fill=GOLD)
    d.text((540, 102), "GDS से MTS / Postman", font=F(EB, 40), fill=NAVY, anchor="mm")
    stroke_c(d, (540, 240), "ये सवाल असली पेपर में", F(EB, 84), (255, 255, 255))
    stroke_c(d, (540, 345), "पूछा जा चुका है!", F(EB, 96), (255, 214, 40), 8)
    k = ease(t / 0.35)
    pcard = paper_card((t - 0.45) / 0.6, 0)
    cv.alpha_composite(pcard, (60, int(1080 + (1 - k) * 700) - pcard.height // 2))
    if t > 0.75:
        s = 1.0 + 0.6 * (1 - ease((t - 0.75) / 0.18))
        im2 = STAMP.resize((int(STAMP.width * s), int(STAMP.height * s)))
        cv.alpha_composite(im2, (int(540 - im2.width / 2), int(620 - im2.height / 2)))
    if t > 1.5:
        a = ease((t - 1.5) / 0.3); y = int(1500 + (1 - a) * 60)
        d.rounded_rectangle((70, y, 1010, y + 120), 30, fill=RED)
        d.text((540, y + 60), "सही जवाब इसी रील में — ध्यान से देखो!", font=F(EB, 50), fill="white", anchor="mm")
    return cv


GUIDE_EN = ["It is desirable to note the sender's address", "preferable in the lower left-hand", "corner on the address side..."]


def sc_kathin(t, dur):
    """Kitaab ki bhasha (kathin) vs hamari bhasha (aasan) - farak har pal dikhe."""
    cv = BG.copy(); d = ImageDraw.Draw(cv)
    trust_strip(cv, "शुरू")
    # upar: kitaab
    d.rounded_rectangle((60, 220, 1020, 760), 30, fill=(235, 235, 238))
    d.rounded_rectangle((90, 190, 560, 260), 35, fill=(120, 120, 130))
    d.text((325, 225), "किताब की भाषा 😵".replace(" 😵", ""), font=F(EB, 40), fill="white", anchor="mm")
    for i, ln in enumerate(GUIDE_EN):
        d.text((100, 320 + i * 80), ln, font=F(MD, 44), fill=(110, 110, 120), anchor="lm")
    d.text((540, 610), "कठिन • लंबा • अंग्रेज़ी", font=F(EB, 50), fill=(170, 60, 60), anchor="mm")
    if t > 0.5:                                           # kaata
        a = ease((t - 0.5) / 0.3)
        d.line((90, 690, 90 + 900 * a, 280), fill=RED, width=12)
    # neeche: hamari bhasha
    if t > 0.9:
        a = ease((t - 0.9) / 0.35)
        y0 = int(860 + (1 - a) * 120)
        d.rounded_rectangle((60, y0, 1020, y0 + 640), 30, fill=(255, 255, 255), outline=GRN, width=8)
        d.rounded_rectangle((90, y0 - 30, 640, y0 + 40), 35, fill=GRN)
        d.text((365, y0 + 5), "Postal Wala की भाषा", font=F(EB, 40), fill="white", anchor="mm")
        d.text((540, y0 + 140), "आसान हिंदी", font=F(EB, 76), fill=INK, anchor="mm")
        d.text((540, y0 + 250), "3 चित्र • 1 ट्रिक", font=F(EB, 84), fill=GRN, anchor="mm")
        d.text((540, y0 + 380), "0 कन्फ्यूज़न • पक्का याद", font=F(EB, 56), fill=(200, 120, 0), anchor="mm")
        d.text((540, y0 + 510), "चलो चित्रों में समझते हैं 👇".replace(" 👇", ""), font=F(MD, 48), fill=(90, 100, 120), anchor="mm")
    return cv


PANEL1 = Image.open(os.path.join(OUT, "panel1.jpg")).convert("RGBA")
MASK = round_mask(PW, PH, 30)


def framed(cv, panel, col, piece, caption):
    trust_strip(cv, piece)
    d = ImageDraw.Draw(cv)
    d.rounded_rectangle((90, 340, 990, 1280), 36, fill=col)
    p = Image.new("RGBA", (PW, PH), (0, 0, 0, 0)); p.paste(panel, (0, 0), MASK)
    cv.alpha_composite(p, (100, 350))
    f, s_, ls = M.fit_lines(caption, 960, 2, 60, 44)
    for i, ln in enumerate(ls):
        stroke_c(d, (540, 1390 + i * int(s_ * 1.25)), " ".join(ln), f, (255, 255, 255), 6)


def sc_p1(t, dur):
    cv = BG.copy()
    z = 1.0 + 0.05 * ease(t / dur)
    pz = PANEL1.resize((int(PW * z), int(PH * z)), Image.BICUBIC)
    pz = pz.crop(((pz.width - PW) // 2, (pz.height - PH) // 2, (pz.width - PW) // 2 + PW, (pz.height - PH) // 2 + PH))
    framed(cv, pz, (60, 140, 230), "1/3", "ग्राहक सोच रहा है — अपना पता कहाँ लिखूँ?")
    return cv


def sc_wrong(t, dur):
    cv = BG.copy()
    framed(cv, panel_wrong(min(t, 2.9)), RED, "2/3", "ऊपर दाएँ कोने में? नहीं! वहाँ टिकट लगता है।")
    return cv


def sc_right(t, dur):
    cv = BG.copy()
    framed(cv, panel_right(min(t * 1.35, 5.9)), GRN, "3/3", "भेजने वाले का पता — पते वाली साइड पर नीचे बाएँ कोने में!")
    return cv


def sc_trick(t, dur):
    cv = BG.copy(); trust_strip(cv, "ट्रिक"); d = ImageDraw.Draw(cv)
    d.rounded_rectangle((260, 210, 820, 290), 40, fill=GOLD)
    d.text((540, 250), "याद रखने की ट्रिक", font=F(EB, 50), fill=NAVY, anchor="mm")
    ex, ey, ew, eh = 110, 380, 860, 540
    d.rounded_rectangle((ex, ey, ex + ew, ey + eh), 20, fill=CREAM, outline=CREAM_D, width=5)
    a1 = back((t - 0.1) / 0.3)
    if a1 > 0:
        d.rectangle((ex + ew - 170, ey + 30, ex + ew - 40, ey + 180), fill=(214, 70, 60))
        d.text((ex + ew - 105, ey + 105), "टिकट", font=F(EB, 36), fill="white", anchor="mm")
    if t > 0.5:
        d.rounded_rectangle((ex + 30, ey + eh - 150, ex + 330, ey + eh - 30), 16, outline=GRN, width=6)
        d.text((ex + 180, ey + eh - 90), "प्रेषक", font=F(EB, 52), fill=GRN, anchor="mm")
    lk = ease((t - 0.8) / 0.7)                            # tirchhi line khinchti hai
    sx, sy = ex + ew - 105, ey + 180
    tx, ty_ = ex + 180, ey + eh - 150
    for kk in range(0, 100, 6):
        a, b = kk / 100, (kk + 3) / 100
        if b > lk:
            break
        d.line((sx + (tx - sx) * a, sy + (ty_ - sy) * a, sx + (tx - sx) * b, sy + (ty_ - sy) * b), fill=RED, width=10)
    if t > 1.4:
        stroke_c(d, (540, 1040), "टिकट ऊपर दाएँ — प्रेषक नीचे बाएँ", F(EB, 60), (255, 214, 40), 5)
        stroke_c(d, (540, 1140), "दोनों तिरछे आमने-सामने!", F(EB, 70), (255, 255, 255), 5)
    if t > 2.1:
        d.rounded_rectangle((90, 1270, 990, 1410), 40, fill=(255, 255, 255))
        d.text((540, 1340), "1 तिरछी लाइन = पूरा नियम याद", font=F(EB, 54), fill=RED, anchor="mm")
    return cv


def sc_answer(t, dur):
    cv = BG.copy(); trust_strip(cv, "जवाब"); d = ImageDraw.Draw(cv)
    stroke_c(d, (540, 260), "अब पेपर का सवाल", F(EB, 84), (255, 255, 255))
    stroke_c(d, (540, 365), "चुटकी में हल!", F(EB, 96), (255, 214, 40), 8)
    pcard = paper_card(1.0, (t - 0.3) / 0.5)
    cv.alpha_composite(pcard, (60, 900 - pcard.height // 2))
    if t > 0.9:
        s = back((t - 0.9) / 0.3)
        b = badge("ok", 150)
        paste_scaled(cv, b, 900, 1180, s)
        stroke_c(d, (540, 1330), f"सही जवाब: {ANS}", F(EB, 90), (120, 255, 150), 7)
    return cv


def sc_end(t, dur):
    cv = BG.copy(); d = ImageDraw.Draw(cv)
    try:
        bh = Image.open(os.path.join("clause_plans", "characters", "bhaiya_shabaash.jpg")).convert("RGBA")
        bh.thumbnail((600, 600))
        m = Image.new("L", bh.size, 0); ImageDraw.Draw(m).ellipse((0, 0, bh.width - 1, bh.height - 1), fill=255)
        ring = Image.new("RGBA", (bh.width + 24, bh.height + 24), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((0, 0, ring.width - 1, ring.height - 1), fill=GOLD)
        cv.alpha_composite(ring, (540 - ring.width // 2, 270))
        cv.paste(bh, (540 - bh.width // 2, 282), m)
    except Exception:
        pass
    d.rounded_rectangle((70, 930, 1010, 1130), 40, fill=GOLD)
    d.text((540, 990), "Postal Wala की गारंटी", font=F(EB, 62), fill=NAVY, anchor="mm")
    d.text((540, 1070), "अब ये नियम कभी नहीं भूलोगे!", font=F(EB, 54), fill=RED, anchor="mm")
    if t > 0.5:
        d.rounded_rectangle((170, 1200, 910, 1320), 60, fill=GRN)
        d.text((540, 1260), "SAVE करो  •  साथी को भेजो", font=F(EB, 54), fill="white", anchor="mm")
        d.text((540, 1420), "रोज़ एक नियम — चित्र + ट्रिक के साथ", font=F(MD, 44), fill=(220, 225, 240), anchor="mm")
    return cv


SCENES = [
    ("proof", sc_proof, 3.0, "GDS साथियो! ये सवाल हरियाणा दो हज़ार बाईस के पेपर में आया था!"),
    ("kathin", sc_kathin, 3.2, "किताब की भाषा कठिन है, हम इसे एक चित्र से आसान बनाते हैं!"),
    ("p1", sc_p1, 2.4, "ग्राहक सोच रहा है, अपना पता कहाँ लिखूँ?"),
    ("wrong", sc_wrong, 2.9, "ऊपर दाएँ कोने में? नहीं! वहाँ तो टिकट लगता है।"),
    ("right", sc_right, 4.4, "भेजने वाले का पता, पते वाली साइड पर, नीचे बाएँ कोने में!"),
    ("trick", sc_trick, 3.0, "ट्रिक याद रखो! टिकट ऊपर दाएँ, प्रेषक नीचे बाएँ, दोनों तिरछे आमने-सामने!"),
    ("answer", sc_answer, 2.2, "इसलिए हरियाणा पेपर का सही जवाब, बी!"),
    ("end", sc_end, 2.4, "Postal Wala की गारंटी, अब ये नियम कभी नहीं भूलोगे!"),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    specs = [{"name": n, "segs": [(n, txt)]} for n, _, _, txt in SCENES]
    voices = None
    if not M.DRY_RUN:
        try:
            voices = [v[0] for v in M.make_voices(specs)]
            voices = [M.speed_voice(v, 1.08) for v in voices]
        except Exception as exc:
            print("Awaaz nahi bani (demo bina awaaz):", str(exc)[:160])
    tl, t = [], 0.0
    for i, (n, fn, mn, _) in enumerate(SCENES):
        vd = len(voices[i]) / M.SR if voices else 0
        dur = max(mn, vd + 0.35)
        tl.append((n, fn, t, dur, voices[i] if voices else None))
        t += dur
    total = t
    print("Timeline:", [(n, round(s, 2), round(d, 2)) for n, _, s, d, _ in tl], "kul", round(total, 1))
    n = int(total * M.SR) + M.SR // 2
    buf = np.zeros(n, dtype=np.float32)
    bed = M.music_bed(total + 0.5)
    m_ = min(n, len(bed))
    buf[:m_] += bed[:m_] * 0.45
    M.add_at(buf, M.sfx_thud(0.7), 0.0)                    # Postal Wala dhun: mohar 'thak' + ghanti
    M.add_at(buf, M.sfx_ding(0.45), 0.25)
    for name, _, s, d, v in tl:
        if v is not None:
            M.add_at(buf, v, s + 0.1)
        if name == "proof":
            M.add_at(buf, M.sfx_thud(0.6), s + 0.75)
        if name == "wrong":
            M.add_at(buf, M.sfx_thud(0.5), s + 1.5)
        if name in ("right", "answer"):
            M.add_at(buf, M.sfx_ding(0.4), s + (3.7 / 1.35 if name == "right" else 0.9))
        if name == "trick":
            M.add_at(buf, M.sfx_pop(0.4), s + 1.4)
    peak = float(np.max(np.abs(buf))) or 1.0
    buf = buf / max(1.0, peak / 0.95)
    wav = os.path.join(OUT, "_a.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", str(M.SR), "-ac", "1", "-i", "-", wav],
                   input=(np.clip(buf, -1, 1) * 32767).astype(np.int16).tobytes(), check=True)
    out = os.path.join(OUT, "demo_bharosa_clause26_part6.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", wav, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium", "-crf", "21",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    prev = None
    for fi in range(int(math.ceil(total * FPS))):
        gt = fi / FPS
        name, fn, s, d, _ = next(x for x in reversed(tl) if gt >= x[2])
        fr = fn(gt - s, d).convert("RGB")
        if gt - s < 0.15 and prev is not None and s > 0:
            fr = Image.blend(prev, fr, (gt - s) / 0.15)
        if gt - s + 1 / FPS >= d:
            prev = fr
        proc.stdin.write(fr.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg fail")
    os.remove(wav)
    for f_ in os.listdir(OUT):
        if f_.startswith("_pg"):
            os.remove(os.path.join(OUT, f_))
    print("DEMO BANI:", out, f"({total:.1f}s)")


if __name__ == "__main__":
    main()
