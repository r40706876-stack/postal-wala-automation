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

Reel flow: HOOK -> SAWAL -> COUNTDOWN -> HINT -> GALAT HATAO -> JAWAB -> NIYAM + TRAP -> YAAD RAKHIYE
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

VOICE_NAME = "hi-IN-SwaraNeural"
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
MOCK_KEYWORD = "MOCK"          # comment me ye likhne pe free mock test
IG_HANDLE = "@POSTAL_WALA"
HASHTAGS = "#gdstomts #postmanexam #mtsexam #poguide #indiapost #gds #postalexam #departmentalexam"
SHOW_HINT = False             # hint scene band: AI isme clause ke bahar ki wajah gadh deta tha
MAX_REPAIR_TRIES = 4          # ek chhoote part ko kitni baar (alag-alag din) sudharne ki koshish
REPAIRS_PER_RUN = 2           # ek run me kitne chhoote parts sudharne ki koshish (API kharcha seemit)
# Coaching notes (optional): sirf ye tay karne ke liye ki kaunse clause syllabus me hain.
# Niyam ka sach hamesha official PO Guide se hi liya jaata hai.
NOTES_PDF = os.getenv("NOTES_PDF", "mts content .pdf")


# ==================== TEXT HELPERS ====================

_ALLOWED = re.compile(r"[^\u0900-\u097F\u0020-\u007E\u00A0-\u00FF\u2010-\u2027\u20B9]")


def clean_text(text):
    """Emoji / unsupported glyph hata deta hai (purane video me yahi box ban rahe the)."""
    if not text:
        return ""
    text = re.sub(r"[*_`#]+", "", str(text))
    text = text.replace("…", "...").replace("—", "-").replace("–", "-")
    text = (text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"')
            .replace("\u201d", '"').replace("\u2022", "-").replace("\u2192", "-"))
    text = re.sub(r"[\u2010-\u2027]", "-", text)   # baaki general punctuation -> '-' (font me na ho to dabba banta)
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


def text_w(text, font):
    return font.getlength(text)


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


@lru_cache(maxsize=128)
def option_sprite(letter, text, w, h, state):
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

    f, s, lines = fit_lines(text, w - (br * 2 + 110), 2, int(h * 0.33), 30)
    lh = int(s * 1.32)
    y0 = by - (len(lines) - 1) * lh / 2
    for i, ln in enumerate(lines):
        d.text((bx + br + 40, y0 + i * lh), " ".join(ln), font=f, fill=tcol + (255,), anchor="lm")

    if state == "wrong":
        tw = max(text_w(" ".join(l), f) for l in lines)
        d.line((bx + br + 35, by, bx + br + 45 + tw, by), fill=RED + (230,), width=6)
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

def _norm_en(s):
    s = (s or "").lower().replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[\u2014\u2013-]", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(s.split())


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


def term_errors(part):
    errs = []
    src = (part.get("source_quote", "") + " " + part.get("trap_quote", "")).lower()
    fields = ("fact", "question", "a", "b", "c", "d", "trap", "yaad", "hook", "hint")
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
        n = words(part.get(k, ""))
        if n > lim:
            errs.append(f"LENGTH: '{k}' {n} shabd ka hai, seema {lim} - chhota karo, koi shart/sankhya mat hatao")
    return errs


def verify_part(part, clause_text):
    """Jo bhi check fail ho, uski wajah lautata hai. Khaali list = pass."""
    errs = []
    need = ["source_quote", "hook", "question", "a", "b", "c", "d", "correct", "hint", "fact", "trap", "yaad"]
    for k in need:
        if not str(part.get(k, "")).strip():
            errs.append(f"'{k}' khaali hai")
    if errs:
        return errs

    errs += length_errors(part)
    errs += term_errors(part)
    if not quote_in_source(part["source_quote"], clause_text):
        errs.append("source_quote PDF ke clause me nahi mila")
    trap_q = part.get("trap_quote", "")
    if trap_q and not quote_in_source(trap_q, clause_text):
        errs.append("trap_quote PDF ke clause me nahi mila")

    corr = str(part["correct"]).strip().upper()[:1]
    if corr not in ("A", "B", "C", "D"):
        errs.append("correct A/B/C/D nahi hai")
        return errs
    opts = [clean_text(part[k]) for k in "abcd"]
    if len(set(opts)) != 4:
        errs.append("options me duplicate hai")

    allowed = number_groups(part["source_quote"], "en")
    allowed_trap = allowed + number_groups(trap_q, "en")
    for field in ("fact", "yaad", "hint"):
        extra = _extra(part[field], allowed)
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
        if r.status_code in (404, 429, 503, 500):
            print(f"  Gemini {model}: {r.status_code} (busy/quota) -> agla model")
            _BUSY.add(model)
            last = RuntimeError(f"{model} {r.status_code}")
            continue
        _raise_for(r, f"Gemini({model})")
        parts = r.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return _parse_json(text)
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


def _parse_json(raw):
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

STRICT RULES:
1. source_quote: copy 1-3 sentences from the clause EXACTLY word for word (English). Every fact of the
   part must be fully supported by this quote alone.
