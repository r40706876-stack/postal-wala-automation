"""
PYQ TEST REEL  (subah 9 baje wali reel)  -  v2: safed premium, 10-12 second
=========================================================================
Ek reel = pichhle saal ke ASLI paper ke 3 sawal, premium test-app jaisa (safed kaagaz, navy + sunehra):
  frame 0 se hi सवाल 1 (alag intro nahi - skip yahin hota tha) -> 3 x [sawal + 4 option + patli timer patti +
  "समय समाप्त"] -> CTA (1-? 2-? 3-? + "सही जवाब पिन कमेंट में").
Har sawal ka samay uski lambai se (padhne jitna), poori reel ~10-12 second.
JAWAB REEL ME KABHI NAHI - sirf PIN comment me (caption file ke neeche taiyar).
Upar hamesha: "जवाब: पिन कमेंट में  •  शाम 5 बजे: चित्रों से आसान नियम".

Sawal sirf pyq_papers/pyq_bank.json se (answer key + PO Guide se milaan karke chune hue).
Bank ke saare set khatam -> reel nahi banti (bina-jaanch sawal se behtar), log me sandesh.

Chalana:  python pyq_reel.py             (din me ek; dobara chalao to skip)
          DRY_RUN=1 python pyq_reel.py   (bina awaaz test, state nahi badalti)
          python pyq_reel.py --force     (aaj ki ban chuki ho tab bhi)
"""
import csv
import datetime
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import main as M

BANK = os.path.join("pyq_papers", "pyq_bank.json")
OUT_DIR = os.path.join(M.OUTPUT_DIR, "pyq")
STATE = os.path.join(OUT_DIR, "state.json")
EXP_LOG = os.path.join(OUT_DIR, "experiments.csv")
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
W, H = M.W, M.H

TARGET = 11.5          # poori reel ka lakshya (sec)
Q_MIN, Q_MAX = 3.0, 3.8
END_DUR = 1.7
TIMEUP = 0.32          # "समय समाप्त" ka pal (sawal ke samay ke andar)
TRANS = 0.18

# ---- safed premium rang ----
PAPER = (250, 249, 245)
PAPER2 = (241, 238, 230)
NAVY = (16, 28, 64)
NAVY2 = (40, 56, 104)
GOLD = (212, 160, 23)
GOLD_L = (247, 222, 150)
GREYT = (98, 108, 128)
LINEC = (222, 224, 232)
RED = (214, 48, 49)
TOP_LINE = "जवाब: पिन कमेंट में   •   शाम 5 बजे: चित्रों से आसान नियम"

HOOK_VOICES = [
    {"id": "A", "voice": "तीन सवाल, दस सेकंड!"},
    {"id": "B", "voice": "असली पेपर के तीन सवाल!"},
]
END_VOICE = "जवाब कमेंट करो!"


# ------------------------------------------------------------------ data

def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"done_sets": [], "made": {}, "n": 0}


def save_state(st):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def load_bank():
    with open(BANK, encoding="utf-8") as f:
        b = json.load(f)
    items = {x["id"]: x for x in b["items"]}
    for x in items.values():
        assert x["ans"] in "ABCD" and len(x["opts"]) == 4, x["id"]
    return items, b["sets"]


def pick_set(st):
    items, sets = load_bank()
    done = set(st.get("done_sets") or [])
    for s in sets:
        k = "|".join(s)
        if k not in done and all(i in items for i in s):
            return k, [items[i] for i in s]
    return None, []


def exams_line(ex, maxn=2):
    if not ex:
        return ""
    head = " · ".join(ex[:maxn])
    return head + (f"  +{len(ex) - maxn}" if len(ex) > maxn else "")


def ans_text(it):
    return it["opts"]["ABCD".index(it["ans"])]


# ------------------------------------------------------------------ timing / voice

def q_seconds(it):
    """Padhne jitna: sawal + options ke shabd se (3.0 - 3.8 sec)."""
    words = len(it["q"].split()) + sum(len(o.split()) for o in it["opts"])
    return max(Q_MIN, min(Q_MAX, 1.6 + 0.085 * words))


def timeline(items):
    durs = [q_seconds(it) for it in items]
    s = sum(durs) + END_DUR
    if s > TARGET + 0.6:                                  # lambi ho rahi -> sab barabar chhote
        k = (TARGET + 0.6 - END_DUR) / sum(durs)
        durs = [max(Q_MIN * 0.9, d * k) for d in durs]
    tl, t = [], 0.0
    for i, d in enumerate(durs):
        tl.append({"name": f"q{i}", "start": t, "dur": d})
        t += d
    tl.append({"name": "end", "start": t, "dur": END_DUR})
    return tl, t + END_DUR


