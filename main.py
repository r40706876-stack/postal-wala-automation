"""
POSTAL WALA - Retention Reel Engine v3 (source-locked)
------------------------------------------------------
NIYAM KA SACH: sirf official Post Office Guide Part I (PO_Guide_Part_1.pdf, repo me).
Code me koi niyam haath se nahi likha.

Har clause ke liye:
  1. PDF se clause ka poora English text nikalta hai
  2. AI (Gemini) clause ko jitne zaroori hon utne parts (1-9) me todta hai,
     har part ke saath PDF ki exact line (source_quote)
  3. TAALA 1 - code jaanch: quote PDF me hai? har sankhya/samay source se milta hai?
  4. TAALA 2 - alag AI "examiner" jaanch: anuvad, exceptions, galat options sach me galat?
  5. TAALA 3 - fail-closed: jis part pe zara bhi shak ho, wo reel NAHI banta.
     Koi manual approval nahi. Har clause ki audit report clause_plans/ me save hoti hai.

Commands:
  python main.py                  -> roz ka run (sirf jaanch-pass part ki reel)
  python main.py --list-clauses   -> PDF se mile clause (* = syllabus/notes me)
  python main.py --build 4 7      -> clause 4 aur 7 ka plan (dobara) banao
  DRY_RUN=1 python main.py        -> bina awaaz ke test render

Reel flow: HOOK (A ya B?) -> SAWAL -> COUNTDOWN -> GALAT HATAO -> JAWAB -> NIYAM + TRAP -> YAAD + MOCK CTA

Har run ke baad generated_reels/ me: reel (.mp4) + caption (.txt); clause poora hone pe carousel/;
pehli baar branding/ (profile photo, highlight covers, intro post).
"""

import os
import re
import sys
import json
import math
import wave
import random
import asyncio
import subprocess
import importlib
from pathlib import Path
from functools import lru_cache


# ---- Auto-install: GitHub Actions / naye PC pe missing package khud install ho jayega ----
def _ensure_packages():
    needed = {"numpy": "numpy", "PIL": "pillow", "requests": "requests", "edge_tts": "edge-tts",
              "pypdf": "pypdf"}
    missing = []
    for module, pip_name in needed.items():
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(pip_name)
    if not missing:
        return
    print("Missing packages install ho rahe hain:", ", ".join(missing))
    base = [sys.executable, "-m", "pip", "install", "--quiet", *missing]
    for cmd in (base, base + ["--break-system-packages"], base + ["--user"]):
        if subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            importlib.invalidate_caches()
            return
    print("WARNING: auto-install fail. Workflow me ye line daaliye: pip install " + " ".join(missing))


_ensure_packages()

# GitHub Actions log me har line turant dikhe (warna sab kuch aakhir me ek saath aata hai)
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, features


# ==================== CONFIG ====================

OUTPUT_DIR = "generated_reels"
STATE_FILE = "progress_state.json"

USE_GEMINI_TTS = True                      # pehli priority: Gemini se ek baar me poori awaaz
# "auto" = Gemini ki Hindi voice library se sabse natural (conversational/warm) native Hindi awaaz.
# Voice test sun ke pasand aaye to yahan uska naam/ID likh dijiye (jaise "Sulafat" ya library ID).
GEMINI_TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "auto")
# "female" ya "male" - Gemini awaaz ka gender (rotation band hone ke baad). Gemini fail ho to hamesha Swara.
GEMINI_TTS_GENDER = os.getenv("GEMINI_TTS_GENDER", "female").strip().lower()
_MALE = GEMINI_TTS_GENDER.startswith("m")
GEMINI_TTS_FALLBACK_VOICE = "Charon" if _MALE else "Sulafat"          # standard voice (Hindi library na mile to)
VOICE_NAME = "hi-IN-SwaraNeural"          # Gemini fail ho to HAMESHA Swara (edge-tts)
GEMINI_TTS_STYLE = "friendly, natural, energetic, speaking briskly"   # docs: chhota style = zyada insaani
# TEST: har reel me 5 awaazon me se agli (baari-baari). Pasand tay hone pe GEMINI_TTS_VOICE me wo ID likhiye
# (tab rotation apne aap band ho jaata hai).
VOICE_ROTATION = True
MERGE_COUNTDOWN = True        # sawal + 4 options + countdown ek scene (dohraav aur khaali taala khatam)
OPT_READ_WPS = 4.0            # options nazar bhar dekhe jaate hain (poora padhne se tez)
SHOW_BEATS = True             # niyam ke neeche 2-4 chhote yaad-tukde (✓/✗/•), examiner-jaanch ke baad hi
SHOW_ENGLISH = True            # Hindi reel me chhoti English line (English wala viewer samjhe aur ruke)
# English kin jagah: hook (sawal + dono cards), sawal, chaaron options (sawal/countdown/galat-hatao),
# sahi jawab, niyam. Screen halki rakhne ke liye trap aur yaad sirf Hindi (chahiye to "trap", "yaad" jodiye).
EN_PLACES = ("hook", "question", "options", "answer", "fact")
EN_COL = (150, 200, 245)
ROTATION_SIZE = 5
VOICE_RATE = "+20%"
VOICE_PITCH = "+2Hz"

W, H = 1080, 1920
FPS = 30
SR = 44100
COUNTDOWN_SECONDS = 3
COUNTDOWN_STEP = 0.7          # 3-2-1 har number 0.7 sec (tez = urgency)

# ---- PACING RULES (retention ka asli game) ----
MAX_PAUSE = 0.14              # voice ke andar koi bhi chuppi isse lambi nahi
VOICE_LEAD = 0.06             # text pehle aata hai, awaaz 60ms baad (aankh kaan se aage)
EYE_LEAD = 0.12               # har word screen pe bolne se 0.12s pehle chamakta hai
READ_WPS = 3.0                # mobile pe Hindi padhne ki speed (shabd / second)
ABSORB = 0.5                  # info khatam hone ke baad dimaag me baithne ka time

DRY_RUN = os.getenv("DRY_RUN", "0") == "1"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

FONT_FILE = os.getenv("FONT_FILE", "Mukta-ExtraBold.ttf")
FONT_URLS = [
    "https://raw.githubusercontent.com/google/fonts/main/ofl/mukta/Mukta-ExtraBold.ttf",
    "https://raw.githubusercontent.com/google/fonts/main/ofl/mukta/Mukta-Bold.ttf",
]
FALLBACK_FONTS = [
    "Mukta-Bold.ttf",
    "C:/Windows/Fonts/NirmalaB.ttf",
    "C:/Windows/Fonts/Nirmala.ttf",
    "C:/Windows/Fonts/Nirmala.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]

# Palette
BG_TOP = (10, 18, 38)
BG_BOTTOM = (20, 36, 66)
CARD = (14, 27, 45)
CARD_2 = (19, 38, 61)
WHITE = (248, 250, 252)
MUTED = (159, 176, 194)
RED = (239, 68, 68)
GREEN = (34, 197, 94)
YELLOW = (250, 204, 21)
ORANGE = (245, 158, 11)
CYAN = (56, 189, 248)
BLUE = (37, 99, 235)
PURPLE = (139, 92, 246)

MOODS = {
    "red": (190, 30, 45),
    "blue": (30, 90, 200),
    "yellow": (200, 140, 10),
    "green": (20, 150, 80),
    "purple": (110, 60, 200),
}


# ==================== SOURCE OF TRUTH: OFFICIAL PO GUIDE PART I ====================
# Code me koi niyam haath se nahi likha. Har reel sirf is PDF ke clause se banti hai.

PDF_FILE = os.getenv("PO_GUIDE_PDF", "PO_Guide_Part_1.pdf")
PLAN_DIR = "clause_plans"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MAX_PARTS = 9
KEEP_LAST_REELS = 20          # repo halka rakhne ke liye sirf aakhri itni reels (.mp4) rakhi jaati hain (0 = sab rakho)
VIDEO_CRF = 23                # video quality/size (Instagram khud dobara compress karta hai; 23 = achhi quality, kam MB)
# Kya-kya banana hai (True = banega). Abhi sirf video + caption + carousel.
MAKE_CAROUSEL = True
MAKE_COVER = False

IG_HANDLE = "@POSTAL_WALA"
MOCK_KEYWORD = "MOCK"          # comment me ye likhne pe aap free mock test bhejenge
HASHTAGS = "#gdstomts #postmanexam #mtsexam #poguide #indiapost #gds #postalexam #departmentalexam"
SHOW_HINT = False             # hint scene band: AI isme clause ke bahar ki wajah gadh deta tha
MAX_REPAIR_TRIES = 4          # ek chhoote part ko kitni baar (alag-alag din) sudharne ki koshish
REPAIRS_PER_RUN = 2           # ek run me kitne chhoote parts sudharne ki koshish (API kharcha seemit)
# Coaching notes (optional): sirf ye tay karne ke liye ki kaunse clause syllabus me hain.
# Niyam ka sach hamesha official PO Guide se hi liya jaata hai.
NOTES_PDF = os.getenv("NOTES_PDF", "mts content .pdf")


# ==================== TEXT HELPERS ====================

_ALLOWED = re.compile(r"[^\u0900-\u097F\u0020-\u007E\u00A0-\u00FF\u2010-\u2027\u20B9\u200C\u200D]")


def clean_text(text):
    """Emoji / unsupported glyph hata deta hai (purane video me yahi box ban rahe the)."""
    if not text:
        return ""
    text = re.sub(r"[*_`#]+", "", str(text))
    text = text.replace("…", "...").replace("—", "-").replace("–", "-")
    text = (text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"')
            .replace("\u201d", '"').replace("\u2022", "-").replace("\u2192", "-"))
    text = re.sub(r"[\u2010-\u2027]", "-", text)   # baaki general punctuation -> '-' (font me na ho to dabba banta)
    text = text.replace("\u200B", "")                 # zero-width space (dikhta nahi, shabd todta hai)
    text = _ALLOWED.sub("", text)
    return " ".join(text.split()).strip()


# ==================== FONTS ====================

_font_path = None
_raqm_warned = False


def resolve_font():
    global _font_path
    if _font_path:
        return _font_path

    if os.path.exists(FONT_FILE) and os.path.getsize(FONT_FILE) > 50000:
        _font_path = FONT_FILE
        return _font_path

    if not DRY_RUN:
        for url in FONT_URLS:
            try:
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                if len(r.content) > 50000:
                    Path(FONT_FILE).write_bytes(r.content)
                    _font_path = FONT_FILE
                    return _font_path
            except Exception:
                continue

    for path in FALLBACK_FONTS:
        if os.path.exists(path) and os.path.getsize(path) > 50000:
            print("Local font use ho raha hai:", path)
            _font_path = path
            return _font_path

    raise RuntimeError("Koi Devanagari font nahi mila. Mukta-Bold.ttf script ke folder me rakhiye.")


@lru_cache(maxsize=256)
def get_font(size):
    global _raqm_warned
    path = resolve_font()
    if features.check("raqm"):
        return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)
    if not _raqm_warned:
        print("WARNING: libraqm nahi mila - Hindi matra galat dikh sakti hai. `pip install --upgrade pillow` karein.")
        _raqm_warned = True
    return ImageFont.truetype(path, size)


FONT_REG_FILE = "Mukta-Medium.ttf"
FONT_REG_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/mukta/Mukta-Medium.ttf"
FALLBACK_REG = ["C:/Windows/Fonts/Nirmala.ttf", "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSans.ttf"]
_reg_path = []


def resolve_reg_font():
    """Body text ke liye halka font (heading ExtraBold, body Medium = professional farak)."""
    if _reg_path:
        return _reg_path[0]
    path = None
    if os.path.exists(FONT_REG_FILE) and os.path.getsize(FONT_REG_FILE) > 50000:
        path = FONT_REG_FILE
    elif not DRY_RUN:
        try:
            r = requests.get(FONT_REG_URL, timeout=30)
            if r.status_code == 200 and len(r.content) > 50000:
                Path(FONT_REG_FILE).write_bytes(r.content)
                path = FONT_REG_FILE
        except Exception:
            pass
    if not path:
        path = next((f for f in FALLBACK_REG if os.path.exists(f)), None) or resolve_font()
    _reg_path.append(path)
    return path


@lru_cache(maxsize=256)
def get_font_reg(size):
    path = resolve_reg_font()
    if features.check("raqm"):
        return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)
    return ImageFont.truetype(path, size)


def text_w(text, font):
    return font.getlength(text)


def fit_lines_f(text, max_w, max_lines, size, min_size, getf):
    s_ = size
    while s_ >= min_size:
        f = getf(s_)
        lines = wrap_words(text, f, max_w)
        if len(lines) <= max_lines and all(text_w(" ".join(l), f) <= max_w for l in lines):
            return f, s_, lines
        s_ -= 2
    f = getf(min_size)
    return f, min_size, wrap_words(text, f, max_w)


def wrap_words(text, font, max_w):
    words = text.split()
    lines, cur = [], []
    for w in words:
        trial = " ".join(cur + [w])
        if cur and text_w(trial, font) > max_w:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def fit_lines(text, max_w, max_lines, size, min_size=26):
    s = size
    while s >= min_size:
        f = get_font(s)
        lines = wrap_words(text, f, max_w)
        if len(lines) <= max_lines and all(text_w(" ".join(l), f) <= max_w for l in lines):
            return f, s, lines
        s -= 2
    f = get_font(min_size)
    return f, min_size, wrap_words(text, f, max_w)


# ==================== EASING / MATH ====================

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(t, start, dur):
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    return clamp((t - start) / dur)


def ease_out_cubic(x):
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    return 3 * x * x - 2 * x * x * x


def ease_out_back(x, s=1.70158):
    x = x - 1
    return x * x * ((s + 1) * x + s) + 1


def with_alpha(color, a):
    return (color[0], color[1], color[2], int(255 * clamp(a)))


def mix(c1, c2, k):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * k) for i in range(3))


# ==================== SPRITES ====================

def place(canvas, sprite, cx, cy, scale=1.0, alpha=1.0, angle=0.0):
    if sprite is None or alpha <= 0.01 or scale <= 0.01:
        return
    sp = sprite
    if abs(scale - 1.0) > 0.005:
        nw, nh = max(1, int(sp.width * scale)), max(1, int(sp.height * scale))
        sp = sp.resize((nw, nh), Image.BILINEAR)
    if abs(angle) > 0.05:
        sp = sp.rotate(angle, resample=Image.BICUBIC, expand=True)
    if alpha < 0.99:
        sp = sp.copy()
        a = sp.getchannel("A").point(lambda v: int(v * alpha))
        sp.putalpha(a)
    canvas.paste(sp, (int(cx - sp.width / 2), int(cy - sp.height / 2)), sp)