2. fact: faithful Hindi translation of what the quote says. Do not add, drop or soften any condition,
   number, exception or authority. Keep standard postal terms (e.g. Head Post Office = प्रधान डाकघर,
   Sub Post Office = उप डाकघर, Branch Post Office = शाखा डाकघर). Max 16 words (short and punchy, but never drop a condition, number, authority or exception).
3. question: exam-style Hindi question answerable only from the quote. Max 16 words.
4. a,b,c,d: 2-5 words each, Hindi only, NO English in brackets. Exactly one correct (matches the quote). The 3 wrong ones must be
   plausible but clearly contradicted by the clause.
5. correct: the letter.
6. hint: Hindi clue that comes ONLY from the quote, must NOT contain the answer or its key words. No opinions,
   no reasons that are not written in the clause. Max 12 words.
7. trap: the likely confusion in Hindi (max 12 words, must NOT repeat the fact), built only from this clause. If it uses another sentence of
   the clause, copy that sentence verbatim into trap_quote. Else trap_quote = "". Max 18 words.
8. yaad: 1-line Hindi memory formula (max 8 words, = and + allowed, NOT a sentence), fully consistent with fact.
9. hook: spoken Hindi challenge line, max 8 words, asking EXACTLY what the question asks (the correct option and one wrong option must be valid answers to it), must not reveal the answer, no fake statistics, no emoji.
10. Write numbers as digits. No emoji anywhere.
12. EXCEPTIONS: if anywhere in the clause there is an exception, "also permitted", "except",
    "excluding", "only", "generally", "usually" etc. that affects a part, that part's fact, correct answer,
    wrong options and trap must respect it, and the exception sentence must be inside source_quote.
    Never turn "generally/usually" into "always". A wrong option must be definitely wrong per the clause,
    never partly true.
15. This Guide is corrected up to 1985. AVOID time-sensitive facts that may have changed (number of
    postal circles, postal rates, fee amounts, commission %, names of firms/dealers/officers, lists of
    cities) unless they are the only exam-relevant content. Prefer procedural rules, authorities,
    conditions and exceptions.
13. Standard Hindi terms (use exactly): registered = पंजीकृत, insured article = बीमाकृत वस्तु (NOT
    insurance/बीमा), V.P. = वी.पी. (मूल्य देय), money order = मनीऑर्डर, night post office = रात्रि डाकघर,
    mobile post office = मोबाइल डाकघर, Head of the Circle = सर्किल प्रमुख, Director General = महानिदेशक,
    extra-departmental = अतिरिक्त विभागीय, certificate of posting = पोस्टिंग प्रमाणपत्र,
    late fee = विलंब शुल्क, letter mail = पत्र डाक, Superintendent of Post Offices = डाकघर अधीक्षक.
11. title_hi: short Hindi title of the clause (max 6 words).

