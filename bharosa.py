"""
BHAROSA FORMAT (v23, 2026-10-23) - series reel. User ki baat: "pehle GDS ko 100% bharosa ho ki ye niyam paper me
aata hai, ye sahi jagah hai, aasan bhasha me sikhaya ja raha hai, clause-wise syllabus ke hisaab se - fir visual."
Demo: demo_out/bharosa/demo_bharosa_v2_clause26_part6.mp4 (user ne haan kaha).

Kram (~24s):
  1. SABOOT  : isi niyam ka ASLI paper sawal mila (answer key se jaancha) -> us paper ka SCAN, sawal pe highlighter,
               mohar "असली पेपर में आया • राज्य साल • प्रश्न N", "सही जवाब इसी रील में".
               Na mila -> PO Guide ka asli panna + "पेपर के 50 में से 30 सवाल इसी PO Guide से!" (DoP syllabus 2019).
  2. AASAN   : kitaab ki kathin angrezi line (kati hui) vs "Postal Wala की भाषा: आसान हिंदी • चित्र • ट्रिक".
  3. RAASTA  : syllabus ke saare clause bindu - hare ho chuke, aaj wala sunehra: "कोई नियम नहीं छूटेगा!"
  4. CHITRA  : wahi photo-chitra kahani (naya_reel ki animation), upar bharose ki patti har pal.
  5. JAWAB   : sahi chitra ✓.
  6. TRICK   : niyam yaad rakhne ki 1 line (AI banata hai, doosri jaanch: niyam badla to nahi) - galat ho to drishya nahi.
  7. PAPER JAWAB : (sirf jab scan mila) wahi scan, sahi option pe laal ghera "सही जवाब: B".
  8. ANT     : Postal Wala की गारंटी + "फॉलो = पूरी तैयारी FREE" + "कमेंट करो MOCK -> FREE मॉक टेस्ट".
Awaaz: saaf aur samajhne layak - chuppi kaati jaati hai, speed sirf halki (BHAROSA_SPEED), lines chhoti.
Kuch bhi fail -> exception -> main.py naya_reel (v21) -> purana format (koi din khaali nahi).
"""
import math
import os
import re
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import naya_reel as N

M = None
W, H, FPS = 1080, 1920, 30
VERSION = "v23-bharosa (2026-10-23): asli paper scan saboot + aasan bhasha + clause-raasta + trick + MOCK"

BHAROSA_SPEED = float(os.getenv("BHAROSA_SPEED", "1.10"))   # user: tez, par samajh aaye
MAX_PAUSE = 0.14
GOLD, NAVY, RED, GRN, INK = (255, 205, 40), (16, 24, 52), (210, 30, 45), (22, 150, 70), (30, 40, 80)
SYL_LINE = "पेपर के 50 में से 30 सवाल इसी PO Guide से!"      # DoP patra 17-08/2018-SPB-I (10.05.2019) Paper-I Part-A
LETTER_HI = {"A": "ए", "B": "बी", "C": "सी", "D": "डी"}
# Shuru ki awaaz (hook) - instagram-agent-skill ke Hindi hook formulas se, roz badalti (ek hi template se skip badhta hai).
# Har line SACH hai: saboot (scan/PO Guide) wahi rehta hai, sirf bolne ka dhaancha badalta hai. (formula id, line)
OPEN_EXACT = [(14, "GDS साथियो! ये सवाल {L} के पेपर में आया था!"),
              (2, "ये नियम मत छोड़ना! {L} के पेपर में ये सवाल आया था!"),
              (3, "कोई नहीं बताता, ये सवाल {L} के पेपर में आ चुका है!"),
              (10, "MTS, पोस्टमैन की तैयारी है? ये सवाल {L} के पेपर में आया था!")]
OPEN_CLAUSE = [(14, "GDS साथियो! इसी क्लॉज़ से {L} के पेपर में सवाल आया!"),
               (2, "ये क्लॉज़ मत छोड़ना! इससे {L} के पेपर में सवाल आया!"),
               (3, "कोई नहीं बताता, इसी क्लॉज़ से {L} के पेपर में सवाल आया!"),
               (10, "MTS, पोस्टमैन की तैयारी है? इसी क्लॉज़ से {L} में सवाल आया!")]
OPEN_GUIDE = [(23, "GDS साथियो! पेपर के पचास में से तीस सवाल, इसी PO Guide से!"),
              (20, "मोटी किताबें छोड़ो! पचास में से तीस सवाल, इसी PO Guide से!"),
              (3, "कोई नहीं बताता, पचास में से तीस सवाल इसी PO Guide से!"),
              (14, "MTS, पोस्टमैन वालों! पचास में से तीस सवाल, इसी PO Guide से!")]
RAASTA_VOICES = ["सिलेबस के हिसाब से, क्लॉज़ वाइज़, कोई नियम नहीं छूटेगा!",
                 "पूरा PO Guide, क्लॉज़ वाइज़, एक भी नियम नहीं छूटेगा!",
                 "सिलेबस के हिसाब से चल रहे हैं, कोई नियम नहीं छूटेगा!"]
END_VOICE = "फॉलो करो, पूरी तैयारी फ्री! कमेंट में मॉक लिखो, फ्री मॉक टेस्ट पाओ!"

# ---- v24 (2026-10-29) "sawal pehle" ----
# Data: bharosa (v23) se series skip 65% -> 90%. Wajah: pehle ~5-8 sec saboot/prachar scene (paper/guide ->
# kathin -> raasta), sawal der se, saboot screen 2-5 sec bilkul ruki. v24: 0 sec par hi bada sawal + laal mohar
# (saboot sawal ke upar, alag scene nahi), kathin/raasta hata ke unki baat ant me, PO Guide ki line JAWAB ke
# baad ("देखो, PO Guide में यही लिखा है"). Chitra/animation/trick/MOCK wahi. BHAROSA_V2=0 -> purana v23.
V2 = os.getenv("BHAROSA_V2", "0") == "1"
# v24.1 (user): awaaz sawal NAHI padhti (sawal screen par hai) - hook bolti hai: kab/kis paper me aaya +
# "aise sawal me log galti karte hain". Roz badalta hai (ek hi line se skip badhta hai).
V2_OPEN_EXACT = ["ये सवाल {L} के पेपर में आया था! ज़्यादातर लोग इसमें गलती करते हैं!",
                 "{L} के पेपर का असली सवाल! जल्दी में लोग यहीं गलत कर देते हैं!",
                 "ये सवाल {L} में पूछा गया था! क्या आप सही जवाब दे पाओगे?"]
V2_OPEN_CLAUSE = ["इसी क्लॉज़ से {L} के पेपर में सवाल आया था! ऐसे सवाल में अक्सर लोग गलती करते हैं!",
                  "{L} के पेपर में इसी क्लॉज़ से सवाल आया! ज़्यादातर लोग यहाँ फँस जाते हैं!",
                  "इसी क्लॉज़ से {L} में सवाल पूछा गया था! आप होते तो क्या जवाब देते?"]
V2_OPEN_GUIDE = ["ऐसे सवाल पेपर में आते हैं, और ज़्यादातर लोग गलत कर देते हैं! आप बताओ?",
                 "PO Guide का पक्का नियम! इस पर लोग अक्सर गलती करते हैं!",
                 "ये नियम पेपर में आता है, और जल्दी में लोग यहीं फँसते हैं!"]
V2_GUIDE_VOICE = "देखो, PO Guide में यही लिखा है!"
V2_END_VOICE = ("उस साथी को भेजो, जो ये गलती करता है! फॉलो करो, कोई नियम नहीं छूटेगा! "
                "कमेंट में मॉक लिखो, फ्री मॉक टेस्ट पाओ!")
# v24.4 (user: "log poora dekh ke bhi like/share nahi karte"): galti ka chhota DRAMA - galat likha lifaafa ud ke
# laut aata hai, mohar "गलती!", Golu udaas + Bhaiya chauka (cutout, hilte-dulte) + awaaz effect; ant me
# "1 लाइन नोट्स" (screenshot/SAVE) + "उस साथी को भेजो" (share ki wajah). Nateeja wali line AI se (niyam se
# seedhe nikle tabhi), warna sach wali aam line (pareeksha me number).
V2_DRAMA = os.getenv("BHAROSA_DRAMA", "1") != "0"
GALTI_FALLBACK = ["यही गलती पेपर में की, तो नंबर कटेगा!",
                  "ऐसे लिखा, तो ये गलती पड़ेगी भारी!",
                  "ये गलती काम में भी, पेपर में भी - मत करना!"]
GALTI_PROMPT = """India Post rule (verified): {fact}
WRONG way (shown in our reel): {wrong}
Write ONE short Hindi line (max 10 words, Devanagari, simple spoken GDS language) saying what REALISTICALLY happens
in post office work if someone does the WRONG way - only a consequence that clearly and directly follows from this
rule (e.g. article cannot be read/delivered, delay, sent back). No invented penalties, no fines, no numbers,
no suspension/notice, no exaggeration. If no such consequence clearly follows, return empty line.
Return ONLY JSON: {{"line": ""}}"""
_BAD_GALTI = ("जुर्माना", "निलंब", "नोटिस", "सज़ा", "सजा", "जेल", "नौकरी", "रुपये", "%")


def init(mod):
    global M
    M = mod
    N.init(mod)


def F(sz):
    return N.font(sz)


def FR(sz):
    return N.font_reg(sz)


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def back(x):
    return M.ease_out_back(max(0.0, min(1.0, x)))


def stroke(d, xy, t, f, fill, sw=7):
    d.text(xy, t, font=f, fill=fill, anchor="mm", stroke_width=sw, stroke_fill=(0, 0, 0))


_BG = {}