@lru_cache(maxsize=64)
def glow_sprite(radius, color, strength=110):
    size = radius * 2
    y, x = np.ogrid[:size, :size]
    d = np.sqrt((x - radius) ** 2 + (y - radius) ** 2) / radius
    a = np.clip(1 - d, 0, 1) ** 2 * strength
    arr = np.zeros((size, size, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = color
    arr[..., 3] = np.clip(a, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


@lru_cache(maxsize=64)
def card_sprite(w, h, fill=CARD_2, outline=(42, 64, 88), width=4, radius=32, shadow=True):
    pad = 30 if shadow else 0
    im = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if shadow:
        for i in range(6, 0, -1):
            d.rounded_rectangle((pad - i * 3, pad - i * 3 + 10, pad + w + i * 3, pad + h + i * 3 + 10),
                                radius=radius + i * 3, fill=(0, 0, 0, 12))
    d.rounded_rectangle((pad, pad, pad + w, pad + h), radius=radius, fill=fill + (255,),
                        outline=outline + (255,), width=width)
    # soft top-light gradient (glass depth)
    arr = np.array(im).astype(np.float32)
    ramp = np.clip(1 - (np.arange(im.height) - pad) / max(1, h * 0.6), 0, 1)[:, None] * 16
    inside = arr[..., 3] > 250
    for c in range(3):
        arr[..., c] = np.where(inside, np.clip(arr[..., c] + ramp, 0, 255), arr[..., c])
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def en_on(place):
    return SHOW_ENGLISH and place in EN_PLACES


def en_h(text, max_w=900, size=36, max_lines=2):
    if not text:
        return 0
    _, s_, lines = fit_lines_f(text, max_w, max_lines, size, 24, get_font_reg)
    return int(s_ * 1.3) * len(lines)


def draw_en(cv, text, y_top, max_w=900, size=36, max_lines=2, color=EN_COL, alpha=1.0):
    """Hindi ke neeche chhoti English line (centre). Returns neeche ka y."""
    if not text or alpha <= 0.02:
        return y_top
    f, s_, lines = fit_lines_f(text, max_w, max_lines, size, 24, get_font_reg)
    lh = int(s_ * 1.3)
    d = ImageDraw.Draw(cv)
    col = mix(BG_BOTTOM, color, alpha) if alpha < 1 else color
    for k, ln in enumerate(lines[:max_lines]):
        d.text((W / 2, y_top + k * lh + lh / 2), " ".join(ln), font=f, fill=col, anchor="mm")
    return y_top + lh * min(len(lines), max_lines)


@lru_cache(maxsize=256)
def option_sprite(letter, text, w, h, state, en=""):
    styles = {
        "normal": (CARD_2, (42, 64, 88), 4, CYAN, WHITE),
        "active": ((24, 52, 82), CYAN, 6, CYAN, WHITE),
        "wrong": ((42, 20, 28), RED, 5, RED, MUTED),
        "correct": ((14, 52, 34), GREEN, 7, GREEN, WHITE),
    }
    fill, outline, width, badge, tcol = styles[state]
    im = card_sprite(w, h, fill, outline, width, 30).copy()
    d = ImageDraw.Draw(im)
    pad = 30
    br = int(h * 0.27)
    bx, by = pad + 30 + br, pad + h // 2
    d.ellipse((bx - br, by - br, bx + br, by + br), fill=badge + (255,))
    d.text((bx, by), letter, font=get_font(int(br * 1.15)), fill=(8, 16, 30, 255), anchor="mm")

    if en:
        # Hindi (1 line) + neeche chhoti English
        f, s, lines = fit_lines(text, w - (br * 2 + 110), 1, int(h * 0.30), 26)
        lines = lines[:1]
        y0 = by - h * 0.13
        fe, se, le = fit_lines_f(en, w - (br * 2 + 110), 1, int(h * 0.215), 20, get_font_reg)
        d.text((bx + br + 40, by + h * 0.19), " ".join(le[0]) if le else "", font=fe,
               fill=(EN_COL if state != "wrong" else MUTED) + (255,), anchor="lm")
        lh = 0
    else:
        f, s, lines = fit_lines(text, w - (br * 2 + 110), 2, int(h * 0.33), 30)
        lh = int(s * 1.32)
        y0 = by - (len(lines) - 1) * lh / 2
    for i, ln in enumerate(lines):
        d.text((bx + br + 40, y0 + i * lh), " ".join(ln), font=f, fill=tcol + (255,), anchor="lm")

    if state == "wrong":
        tw = max(text_w(" ".join(l), f) for l in lines)
        yy = y0 if en else by
        d.line((bx + br + 35, yy, bx + br + 45 + tw, yy), fill=RED + (230,), width=6)
    return im


@lru_cache(maxsize=8)
def x_mark_sprite(size=120):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=RED + (255,))
    m = size * 0.3
    d.line((m, m, size - m, size - m), fill=WHITE + (255,), width=size // 9)
    d.line((size - m, m, m, size - m), fill=WHITE + (255,), width=size // 9)
    return im


@lru_cache(maxsize=8)
def check_sprite(size=140):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=GREEN + (255,))
    s = size
    d.line((s * 0.27, s * 0.52, s * 0.43, s * 0.68), fill=WHITE + (255,), width=s // 10)
    d.line((s * 0.43, s * 0.68, s * 0.74, s * 0.34), fill=WHITE + (255,), width=s // 10)
    return im


@lru_cache(maxsize=4)
def envelope_sprite(w=280):
    h = int(w * 0.68)
    im = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    o = 10
    d.rounded_rectangle((o, o, o + w, o + h), radius=18, fill=(245, 236, 220, 255),
                        outline=(200, 60, 60, 255), width=6)
    d.line((o + 6, o + 8, o + w / 2, o + h * 0.58), fill=(200, 60, 60, 255), width=7)
    d.line((o + w - 6, o + 8, o + w / 2, o + h * 0.58), fill=(200, 60, 60, 255), width=7)
    cx, cy, r = o + w / 2, o + h * 0.58, w * 0.12
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(200, 30, 45, 255))
    d.text((cx, cy), "?", font=get_font(int(r * 1.5)), fill=WHITE + (255,), anchor="mm")
    return im


@lru_cache(maxsize=4)
def stamp_sprite(text="EXAM TRAP"):
    f = get_font(80)
    tw = int(text_w(text, f))
    w, h = tw + 100, 160
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((6, 6, w - 6, h - 6), radius=22, outline=RED + (255,), width=10, fill=(60, 8, 14, 215))
    d.rounded_rectangle((22, 22, w - 22, h - 22), radius=14, outline=RED + (170,), width=3)
    d.text((w / 2, h / 2 + 2), text, font=f, fill=RED + (255,), anchor="mm")
    # grunge ink texture
    rng = random.Random(7)
    arr = np.array(im)
    for _ in range(320):
        x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
        r = rng.randint(1, 3)
        arr[max(0, y - r):y + r, max(0, x - r):x + r, 3] = (arr[max(0, y - r):y + r, max(0, x - r):x + r, 3] * 0.25).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


@lru_cache(maxsize=4)
def bulb_sprite(size=240):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy, r = size / 2, size * 0.40, size * 0.26
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=YELLOW + (255,))
    d.rectangle((cx - r * 0.45, cy + r * 0.7, cx + r * 0.45, cy + r * 1.25), fill=YELLOW + (255,))
    for i in range(3):
        yy = cy + r * 1.3 + i * 13
        d.rounded_rectangle((cx - r * 0.5, yy, cx + r * 0.5, yy + 9), radius=4, fill=(150, 160, 175, 255))
    d.line((cx - r * 0.25, cy + r * 0.1, cx, cy + r * 0.5, cx + r * 0.25, cy + r * 0.1),
           fill=(255, 250, 220, 255), width=5)
    return im


@lru_cache(maxsize=4)
def lock_sprite(size=120):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = max(6, size // 10)
    d.arc((size * 0.25, size * 0.05, size * 0.75, size * 0.6), 180, 360, fill=YELLOW + (255,), width=lw)
    d.line((size * 0.25, size * 0.32, size * 0.25, size * 0.5), fill=YELLOW + (255,), width=lw)
    d.line((size * 0.75, size * 0.32, size * 0.75, size * 0.5), fill=YELLOW + (255,), width=lw)
    d.rounded_rectangle((size * 0.12, size * 0.45, size * 0.88, size * 0.95), radius=size // 9, fill=YELLOW + (255,))
    d.ellipse((size * 0.44, size * 0.6, size * 0.56, size * 0.72), fill=(40, 30, 0, 255))
    return im


@lru_cache(maxsize=4)
def rays_sprite(size=1000):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = size / 2
    for i in range(16):
        a0 = math.radians(i * 22.5)
        a1 = math.radians(i * 22.5 + 9)
        d.polygon([(c, c), (c + math.cos(a0) * c, c + math.sin(a0) * c),
                   (c + math.cos(a1) * c, c + math.sin(a1) * c)], fill=GREEN + (60,))
    mask = np.array(glow_sprite(size // 2, (255, 255, 255), 255).getchannel("A"), dtype=np.float32)
    a = np.array(im.getchannel("A"), dtype=np.float32) * mask / 255.0
    im.putalpha(Image.fromarray(a.astype(np.uint8)))
    return im


@lru_cache(maxsize=32)
def pill_sprite(text, size, fg, bg, outline):
    f = get_font(size)
    w = int(text_w(text, f)) + size * 2
    h = int(size * 1.9)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((2, 2, w - 2, h - 2), radius=h // 2, fill=bg + (235,), outline=outline + (255,), width=3)
    d.text((w / 2, h / 2), text, font=f, fill=fg + (255,), anchor="mm")
    return im


# ==================== BACKGROUND (texture + depth) ====================

@lru_cache(maxsize=8)
def background(mood):
    bw, bh = W + 120, H + 120
    yy, xx = np.mgrid[0:bh, 0:bw].astype(np.float32)
    ty = yy / bh
    base = np.zeros((bh, bw, 3), dtype=np.float32)
    for i in range(3):
        base[..., i] = BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * ty

    col = MOODS[mood]
    for (gx, gy, gr, k) in [(0.2, 0.18, 0.55, 0.55), (0.9, 0.75, 0.6, 0.35)]:
        d = np.sqrt((xx - gx * bw) ** 2 + (yy - gy * bh) ** 2) / (gr * bw)
        g = np.clip(1 - d, 0, 1) ** 2 * k
        for i in range(3):
            base[..., i] += col[i] * g * 0.55

    # subtle exam-paper grid
    grid = ((xx % 60 < 1.5) | (yy % 60 < 1.5)).astype(np.float32) * 5
    base += grid[..., None]

    # vignette
    d = np.sqrt(((xx - bw / 2) / (bw / 2)) ** 2 + ((yy - bh / 2) / (bh / 2)) ** 2)
    base *= np.clip(1.15 - 0.35 * d, 0.62, 1)[..., None]

    # film grain
    rng = np.random.default_rng(3)
    base += rng.normal(0, 4.0, (bh, bw, 1))
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")


def bg_frame(mood, gt):
    im = background(mood)
    ox = int(60 + 40 * math.sin(gt * 0.45))
    oy = int(60 + 40 * math.cos(gt * 0.33))
    return im.crop((ox, oy, ox + W, oy + H))


# ==================== KINETIC TYPOGRAPHY ====================

def word_thresholds(words):
    weights = [len(w) + (3 if re.search(r"[,.!?।]$", w) else 0) + 1 for w in words]
    total = float(sum(weights))
    out, acc = [], 0.0
    for w in weights:
        out.append(acc / total)
        acc += w
    return out


def text_block_h(text, max_w, size, max_lines=4, min_size=30, line_h=1.34):
    _, s, lines = fit_lines(text, max_w, max_lines, size, min_size)
    return int(s * line_h) * len(lines)


def draw_kinetic(canvas, text, cx, top, max_w, size, p, max_lines=4, color=WHITE,
                 hl_words=(), hl_color=YELLOW, karaoke=True, ghost=0.0, min_size=30, line_h=1.34,
                 center_y=None, th=None):
    """Voice ke saath word-by-word text. p = 0..1 speech progress. th = exact word thresholds."""
    font, s, lines = fit_lines(text, max_w, max_lines, size, min_size)
    lh = int(s * line_h)
    if center_y is not None:
        top = center_y - lh * len(lines) / 2
    all_words = [w for ln in lines for w in ln]
    if not all_words:
        return top
    if th is None or len(th) != len(all_words):
        th = word_thresholds(all_words)
    n = len(all_words)
    space = text_w(" ", font)

    layer = Image.new("RGBA", (int(max_w) + 80, lh * len(lines) + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    hl = set(hl_words)

    idx = 0
    for li, ln in enumerate(lines):
        line_w = sum(text_w(w, font) for w in ln) + space * (len(ln) - 1)
        x = (layer.width - line_w) / 2
        y = 20 + li * lh + lh / 2
        for w in ln:
            start = th[idx]
            nxt = th[idx + 1] if idx + 1 < n else 1.0
            a = clamp((p - start) / 0.06 + (0.4 if idx == 0 else 0.0))
            e = ease_out_cubic(a)
            if a <= 0:
                alpha, dy = ghost, 0
            else:
                alpha, dy = max(ghost, e), (1 - e) * 22
            key = re.sub(r"[,.!?।:()]", "", w)
            col = color
            if key in hl and a > 0:
                col = hl_color
            if karaoke and start <= p < nxt and p < 0.999:
                col = YELLOW
            if alpha > 0.01:
                d.text((x, y + dy), w, font=font, fill=with_alpha(col, alpha), anchor="lm")
            x += text_w(w, font) + space
            idx += 1

    canvas.paste(layer, (int(cx - layer.width / 2), int(top - 20)), layer)
    return top + lh * len(lines)


# ==================== PDF -> CLAUSES ====================

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_EN_NUM = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
           "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
           "forty": 40, "fifty": 50, "sixty": 60, "ninety": 90, "hundred": 100}
_HI_NUM = {"दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8,
           "नौ": 9, "दस": 10, "बारह": 12, "पंद्रह": 15, "बीस": 20, "तीस": 30, "चालीस": 40,
           "पचास": 50, "साठ": 60, "नब्बे": 90, "सौ": 100}


def find_guide_pdf():
    """PO_Guide_Part_1.pdf na mile to repo me 'guide' naam wali koi PDF (notes wali chhod ke)."""
    if os.path.exists(PDF_FILE):
        return PDF_FILE
    for fn in sorted(os.listdir(".")):
        low = fn.lower()
        if low.endswith(".pdf") and "guide" in low and fn != NOTES_PDF:
            return fn
    return PDF_FILE


def read_pdf_text(path=None):
    path = path or find_guide_pdf()
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"'{path}' nahi mili. Official PO Guide Part I ki PDF repo me isi naam se upload kijiye.")
    try:
        from pypdf import PdfReader
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pypdf"])
        from pypdf import PdfReader
    reader = PdfReader(path)
    pages = [(pg.extract_text() or "") for pg in reader.pages]
    text = "\n\f\n".join(pages)
    text = text.replace("\u00ad", "").replace("\r", "")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)          # line-break hyphen jodna
    if len(text.strip()) < 2000:
        raise RuntimeError("PDF se text nahi nikla (scanned image PDF ho sakti hai). Text wali PDF chahiye.")
    return text


_LINE_NUM = re.compile(r"^\s*(?:clause\s*[-\u2013.]?\s*)?(\d{1,3})\s*\.\s*(.*)$", re.I)
_TOC_LEADER = re.compile(r"(?:\.\s*){3,}\s*\d*\s*$")


def _squash(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _is_toc_page(page):
    ls = [l for l in page.splitlines() if l.strip()]
    if not ls:
        return False
    first = ls[0].strip().upper()
    leaders = sum(1 for l in ls if _TOC_LEADER.search(l))
    return first.startswith("CONTENTS") or first.startswith("CLAUSE") or leaders / len(ls) >= 0.25


def _title_match(title, rest):
    from difflib import SequenceMatcher
    a, b = _squash(title)[:22], _squash(rest)[:26]
    if len(a) < 4:
        return False
    if b.startswith(a[:8]):
        return True
    return SequenceMatcher(None, a, b[:len(a)]).ratio() >= 0.72


def split_clauses(text):
    """
    Official PO Guide: contents pages se clause -> title, fir body me heading dhoondhna:
      1) 'N.Title – ...' jahan title contents se milta ho (spelling ke chhote farak maaf)
      2) padosi clauses ke beech 'N.' wali line (jahan body me title nahi likha)
      3) sirf 'Title – ...' (jahan body me number nahi likha, jaise clause 1)
    Isse clause ke andar ki 1., 2., 3. wali list kabhi clause nahi banti.
    """
    pages = text.split("\f")
    all_toc = [i for i, pg in enumerate(pages) if _is_toc_page(pg)]
    toc_idx = []
    for i in all_toc:                      # sirf shuru ka lagataar contents hissa (appendix tables nahi)
        if not toc_idx or i - toc_idx[-1] <= 2:
            toc_idx.append(i)
        else:
            break
    if not toc_idx:
        return _split_by_numbers(text.replace("\f", "").splitlines())
    titles = {}
    for i in toc_idx:
        for line in pages[i].splitlines():
            m = _LINE_NUM.match(line)
            if m:
                t = _TOC_LEADER.sub("", m.group(2)).strip(" .\u2013-")
                num = int(m.group(1))
                if t and num not in titles:
                    titles[num] = t
    if len(titles) < 10:
        return _split_by_numbers(text.replace("\f", "").splitlines())

    body = "\n".join(pages[max(toc_idx) + 1:]).splitlines()
    numbered = []
    for idx, line in enumerate(body):
        m = _LINE_NUM.match(line)
        if m:
            numbered.append((idx, int(m.group(1)), m.group(2)))

    # pass 1: number + title
    found, last = {}, -1
    for num in sorted(titles):
        for idx, n, rest in numbered:
            if n == num and idx > last and _title_match(titles[num], rest):
                found[num] = idx
                last = idx
                break

    # pass 2 + 3: jo nahi mile, unhe padosiyon ke beech dhoondho
    for num in sorted(titles):
        if num in found:
            continue
        lo = max([found[k] for k in found if k < num], default=-1)
        hi = min([found[k] for k in found if k > num], default=len(body))
        pick = None
        for idx in range(lo + 1, hi):              # pehle: title + dash (number na likha ho tab bhi)
            line = body[idx]
            if re.search(r"[\u2013\u2014-]", line[:120]) and _title_match(titles[num], re.sub(r"^\s*\d{1,3}\s*\.\s*", "", line)):
                pick = idx
                break
        if pick is None:                           # fir: padosiyon ke beech sirf number
            pick = next((idx for idx, n, _ in numbered if n == num and lo < idx < hi), None)
        if pick is not None:
            found[num] = pick

    heads = sorted(found.items(), key=lambda kv: kv[1])
    clauses = {}
    for k, (num, start) in enumerate(heads):
        end = heads[k + 1][1] if k + 1 < len(heads) else len(body)
        chunk = "\n".join(body[start:end]).strip()
        if _squash(titles.get(num, "")) != "deleted":
            clauses[num] = chunk
    return clauses


def _split_by_numbers(lines):
    """Fallback: bina contents page wali PDF ke liye kram-se-number wala tareeka."""
    head = re.compile(r"^\s*(\d{1,3})\s*[.\-\u2013]\s*[\(\"'\u201cA-Z]")
    best, best_score = {}, -1
    for st in [i for i, l in enumerate(lines) if (m := head.match(l)) and int(m.group(1)) == 1]:
        run, expected, cur, buf = {}, 1, None, []
        for line in lines[st:]:
            m = head.match(line)
            if m and int(m.group(1)) == expected:
                if cur is not None:
                    run[cur] = "\n".join(buf).strip()
                cur, expected, buf = expected, expected + 1, [line]
            elif cur is not None:
                buf.append(line)
        if cur is not None:
            run[cur] = "\n".join(buf).strip()
        long_ones = [v for v in run.values() if len(v) > 150]
        score = len(long_ones) * 1_000_000 + sum(len(v) for v in long_ones)
        if score > best_score:
            best, best_score = run, score
    return best


def clause_title_en(clause_text):
    first = clause_text.split("\n", 1)[0]
    first = re.sub(r"^\s*(?:clause\s*[-\u2013.]?\s*)?\d{1,3}\s*\.\s*", "", first, flags=re.I)
    return re.split(r"\s[\u2014\u2013-]\s|[\u2014\u2013]|--|\.\s*-|\.\s", first)[0].strip()[:90]


def syllabus_clauses(available):
    """Notes PDF me jin clauses ka zikr hai (खंड - 04 / Clause - 13), wahi syllabus. Notes na ho to sab."""
    if not os.path.exists(NOTES_PDF):
        return sorted(available)
    try:
        from pypdf import PdfReader
        txt = "\n".join((pg.extract_text() or "") for pg in PdfReader(NOTES_PDF).pages)
        nums = {int(n) for n in re.findall(r"(?:खंड|Clause)\s*-\s*(\d{1,3})", txt)}
        nums.add(1)
        chosen = sorted(n for n in nums if n in available)
        return chosen or sorted(available)
    except Exception as exc:
        print("Notes PDF nahi padh paya, sab clauses syllabus maane ja rahe hain:", exc)
        return sorted(available)


_NOTES_CACHE = {}


def notes_sections():
    """Notes PDF ko clause-wise tukdon me: {clause_no: text}. Clause 1 = pehli heading se pehle ka hissa."""
    if "sec" in _NOTES_CACHE:
        return _NOTES_CACHE["sec"]
    sec = {}
    if os.path.exists(NOTES_PDF):
        try:
            from pypdf import PdfReader
            txt = "\n".join((pg.extract_text() or "") for pg in PdfReader(NOTES_PDF).pages)
            heads = [(m.start(), int(m.group(1)))
                     for m in re.finditer(r"(?:खंड|Clause)\s*-\s*0*(\d{1,3})", txt)]
            if heads:
                sec[1] = txt[:heads[0][0]]
            for k, (pos, num) in enumerate(heads):
                end = heads[k + 1][0] if k + 1 < len(heads) else len(txt)
                if num not in sec:
                    sec[num] = txt[pos:end]
        except Exception as exc:
            print("Notes PDF nahi padh paya:", exc)
    _NOTES_CACHE["sec"] = sec
    return sec


# ==================== VERIFICATION (auto-check) ====================


def _alnum(s):
    s = (s or "").lower().replace("\u2019", "'")
    return re.sub(r"[^a-z0-9]", "", s)


def quote_in_source(quote, source):
    """
    Quote PDF me sach me hai? Spaces/punctuation hata ke milaan (PDF me 'Bomba y', 'tim ings'
    jaise toote shabd hote hain). Shabd ya akshar badle to fail.
    """
    q, src = _alnum(quote), _alnum(source)
    if len(q) < 25:
        return False
    if q in src:
        return True
    n = 30
    grams = [q[i:i + n] for i in range(0, len(q) - n + 1, 5)]
    hit = sum(1 for g in grams if g in src)
    return bool(grams) and hit / len(grams) >= 0.9


def number_groups(text, lang):
    """
    Har sankhya ka 'barabar roop' group: 17.00 = 17:00 = 17 = 5 (shaam), 8.30 = 8:30,
    five = 5 = पाँच, half = आधा. 1/एक ko chhod diya (Hindi me 'एक' article jaisa aata hai).
    """
    t = (text or "").translate(_DEV_DIGITS)
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)
    groups = []
    for n in re.findall(r"\d+(?:[:.]\d+)?", t):
        n = n.replace(".", ":")
        g = {n}
        if ":" in n:
            h, m = n.split(":", 1)
            h = str(int(h))
            g.add(f"{h}:{m}")
            if int(m or 0) == 0:
                g.add(h)
                if int(h) > 12:
                    g.add(str(int(h) - 12))
        else:
            n2 = str(int(n))
            g.add(n2)
            if n2 == "1":
                continue
        groups.append(g)
    table = _EN_NUM if lang == "en" else _HI_NUM
    words = re.findall(r"[a-z]+", t.lower()) if lang == "en" else re.findall(r"[\u0900-\u097F]+", t)
    for w in words:
        if w in table:
            groups.append({str(table[w])})
    if (lang == "en" and "half" in t.lower()) or (lang == "hi" and ("आधा" in t or "आधे" in t)):
        groups.append({"half"})
    return groups


def _extra(hi_text, allowed_groups):
    allowed = set().union(*allowed_groups) if allowed_groups else set()
    return sorted({min(g) for g in number_groups(hi_text, "hi") if not (g & allowed)})


def _missing(src_groups, hi_text):
    have = set().union(*number_groups(hi_text, "hi")) if number_groups(hi_text, "hi") else set()
    return sorted({min(g) for g in src_groups if not (g & have)})


# Reel chhoti rakhne ke liye har hisse ki shabd-seema (AI ne maani na ho to part FAIL -> sudhaar)
LEN_LIMITS = {"hook": 10, "question": 16, "a": 6, "b": 6, "c": 6, "d": 6,
              "hint": 12, "fact": 18, "trap": 14, "yaad": 9}


def strip_brackets(text):
    """'सर्कल के प्रमुख (Head of the Circle)' -> 'सर्कल के प्रमुख'. Chhote short-form (HO), (SO) rehte hain."""
    if not text or not re.search(r"[\u0900-\u097F]", text):
        return text
    def _cut(m):
        inner = m.group(1).strip()
        return "" if (len(inner) > 6 and re.search(r"[A-Za-z]", inner)) else m.group(0)
    out = re.sub(r"\s*\(([^()]*)\)", _cut, text)
    return " ".join(out.split())


def words(text):
    return len(strip_brackets(text or "").split())


# English term -> galat Hindi roop (auditor se chhoot jaaye to code pakde)
TERM_RULES = [
    (r"\binsured\b", r"बीमा(?!कृत)", "insured = 'बीमाकृत' (sirf 'बीमा' galat, uska matlab insurance hai)"),
]
ENGLISH_IN_HINDI = r"(?<![A-Za-z])(नो|यस|ओनली|नॉट)(?![\u0900-\u097F])"


TRAP_MARKERS = ("गलत", "नहीं", "न कि", "पर ", "पर,", "लेकिन", "बल्कि", "जबकि", "बस ", "केवल", "सिर्फ", "मना", "वर्जित")


def trap_errors(part):
    """
    Trap me 'galat dharana' ke saath uska sudhaar bhi hona chahiye. Warna screen pe galat baat
    niyam jaisi padhi jaati hai (jaise: 'इन्हें मेल वैन लेटर बॉक्स में डाल सकते हैं।').
    """
    t = strip_brackets(part.get("trap", "") or "")
    if t and not any(mk in t + " " for mk in TRAP_MARKERS):
        return ["TRAP: galat dharana ke saath sudhaar nahi (jaise 'X समझना गलत है, सही: Y') - "
                "akele padhne pe ulta niyam lagta hai"]
    return []


def term_errors(part):
    errs = []
    src = ((part.get("source_quote") or "") + " " + (part.get("trap_quote") or "")).lower()
    fields = ("fact", "question", "a", "b", "c", "d", "trap", "yaad", "hook") + (("hint",) if SHOW_HINT else ())
    for en, bad_hi, msg in TERM_RULES:
        if re.search(en, src):
            for k in fields:
                if re.search(bad_hi, part.get(k, "") or ""):
                    errs.append(f"TERM: '{k}' me {msg}")
    for k in fields:
        if re.search(ENGLISH_IN_HINDI, part.get(k, "") or ""):
            errs.append(f"TERM: '{k}' me angrezi shabd (जैसे 'नो') - shuddh Hindi likho ('नहीं')")
    return errs


def length_errors(part):
    errs = []
    for k, lim in LEN_LIMITS.items():
        if k == "hint" and not SHOW_HINT:
            continue
        n = words(part.get(k, ""))
        if n > lim:
            errs.append(f"LENGTH: '{k}' {n} shabd ka hai, seema {lim} - chhota karo, koi shart/sankhya mat hatao")
    return errs


TEXT_KEYS = ("source_quote", "hook", "question", "a", "b", "c", "d", "hint", "fact", "trap", "trap_quote", "yaad")


def norm_correct(v):
    """'D', '(D)', 'Option D', 'D)', 'विकल्प D' -> 'D'. Pehchaan na ho to ''."""
    t = str(v or "").strip().upper()
    m = re.search(r"(?<![A-Z])([ABCD])(?![A-Z])", t)
    return m.group(1) if m else ""


def normalize_part(part):
    """AI ke jawab ko ek roop me: text wale field hamesha str (number/None bhi), 'correct' sirf A-D."""
    out = dict(part)
    for k in TEXT_KEYS:
        v = out.get(k)
        if v is None:
            out[k] = ""
        elif not isinstance(v, str):
            out[k] = str(v)
        out[k] = out[k].strip()
        if out[k].lower() in ("none", "null"):
            out[k] = ""
    out["correct"] = norm_correct(out.get("correct"))
    return out


EN_KEYS = ("question", "a", "b", "c", "d", "fact", "trap", "yaad")
EN_PROMPT = """Translate this Hindi MCQ reel script into simple, clear, exam-style English for Indian postal
department exam aspirants (GDS to MTS / Postman / PA). The official English source line below is the truth.
Use its EXACT official wording and terms wherever possible (for example "insured articles", "V.P. articles",
"letter mail", "Head of the Circle", "Director-General", "certificate of posting") - never casual synonyms,
so a reader who studied the PO Guide recognises the rule at once. Keep EVERY number, time, authority,
condition and exception exactly. Do not add anything.
Short: question max 16 words; each option 1-6 words; fact max 20 words; trap max 16 words and keep its
'wrong belief + correction' meaning; yaad max 10 words, formula style (= and + allowed). No emoji.

OFFICIAL SOURCE (PO Guide, English):
{src}

HINDI SCRIPT (JSON):
{hi}

Return ONLY JSON: {{"question": "", "a": "", "b": "", "c": "", "d": "", "fact": "", "trap": "", "yaad": ""}}
"""


# Hindi shabd -> PO Guide ka official English shabd. Source me official shabd ho aur Hindi me uska roop,
# to English subtitle me bhi wahi official shabd hona chahiye.
EN_TERMS = [
    (r"insured", "बीमाकृत", "insured"),
    (r"v\.\s?p\.|value[- ]payable", "वी.पी.", "V.P."),
    (r"registered", "पंजीकृत", "registered"),
    (r"money[- ]orders?", "मनीऑर्डर", "money order"),
    (r"parcels?", "पार्सल", "parcel"),
    (r"letter mail", "पत्र डाक", "letter mail"),
    (r"head of the circle", "सर्किल प्रमुख", "Head of the Circle"),
    (r"director[- ]general", "महानिदेशक", "Director-General"),
    (r"superintendents?", "अधीक्षक", "Superintendent"),
    (r"head post offices?", "प्रधान डाकघर", "Head Post Office"),
    (r"sub[- ]post offices?", "उप डाकघर", "Sub Post Office"),
    (r"branch (post )?offices?", "शाखा डाकघर", "Branch Office"),
    (r"extra[- ]departmental", "अतिरिक्त विभागीय", "extra-departmental"),
    (r"certificate of posting", "पोस्टिंग प्रमाणपत्र", "certificate of posting"),
    (r"late fee", "विलंब शुल्क", "late fee"),
    (r"night post offices?", "रात्रि डाकघर", "night post office"),
    (r"mobile post offices?", "मोबाइल डाकघर", "mobile post office"),
    (r"postage", "डाक महसूल", "postage"),
    (r"unpaid", "अदत्त", "unpaid"),
    (r"sundays?", "रविवार", "Sunday"),
    (r"postal holidays?", "डाक अवकाश", "postal holiday"),
]


def term_mismatch(part, en):
    """Official PO Guide shabd English me chhoot gaya to batao (Hindi me hai + source me hai)."""
    src = (part.get("source_quote", "") + " " + part.get("trap_quote", "")).lower()
    hi_all = " ".join(str(part.get(k, "")) for k in EN_KEYS)
    en_all = " ".join(str(en.get(k, "")) for k in EN_KEYS).lower()
    errs = []
    for en_re, hi_word, official in EN_TERMS:
        if hi_word in hi_all and re.search(en_re, src) and not re.search(en_re, en_all):
            errs.append(f"EN TERM: PO Guide ka shabd '{official}' use karo (Hindi me '{hi_word}' hai)")
    return errs


EN_AUDIT_PROMPT = """You are an English-language examiner for India Post departmental exam content (GDS to MTS /
Postman / PA). A Hindi MCQ reel (already verified) gets small English subtitles for English-medium viewers.

OFFICIAL SOURCE (PO Guide, English):
{src}

APPROVED HINDI SCRIPT (JSON):
{hi}

ENGLISH SUBTITLES TO CHECK (JSON):
{en}

KNOWN ISSUES FOUND BY CODE (fix them too): {known}

Check strictly:
1. Each English field means EXACTLY the same as the Hindi and the official source: no added, dropped or
   softened condition, number, time, authority or exception.
2. It uses the official PO Guide wording/terms from the source (e.g. "insured articles", "V.P. articles",
   "letter mail", "Head of the Circle") instead of casual synonyms, so a PO Guide reader recognises the rule.
3. The correct option is still the only correct one; wrong options are still clearly wrong.
4. 'trap' read alone still teaches the correct rule (wrong belief + correction).
5. Short, natural, grammatical English. question max 16 words, options 1-6 words, fact max 20,
   trap max 16, yaad max 10 (formula style).
Return ONLY JSON: {{"ok": true/false, "problems": ["..."],
"fixed": {{"question": "", "a": "", "b": "", "c": "", "d": "", "fact": "", "trap": "", "yaad": ""}}}}
Give "fixed" only when ok is false (a corrected version that follows every rule).
"""


def en_examine(part, en, known=()):
    """English examiner. Returns (ok, problems, fixed_or_None)."""
    hi = {k: part.get(k, "") for k in EN_KEYS}
    hi["correct"] = part.get("correct")
    res = as_dict(_llm_json(EN_AUDIT_PROMPT.format(
        src=part.get("source_quote", ""), hi=json.dumps(hi, ensure_ascii=False),
        en=json.dumps({k: en.get(k, "") for k in EN_KEYS}, ensure_ascii=False),
        known="; ".join(known) if known else "none")))
    raw_p = res.get("problems") or []
    if isinstance(raw_p, str):
        raw_p = [raw_p]
    probs = [str(p) for p in raw_p if str(p).strip() and str(p).strip().lower() not in ("none", "no", "[]")]
    ok = res.get("ok")
    ok = (ok is True or (isinstance(ok, str) and ok.strip().lower() in ("true", "yes"))) and not probs
    fixed = res.get("fixed") if isinstance(res.get("fixed"), dict) else None
    if fixed:
        fixed = {k: " ".join(str(fixed.get(k) or "").split()) for k in EN_KEYS}
    return ok, probs, fixed


def nums_match(en_text, hi_text):
    """English aur Hindi me sankhyaen bilkul wahi hon (har group dono taraf mile)."""
    ge, gh = number_groups(en_text, "en"), number_groups(hi_text, "hi")
    return all(any(a & b for b in gh) for a in ge) and all(any(a & b for b in ge) for a in gh)


def english_errors(part, en):
    errs = []
    for k in EN_KEYS:
        v = (en or {}).get(k)
        if not isinstance(v, str) or not v.strip():
            errs.append(f"EN '{k}' khaali")
        elif re.search(r"[\u0900-\u097F]", v):
            errs.append(f"EN '{k}' me Hindi akshar")
    if errs:
        return errs
    corr = norm_correct(part.get("correct")).lower()
    for k in ("fact", "trap", "yaad", "question") + ((corr,) if corr else ()):
        if not nums_match(en[k], part.get(k, "")):
            errs.append(f"EN '{k}' ki sankhya Hindi se alag")
    for k, lim in (("question", 22), ("fact", 26), ("trap", 22), ("yaad", 14)):
        if len(en[k].split()) > lim:
            errs.append(f"EN '{k}' bahut lamba")
    return errs


def ensure_english(plan, part):
    """
    Part ka English roop (subtitle ke liye) - ek baar banke plan me save. Jaanch fail -> English nahi
    dikhegi (galat English kabhi nahi). Returns True agar English taiyar hai.
    """
    if not SHOW_ENGLISH:
        return False
    en = part.get("en") or {}
    if en.get("ok"):
        return True
    if int(en.get("tries", 0)) >= 2:
        return False
    hi = {k: part.get(k, "") for k in EN_KEYS}
    hi["correct"] = part.get("correct")
    try:
        res = as_dict(_llm_json(EN_PROMPT.format(src=part.get("source_quote", ""),
                                                 hi=json.dumps(hi, ensure_ascii=False))))
    except ProviderBusy:
        print("  English line: AI busy - is reel me sirf Hindi")
        return False
    except Exception as exc:
        print("  English line nahi bani:", str(exc)[:120])
        part["en"] = {"tries": int(en.get("tries", 0)) + 1}
        return False
    res = {k: " ".join(str(res.get(k) or "").split()) for k in EN_KEYS}

    def mech(cand):
        e = english_errors(part, cand)
        return e + (term_mismatch(part, cand) if not e else [])

    def fail(why):
        print("  English line jaanch me fail (sirf Hindi dikhegi):", why[:170])
        part["en"] = {"tries": int(en.get("tries", 0)) + 1}
        return False

    try:
        known = mech(res)
        ok, probs, fixed = en_examine(part, res, known)          # English examiner
        if ok and not known:
            final = res
        else:
            if not fixed:
                return fail("; ".join(known + probs) or "examiner ne ok nahi kaha")
            k2 = mech(fixed)
            if k2:
                return fail("sudhar ke baad bhi: " + "; ".join(k2))
            ok2, probs2, _ = en_examine(part, fixed)               # sudhre roop ki dobara jaanch
            if not ok2:
                return fail("sudhar ke baad bhi: " + "; ".join(probs2))
            final = fixed
            print("  English examiner ne sudhara:", "; ".join(known + probs)[:140])
    except ProviderBusy:
        print("  English examiner: AI busy - is reel me sirf Hindi")
        return False
    except Exception as exc:
        return fail(f"examiner nahi chala: {str(exc)[:100]}")
    final = dict(final)
    final["ok"] = True
    part["en"] = final
    save_plan(plan)
    print("  English line taiyar (examiner PASS)")
    return True


BEATS_PROMPT = """Make 2 to 4 very short memory beats (Hindi, max 5 words each) that together restate this
verified exam rule as a quick visual list, so a viewer remembers it at a glance.
Each beat has a mark:
  "yes" = this IS allowed / true / happens,
  "no"  = this is NOT allowed / false / does not happen,
  "key" = the subject or condition (no judgement).
Only restate what the RULE says - add nothing, keep every number and condition exactly, no emoji.
Example rule: "मशीन फ्रैंकित वस्तुएं डाकघर या मेल वैन के लेटर बॉक्स में नहीं डाली जानी चाहिए"
Example beats: [{{"text": "मशीन फ्रैंकित वस्तुएं", "mark": "key"}},
                {{"text": "डाकघर लेटर बॉक्स", "mark": "no"}},
                {{"text": "मेल वैन लेटर बॉक्स", "mark": "no"}}]

RULE (Hindi, verified): {fact}
OFFICIAL SOURCE (English): {src}

Return ONLY JSON: {{"beats": [{{"text": "", "mark": "yes|no|key"}}]}}
"""

BEATS_AUDIT_PROMPT = """You are a strict examiner. A verified exam rule is shown with memory beats marked
✓ (allowed/true), ✗ (NOT allowed/false) and • (subject/condition).
RULE (Hindi): {fact}
OFFICIAL SOURCE (English): {src}
BEATS: {beats}
Read every beat WITH its mark. Is any beat, as shown, different from the rule or misleading (a ✓ on
something not allowed, a ✗ on something allowed, a dropped condition/number that changes the meaning,
anything not in the rule)? Return ONLY JSON: {{"ok": true/false, "problems": ["..."]}}
"""
BEAT_MARKS = {"yes": "✓", "no": "✗", "key": "•"}


def beats_errors(part, beats):
    if not isinstance(beats, list) or not (2 <= len(beats) <= 4):
        return ["BEATS: 2-4 chahiye"]
    errs = []
    fact = part.get("fact", "")
    for b in beats:
        if not isinstance(b, dict) or b.get("mark") not in BEAT_MARKS:
            errs.append("BEATS: mark galat")
            continue
        tx = " ".join(str(b.get("text") or "").split())
        if not tx or not re.search(r"[\u0900-\u097F]", tx) or len(tx.split()) > 6:
            errs.append(f"BEATS: '{tx}' khaali/lamba/Hindi nahi")
            continue
        for g in number_groups(tx, "hi"):
            if not any(g & fg for fg in number_groups(fact, "hi")):
                errs.append(f"BEATS: '{tx}' ki sankhya niyam me nahi")
    return errs


def ensure_beats(plan, part):
    """Niyam ke yaad-tukde (✓/✗/•) - ek baar banke save; examiner fail -> tukde nahi (purana design)."""
    if not SHOW_BEATS:
        return False
    bt = part.get("beats") or {}
    if bt.get("ok"):
        return True
    if int(bt.get("tries", 0)) >= 2:
        return False
    try:
        res = as_dict(_llm_json(BEATS_PROMPT.format(fact=part.get("fact", ""), src=part.get("source_quote", ""))),
                      "beats")
        beats = res.get("beats") if isinstance(res.get("beats"), list) else []
        beats = [{"text": " ".join(str(b.get("text") or "").split()), "mark": str(b.get("mark") or "").lower().strip()}
                 for b in beats if isinstance(b, dict)]
        errs = beats_errors(part, beats)
        if not errs:
            shown = "; ".join(f"{BEAT_MARKS[b['mark']]} {b['text']}" for b in beats)
            aud = as_dict(_llm_json(BEATS_AUDIT_PROMPT.format(fact=part.get("fact", ""),
                                                             src=part.get("source_quote", ""), beats=shown)))
            probs = aud.get("problems") or []
            probs = [probs] if isinstance(probs, str) else probs
            probs = [str(p) for p in probs if str(p).strip() and str(p).strip().lower() not in ("none", "no", "[]")]
            ok = aud.get("ok")
            ok = (ok is True or (isinstance(ok, str) and ok.strip().lower() in ("true", "yes"))) and not probs
            if not ok:
                errs = ["examiner: " + ("; ".join(probs) or "ok nahi")]
    except ProviderBusy:
        print("  Yaad-tukde: AI busy - is reel me purana niyam design")
        return False
    except Exception as exc:
        errs = [f"nahi bane: {str(exc)[:100]}"]
    if errs:
        print("  Yaad-tukde nahi lage:", "; ".join(errs)[:160])
        part["beats"] = {"tries": int(bt.get("tries", 0)) + 1}
        return False
    part["beats"] = {"ok": True, "items": beats}
    save_plan(plan)
    print("  Yaad-tukde taiyar (examiner PASS):", " | ".join(f"{BEAT_MARKS[b['mark']]} {b['text']}" for b in beats))
    return True


def verify_part(part, clause_text):
    """Jo bhi check fail ho, uski wajah lautata hai. Khaali list = pass."""
    errs = []
    # hint ab screen pe nahi aata, isliye zaroori nahi. None/null ko 'khaali' hi maano ("None" shabd nahi)
    part = normalize_part(part)
    need = ["source_quote", "question", "a", "b", "c", "d", "correct", "fact", "trap", "yaad"]
    for k in need:
        v = part.get(k)
        if v is None or not str(v).strip() or str(v).strip().lower() in ("none", "null"):
            errs.append(f"'{k}' khaali hai")
    if errs:
        return errs

    errs += length_errors(part)
    errs += term_errors(part)
    errs += trap_errors(part)
    if not quote_in_source(part["source_quote"], clause_text):
        errs.append("source_quote PDF ke clause me nahi mila")
    trap_q = part.get("trap_quote", "")
    if trap_q and not quote_in_source(trap_q, clause_text):
        errs.append("trap_quote PDF ke clause me nahi mila")

    corr = norm_correct(part.get("correct"))
    if corr not in ("A", "B", "C", "D"):
        errs.append("correct A/B/C/D nahi hai")
        return errs
    opts = [clean_text(part[k]) for k in "abcd"]
    if len(set(opts)) != 4:
        errs.append("options me duplicate hai")

    allowed = number_groups(part["source_quote"], "en")
    allowed_trap = allowed + number_groups(trap_q, "en")
    for field in (("fact", "yaad", "hint") if SHOW_HINT else ("fact", "yaad")):
        extra = _extra(part.get(field) or "", allowed)
        if extra:
            errs.append(f"'{field}' me aisi sankhya hai jo source me nahi: {extra}")
    extra = _extra(part[corr.lower()], allowed)
    if extra:
        errs.append(f"sahi option me aisi sankhya hai jo source me nahi: {extra}")
    extra = _extra(part["trap"], allowed_trap)
    if extra:
        errs.append(f"'trap' me aisi sankhya hai jo source me nahi: {extra}")

    missing = _missing(allowed, part["fact"])
    if missing:
        errs.append(f"source ki sankhya {missing} 'fact' me nahi aayi (niyam adhoora?)")

    correct_forms = [frozenset(g) for g in number_groups(part[corr.lower()], "hi")]
    for k in "abcd":
        if k != corr.lower() and correct_forms:
            other = [frozenset(g) for g in number_groups(part[k], "hi")]
            if other and set(other) == set(correct_forms):
                errs.append(f"galat option {k.upper()} me bhi wahi sankhya hai jo sahi me")
    return errs


# ==================== LLM (Gemini, fallback Groq) ====================

_MODEL_CACHE = {}


def _raise_for(r, who):
    if r.status_code >= 400:
        raise RuntimeError(f"{who} {r.status_code}: {r.text[:300]}")


class ProviderBusy(RuntimeError):
    """AI provider abhi busy/quota khatam - content ki galti nahi."""


def gemini_candidates():
    """
    Abhi chalu Gemini models, pasand ke kram me. Ek busy (503) ya quota khatam (429) ho
    to agla try hota hai (free tier me quota har model ka alag hota hai).
    """
    if os.getenv("GEMINI_MODEL"):
        return [os.getenv("GEMINI_MODEL")]
    if "gemini_list" in _MODEL_CACHE:
        return _MODEL_CACHE["gemini_list"]
    names = _gemini_model_names()

    def ver(n):
        m = re.match(r"gemini-(\d+)(?:\.(\d+))?", n)
        return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)

    bad = ("tts", "image", "live", "audio", "embedding", "robotics", "transcribe", "exp", "preview",
           "learnlm", "gemma", "computer")
    ok = [n for n in names if n.startswith("gemini-") and not any(b in n for b in bad)]
    flash = sorted([n for n in ok if "flash" in n and "lite" not in n], key=ver, reverse=True)
    pro = sorted([n for n in ok if "pro" in n], key=ver, reverse=True)
    lite = sorted([n for n in ok if "lite" in n], key=ver, reverse=True)
    ranked = flash + pro + lite
    if not ranked:
        ranked = ["gemini-flash-latest"]
    print("Gemini models (kram):", ", ".join(ranked[:6]))
    _MODEL_CACHE["gemini_list"] = ranked
    return ranked


def _gemini_model_names():
    """ListModels ek hi baar (text aur TTS dono ke liye)."""
    if "gemini_all" in _MODEL_CACHE:
        return _MODEL_CACHE["gemini_all"]
    names = []
    try:
        token = None
        for _ in range(5):
            params = {"key": GEMINI_API_KEY.strip(), "pageSize": 200}
            if token:
                params["pageToken"] = token
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params=params, timeout=60)
            _raise_for(r, "Gemini ListModels")
            js = r.json()
            names += [m["name"].split("/")[-1] for m in js.get("models", [])
                      if "generateContent" in (m.get("supportedGenerationMethods") or [])]
            token = js.get("nextPageToken")
            if not token:
                break
    except Exception as exc:
        print("Gemini model list nahi mili:", exc)
    _MODEL_CACHE["gemini_all"] = names
    return names


def groq_model():
    """Groq pe abhi chalu models me se sabse bada/behtar text model."""
    if os.getenv("GROQ_MODEL"):
        return os.getenv("GROQ_MODEL")
    if "groq" in _MODEL_CACHE:
        return _MODEL_CACHE["groq"]
    ids = []
    try:
        r = requests.get("https://api.groq.com/openai/v1/models", timeout=60,
                         headers={"Authorization": f"Bearer {GROQ_API_KEY.strip()}"})
        _raise_for(r, "Groq models")
        ids = [m["id"] for m in r.json().get("data", []) if m.get("active", True)]
    except Exception as exc:
        print("Groq model list nahi mili:", exc)
    bad = ("whisper", "guard", "tts", "playai", "orpheus", "distil", "compound", "prompt-guard", "safeguard")
    ids = [i for i in ids if not any(b in i.lower() for b in bad)]
    prefs = [r"gpt-oss-120b", r"llama-3\.3-70b", r"llama-4-maverick", r"kimi-k2", r"qwen.*(32b|235b)",
             r"deepseek", r"llama-4", r"70b", r"gpt-oss", r"llama"]
    pick = None
    for pat in prefs:
        hits = sorted([i for i in ids if re.search(pat, i.lower())], reverse=True)
        if hits:
            pick = hits[0]
            break
    pick = pick or (ids[0] if ids else "llama-3.3-70b-versatile")
    print("Groq model chuna:", pick)
    _MODEL_CACHE["groq"] = pick
    return pick


_BUSY = set()   # is run me jo models busy/quota-khatam mile
_RUN_FLAGS = {"busy": False, "builds": 0}


def _gemini(prompt):
    last = None
    for model in gemini_candidates():
        if model in _BUSY:
            continue
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"}}
        try:
            r = requests.post(url, params={"key": GEMINI_API_KEY.strip()}, json=body, timeout=240)
        except requests.RequestException as exc:
            last = exc
            continue
        low = r.text[:400].lower()
        if r.status_code in (401, 403) or (r.status_code == 400 and ("api key" in low or "api_key" in low)):
            raise RuntimeError("GEMINI_API_KEY galat ya band hai - GitHub Secrets me sahi key daaliye "
                               f"({r.status_code}: {r.text[:150]})")
        if r.status_code in (400, 404, 429, 500, 503):
            print(f"  Gemini {model}: {r.status_code} ({'busy/quota' if r.status_code in (429, 503) else 'model dikkat'}) -> agla model")
            _BUSY.add(model)
            last = RuntimeError(f"{model} {r.status_code}")
            continue
        _raise_for(r, f"Gemini({model})")
        try:
            parts = r.json()["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            return _parse_json(text)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            # jawab block/adhoora (safety ya token seema) -> agla model
            print(f"  Gemini {model}: jawab adhoora/blocked ({type(exc).__name__}) -> agla model")
            _BUSY.add(model)
            last = exc
            continue
    raise ProviderBusy(f"Saare Gemini models busy/quota khatam: {last}")


def _groq(prompt):
    model = groq_model()
    headers = {"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"}
    body = {"model": model, "max_tokens": 8000, "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}]}
    url = "https://api.groq.com/openai/v1/chat/completions"
    r = requests.post(url, headers=headers, json=body, timeout=240)
    if r.status_code == 400:                      # kuch model json_mode/temperature nahi lete
        body.pop("response_format", None)
        body.pop("temperature", None)
        r = requests.post(url, headers=headers, json=body, timeout=240)
    if r.status_code in (401, 403):
        raise RuntimeError(f"GROQ_API_KEY galat ya band hai - GitHub Secrets check kariye ({r.status_code})")
    if r.status_code == 404:
        _MODEL_CACHE.pop("groq", None)
    if r.status_code in (429, 503, 500, 404):
        raise ProviderBusy(f"Groq({model}) {r.status_code}: {r.text[:200]}")
    _raise_for(r, f"Groq({model})")
    return _parse_json(r.json()["choices"][0]["message"]["content"])


def available_providers():
    out = []
    if GEMINI_API_KEY:
        out.append(("gemini", _gemini))
    if GROQ_API_KEY:
        out.append(("groq", _groq))
    return out


def _llm_json(prompt, only=None):
    """
    only=None: jo provider chal jaaye (plan banana). only='gemini'/'groq': wahi (examiner).
    Sab busy hon to ProviderBusy - taaki ise 'content galat' na maana jaaye.
    """
    import time
    last, busy = None, False
    for name, fn in available_providers():
        if only and name != only:
            continue
        for attempt in range(2):
            try:
                return fn(prompt)
            except ProviderBusy as exc:
                last, busy = exc, True
                print(f"  {name} busy: {str(exc)[:160]}")
                break
            except Exception as exc:
                last = exc
                print(f"  {name} fail ({str(exc)[:200]}), 6s baad dobara...")
                time.sleep(6)
    if busy:
        _RUN_FLAGS["busy"] = True
        raise ProviderBusy(str(last))
    raise RuntimeError(f"Koi LLM kaam nahi kiya (GEMINI_API_KEY / GROQ_API_KEY check karein): {last}")


def as_dict(res, list_key=None):
    """
    AI kabhi {..} ki jagah [..] lauta deta hai (Groq ne yahi kiya). Dono ko dict me badlo.
    list_key diya ho (jaise 'parts') aur list me parts jaise dicts hon to {list_key: list}.
    """
    if isinstance(res, dict):
        return res
    if isinstance(res, list):
        dicts = [x for x in res if isinstance(x, dict)]
        if list_key and dicts and any("question" in d or "fact" in d for d in dicts):
            return {list_key: dicts}
        if len(dicts) == 1:
            return dicts[0]
        if dicts:
            merged = {}
            for d_ in dicts:
                merged.update(d_)
            return merged
    return {}


def _parse_json(raw):
    if not raw or not str(raw).strip():
        raise ValueError("AI ka jawab khaali aaya")
    raw = str(raw)
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


PLAN_PROMPT = """You are preparing exam-accurate Hindi MCQ reels for India Post departmental exams
(GDS to MTS / Postman / PA). The ONLY source of truth is the official Post Office Guide Part I
clause given below. Accuracy matters more than anything else.

CLAUSE {num} (official English text):
<<<
{text}
>>>

TASK: Split this clause into the exam-relevant rules it contains. One rule = one part.
Short clause -> 1-2 parts. Long clause -> up to {max_parts} parts. Skip parts that are not exam-worthy.
If the clause is deleted or has no exam-relevant rule, return "parts": [].

STRICT RULES:
1. source_quote: copy 1-3 sentences from the clause EXACTLY word for word (English). Every fact of the
   part must be fully supported by this quote alone.
2. fact: faithful Hindi translation of what the quote says, max 16 words. Do not add, drop or soften any
   condition, number, exception or authority.
3. question: exam-style Hindi question answerable only from the quote. Max 16 words.
4. a, b, c, d: 2-5 words each, Hindi only, NO English in brackets. Exactly one correct (matches the quote).
   The 3 wrong ones must be plausible but DEFINITELY wrong per the clause (never partly true).
5. correct: only the letter, e.g. "B".
6. trap: the likely confusion in Hindi, max 12 words, must NOT repeat the fact. Write it as WRONG belief +
   correction, e.g. "X समझना गलत है, Y ही सही है" or "X नहीं, केवल Y". NEVER write the wrong belief alone
   as a plain statement - read alone it must still teach the correct rule. Built only from this clause.
   If it uses another sentence of the clause, copy that sentence verbatim into trap_quote, else "".
7. yaad: 1-line Hindi memory formula, max 8 words (= and + allowed, NOT a sentence), fully consistent with fact.
8. hook: the SAME question in short, plain, everyday spoken Hindi (max 8 words, no bookish words), so it is
   understood in 1 second while scrolling. It must ask EXACTLY what the question asks (not a yes/no question),
   must not reveal the answer. No fake statistics.
9. Write numbers as digits. No emoji anywhere.
10. EXCEPTIONS: if anywhere in the clause there is an exception, "also permitted", "except", "excluding",
    "only", "generally", "usually" etc. that affects a part, that part's fact, correct answer, wrong options
    and trap must respect it, and the exception sentence must be inside source_quote. Never turn
    "generally/usually" into "always".
11. This Guide is corrected up to 1985. AVOID time-sensitive facts that may have changed (number of postal
    circles, postal rates, fee amounts, commission %, names of firms/dealers/officers, lists of cities)
    unless they are the only exam-relevant content. Prefer procedural rules, authorities, conditions, exceptions.
12. Standard Hindi terms (use exactly): Head Post Office = प्रधान डाकघर, Sub Post Office = उप डाकघर,
    Branch Post Office = शाखा डाकघर, registered = पंजीकृत, insured article = बीमाकृत वस्तु (NOT insurance/बीमा),
    V.P. = वी.पी. (मूल्य देय), money order = मनीऑर्डर, night post office = रात्रि डाकघर,
    mobile post office = मोबाइल डाकघर, Head of the Circle = सर्किल प्रमुख, Director General = महानिदेशक,
    extra-departmental = अतिरिक्त विभागीय, certificate of posting = पोस्टिंग प्रमाणपत्र,
    late fee = विलंब शुल्क, letter mail = पत्र डाक, Superintendent of Post Offices = डाकघर अधीक्षक.
13. title_hi: short Hindi title of the clause (max 6 words).

Return ONLY JSON:
{{"title_hi": "...", "parts": [{{"source_quote": "...", "hook": "...", "question": "...",
"a": "...", "b": "...", "c": "...", "d": "...", "correct": "A", "fact": "...",
"trap": "...", "trap_quote": "...", "yaad": "..."}}]}}
"""


# ==================== CLAUSE PLAN (review file) ====================

def plan_path(num):
    return os.path.join(PLAN_DIR, f"clause_{num}.json")


def load_plan(num):
    p = plan_path(num)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_plan(plan):
    os.makedirs(PLAN_DIR, exist_ok=True)
    with open(plan_path(plan["clause_no"]), "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    write_review_md(plan)


def all_plans():
    if not os.path.isdir(PLAN_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(PLAN_DIR)):
        m = re.fullmatch(r"clause_(\d+)\.json", fn)
        if m:
            p = load_plan(int(m.group(1)))
            if p:
                out.append(p)
    return out


def write_review_md(plan):
    lines = [f"# Clause {plan['clause_no']}: {plan.get('title_hi', '')}",
             f"English title: {plan['title_en']}", "",
             "## Audit report (automatic)",
             "Sirf PASS wale parts ki reel banti hai. FAIL wale kabhi publish nahi hote.",
             "Kisi reel pe shak ho to yahan uska English source dekh sakte hain.", ""]
    for i, p in enumerate(plan["parts"], 1):
        if p.get("auto_check"):
            status = "PASS" + (" (sudhara gaya)" if p.get("repaired") else "")
            status += f" | publish: {p['published']}" if p.get("published") else " | publish baaki"
        else:
            status = (f"FAIL ({p.get('repair_tries', 0)}/{MAX_REPAIR_TRIES} sudhaar koshish): "
                      + "; ".join(p.get("check_errors", [])))
        corr = str(p.get("correct", "")).upper()[:1]
        lines += [f"## Part {i}  [{status}]",
                  f"**Source (PO Guide):** {p.get('source_quote', '')}", "",
                  f"**Niyam:** {p.get('fact', '')}",
                  f"**Sawal:** {p.get('question', '')}"]
        for k in "abcd":
            mark = "  <- SAHI" if k.upper() == corr else ""
            lines.append(f"- {k.upper()}. {p.get(k, '')}{mark}")
        lines += [f"**Hint:** {p.get('hint', '')}",
                  f"**Trap:** {p.get('trap', '')}"
                  + (f"  (source: {p['trap_quote']})" if p.get("trap_quote") else ""),
                  f"**Yaad:** {p.get('yaad', '')}", f"**Hook:** {p.get('hook', '')}", ""]
    lines += ["---", "## Poora clause (PDF se)", "```", plan["clause_text_en"], "```"]
    with open(os.path.join(PLAN_DIR, f"clause_{plan['clause_no']}_review.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def build_plan(num, clauses=None, attempts=3):
    clauses = clauses or split_clauses(read_pdf_text())
    if num not in clauses:
        raise KeyError(f"Clause {num} PDF me nahi mila. `python main.py --list-clauses` se list dekhiye.")
    text = clauses[num]
    best_passed, best_failed, title_hi = [], [], ""
    for attempt in range(attempts):
        try:
            data = as_dict(_llm_json(PLAN_PROMPT.format(num=num, text=text[:40000], max_parts=MAX_PARTS)), "parts")
        except ProviderBusy:
            if attempt == 0:
                raise
            print("  AI busy - pichhli koshish ke parts save kar rahe hain")
            break
        title_hi = clean_text(data.get("title_hi", "")) or title_hi
        raw_parts = []
        raw_list = data.get("parts") or []
        if isinstance(raw_list, dict):
            raw_list = [raw_list]
        for part in [x for x in raw_list if isinstance(x, dict)][:MAX_PARTS]:
            part = normalize_part(part)
            part["_clause_no"] = num
            raw_parts.append(part)
        print(f"  Clause {num}: {len(raw_parts)} parts bane, jaanch chal rahi hai (ek saath)...")

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as ex:
            results = list(ex.map(lambda pt: check_part(pt, text), raw_parts))

        passed, failed = [], []
        seen_q = set()
        for part, errs in zip(raw_parts, results):
            qk = _squash_hi(part.get("question") or "")
            if not errs and qk in seen_q:                 # ek hi sawal do reels me na aaye
                errs = ["DUPLICATE: ye sawal is clause me pehle se hai"]
            if not errs:
                seen_q.add(qk)
            part["auto_check"] = not errs
            part["check_errors"] = errs
            (failed if errs else passed).append(part)
        print(f"  Attempt {attempt + 1}: {len(passed)} pass, {len(failed)} fail")
        if attempt == 0 or len(passed) > len(best_passed):
            best_passed, best_failed = passed, failed
        # ek bhi pakka part mil gaya to ruk jao; fail wale agle runs me 'sudhaar' se aayenge
        if passed:
            break
        if failed and all(is_pending(p) for p in failed):
            print("  Examiner AI abhi busy hai - parts save kar rahe hain, jaanch agle run me.")
            break
    passed, failed = best_passed, best_failed

    os.makedirs(PLAN_DIR, exist_ok=True)
    plan = {
        "clause_no": num,
        "title_en": clause_title_en(text),
        "title_hi": title_hi or clause_title_en(text),
        "source_pdf": os.path.basename(find_guide_pdf()),
        "approved": True,
        "build_tries": 1,
        "note": "Automatic. Sirf auto_check=true wale parts ki reel banti hai. FAIL wale kabhi publish nahi honge.",
        "parts": passed + failed,
        "clause_text_en": text,
    }
    save_plan(plan)
    print(f"Clause {num} plan bana: {len(passed)} part PASS, {len(failed)} FAIL -> {plan_path(num)}")
    return plan


AUDIT_PROMPT = """You are a strict examiner of India Post rules. Below is an official Post Office Guide
Part I clause and one Hindi MCQ reel script made from it. Check it word by word.

CLAUSE (official):
<<<
{text}
>>>

RECENT COACHING NOTES for the same clause (Hindi, text may be garbled; may be empty):
<<<
{notes}
>>>

SCRIPT (JSON):
{part}

Answer these, using the clause (and the notes only for check 7):
1. Is the Hindi 'fact' a faithful translation (no added/dropped condition, number, authority, exception)?
2. Is the marked correct option fully correct per the clause?
3. Is EVERY wrong option definitely wrong per the clause (not partly true, not true for some case)?
4. Are 'trap', 'yaad', 'hook' fully consistent with the clause and free of invented reasons?
5. Is any exception elsewhere in the clause ignored?
6. Are postal terms translated correctly (insured = बीमाकृत वस्तु, not insurance)?
6b. Read the 'trap' ALONE: does it clearly say what is wrong and what is right? If it could be read as
    stating the wrong rule as fact, that is a problem.
7. OUTDATED CHECK: this Guide is corrected only up to 1985. If the recent notes state a DIFFERENT
   value for any fact the script uses (a count, number, fee, time, authority, name, list), or the fact
   is obviously time-sensitive (number of circles, postal rates/fees, office-bearer names, dealer firms)
   and the notes do not confirm it, report a problem starting with "OUTDATED:".

Return ONLY JSON: {{"ok": true/false, "problems": ["short Hindi or English description", ...]}}
ok must be false if there is even one problem.
"""


ADVERSARIAL_PROMPT = """You are a second, very strict India Post examiner. ASSUME the Hindi MCQ script below
contains at least one mistake, and try hard to find it using ONLY the official clause.

CLAUSE (official):
<<<
{text}
>>>

RECENT COACHING NOTES for the same clause (may be garbled; may be empty):
<<<
{notes}
>>>

SCRIPT (JSON):
{part}

Look for: wrong or missing number/time/authority/condition, ignored exception, a wrong option that is
partly true, a 'trap' that (read alone) states the wrong belief as if it were the rule, wrong term (insured = बीमाकृत वस्तु), invented reasons, facts that the notes say changed.
Only if after careful checking you find NOTHING wrong, return ok true.
Return ONLY JSON: {{"ok": true/false, "problems": ["..."]}}
"""


def audit_part(part, clause_text):
    """
    Har uplabdh AI examiner jaanchta hai. Normal: Gemini + Groq dono ka ok zaroori.
    Ek busy ho to: jo chal raha hai wo DO baar jaanchta hai (normal + 'galti dhoondho' tareeka).
    Koi bhi examiner na chale to ProviderBusy (part 'jaanch baaki' me jaata hai).
    """
    providers = available_providers()
    if not providers:
        return ["AUDIT: koi AI examiner uplabdh nahi (GEMINI_API_KEY/GROQ_API_KEY) - bina jaanch pass nahi"]
    view = {k: part.get(k) for k in ("fact", "question", "a", "b", "c", "d", "correct", "trap", "yaad", "hook")}
    if SHOW_HINT:
        view["hint"] = part.get("hint")
    num = part.get("_clause_no")
    notes = (notes_sections().get(num, "") if num else "")[:8000] or "(none)"
    pj = json.dumps(view, ensure_ascii=False)
    prompt = AUDIT_PROMPT.format(text=clause_text[:40000], notes=notes, part=pj)

    def run(pr, name):
        res = as_dict(_llm_json(pr, only=name))
        raw_p = res.get("problems") or []
        if isinstance(raw_p, str):
            raw_p = [raw_p]
        probs = [str(p) for p in raw_p if str(p).strip() and str(p).strip().lower() not in ("none", "no", "[]")]
        ok = res.get("ok")
        ok = ok is True or (isinstance(ok, str) and ok.strip().lower() in ("true", "yes"))
        if ok and not probs:
            return []
        return [f"AUDIT({name}): {p}" for p in probs] or [f"AUDIT({name}): ok nahi kaha"]

    problems, worked, busy = [], [], []
    for name, _ in providers:
        try:
            problems += run(prompt, name)
            worked.append(name)
        except ProviderBusy:
            busy.append(name)
    if not worked:
        raise ProviderBusy("saare examiner busy")
    if problems:
        return problems
    if busy or len(worked) < 2:
        # sirf ek examiner chala: wahi doosri baar 'galti dhoondho' tareeke se jaanche
        adv = ADVERSARIAL_PROMPT.format(text=clause_text[:40000], notes=notes, part=pj)
        try:
            extra = run(adv, worked[0])
        except ProviderBusy:
            raise ProviderBusy("doosri jaanch ke liye examiner busy")
        if extra:
            return ["ADV-" + e for e in extra]
        print(f"  (ek examiner busy tha: {worked[0]} ne 2 alag tareekon se jaancha - PASS)")
    return []


REPAIR_PROMPT = """You are fixing ONE Hindi MCQ reel script for India Post exams. It FAILED accuracy checks.
The ONLY source of truth is this official Post Office Guide Part I clause:
<<<
{text}
>>>

FAILED SCRIPT (JSON):
{part}

PROBLEMS FOUND:
{errors}

Rewrite the script so that every problem is fixed. You may change the question, options, answer,
trap, yaad, hook completely, or pick a different exam-relevant rule from the SAME clause if this
one cannot be made fully accurate. All rules:
- source_quote copied word for word from the clause (English), and it alone must support the fact.
- fact = faithful Hindi translation (max 16 words), keep every condition, number, authority and exception.
- question max 16 words. a, b, c, d: 2-5 words each, Hindi only, no English in brackets.
- exactly one correct option; each wrong option definitely wrong per the clause (never partly true).
- correct = only the letter, e.g. "C".
- trap max 12 words, written as WRONG belief + correction ("X समझना गलत है, Y ही सही है" / "X नहीं, केवल Y");
  never the wrong belief alone. yaad = formula, max 8 words. hook max 8 words.
- trap/yaad/hook only from the clause, no invented reasons. Numbers as digits. No emoji.
- insured article = बीमाकृत वस्तु (not insurance). Never turn "generally/usually" into "always".

Return ONLY JSON with keys: source_quote, hook, question, a, b, c, d, correct, fact, trap, trap_quote, yaad.
"""


PENDING = "AUDIT_PENDING"


def is_pending(part):
    errs = part.get("check_errors") or []
    return bool(errs) and all(str(e).startswith(PENDING) for e in errs)


def check_part(part, clause_text):
    errs = verify_part(part, clause_text)
    if not errs:
        try:
            errs = audit_part(part, clause_text)
        except Exception as exc:
            # AI busy/quota: content galat nahi, bas jaanch baaki - agle run me dobara
            errs = [f"{PENDING}: examiner abhi uplabdh nahi ({str(exc)[:120]})"]
    return errs


def repair_part(part, clause_text):
    """Ek chhoote part ko uski galtiyon ke saath AI ko wapas deta hai, fir poori jaanch dobara."""
    view = {k: part.get(k) for k in ("source_quote", "hook", "question", "a", "b", "c", "d", "correct",
                                     "fact", "trap", "trap_quote", "yaad")}
    fixed = _llm_json(REPAIR_PROMPT.format(
        text=clause_text[:40000], part=json.dumps(view, ensure_ascii=False),
        errors="\n".join("- " + e for e in part.get("check_errors", [])) or "- unknown"))
    fixed = as_dict(fixed, "parts")
    if "parts" in fixed and isinstance(fixed["parts"], list) and fixed["parts"]:
        fixed = fixed["parts"][0]
    fixed = normalize_part(fixed)
    fixed["_clause_no"] = part.get("_clause_no")
    return fixed, check_part(fixed, clause_text)


def repair_pass(clauses, budget=REPAIRS_PER_RUN, pending_budget=6):
    """
    1) Jin parts ki jaanch AI busy hone se ruki thi -> sirf dobara jaanch (koshish nahi ginti).
    2) Jo content ki wajah se fail hue -> galtiyon ke saath sudhaar (MAX_REPAIR_TRIES tak).
    3) Jis clause ka plan khaali bana -> dobara plan.
    AI busy mile to turant ruk jaata hai (quota bachane ke liye).
    """
    fixed_any = 0
    plans = sorted(all_plans(), key=lambda p: p["clause_no"])

    for plan in plans:                                     # 1) pending jaanch
        text = clauses.get(plan["clause_no"])
        changed = False
        for part in plan.get("parts", []):
            part.setdefault("_clause_no", plan["clause_no"])
            if pending_budget <= 0 or _RUN_FLAGS["busy"] or not text:
                break
            if part.get("auto_check") or not is_pending(part):
                continue
            pending_budget -= 1
            print(f"Clause {plan['clause_no']}: baaki jaanch ab ho rahi hai...")
            errs = check_part(part, text)
            part["check_errors"] = errs
            changed = True
            if not errs:
                part.update({"auto_check": True, "repaired": True})
                fixed_any += 1
                print("  PASS - agle video me aayega.")
            elif is_pending(part):
                print("  AI abhi bhi busy - agle run me.")
            else:
                print("  jaanch me galti mili:", "; ".join(errs)[:200])
        if changed:
            save_plan(plan)

    for plan in plans:                                     # 2) + 3) sudhaar
        if budget <= 0 or _RUN_FLAGS["busy"]:
            break
        num = plan["clause_no"]
        text = clauses.get(num)
        if not text:
            continue
        if not plan.get("parts") and plan.get("build_tries", 1) < MAX_REPAIR_TRIES:
            print(f"Clause {num}: plan khaali tha, dobara bana raha hoon...")
            tries = plan.get("build_tries", 1) + 1
            budget -= 1
            try:
                plan = build_plan(num, clauses)
                plan["build_tries"] = tries
                save_plan(plan)
            except ProviderBusy:
                print("  AI busy - agle run me.")
                break
            except Exception as exc:
                print("  dobara nahi bana:", exc)
            continue

        changed = False
        for i, part in enumerate(plan.get("parts", [])):
            if budget <= 0 or _RUN_FLAGS["busy"]:
                break
            part.setdefault("_clause_no", num)
            if part.get("auto_check") or is_pending(part) or part.get("repair_tries", 0) >= MAX_REPAIR_TRIES:
                continue
            budget -= 1
            tries = part.get("repair_tries", 0) + 1
            print(f"Clause {num}: chhoota part sudhaar raha hoon (koshish {tries}/{MAX_REPAIR_TRIES})...")
            try:
                fixed, errs = repair_part(part, text)
            except ProviderBusy:
                print("  AI busy - ye koshish gini nahi gayi, agle run me.")
                break
            except Exception as exc:
                print("  sudhaar nahi ho paya:", exc)
                continue
            others = [_squash_hi(p.get("question", "")) for k, p in enumerate(plan.get("parts", [])) if k != i]
            if _squash_hi(fixed.get("question", "")) in others:
                errs = ["DUPLICATE: ye sawal is clause me pehle se hai"]
            if all(str(e).startswith(PENDING) for e in errs) and errs:
                fixed.update({"auto_check": False, "check_errors": errs, "repair_tries": part.get("repair_tries", 0)})
                plan["parts"][i] = fixed                    # naya version rakho, jaanch baad me
                print("  sudhra hua version bana, jaanch AI busy hone se baaki.")
            elif not errs:
                fixed.update({"auto_check": True, "check_errors": [], "repaired": True, "repair_tries": tries})
                plan["parts"][i] = fixed
                fixed_any += 1
                print("  SUDHAR GAYA - saari jaanch pass. Agle video me aayega.")
            else:
                part["repair_tries"] = tries
                part["check_errors"] = errs
                print("  abhi bhi fail:", "; ".join(errs)[:200])
            changed = True
        if changed:
            save_plan(plan)
    return fixed_any


def _squash_hi(t):
    return re.sub(r"[\s,.!?\u0964:()\-]", "", t or "")


def usable_parts(plan):
    return [p for p in plan.get("parts", []) if p.get("auto_check")]


def enforce_lengths(plan):
    """Purane plans ke lambe parts ko publish se pehle 'sudhaar' queue me bhejo."""
    changed = False
    for p in plan.get("parts", []):
        if p.get("auto_check") and not p.get("published"):
            errs = length_errors(p) + term_errors(p) + trap_errors(p)
            if errs:
                p["auto_check"] = False
                p["check_errors"] = errs
                p["repair_tries"] = min(p.get("repair_tries", 0), MAX_REPAIR_TRIES - 2)
                changed = True
    if changed:
        save_plan(plan)
        print(f"  Clause {plan['clause_no']}: lambe parts chhote karne ke liye sudhaar me bheje.")
    return plan


def next_unpublished(plan):
    """(part, display_no, total) - plan ka pehla pakka part jo abhi publish nahi hua."""
    good = usable_parts(plan)
    for i, p in enumerate(good, 1):
        if not p.get("published"):
            return p, i, len(good)
    return None, 0, len(good)


def pending_repaired(current_clause):
    """Pichhle clauses ke sudhare gaye parts jo abhi publish nahi hue (inhe pehle mauka)."""
    for plan in all_plans():
        if plan["clause_no"] == current_clause:
            continue
        part, no, total = next_unpublished(plan)
        if part is not None and part.get("repaired"):
            return plan, part, no, total
    return None


def prepare_data(data, clause_no, part_no, total_parts=1, next_title="अगला नियम", syllabus=None):
    """Clean + options shuffle (pehle har baar A sahi hota tha - viewer pattern pakad leta tha)."""
    data = dict(data)
    data["syllabus"] = syllabus
    for k in ("hook", "question", "a", "b", "c", "d", "hint", "fact", "trap", "yaad"):
        if isinstance(data.get(k), str):
            data[k] = strip_brackets(data[k])
    data = {k: clean_text(v) if isinstance(v, str) else v for k, v in data.items()}
    for k in ("a", "b", "c", "d"):
        if not isinstance(data.get(k), str):
            data[k] = str(data.get(k) or "")
    correct_key = norm_correct(data.get("correct"))
    if correct_key not in ("A", "B", "C", "D"):
        # kabhi andaza nahi lagana (pehle yahan chup-chaap 'A' ban jaata tha)
        raise ValueError(f"'correct' samajh nahi aaya: {data.get('correct')!r}")
    rng = random.Random(clause_no * 1000 + part_no * 37 + 11)
    right = (data[correct_key.lower()], True, correct_key)
    wrongs = [(data[k.lower()], False, k) for k in "ABCD" if k != correct_key]
    rng.shuffle(wrongs)
    pos = (clause_no * 7 + part_no * 3) % 4          # sahi answer har reel me alag position pe
    items = wrongs[:pos] + [right] + wrongs[pos:]
    letters = "ABCD"
    data["options"] = [(letters[i], txt) for i, (txt, _, _) in enumerate(items)]
    ci = next(i for i, (_, ok, _) in enumerate(items) if ok)
    data["correct"] = letters[ci]
    data["correct_text"] = items[ci][0]
    for i, (txt, _, _) in enumerate(items):
        data[letters[i].lower()] = txt
    # English subtitle (sirf jaanch-pass English ho to); options ke naye kram ke saath
    en = data.get("en") if isinstance(data.get("en"), dict) else {}
    if SHOW_ENGLISH and en.get("ok"):
        data["en_opt"] = {letters[i]: clean_text(en.get(orig.lower(), "")) for i, (_, _, orig) in enumerate(items)}
        for k in ("question", "fact", "trap", "yaad"):
            data["en_" + k] = clean_text(en.get(k, ""))
    else:
        data["en_opt"] = {}
        for k in ("question", "fact", "trap", "yaad"):
            data["en_" + k] = ""
    wrong = [l for l, _ in data["options"] if l != data["correct"]]
    rng.shuffle(wrong)
    # HOOK ke liye 'A ya B?' jodi: sahi jawab + sabse zyada confuse karne wala galat option
    # (jo trap/hint me aata ho, warna pehla). Wahi 'bache do' me sabse aakhir me katega.
    def _overlap(txt):
        words = set(re.findall(r"[\w\u0900-\u097F]+", txt))
        ref = set(re.findall(r"[\w\u0900-\u097F]+", (data.get("trap") or "") + " " + (data.get("hint") or "")))
        return len(words & ref)
    confusing = max(wrong, key=lambda l: (_overlap(dict(data["options"])[l]), -wrong.index(l)))
    wrong = [l for l in wrong if l != confusing] + [confusing]
    data["elim_order"] = wrong
    pair = [data["correct_text"], dict(data["options"])[confusing]]
    if rng.random() < 0.5:
        pair.reverse()
    data["vs_pair"] = pair
    bt = data.get("beats") if isinstance(data.get("beats"), dict) else {}
    data["beat_items"] = ([{"text": clean_text(b["text"]), "mark": b["mark"]} for b in bt.get("items", [])]
                          if (SHOW_BEATS and bt.get("ok")) else [])
    letter_of = {txt: l for l, txt in data["options"]}
    data["en_vs"] = [data["en_opt"].get(letter_of.get(t_, ""), "") for t_ in pair]
    q = data.get("question", "")
    hk = (data.get("hook") or "").strip()
    if hk and not hk.endswith("?"):
        hk += "?"
    # chhota, bol-chaal wala sawal (3-9 shabd) pehle second me samajh aata hai; haan/na ('क्या ...')
    # wala hook A/B cards se mel nahi khaata, isliye wo nahi
    good_hook = bool(hk) and 3 <= words(hk) <= 9 and not re.match(r"^\s*क्या\s", hk)
    data["hook_short"] = good_hook
    data["hook_q"] = hk if good_hook else (q if words(q) <= 14 else (hk or q))
    data["clause_no"], data["part_no"] = clause_no, part_no
    data["total_parts"] = total_parts
    data["hl_words"] = [re.sub(r"[,.!?।:()]", "", w) for w in data["correct_text"].split() if len(w) > 1]
    data["next_title"] = clean_text(next_title) or "अगला नियम"
    if not data.get("yaad"):
        data["yaad"] = " ".join(data["fact"].split()[:8])
    # awaaz ke liye symbols ko shabd me
    # (samay '8:30' ka ':' nahi badalna - warna awaaz 'आठ, तीस' bolti)
    yv = data["yaad"].replace("=", ",").replace("+", " और ")
    yv = re.sub(r"(?<!\d):(?!\d)", ",", yv)
    yv = re.sub(r"\s+,", ",", " ".join(yv.split()))
    data["yaad_voice"] = yv
    return data


# ==================== STATE ====================

def load_state():
    state = {"clause_no": 1, "current_part": 1}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                state.update(saved)
        except Exception:
            pass
    try:
        state["clause_no"] = int(state["clause_no"])
        state["current_part"] = max(1, int(state["current_part"]))
    except (TypeError, ValueError):
        state = {"clause_no": 1, "current_part": 1}
    return state


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def next_clause_no(num, clause_numbers):
    """clause_numbers = syllabus order. Current ke baad wala; aakhir me wapas pehla."""
    later = [n for n in clause_numbers if n > num]
    return later[0] if later else clause_numbers[0]


# ==================== SCENE SCRIPT (voice segments) ====================

def build_scene_specs(data):
    """
    tail = voice khatam hone ke baad scene kitni der ruke (info ko 'absorb' karne ka time)
    min  = scene ki kam se kam lambai
    Rule: jo info screen pe PADHNI hai (options) usko hold milta hai,
          jo sirf SUNNI hai (hook, reveal) uske baad turant agla scene.
    """
    pair_line = f"{data['vs_pair'][0]}, या {data['vs_pair'][1]}?"
    if data.get("hook_short"):
        hook_segs = [("hook", data["hook_q"]), ("vs", pair_line)]      # pehle sawal, fir A ya B
    else:
        hook_segs = [("vs", pair_line), ("hook", "सही कौन?")]
    specs = [
        {"name": "hook", "mood": "red", "tail": 0.15, "min": 2.2, "segs": hook_segs},
        {"name": "question", "mood": "blue", "tail": 0.35, "min": 2.6,
         "segs": ([("q", "चारों में से सही कौन सा?"), ("lock", "जवाब कमेंट कीजिए!")] if MERGE_COUNTDOWN
                  else [("q", "चारों में से सही कौन सा?")])},
        {"name": "countdown", "mood": "purple", "tail": 0.0,
         "min": COUNTDOWN_SECONDS * COUNTDOWN_STEP + 0.35,
         "segs": [("lock", "जवाब कमेंट कीजिए!")]},
        {"name": "hint", "mood": "yellow", "tail": 0.2, "min": 2.0,
         "segs": [("hint", (data.get("hint") or ""))], "read": [("hint", (data.get("hint") or ""))]},
        {"name": "eliminate", "mood": "red", "tail": 0.2, "min": 2.4,
         "segs": [("x1", "ये नहीं,"), ("x2", "ये भी नहीं,"),
                  ("left", "बचे दो..."), ("x3", "ये भी नहीं!")]},
        {"name": "reveal", "mood": "green", "tail": 0.45, "min": 1.7,
         "segs": [("rev", f"सही जवाब, {data['correct']}!")]},
        {"name": "rule", "mood": "blue", "tail": 0.3, "min": 0,
         "segs": [("fact", data["fact"]), ("trapx", "ट्रैप:"), ("trap", data["trap"])],
         "read": [("trap", data["trap"])]},
        {"name": "cta", "mood": "purple", "tail": 1.6, "min": 3.4,
         "segs": [("yaad", "याद रखिए, " + data["yaad_voice"] + "।"),
                  ("mock", "फ्री मॉक टेस्ट के लिए कमेंट कीजिए, मॉक।")],
         "read": [("yaad", data["yaad"])]},
    ]
    if MERGE_COUNTDOWN:
        specs = [sp for sp in specs if sp["name"] != "countdown"]
    if not SHOW_HINT:
        specs = [sp for sp in specs if sp["name"] != "hint"]
    elif hint_leaks(data):
        print("  Hint me jawab khul raha tha -> hint scene hataya (suspense + time bachat)")
        specs = [sp for sp in specs if sp["name"] != "hint"]
    return specs


def hint_leaks(data):
    """Hint me sahi jawab ke khaas shabd/sankhya ho to wo jawab bata deta hai."""
    hint = (data.get("hint") or "")
    key = [w for w in re.findall(r"[\w\u0900-\u097F]+", data.get("correct_text", "")) if len(w) > 2 or w.isdigit()]
    common = {"और", "के", "का", "की", "में", "से", "पर", "है", "हैं", "डाकघर", "डाक"}
    key = [w for w in key if w not in common]
    return any(w in hint for w in key)


def seg_weight(text):
    return len(text.replace(" ", "")) + 4 * len(re.findall(r"[,.!?।]", text)) + 2


def _proportional_word_times(segs, voice_dur):
    """Fallback: word timing andaze se (DRY_RUN / boundary na mile tab)."""
    words = []
    for key, text in segs:
        for w in text.split():
            words.append((key, w))
    th = word_thresholds([w for _, w in words])
    return [(key, w, voice_dur * t) for (key, w), t in zip(words, th)]


def _exact_word_times(segs, boundaries, voice_dur):
    """edge-tts WordBoundary -> har display-word ka asli start time."""
    full, spans = "", []
    for key, text in segs:
        if full:
            full += " "
        for m in re.finditer(r"\S+", text):
            spans.append((key, m.group(), len(full) + m.start(), len(full) + m.end()))
        full += text

    known = {}
    ptr = 0
    for start, _end, wtext in boundaries:
        wtext = (wtext or "").strip()
        if not wtext:
            continue
        pos = full.find(wtext, ptr)
        if pos < 0:
            continue
        ptr = pos + len(wtext)
        for i, (_, _, a, b) in enumerate(spans):
            if a <= pos < b and i not in known:
                known[i] = start
                break

    if len(known) < 2:
        return None
    idx = sorted(known)
    xs = np.array(idx, dtype=float)
    ys = np.array([known[i] for i in idx], dtype=float)
    ys = np.maximum.accumulate(ys)
    all_t = np.interp(np.arange(len(spans)), xs, ys)
    return [(key, w, float(min(t, voice_dur))) for (key, w, _, _), t in zip(spans, all_t)]


def compute_marks(segs, voice_dur, boundaries=None):
    """Returns marks {key: (start, end)} aur word_times {key: [start per word]}."""
    wt = _exact_word_times(segs, boundaries, voice_dur) if boundaries else None
    if wt is None:
        wt = _proportional_word_times(segs, voice_dur)
    keys = [k for k, _ in segs]
    word_times = {k: [t for kk, _, t in wt if kk == k] for k in keys}
    marks = {}
    for i, k in enumerate(keys):
        st = word_times[k][0] if word_times[k] else 0.0
        nxt = None
        for k2 in keys[i + 1:]:
            if word_times[k2]:
                nxt = word_times[k2][0]
                break
        marks[k] = (st, nxt if nxt is not None else voice_dur)
    return marks, word_times


def seg_progress(sc, key, t):
    """Kinetic text ke liye: (p, thresholds) exact word timing ke saath."""
    s0, s1 = sc["marks"][key]
    span = max(0.1, s1 - s0)
    th = [clamp((w - EYE_LEAD - s0) / span) for w in sc["wt"][key]]
    return clamp((t - s0) / span), th


# ==================== AUDIO: TTS ====================

async def tts_save(text, path):
    """MP3 save karta hai aur har word ka (start, end, text) lautata hai."""
    import edge_tts
    last = None
    for attempt in range(4):
        try:
            try:
                com = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate=VOICE_RATE,
                                           pitch=VOICE_PITCH, boundary="WordBoundary")
            except TypeError:  # purana edge-tts: boundary param nahi hota, default WordBoundary
                com = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate=VOICE_RATE, pitch=VOICE_PITCH)
            words = []
            with open(path, "wb") as f:
                async for chunk in com.stream():
                    if chunk.get("type") == "audio":
                        f.write(chunk["data"])
                    elif chunk.get("type") == "WordBoundary":
                        st = chunk["offset"] / 1e7
                        words.append((st, st + chunk["duration"] / 1e7, chunk.get("text", "")))
            if os.path.getsize(path) > 1000:
                return words
        except Exception as exc:
            last = exc
        await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"TTS fail: {last}")


def decode_raw(path, trim=False):
    af = ["-af", ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                  "silenceremove=start_periods=1:start_threshold=-45dB,areverse")] if trim else []
    cmd = ["ffmpeg", "-v", "error", "-i", path, *af, "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if len(arr) < SR * 0.2:
        raise RuntimeError(f"Voice file khali hai: {path}")
    return arr


HOOK_MAX_PAUSE = 0.06          # pehle 2 sec me chuppi = skip; hook me har ruk sirf 0.06s


def tighten_voice(arr, words, max_pause=None):
    """
    Har chuppi ko MAX_PAUSE tak kaat deta hai aur word timings ko usi hisaab se shift karta hai.
    Yahi 46s -> ~30s ka sabse bada fix hai (TTS comma/full-stop pe 0.4-0.6s rukta hai).
    """
    if not words:
        return arr, None
    MAXP = MAX_PAUSE if max_pause is None else max_pause
    words = sorted(words)
    keep = []                 # (src_start, src_end) seconds
    new_words = []
    out_t = 0.0
    cur = max(0.0, words[0][0] - 0.03)
    for i, (ws, we, wt) in enumerate(words):
        if i > 0:
            prev_end = max(words[i - 1][1], cur)
            gap = ws - prev_end
            if gap > MAXP:
                keep.append((cur, prev_end + MAXP / 2))
                out_t += prev_end + MAXP / 2 - cur
                cur = ws - MAXP / 2
        new_words.append((out_t + (ws - cur), out_t + (we - cur), wt))
    tail_end = min(len(arr) / SR, words[-1][1] + 0.12)
    keep.append((cur, tail_end))

    fade = int(0.006 * SR)
    pieces = []
    for a, b in keep:
        seg = arr[int(a * SR):int(b * SR)].copy()
        if len(seg) > 2 * fade:
            seg[:fade] *= np.linspace(0, 1, fade)
            seg[-fade:] *= np.linspace(1, 0, fade)
        pieces.append(seg)
    out = np.concatenate(pieces) if pieces else arr
    return out.astype(np.float32), new_words


# ==================== AUDIO: GEMINI TTS (pehli priority) ====================

GEMINI_TTS_INSTRUCTION = ("Read the following Hindi lines aloud in a clear, energetic teacher voice at a brisk pace. "
                          "Read only the lines, exactly as written, nothing else. "
                          "After every line, pause for one full second.")
VOICE_TEST_LINE = "GDS साथियों, आज का सवाल बहुत ज़रूरी है। मोबाइल डाकघर में कौन सी वस्तुएं बुक नहीं होतीं? सोचिए, फिर जवाब देखिए।"


def _model_ver(n):
    m = re.match(r"gemini-(\d+)(?:\.(\d+))?", n or "")
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)


def gemini_tts_candidates():
    """Chalu TTS models, sabse behtar pehle (3.8-flash-tts > 3.8-flash-lite-tts > 3.1 > 2.5)."""
    if os.getenv("GEMINI_TTS_MODEL"):
        return [os.getenv("GEMINI_TTS_MODEL")]
    names = [n for n in _gemini_model_names() if "tts" in n and n.startswith("gemini-")
             and not any(b in n for b in ("live", "native"))]
    ranked = sorted(names, key=lambda n: (_model_ver(n), "lite" not in n, "preview" not in n, "flash" in n),
                    reverse=True)
    return ranked or ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.1-flash-tts-preview"]


def _new_style_tts(model):
    """3.8+ : text shabdashah padha jaata hai, style alag field me, pause ke liye <long pause> tag."""
    return _model_ver(model) >= (3, 8)


_VOICE_CACHE = {}
PREBUILT_VOICES = {"Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe", "Autonoe",
                   "Enceladus", "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi",
                   "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird",
                   "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat"}


def list_hindi_voices(gender=None):
    """
    Gemini Extended Voice Library se native Hindi awaazein, sabse natural pehle.
    gender diya ho ('male'/'female') to sirf wahi. Returns [(score, id, naam, gender, vivaran)].
    """
    if "hi" not in _VOICE_CACHE:
        allv = []
        try:
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/voices", timeout=60,
                             params={"key": GEMINI_API_KEY.strip(), "language_code": "hi-IN", "page_size": 200})
            if r.status_code == 200:
                for v in r.json().get("voices", []) or []:
                    vid = v.get("id") or v.get("name") or ""
                    if not vid:
                        continue
                    blob = " ".join(str(v.get(k, "")) for k in
                                    ("display_name", "displayName", "description", "persona", "contexts",
                                     "context", "accent", "pitch")).lower()
                    score = 3 * any(w in blob for w in ("conversational", "education", "teacher", "narrat", "explainer"))
                    score += 2 * any(w in blob for w in ("warm", "friendly", "natural", "casual", "engaging"))
                    score += 2 * any(w in blob for w in ("standard hindi", "clear", "neutral accent", "delhi"))
                    score -= 3 * any(w in blob for w in ("whisper", "robot", "villain", "child", "elderly", "news"))
                    # boli (dialect) aur 'assistant' jaisi awaazein reel ke liye nahi (shuddh, insaani Hindi chahiye)
                    score -= 6 * any(w in blob for w in ("awadhi", "bhojpuri", "maithili", "magahi", "haryanvi",
                                                         "rajasthani", "chhattisgarhi", "bundeli", "marwari",
                                                         "dialect", "assistant", "digital"))
                    m_age = re.search(r"(\d{2})-year-old", blob)
                    if m_age and not (22 <= int(m_age.group(1)) <= 45):
                        score -= 2
                    allv.append((score, vid, v.get("display_name") or v.get("displayName") or vid,
                                 str(v.get("gender", "")).lower(), (v.get("description") or "")[:90]))
            else:
                print(f"  Hindi voice list nahi mili ({r.status_code})")
        except Exception as exc:
            print("  Hindi voice list nahi mili:", str(exc)[:120])
        allv.sort(key=lambda x: -x[0])
        _VOICE_CACHE["hi"] = allv
    allv = _VOICE_CACHE["hi"]
    if gender:
        g = gender.lower()[:1]
        return [v for v in allv if v[3][:1] == g]
    return allv


_CURRENT = {"voice": None, "gender": None, "name": None, "used": None}
STANDARD_BACKUP = [("Charon", "Charon", "male", "Informative"), ("Sulafat", "Sulafat", "female", "Warm"),
                   ("Achird", "Achird", "male", "Friendly"), ("Aoede", "Aoede", "female", "Breezy"),
                   ("Sadaltager", "Sadaltager", "male", "Knowledgeable"), ("Kore", "Kore", "female", "Firm")]


def rotation_active():
    return VOICE_ROTATION and USE_GEMINI_TTS and not (GEMINI_TTS_VOICE and GEMINI_TTS_VOICE.lower() != "auto")


def build_voice_rotation(state):
    """
    5 awaazon ki pakki list (pehli baar banke state me save; test ke beech nahi badalti).
    Hindi library ki behtareen shuddh-Hindi awaazein, male/female baari-baari; kam hon to standard.
    """
    if state.get("voice_rotation"):
        return state["voice_rotation"]
    males = [(v[1], v[2], "male", v[4]) for v in list_hindi_voices("male") if v[0] > -3]
    females = [(v[1], v[2], "female", v[4]) for v in list_hindi_voices("female") if v[0] > -3]
    rot, i = [], 0
    while len(rot) < ROTATION_SIZE and (i < len(males) or i < len(females)):
        for grp in (males, females):
            if i < len(grp) and len(rot) < ROTATION_SIZE:
                rot.append(grp[i])
        i += 1
    for b in STANDARD_BACKUP:
        if len(rot) >= ROTATION_SIZE:
            break
        if b[0] not in [r[0] for r in rot]:
            rot.append(b)
    rot = [{"id": a, "name": b, "gender": c, "desc": (d or "")[:80]} for a, b, c, d in rot[:ROTATION_SIZE]]
    state["voice_rotation"] = rot
    state.setdefault("voice_idx", 0)
    print("Awaaz rotation (test):", ", ".join(f"{r['name']} ({r['gender']})" for r in rot))
    return rot


def apply_voice(entry):
    """Is reel ki Gemini awaaz set karo. Gemini poori tarah fail ho to fallback hamesha Swara (edge-tts)."""
    global GEMINI_TTS_FALLBACK_VOICE
    male = entry["gender"].startswith("m")
    _CURRENT.update({"voice": entry["id"], "gender": entry["gender"], "name": entry["name"], "used": None})
    GEMINI_TTS_FALLBACK_VOICE = "Charon" if male else "Sulafat"      # sirf purane Gemini models ke liye


def log_voice(out, entry, num, part_no):
    import csv
    import datetime
    path = os.path.join(OUTPUT_DIR, "voice_log.csv")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "reel", "clause", "part", "awaaz", "gender", "voice_id", "asal_me_chali",
                        "views", "skip_rate", "avg_watch_sec", "likes", "shares", "saves"])
        w.writerow([datetime.date.today().isoformat(), os.path.basename(out), num, part_no, entry["name"],
                    entry["gender"], entry["id"], _CURRENT.get("used") or "", "", "", "", "", "", ""])


def pick_gemini_voice():
    if _CURRENT.get("voice"):
        return _CURRENT["voice"]
    if GEMINI_TTS_VOICE and GEMINI_TTS_VOICE.lower() != "auto":
        return GEMINI_TTS_VOICE
    if "pick" in _VOICE_CACHE:
        return _VOICE_CACHE["pick"]
    hv = list_hindi_voices(GEMINI_TTS_GENDER)
    pick = hv[0][1] if hv else GEMINI_TTS_FALLBACK_VOICE
    if hv:
        print(f"  Awaaz chuni ({GEMINI_TTS_GENDER}): {hv[0][2]} ({hv[0][1]}) - {hv[0][4]}")
    _VOICE_CACHE["pick"] = pick
    return pick


def _pcm_to_array(b64, mime):
    import base64
    import io
    raw = base64.b64decode(b64)
    m = re.search(r"rate=(\d+)", mime or "")
    rate = int(m.group(1)) if m else 24000
    if raw[:4] == b"RIFF":                                   # 3.8 default WAV (header ke saath)
        with wave.open(io.BytesIO(raw)) as wf:
            rate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
    pcm = np.frombuffer(raw[: len(raw) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
    if rate != SR and len(pcm):
        x_new = np.arange(int(len(pcm) * SR / rate)) * (rate / SR)
        pcm = np.interp(x_new, np.arange(len(pcm)), pcm).astype(np.float32)
    return pcm


def _find_audio(obj):
    """Jawab JSON me kahin bhi audio (base64) dhoondho - generateContent aur Interactions dono ke liye."""
    if isinstance(obj, dict):
        mime = obj.get("mimeType") or obj.get("mime_type") or ""
        if isinstance(obj.get("data"), str) and len(obj["data"]) > 1000 and (not mime or "audio" in mime):
            return obj["data"], mime
        for key in ("inlineData", "inline_data", "output_audio", "outputAudio", "audio"):
            if key in obj:
                got = _find_audio(obj[key])
                if got:
                    return got
        for v in obj.values():
            got = _find_audio(v)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_audio(v)
            if got:
                return got
    return None


def _tts_bodies(model, lines, voice):
    """Model ke hisaab se request ke roop, sabse sahi pehle."""
    base = "https://generativelanguage.googleapis.com/v1beta"
    gen_url = f"{base}/models/{model}:generateContent"
    if _new_style_tts(model):
        script = " <long pause> ".join(lines)          # 3.8: shabdashah text + pause tag
        return [
            (gen_url, {"contents": [{"role": "user", "parts": [{"text": script,
                                                                 "speech_metadata": {"style": GEMINI_TTS_STYLE}}]}],
                       "generationConfig": {"responseModalities": ["AUDIO"],
                                            "speechConfig": {"voiceConfig": {"voice": voice}}}}),
            (f"{base}/interactions", {
                "model": model,
                "input": [{"type": "user_input", "content": [{
                    "type": "text", "text": script,
                    "annotations": [{"type": "speech_metadata", "style": GEMINI_TTS_STYLE}]}]}],
                "response_format": {"type": "audio"},
                "generation_config": {"speech_config": [{"voice": voice}]}}),
        ]
    script = "\n".join(lines)                          # purane: instruction + har line alag
    return [
        (gen_url, {"contents": [{"parts": [{"text": GEMINI_TTS_INSTRUCTION + "\n\n" + script}]}],
                   "generationConfig": {"responseModalities": ["AUDIO"],
                                        "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}),
    ]


def gemini_tts_audio(lines, voice=None):
    """Poori script (har scene ek line) EK request me. Returns float32 array @ SR."""
    voice = voice or pick_gemini_voice()
    last = None
    for model in gemini_tts_candidates():
        # purane models sirf 30 standard voices jaante hain -> library ki Hindi voice unke liye nahi
        v = voice if (_new_style_tts(model) or voice in PREBUILT_VOICES) else GEMINI_TTS_FALLBACK_VOICE
        for url, body in _tts_bodies(model, lines, v):
            try:
                r = requests.post(url, params={"key": GEMINI_API_KEY.strip()}, json=body, timeout=300)
            except requests.RequestException as exc:
                last = exc
                break
            low = r.text[:400].lower()
            if r.status_code in (401, 403) or (r.status_code == 400 and ("api key" in low or "api_key" in low)):
                raise RuntimeError(f"GEMINI_API_KEY galat/band ({r.status_code})")
            if r.status_code in (400, 404) and not url.endswith("/interactions"):
                last = RuntimeError(f"{model} {r.status_code}: {r.text[:150]}")
                continue                              # doosra roop (jaise Interactions API)
            if r.status_code != 200:
                last = RuntimeError(f"{model} {r.status_code}: {r.text[:120]}")
                print(f"  Gemini TTS {model}: {r.status_code} -> agla")
                break
            try:
                got = _find_audio(r.json())
                if got:
                    arr = _pcm_to_array(*got)
                    if len(arr) > SR * 0.5:
                        print(f"  Gemini TTS: {model}, awaaz {v}, {len(arr) / SR:.1f}s")
                        return arr
                last = RuntimeError(f"{model}: audio nahi mila")
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                last = exc
    raise RuntimeError(f"Gemini TTS nahi bani: {last}")


def make_voice_test():
    """
    Ek baar: ek hi Hindi line top Hindi-library voices + kuch standard voices me.
    generated_reels/voice_test/ me .wav - sun ke GEMINI_TTS_VOICE me pasand ki voice likhiye.
    """
    out_dir = os.path.join(OUTPUT_DIR, "voice_test")
    if DRY_RUN or not (USE_GEMINI_TTS and GEMINI_API_KEY):
        return None
    marker = os.path.join(out_dir, "MALE_TEST_DONE.txt")
    if os.path.exists(marker):
        print("Voice test pehle se bana hai (dobara chahiye to generated_reels/voice_test delete kijiye)")
        return None
    if os.path.isdir(out_dir):
        # pichhle version ka (female/mixed) test ho sakta hai -> hata ke naya male test
        import shutil
        shutil.rmtree(out_dir, ignore_errors=True)
    # sirf PURUSH (male) awaazein: Hindi library ki top 4 + 5 standard
    cands = [(vid, name, f"PURUSH, Hindi library - {desc}") for _, vid, name, _, desc in list_hindi_voices("male")[:4]]
    cands += [(v, v, d) for v, d in (("Charon", "PURUSH, standard - Informative"),
                                     ("Sadaltager", "PURUSH, standard - Knowledgeable"),
                                     ("Achird", "PURUSH, standard - Friendly"),
                                     ("Iapetus", "PURUSH, standard - Clear"),
                                     ("Puck", "PURUSH, standard - Upbeat"))]
    os.makedirs(out_dir, exist_ok=True)
    notes = ["Sab PURUSH (male) awaazein. Har file sun ke sabse insaani awaaz chuniye. Fir main.py me:",
             '  GEMINI_TTS_VOICE = "..."      <- us awaaz ka VOICE naam/ID',
             '  GEMINI_TTS_GENDER = "male"    <- us awaaz ka gender (Gemini fail ho to Swara hi aayegi)', ""]
    for k, (vid, name, desc) in enumerate(cands, 1):
        try:
            arr = gemini_tts_audio([VOICE_TEST_LINE], voice=vid)
        except Exception as exc:
            notes.append(f"{k:02d}. {name}: nahi bani ({str(exc)[:80]})")
            continue
        tag = "M" if "PURUSH" in desc else "F"
        safe = tag + "_" + re.sub(r"[^A-Za-z0-9]+", "_", name)[:30]
        path = os.path.join(out_dir, f"{k:02d}_{safe}.wav")
        pcm = (np.clip(arr, -1, 1) * 32767).astype(np.int16)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SR)
            wf.writeframes(pcm.tobytes())
        notes.append(f"{k:02d}. {name}  ->  VOICE = {vid}   ({desc})")
    with open(os.path.join(out_dir, "VOICES.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(notes))
    if any(fn.endswith(".wav") for fn in os.listdir(out_dir)):
        with open(marker, "w", encoding="utf-8") as f:
            f.write("male voice test bana")
    return out_dir


def _silence_runs(arr, min_gap, rel_db=-32.0):
    """Chuppi ke hisse (sec): [(start, end)] jo min_gap se lambe hon."""
    hop = int(SR * 0.01)
    n = len(arr) // hop
    if n < 3:
        return []
    fr = arr[: n * hop].reshape(n, hop)
    rms = np.sqrt((fr ** 2).mean(axis=1) + 1e-12)
    ref = np.percentile(rms, 95)
    if ref <= 1e-6:
        return []
    silent = rms < ref * (10 ** (rel_db / 20))
    runs, st = [], None
    for k, sflag in enumerate(silent):
        if sflag and st is None:
            st = k
        elif not sflag and st is not None:
            runs.append((st * 0.01, k * 0.01))
            st = None
    if st is not None:
        runs.append((st * 0.01, n * 0.01))
    return [(a, b) for a, b in runs if b - a >= min_gap]


def _pick_cuts(gaps, expected, total):
    """Har ummeed wali jagah ke liye ek chuppi chuno (kram me, sabse paas + lambi chuppi ko pasand)."""
    n, m = len(expected), len(gaps)
    if n == 0:
        return []
    if m < n:
        return None
    mids = [(a + b) / 2 for a, b in gaps]
    lens = [b - a for a, b in gaps]
    INF = float("inf")
    cost = [[INF] * m for _ in range(n)]
    back = [[-1] * m for _ in range(n)]
    for j in range(m):
        cost[0][j] = abs(mids[j] - expected[0]) / total - 0.15 * min(lens[j], 1.0)
    for i in range(1, n):
        best, bk = INF, -1
        for j in range(m):
            if j - 1 >= 0 and cost[i - 1][j - 1] < best:
                best, bk = cost[i - 1][j - 1], j - 1
            if best < INF:
                cost[i][j] = best + abs(mids[j] - expected[i]) / total - 0.15 * min(lens[j], 1.0)
                back[i][j] = bk
    j = min(range(m), key=lambda x: cost[n - 1][x])
    if cost[n - 1][j] == INF:
        return None
    chosen = []
    for i in range(n - 1, -1, -1):
        chosen.append(j)
        j = back[i][j]
    chosen.reverse()
    return [gaps[k] for k in chosen]


def _speech_bounds(arr):
    runs = _silence_runs(arr, 0.0)
    a, b = 0.0, len(arr) / SR
    if runs and runs[0][0] <= 0.01:
        a = runs[0][1]
    if runs and runs[-1][1] >= b - 0.02:
        b = runs[-1][0]
    return max(0.0, a - 0.03), min(len(arr) / SR, b + 0.08)


def _compress_pauses(arr, max_pause=None):
    """Lambi chuppi ko max_pause tak chhota karo. Returns (naya audio, purana_samay -> naya_samay)."""
    max_pause = MAX_PAUSE if max_pause is None else max_pause
    runs = _silence_runs(arr, max_pause + 0.02)
    keep, cur = [], 0.0
    for a, b in runs:
        keep.append((cur, a + max_pause / 2))
        cur = b - max_pause / 2
    keep.append((cur, len(arr) / SR))
    fade = int(0.006 * SR)
    pieces = []
    for a, b in keep:
        seg = arr[int(a * SR):int(b * SR)].copy()
        if len(seg) > 2 * fade:
            seg[:fade] *= np.linspace(0, 1, fade)
            seg[-fade:] *= np.linspace(1, 0, fade)
        pieces.append(seg)

    def remap(t):
        out = 0.0
        for a, b in keep:
            if t <= a:
                break
            out += min(t, b) - a
        return out
    return (np.concatenate(pieces) if pieces else arr).astype(np.float32), remap


def _durations_ok(bounds, weights, total, lo=0.4, hi=2.5):
    wsum = float(sum(weights)) or 1.0
    for (a, b), w in zip(bounds, weights):
        exp = total * w / wsum
        if b - a < 0.3 or not (lo * exp <= (b - a) <= hi * exp):
            return False
    return True


def split_gemini_audio(full, specs):
    """
    Ek lambi awaaz ko scenes me kaato (line ke beech ki ~1 sec chuppi se), aur har scene ke andar
    segments (jaise 'ये नहीं, ये भी नहीं') ki shuruaat dhoondho. Kuch bhi shak ho -> None (fallback).
    """
    lead, tail = _speech_bounds(full)
    full = full[int(lead * SR):int(tail * SR)]
    total = len(full) / SR
    weights = [seg_weight(" ".join(t for _, t in sp["segs"])) for sp in specs]
    wsum = float(sum(weights))
    acc, expected = 0.0, []
    for w in weights[:-1]:
        acc += w
        expected.append(total * acc / wsum)
    gaps = _silence_runs(full, 0.35)
    chosen = _pick_cuts(gaps, expected, total)
    if chosen is None:
        print(f"  Gemini awaaz: scenes ke beech ruk nahi mile ({len(gaps)} chuppi, {len(expected)} chahiye)")
        return None
    edges = [0.0] + [(a + b) / 2 for a, b in chosen] + [total]
    bounds = list(zip(edges[:-1], edges[1:]))
    if not _durations_ok(bounds, weights, total):
        print("  Gemini awaaz: scenes ki lambai script se mel nahi khaati (shayad instruction bhi bol di)")
        return None

    out = []
    for sp, (a, b) in zip(specs, bounds):
        chunk = full[int(a * SR):int(b * SR)]
        s0, s1 = _speech_bounds(chunk)
        chunk = chunk[int(s0 * SR):int(s1 * SR)]
        segs = sp["segs"]
        seg_starts = None
        if len(segs) > 1:
            cl = len(chunk) / SR
            sw = [seg_weight(t) for _, t in segs]
            ssum = float(sum(sw))
            acc2, exp2 = 0.0, []
            for w in sw[:-1]:
                acc2 += w
                exp2.append(cl * acc2 / ssum)
            inner = _pick_cuts(_silence_runs(chunk, 0.08), exp2, cl)
            if inner is not None:
                st = [0.0] + [g[1] for g in inner]
                sb = list(zip(st, st[1:] + [cl]))
                if _durations_ok(sb, sw, cl, 0.25, 4.0):
                    seg_starts = st
        chunk, remap = _compress_pauses(chunk, HOOK_MAX_PAUSE if sp["name"] == "hook" else None)
        if seg_starts:
            seg_starts = [remap(t) for t in seg_starts]
        out.append((chunk, None, seg_starts))
    return out


def marks_from_seg_starts(segs, starts, voice_dur):
    """Segments ki asli shuruaat (chuppi se mili) + unke andar shabd anupaat se."""
    keys = [k for k, _ in segs]
    marks, word_times = {}, {}
    for i, (key, text) in enumerate(segs):
        a = starts[i]
        b = starts[i + 1] if i + 1 < len(starts) else voice_dur
        marks[key] = (a, b)
        ws = text.split()
        th = word_thresholds(ws) if ws else []
        word_times[key] = [a + (b - a) * x for x in th]
    return marks, {k: word_times.get(k, []) for k in keys}


def make_voices(specs):
    """
    Returns list of (audio, word_boundaries_or_None, seg_starts_or_None).
    1) Gemini TTS: poori script ek request me, fir chuppi se scenes me kaati jaati hai.
    2) Kuch bhi gadbad (quota, block, galat kataai) -> edge-tts (Swara), har scene alag.
    """
    if DRY_RUN:
        out = []
        for sp in specs:
            text = " ".join(t for _, t in sp["segs"])
            est = max(0.6, seg_weight(text) * 0.058)
            out.append((np.zeros(int(est * SR), dtype=np.float32), None, None))
        return out

    if USE_GEMINI_TTS and GEMINI_API_KEY:
        try:
            lines = [" ".join(t for _, t in sp["segs"]) for sp in specs]
            full = gemini_tts_audio(lines)
            res = split_gemini_audio(full, specs)
            if res:
                inner = sum(1 for r in res if r[2])
                print(f"Awaaz: Gemini TTS (ek baar me poori) - {len(res)} scenes, {inner} me andar ka sync mila")
                _CURRENT["used"] = "Gemini: " + (_CURRENT.get("name") or pick_gemini_voice())
                return res
            print("Gemini awaaz sahi scenes me nahi kati -> edge-tts (Swara)")
        except Exception as exc:
            print(f"Gemini TTS nahi chala ({str(exc)[:160]}) -> edge-tts (Swara)")

    voices = []
    for i, sp in enumerate(specs):
        text = " ".join(t for _, t in sp["segs"])
        path = f"_voice_{i}.mp3"
        words = asyncio.run(tts_save(text, path))
        if words:
            arr, words = tighten_voice(decode_raw(path), words,
                                       HOOK_MAX_PAUSE if sp["name"] == "hook" else None)
        else:
            print(f"  (scene {sp['name']}: word timing nahi mila, andaze se timing)")
            arr, words = decode_raw(path, trim=True), None
        voices.append((arr, words, None))
        os.remove(path)
    print(f"Awaaz: edge-tts ({VOICE_NAME})")
    _CURRENT["used"] = "edge-tts: " + VOICE_NAME
    return voices


# ==================== AUDIO: SFX (synthesized, no downloads) ====================

def _t(d):
    return np.arange(int(d * SR)) / SR


def sfx_whoosh(d=0.35, amp=0.35):
    rng = np.random.default_rng(1)
    n = rng.normal(0, 1, int(d * SR)).astype(np.float32)
    out = np.zeros_like(n)
    y = 0.0
    ln = len(n)
    for i in range(ln):
        k = 0.02 + 0.25 * math.sin(math.pi * i / ln)
        y += k * (n[i] - y)
        out[i] = y
    env = np.sin(np.linspace(0, math.pi, ln)) ** 2
    return out * env * amp * 2.2


def sfx_pop(amp=0.4):
    t = _t(0.09)
    f = 900 - 5000 * t
    return np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 40) * amp


def sfx_tick(amp=0.35):
    t = _t(0.04)
    return np.sin(2 * math.pi * 2200 * t) * np.exp(-t * 120) * amp


def sfx_buzz(amp=0.3):
    t = _t(0.28)
    sq = np.sign(np.sin(2 * math.pi * 110 * t)) * 0.6 + np.sin(2 * math.pi * 55 * t) * 0.4
    return sq * np.exp(-t * 6) * amp


def sfx_ding(amp=0.4):
    t = _t(1.1)
    s = (np.sin(2 * math.pi * 1318.5 * t) + 0.6 * np.sin(2 * math.pi * 1975.5 * t)
         + 0.3 * np.sin(2 * math.pi * 2637 * t))
    return s * np.exp(-t * 4.5) * amp / 1.9


def sfx_thud(amp=0.7):
    t = _t(0.45)
    f = 90 - 60 * t
    s = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    rng = np.random.default_rng(2)
    s[:600] += rng.normal(0, 0.5, 600) * np.exp(-np.arange(600) / 120)
    return s * amp


def sfx_riser(d=1.0, amp=0.18):
    t = _t(d)
    f = 200 + 700 * (t / d) ** 2
    rng = np.random.default_rng(4)
    s = np.sin(2 * math.pi * np.cumsum(f) / SR) * 0.6 + rng.normal(0, 0.25, len(t))
    return s * (t / d) ** 2 * amp


def sfx_heartbeat(amp=0.45):
    b = sfx_thud(amp)
    out = np.zeros(int(0.5 * SR), dtype=np.float64)
    n = min(len(b), len(out))
    out[:n] += b[:n]
    s = int(0.18 * SR)
    n2 = min(len(b), len(out) - s)
    out[s:s + n2] += b[:n2] * 0.7
    return out


def music_bed(total):
    """Halka tension pad + soft pulse (copyright-free, code se bana)."""
    t = np.arange(int(total * SR)) / SR
    chord = [110.0, 164.81, 220.0, 261.63]
    pad = sum(np.sin(2 * math.pi * f * t + i) for i, f in enumerate(chord)) / len(chord)
    lfo = 0.6 + 0.4 * np.sin(2 * math.pi * 0.25 * t)
    pulse = np.sin(2 * math.pi * 55 * t) * np.exp(-((t % 0.5) * 14))
    return (pad * lfo * 0.05 + pulse * 0.05).astype(np.float32)


def add_at(buf, clip, t_sec, gain=1.0):
    s = int(t_sec * SR)
    if s >= len(buf) or s < 0:
        return
    e = min(len(buf), s + len(clip))
    buf[s:e] += (clip[:e - s] * gain).astype(np.float32)


def build_audio(voices, timeline, total, out_path):
    n = int(total * SR) + SR
    buf = np.zeros(n, dtype=np.float32)
    voice_track = np.zeros(n, dtype=np.float32)
    for sc, voice in zip(timeline, voices):
        add_at(voice_track, voice[0], sc["start"] + VOICE_LEAD)

    # ducking: voice ke time music neeche
    env = np.abs(voice_track)
    win = int(0.15 * SR)
    env = np.convolve(env, np.ones(win, dtype=np.float32) / win, mode="same")
    duck = 1.0 - np.clip(env * 6, 0, 0.6)
    bed = music_bed(n / SR)
    m = min(len(bed), n)
    buf[:m] += bed[:m] * duck[:m]

    whoosh = sfx_whoosh()
    for sc in timeline:
        s, mk, name = sc["start"], sc["marks"], sc["name"]
        if sc["index"] > 0:
            add_at(buf, whoosh, max(0.0, s - 0.12), 0.8)
        if name == "hook":
            add_at(buf, sfx_pop(0.5), s + 0.02)
            add_at(buf, sfx_thud(0.9), s + sc["stamp_t"])
        elif name == "question":
            for ot in sc["opt_t"]:
                add_at(buf, sfx_pop(0.35), s + ot)
            if "cd_start" in sc:
                c0 = sc["cd_start"]
                for k in range(COUNTDOWN_SECONDS):
                    add_at(buf, sfx_tick(0.5), s + c0 + k * COUNTDOWN_STEP)
                    add_at(buf, sfx_heartbeat(0.45), s + c0 + k * COUNTDOWN_STEP)
                add_at(buf, sfx_pop(0.45), s + c0 + COUNTDOWN_SECONDS * COUNTDOWN_STEP)
        elif name == "countdown":
            for k in range(COUNTDOWN_SECONDS):
                add_at(buf, sfx_tick(0.5), s + k * COUNTDOWN_STEP)
                add_at(buf, sfx_heartbeat(0.45), s + k * COUNTDOWN_STEP)
            add_at(buf, sfx_pop(0.45), s + COUNTDOWN_SECONDS * COUNTDOWN_STEP)
        elif name == "hint":
            add_at(buf, sfx_ding(0.18), s + 0.05)
        elif name == "eliminate":
            for k in ("x1", "x2", "x3"):
                add_at(buf, sfx_buzz(0.35), s + mk[k][0])
            add_at(buf, sfx_riser(max(0.3, mk["x3"][0] - mk["left"][0])), s + mk["left"][0])
        elif name == "reveal":
            add_at(buf, sfx_ding(0.5), s)
            add_at(buf, sfx_thud(0.5), s)
        elif name == "rule":
            add_at(buf, sfx_pop(0.3), s + mk["fact"][0])
            for bt in beat_times(sc):
                add_at(buf, sfx_pop(0.32), s + bt)
            add_at(buf, sfx_buzz(0.18), s + mk["trapx"][0])
        elif name == "cta":
            add_at(buf, sfx_pop(0.4), s + 0.05)
            if "mock" in mk:
                add_at(buf, sfx_pop(0.5), s + mk["mock"][0])

    buf += voice_track
    buf = buf[:int(total * SR)]
    peak = float(np.max(np.abs(buf))) if len(buf) else 1.0
    if peak > 0.95:
        buf = buf / peak * 0.95
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# ==================== COMMON OVERLAYS ====================

def draw_header(canvas, data, gt, total):
    d = ImageDraw.Draw(canvas)
    d.text((60, 70), "POSTAL WALA", font=get_font(34), fill=(148, 163, 184), anchor="lm")
    chip = pill_sprite(f"Clause {data['clause_no']}  |  Part {data['part_no']}/{data['total_parts']}",
                       26, YELLOW, (40, 32, 8), ORANGE)
    place(canvas, chip, W - 60 - chip.width / 2, 70)
    x0, x1, y = 60, W - 60, 118
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((x0, y, x1, y + 10), radius=5, fill=(27, 42, 58))
    cur = x0 + (x1 - x0) * clamp(gt / total)
    d.rounded_rectangle((x0, y, max(x0 + 10, cur), y + 10), radius=5, fill=CYAN)
    place(canvas, glow_sprite(22, CYAN, 200), cur, y + 5)


def topic_chip(canvas, data, y, a=1.0):
    chip = pill_sprite(data["title"], 32, CYAN, (10, 30, 50), (40, 100, 150))
    place(canvas, chip, W / 2, y, alpha=a)


# ==================== SCENES ====================

@lru_cache(maxsize=4)
def audience_banner():
    text = "GDS  |  MTS  |  POSTMAN  परीक्षा"
    f = get_font(46)
    w, h = int(text_w(text, f)) + 90, 96
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=22, fill=YELLOW + (255,))
    d.text((w / 2, h / 2 + 2), text, font=f, fill=(25, 18, 0, 255), anchor="mm")
    return im


@lru_cache(maxsize=16)
def vs_card(text, w=900, h=190, active=False, en=""):
    fill = (30, 58, 96) if active else (22, 42, 72)
    im = card_sprite(w, h, fill, CYAN if active else (80, 120, 170), 7 if active else 5, 36).copy()
    d = ImageDraw.Draw(im)
    if en:
        f, s, lines = fit_lines(text, w - 80, 1, 64, 40)
        lines = lines[:1]
        fe, se, le = fit_lines_f(en, w - 80, 1, 42, 26, get_font_reg)
        d.text((30 + w / 2, 30 + h * 0.74), " ".join(le[0]) if le else "", font=fe, fill=EN_COL + (255,), anchor="mm")
        lh = 0
        y0 = 30 + h * 0.40
    else:
        f, s, lines = fit_lines(text, w - 80, 2, 70, 40)
        lh = int(s * 1.25)
        y0 = 30 + h / 2 - (len(lines) - 1) * lh / 2
    for k, ln in enumerate(lines):
        d.text((30 + w / 2, y0 + k * lh), " ".join(ln), font=f, fill=WHITE + (255,), anchor="mm")
    return im


def scene_hook(cv, data, t, dur, m, vd, sc):
    """
    Frame 0 pe hi: kiske liye (banner) + sawal (poora, chamakta) + '4 ya 5?' do bade jawab + EXAM TRAP.
    Viewer pehle second me hi man me ek jawab chun leta hai -> jawab jaanne ke liye rukta hai.
    """
    fx = {}
    place(cv, audience_banner(), W / 2, 215, scale=0.92 + 0.08 * ease_out_back(prog(t, 0, 0.3)))

    # sawal: frame 0 se poora dikhe (koi grey/chhupa shabd nahi), bolte shabd peele
    # jo sawal dikhe, wahi jiska jawab dono cards hain (pehle hook alag sawal poochta tha)
    en_q = data.get("en_question", "") if en_on("hook") else ""
    hq_c = 430 if en_q else 470
    yb = draw_kinetic(cv, data["hook_q"], W / 2, 0, 940, 84 if data.get("hook_short") else 74, 1.0,
                      max_lines=3, min_size=46, karaoke=False, center_y=hq_c)
    draw_en(cv, en_q, yb + 6, max_w=900, size=39)

    # 'A ya B?' cards
    s0, s1 = m["vs"]
    mid = s0 + (s1 - s0) * 0.5
    a, b = data["vs_pair"]
    k = ease_out_back(prog(t, 0, 0.28))
    place(cv, glow_sprite(420, RED, 70), W / 2, 1010)
    if t < s1 + 0.1:
        act_a, act_b = t < mid, mid <= t
    else:                                   # "ye ya wo?" - baari-baari chamak
        flip = int((t - s1) / 0.55) % 2 == 0
        act_a, act_b = flip, not flip
    bump_a = 1.03 if (act_a and t >= s1) else 1.0
    bump_b = 1.03 if (act_b and t >= s1) else 1.0
    ea, eb = (data.get("en_vs") or ["", ""])[:2] if en_on("hook") else ("", "")
    ka = ease_out_back(prog(t, 0.04, 0.34))          # pehla card baayein se
    kb = ease_out_back(prog(t, 0.16, 0.34))          # doosra daayein se (harkat = scroll rukta hai)
    place(cv, vs_card(a, active=act_a, en=ea), W / 2 - (1 - ka) * 700, 830,
          scale=(0.88 + 0.12 * k) * bump_a, alpha=clamp(0.25 + ka))
    place(cv, vs_card(b, active=act_b, en=eb), W / 2 + (1 - kb) * 700, 1190,
          scale=(0.88 + 0.12 * k) * bump_b, alpha=clamp(0.25 + kb))
    pulse = 1 + 0.06 * math.sin(t * 9)
    place(cv, glow_sprite(90, YELLOW, 160), W / 2, 1010)
    place(cv, pill_sprite("या", 56, (25, 18, 0), YELLOW, ORANGE), W / 2, 1010, scale=pulse)

    # EXAM TRAP stamp: 0.12s pe slam (English line ho to thoda neeche, card ke kone pe)
    stamp_y = 718 if en_q else 680
    st = sc["stamp_t"]
    kk = prog(t, st, 0.16)
    if t >= st:
        place(cv, stamp_sprite(), W / 2 + 250, stamp_y, scale=(1.9 - 0.9 * ease_out_cubic(kk)) * 0.62,
              angle=-11, alpha=clamp(kk * 3))
        if t < st + 0.3:
            fx["shake"] = 12 * (1 - prog(t, st + 0.04, 0.26))
    else:
        place(cv, stamp_sprite(), W / 2 + 250, stamp_y, scale=0.62, angle=-11, alpha=0.35)

    d = ImageDraw.Draw(cv)
    d.text((W / 2, 1420), "आपका जवाब? पूरा देखिए, आखिर में मिलेगा", font=get_font(40),
           fill=YELLOW, anchor="mm")
    return fx


# ---- layout: poori screen use ho (pehle neeche 40% khaali rehta tha) ----
OPT_W, OPT_H = 940, 176
STEPPER_Y = 1552
STEPS = ["सवाल", "जवाब", "नियम", "ट्रैप", "याद"]


def current_step(name, t, m):
    if name in ("question", "countdown", "hint"):
        return 0
    if name in ("eliminate", "reveal"):
        return 1
    if name == "rule":
        return 3 if t >= m["trapx"][0] - 0.1 else 2
    if name == "cta":
        return 4
    return -1


def draw_stepper(cv, step, t):
    """Neeche progress: viewer ko dikhe kya ho gaya aur kya baaki hai (open loop)."""
    if step < 0:
        return
    n = len(STEPS)
    x0, x1 = 90, W - 90
    xs = [x0 + (x1 - x0) * k / (n - 1) for k in range(n)]
    d = ImageDraw.Draw(cv)
    d.line((x0, STEPPER_Y, x1, STEPPER_Y), fill=(60, 80, 110), width=6)
    d.line((x0, STEPPER_Y, xs[step], STEPPER_Y), fill=GREEN, width=6)
    f = get_font(30)
    for k, x in enumerate(xs):
        if k < step:
            col, r, tcol = GREEN, 16, (150, 220, 170)
        elif k == step:
            col, r, tcol = YELLOW, 22 + 3 * math.sin(t * 8), YELLOW
        else:
            col, r, tcol = (70, 90, 120), 14, (120, 135, 160)
        d.ellipse((x - r, STEPPER_Y - r, x + r, STEPPER_Y + r), fill=col)
        d.text((x, STEPPER_Y + 48), STEPS[k], font=f, fill=tcol, anchor="mm")
    if step < 3:
        a = 0.6 + 0.4 * math.sin(t * 5)
        d.text((W / 2, STEPPER_Y - 62), "आगे: EXAM TRAP >>", font=get_font(34),
               fill=mix(BG_BOTTOM, ORANGE, a), anchor="mm")


def opt_positions(n=4, y0=720, gap=190):
    return [y0 + i * gap for i in range(n)]


def source_label(data):
    return f"PO Guide Part I  |  Clause {data['clause_no']}"


def source_chip(cv, data, y, a=1.0):
    chip = pill_sprite(source_label(data), 32, YELLOW, (40, 32, 8), ORANGE)
    place(cv, chip, W / 2, y, alpha=a)


def scene_question(cv, data, t, dur, m, vd, sc):
    place(cv, pill_sprite("सवाल", 40, WHITE, (37, 60, 140), BLUE), W / 2, 225)
    source_chip(cv, data, 318, a=0.95)
    en_q = data.get("en_question", "") if en_on("question") else ""
    yb = draw_kinetic(cv, data["question"], W / 2, 0, 960, 66, 1.0, max_lines=3, min_size=44,
                      karaoke=False, center_y=480 if en_q else 500)
    draw_en(cv, en_q, yb + 4, max_w=940, size=39)

    merged = "cd_start" in sc
    oh = 146 if merged else OPT_H
    ys = opt_positions(y0=max(710, yb + (60 if en_q else 40) + oh / 2), gap=160) if merged \
        else opt_positions(y0=760, gap=200)
    c0 = sc.get("cd_start", 99)
    cd = COUNTDOWN_SECONDS * COUNTDOWN_STEP
    pulse = 1 + (0.015 * math.sin(t * 10) if t >= c0 else 0)
    for i, (l, txt) in enumerate(data["options"]):
        eo = (data.get("en_opt", {}).get(l, "") if en_on("options") else "")
        s0 = sc["opt_t"][i]
        k = prog(t, s0, 0.3)
        if k <= 0:
            place(cv, option_sprite(l, txt, OPT_W, oh, "normal", eo), W / 2, ys[i], alpha=0.12)
            continue
        active = s0 <= t < s0 + 0.35
        e = ease_out_back(k)
        place(cv, option_sprite(l, txt, OPT_W, oh, "active" if active else "normal", eo),
              W / 2 + (1 - e) * 500, ys[i], alpha=clamp(k * 2), scale=(1.04 if active else 1.0) * pulse)

    fx = {}
    if merged and t >= c0 - 0.25:
        # countdown: scene ke aakhir me (padhne ke baad), taaki khaali 'taala' na rahe
        tt = t - c0
        cy = min(ys[-1] + oh / 2 + 82, 1380)        # 'आगे: EXAM TRAP' label (1490) se door
        cx, r = 250, 60
        k_in = ease_out_back(prog(t, c0 - 0.25, 0.25))
        place(cv, glow_sprite(150, PURPLE, 120), cx, cy)
        d = ImageDraw.Draw(cv)
        rr = r * max(0.05, k_in)
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=(24, 20, 50), outline=(70, 60, 120), width=9)
        done = tt >= cd
        if tt >= 0 and not done:
            remain = clamp(1 - tt / cd)
            d.arc((cx - rr, cy - rr, cx + rr, cy + rr), -90, -90 + 360 * remain, fill=YELLOW, width=9)
            num = max(1, COUNTDOWN_SECONDS - int(tt / COUNTDOWN_STEP))
            frac = (tt / COUNTDOWN_STEP) - int(tt / COUNTDOWN_STEP)
            s_ = 1.35 - 0.35 * ease_out_cubic(clamp(frac * 3))
            d.text((cx, cy), str(num), font=get_font(int(70 * s_)), fill=YELLOW, anchor="mm")
            if frac < 0.08 and tt > 0.05:
                fx["shake"] = 4
        elif done:
            place(cv, lock_sprite(76), cx, cy, scale=max(0.05, ease_out_back(prog(tt, cd, 0.3))))
        d.text((cx + r + 34, cy - 20), "अपना जवाब लॉक कीजिए!", font=get_font(40), fill=WHITE, anchor="lm")
        d.text((cx + r + 34, cy + 28), "कमेंट करें:  A / B / C / D", font=get_font(36), fill=YELLOW, anchor="lm")
    return fx


def scene_countdown(cv, data, t, dur, m, vd, sc):
    d = ImageDraw.Draw(cv)
    d.text((W / 2, 235), "अपना जवाब लॉक कीजिए!", font=get_font(70), fill=WHITE, anchor="mm")
    ys = opt_positions(y0=420, gap=178)
    pulse = 1 + 0.015 * math.sin(t * 10)
    for i, (l, txt) in enumerate(data["options"]):
        place(cv, option_sprite(l, txt, OPT_W, 158, "normal", (data.get("en_opt", {}).get(l, "") if en_on("options") else "")), W / 2, ys[i], scale=pulse)

    cx, cy, r = W / 2, 1195, 150
    step = COUNTDOWN_STEP
    cd = COUNTDOWN_SECONDS * step
    done = t >= cd
    num = max(1, COUNTDOWN_SECONDS - int(t / step))
    frac = (t / step) - int(t / step)
    place(cv, glow_sprite(280, PURPLE, 140), cx, cy)
    d = ImageDraw.Draw(cv)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(24, 20, 50), outline=(70, 60, 120), width=14)
    remain = 0.0 if done else clamp(1 - t / cd)
    if remain > 0.002:
        d.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * remain, fill=YELLOW, width=14)
    if done:
        place(cv, lock_sprite(150), cx, cy, scale=max(0.05, ease_out_back(prog(t, cd, 0.3))))
    else:
        s_ = 1.35 - 0.35 * ease_out_cubic(clamp(frac * 3))
        d.text((cx, cy), str(num), font=get_font(int(150 * s_)), fill=YELLOW, anchor="mm")
    d.text((W / 2, 1400), "कमेंट करें:  A  /  B  /  C  /  D", font=get_font(52), fill=WHITE, anchor="mm")
    return {"shake": 5 if (not done and frac < 0.08 and t > 0.05) else 0}


def scene_hint(cv, data, t, dur, m, vd, sc):
    """Sirf SHOW_HINT = True hone pe istemaal hota hai."""
    k = ease_out_back(prog(t, 0, 0.35))
    glow = 0.7 + 0.3 * math.sin(t * 6)
    place(cv, glow_sprite(330, YELLOW, int(130 * glow)), W / 2, 430)
    place(cv, bulb_sprite(300), W / 2, 430, scale=max(0.05, 0.5 + 0.5 * k), angle=math.sin(t * 4) * 5)
    place(cv, pill_sprite("HINT", 52, (30, 20, 0), YELLOW, YELLOW), W / 2, 680, scale=max(0.05, k))
    bh = text_block_h(data["hint"], 860, 74, 4, 46)
    ch = max(bh + 170, 360)
    cy = 1000
    place(cv, card_sprite(980, ch, (34, 30, 18), ORANGE, 6, 44), W / 2, cy, alpha=clamp(k))
    p, th = seg_progress(sc, "hint", t)
    draw_kinetic(cv, data["hint"], W / 2, 0, 860, 74, p, max_lines=4, min_size=46, ghost=0.18,
                 center_y=cy, th=th)
    d = ImageDraw.Draw(cv)
    d.text((W / 2, cy + ch / 2 + 95), "अब भी वही जवाब?", font=get_font(54), fill=WHITE, anchor="mm")
    return {}


def scene_eliminate(cv, data, t, dur, m, vd, sc):
    d = ImageDraw.Draw(cv)
    suspense_phase = m["left"][0] <= t < m["x3"][0]
    if t >= m["x3"][0]:
        title, tcol = "सिर्फ एक बचा!", GREEN
    elif suspense_phase:
        title, tcol = "बचे दो... सही कौन?", YELLOW
    else:
        title, tcol = "गलत हटाओ!", WHITE
    d.text((W / 2, 260), title, font=get_font(74), fill=tcol, anchor="mm")

    ys = opt_positions(y0=520, gap=212)
    fx = {}
    order = data["elim_order"]
    kill_t = {order[0]: m["x1"][0], order[1]: m["x2"][0], order[2]: m["x3"][0]}
    for i, (l, txt) in enumerate(data["options"]):
        y = ys[i]
        if l in kill_t and t >= kill_t[l]:
            k = prog(t, kill_t[l], 0.25)
            shake = math.sin(k * 40) * 18 * (1 - k)
            place(cv, option_sprite(l, txt, OPT_W, OPT_H, "wrong", (data.get("en_opt", {}).get(l, "") if en_on("options") else "")), W / 2 + shake, y,
                  alpha=1 - 0.5 * k, scale=1 - 0.05 * k)
            place(cv, x_mark_sprite(), W / 2 + 400, y, scale=max(0.05, 1.8 - 0.8 * ease_out_back(k)))
            if t - kill_t[l] < 0.1:
                fx["shake"] = 8
        else:
            suspense = t >= m["left"][0]
            sc_ = 1 + (0.03 * math.sin(t * 12) if suspense else 0)
            place(cv, option_sprite(l, txt, OPT_W, OPT_H, "active" if suspense else "normal", (data.get("en_opt", {}).get(l, "") if en_on("options") else "")), W / 2, y, scale=sc_)

    if suspense_phase:
        heart = 0.5 + 0.5 * math.sin(t * 14)
        d = ImageDraw.Draw(cv)
        d.text((W / 2, 1405), "? ? ?", font=get_font(84), fill=mix(BG_BOTTOM, YELLOW, heart), anchor="mm")
    return fx


def scene_reveal(cv, data, t, dur, m, vd, sc):
    cy = 820
    place(cv, rays_sprite(), W / 2, cy, angle=t * 25, scale=1.25)
    place(cv, glow_sprite(400, GREEN, 150), W / 2, cy)

    d = ImageDraw.Draw(cv)
    d.text((W / 2, 280), "सही जवाब", font=get_font(84), fill=GREEN, anchor="mm")

    k = ease_out_back(prog(t, 0, 0.4))
    place(cv, check_sprite(190), W / 2, 520, scale=max(0.05, 0.3 + 0.7 * k))
    place(cv, option_sprite(data["correct"], data["correct_text"], 900, 200, "correct",
                            data.get("en_opt", {}).get(data["correct"], "") if en_on("answer") else ""),
          W / 2, cy + 20, scale=max(0.05, 0.8 + 0.2 * min(k, 1.0) + 0.03 * max(k - 1.0, 0)))

    rng = random.Random(9)
    d = ImageDraw.Draw(cv)
    for _ in range(90):
        ang = rng.uniform(0, 2 * math.pi)
        sp = rng.uniform(500, 1300)
        col = rng.choice([GREEN, YELLOW, CYAN, WHITE, ORANGE])
        sz = rng.randint(10, 18)
        x = W / 2 + math.cos(ang) * sp * t * 0.9
        y = cy + math.sin(ang) * sp * t * 0.9 + 900 * t * t
        if 0 < x < W and 0 < y < H and t < 1.8:
            d.rectangle((x, y, x + sz, y + sz * 0.6), fill=col)

    d.text((W / 2, 1120), "आपका जवाब सही था?", font=get_font(60), fill=WHITE, anchor="mm")
    place(cv, pill_sprite("सही था तो कमेंट:  " + data["correct"], 44, (5, 30, 15), GREEN, GREEN),
          W / 2, 1260, scale=max(0.05, ease_out_back(prog(t, 0.35, 0.3))))
    return {"flash": 0.28 * (1 - prog(t, 0, 0.12))}


def beat_times(sc):
    """Yaad-tukde niyam bolte-bolte ek-ek karke (niyam ki awaaz ke 15%-90% hisse me)."""
    items = (sc.get("data") or {}).get("beat_items") or []
    if not items or "fact" not in sc.get("marks", {}):
        return []
    a, b = sc["marks"]["fact"]
    n = len(items)
    return [a + (b - a) * (0.15 + 0.75 * i / max(1, n - 1 if n > 1 else 1)) for i in range(n)]


@lru_cache(maxsize=64)
def beat_sprite(text, mark, w=880, h=96):
    col = {"yes": GREEN, "no": RED, "key": CYAN}[mark]
    fill = {"yes": (14, 44, 32), "no": (52, 18, 26), "key": (18, 36, 64)}[mark]
    im = card_sprite(w, h, fill, col, 4, 30, shadow=False).copy()
    d = ImageDraw.Draw(im)
    cx, cy, r = 58, h / 2, 30
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col + (255,))
    if mark == "yes":
        d.line((cx - 13, cy + 1, cx - 3, cy + 11, cx + 14, cy - 10), fill=(255, 255, 255, 255), width=6, joint="curve")
    elif mark == "no":
        d.line((cx - 11, cy - 11, cx + 11, cy + 11), fill=(255, 255, 255, 255), width=6)
        d.line((cx + 11, cy - 11, cx - 11, cy + 11), fill=(255, 255, 255, 255), width=6)
    else:
        d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=(10, 20, 40, 255))
    f, s_, lines = fit_lines(text, w - 140, 1, 48, 30)
    d.text((110, cy), " ".join(lines[0]) if lines else "", font=f, fill=WHITE + (255,), anchor="lm")
    return im


def scene_rule(cv, data, t, dur, m, vd, sc):
    topic_chip(cv, data, 235)
    FS, TS = 64, 58
    ef = data.get("en_fact", "") if en_on("fact") else ""
    et = data.get("en_trap", "") if en_on("trap") else ""
    ehf, eht = en_h(ef, 860, 38), en_h(et, 860, 34)
    fh = text_block_h(data["fact"], 880, FS, 5, 42) + 160 + (ehf + 14 if ehf else 0)
    th = text_block_h(data["trap"], 880, TS, 4, 40) + 160 + (eht + 14 if eht else 0)
    gap = 105
    area_top, area_bot = 320, 1450
    ts = m["trapx"][0]
    items = data.get("beat_items") or []
    if items:
        # niyam upar, uske neeche yaad-tukde (khaali jagah ka upyog), sabse neeche trap
        row_h, row_gap = 96, 14
        beats_h = len(items) * (row_h + row_gap) - row_gap
        total = fh + 30 + beats_h + 50 + th
        if total > area_bot - area_top:
            row_h, row_gap = 84, 10
            beats_h = len(items) * (row_h + row_gap) - row_gap
            total = fh + 30 + beats_h + 50 + th
        top = max(area_top, area_top + (area_bot - area_top - total) / 2)
        fc = top + fh / 2
        beats_top = top + fh + 30
        tc = beats_top + beats_h + 50 + th / 2
    else:
        top = max(area_top, (area_top + area_bot) / 2 - (fh + gap + th) / 2)
        fc_final, tc = top + fh / 2, top + fh + gap + th / 2
        fc_center = (area_top + area_bot) / 2 - 60
        # trap aane se pehle niyam card screen ke beech me bada; trap aate hi upar khisakta hai
        mv = ease_in_out(prog(t, ts - 0.45, 0.4)) if t >= ts - 0.45 else 0.0
        fc = fc_center + (fc_final - fc_center) * mv

    k1 = ease_out_back(prog(t, 0, 0.35))
    place(cv, card_sprite(980, int(fh), (14, 44, 32), GREEN, 6, 44), W / 2, fc,
          scale=0.92 + 0.08 * k1, alpha=clamp(k1))
    place(cv, pill_sprite("नियम", 46, (5, 30, 15), GREEN, GREEN), W / 2, fc - fh / 2, scale=max(0.05, k1))
    place(cv, pill_sprite("स्रोत: " + source_label(data), 28, (170, 230, 190), (10, 40, 26), (40, 110, 70)),
          W / 2, fc + fh / 2 - 6, alpha=clamp(k1))
    fp, th_f = seg_progress(sc, "fact", t)
    yb = draw_kinetic(cv, data["fact"], W / 2, 0, 880, FS, fp, max_lines=5, min_size=42,
                      hl_words=data["hl_words"], hl_color=GREEN, ghost=0.18,
                      center_y=fc + 10 - (ehf + 14) / 2 if ehf else fc + 10, th=th_f)
    draw_en(cv, ef, yb + 10, max_w=860, size=38, alpha=clamp(k1))

    fx = {}
    if items:
        for i, (b, bt_) in enumerate(zip(items, beat_times(sc))):
            if t < bt_ - 0.05:
                continue
            kb = ease_out_back(prog(t, bt_ - 0.05, 0.3))
            y = beats_top + i * (row_h + row_gap) + row_h / 2
            place(cv, beat_sprite(b["text"], b["mark"], 880, row_h), W / 2 + (1 - kb) * 600, y,
                  alpha=clamp(kb * 1.5), scale=0.9 + 0.1 * min(kb, 1.0))
    if t >= ts - 0.1:
        k2 = ease_out_back(prog(t, ts - 0.1, 0.35))
        place(cv, card_sprite(980, int(th), (56, 18, 26), RED, 6, 44), W / 2, tc,
              scale=0.9 + 0.1 * k2, alpha=clamp(k2))
        place(cv, pill_sprite("EXAM TRAP", 46, WHITE, RED, RED), W / 2, tc - th / 2,
              scale=max(0.05, k2), angle=-3)
        tp, th2 = seg_progress(sc, "trap", t)
        yb2 = draw_kinetic(cv, data["trap"], W / 2, 0, 880, TS, tp, max_lines=4, min_size=40,
                           ghost=0.18, center_y=tc + 10 - (eht + 14) / 2 if eht else tc + 10, th=th2)
        draw_en(cv, et, yb2 + 10, max_w=860, size=32, color=(255, 190, 190), alpha=clamp(k2))
        if t - ts < 0.12:
            fx["shake"] = 6
    else:
        d = ImageDraw.Draw(cv)
        a = 0.5 + 0.5 * math.sin(t * 6)
        d.text((W / 2, (tc if items else fc + fh / 2 + 110)), "लेकिन असली ट्रैप अभी बाकी है...", font=get_font(52),
               fill=mix(BG_BOTTOM, ORANGE, 0.4 + 0.6 * a), anchor="mm")
    return fx


def scene_cta(cv, data, t, dur, m, vd, sc):
    """Yaad formula + comment CTA + agli reel ka khaas teaser + follow."""
    k = ease_out_back(prog(t, 0, 0.35))
    place(cv, pill_sprite("याद रखिए", 50, (30, 20, 0), YELLOW, YELLOW), W / 2, 305, scale=max(0.05, k))

    cy = 540
    ey = data.get("en_yaad", "") if en_on("yaad") else ""
    ehy = en_h(ey, 860, 36)
    bh = text_block_h(data["yaad"], 880, 80, 3, 50)
    ch = bh + 170 + (ehy + 12 if ehy else 0)
    place(cv, glow_sprite(440, YELLOW, 70), W / 2, cy)
    place(cv, card_sprite(1000, ch, (46, 38, 10), YELLOW, 7, 46), W / 2, cy,
          scale=0.9 + 0.1 * k, alpha=clamp(k))
    p, th = seg_progress(sc, "yaad", t)
    yb = draw_kinetic(cv, data["yaad"], W / 2, 0, 880, 80, max(p, 0.001), max_lines=3, min_size=50,
                      ghost=0.3, center_y=cy - (ehy + 12) / 2 if ehy else cy, th=th, karaoke=True)
    draw_en(cv, ey, yb + 8, max_w=860, size=36, color=(255, 225, 150), alpha=clamp(k))

    # FREE MOCK TEST - "कमेंट कीजिए, मॉक" bolte hi
    y2 = cy + ch / 2 + 125
    m0 = m["mock"][0]
    k2 = ease_out_back(prog(t, m0 - 0.15, 0.35)) if t >= m0 - 0.15 else 0.0
    pulse = 1 + (0.05 * math.sin(t * 9) if t > m0 + 0.4 else 0)
    if k2 > 0:
        place(cv, glow_sprite(300, ORANGE, 110), W / 2, y2)
        place(cv, mock_button(), W / 2, y2, scale=max(0.05, (0.5 + 0.5 * k2) * pulse), alpha=clamp(k2 * 2))

    # agli reel ka khaas sawal (open loop)
    teaser = data.get("teaser") or ""
    if teaser.strip() in ("", "अगला नियम"):
        teaser = ""                      # khaali/generic teaser se better kuch na dikhana
    ty = y2 + 190
    if teaser and t > m0 + 0.2:
        kt = ease_out_cubic(prog(t, m0 + 0.2, 0.35))
        box_h = text_block_h(teaser, 820, 42, 2, 34) + 90
        place(cv, card_sprite(960, box_h, CARD, PURPLE, 4, 30), W / 2, ty + box_h / 2 - 10, alpha=kt)
        d = ImageDraw.Draw(cv)
        d.text((W / 2, ty + 18), "अगली रील में:", font=get_font(34), fill=YELLOW, anchor="mm")
        draw_kinetic(cv, teaser, W / 2, 0, 820, 42, 1.0, max_lines=2, min_size=34, karaoke=False,
                     center_y=ty + box_h / 2 + 12)
    place(cv, pill_sprite("FOLLOW  " + IG_HANDLE, 42, WHITE, (220, 38, 38), (255, 120, 120)),
          W / 2, 1440, scale=1 + 0.03 * math.sin(t * 8), alpha=clamp(k))
    return {}


@lru_cache(maxsize=2)
def mock_button():
    top, bot = "FREE MOCK TEST", f"कमेंट करें:  {MOCK_KEYWORD}"
    f1, f2 = get_font(54), get_font(46)
    w = int(max(text_w(top, f1), text_w(bot, f2))) + 120
    h = 190
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=36, fill=(255, 196, 0, 255), outline=(255, 245, 200, 255), width=5)
    d.text((w / 2, 60), top, font=f1, fill=(40, 20, 0, 255), anchor="mm")
    d.rounded_rectangle((40, 104, w - 40, 170), radius=26, fill=(200, 30, 40, 255))
    d.text((w / 2, 137), bot, font=f2, fill=WHITE + (255,), anchor="mm")
    return im


SCENES = {
    "hook": scene_hook, "question": scene_question, "countdown": scene_countdown,
    "hint": scene_hint, "eliminate": scene_eliminate, "reveal": scene_reveal,
    "rule": scene_rule, "cta": scene_cta,
}


# ==================== RENDER ====================

def render_frame(sc, data, gt, total):
    t = gt - sc["start"]
    cv = bg_frame(sc["mood"], gt)
    fx = SCENES[sc["name"]](cv, data, t, sc["dur"], sc["marks"], sc["vdur"], sc) or {}
    draw_header(cv, data, gt, total)
    draw_stepper(cv, current_step(sc["name"], t, sc["marks"]), t)

    # scene-entry punch zoom + hook me dheema push-in (screen jama hua na lage)
    z = 1.0
    if t < 0.2:
        z *= 1 + 0.07 * (1 - ease_out_cubic(t / 0.2))
    if sc["name"] == "hook":
        z *= 1 + 0.035 * clamp(t / max(sc["dur"], 0.1))
    if z > 1.0005:
        nw, nh = int(W * z), int(H * z)
        big = cv.resize((nw, nh), Image.BILINEAR)
        ox, oy = (nw - W) // 2, (nh - H) // 2
        cv = big.crop((ox, oy, ox + W, oy + H))

    shake = fx.get("shake", 0) or 0
    if shake > 0.5:
        rng = random.Random(int(gt * 1000))
        s = int(shake)
        dx, dy = rng.randint(-s, s), rng.randint(-s, s)
        base = Image.new("RGB", (W, H), BG_TOP)
        base.paste(cv, (dx, dy))
        cv = base

    flash = fx.get("flash", 0) or 0
    if flash > 0.01:
        cv = Image.blend(cv, Image.new("RGB", (W, H), (255, 255, 255)), clamp(flash))
    return cv


def build_timeline(specs, voices, data):
    timeline, cur = [], 0.0
    for i, (sp, voice) in enumerate(zip(specs, voices)):
        v, words = voice[0], voice[1]
        seg_starts = voice[2] if len(voice) > 2 else None
        vdur = len(v) / SR + VOICE_LEAD
        dur = max(vdur + sp["tail"], sp["min"])
        if seg_starts and len(seg_starts) == len(sp["segs"]):
            marks, wt = marks_from_seg_starts(sp["segs"], [x + VOICE_LEAD for x in seg_starts], vdur)
        else:
            shifted = [(a + VOICE_LEAD, b + VOICE_LEAD, w) for a, b, w in words] if words else None
            marks, wt = compute_marks(sp["segs"], vdur, shifted)
        # RULE: jo text padhna hai, use (shabd / READ_WPS) + ABSORB time zaroor mile
        for key, text in sp.get("read", []):
            need = marks[key][0] + len(text.split()) / READ_WPS + ABSORB
            dur = max(dur, need)
        if sp["name"] == "question" and MERGE_COUNTDOWN:
            cd_len = COUNTDOWN_SECONDS * COUNTDOWN_STEP
            opt_words = sum(len(t.split()) for _, t in data["options"]) + len(data["question"].split()) * 0.5
            need = 0.12 + opt_words / OPT_READ_WPS + 0.3            # options dikhne se padhne tak
            cd_start = max(marks["lock"][0], need - cd_len)
            dur = max(dur, cd_start + cd_len + 0.35)
        if sp["name"] == "countdown" and timeline:
            # options padhne ka time: options dikhne se countdown khatam hone tak
            q = timeline[-1]
            opt_words = sum(len(t.split()) for _, t in data["options"])
            seen = q["dur"] - q["opt_t"][0]
            dur = max(dur, opt_words / READ_WPS + 0.3 - seen)
        sc = {
            "index": i, "name": sp["name"], "mood": sp["mood"], "start": cur, "dur": dur,
            "vdur": vdur, "marks": marks, "wt": wt, "data": data,
        }
        if sp["name"] == "question" and MERGE_COUNTDOWN:
            sc["cd_start"] = cd_start
        if sp["name"] == "hook":
            # stamp aakhri shabd (stake) ke saath girta hai
            sc["stamp_t"] = 0.12                         # stamp pehle 0.12 sec me (pehle 2.2s tha)
        if sp["name"] == "question":
            # options sawal ke 60% pe aane lagte hain -> jab tak sawal khatam, options padhne layak
            sc["opt_t"] = [0.12 + j * 0.14 for j in range(4)]
        timeline.append(sc)
        cur += dur
    return timeline, cur


def build_reel(data, output_video):
    os.makedirs(os.path.dirname(output_video) or ".", exist_ok=True)
    resolve_font()

    specs = build_scene_specs(data)
    # hint pehle se hata na ho aur reel lambi ban rahi ho to hint hatao
    MAX_REEL = 34.0
    print("Voice ban rahi hai...")
    voices = make_voices(specs)
    timeline, total = build_timeline(specs, voices, data)
    if total > MAX_REEL and any(sp["name"] == "hint" for sp in specs):
        k = next(i for i, sp in enumerate(specs) if sp["name"] == "hint")
        print(f"  Reel {total:.1f}s > {MAX_REEL}s -> hint scene hataya")
        specs.pop(k)
        voices.pop(k)
        timeline, total = build_timeline(specs, voices, data)
        for i, sc in enumerate(timeline):
            sc["index"] = i
    print("  PACING REPORT (scene | kab shuru | kitni der | voice | voice ke baad hold)")
    print(f"  Rules: max pause {MAX_PAUSE}s | padhne ki speed {READ_WPS} shabd/s | absorb {ABSORB}s")
    for sc in timeline:
        print(f"  {sc['name']:<10} {sc['start']:5.2f}s  {sc['dur']:4.2f}s  "
              f"voice {sc['vdur']:4.2f}s  hold {sc['dur'] - sc['vdur']:4.2f}s")

    audio_path = "_master_audio.wav"
    build_audio(voices, timeline, total, audio_path)

    n_frames = int(math.ceil(total * FPS))
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(VIDEO_CRF), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
        output_video,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        si = 0
        for fi in range(n_frames):
            gt = fi / FPS
            while si + 1 < len(timeline) and gt >= timeline[si + 1]["start"]:
                si += 1
            frame = render_frame(timeline[si], data, gt, total)
            proc.stdin.write(frame.tobytes())
            if fi % 90 == 0:
                print(f"  frame {fi}/{n_frames}")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    ret = proc.wait()
    if os.path.exists(audio_path):
        os.remove(audio_path)
    if ret != 0:
        raise RuntimeError("ffmpeg encoding fail hua")
    print(f"COMPLETE: {output_video} ({total:.2f}s)")
    return total


# ==================== CAPTION ====================

def find_teaser(plan, part, nxt):
    """Agli reel ka asli sawal (open loop) - pehle isi clause ka agla part, warna agle clause ka pehla."""
    good = usable_parts(plan)
    after = False
    for p in good:
        if p is part:
            after = True
            continue
        if after and not p.get("published"):
            return strip_brackets(p.get("question", ""))
    for p in good:
        if p is not part and not p.get("published"):
            return strip_brackets(p.get("question", ""))
    np_ = load_plan(nxt) if nxt else None
    if np_:
        for p in usable_parts(np_):
            if not p.get("published"):
                return strip_brackets(p.get("question", ""))
        return np_.get("title_hi", "")
    return ""


def write_caption(data, path):
    """Instagram caption: pehli line search ke liye, jawab nahi batati (spoiler nahi)."""
    en_q = data.get("en_question", "")
    lines = [
        f"{data['question']} | GDS to MTS / Postman | PO Guide Part I Clause {data['clause_no']}",
    ] + ([f"🇬🇧 {en_q} (Answer in the reel 👀)"] if en_q else []) + [
        "",
        "सही उत्तर जानने के लिए पूरी रील देखें 👀",
        f"📘 स्रोत: PO Guide Part I, Clause {data['clause_no']}",
        f"🎯 FREE MOCK TEST चाहिए? कमेंट करें: {MOCK_KEYWORD}  |  Want a FREE MOCK TEST? Comment {MOCK_KEYWORD}",
        "🔔 रोज़ 1 नियम | PO Guide Series  |  1 rule daily for GDS, MTS, Postman & PA",
        "",
        HASHTAGS,
        "",
        "----- PIN करने वाला पहला कमेंट -----",
        f"आपका उत्तर? A / B / C / D लिखें 👇  |  Your answer? Comment A / B / C / D  |  Free Mock Test: {MOCK_KEYWORD}",
    ]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("Caption:", path)


# ==================== COVER / CAROUSEL / DM / LOG ====================

def _poster_bg(w, h, mood="blue"):
    im = background(mood).resize((w + 120, int((w + 120) * (H + 120) / (W + 120))))
    return im.crop((60, 60, 60 + w, 60 + h)).convert("RGB")


def make_cover(data, path):
    """
    Profile grid ke liye saaf cover (1080x1920). Zaroori cheezein beech ke 1080x1350 hisse me,
    kyunki grid me upar-neeche kat jaata hai.
    """
    cv = _poster_bg(W, H, "red")
    place(cv, audience_banner(), W / 2, 380)
    source_chip(cv, data, 480)
    draw_kinetic(cv, data["question"], W / 2, 0, 960, 100, 1.0, max_lines=4, min_size=64,
                 karaoke=False, center_y=870)
    place(cv, stamp_sprite(), W / 2, 1230, scale=0.95, angle=-8)
    d = ImageDraw.Draw(cv)
    d.text((W / 2, 1400), "सही जवाब रील में", font=get_font(52), fill=YELLOW, anchor="mm")
    d.text((W / 2, 1480), f"Clause {data['clause_no']}  |  Part {data['part_no']}/{data['total_parts']}",
           font=get_font(40), fill=MUTED, anchor="mm")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    cv.save(path, quality=92)
    print("Cover:", path)
    return path


# ---------- CAROUSEL: save karne layak notes (1080x1350) ----------
SW, SH = 1080, 1350
C_TOP, C_BOT = 150, SH - 150          # content ka area (header aur footer ke beech)
_COMMON_HI = {"और", "के", "का", "की", "में", "से", "पर", "है", "हैं", "को", "भी", "नहीं", "या", "एक", "यह", "वह"}


def key_words(part):
    """Highlight hone wale shabd: sankhya + sahi jawab ke khaas shabd."""
    keys = set()
    for fld in ("fact", "trap", "yaad"):
        for w in re.findall(r"[\w\u0900-\u097F:.]+", strip_brackets(part.get(fld, ""))):
            if re.search(r"\d", w):
                keys.add(w.strip(".,"))
    corr = part.get(str(part.get("correct", "A")).lower(), "")
    for w in re.findall(r"[\w\u0900-\u097F.]+", strip_brackets(corr)):
        if len(w) > 2 and w not in _COMMON_HI:
            keys.add(w)
    return tuple(sorted(keys))


# ---- "premium study notes" look: cream kaagaz, navy text, kesariya accent ----
CREAM = (255, 248, 236)
NAVY = (20, 33, 61)
SAFFRON = (255, 145, 36)
POST_RED = (214, 40, 57)
LEAF = (22, 140, 70)
GREY_T = (104, 112, 130)
MARKER_Y = (255, 222, 89)
PINK_BG = (255, 236, 238)
WHITE_C = (255, 255, 255)


@lru_cache(maxsize=2)
def cream_bg():
    im = Image.new("RGB", (SW, SH), CREAM)
    d = ImageDraw.Draw(im)
    for y in range(20, SH, 36):
        for x in range(20, SW, 36):
            d.ellipse((x - 1.6, y - 1.6, x + 1.6, y + 1.6), fill=(234, 222, 200))
    # halka saffron kona (depth)
    g = glow_sprite(520, (255, 190, 120), 60)
    im.paste(g, (SW - 620, -380), g)
    g2 = glow_sprite(480, (140, 190, 255), 40)
    im.paste(g2, (-420, SH - 520), g2)
    return im


def rich_text(cv, text, x, y, max_w, size, *, color=NAVY, keys=(), marker=MARKER_Y, key_color=None,
              max_lines=6, min_size=30, align="left", line_h=1.38, weight="reg"):
    """Shabd-dar-shabd likhta hai; khaas shabd BOLD + highlighter. Returns (neeche ka y, size)."""
    getf = get_font_reg if weight == "reg" else get_font
    font, s_, lines = fit_lines_f(text, max_w, max_lines, size, min_size, getf)
    bold = get_font(s_)
    lh = int(s_ * line_h)
    d = ImageDraw.Draw(cv)
    space = text_w(" ", font)
    keyset = {re.sub(r"[,.!?\u0964:()]", "", k) for k in keys}
    for n, ln in enumerate(lines):
        widths = []
        for w in ln:
            is_key = re.sub(r"[,.!?\u0964:()]", "", w) in keyset
            widths.append(text_w(w, bold if is_key else font))
        line_w = sum(widths) + space * (len(ln) - 1)
        cx = x if align == "left" else x + (max_w - line_w) / 2
        cy = y + n * lh + lh / 2
        for w, ww in zip(ln, widths):
            is_key = re.sub(r"[,.!?\u0964:()]", "", w) in keyset
            if is_key and marker:
                d.rounded_rectangle((cx - 5, cy - s_ * 0.36, cx + ww + 5, cy + s_ * 0.46), radius=7, fill=marker)
            d.text((cx, cy), w, font=bold if is_key else font,
                   fill=(key_color if (is_key and key_color) else color), anchor="lm")
            cx += ww + space
    return y + lh * len(lines), s_


def rich_h(text, max_w, size, max_lines=6, min_size=30, line_h=1.38, weight="reg"):
    getf = get_font_reg if weight == "reg" else get_font
    _, s_, lines = fit_lines_f(text, max_w, max_lines, size, min_size, getf)
    return int(s_ * line_h) * len(lines)


def white_card(cv, x, y, w, h, *, fill=WHITE_C, border=None, accent=None, radius=26):
    sh = Image.new("RGBA", (int(w) + 60, int(h) + 60), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((30, 38, w + 30, h + 38), radius=radius, fill=(70, 50, 20, 26))
    cv.paste(sh, (int(x) - 30, int(y) - 30), sh)
    d = ImageDraw.Draw(cv)
    d.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=fill,
                        outline=border or (236, 226, 208), width=2)
    if accent:
        d.rounded_rectangle((x, y + 18, x + 8, y + h - 18), radius=4, fill=accent)


def icon_bookmark(size=64, col=YELLOW):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = size * 0.62
    x0 = (size - w) / 2
    d.polygon([(x0, 4), (x0 + w, 4), (x0 + w, size - 4), (size / 2, size * 0.7), (x0, size - 4)], fill=col + (255,))
    return im


def icon_xcircle(size=58):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((2, 2, size - 2, size - 2), fill=POST_RED + (255,))
    m = size * 0.31
    d.line((m, m, size - m, size - m), fill=(255, 255, 255, 255), width=max(3, size // 10))
    d.line((size - m, m, m, size - m), fill=(255, 255, 255, 255), width=max(3, size // 10))
    return im


def icon_tick(size=56, col=LEAF):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((2, 2, size - 2, size - 2), fill=col + (255,))
    d.line((size * 0.28, size * 0.52, size * 0.44, size * 0.67), fill=(255, 255, 255, 255), width=max(3, size // 10))
    d.line((size * 0.44, size * 0.67, size * 0.74, size * 0.35), fill=(255, 255, 255, 255), width=max(3, size // 10))
    return im


def icon_bulb_small(size=56):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((2, 2, size - 2, size - 2), fill=SAFFRON + (255,))
    c, r = size / 2, size * 0.2
    d.ellipse((c - r, size * 0.22, c + r, size * 0.22 + 2 * r), fill=(255, 255, 255, 255))
    d.rectangle((c - r * 0.5, size * 0.58, c + r * 0.5, size * 0.72), fill=(255, 255, 255, 255))
    return im


def swipe_button(cv, y=None):
    """Kinare pe gol '>' button - professional carousels jaisa."""
    y = y or SH / 2
    d = ImageDraw.Draw(cv)
    x = SW - 46
    d.ellipse((x - 34, y - 34, x + 34, y + 34), fill=NAVY)
    d.line((x - 8, y - 14, x + 8, y, x - 8, y + 14), fill=SAFFRON, width=6, joint="curve")


@lru_cache(maxsize=2)
def postbox_sprite(h=420):
    """Laal postbox ka saadha chitra (koi logo nahi)."""
    w = int(h * 0.56)
    im = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0 = 20, 20
    d.pieslice((x0, y0, x0 + w, y0 + w * 0.9), 180, 360, fill=POST_RED + (255,))
    d.rectangle((x0, y0 + w * 0.45, x0 + w, y0 + h - 40), fill=POST_RED + (255,))
    d.rectangle((x0 + w * 0.72, y0 + w * 0.5, x0 + w * 0.86, y0 + h - 44), fill=(235, 70, 85, 255))   # chamak
    d.rectangle((x0 - 10, y0 + w * 0.43, x0 + w + 10, y0 + w * 0.53), fill=(170, 20, 40, 255))
    d.rounded_rectangle((x0 + w * 0.2, y0 + w * 0.68, x0 + w * 0.8, y0 + w * 0.78), radius=6, fill=(40, 20, 25, 255))
    d.rectangle((x0 - 14, y0 + h - 44, x0 + w + 14, y0 + h - 14), fill=(150, 20, 35, 255))
    d.rectangle((x0 + w * 0.22, y0 + w * 1.0, x0 + w * 0.78, y0 + w * 1.28), fill=(255, 240, 220, 255))
    d.text((x0 + w / 2, y0 + w * 1.14), "डाक", font=get_font(int(w * 0.16)), fill=POST_RED + (255,), anchor="mm")
    env = envelope_sprite(int(w * 0.62)).rotate(-12, expand=True)
    im.paste(env, (int(x0 + w * 0.2), int(y0 + w * 0.46)), env)
    return im


def _ill_canvas(size=420):
    return Image.new("RGBA", (size, size), (0, 0, 0, 0))


@lru_cache(maxsize=2)
def ill_moon(size=420):
    im = _ill_canvas(size)
    d = ImageDraw.Draw(im)
    c = size / 2
    d.ellipse((c - 150, c - 150, c + 150, c + 150), fill=(255, 214, 102, 255))
    d.ellipse((c - 80, c - 190, c + 200, c + 90), fill=(0, 0, 0, 0))
    im2 = _ill_canvas(size)
    d2 = ImageDraw.Draw(im2)
    d2.ellipse((c - 150, c - 150, c + 150, c + 150), fill=(255, 214, 102, 255))
    d2.ellipse((c - 70, c - 200, c + 210, c + 80), fill=(0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((c - 150, c - 150, c + 150, c + 150), fill=255)
    ImageDraw.Draw(mask).ellipse((c - 60, c - 190, c + 210, c + 80), fill=0)
    out = _ill_canvas(size)
    moon = Image.new("RGBA", (size, size), (255, 214, 102, 255))
    out.paste(moon, (0, 0), mask)
    d = ImageDraw.Draw(out)
    for (x, y, r) in ((300, 90, 12), (350, 170, 8), (260, 200, 6), (330, 260, 10)):
        d.polygon([(x, y - r * 2), (x + r * 0.6, y - r * 0.6), (x + r * 2, y), (x + r * 0.6, y + r * 0.6),
                   (x, y + r * 2), (x - r * 0.6, y + r * 0.6), (x - r * 2, y), (x - r * 0.6, y - r * 0.6)],
                  fill=(255, 245, 210, 255))
    return out


@lru_cache(maxsize=2)
def ill_clock(size=420):
    im = _ill_canvas(size)
    d = ImageDraw.Draw(im)
    c, r = size / 2, 170
    d.ellipse((c - r, c - r, c + r, c + r), fill=(255, 248, 236, 255), outline=SAFFRON + (255,), width=18)
    for k in range(12):
        a = math.radians(k * 30)
        r1, r2 = r - 30, r - (52 if k % 3 == 0 else 42)
        d.line((c + r1 * math.sin(a), c - r1 * math.cos(a), c + r2 * math.sin(a), c - r2 * math.cos(a)),
               fill=NAVY + (255,), width=8 if k % 3 == 0 else 4)
    d.line((c, c, c + 70, c - 40), fill=NAVY + (255,), width=12)
    d.line((c, c, c - 20, c - 115), fill=NAVY + (255,), width=9)
    d.ellipse((c - 14, c - 14, c + 14, c + 14), fill=POST_RED + (255,))
    return im


@lru_cache(maxsize=2)
def ill_van(size=420):
    im = _ill_canvas(size)
    d = ImageDraw.Draw(im)
    y0 = 120
    d.rounded_rectangle((20, y0, 280, y0 + 170), radius=18, fill=POST_RED + (255,))
    d.polygon([(280, y0 + 40), (360, y0 + 40), (400, y0 + 100), (400, y0 + 170), (280, y0 + 170)],
              fill=(190, 25, 45, 255))
    d.polygon([(292, y0 + 52), (352, y0 + 52), (382, y0 + 98), (292, y0 + 98)], fill=(200, 230, 255, 255))
    d.rectangle((20, y0 + 110, 280, y0 + 124), fill=(255, 214, 102, 255))
    env = envelope_sprite(150)
    im.paste(env, (70, y0 + 10), env)
    for x in (95, 320):
        d.ellipse((x - 42, y0 + 140, x + 42, y0 + 224), fill=NAVY + (255,))
        d.ellipse((x - 18, y0 + 164, x + 18, y0 + 200), fill=(200, 200, 205, 255))
    return im


@lru_cache(maxsize=2)
def ill_coins(size=420):
    im = _ill_canvas(size)
    d = ImageDraw.Draw(im)
    for k in range(5):
        y = 300 - k * 34
        d.ellipse((70, y - 30, 250, y + 30), fill=(214, 150, 20, 255))
        d.ellipse((70, y - 42, 250, y + 18), fill=(255, 200, 60, 255), outline=(214, 150, 20, 255), width=4)
    d.ellipse((200, 90, 380, 270), fill=(255, 200, 60, 255), outline=(214, 150, 20, 255), width=10)
    d.ellipse((232, 122, 348, 238), outline=(214, 150, 20, 255), width=6)
    return im


@lru_cache(maxsize=2)
def ill_parcel(size=420):
    im = _ill_canvas(size)
    d = ImageDraw.Draw(im)
    d.polygon([(60, 150), (210, 90), (360, 150), (210, 210)], fill=(222, 170, 110, 255))
    d.polygon([(60, 150), (210, 210), (210, 380), (60, 320)], fill=(196, 140, 80, 255))
    d.polygon([(210, 210), (360, 150), (360, 320), (210, 380)], fill=(176, 120, 64, 255))
    d.polygon([(125, 124), (275, 184), (275, 214), (125, 154)], fill=(255, 236, 200, 255))
    d.rectangle((240, 250, 330, 300), fill=(255, 255, 255, 255))
    d.line((250, 265, 320, 265), fill=NAVY + (255,), width=5)
    d.line((250, 283, 300, 283), fill=NAVY + (255,), width=5)
    return im


@lru_cache(maxsize=2)
def ill_letter(size=420):
    im = _ill_canvas(size)
    env = envelope_sprite(330)
    im.paste(env, (40, 110), env)
    d = ImageDraw.Draw(im)
    d.rectangle((270, 70, 380, 190), fill=(255, 255, 255, 255), outline=POST_RED + (255,), width=6)
    d.rectangle((288, 88, 362, 172), fill=(255, 214, 102, 255))
    d.ellipse((300, 104, 350, 154), fill=POST_RED + (255,))
    return im


TOPIC_ILLUSTRATIONS = [
    (("night", "रात्रि", "रात"), ill_moon),
    (("mobile", "मोबाइल", "चल डाक"), ill_van),
    (("hour", "time", "timing", "week day", "holiday", "sunday", "समय", "घंटे", "अवकाश", "रविवार"), ill_clock),
    (("money order", "fee", "rate", "charge", "commission", "postage", "मनीऑर्डर", "शुल्क", "प्रभार", "दर"), ill_coins),
    (("parcel", "पार्सल"), ill_parcel),
    (("letter", "stamp", "post card", "पत्र", "टिकट", "पोस्टकार्ड", "लिफाफा"), ill_letter),
]


def topic_illustration(plan):
    """Clause ke title se chitra chuno; kuch na mile to postbox."""
    hay = " ".join([plan.get("title_en", ""), plan.get("title_hi", "")]).lower()
    for words, fn in TOPIC_ILLUSTRATIONS:
        if any(w in hay for w in words):
            return fn()
    return postbox_sprite(400)


@lru_cache(maxsize=2)
def monogram(size=64):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 4, fill=NAVY + (255,))
    d.text((size / 2, size / 2 + 1), "PW", font=get_font(int(size * 0.44)), fill=SAFFRON + (255,), anchor="mm")
    return im


def slide_base(num, total, mood=None, clause_no=None, dark_top=False):
    cv = cream_bg().copy()
    d = ImageDraw.Draw(cv)
    tcol, scol = (WHITE_C, (190, 200, 220)) if dark_top else (NAVY, GREY_T)
    place(cv, monogram(60), 92, 78)
    d.text((136, 64), "Postal Wala", font=get_font(34), fill=tcol, anchor="lm")
    d.text((136, 98), "GDS  |  MTS  |  Postman  |  PA", font=get_font_reg(24), fill=scol, anchor="lm")
    if clause_no:
        chip = f"Clause {clause_no}"
        f = get_font(28)
        cw = text_w(chip, f) + 44
        d.rounded_rectangle((SW - 60 - cw, 56, SW - 60, 102), radius=23, outline=SAFFRON, width=3)
        d.text((SW - 60 - cw / 2, 79), chip, font=f, fill=SAFFRON, anchor="mm")
    # footer
    fy = SH - 62
    d.line((60, SH - 118, SW - 60, SH - 118), fill=(228, 216, 194), width=2)
    place(cv, icon_bookmark(40, NAVY), 80, fy)
    d.text((110, fy), "SAVE करें", font=get_font(30), fill=NAVY, anchor="lm")
    gap = 24
    x0 = SW / 2 - gap * (total - 1) / 2
    for k in range(total):
        on = k + 1 == num
        if on:
            d.rounded_rectangle((x0 + k * gap - 16, fy - 7, x0 + k * gap + 16, fy + 7), radius=7, fill=SAFFRON)
        else:
            d.ellipse((x0 + k * gap - 6, fy - 6, x0 + k * gap + 6, fy + 6), fill=(214, 200, 176))
    right = "आगे स्वाइप करें" if num < total else "SHARE करें"
    d.text((SW - 60, fy), right, font=get_font(30), fill=SAFFRON if num < total else POST_RED, anchor="rm")
    return cv


def slide_title(plan, parts, total):
    num = plan["clause_no"]
    title = plan.get("title_hi") or plan.get("title_en", "")
    cv = cream_bg().copy()
    d = ImageDraw.Draw(cv)
    # upar navy panel (hero)
    d.rounded_rectangle((40, 30, SW - 40, 700), radius=40, fill=NAVY)
    g = glow_sprite(380, SAFFRON, 55)
    cv.paste(g, (SW - 560, -120), g)
    base = slide_base(1, total, clause_no=num, dark_top=True)
    cv.paste(base.crop((0, SH - 130, SW, SH)), (0, SH - 130))
    d = ImageDraw.Draw(cv)
    place(cv, monogram(60), 92, 88)
    d.text((136, 74), "Postal Wala", font=get_font(34), fill=WHITE_C, anchor="lm")
    d.text((136, 108), "GDS  |  MTS  |  Postman  |  PA", font=get_font_reg(24), fill=(190, 200, 220), anchor="lm")
    d.text((90, 210), f"PO GUIDE PART I   |   CLAUSE {num}", font=get_font(32), fill=SAFFRON, anchor="lm")
    f, s_, lines = fit_lines_f(title, 600, 2, 112, 56, get_font)
    lines = lines[:2]                                   # panel se bahar na jaaye
    y = 260
    for ln in lines:
        d.text((86, y + s_ * 0.62), " ".join(ln), font=f, fill=WHITE_C, anchor="lm")
        y += int(s_ * 1.2)
    d.rounded_rectangle((90, y + 14, 250, y + 26), radius=6, fill=SAFFRON)
    sub = f"परीक्षा के लिए {len(parts)} ज़रूरी नियम"
    rich_text(cv, sub, 90, y + 48, 600, 46, color=(220, 228, 240), max_lines=2, min_size=34)
    ill = topic_illustration(plan)
    place(cv, ill, SW - 210, 500, scale=min(1.0, 400 / max(ill.width, ill.height)))
    # neeche: is post me
    d = ImageDraw.Draw(cv)
    d.text((80, 770), "इस पोस्ट में", font=get_font(44), fill=NAVY, anchor="lm")
    items = [(f"{len(parts)} पक्के नियम, PO Guide से", icon_tick(46)),
             (f"{len(parts)} EXAM TRAP, जहाँ अक्सर गलती होती है", icon_xcircle(46)),
             ("1 मिनट रिवीजन + खुद को परखें", icon_bulb_small(46))]
    y = 830
    for txt, ic in items:
        place(cv, ic, 104, y + 26)
        rich_text(cv, txt, 146, y, SW - 240, 38, color=NAVY, max_lines=1, min_size=28)
        y += 66
    # curiosity card
    q = strip_brackets(parts[0].get("question", ""))
    ch = rich_h(q, SW - 240, 40, 2, 30, weight="bold") + 96
    white_card(cv, 70, y + 20, SW - 140, ch, accent=SAFFRON)
    d = ImageDraw.Draw(cv)
    d.text((110, y + 58), "क्या आप जानते हैं?", font=get_font_reg(32), fill=SAFFRON, anchor="lm")
    rich_text(cv, q, 110, y + 82, SW - 240, 40, color=NAVY, max_lines=2, min_size=30, weight="bold")
    swipe_button(cv, y + 20 + ch / 2)
    return cv


def slide_rule(part, i, n, num, total, clause_no=None):
    cv = slide_base(num, total, clause_no=clause_no)
    keys = key_words(part)
    fact = strip_brackets(part.get("fact", ""))
    trap = strip_brackets(part.get("trap", ""))
    yaad = strip_brackets(part.get("yaad", ""))
    q = strip_brackets(part.get("question", ""))
    corr = strip_brackets(part.get(str(part.get("correct", "A")).lower(), ""))
    sq = " ".join((part.get("source_quote") or "").split())
    src_line = f"Source (PO Guide Part I, Clause {clause_no}): \u201c{sq}\u201d".replace("\u201c", '"').replace("\u201d", '"') if sq else ""
    X, CW = 70, SW - 140
    top, bottom = 140, SH - 140
    for sc_ in (1.14, 1.07, 1.0, 0.93, 0.86, 0.8, 0.74):
        qs, fs, ts_, ys_ = int(42 * sc_), int(56 * sc_), int(44 * sc_), int(52 * sc_)
        hq = rich_h(q, CW - 90, qs, 2, 28, weight="bold") + 150
        hf = rich_h(fact, CW - 60, fs, 5, 32) + 70
        ht = rich_h(trap, CW - 90, ts_, 3, 30) + 96
        hy = rich_h(yaad, CW - 90, ys_, 2, 32, weight="bold") + 96
        hs = rich_h(src_line, CW - 20, 24, 3, 20) + 16 if src_line else 0
        need = 120 + hq + 28 + hf + 24 + ht + 24 + hy + (20 + hs if hs else 0)
        if need <= bottom - top:
            break
    src_max_lines = 3
    if need > bottom - top and src_line:               # jagah kam: source 2 line, fir bhi kam to hatao
        src_max_lines = 2
        need -= hs - (rich_h(src_line, CW - 20, 24, 2, 20) + 16)
        if need > bottom - top:
            need -= 20 + rich_h(src_line, CW - 20, 24, 2, 20) + 16
            src_line = ""
    y = top + max(0, (bottom - top - need) / 2)
    d = ImageDraw.Draw(cv)
    d.text((X - 4, y + 56), f"{i:02d}", font=get_font(120), fill=SAFFRON, anchor="lm")
    d.text((X + 190, y + 38), "नियम", font=get_font(52), fill=NAVY, anchor="lm")
    d.text((X + 192, y + 90), f"{i} / {n}  -  PO Guide Part I", font=get_font_reg(28), fill=GREY_T, anchor="lm")
    y += 120
    # सवाल + सही उत्तर
    white_card(cv, X, y, CW, hq)
    d = ImageDraw.Draw(cv)
    d.text((X + 36, y + 38), "परीक्षा में ऐसे पूछा जाता है", font=get_font_reg(28), fill=GREY_T, anchor="lm")
    yq, _ = rich_text(cv, q, X + 36, y + 62, CW - 90, qs, color=NAVY, max_lines=2, min_size=28, weight="bold")
    chip_t = "सही उत्तर:  " + corr
    f = get_font(34)
    cw = min(CW - 72, text_w(chip_t, f) + 90)
    d.rounded_rectangle((X + 36, yq + 16, X + 36 + cw, yq + 72), radius=28, fill=(226, 246, 234))
    place(cv, icon_tick(38), X + 64, yq + 44)
    d.text((X + 94, yq + 44), chip_t, font=f, fill=LEAF, anchor="lm")
    y += hq + 28
    # नियम (bina dabbe - saaf padhai)
    d.text((X + 4, y + 20), "नियम", font=get_font(34), fill=LEAF, anchor="lm")
    d.line((X + 110, y + 22, X + CW, y + 22), fill=(214, 232, 220), width=3)
    rich_text(cv, fact, X + 4, y + 52, CW - 60, fs, color=NAVY, keys=keys, max_lines=5, min_size=32)
    y += hf + 24
    # EXAM TRAP
    white_card(cv, X, y, CW, ht, accent=POST_RED)
    d = ImageDraw.Draw(cv)
    place(cv, icon_xcircle(40), X + 56, y + 42)
    d.text((X + 86, y + 42), "EXAM TRAP", font=get_font(32), fill=POST_RED, anchor="lm")
    rich_text(cv, trap, X + 36, y + 72, CW - 90, ts_, color=NAVY, keys=keys, max_lines=3, min_size=30)
    y += ht + 24
    # SHORTCUT (akela gehra card = focal point)
    d.rounded_rectangle((X, y, X + CW, y + hy), radius=26, fill=NAVY)
    place(cv, icon_bulb_small(40), X + 56, y + 42)
    d.text((X + 86, y + 42), "SHORTCUT  -  याद रखिए", font=get_font(30), fill=SAFFRON, anchor="lm")
    rich_text(cv, yaad, X + 36, y + 70, CW - 90, ys_, color=WHITE_C, keys=keys, marker=None,
              key_color=SAFFRON, max_lines=2, min_size=32, weight="bold")
    y += hy + 20
    if src_line:
        # asli English line - exam wale khud mila sakte hain (bharosa)
        f, s2, lines = fit_lines_f(src_line, CW - 20, src_max_lines, 24, 20, get_font_reg)
        shown = lines[:src_max_lines]
        dd = ImageDraw.Draw(cv)
        for k, ln in enumerate(shown):
            t = " ".join(ln)
            if k == len(shown) - 1 and len(lines) > len(shown):
                t = t.rstrip(".,") + " ..."
            if y + k * int(s2 * 1.35) + s2 > SH - 128:      # footer line se upar hi ruko
                break
            dd.text((X + 6, y + k * int(s2 * 1.35) + s2 * 0.6), t, font=f, fill=GREY_T, anchor="lm")
    swipe_button(cv)
    return cv


def slide_quiz(qs, num, total, clause_no=None):
    cv = slide_base(num, total, clause_no=clause_no)
    d = ImageDraw.Draw(cv)
    d.text((70, 190), "खुद को परखें", font=get_font(78), fill=NAVY, anchor="lm")
    d.rounded_rectangle((74, 236, 234, 248), radius=6, fill=SAFFRON)
    d.text((70, 290), "अपने उत्तर कमेंट में लिखें  -  जवाब अगली स्लाइड पर", font=get_font_reg(32),
           fill=GREY_T, anchor="lm")
    top, bottom = 340, SH - 140
    for qsz, oh, og in ((38, 66, 76), (35, 62, 72), (32, 58, 66), (29, 54, 62)):
        blocks = [rich_h(d_["question"], SW - 290, qsz, 2, 26, weight="bold") + 50 + og + oh
                  for d_ in qs]
        if sum(blocks) + 22 * (len(qs) - 1) <= bottom - top:
            break
    y = top + max(0, ((bottom - top) - sum(blocks) - 22 * (len(qs) - 1)) / 2)
    for k, d_ in enumerate(qs, 1):
        bh = blocks[k - 1]
        white_card(cv, 70, y, SW - 140, bh - 8)
        d = ImageDraw.Draw(cv)
        d.ellipse((96, y + 24, 144, y + 72), fill=NAVY)
        d.text((120, y + 48), str(k), font=get_font(30), fill=SAFFRON, anchor="mm")
        yq, _ = rich_text(cv, d_["question"], 166, y + 24, SW - 290, qsz, color=NAVY, max_lines=2,
                          min_size=26, weight="bold")
        oy = max(yq, y + 72) + 14
        for m_, (l, txt) in enumerate(d_["options"]):
            cx0 = 96 + (m_ % 2) * 452
            cy0 = oy + (m_ // 2) * og
            d.rounded_rectangle((cx0, cy0, cx0 + 432, cy0 + oh - 10), radius=(oh - 10) // 2,
                                fill=(250, 245, 236), outline=(228, 216, 194), width=2)
            rr = (oh - 10) / 2 - 7
            d.ellipse((cx0 + 7, cy0 + 7, cx0 + 7 + 2 * rr, cy0 + 7 + 2 * rr), outline=NAVY, width=3)
            d.text((cx0 + 7 + rr, cy0 + 7 + rr), l, font=get_font(int(rr * 1.05)), fill=NAVY, anchor="mm")
            ff, s2, ls = fit_lines_f(txt, 432 - 2 * rr - 40, 1, int(oh * 0.44), 20, get_font_reg)
            d.text((cx0 + 2 * rr + 26, cy0 + (oh - 10) / 2), " ".join(ls[0]) if ls else "", font=ff,
                   fill=NAVY, anchor="lm")
        y += bh + 22
    return cv


def slide_revision(parts, quiz, num, total, clause_no, next_teaser=""):
    cv = slide_base(num, total, clause_no=clause_no)
    d = ImageDraw.Draw(cv)
    d.text((70, 190), "1 मिनट रिवीजन", font=get_font(78), fill=NAVY, anchor="lm")
    d.rounded_rectangle((74, 236, 234, 248), radius=6, fill=SAFFRON)
    d.text((70, 290), "Screenshot लें या SAVE करें", font=get_font_reg(32), fill=GREY_T, anchor="lm")
    # jagah ke hisaab se font aur rows (SAVE card aur quiz ke jawab kabhi dhake na)
    avail = (SH - 140) - 340 - 8 - 44 - (130 if quiz else 0) - 150
    rows, rs, hs = parts[:7], 44, []
    done = False
    for n_rows in range(min(7, len(parts)), 0, -1):
        for rs in (44, 40, 36, 32):
            hs = [rich_h(strip_brackets(p.get("yaad", "")), SW - 330, rs, 2, 28, weight="bold") + (44 if rs >= 40 else 34)
                  for p in parts[:n_rows]]
            if sum(hs) <= avail:
                rows, done = parts[:n_rows], True
                break
        if done:
            break
    y = 340
    white_card(cv, 70, y, SW - 140, sum(hs) + 8)
    for k, (p, h) in enumerate(zip(rows, hs), 1):
        d = ImageDraw.Draw(cv)
        if k % 2 == 0:
            d.rectangle((72, y + 4, SW - 72, y + h + 4), fill=(251, 246, 238))
        d.ellipse((100, y + h / 2 - 24, 148, y + h / 2 + 24), fill=SAFFRON)
        d.text((124, y + h / 2 + 4), str(k), font=get_font(30), fill=WHITE_C, anchor="mm")
        rich_text(cv, strip_brackets(p.get("yaad", "")), 176, y + (h - rich_h(strip_brackets(p.get("yaad", "")),
                  SW - 330, rs, 2, 28, weight="bold")) / 2, SW - 330, rs, color=NAVY,
                  keys=key_words(p), max_lines=2, min_size=28, weight="bold")
        y += h
    y += 44
    if quiz:
        d = ImageDraw.Draw(cv)
        d.text((70, y + 10), "खुद को परखें - उत्तर", font=get_font(34), fill=NAVY, anchor="lm")
        x = 70
        for k, d_ in enumerate(quiz, 1):
            t = f"{k}  -  {d_['correct']}"
            f = get_font(34)
            w = text_w(t, f) + 50
            d.rounded_rectangle((x, y + 44, x + w, y + 100), radius=28, fill=(226, 246, 234))
            d.text((x + w / 2, y + 72), t, font=f, fill=LEAF, anchor="mm")
            x += w + 16
        y += 130
    # SAVE card - andar agle post ka teaser (follow ki wajah)
    d = ImageDraw.Draw(cv)
    box_bottom = SH - 140
    tz = next_teaser or ""
    t_h = rich_h(tz, SW - 250, 34, 2, 26, weight="bold") if tz else 0
    h = 96 + (t_h + 56 if tz else 44)
    if tz and box_bottom - h < y + 10:              # jagah kam: teaser 1 line
        t_h = rich_h(tz, SW - 250, 30, 1, 24, weight="bold")
        h = 96 + t_h + 56
        if box_bottom - h < y + 10:
            tz, h = "", 140
    by = box_bottom - h
    d.rounded_rectangle((70, by, SW - 70, box_bottom), radius=30, fill=NAVY)
    place(cv, icon_bookmark(56, SAFFRON), 126, by + 50)
    d.text((170, by + 50), "SAVE करें, परीक्षा से पहले काम आएगा", font=get_font(36), fill=WHITE_C, anchor="lm")
    if tz:
        d.line((104, by + 92, SW - 104, by + 92), fill=(60, 75, 110), width=2)
        d.text((104, by + 122), "अगले पोस्ट में:", font=get_font_reg(28), fill=SAFFRON, anchor="lm")
        rich_text(cv, tz, 104, by + 142, SW - 250, 34 if t_h > 50 else 30, color=WHITE_C, max_lines=2,
                  min_size=24, weight="bold")
    else:
        d.text((170, by + 100), "अपने GDS / Postman साथी को SHARE करें  |  " + IG_HANDLE,
               font=get_font_reg(27), fill=(190, 200, 220), anchor="lm")
    return cv


def make_carousel(plan, next_teaser=""):
    """
    Clause poora hone pe save-karne-layak carousel:
    1 hook slide -> har niyam ki slide -> 'खुद को परखें' quiz -> 1 मिनट रिवीजन + jawab.
    """
    parts = usable_parts(plan)[:8]
    if not parts:
        raise ValueError("koi pakka part nahi")
    num = plan["clause_no"]
    quiz = []
    for i, p in enumerate(parts[:3], 1):
        try:
            quiz.append(prepare_data(dict(p, title=""), num, 100 + i))
        except Exception as exc:
            print(f"  quiz sawal {i} chhoda (data me kami):", exc)
    total = 1 + len(parts) + (1 if quiz else 0) + 1
    slides = [slide_title(plan, parts, total)]
    for i, p in enumerate(parts, 1):
        slides.append(slide_rule(p, i, len(parts), i + 1, total, clause_no=num))
    if quiz:
        slides.append(slide_quiz(quiz, len(slides) + 1, total, clause_no=num))
    slides.append(slide_revision(parts, quiz, total, total, num, next_teaser=next_teaser))

    out_dir = os.path.join(OUTPUT_DIR, "carousel", f"clause_{num}")
    os.makedirs(out_dir, exist_ok=True)
    for f_ in os.listdir(out_dir):
        if f_.endswith(".jpg"):
            os.remove(os.path.join(out_dir, f_))
    for k, sl in enumerate(slides, 1):
        sl.save(os.path.join(out_dir, f"{k:02d}.jpg"), quality=93)
    title = plan.get("title_hi") or plan.get("title_en", "")
    cap = [f"Clause {num}: {title} | {len(parts)} नियम + {len(parts)} EXAM TRAP | PO Guide Part I",
           "",
           "📌 परीक्षा से पहले 1 मिनट में रिवीजन के लिए SAVE कर लीजिए",
           "🧠 आखिर में 'खुद को परखें' - अपने उत्तर कमेंट में लिखें",
           "🤝 अपने GDS / Postman साथी को SHARE करें",
           f"🎯 FREE MOCK TEST चाहिए? कमेंट करें: {MOCK_KEYWORD}",
           "",
           HASHTAGS]
    with open(os.path.join(out_dir, "caption.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(cap))
    return out_dir


# ==================== MAIN ====================

def list_clauses():
    clauses = split_clauses(read_pdf_text())
    syl = set(syllabus_clauses(clauses.keys()))
    print(f"{len(clauses)} clause mile official PDF me ({len(syl)} syllabus me):")
    for n, t in clauses.items():
        mark = "*" if n in syl else " "
        print(f" {mark}{n:>3}. {clause_title_en(t)[:70]}  ({len(t)} chars)")


MAX_NEW_PLANS_PER_RUN = 2


def run_daily():
    _RUN_FLAGS.update({"busy": False, "builds": 0})
    try:
        b = make_branding()
        if b:
            print("Branding images bani (sirf ek baar):", b)
    except Exception as exc:
        print("Branding nahi bani (koi baat nahi):", exc)
    _BUSY.clear()
    if not os.path.exists(find_guide_pdf()):
        print(f"RUKA: '{PDF_FILE}' repo me nahi hai. Official PO Guide Part I ki PDF isi naam se daaliye. "
              "Bina official source ke koi reel nahi banegi.")
        return
    clauses = split_clauses(read_pdf_text())
    order = syllabus_clauses(clauses.keys())
    if not order:
        print("RUKA: PDF me koi clause nahi mila. `python main.py --list-clauses` chala ke dekhiye.")
        return

    state = load_state()
    if state["clause_no"] not in order:
        later = [n for n in order if n >= state["clause_no"]]
        state["clause_no"] = later[0] if later else order[0]
    print("Current State:", {k: v for k, v in state.items() if k != "voice_rotation"})

    for pl in all_plans():
        enforce_lengths(pl)

    # 1) pichhle chhoote parts ko sudharne ki koshish
    try:
        repair_pass(clauses)
    except Exception as exc:
        print("Sudhaar pass me dikkat (aage badh rahe hain):", exc)

    # 2) aaj kya publish ho: pehle sudhara hua purana part, warna current clause ka agla part
    pick = pending_repaired(state["clause_no"])
    advance_main = False
    if pick:
        plan, part, part_no, total = pick
        num = plan["clause_no"]
        print(f"Aaj pichhla sudhara hua part: Clause {num} Part {part_no}/{total}")
    else:
        part = None
        for _ in range(len(order) + 1):
            num = state["clause_no"]
            plan = load_plan(num)
            if plan is None:
                if _RUN_FLAGS["busy"] or _RUN_FLAGS["builds"] >= MAX_NEW_PLANS_PER_RUN:
                    print("Is run me aur naya plan nahi (AI busy / API bachat). Agle slot me.")
                    return
                print(f"Clause {num}: official PDF se plan ban raha hai...")
                _RUN_FLAGS["builds"] += 1
                try:
                    plan = build_plan(num, clauses)
                except ProviderBusy as exc:
                    print(f"AI abhi busy / quota khatam ({str(exc)[:150]}). Aaj is slot me reel nahi - agle slot me apne aap.")
                    return
                except Exception as exc:
                    print(f"Clause {num} ka plan banate waqt dikkat ({type(exc).__name__}: {str(exc)[:200]}). "
                          "Agle slot me dobara koshish hogi.")
                    return
            part, part_no, total = next_unpublished(plan)
            if part is not None:
                advance_main = True
                break
            if any(is_pending(p) for p in plan.get("parts", [])) and _RUN_FLAGS["busy"]:
                print(f"Clause {num}: jaanch baaki hai aur AI busy hai. Agle slot me yahin se.")
                return
            pending = sum(1 for p in plan.get("parts", []) if not p.get("auto_check"))
            if pending:
                print(f"Clause {num}: {pending} part abhi fail hain -> baad me sudhaar ke aayenge. Agla clause.")
            state["clause_no"] = next_clause_no(num, order)
            state["current_part"] = 1
            save_state(state)
        if part is None:
            print("Aaj koi pakka part nahi mila. Reel nahi banegi (galat reel se behtar).")
            return

    nxt = next_clause_no(num, order)
    if part_no < total:
        next_title = plan.get("title_hi", "")
    else:
        next_title = (load_plan(nxt) or {}).get("title_hi") or "अगला नियम"

    try:
        ensure_english(plan, part)          # English subtitle (ek baar banke save)
    except Exception as exc:
        print("  English line nahi bani:", str(exc)[:120])
    try:
        ensure_beats(plan, part)            # niyam ke yaad-tukde (ek baar banke save)
    except Exception as exc:
        print("  Yaad-tukde nahi bane:", str(exc)[:120])
    data_in = dict(part)
    data_in["title"] = plan.get("title_hi") or plan.get("title_en", "")
    data = prepare_data(data_in, num, part_no, total_parts=total, next_title=next_title,
                        syllabus=(order.index(num) + 1 if num in order else None, len(order)))
    data["teaser"] = find_teaser(plan, part, nxt)
    if not data["teaser"] and nxt in clauses:
        # agle clause ka plan abhi nahi bana: PDF se uska asli naam
        data["teaser"] = f"Clause {nxt}: {clause_title_en(clauses[nxt])}"
    print("\nSCRIPT DATA:")
    print(json.dumps({k: v for k, v in data.items() if k not in ("hl_words",)}, ensure_ascii=False, indent=2))
    print("SOURCE (PO Guide):", part.get("source_quote", ""))

    voice_entry = None
    if rotation_active() and not DRY_RUN and GEMINI_API_KEY:
        try:
            rot = build_voice_rotation(state)
            voice_entry = rot[int(state.get("voice_idx", 0)) % len(rot)]
            apply_voice(voice_entry)
            print(f"Is reel ki awaaz: {voice_entry['name']} ({voice_entry['gender']}) "
                  f"[{int(state.get('voice_idx', 0)) % len(rot) + 1}/{len(rot)}]")
        except Exception as exc:
            print("Awaaz rotation nahi chala (default awaaz):", str(exc)[:120])
            voice_entry = None

    out = os.path.join(OUTPUT_DIR, f"reel_clause_{num}_part_{part_no}.mp4")
    k_ = 2
    while os.path.exists(out) and not DRY_RUN:          # purani reel kabhi overwrite na ho
        out = os.path.join(OUTPUT_DIR, f"reel_clause_{num}_part_{part_no}_v{k_}.mp4")
        k_ += 1
    build_reel(data, out)
    jobs0 = [(lambda: write_caption(data, out.replace(".mp4", "_caption.txt")), "caption")]
    if MAKE_COVER:
        jobs0.append((lambda: make_cover(data, out.replace(".mp4", "_cover.jpg")), "cover"))
    for fn, what in jobs0:
        try:
            fn()
        except Exception as exc:
            print(f"{what} nahi bana:", exc)
    if DRY_RUN:
        return

    # publish mark (index ki jagah flag, taaki baad me sudhre parts se kram na bigde)
    import datetime
    part["published"] = datetime.date.today().isoformat()
    remember_reel(out)
    if voice_entry:
        try:
            log_voice(out, voice_entry, num, part_no)
        except Exception as exc:
            print("voice_log nahi likha:", exc)
        state["voice_idx"] = int(state.get("voice_idx", 0)) + 1
        save_state(state)
    save_plan(plan)
    clause_done = next_unpublished(plan)[0] is None

    if advance_main:
        _, left_no, _ = next_unpublished(plan)
        if left_no == 0:
            state["clause_no"] = nxt
        state["current_part"] = max(1, left_no)
        save_state(state)

    upcoming = state["clause_no"]
    if load_plan(upcoming) is None and not _RUN_FLAGS["busy"] and _RUN_FLAGS["builds"] == 0:
        try:
            print(f"Agle clause {upcoming} ka plan pehle se bana raha hoon...")
            build_plan(upcoming, clauses)
        except Exception as exc:
            print("Agla plan abhi nahi bana (agle run me banega):", exc)

    if clause_done and MAKE_CAROUSEL:
        try:
            print("Bana:", make_carousel(plan, carousel_teaser(nxt)))
        except Exception as exc:
            print("carousel nahi bana:", exc)

    cleanup_old_reels()
    try:
        vt = make_voice_test()
        if vt:
            print("Voice test bana (sirf ek baar):", vt)
    except Exception as exc:
        print("Voice test nahi bana (koi baat nahi):", str(exc)[:150])


REEL_INDEX = os.path.join(OUTPUT_DIR, "reel_index.json")


def remember_reel(path):
    """Banne ka kram yaad rakho (GitHub pe file ka samay bharosemand nahi hota)."""
    idx = []
    if os.path.exists(REEL_INDEX):
        try:
            with open(REEL_INDEX, encoding="utf-8") as f:
                idx = json.load(f)
        except Exception:
            idx = []
    name = os.path.basename(path)
    idx = [n for n in idx if n != name] + [name]
    with open(REEL_INDEX, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    return idx


def cleanup_old_reels(keep=None):
    """Repo bhaari na ho: sirf aakhri KEEP_LAST_REELS reels (.mp4 + caption) rakho."""
    keep = KEEP_LAST_REELS if keep is None else keep
    if not keep or not os.path.isdir(OUTPUT_DIR):
        return
    idx = []
    if os.path.exists(REEL_INDEX):
        try:
            with open(REEL_INDEX, encoding="utf-8") as f:
                idx = json.load(f)
        except Exception:
            idx = []
    vids = [f for f in os.listdir(OUTPUT_DIR) if f.startswith("reel_") and f.endswith(".mp4")]
    # suchi me na ho (purani) -> sabse pehle; baaki suchi ke kram me
    order = sorted([f for f in vids if f not in idx]) + [f for f in idx if f in vids]
    for f in order[:-keep]:
        for extra in (f, f.replace(".mp4", "_caption.txt"), f.replace(".mp4", "_cover.jpg")):
            fp = os.path.join(OUTPUT_DIR, extra)
            if os.path.exists(fp):
                os.remove(fp)
        print("Purani reel hatayi (repo halka rakhne ke liye):", f)
    if idx:
        with open(REEL_INDEX, "w", encoding="utf-8") as fh:
            json.dump([f for f in idx if f in set(order[-keep:])], fh, ensure_ascii=False, indent=1)


# ==================== BRANDING (ek baar): profile photo, highlights, intro post ====================

def _navy_bg(w, h):
    im = Image.new("RGB", (w, h), NAVY)
    g = glow_sprite(max(w, h) // 2, SAFFRON, 50)
    im.paste(g, (w - g.width // 2 - 60, -g.height // 2 + 80), g)
    g2 = glow_sprite(max(w, h) // 2, (70, 110, 200), 45)
    im.paste(g2, (-g2.width // 2 + 40, h - g2.height // 2 - 40), g2)
    return im


def make_profile_photo(path):
    """1080x1080, gole me bhi saaf: bada PW + naam."""
    S = 1080
    im = _navy_bg(S, S)
    d = ImageDraw.Draw(im)
    d.ellipse((40, 40, S - 40, S - 40), outline=SAFFRON, width=34)
    d.text((S / 2, S / 2 - 70), "PW", font=get_font(400), fill=WHITE_C, anchor="mm")
    d.rounded_rectangle((S / 2 - 170, S / 2 + 120, S / 2 + 170, S / 2 + 146), radius=13, fill=SAFFRON)
    d.text((S / 2, S / 2 + 235), "POSTAL WALA", font=get_font(96), fill=SAFFRON, anchor="mm")
    im.save(path)
    return path


def _hl_icon_book(d, c, r):
    x, y = c
    d.polygon([(x - r, y - r * 0.55), (x - 8, y - r * 0.4), (x - 8, y + r * 0.7), (x - r, y + r * 0.55)], fill=WHITE_C)
    d.polygon([(x + r, y - r * 0.55), (x + 8, y - r * 0.4), (x + 8, y + r * 0.7), (x + r, y + r * 0.55)], fill=WHITE_C)
    for k in range(3):
        yy = y - r * 0.2 + k * r * 0.25
        d.line((x - r * 0.8, yy, x - r * 0.25, yy + 8), fill=SAFFRON, width=10)
        d.line((x + r * 0.25, yy + 8, x + r * 0.8, yy), fill=SAFFRON, width=10)


def _hl_icon_list(d, c, r):
    x, y = c
    for k in range(4):
        yy = y - r * 0.6 + k * r * 0.4
        d.ellipse((x - r * 0.8 - 18, yy - 18, x - r * 0.8 + 18, yy + 18), fill=WHITE_C)
        d.rounded_rectangle((x - r * 0.5, yy - 12, x + r * 0.85, yy + 12), radius=12, fill=WHITE_C)


def _hl_icon_correction(d, c, r):
    x, y = c
    # pencil
    d.polygon([(x - r * 0.75, y + r * 0.45), (x + r * 0.35, y - r * 0.65), (x + r * 0.62, y - r * 0.38),
               (x - r * 0.48, y + r * 0.72)], fill=WHITE_C)
    d.polygon([(x - r * 0.75, y + r * 0.45), (x - r * 0.48, y + r * 0.72), (x - r * 0.9, y + r * 0.86)],
              fill=SAFFRON)
    # tick
    d.line((x - r * 0.05, y + r * 0.5, x + r * 0.2, y + r * 0.75, x + r * 0.85, y + r * 0.05),
           fill=SAFFRON, width=26, joint="curve")


def make_highlight(path, icon_fn):
    """1080x1920; Instagram beech ka gola dikhata hai, isliye icon beech me."""
    w, h = 1080, 1920
    im = _navy_bg(w, h)
    d = ImageDraw.Draw(im)
    c, r = (w / 2, h / 2), 330
    d.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), fill=(32, 50, 88), outline=SAFFRON, width=16)
    icon_fn(d, c, 210)
    im.save(path)
    return path


def make_intro_post(out_dir):
    """Pin karne layak 3 slide: page kya hai, kya milega, kaise fayda uthayein."""
    total = 3
    # 1) hero
    cv = cream_bg().copy()
    d = ImageDraw.Draw(cv)
    d.rounded_rectangle((40, 30, SW - 40, 760), radius=40, fill=NAVY)
    g = glow_sprite(380, SAFFRON, 55)
    cv.paste(g, (SW - 560, -120), g)
    base = slide_base(1, total, dark_top=True)
    cv.paste(base.crop((0, SH - 130, SW, SH)), (0, SH - 130))
    d = ImageDraw.Draw(cv)
    place(cv, monogram(60), 92, 88)
    d.text((136, 74), "Postal Wala", font=get_font(34), fill=WHITE_C, anchor="lm")
    d.text((136, 108), "GDS  |  MTS  |  Postman  |  PA", font=get_font_reg(24), fill=(190, 200, 220), anchor="lm")
    d.text((90, 210), "GDS से MTS / POSTMAN / PA", font=get_font(34), fill=SAFFRON, anchor="lm")
    y = 250
    for ln in ("तैयारी यहाँ", "से शुरू करें"):
        d.text((86, y + 62), ln, font=get_font(104), fill=WHITE_C, anchor="lm")
        y += 124
    d.rounded_rectangle((90, y + 14, 250, y + 26), radius=6, fill=SAFFRON)
    rich_text(cv, "पूरा सिलेबस, आसान हिंदी में, रोज़", 90, y + 48, 560, 44, color=(220, 228, 240),
              max_lines=2, min_size=32)
    place(cv, postbox_sprite(400), SW - 210, 560)
    d = ImageDraw.Draw(cv)
    d.text((80, 830), "Postal Wala क्या है?", font=get_font(48), fill=NAVY, anchor="lm")
    rich_text(cv, "GDS से MTS, Postman और PA की विभागीय परीक्षा का पूरा सिलेबस, "
                  "हर दिन, सवाल और EXAM TRAP के साथ।", 80, 880, SW - 160, 42, color=NAVY,
              keys=("पूरा", "सिलेबस,", "EXAM", "TRAP"), max_lines=4, min_size=32)
    swipe_button(cv, 1100)
    slides = [cv]

    # 2) kya milega
    cv = slide_base(2, total)
    d = ImageDraw.Draw(cv)
    d.text((70, 190), "यहाँ आपको क्या मिलेगा", font=get_font(70), fill=NAVY, anchor="lm")
    d.rounded_rectangle((74, 236, 234, 248), radius=6, fill=SAFFRON)
    items = [
        ("रोज़ 1 नियम", "छोटी Reel में सवाल, सही उत्तर और नियम", icon_tick(52)),
        ("हर नियम का Source", "नियम-पुस्तक की असली लाइन के साथ, खुद मिलाइए", icon_tick(52, (37, 99, 235))),
        ("EXAM TRAP", "जहाँ अक्सर गलती होती है, पहले से सावधान", icon_xcircle(52)),
        ("1 मिनट रिवीजन", "हर टॉपिक का Carousel, SAVE करके रखिए", icon_bookmark(52, SAFFRON)),
        ("खुद को परखें", "Quiz से अपनी तैयारी जाँचिए", icon_bulb_small(52)),
    ]
    y = 300
    for head, sub, ic in items:
        white_card(cv, 70, y, SW - 140, 150)
        place(cv, ic, 130, y + 75)
        d = ImageDraw.Draw(cv)
        d.text((180, y + 52), head, font=get_font(44), fill=NAVY, anchor="lm")
        d.text((180, y + 104), sub, font=get_font_reg(32), fill=GREY_T, anchor="lm")
        y += 172
    slides.append(cv)

    # 3) kaise fayda
    cv = slide_base(3, total)
    d = ImageDraw.Draw(cv)
    d.text((70, 190), "कैसे फायदा उठाएँ", font=get_font(70), fill=NAVY, anchor="lm")
    d.rounded_rectangle((74, 236, 234, 248), radius=6, fill=SAFFRON)
    steps = [("FOLLOW करें", "ताकि रोज़ का नियम छूटे नहीं"),
             ("हर Reel में उत्तर कमेंट करें", "A / B / C / D, खुद को परखिए"),
             ("Carousel SAVE करें", "परीक्षा से पहले 1 मिनट में रिवीजन"),
             ("साथियों को SHARE करें", "साथ पढ़ेंगे तो साथ आगे बढ़ेंगे")]
    y = 300
    for k, (head, sub) in enumerate(steps, 1):
        d = ImageDraw.Draw(cv)
        d.ellipse((74, y + 14, 138, y + 78), fill=SAFFRON)
        d.text((106, y + 47), str(k), font=get_font(38), fill=WHITE_C, anchor="mm")
        d.text((166, y + 32), head, font=get_font(44), fill=NAVY, anchor="lm")
        d.text((166, y + 82), sub, font=get_font_reg(32), fill=GREY_T, anchor="lm")
        if k < len(steps):
            d.line((106, y + 88, 106, y + 150), fill=(226, 212, 188), width=4)
        y += 160
    by = SH - 330
    d.rounded_rectangle((70, by, SW - 70, by + 170), radius=30, fill=NAVY)
    d.text((SW / 2, by + 62), "FOLLOW  " + IG_HANDLE, font=get_font(52), fill=SAFFRON, anchor="mm")
    d.text((SW / 2, by + 122), "सवाल या डाउट? Bio में WhatsApp लिंक", font=get_font_reg(32),
           fill=(200, 210, 228), anchor="mm")
    slides.append(cv)

    for k, sl in enumerate(slides, 1):
        sl.save(os.path.join(out_dir, f"intro_{k:02d}.jpg"), quality=93)
    cap = ["GDS से MTS / Postman / PA की तैयारी? यहाँ से शुरू करें 📮", "",
           "📘 GDS से MTS / Postman / PA का पूरा सिलेबस, रोज़",
           "✅ हर नियम Source के साथ",
           "⚠️ EXAM TRAP + 1 मिनट रिवीजन Carousel",
           f"🎯 FREE MOCK TEST चाहिए? कमेंट करें: {MOCK_KEYWORD}",
           "", "FOLLOW करें और अपने साथियों को SHARE करें 🙏", "", HASHTAGS]
    with open(os.path.join(out_dir, "intro_caption.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(cap))


def make_branding(force=False):
    out_dir = os.path.join(OUTPUT_DIR, "branding")
    if os.path.isdir(out_dir) and not force:
        return None
    os.makedirs(out_dir, exist_ok=True)
    make_profile_photo(os.path.join(out_dir, "profile_photo.png"))
    make_highlight(os.path.join(out_dir, "highlight_syllabus.png"), _hl_icon_book)
    make_highlight(os.path.join(out_dir, "highlight_topic_list.png"), _hl_icon_list)
    make_highlight(os.path.join(out_dir, "highlight_correction.png"), _hl_icon_correction)
    make_intro_post(out_dir)
    return out_dir


def carousel_teaser(nxt):
    """Agle clause ka pehla sawal (plan ho to), warna uska naam."""
    np_ = load_plan(nxt) if nxt else None
    if np_:
        for p in usable_parts(np_):
            return f"Clause {nxt}: " + strip_brackets(p.get("question", ""))
        if np_.get("title_hi"):
            return f"Clause {nxt}: {np_['title_hi']}"
    return f"Clause {nxt} - PO Guide Part I" if nxt else ""


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--list-clauses"]:
        list_clauses()
    elif args[:1] == ["--voice-test"]:
        import shutil
        shutil.rmtree(os.path.join(OUTPUT_DIR, "voice_test"), ignore_errors=True)
        print(make_voice_test())
    elif args[:1] == ["--branding"]:
        print(make_branding(force=True))
    elif args[:1] == ["--build"] and len(args) >= 2:
        for n in args[1:]:
            build_plan(int(n))
    else:
        run_daily()