Return ONLY JSON:
{{"title_hi": "...", "parts": [{{"source_quote": "...", "hook": "...", "question": "...",
"a": "...", "b": "...", "c": "...", "d": "...", "correct": "A", "hint": "...", "fact": "...",
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
        data = _llm_json(PLAN_PROMPT.format(num=num, text=text[:40000], max_parts=MAX_PARTS))
        title_hi = clean_text(data.get("title_hi", "")) or title_hi
        raw_parts = []
        for part in (data.get("parts") or [])[:MAX_PARTS]:
            part = {k: (v.strip() if isinstance(v, str) else v) for k, v in part.items()}
            part["_clause_no"] = num
            raw_parts.append(part)
        print(f"  Clause {num}: {len(raw_parts)} parts bane, jaanch chal rahi hai (ek saath)...")

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as ex:
            results = list(ex.map(lambda pt: check_part(pt, text), raw_parts))

        passed, failed = [], []
        for part, errs in zip(raw_parts, results):
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
        "source_pdf": os.path.basename(PDF_FILE),
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
4. Are 'hint', 'trap', 'yaad', 'hook' fully consistent with the clause and free of invented reasons?
5. Is any exception elsewhere in the clause ignored?
6. Are postal terms translated correctly (insured = बीमाकृत वस्तु, not insurance)?
7. OUTDATED CHECK: this Guide is corrected only up to 1985. If the recent notes state a DIFFERENT
   value for any fact the script uses (a count, number, fee, time, authority, name, list), or the fact
   is obviously time-sensitive (number of circles, postal rates/fees, office-bearer names, dealer firms)
   and the notes do not confirm it, report a problem starting with "OUTDATED:".

Return ONLY JSON: {{"ok": true/false, "problems": ["short Hindi or English description", ...]}}
ok must be false if there is even one problem.
"""


def audit_part(part, clause_text):
    """
    Har uplabdh AI (Gemini + Groq) alag-alag examiner ki tarah jaanchta hai.
    SABKO ok kehna hoga. Ek ne bhi shak kiya to part reject.
    """
    view = {k: part.get(k) for k in ("fact", "question", "a", "b", "c", "d", "correct",
                                     "hint", "trap", "yaad", "hook")}
    num = part.get("_clause_no")
    notes = notes_sections().get(num, "") if num else ""
    prompt = AUDIT_PROMPT.format(text=clause_text[:40000], notes=notes[:8000] or "(none)",
                                 part=json.dumps(view, ensure_ascii=False))
    providers = available_providers()
    if not providers:
        return ["AUDIT: koi AI examiner uplabdh nahi (GEMINI_API_KEY/GROQ_API_KEY) - bina jaanch pass nahi"]
    problems = []
    for name, _ in providers:
        res = _llm_json(prompt, only=name)
        probs = [str(p) for p in (res.get("problems") or []) if str(p).strip()]
        if res.get("ok") is not True or probs:
            problems += [f"AUDIT({name}): {p}" for p in probs] or [f"AUDIT({name}): ok nahi kaha"]
    return problems


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
hint, trap, yaad, hook completely, or pick a different exam-relevant rule from the SAME clause if this
one cannot be made fully accurate. All earlier rules still apply:
- source_quote copied word for word from the clause (English), and it alone must support the fact.
- fact = faithful Hindi translation, keep every condition, number, authority and exception.
- exactly one correct option; each wrong option definitely wrong per the clause (never partly true).
- hint/trap/yaad only from the clause, no invented reasons. Numbers as digits. No emoji.
- insured article = बीमाकृत वस्तु (not insurance). Never turn "generally/usually" into "always".

Return ONLY JSON with keys: source_quote, hook, question, a, b, c, d, correct, hint, fact, trap,
trap_quote, yaad.
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
                                     "hint", "fact", "trap", "trap_quote", "yaad")}
    fixed = _llm_json(REPAIR_PROMPT.format(
        text=clause_text[:40000], part=json.dumps(view, ensure_ascii=False),
        errors="\n".join("- " + e for e in part.get("check_errors", [])) or "- unknown"))
    fixed = {k: (v.strip() if isinstance(v, str) else v) for k, v in fixed.items()}
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
            errs = length_errors(p) + term_errors(p)
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
    data = dict(data)
    data["syllabus"] = syllabus
    for k in ("hook", "question", "a", "b", "c", "d", "hint", "fact", "trap", "yaad"):
        if isinstance(data.get(k), str):
            data[k] = strip_brackets(data[k])
    """Clean + options shuffle (pehle har baar A sahi hota tha - viewer pattern pakad leta tha)."""
    data = {k: clean_text(v) if isinstance(v, str) else v for k, v in data.items()}
    correct_key = (data.get("correct") or "A").upper()
    if correct_key not in ("A", "B", "C", "D"):
        correct_key = "A"
    rng = random.Random(clause_no * 1000 + part_no * 37 + 11)
    right = (data[correct_key.lower()], True)
    wrongs = [(data[k.lower()], False) for k in "ABCD" if k != correct_key]
    rng.shuffle(wrongs)
    pos = (clause_no * 7 + part_no * 3) % 4          # sahi answer har reel me alag position pe
    items = wrongs[:pos] + [right] + wrongs[pos:]
    letters = "ABCD"
    data["options"] = [(letters[i], txt) for i, (txt, _) in enumerate(items)]
    ci = next(i for i, (_, ok) in enumerate(items) if ok)
    data["correct"] = letters[ci]
    data["correct_text"] = items[ci][0]
    for i, (txt, _) in enumerate(items):
        data[letters[i].lower()] = txt
    wrong = [l for l, _ in data["options"] if l != data["correct"]]
    rng.shuffle(wrong)
    # HOOK ke liye 'A ya B?' jodi: sahi jawab + sabse zyada confuse karne wala galat option
    # (jo trap/hint me aata ho, warna pehla). Wahi 'bache do' me sabse aakhir me katega.
    def _overlap(txt):
        words = set(re.findall(r"[\w\u0900-\u097F]+", txt))
        ref = set(re.findall(r"[\w\u0900-\u097F]+", data.get("trap", "") + " " + data.get("hint", "")))
        return len(words & ref)
    confusing = max(wrong, key=lambda l: (_overlap(dict(data["options"])[l]), -wrong.index(l)))
    wrong = [l for l in wrong if l != confusing] + [confusing]
    data["elim_order"] = wrong
    pair = [data["correct_text"], dict(data["options"])[confusing]]
    if rng.random() < 0.5:
        pair.reverse()
    data["vs_pair"] = pair
    q = data.get("question", "")
    data["hook_q"] = q if words(q) <= 14 else data.get("hook", q)
    data["clause_no"], data["part_no"] = clause_no, part_no
    data["total_parts"] = total_parts
    data["hl_words"] = [re.sub(r"[,.!?।:()]", "", w) for w in data["correct_text"].split() if len(w) > 1]
    data["next_title"] = clean_text(next_title) or "अगला नियम"
    if not data.get("yaad"):
        data["yaad"] = " ".join(data["fact"].split()[:8])
    # awaaz ke liye symbols ko shabd me
    data["yaad_voice"] = (data["yaad"].replace("=", ",").replace("+", " और ")
                          .replace(":", ",").replace("  ", " "))
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
    hook_voice = "सही कौन?"
    specs = [
        {"name": "hook", "mood": "red", "tail": 0.15, "min": 2.2,
         "segs": [("vs", f"{data['vs_pair'][0]}, या {data['vs_pair'][1]}?"), ("hook", hook_voice)]},
        {"name": "question", "mood": "blue", "tail": 0.35, "min": 2.6,
         "segs": [("q", "चारों में से सही कौन सा?")]},
        {"name": "countdown", "mood": "purple", "tail": 0.0,
         "min": COUNTDOWN_SECONDS * COUNTDOWN_STEP + 0.35,
         "segs": [("lock", "जवाब कमेंट कीजिए!")]},
        {"name": "hint", "mood": "yellow", "tail": 0.2, "min": 2.0,
         "segs": [("hint", data["hint"])], "read": [("hint", data["hint"])]},
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
    if not SHOW_HINT:
        specs = [sp for sp in specs if sp["name"] != "hint"]
    elif hint_leaks(data):
        print("  Hint me jawab khul raha tha -> hint scene hataya (suspense + time bachat)")
        specs = [sp for sp in specs if sp["name"] != "hint"]
    return specs


def hint_leaks(data):
    """Hint me sahi jawab ke khaas shabd/sankhya ho to wo jawab bata deta hai."""
    hint = data.get("hint", "")
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


def tighten_voice(arr, words):
    """
    Har chuppi ko MAX_PAUSE tak kaat deta hai aur word timings ko usi hisaab se shift karta hai.
    Yahi 46s -> ~30s ka sabse bada fix hai (TTS comma/full-stop pe 0.4-0.6s rukta hai).
    """
    if not words:
        return arr, None
    words = sorted(words)
    keep = []                 # (src_start, src_end) seconds
    new_words = []
    out_t = 0.0
    cur = max(0.0, words[0][0] - 0.03)
    for i, (ws, we, wt) in enumerate(words):
        if i > 0:
            prev_end = max(words[i - 1][1], cur)
            gap = ws - prev_end
            if gap > MAX_PAUSE:
                keep.append((cur, prev_end + MAX_PAUSE / 2))
                out_t += prev_end + MAX_PAUSE / 2 - cur
                cur = ws - MAX_PAUSE / 2
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


def make_voices(specs):
    """Returns list of (audio_array, word_boundaries_or_None)."""
    voices = []
    for i, sp in enumerate(specs):
        text = " ".join(t for _, t in sp["segs"])
        if DRY_RUN:
            est = max(0.6, seg_weight(text) * 0.058)
            voices.append((np.zeros(int(est * SR), dtype=np.float32), None))
            continue
        path = f"_voice_{i}.mp3"
        words = asyncio.run(tts_save(text, path))
        if words:
            arr, words = tighten_voice(decode_raw(path), words)
        else:
            print(f"  (scene {sp['name']}: word timing nahi mila, andaze se timing)")
            arr, words = decode_raw(path, trim=True), None
        voices.append((arr, words))
        os.remove(path)
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
    for sc, (v, _) in zip(timeline, voices):
        add_at(voice_track, v, sc["start"] + VOICE_LEAD)

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
            add_at(buf, sfx_buzz(0.18), s + mk["trapx"][0])
        elif name == "cta":
            add_at(buf, sfx_pop(0.4), s + 0.05)

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
def vs_card(text, w=900, h=190, active=False):
    fill = (30, 58, 96) if active else (22, 42, 72)
    im = card_sprite(w, h, fill, CYAN if active else (80, 120, 170), 7 if active else 5, 36).copy()
    d = ImageDraw.Draw(im)
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
    draw_kinetic(cv, data["hook_q"], W / 2, 0, 940, 74, 1.0, max_lines=3, min_size=46,
                 karaoke=False, center_y=470)

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
    place(cv, vs_card(a, active=act_a), W / 2, 830, scale=(0.88 + 0.12 * k) * bump_a)
    place(cv, vs_card(b, active=act_b), W / 2, 1190, scale=(0.88 + 0.12 * k) * bump_b)
    pulse = 1 + 0.06 * math.sin(t * 9)
    place(cv, glow_sprite(90, YELLOW, 160), W / 2, 1010)
    place(cv, pill_sprite("या", 56, (25, 18, 0), YELLOW, ORANGE), W / 2, 1010, scale=pulse)

    # EXAM TRAP stamp: 0.12s pe slam
    st = sc["stamp_t"]
    kk = prog(t, st, 0.16)
    if t >= st:
        place(cv, stamp_sprite(), W / 2 + 250, 680, scale=(1.9 - 0.9 * ease_out_cubic(kk)) * 0.62,
              angle=-11, alpha=clamp(kk * 3))
        if t < st + 0.3:
            fx["shake"] = 12 * (1 - prog(t, st + 0.04, 0.26))
    else:
        place(cv, stamp_sprite(), W / 2 + 250, 680, scale=0.62, angle=-11, alpha=0.35)

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
    draw_kinetic(cv, data["question"], W / 2, 0, 960, 66, 1.0, max_lines=3, min_size=44,
                 karaoke=False, center_y=500)

    ys = opt_positions(y0=760, gap=200)
    for i, (l, txt) in enumerate(data["options"]):
        s0 = sc["opt_t"][i]
        k = prog(t, s0, 0.3)
        if k <= 0:
            place(cv, option_sprite(l, txt, OPT_W, OPT_H, "normal"), W / 2, ys[i], alpha=0.12)
            continue
        active = s0 <= t < s0 + 0.35
        e = ease_out_back(k)
        place(cv, option_sprite(l, txt, OPT_W, OPT_H, "active" if active else "normal"),
              W / 2 + (1 - e) * 500, ys[i], alpha=clamp(k * 2), scale=1.04 if active else 1.0)
    return {}


def scene_countdown(cv, data, t, dur, m, vd, sc):
    d = ImageDraw.Draw(cv)
    d.text((W / 2, 235), "अपना जवाब लॉक कीजिए!", font=get_font(70), fill=WHITE, anchor="mm")
    ys = opt_positions(y0=420, gap=178)
    pulse = 1 + 0.015 * math.sin(t * 10)
    for i, (l, txt) in enumerate(data["options"]):
        place(cv, option_sprite(l, txt, OPT_W, 158, "normal"), W / 2, ys[i], scale=pulse)

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
            place(cv, option_sprite(l, txt, OPT_W, OPT_H, "wrong"), W / 2 + shake, y,
                  alpha=1 - 0.5 * k, scale=1 - 0.05 * k)
            place(cv, x_mark_sprite(), W / 2 + 400, y, scale=max(0.05, 1.8 - 0.8 * ease_out_back(k)))
            if t - kill_t[l] < 0.1:
                fx["shake"] = 8
        else:
            suspense = t >= m["left"][0]
            sc_ = 1 + (0.03 * math.sin(t * 12) if suspense else 0)
            place(cv, option_sprite(l, txt, OPT_W, OPT_H, "active" if suspense else "normal"), W / 2, y, scale=sc_)

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
    place(cv, option_sprite(data["correct"], data["correct_text"], 900, 200, "correct"),
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


def scene_rule(cv, data, t, dur, m, vd, sc):
    topic_chip(cv, data, 235)
    FS, TS = 64, 58
    fh = text_block_h(data["fact"], 880, FS, 5, 42) + 160
    th = text_block_h(data["trap"], 880, TS, 4, 40) + 160
    gap = 105
    area_top, area_bot = 320, 1450
    top = max(area_top, (area_top + area_bot) / 2 - (fh + gap + th) / 2)
    fc_final, tc = top + fh / 2, top + fh + gap + th / 2
    fc_center = (area_top + area_bot) / 2 - 60

    ts = m["trapx"][0]
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
    draw_kinetic(cv, data["fact"], W / 2, 0, 880, FS, fp, max_lines=5, min_size=42,
                 hl_words=data["hl_words"], hl_color=GREEN, ghost=0.18, center_y=fc + 10, th=th_f)

    fx = {}
    if t >= ts - 0.1:
        k2 = ease_out_back(prog(t, ts - 0.1, 0.35))
        place(cv, card_sprite(980, int(th), (56, 18, 26), RED, 6, 44), W / 2, tc,
              scale=0.9 + 0.1 * k2, alpha=clamp(k2))
        place(cv, pill_sprite("EXAM TRAP", 46, WHITE, RED, RED), W / 2, tc - th / 2,
              scale=max(0.05, k2), angle=-3)
        tp, th2 = seg_progress(sc, "trap", t)
        draw_kinetic(cv, data["trap"], W / 2, 0, 880, TS, tp, max_lines=4, min_size=40,
                     ghost=0.18, center_y=tc + 10, th=th2)
        if t - ts < 0.12:
            fx["shake"] = 6
    else:
        d = ImageDraw.Draw(cv)
        a = 0.5 + 0.5 * math.sin(t * 6)
        d.text((W / 2, fc + fh / 2 + 110), "लेकिन असली ट्रैप अभी बाकी है...", font=get_font(52),
               fill=mix(BG_BOTTOM, ORANGE, 0.4 + 0.6 * a), anchor="mm")
    return fx


def scene_cta(cv, data, t, dur, m, vd, sc):
    """Yaad formula + FREE MOCK TEST CTA + agli reel ka khaas teaser + follow."""
    k = ease_out_back(prog(t, 0, 0.35))
    place(cv, pill_sprite("याद रखिए", 50, (30, 20, 0), YELLOW, YELLOW), W / 2, 305, scale=max(0.05, k))

    cy = 540
    bh = text_block_h(data["yaad"], 880, 80, 3, 50)
    ch = bh + 170
    place(cv, glow_sprite(440, YELLOW, 70), W / 2, cy)
    place(cv, card_sprite(1000, ch, (46, 38, 10), YELLOW, 7, 46), W / 2, cy,
          scale=0.9 + 0.1 * k, alpha=clamp(k))
    p, th = seg_progress(sc, "yaad", t)
    draw_kinetic(cv, data["yaad"], W / 2, 0, 880, 80, max(p, 0.001), max_lines=3, min_size=50,
                 ghost=0.3, center_y=cy, th=th, karaoke=True)

    # FREE MOCK TEST - awaaz ke saath hi bada ho
    y2 = cy + ch / 2 + 125
    m0 = m["mock"][0]
    k2 = ease_out_back(prog(t, m0 - 0.15, 0.35)) if t >= m0 - 0.15 else 0.0
    pulse = 1 + (0.05 * math.sin(t * 9) if t > m0 + 0.4 else 0)
    place(cv, glow_sprite(300, ORANGE, 110), W / 2, y2)
    place(cv, mock_button(), W / 2, y2, scale=max(0.05, (0.5 + 0.5 * k2) * pulse), alpha=clamp(k2 * 2))

    # agli reel ka khaas sawal (open loop)
    teaser = data.get("teaser") or data.get("next_title", "")
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

    # scene-entry punch zoom
    if t < 0.2:
        z = 1 + 0.07 * (1 - ease_out_cubic(t / 0.2))
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
    for i, (sp, (v, words)) in enumerate(zip(specs, voices)):
        vdur = len(v) / SR + VOICE_LEAD
        dur = max(vdur + sp["tail"], sp["min"])
        shifted = [(a + VOICE_LEAD, b + VOICE_LEAD, w) for a, b, w in words] if words else None
        marks, wt = compute_marks(sp["segs"], vdur, shifted)
        # RULE: jo text padhna hai, use (shabd / READ_WPS) + ABSORB time zaroor mile
        for key, text in sp.get("read", []):
            need = marks[key][0] + len(text.split()) / READ_WPS + ABSORB
            dur = max(dur, need)
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
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
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


# ==================== CAPTION / NOTES / MOCK TEST ====================

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
    lines = [
        f"{data['question']} | GDS to MTS / Postman | PO Guide Part I Clause {data['clause_no']}",
        "",
        "सही उत्तर जानने के लिए पूरी रील देखें 👀",
        f"📘 स्रोत: PO Guide Part I, Clause {data['clause_no']}",
        f"🎯 FREE MOCK TEST चाहिए? कमेंट करें: {MOCK_KEYWORD}",
        "🔔 रोज़ 1 नियम | PO Guide Series",
        "",
        HASHTAGS,
        "",
        "----- PIN करने वाला पहला कमेंट -----",
        f"आपका उत्तर? A / B / C / D लिखें 👇  |  Free Mock Test के लिए {MOCK_KEYWORD} लिखें",
    ]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("Caption:", path)


def _pdf_pages(title, blocks, footer):
    """blocks: list of (label, text, color, size). A4 pages (1240x1754) banata hai."""
    PW_, PH_, M = 1240, 1754, 80
    pages, page, d, y = [], None, None, 0

    def new_page():
        nonlocal page, d, y
        page = Image.new("RGB", (PW_, PH_), (255, 255, 255))
        d = ImageDraw.Draw(page)
        d.rectangle((0, 0, PW_, 150), fill=(14, 27, 45))
        d.text((M, 55), "POSTAL WALA", font=get_font(40), fill=(250, 204, 21), anchor="lm")
        d.text((M, 108), title, font=get_font(34), fill=(248, 250, 252), anchor="lm")
        d.text((PW_ - M, 55), IG_HANDLE, font=get_font(30), fill=(159, 176, 194), anchor="rm")
        d.rectangle((0, PH_ - 90, PW_, PH_), fill=(245, 158, 11))
        d.text((PW_ / 2, PH_ - 45), footer, font=get_font(32), fill=(20, 12, 0), anchor="mm")
        pages.append(page)
        y = 200

    new_page()
    for label, text, col, size in blocks:
        f, s_, lines = fit_lines(text, PW_ - 2 * M - 40, 30, size, size)
        need = (60 if label else 0) + len(lines) * int(s_ * 1.45) + 30
        if y + need > PH_ - 120:
            new_page()
        if label:
            d.text((M, y + 20), label, font=get_font(34), fill=col, anchor="lm")
            y += 60
        for ln in lines:
            d.text((M + 20, y + s_ * 0.7), " ".join(ln), font=f, fill=(26, 32, 50), anchor="lm")
            y += int(s_ * 1.45)
        y += 30
    return pages


def make_notes_pdf(plan):
    """Clause ki notes: har pakke part ka niyam, trap, yaad aur English source."""
    num = plan["clause_no"]
    blocks = []
    for i, p in enumerate(usable_parts(plan), 1):
        blocks += [
            (f"{i}. नियम", strip_brackets(p.get("fact", "")), (18, 140, 64), 38),
            ("ध्यान दें (Trap)", strip_brackets(p.get("trap", "")), (206, 38, 38), 34),
            ("याद रखिए", strip_brackets(p.get("yaad", "")), (180, 120, 0), 36),
            ("", "Source: " + p.get("source_quote", ""), (96, 104, 124), 26),
        ]
    if not blocks:
        raise ValueError("koi pakka part nahi")
    title = f"PO Guide Part I | Clause {num}: {plan.get('title_hi', '')}"
    pages = _pdf_pages(title, blocks, f"FREE MOCK TEST के लिए Instagram पर कमेंट करें: {MOCK_KEYWORD}")
    out_dir = os.path.join(OUTPUT_DIR, "notes")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"clause_{num}_notes.pdf")
    pages[0].save(path, save_all=True, append_images=pages[1:], resolution=150)
    return path


def make_mock_pdf(max_q=20):
    """Free mock test: publish ho chuke (jaanch-pass) sawal, aakhir me answer key + source."""
    items = []
    for plan in all_plans():
        for i, p in enumerate(usable_parts(plan), 1):       # sirf saari jaanch pass wale sawal
            items.append((p.get("published") or "", plan["clause_no"], i, p))
    # pehle publish ho chuke (naye pehle), fir baaki pakke sawal
    items.sort(key=lambda x: (x[0] != "", x[0], -x[1]), reverse=True)
    seen, uniq = set(), []
    for it in items:                                   # ek sawal do baar nahi
        key = _squash_hi(it[3].get("question", ""))
        if key not in seen:
            seen.add(key)
            uniq.append(it)
    items = uniq[:max_q]
    if len(items) < 5:
        raise ValueError(f"abhi sirf {len(items)} sawal publish hue - kam se kam 5 chahiye")
    items.sort(key=lambda x: (x[1], x[2]))
    q_blocks, keys = [], []
    for n, (_, cl, i, p) in enumerate(items, 1):
        d = prepare_data(dict(p, title=""), cl, i)
        opts = "     ".join(f"({l}) {t}" for l, t in d["options"])
        q_blocks += [(f"प्रश्न {n}", d["question"], (37, 99, 235), 36), ("", opts, (26, 32, 50), 32)]
        keys.append((f"{n}. उत्तर: ({d['correct']}) {d['correct_text']}",
                     f"Clause {cl}: {strip_brackets(p.get('fact', ''))}"))
    key_blocks = [("उत्तर कुंजी (Answer Key)", "सही उत्तर और PO Guide का नियम", (18, 140, 64), 30)]
    for a, b in keys:
        key_blocks += [("", a, (18, 140, 64), 32), ("", b, (96, 104, 124), 28)]
    footer = f"और टेस्ट चाहिए? Instagram {IG_HANDLE} पर कमेंट करें: {MOCK_KEYWORD}"
    pages = _pdf_pages(f"FREE MOCK TEST  |  {len(items)} प्रश्न  |  PO Guide Part I", q_blocks, footer)
    pages += _pdf_pages("FREE MOCK TEST  |  उत्तर कुंजी", key_blocks, footer)
    out_dir = os.path.join(OUTPUT_DIR, "mock")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "free_mock_test.pdf")
    pages[0].save(path, save_all=True, append_images=pages[1:], resolution=150)
    return path


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


def _slide(num, total, title, body_blocks, footer, mood="blue", title_size=64):
    """Carousel slide 1080x1350, content beech me (khaali neeche wala hissa nahi)."""
    SW, SH = 1080, 1350
    TOP, BOT = 130, SH - 140
    cv = _poster_bg(SW, SH, mood)
    d = ImageDraw.Draw(cv)
    d.text((60, 70), "POSTAL WALA", font=get_font(36), fill=(148, 163, 184), anchor="lm")
    d.text((SW - 60, 70), f"{num}/{total}", font=get_font(38), fill=YELLOW, anchor="rm")

    tf, ts, tlines = fit_lines(title, SW - 140, 3, title_size, 44)
    t_h = len(tlines) * int(ts * 1.25)
    laid = []
    for label, text, col, size in body_blocks:
        f, s_, lines = fit_lines(text, SW - 200, 6, size, 36)
        bh = len(lines) * int(s_ * 1.35) + (78 if label else 34) + 34
        laid.append((label, col, f, s_, lines, bh))
    gap = 34
    total_h = t_h + 50 + sum(b[-1] for b in laid) + gap * (len(laid) - 1)
    y = max(TOP, TOP + (BOT - TOP - total_h) / 2)
    for ln in tlines:
        d.text((SW / 2, y + ts * 0.55), " ".join(ln), font=tf, fill=WHITE, anchor="mm")
        y += int(ts * 1.25)
    y += 50
    for label, col, f, s_, lines, bh in laid:
        card = card_sprite(SW - 100, int(bh), CARD, col, 6, 34, shadow=False)
        cv.paste(card.convert("RGB"), (50, int(y)), card)
        d = ImageDraw.Draw(cv)
        yy = y + 34
        if label:
            d.text((SW / 2, yy + 14), label, font=get_font(40), fill=col, anchor="mm")
            yy += 70
        for ln in lines:
            d.text((SW / 2, yy + s_ * 0.6), " ".join(ln), font=f, fill=WHITE, anchor="mm")
            yy += int(s_ * 1.35)
        y += bh + gap
    d.rectangle((0, SH - 110, SW, SH), fill=(245, 158, 11))
    d.text((SW / 2, SH - 55), footer, font=get_font(38), fill=(20, 12, 0), anchor="mm")
    return cv


def make_carousel(plan):
    """Clause poora hone pe: 1 title + har niyam ki slide + revision slide. Save hone wala post."""
    parts = usable_parts(plan)
    if not parts:
        raise ValueError("koi pakka part nahi")
    num = plan["clause_no"]
    title = plan.get("title_hi") or plan.get("title_en", "")
    total = len(parts) + 2
    footer = f"FREE MOCK TEST: कमेंट करें {MOCK_KEYWORD}  |  {IG_HANDLE}"
    slides = [_slide(1, total, f"Clause {num}\n{title}".replace("\n", " : "),
                     [("PO Guide Part I", f"{len(parts)} नियम  +  {len(parts)} EXAM TRAP  +  1 लाइन रिवीजन", CYAN, 58),
                      ("", "Save कर लीजिए, परीक्षा से पहले काम आएगा", YELLOW, 52)], footer, "red", title_size=92)]
    for i, p in enumerate(parts, 1):
        slides.append(_slide(i + 1, total, f"नियम {i}", [
            ("नियम", strip_brackets(p.get("fact", "")), GREEN, 58),
            ("EXAM TRAP", strip_brackets(p.get("trap", "")), RED, 54),
            ("याद रखिए", strip_brackets(p.get("yaad", "")), YELLOW, 58),
        ], footer, title_size=72))
    revision = [("", f"{i}. " + strip_brackets(p.get("yaad", "")), YELLOW, 52) for i, p in enumerate(parts, 1)]
    slides.append(_slide(total, total, "1 लाइन रिवीजन", revision[:6] +
                         [("", f"स्रोत: PO Guide Part I, Clause {num}", CYAN, 38)], footer, "green", title_size=80))
    out_dir = os.path.join(OUTPUT_DIR, "carousel", f"clause_{num}")
    os.makedirs(out_dir, exist_ok=True)
    for k, sl in enumerate(slides, 1):
        sl.save(os.path.join(out_dir, f"{k:02d}.jpg"), quality=92)
    cap = [f"Clause {num}: {title} | PO Guide Part I | GDS to MTS / Postman", "",
           f"{len(parts)} नियम + EXAM TRAP + 1 लाइन रिवीजन 📌 Save कर लीजिए",
           f"🎯 FREE MOCK TEST चाहिए? कमेंट करें: {MOCK_KEYWORD}", "", HASHTAGS]
    with open(os.path.join(out_dir, "caption.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(cap))
    return out_dir


def write_dm_message():
    """MOCK comment karne walon ko bhejne ka taiyar message."""
    out_dir = os.path.join(OUTPUT_DIR, "mock")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "dm_message.txt")
    txt = ("नमस्ते! 🙏 आपका FREE MOCK TEST यहाँ है (PDF अटैच है)।\n"
           "✅ सारे प्रश्न PO Guide Part I से, आखिर में उत्तर कुंजी और नियम के साथ।\n"
           "📌 हर हफ्ते नया मॉक आता है, छूटे नहीं इसलिए Follow कर लीजिए।\n"
           "❓ कोई डाउट हो तो यहीं पूछिए।\n"
           "All the best! - Postal Wala")
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)
    return path


def log_reel(data, out, duration):
    """Har reel ki ek line - insights aap khud baad me bharenge."""
    import csv
    import datetime
    path = os.path.join(OUTPUT_DIR, "reel_log.csv")
    new = not os.path.exists(path)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "file", "clause", "part", "question", "sahi_jawab", "hook_A", "hook_B",
                        "length_sec", "views", "skip_rate", "avg_watch_sec", "shares", "saves", "follows"])
        w.writerow([datetime.date.today().isoformat(), os.path.basename(out), data["clause_no"],
                    data["part_no"], data["question"], data["correct_text"],
                    data["vs_pair"][0], data["vs_pair"][1], f"{duration:.1f}", "", "", "", "", "", ""])


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
    print("Current State:", state)

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

    data_in = dict(part)
    data_in["title"] = plan.get("title_hi") or plan.get("title_en", "")
    data = prepare_data(data_in, num, part_no, total_parts=total, next_title=next_title,
                        syllabus=(order.index(num) + 1 if num in order else None, len(order)))
    data["day"] = int(state.get("day", 0)) + 1
    data["teaser"] = find_teaser(plan, part, nxt)
    print("\nSCRIPT DATA:")
    print(json.dumps({k: v for k, v in data.items() if k not in ("hl_words",)}, ensure_ascii=False, indent=2))
    print("SOURCE (PO Guide):", part.get("source_quote", ""))

    out = os.path.join(OUTPUT_DIR, f"reel_clause_{num}_part_{part_no}.mp4")
    duration = build_reel(data, out)
    for fn, what in ((lambda: write_caption(data, out.replace(".mp4", "_caption.txt")), "caption"),
                     (lambda: make_cover(data, out.replace(".mp4", "_cover.jpg")), "cover")):
        try:
            fn()
        except Exception as exc:
            print(f"{what} nahi bana:", exc)
    if DRY_RUN:
        return

    # publish mark (index ki jagah flag, taaki baad me sudhre parts se kram na bigde)
    import datetime
    part["published"] = datetime.date.today().isoformat()
    save_plan(plan)
    state["day"] = data["day"]
    save_state(state)
    clause_done = next_unpublished(plan)[0] is None
    jobs = [(lambda: make_notes_pdf(plan), "notes PDF"), (make_mock_pdf, "mock test PDF"),
            (write_dm_message, "DM message"), (lambda: log_reel(data, out, duration) or "reel_log.csv", "reel log")]
    if clause_done:
        jobs.append((lambda: make_carousel(plan), "carousel"))
    for fn, what in jobs:
        try:
            print("Bana:", fn())
        except Exception as exc:
            print(f"{what} nahi bana:", exc)

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


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--list-clauses"]:
        list_clauses()
    elif args[:1] == ["--build"] and len(args) >= 2:
        for n in args[1:]:
            build_plan(int(n))
    else:
        run_daily()
