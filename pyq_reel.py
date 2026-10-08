"""
PYQ TEST REEL  (subah 9 baje wali reel)
=======================================
Ek reel = pichhle saal ke ASLI paper ke 3 sawal, premium test-app jaisa:
  intro (PYQ TEST, kitni parikshaon me aaya) -> 3 x [sawal + 4 option + countdown + "समय समाप्त"] -> CTA.
JAWAB REEL ME KABHI NAHI - sirf PIN comment me (caption file ke neeche taiyar).
Upar hamesha: "जवाब: पिन कमेंट में" + "शाम 5 बजे: चित्रों से आसान नियम" (shaam wali series se jodta hai).

Sawal sirf pyq_papers/pyq_bank.json se (answer key + PO Guide se milaan karke chune hue). Naya kuch gadha nahi jaata.
Bank ke saare set khatam -> reel nahi banti (galat/bina-jaanch sawal se behtar), log me sandesh.

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

THINK = 3.0            # sawal bolne ke baad sochne ka samay (countdown)
TIMEUP = 0.45          # "समय समाप्त" ka pal
INTRO_MIN = 2.0
END_MIN = 4.2
TRANS = 0.22           # scene badalne ka push

GOLD = (245, 196, 66)
GOLD_L = (255, 226, 140)
INK = (8, 12, 28)
CARD = (22, 30, 60)
LINE = (70, 86, 130)
SOFT = (170, 182, 210)
TOP_LINE = "जवाब: पिन कमेंट में   |   शाम 5 बजे: चित्रों से आसान नियम"

INTROS = [
    {"id": "A", "voice": "असली पेपर के तीन सवाल. आपके कितने सही?",
     "big": "3 सवाल", "small": "पिछले साल के असली पेपर से"},
    {"id": "B", "voice": "ये सवाल परीक्षा में आ चुके हैं. आपको आते हैं?",
     "big": "PYQ टेस्ट", "small": "ये सवाल परीक्षा में आ चुके हैं"},
]
END_VOICE = "जवाब कमेंट करो, सही जवाब पिन कमेंट में. शाम पाँच बजे, चित्रों से नियम!"


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


# ------------------------------------------------------------------ voice / timing

def make_specs(items, intro):
    sp = [{"name": "intro", "segs": [("i", intro["voice"])]}]
    for i, it in enumerate(items):
        sp.append({"name": f"q{i}", "segs": [("q", it["q"])]})
    sp.append({"name": "end", "segs": [("e", END_VOICE)]})
    return sp


def vlen(v):
    return len(v[0]) / M.SR if v and v[0] is not None else 0.0


def timeline(specs, voices):
    tl, t = [], 0.0
    for sp, v in zip(specs, voices):
        vd = vlen(v)
        nm = sp["name"]
        if nm == "intro":
            d = max(INTRO_MIN, vd + 0.2)
        elif nm == "end":
            d = max(END_MIN, vd + 0.8)
        else:
            d = max(2.4, vd) + THINK + TIMEUP
        tl.append({"name": nm, "start": t, "dur": d, "vdur": vd})
        t += d
    return tl, t


def get_voices(specs):
    try:
        return M.make_voices(specs)
    except M.VoiceUnavailable:
        print("PYQ: Gemini awaaz nahi mili -> purani awaaz (Swara)")
        M._VOICE_FLAGS["allow_edge"] = True
        return M.make_voices(specs)


def think_start(sc):
    return max(2.4, sc["vdur"])


def build_audio(voices, tl, total, path):
    n = int(total * M.SR) + M.SR
    vt = np.zeros(n, dtype=np.float32)
    for sc, v in zip(tl, voices):
        if v and v[0] is not None:
            M.add_at(vt, v[0], sc["start"] + M.VOICE_LEAD)
    win = int(0.15 * M.SR)
    env = np.convolve(np.abs(vt), np.ones(win, dtype=np.float32) / win, mode="same")
    duck = 1.0 - np.clip(env * 6, 0, 0.65)
    buf = np.zeros(n, dtype=np.float32)
    bed = M.music_bed(n / M.SR)
    m = min(len(bed), n)
    buf[:m] += bed[:m] * duck[:m] * 0.9
    for sc in tl:
        s, nm = sc["start"], sc["name"]
        if nm == "intro":
            M.add_at(buf, M.sfx_thud(0.85), s)
            M.add_at(buf, M.sfx_riser(1.2, 0.16), s + 0.2)
            M.add_at(buf, M.sfx_pop(0.4), s + 0.5)
        elif nm.startswith("q"):
            if sc["start"] > 0:
                M.add_at(buf, M.sfx_whoosh(0.28, 0.32), max(0.0, s - 0.08))
            for j in range(4):                                     # option aate hi halka pop
                M.add_at(buf, M.sfx_pop(0.22), s + 0.55 + 0.12 * j)
            t0 = think_start(sc)
            for k in range(int(THINK)):                            # har second tik
                M.add_at(buf, M.sfx_tick(0.42), s + t0 + k)
            M.add_at(buf, M.sfx_heartbeat(0.35), s + t0 + THINK - 1.0)
            M.add_at(buf, M.sfx_thud(0.7), s + t0 + THINK)         # samay samaapt
        elif nm == "end":
            M.add_at(buf, M.sfx_whoosh(0.3, 0.35), max(0.0, s - 0.08))
            M.add_at(buf, M.sfx_pop(0.45), s + 0.1)
            M.add_at(buf, M.sfx_pop(0.4), s + 0.5)
    buf += vt
    peak = float(np.max(np.abs(buf))) or 1.0
    buf = buf / max(1.0, peak / 0.95)
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", str(M.SR), "-ac", "1", "-i", "-", path],
                   input=pcm.tobytes(), check=True)


# ------------------------------------------------------------------ drawing helpers

_BG = {}


def bg_base():
    """Premium test-hall background: gehra navy gradient + upar sunehri roshni + halki jaali."""
    if "b" in _BG:
        return _BG["b"]
    bw, bh = W + 160, H + 160
    y = np.linspace(0, 1, bh)[:, None]
    x = np.linspace(0, 1, bw)[None, :]
    top, bot = np.array([16, 22, 48]), np.array([5, 8, 20])
    base = top[None, None, :] * (1 - y[..., None]) + bot[None, None, :] * y[..., None]
    gl = np.exp(-(((x - 0.5) / 0.45) ** 2 + ((y - 0.08) / 0.22) ** 2))[..., None]
    base = base + gl * np.array([70, 52, 14])[None, None, :] * 0.55
    gl2 = np.exp(-(((x - 0.85) / 0.35) ** 2 + ((y - 0.85) / 0.3) ** 2))[..., None]
    base = base + gl2 * np.array([20, 40, 110])[None, None, :] * 0.5
    im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(im, "RGBA")
    for gx in range(0, bw, 90):
        d.line((gx, 0, gx, bh), fill=(255, 255, 255, 7), width=1)
    for gy in range(0, bh, 90):
        d.line((0, gy, bw, gy), fill=(255, 255, 255, 7), width=1)
    _BG["b"] = im
    return im


_DUST = [(((i * 0.6180339) % 1.0), ((i * 0.41421) % 1.0), 0.4 + (i % 5) * 0.15) for i in range(36)]


def bg(gt):
    im = bg_base()
    ox = int(80 + 50 * math.sin(gt * 0.35))
    oy = int(80 + 50 * math.cos(gt * 0.27))
    im = im.crop((ox, oy, ox + W, oy + H)).copy()
    d = ImageDraw.Draw(im, "RGBA")
    for px, py, sp in _DUST:                          # tairti sunehri dhool
        yy = (py * H - gt * 30 * sp) % H
        xx = px * W + 16 * math.sin(gt * 0.7 + py * 8)
        r = 1.5 + 2.5 * sp
        d.ellipse((xx - r, yy - r, xx + r, yy + r), fill=(255, 215, 120, int(40 + 50 * sp)))
    return im


def rrect(size, radius, fill, outline=None, width=0, glow=None):
    w, h = size
    pad = 30 if glow else 0
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    if glow:
        g = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(g).rounded_rectangle((pad, pad, pad + w, pad + h), radius=radius, fill=glow)
        im = Image.alpha_composite(im, g.filter(ImageFilter.GaussianBlur(16)))
    ImageDraw.Draw(im).rounded_rectangle((pad, pad, pad + w - 1, pad + h - 1), radius=radius, fill=fill,
                                         outline=outline, width=width)
    return im


def text_c(d, xy, text, size, fill, stroke=0, reg=False, anchor="mm"):
    f = M.get_font_reg(size) if reg else M.get_font(size)
    d.text(xy, text, font=f, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=INK)


def block(d, text, cx, cy, max_w, size, min_size, fill, lines=4, lh=1.3, stroke=0):
    f, s_, ls = M.fit_lines(text, max_w, lines, size, min_size)
    step = int(s_ * lh)
    y0 = cy - (len(ls) - 1) * step / 2
    for k, ln in enumerate(ls):
        d.text((cx, y0 + k * step), " ".join(ln), font=f, fill=fill, anchor="mm", stroke_width=stroke,
               stroke_fill=INK)
    return len(ls) * step


def top_strip(cv, t):
    """Har frame pe upar: brand + 'जवाब पिन कमेंट में | शाम 5 बजे चित्रों से नियम'."""
    d = ImageDraw.Draw(cv, "RGBA")
    d.rectangle((0, 0, W, 210), fill=(4, 6, 16, 150))
    d.line((0, 210, W, 210), fill=GOLD + (120,), width=2)
    M.place(cv, M.pill_sprite("POSTAL WALA  ·  PYQ TEST", 34, INK, GOLD, GOLD_L), W / 2, 62)
    f, s_, ls = M.fit_lines(TOP_LINE, 1020, 1, 42, 28)
    shine = 0.75 + 0.25 * math.sin(t * 2.2)
    col = tuple(int(c * shine + 255 * (1 - shine) * 0.0) for c in (255, 236, 190))
    d.text((W / 2, 150), " ".join(ls[0]) if ls else TOP_LINE, font=f, fill=col, anchor="mm")


def progress(cv, cur, n, t, done_frac=0.0):
    """3 khaanon wali patti: ho chuke sunehre, abhi wala bharta hua."""
    d = ImageDraw.Draw(cv, "RGBA")
    x0, x1, y = 300, 1020, 285
    gap = 16
    seg = (x1 - x0 - gap * (n - 1)) / n
    for i in range(n):
        a = x0 + i * (seg + gap)
        d.rounded_rectangle((a, y - 7, a + seg, y + 7), radius=7, fill=(255, 255, 255, 40))
        k = 1.0 if i < cur else (done_frac if i == cur else 0.0)
        if k > 0:
            d.rounded_rectangle((a, y - 7, a + seg * k, y + 7), radius=7, fill=GOLD + (255,))


def opt_row(letter, text, w=960, h=146, state="idle"):
    fill = {"idle": (24, 34, 70, 235), "lock": (30, 34, 50, 235)}[state]
    out = {"idle": (90, 112, 170, 255), "lock": (70, 76, 96, 255)}[state]
    im = rrect((w, h), 28, fill, out, 3)
    d = ImageDraw.Draw(im)
    pad = 0
    cx, cy = 70, h / 2
    d.ellipse((cx - 42, cy - 42, cx + 42, cy + 42), fill=GOLD if state == "idle" else (120, 120, 130),
              outline=GOLD_L, width=3)
    d.text((cx, cy), letter, font=M.get_font(48), fill=INK, anchor="mm")
    f, s_, ls = M.fit_lines(text, w - 180, 2, 56, 34)
    step = int(s_ * 1.2)
    y0 = cy - (len(ls) - 1) * step / 2
    for k, ln in enumerate(ls):
        d.text((130, y0 + k * step), " ".join(ln), font=f, fill=(240, 244, 252) if state == "idle" else SOFT,
               anchor="lm")
    return im


_OPT_CACHE = {}


def opt_sprite(letter, text, state):
    k = (letter, text, state)
    if k not in _OPT_CACHE:
        _OPT_CACHE[k] = opt_row(letter, text, state=state)
    return _OPT_CACHE[k]


def timer_ring(cv, cx, cy, left, total, urgent):
    """Gol countdown: bachi sec ka number + ghat-ti patti; aakhri sec laal + dhadkan."""
    d = ImageDraw.Draw(cv, "RGBA")
    r = 84
    pulse = 1.0 + (0.06 * math.sin(left * 18) if urgent else 0.0)
    rr = r * pulse
    d.ellipse((cx - rr - 14, cy - rr - 14, cx + rr + 14, cy + rr + 14), fill=(4, 6, 16, 170))
    d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=(255, 255, 255, 40), width=12)
    k = max(0.0, min(1.0, left / total))
    col = (239, 68, 68) if urgent else GOLD
    if k > 0.001:
        d.arc((cx - rr, cy - rr, cx + rr, cy + rr), -90, -90 + 360 * k, fill=col, width=12)
    d.text((cx, cy), str(int(math.ceil(left - 1e-6))) if left > 0 else "0", font=M.get_font(64), fill=col,
           anchor="mm")


# ------------------------------------------------------------------ scenes

def scene_intro(data, t, gt):
    """PEHLA FRAME hi poora bhara (thumbnail jaisa) - kuch bhi fade-in se shuru nahi; sirf halki jaan (pulse/chamak)."""
    cv = bg(gt)
    top_strip(cv, gt)
    it = data["intro"]
    d = ImageDraw.Draw(cv, "RGBA")
    stamp = rrect((780, 150), 30, (0, 0, 0, 0), GOLD + (255,), 7)
    ImageDraw.Draw(stamp).text((stamp.width / 2, stamp.height / 2), "PREVIOUS YEAR PAPER", font=M.get_font(60),
                               fill=GOLD, anchor="mm")
    k = M.ease_out_back(M.clamp(t / 0.3))
    M.place(cv, stamp, W / 2, 430, scale=1.12 - 0.12 * k, angle=-6)        # frame 0 pe bhi dikhti, bas thump
    M.place(cv, M.glow_sprite(360, GOLD, 60), W / 2, 760)
    pulse = 1.0 + 0.025 * math.sin(t * 7)
    lay = Image.new("RGBA", (W, 330), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    block(ld, it["big"], W / 2, 120, 1000, 170, 100, (255, 255, 255), 1, stroke=7)
    block(ld, it["small"], W / 2, 270, 1000, 62, 44, GOLD_L, 1)
    M.place(cv, lay, W / 2, 760, scale=pulse)
    ex = data["items"][0].get("exams") or []
    if len(ex) >= 2:
        M.place(cv, M.pill_sprite(f"पहला सवाल {len(ex)} परीक्षाओं में पूछा गया", 48, INK, GOLD, GOLD_L), W / 2, 1040)
        shown = ex[:4]
        for j, e in enumerate(shown):
            row, col_ = divmod(j, 2)
            x = W / 2 + (col_ - 0.5) * 420
            M.place(cv, M.pill_sprite(e, 38, (235, 240, 252), (30, 40, 80), (90, 112, 170)), x, 1140 + row * 80)
        if len(ex) > 4:
            text_c(d, (W / 2, 1310), f"+ {len(ex) - 4} और", 38, SOFT, reg=True)
    elif ex:
        M.place(cv, M.pill_sprite(f"पहला सवाल: {ex[0]} की परीक्षा से", 46, INK, GOLD, GOLD_L), W / 2, 1060)
    for j in range(len(data["items"])):
        x = W / 2 + (j - 1) * 190
        ring = rrect((140, 140), 70, (20, 28, 58, 255), GOLD + (255,), 5)
        ImageDraw.Draw(ring).text((70, 70), str(j + 1), font=M.get_font(70), fill=GOLD, anchor="mm")
        M.place(cv, ring, x, 1480, scale=1.0 + 0.06 * max(0.0, math.sin(t * 6 - j * 0.8)))
    text_c(d, (W / 2, 1650), "हर सवाल पर 3 सेकंड · अपना जवाब सोचो", 44, SOFT, reg=True)
    return cv


def scene_q(data, i, t, gt, sc):
    it = data["items"][i]
    n = len(data["items"])
    cv = bg(gt)
    top_strip(cv, gt)
    t0 = think_start(sc)
    left = THINK - (t - t0) if t >= t0 else THINK
    timeup = t >= t0 + THINK
    progress(cv, i, n, gt, done_frac=M.clamp(t / sc["dur"]))
    M.place(cv, M.pill_sprite(f"प्रश्न {i + 1}/{n}", 40, INK, GOLD, GOLD_L), 160, 285)
    ex = it.get("exams") or []
    if ex:
        chip = ("पूछा गया: " + exams_line(ex)) if len(ex) < 2 else f"{len(ex)} परीक्षाओं में पूछा गया: {exams_line(ex)}"
        kc = M.ease_out_back(M.clamp((t - 0.1) / 0.3))
        M.place(cv, M.pill_sprite(chip, 36, (255, 236, 190), (60, 44, 10), GOLD), W / 2, 380, scale=max(0.05, kc))
    # sawal card
    kq = M.ease_out_cubic(M.clamp(t / 0.3))
    f, s_, ls = M.fit_lines(it["q"], 900, 4, 74, 48)
    step = int(s_ * 1.32)
    ch = max(260, len(ls) * step + 90)
    card = rrect((980, ch), 36, (255, 255, 255, 18), GOLD + (150,), 3, glow=(245, 196, 66, 40))
    cd = ImageDraw.Draw(card)
    y0 = card.height / 2 - (len(ls) - 1) * step / 2
    for k, ln in enumerate(ls):
        cd.text((card.width / 2, y0 + k * step), " ".join(ln), font=f, fill=(255, 255, 255), anchor="mm")
    cy_card = 470 + ch / 2
    M.place(cv, card, W / 2 + 60 * (1 - kq), cy_card, alpha=kq)
    # options: daayein se ek-ek kar aate
    oy = cy_card + ch / 2 + 120
    for j, (L, o) in enumerate(zip("ABCD", it["opts"])):
        kj = M.ease_out_cubic(M.clamp((t - 0.5 - 0.12 * j) / 0.32))
        if kj <= 0:
            continue
        spr = opt_sprite(L, o, "lock" if timeup else "idle")
        M.place(cv, spr, W / 2 + 260 * (1 - kj), oy + j * 172, alpha=kj)
    # countdown
    ty = min(H - 200, oy + 3 * 172 + 230)
    if t >= t0 - 0.3:
        ka = M.clamp((t - (t0 - 0.3)) / 0.3)
        if not timeup:
            timer_ring(cv, W / 2, ty, left, THINK, left <= 1.0)
            d = ImageDraw.Draw(cv, "RGBA")
            d.text((W / 2, ty + 112), "अपना जवाब सोचो...", font=M.get_font(40), fill=GOLD_L + (int(255 * ka),),
                   anchor="mm")
    if timeup:                                            # samay samaapt: options band, muhar
        k5 = M.ease_out_back(M.clamp((t - t0 - THINK) / 0.18))
        st = M.pill_sprite("समय समाप्त", 70, (255, 255, 255), (200, 40, 50), (255, 150, 150))
        M.place(cv, st, W / 2, ty, scale=max(0.05, 1.5 - 0.5 * k5), angle=-5)
    return cv


def scene_end(data, t, gt):
    n = len(data["items"])
    cv = bg(gt)
    top_strip(cv, gt)
    d = ImageDraw.Draw(cv, "RGBA")
    k = M.ease_out_back(M.clamp(t / 0.3))
    M.place(cv, M.pill_sprite("अपने जवाब कमेंट करो", 84, INK, GOLD, GOLD_L), W / 2, 480, scale=max(0.05, k))
    for j in range(n):                                    # 1-? 2-? 3-? dabbe
        kj = M.ease_out_back(M.clamp((t - 0.25 - 0.12 * j) / 0.25))
        box = rrect((230, 150), 30, (24, 34, 70, 240), GOLD + (255,), 4)
        ImageDraw.Draw(box).text((115, 75), f"{j + 1} - ?", font=M.get_font(64), fill=(255, 255, 255), anchor="mm")
        M.place(cv, box, W / 2 + (j - (n - 1) / 2) * 280, 720, scale=max(0.05, kj))
    text_c(d, (W / 2, 850), "ऐसे लिखो:  1-B  2-A  3-D", 46, SOFT, reg=True)
    k2 = M.ease_out_back(M.clamp((t - 0.6) / 0.3))
    M.place(cv, M.pill_sprite("सही जवाब: पिन कमेंट में", 64, (255, 255, 255), (200, 40, 50), (255, 150, 150)),
            W / 2, 1010, scale=max(0.05, k2))
    k3 = M.ease_out_cubic(M.clamp((t - 0.9) / 0.3))
    lay = Image.new("RGBA", (W, 240), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    block(ld, "SAVE करो · परीक्षा से पहले दोहराना", W / 2, 60, 980, 50, 38, (255, 255, 255), 1)
    block(ld, "जिस दोस्त की तैयारी चल रही है, उसे भेजो", W / 2, 150, 980, 44, 34, GOLD_L, 1)
    M.place(cv, lay, W / 2, 1220, alpha=k3)
    if M.host_ready():
        M.host_bubble(cv, "शाम 5 बजे: चित्रों से नियम आसान!", t, 1.2, 1560, "batata")
    else:
        text_c(d, (W / 2, 1500), "शाम 5 बजे: चित्रों से नियम आसान!", 52, (255, 255, 255))
    return cv


def render(data, tl, gt):
    si = 0
    while si + 1 < len(tl) and gt >= tl[si + 1]["start"]:
        si += 1
    sc = tl[si]
    t = gt - sc["start"]
    nm = sc["name"]
    if nm == "intro":
        return scene_intro(data, t, gt)
    if nm == "end":
        return scene_end(data, t, gt)
    return scene_q(data, int(nm[1:]), t, gt, sc)


def push(prev, cur, k):
    """Purana scene baayein khisakta, naya daayein se (premium app jaisa)."""
    k = M.ease_in_out(M.clamp(k))
    out = Image.new("RGB", (W, H))
    off = int(W * k)
    out.paste(prev, (-off, 0))
    out.paste(cur, (W - off, 0))
    return out


def build_video(data, out):
    M.resolve_font()
    specs = make_specs(data["items"], data["intro"])
    print("PYQ: awaaz ban rahi hai...")
    voices = get_voices(specs)
    tl, total = timeline(specs, voices)
    for sc in tl:
        print(f"  {sc['name']:<5} {sc['start']:5.2f}s  {sc['dur']:4.2f}s  voice {sc['vdur']:4.2f}s")
    apath = out.replace(".mp4", "_audio.wav")
    build_audio(voices, tl, total, apath)
    n_frames = int(math.ceil(total * M.FPS))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(M.FPS),
           "-i", "-", "-i", apath, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium",
           "-crf", str(M.VIDEO_CRF), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    prev_cache = {}
    try:
        si = 0
        for fi in range(n_frames):
            gt = fi / M.FPS
            while si + 1 < len(tl) and gt >= tl[si + 1]["start"]:
                si += 1
            fr = render(data, tl, gt).convert("RGB")
            tt = gt - tl[si]["start"]
            if si > 0 and tt < TRANS:
                if si not in prev_cache:
                    prev_cache = {si: render(data, tl, tl[si]["start"] - 1.0 / M.FPS).convert("RGB")}
                fr = push(prev_cache[si], fr, tt / TRANS)
            proc.stdin.write(fr.tobytes())
            if fi % 150 == 0:
                print(f"  frame {fi}/{n_frames}")
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
        f"GDS to MTS / Postman परीक्षा | पिछले साल के {n} असली सवाल (PYQ) | आपका स्कोर?",
        "",
        f"{n} सवाल, हर सवाल पर 3 सेकंड. अपने जवाब कमेंट में लिखो (जैसे 1-B 2-A 3-D)",
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
        *[f"{k + 1}. {it['q']} → {it['ans']}) {it['opts']["ABCD".index(it['ans'])]}"
          f"  [पूछा गया: {exams_line(it.get('exams') or [], 3)}]" for k, it in enumerate(items)],
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
            w.writerow(["post_date", "file", "format", "intro_variant", "questions", "length_sec",
                        "views", "skip_rate", "avg_watch_sec", "comments", "saves", "shares", "follows"])
        w.writerow([data["post_date"], os.path.basename(out), "pyq3", data["intro"]["id"],
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
    intro = INTROS[int(st.get("n", 0)) % len(INTROS)]
    data = {"items": items, "intro": intro, "post_date": pdate}
    print(f"PYQ {pdate} | intro {intro['id']} | sawal: {[x['id'] for x in items]}")
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