def get_voices(specs):
    try:
        return M.make_voices(specs)
    except M.VoiceUnavailable:
        print(f"PYQ: Gemini awaaz nahi mili -> edge-tts ({M.VOICE_NAME})")
        M._VOICE_FLAGS["allow_edge"] = True
        return M.make_voices(specs)


def build_audio(tl, total, hook_v, end_v, path):
    n = int(total * M.SR) + M.SR // 2
    vt = np.zeros(n, dtype=np.float32)
    if hook_v is not None:
        M.add_at(vt, hook_v, 0.05)
    if end_v is not None:
        M.add_at(vt, end_v, tl[-1]["start"] + 0.15)
    win = int(0.15 * M.SR)
    env = np.convolve(np.abs(vt), np.ones(win, dtype=np.float32) / win, mode="same")
    duck = 1.0 - np.clip(env * 6, 0, 0.6)
    buf = np.zeros(n, dtype=np.float32)
    bed = M.music_bed(n / M.SR)
    m = min(len(bed), n)
    buf[:m] += bed[:m] * duck[:m] * 0.85
    M.add_at(buf, M.sfx_thud(0.6), 0.0)
    for sc in tl:
        s = sc["start"]
        if sc["name"].startswith("q"):
            if s > 0:
                M.add_at(buf, M.sfx_whoosh(0.22, 0.28), max(0.0, s - 0.06))
            M.add_at(buf, M.sfx_pop(0.25), s + 0.12)
            tend = s + sc["dur"] - TIMEUP
            k = tend - 1.0
            while k < tend - 0.05:                         # aakhri second: tik-tik
                M.add_at(buf, M.sfx_tick(0.4), k)
                k += 0.25
            M.add_at(buf, M.sfx_thud(0.55), tend)
        else:
            M.add_at(buf, M.sfx_pop(0.45), s + 0.05)
            M.add_at(buf, M.sfx_ding(0.35), s + 0.45)
    buf += vt
    peak = float(np.max(np.abs(buf))) or 1.0
    buf = buf / max(1.0, peak / 0.95)
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", str(M.SR), "-ac", "1", "-i", "-", path],
                   input=pcm.tobytes(), check=True)


# ------------------------------------------------------------------ drawing

_C = {}


def paper_bg():
    """Safed premium kaagaz: halka garam gradient + baarik bindu-jaali."""
    if "bg" in _C:
        return _C["bg"]
    y = np.linspace(0, 1, H)[:, None, None]
    base = np.array(PAPER)[None, None, :] * (1 - y * 0.6) + np.array(PAPER2)[None, None, :] * (y * 0.6)
    base = np.repeat(base, W, axis=1)
    im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(im, "RGBA")
    for gx in range(30, W, 60):
        for gy in range(290, H, 60):
            d.ellipse((gx - 1.3, gy - 1.3, gx + 1.3, gy + 1.3), fill=(16, 28, 64, 18))
    _C["bg"] = im
    return im