def bg():
    if "bg" not in _BG:
        im = Image.new("RGBA", (W, H))
        d = ImageDraw.Draw(im)
        for y in range(H):
            k = y / H
            d.line((0, y, W, y), fill=(int(10 + 10 * k), int(16 + 18 * k), int(38 + 34 * k), 255))
        _BG["bg"] = im
    return _BG["bg"].copy()


def paste(cv, im, cx, cy, s=1.0):
    if s <= 0.02:
        return
    im2 = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BICUBIC) if s != 1 else im
    cv.alpha_composite(im2, (int(cx - im2.width / 2), int(cy - im2.height / 2)))


def stamp_img(top, sub=""):
    f1, f2 = F(62), F(44)
    w = int(max(f1.getlength(top), f2.getlength(sub) if sub else 0)) + 110
    h = 112 + (68 if sub else 0)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((4, 4, w - 5, h - 5), 26, fill=(255, 244, 240), outline=RED, width=10)
    d.rounded_rectangle((20, 20, w - 21, h - 21), 18, outline=RED, width=3)
    d.text((w / 2, 60), top, font=f1, fill=RED, anchor="mm")
    if sub:
        d.text((w / 2, 128), sub, font=f2, fill=NAVY, anchor="mm")
    return im.rotate(-5, expand=True, resample=Image.BICUBIC)


_CUT = {}


def cutout(path, h):
    """Kirdaar ki tasveer se background hatao: kinaron (rekha/rang-badlav) tak, kinare se jude saade hisse = background.
    (pehle wala flood-fill halka gola chhod deta tha). -> RGBA, unchai h."""
    key = (path, h)
    if key in _CUT:
        return _CUT[key]
    im = Image.open(path).convert("RGB")
    im = im.resize((int(im.width * h / im.height), h), Image.LANCZOS)
    a = np.array(im.filter(ImageFilter.GaussianBlur(1.2))).astype(np.float32)
    gx = np.abs(np.diff(a, axis=1, prepend=a[:, :1])).sum(2)
    gy = np.abs(np.diff(a, axis=0, prepend=a[:1])).sum(2)
    edge = (np.maximum(gx, gy) > 10) | (a.mean(2) < 80)
    work = Image.fromarray(np.where(edge, 0, 255).astype("uint8")).filter(ImageFilter.MinFilter(3))  # rekha mot
    w_, h_ = work.size
    seeds = [(x, 0) for x in range(0, w_, 6)] + [(0, y) for y in range(0, h_, 6)] + [(w_ - 1, y) for y in range(0, h_, 6)]
    for sx, sy in seeds:
        if work.getpixel((sx, sy)) == 255:
            ImageDraw.floodfill(work, (sx, sy), 128)
    fg = (np.array(work) != 128).astype("uint8") * 255
    mask = Image.fromarray(fg).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.0))
    out = im.convert("RGBA")
    out.putalpha(mask)
    _CUT[key] = out
    return out


_VIG = {}


def vignette():
    if "v" not in _VIG:
        yy, xx = np.mgrid[0:H, 0:W]
        r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.6)) ** 2)
        a = (np.clip((r - 0.55) / 0.6, 0, 1) ** 1.6 * 200).astype("uint8")
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        im.putalpha(Image.fromarray(a))
        _VIG["v"] = im
    return _VIG["v"]


def sprite_at(cv, sp, cx, bottom, t, sx=1.0, sy=1.0, tilt=0.0, phase=0.0):
    """Kirdaar ko zinda rakho: saans (halka upar-neeche phoolna) + jhoolna; paon (neeche) anchor."""
    br = 1 + 0.018 * math.sin(t * 2.4 + phase)
    sw = 1.6 * math.sin(t * 1.7 + phase) + tilt
    im = sp.resize((max(1, int(sp.width * sx)), max(1, int(sp.height * sy * br))), Image.BICUBIC)
    im = im.rotate(sw, expand=True, resample=Image.BICUBIC, center=(im.width / 2, im.height))
    cv.alpha_composite(im, (int(cx - im.width / 2), int(bottom - im.height)))


def burst(cv, cx, cy, k, col, n=14):
    """Takkar ka gubbaar: kirne bahar phailti, fiki padti."""
    if k <= 0 or k >= 1:
        return
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    e = ease(k)
    for i in range(n):
        a = i * 2 * math.pi / n + 0.3
        r0, r1 = 120 + 260 * e, 170 + 330 * e
        al = int(255 * (1 - k))
        d.line((cx + r0 * math.cos(a), cy + r0 * math.sin(a) * 0.8, cx + r1 * math.cos(a), cy + r1 * math.sin(a) * 0.8),
               fill=col + (al,), width=10)
    cv.alpha_composite(ov)


_CONF = [(((i * 97) % 1000) / 1000, ((i * 57) % 1000) / 1000, i % 5) for i in range(70)]
_CCOL = [(255, 205, 40), (22, 170, 80), (230, 50, 60), (60, 140, 255), (255, 255, 255)]


def confetti(cv, t):
    if t <= 0 or t > 2.2:
        return
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for i, (u, v, c) in enumerate(_CONF):
        vx = (u - 0.5) * 1500
        vy = -900 - 700 * v
        x = 540 + vx * t
        y = 900 + vy * t + 1400 * t * t
        if not (-40 < x < W + 40 and -40 < y < H + 40):
            continue
        a = t * (6 + 5 * v) + i
        w_, h_ = 22 * abs(math.cos(a)) + 4, 12
        pts = [(x + w_ * math.cos(a) - h_ * math.sin(a), y + w_ * math.sin(a) + h_ * math.cos(a)) for w_, h_ in
               ((w_, h_), (-w_, h_), (-w_, -h_), (w_, -h_))]
        d.polygon(pts, fill=_CCOL[c] + (int(255 * min(1.0, (2.2 - t) / 0.5)),))
    cv.alpha_composite(ov)


def drop(cv, x, y, a):
    """Pasine/aansu ki boond."""
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    al = int(230 * max(0.0, min(1.0, a)))
    d.polygon([(x, y - 30), (x - 16, y), (x + 16, y)], fill=(120, 190, 255, al))
    d.ellipse((x - 16, y - 12, x + 16, y + 20), fill=(120, 190, 255, al))
    cv.alpha_composite(ov)


def char_file(name, expr):
    for p in (os.path.join("clause_plans", "characters", f"{name}_{expr}.jpg"),
              os.path.join("clause_plans", "characters", f"{name}.jpg")):
        if os.path.exists(p):
            return p
    return None


def lifaafa(lines):
    """Galat likha lifaafa (PIL) - Hindi likhai yahin (Blender/FLUX me Hindi bigadti hai)."""
    im = Image.new("RGBA", (760, 470), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((10, 10, 750, 460), 22, fill=(252, 250, 244), outline=(180, 170, 150), width=4)
    d.line((10, 10, 380, 230), fill=(225, 218, 200), width=4)
    d.line((750, 10, 380, 230), fill=(225, 218, 200), width=4)
    d.rectangle((600, 40, 710, 160), fill=(214, 60, 60), outline=(255, 255, 255), width=5)
    d.text((655, 100), "₹", font=F(56), fill="white", anchor="mm")
    y = 260
    for ln in (lines or [])[:3]:
        f, s_, ls = M.fit_lines(str(ln), 620, 1, 46, 30)
        d.text((80, y), " ".join(ls[0]), font=f, fill=(30, 40, 90), anchor="lm")
        y += int(s_ * 1.35)
    return im.rotate(-4, expand=True, resample=Image.BICUBIC)


def galti_line(part, data, wrong_pn):
    """Galti ka nateeja (AI, niyam se seedha nikle tabhi) - part me cache. Na bane -> sach wali aam line."""
    gv = part.get("galti_v") if isinstance(part, dict) and isinstance(part.get("galti_v"), dict) else {}
    if gv.get("v") == 1:
        ln = gv.get("line") or ""
    else:
        ln = ""
        try:
            js = M._llm_json(GALTI_PROMPT.format(fact=data.get("fact", ""), wrong=wrong_pn.get("text", "")),
                             only="gemini" if M.GEMINI_API_KEY else None)
            ln = " ".join(str((js or {}).get("line") or "").split())
            if len(ln.split()) > 12 or any(b in ln for b in _BAD_GALTI) or re.search(r"[0-9०-९]", ln):
                ln = ""
            if isinstance(part, dict) and not M.DRY_RUN:
                part["galti_v"] = {"v": 1, "line": ln}
        except Exception as exc:
            print("  Galti-line AI se nahi bani (aam line):", str(exc)[:100])
    if not ln:
        ln = GALTI_FALLBACK[int(data.get("episode") or 0) % len(GALTI_FALLBACK)]
    print("  Galti-drama line:", ln)
    return ln


# ============================================================ asli paper ka scan

_BB = {}


def _paper_words(pdf):
    if pdf not in _BB:
        html = subprocess.run(["pdftotext", "-bbox", pdf, "-"], capture_output=True, text=True, timeout=90).stdout
        pages = []
        for pg in html.split("<page ")[1:]:
            m = re.match(r'width="([\d.]+)" height="([\d.]+)"', pg)
            ws = [(float(a), float(b), float(c), float(d_), t) for a, b, c, d_, t in
                  re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', pg)]
            pages.append((float(m.group(1)) if m else 595, float(m.group(2)) if m else 842, ws))
        _BB[pdf] = pages
    return _BB[pdf]


def _norm(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def _qtok(no):
    return re.compile(r"^(?:Q\.?)?%d[.):]?$" % no, re.I)


_OPT = re.compile(r"^\(?([A-Da-d])[.)]$")


def paper_scan(pyq):
    """
    PYQ (src 'file#Q20') ka asli scan: {img, q:(y0,y1), a:(y0,y1), label, letter} ya None.
    Sawal ke pehle shabd index se milaye jaate hain; option ki line A./a) se; kuch bhi shak -> None (scan nahi).
    """
    try:
        import pyq_reel as P
        src = str(pyq.get("src") or "")
        m = re.match(r"(.+)#Q(\d+)$", src)
        if not m or pyq.get("ans") not in ("A", "B", "C", "D"):
            return None
        fn, no = m.group(1), int(m.group(2))
        pdf = os.path.join(P.PAPER_DIR, fn)
        if not os.path.exists(pdf):
            return None
        qtext = pyq.get("q_en") or next((c["text"] for c in P.paper_index() if c["file"] == fn and int(c["no"]) == no), "")
        want = [_norm(w) for w in qtext.split()[:9] if len(_norm(w)) >= 3][:5]
        if len(want) < 2:
            return None
        for pi, (pw, ph, ws) in enumerate(_paper_words(pdf)):
            for i, w in enumerate(ws):
                if not _qtok(no).match(w[4]):
                    continue
                nxt = [_norm(x[4]) for x in ws[i + 1:i + 40]]
                if sum(1 for t in want if t in nxt) < max(2, len(want) - 2):
                    continue
                j = next((k for k in range(i + 1, min(len(ws), i + 170)) if _qtok(no + 1).match(ws[k][4])), None)
                seg = [s for s in (ws[i:j] if j else ws[i:i + 90]) if abs(s[0] - w[0]) < pw * 0.5]
                opts = [(k, _OPT.match(s[4]).group(1).upper()) for k, s in enumerate(seg) if _OPT.match(s[4])]
                letters = [L for _, L in opts]
                if letters[:4] != ["A", "B", "C", "D"]:
                    continue
                ia = opts[0][0]
                il = opts["ABCD".index(pyq["ans"])][0]
                inx = opts["ABCD".index(pyq["ans"]) + 1][0] if pyq["ans"] != "D" else len(seg)
                x0, y0 = min(s[0] for s in seg), min(s[1] for s in seg)
                x1, y1 = max(s[2] for s in seg), max(s[3] for s in seg)
                dpi = 200
                base = os.path.join(tempfile.gettempdir(), f"_pyq_scan_{pi + 1}")
                subprocess.run(["pdftoppm", "-f", str(pi + 1), "-l", str(pi + 1), "-r", str(dpi), "-png", "-singlefile",
                                pdf, base], check=True, capture_output=True)
                pg = Image.open(base + ".png").convert("RGB")
                k = dpi / 72.0
                pad = 10
                box = [max(0, int((x0 - pad) * k)), max(0, int((y0 - pad) * k)),
                       min(pg.width, int((x1 + pad) * k)), min(pg.height, int((y1 + pad) * k))]
                cr = pg.crop(box)
                sc = 940 / cr.width
                cr = cr.resize((940, int(cr.height * sc)), Image.LANCZOS)
                if cr.height > 900 or cr.height < 120:
                    return None
                ty = lambda v: (v * k - box[1]) * sc
                return {"img": cr, "clause_level": bool(pyq.get("clause_level")),
                        "q": (ty(min(s[1] for s in seg[:ia])), ty(max(s[3] for s in seg[:ia]))),
                        "a": (ty(min(s[1] for s in seg[il:inx])), ty(max(s[3] for s in seg[il:inx]))),
                        "label": (P.paper_label(fn), no), "letter": pyq["ans"]}
        return None
    except Exception as exc:
        print("  Paper scan nahi bana (PO Guide saboot chalega):", str(exc)[:140])
        return None


CLAUSE_PYQ_PROMPT = """Below are REAL questions from India Post departmental exam papers (GDS to MTS / Postman), found by
keyword search for PO Guide Part I, Clause {num}: "{title}".
Clause text (start): {clause}

Pick the questions that are truly about THIS clause's subject (the same rule area), not just sharing a word.
Ignore garbage text that belongs to a previous question (e.g. "PAPER - 1 D. ..." before the real question).
For each picked question give "q_en": the clean English question sentence exactly as printed (without options).
CANDIDATES:
{cands}
Return ONLY JSON: {{"items": [{{"id": "", "q_en": ""}}]}}  (best first, max 3; empty list if none fits)"""


def clause_pyq(plan, part_no=1):
    """Isi CLAUSE ka asli paper sawal (niyam ka exact na mile tab). Jawab = paper ki answer key. Plan me cache.
    v2 (2026-10-29): pehle ek hi sawal save hota tha -> Clause 26 ke har part me "हरियाणा 2020". Ab saare
    scan-layak sawal (max 3) save, part ke hisaab se badalte hain."""
    cv = plan.get("clause_pyq_v") if isinstance(plan.get("clause_pyq_v"), dict) else {}
    if cv.get("v") == 2:
        its = cv.get("items") or []
        return dict(its[(int(part_no or 1) - 1) % len(its)]) if its else None
    if M.DRY_RUN:
        return None
    import pyq_reel as P
    e = {"guide_line": " ".join((plan.get("clause_text_en") or "").split())[:1500],
         "en_question": plan.get("title_en", ""), "en_fact": "", "source_quote": "", "trap_quote": ""}
    cands = []
    for c in P.candidates(e, k=10):
        if c.get("trust") and P.key_map(c["file"]).get(int(c["no"])) in ("A", "B", "C", "D"):
            cands.append(c)
    item, items = None, []
    if cands:
        try:
            js = M._llm_json(CLAUSE_PYQ_PROMPT.format(
                num=plan.get("clause_no"), title=plan.get("title_en", ""),
                clause=" ".join((plan.get("clause_text_en") or "").split())[:900],
                cands="\n".join(f'[{c["id"]}] {c["exam"]} Q{c["no"]}: {c["text"][:400]}' for c in cands)),
                only="gemini" if M.GEMINI_API_KEY else None)
            by = {c["id"]: c for c in cands}
            for x in (js or {}).get("items") or []:
                c = by.get(str(x.get("id")))
                if not c:
                    continue
                cand = {"src": f'{c["file"]}#Q{c["no"]}', "ans": P.key_map(c["file"])[int(c["no"])],
                        "exams": c.get("exams") or [c["exam"]], "q_en": " ".join(str(x.get("q_en") or "").split())}
                if paper_scan(cand):                 # scan ban sake tabhi (asli panna dikhna chahiye)
                    items.append(cand)
        except Exception as exc:
            print("  Clause PYQ jaanch nahi hui (agli run me):", str(exc)[:140])
            return None
    plan["clause_pyq_v"] = {"v": 2, "items": items}
    item = dict(items[(int(part_no or 1) - 1) % len(items)]) if items else None
    try:
        M.save_plan(plan)
    except Exception:
        pass
    print("  Clause-level asli PYQ:", (item or {}).get("src") or "nahi mila")
    return item


def scan_card(scan, t_hl, t_ring):
    pc = scan["img"].copy()
    if t_hl > 0:
        hl = Image.new("RGB", pc.size, (255, 255, 255))
        q0, q1 = scan["q"]
        ImageDraw.Draw(hl).rectangle((0, q0 - 4, pc.width * ease(t_hl), q1 + 4), fill=(255, 226, 70))
        pc = ImageChops.multiply(pc, hl)
    pc = pc.convert("RGBA")
    if t_ring > 0:
        a0, a1 = scan["a"]
        ImageDraw.Draw(pc).ellipse((10, a0 - 16, 10 + (pc.width - 60) * ease(t_ring) + 40, a1 + 16),
                                   outline=(220, 20, 30), width=7)
    out = Image.new("RGBA", (pc.width + 40, pc.height + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((24, 28, pc.width + 24, pc.height + 28), fill=(0, 0, 0, 150))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    out.alpha_composite(pc, (10, 10))
    return out.rotate(1.5, expand=True, resample=Image.BICUBIC)


# ============================================================ trick (yaad rakhne ki)

TRICK_PROMPT = """You write ONE memory trick (Hindi) that makes an India Post rule unforgettable for GDS employees.
Rule (verified, Hindi): {fact}
Official source (PO Guide): {src}
Question: {question}   Correct answer: {answer}

The trick: at most 14 Hindi words, simple spoken Hindi, catchy - a rhyme, a picture in the mind, a pairing/contrast,
a body/hand gesture, or a first-letter hook. It must lead the viewer to EXACTLY the rule above.
STRICT: no new fact, no number or condition that is not in the rule/source, never change the meaning.
English letters only for terms the rule itself writes in English (PIN, VP, QMS...).
"key": 1-3 short words of the trick to highlight.
Return ONLY JSON: {{"trick": "", "key": []}}"""

TRICK_CHECK = """Rule (verified): {fact}
Source: {src}
Memory trick (Hindi): {trick}
Does the trick lead to exactly this rule, without adding any fact, number or condition and without contradicting it?
A rhyme or picture is fine as long as the rule it points to is right.
Return ONLY JSON: {{"ok": true, "why": ""}}"""


def ensure_trick(part, data):
    tv = part.get("trick_v") if isinstance(part.get("trick_v"), dict) else {}
    if tv.get("v") == 1:
        return tv if tv.get("ok") else None
    if M.DRY_RUN:
        return None
    src = " ".join(str(part.get("source_quote") or "").split())[:600]
    try:
        js = M._llm_json(TRICK_PROMPT.format(fact=data.get("fact", ""), src=src, question=data.get("question", ""),
                                             answer=data.get("correct_text", "")))
        tr = " ".join(str((js or {}).get("trick") or "").split())
        key = [str(k).strip() for k in ((js or {}).get("key") or []) if str(k).strip()][:3]
        ok = bool(tr) and len(tr.split()) <= 16 and re.search(r"[ऀ-ॿ]", tr) is not None
        why = ""
        if ok:
            chk = M._llm_json(TRICK_CHECK.format(fact=data.get("fact", ""), src=src, trick=tr),
                              only="gemini" if M.GEMINI_API_KEY else None)
            ok, why = bool((chk or {}).get("ok")), str((chk or {}).get("why") or "")[:160]
        tv = {"v": 1, "ok": ok, "text": tr, "key": key, "why": why}
        print(f"  Trick: {tr} | jaanch {'PASS' if ok else 'FAIL ' + why}")
    except Exception as exc:
        print("  Trick nahi bani (reel bina trick):", str(exc)[:140])
        return None                                   # agli run me dobara
    part["trick_v"] = tv
    return tv if ok else None


# ============================================================ awaaz (saaf)

def _trim(a, thr=0.012):
    idx = np.where(np.abs(a) > thr)[0]
    if not len(idx):
        return a
    s = max(0, idx[0] - int(0.03 * M.SR))
    e = min(len(a), idx[-1] + int(0.06 * M.SR))
    return a[s:e]


def clean_voice(a):
    try:
        a = M._compress_pauses(a, MAX_PAUSE)[0]
    except Exception:
        pass
    a = _trim(a)
    return M.speed_voice(a, BHAROSA_SPEED) if BHAROSA_SPEED != 1.0 else a


# ============================================================ reel

class Bharosa(N.Reel):
    def __init__(self, data, story, ans_pn, proof, scan, trick, syl, guide_en):
        super().__init__(data, story, ans_pn, proof, None, False)
        self.guide_proof = proof
        self.proof = True                     # naya ki "GDS की गलती" pill story pe nahi (patti me sab hai)
        self.scan, self.trick, self.syl, self.guide_en = scan, trick, syl, guide_en
        self.stamp = (stamp_img(f"इसी Clause से {scan['label'][0]} में सवाल", f"असली पेपर  •  प्रश्न {scan['label'][1]}")
                      if scan.get("clause_level") else
                      stamp_img("असली पेपर में आया", f"{scan['label'][0]}  •  प्रश्न {scan['label'][1]}")) if scan else \
            stamp_img("सिलेबस का पक्का नियम", "PO Guide Part I")
        self.piece_n = len(story) + 1
        self._fx = {}

    # ---- bharose ki patti (puri reel) ----
    def strip(self, cv, piece, cover=158):
        d = ImageDraw.Draw(cv)
        d.rectangle((0, 0, W, cover), fill=(8, 12, 30))
        d.rounded_rectangle((30, 36, 520, 108), 36, fill=GRN)
        d.text((275, 72), "100% परीक्षा वाला नियम", font=F(38), fill="white", anchor="mm")
        d.rounded_rectangle((550, 36, 1050, 108), 36, fill=GOLD)
        d.text((800, 72), f"चित्रों से आसान • {piece}", font=F(36), fill=NAVY, anchor="mm")
        if self.syl and self.syl[0]:
            d.text((540, 136), f"सिलेबस: PO Guide Part I  •  Clause {self.cno}  •  {self.syl[0]}/{self.syl[1]}",
                   font=FR(26), fill=(190, 200, 225), anchor="mm")

    def sc_paper(self, sc, t):
        cv = bg()
        d = ImageDraw.Draw(cv)
        d.rounded_rectangle((300, 70, 780, 134), 32, fill=GOLD)
        d.text((540, 102), "GDS से MTS / Postman", font=F(40), fill=NAVY, anchor="mm")
        if self.scan.get("clause_level"):
            stroke(d, (540, 240), f"इसी Clause {self.cno} से", F(84), (255, 255, 255))
            stroke(d, (540, 345), "पेपर में सवाल आया!", F(96), (255, 214, 40), 8)
        else:
            stroke(d, (540, 240), "ये सवाल असली पेपर में", F(84), (255, 255, 255))
            stroke(d, (540, 345), "पूछा जा चुका है!", F(96), (255, 214, 40), 8)
        k = ease(t / 0.35)
        card = scan_card(self.scan, (t - 0.45) / 0.6, 0)
        cv.alpha_composite(card, (60, int(1080 + (1 - k) * 700) - card.height // 2))
        if t > 0.75:
            paste(cv, self.stamp, 540, 620, 1.0 + 0.6 * (1 - ease((t - 0.75) / 0.18)))
        if t > 1.5:
            a = ease((t - 1.5) / 0.3)
            y = int(1500 + (1 - a) * 60)
            d.rounded_rectangle((70, y, 1010, y + 120), 30, fill=RED)
            d.text((540, y + 60), ("इसलिए ये नियम ध्यान से देखो!" if self.scan.get("clause_level")
                                   else "सही जवाब इसी रील में — ध्यान से देखो!"), font=F(50), fill="white", anchor="mm")
        return cv

    def sc_guide(self, sc, t):                       # scan nahi -> PO Guide panna + syllabus ka sach
        cv = self.guide_proof.frame(t, sc["dur"]) if self.guide_proof else bg()
        d = ImageDraw.Draw(cv)
        d.rectangle((0, 0, W, 300), fill=(8, 12, 30, 255))
        stroke(d, (540, 110), "पेपर के 50 में से 30 सवाल", F(76), (255, 255, 255))
        stroke(d, (540, 215), "इसी PO Guide से!", F(86), (255, 214, 40), 8)
        if t > 0.6:
            paste(cv, self.stamp, 540, 420, 1.0 + 0.5 * (1 - ease((t - 0.6) / 0.18)))
        return cv

    def sc_sawal(self, sc, t):
        """Bada saaf sawal + chaaron option + 3-2-1 (jawab baad me chitron se)."""
        cv = N.blurred_bg(self.story[0], dark=0.68)
        self.strip(cv, "सवाल")
        d = ImageDraw.Draw(cv)
        if V2:      # saboot ki mohar pehle frame se (thump + halki dhadkan -> screen kabhi ruki nahi)
            s = 1.25 - 0.25 * ease(t / 0.2) + 0.03 * math.sin(t * 6.0)
            paste(cv, self.stamp, 470, 262, s * 0.78)
        else:
            paste(cv, N.pill("रुको! पहले सोचो", 54, (255, 255, 255), RED), 540, 255, back(t / 0.3))
        q = " ".join((self.data.get("question") or "").split())
        f, s_, ls = M.fit_lines(q, 900, 4, 68, 44)
        step = int(s_ * 1.28)
        h = 90 + len(ls) * step
        y0 = 400 if V2 else 340
        k = 1.0 if V2 else ease((t - 0.1) / 0.3)           # v24: sawal 0 sec se poora dikhe
        if k > 0:
            d.rounded_rectangle((60, y0, 1020, y0 + h), 34, fill=(255, 255, 255), outline=GOLD, width=6)
            if V2:      # v24: awaaz ke saath shabd laal hote jaayein (screen kabhi ruki nahi, aankh padhti rahe)
                nw = sum(len(l) for l in ls)
                p = (t - 0.3) / max(1.0, sc.get("cd0", 2.5) - 0.3)   # padhne ki raftaar se (awaaz hook bolti hai)
                shown = int(nw * min(1.0, max(0.0, p)))
                cnt, sp_ = 0, f.getlength(" ")
                for i, ln in enumerate(ls):
                    wz = [f.getlength(w_) for w_ in ln]
                    x = 540 - (sum(wz) + sp_ * (len(ln) - 1)) / 2
                    yy = y0 + 45 + step / 2 + i * step - 8
                    for w_, z in zip(ln, wz):
                        d.text((x, yy), w_, font=f, fill=(RED if cnt < shown else INK), anchor="lm")
                        x += z + sp_
                        cnt += 1
            else:
                for i, ln in enumerate(ls):
                    d.text((540, y0 + 45 + step / 2 + i * step - 8), " ".join(ln), font=f, fill=INK, anchor="mm")
        oy = y0 + h + 40
        for j, (L, txt) in enumerate(self.data.get("options") or []):
            kj = back((t - (0.12 if V2 else 0.35) - (0.08 if V2 else 0.12) * j) / 0.25)
            if kj <= 0.02:
                continue
            fo, so, lo = M.fit_lines(txt, 760, 2, 50, 34)
            bh = max(110, 40 + len(lo) * int(so * 1.2))
            card = Image.new("RGBA", (960, bh), (0, 0, 0, 0))
            cd = ImageDraw.Draw(card)
            cd.rounded_rectangle((0, 0, 959, bh - 1), 30, fill=(255, 255, 255, 235), outline=(220, 224, 235), width=3)
            cd.ellipse((24, bh / 2 - 34, 92, bh / 2 + 34), fill=NAVY)
            cd.text((58, bh / 2), L, font=F(40), fill=GOLD, anchor="mm")
            for i, ln in enumerate(lo):
                cd.text((122, bh / 2 + (i - (len(lo) - 1) / 2) * int(so * 1.2)), " ".join(ln), font=fo, fill=INK,
                        anchor="lm")
            paste(cv, card, 540, oy + bh / 2, kj)
            oy += bh + 22
        cd0 = sc["cd0"]
        if t >= cd0:
            n = 3 - min(2, int((t - cd0) / N.CD_STEP))
            kk = back((t - cd0 - (3 - n) * N.CD_STEP) / 0.18)
            paste(cv, N.countdown(n), 960, 255, max(0.05, 1.3 - 0.3 * kk))
        stroke(d, (540, min(oy + 70, 1780)), "सोचो... जवाब इसी रील में!", F(52), (255, 214, 40), 6)
        return cv

    def sc_guide2(self, sc, t):                      # v24: jawab ke baad saboot - PO Guide ki asli line
        cv = self.guide_proof.frame(t, sc["dur"])
        d = ImageDraw.Draw(cv)
        d.rectangle((0, 0, W, 300), fill=(8, 12, 30, 255))
        stroke(d, (540, 110), "देखो! PO Guide में", F(80), (255, 255, 255))
        stroke(d, (540, 215), "यहीं लिखा है", F(90), (255, 214, 40), 8)
        paste(cv, M.check_sprite(120), 930, 160, back((t - 0.25) / 0.3))
        return cv

    def sc_galti(self, sc, t):                       # v24.5: galti ka drama - gehraai, speed, takkar, bhaav
        pn = sc["pn"]
        # 1) asli (saaf) chitra peeche, dheere andar khiskta (camera push) + andhera kinara -> gehraai
        key = ("galti_bg", pn.get("img"))
        if key not in self._fx:
            base = N.panel_full(pn, 0.6, 0.0, 0.0, 0.0, 0.0).convert("RGB").filter(ImageFilter.GaussianBlur(3))
            self._fx[key] = Image.blend(base, Image.new("RGB", (W, H), (12, 14, 26)), 0.38)
        z = 1.0 + 0.06 * min(1.0, t / max(1.0, sc["dur"]))
        bgi = self._fx[key].resize((int(W * z), int(H * z)), Image.BILINEAR)
        ox, oy = (bgi.width - W) // 2, (bgi.height - H) // 2
        cv = bgi.crop((ox, oy, ox + W, oy + H)).convert("RGBA")
        cv.alpha_composite(vignette())
        d = ImageDraw.Draw(cv)
        env = self._fx.get("env")
        if env is None:
            env = self._fx["env"] = lifaafa((pn.get("card") or {}).get("lines") or [])
        # 2) lifaafa: anticipation (peeche jhukna) -> zoom se ud jaana (trail + speed lines) -> laut ke dhadaam
        T_OUT, T_BACK, T_HIT = 0.55, 1.0, 1.45
        cx, cy, rot, sx, sy = 540.0, 700.0, 0.0, 1.0, 1.0
        trail = []
        if t < 0.35:
            k = back(t / 0.35)
            sx = sy = max(0.05, k)
        elif t < T_OUT:                                  # anticipation: thoda peeche + dabna
            k = ease((t - 0.35) / (T_OUT - 0.35))
            cx, rot, sx, sy = 540 - 60 * k, 6 * k, 1 - 0.06 * k, 1 + 0.04 * k
        elif t < T_BACK:
            k = ease((t - T_OUT) / (T_BACK - T_OUT)) ** 1.6
            cx, rot, sx, sy = 480 + 1150 * k, 6 - 30 * k, 1.12, 0.9
            trail = [(-1, 0.09), (-1, 0.18)]
        elif t < T_HIT:
            k = ease((t - T_BACK) / (T_HIT - T_BACK))
            cx, rot, sx, sy = 1640 - 1100 * k, 20 * (1 - k), 1.1, 0.92
            trail = [(1, 0.09), (1, 0.18)]
        else:                                            # takkar: squash -> wapas
            k = (t - T_HIT) / 0.22
            sq = max(0.0, 1 - k) * math.sin(min(1.0, k) * math.pi)
            sx, sy = 1 + 0.12 * sq, 1 - 0.1 * sq
        e = env.resize((max(1, int(env.width * sx)), max(1, int(env.height * sy))), Image.BICUBIC)
        e = e.rotate(rot, expand=True, resample=Image.BICUBIC) if abs(rot) > 0.5 else e
        if trail:                                        # raftaar: speed lines + parchhai
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            for yy in range(560, 860, 46):
                L = 260 + (yy * 37) % 180
                x_end = cx - trail[0][0] * e.width * 0.45
                od.line((x_end - trail[0][0] * L, yy, x_end, yy), fill=(255, 255, 255, 130), width=6)
            cv.alpha_composite(ov)
            for sgn, lag in trail:
                gh = e.copy()
                gh.putalpha(gh.getchannel("A").point(lambda v: int(v * 0.28)))
                paste(cv, gh, cx - sgn * lag * 1500, cy, 1.0)
        paste(cv, e, cx, cy, 1.0)
        if T_BACK <= t < T_HIT + 0.3:
            ka = back((t - T_BACK) / 0.3)
            paste(cv, N.pill("वापस आ गया!", 64, NAVY, GOLD), 540, 360, max(0.05, ka))
        if t >= T_HIT:                                   # mohar: oopar se girti, dhool ka gubbaar
            k = ease((t - T_HIT) / 0.14)
            paste(cv, stamp_img("गलती!"), 560, 740, 2.6 - 1.1 * k)
            burst(cv, 560, 740, (t - T_HIT) / 0.45, (255, 90, 80))
        # 3) kirdaar: Bhaiya uchhal ke chaunkte hain, Golu sir jhukaata hai (aansu ki boond)
        if t >= T_HIT + 0.05:
            tt = t - T_HIT - 0.05
            g, b = char_file("grahak", "udaas"), char_file("bhaiya", "chauka")
            if g:
                ent = back(tt / 0.35)
                sink = 18 * ease((tt - 0.4) / 0.6)
                sprite_at(cv, cutout(g, 780), 255, 1930 + (1 - ent) * 700 + sink, t,
                          tilt=-4 * ease((tt - 0.4) / 0.6), phase=0.0)
                if tt > 0.6:
                    drop(cv, 345, 1250 + 60 * ((tt - 0.6) % 0.9), 1 - ((tt - 0.6) % 0.9) / 0.9)
            if b:
                jump = 120 * max(0.0, math.sin(min(1.0, tt / 0.45) * math.pi))
                land = (tt - 0.45) / 0.18
                sqz = 0.07 * max(0.0, 1 - land) * math.sin(min(1.0, max(0.0, land)) * math.pi) if tt > 0.45 else 0.0
                sprite_at(cv, cutout(b, 720), 830, 1960 - jump, t, sx=1 + sqz, sy=1 - sqz, phase=1.3)
                if tt > 0.2:
                    paste(cv, N.pill("!", 90, (255, 255, 255), RED), 985, 1300 - jump, back((tt - 0.2) / 0.25))
        p = (t - sc["lead"]) / max(0.3, sc["vd"])
        N.caption(cv, sc["text"], p, cy=1080)
        self.strip(cv, "गलती")
        if T_HIT <= t < T_HIT + 0.25:                    # camera jhatka
            a_ = 16 * (1 - (t - T_HIT) / 0.25)
            cv = ImageChops.offset(cv, int(a_ * math.sin(t * 90)), int(a_ * math.cos(t * 70)))
        return cv

    def b3d_frame(self, t):
        """v24.6 demo: Blender ka 3D shot (B3D_ANS = PNG frames ka folder, 24 fps) - na ho to None."""
        d_ = os.environ.get("B3D_ANS", "")
        if not d_ or not os.path.isdir(d_):
            return None
        fs = self._fx.get("b3d_files")
        if fs is None:
            fs = self._fx["b3d_files"] = sorted(f for f in os.listdir(d_) if f.endswith(".png"))
        if not fs:
            return None
        f = fs[min(len(fs) - 1, int(t * 24))]
        return Image.open(os.path.join(d_, f)).convert("RGB").resize((W, H), Image.LANCZOS).convert("RGBA")

    def sc_ans(self, sc, t):                         # v24.5: sahi jawab par jashn (confetti + Golu khush)
        b3 = self.b3d_frame(t) if V2 else None
        if b3 is not None:                           # 3D shot: lifaafa + globe + ✓ (Blender)
            cv = b3
            p = (t - sc["lead"]) / max(0.3, sc["vd"])
            N.caption(cv, sc["text"], p, cy=1560)
            self.strip(cv, f"टुकड़ा {self.piece_n}/{self.piece_n}", cover=196)
            N.put(cv, N.pill("सही जवाब", 42, (255, 255, 255), N.GREEN_C), W / 2, 228,
                  scale=max(0.05, M.ease_out_back(M.prog(t, 0.0, 0.3))))
            confetti(cv, t - 2.1)
            return cv
        cv = super().sc_ans(sc, t)
        self.strip(cv, f"टुकड़ा {self.piece_n}/{self.piece_n}", cover=196)
        N.put(cv, N.pill("सही जवाब", 42, (255, 255, 255), N.GREEN_C), W / 2, 228,
              scale=max(0.05, M.ease_out_back(M.prog(t, 0.0, 0.3))))
        if V2 and V2_DRAMA:
            confetti(cv, t - 0.3)
            g = char_file("grahak", "khush")
            if g and t > 0.45:
                tt = t - 0.45
                hop = 70 * abs(math.sin(tt * 5.5)) * max(0.0, 1 - tt / 1.6)
                sprite_at(cv, cutout(g, 600), 170, 2010 + (1 - back(tt / 0.35)) * 500 - hop, t, phase=0.5)
        return cv

    def sc_end2(self, sc, t):                        # v24.4: 1 लाइन नोट्स (SAVE) + साथी को भेजो (share)
        cv = bg()
        d = ImageDraw.Draw(cv)
        k0 = back(t / 0.3)
        card = Image.new("RGBA", (960, 470), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle((0, 0, 959, 469), 34, fill=(255, 248, 230), outline=GOLD, width=8)
        cd.rounded_rectangle((30, -2, 470, 74), 30, fill=NAVY)
        cd.text((250, 36), "1 लाइन नोट्स", font=F(46), fill=GOLD, anchor="mm")
        f, s_, ls = M.fit_lines(self.data.get("fact") or "", 860, 3, 62, 40)
        yy = 110
        for ln in ls:
            cd.text((480, yy + s_ // 2), " ".join(ln), font=f, fill=INK, anchor="mm")
            yy += int(s_ * 1.3)
        cd.text((480, 425), "SAVE करो  •  स्क्रीनशॉट लो", font=F(40), fill=RED, anchor="mm")
        paste(cv, card, 540, 370, k0)
        if t > 0.35:
            k = back((t - 0.35) / 0.3)
            sh = Image.new("RGBA", (960, 250), (0, 0, 0, 0))
            sd = ImageDraw.Draw(sh)
            sd.rounded_rectangle((0, 0, 959, 249), 40, fill=GRN)
            sd.polygon([(220, 125), (140, 60), (140, 95), (70, 95), (70, 155), (140, 155), (140, 190)], fill="white")
            sd.text((590, 85), "उस GDS साथी को भेजो", font=F(58), fill="white", anchor="mm")
            sd.text((590, 168), "जो ये गलती करता है!", font=F(58), fill=(255, 235, 120), anchor="mm")
            paste(cv, sh, 540, 780, k * (1.0 + 0.025 * math.sin(t * 6)))
        if t > 0.9:
            a = ease((t - 0.9) / 0.3)
            y = int(980 + (1 - a) * 60)
            d.rounded_rectangle((60, y, 1020, y + 200), 40, fill=(255, 255, 255), outline=GOLD, width=8)
            d.text((540, y + 65), f"कमेंट करो:  {M.MOCK_KEYWORD}", font=F(70), fill=RED, anchor="mm")
            d.text((540, y + 150), "FREE मॉक टेस्ट — असली परीक्षा जैसे सवाल", font=F(42), fill=NAVY, anchor="mm")
        if t > 1.3:
            d.rounded_rectangle((90, 1250, 760, 1350), 50, fill=RED)
            d.text((425, 1300), "+ FOLLOW  @postal_wala", font=F(48), fill="white", anchor="mm")
            stroke(d, (425, 1440), "Clause-wise पूरा PO Guide", F(50), (255, 214, 40), 5)
            stroke(d, (425, 1520), "कोई नियम नहीं छूटेगा!", F(50), (255, 255, 255), 5)
            b = char_file("bhaiya", "shabaash")
            if b:
                paste(cv, cutout(b, 560), 880, int(1640 + 10 * math.sin(t * 5)), back((t - 1.3) / 0.35))
        return cv

    def sc_kathin(self, sc, t):
        cv = bg()
        self.strip(cv, "शुरू")
        d = ImageDraw.Draw(cv)
        d.rounded_rectangle((60, 230, 1020, 770), 30, fill=(235, 235, 238))
        d.rounded_rectangle((90, 200, 560, 270), 35, fill=(120, 120, 130))
        d.text((325, 235), "किताब की भाषा", font=F(40), fill="white", anchor="mm")
        f, s_, ls = M.fit_lines_f(self.guide_en, 900, 4, 44, 32, FR) if hasattr(M, "fit_lines_f") else (FR(40), 40, [])
        for i, ln in enumerate(ls[:4]):
            d.text((100, 330 + i * int(s_ * 1.5)), " ".join(ln), font=f, fill=(110, 110, 120), anchor="lm")
        d.text((540, 700), "कठिन • लंबा • अंग्रेज़ी", font=F(48), fill=(170, 60, 60), anchor="mm")
        if t > 0.5:
            a = ease((t - 0.5) / 0.3)
            d.line((90, 740, 90 + 900 * a, 290), fill=RED, width=12)
        if t > 0.9:
            a = ease((t - 0.9) / 0.35)
            y0 = int(870 + (1 - a) * 120)
            d.rounded_rectangle((60, y0, 1020, y0 + 620), 30, fill=(255, 255, 255), outline=GRN, width=8)
            d.rounded_rectangle((90, y0 - 30, 640, y0 + 40), 35, fill=GRN)
            d.text((365, y0 + 5), "Postal Wala की भाषा", font=F(40), fill="white", anchor="mm")
            d.text((540, y0 + 140), "आसान हिंदी", font=F(76), fill=INK, anchor="mm")
            d.text((540, y0 + 250), f"{len(self.story) + 1} चित्र • 1 ट्रिक" if self.trick else
                   f"{len(self.story) + 1} चित्र • छोटे टुकड़े", font=F(80), fill=GRN, anchor="mm")
            d.text((540, y0 + 380), "0 कन्फ्यूज़न • पक्का याद", font=F(56), fill=(200, 120, 0), anchor="mm")
            d.text((540, y0 + 500), "चलो चित्रों में समझते हैं", font=FR(46), fill=(90, 100, 120), anchor="mm")
        return cv

    def sc_raasta(self, sc, t):
        cv = bg()
        self.strip(cv, "शुरू")
        d = ImageDraw.Draw(cv)
        stroke(d, (540, 260), "सिलेबस के हिसाब से,", F(76), (255, 255, 255))
        stroke(d, (540, 360), "Clause-wise पूरा PO Guide", F(76), (255, 214, 40))
        pos, tot = self.syl
        cols = 12
        rows = math.ceil(tot / cols)
        gy = min(92, int(560 / max(1, rows)))
        r, gx, x0, y0 = min(26, gy // 2 - 6), 78, 112, 480
        shown = int(tot * ease(t / 1.0))
        for i in range(tot):
            cx, cy = x0 + (i % cols) * gx, y0 + (i // cols) * gy
            col = (60, 70, 100) if i >= shown else (GRN if i < pos - 1 else (GOLD if i == pos - 1 else (90, 100, 135)))
            rr = r + (8 if i == pos - 1 and t > 1.0 else 0)
            d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=col)
            if i == pos - 1 and t > 1.0:
                d.text((cx, cy), str(self.cno), font=F(30), fill=NAVY, anchor="mm")
        if t > 1.0:
            cx, cy = x0 + ((pos - 1) % cols) * gx, y0 + ((pos - 1) // cols) * gy
            cx = min(max(cx, 110), W - 110)
            d.rounded_rectangle((cx - 95, cy - 108, cx + 95, cy - 50), 28, fill=GOLD)
            d.text((cx, cy - 79), "आज यहाँ", font=F(34), fill=NAVY, anchor="mm")
        yb = y0 + rows * gy + 20
        d.text((540, yb), f"हरा = हो चुका  •  {tot} Clause, एक-एक करके", font=FR(40), fill=(210, 220, 240), anchor="mm")
        if t > 1.3:
            a = ease((t - 1.3) / 0.3)
            y = int(yb + 80 + (1 - a) * 60)
            d.rounded_rectangle((60, y, 1020, y + 130), 34, fill=(255, 255, 255))
            d.text((540, y + 65), "कोई नियम नहीं छूटेगा!", font=F(64), fill=RED, anchor="mm")
            d.text((540, y + 210), SYL_LINE, font=F(42), fill=(255, 214, 40), anchor="mm")
        return cv

    def sc_story(self, sc, t, i):
        cv = super().sc_story(sc, t, i)
        self.strip(cv, f"टुकड़ा {i + 1}/{self.piece_n}", cover=196)      # purani POV line dhak ke neeche chhoti
        stroke(ImageDraw.Draw(cv), (W / 2, 236), N.POV_LINE, F(50), (255, 255, 255), 6)
        return cv

    def sc_trick(self, sc, t):
        cv = N.blurred_bg(self.ans_pn, dark=0.62)
        self.strip(cv, "ट्रिक")
        d = ImageDraw.Draw(cv)
        paste(cv, N.pill("याद रखने की ट्रिक", 52, NAVY, GOLD), 540, 300, back(t / 0.3))
        thumb = N.panel_full(self.ans_pn, 0.6, 1.0, 0.0, 0.0, 0.0).convert("RGB").crop((140, 420, 940, 1220))
        thumb = thumb.resize((420, 420))
        m = Image.new("L", thumb.size, 0)
        ImageDraw.Draw(m).ellipse((0, 0, 419, 419), fill=255)
        ring = Image.new("RGBA", (444, 444), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((0, 0, 443, 443), fill=GOLD)
        k = back((t - 0.15) / 0.35)
        if k > 0.02:
            tc = Image.new("RGBA", (444, 444), (0, 0, 0, 0))
            tc.alpha_composite(ring)
            tc.paste(thumb, (12, 12), m)
            paste(cv, tc, 540, 640, k)
        txt = self.trick["text"]
        keys = [k_ for k_ in self.trick.get("key") or [] if k_]
        f, s_, ls = M.fit_lines(txt, 960, 3, 72, 48)
        y = 960
        p = (t - sc["lead"]) / max(0.3, sc["vd"])
        nwords = sum(len(l) for l in ls)
        shown = int(nwords * min(1.0, max(0.0, p) * 1.1)) + 1
        cnt = 0
        for ln in ls:
            wsz = [f.getlength(w_) for w_ in ln]
            sp = f.getlength(" ")
            x = W / 2 - (sum(wsz) + sp * (len(ln) - 1)) / 2
            for w_, wz in zip(ln, wsz):
                cnt += 1
                hot = any(k_ in w_ or w_ in k_ for k_ in keys)
                col = (255, 214, 40) if hot else (255, 255, 255)
                if cnt > shown:
                    col = (120, 125, 140)
                d.text((x, y), w_, font=f, fill=col, anchor="lm", stroke_width=6, stroke_fill=(0, 0, 0))
                x += wz + sp
            y += int(s_ * 1.3)
        if t > sc["lead"] + sc["vd"] * 0.8:
            d.rounded_rectangle((120, y + 40, 960, y + 160), 40, fill=(255, 255, 255))
            d.text((540, y + 100), "1 लाइन = पूरा नियम याद", font=F(54), fill=RED, anchor="mm")
        return cv

    def sc_paper_ans(self, sc, t):
        cv = bg()
        self.strip(cv, "जवाब")
        d = ImageDraw.Draw(cv)
        stroke(d, (540, 270), "अब पेपर का सवाल", F(84), (255, 255, 255))
        stroke(d, (540, 375), "चुटकी में हल!", F(96), (255, 214, 40), 8)
        card = scan_card(self.scan, 1.0, (t - 0.3) / 0.5)
        cv.alpha_composite(card, (60, 900 - card.height // 2))
        if t > 0.9:
            paste(cv, M.check_sprite(150), 900, 1180, back((t - 0.9) / 0.3))
            stroke(d, (540, 1330), f"सही जवाब: {self.scan['letter']}", F(90), (120, 255, 150), 7)
        return cv

    def sc_end(self, sc, t):
        cv = bg()
        d = ImageDraw.Draw(cv)
        try:
            bh = Image.open(os.path.join("clause_plans", "characters", "bhaiya_shabaash.jpg")).convert("RGBA")
            bh.thumbnail((380, 380))
            m = Image.new("L", bh.size, 0)
            ImageDraw.Draw(m).ellipse((0, 0, bh.width - 1, bh.height - 1), fill=255)
            ring = Image.new("RGBA", (bh.width + 20, bh.height + 20), (0, 0, 0, 0))
            ImageDraw.Draw(ring).ellipse((0, 0, ring.width - 1, ring.height - 1), fill=GOLD)
            cv.alpha_composite(ring, (540 - ring.width // 2, 110))
            cv.paste(bh, (540 - bh.width // 2, 120), m)
        except Exception:
            pass
        d.rounded_rectangle((90, 530, 990, 680), 40, fill=GOLD)
        d.text((540, 580), "Postal Wala की गारंटी", font=F(56), fill=NAVY, anchor="mm")
        d.text((540, 645), "अब ये नियम कभी नहीं भूलोगे!", font=F(46), fill=RED, anchor="mm")
        stroke(d, (540, 770), "सारी रीलें देखो + फॉलो करो", F(62), (255, 255, 255))
        stroke(d, (540, 865), "= पूरी तैयारी, बिल्कुल FREE", F(68), (255, 214, 40))
        if t > 0.5:
            a = ease((t - 0.5) / 0.3)
            y = int(980 + (1 - a) * 60)
            d.rounded_rectangle((60, y, 1020, y + 240), 40, fill=(255, 255, 255), outline=GOLD, width=8)
            d.text((540, y + 70), f"कमेंट करो:  {M.MOCK_KEYWORD}", font=F(76), fill=RED, anchor="mm")
            d.text((540, y + 170), "FREE मॉक टेस्ट — असली परीक्षा जैसे सवाल", font=F(44), fill=NAVY, anchor="mm")
        if t > 0.9:
            d.rounded_rectangle((200, 1290, 880, 1390), 50, fill=GRN)
            d.text((540, 1340), "+ FOLLOW  @postal_wala", font=F(50), fill="white", anchor="mm")
            d.text((540, 1460), "SAVE करो  •  साथी को भेजो", font=F(46), fill=(230, 235, 250), anchor="mm")
        if V2:      # v24: raasta scene ki baat yahan (beech se hata)
            stroke(d, (540, 1600), "Clause-wise पूरा PO Guide", F(54), (255, 214, 40), 5)
            stroke(d, (540, 1690), "कोई नियम नहीं छूटेगा!", F(54), (255, 255, 255), 5)
        return cv

    def render(self, tl, si, t):
        sc = tl[si]
        n = sc["name"]
        if n == "ruko":
            return self.sc_sawal(sc, t)
        if n == "end" and V2 and V2_DRAMA:
            return self.sc_end2(sc, t)
        fn = {"paper": self.sc_paper, "guide": self.sc_guide, "guide2": self.sc_guide2, "galti": self.sc_galti,
              "kathin": self.sc_kathin, "raasta": self.sc_raasta,
              "ans": self.sc_ans, "trick": self.sc_trick, "pans": self.sc_paper_ans, "end": self.sc_end}.get(n)
        if fn:
            return fn(sc, t)
        return self.sc_story(sc, t, int(n[1:]))


THUMB_POINTS = [("चित्र", "पूरा वीडियो चित्रों से — बहुत आसानी से"),
                ("सिलेबस", "Clause-wise — कोई भी टॉपिक नहीं छूटेगा"),
                ("पेपर", "पेपर के 50 में से 30 सवाल इसी PO Guide से"),   # DoP syllabus 2019 (SYL_LINE) - sach
                ("FREE", "सब कुछ FREE  +  साथ में FREE नोट्स")]


def make_thumb(data, pn, scan, path):
    """v24.2 (user): har series reel ka cover. Upar Clause/Part -> kis paper/saal me aaya -> chitra ->
    Postal Wala ke vaade. Sab zaroori cheezein beech ke 1080x1440 (profile grid 3:4) me."""
    cv = N.blurred_bg(pn, dark=0.72).convert("RGBA")
    d = ImageDraw.Draw(cv)
    d.rectangle((0, 0, W, 250), fill=(8, 12, 30))
    d.rectangle((0, H - 250, W, H), fill=(8, 12, 30))
    # 0) sabse upar: Postal Wala + kiske liye (user)
    d.rounded_rectangle((40, 255, 1040, 355), 24, fill=RED)
    d.text((540, 305), "POSTAL WALA  •  GDS से MTS / Postman / PA", font=F(43), fill="white", anchor="mm")
    # 1) Clause + Part
    tp = data.get("total_parts")
    txt = f"Clause {data.get('clause_no')}  •  Part {data.get('part_no')}" + (f"/{tp}" if tp else "")
    d.rounded_rectangle((90, 375, 990, 485), 55, fill=GOLD)
    d.text((540, 430), txt, font=F(70), fill=NAVY, anchor="mm")
    # 2) chitra + 3) paper/saal mohar
    try:
        im = N.panel_full(pn, 0.6, 1.0, 0.0, 0.0, 0.0).convert("RGB").crop((40, 380, 1040, 960)).resize((900, 522))
        frame = Image.new("RGBA", (924, 546), GOLD)
        frame.paste(im, (12, 12))
        cv.alpha_composite(frame, (78, 505))
    except Exception as exc:
        print("  Cover chitra nahi laga:", str(exc)[:100])
    if scan and scan.get("clause_level"):        # sawal is CLAUSE ka hai, is part ke niyam ka nahi - waisa hi likho
        st = stamp_img(f"इसी Clause से {scan['label'][0]} में सवाल", f"प्रश्न {scan['label'][1]}  •  असली पेपर")
    elif scan:
        st = stamp_img(f"{scan['label'][0]} के पेपर में आया", f"प्रश्न {scan['label'][1]}  •  असली पेपर")
    else:
        st = stamp_img("परीक्षा का पक्का नियम", "PO Guide Part I")
    paste(cv, st, 540, 1065, min(1.0, 980 / max(1, st.width)))
    # 4) vaade
    y = 1200
    for tag, line in THUMB_POINTS:
        d.rounded_rectangle((70, y - 52, 1010, y + 52), 26, fill=(255, 255, 255, 240))
        d.rounded_rectangle((70, y - 52, 270, y + 52), 26, fill=(RED if tag == "FREE" else GRN))
        d.text((170, y), tag, font=F(44), fill="white", anchor="mm")
        f, s_, ls = M.fit_lines(line, 700, 1, 44, 30)
        d.text((290, y), " ".join(ls[0]), font=f, fill=INK, anchor="lm")
        y += 122
    d.text((540, 1730), "@postal_wala", font=F(44), fill=(230, 235, 250), anchor="mm")
    cv.convert("RGB").save(path, quality=92)
    print("Cover (thumbnail):", path)
    return path


def build_audio(tl, total, path):
    n = int(total * M.SR) + M.SR
    vt = np.zeros(n, dtype=np.float32)
    for sc in tl:
        M.add_at(vt, sc["audio"], sc["start"] + sc["lead"])
    win = int(0.15 * M.SR)
    env = np.convolve(np.abs(vt), np.ones(win, dtype=np.float32) / win, mode="same")
    duck = 1.0 - np.clip(env * 6, 0, 0.65)
    buf = np.zeros(n, dtype=np.float32)
    bed = M.music_bed(n / M.SR)
    m = min(len(bed), n)
    buf[:m] += bed[:m] * duck[:m] * 0.8
    M.add_at(buf, M.sfx_thud(0.7), 0.0)                  # Postal Wala dhun: mohar 'thak' + ghanti
    M.add_at(buf, M.sfx_ding(0.4), 0.22)
    for i, sc in enumerate(tl):
        s, nm = sc["start"], sc["name"]
        if i > 0:
            M.add_at(buf, M.sfx_whoosh(0.3, 0.3), max(0.0, s - 0.12), 0.9)
        if nm in ("paper", "guide"):
            M.add_at(buf, M.sfx_thud(0.6), s + 0.75)
        elif nm == "galti":                               # v24.4 drama ki awaazein
            M.add_at(buf, M.sfx_pop(0.45), s + 0.05)
            M.add_at(buf, M.sfx_whoosh(0.35, 0.55), s + 0.5, 1.0)
            M.add_at(buf, M.sfx_whoosh(0.35, 0.55), s + 0.95, 1.0)
            M.add_at(buf, M.sfx_thud(0.75), s + 1.5)
            M.add_at(buf, M.sfx_buzz(0.35), s + 1.58)
        elif nm == "ruko" and V2:
            M.add_at(buf, M.sfx_thud(0.55), s + 0.05)
        elif nm == "ans":
            M.add_at(buf, M.sfx_ding(0.5), s + 0.3)
        elif nm == "pans":
            M.add_at(buf, M.sfx_ding(0.45), s + 0.9)
        elif nm == "trick":
            M.add_at(buf, M.sfx_pop(0.4), s + 0.1)
        elif nm == "end":
            M.add_at(buf, M.sfx_pop(0.4), s + 0.5)
        if nm.startswith("s") and nm[1:].isdigit() and sc.get("wrong"):
            M.add_at(buf, M.sfx_buzz(0.33), s + sc["lead"] + sc["vd"] - 0.15)
    out = buf + vt
    peak = float(np.max(np.abs(out))) or 1.0
    if peak > 0.98:
        out = out * (0.98 / peak)
    import wave
    with wave.open(path, "wb") as w_:
        w_.setnchannels(1)
        w_.setsampwidth(2)
        w_.setframerate(M.SR)
        w_.writeframes((np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes())


def build(data, out, plan=None, part=None):
    if not N.usable(data):
        raise RuntimeError("bharosa format ke liye photo-chitra nahi")
    M.resolve_font()
    panels = data["chitra"]["panels"]
    story, ans_pn = N.story_split(panels)
    pyq, rel = (None, False)
    if plan is not None and part is not None:
        try:
            pyq, rel = N.pyq_for(plan, part, data)
        except Exception as exc:
            print("  PYQ nahi juda:", str(exc)[:140])
    scan = paper_scan(pyq) if (pyq and rel) else None
    if not scan and plan is not None:                 # niyam ka exact nahi -> isi Clause ka asli paper sawal
        cp = clause_pyq(plan, data.get("part_no"))
        if cp:
            scan = paper_scan(dict(cp, clause_level=True))
    print("  Saboot:", f"asli paper scan {scan['label']}" if scan else "PO Guide panna + syllabus line")
    proof = None
    need_proof = (not scan or scan.get("clause_level")) if V2 else not scan   # v24: exact scan nahi -> PO Guide line jawab ke baad
    if need_proof and plan is not None and part is not None:
        a = N.proof_assets(plan, part, data)
        if a:
            proof = N.Proof(a, data.get("clause_no"), int(data.get("episode") or 0), badge=None)
    gv = N.guide_line(plan, part, data) if (plan is not None and part is not None) else {}
    guide_en = (gv or {}).get("sentence") or (data.get("en") or {}).get("fact") or ""
    trick = ensure_trick(part, data) if part is not None else None
    syl = data.get("syllabus") if data.get("syllabus") and data["syllabus"][0] else None
    ep = int(data.get("episode") or 0)
    specs = []
    if V2:
        pool = (V2_OPEN_CLAUSE if scan.get("clause_level") else V2_OPEN_EXACT) if scan else V2_OPEN_GUIDE
        op = pool[ep % len(pool)].format(L=scan['label'][0] if scan else "")
        print("  v24 sawal-pehle | hook awaaz:", op)
        specs.append({"name": "ruko", "segs": [("r", op)]})          # sawal screen par, awaaz me hook
        wrong_i = max([i for i, pn in enumerate(story) if pn.get("mark") == "wrong"], default=None)
        for i, pn in enumerate(story):
            specs.append({"name": f"s{i}", "segs": [(f"c{i}", pn.get("text") or "")]})
            if V2_DRAMA and i == wrong_i:
                specs.append({"name": "galti", "pn": pn, "segs": [("x", galti_line(part, data, pn))]})
        specs.append({"name": "ans", "segs": [("a", ans_pn.get("text") or f"सही जवाब है, {data['correct_text']}!")]})
        if proof is not None:
            specs.append({"name": "guide2", "segs": [("g", V2_GUIDE_VOICE)]})
        if scan and not scan.get("clause_level"):
            specs.append({"name": "pans", "segs": [("q", f"इसलिए पेपर का सही जवाब, {LETTER_HI[scan['letter']]}!")]})
        if trick:
            specs.append({"name": "trick", "segs": [("t", "याद रखने की ट्रिक! " + trick["text"])]})
        specs.append({"name": "end", "segs": [("e", V2_END_VOICE)]})
    else:                                            # v23 (purana) kram
        if scan:
            L0 = scan['label'][0]
            pool = OPEN_CLAUSE if scan.get("clause_level") else OPEN_EXACT
            fid, line = pool[ep % len(pool)]
            specs.append({"name": "paper", "segs": [("p", line.format(L=L0))]})
        else:
            fid, line = OPEN_GUIDE[ep % len(OPEN_GUIDE)]
            specs.append({"name": "guide", "segs": [("p", line)]})
        print(f"  Hook formula #{fid}: {specs[-1]['segs'][0][1]}")
        specs.append({"name": "ruko", "segs": [("r", "रुको! पहले सोचो, " + N.ruko_q(data))]})
        if guide_en:
            specs.append({"name": "kathin", "segs": [("k", "किताब कठिन है, हम चित्रों से आसान बनाते हैं!")]})
        if syl:
            specs.append({"name": "raasta", "segs": [("r", RAASTA_VOICES[ep % len(RAASTA_VOICES)])]})
        for i, pn in enumerate(story):
            specs.append({"name": f"s{i}", "segs": [(f"c{i}", pn.get("text") or "")]})
        specs.append({"name": "ans", "segs": [("a", ans_pn.get("text") or f"सही जवाब है, {data['correct_text']}!")]})
        if trick:
            specs.append({"name": "trick", "segs": [("t", "याद रखने की ट्रिक! " + trick["text"])]})
        if scan and not scan.get("clause_level"):
            specs.append({"name": "pans", "segs": [("q", f"इसलिए पेपर का सही जवाब, {LETTER_HI[scan['letter']]}!")]})
        specs.append({"name": "end", "segs": [("e", END_VOICE)]})
    print(f"BHAROSA FORMAT ({VERSION.split(':')[0]}): awaaz ({len(specs)} tukde)...")
    voices = M.make_voices(specs)
    mins = {"paper": 2.8, "guide": 2.8, "guide2": 1.5, "galti": 2.6, "kathin": 2.0, "raasta": 2.2, "trick": 2.4, "pans": 1.8, "end": 2.8, "ans": 1.6}
    tl, cur = [], 0.0
    for sp, v in zip(specs, voices):
        a = clean_voice(v[0])
        vd = len(a) / M.SR
        nm = sp["name"]
        lead = 0.2 if nm in ("ans", "trick") else 0.08
        dur = max(mins.get(nm, 1.6), lead + vd + 0.22)
        sc = {"name": nm, "start": cur, "dur": dur, "lead": lead, "vd": vd, "audio": a,
              "text": " ".join(t for _, t in sp["segs"])}
        if nm == "ruko":
            cd0 = max(0.9, lead + vd - 0.9)
            sc["cd0"] = cd0
            sc["dur"] = dur = max(cd0 + 3 * N.CD_STEP + 0.1, lead + vd + 0.2)
            if V2:                                  # sawal padhne ka samay (awaaz sawal nahi padhti)
                nq = len((data.get("question") or "").split())
                cd0 = max(cd0, min(4.0, 0.28 * nq))
                sc["cd0"] = cd0
                sc["dur"] = dur = max(dur, cd0 + 3 * N.CD_STEP + 0.1)
        if nm.startswith("s") and nm[1:].isdigit():
            sc["wrong"] = story[int(nm[1:])].get("mark") == "wrong"
        if nm == "galti":
            sc["pn"] = sp["pn"]
            sc["lead"] = 1.6                                 # pehle lifaafa ka drama, fir line
            sc["dur"] = dur = max(2.6, 1.6 + vd + 0.25)
        tl.append(sc)
        cur += dur
    total = cur
    print("  BHAROSA TIMELINE:", " | ".join(f"{s['name']} {s['start']:.1f}+{s['dur']:.1f}" for s in tl),
          f"= {total:.1f}s")
    reel = Bharosa(data, story, ans_pn, proof, scan, trick, syl, guide_en)
    apath = out.replace(".mp4", "_bharosa_audio.wav")
    build_audio(tl, total, apath)
    n_frames = int(math.ceil(total * FPS))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", apath, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium",
           "-crf", str(M.VIDEO_CRF), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    prev = {}
    try:
        for fi in range(n_frames):
            gt = fi / FPS
            fr, si = reel.frame(tl, gt)
            tt = gt - tl[si]["start"]
            if si > 0 and tt < N.TRANS:
                if si not in prev:
                    prev = {si: reel.render(tl, si - 1, tl[si - 1]["dur"] - 1.0 / FPS)}
                k = M.ease_in_out(tt / N.TRANS)
                base = Image.new("RGBA", (W, H), (0, 0, 0, 255))
                base.alpha_composite(prev[si], (int(-k * W * 0.35), 0))
                cur_ = fr.copy()
                cur_.putalpha(int(255 * min(1.0, k * 1.6)))
                base.alpha_composite(cur_, (int((1 - k) * W * 0.5), 0))
                fr = base
            proc.stdin.write(fr.convert("RGB").tobytes())
            if fi % 150 == 0:
                print(f"  frame {fi}/{n_frames}")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    ret = proc.wait()
    if os.path.exists(apath):
        os.remove(apath)
    if ret != 0:
        raise RuntimeError("ffmpeg (bharosa) fail")
    data["bharosa"] = {"scan": bool(scan), "trick": (trick or {}).get("text", ""),
                       "pyq": ({"q": pyq["q"], "ans": pyq["ans"], "exams": pyq.get("exams") or []} if (pyq and rel) else None)}
    print(f"COMPLETE (bharosa format): {out} ({total:.2f}s)")
    try:                                     # cover fail ho to bhi reel nahi rukti
        make_thumb(data, story[0], scan, out.replace(".mp4", "_cover.jpg"))
    except Exception as exc:
        print("  Cover nahi bana (reel theek hai):", str(exc)[:160])
    return total