def shadow_card(w, h, r=34, fill=(255, 255, 255), border=None, bw=2, sh=26, sh_a=38, accent=None):
    """Mulayam parchhai wala safed card (premium app jaisa)."""
    key = ("card", w, h, r, fill, border, bw, sh, sh_a, accent)
    if key in _C:
        return _C[key]
    pad = sh * 2
    im = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    s = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(s).rounded_rectangle((pad, pad + sh * 0.45, pad + w, pad + h + sh * 0.45), radius=r,
                                        fill=(16, 28, 64, sh_a))
    im = Image.alpha_composite(im, s.filter(ImageFilter.GaussianBlur(sh * 0.6)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((pad, pad, pad + w - 1, pad + h - 1), radius=r, fill=fill + (255,),
                        outline=(border + (255,)) if border else None, width=bw if border else 0)
    if accent:
        d.rounded_rectangle((pad, pad + 26, pad + 10, pad + h - 26), radius=5, fill=accent + (255,))
    _C[key] = im
    return im


def pill(text, size, fg, bg, outline=None, padx=26, pady=12, reg=False):
    key = ("pill", text, size, fg, bg, outline, reg, padx, pady)
    if key in _C:
        return _C[key]
    f = M.get_font_reg(size) if reg else M.get_font(size)
    tw = int(f.getlength(text))
    w, h = tw + padx * 2, int(size * 1.25) + pady * 2
    im = Image.new("RGBA", (w + 4, h + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((2, 2, w + 1, h + 1), radius=h // 2, fill=bg + (255,),
                        outline=(outline + (255,)) if outline else None, width=3 if outline else 0)
    d.text((w / 2 + 2, h / 2 + 2), text, font=f, fill=fg, anchor="mm")
    _C[key] = im
    return im


# ---------------- POSTAL WALA ki pehchaan: dak-ticket logo, airmail dhaari, daak-muhar, Bhaiya ----------------
POST_RED = (200, 30, 45)
AIR_BLUE = (24, 54, 140)


def stamp_logo(size=104):
    """Dak-ticket jaisa logo: kinaare kate (perforation), andar Bhaiya ka chehra (na ho to PW)."""
    key = ("stamp", size)
    if key in _C:
        return _C[key]
    S = size + 24
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((4, 4, S - 5, S - 5), fill=(255, 255, 255, 255))
    step = 13
    for x in range(4, S - 4, step):                       # perforation: kinaaron pe chhote gol kataav
        for y_ in (4, S - 5):
            d.ellipse((x - 4, y_ - 4, x + 4, y_ + 4), fill=(0, 0, 0, 0))
    for y in range(4, S - 4, step):
        for x_ in (4, S - 5):
            d.ellipse((x_ - 4, y - 4, x_ + 4, y + 4), fill=(0, 0, 0, 0))
    d.rectangle((14, 14, S - 15, S - 15), fill=POST_RED + (255,))
    inner = S - 36
    face = None
    try:
        if M.host_ready():
            f_ = Image.open(M.host_img(None)).convert("RGB")
            w_, h_ = f_.size
            side = int(min(w_, h_) * 0.55)
            x0, y0 = (w_ - side) // 2, int(h_ * 0.04)
            face = f_.crop((x0, y0, x0 + side, y0 + side)).resize((inner, inner), Image.LANCZOS).convert("RGBA")
    except Exception:
        face = None
    if face is not None:
        im.alpha_composite(face, (18, 18))
        d.rectangle((18, S - 40, S - 19, S - 19), fill=POST_RED + (230,))
        d.text((S / 2, S - 30), "POSTAL WALA", font=M.get_font(13), fill=(255, 255, 255), anchor="mm")
    else:
        d.text((S / 2, S / 2), "PW", font=M.get_font(44), fill=(255, 255, 255), anchor="mm")
    _C[key] = im
    return im


def airmail_stripe(cv, y=0, h=12):
    """Airmail lifaafe jaisi laal-neeli tirchhi dhaariyaan."""
    d = ImageDraw.Draw(cv)
    w_ = 34
    for k, x in enumerate(range(-h * 2, W + w_, w_)):
        col = POST_RED if k % 2 == 0 else AIR_BLUE
        d.polygon([(x, y + h), (x + w_ * 0.55, y), (x + w_ * 0.55 + w_ * 0.45, y), (x + w_ * 0.45, y + h)], fill=col)


def postmark(date_txt, size=210):
    """Gol daak-muhar: POSTAL WALA · PYQ + tareekh (asli dak ki tarah, halki syahi)."""
    key = ("pm", date_txt, size)
    if key in _C:
        return _C[key]
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ink = (40, 56, 120, 150)
    c = size / 2
    d.ellipse((6, 6, size - 6, size - 6), outline=ink, width=5)
    d.ellipse((30, 30, size - 30, size - 30), outline=ink, width=3)
    f = M.get_font(20)
    txt = "POSTAL WALA • PYQ • "
    r = c - 18
    for i, ch in enumerate(txt * 2):                    # gol ghoomta naam
        ang = -math.pi / 2 + 2 * math.pi * i / (len(txt) * 2)
        x, y = c + r * math.cos(ang), c + r * math.sin(ang)
        g = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
        ImageDraw.Draw(g).text((15, 15), ch, font=f, fill=ink, anchor="mm")
        g = g.rotate(-math.degrees(ang) - 90, resample=Image.BICUBIC)
        im.alpha_composite(g, (int(x - 15), int(y - 15)))
    d.text((c, c - 10), date_txt, font=M.get_font(30), fill=ink, anchor="mm")
    d.text((c, c + 24), "GDS → MTS", font=M.get_font(20), fill=ink, anchor="mm")
    for k in range(4):                                  # muhar ki lehron wali rekhayein
        yy = c - 30 + k * 20
        d.line((size - 4, yy, size + 200, yy), fill=ink, width=3)
    _C[key] = im
    return im


def bhaiya_says(cv, text, x, y, t, expr="sochta", instant=False):
    """Postal Wala Bhaiya ka chhota chehra + gubbara (har reel ki pehchaan)."""
    if not M.host_ready():
        return
    key = ("face", expr)
    if key not in _C:
        try:
            _C[key] = M._host_face(M.host_img(expr), 120)
        except Exception:
            _C[key] = M._host_face(M.host_img(None), 120)
    bob = 5 * math.sin(t * 5)
    M.place(cv, _C[key], x, y + bob)
    b = pill(text, 36, NAVY, (255, 255, 255), LINEC, padx=24, pady=12)
    k = 1.0 if instant else M.ease_out_back(M.clamp(t / 0.25))
    M.place(cv, b, x + 90 + b.width / 2, y - 30, scale=max(0.05, k))


def header(cv, k_cur, cur, n):
    """Brand patti + upar ki line + 3 khaanon ki progress (abhi wala bharta hua)."""
    d = ImageDraw.Draw(cv, "RGBA")
    d.rectangle((0, 0, W, 236), fill=(255, 255, 255, 255))
    d.line((0, 236, W, 236), fill=LINEC, width=2)
    airmail_stripe(cv, 0, 12)
    M.place(cv, stamp_logo(104), 104, 100, angle=-4)
    d.text((178, 78), "POSTAL WALA", font=M.get_font(44), fill=NAVY, anchor="lm")
    d.text((180, 124), "PYQ टेस्ट सीरीज़ · GDS → MTS / Postman", font=M.get_font_reg(30), fill=GREYT, anchor="lm")
    M.place(cv, pill("असली पेपर", 30, NAVY, GOLD_L, GOLD), W - 150, 92)
    f, s_, ls = M.fit_lines(TOP_LINE, 1000, 1, 36, 26)
    d.text((W / 2, 196), " ".join(ls[0]) if ls else TOP_LINE, font=f, fill=NAVY2, anchor="mm")
    x0, x1, y = 48, W - 48, 262
    gap = 14
    seg = (x1 - x0 - gap * (n - 1)) / n
    for i in range(n):
        a = x0 + i * (seg + gap)
        d.rounded_rectangle((a, y - 5, a + seg, y + 5), radius=5, fill=LINEC)
        k = 1.0 if i < cur else (k_cur if i == cur else 0.0)
        if k > 0:
            d.rounded_rectangle((a, y - 5, a + seg * min(1.0, k), y + 5), radius=5, fill=GOLD)


def opt_sprite(letter, text, dim):
    key = ("opt", letter, text, dim)
    if key in _C:
        return _C[key]
    w, h = 980, 156
    card = shadow_card(w, h, r=28, border=LINEC, bw=2, sh=14, sh_a=22).copy()
    pad = 28
    d = ImageDraw.Draw(card)
    cx, cy = pad + 66, pad + h / 2
    d.ellipse((cx - 36, cy - 36, cx + 36, cy + 36), fill=(NAVY if not dim else (180, 186, 200)))
    d.text((cx, cy), letter, font=M.get_font(40), fill=GOLD_L if not dim else (250, 250, 250), anchor="mm")
    f, s_, ls = M.fit_lines(text, w - 170, 2, 56, 34)
    step = int(s_ * 1.18)
    y0 = cy - (len(ls) - 1) * step / 2
    for k, ln in enumerate(ls):
        d.text((pad + 124, y0 + k * step), " ".join(ln), font=f, fill=NAVY if not dim else (160, 166, 180),
               anchor="lm")
    _C[key] = card
    return card


def q_card(it, i, n):
    key = ("q", it["id"], i)
    if key in _C:
        return _C[key]
    f, s_, ls = M.fit_lines(it["q"], 880, 4, 74, 46)
    step = int(s_ * 1.3)
    ex = it.get("exams") or []
    h = max(300, 130 + len(ls) * step + (70 if len(ex) >= 2 else 40))
    card = shadow_card(980, h, r=36, accent=GOLD).copy()
    pad = 52
    d = ImageDraw.Draw(card)
    qp = pill(f"प्रश्न {i + 1}/{n}", 32, (255, 255, 255), NAVY)
    card.alpha_composite(qp, (pad + 40, pad + 30))
    if ex:
        lbl = (f"{len(ex)} परीक्षाओं में पूछा गया" if len(ex) >= 2 else f"पूछा गया: {ex[0]}")
        ep = pill(lbl, 28, (120, 84, 0), (255, 246, 214), GOLD, padx=20, pady=10)
        card.alpha_composite(ep, (pad + 980 - ep.width - 34, pad + 32))
    y0 = pad + 130 + step / 2 - 10
    for k, ln in enumerate(ls):
        d.text((pad + 980 / 2 + 6, y0 + k * step), " ".join(ln), font=f, fill=NAVY, anchor="mm")
    if len(ex) >= 2:
        d.text((pad + 980 / 2, pad + h - 38), exams_line(ex, 3), font=M.get_font_reg(28), fill=GREYT, anchor="mm")
    _C[key] = card
    return card


def scene_q(data, i, t, sc):
    it = data["items"][i]
    n = len(data["items"])
    cv = paper_bg().copy()
    header(cv, M.clamp(t / sc["dur"]), i, n)
    first = (i == 0)
    tend = sc["dur"] - TIMEUP
    timeup = t >= tend
    # sawal card: pehle sawal pe frame 0 se poora (thumbnail jaisa), baaki pe halka upar khisak ke
    kq = 1.0 if first else M.ease_out_cubic(M.clamp(t / 0.22))
    card = q_card(it, i, n)
    cy = 330 + card.height / 2 - 30
    M.place(cv, card, W / 2, cy + 40 * (1 - kq), alpha=kq)
    pm = postmark(data.get("pm_date", ""))
    M.place(cv, pm, W - 92, cy + card.height / 2 - 52, scale=0.85, angle=-12, alpha=0.85 * kq)   # kone par, shabdon se door
    oy = cy + card.height / 2 + 40
    for j, (L, o) in enumerate(zip("ABCD", it["opts"])):
        # v20.3: pehle sawal pe bhi option ek-ek karke (0.1-0.5s) - frame 0 pe sawal, fir harkat (still screen = skip)
        kj = M.ease_out_cubic(M.clamp((t - 0.10 - 0.07 * j) / 0.22)) if first else \
            M.ease_out_cubic(M.clamp((t - 0.06 - 0.05 * j) / 0.2))
        M.place(cv, opt_sprite(L, o, timeup), W / 2 + 120 * (1 - kj), oy + 40 + j * 180, alpha=kj)
    ty = min(H - 230, oy + 40 + 3 * 180 + 170)                        # timer: patli patti jo khaali hoti hai
    d = ImageDraw.Draw(cv, "RGBA")
    left = max(0.0, tend - t)
    k = left / tend if tend > 0 else 0
    col = RED if left <= 1.0 else GOLD
    d.rounded_rectangle((90, ty - 9, W - 90, ty + 9), radius=9, fill=LINEC)
    if k > 0:
        d.rounded_rectangle((90, ty - 9, 90 + (W - 180) * k, ty + 9), radius=9, fill=col)
    if not timeup:
        M.place(cv, pill(f"{left:0.1f} s", 40, (255, 255, 255), col), W / 2 + 260, ty + 70)
        lines_ = ["सोचो, जवाब क्या है?", "ये कई बार आ चुका है!", "आखिरी सवाल!"]
        say = lines_[2] if i == n - 1 else (lines_[1] if len(it.get("exams") or []) >= 2 else lines_[0])
        bhaiya_says(cv, say, 140, ty + 90, t, "sochta" if left > 1.0 else "chauka", instant=first)
    else:
        k5 = M.ease_out_back(M.clamp((t - tend) / 0.14))
        M.place(cv, pill("समय समाप्त", 52, (255, 255, 255), RED), W / 2, ty + 70,
                scale=max(0.05, 1.35 - 0.35 * k5), angle=-4)
    return cv


def scene_end(data, t):
    n = len(data["items"])
    cv = paper_bg().copy()
    header(cv, 1.0, n, n)
    d = ImageDraw.Draw(cv, "RGBA")
    k = M.ease_out_back(M.clamp(t / 0.22))
    M.place(cv, shadow_card(980, 1080, r=40, accent=GOLD), W / 2, 940, alpha=M.clamp(t / 0.12))
    M.place(cv, pill("अपने जवाब कमेंट करो", 64, (255, 255, 255), NAVY), W / 2, 560, scale=max(0.05, k))
    for j in range(n):
        kj = M.ease_out_back(M.clamp((t - 0.12 - 0.08 * j) / 0.2))
        box = shadow_card(240, 150, r=28, border=GOLD, bw=4, sh=12, sh_a=22).copy()
        ImageDraw.Draw(box).text((box.width / 2, box.height / 2), f"{j + 1} - ?", font=M.get_font(62), fill=NAVY,
                                 anchor="mm")
        M.place(cv, box, W / 2 + (j - (n - 1) / 2) * 290, 790, scale=max(0.05, kj))
    d.text((W / 2, 930), "ऐसे लिखो:  1-B  2-A  3-D", font=M.get_font_reg(42), fill=GREYT, anchor="mm")
    k2 = M.ease_out_back(M.clamp((t - 0.35) / 0.2))
    M.place(cv, pill("सही जवाब: पिन कमेंट में", 54, (255, 255, 255), RED), W / 2, 1080, scale=max(0.05, k2))
    lay = Image.new("RGBA", (W, 200), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    ld.text((W / 2, 50), "SAVE करो · परीक्षा से पहले दोहराना", font=M.get_font(46), fill=NAVY, anchor="mm")
    ld.text((W / 2, 130), "शाम 5 बजे: नियम चित्रों से आसान भाषा में", font=M.get_font_reg(40), fill=(150, 108, 0),
            anchor="mm")
    M.place(cv, lay, W / 2, 1270, alpha=M.clamp((t - 0.5) / 0.2))
    if M.host_ready():
        M.host_bubble(cv, "कल सुबह 9 बजे: नए 3 सवाल!", t, 0.6, 1600, "batata")
    return cv


def render(data, tl, gt):
    si = 0
    while si + 1 < len(tl) and gt >= tl[si + 1]["start"]:
        si += 1
    sc = tl[si]
    t = gt - sc["start"]
    if sc["name"] == "end":
        return scene_end(data, t)
    return scene_q(data, int(sc["name"][1:]), t, sc)


def build_video(data, out):
    M.resolve_font()
    tl, total = timeline(data["items"])
    specs = [{"name": "hook", "segs": [("h", data["hook"]["voice"])]}, {"name": "end", "segs": [("e", END_VOICE)]}]
    print("PYQ: awaaz ban rahi hai...")
    hook_v = end_v = None
    try:
        vs = get_voices(specs)
        hook_v, end_v = vs[0][0], vs[1][0]
    except Exception as exc:
        print("PYQ: awaaz nahi bani (reel sirf sangeet/sfx se):", str(exc)[:120])
    for sc in tl:
        print(f"  {sc['name']:<4} {sc['start']:5.2f}s  {sc['dur']:4.2f}s")
    apath = out.replace(".mp4", "_audio.wav")
    build_audio(tl, total, hook_v, end_v, apath)
    n_frames = int(math.ceil(total * M.FPS))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(M.FPS),
           "-i", "-", "-i", apath, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium",
           "-crf", str(M.VIDEO_CRF), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    prev = {}
    try:
        si = 0
        for fi in range(n_frames):
            gt = fi / M.FPS
            while si + 1 < len(tl) and gt >= tl[si + 1]["start"]:
                si += 1
            fr = render(data, tl, gt).convert("RGB")
            tt = gt - tl[si]["start"]
            if si > 0 and tt < TRANS:                       # purana halka ghul ke naya (saaf, tez)
                if si not in prev:
                    prev = {si: render(data, tl, tl[si]["start"] - 1.0 / M.FPS).convert("RGB")}
                fr = Image.blend(prev[si], fr, M.ease_in_out(tt / TRANS))
            proc.stdin.write(fr.tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    ret = proc.wait()
    if os.path.exists(apath):
        os.remove(apath)
    if ret != 0:
        raise RuntimeError("ffmpeg fail")
    print(f"PYQ REEL BANI: {out} ({total:.1f}s)")
    return total


# ------------------------------------------------------------------ caption / log

def write_caption(data, path):
    items = data["items"]
    n = len(items)
    pin = "  ".join(f"{k + 1}-{it['ans']}" for k, it in enumerate(items))
    ex_all = sorted({e for it in items for e in it.get("exams") or []})
    lines = [
        f"GDS to MTS / Postman परीक्षा | पिछले साल के {n} असली सवाल (PYQ) | 10 सेकंड चैलेंज",
        "",
        "अपने जवाब कमेंट में लिखो (जैसे 1-B 2-A 3-D) · रील रोककर पढ़ सकते हो",
        "सही जवाब पिन कमेंट में 📌",
        "",
        "📝 स्रोत: GDS से MTS / Postman विभागीय परीक्षा प्रश्नपत्र (" + ", ".join(ex_all[:8])
        + (" ..." if len(ex_all) > 8 else "") + ")",
        "🎨 शाम 5 बजे: PO Guide का नियम चित्रों से आसान भाषा में",
        "🔖 SAVE करो - परीक्षा से पहले दोहराना",
        f"🎯 FREE MOCK TEST चाहिए? कमेंट करें: {M.MOCK_KEYWORD}",
        "",
        M.HASHTAGS + " #gdsexam #pyq #postalexam",
        "",
        "----- PIN करने वाला पहला कमेंट (reel डालने के 1 घंटे बाद पिन करें) -----",
        f"✅ सही जवाब: {pin}",
        *[f"{k + 1}. {it['q']} → {it['ans']}) {ans_text(it)}  [पूछा गया: {exams_line(it.get('exams') or [], 3)}]"
          for k, it in enumerate(items)],
        f"आपके कितने सही हुए? __/{n} लिखो 👇  शाम 5 बजे नियम चित्रों से समझेंगे!",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("Caption:", path)


def log_experiment(data, out, total):
    new = not os.path.exists(EXP_LOG)
    with open(EXP_LOG, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["post_date", "file", "format", "hook_variant", "questions", "length_sec",
                        "views", "skip_rate", "avg_watch_sec", "comments", "saves", "shares", "follows"])
        w.writerow([data["post_date"], os.path.basename(out), "pyq3-white", data["hook"]["id"],
                    " ".join(it["id"] for it in data["items"]), f"{total:.1f}", "", "", "", "", "", "", ""])


# ------------------------------------------------------------------ run

def post_date_now():
    """Shaam 3 baje ke baad bane to KAL subah 9 baje ki reel (raat me taiyar mile)."""
    now = datetime.datetime.now(IST)
    return (now.date() + datetime.timedelta(days=1 if now.hour >= 15 else 0)).isoformat()


def run(force=False):
    os.makedirs(OUT_DIR, exist_ok=True)
    st = load_state()
    pdate = post_date_now()
    if pdate in (st.get("made") or {}) and not force and not M.DRY_RUN:
        print(f"PYQ: {pdate} ki reel pehle se bani hai ({st['made'][pdate]}) - skip")
        return
    key, items = pick_set(st)
    if not items:
        print("PYQ: sawal-bank ke saare set ho gaye - naye jaanche hue sawal pyq_bank.json me jodiye "
              "(Claude se agla batch banwa lijiye). Aaj PYQ reel nahi.")
        return
    hook = HOOK_VOICES[int(st.get("n", 0)) % len(HOOK_VOICES)]
    mon = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    dd = datetime.date.fromisoformat(pdate)
    data = {"items": items, "hook": hook, "post_date": pdate, "pm_date": f"{dd.day:02d} {mon[dd.month - 1]} {dd.year % 100:02d}"}
    print(f"PYQ {pdate} | awaaz {hook['id']} | sawal: {[x['id'] for x in items]}")
    out = os.path.join(OUT_DIR, f"pyq_{pdate}.mp4")
    k = 2
    while os.path.exists(out) and not M.DRY_RUN:
        out = os.path.join(OUT_DIR, f"pyq_{pdate}_v{k}.mp4")
        k += 1
    total = build_video(data, out)
    write_caption(data, out.replace(".mp4", "_caption.txt"))
    if M.DRY_RUN:
        return
    st.setdefault("done_sets", []).append(key)
    st.setdefault("made", {})[pdate] = os.path.basename(out)
    st["n"] = int(st.get("n", 0)) + 1
    save_state(st)
    log_experiment(data, out, total)


if __name__ == "__main__":
    try:
        run(force="--force" in sys.argv[1:])
    except Exception as exc:                      # shaam wali series kabhi na ruke
        import traceback
        traceback.print_exc()
        print(f"PYQ reel nahi bani ({type(exc).__name__}: {str(exc)[:200]}) - agli run me dobara")
