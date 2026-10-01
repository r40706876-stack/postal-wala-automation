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
from PIL import ImageChops, ImageFilter
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
PUBLISH_OLD_REPAIRS = False   # True = pichhle clauses ke sudhare parts beech me (kram tootega)
MAX_OPTION_WORDS = 7          # isse lamba option = scene lamba + padhna mushkil -> sudhaar
MERGE_COUNTDOWN = True        # sawal + 4 options + countdown ek scene (dohraav aur khaali taala khatam)
OPT_READ_WPS = 4.0            # options nazar bhar dekhe jaate hain (poora padhne se tez)
SHOW_BEATS = True             # niyam ke neeche 2-4 chhote yaad-tukde (✓/✗/•), examiner-jaanch ke baad hi
SHOW_ENGLISH = True            # Hindi reel me chhoti English line (English wala viewer samjhe aur ruke)
# English kin jagah: hook (sawal + dono cards), sawal, chaaron options (sawal/countdown/galat-hatao),
# sahi jawab, niyam. Screen halki rakhne ke liye trap aur yaad sirf Hindi (chahiye to "trap", "yaad" jodiye).
EN_PLACES = ("question", "options", "answer", "fact")   # hook me English nahi (pehla frame halka)
EN_COL = (150, 200, 245)
ROTATION_SIZE = 5
VOICE_RATE = "+6%"
VOICE_PITCH = "+2Hz"

W, H = 1080, 1920
LOOP_BLEND = 0.35             # reel ka ant pehle frame me ghulta hai -> Instagram loop pe seamless
TRANSITION = 0.30             # scene badalne pe swipe (naya pan); hook -> sawal bina cut ke
FPS = 30
SR = 44100
COUNTDOWN_SECONDS = 3
COUNTDOWN_STEP = 0.5         # 3-2-1 = 2.4 sec (screen pe ab "N सेकंड" ka vaada nahi, sirf ginti)

# ---- PACING RULES (retention ka asli game) ----
MAX_PAUSE = 0.14              # voice ke andar koi bhi chuppi isse lambi nahi
VOICE_LEAD = 0.06             # text pehle aata hai, awaaz 60ms baad (aankh kaan se aage)
EYE_LEAD = 0.12               # har word screen pe bolne se 0.12s pehle chamakta hai
READ_WPS = 3.4                # mobile pe Hindi padhne ki speed (shabd / second)
ABSORB = 0.4                  # info khatam hone ke baad dimaag me baithne ka time

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
SIMPLE_MODE = True            # aasaan system: 1 call me sab, sirf zaroori rok, baaki hissa hata do, 1 examiner
READY_BUFFER = 6              # itni taiyar reels ka stock pehle se (koi clause atke to bhi reel bane)
KEEP_LAST_REELS = 20          # repo halka rakhne ke liye sirf aakhri itni reels (.mp4) rakhi jaati hain (0 = sab rakho)
VIDEO_CRF = 23                # video quality/size (Instagram khud dobara compress karta hai; 23 = achhi quality, kam MB)
# Kya-kya banana hai (True = banega). Abhi sirf video + caption + carousel.
MAKE_CAROUSEL = True
MAKE_COVER = False

IG_HANDLE = "@POSTAL_WALA"
MOCK_KEYWORD = "MOCK"          # comment me ye likhne pe aap free mock test bhejenge
# Instagram ab ek post me sirf 5 hashtag leta hai - zyada = nuksaan
HASHTAGS = "#gdstomts #postmanexam #mtsexam #poguide #indiapost"

# ---- SEASON 2 (naya pan, pehchaan wahi): ----
# HOOK_MODE "tease": sawal kabhi dobara nahi likha jaata (arth nahi badalta). Pehle 2 sec me sirf
# ek chhoti challenge line + "A ya B?" bola jaata hai; poora asli sawal screen pe likha hota hai aur
# agle scene me bola jaata hai. AI wala chhota hook ab istemaal nahi hota.
HOOK_MODE = "pro"             # "pro" = naya editor-style flow (neeche), "tease" = pichhla
SEASON = 2
NEW_BADGE_EPISODES = 6        # S2 ke pehle itne episode pe "NEW" ribbon (viewer ko sudhaar dikhe)
# Challenge lines: sirf sach baat (koi fake daava/aankda nahi), kisi niyam ka arth nahi chhooti
CHALLENGE_LINES = ["सिर्फ एक सही है!", "3 सेकंड में बताओ!", "आप क्या चुनोगे?", "इसमें ट्रैप है!"]
# HOOK KA PAKKA NIYAM (ab badlega nahi): hook = VISHAY + tay jigyasa-dhaancha. Hook kabhi sawal ko
# dobara nahi likhta, isliye arth badal hi nahi sakta. Asli sawal usi frame me hook ke neeche.
# Har dhaancha sach hai (har reel me ek EXAM TRAP hai, 2 me se 1 hi sahi hai) - koi nakli aankda nahi.
HOOK_TEMPLATES = [
    "{t}: इसमें EXAM TRAP है!",
    "{t}: 2 जवाब, सही सिर्फ 1!",
    "{t} का ये नियम पता है?",
    "{t}: आप क्या जवाब दोगे?",
]
HOOK_TEMPLATES_NOTOPIC = ["इस सवाल में EXAM TRAP है!", "2 जवाब, सही सिर्फ 1!",
                          "ये नियम पता है?", "आप क्या जवाब दोगे?"]
HOOK_SECONDS = 2.3            # hook ki lambai (timer bar isi me khaali hota hai)
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


_PARTS = [(random.Random(k).random(), random.Random(k + 99).random(), 0.4 + random.Random(k + 7).random())
          for k in range(34)]


def bg_frame(mood, gt):
    im = background(mood)
    ox = int(60 + 40 * math.sin(gt * 0.45))
    oy = int(60 + 40 * math.cos(gt * 0.33))
    im = im.crop((ox, oy, ox + W, oy + H))
    d = ImageDraw.Draw(im)
    col = mix((40, 60, 95), MOODS[mood], 0.35)
    for px, py, sp in _PARTS:                      # halki tairti roshni: screen kabhi jami na lage
        y = (py * H - gt * 38 * sp) % H
        x = px * W + 18 * math.sin(gt * 0.8 + py * 9)
        r = 2 + 3 * sp
        d.ellipse((x - r, y - r, x + r, y + r), fill=col)
    return im


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
            a = clamp((p - start) / 0.06 + (0.4 if (idx == 0 and p > 0) else 0.0))
            e = ease_out_cubic(a)
            if a <= 0:
                alpha, dy = ghost, 0
            else:
                alpha, dy = max(ghost, e), (1 - e) * 22
            key = re.sub(r"[,.!?।:()]", "", w)
            col = color
            if key in hl and a > 0:
                col = hl_color
            if karaoke and p > 0 and start <= p < nxt and p < 0.999:     # p=0: koi shabd nahi chamke
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
    """AI kabhi beech me '...' laga deta hai - tab har tukda (kram se) PDF me hona chahiye."""
    frags = [f for f in re.split(r"\.{3,}|…", quote or "") if len(_alnum(f)) >= 12]
    if len(frags) > 1:
        return all(_quote_in_source_one(f, source, min_len=12) for f in frags)
    return _quote_in_source_one(quote, source)


def _quote_in_source_one(quote, source, min_len=25):
    """
    Quote PDF me sach me hai? Spaces/punctuation hata ke milaan (PDF me 'Bomba y', 'tim ings'
    jaise toote shabd hote hain). Shabd ya akshar badle to fail.
    """
    q, src = _alnum(quote), _alnum(source)
    if len(q) < min_len:
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
    t = t.replace("½", " 1/2").replace("¼", " 1/4").replace("¾", " 3/4")

    def _mixed(m):                       # "1 -1/2", "1 1/2", "1-1/2" -> "1.5"
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{a + b / c:g}" if c else m.group(0)
    t = re.sub(r"(\d+)\s*[-–]?\s*(\d+)\s*/\s*(\d+)", _mixed, t)
    t = re.sub(r"(?<![\d.])(\d+)\s*/\s*(\d+)(?![\d.])",
               lambda m: f"{int(m.group(1)) / int(m.group(2)):g}" if int(m.group(2)) else m.group(0), t)
    groups = []
    for n in re.findall(r"\d+(?:[:.]\d+)?", t):
        dec = None
        if "." in n:
            try:
                dec = f"{float(n):g}"             # 1.5 = 1.50 (dashamlav bhi, samay bhi ho sakta)
            except ValueError:
                dec = None
        n = n.replace(".", ":")
        g = {n}
        if dec:
            g.add(dec)
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
LEN_LIMITS = {"question": 16, "a": 6, "b": 6, "c": 6, "d": 6,
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


TRAP_MARKERS = ("गलत", "नहीं", "न कि", "पर ", "पर,", "लेकिन", "बल्कि", "जबकि", "बस ", "केवल", "सिर्फ", "मना", "वर्जित",
                "पुराना", "पुरानी")


def trap_errors(part):
    """
    Trap me 'galat dharana' ke saath uska sudhaar bhi hona chahiye. Warna screen pe galat baat
    niyam jaisi padhi jaati hai (jaise: 'इन्हें मेल वैन लेटर बॉक्स में डाल सकते हैं।').
    """
    t = strip_brackets(part.get("trap", "") or "")
    strong = ("गलत", "नहीं", "न कि", "बल्कि", "लेकिन", "जबकि", "मना", "वर्जित", "पुराना", "पुरानी", "सही")
    if t and (not any(mk in t for mk in strong) or len(t.split()) < 4):
        return ["TRAP: galat dharana ke saath sudhaar nahi (jaise 'X समझना गलत है, सही: Y') - "
                "akele padhne pe ulta niyam lagta hai"]
    if t and trap_repeats_fact(t, part.get("fact", "")):
        return ["TRAP REPEAT: trap sirf niyam ke shabd dohra raha hai - nayi kaam ki baat do (apvaad, seema, "
                "kaun tay karta hai, ulta case, ya lalchane wala galat option kyon galat hai)"]
    return []


_TRAP_STOP = {"अनिवार्य", "ज़रूरी", "जरूरी", "आवश्यक", "बिना", "सकते", "सकता", "सकती", "करना", "करें", "है", "हैं", "के", "का", "की", "को", "में", "से", "पर", "और", "या", "नहीं", "गलत", "सही", "केवल",
              "सिर्फ", "भी", "ही", "तो", "एक", "जाता", "जाती", "जाते", "होता", "होती", "होते", "चाहिए", "कि",
              "न", "यह", "ये", "वह", "इसे", "इन्हें", "समझना", "क्योंकि", "बल्कि", "लेकिन"}


def _content_words(t):
    # chhota stem (चिपकाना/चिपकाने -> चिपक) taaki roop badalne se dohraav chhup na jaaye
    return {w[:3] for w in re.findall(r"[\w\u0900-\u097F]+", t or "") if w not in _TRAP_STOP and len(w) > 1}


VAGUE_TRAP = re.compile(r"(यह|ये|ऐसी|ऐसा|इस)\s+(सावधानी|नियम|बात|काम|व्यवस्था|तरीका)")


def trap_has_new_source(part):
    """Trap ki baat clause ke kisi DOOSRE vakya (trap_quote) se aayi ho - wahi pakki nayi jaankari hai."""
    tq = (part.get("trap_quote") or "").strip()
    if len(tq) < 15:
        return False
    return _ngram_cover(tq.lower(), (part.get("source_quote") or "").lower(), 4) < 0.5


def trap_is_weak(part):
    """Trap bekaar: niyam/sawal/options/chitra ki baat dohraye, ya 'यह सावधानी' jaisa gol-mol ho."""
    t = strip_brackets(part.get("trap", "") or "")
    if not t:
        return False
    if trap_repeats_fact(t, part.get("fact", "")) or VAGUE_TRAP.search(t):
        return True
    shown = " ".join(str(part.get(k) or "") for k in ("fact", "question", "a", "b", "c", "d"))
    cv = part.get("chitra_v") or {}
    shown += " " + " ".join(cv.get("caps") or [])
    tw = _content_words(t)
    return len(tw) >= 2 and len(tw & _content_words(shown)) / len(tw) >= 0.6


def trap_repeats_fact(trap, fact):
    """Trap ke aadhe+ khaas shabd fact me pehle se hain -> nayi jaankari nahi, bas dohraav."""
    tw = _content_words(trap)
    if len(tw) < 2:
        return False
    return len(tw & _content_words(fact)) / len(tw) >= 0.5


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
        src=truth_src(part), hi=json.dumps(hi, ensure_ascii=False),
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
    if int(en.get("tries", 0)) == 9:          # purana nishaan (galti se hamesha ke liye band) -> dobara koshish
        en = {}
    if int(en.get("tries", 0)) >= 2:
        return False
    hi = {k: part.get(k, "") for k in EN_KEYS}
    hi["correct"] = part.get("correct")
    try:
        res = as_dict(_llm_json(EN_PROMPT.format(src=truth_src(part),
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


HOOK_PROMPT = """Write ONE short, eye-catching hook question in everyday spoken Hindi (max 12 words) for this
India Post exam MCQ - it is the first thing a scrolling viewer reads, so it must make them stop and be
understood in 1 second (tricky part first, crisp question at the end; no fake statistics or claims).
It must KEEP the question's main subject (what/who) and its condition - never drop them to sound catchy.
Example: "एम्बोस्ड स्टेशनरी पर छपे मूल्य से अधिक डाक शुल्क होने पर क्या करें?" -> "लिफाफे पर छपा टिकट कम पड़ जाए, तो क्या करें?"
ONLY use a counter/customer scene if the rule really is about what the postal employee does. If the rule is about the public/sender, ask it plainly. Never change WHO does what, never add a situation the question does not have, keep the question's key words, never hint which option is correct.
Best style = the same question set in the viewer's DAILY POSTAL WORK (counter, customer, parcel, registry,
mail bag, beat) in plain spoken words, best 5-8 words (max 12 only if the meaning needs it), naming no
option, e.g. "नाजुक वस्तुओं की सुरक्षा के लिए डाकघर क्या करता है?" -> "ग्राहक काँच का पार्सल लाया, डाकघर क्या करेगा?"
STRICT:
- It must ask EXACTLY the same thing as the full question: same situation, same condition, and the same
  option ({ans}) must be its correct answer. Never drop or change a condition.
- Replace technical terms with their plain meaning from the official source, e.g.
  "embossed postal stationery" -> "जिस लिफाफे/कार्ड पर टिकट पहले से छपा हो".
- Not a yes/no question. Must not reveal the answer. No emoji.
FULL QUESTION (Hindi): {q}
CORRECT ANSWER: {ans}
OFFICIAL SOURCE (English): {src}
Return ONLY JSON: {{"hook": ""}}
"""

HOOK_AUDIT_PROMPT = """You are a strict examiner. Compare the SHORT hook with the FULL exam question.
FULL QUESTION: {q}
CORRECT ANSWER: {ans}
OFFICIAL SOURCE: {src}
SHORT HOOK: {hook}
ok = true ONLY if ALL are true:
1. The hook asks the same thing with the same condition AND the same main subject (what/who) - "{ans}" is
   still the correct answer, and it could not be read as a question about something more general.
2. A GDS postal employee understands it in one quick read (no odd or unclear wording, no unexplained jargon).
3. Nothing misleading or different in meaning (e.g. "low value stationery" instead of "postage exceeds the
   printed stamp value" is WRONG).
4. It does not reveal the answer.
Return ONLY JSON: {{"ok": true/false, "problems": ["..."]}}
"""


def hook_errors(part, hk):
    hk = (hk or "").strip()
    if not hk or not re.search(r"[\u0900-\u097F]", hk):
        return ["HOOK: khaali"]
    errs = []
    n = len(hk.split())
    if not (3 <= n <= 12):
        errs.append(f"HOOK: {n} shabd (3-12 chahiye)")
    if re.match(r"^\s*क्या\s", hk):
        errs.append("HOOK: haan/na wala sawal")
    corr_ = norm_correct(part.get("correct")).lower()
    ans_ = " ".join(str(part.get(corr_, "") if corr_ else "").split())
    if ans_ and len(ans_.split()) >= 2 and ans_ in " ".join(hk.split()):
        errs.append("HOOK: sahi jawab hook me hi likha hai (jawab khul gaya)")
    stop = {"क्या", "कौन", "कौनसा", "कौनसी", "कौनसे", "कितने", "कितनी", "कितना", "किस", "किसके", "किसकी", "किसका",
            "कब", "कहाँ", "कहां", "कैसे", "करें", "करना", "करते", "जाता", "जाती", "जाते", "होता", "होती", "होते",
            "होना", "चाहिए", "लिए", "में", "पर", "से", "को", "का", "की", "के", "है", "हैं", "और", "या", "तो"}
    def _stems(txt):
        ws = re.findall(r"[\u0900-\u097F]+", txt or "")
        return {w[:2] for w in ws if len(w) >= 3 and w not in stop}
    if _stems(hk) and not (_stems(hk) & _stems(part.get("question", ""))):
        errs.append("HOOK: sawal ka koi mukhya shabd hook me nahi - hook alag baat poochh raha hai")
    if re.match(r"^\s*(वे|वह|वो|उन|उस|इन|इस|ये|यह)\s", hk):
        errs.append("HOOK: 'वे/वह/इन...' se shuru - kiski baat, saaf nahi (adhoora)")
    q = part.get("question", "")
    for g in number_groups(hk, "hi"):
        if not any(g & qg for qg in number_groups(q, "hi")):
            errs.append("HOOK: sankhya sawal me nahi")
    return errs


STYLE_VERSION = "2026-09-26c"      # hook/yaad ke niyam badle -> purane (stock) parts bhi reel se pehle naye bane

STYLE_PROMPT = """For this India Post exam MCQ, write two short Hindi lines.
1. hook: IMPORTANT: ONLY use a counter/customer scene if the rule really is about what the postal employee does. If the rule is about the public/sender, ask it plainly. Never change WHO does what, never add a situation the question does not have, keep the question's key words, never hint which option is correct.
   the SAME question set in the viewer's DAILY POSTAL WORK in plain spoken words, so a GDS / postman / counter
   clerk instantly feels "this is my work" (counter, customer, parcel, registry, mail bag, beat, BO).
   Priority: (1) exactly the same meaning as the question - same subject and condition, "{ans}" still the
   correct answer; (2) daily-work connection; (3) simple words, no bookish words; (4) SHORT - best 5-8
   words, up to 12 only if the meaning needs it. Do NOT name any answer option. End with a question,
   not yes/no, answer not revealed, NO fake statistics or claims.
   Examples: "पार्सल की सुरक्षा के लिए उपयोग होने वाले मोम कपड़े को कैसे लगाना चाहिए?" ->
   "काउंटर पर पार्सल आया, मोम कपड़ा कैसे लगेगा?"; "नाजुक वस्तुओं की सुरक्षा के लिए डाकघर क्या करता है?" ->
   "ग्राहक काँच का पार्सल लाया, डाकघर क्या करेगा?"; "एम्बोस्ड स्टेशनरी पर छपे मूल्य से अधिक डाक शुल्क होने पर
   क्या करें?" -> "लिफाफे का छपा टिकट कम पड़े, तो क्या करें?"
2. yaad: a memory formula with arrows (→) or =, max 10 words, 2-3 pieces, taken ONLY from the rule,
   e.g. "टिकट → पुनरुत्पादन → केवल काला" or "रजिस्टर्ड पत्र → मोहर → बुकिंग + गंतव्य डाकघर".
   Keep every number exactly; keep "नहीं" together with what it applies to.
QUESTION: {q}
CORRECT ANSWER: {ans}
RULE: {fact}
Return ONLY JSON: {{"hook": "", "yaad": ""}}
"""

STYLE_AUDIT_PROMPT = """Strict examiner. QUESTION: {q}
CORRECT ANSWER: {ans}
RULE: {fact}
HOOK: {hook}
YAAD: {yaad}
ok = true only if: the HOOK asks exactly the same thing (same main subject and condition, "{ans}" still the
answer, not more general, not yes/no, answer not revealed or hinted, clear Hindi, same WHO does what - no
counter/customer scene added when the rule is about the sender/public) AND the YAAD says only what the RULE
says (no changed number, no misleading order, "नहीं" stays with what it applies to).
Return ONLY JSON: {{"ok": true/false, "hook_ok": true/false, "yaad_ok": true/false, "problems": []}}
"""


def refresh_style(plan, part):
    """
    Stock me pehle se bane parts ka hook + yaad naye niyam se (reel se theek pehle). Examiner-pass hi lagta hai;
    AI busy / fail -> purana hi rehta hai (reel kabhi nahi rukti). Har part pe sirf ek baar.
    """
    already = part.get("style_v") == STYLE_VERSION
    if already and ((part.get("hook_v") or {}).get("ok") or part.get("style_retry")):
        return                  # hook theek hai, ya fail hook ko ek aur mauka mil chuka
    corr = norm_correct(part.get("correct")).lower()
    ans = part.get(corr, "") if corr else ""
    args = dict(q=part.get("question", ""), ans=ans, fact=part.get("fact", ""))
    try:
        fact_groups = number_groups(part.get("fact", ""), "hi")
        t_ = lambda v: v is True or (isinstance(v, str) and v.strip().lower() in ("true", "yes"))
        hk_best, yd_best, hook_ok, yaad_ok, note = "", "", False, False, ""
        for attempt in range(2):                     # hook fail -> ek aur koshish (galti batake)
            res = as_dict(_llm_json(STYLE_PROMPT.format(**args) + note))
            hk = " ".join(str(res.get("hook") or "").split())
            if hk and not hk.endswith("?"):
                hk += "?"
            yd = " ".join(str(res.get("yaad") or "").split())
            h_errs = hook_errors(part, hk) if hk else ["khaali"]
            h_ok = not h_errs
            y_ok = (not yaad_ok) and bool(yd) and bool(re.search(r"=|→", yd)) and len(yd.split()) <= 12 and all(
                any(g & fg for fg in fact_groups) for g in number_groups(yd, "hi"))
            if h_ok or y_ok:
                aud = as_dict(_llm_json(STYLE_AUDIT_PROMPT.format(hook=hk or "-", yaad=yd or "-", **args)))
                if h_ok and not t_(aud.get("hook_ok")):
                    h_ok = False
                    pr = aud.get("problems") or []
                    h_errs = [str(x) for x in (pr if isinstance(pr, list) else [pr])] or ["examiner ne roka"]
                y_ok = y_ok and t_(aud.get("yaad_ok"))
            if y_ok:
                yaad_ok, yd_best = True, yd
            if h_ok:
                hook_ok, hk_best = True, hk
                break
            note = (f"\nYour previous hook \"{hk}\" was REJECTED: {'; '.join(h_errs)[:200]}. "
                    "Write a better one (short, same meaning, key words of the question, no hint of the answer).")
        hk, yd = hk_best, yd_best
    except ProviderBusy:
        print("  Naya hook/yaad: AI busy - is reel me purana")
        return
    except Exception as exc:
        print("  Naya hook/yaad nahi bana:", str(exc)[:100])
        part["style_v"] = STYLE_VERSION
        return
    if hook_ok:
        part["hook_v"] = {"ok": True, "text": hk}
    else:
        part["hook_v"] = {"tries": 2}          # purana (dheela) hook bhi nahi - reel me poora sawal
    if yaad_ok:
        part["yaad"] = yd
    if already:
        part["style_retry"] = True             # fail hook ko ye doosra (aakhri) mauka tha
    part["style_v"] = STYLE_VERSION
    save_plan(plan)
    print(f"  Naya hook: {'haan - ' + hk if hook_ok else 'purana'} | naya yaad: {'haan - ' + yd if yaad_ok else 'purana'}")


def ensure_hook(plan, part):
    """Chhota, aasaan hook - examiner PASS ho tabhi; warna reel me poora sawal (surakshit)."""
    hv = part.get("hook_v") or {}
    if hv.get("ok"):
        return True
    if int(hv.get("tries", 0)) == 9:
        hv = {}
    if int(hv.get("tries", 0)) >= 2:
        return False
    corr = norm_correct(part.get("correct")).lower()
    ans = part.get(corr, "") if corr else ""
    args = dict(q=part.get("question", ""), ans=ans, src=truth_src(part))
    try:
        res = as_dict(_llm_json(HOOK_PROMPT.format(**args)))
        hk = " ".join(str(res.get("hook") or "").split())
        if hk and not hk.endswith("?"):
            hk += "?"
        errs = hook_errors(part, hk)
        if not errs:
            aud = as_dict(_llm_json(HOOK_AUDIT_PROMPT.format(hook=hk, **args)))
            probs = aud.get("problems") or []
            probs = [probs] if isinstance(probs, str) else probs
            probs = [str(p) for p in probs if str(p).strip() and str(p).strip().lower() not in ("none", "no", "[]")]
            ok = aud.get("ok")
            ok = (ok is True or (isinstance(ok, str) and ok.strip().lower() in ("true", "yes"))) and not probs
            if not ok:
                errs = ["examiner: " + ("; ".join(probs) or "ok nahi")]
    except ProviderBusy:
        print("  Hook: AI busy - is reel me poora sawal")
        return False
    except Exception as exc:
        errs = [f"nahi bana: {str(exc)[:100]}"]
    if errs:
        print("  Chhota hook nahi laga (poora sawal dikhega):", "; ".join(errs)[:160])
        part["hook_v"] = {"tries": int(hv.get("tries", 0)) + 1}
        return False
    part["hook_v"] = {"ok": True, "text": hk}
    save_plan(plan)
    print("  Chhota hook taiyar (examiner PASS):", hk)
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


# ==================== "आपके काम में" : niyam ko roz ke daak-kaam se jodna ====================
KAAM_PROMPT = """You help GDS (Gramin Dak Sevak) employees who are preparing for the MTS / Postman / PA exam.
Verified exam rule (Hindi): {fact}
Official source (English / notes): {src}

Write ONE short Hindi line (max 14 words) that shows how this SAME rule appears in the viewer's DAILY postal
work - at the counter, on the beat, with the mail bag, in the BO/SO - so the viewer thinks
"अच्छा, इसलिए हम ये काम ऐसे करते हैं".
STRICT:
- It must follow DIRECTLY from the rule above. Add NO new condition, number, authority, fee, exception or reason
  that is not in the source. Never change who does what.
- If the rule is about the sender/public (not the employee), phrase it as what the employee notices or tells the
  customer, e.g. "काउंटर पर ऐसा पार्सल आए तो ग्राहक से ... करवाएँ" - only if the source supports it.
- Simple spoken Hindi, standard postal terms, numbers as digits, no emoji, no English.
- If no honest daily-work link exists, return "".
Return ONLY JSON: {{"kaam": "..."}}
"""

KAAM_AUDIT_PROMPT = """You are a strict examiner of India Post rules.
Rule (Hindi): {fact}
Official source: {src}
Daily-work line shown to learners: {kaam}
Check: does the line follow ONLY from the rule/source (no new condition, number, authority, fee, exception,
reason; nothing that changes who does what) and is it correct, natural Hindi? A practical, plain restatement
of the same rule as a work action is fine.
Return ONLY JSON: {{"ok": true, "problems": []}}
"""


def ensure_kaam(plan, part):
    """'आपके काम में' line - ek baar banke save; examiner fail -> line nahi dikhti (reel waise hi banti hai)."""
    kv = part.get("kaam_v") or {}
    if not isinstance(kv, dict):
        kv = {}
    if kv.get("ok") or int(kv.get("tries", 0)) >= 2:
        return bool(kv.get("ok"))
    try:
        res = as_dict(_llm_json(KAAM_PROMPT.format(fact=part.get("fact", ""), src=truth_src(part))))
        line = " ".join(str(res.get("kaam") or "").split()).strip(' "')
        errs = []
        if not line:
            errs = ["khaali (koi sachcha kaam-link nahi)"]
        elif len(line.split()) > 16:
            errs = ["lamba"]
        elif re.search(r"[A-Za-z]{3,}", line):
            errs = ["angrezi shabd"]
        else:
            allowed = number_groups(truth_src(part), "en") + number_groups(truth_src(part), "hi") + \
                number_groups(part.get("fact", ""), "hi")
            for g in number_groups(line, "hi"):
                if not any(g & t for t in allowed):
                    errs = ["aisi sankhya jo source me nahi"]
                    break
        if not errs:
            aud = as_dict(_llm_json(KAAM_AUDIT_PROMPT.format(fact=part.get("fact", ""), src=truth_src(part),
                                                             kaam=line)))
            probs = aud.get("problems") or []
            probs = [probs] if isinstance(probs, str) else probs
            probs = [str(p) for p in probs if str(p).strip() and str(p).strip().lower() not in ("none", "no", "[]")]
            ok = aud.get("ok")
            ok = (ok is True or (isinstance(ok, str) and ok.strip().lower() in ("true", "yes"))) and not probs
            if not ok:
                errs = ["examiner: " + ("; ".join(probs) or "ok nahi")]
    except ProviderBusy:
        print("  Kaam-line: AI busy - is reel me nahi")
        return False
    except Exception as exc:
        errs = [f"nahi bani: {str(exc)[:100]}"]
    if errs:
        print("  Kaam-line nahi lagi:", "; ".join(errs)[:160])
        part["kaam_v"] = {"tries": int(kv.get("tries", 0)) + 1}
        save_plan(plan)
        return False
    part["kaam_v"] = {"ok": True, "text": line}
    save_plan(plan)
    print("  Kaam-line taiyar (examiner PASS):", line)
    return True



CHITRA_PROMPT = """You design a 5-second picture explanation for ONE India Post exam rule, shown to GDS employees
(Gramin Dak Sevaks preparing for MTS / Postman / PA) so they feel "this is my daily work - so THIS is why we do it".
There are THREE fixed kits. Pick in this order:
- KIT 3 "address" if the rule is about HOW the address is written (a line of the address, block letters,
  underlining, PIN, legibility, missing parts).
- KIT 1 "article_mark" if the rule is about where something is stuck/placed on a postal article.
- KIT 2 "story" if the rule is about a postal article and what is put ON it (wax, paper, cloth, stamps, labels).
- otherwise ALWAYS KIT 4 "scene" - it can build a picture of ANY rule (who, what, where, when, how much, which
  office, which transport...) by combining pictures with short labels and arrows.
The picture must TEACH by showing the real thing - never just repeat the question or the options in words.

KIT 1 "article_mark":
- object: "envelope" | "postcard" | "parcel"  (the postal article the customer hands over)
- item: "festive_seal" (a decorative non-postal festival seal) | "shop_sticker" (a shop's non-postal label) |
        "postage_stamp"
- wrong_place: where the item is stuck in the WRONG way: "address" | "stamp_corner" | "top_left" | "back"
- right: the CORRECT way: "remove" (item taken off, address side left clear) | "stamp_corner" | "top_left" | "back"
- caps: exactly 3 short Hindi captions (max 7 words each), spoken aloud:
  1) the counter situation, 2) what goes wrong, 3) the correct way / why.

KIT 4 "scene": 3 panels; each panel shows 1-3 PICTURES side by side, each with a short Hindi label (max 3 words,
may hold a number/amount/days ONLY if that number is in the source), optional arrows between them, a caption, a mark.
- panels: exactly 3, each {{"pics": [{{"pic": PIC, "label": ""}}, ...1-3], "arrows": true|false,
  "text": Hindi caption max 7 words, "mark": "none"|"wrong"|"right"}}
  PIC is one of: customer, officer, postman, counter, office, house, village, letter, postcard, parcel, registered,
  moneyorder, stamp, seal, letterbox, bag, clock, calendar, weight, scale, rupee, receipt, form, register, lock,
  datestamp, phone, cycle, van, train, plane, ship, tick_box, cross_box.
  Panel 1 = the situation (mark "none"); panel 2 = the next step (mark "none") or a common MISTAKE the source/answer
  clearly makes wrong (mark "wrong"); panel 3 = what the rule says (mark "right"). Use labels to name the exact
  thing (e.g. pic "office" label "प्रधान डाकघर"; pic "calendar" label "7 दिन" only if 7 days is in the source).
  Panels 2 and 3 must show DIFFERENT pictures or labels (panel 1 and 3 may be the same).

KIT 3 "address": an envelope with a real Indian address (in English, e.g. "PATNA - 800001") at the SORTING rack.
- line: which address line the rule is about: "name" | "house" | "village" | "post_town" | "pin" | "district"
- wrong: how it is written WRONGLY: "small" (small/lower-case letters) | "missing" | "unclear" (hard to read)
- right: how the rule says to write it: "block_caps_underline" | "block_caps" | "clear" | "present"
  (the picture: with the wrong writing the letter gets stuck between rack boxes; written right it goes straight
  into the correct box)
- caps: exactly 3 Hindi captions (max 7 words each): 1) the sorting situation, 2) the problem, 3) the right way.

KIT 2 "story": a 3-panel PICTURE story of daily postal work. Each panel is a real drawn picture; the text is
only a short caption. The PICTURES must show the difference between the wrong and the right way.
- steps: exactly 3 panels, each {{"object": OBJ, "items": [ITEM...], "text": Hindi max 7 words,
  "mark": "none"|"wrong"|"right"}}
  OBJ is one of: envelope, postcard, parcel (drawn big, realistic, with an Indian address) - or, when the rule is
  about a person / place / time: customer, officer, counter, letterbox, bag, clock, weight, cycle, moneyorder,
  receipt, office.
  ITEM (only on envelope / postcard / parcel): {{"item": "wax_seal"|"postage_stamp"|"festive_seal"|"shop_sticker"|
  "tissue_paper"|"thick_cloth"|"plastic_sheet"|"twine", "place": "address"|"stamp_corner"|"top_left"|"center"|"back",
  "count": 1-4}}  ("back" = envelope back / flap; "center" = middle of the article, e.g. the knot of a parcel).
  Items at the SAME place are drawn in list order, each ON TOP of the previous (e.g. [wax_seal, tissue_paper] =
  tissue paper laid over the wax). Use [] for no items. Show the tempting WRONG option and the correct answer as
  pictures when they are physical things (paper, cloth, plastic, extra wax, stamp, label...).
  Panel 1 = the daily situation (mark "none"). Panel 2 = the next step (mark "none") or a COMMON MISTAKE
  (mark "wrong") that the source/answer clearly makes wrong. Panel 3 = what the rule says to do (mark "right").
  Prefer envelope / postcard / parcel pictures whenever the rule is about a postal article. The wrong and right
  panels (2 and 3) must LOOK different (different item, count, place or object); panel 1 and 3 may look the same. Texts describe what happens in the work,
  NOT the exam question or option wording.

Rule (Hindi): {fact}
Question: {question}   Correct answer: {answer}
Reel's opening line: {hook}
Official source: {src}

STRICT:
- If the opening line names an article (पार्सल / लिफाफा / पोस्टकार्ड), use that SAME object / icon.
- Show nothing the source does not say. Kit 1: do NOT show a "right" place unless the source says it is allowed
  there; if the source only forbids a place, use right = "remove". Kit 2: never invent a step, time, fee, number,
  form or authority that is not in the source; keep who-does-what exactly as the source.
- Captions follow ONLY from the rule/source (no new condition, number, reason, authority). Simple spoken Hindi,
  standard postal terms, no English, no emoji. Caption 2 may state the problem only if the source/answer says it.
Return ONLY JSON, one of:
{{"kit": "article_mark", "object": "", "item": "", "wrong_place": "", "right": "", "caps": ["", "", ""]}}
{{"kit": "address", "line": "", "wrong": "", "right": "", "caps": ["", "", ""]}}
{{"kit": "scene", "panels": [{{"pics": [{{"pic": "", "label": ""}}], "arrows": false, "text": "", "mark": "none"}},
 {{"pics": [], "arrows": false, "text": "", "mark": ""}}, {{"pics": [], "arrows": false, "text": "", "mark": "right"}}]}}
{{"kit": "story", "steps": [{{"object": "", "items": [], "text": "", "mark": "none"}},
 {{"object": "", "items": [], "text": "", "mark": ""}}, {{"object": "", "items": [], "text": "", "mark": "right"}}]}}
"""
STORY_ARTICLES = ("envelope", "postcard", "parcel")
STORY_ITEMS = ("wax_seal", "postage_stamp", "festive_seal", "shop_sticker", "tissue_paper", "thick_cloth",
               "plastic_sheet", "twine")
STORY_PLACES = ("address", "stamp_corner", "top_left", "center", "back")
STORY_ICONS = ("customer", "officer", "counter", "letter", "postcard", "parcel", "registered", "moneyorder", "stamp",
               "seal", "letterbox", "bag", "clock", "weight", "cycle", "receipt", "office", "postman", "van",
               "scale", "calendar", "rupee", "form", "register", "lock", "datestamp", "phone", "house", "village",
               "train", "plane", "ship", "tick_box", "cross_box")

CHITRA_AUDIT_PROMPT = """You are a strict examiner of India Post rules. A short animated picture will be shown to
learners to explain this rule.
Rule (Hindi): {fact}
Official source: {src}
PICTURE (exactly what is shown): {story}
Check: does EVERY part of the picture and every caption follow from the rule/source? Nothing may suggest an
extra rule (e.g. that some other place is allowed when the source does not say so), a wrong reason, or a
different article type than the rule covers. Captions must be correct, natural Hindi.
Return ONLY JSON: {{"ok": true, "problems": []}}
"""



TRAP_FIX_PROMPT = """You improve the EXAM TRAP line of ONE verified India Post exam reel (Hindi).
Rule (verified, Hindi): {fact}
Question: {question}   Correct answer: {answer}   Tempting wrong options: {wrong}
Current trap (weak - repeats what the reel already shows, or is vague): {trap}
Already shown in the reel (do NOT repeat any of it): {shown}
Official clause text (source of truth):
<<<
{clause}
>>>
Write ONE new trap line in Hindi, max 11 words, that gives ONE NEW exam-useful fact the viewer has NOT yet seen:
the exception / "only" case, the scope (which articles / which cases it applies to), the exact limit or number,
who decides / which office, or the opposite case. Do NOT repeat the rule, the question, the options or the picture
story; do not just say an option is wrong. No vague words like "यह सावधानी / यह नियम" - name the thing clearly.
Examples of the STYLE (not content): "यह नियम केवल विदेशी डाक पर नहीं, सभी अपंजीकृत पर" -> BAD (vague);
"गरम जलवायु वाले देशों को जाने वाली डाक पर टिशू अनिवार्य" -> GOOD (new, clear). The new fact MUST come from a clause sentence OTHER than the rule's own sentence: copy that sentence exactly into
trap_quote (English, word for word). If the clause has NO other exam-useful sentence, return {{"trap": "",
"trap_quote": ""}} - an empty trap is better than repeating the rule. Numbers as digits, no English words in the trap, no emoji.
Return ONLY JSON: {{"trap": "", "trap_quote": ""}}
"""

TRAP_AUDIT_PROMPT = """You are a strict examiner of India Post rules.
Official clause text:
<<<
{clause}
>>>
Rule shown in the reel (Hindi): {fact}
New EXAM TRAP line (Hindi): {trap}
Check: is the trap line fully correct per the clause text (no invented condition, number, authority or reason),
does read alone it teach the correct rule, and is it correct natural Hindi?
Return ONLY JSON: {{"ok": true, "problems": []}}
"""


def ensure_trap(plan, part, clause_text):
    """Purane plan ka trap sirf niyam dohraye to naya kaam ka trap (examiner-pass). Fail -> purana (sahi) trap hi."""
    if trap_has_new_source(part) and not trap_is_weak(part):
        return False
    tv = part.get("trap_v") or {}
    if isinstance(tv, dict) and int(tv.get("v", 1)) < 3:
        tv = {}
    if tv.get("none"):
        return False
    if not isinstance(tv, dict) or int(tv.get("tries", 0)) >= 2:
        return False
    corr = (part.get("correct") or "a").lower()
    wrong = ", ".join(part.get(k, "") for k in "abcd" if k != corr)
    feedback, errs = "", []
    try:
        for _ in range(2):
            shown_ = "; ".join([part.get("fact", ""), part.get("question", "")] +
                               [part.get(k, "") for k in "abcd"] + list((part.get("chitra_v") or {}).get("caps") or []))
            prompt = TRAP_FIX_PROMPT.format(fact=part.get("fact", ""), question=part.get("question", ""),
                                            answer=part.get(corr, ""), wrong=wrong, trap=part.get("trap", ""),
                                            clause=clause_text[:6000], shown=shown_)
            if feedback:
                prompt += "\\nPREVIOUS ATTEMPT REJECTED for: " + feedback + "\\nFix exactly this."
            res = as_dict(_llm_json(prompt))
            new = " ".join(str(res.get("trap") or "").split())
            tq = " ".join(str(res.get("trap_quote") or "").split())
            cand = dict(part, trap=new, trap_quote=tq)
            errs = [e for e in trap_errors(cand)]
            if trap_is_weak(cand):
                errs.append("naya trap bhi reel me dikh chuki baat dohra raha / gol-mol hai")
            if new and not trap_has_new_source(cand):
                errs.append("trap_quote me clause ka DOOSRA vakya (source_quote ke alawa) shabd-dar-shabd chahiye - "
                            "agar clause me koi aur kaam ki baat nahi, to trap aur trap_quote dono \"\" do")
            if not new:
                part["trap_v"] = {"none": True, "v": 3}
                save_plan(plan)
                print("  Trap: clause me koi nayi baat nahi - is reel me EXAM TRAP nahi dikhega (dohraav se behtar)")
                return False
            if not new or len(new.split()) > 12:
                errs.append("trap khaali/lamba")
            if re.search(r"[A-Za-z]{3,}", new):
                errs.append("trap me angrezi")
            if tq and _squash(tq) not in _squash(clause_text):
                errs.append("trap_quote clause me shabd-dar-shabd nahi")
            allowed = number_groups(truth_src(part), "en") + number_groups(truth_src(part), "hi") + \
                number_groups(tq, "en") + number_groups(part.get("fact", ""), "hi")
            for g in number_groups(new, "hi"):
                if not any(g & t_ for t_ in allowed):
                    errs.append("trap me aisi sankhya jo source me nahi")
                    break
            if not errs:
                aud = as_dict(_llm_json(TRAP_AUDIT_PROMPT.format(clause=clause_text[:6000], fact=part.get("fact", ""),
                                                                 trap=new)))
                probs = aud.get("problems") or []
                probs = [probs] if isinstance(probs, str) else probs
                probs = [str(p_) for p_ in probs if str(p_).strip() and str(p_).strip().lower() not in ("none", "no", "[]")]
                ok = aud.get("ok")
                ok = (ok is True or (isinstance(ok, str) and ok.strip().lower() in ("true", "yes"))) and not probs
                if ok:
                    part["trap_old"] = part.get("trap", "")
                    part["trap"], part["trap_quote"] = new, tq
                    part["trap_v"] = {"ok": True, "v": 3}
                    save_plan(plan)
                    print("  Naya EXAM TRAP (examiner PASS):", new)
                    return True
                errs = ["examiner: " + ("; ".join(probs) or "ok nahi")]
            feedback = "; ".join(errs)[:300]
    except ProviderBusy:
        print("  Trap: AI busy - purana trap is reel me")
        return False
    except Exception as exc:
        feedback = str(exc)[:120]
    print("  Naya trap nahi laga (purana sahi trap rahega):", feedback[:160])
    part["trap_v"] = {"tries": int(tv.get("tries", 0)) + 1, "v": 3}
    save_plan(plan)
    return False


CHITRA_SILENT = ()            # sab khaano ki awaaz hai
CHITRA_C1_SHOW = 1.2          # khaana 1 bina awaaz itni der (sec) dikhta hai
CHITRA_GAP = 0.5              # chitra ke har khaane ke baad thehrav (sec) - dekhne/samajhne ka samay
CHITRA_OK_MIN = 8             # isse naye version ke PASS chitra dobara nahi bante (API bachat)

DRAW_PROMPT = """You are an illustrator for Hindi exam reels for GDS employees (Gramin Dak Sevaks preparing for MTS /
Postman / PA). Draw a 3-panel picture STORY that makes ONE India Post rule understood ~99% FROM THE PICTURES AND
CAPTIONS ALONE, by a viewer who has never read the rule. Set it in the viewer's daily post office work.

Rule (Hindi, verified): {fact}
Question: {question}   Correct answer: {answer}   Tempting wrong options: {wrong}
Official source: {src}

THE STORY MUST HAVE A LOGIC (situation -> mistake -> right way + WHY):
- Panel 1 (mark "none") = the situation: WHICH article (exact type from the rule) and WHAT decision has to be taken.
  Caption = a short full sentence or question, e.g. "ग्राहक साधारण पार्सल लाया - सीलिंग वैक्स लगाएँ?"
- Panel 2 (mark "wrong") = the tempting wrong option actually DONE on the same kind of article. Caption = what was
  done + why it is wrong according to the rule (full sentence, e.g. "हर साधारण पत्र पर वैक्स - ज़रूरत नहीं, गलत").
- Panel 3 (mark "right") = exactly what the rule says. The REASON must be VISIBLE: an "arrow" pointing at the thing
  that matters + a "label" naming it (e.g. what needs protection). Caption = the rule as a full sentence with its
  reason. You MAY use an everyday example object to illustrate the rule's condition (e.g. a loose knot, a fragile
  item), but never invent a new rule, number, office or exception.
- Panels 2 and 3 are CLOSE-UPS: the main article must be BIG (width >= 45% of the canvas), centred, on a plain
  background (no counter/desk/arch behind it). Panel 2 vs panel 3 must differ ONLY in the rule's point, so the eye
  sees the difference instantly (big, central, contrasting colours).
- Spell rule words EXACTLY as written in the rule/question (e.g. अपंजीकृत, not अंजीकृत). Natural, simple Hindi.

Each panel is a {w}x{h} canvas (light cream background already drawn; x right, y down). Draw with a list of shapes:
- {{"t":"rect","x":,"y":,"w":,"h":,"r":corner,"fill":"#RRGGBB[AA]","stroke":"#RRGGBB","sw":width}}
- {{"t":"ellipse","x":,"y":,"w":,"h":,...}}   {{"t":"circle","cx":,"cy":,"r":,...}}
- {{"t":"poly","pts":[[x,y],...],"fill":,"stroke":,"sw":}}   {{"t":"line","pts":[[x,y],...],"stroke":,"sw":}}
- {{"t":"arrow","from":[x,y],"to":[x,y],"color":"#RRGGBB"}}
- {{"t":"sprite","name":NAME,"x":centerX,"y":centerY,"w":width,"rot":deg}}  ready-made pictures you may use:
  {sprites}   (envelope/postcard/parcel = realistic article with Indian address; wax_seal = red sealing-wax seal;
  tissue_paper = thin semi-transparent paper; thick_cloth; plastic_sheet; twine = string knot; postage_stamp;
  festive_seal/shop_sticker = NON-postal labels)
- {{"t":"label","text":"Hindi, max 3 words","x":,"y":,"color":"dark|light|red|green"}}  (max 3 per panel;
  numbers only if in the source)
(Do NOT draw ✓/✗ marks - the reel adds them itself.)
Draw back-to-front (later shapes on top). 6-25 shapes per panel (compact JSON, no comments). Keep everything inside
the canvas. Use a semi-transparent fill (#RRGGBB88) when something lies ON TOP of another thing that must stay visible.
Caption: Hindi, 4-11 words per panel, a complete sentence (all three are SPOKEN aloud), only what the source says.
Also give "desc": one plain English sentence per panel describing exactly what the drawing shows, and "lesson":
one Hindi sentence = what the viewer must understand from the 3 panels.
{feedback}
Return ONLY JSON: {{"lesson":"","panels":[{{"shapes":[...],"text":"","desc":"","mark":"none"}},
{{"shapes":[...],"text":"","desc":"","mark":"wrong"}},{{"shapes":[...],"text":"","desc":"","mark":"right"}}]}}
"""

# Andhi-jaanch: Gemini ko NIYAM NAHI batate - sirf chitra + caption. Wo khud bataye kya samjha; fir text-jaj milaata hai.
BLIND_PROMPT = """You are a GDS post office employee who has NEVER read this rule. Look at the 3 attached pictures in
order. Captions (spoken aloud): 1) {c1}  2) {c2}  (shown with a red X = MISTAKE)  3) {c3}  (shown with a green tick =
RIGHT way).
Using ONLY the pictures and captions, answer honestly:
- "lesson": in one English sentence, the exact rule you learned (what to do, on which article, when/why).
- "why3": why is picture 3 right and picture 2 wrong - what exactly is different in the pictures?
- "confusing": list everything confusing: unclear objects, text you cannot read, a caption that does not match its
  picture, misspelt words, things cut off or overlapping, panels that look almost the same.
- "clarity": 1-10, how sure you are about the rule from the pictures alone.
Return ONLY JSON: {{"lesson":"","why3":"","confusing":[],"clarity":0}}
"""

BLIND_JUDGE_PROMPT = """A viewer saw only a 3-panel picture story (not the rule) and wrote what he learned.
Real rule (Hindi): {fact}
Official source: {src}
Viewer learned: {lesson}
Viewer's reason for panel 3 vs 2: {why3}
Did the viewer learn EXACTLY the real rule (same article type, same action, same condition) and nothing false?
Return ONLY JSON: {{"same": true, "missing": "what he missed or got wrong (empty if same)"}}
"""

VISION_PROMPT = BLIND_PROMPT       # purana naam (pichhle code ke liye)


_HI_WORD = re.compile(r"[\u0900-\u097F]+")


def _hi_norm(w):
    return w.replace("ँ", "ं").replace("़", "")


def hindi_typos(text, ref):
    """
    Caption/label me rule-shabdon ki galat vartani pakdo (jaise 'अंजीकृत' jab rule me 'अपंजीकृत' hai).
    Sirf beech ki galti - shabd ke ant ka badlaav (पत्र/पत्रों) galti nahi maana jaata.
    """
    from difflib import SequenceMatcher
    refs = {_hi_norm(w) for w in _HI_WORD.findall(ref) if len(w) >= 4}
    bad = []
    for w in _HI_WORD.findall(text):
        n = _hi_norm(w)
        if len(n) < 4 or n in refs:
            continue
        for r in refs:
            if abs(len(r) - len(n)) > 2:
                continue
            pre = 0
            while pre < min(len(r), len(n)) and r[pre] == n[pre]:
                pre += 1
            if pre >= min(len(r), len(n)) - 2:
                continue                                    # sirf ant badla (vibhakti) - theek
            if SequenceMatcher(None, n, r).ratio() >= 0.85:
                bad.append(f"{w} (sahi: {r})")
                break
    return bad


def _shape_w(sh):
    t = sh.get("t")
    try:
        if t in ("rect", "ellipse", "sprite"):
            return float(sh.get("w") or 0)
        if t == "circle":
            return 2 * float(sh.get("r") or 0)
        if t == "poly":
            xs = [float(p_[0]) for p_ in sh.get("pts") or []]
            return max(xs) - min(xs) if xs else 0.0
    except (TypeError, ValueError, IndexError):
        return 0.0
    return 0.0


def draw_logic_errors(panels, part):
    """Code se pakki jaanch: kahani ka logic (bada main object, panel 3 me teer+label 'kyon', poore vaakya, vartani)."""
    errs = []
    caps = [p_["text"] for p_ in panels]
    ref = " ".join(str(part.get(k) or "") for k in ("fact", "question", "a", "b", "c", "d", "hook", "scene_line"))
    labels = " ".join(str(x.get("text") or "") for p_ in panels for x in p_["shapes"] if x.get("t") == "label")
    ty = hindi_typos(" ".join(caps) + " " + labels, ref)
    if ty:
        errs.append("galat vartani: " + ", ".join(ty[:4]))
    short = [str(i + 1) for i, c in enumerate(caps) if not 4 <= len(c.split()) <= 12]
    if short:
        errs.append(f"caption {','.join(short)}: tukda hai - 4-11 shabd ka poora vaakya (kya + kyon) likho")
    for i in (1, 2):
        sh = panels[i]["shapes"]
        sps = [_shape_w(x) for x in sh if x.get("t") == "sprite"]      # asli cheez (lifaafa/parcel) ka naap
        big = max(sps or [_shape_w(x) for x in sh if x.get("t") in ("rect", "ellipse", "circle", "poly")
                          and _shape_w(x) < DRAW_W * 0.95] or [0])
        if big < DRAW_W * 0.42:
            errs.append(f"panel {i + 1}: mukhya cheez chhoti ({big:.0f}px) - close-up me kam se kam {int(DRAW_W * 0.45)}px chaudi banao")
    s3 = panels[2]["shapes"]
    if not any(x.get("t") == "arrow" for x in s3) or not any(x.get("t") == "label" for x in s3):
        errs.append("panel 3 me 'kyon' nahi dikha - jo cheez niyam ki wajah hai us par arrow + label lagao")
    return errs


def _gemini_draw(prompt):
    """Drawing ke liye alag call: lamba jawab (maxOutputTokens bada); adhoora jawab pe model 'busy' NAHI maana jaata."""
    if not GEMINI_API_KEY:
        raise ProviderBusy("Gemini key nahi")
    last = None
    for model in gemini_candidates():
        if model in _BUSY:
            continue
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 32768,
                                     "temperature": 0.7}}
        try:
            r = requests.post(url, params={"key": GEMINI_API_KEY.strip()}, json=body, timeout=300)
        except requests.RequestException as exc:
            last = exc
            continue
        if r.status_code in (429, 503):
            print(f"  Chitra-draw {model}: {r.status_code} busy -> agla model")
            _BUSY.add(model)
            last = RuntimeError(f"{model} {r.status_code}")
            continue
        if r.status_code in (400, 404, 500):
            print(f"  Chitra-draw {model}: {r.status_code} ({r.text[:120]}) -> agla model")
            last = RuntimeError(f"{model} {r.status_code}")
            continue
        _raise_for(r, f"Gemini draw({model})")
        try:
            cand = r.json()["candidates"][0]
            text = "".join(p.get("text", "") for p in cand["content"]["parts"] if not p.get("thought"))
            return _parse_json(text)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            fr = ""
            try:
                fr = r.json()["candidates"][0].get("finishReason", "")
            except Exception:
                pass
            print(f"  Chitra-draw {model}: jawab adhoora/galat JSON ({type(exc).__name__}, finish={fr}) -> agla model")
            last = exc
            continue
    raise ProviderBusy(f"Chitra-draw: koi model drawing nahi de paya: {last}")


def _gemini_vision(prompt, pngs):
    """Gemini ko chitra (PNG) dikha ke JSON jawab. Busy -> ProviderBusy."""
    import base64
    if not GEMINI_API_KEY:
        raise ProviderBusy("Gemini key nahi - chitra ki aankh-jaanch nahi ho sakti")
    parts = [{"text": prompt}] + [{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(b).decode()}}
                                  for b in pngs]
    last = None
    for model in gemini_candidates():
        if model in _BUSY:
            continue
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json"}}
        try:
            r = requests.post(url, params={"key": GEMINI_API_KEY.strip()}, json=body, timeout=240)
        except requests.RequestException as exc:
            last = exc
            continue
        if r.status_code in (400, 404, 429, 500, 503):
            print(f"  Gemini vision {model}: {r.status_code} -> agla model")
            _BUSY.add(model)
            last = RuntimeError(f"{model} {r.status_code}")
            continue
        _raise_for(r, f"Gemini vision({model})")
        try:
            ps = r.json()["candidates"][0]["content"]["parts"]
            return _parse_json("".join(p.get("text", "") for p in ps if not p.get("thought")))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            _BUSY.add(model)
            last = exc
            continue
    raise ProviderBusy(f"Gemini vision busy: {last}")


def _png_bytes(im):
    import io
    bg = Image.new("RGB", im.size, (20, 36, 66))
    bg.paste(im, (0, 0), im)
    buf = io.BytesIO()
    bg.save(buf, "PNG")
    return buf.getvalue()


def _draw_attempt(part, feedback=""):
    """Kit 'draw': AI drawing banata hai -> code jaanch -> render -> Gemini aankh se jaanch -> text examiner."""
    corr = (part.get("correct") or "a").lower()
    wrong = ", ".join(part.get(k, "") for k in "abcd" if k != corr)
    fb = ("\\nPREVIOUS DRAWING WAS REJECTED. Examiner said: " + feedback + "\\nRedraw fixing exactly this.") if feedback else ""
    res = as_dict(_gemini_draw(DRAW_PROMPT.format(fact=part.get("fact", ""), question=part.get("question", ""),
                                             answer=part.get(corr, ""), wrong=wrong, src=truth_src(part),
                                             w=DRAW_W, h=DRAW_H, sprites=", ".join(DRAW_SPRITES), feedback=fb)))
    raw = res.get("panels") if isinstance(res.get("panels"), list) else []
    if len(raw) != 3:
        return None, ["3 panel nahi"], ""
    panels = []
    for i, x in enumerate(raw):
        if not isinstance(x, dict):
            return None, ["panel dict nahi"], ""
        shapes = x.get("shapes")
        try:
            draw_validate(shapes)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            return None, [f"panel {i + 1} drawing galat: {exc}"], ""
        panels.append({"shapes": shapes, "text": " ".join(str(x.get("text") or "").split()),
                       "desc": " ".join(str(x.get("desc") or "").split()),
                       "mark": ("none", "wrong", "right")[i]})
    caps = [p_["text"] for p_ in panels]
    errs = []
    if any(not c for c in caps):
        errs.append("caption khaali")
    if any(re.search(r"[A-Za-z]{3,}", c) for c in caps):
        errs.append("caption me angrezi")
    allowed = number_groups(truth_src(part), "en") + number_groups(truth_src(part), "hi") + \
        number_groups(part.get("fact", ""), "hi")
    labels = " ".join(str(sh.get("text") or "") for p_ in panels for sh in p_["shapes"] if sh.get("t") == "label")
    for c in caps + [labels]:
        for g in number_groups(c, "hi"):
            if not any(g & t_ for t_ in allowed):
                errs.append("caption/label me aisi sankhya jo source me nahi")
                break
    errs += draw_logic_errors(panels, part)
    if errs:
        print("  Chitra (draw) logic-jaanch FAIL: " + "; ".join(errs)[:220])
        return None, errs, ""
    try:
        imgs = [render_drawing(p_["shapes"]) for p_ in panels]
    except Exception as exc:
        return None, [f"drawing ban nahi paya: {str(exc)[:80]}"], ""
    for i, im in enumerate(imgs):                           # khaali/ek-rang chitra nahi
        a = np.asarray(im.convert("L"), dtype=np.float32)
        if a.std() < 12:
            return None, [f"panel {i + 1} lagbhag khaali"], ""
    vis = as_dict(_gemini_vision(BLIND_PROMPT.format(c1=caps[0], c2=caps[1], c3=caps[2]),
                                 [_png_bytes(im) for im in imgs]))
    try:
        score = float(vis.get("clarity") or vis.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    probs = vis.get("confusing") or []
    probs = [probs] if isinstance(probs, str) else [str(p_) for p_ in probs if str(p_).strip()
                                                     and str(p_).strip().lower() not in ("none", "no", "nothing")]
    lesson = " ".join(str(vis.get("lesson") or "").split())
    why3 = " ".join(str(vis.get("why3") or "").split())
    print(f"  Chitra (draw) andhi-jaanch: {score:.0f}/10 | samjha: {lesson[:140]}"
          + (f" | uljhan: {'; '.join(probs)[:160]}" if probs else ""))
    if score < DRAW_MIN_SCORE or not lesson:
        return None, [f"bina niyam padhe dekhne wala {score:.0f}/10 hi samjha; usne samjha: '{lesson[:160]}'; "
                      f"uljhan: " + "; ".join(probs)[:250]], ""
    jj = as_dict(_llm_json(BLIND_JUDGE_PROMPT.format(fact=part.get("fact", ""), src=truth_src(part),
                                                     lesson=lesson, why3=why3)))
    same = jj.get("same")
    same = same is True or (isinstance(same, str) and same.strip().lower() in ("true", "yes"))
    print(f"  Chitra (draw) niyam-milan: {'PASS' if same else 'FAIL'}"
          + (f" - {str(jj.get('missing') or '')[:160]}" if not same else ""))
    if not same:
        return None, [f"dekhne wale ne galat niyam samjha: '{lesson[:160]}' - chhoota: "
                      + str(jj.get("missing") or "")[:200]], ""
    cfg = {"kit": "draw", "panels": panels, "caps": caps, "score": score, "lesson": lesson}
    aud = as_dict(_llm_json(CHITRA_AUDIT_PROMPT.format(fact=part.get("fact", ""), src=truth_src(part),
                                                       story=chitra_story_en(cfg))))
    ps2 = aud.get("problems") or []
    ps2 = [ps2] if isinstance(ps2, str) else [str(p_) for p_ in ps2 if str(p_).strip() and str(p_).strip().lower() not in ("none", "no", "[]")]
    ok2 = aud.get("ok")
    ok2 = (ok2 is True or (isinstance(ok2, str) and ok2.strip().lower() in ("true", "yes"))) and not ps2
    if not ok2:
        return None, ["examiner: " + ("; ".join(ps2) or "ok nahi")], ""
    return cfg, [], ""


# ==================== KIT "photo": Cloudflare (free) FLUX se ASLI chitra + hamari Hindi parchi/ghera ====================
# AI-image me likhai kabhi nahi (wo galat Hindi likhta hai); niyam wali parchi/ghera hamara code upar lagata hai.
# Jaanch: (1) Gemini aankh: chitra me wahi hai? mukhya cheez kahan hai (box)? nakli akshar/bigde haath? 
#         (2) andhi-jaanch: bina niyam padhe dekhne wala kya samjha -> asli niyam se milan  (3) text examiner.
CF_ACCOUNT_ID = (os.getenv("CLOUDFLARE_ACCOUNT_ID") or "").strip()
CF_API_TOKEN = (os.getenv("CLOUDFLARE_API_TOKEN") or "").strip()
CF_IMAGE_MODEL = os.getenv("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
USE_PHOTO = os.getenv("USE_PHOTO", "1") != "0" and bool(CF_ACCOUNT_ID and CF_API_TOKEN)
PHOTO_DIR = os.path.join("clause_plans", "chitra_img")
PHOTO_STEPS = 8               # flux-schnell: 8 = sabse saaf (free quota me ~100+ chitra roz)
PHOTO_TRIES = 3               # ek run me poori kahani ke itne mauke (har baar pichhli galti batake)
PHOTO_ROUNDS = 3              # har kahani me kharab khaana itni baar dobara banta hai
PHOTO_MIN_SCORE = 7           # Gemini aankh: har chitra kam se kam itna saaf
CHITRA_PREVIEW = os.getenv("CHITRA_PREVIEW", "1") != "0"   # 1 = sirf chitra ka namoona (reel nahi) - pasand aaye to 0

PHOTO_STYLE = ("Flat 2D vector illustration, modern Indian educational cartoon style, clean bold outlines, soft warm "
               "colours, simple plain light background, the main object large, centred and clearly recognisable, "
               "Indian people in everyday Indian clothes, Indian village post office. Absolutely no text, no letters, "
               "no words, no numbers, no logos, no signs, no labels, no writing anywhere in the image.")

PHOTO_PLAN_PROMPT = """You design a 3-picture story for a Hindi exam reel for GDS employees (Gramin Dak Sevaks preparing
for MTS / Postman / PA). The pictures are made by an image AI and must make ONE India Post rule understood ~99% by a
viewer who never read the rule.

Rule (Hindi, verified): {fact}
Question: {question}   Correct answer: {answer}   Tempting wrong options: {wrong}
Official source: {src}

IMPORTANT about the image AI: it draws people, hands, objects, counters, parcels, letters, coins, jewellery, scales,
bags, vans etc. very well, but it CANNOT write any text and does not know India Post forms or labels. So:
- Each picture shows ONE simple, clear scene (max 2 people, one main object, close view, no clutter).
- Anything postal-specific (a label like "बीमाकृत" / "रजिस्टर्ड", a seal name, a form name) is NOT drawn by the image
  AI - you put it in "tag": a Hindi word (1-3 words) that our code pastes ON the main object ("target").
- Panel 2 and panel 3 show the SAME kind of main object; the difference (the heart of the rule) is the action/state
  and the tag, so the eye sees it instantly.

STORY LOGIC: panel 1 (mark "none") = the daily situation: which article and what decision is needed.
panel 2 (mark "wrong") = the tempting wrong option actually done. panel 3 (mark "right") = exactly what the rule says.
Never show anything the source does not say (no new rule, number, office or exception).

For each panel give:
- "prompt": English, 1-2 sentences, ONLY what is visible (people, action, objects, colours). No text/labels in it.
- "target": English short noun phrase = the main object to mark (e.g. "the brown parcel on the counter").
- "tag": Hindi 1-3 words pasted on the target ("" if none; panels 2 and 3 should usually have one).
- "tag_color": "red" (wrong / warning), "green" (right), or "dark".
- "text": Hindi caption, a complete sentence of 4-11 words, spoken aloud (what happens + why). Spell rule words
  exactly as in the rule/question. Simple natural Hindi, no English.
- "desc": one English sentence describing the final picture including the tag.
Also "scene": one English sentence describing the shared setting and the people (same in all 3 pictures), and
"lesson": one Hindi sentence = what the viewer must learn.
{feedback}
Return ONLY JSON: {{"scene":"","lesson":"","panels":[{{"prompt":"","target":"","tag":"","tag_color":"dark","text":"","desc":"","mark":"none"}},
{{"prompt":"","target":"","tag":"","tag_color":"red","text":"","desc":"","mark":"wrong"}},
{{"prompt":"","target":"","tag":"","tag_color":"green","text":"","desc":"","mark":"right"}}]}}
"""

PHOTO_CHECK_PROMPT = """You check AI-generated illustrations for a Hindi educational reel. The attached images are, in
order:
{items}
For EACH image answer honestly:
- "match": true only if the image clearly shows the intended content and the key object is clearly visible.
- "box_2d": bounding box of the key object as [ymin, xmin, ymax, xmax], normalised 0-1000.
- "gibberish_text": true if fake letters, words or numbers are clearly visible anywhere.
- "defects": list of serious problems (distorted faces or hands, extra limbs, melted or unrecognisable objects,
  confusing clutter). Empty list if none.
- "score": 1-10, how clear and clean the picture is.
- "problem": short English note on what to change (empty if fine).
Return ONLY JSON: {{"images":[{{"match":true,"box_2d":[0,0,1000,1000],"gibberish_text":false,"defects":[],"score":0,"problem":""}}]}}
"""


def _cf_image(prompt, seed):
    """Cloudflare Workers AI (free roz ka quota) se ek chitra -> JPEG bytes. Quota/busy -> ProviderBusy."""
    import base64
    if not (CF_ACCOUNT_ID and CF_API_TOKEN):
        raise ProviderBusy("Cloudflare secrets nahi (CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN)")
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{CF_IMAGE_MODEL}"
    last = None
    for attempt in range(2):
        try:
            r = requests.post(url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"},
                              json={"prompt": prompt[:2000], "steps": PHOTO_STEPS, "seed": int(seed) % 2147483647},
                              timeout=120)
        except requests.RequestException as exc:
            last = exc
            continue
        if r.status_code in (429, 503, 502, 504):
            raise ProviderBusy(f"Cloudflare {r.status_code} (aaj ka free quota khatam / busy): {r.text[:120]}")
        if r.status_code in (401, 403, 404):
            raise ProviderBusy(f"CLOUDFLARE SETUP GALAT ({r.status_code}): Account ID ya token galat, ya token me "
                               f"'Workers AI' permission nahi. GitHub secrets jaanchiye. {r.text[:120]}")
        if r.status_code != 200:
            last = RuntimeError(f"Cloudflare {r.status_code}: {r.text[:160]}")
            continue
        if r.headers.get("content-type", "").startswith("image/"):
            return r.content
        try:
            js = r.json()
            img = (js.get("result") or {}).get("image") if isinstance(js.get("result"), dict) else js.get("image")
            return base64.b64decode(img)
        except Exception as exc:
            last = exc
            continue
    raise RuntimeError(f"Cloudflare chitra nahi aaya: {last}")


_HI_CLEAN = re.compile(r"[^ऀ-ॿ0-9 ,.!?()\-:]")


def clean_hi(text):
    """Hindi label se ZWJ/ZWNJ/ajeeb chinh hatao (warna font me ◻◻ dikhte hain)."""
    return " ".join(_HI_CLEAN.sub("", str(text or "").replace("‌", "").replace("‍", "")).split())


def photo_files_ok(cv):
    try:
        return len(cv.get("panels") or []) == 3 and all(os.path.exists(p_["img"]) for p_ in cv["panels"])
    except (TypeError, KeyError):
        return False


def _photo_box(v):
    """Gemini box_2d [ymin,xmin,ymax,xmax] 0-1000 -> [x0,y0,x1,y1] 0-1; galat -> None."""
    try:
        y0, x0, y1, x1 = [float(a) / 1000.0 for a in v]
    except (TypeError, ValueError):
        return None
    x0, x1 = sorted((clamp(x0), clamp(x1)))
    y0, y1 = sorted((clamp(y0), clamp(y1)))
    area = (x1 - x0) * (y1 - y0)
    if area < 0.01 or area > 0.92:
        return None
    return [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]


def photo_plan_errors(panels, part):
    errs = []
    caps = [p_["text"] for p_ in panels]
    if any(not p_["prompt"] or not p_["target"] for p_ in panels):
        errs.append("har khaane ka prompt aur target chahiye")
    short = [str(i + 1) for i, c in enumerate(caps) if not 4 <= len(c.split()) <= 12]
    if short:
        errs.append(f"caption {','.join(short)}: 4-11 shabd ka poora vaakya chahiye")
    if any(re.search(r"[A-Za-z]{3,}", c) for c in caps):
        errs.append("caption me angrezi")
    for i, p_ in enumerate(panels):
        if p_["tag"] and (len(p_["tag"].split()) > 3 or not re.search(r"[ऀ-ॿ]", p_["tag"])):
            errs.append(f"panel {i + 1} tag 1-3 Hindi shabd ka ho")
    if not panels[2]["tag"] and not panels[1]["tag"]:
        errs.append("panel 2/3 me niyam wali parchi (tag) nahi - farak dikhega kaise")
    ref = " ".join(str(part.get(k) or "") for k in ("fact", "question", "a", "b", "c", "d", "hook", "scene_line"))
    ty = hindi_typos(" ".join(caps + [p_["tag"] for p_ in panels]), ref)
    if ty:
        errs.append("galat vartani: " + ", ".join(ty[:4]))
    allowed = number_groups(truth_src(part), "en") + number_groups(truth_src(part), "hi") + \
        number_groups(part.get("fact", ""), "hi")
    for c in caps + [p_["tag"] for p_ in panels]:
        for g in number_groups(c, "hi"):
            if not any(g & t_ for t_ in allowed):
                errs.append("caption/tag me aisi sankhya jo source me nahi")
                break
    return errs


def _photo_key(part):
    import hashlib
    return hashlib.md5((part.get("question", "") + "|" + part.get("fact", "")).encode("utf-8")).hexdigest()[:10]


def _photo_attempt(part, feedback=""):
    """Kahani (text AI) -> 3 chitra (Cloudflare) -> aankh-jaanch + box -> parchi lagao -> andhi-jaanch -> examiner."""
    import io
    corr = (part.get("correct") or "a").lower()
    wrong = ", ".join(part.get(k, "") for k in "abcd" if k != corr)
    fb = ("\nPREVIOUS STORY WAS REJECTED. Reason: " + feedback + "\nMake a new story fixing exactly this.") if feedback else ""
    res = as_dict(_llm_json(PHOTO_PLAN_PROMPT.format(fact=part.get("fact", ""), question=part.get("question", ""),
                                                     answer=part.get(corr, ""), wrong=wrong, src=truth_src(part),
                                                     feedback=fb)))
    raw = res.get("panels") if isinstance(res.get("panels"), list) else []
    if len(raw) != 3 or not all(isinstance(x, dict) for x in raw):
        return None, ["3 khaane nahi aaye"]
    scene = " ".join(str(res.get("scene") or "").split())
    panels = []
    for i, x in enumerate(raw):
        tc = str(x.get("tag_color") or "dark").lower().strip()
        panels.append({"prompt": " ".join(str(x.get("prompt") or "").split()),
                       "target": " ".join(str(x.get("target") or "").split()),
                       "tag": clean_hi(x.get("tag")), "tag_color": tc if tc in ("red", "green", "dark") else "dark",
                       "text": " ".join(str(x.get("text") or "").split()),
                       "desc": " ".join(str(x.get("desc") or "").split()),
                       "mark": ("none", "wrong", "right")[i]})
    errs = photo_plan_errors(panels, part)
    if errs:
        print("  Chitra (photo) kahani-jaanch FAIL: " + "; ".join(errs)[:220])
        return None, errs
    # --- 3 chitra Cloudflare se; kharab khaana dobara (sirf wahi) ---
    seed0 = random.randint(1000, 10 ** 8)
    imgs, boxes, todo, last_probs = [None] * 3, [None] * 3, [0, 1, 2], {}
    for rnd in range(PHOTO_ROUNDS):
        for i in todo:
            pr = f"{scene} {panels[i]['prompt']} {PHOTO_STYLE}"
            imgs[i] = _cf_image(pr, seed0 + 7919 * rnd + 31 * i)
        items = "\n".join(f"image {j + 1}: intended content: {panels[i]['prompt']} | key object: {panels[i]['target']}"
                          for j, i in enumerate(todo))
        chk = as_dict(_gemini_vision(PHOTO_CHECK_PROMPT.format(items=items), [imgs[i] for i in todo]))
        rows = chk.get("images") if isinstance(chk.get("images"), list) else []
        bad = []
        for j, i in enumerate(todo):
            r_ = rows[j] if j < len(rows) and isinstance(rows[j], dict) else {}
            try:
                sc_ = float(r_.get("score") or 0)
            except (TypeError, ValueError):
                sc_ = 0.0
            box = _photo_box(r_.get("box_2d"))
            defects = r_.get("defects") or []
            defects = [defects] if isinstance(defects, str) else [str(d) for d in defects if str(d).strip()]
            okk = r_.get("match") is True and box and not r_.get("gibberish_text") and sc_ >= PHOTO_MIN_SCORE \
                and not (defects and sc_ < 8)
            print(f"  Chitra (photo) khaana {i + 1}: aankh {sc_:.0f}/10 {'PASS' if okk else 'FAIL'}"
                  + ("" if okk else f" - {str(r_.get('problem') or '; '.join(defects) or 'match/box nahi')[:120]}"))
            if okk:
                boxes[i] = box
            else:
                bad.append(i)
                last_probs[i] = str(r_.get("problem") or "; ".join(defects) or "")[:150]
        todo = bad
        if not todo:
            break
    if todo:
        return None, ["chitra saaf nahi bana (khaana " + ", ".join(str(i + 1) for i in todo) + "): "
                      + "; ".join(last_probs.get(i, "") for i in todo)[:300]]
    # --- save (repo me) ---
    os.makedirs(PHOTO_DIR, exist_ok=True)
    key = _photo_key(part)
    for i in range(3):
        im = Image.open(io.BytesIO(imgs[i])).convert("RGB")
        path = os.path.join(PHOTO_DIR, f"{key}_{seed0}_{i + 1}.jpg").replace("\\", "/")
        im.save(path, "JPEG", quality=88)
        panels[i]["img"] = path
        panels[i]["box"] = boxes[i]
    # --- andhi-jaanch: parchi/ghera laga ke, NIYAM BINA ---
    caps = [p_["text"] for p_ in panels]
    stills = [_png_bytes(photo_still(p_, 768)) for p_ in panels]
    vis = as_dict(_gemini_vision(BLIND_PROMPT.format(c1=caps[0], c2=caps[1], c3=caps[2]), stills))
    try:
        score = float(vis.get("clarity") or vis.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    probs = vis.get("confusing") or []
    probs = [probs] if isinstance(probs, str) else [str(p_) for p_ in probs if str(p_).strip()
                                                     and str(p_).strip().lower() not in ("none", "no", "nothing")]
    lesson = " ".join(str(vis.get("lesson") or "").split())
    why3 = " ".join(str(vis.get("why3") or "").split())
    print(f"  Chitra (photo) andhi-jaanch: {score:.0f}/10 | samjha: {lesson[:140]}"
          + (f" | uljhan: {'; '.join(probs)[:160]}" if probs else ""))
    def _drop():
        for p_ in panels:
            try:
                os.remove(p_["img"])
            except OSError:
                pass
    if score < DRAW_MIN_SCORE or not lesson:
        _drop()
        return None, [f"bina niyam padhe dekhne wala {score:.0f}/10 hi samjha; usne samjha: '{lesson[:160]}'; "
                      f"uljhan: " + "; ".join(probs)[:250]]
    jj = as_dict(_llm_json(BLIND_JUDGE_PROMPT.format(fact=part.get("fact", ""), src=truth_src(part),
                                                     lesson=lesson, why3=why3)))
    same = jj.get("same")
    same = same is True or (isinstance(same, str) and same.strip().lower() in ("true", "yes"))
    print(f"  Chitra (photo) niyam-milan: {'PASS' if same else 'FAIL'}"
          + (f" - {str(jj.get('missing') or '')[:160]}" if not same else ""))
    if not same:
        _drop()
        return None, [f"dekhne wale ne galat niyam samjha: '{lesson[:160]}' - chhoota: "
                      + str(jj.get("missing") or "")[:200]]
    cfg = {"kit": "photo", "panels": panels, "caps": caps, "score": score, "lesson": lesson}
    aud = as_dict(_llm_json(CHITRA_AUDIT_PROMPT.format(fact=part.get("fact", ""), src=truth_src(part),
                                                       story=chitra_story_en(cfg))))
    ps2 = aud.get("problems") or []
    ps2 = [ps2] if isinstance(ps2, str) else [str(p_) for p_ in ps2 if str(p_).strip() and str(p_).strip().lower() not in ("none", "no", "[]")]
    ok2 = aud.get("ok")
    ok2 = (ok2 is True or (isinstance(ok2, str) and ok2.strip().lower() in ("true", "yes"))) and not ps2
    if not ok2:
        _drop()
        return None, ["examiner: " + ("; ".join(ps2) or "ok nahi")]
    return cfg, []


def chitra_ready(cv):
    """Ye save hua chitra reel me lag sakta hai? (ek hi jagah niyam - gate, look-ahead, prepare_data)"""
    if not isinstance(cv, dict) or not cv.get("ok") or int(cv.get("v", 1)) < CHITRA_OK_MIN:
        return False
    kit = cv.get("kit") or "article_mark"
    if not USE_ICON_KITS and kit in ("story", "scene"):
        return False
    if kit == "draw" and not USE_DRAW:
        return False
    if USE_PHOTO and kit != "photo":
        return False                       # Cloudflare chalu: sirf asli chitra
    if kit == "photo" and not photo_files_ok(cv):
        return False                       # chitra file repo me nahi (commit nahi hui) -> dobara banega
    return True


DRAW_MIN_SCORE = 8            # aankh-jaanch me itne (10 me se) number tabhi chitra lagta hai
DRAW_TRIES = 2                # har run me 'draw' kit ke itne mauke, fir icon-kit
CHITRA_SCHEMA = 9             # niyam badle to ye badhao -> purane save kiye chitra dobara bante hain
CHITRA_TRIES_PER_RUN = 4      # ek run me itne mauke (har baar pichhli galti AI ko batai jaati hai)
CHITRA_MAX_RUNS = 4           # itne alag din/run tak koshish (part publish hone se pehle bhi - look-ahead)


def _chitra_attempt(part, feedback=""):
    """Ek koshish: (cfg, errs). cfg None ho to errs me wajah."""
    corr = (part.get("correct") or "a").lower()
    prompt = CHITRA_PROMPT.format(fact=part.get("fact", ""), question=part.get("question", ""),
                                  answer=part.get(corr, ""), src=truth_src(part),
                                  hook=((part.get("hook_v") or {}).get("text") or "-"))
    if feedback:
        prompt += ("\nYOUR PREVIOUS ATTEMPT WAS REJECTED for: " + feedback +
                   "\nFix exactly these problems. Keep strictly to the source.")
    res = as_dict(_llm_json(prompt))
    kit = str(res.get("kit") or "").strip().lower()
    errs = []
    if not USE_ICON_KITS and kit in ("story", "scene"):
        return None, ["icon-kahani band hai (kamzor chitra) - 'article_mark' ya 'address' hi"]
    if kit not in ("article_mark", "story", "address", "scene"):
        return None, ["kit 'none' nahi chalega - kit 4 (scene) chitra+label se har niyam dikha sakta hai, use lo"]
    if kit == "scene":
        raw = res.get("panels") if isinstance(res.get("panels"), list) else []
        panels = []
        for x in raw[:3]:
            if not isinstance(x, dict):
                continue
            pics = [{"pic": str(p_.get("pic") or "").strip().lower(), "label": " ".join(str(p_.get("label") or "").split())}
                    for p_ in (x.get("pics") if isinstance(x.get("pics"), list) else []) if isinstance(p_, dict)]
            panels.append({"pics": pics, "arrows": bool(x.get("arrows")),
                           "text": " ".join(str(x.get("text") or "").split()),
                           "mark": str(x.get("mark") or "none").strip().lower()})
        cfg = {"panels": panels}
        caps = [x["text"] for x in panels]
        marks_ = [x["mark"] for x in panels]
        if len(panels) != 3 or marks_[0] != "none" or marks_[2] != "right" or marks_[1] == "right" or \
                any(mk not in ("none", "wrong", "right") for mk in marks_):
            errs.append("scene ka dhaancha galat (3 khaane: pal / kadam ya galti / sahi)")
        else:
            for x in panels:
                if not 1 <= len(x["pics"]) <= 3:
                    errs.append("har khaane me 1-3 chitra")
                for p_ in x["pics"]:
                    if p_["pic"] not in STORY_ICONS:
                        errs.append(f"chitra '{p_['pic']}' list me nahi")
                    if len(p_["label"].split()) > 3:
                        errs.append("label 3 shabd se lamba")
                    if re.search(r"[A-Za-z]{3,}", p_["label"]):
                        errs.append("label me angrezi")
            sig = [tuple((p_["pic"], p_["label"]) for p_ in x["pics"]) for x in panels]
            if sig[1] == sig[2]:
                errs.append("khaana 2 aur khaana 3 ke chitra+label bilkul ek jaise - galti aur sahi alag dikhao")
            labels_ = " ".join(p_["label"] for x in panels for p_ in x["pics"])
            caps = caps + [labels_]                     # labels ki sankhya bhi source se milegi (neeche)
    elif kit == "address":
        cfg = {k: str(res.get(k) or "").strip().lower() for k in ("line", "wrong", "right")}
        caps = [" ".join(str(c or "").split()) for c in (res.get("caps") or [])][:3]
        if cfg["line"] not in ADDR_LINES or cfg["wrong"] not in ADDR_WRONG or cfg["right"] not in ADDR_RIGHT:
            errs.append("address kit ke bahar ka shabd")
        if cfg["wrong"] == "missing" and cfg["right"] not in ("present", "block_caps", "block_caps_underline"):
            errs.append("'missing' ka sahi roop 'present'/'block_caps' hi ho sakta hai")
        if cfg["wrong"] != "missing" and cfg["right"] == "present":
            errs.append("'present' sirf 'missing' ke saath")
        if cfg["line"] == "pin" and cfg["right"] in ("block_caps", "block_caps_underline"):
            errs.append("PIN ank hain - 'block_caps' nahi; 'clear'/'present' lo")
        if cfg["wrong"] == "unclear" and cfg["right"] == "present":
            errs.append("'unclear' ka sahi roop 'clear'/'block_caps' hai")
    elif kit == "article_mark":
        cfg = {k: str(res.get(k) or "").strip().lower() for k in ("object", "item", "wrong_place", "right")}
        caps = [" ".join(str(c or "").split()) for c in (res.get("caps") or [])][:3]
        if cfg["object"] not in CHITRA_OBJECTS or cfg["item"] not in CHITRA_ITEMS or \
                cfg["wrong_place"] not in CHITRA_PLACES or cfg["right"] not in CHITRA_RIGHT or \
                cfg["right"] == cfg["wrong_place"]:
            errs.append("kit ke bahar ka shabd")
        if "back" in (cfg["wrong_place"], cfg["right"]) and cfg["object"] != "envelope":
            errs.append("'back' sirf lifaafe ka ban sakta hai")
    else:
        raw = res.get("steps") if isinstance(res.get("steps"), list) else []
        steps = []
        for x in raw[:3]:
            if not isinstance(x, dict):
                continue
            obj = str(x.get("object") or x.get("icon") or "").strip().lower()
            if obj == "letter":
                obj = "envelope"
            its = []
            for it in (x.get("items") if isinstance(x.get("items"), list) else []):
                if isinstance(it, dict):
                    try:
                        cnt = int(it.get("count") or 1)
                    except (TypeError, ValueError):
                        cnt = 0
                    its.append({"item": str(it.get("item") or "").strip().lower(),
                                "place": str(it.get("place") or "center").strip().lower(), "count": cnt})
            steps.append({"object": obj, "items": its, "text": " ".join(str(x.get("text") or "").split()),
                          "mark": str(x.get("mark") or "none").strip().lower()})
        cfg = {"steps": steps}
        caps = [x["text"] for x in steps]
        marks_ = [x["mark"] for x in steps]
        if len(steps) != 3 or any(x["object"] not in STORY_ICONS + STORY_ARTICLES for x in steps) or \
                any(mk not in ("none", "wrong", "right") for mk in marks_) or marks_[0] != "none" or \
                marks_[2] != "right" or marks_[1] == "right":
            errs.append("kahani ka dhaancha galat (3 khaane: pal / kadam ya galti / sahi; object list se)")
        else:
            for x in steps:
                for it in x["items"]:
                    if x["object"] not in STORY_ARTICLES:
                        errs.append("item sirf lifaafa/postcard/parcel pe lag sakta hai")
                    elif it["item"] not in STORY_ITEMS or it["place"] not in STORY_PLACES or not 1 <= it["count"] <= 4:
                        errs.append("item/jagah/ginti list ke bahar")
                    elif it["place"] == "back" and x["object"] != "envelope":
                        errs.append("'back' sirf lifaafe ka")
                if len(x["items"]) > 3:
                    errs.append("ek khaane me 3 se zyada item")
            if not any(x["items"] for x in steps) and not any(x["object"] not in STORY_ARTICLES for x in steps) \
                    and len({x["object"] for x in steps}) < 2:
                errs.append("chitron me koi farak nahi (sirf khaali lifaafe) - items se galat/sahi dikhao")
            sig = [(x["object"], tuple(sorted((i["item"], i["place"], i["count"]) for i in x["items"]))) for x in steps]
            if sig[1] == sig[2]:            # sirf khaana 2 (galti/kadam) aur 3 (sahi) alag hone chahiye
                errs.append("khaana 2 aur khaana 3 ke chitra bilkul ek jaise - galti aur sahi tareeka chitra me alag "
                            "dikhao (item, ginti, jagah ya cheez badlo). Khaana 1 aur 3 ek jaise ho sakte hain.")
            if not any(x["object"] in STORY_ARTICLES for x in steps) and \
                    any(w in (part.get("fact", "") + part.get("question", "")) for w in
                        ("लिफाफ", "पार्सल", "पोस्टकार्ड", "डाक वस्तु", "डाक लेख", "पत्र")):
                errs.append("niyam daak vastu ka hai - kam se kam ek khaane me lifaafa/parcel/postcard ka chitra")
        # dohraav rok: khaana sawal ya kisi option ko hi dohra raha ho to kahani nayi samajh nahi deti
        corr_ = (part.get("correct") or "a").lower()
        for x in steps:
            if trap_repeats_fact(x["text"], part.get("question", "")) and \
                    len(_content_words(x["text"]) & _content_words(part.get("question", ""))) >= 3:
                errs.append(f"khaana sawal dohra raha: '{x['text']}' - kaam ka drishya likho, sawal nahi")
                break
            for k_ in "abcd":
                o_ = _squash_hi(part.get(k_, ""))
                if o_ and len(o_) > 4 and o_ in _squash_hi(x["text"]) and k_ != corr_:
                    errs.append(f"khaana option dohra raha: '{x['text']}' - galti ko kaam ke roop me dikhao")
                    break
    labels_extra = caps[3:] if kit == "scene" else []
    caps = caps[:3]
    long_ = [i + 1 for i, c in enumerate(caps) if c and len(c.split()) > 12]
    if len(caps) != 3 or any(not c for c in caps):
        errs.append("3 caption chahiye")
    elif long_:
        errs.append(f"caption {long_} 12 shabd se lamba - chhota karo")
    if any(re.search(r"[A-Za-z]{3,}", c) for c in caps):
        errs.append("caption me angrezi")
    allowed = number_groups(truth_src(part), "en") + number_groups(truth_src(part), "hi") + \
        number_groups(part.get("fact", ""), "hi")
    for c in caps + labels_extra:
        for g in number_groups(c, "hi"):
            if not any(g & t_ for t_ in allowed):
                errs.append("caption/label me aisi sankhya jo source me nahi")
    if errs:
        return None, errs
    cfg["caps"] = caps
    cfg["kit"] = kit
    aud = as_dict(_llm_json(CHITRA_AUDIT_PROMPT.format(fact=part.get("fact", ""), src=truth_src(part),
                                                       story=chitra_story_en(cfg))))
    probs = aud.get("problems") or []
    probs = [probs] if isinstance(probs, str) else probs
    probs = [str(p_) for p_ in probs if str(p_).strip() and str(p_).strip().lower() not in ("none", "no", "[]")]
    ok = aud.get("ok")
    ok = (ok is True or (isinstance(ok, str) and ok.strip().lower() in ("true", "yes"))) and not probs
    if not ok:
        return None, ["examiner: " + ("; ".join(probs) or "ok nahi")]
    return cfg, []


def ensure_chitra(plan, part):
    """
    Chitra storyboard - ek baar banke save. Har run me CHITRA_TRIES_PER_RUN mauke (pichhli galti batake),
    CHITRA_MAX_RUNS runs tak. Examiner-pass hi lagta hai - galat chitra kabhi nahi.
    """
    cv_ = part.get("chitra_v") or {}
    if not isinstance(cv_, dict):
        cv_ = {}
    if int(cv_.get("v", 1)) < CHITRA_SCHEMA and not (cv_.get("ok") and int(cv_.get("v", 1)) >= CHITRA_OK_MIN):
        cv_ = {}                                       # purana chitra / purani fail-ginti -> naye se
    if not USE_ICON_KITS and cv_.get("kit") in ("story", "scene"):
        cv_ = {}                                       # save hua kamzor icon-chitra -> naya drawing
    if cv_.get("ok") and not chitra_ready(cv_):
        cv_ = {}                                       # purani kit (drawing/icon) ya chitra-file gayab -> naya
    if USE_PHOTO and not cv_.get("ok") and cv_.get("kit_try") != "photo":
        cv_ = {}                                       # purani kit ki fail-ginti photo pe laagu nahi
    if cv_.get("ok"):
        return True
    runs = int(cv_.get("tries", 0))
    if runs >= CHITRA_MAX_RUNS:
        return False
    feedback, errs = "", []
    if USE_PHOTO:
        for _ in range(PHOTO_TRIES):
            try:
                cfg, errs = _photo_attempt(part, feedback)
            except ProviderBusy as exc:
                print("  Chitra (photo): busy -", str(exc)[:140], "- ye run ginti me nahi, agli run me dobara")
                return False
            except Exception as exc:
                cfg, errs = None, [f"photo nahi bana: {str(exc)[:160]}"]
            if cfg:
                part["chitra_v"] = dict(cfg, ok=True, v=CHITRA_SCHEMA)
                save_plan(plan)
                print("  Chitra taiyar (photo, aankh + andhi-jaanch + examiner PASS):", " | ".join(cfg["caps"]))
                return True
            feedback = "; ".join(errs)[:900]
            print("  CHITRA (photo) FAIL WAJAH:", feedback[:400])
        part["chitra_v"] = {"tries": runs + 1, "last_err": feedback[:300], "v": CHITRA_SCHEMA, "kit_try": "photo"}
        save_plan(plan)
        return False
    draw_busy = False
    if USE_DRAW and GEMINI_API_KEY:
        for _ in range(DRAW_TRIES):
            try:
                cfg, errs, _x = _draw_attempt(part, feedback)
            except ProviderBusy:
                print("  Chitra (draw): Gemini busy - aaj lifaafa/pata-chitra se koshish")
                draw_busy = True
                break
            except Exception as exc:
                cfg, errs = None, [f"draw nahi bana: {str(exc)[:100]}"]
            if cfg:
                part["chitra_v"] = dict(cfg, ok=True, v=CHITRA_SCHEMA)
                save_plan(plan)
                print("  Chitra taiyar (draw, aankh-jaanch + examiner PASS):", " | ".join(cfg["caps"]))
                return True
            feedback = "; ".join(errs)[:900]
            print("  CHITRA (draw) FAIL WAJAH:", feedback[:400])
        feedback = ""
    for _ in range(CHITRA_TRIES_PER_RUN):
        try:
            cfg, errs = _chitra_attempt(part, feedback)
        except ProviderBusy:
            print("  Chitra: AI busy - agle run me dobara")
            return False                                   # busy run nahi ginte
        except Exception as exc:
            cfg, errs = None, [f"nahi bana: {str(exc)[:100]}"]
        if cfg:
            part["chitra_v"] = dict(cfg, ok=True, v=CHITRA_SCHEMA)
            save_plan(plan)
            print("  Chitra taiyar (examiner PASS):", cfg["kit"], " | ".join(cfg["caps"]))
            return True
        feedback = "; ".join(errs)[:400]
        print("  Chitra koshish fail:", feedback[:160])
    if draw_busy:                                       # busy din ki ginti nahi (drawing ka mauka mila hi nahi)
        print("  Chitra: aaj Gemini busy tha - ye din ginti me nahi, agli run me drawing dobara")
        return False
    part["chitra_v"] = {"tries": runs + 1, "last_err": feedback[:200], "v": CHITRA_SCHEMA}
    save_plan(plan)
    return False


def ensure_chitra_ahead(plan, part, n=2):
    """Aage aane wale parts ka chitra PEHLE se (kisi din AI fail/busy ho to publish se pehle aur mauke milen)."""
    if not (HOOK_MODE == "pro" and SHOW_CHITRA):
        return
    ahead = [p_ for p_ in usable_parts(plan) if not p_.get("published") and p_ is not part
             and not chitra_ready(p_.get("chitra_v"))][:n]
    for p_ in ahead:
        try:
            ensure_chitra(plan, p_)
        except Exception as exc:
            print("  Aage ka chitra nahi bana:", str(exc)[:120])


def ensure_beats(plan, part):
    """Niyam ke yaad-tukde (✓/✗/•) - ek baar banke save; examiner fail -> tukde nahi (purana design)."""
    if not SHOW_BEATS:
        return False
    bt = part.get("beats") or {}
    if isinstance(bt, list):
        bt = {}
    if bt.get("ok"):
        return True
    if int(bt.get("tries", 0)) == 9:
        bt = {}
    if int(bt.get("tries", 0)) >= 2:
        return False
    try:
        res = as_dict(_llm_json(BEATS_PROMPT.format(fact=part.get("fact", ""), src=truth_src(part))),
                      "beats")
        beats = res.get("beats") if isinstance(res.get("beats"), list) else []
        beats = [{"text": " ".join(str(b.get("text") or "").split()), "mark": str(b.get("mark") or "").lower().strip()}
                 for b in beats if isinstance(b, dict)]
        errs = beats_errors(part, beats)
        if not errs:
            shown = "; ".join(f"{BEAT_MARKS[b['mark']]} {b['text']}" for b in beats)
            aud = as_dict(_llm_json(BEATS_AUDIT_PROMPT.format(fact=part.get("fact", ""),
                                                             src=truth_src(part), beats=shown)))
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


# 1985 ki Guide ke wo tathya jo ab badal chuke hain (coaching notes se pakka). Inpar tika part = FAIL,
# AI examiner pe bharosa kiye bina (taala).
OUTDATED_SOURCES = [
    (r"following holidays are observed|holidays on 5 other days|5 other days which vary",
     "OUTDATED: chhuttiyan ab kul 17 (14 anivarya + 3 circle-wise); Guide (1985) ki 11 + 5 wali suchi purani"),
    (r"sixteen postal circles|divided into sixteen",
     "OUTDATED: postal circles ab 23 hain; Guide (1985) me 16 likha hai"),
]


def outdated_errors(part):
    if part.get("basis") == "notes":          # notes (naya niyam) se bana part - purani line sirf sandarbh
        return []
    src = " ".join(str(part.get(k, "")) for k in ("source_quote", "trap_quote")).lower()
    src = " ".join(src.split())
    return [msg for pat, msg in OUTDATED_SOURCES if re.search(pat, src)]


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

    errs += outdated_errors(part)
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
    if r.status_code in (413, 429, 503, 500, 404):     # 413 = request badi (free seema) -> busy jaisa
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
3. question: exam-style Hindi question answerable only from the quote. Max 16 words. If the source uses a
   technical term, write its plain meaning so a GDS employee understands it (e.g. "embossed postal
   stationery" -> "टिकट छपे लिफाफे/पोस्टकार्ड"), without changing the meaning.
4. a, b, c, d: 2-5 words each, Hindi only, NO English in brackets. Exactly one correct (matches the quote).
   The 3 wrong ones must be plausible but DEFINITELY wrong per the clause (never partly true).
5. correct: only the letter, e.g. "B".
6. trap: max 14 words, must NOT repeat the fact - add ONE NEW exam-useful point (exception, limit, authority,
   opposite case, or why the tempting wrong option is wrong). Write it as WRONG belief +
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


# ==================== NAYA DAUR (round): kisi clause se dobara, naye format me ====================
# RESTART_ROUND badhao + RESTART_FROM_CLAUSE likho -> agli run clause RESTART_FROM_CLAUSE part 1 se shuru.
# Us clause aur aage ke purane daur me publish hue parts "baaki" maane jaate hain (dobara naye format me banenge);
# unka purana record "published_prev" me rehta hai (mitaya nahi jaata). Pichhle clauses nahi chhede jaate.
RESTART_ROUND = int(os.getenv("RESTART_ROUND", "12"))
RESTART_FROM_CLAUSE = int(os.getenv("RESTART_FROM_CLAUSE", "17"))


def _apply_round(plan):
    if not plan or int(plan.get("clause_no", 0)) < RESTART_FROM_CLAUSE:
        return plan
    for p_ in plan.get("parts", []):
        if p_.get("published") and int(p_.get("published_round", 1)) < RESTART_ROUND:
            p_["published_prev"] = p_.pop("published")        # purana record rakho
            p_["published_round_prev"] = int(p_.pop("published_round", 1))
    return plan


def load_plan(num):
    p = plan_path(num)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return _apply_round(json.load(f))


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
    if SIMPLE_MODE:
        return simple_build_plan(num, clauses)
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


# ==================== AASAAN SYSTEM (SIMPLE_MODE) ====================
SIMPLE_PLAN_PROMPT = """You make short Hindi MCQ reels for India Post departmental exams (GDS to MTS / Postman / PA).
Below: one clause of the official PO Guide Part I (English, corrected only up to 1985) and the candidate's
CURRENT coaching NOTES for the same topic (Hindi; PDF text may have broken letters).
If the NOTES and the Guide DIFFER on any fact, the NOTES are correct (current rule) - use the notes.

GUIDE CLAUSE {num}:
<<<
{guide}
>>>
NOTES (current):
<<<
{notes}
>>>

Make up to {max_parts} parts, one exam-relevant rule each (short clause -> 1-2 parts). Skip dealer/firm names,
addresses and pure lists of old names. For EACH part give:
- basis: "guide" or "notes" (notes if the fact comes from / differs per the notes)
- source_quote: copied EXACTLY word for word from the Guide (English) if basis=guide, or the supporting
  words copied exactly from the NOTES if basis=notes. It alone must support the fact.
- question: exam-style Hindi, SHORT and direct - best 8-12 words, never more than 14. Technical terms with their plain meaning (e.g. embossed postal
  stationery -> टिकट छपे लिफाफे/पोस्टकार्ड), meaning unchanged.
- a, b, c, d: 2-5 words Hindi each, no English in brackets. Exactly one correct; wrong ones clearly wrong.
- correct: only the letter.
- fact: the rule in Hindi, max 16 words, keeps every number/condition/exception/authority.
- trap: EXAM TRAP = ONE NEW exam-useful point (max 11 words) that the fact line does NOT already say, taken from
  the SAME source (source_quote, or another sentence of the same clause/notes copied verbatim into trap_quote).
  Pick the most useful of: the exception / "only" case, the exact limit or number, who decides / which office,
  the opposite case, or WHY the most tempting wrong option is wrong (name that option). Form: "X नहीं, Y" or
  "X गलत, क्योंकि Y". Max 14 words. Must NOT reuse the fact's words or just restate the rule in reverse.
  If the source truly has nothing more, name the tempting wrong option and why it is wrong per the source.
- trap_quote: the extra source sentence used by trap, copied exactly (or "" if it only uses source_quote).
- yaad: memory formula, max 8 words (= and + allowed).
- hook: IMPORTANT: ONLY use a counter/customer scene if the rule really is about what the postal employee does. If the rule is about the public/sender, ask it plainly. Never change WHO does what, never add a situation the question does not have, keep the question's key words, never hint which option is correct.
   the SAME question set in the viewer's DAILY POSTAL WORK in plain spoken words, so a GDS / postman / counter
  clerk instantly feels "this is my work" (counter, customer, parcel, registry, mail bag, beat, BO).
  Priority: (1) exactly the same meaning as the question - same subject and condition, the correct option still the
  correct answer; (2) daily-work connection; (3) simple words, no bookish words; (4) SHORT - best 5-8
  words, up to 12 only if the meaning needs it. Do NOT name any answer option. End with a question,
  not yes/no, answer not revealed, NO fake statistics or claims.
  Examples: "पार्सल की सुरक्षा के लिए उपयोग होने वाले मोम कपड़े को कैसे लगाना चाहिए?" ->
  "काउंटर पर पार्सल आया, मोम कपड़ा कैसे लगेगा?"; "नाजुक वस्तुओं की सुरक्षा के लिए डाकघर क्या करता है?" ->
  "ग्राहक काँच का पार्सल लाया, डाकघर क्या करेगा?"; "एम्बोस्ड स्टेशनरी पर छपे मूल्य से अधिक डाक शुल्क होने पर
  क्या करें?" -> "लिफाफे का छपा टिकट कम पड़े, तो क्या करें?"
- en: {{"question": "", "a": "", "b": "", "c": "", "d": "", "fact": ""}} simple English with official PO
  Guide terms (insured articles, V.P. articles, letter mail, Head of the Circle ...), same meaning & numbers.
- beats: 2-4 items {{"text": "max 5 Hindi words", "mark": "yes|no|key"}} restating only the fact
  (yes = allowed/true, no = NOT allowed/false, key = subject).
Standard terms: insured = बीमाकृत वस्तु, registered = पंजीकृत, V.P. = वी.पी., money order = मनीऑर्डर,
Head of the Circle = सर्किल प्रमुख, Director General = महानिदेशक. Numbers as digits. No emoji.
Return ONLY JSON: {{"title_hi": "", "parts": [ {{...}} ]}}
"""

SIMPLE_AUDIT_PROMPT = """You are the MASTER EXAMINER of India Post departmental exam reels (GDS to MTS / Postman / PA).
Two sources are given: the official PO Guide Part I (English, corrected only up to 1985) and the candidate's
CURRENT coaching NOTES (Hindi, mostly already updated; PDF text may have broken letters).

GUIDE (relevant part):
<<<
{guide}
>>>
NOTES (current):
<<<
{notes}
>>>
PARTS (JSON):
{parts}

For EACH part check:
A. RULE (core): fact correct and complete (numbers, conditions, exceptions, authority); the marked option is
   the only correct one; every wrong option is clearly wrong but TEMPTING - a wrong option that is just the
   correct answer negated ("…नहीं…") gives no challenge and is a core problem ("WEAK OPTION"); trap read
   alone teaches the correct rule, is fully supported by the source (source_quote/trap_quote), and adds a
   NEW useful point (exception, limit, authority, opposite case, or why a tempting option is wrong) - a trap
   that only repeats the fact in other words is a core problem ("TRAP REPEAT").
B. MISMATCH (core): compare the point in the Guide AND in the Notes. If the notes give a different / newer
   value or rule (a number changed, something added or separated), the NOTES version is the updated one and
   is correct. A part that uses the old Guide value is a core problem - write it as
   "OUTDATED: notes say <new value>, Guide (1985) says <old value>".
C. HINDI (core): correct, natural, grammatical Hindi with standard postal terms (insured = बीमाकृत वस्तु,
   registered = पंजीकृत, V.P. = वी.पी., Head of the Circle = सर्किल प्रमुख ...); no broken or odd words.
D. OPTIONAL fields - hook (catchy is good, but it must ask exactly the same thing with the same answer,
   KEEP the main subject and condition - e.g. "छपा टिकट कम पड़ जाए" without "लिफाफे पर" is too loose -
   a daily-postal-work framing is good only if the rule is about the employee's own work; a hook that changes
   who does what, adds a situation not in the question, or hints the correct option is a bad hook -
   be clear, not yes/no, no fake claims), en (English: same meaning, correct grammar,
   official PO Guide terms like "insured articles", "letter mail"), beats (each ✓/✗/• mark correct).
   A bad optional field is NOT a core problem - just list the field name in "drop".
Return ONLY JSON: {{"results": [{{"id": 1, "ok": true, "problems": [], "drop": []}}]}}
("ok" = true only if A, B and C are all fine; "drop" may contain "hook", "en", "beats")
"""

SIMPLE_FIX_PROMPT = """Fix these India Post exam reel parts. Each has problems listed. Keep what is correct,
fix what is wrong, following the same rules:
- If a problem says OUTDATED (or the Guide and the notes differ), rewrite the part with the UPDATED rule from
  the NOTES: set "basis": "notes" and copy the supporting words from the NOTES exactly into source_quote.
  Otherwise basis "guide" with source_quote copied exactly from the Guide (English).
- Exactly one correct option; wrong options clearly wrong; trap = EXAM TRAP = ONE NEW exam-useful point (max 11 words) that the fact line does NOT already say, taken from
  the SAME source (source_quote, or another sentence of the same clause/notes copied verbatim into trap_quote).
  Pick the most useful of: the exception / "only" case, the exact limit or number, who decides / which office,
  the opposite case, or WHY the most tempting wrong option is wrong (name that option). Form: "X नहीं, Y" or
  "X गलत, क्योंकि Y". Max 14 words. Must NOT reuse the fact's words or just restate the rule in reverse.
  If the source truly has nothing more, name the tempting wrong option and why it is wrong per the source.
- Correct, natural Hindi with standard postal terms; numbers as digits; no emoji; no English in brackets.
- Also give a fresh "hook": the same question set in the viewer's daily postal work, plain spoken words,
  best 5-8 words (max 12 only if the meaning needs it), e.g. "काउंटर पर पार्सल आया, मोम कपड़ा कैसे लगेगा?" -
  same meaning, keeps main subject and condition, names no option, not yes/no, no fake statistics,
- Wrong options must be TEMPTING (sound correct); never just the correct answer with "नहीं"/"कोई" added. "en" {{"question","a","b","c","d","fact"}}
  (simple English, official terms, same meaning and numbers) and "beats" (2-4 items {{"text","mark"}}).

GUIDE (relevant part):
<<<
{guide}
>>>
NOTES (current):
<<<
{notes}
>>>
PARTS WITH PROBLEMS (JSON):
{parts}

Return ONLY JSON: {{"parts": [ {{same fields as given, including "id"}} ]}}
"""

CORE_KEYS = ("question", "a", "b", "c", "d", "fact", "trap", "yaad")


def _src_ok(part, guide, notes):
    """Line sach me Guide ya notes me hai? (Guide me na mile par notes me mile -> basis=notes)."""
    q = part.get("source_quote", "")
    if part.get("basis") != "notes" and quote_in_source(q, guide):
        part["basis"] = "guide"
        return True
    if notes and _ngram_cover(q, notes) >= 0.55:
        part["basis"] = "notes"
        return True
    return False


def simple_core_errors(part, guide, notes):
    """Sirf zaroori rok: line asli ho, sankhya mile, ek sahi option, trap sahi."""
    errs = []
    for k in CORE_KEYS:
        if not part.get(k):
            errs.append(f"'{k}' khaali")
    if part.get("correct") not in ("A", "B", "C", "D"):
        errs.append("correct A-D nahi")
    opts = [_squash_hi(part.get(k, "")) for k in "abcd"]
    if len(set(o for o in opts if o)) < 4:
        errs.append("options ek jaise/khaali")
    long_o = [k.upper() for k in "abcd" if len(str(part.get(k, "")).split()) > MAX_OPTION_WORDS]
    if long_o:
        errs.append(f"OPTION LAMBA: {', '.join(long_o)} {MAX_OPTION_WORDS} shabd se zyada - chhota karo (arth wahi)")
    if errs:
        return errs
    if not _src_ok(part, guide, notes):
        errs.append("source_quote Guide/notes me nahi mila")
    else:
        truth = part["source_quote"] if part["basis"] == "guide" else notes
        tg = number_groups(truth, "en" if part["basis"] == "guide" else "hi")
        if part["basis"] == "guide":
            tg += number_groups(truth, "hi")
        corr = part["correct"].lower()
        for k in ("fact", corr):
            for g in number_groups(part.get(k, ""), "hi"):
                if not any(g & t for t in tg):
                    errs.append(f"'{k}' ki sankhya source me nahi")
                    break
    errs += [e for e in trap_errors(part) if not e.startswith("TRAP REPEAT")]   # dohraav: publish se pehle ensure_trap
    errs += outdated_errors(part)
    return errs


def simple_optional(part):
    """Hook / English / tukde: gadbad ho to part nahi rukta - bas wo hissa hat jaata hai."""
    hk = " ".join(str(part.get("hook") or "").split())
    if hk and not hk.endswith("?"):
        hk += "?"
    part["hook_v"] = {"ok": True, "text": hk} if (hk and not hook_errors(part, hk)) else {"tries": 0}
    en = part.get("en") if isinstance(part.get("en"), dict) else {}
    en = {k: " ".join(str(en.get(k) or "").split()) for k in ("question", "a", "b", "c", "d", "fact")}
    corr = (part.get("correct") or "a").lower()
    en_ok = all(en.values()) and not any(re.search(r"[\u0900-\u097F]", v) for v in en.values()) \
        and all(nums_match(en[k], part.get(k, "")) for k in ("fact", "question", corr))
    part["en"] = dict(en, trap="", yaad="", ok=True) if en_ok else {"tries": 0}
    bt = part.get("beats") if isinstance(part.get("beats"), list) else []
    bt = [{"text": " ".join(str(b.get("text") or "").split()), "mark": str(b.get("mark") or "").lower().strip()}
          for b in bt if isinstance(b, dict)]
    part["beats"] = {"ok": True, "items": bt} if (bt and not beats_errors(part, bt)) else {"tries": 0}


def _drop_optional(part, drop):
    for f in drop or []:
        f = str(f).lower()
        if "hook" in f:
            part["hook_v"] = {"tries": 0}
        elif f.startswith("en") or "english" in f:
            part["en"] = {"tries": 0}
        elif "beat" in f:
            part["beats"] = {"tries": 0}


def _audit_view(parts):
    out = []
    for i, p_ in enumerate(parts, 1):
        v = {k: p_.get(k) for k in ("basis", "source_quote", "question", "a", "b", "c", "d", "correct",
                                    "fact", "trap", "yaad")}
        v["id"] = i
        if (p_.get("hook_v") or {}).get("ok"):
            v["hook"] = p_["hook_v"]["text"]
        if (p_.get("en") or {}).get("ok"):
            v["en"] = {k: p_["en"].get(k) for k in ("question", "a", "b", "c", "d", "fact")}
        if (p_.get("beats") or {}).get("ok"):
            v["beats"] = [f"{BEAT_MARKS[b['mark']]} {b['text']}" for b in p_["beats"]["items"]]
        out.append(v)
    return out


def simple_audit(parts, guide, notes):
    """Ek examiner call, saare parts ek saath. Returns {index: (ok, problems, drop)}."""
    if not parts:
        return {}
    out = {}
    for c0 in range(0, len(parts), 3):                 # ek call me 3 parts (bahut badi request = Groq 413)
        chunk = parts[c0:c0 + 3]
        ctx = relevant_context(guide, {"source_quote": " ".join(p_.get("source_quote", "") for p_ in chunk)}, 5000)
        res = as_dict(_llm_json(SIMPLE_AUDIT_PROMPT.format(
            guide=ctx, notes=notes[:3000] or "(none)",
            parts=json.dumps(_audit_view(chunk), ensure_ascii=False))), "results")
        rows = res.get("results") if isinstance(res.get("results"), list) else []
        out.update(_audit_rows(rows, c0))
    return out


def _audit_rows(rows, offset):
    out = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            i = int(r.get("id")) - 1 + offset
        except (TypeError, ValueError):
            continue
        probs = r.get("problems") or []
        probs = [probs] if isinstance(probs, str) else probs
        probs = [str(x) for x in probs if str(x).strip() and str(x).strip().lower() not in ("none", "no", "[]")]
        ok = r.get("ok")
        ok = (ok is True or (isinstance(ok, str) and ok.strip().lower() in ("true", "yes"))) and not probs
        out[i] = (ok, probs, r.get("drop") or [])
    return out


def _simple_prepare(raw, num, guide, notes):
    part = normalize_part(raw)
    for k in ("basis",):
        part[k] = str(raw.get(k) or "guide").lower().strip()
    part["en"], part["hook"], part["beats"] = raw.get("en"), raw.get("hook"), raw.get("beats")
    part["_clause_no"] = num
    part["trap_quote"] = ""
    errs = simple_core_errors(part, guide, notes)
    simple_optional(part)
    return part, errs


def simple_process(raw_parts, num, guide, notes):
    """Code-jaanch -> (fail pe) 1 sudhaar -> 1 examiner -> (problem pe) 1 sudhaar + 1 dobara examiner."""
    parts, errs = [], []
    for rp in raw_parts:
        p_, e = _simple_prepare(rp, num, guide, notes)
        parts.append(p_)
        errs.append(e)

    def fix(idx, problems):
        if not idx:
            return
        ctx = relevant_context(guide, {"source_quote": " ".join(parts[i].get("source_quote", "") for i in idx)}, 8000)
        view = []
        for n_, i in enumerate(idx, 1):
            v = {k: parts[i].get(k) for k in ("basis", "source_quote") + CORE_KEYS + ("correct",)}
            v.update({"id": n_, "hook": (parts[i].get("hook_v") or {}).get("text", ""),
                      "problems": problems[i]})
            view.append(v)
        res = as_dict(_llm_json(SIMPLE_FIX_PROMPT.format(guide=ctx, notes=notes[:3500] or "(none)",
                                                         parts=json.dumps(view, ensure_ascii=False))), "parts")
        got = res.get("parts") if isinstance(res.get("parts"), list) else []
        for r in got:
            try:
                j = idx[int(r.get("id")) - 1]
            except (TypeError, ValueError, IndexError):
                continue
            keep_opt = {k: parts[j].get(k) for k in ("en", "beats")}
            p_, e = _simple_prepare(dict(r, en=r.get("en") or {}, beats=r.get("beats") or []), num, guide, notes)
            for k, v in keep_opt.items():            # English/tukde purane sahi the to rakho (sankhya mile tab)
                if (v or {}).get("ok") and not (p_.get(k) or {}).get("ok"):
                    p_[k] = v
            simple_optional_recheck(p_)
            parts[j], errs[j] = p_, e

    bad = [i for i, e in enumerate(errs) if e]
    try:
        fix(bad, {i: errs[i] for i in bad})                  # code-jaanch fail -> ek sudhaar
    except ProviderBusy:
        pass
    good = [i for i, e in enumerate(errs) if not e]
    try:
        verdict = simple_audit([parts[i] for i in good], guide, notes)
    except ProviderBusy:
        print("  Examiner AI busy - parts 'jaanch baaki' ke saath save, agle run me sirf jaanch")
        for i in good:
            errs[i] = [PENDING + ": examiner busy"]
        verdict = None
    if verdict is None:
        for p_, e in zip(parts, errs):
            p_["auto_check"], p_["check_errors"], p_["simple"] = not e, e, True
        return parts
    retry, probs = [], {}
    for n_, i in enumerate(good):
        ok, pr, drop = verdict.get(n_, (False, ["examiner ne jawab nahi diya"], []))
        _drop_optional(parts[i], drop)
        if not ok:
            retry.append(i)
            probs[i] = pr
            errs[i] = ["AUDIT: " + "; ".join(pr)[:300]]
    if retry:
        try:
            fix(retry, probs)                                 # examiner problem -> ek sudhaar
            again = [i for i in retry if not errs[i]]
            v2 = simple_audit([parts[i] for i in again], guide, notes)
        except ProviderBusy:
            again, v2 = [], {}
        for n_, i in enumerate(again):
            ok, pr, drop = v2.get(n_, (False, ["examiner ne jawab nahi diya"], []))
            _drop_optional(parts[i], drop)
            errs[i] = [] if ok else ["AUDIT: " + "; ".join(pr)[:300]]
    for p_, e in zip(parts, errs):
        p_["auto_check"] = not e
        p_["check_errors"] = e
        p_["simple"] = True
        web_gate(p_, num)
        if not yaad_chips(p_.get("yaad", "")):
            p_.pop("style_v", None)            # teer wali yaad nahi -> reel se pehle ek baar naya
        else:
            p_["style_v"] = STYLE_VERSION
    return parts


def web_gate(part, num):
    """Notes (naya niyam) wale pakke part pe ek baar internet jaanch; sarkari strot ulta kahe to rok."""
    if not (part.get("auto_check") and part.get("basis") == "notes") or part.get("web_verdict"):
        return
    try:
        verdict, srcs = web_verify(part)
    except Exception:
        verdict, srcs = "unknown", []
    part["web_verdict"], part["web_sources"] = verdict, srcs
    log_review(num, part, verdict, srcs)
    print(f"  Naya niyam (notes) - internet jaanch: {verdict} ({', '.join(srcs[:2]) or 'strot nahi'})")
    if verdict == "contradicted":
        part["auto_check"] = False
        part["check_errors"] = ["WEB: sarkari strot ne notes ka niyam ulta bataya - review_needed.md dekhiye"]


def simple_optional_recheck(part):
    """Sudhaar ke baad bache optional hisson ki sankhya-jaanch (niyam badla ho to English/tukde hatao)."""
    en = part.get("en") or {}
    if en.get("ok"):
        corr = (part.get("correct") or "a").lower()
        if not all(nums_match(en.get(k, ""), part.get(k, "")) for k in ("fact", "question", corr)):
            part["en"] = {"tries": 0}
    bt = part.get("beats") or {}
    if bt.get("ok") and beats_errors(part, bt.get("items")):
        part["beats"] = {"tries": 0}


def simple_build_plan(num, clauses=None):
    clauses = clauses or split_clauses(read_pdf_text())
    if num not in clauses:
        raise KeyError(f"Clause {num} PDF me nahi mila.")
    guide = clauses[num]
    notes = notes_sections().get(num, "")
    data = as_dict(_llm_json(SIMPLE_PLAN_PROMPT.format(num=num, guide=guide[:20000], notes=notes[:3500] or "(none)",
                                                       max_parts=MAX_PARTS)), "parts")
    raw = [x for x in (data.get("parts") or []) if isinstance(x, dict)][:MAX_PARTS]
    print(f"  Clause {num}: {len(raw)} parts bane (aasaan system), jaanch...")
    parts = simple_process(raw, num, guide, notes)
    seen = set()
    for p_ in parts:                                          # ek hi sawal do baar nahi
        qk = _squash_hi(p_.get("question", ""))
        if p_["auto_check"] and qk in seen:
            p_["auto_check"], p_["check_errors"] = False, ["DUPLICATE"]
        seen.add(qk)
    ok_n = sum(1 for p_ in parts if p_["auto_check"])
    os.makedirs(PLAN_DIR, exist_ok=True)
    plan = {"clause_no": num, "title_en": clause_title_en(guide),
            "title_hi": clean_text(data.get("title_hi", "")) or clause_title_en(guide),
            "source_pdf": os.path.basename(find_guide_pdf()), "approved": True, "build_tries": 1,
            "simple": True, "note": "Aasaan system. Sirf auto_check=true wale parts ki reel banti hai.",
            "parts": sorted(parts, key=lambda x: not x["auto_check"]), "clause_text_en": guide}
    save_plan(plan)
    print(f"Clause {num} plan bana: {ok_n} PASS, {len(parts) - ok_n} FAIL -> {plan_path(num)}")
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


def relevant_context(clause_text, part, limit=5000):
    """Lamba clause ho to sirf wo hisse jo is part ki line se mel khaate hain (+ shuruaat)."""
    if len(clause_text) <= limit:
        return clause_text
    paras = [p_ for p_ in re.split(r"\n\s*\n|(?<=\.)\s{2,}", clause_text) if p_.strip()]
    key = set(re.findall(r"[a-z]{4,}", (part.get("source_quote", "") + " " + part.get("trap_quote", "")).lower()))
    scored = sorted(range(len(paras)),
                    key=lambda i: -len(key & set(re.findall(r"[a-z]{4,}", paras[i].lower()))))
    keep, size = {0}, len(paras[0]) if paras else 0
    for i in scored:
        if size + len(paras[i]) > limit:
            continue
        keep.add(i)
        size += len(paras[i])
    return "\n\n".join(paras[i] for i in sorted(keep))[:limit + 800]


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
    notes = (notes_sections().get(num, "") if num else "")[:3500] or "(none)"   # Hindi bhaari hai (Groq seema)
    pj = json.dumps(view, ensure_ascii=False)
    ctx = relevant_context(clause_text, part)
    prompt = AUDIT_PROMPT.format(text=ctx, notes=notes, part=pj)

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
        adv = ADVERSARIAL_PROMPT.format(text=ctx, notes=notes, part=pj)
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
- trap max 14 words, WRONG belief + correction ("X नहीं, Y" / "X गलत, क्योंकि Y") that adds a NEW useful
  point (exception, limit, authority, opposite case, or why a tempting option is wrong), never a restated fact;
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


# ==================== NOTES = ABHI KA SACH (Guide 1985 purani ho to) ====================
NOTES_PROMPT = """The official PO Guide Part I (corrected only up to 1985) is OUTDATED on this point. The candidate's
current coaching NOTES (Hindi) hold the CURRENT rule and must be followed.
Make ONE exam MCQ reel script on this point using the CURRENT rule from the NOTES.

PROBLEM FOUND: {problems}
OLD PO GUIDE TEXT (outdated, context only):
{old}
CURRENT NOTES (Hindi; the PDF text may have broken letters):
{notes}

Rules:
- fact: the current rule in clean, correct Hindi (max 16 words), exactly as the notes say (fix broken
  letters, never change meaning or numbers).
- notes_quote: copy the supporting words from the NOTES exactly as they appear (broken letters allowed).
- guide_old: the older PO Guide value in short Hindi (e.g. "11 + 5 दिन"), or "" if not relevant.
- question: max 16 words. a, b, c, d: 2-5 words Hindi. Exactly one correct per the CURRENT rule; wrong
  options clearly wrong (the old Guide value can be a wrong option). correct: only the letter.
- trap: wrong belief + correction, max 12 words; you may use the old Guide value,
  e.g. "PO Guide (1985) का 11 + 5 पुराना है, अब 14 + 3".
- yaad: formula, max 8 words. hook: the same question in plain spoken Hindi, max 8 words, not yes/no.
- Numbers as digits. No emoji. No English in brackets.
Return ONLY JSON: {{"notes_quote": "", "guide_old": "", "hook": "", "question": "", "a": "", "b": "", "c": "",
"d": "", "correct": "", "fact": "", "trap": "", "yaad": ""}}
"""

NOTES_AUDIT_PROMPT = """You are a strict examiner. The CURRENT rule comes from these coaching NOTES (the 1985 PO Guide
is outdated on this point). Check the script against the NOTES only.
CURRENT NOTES (Hindi; may have broken letters): {notes}
OLD PO GUIDE (outdated, context): {old}
SCRIPT (JSON): {part}
ok = true only if: the fact matches the notes exactly (numbers, conditions); exactly one option is correct
per the notes and it is the marked answer; wrong options are clearly wrong; trap (read alone) teaches the
current rule; nothing invented. Return ONLY JSON: {{"ok": true/false, "problems": ["..."]}}
"""

WEB_VERIFY_PROMPT = """Use Google Search to check whether this rule of India Post / Department of Posts (India) is
correct TODAY: "{fact}"
(The 1985 PO Guide said instead: "{old}".)
Prefer official sources: indiapost.gov.in, dopt.gov.in, pib.gov.in and other .gov.in / .nic.in sites.
Reply ONLY with JSON: {{"verdict": "confirmed" | "contradicted" | "unknown", "current_rule": "...", "why": "..."}}
Use "contradicted" only if an official or clearly reliable current source says something different.
"""


def is_notes_conflict(errs):
    return any("OUTDATED" in str(e) for e in (errs or []))


def _ngram_cover(quote, text, n=3):
    q = re.sub(r"\s+", "", quote or "")
    t = re.sub(r"\s+", "", text or "")
    grams = {q[i:i + n] for i in range(max(0, len(q) - n + 1))}
    if not grams:
        return 0.0
    return sum(1 for g in grams if g in t) / len(grams)


def truth_src(part):
    """English/hook/tukde ke liye 'sach': notes-part ho to naya niyam, warna Guide ki line."""
    if part.get("basis") == "notes":
        return (f"CURRENT RULE (updated, follow this): {part.get('fact', '')}. "
                f"Older PO Guide text (outdated): {part.get('source_quote', '')[:300]}")
    return part.get("source_quote", "")


def web_verify(part):
    """
    5% wali jaanch: Gemini + Google Search. 'confirmed' tabhi jab koi sarkari (.gov.in/.nic.in) strot ho.
    Returns (verdict, [sources]). Kuch na chale -> ('unknown', []).
    """
    if not GEMINI_API_KEY:
        return "unknown", []
    prompt = WEB_VERIFY_PROMPT.format(fact=part.get("fact", ""),
                                      old=(part.get("guide_old") or part.get("source_quote", ""))[:300])
    body = {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}
    for model in gemini_candidates()[:4]:
        if model in _BUSY:
            continue
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                              params={"key": GEMINI_API_KEY.strip()}, json=body, timeout=180)
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        try:
            js = r.json()
            cand = js["candidates"][0]
            text = "".join(p_.get("text", "") for p_ in cand["content"]["parts"] if not p_.get("thought"))
            res = as_dict(_parse_json(text))
            chunks = (cand.get("groundingMetadata") or {}).get("groundingChunks") or []
            srcs = [((c.get("web") or {}).get("title") or (c.get("web") or {}).get("uri") or "") for c in chunks]
            srcs = [x for x in srcs if x][:6]
        except Exception:
            continue
        verdict = str(res.get("verdict", "unknown")).lower().strip()
        official = any(re.search(r"(gov\.in|nic\.in|indiapost)", x, re.I) for x in srcs)
        if verdict == "confirmed" and not official:
            verdict = "unknown"                      # sarkari strot bina 'pakka' nahi
        if verdict not in ("confirmed", "contradicted", "unknown"):
            verdict = "unknown"
        return verdict, srcs
    return "unknown", []


def log_review(num, part, verdict, srcs, note=""):
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        path = os.path.join(OUTPUT_DIR, "review_needed.md")
        new = not os.path.exists(path)
        import datetime
        with open(path, "a", encoding="utf-8") as f:
            if new:
                f.write("# Jaanch ke liye (notes vs PO Guide 1985)\n\n"
                        "Har line: Guide purana tha, notes ka niyam liya gaya. 'contradicted' = reel NAHI bani.\n\n")
            f.write(f"- {datetime.date.today().isoformat()} | Clause {num} | web: **{verdict}** | "
                    f"abhi: {part.get('fact', '')} | Guide(1985): {part.get('guide_old', '') or '-'} | "
                    f"strot: {', '.join(srcs[:3]) or '-'} {note}\n")
    except Exception as exc:
        print("  review file nahi likhi:", exc)


def notes_repair_part(part, clause_text, notes_text, num):
    """Guide purana -> notes ke niyam se naya part, code + examiner + web jaanch ke saath."""
    view = {k: part.get(k) for k in ("question", "a", "b", "c", "d", "correct", "fact", "trap", "yaad")}
    res = as_dict(_llm_json(NOTES_PROMPT.format(
        problems="; ".join(part.get("check_errors") or [])[:600],
        old=(part.get("source_quote", "") + "\n" + clause_text[:3000]),
        notes=notes_text[:6000])))
    fixed = normalize_part(dict(res, source_quote=part.get("source_quote", ""), trap_quote=""))
    fixed.update({"basis": "notes", "notes_quote": str(res.get("notes_quote") or "").strip(),
                  "guide_old": str(res.get("guide_old") or "").strip(), "_clause_no": num})
    errs = []
    need = ["question", "a", "b", "c", "d", "fact", "trap", "yaad"]
    errs += [f"NOTES: '{k}' khaali" for k in need if not fixed.get(k)]
    if fixed.get("correct") not in ("A", "B", "C", "D"):
        errs.append("NOTES: correct galat")
    if _ngram_cover(fixed["notes_quote"], notes_text) < 0.55:
        errs.append("NOTES: notes_quote notes me nahi mila")
    notes_groups = number_groups(notes_text, "hi")
    corr = (fixed.get("correct") or "a").lower()
    for k in ("fact", "yaad", corr):
        for g in number_groups(fixed.get(k, ""), "hi"):
            if not any(g & ng for ng in notes_groups):
                errs.append(f"NOTES: '{k}' ki sankhya notes me nahi")
    errs += length_errors(fixed) + trap_errors(fixed)
    if errs:
        return fixed, errs
    aud = as_dict(_llm_json(NOTES_AUDIT_PROMPT.format(
        notes=notes_text[:6000], old=part.get("source_quote", "")[:600],
        part=json.dumps({k: fixed.get(k) for k in need + ["correct"]}, ensure_ascii=False))))
    probs = aud.get("problems") or []
    probs = [probs] if isinstance(probs, str) else probs
    probs = [str(p_) for p_ in probs if str(p_).strip() and str(p_).strip().lower() not in ("none", "no", "[]")]
    ok = aud.get("ok")
    ok = (ok is True or (isinstance(ok, str) and ok.strip().lower() in ("true", "yes"))) and not probs
    if not ok:
        return fixed, ["NOTES-AUDIT: " + ("; ".join(probs) or "ok nahi")]
    verdict, srcs = web_verify(fixed)                   # bache 5% ke liye internet jaanch
    fixed.update({"web_verdict": verdict, "web_sources": srcs})
    log_review(num, fixed, verdict, srcs)
    print(f"  Internet jaanch: {verdict} ({', '.join(srcs[:2]) or 'strot nahi'})")
    if verdict == "contradicted":
        return fixed, ["WEB: sarkari/bharosemand strot ne notes ka niyam galat bataya - review_needed.md dekhiye"]
    return fixed, []


def repair_part(part, clause_text):
    """Ek chhoote part ko uski galtiyon ke saath AI ko wapas deta hai, fir poori jaanch dobara."""
    view = {k: part.get(k) for k in ("source_quote", "hook", "question", "a", "b", "c", "d", "correct",
                                     "fact", "trap", "trap_quote", "yaad")}
    fixed = _llm_json(REPAIR_PROMPT.format(
        text=relevant_context(clause_text, part, 9000), part=json.dumps(view, ensure_ascii=False),
        errors="\n".join("- " + e for e in part.get("check_errors", [])) or "- unknown"))
    fixed = as_dict(fixed, "parts")
    if "parts" in fixed and isinstance(fixed["parts"], list) and fixed["parts"]:
        fixed = fixed["parts"][0]
    fixed = normalize_part(fixed)
    fixed["_clause_no"] = part.get("_clause_no")
    return fixed, check_part(fixed, clause_text)


def simple_repair_pass(clauses, budget=2):
    """
    Aasaan sudhaar: (1) jin parts ki jaanch baaki hai -> ek examiner call me jaanch.
    (2) jis clause me ek bhi taiyar part nahi bacha -> clause dobara (2 baar tak), published parts bache rahte hain.
    """
    done = 0
    for num in sorted(n for n in clauses if load_plan(n)):
        if done >= budget:
            break
        plan = load_plan(num)
        parts = plan.get("parts", [])
        guide, notes = clauses[num], notes_sections().get(num, "")
        pend = [i for i, p_ in enumerate(parts) if not p_.get("published") and not p_.get("auto_check") and is_pending(p_)]
        try:
            if pend:
                print(f"Clause {num}: {len(pend)} parts ki baaki jaanch (ek call)...")
                for i in pend:
                    parts[i].setdefault("basis", "guide")
                    parts[i]["_clause_no"] = num
                    if not isinstance(parts[i].get("hook_v"), dict):
                        simple_optional(parts[i])
                verdict = simple_audit([parts[i] for i in pend], guide, notes)
                for n_, i in enumerate(pend):
                    ok, pr, drop = verdict.get(n_, (False, ["examiner ne jawab nahi diya"], []))
                    _drop_optional(parts[i], drop)
                    parts[i]["auto_check"] = ok
                    parts[i]["check_errors"] = [] if ok else ["AUDIT: " + "; ".join(pr)[:300]]
                    web_gate(parts[i], num)
                save_plan(plan)
                done += 1
                continue
            old_failed = [i for i, p_ in enumerate(parts) if not p_.get("published") and not p_.get("auto_check")
                          and not p_.get("simple") and not is_pending(p_)]
            if old_failed:
                print(f"Clause {num}: purane system ke {len(old_failed)} ruke parts - aasaan system se sudhaar + jaanch...")
                raw = []
                for i in old_failed:
                    rp = {k: parts[i].get(k) for k in ("source_quote", "question", "a", "b", "c", "d", "correct",
                                                        "fact", "trap", "yaad", "hook")}
                    rp["basis"] = parts[i].get("basis") or "guide"
                    raw.append(rp)
                fresh = simple_process(raw, num, guide, notes)
                for i, fp in zip(old_failed, fresh):
                    if not fp.get("auto_check") and not is_pending(fp):
                        fp["simple_rebuilds"] = 1
                    parts[i] = fp
                save_plan(plan)
                print(f"  {sum(1 for fp in fresh if fp.get('auto_check'))}/{len(fresh)} parts ab taiyar")
                done += 1
                continue
            usable = [p_ for p_ in parts if p_.get("auto_check") and not p_.get("published")]
            failed = [p_ for p_ in parts if not p_.get("auto_check") and not p_.get("published")]
            published_any = any(p_.get("published") or p_.get("published_prev") for p_ in parts)
            # sirf wo clause dobara jisse ek bhi reel nahi bani (quota bachao)
            if not usable and failed and not published_any and int(plan.get("simple_rebuilds", 0)) < 2:
                print(f"Clause {num}: koi taiyar part nahi - aasaan system se dobara...")
                old_pub = [p_ for p_ in parts if p_.get("published")]
                new = simple_build_plan(num, clauses)
                pubq = {_squash_hi(p_.get("question", "")) for p_ in old_pub}
                new["parts"] = old_pub + [p_ for p_ in new["parts"] if _squash_hi(p_.get("question", "")) not in pubq]
                new["simple_rebuilds"] = int(plan.get("simple_rebuilds", 0)) + 1
                save_plan(new)
                done += 1
        except ProviderBusy:
            print("  AI busy - sudhaar agle run me")
            _RUN_FLAGS["busy"] = True
            break
        except Exception as exc:
            print(f"  Clause {num} sudhaar nahi hua:", str(exc)[:150])
    return done


def repair_pass(clauses, budget=REPAIRS_PER_RUN, pending_budget=6):
    if SIMPLE_MODE:
        return simple_repair_pass(clauses)
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
                notes_text = notes_sections().get(num, "") if is_notes_conflict(part.get("check_errors")) else ""
                if notes_text:
                    print("  Guide (1985) purana laga -> notes ke niyam se part (notes = abhi ka sach)")
                    fixed, errs = notes_repair_part(part, text, notes_text, num)
                else:
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
        # v7/v7.1 ne jo parts sirf "TRAP REPEAT" pe roke the -> wapas taiyar (trap ab publish se pehle sudharta hai)
        errs0 = p.get("check_errors") or []
        if not p.get("auto_check") and errs0 and all(str(e).startswith("TRAP REPEAT") for e in errs0):
            p["auto_check"] = True
            p["check_errors"] = []
            p["simple"] = True
            changed = True
        if p.get("auto_check") and not p.get("published"):
            if SIMPLE_MODE:
                errs = outdated_errors(p) + [e for e in trap_errors(p) if not e.startswith("TRAP REPEAT")]
                # (dohraav wala trap part nahi rokta - publish se pehle ensure_trap() naya trap banata hai)
                hv = p.get("hook_v") or {}
                if hv.get("ok") and hook_errors(p, hv.get("text", "")):
                    p["hook_v"] = {"tries": 2}                 # sawal se na juda hook -> poora sawal dikhe
                    changed = True
                if errs:
                    p["simple"] = False                        # purane-part sudhaar raaste se theek hoga
            else:
                errs = outdated_errors(p) + length_errors(p) + term_errors(p) + trap_errors(p)
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
    done = sum(1 for p in plan.get("parts", []) if p.get("published"))
    left = [p for p in good if not p.get("published")]
    total = done + len(left)
    if left:
        return left[0], done + 1, total          # number hamesha kram me (baad me sudhre part se khiske nahi)
    return None, 0, total


def highest_published_clause():
    """Jis sabse aage wale clause ka koi part publish ho chuka (plans me darj) - kram yahin se aage."""
    hi = None
    for plan in all_plans():
        if any(p.get("published") for p in plan.get("parts", [])):
            hi = plan["clause_no"] if hi is None else max(hi, plan["clause_no"])
    return hi


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
    # jo option sahi jawab ka sirf ULTA hai ("…नहीं…") wo challenge nahi deta - use peeche rakho
    def _is_negation(txt):
        neg = {"नहीं", "न", "कोई", "बिना", "नही", "मत"}
        a_ = set(re.findall(r"[\w\u0900-\u097F]+", txt)) - neg
        b_ = set(re.findall(r"[\w\u0900-\u097F]+", data["correct_text"])) - neg
        return bool(a_) and (a_ == b_ or a_ <= b_ or b_ <= a_) and a_ != set(re.findall(r"[\w\u0900-\u097F]+", data["correct_text"]))
    confusing = max(wrong, key=lambda l: (not _is_negation(dict(data["options"])[l]),
                                          _overlap(dict(data["options"])[l]), -wrong.index(l)))
    wrong = [l for l in wrong if l != confusing] + [confusing]
    data["elim_order"] = wrong
    pair = [data["correct_text"], dict(data["options"])[confusing]]
    if rng.random() < 0.5:
        pair.reverse()
    data["vs_pair"] = pair
    bt = data.get("beats") if isinstance(data.get("beats"), dict) else {}
    data["beat_items"] = ([{"text": clean_text(b["text"]), "mark": b["mark"]} for b in bt.get("items", [])]
                          if (SHOW_BEATS and bt.get("ok")) else [])
    if data["beat_items"]:
        fw = set(re.findall(r"[\u0900-\u097F]+", data.get("fact", "")))
        bw = [w for b in data["beat_items"] for w in re.findall(r"[\u0900-\u097F]+", b["text"])]
        chopped = bw and sum(1 for w in bw if w in fw) / len(bw) >= 0.75 \
            and not any(b["mark"] == "no" for b in data["beat_items"])
        if chopped:
            data["beat_items"] = []          # sirf niyam ke kate tukde the - khaali jagah behtar
    if HOOK_MODE == "pro" and not (trap_has_new_source(data) and not trap_is_weak(data)):
        data["trap"] = ""                    # nayi baat nahi -> EXAM TRAP nahi (dohraav kabhi nahi)
        data["en_trap"] = ""
    cvb = data.get("chitra_v") if isinstance(data.get("chitra_v"), dict) else {}
    if HOOK_MODE == "pro" and SHOW_CHITRA and cvb.get("ok"):
        data["beat_items"] = []              # chitra pehle hi samjha chuka - chip dohraav hote
    letter_of = {txt: l for l, txt in data["options"]}
    data["en_vs"] = [data["en_opt"].get(letter_of.get(t_, ""), "") for t_ in pair]
    q = data.get("question", "")
    hv = data.get("hook_v") if isinstance(data.get("hook_v"), dict) else {}
    hk = (hv.get("text") or "").strip() if hv.get("ok") else ""      # sirf examiner-pass chhota hook
    # chhota, bol-chaal wala sawal (3-9 shabd) pehle second me samajh aata hai; haan/na ('क्या ...')
    # wala hook A/B cards se mel nahi khaata, isliye wo nahi
    good_hook = bool(hk) and 3 <= words(hk) <= 12 and not re.match(r"^\s*क्या\s", hk)
    if HOOK_MODE == "tease":
        good_hook = False             # asli sawal hi dikhega - kabhi dobara likha hua nahi
    data["hook_short"] = good_hook
    data["hook_q"] = hk if good_hook else q
    # PRO: examiner-pass "roz ke kaam" wala hook asli sawal ke UPAR dikhta hai (sawal ki jagah nahi)
    data["scene_line"] = hk if (HOOK_MODE == "pro" and good_hook) else ""
    kv = data.get("kaam_v") if isinstance(data.get("kaam_v"), dict) else {}
    data["kaam"] = (kv.get("text") or "").strip() if kv.get("ok") else ""
    chv = data.get("chitra_v") if isinstance(data.get("chitra_v"), dict) else {}
    if not chitra_ready(chv):
        chv = {}                                    # purana / kamzor / file-gayab chitra reel me kabhi nahi
    data["chitra"] = {k: chv[k] for k in ("kit", "object", "item", "wrong_place", "right", "caps", "steps",
                                          "line", "wrong", "panels", "score")
                      if k in chv} if (chv.get("ok") and SHOW_CHITRA) else None
    if data["chitra"]:
        data["chitra"].setdefault("kit", "article_mark")
        ch_ = data["chitra"]
        cand = []
        if ch_["kit"] == "story":
            cand = [x.get("object") for x in ch_.get("steps") or []]
        elif ch_["kit"] == "scene":
            cand = [p_["pic"] for x in ch_.get("panels") or [] for p_ in x.get("pics") or []]
        cand = [{"envelope": "letter"}.get(c, c) for c in cand if c]
        cand = [c for c in cand if c not in ("customer", "officer", "postman", "tick_box", "cross_box", "counter")]
        if cand:
            data["icon"] = cand[0]                     # hook ka chitra = niyam ki asli cheez
    data["icon"] = next((ic for ic in (pick_icon(str(data.get(k) or "")) for k in ("title", "question", "fact"))
                         if ic != "office"), "office")
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
    hq_ = data.get("hook_q") or data["question"]
    short_opts = all(len(x.split()) <= 3 for x in data["vs_pair"])
    if HOOK_MODE == "tease":
        # pehle 2 sec: sirf challenge + (chhote hon to) dono vikalp. Poora sawal agle scene me bola jaata hai.
        ch = data.get("challenge") or CHALLENGE_LINES[0]
        hook_segs = [("hook", ch)] + ([("vs", pair_line)] if short_opts else [])
        hook_min = HOOK_SECONDS
        q_segs = [("q", data["question"]), ("lock", "कमेंट कीजिए!")]
    else:
        say_pair = short_opts and len(hq_.split()) <= 7
        hook_segs = [("hook", hq_), ("vs", pair_line)] if say_pair else [("hook", hq_)]
        hook_min = min(3.8, max(2.4, 1.0 + sum(len(x.split()) for x in data["vs_pair"]) / READ_WPS + 0.3))
        q_segs = [("q", "सही कौन?"), ("lock", "कमेंट कीजिए!")]
    if HOOK_MODE == "pro":
        # PRO flow (~20s): VS face-off + sawal bade captions me -> 2x2 grid + 3-2-1 -> faisla (usi grid me)
        # -> niyam + band trap -> yaad. Koi scene dobara wahi cheez nahi dikhata.
        return [
            # awaaz: pehle jigyasa line (~1s), fir ASLI sawal
            # kaam wala drishya ho to awaaz sirf wahi bolti hai (sawal screen pe bada likha) -> ~2.5s bachat
            {"name": "hook", "mood": "red", "tail": 0.25,
             "min": 3.4 if data.get("scene_line") else 2.2,
             "segs": [("hk", hook_line(data))] + ([] if data.get("scene_line") else [("q", data["question"])])},
            {"name": "question", "mood": "blue", "tail": 0.0, "min": 0, "segs": [("lock", "जवाब कमेंट करो!")]},
            {"name": "verdict", "mood": "green", "tail": 0.45, "min": 2.3, "delay": 0.95,
             "segs": [("rev", f"सही जवाब, {data['correct']}!")]},
        ] + ([{"name": "chitra", "mood": "blue", "tail": 0.0, "min": 0,
               # har khaane ki line ALAG tukda: khaana dikhe -> line -> thehrav (chitra dekhne ka samay) -> agla
               # teeno khaano ki line alag tukde me: khaana dikhe -> line -> thehrav -> agla
               "segs": [("c1", data["chitra"]["caps"][0])],
               "clips": [("c2", data["chitra"]["caps"][1]), ("c3", data["chitra"]["caps"][2])]}]
             if data.get("chitra") else []) + [
            ({"name": "rule", "mood": "blue", "tail": 0.2, "min": 0,
              "segs": [("fact", data["fact"]), ("trapx", "ट्रैप:"), ("trap", data["trap"])],
              "read": [("trap", data["trap"])]} if data.get("trap") else
             {"name": "rule", "mood": "blue", "tail": 0.6, "min": 0, "segs": [("fact", data["fact"])],
              "read": [("fact", data["fact"])]}),
        ] + ([{"name": "kaam", "mood": "yellow", "min": 3.0,
               "tail": 2.0,                     # yaad-sutra + MOCK + follow ek ke baad ek (~2s)
               "segs": [("kx", "आपके काम में,"), ("kaam", data["kaam"])]}]
            if (data.get("kaam") and not data.get("chitra")) else [
            {"name": "cta", "mood": "purple", "tail": 1.0, "min": 2.8,
             "segs": [("yaad", "याद रखिए!" if data.get("chitra") else "याद रखिए, " + data["yaad_voice"] + "।")],
             "read": [("yaad", data["yaad"])]}])
    specs = [
        {"name": "hook", "mood": "red", "tail": 0.15, "min": hook_min, "segs": hook_segs},
        {"name": "question", "mood": "blue", "tail": 0.25, "min": 2.4,
         "segs": (q_segs if MERGE_COUNTDOWN
                  else [("q", "चारों में से सही कौन सा?")])},
        {"name": "countdown", "mood": "purple", "tail": 0.0,
         "min": COUNTDOWN_SECONDS * COUNTDOWN_STEP + 0.35,
         "segs": [("lock", "जवाब कमेंट कीजिए!")]},
        {"name": "hint", "mood": "yellow", "tail": 0.2, "min": 2.0,
         "segs": [("hint", (data.get("hint") or ""))], "read": [("hint", (data.get("hint") or ""))]},
        # har ✗ ke saath shabd NAHI (Gemini awaaz me 'ये नहीं' ka sahi samay pakda nahi ja sakta -> pop aur
        # awaaz alag sunai dete the). Awaaz ek baar, fir ✗ + unki awaaz ek hi tay ghadi par.
        {"name": "eliminate", "mood": "red", "tail": 0.15, "min": 1.8,
         "segs": [("x1", "ये नहीं!")],
         # har ✗ ki awaaz ALAG tukda - uski shuruaat pakki pata hoti hai, isliye theek ✗ ke pal par
         "clips": [("x2", "ये भी नहीं!"), ("left", "बचे दो!"), ("x3", "ये भी नहीं!")]},
        {"name": "reveal", "mood": "green", "tail": 0.3, "min": 1.5,
         "segs": [("rev", f"सही जवाब, {data['correct']}!")]},
        {"name": "rule", "mood": "blue", "tail": 0.2, "min": 0,
         "segs": [("fact", data["fact"]), ("trapx", "ट्रैप:"), ("trap", data["trap"])],
         "read": [("trap", data["trap"])]},
        {"name": "cta", "mood": "purple",
         "tail": 0.7 + min(1.7, 0.17 * len((data.get("teaser") or "").split())),   # bonus sawal padhne bhar
         "min": 2.6,
         "segs": [("yaad", "याद रखिए, " + data["yaad_voice"] + "।")],
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


def kin(sc, p):
    """
    Shabd-dar-shabd chamak sirf tab jab shabdon ka ASLI samay pata ho (edge-tts). Gemini awaaz me samay
    andaze se hota hai - tab poora vakya ek saath (galat sync se behtar).
    """
    if sc.get("exact_words"):
        return p
    return 1.0 if p > 0 else 0.0


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


VOICE_SPEEDUP = float(os.getenv("VOICE_SPEEDUP", "1.06"))   # 1.0 asli (Gemini thoda dheema), 1.12 tez tha; 1.06 beech - pitch wahi


def speed_voice(arr, f=VOICE_SPEEDUP):
    """Awaaz f guna tez, pitch wahi (ffmpeg atempo). Kuch gadbad ho to asli awaaz hi."""
    if arr is None or abs(f - 1.0) < 0.01 or len(arr) < SR * 0.2:
        return arr
    try:
        pcm = (np.clip(arr, -1, 1) * 32767).astype(np.int16).tobytes()
        cmd = ["ffmpeg", "-v", "error", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-",
               "-af", f"atempo={f:.3f}", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-"]
        raw = subprocess.run(cmd, input=pcm, check=True, capture_output=True).stdout
        out = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        return out if len(out) > SR * 0.1 else arr
    except Exception as exc:
        print("  Awaaz tez nahi hui (asli chalegi):", str(exc)[:100])
        return arr


def speed_voice_tuple(v, f=VOICE_SPEEDUP):
    """(audio, words, seg_starts, ...) - audio tez, aur saare samay usi hisaab se chhote (sync bana rahe)."""
    if abs(f - 1.0) < 0.01:
        return v
    arr = speed_voice(v[0], f)
    if arr is v[0]:
        return v
    words = [(a / f, b / f, w) for a, b, w in v[1]] if v[1] else v[1]
    segs = [x / f for x in v[2]] if len(v) > 2 and v[2] else (v[2] if len(v) > 2 else None)
    return (arr, words, segs) + tuple(v[3:])


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
        # sirf script (koi English instruction nahi - purane model use zor se padh dete the)
        (gen_url, {"contents": [{"parts": [{"text": script}]}],
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


def _pick_cuts(gaps, expected, total, len_w=0.15):
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
        cost[0][j] = abs(mids[j] - expected[0]) / total - len_w * min(lens[j], 1.2)
    for i in range(1, n):
        best, bk = INF, -1
        for j in range(m):
            if j - 1 >= 0 and cost[i - 1][j - 1] < best:
                best, bk = cost[i - 1][j - 1], j - 1
            if best < INF:
                cost[i][j] = best + abs(mids[j] - expected[i]) / total - len_w * min(lens[j], 1.2)
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
    chosen = _pick_cuts(gaps, expected, total, len_w=0.6)      # scene ke beech ki chuppi lambi hoti hai
    if chosen is None:
        print(f"  Gemini awaaz: scenes ke beech ruk nahi mile ({len(gaps)} chuppi, {len(expected)} chahiye)")
        return None
    edges = [0.0] + [(a + b) / 2 for a, b in chosen] + [total]
    bounds = list(zip(edges[:-1], edges[1:]))
    if not _durations_ok(bounds, weights, total):
        print("  Gemini awaaz: scenes ki lambai script se mel nahi khaati (shayad instruction bhi bol di)")
        return None
    # har scene ki bolne ki gati (sec / text) baaki scenes jaisi ho - kisi me faaltu awaaz (jaise instruction
    # zor se padhna) ya kata hua hissa ho to wo alag dikhta hai -> Swara (galat awaaz kabhi nahi)
    rates = sorted((b - a) / max(w, 1e-6) for (a, b), w in zip(bounds, weights))
    med = rates[len(rates) // 2]
    for (a, b), w, sp in zip(bounds, weights, specs):
        r = (b - a) / max(w, 1e-6)
        if r > 1.7 * med or r < 0.45 * med:
            print(f"  Gemini awaaz: '{sp['name']}' scene ki gati baaki se alag ({r / med:.1f}x) -> Swara")
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
        # (eliminate me ab ek hi line 'गलत हटाओ!' hai - ✗ tay taal par; andar ke tukdon ki zaroorat nahi)
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
    clip_list = [(i, k, t) for i, sp in enumerate(specs) for k, t in sp.get("clips", [])]

    def attach(voices, clip_arrs):
        out = [list(v) + [None] * (3 - len(v)) for v in voices]
        for (i, k, _), arr in zip(clip_list, clip_arrs):
            while len(out[i]) < 4:
                out[i].append(None)
            if out[i][3] is None:
                out[i][3] = {}
            out[i][3][k] = arr
        return [tuple(v) for v in out]

    if DRY_RUN:
        out = []
        for sp in specs:
            text = " ".join(t for _, t in sp["segs"])
            est = max(0.6, seg_weight(text) * 0.058)
            out.append((np.zeros(int(est * SR), dtype=np.float32), None, None))
        clips = [np.zeros(int(max(0.35, seg_weight(t) * 0.058) * SR), dtype=np.float32) for _, _, t in clip_list]
        return attach(out, clips)

    if USE_GEMINI_TTS and GEMINI_API_KEY:
        try:
            lines = [" ".join(t for _, t in sp["segs"]) for sp in specs] + [t for _, _, t in clip_list]
            pseudo = [{"name": "clip", "segs": [(k, t)]} for _, k, t in clip_list]
            full = gemini_tts_audio(lines)
            res = split_gemini_audio(full, list(specs) + pseudo)
            if res:
                voices, clips = res[:len(specs)], [r[0] for r in res[len(specs):]]
                voices = [speed_voice_tuple(tuple(v)) for v in voices]      # ~12% tez, sync saath
                clips = [speed_voice(c) for c in clips]
                inner = sum(1 for r in voices if r[2])
                print(f"Awaaz: Gemini TTS (ek baar me poori) - {len(voices)} scenes + {len(clips)} ✗-tukde, "
                      f"{inner} me andar ka sync mila")
                _CURRENT["used"] = "Gemini: " + (_CURRENT.get("name") or pick_gemini_voice())
                return attach(voices, clips)
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
    clips = []
    for j, (_, _, text) in enumerate(clip_list):
        path = f"_clip_{j}.mp3"
        asyncio.run(tts_save(text, path))
        clips.append(decode_raw(path, trim=True))
        os.remove(path)
    print(f"Awaaz: edge-tts ({VOICE_NAME})")
    _CURRENT["used"] = "edge-tts: " + VOICE_NAME
    return attach(voices, clips)


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
        add_at(voice_track, voice[0], sc["start"] + sc.get("lead", VOICE_LEAD))
        for k_, arr_ in (sc.get("clips") or {}).items():          # ✗-awaaz: shuruaat = ✗ ka pal
            if k_ in sc["marks"]:
                add_at(voice_track, arr_, sc["start"] + sc["marks"][k_][0])

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
        if sc["index"] > 0 and not is_seamless(name):
            add_at(buf, whoosh, max(0.0, s - 0.14), 0.9)
        if HOOK_MODE == "pro" and name == "hook":
            add_at(buf, sfx_thud(0.8), s + 0.0)                 # pehle frame pe hi dhamak
            add_at(buf, sfx_pop(0.45), s + 0.08)
            continue
        if HOOK_MODE == "pro" and name == "question":
            add_at(buf, sfx_whoosh(0.25, 0.3), s)
            c0 = sc["cd_start"]
            for k in range(COUNTDOWN_SECONDS):
                add_at(buf, sfx_tick(0.5), s + c0 + k * COUNTDOWN_STEP)
                add_at(buf, sfx_heartbeat(0.45), s + c0 + k * COUNTDOWN_STEP)
            continue
        if name == "verdict":
            add_at(buf, sfx_riser(0.9, 0.2), s)
            for xt in VERDICT_X:
                add_at(buf, sfx_buzz(0.33), s + xt)
            add_at(buf, sfx_ding(0.5), s + VERDICT_WIN)
            add_at(buf, sfx_thud(0.6), s + VERDICT_WIN)
            continue
        if name == "hook":
            add_at(buf, sfx_pop(0.5), s + 0.02)
            add_at(buf, sfx_thud(0.9), s + sc["stamp_t"])
            if HOOK_MODE == "tease":
                tk = 0.6
                while tk < sc["dur"] - 0.1:
                    add_at(buf, sfx_tick(0.28), s + tk)
                    tk += 0.5
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
            if "trapx" in mk:
                add_at(buf, sfx_buzz(0.18), s + trap_start(sc))
                add_at(buf, sfx_thud(0.8), s + trap_start(sc) + 0.05)      # second payoff ka thappa
        elif name == "chitra" and (sc["data"].get("chitra") or {}).get("kit") in ("story", "scene", "draw", "photo"):
            for i_, k_ in enumerate(("c1", "c2", "c3")):
                add_at(buf, sfx_whoosh(0.25, 0.3), s + max(0.0, mk[k_][0] - 0.3))
                ch_ = sc["data"]["chitra"]
                m_ = (ch_.get("steps") or ch_.get("panels"))[i_]["mark"]
                if m_ == "wrong":
                    add_at(buf, sfx_buzz(0.33), s + mk[k_][1] - 0.2)
                elif m_ == "right":
                    add_at(buf, sfx_ding(0.45), s + mk[k_][1] - 0.2)
        elif name == "chitra":
            tw_ = max(0.9, mk["c2"][0] - 0.35)
            tr_ = max(tw_ + 1.0, mk["c3"][0] - 0.3)
            add_at(buf, sfx_whoosh(0.3, 0.35), s + 0.02)             # lifaafa counter pe sarakta
            add_at(buf, sfx_thud(0.8), s + tw_ + 0.05)                # item dhap se chipka
            add_at(buf, sfx_buzz(0.3), s + tw_ + 0.5)
            add_at(buf, sfx_ding(0.45), s + tr_ + 0.3)
        elif name == "kaam":
            add_at(buf, sfx_ding(0.3), s + 0.05)
            add_at(buf, sfx_pop(0.3), s + mk["kaam"][1])
            add_at(buf, sfx_pop(0.45), s + mk["kaam"][1] + 0.6)          # MOCK button
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
    # chhota version-chinh (neeche kone me, Instagram caption ke neeche chhip jaata hai) - kaunsa code chala, pakka pata
    d.text((W - 40, H - 30), ENGINE_VERSION.split()[0], font=get_font(22), fill=(70, 85, 110), anchor="rm")
    hy = 150 if HOOK_MODE == "pro" else 70       # Instagram ka upar wala UI pehle 150px dhak leta hai
    d.text((60, hy), "POSTAL WALA", font=get_font(34), fill=(148, 163, 184), anchor="lm")
    chip = pill_sprite(f"Clause {data['clause_no']}  |  Part {data['part_no']}/{data['total_parts']}",
                       26, YELLOW, (40, 32, 8), ORANGE)
    place(canvas, chip, W - 130 - chip.width / 2 if HOOK_MODE == "pro" else W - 60 - chip.width / 2, hy)
    x0, x1, y = 60, W - 60, hy + 48
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((x0, y, x1, y + 10), radius=5, fill=(27, 42, 58))
    cur = x0 + (x1 - x0) * clamp(gt / total)
    d.rounded_rectangle((x0, y, max(x0 + 10, cur), y + 10), radius=5, fill=CYAN)
    place(canvas, glow_sprite(22, CYAN, 200), cur, y + 5)


def topic_chip(canvas, data, y, a=1.0):
    chip = pill_sprite(data["title"], 32, CYAN, (10, 30, 50), (40, 100, 150))
    place(canvas, chip, W / 2, y, alpha=a)


# ==================== SCENES ====================

SERIES_NAME = "POSTAL EXAM TRAP"


@lru_cache(maxsize=64)
def series_banner(ep, season=0, new=False):
    """Pehchaan: POSTAL EXAM TRAP · S2 · EP 12 (laal) + chhota GDS | MTS | POSTMAN | PA."""
    top = f"{SERIES_NAME}  ·  S{season}  ·  EP {ep}" if season and season > 1 else f"{SERIES_NAME}  ·  EP {ep}"
    sub = "GDS  |  MTS  |  POSTMAN  |  PA"
    f1, f2 = get_font(46), get_font(32)
    w = int(max(text_w(top, f1), text_w(sub, f2))) + 90
    h = 150
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, 92), radius=24, fill=RED + (255,), outline=(255, 150, 150, 255), width=3)
    d.text((w / 2, 48), top, font=f1, fill=WHITE + (255,), anchor="mm")
    d.text((w / 2, 124), sub, font=f2, fill=YELLOW + (255,), anchor="mm")
    if new:                                    # "NEW" ribbon: purane viewer ko turant dikhe ki kuch naya hai
        fn = get_font(30)
        rw = int(text_w("NEW", fn)) + 40
        im2 = Image.new("RGBA", (w + rw // 2 + 8, h + 20), (0, 0, 0, 0))
        im2.paste(im, (0, 20), im)
        d2 = ImageDraw.Draw(im2)
        d2.rounded_rectangle((w - rw // 2, 0, w + rw // 2, 44), radius=14, fill=YELLOW + (255,),
                             outline=(40, 20, 0, 255), width=3)
        d2.text((w, 23), "NEW", font=fn, fill=(40, 20, 0, 255), anchor="mm")
        return im2
    return im


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


HOOK_QWORDS = ("क्या", "कौन", "कौनसा", "कौनसी", "कौनसे", "कितने", "कितनी", "कितना", "कब", "कहाँ", "कहां",
               "किसके", "किसकी", "किसका", "किसे", "किस", "कैसे", "क्यों")


def hook_highlights(text):
    """Hook me sawal-shabd aur sankhya chamkao (nazar turant jaaye)."""
    out = []
    for w in text.split():
        core = re.sub(r"[,.!?।:()]", "", w)            # draw_kinetic jaisa hi (8:30 -> 830)
        if core in HOOK_QWORDS or re.search(r"\d", core):
            out.append(core)
    return tuple(out)


HOOK_AREA_TOP = 318        # series badge (GDS | MTS | ...) ke neeche
HOOK_AREA_BOTTOM = 640     # stamp (645-755, card ke upar wale kinare par) se pehle


@lru_cache(maxsize=64)
def hook_layout(hook_q, en_q, short):
    """
    Hook + English ko badge aur pehle card ke BEECH naap ke rakho - kabhi kisi pe na chadhe.
    Returns (hook_uchai, hook_size, english_size (0 = nahi), top_y).
    """
    area = HOOK_AREA_BOTTOM - HOOK_AREA_TOP
    sizes = [98, 90, 84, 78, 72, 66, 60, 56, 52] if short else [80, 74, 68, 62, 58, 54, 50, 46]

    def en_fit(sz):
        if not en_q:
            return 0
        _, _, ls = fit_lines_f(en_q, 900, 2, sz, sz, get_font_reg)
        return en_h(en_q, 900, sz, 2) if len(ls) <= 2 else None

    for sz in sizes:
        _, s_, ls = fit_lines(hook_q, 940, 3, sz, sz)
        if len(ls) > 3:
            continue
        hq = int(s_ * 1.34) * len(ls)
        for es in (39, 36, 33):
            eh = en_fit(es)
            if eh is None:
                continue
            total = hq + (eh + 6 if eh else 0)
            if total <= area:
                return hq, sz, (es if en_q else 0), HOOK_AREA_TOP + (area - total) / 2
    # English ke bina (agle scene me poori English aati hai)
    for sz in sizes:
        _, s_, ls = fit_lines(hook_q, 940, 3, sz, sz)
        if len(ls) > 3:
            continue
        hq = int(s_ * 1.34) * len(ls)
        if hq <= area:
            return hq, sz, 0, HOOK_AREA_TOP + (area - hq) / 2
    _, s_, ls = fit_lines(hook_q, 940, 3, sizes[-1], 40)
    hq = int(s_ * 1.34) * min(3, len(ls))
    return hq, int(s_), 0, HOOK_AREA_TOP


def scene_hook(cv, data, t, dur, m, vd, sc):
    """
    Frame 0 pe hi: kiske liye (banner) + sawal (poora, chamakta) + '4 ya 5?' do bade jawab + EXAM TRAP.
    Viewer pehle second me hi man me ek jawab chun leta hai -> jawab jaanne ke liye rukta hai.
    """
    fx = {}
    ep = data.get("episode")
    if ep:
        place(cv, series_banner(int(ep)), W / 2, 225, scale=0.92 + 0.08 * ease_out_back(prog(t, 0, 0.3)))
    else:
        place(cv, audience_banner(), W / 2, 215, scale=0.92 + 0.08 * ease_out_back(prog(t, 0, 0.3)))

    # sawal: frame 0 se poora dikhe (koi grey/chhupa shabd nahi), bolte shabd peele
    # jo sawal dikhe, wahi jiska jawab dono cards hain (pehle hook alag sawal poochta tha)
    en_q = data.get("en_question", "") if en_on("hook") else ""
    hq, hq_size, en_size, top_ = hook_layout(data["hook_q"], en_q, bool(data.get("hook_short")))
    if en_size == 0:
        en_q = ""
    yb = draw_kinetic(cv, data["hook_q"], W / 2, 0, 940, hq_size, 1.0,
                      max_lines=3, min_size=hq_size, karaoke=False, center_y=top_ + hq / 2,
                      hl_words=hook_highlights(data["hook_q"]), hl_color=YELLOW)
    if en_q:
        draw_en(cv, en_q, yb + 6, max_w=900, size=en_size, max_lines=2)

    # 'A ya B?' cards - FRAME 0 se dikhte hain (khaali pehla frame = scroll; data: purane bhare frame ka
    # 2-sec retention behtar tha). Halki slide = harkat. Chamak awaaz se nahi judi (tay taal A <-> B)
    a, b = data["vs_pair"]
    k = ease_out_back(prog(t, 0.0, 0.28))
    place(cv, glow_sprite(420, RED, 70), W / 2, 1010)
    flip = int(t / 0.6) % 2 == 0
    act_a, act_b = flip, not flip
    bump_a = 1.03 if act_a else 1.0
    bump_b = 1.03 if act_b else 1.0
    ea, eb = (data.get("en_vs") or ["", ""])[:2] if en_on("hook") else ("", "")
    ka = ease_out_back(prog(t, 0.0, 0.3))            # pehla card baayein se (frame 0 pe bhi dikhta)
    kb = ease_out_back(prog(t, 0.06, 0.3))           # doosra daayein se
    place(cv, vs_card(a, active=act_a, en=ea), W / 2 - (1 - ka) * 160, 830,
          scale=(0.92 + 0.08 * k) * bump_a, alpha=clamp(0.8 + ka))
    place(cv, vs_card(b, active=act_b, en=eb), W / 2 + (1 - kb) * 160, 1190,
          scale=(0.92 + 0.08 * k) * bump_b, alpha=clamp(0.8 + kb))
    pulse = 1 + 0.06 * math.sin(t * 9)
    place(cv, glow_sprite(90, YELLOW, 160), W / 2, 1010)
    place(cv, pill_sprite("या", 56, (25, 18, 0), YELLOW, ORANGE), W / 2, 1010, scale=pulse)

    # EXAM TRAP stamp: 0.12s pe slam (English line ho to thoda neeche, card ke kone pe)
    stamp_y = 700                         # card ke UPAR wale kinare par - na card ka text dhake, na English
    st = sc["stamp_t"]
    kk = prog(t, st, 0.16)
    if t >= st:
        place(cv, stamp_sprite(), W / 2 + 310, stamp_y, scale=(1.9 - 0.9 * ease_out_cubic(kk)) * 0.46,
              angle=-11, alpha=clamp(kk * 3))
        if t < st + 0.3:
            fx["shake"] = 12 * (1 - prog(t, st + 0.04, 0.26))
    # comment ka sawal PEHLE 1 sec me (70% log 2-5 sec me chale jaate hain - baad me poochhna bekaar)
    kc = ease_out_back(prog(t, 0.4, 0.3)) if t >= 0.4 else 0.0
    if kc > 0.01:
        place(cv, pill_sprite("आपका जवाब? कमेंट करो!", 46, (30, 20, 0), YELLOW, ORANGE),
              W / 2, 1420, scale=max(0.05, kc) * (1 + 0.04 * math.sin(t * 9)))
    return fx


def scene_hook_tease(cv, data, t, dur, m, vd, sc):
    """
    SEASON 2 hook: frame 0 pe hi challenge line + asli sawal (bilkul wahi, dobara likha nahi) + "A ya B?"
    + khaali hota timer. Aankh pehle badi peeli line aur do cards pe jaati hai; sawal chhota par poora.
    """
    fx = {}
    ep = data.get("episode")
    if ep:
        place(cv, series_banner(int(ep), SEASON, bool(data.get("new_badge"))), W / 2, 222,
              scale=0.86 + 0.06 * ease_out_back(prog(t, 0, 0.3)))
    else:
        place(cv, audience_banner(), W / 2, 215)

    # 1) challenge line - frame 0 pe poori dikhe, halki dhadkan
    ch = data.get("challenge") or CHALLENGE_LINES[0]
    pulse = 1 + 0.035 * math.sin(t * 10)
    f, s_, lines = fit_lines(ch, 960, 1, 92, 60)
    lay = Image.new("RGBA", (W, int(s_ * 1.5)), (0, 0, 0, 0))
    ImageDraw.Draw(lay).text((W / 2, lay.height / 2), " ".join(lines[0]) if lines else ch,
                             font=f, fill=YELLOW + (255,), anchor="mm")
    place(cv, lay, W / 2, 360, scale=pulse)

    # 2) asli sawal (arth wahi) - 3 line tak, card ke upar tak
    sz, qc = tease_q_layout(data["question"])
    draw_kinetic(cv, data["question"], W / 2, 0, 960, sz, 1.0, max_lines=3, min_size=40, karaoke=False,
                 line_h=1.3, center_y=qc, color=(225, 232, 242),
                 hl_words=hook_highlights(data["question"]), hl_color=YELLOW)

    # 3) "A ya B?" cards (frame 0 se)
    a, b = data["vs_pair"]
    k = 1.0
    place(cv, glow_sprite(420, RED, 70), W / 2, 1010)
    flip = int(t / 0.5) % 2 == 0
    ka = kb = 1.0                     # frame 0 = cover: dono card poore, kinare se kate nahi
    place(cv, vs_card(a, active=flip), W / 2 - (1 - ka) * 160, 830,
          scale=(0.92 + 0.08 * k) * (1.03 if flip else 1.0), alpha=clamp(0.8 + ka))
    place(cv, vs_card(b, active=not flip), W / 2 + (1 - kb) * 160, 1190,
          scale=(0.92 + 0.08 * k) * (1.0 if flip else 1.03), alpha=clamp(0.8 + kb))
    place(cv, glow_sprite(90, YELLOW, 160), W / 2, 1010)
    place(cv, pill_sprite("या", 56, (25, 18, 0), YELLOW, ORANGE), W / 2, 1010, scale=pulse)

    # EXAM TRAP stamp (pehchaan) - pehle card ke kone par
    st = sc["stamp_t"]
    kk = prog(t, st, 0.16)
    if t >= st:
        place(cv, stamp_sprite(), W / 2 + 330, 712, scale=(1.9 - 0.9 * ease_out_cubic(kk)) * 0.42,
              angle=-11, alpha=clamp(kk * 3))
        if t < st + 0.3:
            fx["shake"] = 10 * (1 - prog(t, st + 0.04, 0.26))

    # 4) khaali hota timer (jaldi jawab do) - peela se laal
    rem = clamp(1 - t / max(dur, 0.1))
    x0, x1, y = 170, W - 170, 1352
    d = ImageDraw.Draw(cv)
    d.rounded_rectangle((x0, y - 11, x1, y + 11), radius=11, fill=(40, 30, 50))
    if rem > 0.01:
        d.rounded_rectangle((x0, y - 11, x0 + (x1 - x0) * rem, y + 11), radius=11, fill=mix(RED, YELLOW, rem))
    kc = ease_out_back(prog(t, 0.35, 0.3)) if t >= 0.35 else 0.0
    if kc > 0.01:
        place(cv, pill_sprite("अपना जवाब कमेंट करो!", 44, (30, 20, 0), YELLOW, ORANGE),
              W / 2, 1440, scale=max(0.05, kc) * (1 + 0.04 * math.sin(t * 9)))
    return fx


# ---- layout: poori screen use ho (pehle neeche 40% khaali rehta tha) ----
OPT_W, OPT_H = 940, 176
STEPPER_Y = 1552
STEPS = ["सवाल", "जवाब", "नियम", "ट्रैप", "याद"]


def current_step(name, t, m, sc=None):
    if name in ("question", "countdown", "hint") or (name == "hook" and HOOK_MODE == "pro"):
        return 0
    if name in ("eliminate", "reveal", "verdict"):
        return 1
    if name == "chitra":
        return 2
    if name == "rule":
        t0 = trap_start(sc) if sc else m["trapx"][0]
        return 3 if t >= t0 - 0.1 else 2
    if name in ("cta", "kaam"):
        return 4
    return -1


def draw_stepper(cv, step, t, no_trap=False):
    """Neeche progress: viewer ko dikhe kya ho gaya aur kya baaki hai (open loop)."""
    if step < 0:
        return
    steps_ = STEPS
    if no_trap:                                         # trap nahi to uska vaada bhi nahi
        steps_ = [x for x in STEPS if x != "ट्रैप"]
        step = min(step, 2) if step < 4 else 3
    n = len(steps_)
    x0, x1 = 90, W - 90
    xs = [x0 + (x1 - x0) * k / (n - 1) for k in range(n)]
    d = ImageDraw.Draw(cv)
    lite = HOOK_MODE == "pro"
    d.line((x0, STEPPER_Y, x1, STEPPER_Y), fill=(45, 60, 85) if lite else (60, 80, 110), width=4 if lite else 6)
    d.line((x0, STEPPER_Y, xs[step], STEPPER_Y), fill=GREEN, width=4 if lite else 6)
    f = get_font(26 if lite else 30)
    for k, x in enumerate(xs):
        if k < step:
            col, r, tcol = GREEN, 16, (150, 220, 170)
        elif k == step:
            col, r, tcol = YELLOW, 22 + 3 * math.sin(t * 8), YELLOW
        else:
            col, r, tcol = (70, 90, 120), 14, (120, 135, 160)
        d.ellipse((x - r, STEPPER_Y - r, x + r, STEPPER_Y + r), fill=col)
        d.text((x, STEPPER_Y + 48), steps_[k], font=f, fill=tcol, anchor="mm")
    if step < 3 and not no_trap:
        a = 0.6 + 0.4 * math.sin(t * 5)
        d.text((W / 2, STEPPER_Y - 62), "आगे: EXAM TRAP >>", font=get_font(34),
               fill=mix(BG_BOTTOM, ORANGE, a), anchor="mm")


def opt_positions(n=4, y0=720, gap=190):
    return [y0 + i * gap for i in range(n)]


def source_label(data):
    if data.get("basis") == "notes":
        return f"PO Guide Part I  |  Clause {data['clause_no']}  |  नया नियम"
    return f"PO Guide Part I  |  Clause {data['clause_no']}"


def source_chip(cv, data, y, a=1.0):
    chip = pill_sprite(source_label(data), 32, YELLOW, (40, 32, 8), ORANGE)
    place(cv, chip, W / 2, y, alpha=a)


def draw_countdown_row(cv, t, c0, cy, fx):
    """3-2-1 ring + 'अपना जवाब लॉक कीजिए' (question scene ke neeche)."""
    tt = t - c0
    cd = COUNTDOWN_SECONDS * COUNTDOWN_STEP
    cx, r = 250, 60
    k_in = ease_out_back(prog(t, c0 - 0.25, 0.25))
    place(cv, glow_sprite(150, PURPLE, 120), cx, cy)
    d = ImageDraw.Draw(cv)
    rr = r * max(0.05, k_in)
    d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=(24, 20, 50), outline=(70, 60, 120), width=9)
    if 0 <= tt < cd:
        remain = clamp(1 - tt / cd)
        d.arc((cx - rr, cy - rr, cx + rr, cy + rr), -90, -90 + 360 * remain, fill=YELLOW, width=9)
        num = max(1, COUNTDOWN_SECONDS - int(tt / COUNTDOWN_STEP))
        frac = (tt / COUNTDOWN_STEP) - int(tt / COUNTDOWN_STEP)
        s_ = 1.35 - 0.35 * ease_out_cubic(clamp(frac * 3))
        d.text((cx, cy), str(num), font=get_font(int(70 * s_)), fill=YELLOW, anchor="mm")
        if frac < 0.08 and tt > 0.05:
            fx["shake"] = 4
    elif tt >= cd:
        place(cv, lock_sprite(76), cx, cy, scale=max(0.05, ease_out_back(prog(tt, cd, 0.3))))
    if k_in > 0.05:
        d.text((cx + r + 34, cy - 20), "अपना जवाब लॉक कीजिए!", font=get_font(40), fill=WHITE, anchor="lm")
        d.text((cx + r + 34, cy + 28), "कमेंट करें:  A / B / C / D", font=get_font(36), fill=YELLOW, anchor="lm")


def tease_q_layout(question):
    """Hook aur question scene me sawal BILKUL ek hi jagah/size par (cut ke baad bhi hile nahi)."""
    area_top, area_bot = 420, 652
    sz = 42
    for sz in (62, 58, 54, 50, 46, 42):
        _, s2, ls = fit_lines(question, 960, 3, sz, sz)
        if len(ls) <= 3 and int(s2 * 1.3) * len(ls) <= area_bot - area_top:
            break
    return sz, area_top + (area_bot - area_top) / 2


def scene_question_tease(cv, data, t, dur, m, vd, sc):
    """
    Hook ka hi agla pal: sawal apni jagah tika rehta hai (dobara nahi aata), banner upar ud jaata hai,
    'A या B' ke do card chhote hokar options ban jaate hain, baaki 2 options awaaz ke saath ek-ek karke
    aate hain -> har second kuch naya.
    """
    fx = {}
    e_out = ease_in_out(prog(t, 0.0, 0.35))
    if e_out < 1:
        ep = data.get("episode")
        if ep:
            place(cv, series_banner(int(ep), SEASON, bool(data.get("new_badge"))), W / 2, 222 - 120 * e_out,
                  scale=0.92, alpha=1 - e_out)
        ch = data.get("challenge") or CHALLENGE_LINES[0]
        f, s_, lines = fit_lines(ch, 960, 1, 92, 60)
        lay = Image.new("RGBA", (W, int(s_ * 1.5)), (0, 0, 0, 0))
        ImageDraw.Draw(lay).text((W / 2, lay.height / 2), " ".join(lines[0]) if lines else ch,
                                 font=f, fill=YELLOW + (255,), anchor="mm")
        place(cv, lay, W / 2, 360 - 60 * e_out, alpha=1 - e_out)
    k_in = ease_out_back(prog(t, 0.2, 0.3)) if t >= 0.2 else 0.0
    if k_in > 0.01:
        place(cv, pill_sprite("सवाल", 40, WHITE, (37, 60, 140), BLUE), W / 2, 225, scale=max(0.05, k_in))
        source_chip(cv, data, 318, a=clamp(k_in))

    sz, qc = tease_q_layout(data["question"])
    yb = draw_kinetic(cv, data["question"], W / 2, 0, 960, sz, 1.0, max_lines=3, min_size=40, karaoke=False,
                      line_h=1.3, center_y=qc, color=mix((225, 232, 242), WHITE, e_out),
                      hl_words=hook_highlights(data["question"]), hl_color=YELLOW)
    oh, gap = 132, 146
    en_q = data.get("en_question", "") if en_on("question") else ""
    y0 = max(760, yb + 24 + oh / 2)
    if en_q:
        eh = en_h(en_q, 940, 32, 2)
        if yb + 6 + eh + 22 + oh / 2 <= 830:
            draw_en(cv, en_q, yb + 6, max_w=940, size=32, max_lines=2, alpha=clamp(k_in))
            y0 = max(y0, yb + 6 + eh + 22 + oh / 2)
    if y0 + 3 * gap + oh / 2 > 1318:
        gap, oh = 138, 124
        y0 = min(y0, 1318 - 3 * gap - oh / 2)
    ys = [y0 + i * gap for i in range(4)]

    c0 = sc.get("cd_start", 99)
    cd = COUNTDOWN_SECONDS * COUNTDOWN_STEP
    scan = min(3, int((t - c0) / (cd / 4))) if c0 <= t < c0 + cd else -1
    pair = data.get("vs_pair") or []
    hook_y = {pair[0]: 830, pair[1]: 1190} if len(pair) == 2 else {}
    morph = ease_in_out(prog(t, 0.05, 0.4))
    for i, (l, txt) in enumerate(data["options"]):
        eo = (data.get("en_opt", {}).get(l, "") if en_on("options") else "")
        active = i == scan
        if txt in hook_y:                          # hook ka card -> option (koi cut nahi)
            y = hook_y[txt] + (ys[i] - hook_y[txt]) * morph
            if morph < 1:
                place(cv, vs_card(txt), W / 2, y, scale=1 - 0.3 * morph, alpha=1 - morph)
            place(cv, option_sprite(l, txt, OPT_W, oh, "active" if active else "normal", eo), W / 2, y,
                  alpha=clamp(morph * 1.4), scale=(1.04 if active else 1.0))
            continue
        s0 = sc["opt_t"][i]
        k = prog(t, s0, 0.3)
        if k <= 0:
            place(cv, option_sprite(l, "?", OPT_W, oh, "normal"), W / 2, ys[i], alpha=0.18)   # jagah khaali: kya aayega?
            continue
        e = ease_out_back(k)
        just = s0 <= t < s0 + 0.4
        place(cv, option_sprite(l, txt, OPT_W, oh, "active" if (active or just) else "normal", eo),
              W / 2 + (1 - e) * 500, ys[i], alpha=clamp(k * 2), scale=(1.04 if (active or just) else 1.0))
    if t >= c0 - 0.25:
        draw_countdown_row(cv, t, c0, 1395, fx)
    return fx



# ==================== PRO FLOW (editor-style) ====================
# Siddhant: har pal screen pe EK hi cheez padhne ko ho; har 0.5-1s kuch naya aaye; scene ek-doosre me
# behte hain (grid wahi rehti hai), sirf bade badlaav pe whip transition. Sab kuch Instagram ke safe zone
# (upar ~250px aur neeche ~350px UI se dhakte hain) ke andar.

VERDICT_X = (0.12, 0.36, 0.60)       # ✗ girne ke pal (verdict scene)
VERDICT_WIN = 0.95                   # sahi jawab ka pal
TILE_W, TILE_H = 450, 280
GRID_X = (290, 790)                  # daayein kinare pe Instagram ke like/comment button - usse door
GRID_Y = (810, 1110)
VS_Y = 880
CAP_Y = 1250                         # caption zone (hook)


def is_seamless(name):
    """Ye scene pichhle se bina cut ke bahta hai (grid wahi rehti hai)."""
    if HOOK_MODE == "pro":
        return name in ("question", "verdict")
    return HOOK_MODE == "tease" and name == "question"


def grid_pos(i):
    return GRID_X[i % 2], GRID_Y[i // 2]


@lru_cache(maxsize=96)
def tile_sprite(letter, text, en, state, w=TILE_W, h=TILE_H):
    styles = {
        "normal": ((22, 42, 72), (70, 110, 160), 4, CYAN, WHITE),
        "active": ((28, 58, 96), CYAN, 7, CYAN, WHITE),
        "vs": ((26, 48, 84), (110, 150, 205), 5, YELLOW, WHITE),
        "wrong": ((40, 18, 26), RED, 5, RED, MUTED),
        "correct": ((14, 60, 36), GREEN, 8, GREEN, WHITE),
        "ghost": ((18, 30, 50), (45, 62, 90), 3, (70, 90, 120), (90, 105, 130)),
    }
    fill, outline, width, badge, tcol = styles[state]
    im = card_sprite(w, h, fill, outline, width, 34).copy()
    d = ImageDraw.Draw(im)
    pad = 30
    br = 30
    bx, by = pad + 22 + br, pad + 22 + br
    d.ellipse((bx - br, by - br, bx + br, by + br), fill=badge + (255,))
    d.text((bx, by), letter, font=get_font(36), fill=(8, 16, 30, 255), anchor="mm")
    maxw = w - 120                    # beech ke 'या' badge se text na takraye
    f, s_, lines = fit_lines(text, maxw, 2, 62, 34)
    lines = lines[:2]
    lh = int(s_ * 1.2)
    enh = 40 if en else 0
    y0 = pad + h / 2 + 18 - (lh * len(lines) + enh) / 2 + lh / 2
    for k, ln in enumerate(lines):
        d.text((pad + w / 2, y0 + k * lh), " ".join(ln), font=f, fill=tcol + (255,), anchor="mm")
    if en:
        fe, se, le = fit_lines_f(en, maxw, 1, 30, 20, get_font_reg)
        d.text((pad + w / 2, y0 + len(lines) * lh - lh / 2 + 24), " ".join(le[0]) if le else "", font=fe,
               fill=(EN_COL if state != "wrong" else MUTED) + (255,), anchor="mm")
    if state == "wrong":
        yy = y0 + (len(lines) - 1) * lh / 2
        tw = max(text_w(" ".join(l), f) for l in lines) if lines else 0
        d.line((pad + w / 2 - tw / 2 - 10, yy, pad + w / 2 + tw / 2 + 10, yy), fill=RED + (230,), width=7)
    return im


def caption_chunks(words, maxw=900, size=104, maxn=4):
    """Bol-chaal ke tukde: ek baar me 1 line (max 4 shabd) - pro reels jaisa, padhna bina mehnat."""
    f = get_font(size)
    out, cur = [], []
    for i, w in enumerate(words):
        trial = " ".join([words[j] for j in cur] + [w])
        if cur and (len(cur) >= maxn or text_w(trial, f) > maxw):
            out.append(cur)
            cur = []
        cur.append(i)
        if re.search(r"[,?।!]$", w) and len(cur) >= 2:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def caption_chunk_times(sc, key):
    if key not in sc.get("wt", {}):
        return []
    text = dict(sc["segs_text"]).get(key, "") if sc.get("segs_text") else ""
    ws = text.split()
    wt = sc["wt"][key]
    if len(ws) != len(wt):
        return []
    return [max(0.0, wt[c[0]] - EYE_LEAD) for c in caption_chunks(ws)]


def draw_captions(cv, text, wt, t, y, size=96):
    """Sirf abhi bola ja raha tukda, bada; bolta shabd peela. Tukda aate hi halka pop."""
    ws = text.split()
    if not ws or len(ws) != len(wt):
        return
    chunks = caption_chunks(ws, size=size)
    cur = None
    for c in chunks:
        if t >= wt[c[0]] - EYE_LEAD:
            cur = c
    if cur is None:
        return
    st = wt[cur[0]] - EYE_LEAD
    k = ease_out_back(prog(t, st, 0.16))
    f = get_font(size)
    space = text_w(" ", f)
    tot = sum(text_w(ws[i], f) for i in cur) + space * (len(cur) - 1)
    lay = Image.new("RGBA", (int(tot) + 60, int(size * 1.6)), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    x = 30
    for i in cur:
        nxt = wt[i + 1] if i + 1 < len(wt) else wt[i] + 0.5
        active = wt[i] - EYE_LEAD <= t < nxt - EYE_LEAD
        said = t >= wt[i] - EYE_LEAD
        col = YELLOW if active else (WHITE if said else (170, 182, 200))
        d.text((x, lay.height / 2), ws[i], font=f, fill=col + (255,), anchor="lm",
               stroke_width=7, stroke_fill=(5, 10, 22, 255))
        x += text_w(ws[i], f) + space
    place(cv, lay, W / 2, y, scale=max(0.05, 0.82 + 0.18 * k))


def draw_grid(cv, data, states, offsets=None, scales=None, alphas=None):
    offsets = offsets or {}
    scales = scales or {}
    alphas = alphas or {}
    for i, (l, txt) in enumerate(data["options"]):
        st = states.get(l)
        if not st:
            continue
        x, y = grid_pos(i)
        dx, dy = offsets.get(l, (0, 0))
        eo = data.get("en_opt", {}).get(l, "") if en_on("options") else ""
        place(cv, tile_sprite(l, txt, eo, st), x + dx, y + dy, scale=scales.get(l, 1.0),
              alpha=alphas.get(l, 1.0))


def question_recap(cv, data, a=1.0, y=520):
    if a <= 0.02:
        return
    draw_kinetic(cv, data["question"], W / 2, 0, 900, 50, 1.0, max_lines=3, min_size=36, karaoke=False,
                 line_h=1.28, center_y=y, color=mix(BG_BOTTOM, WHITE, a),
                 hl_words=hook_highlights(data["question"]) if a > 0.9 else (), hl_color=YELLOW)



# ==================== ICONS: vishay ki tasveer (code se bani, koi bahar ki file nahi) ====================
ICON_RULES = [   # (naam, shabd) - pehla milne wala
    ("moneyorder", ("मनीऑर्डर", "मनी ऑर्डर", "धनादेश", "money order")),
    ("postcard", ("पोस्टकार्ड", "पोस्ट कार्ड", "postcard")),
    ("parcel", ("पार्सल", "पैकेट", "पैकिंग", "मोम कपड़", "parcel", "packet")),
    ("registered", ("पंजीकृत", "रजिस्ट्री", "रजिस्टर्ड", "बीमाकृत", "registered", "insured")),
    ("stamp", ("डाक टिकट", "टिकट", "स्टाम्प", "stamp")),
    ("seal", ("सील", "लेबल", "मुहर", "seal", "label")),
    ("letterbox", ("लेटर बॉक्स", "पत्र पेटी", "डाक पेटी", "letter box")),
    ("bag", ("थैला", "थैले", "बैग", "bag")),
    ("clock", ("समय", "देर", "विलंब", "घंटे", "दिन के", "late", "time")),
    ("weight", ("वजन", "ग्राम", "किलो", "weight")),
    ("cycle", ("डाकिया", "वितरण", "बीट", "postman", "delivery")),
    ("letter", ("पत्र", "लिफाफ", "चिट्ठी", "डाक लेख", "letter", "article")),
]


def pick_icon(text):
    t = (text or "").lower()
    for name, keys in ICON_RULES:
        if any(k.lower() in t for k in keys):
            return name
    return "office"


@lru_cache(maxsize=32)
def icon_sprite(name, size=220):
    """Gol chamakta badge + andar saaf vector chitra."""
    S = 4                                             # bada banao, fir chhota -> chikne kinare
    n = size * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, n - 1, n - 1), fill=(20, 40, 72, 255), outline=CYAN + (255,), width=5 * S)
    c = n / 2
    u = n / 100                                      # 100 ke grid me aakar
    W_, INK_, Y_, R_, G_, B_ = (255, 255, 255, 255), (15, 25, 45, 255), YELLOW + (255,), RED + (255,), \
        GREEN + (255,), (90, 170, 255, 255)
    br = (205, 150, 90, 255)
    def R(x0, y0, x1, y1, **k):
        d.rounded_rectangle((x0 * u, y0 * u, x1 * u, y1 * u), radius=k.pop("r", 3) * u, **k)
    def L(pts, col, w):
        d.line([(x * u, y * u) for x, y in pts], fill=col, width=int(w * u), joint="curve")
    if name == "letter":
        R(20, 32, 80, 70, fill=W_)
        L([(20, 33), (50, 55), (80, 33)], B_, 3)
        R(64, 36, 75, 48, r=1, fill=R_)
    elif name == "postcard":
        R(18, 30, 82, 72, fill=(250, 240, 215, 255))
        L([(52, 36), (52, 66)], INK_, 1.5)
        for y in (48, 56, 64):
            L([(57, y), (77, y)], INK_, 1.5)
        R(68, 34, 78, 44, r=1, fill=R_)
        for y in (40, 48, 56):
            L([(24, y), (46, y)], (120, 130, 150, 255), 2)
    elif name == "parcel":
        R(22, 34, 78, 76, fill=br)
        d.polygon([(22 * u, 34 * u), (32 * u, 22 * u), (88 * u, 22 * u), (78 * u, 34 * u)], fill=(230, 180, 115, 255))
        L([(50, 34), (50, 76)], (150, 100, 55, 255), 4)
        L([(55, 22), (45, 34)], (150, 100, 55, 255), 4)
        R(56, 50, 74, 62, r=1, fill=W_)
    elif name == "registered":
        R(20, 32, 80, 70, fill=W_)
        L([(20, 33), (50, 55), (80, 33)], B_, 3)
        d.ellipse((52 * u, 44 * u, 82 * u, 74 * u), fill=R_)
        d.text((67 * u, 59 * u), "R", font=get_font(int(22 * u)), fill=W_, anchor="mm")
    elif name == "stamp":
        R(28, 22, 72, 78, r=1, fill=W_)
        for k in range(8):                           # daant wale kinare
            for x, y in ((28, 25 + k * 7), (72, 25 + k * 7)):
                d.ellipse(((x - 2) * u, (y - 2) * u, (x + 2) * u, (y + 2) * u), fill=(20, 40, 72, 255))
        R(34, 28, 66, 64, r=1, fill=(255, 120, 80, 255))
        d.ellipse((42 * u, 34 * u, 58 * u, 50 * u), fill=Y_)
    elif name == "seal":                              # label/tag + laal lakh ki mohar (✓ nahi - jawab jaisa na lage)
        d.polygon([(22 * u, 34 * u), (62 * u, 34 * u), (80 * u, 50 * u), (62 * u, 66 * u), (22 * u, 66 * u)],
                  fill=Y_)
        d.ellipse((64 * u, 46 * u, 72 * u, 54 * u), fill=(20, 40, 72, 255))
        for y in (43, 50, 57):
            L([(28, y), (54, y)], (120, 90, 20, 255), 2.5)
        d.ellipse((14 * u, 58 * u, 38 * u, 82 * u), fill=(190, 30, 45, 255))
        d.ellipse((19 * u, 63 * u, 33 * u, 77 * u), outline=(240, 150, 150, 255), width=int(1.5 * u))
    elif name == "letterbox":
        R(30, 26, 70, 84, r=8, fill=R_)
        d.pieslice((30 * u, 14 * u, 70 * u, 40 * u), 180, 360, fill=(220, 50, 50, 255))
        R(38, 40, 62, 45, r=1, fill=INK_)
        R(40, 60, 60, 70, r=1, fill=Y_)
        R(26, 82, 74, 88, r=2, fill=(130, 20, 30, 255))
    elif name == "bag":
        d.polygon([(26 * u, 40 * u), (74 * u, 40 * u), (80 * u, 82 * u), (20 * u, 82 * u)], fill=(170, 130, 80, 255))
        d.polygon([(34 * u, 40 * u), (66 * u, 40 * u), (58 * u, 28 * u), (42 * u, 28 * u)], fill=(140, 100, 60, 255))
        L([(40, 30), (60, 30)], INK_, 3)
        R(40, 55, 60, 68, r=2, fill=W_)
        d.text((50 * u, 61.5 * u), "डाक", font=get_font(int(7 * u)), fill=INK_, anchor="mm")
    elif name == "moneyorder":
        R(16, 34, 84, 68, fill=(120, 200, 140, 255))
        d.ellipse((38 * u, 39 * u, 62 * u, 63 * u), fill=(90, 170, 110, 255))
        d.text((50 * u, 51 * u), "₹", font=get_font(int(18 * u)), fill=W_, anchor="mm")
        L([(22, 74), (78, 74)], Y_, 3)
        d.polygon([(72 * u, 68 * u), (84 * u, 74 * u), (72 * u, 80 * u)], fill=Y_)
    elif name == "clock":
        d.ellipse((24 * u, 24 * u, 76 * u, 76 * u), fill=W_)
        d.ellipse((28 * u, 28 * u, 72 * u, 72 * u), outline=INK_, width=int(2 * u))
        L([(50, 50), (50, 34)], INK_, 3.5)
        L([(50, 50), (62, 56)], R_, 3)
        d.ellipse((47 * u, 47 * u, 53 * u, 53 * u), fill=INK_)
    elif name == "weight":
        d.polygon([(28 * u, 78 * u), (72 * u, 78 * u), (64 * u, 38 * u), (36 * u, 38 * u)], fill=(170, 180, 195, 255))
        d.ellipse((42 * u, 24 * u, 58 * u, 40 * u), outline=(170, 180, 195, 255), width=int(4 * u))
        d.text((50 * u, 62 * u), "kg", font=get_font(int(14 * u)), fill=INK_, anchor="mm")
    elif name == "cycle":
        for x in (30, 70):
            d.ellipse(((x - 14) * u, 52 * u, (x + 14) * u, 80 * u), outline=W_, width=int(3.5 * u))
        L([(30, 66), (46, 46), (62, 46), (70, 66)], Y_, 3.5)
        L([(46, 46), (52, 66), (30, 66)], Y_, 3.5)
        L([(62, 46), (60, 38), (68, 38)], W_, 3)
        R(36, 30, 54, 42, r=2, fill=br)
    elif name == "customer":                         # graahak
        d.ellipse((38 * u, 18 * u, 62 * u, 42 * u), fill=(240, 200, 160, 255))
        d.pieslice((22 * u, 44 * u, 78 * u, 100 * u), 180, 360, fill=(70, 150, 220, 255))
        R(44, 60, 64, 76, r=1, fill=W_)
        L([(44, 60), (54, 68), (64, 60)], B_, 1.5)
    elif name == "officer":                          # adhikari (topi + tie)
        d.ellipse((38 * u, 22 * u, 62 * u, 46 * u), fill=(240, 200, 160, 255))
        R(34, 16, 66, 26, r=3, fill=(40, 60, 110, 255))
        d.pieslice((22 * u, 48 * u, 78 * u, 104 * u), 180, 360, fill=(40, 60, 110, 255))
        d.polygon([(50 * u, 52 * u), (46 * u, 60 * u), (50 * u, 76 * u), (54 * u, 60 * u)], fill=R_)
    elif name == "receipt":                          # rasid / form
        d.polygon([(28 * u, 16 * u), (72 * u, 16 * u), (72 * u, 84 * u), (66 * u, 80 * u), (60 * u, 84 * u),
                   (54 * u, 80 * u), (48 * u, 84 * u), (42 * u, 80 * u), (36 * u, 84 * u), (28 * u, 80 * u)], fill=W_)
        for y in (28, 38, 48, 58):
            L([(34, y), (66 if y != 58 else 52, y)], (120, 130, 150, 255), 2.5)
        d.ellipse((50 * u, 58 * u, 68 * u, 76 * u), outline=R_, width=int(2.5 * u))
    elif name == "counter":                          # daak counter ki khidki
        R(18, 30, 82, 82, r=3, fill=(160, 108, 62, 255))
        R(26, 36, 74, 62, r=2, fill=(170, 210, 240, 255))
        L([(50, 36), (50, 62)], (120, 80, 45, 255), 3)
        R(14, 62, 86, 70, r=2, fill=(110, 70, 38, 255))
        R(32, 20, 68, 30, r=2, fill=R_)
    elif name == "postman":                          # khaki vardi + topi + thaila
        d.ellipse((40 * u, 16 * u, 60 * u, 36 * u), fill=(240, 200, 160, 255))
        R(36, 12, 64, 20, r=3, fill=(150, 120, 60, 255))
        d.pieslice((24 * u, 38 * u, 76 * u, 100 * u), 180, 360, fill=(190, 160, 95, 255))
        R(56, 56, 76, 76, r=2, fill=(140, 95, 50, 255))
        L([(46, 40), (66, 58)], (110, 75, 40, 255), 3)
    elif name == "van":                              # daak gaadi
        R(12, 40, 70, 72, r=4, fill=R_)
        R(70, 50, 90, 72, r=4, fill=(200, 40, 40, 255))
        R(74, 53, 86, 62, r=1, fill=B_)
        d.text((41 * u, 56 * u), "डाक", font=get_font(int(11 * u)), fill=W_, anchor="mm")
        for x in (28, 76):
            d.ellipse(((x - 8) * u, 66 * u, (x + 8) * u, 82 * u), fill=INK_)
    elif name == "scale":                            # tolne ka kaanta
        R(20, 66, 80, 80, r=3, fill=(170, 180, 195, 255))
        R(30, 58, 70, 66, r=2, fill=(210, 220, 230, 255))
        d.ellipse((34 * u, 22 * u, 66 * u, 54 * u), fill=W_, outline=INK_, width=int(2 * u))
        L([(50, 38), (60, 30)], R_, 3)
    elif name == "calendar":
        R(22, 24, 78, 80, r=4, fill=W_)
        R(22, 24, 78, 38, r=4, fill=R_)
        for x in (34, 66):
            L([(x, 18), (x, 30)], INK_, 3)
        for yy in (48, 60, 72):
            for xx in (32, 44, 56, 68):
                d.rectangle(((xx - 3) * u, (yy - 3) * u, (xx + 3) * u, (yy + 3) * u), fill=(170, 180, 195, 255))
    elif name == "rupee":                            # sikke + note
        R(18, 38, 70, 66, r=3, fill=(120, 200, 140, 255))
        d.text((44 * u, 52 * u), "₹", font=get_font(int(18 * u)), fill=W_, anchor="mm")
        for k, (x, y) in enumerate(((70, 62), (78, 70), (64, 74))):
            d.ellipse(((x - 9) * u, (y - 9) * u, (x + 9) * u, (y + 9) * u), fill=Y_, outline=(190, 140, 20, 255),
                      width=int(1.5 * u))
    elif name == "form":                             # form/aavedan
        R(26, 14, 74, 86, r=2, fill=W_)
        R(26, 14, 74, 26, r=2, fill=B_)
        for y in (36, 46, 56, 66):
            R(32, y, 68, y + 5, r=1, outline=(150, 160, 175, 255), width=int(1.2 * u))
        L([(52, 78), (68, 74)], INK_, 2)
    elif name == "register":                         # mota register/khata
        R(24, 18, 76, 84, r=3, fill=(40, 90, 150, 255))
        R(28, 22, 72, 80, r=2, fill=(60, 115, 180, 255))
        R(36, 36, 64, 46, r=1, fill=W_)
        L([(24, 30), (18, 30)], INK_, 2)
        L([(24, 70), (18, 70)], INK_, 2)
    elif name == "lock":
        d.arc((34 * u, 18 * u, 66 * u, 52 * u), 180, 360, fill=(170, 180, 195, 255), width=int(6 * u))
        R(28, 40, 72, 80, r=6, fill=Y_)
        d.ellipse((46 * u, 52 * u, 54 * u, 60 * u), fill=INK_)
        R(48, 58, 52, 68, r=1, fill=INK_)
    elif name == "datestamp":                        # mohar (tarikh wali)
        R(40, 14, 60, 44, r=4, fill=(120, 80, 45, 255))
        R(28, 44, 72, 56, r=3, fill=(80, 55, 30, 255))
        d.ellipse((26 * u, 60 * u, 74 * u, 90 * u), outline=(40, 70, 160, 255), width=int(3 * u))
        d.text((50 * u, 75 * u), "12 OCT", font=get_font(int(8 * u)), fill=(40, 70, 160, 255), anchor="mm")
    elif name == "phone":
        R(34, 14, 66, 86, r=8, fill=INK_)
        R(38, 22, 62, 74, r=2, fill=B_)
        d.ellipse((47 * u, 77 * u, 53 * u, 83 * u), fill=(120, 130, 150, 255))
    elif name == "house":
        d.polygon([(22 * u, 46 * u), (50 * u, 22 * u), (78 * u, 46 * u)], fill=(200, 90, 50, 255))
        R(28, 46, 72, 82, r=1, fill=(245, 225, 190, 255))
        R(44, 60, 56, 82, r=1, fill=(120, 80, 50, 255))
        R(32, 52, 40, 60, r=1, fill=B_)
    elif name == "village":                          # jhopdi + ped
        d.polygon([(14 * u, 56 * u), (36 * u, 36 * u), (58 * u, 56 * u)], fill=(170, 130, 60, 255))
        R(20, 56, 52, 80, r=1, fill=(210, 170, 110, 255))
        R(68, 50, 74, 80, r=1, fill=(110, 75, 40, 255))
        d.ellipse((56 * u, 26 * u, 86 * u, 56 * u), fill=G_)
    elif name == "train":
        R(14, 36, 86, 70, r=6, fill=(40, 90, 160, 255))
        for x in (22, 40, 58):
            R(x, 42, x + 12, 54, r=1, fill=(200, 225, 245, 255))
        for x in (26, 50, 74):
            d.ellipse(((x - 6) * u, 66 * u, (x + 6) * u, 78 * u), fill=INK_)
        L([(10, 80), (90, 80)], (120, 120, 130, 255), 2)
    elif name == "plane":
        d.polygon([(14 * u, 52 * u), (86 * u, 44 * u), (90 * u, 50 * u), (18 * u, 58 * u)], fill=W_)
        d.polygon([(46 * u, 48 * u), (60 * u, 22 * u), (66 * u, 24 * u), (58 * u, 48 * u)], fill=(200, 210, 225, 255))
        d.polygon([(44 * u, 54 * u), (58 * u, 80 * u), (64 * u, 78 * u), (56 * u, 54 * u)], fill=(200, 210, 225, 255))
        d.polygon([(16 * u, 52 * u), (12 * u, 38 * u), (20 * u, 40 * u), (24 * u, 52 * u)], fill=R_)
    elif name == "ship":
        d.polygon([(14 * u, 58 * u), (86 * u, 58 * u), (74 * u, 76 * u), (26 * u, 76 * u)], fill=(150, 40, 40, 255))
        R(34, 40, 66, 58, r=2, fill=W_)
        R(46, 26, 54, 40, r=1, fill=(60, 60, 70, 255))
        L([(10, 82), (90, 82)], B_, 3)
    elif name == "tick_box":                         # khaali daftar ki mez/khidki - 'jaanch'
        R(24, 24, 76, 76, r=6, fill=W_, outline=G_, width=int(4 * u))
        L([(36, 50), (46, 62), (66, 38)], G_, 6)
    elif name == "cross_box":
        R(24, 24, 76, 76, r=6, fill=W_, outline=R_, width=int(4 * u))
        L([(36, 36), (64, 64)], R_, 6)
        L([(64, 36), (36, 64)], R_, 6)
    else:                                            # office: daakghar ki imarat
        d.polygon([(20 * u, 44 * u), (50 * u, 22 * u), (80 * u, 44 * u)], fill=R_)
        R(26, 44, 74, 80, r=1, fill=(245, 235, 215, 255))
        R(44, 60, 56, 80, r=1, fill=(120, 80, 50, 255))
        for x in (30, 60):
            R(x, 52, x + 10, 62, r=1, fill=B_)
        R(34, 46, 66, 52, r=1, fill=Y_)
    return im.resize((size, size), Image.LANCZOS)


# ==================== CHITRA SE SAMJHO: niyam ko daak-counter ke drishya se samjhana ====================
# AI sirf tay shabdavali (object / item / jagah) se "storyboard" bharta hai; examiner jaanchta hai ki drishya
# niyam se bilkul milta hai. Chitra code se banta hai (asli jaisi baariki: PIN ke khaane, prempak, daanta
# wala daak ticket) - galat/nakli cheez (jaise "50% OFF") kabhi nahi.
CHITRA_OBJECTS = ("envelope", "postcard", "parcel")
CHITRA_ITEMS = ("festive_seal", "shop_sticker", "postage_stamp")
CHITRA_PLACES = ("address", "stamp_corner", "top_left", "back")
CHITRA_RIGHT = ("remove", "stamp_corner", "top_left", "back")
ART_W, ART_H = 880, 540
ART_CY = 930


def _art_regions(obj):
    """Article ke hisse (sprite ke andar, px): address / stamp_corner / top_left."""
    if obj == "postcard":
        return {"address": (470, 170, 840, 470), "stamp_corner": (720, 30, 850, 160), "top_left": (40, 40, 420, 200)}
    if obj == "parcel":                                  # dori ki gaanth baayein (215,300) - pata-parchi daayein
        return {"address": (420, 170, 840, 480), "stamp_corner": (700, 30, 850, 160), "top_left": (40, 40, 330, 170)}
    return {"address": (330, 190, 830, 470), "stamp_corner": (720, 30, 850, 170), "top_left": (40, 40, 330, 170)}


def _stamp_img(w=120, h=150):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, w - 1, h - 1), fill=(255, 255, 255, 255))
    for k in range(0, h, 14):                                  # daante (perforation)
        for x in (0, w - 1):
            d.ellipse((x - 5, k + 2, x + 5, k + 12), fill=(0, 0, 0, 0))
    for k in range(0, w, 14):
        for y in (0, h - 1):
            d.ellipse((k + 2, y - 5, k + 12, y + 5), fill=(0, 0, 0, 0))
    d.rectangle((12, 12, w - 13, h - 34), fill=(222, 92, 60, 255))
    d.ellipse((w / 2 - 22, 30, w / 2 + 22, 74), fill=(255, 210, 90, 255))
    d.polygon([(12, h - 34), (w / 2, h - 70), (w - 13, h - 34)], fill=(40, 120, 90, 255))
    d.text((w / 2, h - 18), "भारत", font=get_font(20), fill=(40, 40, 60, 255), anchor="mm")
    return im


@lru_cache(maxsize=12)
def article_sprite(obj, back=False, no_stamp=False):
    """Asli jaisa daak lekh: pata 'सेवा में' + PIN ke 6 khaane + प्रेषक + daant wala ticket."""
    im = Image.new("RGBA", (ART_W, ART_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ink = (28, 40, 78, 255)
    if obj == "parcel":
        d.rounded_rectangle((0, 0, ART_W - 1, ART_H - 1), radius=10, fill=(196, 150, 96, 255),
                            outline=(150, 108, 62, 255), width=5)
        d.rectangle((0, 300 - 12, ART_W, 300 + 12), fill=(235, 225, 200, 255))     # dori (sutli)
        d.rectangle((215 - 12, 0, 215 + 12, ART_H), fill=(235, 225, 200, 255))
        d.ellipse((215 - 30, 300 - 30, 215 + 30, 300 + 30), fill=(215, 200, 170, 255))  # gaanth
        d.rounded_rectangle((410, 160, 845, 485), radius=10, fill=(252, 250, 244, 255), outline=(200, 190, 170, 255),
                            width=3)
    elif obj == "postcard":
        d.rounded_rectangle((0, 0, ART_W - 1, ART_H - 1), radius=14, fill=(250, 238, 200, 255),
                            outline=(210, 190, 140, 255), width=4)
        d.line((440, 60, 440, 500), fill=(150, 130, 90, 255), width=3)
        for y in (110, 170, 230, 290, 350):
            d.line((50, y, 400, y), fill=(190, 170, 130, 255), width=2)
        d.text((60, 460), "पोस्टकार्ड", font=get_font(34), fill=(150, 120, 70, 255), anchor="lm")
    else:
        d.rounded_rectangle((0, 0, ART_W - 1, ART_H - 1), radius=16, fill=(250, 246, 236, 255),
                            outline=(205, 195, 175, 255), width=4)
        if back:                                                  # lifaafe ki peeth: flap
            d.polygon([(8, 8), (ART_W / 2, ART_H * 0.55), (ART_W - 8, 8)], fill=(240, 234, 220, 255),
                      outline=(205, 195, 175, 255))
            d.line((8, ART_H - 8, ART_W / 2, ART_H * 0.55, ART_W - 8, ART_H - 8), fill=(215, 205, 188, 255), width=3)
            d.text((ART_W / 2, ART_H - 60), "पीछे की तरफ", font=get_font(34), fill=(160, 150, 130, 255), anchor="mm")
            return im
    if not no_stamp:                                  # ticket hi 'item' ho to pehle se chhapa ticket nahi (do ticket na dikhen)
        st = _stamp_img()
        r = _art_regions(obj)["stamp_corner"]
        im.paste(st, (r[0] + (r[2] - r[0] - st.width) // 2, r[1] + (r[3] - r[1] - st.height) // 2), st)
    r = _art_regions(obj)["address"]
    x0, y0 = r[0] + 20, r[1] + 16
    d.text((x0, y0), "सेवा में,", font=get_font_reg(32), fill=ink, anchor="lt")
    for i, ln in enumerate(("श्री राम कुमार", "ग्राम व डाक: सोनपुर", "जिला: पटना")):
        d.text((x0 + 30, y0 + 52 + i * 52), ln, font=get_font(38), fill=ink, anchor="lt")
    px = x0 + 30
    py = y0 + 52 + 3 * 52 + 12
    d.text((px, py + 22), "PIN", font=get_font(26), fill=ink, anchor="lm")
    for i, ch in enumerate("800001"):                              # PIN ke 6 khaane
        bx = px + 64 + i * 46
        d.rectangle((bx, py, bx + 40, py + 44), outline=(120, 110, 90, 255), width=2)
        d.text((bx + 20, py + 23), ch, font=get_font(30), fill=ink, anchor="mm")
    if obj == "envelope":
        d.text((40, ART_H - 70), "प्रेषक: मोहन लाल, आरा", font=get_font_reg(28), fill=(90, 90, 110, 255), anchor="lm")
    return im


@lru_cache(maxsize=8)
def item_sprite(item):
    """Gair-daak cheezein asli zindagi jaisi: tyohaar ka sajawati seal, dukaan ka sticker; ya daak ticket."""
    if item == "postage_stamp":
        return _stamp_img(130, 160)
    if item == "tissue_paper":                               # patla, aadha-paardarshi kagaz (neeche ka dikhe)
        im = Image.new("RGBA", (230, 200), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.polygon([(10, 22), (205, 6), (222, 176), (24, 192)], fill=(255, 255, 255, 150), outline=(200, 205, 215, 220))
        for y in (60, 100, 140):
            d.line((40, y, 190, y - 8), fill=(220, 224, 232, 120), width=2)
        return im
    if item == "thick_cloth":                                # mota sooti kapda (bunai ki dhaariyan)
        im = Image.new("RGBA", (240, 210), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, 239, 209), radius=18, fill=(214, 200, 170, 255), outline=(160, 140, 105, 255), width=5)
        for k in range(0, 240, 16):
            d.line((k, 0, k, 209), fill=(190, 172, 138, 255), width=3)
        for k in range(0, 210, 16):
            d.line((0, k, 239, k), fill=(196, 180, 148, 255), width=2)
        return im
    if item == "plastic_sheet":                              # chamakti plastic (neela, chamak ki dhaari)
        im = Image.new("RGBA", (230, 200), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, 229, 199), radius=14, fill=(150, 200, 240, 150), outline=(90, 150, 210, 230), width=4)
        d.line((30, 170, 190, 20), fill=(255, 255, 255, 190), width=10)
        return im
    if item == "twine":                                      # sutli ki gaanth
        im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.line((0, 100, 200, 100), fill=(225, 205, 160, 255), width=14)
        d.line((100, 0, 100, 200), fill=(225, 205, 160, 255), width=14)
        d.ellipse((72, 72, 128, 128), fill=(200, 175, 125, 255))
        d.arc((40, 40, 110, 110), 90, 360, fill=(200, 175, 125, 255), width=10)
        return im
    if item == "wax_seal":                                   # laal lakh ki mohar (asli jaisi, aniyamit kinara)
        s_ = 170
        im = Image.new("RGBA", (s_, s_), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        rng = random.Random(11)
        pts = []
        for k in range(28):
            a = k * 2 * math.pi / 28
            r = 70 + rng.uniform(-9, 9)
            pts.append((s_ / 2 + r * math.cos(a), s_ / 2 + r * math.sin(a)))
        d.polygon(pts, fill=(150, 18, 28, 255))
        d.ellipse((s_ / 2 - 50, s_ / 2 - 50, s_ / 2 + 50, s_ / 2 + 50), fill=(175, 28, 38, 255),
                  outline=(120, 10, 20, 255), width=5)
        d.ellipse((s_ / 2 - 36, s_ / 2 - 36, s_ / 2 + 36, s_ / 2 + 36), outline=(215, 90, 90, 255), width=3)
        d.text((s_ / 2, s_ / 2), "डाक", font=get_font(30), fill=(225, 120, 120, 255), anchor="mm")
        d.ellipse((s_ / 2 - 40, s_ / 2 - 46, s_ / 2 - 18, s_ / 2 - 30), fill=(230, 120, 120, 160))   # chamak
        return im
    if item == "shop_sticker":
        w, h = 330, 150
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=18, fill=(255, 255, 255, 255), outline=(40, 90, 200, 255),
                            width=6)
        d.text((w / 2, 52), "गुप्ता स्टोर्स", font=get_font(40), fill=(40, 90, 200, 255), anchor="mm")
        d.text((w / 2, 104), "खरीदारी के लिए धन्यवाद", font=get_font(24), fill=(90, 90, 110, 255), anchor="mm")
        return im
    s = 230                                                        # festive_seal
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for k in range(24):                                            # daantedaar kinara
        a = k * math.pi / 12
        d.ellipse((s / 2 + 100 * math.cos(a) - 16, s / 2 + 100 * math.sin(a) - 16,
                   s / 2 + 100 * math.cos(a) + 16, s / 2 + 100 * math.sin(a) + 16), fill=(230, 170, 40, 255))
    d.ellipse((14, 14, s - 14, s - 14), fill=(230, 170, 40, 255))
    d.ellipse((26, 26, s - 26, s - 26), fill=(190, 30, 50, 255))
    d.ellipse((34, 34, s - 34, s - 34), outline=(255, 220, 120, 255), width=3)
    d.text((s / 2, s / 2 - 22), "शुभ", font=get_font(40), fill=(255, 230, 150, 255), anchor="mm")
    d.text((s / 2, s / 2 + 26), "दीपावली", font=get_font(40), fill=(255, 230, 150, 255), anchor="mm")
    return im


@lru_cache(maxsize=2)
def counter_layer():
    """Lakdi ka daak counter + 'डाक काउंटर' ki takhti (peeche)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top, bot = 600, 1500
    rng = random.Random(3)
    for y in range(top, bot):
        k = (y - top) / (bot - top)
        xl = 150 * (1 - k)
        col = mix((120, 78, 44), (160, 108, 62), k)
        d.line((xl, y, W - xl, y), fill=col + (255,))
    for _ in range(46):                                            # lakdi ki dhaariyan
        y = rng.uniform(top + 10, bot - 10)
        k = (y - top) / (bot - top)
        xl = 150 * (1 - k)
        x0 = rng.uniform(xl, W - xl - 200)
        d.line((x0, y, x0 + rng.uniform(120, 420), y + rng.uniform(-3, 3)), fill=(100, 64, 34, 150), width=2)
    d.rectangle((0, bot, W, bot + 70), fill=(86, 54, 28, 255))
    d.line((0, bot, W, bot), fill=(190, 140, 90, 255), width=4)
    # takhti
    d.line((W / 2 - 150, 380, W / 2 - 150, 420), fill=(160, 160, 170, 255), width=4)
    d.line((W / 2 + 150, 380, W / 2 + 150, 420), fill=(160, 160, 170, 255), width=4)
    d.rounded_rectangle((W / 2 - 220, 418, W / 2 + 220, 500), radius=12, fill=(170, 30, 40, 255),
                        outline=(240, 200, 120, 255), width=4)
    d.text((W / 2, 459), "डाक काउंटर", font=get_font(46), fill=(255, 240, 210, 255), anchor="mm")
    return im


@lru_cache(maxsize=4)
def soft_shadow(w, h):
    im = Image.new("RGBA", (w + 120, h + 120), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((60, 60, w + 60, h + 60), radius=20, fill=(0, 0, 0, 150))
    return im.filter(ImageFilter.GaussianBlur(24))


def _region_center(obj, place_):
    r = _art_regions(obj)[place_]
    return (r[0] + r[2]) / 2 - ART_W / 2, (r[1] + r[3]) / 2 - ART_H / 2



# ---------- KIT 3 "address": pata likhne ke niyam - chhantai rack + lifaafa ----------
ADDR_LINES = ("name", "house", "village", "post_town", "pin", "district")
ADDR_WRONG = ("small", "missing", "unclear")
ADDR_RIGHT = ("block_caps_underline", "block_caps", "clear", "present")
ADDR_TEXT = {"name": "Shri Ram Kumar", "house": "H. No. 12, Main Road", "village": "Vill. & PO: Sonpur",
             "district": "Distt: Patna", "post_town": "PATNA", "pin": "800001"}
RACK_TOWNS = ("GAYA", "PATNA", "ARA", "BUXAR", "SIWAN", "NALANDA", "CHAPRA", "NAWADA")
RACK_TARGET = 1                                              # PATNA ka khaana
RACK_TOP, RACK_ROWS, RACK_COLS = 560, 2, 4
SLOT_W, SLOT_H = 220, 118


def _slot_center(i):
    r_, c_ = divmod(i, RACK_COLS)
    x0 = W / 2 - RACK_COLS * SLOT_W / 2
    return x0 + c_ * SLOT_W + SLOT_W / 2, RACK_TOP + r_ * SLOT_H + SLOT_H / 2


@lru_cache(maxsize=2)
def sorting_layer():
    """Chhantai ka lakdi ka rack (shahron ke khaane) + neeche mez + 'छंटाई' takhti."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0 = W / 2 - RACK_COLS * SLOT_W / 2 - 18
    d.rounded_rectangle((x0, RACK_TOP - 18, W - x0, RACK_TOP + RACK_ROWS * SLOT_H + 18), radius=10,
                        fill=(110, 70, 38, 255))
    for i in range(RACK_ROWS * RACK_COLS):
        cx, cy = _slot_center(i)
        d.rectangle((cx - SLOT_W / 2 + 8, cy - SLOT_H / 2 + 8, cx + SLOT_W / 2 - 8, cy + SLOT_H / 2 - 8),
                    fill=(52, 32, 18, 255))
        d.rounded_rectangle((cx - 78, cy + 14, cx + 78, cy + 46), radius=5, fill=(245, 235, 210, 255))
        d.text((cx, cy + 30), RACK_TOWNS[i], font=get_font(24), fill=(60, 40, 20, 255), anchor="mm")
    top, bot = 900, 1500
    for y in range(top, bot):
        k = (y - top) / (bot - top)
        xl = 120 * (1 - k)
        d.line((xl, y, W - xl, y), fill=mix((120, 78, 44), (160, 108, 62), k) + (255,))
    d.rectangle((0, bot, W, bot + 70), fill=(86, 54, 28, 255))
    d.rounded_rectangle((W / 2 - 150, 430, W / 2 + 150, 500), radius=12, fill=(170, 30, 40, 255),
                        outline=(240, 200, 120, 255), width=4)
    d.text((W / 2, 465), "छंटाई", font=get_font(44), fill=(255, 240, 210, 255), anchor="mm")
    return im


def address_envelope(line, style, reveal=1.0, mark=None):
    """English pata (asli jaisa) - `line` ko `style` me: small/missing/unclear/block_caps/_underline/clear/present."""
    ew, eh = 820, 470
    im = Image.new("RGBA", (ew, eh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, ew - 1, eh - 1), radius=14, fill=(250, 246, 236, 255), outline=(205, 195, 175, 255),
                        width=4)
    st = _stamp_img(100, 124)
    im.paste(st, (ew - 130, 24), st)
    ink = (28, 40, 78, 255)
    order = ["name", "house", "village", "district", "post_town"]
    x0, y = 250, 110
    d.text((x0, y - 50), "To,", font=get_font_reg(30), fill=ink, anchor="lm")
    for key in order:
        txt = ADDR_TEXT[key]
        if key == "post_town":
            txt = "PATNA - 800001"
            if line == "pin" and style in ("missing",):
                txt = "PATNA"
        is_t = key == line or (line == "pin" and key == "post_town")
        f = get_font(36)
        col = ink
        if is_t:
            if style == "missing":
                if line != "pin":
                    d.rounded_rectangle((x0 - 6, y - 24, x0 + 360, y + 24), radius=6, outline=(210, 60, 60, 255),
                                        width=3)
                    d.text((x0 + 12, y), "? ? ?", font=get_font(30), fill=(210, 60, 60, 255), anchor="lm")
                    y += 62
                    continue
            elif style == "small":
                txt = txt.lower() if line != "pin" else txt           # chhote akshar (PIN ank hain - wahi)
                f, col = get_font_reg(26), (120, 120, 140, 255)
            elif style in ("block_caps", "block_caps_underline"):
                txt = txt.upper()                                    # BLOCK CAPITALS - sach me capital
                sz_ = int(36 + 16 * reveal)
                while sz_ > 34 and text_w(txt, get_font(sz_)) > ew - 170 - x0:   # daak ticket tak na pahunche
                    sz_ -= 2
                f = get_font(sz_)
            elif style == "unclear":
                lay = Image.new("RGBA", (500, 60), (0, 0, 0, 0))
                ImageDraw.Draw(lay).text((6, 30), txt, font=get_font(36), fill=ink, anchor="lm")
                lay = lay.filter(ImageFilter.GaussianBlur(5))
                im.paste(lay, (int(x0 - 6), int(y - 30)), lay)
                y += 62
                continue
        d.text((x0, y), txt, font=f, fill=col, anchor="lm")
        if is_t and mark:                               # aankh seedhe isi line pe: laal (galat) / hara (sahi)
            tw2 = text_w(txt, f)
            ul_ = 18 if style == "block_caps_underline" else 8           # rekha ghere ke andar dikhe
            d.rounded_rectangle((x0 - 14, y - f.size * 0.75, x0 + tw2 + 14, y + f.size * 0.75 + ul_), radius=8,
                                outline=((220, 40, 50, 255) if mark == "wrong" else (30, 170, 80, 255)), width=5)
        if is_t and style == "block_caps_underline":
            # rekha sirf us line ke naam ke neeche (post town: 'PATNA', PIN nahi)
            tw_ = text_w(txt.split(" - ")[0] if key == "post_town" else txt, f)
            d.line((x0, y + 32, x0 + tw_ * clamp(reveal), y + 32), fill=(200, 30, 40, 255), width=6)
        y += 62 if not (is_t and style in ("block_caps", "block_caps_underline")) else 74
    return im


def scene_address(cv, data, t, dur, m, vd, sc):
    """
    Chhantai: lifaafa mez pe (c1) -> galat likha pata, chitthi khaanon ke beech atakti, ❌ (c2) ->
    sahi likhawat (bade akshar + rekha...), chitthi seedhe PATNA ke khaane me, ✓ (c3).
    """
    fx = {}
    cfg = data["chitra"]
    line, wr, rt = cfg["line"], cfg["wrong"], cfg["right"]
    tw = max(0.9, m["c2"][0] - 0.3)
    tr = max(tw + 1.0, m["c3"][0] - 0.3)
    cv.paste(sorting_layer(), (0, 0), sorting_layer())
    e = ease_out_cubic(prog(t, 0.0, 0.5))
    ex, ey = W / 2 + (1 - e) * 600, 1075 + (1 - e) * 200
    style = wr if t < tr else rt
    rv = ease_out_cubic(prog(t, tr, 0.45)) if t >= tr else 1.0
    mk_ = "wrong" if tw + 0.3 <= t < tr else ("right" if t >= tr + 0.5 else None)
    env = address_envelope(line, style, rv, mk_)
    sc_ = 1.0
    fly = prog(t, tr + 0.9, 0.55) if t >= tr + 0.9 else 0.0
    if tw <= t < tr:
        # chhantai wala dhoondh raha: chitthi do khaanon ke beech jhoolti (kaunsa khaana?)
        p_ = t - tw
        ex += 150 * math.sin(p_ * 5.0)
        ey -= 60 * abs(math.sin(p_ * 2.5))
    if fly > 0:
        tx_, ty_ = _slot_center(RACK_TARGET)
        k = ease_in_out(fly)
        ex, ey = ex + (tx_ - ex) * k, ey + (ty_ - ey) * k
        sc_ = 1 - 0.8 * k
    place(cv, soft_shadow(env.width, env.height), ex + 16, ey + 22, scale=sc_)
    place(cv, env, ex, ey, scale=sc_, angle=(-2 + 2 * math.sin(t * 1.4)) * (1 - fly))
    if tw + 0.4 <= t < tr:
        kq = ease_out_back(prog(t, tw + 0.4, 0.3))
        for i in (0, 2):
            cx, cy = _slot_center(i)
            place(cv, pill_sprite("?", 50, WHITE, (160, 30, 40), RED), cx, cy - 12, scale=max(0.05, kq))
        place(cv, x_mark_sprite(140), W - 160, 860, scale=max(0.05, 1.6 - 0.6 * ease_out_back(prog(t, tw + 0.5, 0.25))))
        if t < tw + 0.55:
            fx["shake"] = 6
    if t >= tr + 0.9:
        cx, cy = _slot_center(RACK_TARGET)
        kk = prog(t, tr + 1.3, 0.3)
        if kk > 0:
            place(cv, glow_sprite(160, GREEN, int(160 * (1 - 0.5 * kk))), cx, cy)
        place(cv, check_sprite(140), W - 160, 860, scale=max(0.05, ease_out_back(prog(t, tr + 0.2, 0.3))))
    elif t >= tr + 0.2:
        place(cv, check_sprite(140), W - 160, 860, scale=max(0.05, ease_out_back(prog(t, tr + 0.2, 0.3))))
    place(cv, pill_sprite("चित्र से समझो", 46, (30, 20, 0), YELLOW, ORANGE), W / 2, 300,
          scale=max(0.05, ease_out_back(prog(t, 0, 0.3))))
    key = "c1" if t < m["c2"][0] - EYE_LEAD else ("c2" if t < m["c3"][0] - EYE_LEAD else "c3")
    col = {"c1": WHITE, "c2": (255, 150, 150), "c3": (150, 255, 180)}[key]
    txt = cfg["caps"][int(key[1]) - 1]
    place(cv, card_sprite(1000, 150, (10, 16, 30), mix((10, 16, 30), col, 0.6), 4, 34), W / 2, 1400)
    if sc.get("exact_words"):
        kp, th = seg_progress(sc, key, t)
    else:
        a_, b_ = m[key]
        kp, th = clamp((t - a_ + EYE_LEAD) / max(0.3, b_ - a_)), None
    if key in CHITRA_SILENT:
        kp, th = 1.0, None
    draw_kinetic(cv, txt, W / 2, 0, 930, 52, max(kp, 0.001), max_lines=2, min_size=38, line_h=1.25,
                 center_y=1400, ghost=0.3, th=th, color=col)
    return fx


def _story_place(obj, place_):
    if place_ == "center" and obj == "parcel":
        return 215 - ART_W / 2, 300 - ART_H / 2           # parcel ki gaanth
    if place_ in ("center", "back"):
        return 0.0, 0.0
    return _region_center(obj, place_)


def story_picture(step, w=380, h=250):
    """Khaane ka asli chitra: lifaafa/postcard/parcel + us par items (ginti/jagah ke saath); warna bada icon."""
    obj = step.get("object") or step.get("icon") or "office"
    key = (obj, tuple((i["item"], i["place"], i["count"]) for i in step.get("items") or []), w, h)
    if key in _STORY_PICS:
        return _STORY_PICS[key]
    if obj in STORY_ARTICLES:
        back = any(i["place"] == "back" for i in step.get("items") or []) and obj == "envelope"
        has_stamp_item = any(i["item"] == "postage_stamp" for i in step.get("items") or [])
        art = article_sprite(obj, back=back, no_stamp=has_stamp_item).copy()
        for it in step.get("items") or []:
            spr = item_sprite(it["item"])
            n_ = max(1, min(4, int(it["count"])))
            cx_, cy_ = _story_place(obj, it["place"])
            offs = [(0, 0)] if n_ == 1 else [(-170, -90), (170, 80), (160, -110), (-150, 100)][:n_]
            if obj == "parcel" and it["place"] == "center" and n_ > 1:
                offs = [(0, 0), (500, -190), (420, 150), (60, 170)][:n_]
            elif it["place"] != "center" and n_ > 1:
                offs = [(dx * 0.6, dy * 0.6) for dx, dy in offs]
            for k, (dx, dy) in enumerate(offs):
                sp = spr.rotate((-8, 12, -15, 6)[k], expand=True, resample=Image.BICUBIC)
                art.paste(sp, (int(ART_W / 2 + cx_ + dx - sp.width / 2), int(ART_H / 2 + cy_ + dy - sp.height / 2)), sp)
        sc_ = min(w / ART_W, h / ART_H)
        im = art.resize((int(ART_W * sc_), int(ART_H * sc_)), Image.LANCZOS)
    else:
        im = icon_sprite(obj, min(w, h))
    _STORY_PICS[key] = im
    return im


_STORY_PICS = {}



# ==================== KIT "draw": har niyam ka APNA chitra (AI aakaron se banata hai, PIL draw karta hai) ====================
DRAW_W, DRAW_H = 480, 300
DRAW_SPRITES = STORY_ICONS + ("envelope", "wax_seal", "tissue_paper", "thick_cloth", "plastic_sheet", "twine",
                              "festive_seal", "shop_sticker", "postage_stamp")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")


def _col(c, default=None):
    c = str(c or "").strip()
    if _HEX.match(c):
        a = int(c[7:9], 16) if len(c) == 9 else 255
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) + (a,)
    return default


def _num(v, lo=-50, hi=600):
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ValueError("sankhya nahi")
    if not lo <= v <= hi:
        raise ValueError("canvas ke bahar")
    return v


def draw_validate(shapes):
    """Drawing ke aakar jaancho (list, ginti, rang, jagah). Galti -> ValueError(wajah)."""
    if not isinstance(shapes, list) or not 3 <= len(shapes) <= 45:
        raise ValueError("3-45 aakar chahiye")
    labels = 0
    for sh in shapes:
        if not isinstance(sh, dict):
            raise ValueError("aakar dict nahi")
        t = sh.get("t")
        if t in ("rect", "ellipse"):
            for k in ("x", "y", "w", "h"):
                _num(sh.get(k))
        elif t == "circle":
            for k in ("cx", "cy", "r"):
                _num(sh.get(k))
        elif t in ("poly", "line"):
            pts = sh.get("pts")
            if not isinstance(pts, list) or not 2 <= len(pts) <= 16:
                raise ValueError("pts 2-16")
            for p_ in pts:
                _num(p_[0]); _num(p_[1])
        elif t == "arrow":
            for k in ("from", "to"):
                _num(sh[k][0]); _num(sh[k][1])
        elif t == "sprite":
            if sh.get("name") not in DRAW_SPRITES:
                raise ValueError(f"sprite '{sh.get('name')}' list me nahi")
            for k in ("x", "y", "w"):
                _num(sh.get(k))
        elif t == "label":
            labels += 1
            txt = " ".join(str(sh.get("text") or "").split())
            if not txt or len(txt.split()) > 3 or re.search(r"[A-Za-z]{3,}", txt):
                raise ValueError("label 1-3 Hindi shabd")
            _num(sh.get("x")); _num(sh.get("y"))
        elif t == "mark":
            if sh.get("kind") not in ("x", "tick"):
                raise ValueError("mark x/tick")
            _num(sh.get("x")); _num(sh.get("y"))
        else:
            raise ValueError(f"aakar '{t}' samajh nahi")
    if labels > 3:
        raise ValueError("3 se zyada label")


def stroke_needed(sh):
    return bool(_col(sh.get("stroke")))


def _draw_sprite(name, w):
    if name in ("envelope", "postcard", "parcel"):
        return article_sprite(name).resize((int(w), int(w * ART_H / ART_W)), Image.LANCZOS)
    if name in ("wax_seal", "tissue_paper", "thick_cloth", "plastic_sheet", "twine", "festive_seal", "shop_sticker",
                "postage_stamp"):
        sp = item_sprite(name)
        return sp.resize((int(w), int(w * sp.height / sp.width)), Image.LANCZOS)
    return icon_sprite(name, int(w))


_DRAW_CACHE = {}


def render_drawing(shapes, scale=2):
    """Aakar -> RGBA chitra (DRAW_W x DRAW_H), halka krem kagaz ke upar. 2x bana ke chhota (chikne kinare)."""
    key = json.dumps(shapes, ensure_ascii=False, sort_keys=True)
    if key in _DRAW_CACHE:
        return _DRAW_CACHE[key]
    S = scale
    im = Image.new("RGBA", (DRAW_W * S, DRAW_H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, DRAW_W * S - 1, DRAW_H * S - 1), radius=22 * S, fill=(250, 244, 230, 255))
    ink = (40, 45, 60, 255)
    late = []
    for sh in shapes:
        t = sh["t"]
        fill = _col(sh.get("fill"))
        if (fill and fill[3] < 255) and t in ("rect", "ellipse", "circle", "poly"):
            lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
            dl = ImageDraw.Draw(lay)
            if t == "rect":
                x, y, w, h = (float(sh[k]) * S for k in ("x", "y", "w", "h"))
                dl.rounded_rectangle((x, y, x + w, y + h), radius=float(sh.get("r") or 0) * S, fill=fill)
            elif t == "ellipse":
                x, y, w, h = (float(sh[k]) * S for k in ("x", "y", "w", "h"))
                dl.ellipse((x, y, x + w, y + h), fill=fill)
            elif t == "circle":
                cx, cy, r = (float(sh[k]) * S for k in ("cx", "cy", "r"))
                dl.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
            else:
                dl.polygon([(float(a) * S, float(b) * S) for a, b in sh["pts"]], fill=fill)
            im.alpha_composite(lay)
            d = ImageDraw.Draw(im)
            fill = None
            if not stroke_needed(sh):
                continue
        stroke = _col(sh.get("stroke"))
        sw = int(max(0, min(12, float(sh.get("sw") or (3 if stroke else 0)))) * S)
        if t == "rect":
            x, y, w, h = (float(sh[k]) * S for k in ("x", "y", "w", "h"))
            d.rounded_rectangle((x, y, x + w, y + h), radius=float(sh.get("r") or 0) * S, fill=fill,
                                outline=stroke, width=sw)
        elif t == "ellipse":
            x, y, w, h = (float(sh[k]) * S for k in ("x", "y", "w", "h"))
            d.ellipse((x, y, x + w, y + h), fill=fill, outline=stroke, width=sw)
        elif t == "circle":
            cx, cy, r = (float(sh[k]) * S for k in ("cx", "cy", "r"))
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill, outline=stroke, width=sw)
        elif t == "poly":
            pts = [(float(a) * S, float(b) * S) for a, b in sh["pts"]]
            d.polygon(pts, fill=fill, outline=stroke)
            if stroke and sw:
                d.line(pts + [pts[0]], fill=stroke, width=sw, joint="curve")
        elif t == "line":
            pts = [(float(a) * S, float(b) * S) for a, b in sh["pts"]]
            d.line(pts, fill=stroke or ink, width=max(S, sw or 4 * S), joint="curve")
        elif t == "arrow":
            (x0, y0), (x1, y1) = [(float(a) * S, float(b) * S) for a, b in (sh["from"], sh["to"])]
            col = _col(sh.get("color"), (230, 150, 0, 255))
            d.line((x0, y0, x1, y1), fill=col, width=6 * S)
            ang = math.atan2(y1 - y0, x1 - x0)
            L = 18 * S
            d.polygon([(x1, y1), (x1 - L * math.cos(ang - 0.45), y1 - L * math.sin(ang - 0.45)),
                       (x1 - L * math.cos(ang + 0.45), y1 - L * math.sin(ang + 0.45))], fill=col)
        elif t == "sprite":
            sp = _draw_sprite(sh["name"], float(sh["w"]) * S)
            rot = float(sh.get("rot") or 0)
            if abs(rot) > 0.5:
                sp = sp.rotate(-rot, expand=True, resample=Image.BICUBIC)
            im.alpha_composite(sp, (int(float(sh["x"]) * S - sp.width / 2), int(float(sh["y"]) * S - sp.height / 2)))
            d = ImageDraw.Draw(im)
        else:
            late.append(sh)                                  # label/mark sabse upar
    for sh in late:
        if sh["t"] == "label":
            txt = clean_hi(sh["text"])
            kind = sh.get("color") or "dark"
            fg, bg, ol = {"red": (WHITE, (190, 30, 45), (120, 10, 20)), "green": (WHITE, (22, 140, 70), (10, 90, 40)),
                          "light": ((30, 30, 40), (255, 255, 255), (150, 150, 160))}.get(
                kind, (WHITE, (30, 40, 70), (15, 20, 40)))
            pl = pill_sprite(txt, 26 * S, fg, bg, ol)
            im.alpha_composite(pl, (int(float(sh["x"]) * S - pl.width / 2), int(float(sh["y"]) * S - pl.height / 2)))
        elif sh["t"] == "mark":
            sp = x_mark_sprite(60 * S) if sh["kind"] == "x" else check_sprite(60 * S)
            im.alpha_composite(sp, (int(float(sh["x"]) * S - sp.width / 2), int(float(sh["y"]) * S - sp.height / 2)))
    d = ImageDraw.Draw(im)
    out = im.resize((DRAW_W, DRAW_H), Image.LANCZOS)
    _DRAW_CACHE[key] = out
    return out


def scene_draw(cv, data, t, dur, m, vd, sc):
    """
    Kit 'draw' (cinema jaisa): ek waqt me EK chitra poori chaudai me bada; ho chuke khaane upar chhote thumbnail
    (❌/✓ ke saath) - galat aur sahi ki tulna aankh ke saamne. Caption chitra ke neeche.
    """
    fx = {}
    panels = data["chitra"]["panels"]
    keys = ("c1", "c2", "c3")
    starts = [max(0.0, m[k][0] - 0.3) for k in keys]
    cur = max(i for i in range(3) if t >= starts[i] or i == 0)
    place(cv, pill_sprite("चित्र से समझो", 44, (30, 20, 0), YELLOW, ORANGE), W / 2, 285,
          scale=max(0.05, ease_out_back(prog(t, 0, 0.3))))
    # --- upar thumbnail strip (pichhle khaane) ---
    tw_, th_ = 300, int(300 * DRAW_H / DRAW_W)
    for j in range(cur):
        kj = ease_out_cubic(prog(t, starts[j + 1], 0.35))
        pn = panels[j]
        col = {"none": CYAN, "wrong": RED, "right": GREEN}[pn["mark"]]
        tx = 90 + tw_ / 2 + j * (tw_ + 40)
        ty = 470
        pic = render_drawing(pn["shapes"]).resize((tw_, th_), Image.LANCZOS)
        d0 = ImageDraw.Draw(cv)
        d0.rounded_rectangle((tx - tw_ / 2 - 6, ty - th_ / 2 - 6, tx + tw_ / 2 + 6, ty + th_ / 2 + 6), radius=18,
                             outline=col, width=5)
        place(cv, pic, tx, ty, alpha=clamp(kj * 1.5))
        if pn["mark"] in ("wrong", "right"):
            place(cv, (x_mark_sprite if pn["mark"] == "wrong" else check_sprite)(70), tx + tw_ / 2 - 8, ty - th_ / 2 + 8)
        d0.text((tx, ty + th_ / 2 + 26), f"{j + 1}", font=get_font(28), fill=col, anchor="mm")
    # --- abhi ka khaana: bada ---
    pn = panels[cur]
    k = ease_out_back(prog(t, starts[cur], 0.4))
    mk = pn["mark"]
    col = {"none": CYAN, "wrong": RED, "right": GREEN}[mk]
    bw = 960
    bh = int(bw * DRAW_H / DRAW_W)
    cy = 640 + bh / 2 - 20
    place(cv, glow_sprite(520, col, 45), W / 2, cy)
    d = ImageDraw.Draw(cv)
    pic = render_drawing(pn["shapes"]).resize((bw, bh), Image.LANCZOS)
    x = W / 2 + (1 - k) * 700
    d.rounded_rectangle((x - bw / 2 - 8, cy - bh / 2 - 8, x + bw / 2 + 8, cy + bh / 2 + 8), radius=30, outline=col,
                        width=7)
    place(cv, pic, x, cy, scale=1 + 0.01 * math.sin(t * 2.5))
    place(cv, pill_sprite(f"{cur + 1} / 3", 30, WHITE, (20, 30, 50), col), x - bw / 2 + 60, cy - bh / 2 + 36)
    key = keys[cur]
    if sc.get("exact_words"):
        kp, th = seg_progress(sc, key, t)
    else:
        a_, b_ = m[key]
        kp, th = clamp((t - a_ + EYE_LEAD) / max(0.3, b_ - a_)), None
    if key in CHITRA_SILENT:
        kp, th = 1.0, None
    txt_col = {"none": WHITE, "wrong": (255, 170, 170), "right": (170, 255, 190)}[mk]
    draw_kinetic(cv, pn["text"], W / 2, 0, 960, 56, max(kp, 0.001), max_lines=2, min_size=40, line_h=1.25,
                 center_y=cy + bh / 2 + 80, ghost=0.3, th=th, color=txt_col)
    t_mk = (m[key][0] + 0.35) if key in CHITRA_SILENT else (m[key][1] - 0.2)
    if mk in ("wrong", "right") and t >= t_mk:
        km = ease_out_back(prog(t, t_mk, 0.3))
        spr = x_mark_sprite(150) if mk == "wrong" else check_sprite(150)
        place(cv, spr, x + bw / 2 - 30, cy - bh / 2 + 30, scale=max(0.05, 1.6 - 0.6 * km))
        if mk == "wrong" and t - t_mk < 0.1:
            fx["shake"] = 8
        if mk == "right" and t - t_mk < 0.25:
            place(cv, glow_sprite(560, GREEN, int(120 * (1 - (t - t_mk) / 0.25))), x, cy)
    return fx


def scene_story(cv, data, t, dur, m, vd, sc):
    """
    'काम की कहानी' (chitra-kahani): 3 khaane, har khaane me BADA asli chitra (lifaafa/parcel/postcard + items)
    aur chhota caption. Galat khaana laal ❌, sahi hara ✓ - farak chitra me dikhta hai.
    """
    fx = {}
    steps = data["chitra"]["steps"]
    place(cv, pill_sprite("चित्र से समझो", 46, (30, 20, 0), YELLOW, ORANGE), W / 2, 300,
          scale=max(0.05, ease_out_back(prog(t, 0, 0.3))))
    ys = (560, 890, 1220)
    ph, pw = 300, 980
    keys = ("c1", "c2", "c3")
    for i, st in enumerate(steps):
        t0 = max(0.0, m[keys[i]][0] - 0.3)
        if t < t0:
            place(cv, card_sprite(pw, ph, (16, 26, 44), (40, 56, 80), 3, 34), W / 2, ys[i], alpha=0.35)
            place(cv, pill_sprite("?", 54, (150, 165, 190), (26, 38, 60), (60, 80, 110)), W / 2, ys[i], alpha=0.6)
            continue
        k = ease_out_back(prog(t, t0, 0.35))
        active = t < (m[keys[i + 1]][0] - 0.3 if i < 2 else 99)
        mk = st["mark"]
        col = {"none": CYAN, "wrong": RED, "right": GREEN}[mk]
        fill = {"none": (18, 34, 58), "wrong": (52, 18, 26), "right": (14, 50, 32)}[mk]
        x = W / 2 + (1 - k) * (-520 if i % 2 == 0 else 520)
        sc_ = 1.02 if active else 0.97
        place(cv, card_sprite(pw, ph, fill, col, 6 if active else 4, 34), x, ys[i], scale=sc_, alpha=clamp(k * 1.5))
        pic = story_picture(st, 450, 285)
        px_ = x - pw / 2 + 250
        place(cv, glow_sprite(170, col, 50 if active else 20), px_, ys[i])
        place(cv, pic, px_, ys[i] + (4 * math.sin(t * 3.5) if active else 0), scale=sc_,
              angle=(1.5 * math.sin(t * 2) if active else 0))
        d = ImageDraw.Draw(cv)
        d.text((x + 235, ys[i] - ph / 2 + 30), f"{i + 1}", font=get_font(30), fill=col, anchor="mm")
        if sc.get("exact_words"):
            kp, th = seg_progress(sc, keys[i], t)
        else:
            a_, b_ = m[keys[i]]
            kp, th = clamp((t - a_ + EYE_LEAD) / max(0.3, b_ - a_)), None
        if keys[i] in CHITRA_SILENT:
            kp, th = 1.0, None                          # bina awaaz wala khaana: text turant poora
        draw_kinetic(cv, st["text"], x + 235, 0, 440, 46, max(kp, 0.001), max_lines=3, min_size=32, line_h=1.25,
                     center_y=ys[i], ghost=0.3, th=th, color=WHITE)
        t_mk = (m[keys[i]][0] + 0.35) if keys[i] in CHITRA_SILENT else (m[keys[i]][1] - 0.2)
        if mk in ("wrong", "right") and t >= t_mk:
            km = ease_out_back(prog(t, t_mk, 0.3))
            spr = x_mark_sprite(110) if mk == "wrong" else check_sprite(110)
            place(cv, spr, x + pw / 2 - 40, ys[i] - ph / 2 + 30, scale=max(0.05, 1.5 - 0.5 * km))
            if mk == "wrong" and t - t_mk < 0.1:
                fx["shake"] = 7
        if i < 2 and t >= m[keys[i + 1]][0] - 0.45:
            d.polygon([(W / 2 - 24, ys[i] + ph / 2 + 2), (W / 2 + 24, ys[i] + ph / 2 + 2), (W / 2, ys[i] + ph / 2 + 30)],
                      fill=YELLOW)
    return fx


@lru_cache(maxsize=64)
def scene_pic_sprite(pic, label, size=170):
    ic = icon_sprite(pic, size)
    if not label:
        return ic
    lb = pill_sprite(label, 30, WHITE, (20, 30, 50), (90, 110, 140))
    w = max(ic.width, lb.width)
    im = Image.new("RGBA", (w, ic.height + lb.height - 10), (0, 0, 0, 0))
    im.paste(ic, ((w - ic.width) // 2, 0), ic)
    im.paste(lb, ((w - lb.width) // 2, ic.height - 10), lb)
    return im


def scene_compose(cv, data, t, dur, m, vd, sc):
    """Kit 4: har khaane me 1-3 chitra (label ke saath), teer, aur chhota caption; galat ❌ / sahi ✓."""
    fx = {}
    panels = data["chitra"]["panels"]
    place(cv, pill_sprite("चित्र से समझो", 46, (30, 20, 0), YELLOW, ORANGE), W / 2, 300,
          scale=max(0.05, ease_out_back(prog(t, 0, 0.3))))
    ys = (570, 900, 1230)
    ph, pw = 310, 1000
    keys = ("c1", "c2", "c3")
    for i, pn in enumerate(panels):
        t0 = max(0.0, m[keys[i]][0] - 0.3)
        if t < t0:
            place(cv, card_sprite(pw, ph, (16, 26, 44), (40, 56, 80), 3, 34), W / 2, ys[i], alpha=0.35)
            place(cv, pill_sprite("?", 54, (150, 165, 190), (26, 38, 60), (60, 80, 110)), W / 2, ys[i], alpha=0.6)
            continue
        k = ease_out_back(prog(t, t0, 0.35))
        active = t < (m[keys[i + 1]][0] - 0.3 if i < 2 else 99)
        mk = pn["mark"]
        col = {"none": CYAN, "wrong": RED, "right": GREEN}[mk]
        fill = {"none": (18, 34, 58), "wrong": (52, 18, 26), "right": (14, 50, 32)}[mk]
        x = W / 2 + (1 - k) * (-520 if i % 2 == 0 else 520)
        place(cv, card_sprite(pw, ph, fill, col, 6 if active else 4, 34), x, ys[i], scale=1.02 if active else 0.97,
              alpha=clamp(k * 1.5))
        n_ = len(pn["pics"])
        area_l, area_w = x - pw / 2 + 20, 600
        size_ = {1: 215, 2: 185, 3: 150}[n_]
        step_ = area_w / n_
        for j, p_ in enumerate(pn["pics"]):
            kj = ease_out_back(prog(t, t0 + 0.12 * j, 0.3))
            cx_ = area_l + step_ * (j + 0.5)
            place(cv, scene_pic_sprite(p_["pic"], p_["label"], size_), cx_, ys[i] + (5 * math.sin(t * 3.5 + j) if active else 0),
                  scale=max(0.05, kj))
            if pn["arrows"] and j < n_ - 1 and kj > 0.9:
                ax_ = area_l + step_ * (j + 1)
                d = ImageDraw.Draw(cv)
                d.line((ax_ - 22, ys[i], ax_ + 14, ys[i]), fill=YELLOW, width=7)
                d.polygon([(ax_ + 14, ys[i] - 13), (ax_ + 32, ys[i]), (ax_ + 14, ys[i] + 13)], fill=YELLOW)
        if sc.get("exact_words"):
            kp, th = seg_progress(sc, keys[i], t)
        else:
            a_, b_ = m[keys[i]]
            kp, th = clamp((t - a_ + EYE_LEAD) / max(0.3, b_ - a_)), None
        if keys[i] in CHITRA_SILENT:
            kp, th = 1.0, None                          # bina awaaz wala khaana: text turant poora
        draw_kinetic(cv, pn["text"], x + 315, 0, 330, 46, max(kp, 0.001), max_lines=4, min_size=30, line_h=1.25,
                     center_y=ys[i], ghost=0.3, th=th, color=WHITE)
        d = ImageDraw.Draw(cv)
        d.text((x + 315, ys[i] - ph / 2 + 28), f"{i + 1}", font=get_font(30), fill=col, anchor="mm")
        t_mk = (m[keys[i]][0] + 0.35) if keys[i] in CHITRA_SILENT else (m[keys[i]][1] - 0.2)
        if mk in ("wrong", "right") and t >= t_mk:
            km = ease_out_back(prog(t, t_mk, 0.3))
            spr = x_mark_sprite(110) if mk == "wrong" else check_sprite(110)
            place(cv, spr, x + pw / 2 - 40, ys[i] - ph / 2 + 30, scale=max(0.05, 1.5 - 0.5 * km))
            if mk == "wrong" and t - t_mk < 0.1:
                fx["shake"] = 7
        if i < 2 and t >= m[keys[i + 1]][0] - 0.45:
            d.polygon([(W / 2 - 24, ys[i] + ph / 2 + 2), (W / 2 + 24, ys[i] + ph / 2 + 2), (W / 2, ys[i] + ph / 2 + 22)],
                      fill=YELLOW)
    return fx


def scene_story_old(cv, data, t, dur, m, vd, sc):
    """
    'काम की कहानी': 3 khaane (comic strip) ek ke baad ek, awaaz ke saath - roz ka pal -> kadam/galti ❌ ->
    niyam ke hisaab se sahi ✓. Jo khaana bola ja raha, wo bada aur chamakta.
    """
    fx = {}
    steps = data["chitra"]["steps"]
    place(cv, pill_sprite("काम की कहानी", 46, (30, 20, 0), YELLOW, ORANGE), W / 2, 300,
          scale=max(0.05, ease_out_back(prog(t, 0, 0.3))))
    ys = (560, 890, 1220)
    ph, pw = 290, 960
    keys = ("c1", "c2", "c3")
    for i, st in enumerate(steps):
        t0 = max(0.0, m[keys[i]][0] - 0.3)
        if t < t0:
            # aane wala khaana: dhundhla khaka + "?" (aage kya hoga?)
            place(cv, card_sprite(pw, ph, (16, 26, 44), (40, 56, 80), 3, 34), W / 2, ys[i], alpha=0.35)
            place(cv, pill_sprite("?", 54, (150, 165, 190), (26, 38, 60), (60, 80, 110)), W / 2, ys[i], alpha=0.6)
            continue
        k = ease_out_back(prog(t, t0, 0.35))
        active = t < (m[keys[i + 1]][0] - 0.3 if i < 2 else 99)
        mk = st["mark"]
        col = {"none": CYAN, "wrong": RED, "right": GREEN}[mk]
        fill = {"none": (18, 34, 58), "wrong": (52, 18, 26), "right": (14, 50, 32)}[mk]
        x = W / 2 + (1 - k) * (-520 if i % 2 == 0 else 520)
        sc_ = (1.03 if active else 0.97)
        place(cv, card_sprite(pw, ph, fill, col, 6 if active else 4, 34), x, ys[i], scale=sc_,
              alpha=clamp(k * 1.5) * (1.0 if active or mk != "none" else 0.8))
        place(cv, glow_sprite(120, col, 70 if active else 30), x - pw / 2 + 150, ys[i])
        place(cv, icon_sprite(st["icon"], 190), x - pw / 2 + 150, ys[i] + (6 * math.sin(t * 4) if active else 0),
              scale=sc_)
        d = ImageDraw.Draw(cv)
        d.text((x - pw / 2 + 290, ys[i] - ph / 2 + 36), f"{i + 1}", font=get_font(34), fill=col, anchor="mm")
        if sc.get("exact_words"):
            kp, th = seg_progress(sc, keys[i], t)
        else:
            a_, b_ = m[keys[i]]
            kp, th = clamp((t - a_ + EYE_LEAD) / max(0.3, b_ - a_)), None
        if keys[i] in CHITRA_SILENT:
            kp, th = 1.0, None                          # bina awaaz wala khaana: text turant poora
        draw_kinetic(cv, st["text"], x + 110, 0, 600, 50, max(kp, 0.001), max_lines=3, min_size=34, line_h=1.25,
                     center_y=ys[i], ghost=0.3, th=th, color=WHITE)
        t_mk = (m[keys[i]][0] + 0.35) if keys[i] in CHITRA_SILENT else (m[keys[i]][1] - 0.2)
        if mk in ("wrong", "right") and t >= t_mk:
            km = ease_out_back(prog(t, t_mk, 0.3))
            spr = x_mark_sprite(110) if mk == "wrong" else check_sprite(110)
            place(cv, spr, x + pw / 2 - 40, ys[i] - ph / 2 + 30, scale=max(0.05, 1.5 - 0.5 * km))
            if mk == "wrong" and t - t_mk < 0.1:
                fx["shake"] = 7
        if i < 2 and t >= m[keys[i + 1]][0] - 0.45:
            d.polygon([(W / 2 - 24, ys[i] + ph / 2 + 4), (W / 2 + 24, ys[i] + ph / 2 + 4), (W / 2, ys[i] + ph / 2 + 36)],
                      fill=YELLOW)
    return fx


# ==================== KIT "photo" ka chitran: asli chitra + dheema zoom (documentary) + ghera + Hindi parchi ====================
_PHOTO_CACHE = {}
PHOTO_ZOOM = 0.12             # khaane ke dauraan mukhya cheez ki taraf itna dheema zoom
TAG_COLORS = {"red": (WHITE, (200, 30, 45), (120, 10, 20)), "green": (WHITE, (22, 140, 70), (10, 90, 40)),
              "dark": (WHITE, (30, 40, 70), (15, 20, 40))}
MARK_COLORS = {"none": YELLOW, "wrong": RED, "right": GREEN}


def photo_base(path):
    im = _PHOTO_CACHE.get(path)
    if im is None:
        im = Image.open(path).convert("RGB")
        _PHOTO_CACHE[path] = im
    return im


def photo_frame(pn, size, zk=0.0, rk=1.0, tk=1.0):
    """
    Ek khaane ka chitra (size x size): zk = zoom (0-1), rk = ghera (0-1), tk = parchi (0-1).
    Zoom mukhya cheez (box) ki taraf; ghera aur parchi box ke saath chalte hain.
    """
    base = photo_base(pn["img"])
    bw, bh = base.size
    side = min(bw, bh)
    box = pn.get("box") or [0.3, 0.3, 0.7, 0.7]
    fx, fy = (box[0] + box[2]) / 2 * bw, (box[1] + box[3]) / 2 * bh
    z = 1.0 + PHOTO_ZOOM * ease_in_out(clamp(zk))
    win = side / z
    cx = bw / 2 + (fx - bw / 2) * (z - 1) / PHOTO_ZOOM * 0.7 if PHOTO_ZOOM else bw / 2
    cy = bh / 2 + (fy - bh / 2) * (z - 1) / PHOTO_ZOOM * 0.7 if PHOTO_ZOOM else bh / 2
    x0 = min(max(cx - win / 2, 0), bw - win)
    y0 = min(max(cy - win / 2, 0), bh - win)
    im = base.crop((int(x0), int(y0), int(x0 + win), int(y0 + win))).resize((size, size), Image.BILINEAR).convert("RGBA")
    s = size / win
    bx0, by0 = (box[0] * bw - x0) * s, (box[1] * bh - y0) * s
    bx1, by1 = (box[2] * bw - x0) * s, (box[3] * bh - y0) * s
    col = MARK_COLORS.get(pn.get("mark"), YELLOW)
    if rk > 0:
        k = ease_out_back(clamp(rk))
        grow = (1 - k) * 0.25
        pw, ph = (bx1 - bx0), (by1 - by0)
        pad = 10 * size / 900
        r0 = (bx0 - pad - pw * grow / 2, by0 - pad - ph * grow / 2, bx1 + pad + pw * grow / 2, by1 + pad + ph * grow / 2)
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        a = int(255 * clamp(rk * 2))
        wid = max(4, int(11 * size / 900))
        d.rounded_rectangle(r0, radius=int(28 * size / 900), outline=(0, 0, 0, a // 2), width=wid + 6)
        d.rounded_rectangle(r0, radius=int(28 * size / 900), outline=col + (a,), width=wid)
        im.alpha_composite(ov)
    if tk > 0 and pn.get("tag"):
        fg, bg, ol = TAG_COLORS.get(pn.get("tag_color"), TAG_COLORS["dark"])
        pl = pill_sprite(pn["tag"], max(18, int(46 * size / 900)), fg, bg, ol)
        k = ease_out_back(clamp(tk))
        if k < 0.999:
            pl = pl.resize((max(1, int(pl.width * max(0.05, k))), max(1, int(pl.height * max(0.05, k)))), Image.LANCZOS)
        tx = min(max((bx0 + bx1) / 2, pl.width / 2 + 8), size - pl.width / 2 - 8)
        ty = min(max(by0 + (by1 - by0) * 0.35, pl.height / 2 + 8), size - pl.height / 2 - 8)
        im.alpha_composite(pl, (int(tx - pl.width / 2), int(ty - pl.height / 2)))
    return im


def ease_in_out(x):
    return x * x * (3 - 2 * x)


def photo_still(pn, size):
    key = (pn["img"], size, pn.get("tag"), tuple(pn.get("box") or ()))
    im = _PHOTO_CACHE.get(key)
    if im is None:
        im = photo_frame(pn, size, 0.0, 1.0, 1.0)
        _PHOTO_CACHE[key] = im
    return im


def _round_mask(im, radius):
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=radius, fill=255)
    out = im.copy()
    out.putalpha(ImageChops.multiply(out.getchannel("A"), m))
    return out


PHOTO_SIZE = 880
PHOTO_CY = 830


def scene_photo(cv, data, t, dur, m, vd, sc):
    """
    Kit 'photo': ek waqt me EK bada asli chitra; awaaz ke saath dheema zoom mukhya cheez ki taraf, phir ghera
    aur Hindi parchi; galat khaane pe ❌ + jhatka, sahi pe ✓ + chamak. Teesre khaane me kone me galat wala chhota chitra.
    """
    fx = {}
    panels = data["chitra"]["panels"]
    keys = ("c1", "c2", "c3")
    starts = [max(0.0, m[k][0] - 0.3) for k in keys]
    cur = max(i for i in range(3) if t >= starts[i] or i == 0)
    place(cv, pill_sprite("चित्र से समझो", 44, (30, 20, 0), YELLOW, ORANGE), W / 2, 285,
          scale=max(0.05, ease_out_back(prog(t, 0, 0.3))))
    pn = panels[cur]
    mk = pn["mark"]
    col = {"none": CYAN, "wrong": RED, "right": GREEN}[mk]
    t0 = starts[cur]
    t1 = starts[cur + 1] if cur < 2 else dur
    k_in = ease_out_cubic(prog(t, t0, 0.45))
    S = PHOTO_SIZE
    zk = clamp((t - t0) / max(0.5, t1 - t0))
    a_, b_ = m[keys[cur]]
    rk = prog(t, a_ + 0.35, 0.45)
    tk = prog(t, a_ + 0.7, 0.4)
    pic = _round_mask(photo_frame(pn, S, zk, rk, tk), 36)
    x = W / 2 + (1 - k_in) * 760 * (1 if cur else 0)
    alpha = clamp(k_in * 1.4) if cur else clamp(prog(t, t0, 0.35) * 1.4)
    place(cv, glow_sprite(500, col, 40), x, PHOTO_CY)
    d = ImageDraw.Draw(cv)
    d.rounded_rectangle((x - S / 2 - 8, PHOTO_CY - S / 2 - 8, x + S / 2 + 8, PHOTO_CY + S / 2 + 8), radius=42,
                        outline=col, width=7)
    place(cv, pic, x, PHOTO_CY, alpha=alpha)
    place(cv, pill_sprite(f"{cur + 1} / 3", 30, WHITE, (20, 30, 50), col), x - S / 2 + 62, PHOTO_CY - S / 2 + 38)
    if cur == 2 and panels[1]["mark"] == "wrong":         # tulna: galat wala chhota chitra kone me
        ki = ease_out_back(prog(t, t0 + 0.5, 0.35))
        if ki > 0.02:
            th = _round_mask(photo_still(panels[1], 240), 20)
            tx_, ty_ = x - S / 2 + 150, PHOTO_CY + S / 2 - 150
            d.rounded_rectangle((tx_ - 126, ty_ - 126, tx_ + 126, ty_ + 126), radius=24, fill=(20, 24, 40), outline=RED, width=6)
            place(cv, th, tx_, ty_, scale=max(0.05, ki))
            place(cv, x_mark_sprite(70), tx_ + 105, ty_ - 105, scale=max(0.05, ki))
    key = keys[cur]
    if sc.get("exact_words"):
        kp, th_ = seg_progress(sc, key, t)
    else:
        kp, th_ = clamp((t - a_ + EYE_LEAD) / max(0.3, b_ - a_)), None
    txt_col = {"none": WHITE, "wrong": (255, 170, 170), "right": (170, 255, 190)}[mk]
    draw_kinetic(cv, pn["text"], W / 2, 0, 980, 56, max(kp, 0.001), max_lines=2, min_size=40, line_h=1.25,
                 center_y=PHOTO_CY + S / 2 + 105, ghost=0.3, th=th_, color=txt_col)
    t_mk = b_ - 0.2
    if mk in ("wrong", "right") and t >= t_mk:
        km = ease_out_back(prog(t, t_mk, 0.3))
        spr = x_mark_sprite(160) if mk == "wrong" else check_sprite(160)
        place(cv, spr, x + S / 2 - 40, PHOTO_CY - S / 2 + 40, scale=max(0.05, 1.6 - 0.6 * km))
        if mk == "wrong" and t - t_mk < 0.1:
            fx["shake"] = 8
        if mk == "right" and t - t_mk < 0.25:
            place(cv, glow_sprite(560, GREEN, int(120 * (1 - (t - t_mk) / 0.25))), x, PHOTO_CY)
    return fx


def save_chitra_preview(part, path):
    """Namoona: teeno chitra (parchi + ghera ke saath) + caption ek PNG me - reel banne se pehle dekhne ke liye."""
    panels = (part.get("chitra_v") or {}).get("panels") or []
    S, pad = 600, 30
    out = Image.new("RGB", (pad + 3 * (S + pad), S + 260), (12, 20, 40))
    d = ImageDraw.Draw(out)
    for i, pn in enumerate(panels):
        x = pad + i * (S + pad)
        col = {"none": CYAN, "wrong": RED, "right": GREEN}[pn["mark"]]
        d.rounded_rectangle((x - 6, pad - 6, x + S + 6, pad + S + 6), radius=24, outline=col, width=6)
        out.paste(photo_still(pn, S).convert("RGB"), (x, pad))
        f, s_, lines = fit_lines(pn["text"], S - 20, 3, 34, 24)
        for j, ln in enumerate(lines):
            d.text((x + S / 2, pad + S + 50 + j * s_ * 1.3), " ".join(ln), font=f, fill=WHITE, anchor="mm")
        d.text((x + 30, pad + 30), f"{i + 1}", font=get_font(40), fill=col, anchor="mm")
    out.save(path)
    return path


def scene_chitra(cv, data, t, dur, m, vd, sc):
    """
    Counter pe article aata hai (c1) -> galat jagah item chipakta hai, camera zoom, magnifier, ❌ (c2) ->
    sahi (c3): item hat-ta hai / sahi jagah jaata hai, ✓. Sab kuch storyboard (examiner-pass) ke hisaab se.
    """
    if data["chitra"].get("kit") == "story":
        return scene_story(cv, data, t, dur, m, vd, sc)
    if data["chitra"].get("kit") == "scene":
        return scene_compose(cv, data, t, dur, m, vd, sc)
    if data["chitra"].get("kit") == "draw":
        return scene_draw(cv, data, t, dur, m, vd, sc)
    if data["chitra"].get("kit") == "photo":
        return scene_photo(cv, data, t, dur, m, vd, sc)
    if data["chitra"].get("kit") == "address":
        return scene_address(cv, data, t, dur, m, vd, sc)
    fx = {}
    cfg = data["chitra"]
    obj, item, wp, rp = cfg["object"], cfg["item"], cfg["wrong_place"], cfg["right"]
    tw = max(0.9, m["c2"][0] - 0.35)                  # galat pal (awaaz se thoda pehle)
    tr = max(tw + 1.0, m["c3"][0] - 0.3)              # sahi pal
    cv.paste(counter_layer(), (0, 0), counter_layer())
    # article entrance (graahak ka haath counter pe rakhta hai)
    e = ease_out_cubic(prog(t, 0.0, 0.55))
    ax = W / 2 + (1 - e) * 620
    ay = ART_CY + (1 - e) * 260
    rot = (1 - e) * 9 - 1.5
    flip_back = (wp == "back" and t >= tw - 0.35) or (rp == "back" and t >= tr - 0.35)
    if wp == "back" and t >= tr - 0.35 and rp != "back":
        flip_back = False
    place(cv, soft_shadow(ART_W, ART_H), ax + 18, ay + 26, angle=rot)
    art = article_sprite(obj, back=flip_back and obj == "envelope", no_stamp=(item == "postage_stamp")).copy()
    # item par article pe (rotation se pehle, taaki saath ghoome)
    it = item_sprite(item)
    ph_w = prog(t, tw, 0.3) if t >= tw else 0.0
    ph_r = prog(t, tr, 0.5) if t >= tr else 0.0
    def put(pl, k_in, alpha=1.0, lift=0.0, spin=0.0):
        if pl == "back":
            cx_, cy_ = 0, 0
        else:
            cx_, cy_ = _region_center(obj, pl)
        s_ = 1.8 - 0.8 * ease_out_back(k_in)
        spr = it.rotate(-6 + spin, expand=True, resample=Image.BICUBIC)
        spr = spr.resize((max(1, int(spr.width * s_)), max(1, int(spr.height * s_))), Image.BILINEAR)
        if alpha < 0.99:
            spr.putalpha(spr.getchannel("A").point(lambda v: int(v * alpha)))
        art.paste(spr, (int(ART_W / 2 + cx_ - spr.width / 2), int(ART_H / 2 + cy_ - lift - spr.height / 2)), spr)
    if t >= tw and (t < tr or rp != "remove" or ph_r < 1):
        if t < tr:
            put(wp, ph_w)
        elif rp == "remove":
            put(wp, 1.0, alpha=1 - ph_r, lift=160 * ph_r, spin=25 * ph_r)       # ukhad ke udta hai
        else:
            put(rp, 1.0)
    # galat pal: pata/jagah ke chaaron taraf laal dhaari; sahi pal: hari
    dd = ImageDraw.Draw(art)
    if tw + 0.35 <= t < tr and wp != "back":
        r = _art_regions(obj)[wp]
        a_ = int(160 + 90 * math.sin(t * 10))
        dd.rounded_rectangle((r[0] - 6, r[1] - 6, r[2] + 6, r[3] + 6), radius=10, outline=RED + (a_,), width=7)
    if t >= tr + 0.3:
        if rp in ("remove",):                          # pata ab saaf -> pate pe hara ghera
            r = _art_regions(obj)["address"]
        elif rp == "back":                             # peeth pe pata nahi hota -> item ke chaaron taraf
            r = (ART_W / 2 - 190, ART_H / 2 - 110, ART_W / 2 + 190, ART_H / 2 + 110)
        else:                                          # item ki sahi jagah pe
            r = _art_regions(obj)[rp]
        dd.rounded_rectangle((r[0] - 6, r[1] - 6, r[2] + 6, r[3] + 6), radius=10, outline=GREEN + (230,), width=7)
    place(cv, art, ax, ay, angle=rot + (0.8 * math.sin(t * 1.3) if e >= 1 else 0))
    if tw <= t < tw + 0.12:
        fx["shake"] = 9
    # magnifier galat jagah pe dhoondhta hai
    if tw + 0.4 <= t < tr and wp != "back":
        cx_, cy_ = _region_center(obj, wp)
        p_ = t - tw - 0.4
        lx = ax + cx_ + 110 * math.sin(p_ * 3.0)
        ly = ay + cy_ + 50 * math.cos(p_ * 2.2)
        d = ImageDraw.Draw(cv)
        d.line((lx + 70, ly + 70, lx + 160, ly + 160), fill=(60, 45, 30), width=30)
        d.ellipse((lx - 100, ly - 100, lx + 100, ly + 100), outline=(50, 50, 60), width=18)
        d.ellipse((lx - 100, ly - 100, lx + 100, ly + 100), outline=(215, 225, 240), width=7)
        if t >= tw + 0.9:
            kq = ease_out_back(prog(t, tw + 0.9, 0.3))
            place(cv, pill_sprite("?", 76, WHITE, (160, 30, 40), RED), lx, ly, scale=max(0.05, kq))
    # camera: galat pal pe jagah ki taraf zoom, sahi pal pe wapas
    zin = ease_in_out(prog(t, tw + 0.1, 0.5)) * (1 - ease_in_out(prog(t, tr, 0.5)))
    if zin > 0.01 and wp != "back":
        cx_, cy_ = _region_center(obj, wp)
        z = 1 + 0.28 * zin
        top_z = 540                                   # takhti/label ke neeche ka hissa hi zoom ho
        fxp, fyp = ax + cx_ * zin, ay + cy_ * zin
        bw, bh = W / z, (H - top_z) / z
        x0 = min(max(0, fxp - bw / 2), W - bw)
        y0 = min(max(top_z, fyp - bh / 2), H - bh)
        cv.paste(cv.crop((int(x0), int(y0), int(x0 + bw), int(y0 + bh))).resize((W, H - top_z), Image.BILINEAR),
                 (0, top_z))
    # upar ka label + ❌/✓ (zoom ke baad, taaki saaf rahe)
    place(cv, pill_sprite("चित्र से समझो", 46, (30, 20, 0), YELLOW, ORANGE), W / 2, 300,
          scale=max(0.05, ease_out_back(prog(t, 0, 0.3))))
    if tw + 0.5 <= t < tr:
        place(cv, x_mark_sprite(150), W - 170, 640, scale=max(0.05, 1.6 - 0.6 * ease_out_back(prog(t, tw + 0.5, 0.25))))
    if t >= tr + 0.3:
        place(cv, check_sprite(150), W - 170, 640, scale=max(0.05, ease_out_back(prog(t, tr + 0.3, 0.3))))
        if t < tr + 0.5:
            place(cv, glow_sprite(500, GREEN, int(120 * (1 - prog(t, tr + 0.3, 0.2)))), ax, ay)
    # caption (jo bola ja raha hai) - neeche, gehre patte pe
    key = "c1" if t < m["c2"][0] - EYE_LEAD else ("c2" if t < m["c3"][0] - EYE_LEAD else "c3")
    col = {"c1": WHITE, "c2": (255, 150, 150), "c3": (150, 255, 180)}[key]
    txt = cfg["caps"][int(key[1]) - 1]
    place(cv, card_sprite(1000, 160, (10, 16, 30), mix((10, 16, 30), col, 0.6), 4, 34), W / 2, 1365)
    if sc.get("exact_words"):
        kp, th = seg_progress(sc, key, t)
    else:
        a_, b_ = m[key]
        kp, th = clamp((t - a_ + EYE_LEAD) / max(0.3, b_ - a_)), None
    if key in CHITRA_SILENT:
        kp, th = 1.0, None
    draw_kinetic(cv, txt, W / 2, 0, 930, 54, max(kp, 0.001), max_lines=2, min_size=38, line_h=1.25,
                 center_y=1365, ghost=0.3, th=th, color=col)
    return fx


def chitra_thumb(cfg, w=250):
    """Hook ke liye chhota lifaafa - galat jagah item ke saath (jawab nahi batata, bas 'kuch gadbad hai')."""
    key = (cfg["object"], cfg["item"], cfg["wrong_place"], w)
    if key in _THUMBS:
        return _THUMBS[key]
    art = article_sprite(cfg["object"], back=(cfg["wrong_place"] == "back" and cfg["object"] == "envelope"),
                         no_stamp=(cfg["item"] == "postage_stamp")).copy()
    it = item_sprite(cfg["item"]).rotate(-6, expand=True, resample=Image.BICUBIC)
    cx_, cy_ = (0, 0) if cfg["wrong_place"] == "back" else _region_center(cfg["object"], cfg["wrong_place"])
    art.paste(it, (int(ART_W / 2 + cx_ - it.width / 2), int(ART_H / 2 + cy_ - it.height / 2)), it)
    h = int(w * ART_H / ART_W)
    im = art.resize((w, h), Image.LANCZOS)
    _THUMBS[key] = im
    return im


_THUMBS = {}


def chitra_story_en(cfg):
    """Examiner ke liye drishya ka seedha varnan (jo screen pe dikhega)."""
    if cfg.get("kit") == "photo":
        mk = {"none": "", "wrong": " - shown as WRONG (red X)", "right": " - shown as the CORRECT way (green tick)"}
        return "A 3-panel illustrated picture story of daily post office work: " + "; ".join(
            f"panel {i + 1}: {x['desc']}" + (f" (Hindi label '{x['tag']}' pasted on {x['target']})" if x.get("tag") else "")
            + f", caption '{x['text']}'{mk[x['mark']]}" for i, x in enumerate(cfg["panels"]))
    if cfg.get("kit") == "draw":
        mk = {"none": "", "wrong": " - shown as WRONG (red X)", "right": " - shown as the CORRECT way (green tick)"}
        return "A 3-panel drawn picture story of daily post office work: " + "; ".join(
            f"panel {i + 1}: {x['desc']} caption '{x['text']}'{mk[x['mark']]}" for i, x in enumerate(cfg["panels"]))
    if cfg.get("kit") == "scene":
        mk = {"none": "", "wrong": " - shown as WRONG (red X)", "right": " - shown as the CORRECT way (green tick)"}
        def _pn(x):
            ps = (" -> " if x["arrows"] else " and ").join(
                f"picture of a {p_['pic']}" + (f" labelled '{p_['label']}'" if p_["label"] else "") for p_ in x["pics"])
            return ps
        return "A 3-panel picture story of daily post office work: " + "; ".join(
            f"panel {i + 1}: {_pn(x)}, caption '{x['text']}'{mk[x['mark']]}" for i, x in enumerate(cfg["panels"]))
    if cfg.get("kit") == "address":
        lines = {"name": "the addressee's name", "house": "the house/street line", "village": "the village/PO line",
                 "post_town": "the post town (e.g. PATNA)", "pin": "the PIN code", "district": "the district line"}
        wrong = {"small": "written in small/lower-case letters", "missing": "left out", "unclear": "written unclearly"}
        right = {"block_caps_underline": "written in BLOCK CAPITALS and underlined", "block_caps": "written in BLOCK CAPITALS",
                 "clear": "written clearly", "present": "written in"}
        return (f"At the post office sorting rack, an envelope with a normal Indian address in English. First "
                f"{lines[cfg['line']]} is {wrong[cfg['wrong']]}; the letter gets stuck between rack boxes, red X. Then "
                f"it is {right[cfg['right']]}, and the letter goes straight into the correct box, green tick. "
                f"Captions: 1) {cfg['caps'][0]} 2) {cfg['caps'][1]} 3) {cfg['caps'][2]}")
    if cfg.get("kit") == "story":
        mk = {"none": "", "wrong": " - shown as WRONG (red X)", "right": " - shown as the CORRECT way (green tick)"}
        nm = {"wax_seal": "sealing-wax seal", "postage_stamp": "postage stamp", "festive_seal": "decorative festival seal",
              "shop_sticker": "shop sticker", "tissue_paper": "piece of tissue/thin paper",
              "thick_cloth": "piece of thick cotton cloth", "plastic_sheet": "plastic sheet", "twine": "twine knot"}
        def _pic(x):
            obj = x.get("object") or x.get("icon")
            its = ", then on top of it ".join(
                f"{i['count']} {nm.get(i['item'], i['item'])}(s) on the {i['place'].replace('_', ' ')}"
                for i in x.get("items") or [])
            return f"a {obj}" + (f" with {its}" if its else " with nothing extra on it" if obj in STORY_ARTICLES else "")
        return "A 3-panel picture story of daily post office work: " + "; ".join(
            f"panel {i + 1}: picture of {_pic(x)}, caption '{x['text']}'{mk[x['mark']]}" for i, x in enumerate(cfg["steps"]))
    names = {"festive_seal": "a decorative festival seal (non-postal, 'शुभ दीपावली')",
             "shop_sticker": "a shop's sticker (non-postal label, 'गुप्ता स्टोर्स')",
             "postage_stamp": "a postage stamp"}
    places = {"address": "on the ADDRESS area (covering part of the address)", "stamp_corner": "in the top-right stamp corner",
              "top_left": "in the top-left corner", "back": "on the BACK side"}
    right = "then it is removed and the address side is left clear" if cfg["right"] == "remove" else \
        f"then it is moved {places[cfg['right']]} and this is shown as correct"
    return (f"A customer hands a {cfg['object']} at the post office counter (normal Indian address with PIN). "
            f"{names[cfg['item']]} is stuck {places[cfg['wrong_place']]}; this is marked WRONG with a red X; {right}; "
            f"a green tick. Captions in order: 1) {cfg['caps'][0]} 2) {cfg['caps'][1]} 3) {cfg['caps'][2]}")


def hook_line(data):
    """Pehle: examiner-pass 'roz ke kaam' ka drishya. Na ho to: vishay + tay dhaancha."""
    if data.get("scene_line"):
        return data["scene_line"]
    t = re.sub(r"\s+", " ", (data.get("title") or "")).strip(" ।:-")
    i = int(data.get("episode") or 0) % len(HOOK_TEMPLATES)
    if t and len(t.split()) <= 5 and len(t) <= 28:
        return HOOK_TEMPLATES[i].format(t=t)
    return HOOK_TEMPLATES_NOTOPIC[i]


def hook_q_size(question):
    """Pehle frame ka headline: asli sawal, jitna bada ho sake (3 line tak)."""
    for sz in (80, 76, 72, 68, 64, 60, 56, 52, 48):
        _, s2, ls = fit_lines(question, 960, 3, sz, sz)
        if len(ls) <= 3 and int(s2 * 1.28) * len(ls) <= 330:
            return sz
    return 46


HOOK_QC = 575                         # headline sawal ka beech


def scene_hook_pro(cv, data, t, dur, m, vd, sc):
    """
    Pehla frame = ek hi kaam: 'kya poochha ja raha hai' turant samajh aaye.
    Upar chhota EXAM TRAP tag, beech me ASLI sawal bada (awaaz usi pal se bolti hai, bolta shabd peela),
    neeche do jawab aamne-saamne (VS) -> "inme se kaun?" ki jigyasa.
    """
    fx = {}
    ep = data.get("episode")
    if ep:
        place(cv, series_banner(int(ep), SEASON, bool(data.get("new_badge"))), W / 2, 290,
              scale=0.66 + 0.04 * ease_out_back(prog(t, 0, 0.25)))
    # 1) jigyasa line - frame 0 se poori, badi, peeli (scroll rokne wali)
    hl = data.get("hook_line") or hook_line(data)
    icx, icy = 175, 490
    tx0 = 300 if data.get("icon") else 50               # icon ho to text daayein
    tw = W - 60 - tx0
    f, s_, lines = fit_lines(hl, tw, 2, 78 if not data.get("scene_line") else 68, 48)
    lh = int(s_ * 1.25)
    lay = Image.new("RGBA", (int(tw) + 40, lh * len(lines) + 40), (0, 0, 0, 0))
    dl = ImageDraw.Draw(lay)
    for k_, ln in enumerate(lines):
        dl.text((lay.width / 2, 20 + lh * k_ + lh / 2), " ".join(ln), font=f, fill=YELLOW + (255,), anchor="mm",
                stroke_width=6, stroke_fill=(5, 10, 22, 255))
    place(cv, lay, tx0 + tw / 2, icy, scale=1 + 0.02 * math.sin(t * 8))
    if data.get("chitra") and data["chitra"]["kit"] in ("article_mark", "draw", "photo"):
        if data["chitra"]["kit"] == "photo":
            th_ = _round_mask(photo_still(data["chitra"]["panels"][1], 220), 22)
        else:
            th_ = chitra_thumb(data["chitra"]) if data["chitra"]["kit"] == "article_mark" else \
                render_drawing(data["chitra"]["panels"][1]["shapes"]).resize((250, 156), Image.LANCZOS)
        place(cv, glow_sprite(170, RED, 80), icx, icy)
        place(cv, th_, icx, icy + 6 * math.sin(t * 4.2), angle=4 * math.sin(t * 2.6))
    elif data.get("icon"):
        # chitra: halka uchhalta + dolta; peeche chamak
        place(cv, glow_sprite(170, CYAN, 90), icx, icy)
        place(cv, icon_sprite(data["icon"], 210), icx, icy + 8 * math.sin(t * 4.2),
              angle=5 * math.sin(t * 2.6))
    # 2) asli sawal (bilkul wahi) - awaaz ke saath shabd-dar-shabd
    sz = min(hook_q_size(data["question"]), 64)
    if sc.get("exact_words") and "q" in m:
        qp, th = seg_progress(sc, "q", t)
    else:
        qp, th = 1.0, None
    draw_kinetic(cv, data["question"], W / 2, 0, 960, sz, qp, max_lines=3, min_size=44, line_h=1.28,
                 center_y=HOOK_QC + 150, ghost=1.0, th=th, karaoke=bool(sc.get("exact_words")),
                 hl_words=hook_highlights(data["question"]), hl_color=CYAN)
    pair = data["vs_pair"]
    letter = {txt: l for l, txt in data["options"]}
    cy0 = VS_Y + 150
    if HOOK_ANIM == "scale":
        # TARAAZU: dono jawab ek beam pe. Beam jhoolta hai - kabhi A bhaari, kabhi B - kabhi tay nahi hota.
        # Neeche beech me sikka palatta hai (A / B / ?). Aankh do cheezon ke beech atki rehti hai.
        ang = 7.5 * math.sin(t * 3.3) * (1 - 0.25 * math.exp(-t * 2))     # degree; frame 0 pe seedha
        rad = math.radians(ang)
        half = (GRID_X[1] - GRID_X[0]) / 2
        piv_y = cy0 + TILE_H / 2 + 46
        heavy = 0 if ang > 0 else 1                  # jo neeche jhuka, wo "bhaari" (chamakta)
        # beam + pivot
        d = ImageDraw.Draw(cv)
        L = half * 1.18
        bx0, by0 = W / 2 - L * math.cos(rad), piv_y + L * math.sin(rad)     # ang > 0: baayan neeche
        bx1, by1 = W / 2 + L * math.cos(rad), piv_y - L * math.sin(rad)
        d.line((bx0, by0, bx1, by1), fill=(255, 205, 60), width=12)
        d.polygon([(W / 2, piv_y - 6), (W / 2 - 46, piv_y + 70), (W / 2 + 46, piv_y + 70)], fill=(200, 150, 30))
        d.ellipse((W / 2 - 14, piv_y - 20, W / 2 + 14, piv_y + 8), fill=(255, 225, 120))
        for side, txt in enumerate(pair):
            l = letter.get(txt, "?")
            sgn = -1 if side == 0 else 1
            x = W / 2 + sgn * half * math.cos(rad)
            y = cy0 - sgn * half * math.sin(rad)
            eo = data.get("en_opt", {}).get(l, "") if en_on("options") else ""
            is_heavy = side == heavy and abs(ang) > 2.5
            place(cv, tile_sprite(l, txt, eo, "active" if is_heavy else "vs"), x, y,
                  scale=1.04 if is_heavy else 0.98, angle=ang * 0.6)
            if is_heavy:
                place(cv, glow_sprite(160, CYAN, 60), x, y + TILE_H / 2 + 10)
        if ANIM_SET == "flip":
            for side in (0, 1):
                x = W / 2 + (-1 if side == 0 else 1) * half * math.cos(rad)
                y = cy0 + (half * math.sin(rad) if side == 0 else -half * math.sin(rad))
                sheen(cv, x, y, TILE_W, TILE_H, t, period=1.6, offset=0.35 * side)
        # beech me palatta sikka: A -> ? -> B -> ?  (kaun?)
        # "?" se shuru (pehle frame pe koi akshar nahi - warna sahi jawab ka ishaara ban sakta)
        faces = [pill_sprite("?", 58, WHITE, (70, 40, 140), PURPLE),
                 pill_sprite(letter.get(pair[0], "?"), 58, (30, 18, 0), YELLOW, ORANGE),
                 pill_sprite("?", 58, WHITE, (70, 40, 140), PURPLE),
                 pill_sprite(letter.get(pair[1], "?"), 58, (30, 18, 0), YELLOW, ORANGE)]
        cyc = t / 0.42
        i_ = int(cyc) % 4
        place(cv, glow_sprite(110, YELLOW, 150), W / 2, piv_y + 36)
        place_flip(cv, faces[i_], faces[(i_ + 1) % 4], W / 2, piv_y + 36, cyc - int(cyc))
        if t > 0.05 and abs(math.sin(t * 3.3)) > 0.985:
            fx["shake"] = 3                           # jhukne ke chhor pe halka thud
    else:
        flip = int(t / 0.55) % 2 == 0
        for side, txt in enumerate(pair):
            l = letter.get(txt, "?")
            active = (side == 0) == flip
            eo = data.get("en_opt", {}).get(l, "") if en_on("options") else ""
            place(cv, tile_sprite(l, txt, eo, "active" if active else "vs"), GRID_X[side], cy0,
                  scale=1.04 if active else 1.0)
        if ANIM_SET == "flip":
            for side in (0, 1):
                sheen(cv, GRID_X[side], cy0, TILE_W, TILE_H, t, period=1.6, offset=0.35 * side)
        pulse = 1 + 0.06 * math.sin(t * 10)
        place(cv, glow_sprite(100, YELLOW, 170), W / 2, cy0)
        place(cv, pill_sprite("या", 50, (30, 18, 0), YELLOW, ORANGE), W / 2, cy0, scale=pulse)
    kc = ease_out_back(prog(t, 0.7, 0.3)) if t >= 0.7 else 0.0
    if kc > 0.01:
        place(cv, pill_sprite("आपका जवाब? कमेंट करो!", 42, (30, 20, 0), YELLOW, ORANGE), W / 2, 1400,
              scale=max(0.05, kc) * (1 + 0.03 * math.sin(t * 9)))
    return fx


def scene_kaam_pro(cv, data, t, dur, m, vd, sc):
    """
    'आपके काम में': niyam -> roz ka kaam (awaaz ke saath). Fir header badal ke 'अच्छा... इसलिए ये नियम है!',
    neeche yaad-sutra, FREE MOCK aur course progress - alag CTA scene nahi (ant chhota aur saaf).
    """
    fx = {}
    k = ease_out_back(prog(t, 0.0, 0.35))
    ke = m["kaam"][1]
    head = "आपके काम में" if t < ke - 0.05 else "अच्छा... इसलिए ये नियम है!"
    kh = ease_out_back(prog(t, ke - 0.05, 0.3)) if t >= ke - 0.05 else k
    place(cv, pill_sprite(head, 50, (30, 20, 0), YELLOW, ORANGE), W / 2, 330, scale=max(0.05, kh))
    place(cv, glow_sprite(260, YELLOW, 70), W / 2, 560)
    place(cv, rays_sprite(), W / 2, 560, angle=t * 20, scale=0.48)
    place(cv, icon_sprite(data.get("icon") or "office", 260), W / 2, 560 + 10 * math.sin(t * 3.5),
          scale=max(0.05, ease_out_back(prog(t, 0.05, 0.4))), angle=4 * math.sin(t * 2.2))
    if sc.get("exact_words"):
        kp, th = seg_progress(sc, "kaam", t)
    else:
        kp, th = kin(sc, clamp((t - m["kaam"][0]) / max(0.3, ke - m["kaam"][0]))), None
    place(cv, card_sprite(980, 300, (30, 26, 12), YELLOW, 4, 40), W / 2, 880, alpha=clamp(k))
    draw_kinetic(cv, data["kaam"], W / 2, 0, 900, 60, kp, max_lines=3, min_size=42, line_h=1.3,
                 center_y=880, ghost=0.2, th=th, color=WHITE, hl_words=data.get("hl_words") or (),
                 hl_color=YELLOW)
    # yaad-sutra (bina awaaz) -> MOCK -> follow -> course progress, ek ke baad ek
    ty_ = ke + 0.1
    if t >= ty_:
        ky = ease_out_back(prog(t, ty_, 0.3))
        place(cv, pill_sprite("याद:  " + (data.get("yaad") or ""), 44, (30, 20, 0), YELLOW, ORANGE), W / 2, 1100,
              scale=max(0.05, ky))
    tm_ = ty_ + 0.5
    if t >= tm_:
        km = ease_out_back(prog(t, tm_, 0.3))
        place(cv, mock_button(), W / 2, 1255, scale=max(0.05, km) * (1 + 0.03 * math.sin(t * 7)))
    if t >= tm_ + 0.4:
        kf = ease_out_back(prog(t, tm_ + 0.4, 0.3))
        place(cv, pill_sprite("ऐसे EXAM TRAP रोज़:  FOLLOW " + IG_HANDLE, 34, WHITE, (170, 30, 40), (255, 120, 120)),
              W / 2, 1385, scale=max(0.05, kf))
    if SHOW_COURSE_PROGRESS and data.get("syllabus") and data["syllabus"][0] and t >= tm_ + 0.4:
        i_, n_ = data["syllabus"]
        kp_ = ease_out_cubic(prog(t, tm_ + 0.4, 0.8))
        d_ = ImageDraw.Draw(cv)
        d_.text((W / 2, 1450), f"PO Guide पूरा कोर्स:  Clause {i_} / {n_}", font=get_font(30),
                fill=(200, 210, 230), anchor="mm")
        d_.rounded_rectangle((220, 1478, W - 220, 1492), radius=7, fill=(60, 55, 30))
        d_.rounded_rectangle((220, 1478, 220 + max(14, (W - 440) * i_ / n_ * kp_), 1492), radius=7, fill=GREEN)
    return fx


def scene_grid_pro(cv, data, t, dur, m, vd, sc):
    """VS ke do card apni jagah (A/B/C/D) jaate hain, baaki do gir ke aate hain -> 2x2 grid + 3-2-1."""
    fx = {}
    pair = data["vs_pair"]
    e = ease_in_out(prog(t, 0.0, 0.35))
    em = ease_in_out(prog(t, 0.0, 0.35))
    big = min(hook_q_size(data["question"]), 64)
    draw_kinetic(cv, data["question"], W / 2, 0, 960 - 60 * em, int(big + (50 - big) * em), 1.0, max_lines=3,
                 min_size=36, karaoke=False, line_h=1.28, center_y=HOOK_QC + 150 + (460 - HOOK_QC - 90) * em,
                 hl_words=hook_highlights(data["question"]), hl_color=CYAN)
    offs, scl, alp, states = {}, {}, {}, {}
    c0 = sc["cd_start"]
    cd = COUNTDOWN_SECONDS * COUNTDOWN_STEP
    scan = min(3, int((t - c0) / (cd / 4))) if c0 <= t < c0 + cd else -1
    for i, (l, txt) in enumerate(data["options"]):
        gx, gy = grid_pos(i)
        states[l] = "active" if i == scan else "normal"
        if txt in pair:
            side = pair.index(txt)
            sx, sy = GRID_X[side], VS_Y + 150
            offs[l] = ((sx - gx) * (1 - e), (sy - gy) * (1 - e))
        else:
            kd = ease_out_back(prog(t, 0.1 + 0.08 * i, 0.3))
            offs[l] = (0, -140 * (1 - kd))
            alp[l] = clamp(kd * 1.6)
            scl[l] = 0.85 + 0.15 * min(kd, 1.0)
    draw_grid(cv, data, states, offs, scl, alp)
    if ANIM_SET == "flip" and t > 0.5:
        for i in range(4):
            gx_, gy_ = grid_pos(i)
            sheen(cv, gx_, gy_, TILE_W, TILE_H, t, period=1.8, offset=0.22 * i, strength=45)
    # 3-2-1 ring grid ke beech (quiz-show jaisa)
    cx, cy = W / 2, (GRID_Y[0] + GRID_Y[1]) / 2
    if t >= c0 - 0.2:
        kin_ = ease_out_back(prog(t, c0 - 0.2, 0.25))
        r = 78 * max(0.05, kin_)
        place(cv, glow_sprite(170, PURPLE, 150), cx, cy)
        d = ImageDraw.Draw(cv)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(20, 16, 44), outline=(90, 80, 150), width=8)
        tt = t - c0
        if 0 <= tt < cd:
            d.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * clamp(1 - tt / cd), fill=YELLOW, width=9)
            num = max(1, COUNTDOWN_SECONDS - int(tt / COUNTDOWN_STEP))
            frac = tt / COUNTDOWN_STEP - int(tt / COUNTDOWN_STEP)
            d.text((cx, cy), str(num), font=get_font(int(84 * (1.3 - 0.3 * ease_out_cubic(clamp(frac * 3))))),
                   fill=YELLOW, anchor="mm")
            if frac < 0.08 and tt > 0.05:
                fx["shake"] = 4
        elif tt >= cd:
            place(cv, lock_sprite(80), cx, cy)
    kc = ease_out_back(prog(t, 0.3, 0.3)) if t >= 0.3 else 0.0
    if kc > 0.01:
        place(cv, pill_sprite("अपना जवाब लॉक करो: A / B / C / D", 40, (30, 20, 0), YELLOW, ORANGE),
              W / 2, 1360, scale=max(0.05, kc))
    return fx


def scene_verdict_pro(cv, data, t, dur, m, vd, sc):
    """Usi grid me: galat ek-ek karke kat-te hain (✗), fir sahi card beech me aake bada hota hai."""
    fx = {}
    wrong = data["elim_order"]
    xt = dict(zip(wrong, VERDICT_X))
    win = VERDICT_WIN
    ew = ease_in_out(prog(t, win, 0.4))
    question_recap(cv, data, a=1 - clamp(ew * 3))          # sawal jaldi hate, "सही जवाब" upar na chadhe
    ci = next(i for i, (l, _) in enumerate(data["options"]) if l == data["correct"])
    gx, gy = grid_pos(ci)
    states, offs, scl, alp = {}, {}, {}, {}
    for i, (l, txt) in enumerate(data["options"]):
        if l == data["correct"]:
            continue
        if t >= xt[l]:
            kx = prog(t, xt[l], 0.2)
            states[l] = "wrong"
            offs[l] = (math.sin(kx * 40) * 14 * (1 - kx), 40 * ew)
            scl[l] = 0.94 - 0.2 * ew
            alp[l] = (1 - 0.35 * kx) * (1 - ew)
            if t - xt[l] < 0.08:
                fx["shake"] = 7
        else:
            states[l] = "normal"
    if ANIM_SET == "flip":
        # galat card palat ke laal (✗ wala) hota hai - ek-ek karke
        for i, (l, txt) in enumerate(data["options"]):
            if l == data["correct"]:
                continue
            x, y = grid_pos(i)
            eo = data.get("en_opt", {}).get(l, "") if en_on("options") else ""
            pf = prog(t, xt[l], 0.28) if t >= xt[l] else 0.0
            if alp.get(l, 1.0) <= 0.02:
                continue
            fr, bk = tile_sprite(l, txt, eo, "normal"), tile_sprite(l, txt, eo, "wrong")
            if pf < 1:
                place_flip(cv, fr, bk, x, y, pf)
            else:
                place(cv, bk, x + offs[l][0] * 0, y + offs[l][1], scale=scl[l], alpha=alp[l])
    else:
        draw_grid(cv, data, states, offs, scl, alp)
    for i, (l, _) in enumerate(data["options"]):
        if ANIM_SET == "flip" and l in xt and t < xt[l] + 0.28:
            continue
        if l in xt and t >= xt[l] and ew < 0.9:
            x, y = grid_pos(i)
            kx = prog(t, xt[l], 0.2)
            place(cv, x_mark_sprite(96), x + TILE_W / 2 - 40, y - TILE_H / 2 + 40 + 40 * ew,
                  scale=max(0.05, 1.7 - 0.7 * ease_out_back(kx)), alpha=1 - ew)
    # sahi card: pehle chupchaap chamakta (suspense), fir beech me bada
    tx, ty = W / 2, 900
    x = gx + (tx - gx) * ew
    y = gy + (ty - gy) * ew
    if ew > 0.05:
        place(cv, rays_sprite(), x, y, angle=t * 30, scale=1.1 * ew)
        place(cv, glow_sprite(360, GREEN, int(150 * ew)), x, y)
    eo = data.get("en_opt", {}).get(data["correct"], "") if en_on("answer") else ""
    st = "correct" if t >= win else ("active" if t >= VERDICT_X[-1] + 0.15 else "normal")
    hb = 1 + (0.04 * math.sin(t * 20) if VERDICT_X[-1] + 0.15 <= t < win else 0)
    if ANIM_SET == "flip" and win <= t < win + 0.26:
        place_flip(cv, tile_sprite(data["correct"], data["correct_text"], eo, "active"),
                   tile_sprite(data["correct"], data["correct_text"], eo, "correct"), x, y,
                   prog(t, win, 0.26), scale=1 + 0.45 * ew)
    else:
      place(cv, tile_sprite(data["correct"], data["correct_text"], eo, st), x, y,
          scale=(1 + 0.45 * ew) * hb)
    if t >= win + 0.12:
        kk = ease_out_back(prog(t, win + 0.12, 0.3))
        place(cv, check_sprite(150), W / 2, 580, scale=max(0.05, kk))
        d = ImageDraw.Draw(cv)
        d.text((W / 2, 440), "सही जवाब", font=get_font(84), fill=GREEN, anchor="mm")
        if t < win + 0.1:
            fx["flash"] = 0.3 * (1 - (t - win) / 0.1)
        rng = random.Random(9)
        tt = t - win
        for _ in range(70):
            ang = rng.uniform(0, 2 * math.pi)
            sp = rng.uniform(500, 1300)
            col = rng.choice([GREEN, YELLOW, CYAN, WHITE, ORANGE])
            sz = rng.randint(10, 18)
            px = W / 2 + math.cos(ang) * sp * tt * 0.9
            py = ty + math.sin(ang) * sp * tt * 0.9 + 900 * tt * tt
            if 0 < px < W and 0 < py < H and tt < 1.6:
                d.rectangle((px, py, px + sz, py + sz * 0.6), fill=col)
    if VERDICT_X[-1] + 0.12 <= t < win:
        d = ImageDraw.Draw(cv)
        a_ = 0.6 + 0.4 * math.sin(t * 16)
        d.text((W / 2, 1300), "...और सही जवाब है", font=get_font(62),
               fill=mix(BG_BOTTOM, YELLOW, a_), anchor="mm", stroke_width=5, stroke_fill=(5, 10, 22))
    if t >= win + 0.45:
        k3 = ease_out_back(prog(t, win + 0.45, 0.3))
        place(cv, pill_sprite("जो दोस्त गलत करेगा, उसे भेजो!", 40, WHITE, (37, 60, 140), CYAN),
              W / 2, 1250, scale=max(0.05, k3))
    return fx


ANIM_SET = os.getenv("ANIM_SET", "flip")            # "flip" = naya animation set, "classic" = pichhla
HOOK_ANIM = os.getenv("HOOK_ANIM", "scale")         # "scale" = taraazu pe jhoolte 2 jawab, "plain" = pichhla
SHOW_CHITRA = os.getenv("SHOW_CHITRA", "1") != "0"
USE_DRAW = os.getenv("USE_DRAW", "0") != "0"   # AI-aakaron wali drawing (kamzor) - band
USE_ICON_KITS = os.getenv("USE_ICON_KITS", "0") != "0"   # purani icon-kahani (kamzor) - band; sirf drawing/lifaafa/pata       # har niyam ka apna AI-drawn chitra (aankh-jaanch ke saath)
SHOW_COURSE_PROGRESS = False   # "PO Guide पूरा कोर्स: Clause X / N" (user ne hataya)
REQUIRE_CHITRA = os.getenv("REQUIRE_CHITRA", "1") != "0"   # chitra na bane to us run me reel NAHI (bekaar reel nahi)  # "चित्र से समझो" / "काम की कहानी" scene (0 = band)
ENGINE_VERSION = "v10.0-asli-chitra (2026-10-01): Cloudflare FLUX asli chitra + Hindi parchi/ghera + andhi-jaanch"


def place_flip(canvas, front, back, cx, cy, p, scale=1.0):
    """Card palatna: chaudai cos() se simat-ti hai, beech me front -> back badalta hai (3D flip jaisa)."""
    p = clamp(p)
    sp = front if p < 0.5 else back
    sx = abs(math.cos(math.pi * p))
    if sx < 0.03:
        return
    w_, h_ = max(1, int(sp.width * sx * scale)), max(1, int(sp.height * scale * (1 + 0.06 * (1 - sx))))
    place(canvas, sp.resize((w_, h_), Image.BILINEAR), cx, cy)


def sheen(canvas, cx, cy, w, h, t, period=2.2, offset=0.0, strength=70):
    """Card pe tirchhi chamak ki patti guzarti hai (premium feel), har `period` second me ek baar."""
    ph = ((t + offset) % period) / 0.55
    if ph > 1:
        return
    x0 = cx - w / 2 - 160 + (w + 320) * ph
    lay = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    lx = x0 - (cx - w / 2)
    d.polygon([(lx, 0), (lx + 70, 0), (lx + 20, h), (lx - 50, h)], fill=(255, 255, 255, strength))
    mask = Image.new("L", (int(w), int(h)), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=34, fill=255)
    a = ImageChops.multiply(lay.getchannel("A"), mask)
    lay.putalpha(a)
    canvas.paste(lay, (int(cx - w / 2), int(cy - h / 2)), lay)


def iris(prev, cur, p, cx=W / 2, cy=H * 0.45):
    """Gola khulta hai: naya scene beech se phailta hai, kinare pe patli chamakti rekha."""
    e = ease_in_out(clamp(p))
    rmax = math.hypot(max(cx, W - cx), max(cy, H - cy)) + 20
    r = rmax * e
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    out = prev.copy()
    if e < 1:                                      # pichhla scene thoda peeche hat-ta hai
        z = 1 + 0.08 * e
        nw, nh = int(W * z), int(H * z)
        out = prev.resize((nw, nh), Image.BILINEAR).crop(((nw - W) // 2, (nh - H) // 2, (nw - W) // 2 + W,
                                                         (nh - H) // 2 + H))
        out = Image.blend(out, Image.new("RGB", (W, H), BG_BOTTOM), 0.35 * e)
    out.paste(cur, (0, 0), mask)
    if 0.02 < e < 0.98:
        d = ImageDraw.Draw(out)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=CYAN, width=6)
        d.ellipse((cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10), outline=mix(CYAN, BG_BOTTOM, 0.6), width=3)
    return out


def whip(prev, cur, p):
    """Pro 'whip pan': dono frame tezi se sarakte hain, beech me motion blur."""
    e = ease_in_out(clamp(p))
    off = int(W * e)
    comp = Image.new("RGB", (W, H))
    comp.paste(prev, (-off, 0))
    comp.paste(cur, (W - off, 0))
    strength = math.sin(math.pi * clamp(p))
    n = int(2 + 8 * strength)
    if n > 2:
        a = np.asarray(comp, dtype=np.float32)
        acc = np.zeros_like(a)
        step = int(10 + 26 * strength)
        for k in range(n):
            acc += np.roll(a, (k - n // 2) * step // 2, axis=1)
        comp = Image.fromarray((acc / n).astype(np.uint8), "RGB")
    return comp


def scene_question(cv, data, t, dur, m, vd, sc):
    place(cv, pill_sprite("सवाल", 40, WHITE, (37, 60, 140), BLUE), W / 2, 225)
    source_chip(cv, data, 318, a=0.95)
    en_q = data.get("en_question", "") if en_on("question") else ""
    merged = "cd_start" in sc
    # jagah ka hisaab pehle: sawal + English (jitni line bane) + 4 options + countdown - kuch bhi na dabe
    oh, gap_o = (146, 160) if merged else (OPT_H, 200)
    bottom_limit = 1300 if merged else 1470          # merged: neeche countdown row (1380) ke liye jagah
    q_size, en_size, en_lines = 66, 39, 2

    def en_fits(txt, size, lines_):
        _, _, ls = fit_lines_f(txt, 940, lines_, size, 26, get_font_reg)
        return len(ls) <= lines_

    for step_ in range(12):
        qh = text_block_h(data["question"], 960, q_size, 3, 40)
        eh = en_h(en_q, 940, en_size, en_lines) if en_q else 0
        top_q = 362 if merged else max(362, 500 - qh / 2)      # 'PO Guide | Clause' chip (318) ke neeche
        opt0 = top_q + qh + (eh + 8 if eh else 0) + 34 + oh / 2
        last_bottom = opt0 + 3 * gap_o + oh / 2
        if last_bottom <= bottom_limit and (not en_q or en_fits(en_q, en_size, en_lines)):
            break
        # kram: options ki jagah -> Hindi size -> English size (poori rahe) -> English sawal hatao
        if gap_o > 148:
            gap_o -= 6
            oh = min(oh, gap_o - 12)
        elif q_size > 54:
            q_size -= 4
        elif en_q and en_size > 33:
            en_size -= 2
        else:
            en_q = ""          # adhoori English se behtar kuch nahi (hook me poora dikh chuka)
    yb = draw_kinetic(cv, data["question"], W / 2, 0, 960, q_size, 1.0, max_lines=3, min_size=40,
                      karaoke=False, center_y=top_q + qh / 2)
    yb = draw_en(cv, en_q, yb + 4, max_w=940, size=en_size, max_lines=en_lines)
    ys = opt_positions(y0=max(opt0, yb + 30 + oh / 2), gap=gap_o)
    c0 = sc.get("cd_start", 99)
    cd = COUNTDOWN_SECONDS * COUNTDOWN_STEP
    pulse = 1 + (0.015 * math.sin(t * 10) if t >= c0 else 0)
    scan = -1
    if merged and c0 <= t < c0 + cd:
        scan = min(3, int((t - c0) / (cd / 4)))          # tik-tik ke saath nazar A->B->C->D
    for i, (l, txt) in enumerate(data["options"]):
        eo = (data.get("en_opt", {}).get(l, "") if en_on("options") else "")
        s0 = sc["opt_t"][i]
        k = prog(t, s0, 0.3)
        if k <= 0:
            place(cv, option_sprite(l, txt, OPT_W, oh, "normal", eo), W / 2, ys[i], alpha=0.12)
            continue
        active = (s0 <= t < s0 + 0.35) or i == scan
        e = ease_out_back(k)
        place(cv, option_sprite(l, txt, OPT_W, oh, "active" if active else "normal", eo),
              W / 2 + (1 - e) * 500, ys[i], alpha=clamp(k * 2), scale=(1.04 if active else 1.0) * pulse)

    fx = {}
    if merged and t >= c0 - 0.25:
        # countdown: scene ke aakhir me (padhne ke baad), taaki khaali 'taala' na rahe
        tt = t - c0
        cy = min(ys[-1] + oh / 2 + 78, 1385)        # 'आगे: EXAM TRAP' label (1490) se door
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
    if t >= 0.5:
        place(cv, pill_sprite("जो दोस्त गलत करेगा, उसे भेजो!", 38, WHITE, (37, 60, 140), CYAN),
              W / 2, 1390, scale=max(0.05, ease_out_back(prog(t, 0.5, 0.3))))
    return {"flash": 0.28 * (1 - prog(t, 0, 0.12))}


TRAP_SPLITS = (", ", " लेकिन ", " बल्कि ", " जबकि ", " पर ")     # comma sabse pakka; 'पर' aksar sthaan-sambandhi hota hai


def split_trap(text):
    """'X समझना गलत है, Y ही सही है' -> ('X समझना गलत है', 'Y ही सही है'). Na bane to None."""
    t_ = " ".join((text or "").split())
    for sp in TRAP_SPLITS:
        if sp in t_:
            a, b = t_.split(sp, 1)
            b = (sp.strip(" ,") + " " + b).strip() if sp.strip(" ,") else b
            # ❌ sirf tab jab pehla hissa KHUD galat/purana kahe - warna sach baat pe ❌ lag jaata (ulta niyam)
            # "गलत नहीं" / "मना नहीं" = sach baat -> uspe ❌ kabhi nahi (ulta niyam banta)
            if re.search(r"(गलत|मना|वर्जित)\s+नहीं", a):
                return None
            if len(a.split()) >= 2 and len(b.split()) >= 2 and re.search(r"गलत|पुरान|भ्रम", a):
                return a.strip(" ,"), b.strip()
            continue                                  # ye tod theek nahi - agla try karo
    return None


def _mark_icon(cv, x, y, good, a=1.0):
    col = GREEN if good else RED
    r = 26
    d = ImageDraw.Draw(cv)
    d.ellipse((x - r, y - r, x + r, y + r), fill=mix(BG_BOTTOM, col, a))
    w_ = mix(BG_BOTTOM, WHITE, a)
    if good:
        d.line((x - 11, y + 1, x - 3, y + 10, x + 12, y - 9), fill=w_, width=6, joint="curve")
    else:
        d.line((x - 9, y - 9, x + 9, y + 9), fill=w_, width=6)
        d.line((x + 9, y - 9, x - 9, y + 9), fill=w_, width=6)


def trap_start(sc):
    """Trap card ka samay: shabd-samay andaza ho (Gemini) to 0.3s PEHLE - awaaz se kabhi peeche nahi."""
    if "trapx" not in sc["marks"]:
        return 1e9                                    # is reel me trap nahi
    t0 = sc["marks"]["trapx"][0]
    return t0 if sc.get("exact_words") else max(0.0, t0 - 0.3)


def beat_times(sc):
    """Yaad-tukde niyam bolte-bolte ek-ek karke (niyam ki awaaz ke 15%-90% hisse me)."""
    items = (sc.get("data") or {}).get("beat_items") or []
    if not items or "fact" not in sc.get("marks", {}):
        return []
    a, b = sc["marks"]["fact"]
    n = len(items)
    # awaaz se thoda PEHLE aur tay taal par: subtitle ki tarah aage rehna natural lagta hai, peeche nahi
    gap = min(0.75, max(0.45, (b - a) * 0.55 / max(1, n)))
    return [a + 0.2 + gap * i for i in range(n)]


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
    tsplit = split_trap(data["trap"])
    if tsplit:
        th1, th2_ = text_block_h(tsplit[0], 800, TS, 3, 38), text_block_h(tsplit[1], 800, TS, 3, 38)
        th = th1 + th2_ + 200 + (eht + 14 if eht else 0)
    else:
        th = text_block_h(data["trap"], 880, TS, 4, 40) + 160 + (eht + 14 if eht else 0)
    gap = 105
    area_top, area_bot = 320, 1450
    ts = trap_start(sc)
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
        if HOOK_MODE == "tease":
            mv = 1.0
        fc = fc_center + (fc_final - fc_center) * mv

    k1 = ease_out_back(prog(t, 0, 0.35))
    place(cv, card_sprite(980, int(fh), (14, 44, 32), GREEN, 6, 44), W / 2, fc,
          scale=0.92 + 0.08 * k1, alpha=clamp(k1))
    place(cv, pill_sprite("नियम", 46, (5, 30, 15), GREEN, GREEN), W / 2, fc - fh / 2, scale=max(0.05, k1))
    place(cv, pill_sprite("स्रोत: " + source_label(data), 28, (170, 230, 190), (10, 40, 26), (40, 110, 70)),
          W / 2, fc + fh / 2 - 6, alpha=clamp(k1))
    fp, th_f = seg_progress(sc, "fact", t)
    fp, th_f = kin(sc, fp), (th_f if sc.get("exact_words") else None)
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
    if not data.get("trap"):
        return fx                                    # trap nahi: sirf niyam (beech me)
    trap_base = cv.copy() if ANIM_SET == "flip" else None      # palatne ke liye bina-trap wala pichhla hissa
    if t >= ts - 0.1:
        k2 = ease_out_back(prog(t, ts - 0.1, 0.35))
        place(cv, card_sprite(980, int(th), (56, 18, 26), RED, 6, 44), W / 2, tc,
              scale=0.9 + 0.1 * k2, alpha=clamp(k2))
        place(cv, pill_sprite("EXAM TRAP", 46, WHITE, RED, RED), W / 2, tc - th / 2,
              scale=max(0.05, k2), angle=-3)
        # SECOND PAYOFF: trap aate hi laal chamak + thappa girta hai (doosra "arre!" pal)
        pt = t - (ts - 0.1)
        if 0 <= pt < 0.45:
            fl = 1 - pt / 0.45
            place(cv, glow_sprite(700, RED, int(150 * fl)), W / 2, tc)
        kk_ = prog(t, ts - 0.05, 0.18)
        st_y = tc - th / 2 - 10
        fade_ = 1 - prog(t, ts + 0.8, 0.4)                # thappa apna kaam karke hat jaaye (pill me naam hai)
        if fade_ > 0.01:
            place(cv, stamp_sprite(), W - 230, st_y, scale=(1.9 - 0.9 * ease_out_cubic(kk_)) * 0.5,
                  angle=-11, alpha=clamp(kk_ * 3) * fade_)
        tp, th2 = seg_progress(sc, "trap", t)
        if tsplit:
            # do hisse: pehle galat dharana (laal ❌), awaaz pahunchte hi sahi baat (hari ✓)
            n1 = len(tsplit[0].split())
            r_ = n1 / max(1, n1 + len(tsplit[1].split()))
            top_ = tc - th / 2 + 70
            y1 = top_ + th1 / 2
            _mark_icon(cv, 110, y1, False, clamp(k2))
            draw_kinetic(cv, tsplit[0], W / 2 + 30, 0, 800, TS, kin(sc, clamp(tp / max(r_, 0.01))), max_lines=3,
                         min_size=38, ghost=0.18, center_y=y1, color=(255, 200, 200))
            p2 = clamp((tp - r_) / max(1 - r_, 0.01))
            if not sc.get("exact_words"):            # samay andaza -> ✓ hissa jaldi (0.6s) aur poora
                tp = r_ if t >= m["trap"][0] + 0.6 else min(tp, r_ - 0.05)
                p2 = 1.0 if t >= m["trap"][0] + 0.6 else 0.0
            y2_ = top_ + th1 + 60 + th2_ / 2
            if tp >= r_ - 0.02:
                k3 = ease_out_back(prog(p2, 0, 0.15))
                _mark_icon(cv, 110, y2_, True, clamp(k3))
                d = ImageDraw.Draw(cv)
                d.line((150, top_ + th1 + 30, W - 150, top_ + th1 + 30), fill=(120, 60, 70), width=3)
            yb2 = draw_kinetic(cv, tsplit[1], W / 2 + 30, 0, 800, TS,
                               kin(sc, max(p2, 0.001)) if tp >= r_ - 0.02 else 0.0,
                               max_lines=3, min_size=38, ghost=0.12, center_y=y2_, color=(200, 255, 210))
        else:
            yb2 = draw_kinetic(cv, data["trap"], W / 2, 0, 880, TS, kin(sc, tp), max_lines=4, min_size=40,
                               ghost=0.18, center_y=tc + 10 - (eht + 14) / 2 if eht else tc + 10,
                               th=th2 if sc.get("exact_words") else None)
        draw_en(cv, et, yb2 + 10, max_w=860, size=32, color=(255, 190, 190), alpha=clamp(k2))
        if t - ts < 0.12:
            fx["shake"] = 6
    else:
        # band tala: trap wali jagah pe ek locked dabba jo hilta hai -> "isme kya hai?"
        kl = ease_out_back(prog(t, 0.25, 0.35)) if t >= 0.25 else 0.0
        if kl > 0.01:
            place(cv, card_sprite(980, int(th), (34, 22, 36), (120, 60, 72), 5, 44), W / 2, tc,
                  scale=0.9 + 0.1 * min(kl, 1.0), alpha=clamp(kl))
            place(cv, pill_sprite("EXAM TRAP", 46, (200, 170, 175), (70, 30, 40), (120, 60, 72)), W / 2,
                  tc - th / 2, scale=max(0.05, kl))
            wig = 9 * math.sin(t * 30) if (t % 0.9) < 0.3 else 0.0
            place(cv, glow_sprite(120, RED, 70), W / 2, tc - 16)
            # tala ke chaaron taraf bharta ghera: trap khulne me kitna baaki (intezaar dikhe, jama na lage)
            fill_ = clamp((t - 0.25) / max(0.3, ts - 0.25))
            d0 = ImageDraw.Draw(cv)
            rr = 92
            d0.ellipse((W / 2 - rr, tc - 16 - rr, W / 2 + rr, tc - 16 + rr), outline=(90, 45, 55), width=8)
            d0.arc((W / 2 - rr, tc - 16 - rr, W / 2 + rr, tc - 16 + rr), -90, -90 + 360 * fill_,
                   fill=mix(ORANGE, RED, fill_), width=8)
            place(cv, lock_sprite(110), W / 2, tc - 16, angle=wig, scale=max(0.05, kl))
            left = max(0.0, ts - t)
            d = ImageDraw.Draw(cv)
            d.text((W / 2, tc + 76), "खुलने वाला है..." if left > 0.2 else "खुल गया!", font=get_font(44),
                   fill=mix(BG_BOTTOM, ORANGE, 0.55 + 0.45 * math.sin(t * 6)), anchor="mm")
    if trap_base is not None:
        # TRAP CARD PALAT-TA HAI: band dabba simat ke patli rekha, fir laal trap card khulta hai
        sq = 1.0
        if ts - 0.2 <= t < ts - 0.1:
            sq = math.cos(math.pi / 2 * prog(t, ts - 0.2, 0.1))
        elif ts - 0.1 <= t < ts + 0.12:
            sq = math.sin(math.pi / 2 * prog(t, ts - 0.1, 0.22))
        if sq < 0.995:
            y0_, y1_ = int(tc - th / 2 - 50), int(tc + th / 2 + 90)
            box = (0, max(0, y0_), W, min(H, y1_))
            reg = cv.crop(box)
            cv.paste(trap_base.crop(box), box[:2])
            nw_ = max(2, int(W * max(sq, 0.02)))
            cv.paste(reg.resize((nw_, reg.height), Image.BILINEAR), ((W - nw_) // 2, box[1]))
            if sq < 0.5:
                ImageDraw.Draw(cv).line((W / 2, box[1] + 30, W / 2, box[3] - 30), fill=(255, 230, 230), width=4)
    return fx


def yaad_chips(text):
    """'मोबाइल डाकघर: बीमाकृत + वी.पी. नहीं' -> [('मोबाइल डाकघर',''),('बीमाकृत',':'),('वी.पी. नहीं','+')]."""
    t_ = " ".join((text or "").split())
    # '+' pe nahi todte ('बीमाकृत + वी.पी. नहीं' me 'नहीं' dono pe lagta hai); '8:30' ka ':' samay hai
    # '→' safai me ' - ' ban jaata hai, isliye spaced '-' / '–' bhi teer
    parts = re.split(r"\s*(=|→|(?<!\d):(?!\d))\s*|\s+([-–])\s+", t_)
    parts = [x for x in parts if x is not None]
    if len(parts) < 3:
        return None
    chips, op = [], ""
    for i, x in enumerate(parts):
        if i % 2 == 1:
            op = x
            continue
        x = x.strip(" ।.")
        if not x:
            return None
        chips.append((x, op))
        op = ""
    if not (2 <= len(chips) <= 4) or any(len(c.split()) > 6 for c, _ in chips):
        return None
    return chips


@lru_cache(maxsize=64)
def chip_sprite(text, final=False, w=820, h=104):
    fill = YELLOW if final else (58, 48, 14)
    im = card_sprite(w, h, fill, YELLOW, 4, 30, shadow=False).copy()
    d = ImageDraw.Draw(im)
    f, s_, lines = fit_lines(text, w - 80, 1, 58, 36)
    d.text((w / 2, h / 2), " ".join(lines[0]) if lines else "", font=f,
           fill=((30, 20, 0) if final else WHITE) + (255,), anchor="mm")
    return im


def scene_cta(cv, data, t, dur, m, vd, sc):
    """Yaad formula + comment CTA + agli reel ka khaas teaser + follow."""
    k = ease_out_back(prog(t, 0, 0.35))
    place(cv, pill_sprite("याद रखिए", 50, (30, 20, 0), YELLOW, YELLOW), W / 2, 305, scale=max(0.05, k))

    ey = data.get("en_yaad", "") if en_on("yaad") else ""
    ehy = en_h(ey, 860, 36)
    chips = yaad_chips(data["yaad"])
    topic = (data.get("title") or "").strip()
    if not chips and topic and 1 <= len(topic.split()) <= 5 and topic not in data["yaad"] \
            and len(data["yaad"].split()) <= 8:
        chips = [(topic, ""), (data["yaad"].strip(" ।"), "→")]      # vishay -> jawab
    p, th = seg_progress(sc, "yaad", t)
    if chips:
        # formula ke tukde ek-ek karke: Ticket -> Reproduction -> BLACK jaisa (wahi text, naya daava nahi)
        rh, og = 104, 58
        ch = len(chips) * rh + (len(chips) - 1) * og + 90 + (ehy + 12 if ehy else 0)
        cy = 380 + ch / 2
        place(cv, glow_sprite(440, YELLOW, 60), W / 2, cy)
        place(cv, card_sprite(1000, ch, (40, 32, 8), YELLOW, 6, 46), W / 2, cy, scale=0.9 + 0.1 * k, alpha=clamp(k))
        y = cy - ch / 2 + 45 + rh / 2
        n = len(chips)
        for i, (c, op) in enumerate(chips):
            t_i = 0.05 + 0.35 * i                            # tay taal - awaaz se pehle, kabhi peeche nahi
            kc = ease_out_back(prog(t, t_i, 0.3)) if t >= t_i else 0.0
            if op and kc > 0:
                d = ImageDraw.Draw(cv)
                oy = y - rh / 2 - og / 2
                if op == "=":
                    d.text((W / 2, oy), "=", font=get_font(56), fill=YELLOW, anchor="mm")
                else:                                   # teer khud banao (font pe nirbhar nahi)
                    d.line((W / 2, oy - 18, W / 2, oy + 8), fill=YELLOW, width=7)
                    d.polygon([(W / 2 - 16, oy + 2), (W / 2 + 16, oy + 2), (W / 2, oy + 22)], fill=YELLOW)
            if kc > 0:
                place(cv, chip_sprite(c, final=(i == n - 1)), W / 2, y, scale=max(0.05, 0.85 + 0.15 * kc),
                      alpha=clamp(kc * 1.5))
            y += rh + og
        yb = cy + ch / 2 - (ehy + 30 if ehy else 0)
    else:
        cy = 540
        bh = text_block_h(data["yaad"], 880, 80, 3, 50)
        ch = bh + 170 + (ehy + 12 if ehy else 0)
        place(cv, glow_sprite(440, YELLOW, 70), W / 2, cy)
        place(cv, card_sprite(1000, ch, (46, 38, 10), YELLOW, 7, 46), W / 2, cy,
              scale=0.9 + 0.1 * k, alpha=clamp(k))
        yb = draw_kinetic(cv, data["yaad"], W / 2, 0, 880, 80, kin(sc, max(p, 0.001)), max_lines=3, min_size=50,
                          ghost=0.3, center_y=cy - (ehy + 12) / 2 if ehy else cy,
                          th=th if sc.get("exact_words") else None, karaoke=bool(sc.get("exact_words")))
    draw_en(cv, ey, yb + 8, max_w=860, size=36, color=(255, 225, 150), alpha=clamp(k))

    # FREE MOCK TEST - "कमेंट कीजिए, मॉक" bolte hi
    y2 = cy + ch / 2 + 125
    m0 = m["mock"][0] if "mock" in m else max(0.6, m["yaad"][1] - 0.4)
    if HOOK_MODE == "tease":
        m0 = min(m0, 1.0)
    if HOOK_MODE == "pro":
        m0 = 0.05 + 0.35 * len(chips or [1, 1]) + 0.35      # yaad ke tukde poore hone ke baad hi MOCK                  # neeche ki jagah turant bhare (khaali pal nahi)   # mock ki awaaz ab nahi - button yaad ke saath
    k2 = ease_out_back(prog(t, m0 - 0.15, 0.35)) if t >= m0 - 0.15 else 0.0
    pulse = 1 + (0.05 * math.sin(t * 9) if t > m0 + 0.4 else 0)
    if k2 > 0:
        place(cv, glow_sprite(300, ORANGE, 110), W / 2, y2)
        msc = 1.3 if HOOK_MODE == "pro" else 1.0
        place(cv, mock_button(), W / 2, y2 + (40 if HOOK_MODE == "pro" else 0),
              scale=max(0.05, (0.5 + 0.5 * k2) * pulse * msc), alpha=clamp(k2 * 2))

    # agli reel ka khaas sawal (open loop)
    teaser = data.get("teaser") or ""
    if HOOK_MODE == "pro" or teaser.strip() in ("", "अगला नियम"):
        teaser = ""                      # khaali/generic teaser se better kuch na dikhana
    ty = y2 + 190
    if teaser and t > m0 + 0.2:
        kt = ease_out_cubic(prog(t, m0 + 0.2, 0.35))
        box_h = text_block_h(teaser, 820, 42, 2, 34) + 90
        bp = 1 + 0.015 * math.sin(t * 5)          # bonus sawal halka saans le - screen zinda rahe
        place(cv, glow_sprite(260, PURPLE, int(60 + 40 * math.sin(t * 5))), W / 2, ty + box_h / 2 - 10)
        place(cv, card_sprite(960, box_h, CARD, PURPLE, 4, 30), W / 2, ty + box_h / 2 - 10, alpha=kt, scale=bp)
        d = ImageDraw.Draw(cv)
        label = "बोनस सवाल: जवाब कमेंट करो!" if teaser.rstrip().endswith("?") else "अगली रील में:"
        d.text((W / 2, ty + 18), label, font=get_font(34), fill=YELLOW, anchor="mm")
        draw_kinetic(cv, teaser, W / 2, 0, 820, 42, 1.0, max_lines=2, min_size=34, karaoke=False,
                     center_y=ty + box_h / 2 + 12)
    if SHOW_COURSE_PROGRESS and HOOK_MODE == "pro" and data.get("syllabus") and data["syllabus"][0]:
        i_, n_ = data["syllabus"]
        kp_ = ease_out_cubic(prog(t, 0.2, 0.9))
        yy = y2 + 400
        d_ = ImageDraw.Draw(cv)
        d_.text((W / 2, yy - 42), f"PO Guide पूरा कोर्स:  Clause {i_} / {n_}", font=get_font(36),
                fill=(200, 210, 230), anchor="mm")
        x0_, x1_ = 190, W - 190
        d_.rounded_rectangle((x0_, yy - 9, x1_, yy + 9), radius=9, fill=(45, 45, 80))
        d_.rounded_rectangle((x0_, yy - 9, x0_ + max(18, (x1_ - x0_) * i_ / n_ * kp_), yy + 9), radius=9, fill=GREEN)
    if HOOK_MODE == "pro":
        kf = ease_out_back(prog(t, m0 + 0.6, 0.3)) if t >= m0 + 0.6 else 0.0
        if kf > 0.01:
            place(cv, pill_sprite("ऐसे EXAM TRAP रोज़:  FOLLOW " + IG_HANDLE, 40, WHITE, (170, 30, 40),
                                  (255, 120, 120)), W / 2, y2 + 280, scale=max(0.05, kf) * (1 + 0.03 * math.sin(t * 7)))
    else:
        place(cv, pill_sprite("FOLLOW  " + IG_HANDLE, 42, WHITE, (220, 38, 38), (255, 120, 120)),
              W / 2, 1482, scale=1 + 0.03 * math.sin(t * 8), alpha=clamp(k))
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
    "hook": {"pro": scene_hook_pro, "tease": scene_hook_tease}.get(HOOK_MODE, scene_hook),
    "question": {"pro": scene_grid_pro, "tease": scene_question_tease}.get(HOOK_MODE, scene_question),
    "verdict": scene_verdict_pro, "countdown": scene_countdown,
    "hint": scene_hint, "eliminate": scene_eliminate, "reveal": scene_reveal,
    "rule": scene_rule, "cta": scene_cta, "kaam": scene_kaam_pro, "chitra": scene_chitra,
}


# ==================== RENDER ====================

def render_frame(sc, data, gt, total):
    if REEL_STYLE == "paper" and HOOK_MODE == "pro":
        return render_frame_paper(sc, data, gt, total)
    t = gt - sc["start"]
    cv = bg_frame(sc["mood"], gt)
    fx = SCENES[sc["name"]](cv, data, t, sc["dur"], sc["marks"], sc["vdur"], sc) or {}
    draw_header(cv, data, gt, total)
    draw_stepper(cv, current_step(sc["name"], t, sc["marks"], sc), t, no_trap=(HOOK_MODE == "pro" and not data.get("trap")))

    # scene-entry punch zoom + hook me dheema push-in (screen jama hua na lage)
    z = 1.0
    if t < 0.2 and sc["name"] not in ("hook", "question", "verdict", "chitra"):          # hook ka pehla frame poora saaf (kuch na kate)
        z *= 1 + 0.07 * (1 - ease_out_cubic(t / 0.2))
    if sc["name"] == "hook":
        z *= 1 + 0.035 * clamp(t / max(sc["dur"], 0.1))
    if sc["name"] == "rule":
        z *= 1 + 0.02 * clamp(t / max(sc["dur"], 0.1))       # poore niyam scene me bahut halka push-in
    if sc["name"] == "rule" and "trapx" in sc.get("marks", {}):
        ts_ = sc["marks"]["trapx"][0]
        if t > ts_:
            z *= 1 + 0.03 * clamp((t - ts_) / max(sc["dur"] - ts_, 0.1))
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


# ==================== STYLE "paper": EXAM PAPER EXPERIMENT ====================
# Poori reel ek asli exam prashn-patra jaisi: kagaz, OMR gole, pencil jo options pe atakti hai,
# teacher ki laal kalam ke ✗/✓, highlighter jo bolte shabdon pe chalta hai, niyam ek sticky note,
# trap pe masking-tape jo aakhir me ukhadti hai. Exam dene wala ye pal pehchaanta hai (scroll rukta hai).
# Wapas purane dark style ke liye: REEL_STYLE = "dark"
REEL_STYLE = os.getenv("REEL_STYLE", "dark")      # paper band (user ne mana kiya)

PAPER = (247, 242, 229)
RULE_LINE = (190, 208, 230)
MARGIN = (226, 120, 120)
INK = (28, 32, 44)
INK_SOFT = (120, 124, 136)
RED_PEN = (205, 30, 45)
GREEN_PEN = (22, 140, 70)
HILITE = (255, 226, 60)
NOTE = (255, 236, 120)
P_LEFT = 150                      # margin ke baad text shuru
P_RIGHT = W - 120                 # daayein Instagram buttons se door


@lru_cache(maxsize=2)
def paper_base():
    rng = np.random.default_rng(7)
    a = np.zeros((H, W, 3), dtype=np.float32)
    a[:] = PAPER
    a += rng.normal(0, 3.2, (H, W, 1))                         # kagaz ka daana
    yy = np.linspace(0, 1, H)[:, None, None]
    xx = np.linspace(0, 1, W)[None, :, None]
    vig = 1 - 0.10 * ((xx - 0.5) ** 2 * 2 + (yy - 0.5) ** 2 * 2)   # kinare halke dhoondhle
    a *= vig
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(im)
    for y in range(260, H - 120, 66):
        d.line((0, y, W, y), fill=RULE_LINE, width=2)
    d.line((P_LEFT - 34, 0, P_LEFT - 34, H), fill=MARGIN, width=3)
    d.line((P_LEFT - 26, 0, P_LEFT - 26, H), fill=MARGIN, width=1)
    for y in (330, 960, 1590):                                   # file ke ched
        d.ellipse((34, y - 22, 78, y + 22), fill=(222, 216, 200), outline=(200, 194, 178), width=2)
    return im


def paper_header(cv, data, gt, total, page):
    d = ImageDraw.Draw(cv)
    f = get_font(30)
    d.text((P_LEFT, 170), f"POSTAL WALA  ·  प्रश्न-पत्र", font=f, fill=INK_SOFT, anchor="lm")
    d.text((P_RIGHT, 170), f"Clause {data['clause_no']}  ·  Part {data['part_no']}/{data['total_parts']}",
           font=get_font(28), fill=INK_SOFT, anchor="rm")
    d.line((P_LEFT, 200, P_RIGHT, 200), fill=INK_SOFT, width=2)
    # paper ke upar laal patli progress line (kitna bacha)
    d.line((P_LEFT, 208, P_LEFT + (P_RIGHT - P_LEFT) * clamp(gt / total), 208), fill=RED_PEN, width=5)
    # page number neeche
    d.text((W / 2, 1700), f"— {page} / 5 —", font=get_font(30), fill=INK_SOFT, anchor="mm")


@lru_cache(maxsize=16)
def rubber_stamp(text, color=RED_PEN, size=46, angle=-7):
    f = get_font(size)
    tw = int(text_w(text, f)) + 60
    th = int(size * 1.7)
    im = Image.new("RGBA", (tw + 20, th + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((10, 10, tw + 10, th + 10), radius=12, outline=color + (235,), width=6)
    d.text((tw / 2 + 10, th / 2 + 10), text, font=f, fill=color + (235,), anchor="mm")
    a = np.array(im)
    rng = np.random.default_rng(len(text))
    holes = rng.random(a.shape[:2]) < 0.10                      # syahi ke khaali daane (asli stamp)
    a[..., 3] = np.where(holes, (a[..., 3] * 0.35).astype(np.uint8), a[..., 3])
    return Image.fromarray(a, "RGBA").rotate(angle, expand=True, resample=Image.BICUBIC)


@lru_cache(maxsize=2)
def pencil_sprite():
    L, Wd = 330, 34
    im = Image.new("RGBA", (L + 20, Wd + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    y0, y1 = 10, 10 + Wd
    d.polygon([(10, (y0 + y1) / 2), (70, y0), (70, y1)], fill=(236, 200, 150, 255))     # chhila hua lakdi
    d.polygon([(10, (y0 + y1) / 2), (30, (y0 + y1) / 2 - 6), (30, (y0 + y1) / 2 + 6)], fill=(40, 40, 48, 255))
    d.rectangle((70, y0, L - 40, y1), fill=(250, 190, 30, 255))
    d.line((70, (y0 + y1) / 2, L - 40, (y0 + y1) / 2), fill=(225, 160, 20, 255), width=3)
    d.rectangle((L - 40, y0 - 2, L - 14, y1 + 2), fill=(180, 180, 190, 255))
    d.rounded_rectangle((L - 14, y0, L + 8, y1), radius=6, fill=(240, 130, 140, 255))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sh.paste((0, 0, 0, 70), (0, 0), im.split()[3])
    out = Image.new("RGBA", (im.width + 16, im.height + 16), (0, 0, 0, 0))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)), (12, 14))
    out.alpha_composite(im, (0, 0))
    return out


def draw_pencil(cv, tip_x, tip_y, angle=-35):
    sp = pencil_sprite().rotate(angle, expand=True, resample=Image.BICUBIC)
    # tip sprite ke baayein kinare pe tha; ghumane ke baad tip ki jagah nikaalo
    r = math.radians(angle)
    L = pencil_sprite().width / 2 - 10
    cx = tip_x + L * math.cos(r)
    cy = tip_y - L * math.sin(r)
    place(cv, sp, cx, cy)


def ink_stroke(d, pts, p, color, width):
    """Pen se khinchi line: p (0-1) jitni kheench chuki."""
    if p <= 0 or len(pts) < 2:
        return
    seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    tot = sum(seg)
    left = tot * clamp(p)
    out = [pts[0]]
    for i, sl in enumerate(seg):
        if left >= sl:
            out.append(pts[i + 1])
            left -= sl
        else:
            k = left / max(sl, 1e-6)
            out.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k))
            break
    d.line(out, fill=color, width=width, joint="curve")
    for q in (out[0], out[-1]):
        d.ellipse((q[0] - width / 2, q[1] - width / 2, q[0] + width / 2, q[1] + width / 2), fill=color)


def wobble_circle(cx, cy, rx, ry, seed=1, n=48, turns=1.08):
    rng = random.Random(seed)
    ph = rng.uniform(0, 6.28)
    return [(cx + rx * (1 + 0.04 * math.sin(k * 0.7 + ph)) * math.cos(-2.2 + turns * 2 * math.pi * k / n),
             cy + ry * (1 + 0.05 * math.cos(k * 0.5 + ph)) * math.sin(-2.2 + turns * 2 * math.pi * k / n))
            for k in range(n + 1)]


def layout_words(text, x0, x1, top, size, max_lines=4, min_size=36, center=False):
    """Har shabd ka dabba lautao (highlighter ke liye)."""
    f, s_, lines = fit_lines(text, x1 - x0, max_lines, size, min_size)
    lh = int(s_ * 1.42)
    sp = text_w(" ", f)
    boxes = []
    for li, ln in enumerate(lines):
        lw = sum(text_w(w, f) for w in ln) + sp * (len(ln) - 1)
        x = x0 + ((x1 - x0) - lw) / 2 if center else x0
        y = top + li * lh
        for w in ln:
            ww = text_w(w, f)
            boxes.append((w, x, y, x + ww, y + lh))
            x += ww + sp
    return f, boxes, top + len(lines) * lh


def print_words(cv, f, boxes, color=INK, hl=None, hl_col=HILITE, lit=None):
    """hl: kitne shabd highlighter se rang chuke (float - aadha shabd bhi). lit: shabd jo gaadhe (baaki halke)."""
    d = ImageDraw.Draw(cv, "RGBA")
    if hl is not None:
        for i, (w, x0, y0, x1, y1) in enumerate(boxes):
            k = clamp(hl - i)
            if k <= 0:
                break
            pad = 6
            d.rounded_rectangle((x0 - pad, y0 + 10, x0 - pad + (x1 - x0 + 2 * pad) * k, y1 - 8), radius=6,
                                fill=hl_col + (150,))
    for i, (w, x0, y0, x1, y1) in enumerate(boxes):
        col = color if (lit is None or i < lit) else mix(PAPER, color, 0.35)
        d.text((x0, (y0 + y1) / 2), w, font=f, fill=col, anchor="lm")


def spoken_count(sc, key, t, n):
    """Kitne shabd bole ja chuke (highlighter/gaadhe akshar ke liye)."""
    if key not in sc["marks"]:
        return n
    if sc.get("exact_words") and key in sc.get("wt", {}) and len(sc["wt"][key]) == n:
        wt = sc["wt"][key]
        c = 0.0
        for i, w in enumerate(wt):
            nx = wt[i + 1] if i + 1 < n else sc["marks"][key][1]
            c += clamp((t - (w - EYE_LEAD)) / max(0.08, nx - w))
        return c
    s0, s1 = sc["marks"][key]
    return n * clamp((t - s0 + EYE_LEAD) / max(0.2, s1 - s0))


OPT_TOP = 900
OPT_GAP = 172


def paper_page(cv, data, sc, t, m, highlight=True, hook_a=1.0):
    """Prashn-page: prashn sankhya, laal hook line, asli sawal, OMR options - teeno scene me BILKUL ek jagah."""
    global OPT_TOP
    d = ImageDraw.Draw(cv)
    ep = data.get("episode") or 0
    d.text((P_LEFT, 300), f"प्रश्न {ep}.", font=get_font(48), fill=INK, anchor="lm")
    hl = data.get("hook_line") or hook_line(data)
    f, s_, lines = fit_lines(hl, P_RIGHT - P_LEFT, 2, 84, 54)
    y = 420
    col = mix(PAPER, RED_PEN, hook_a)
    for ln in lines:
        d.text((P_LEFT, y), " ".join(ln), font=f, fill=col, anchor="lm")
        y += int(s_ * 1.22)
    uw = text_w(" ".join(lines[-1]), f) if lines else 300
    ink_stroke(ImageDraw.Draw(cv), [(P_LEFT, y - s_ * 0.52), (P_LEFT + uw * 0.5, y - s_ * 0.47 + 6),
                                    (P_LEFT + uw, y - s_ * 0.57)],
               ease_out_cubic(prog(t, 0.05, 0.5)) if sc["name"] == "hook" else 1.0, col, 6)
    fq, boxes, yb = layout_words(data["question"], P_LEFT, P_RIGHT, y + 16, 64, 3, 42)
    n = len(boxes)
    said = (spoken_count(sc, "q", t, n) if (sc["name"] == "hook" and "q" in m) else n) if highlight else None
    print_words(cv, fq, boxes, hl=said)
    OPT_TOP = int(yb + 100)
    return OPT_TOP


def opt_row_y(i):
    return OPT_TOP + i * OPT_GAP


def draw_omr_options(cv, data, filled=None, wrong_p=None, fill_col=INK, dim=None):
    """(A) (B) (C) (D) OMR gole + option text. wrong_p: {letter: 0-1 laal kaat}."""
    d = ImageDraw.Draw(cv, "RGBA")
    for i, (l, txt) in enumerate(data["options"]):
        y = opt_row_y(i)
        a = 1.0 if not dim else dim.get(l, 1.0)
        bx = P_LEFT + 40
        d.ellipse((bx - 38, y - 38, bx + 38, y + 38), outline=mix(PAPER, INK, a), width=5)
        if filled and l in filled:
            k = filled[l]
            r = 30 * k
            d.ellipse((bx - r, y - r, bx + r, y + r), fill=fill_col)
            d.text((bx, y), l, font=get_font(36), fill=PAPER if k > 0.7 else mix(PAPER, INK, a), anchor="mm")
        else:
            d.text((bx, y), l, font=get_font(36), fill=mix(PAPER, INK, a), anchor="mm")
        f, s_, lines = fit_lines(txt, P_RIGHT - (bx + 76), 1, 64, 38)
        eo = data.get("en_opt", {}).get(l, "") if en_on("options") else ""
        ty_ = y - (12 if eo else 0)
        d.text((bx + 76, ty_), " ".join(lines[0]) if lines else txt, font=f, fill=mix(PAPER, INK, a), anchor="lm")
        if eo:
            d.text((bx + 76, y + 40), eo, font=get_font_reg(28), fill=mix(PAPER, INK_SOFT, a), anchor="lm")
        if wrong_p and l in wrong_p:
            tw = text_w(" ".join(lines[0]) if lines else txt, f)
            x0, x1 = bx - 48, bx + 96 + tw
            ink_stroke(d, [(x0, ty_ + 4), ((x0 + x1) / 2, ty_ - 6), (x1, ty_ + 2)], wrong_p[l], RED_PEN, 9)


def pencil_hover(t, speed=1.0):
    """Pencil options ke beech hichkichati hai (kaun sa bharun?) - har pal halchal."""
    seq = [1, 3, 0, 2, 3, 1]
    step = 0.62 / speed
    k = t / step
    i = int(k) % len(seq)
    j = (int(k) + 1) % len(seq)
    e = ease_in_out(clamp((k - int(k)) * 1.6))
    y = opt_row_y(seq[i]) + (opt_row_y(seq[j]) - opt_row_y(seq[i])) * e
    x = P_LEFT + 40 + 10 * math.sin(t * 7)
    return x + 26, y + 18 + 8 * math.sin(t * 11)


def scene_hook_paper(cv, data, t, dur, m, vd, sc):
    fx = {}
    ep = data.get("episode") or 0
    st = rubber_stamp(f"EXAM TRAP  ·  S{SEASON} EP {ep}")
    paper_page(cv, data, sc, t, m)
    place(cv, st, W - 330, 300, scale=1.0 + 0.04 * math.sin(t * 9))
    draw_omr_options(cv, data)
    tx, ty = pencil_hover(t)
    draw_pencil(cv, tx, ty)
    if t >= 0.9:
        kk = ease_out_back(prog(t, 0.9, 0.3))
        place(cv, rubber_stamp("आपका जवाब? कमेंट करो", (30, 80, 170), 46, 3), W / 2, opt_row_y(3) + 190,
              scale=max(0.05, kk))
    return fx


def draw_exam_clock(cv, t, c0, cx, cy):
    cd = COUNTDOWN_SECONDS * COUNTDOWN_STEP
    tt = t - c0
    d = ImageDraw.Draw(cv)
    r = 70
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 252, 244), outline=INK, width=6)
    rem = clamp(1 - tt / cd) if tt >= 0 else 1.0
    d.pieslice((cx - r + 12, cy - r + 12, cx + r - 12, cy + r - 12), -90, -90 + 360 * rem, fill=(250, 200, 200))
    ang = -90 + 360 * (1 - rem)
    d.line((cx, cy, cx + 50 * math.cos(math.radians(ang)), cy + 50 * math.sin(math.radians(ang))), fill=RED_PEN,
           width=6)
    if 0 <= tt < cd:
        num = max(1, COUNTDOWN_SECONDS - int(tt / COUNTDOWN_STEP))
        d.text((cx + r + 30, cy), f"{num}", font=get_font(96), fill=RED_PEN, anchor="lm")
    elif tt >= cd:
        d.text((cx + r + 30, cy), "समय!", font=get_font(60), fill=RED_PEN, anchor="lm")


def paper_question_block(cv, data, y0=300):
    fq, boxes, yb = layout_words(data["question"], P_LEFT, P_RIGHT, y0, 52, 3, 38)
    print_words(cv, fq, boxes)
    return yb


def scene_question_paper(cv, data, t, dur, m, vd, sc):
    fx = {}
    paper_page(cv, data, sc, t, m, hook_a=0.55)
    place(cv, rubber_stamp(f"EXAM TRAP  ·  S{SEASON} EP {data.get('episode') or 0}"), W - 330, 300)
    draw_omr_options(cv, data)
    c0 = sc.get("cd_start", 0.4)
    cy = opt_row_y(3) + 200
    draw_exam_clock(cv, t, c0, P_LEFT + 80, cy)
    tx, ty = pencil_hover(t + 3, speed=1.8)                      # ghadi chalte hi pencil tez hichkichaati
    draw_pencil(cv, tx, ty)
    ImageDraw.Draw(cv).text((P_LEFT + 330, cy), "गोला भरो: कमेंट A/B/C/D", font=get_font(46), fill=INK,
                            anchor="lm")
    if c0 <= t < c0 + COUNTDOWN_SECONDS * COUNTDOWN_STEP:
        if ((t - c0) / COUNTDOWN_STEP) % 1 < 0.08:
            fx["shake"] = 3
    return fx


def scene_verdict_paper(cv, data, t, dur, m, vd, sc):
    fx = {}
    d = ImageDraw.Draw(cv)
    paper_page(cv, data, sc, t, m, hook_a=0.55)
    wrong = data["elim_order"]
    xt = dict(zip(wrong, VERDICT_X))
    wp = {l: ease_out_cubic(prog(t, xt[l], 0.22)) for l in wrong if t >= xt[l]}
    win = VERDICT_WIN
    filled = {data["correct"]: ease_out_cubic(prog(t, win, 0.25))} if t >= win else None
    dim = {l: (1 - 0.45 * wp.get(l, 0)) for l in wrong}
    draw_omr_options(cv, data, filled=filled, wrong_p=wp, dim=dim)
    ci = next(i for i, (l, _) in enumerate(data["options"]) if l == data["correct"])
    cy = opt_row_y(ci)
    dd = ImageDraw.Draw(cv, "RGBA")
    if t >= win:
        pc = ease_in_out(prog(t, win + 0.05, 0.45))
        ink_stroke(dd, wobble_circle(W / 2 - 10, cy + 4, (P_RIGHT - P_LEFT) / 2 + 24, 78, seed=ci), pc, GREEN_PEN, 9)
        pt = ease_out_cubic(prog(t, win + 0.4, 0.25))
        tick = [(P_RIGHT - 40, cy - 110), (P_RIGHT - 10, cy - 76), (P_RIGHT + 50, cy - 170)]
        ink_stroke(dd, tick, pt, GREEN_PEN, 12)
        if t < win + 0.12:
            fx["shake"] = 6
        k3 = ease_out_back(prog(t, win + 0.55, 0.3)) if t >= win + 0.55 else 0
        if k3 > 0.01:
            place(cv, rubber_stamp(f"सही जवाब: {data['correct']}", GREEN_PEN, 64, -5), W / 2, opt_row_y(3) + 200,
                  scale=max(0.05, 1.5 - 0.5 * k3))
        k4 = ease_out_back(prog(t, win + 0.8, 0.3)) if t >= win + 0.8 else 0
        if k4 > 0.01:
            place(cv, rubber_stamp("जो दोस्त गलत करेगा, उसे भेजो!", (30, 80, 170), 42, 2), W / 2,
                  opt_row_y(3) + 350, scale=max(0.05, k4))
    else:
        # teacher ki kalam: galat kaatte hue option se option
        cur = None
        for l in wrong:
            if t >= xt[l] - 0.12:
                cur = l
        if cur and t < win:
            i = next(i for i, (l, _) in enumerate(data["options"]) if l == cur)
            p = clamp((t - xt[cur]) / 0.22)
            draw_pencil(cv, P_LEFT + 20 + 300 * p, opt_row_y(i) + 6, angle=-30)
        if VERDICT_X[-1] + 0.2 <= t < win:
            a_ = 0.6 + 0.4 * math.sin(t * 16)
            d.text((W / 2, opt_row_y(3) + 200), "...और सही जवाब है", font=get_font(66),
                   fill=mix(PAPER, RED_PEN, a_), anchor="mm")
    return fx


@lru_cache(maxsize=8)
def sticky_note(w, h, color=NOTE):
    im = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((24, 28, w + 24, h + 30), fill=(0, 0, 0, 80))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(im)
    d.rectangle((14, 14, w + 14, h + 14), fill=color + (255,))
    d.rectangle((14, 14, w + 14, 60), fill=mix(color, (255, 200, 60), 0.5) + (255,))
    return im


@lru_cache(maxsize=4)
def tape_strip(w, h):
    rng = np.random.default_rng(3)
    a = np.zeros((h, w, 4), dtype=np.uint8)
    base = np.array([226, 214, 178], dtype=np.float32)
    a[..., :3] = np.clip(base + rng.normal(0, 6, (h, w, 1)), 0, 255)
    a[..., 3] = 245
    # tooti kinaari
    for x in range(w):
        cut = int(abs(math.sin(x * 0.9) * 6 + rng.normal(0, 2)))
        a[:cut, x, 3] = 0
        a[h - cut:, x, 3] = 0
    im = Image.fromarray(a, "RGBA")
    d = ImageDraw.Draw(im)
    d.text((w / 2, h / 2), "EXAM TRAP  —  अभी खुलेगा", font=get_font(44), fill=RED_PEN + (255,), anchor="mm")
    return im


def scene_rule_paper(cv, data, t, dur, m, vd, sc):
    fx = {}
    d = ImageDraw.Draw(cv)
    d.text((P_LEFT, 300), "उत्तर का कारण  (PO Guide Part I · Clause %s)" % data["clause_no"], font=get_font(38),
           fill=INK_SOFT, anchor="lm")
    # sticky note pe niyam; bolte-bolte highlighter
    k = ease_out_back(prog(t, 0.0, 0.3))
    nw = 900
    fq, boxes, yb = layout_words(data["fact"], 44, nw - 16, 90, 66, 5, 42)
    nh = int(yb + 40)
    note = sticky_note(nw, nh).copy()
    nd = ImageDraw.Draw(note)
    nd.text((44, 38), "नियम", font=get_font(40), fill=(120, 80, 0, 255), anchor="lm")
    said = spoken_count(sc, "fact", t, len(boxes))
    print_words_on = ImageDraw.Draw(note, "RGBA")
    for i, (w, x0, y0, x1, y1) in enumerate(boxes):
        kx = clamp(said - i)
        if kx > 0:
            print_words_on.rounded_rectangle((x0 - 6, y0 + 10, x0 - 6 + (x1 - x0 + 12) * kx, y1 - 8), radius=6,
                                             fill=(255, 150, 60, 120))
        print_words_on.text((x0, (y0 + y1) / 2), w, font=fq, fill=INK + (255,), anchor="lm")
    ang = 2.0 - 2.0 * (1 - k)
    place(cv, note.rotate(ang, expand=True, resample=Image.BICUBIC), W / 2 + 10, 380 + nh / 2,
          scale=max(0.05, 0.9 + 0.1 * k))
    # trap: tape se dhaka; trap ke pal tape ukhadti hai
    ts = trap_start(sc)
    box_top = 380 + nh + 120
    tf, tb, tyb = layout_words(data["trap"], P_LEFT + 20, P_RIGHT - 20, box_top + 50, 60, 3, 40, center=True)
    box_bot = max(tyb + 40, box_top + 230)
    dd = ImageDraw.Draw(cv, "RGBA")
    dd.rounded_rectangle((P_LEFT - 10, box_top, P_RIGHT + 10, box_bot), radius=18, outline=RED_PEN, width=5,
                         fill=(255, 235, 235, 255))
    if t >= ts:
        print_words(cv, tf, tb, color=RED_PEN, hl=spoken_count(sc, "trap", t, len(tb)), hl_col=(255, 200, 200))
        kk = prog(t, ts, 0.18)
        place(cv, rubber_stamp("EXAM TRAP", RED_PEN, 54, -8), P_RIGHT - 120, box_top - 10,
              scale=1.7 - 0.7 * ease_out_cubic(kk), alpha=clamp(kk * 3))
        if t - ts < 0.14:
            fx["shake"] = 7
    peel = ease_in_out(prog(t, ts - 0.15, 0.4))
    if peel < 1:
        tp = tape_strip(P_RIGHT - P_LEFT + 60, box_bot - box_top + 10)
        wig = 1.5 * math.sin(t * 25) if 0.4 < ts - t < 1.2 else 0
        place(cv, tp, W / 2 + peel * 1100, (box_top + box_bot) / 2, angle=-2 + wig - 14 * peel)
    return fx


def scene_cta_paper(cv, data, t, dur, m, vd, sc):
    fx = {}
    d = ImageDraw.Draw(cv)
    d.text((P_LEFT, 320), "याद रखिए", font=get_font(76), fill=RED_PEN, anchor="lm")
    ink_stroke(ImageDraw.Draw(cv), [(P_LEFT, 372), (P_LEFT + 340, 366)], ease_out_cubic(prog(t, 0.05, 0.3)),
               RED_PEN, 6)
    chips = yaad_chips(data["yaad"]) or [(data["yaad"], "")]
    y = 470
    for i, (txt, arrow) in enumerate(chips[:4]):
        k = ease_out_back(prog(t, 0.05 + 0.35 * i, 0.3)) if t >= 0.05 + 0.35 * i else 0
        if k <= 0.01:
            break
        last = i == len(chips[:4]) - 1
        f, s_, ls = fit_lines(txt, P_RIGHT - P_LEFT - 60, 2, 78, 44)
        tw = max(text_w(" ".join(l), f) for l in ls)
        hgt = int(s_ * 1.3) * len(ls)
        lay = Image.new("RGBA", (int(tw) + 60, hgt + 30), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        if last:
            ld.rounded_rectangle((0, 8, lay.width, lay.height - 4), radius=10, fill=HILITE + (170,))
        for j, l in enumerate(ls):
            ld.text((30, 15 + j * int(s_ * 1.3) + s_ * 0.65), " ".join(l), font=f, fill=INK + (255,), anchor="lm")
        place(cv, lay, W / 2, y + lay.height / 2, scale=max(0.05, k))
        y += lay.height + 20
        if not last:
            d.text((W / 2, y + 22), "↓", font=get_font(64), fill=RED_PEN, anchor="mm")
            y += 72
    m0 = 0.05 + 0.35 * len(chips[:4]) + 0.3
    if t >= m0:
        k2 = ease_out_back(prog(t, m0, 0.3))
        place(cv, rubber_stamp("FREE MOCK TEST: कमेंट करें MOCK", RED_PEN, 48, -3), W / 2, y + 170,
              scale=max(0.05, 1.5 - 0.5 * k2) * (1 + 0.02 * math.sin(t * 7)))
    if t >= m0 + 0.55:
        k3 = ease_out_back(prog(t, m0 + 0.55, 0.3))
        place(cv, rubber_stamp("ऐसे EXAM TRAP रोज़: FOLLOW " + IG_HANDLE, (30, 80, 170), 36, 2), W / 2, y + 340,
              scale=max(0.05, k3))
    return fx


PAPER_SCENES = {"hook": scene_hook_paper, "question": scene_question_paper, "verdict": scene_verdict_paper,
                "rule": scene_rule_paper, "cta": scene_cta_paper}
PAPER_PAGE = {"hook": 1, "question": 1, "verdict": 2, "rule": 3, "cta": 5}


def render_frame_paper(sc, data, gt, total):
    t = gt - sc["start"]
    cv = paper_base().copy()
    fx = PAPER_SCENES[sc["name"]](cv, data, t, sc["dur"], sc["marks"], sc["vdur"], sc) or {}
    page = PAPER_PAGE.get(sc["name"], 1)
    if sc["name"] == "rule" and t >= trap_start(sc):
        page = 4
    paper_header(cv, data, gt, total, page)
    shake = fx.get("shake", 0) or 0
    if shake > 0.5:
        rng = random.Random(int(gt * 1000))
        s = int(shake)
        base = Image.new("RGB", (W, H), PAPER)
        base.paste(cv, (rng.randint(-s, s), rng.randint(-s, s)))
        cv = base
    return cv


def page_turn(prev, cur, p):
    """Naya panna neeche se upar chadhta hai, pichhle pe parchhai - kitaab/copy palatne jaisa."""
    e = ease_in_out(clamp(p))
    off = int(H * (1 - e))
    out = prev.copy()
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    out = Image.blend(out, dark, 0.35 * e)
    out.paste(cur.crop((0, 0, W, H - off)), (0, off))
    d = ImageDraw.Draw(out, "RGBA")
    for k in range(24):
        d.line((0, off - k, W, off - k), fill=(0, 0, 0, int(60 * (1 - k / 24) * (1 - e))))
    return out


def build_timeline(specs, voices, data):
    timeline, cur = [], 0.0
    for i, (sp, voice) in enumerate(zip(specs, voices)):
        v, words = voice[0], voice[1]
        seg_starts = voice[2] if len(voice) > 2 else None
        lead = VOICE_LEAD + sp.get("delay", 0.0)          # verdict: pehle ✗ girte hain, fir awaaz
        vdur = len(v) / SR + lead
        dur = max(vdur + sp["tail"], sp["min"])
        if seg_starts and len(seg_starts) == len(sp["segs"]):
            marks, wt = marks_from_seg_starts(sp["segs"], [x + lead for x in seg_starts], vdur)
        else:
            if words:
                shifted = [(a + lead, b + lead, w) for a, b, w in words]
                marks, wt = compute_marks(sp["segs"], vdur, shifted)
            else:                                   # timing nahi mila: andaza awaaz ke shuru (lead) se, 0 se nahi
                marks, wt = compute_marks(sp["segs"], max(0.3, vdur - lead), None)
                marks = {k_: (a_ + lead, b_ + lead) for k_, (a_, b_) in marks.items()}
                wt = {k_: [x + lead for x in v_] for k_, v_ in wt.items()}
        # RULE: jo text padhna hai, use (shabd / READ_WPS) + ABSORB time zaroor mile
        for key, text in sp.get("read", []):
            need = marks[key][0] + len(text.split()) / READ_WPS + ABSORB
            dur = max(dur, min(need, vdur + (0.5 if HOOK_MODE == "pro" else 1.2)))       # awaaz ke baad max 1.2s (lamba text = lamba jama frame)
        if sp["name"] == "question" and HOOK_MODE == "pro":
            cd_start = 0.45                                  # naye 2 option aate hi ginti
            dur = max(dur, cd_start + COUNTDOWN_SECONDS * COUNTDOWN_STEP + 0.25)
        elif sp["name"] == "question" and MERGE_COUNTDOWN:
            cd_len = COUNTDOWN_SECONDS * COUNTDOWN_STEP
            opt_words = sum(len(t.split()) for _, t in data["options"])      # sawal hook me padh chuka
            need = min(4.0, 0.12 + opt_words / OPT_READ_WPS + 0.3)  # max ~1s jama (options agle scene me bhi dikhte)
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
            "vdur": vdur, "marks": marks, "wt": wt, "data": data, "lead": lead,
            "segs_text": list(sp["segs"]),
        }
        sc["exact_words"] = bool(words) and not (seg_starts and len(seg_starts) == len(sp["segs"]))
        if sp["name"] == "eliminate" and "x1" in marks:
            # ✗ tay taal par - screen ka ✗, 'buzz' aur uski awaaz ek hi pal (sab isi samay se chalte hain)
            x1, e1 = marks["x1"]                   # pehla ✗ = scene ki awaaz 'ये नहीं!' ki shuruaat
            cl_ = voice[3] if len(voice) > 3 and voice[3] else {}
            cd_ = {k_: len(a_) / SR for k_, a_ in cl_.items()}
            x2 = max(x1 + 0.5, e1 + 0.06)                      # agla ✗ tabhi jab pichhli awaaz khatam
            lf = x2 + max(0.45, cd_.get("x2", 0) + 0.06)
            x3 = lf + max(0.6, cd_.get("left", 0) + 0.15)
            marks.update({"x1": (x1, x2), "x2": (x2, lf), "left": (lf, x3), "x3": (x3, x3 + 0.4)})
            dur = max(dur, x3 + max(0.5, cd_.get("x3", 0) + 0.12))
            sc["dur"] = dur                     # agla scene bhi isi hisaab se (cur += dur)
            sc["clips"] = cl_
        if sp["name"] == "chitra" and "c1" in marks:
            cl_ = voice[3] if len(voice) > 3 and voice[3] else {}
            c1a, c1b = marks["c1"]
            d2 = len(cl_["c2"]) / SR if "c2" in cl_ else 1.6
            d3 = len(cl_["c3"]) / SR if "c3" in cl_ else 1.6
            c2a = c1b + CHITRA_GAP
            c3a = c2a + d2 + CHITRA_GAP + 0.15                   # ❌ dikhe + samjhe
            marks.update({"c1": (c1a, c1b), "c2": (c2a, c2a + d2), "c3": (c3a, c3a + d3)})
            for k_, (a_, b_) in (("c2", (c2a, c2a + d2)), ("c3", (c3a, c3a + d3))):
                ws_ = data["chitra"]["caps"][int(k_[1]) - 1].split()
                th_ = word_thresholds(ws_) if ws_ else []
                wt[k_] = [a_ + (b_ - a_) * x for x in th_]
            dur = c3a + d3 + CHITRA_GAP + 0.3                    # ✓ dekhne ka samay
            sc["dur"] = dur
            sc["marks"], sc["wt"] = marks, wt
            sc["clips"] = cl_
        if sp["name"] == "question" and (MERGE_COUNTDOWN or HOOK_MODE == "pro"):
            sc["cd_start"] = cd_start
        if sp["name"] == "hook":
            # stamp aakhri shabd (stake) ke saath girta hai
            sc["stamp_t"] = 0.3                          # stamp jaldi (pehle 2 sec me hi sab kuch)
        if sp["name"] == "question":
            # options sawal ke 60% pe aane lagte hain -> jab tak sawal khatam, options padhne layak
            sc["opt_t"] = [0.12 + j * 0.14 for j in range(4)]
            if HOOK_MODE == "pro":
                sc["opt_t"] = [0.05, 0.12, 0.19, 0.26]
            elif HOOK_MODE == "tease" and "q" in marks:
                qa, qb = marks["q"]
                later = iter([qa + 0.3 * (qb - qa), qa + 0.65 * (qb - qa)])
                pair = data.get("vs_pair") or []
                sc["opt_t"] = [0.0 if txt in pair else next(later, qb) for _, txt in data["options"]]
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
        prev_cache = {}
        for fi in range(n_frames):
            gt = fi / FPS
            while si + 1 < len(timeline) and gt >= timeline[si + 1]["start"]:
                si += 1
            frame = render_frame(timeline[si], data, gt, total)
            sc_ = timeline[si]
            tt_ = gt - sc_["start"]
            tr_ = 0.32 if REEL_STYLE == "paper" else TRANSITION
            if si > 0 and tt_ < tr_ and not is_seamless(sc_["name"]):
                # pichhla scene baayein dhakela jaata hai, naya daayein se aata hai (swipe jaisa)
                if si not in prev_cache:
                    prev_cache = {k_: v_ for k_, v_ in prev_cache.items() if k_ == "first"}
                    prev_cache[si] = render_frame(timeline[si - 1], data, sc_["start"] - 1.0 / FPS, total)
                if REEL_STYLE == "paper" and HOOK_MODE == "pro":
                    frame = page_turn(prev_cache[si], frame, tt_ / tr_)
                elif ANIM_SET == "flip":
                    frame = iris(prev_cache[si], frame, tt_ / TRANSITION)
                else:
                    frame = whip(prev_cache[si], frame, tt_ / TRANSITION)
            if HOOK_MODE == "pro" and gt > total - LOOP_BLEND:
                if "first" not in prev_cache:
                    prev_cache["first"] = render_frame(timeline[0], data, 0.0, total)
                q_ = clamp((gt - (total - LOOP_BLEND)) / LOOP_BLEND)
                dark_ = Image.new("RGB", (W, H), BG_BOTTOM)
                frame = Image.blend(frame, dark_, q_ * 2) if q_ < 0.5 else \
                    Image.blend(dark_, prev_cache["first"], (q_ - 0.5) * 2)
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
        (f"🚨 {SERIES_NAME} S{SEASON} EP {data['episode']} | " if data.get("episode") else "")
        + f"{data['question']} | GDS to MTS / Postman | PO Guide Part I Clause {data['clause_no']}",
    ] + ([f"🇬🇧 {en_q} (Answer in the reel 👀)"] if en_q else []) + [
        "",
        "सही उत्तर जानने के लिए पूरी रील देखें 👀",
        f"📘 स्रोत: PO Guide Part I, Clause {data['clause_no']}"
        + ("  (नया नियम - PO Guide 1985 के बाद बदला)" if data.get("basis") == "notes" else ""),
        f"🎯 FREE MOCK TEST चाहिए? कमेंट करें: {MOCK_KEYWORD}  |  Want a FREE MOCK TEST? Comment {MOCK_KEYWORD}",
        "📤 जो दोस्त ये गलत करेगा, उसे ये रील भेजो!",
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
    if part.get("basis") == "notes":
        go = part.get("guide_old") or ""
        src_line = (f"अपडेटेड नियम (Clause {clause_no})" + (f" - PO Guide (1985) में था: {go}" if go else ""))
    else:
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
    print("=" * 60)
    print(f"POSTAL WALA ENGINE: {ENGINE_VERSION}")
    print("ASLI CHITRA (Cloudflare):", "CHALU" if USE_PHOTO else
          "BAND - CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN secrets workflow me nahi mile (purane lifaafa/pata chitra chalenge)")
    print("=" * 60)
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
    if int(state.get("round", 1)) < RESTART_ROUND:
        print(f"NAYA DAUR {RESTART_ROUND}: Clause {RESTART_FROM_CLAUSE} Part 1 se dobara shuru (naye format me). "
              f"Clause {RESTART_FROM_CLAUSE} aur aage ke purane parts dobara banenge; pichhle clauses waise hi.")
        state["round"] = RESTART_ROUND
        state["clause_no"] = RESTART_FROM_CLAUSE
        state["current_part"] = 1
        save_state(state)
    if state["clause_no"] not in order:
        later = [n for n in order if n >= state["clause_no"]]
        state["clause_no"] = later[0] if later else order[0]
    # KRAM KABHI PEECHE NAHI: yaad-file (progress_state) peeche chali gayi ho (purana commit, purana
    # raasta) to jo sabse aage publish hua clause hai wahin se aage badho
    hi = highest_published_clause()
    if hi and hi in order and order.index(state["clause_no"]) < order.index(hi):
        print(f"Yaad-file Clause {state['clause_no']} pe thi, lekin Clause {hi} tak publish ho chuka - "
              f"kram aage se: Clause {hi}")
        state["clause_no"] = hi
        state["current_part"] = 1
        save_state(state)
    print("Current State:", {k: v for k, v in state.items() if k != "voice_rotation"})

    for pl in all_plans():
        enforce_lengths(pl)

    # 1) pichhle chhoote parts ko sudharne ki koshish
    try:
        repair_pass(clauses)
    except Exception as exc:
        print("Sudhaar pass me dikkat (aage badh rahe hain):", exc)

    # 2) aaj kya publish ho: pehle sudhara hua purana part, warna current clause ka agla part
    # pichhle clauses ke sudhare parts ab beech me NAHI (kram toot-ta tha: 16 ke baad 2, 4...)
    pick = pending_repaired(state["clause_no"]) if PUBLISH_OLD_REPAIRS else None
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
        refresh_style(plan, part)           # stock ke purane parts: naya aakarshak hook + teer wali yaad
    except Exception as exc:
        print("  Style refresh nahi hua:", str(exc)[:120])
    try:
        if HOOK_MODE != "tease":
            ensure_hook(plan, part)         # chhota aasaan hook (examiner-pass ho tabhi)
    except Exception as exc:
        print("  Hook nahi bana:", str(exc)[:120])
    try:
        if HOOK_MODE == "pro" and SHOW_CHITRA:
            ensure_chitra(plan, part)       # "चित्र से समझो" storyboard (examiner-pass ho tabhi)
            if not (CHITRA_PREVIEW and USE_PHOTO):
                ensure_chitra_ahead(plan, part)  # agle 2 parts ka bhi pehle se (fail/busy din ka bachav)
            if part_no >= total and nxt and not (CHITRA_PREVIEW and USE_PHOTO):
                np_ = load_plan(nxt)         # clause ka aakhri part: agle clause ka pehla part bhi (plan bana ho to)
                if np_:
                    ensure_chitra_ahead(np_, None, n=1)
    except Exception as exc:
        print("  Chitra nahi bana:", str(exc)[:120])
    try:
        ensure_trap(plan, part, clauses.get(num, ""))   # dohraav/gol-mol trap -> nayi kaam ki baat
    except Exception as exc:
        print("  Trap sudhaar nahi hua:", str(exc)[:120])
    cvs = part.get("chitra_v") or {}
    if CHITRA_PREVIEW and USE_PHOTO and HOOK_MODE == "pro" and SHOW_CHITRA and chitra_ready(cvs):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        pv = save_chitra_preview(part, os.path.join(OUTPUT_DIR, f"chitra_preview_clause_{num}_part_{part_no}.png"))
        print(f"\nCHITRA NAMOONA BANA: {pv}\n  Reel abhi NAHI banayi (CHITRA_PREVIEW=1). Chitra pasand aaye to "
              f"main.py me CHITRA_PREVIEW wali line me \"1\" ko \"0\" karke dobara chalaiye.")
        return
    if HOOK_MODE == "pro" and SHOW_CHITRA and REQUIRE_CHITRA and not chitra_ready(cvs):
        tries_ = int(cvs.get("tries", 0)) if int(cvs.get("v", 1)) >= CHITRA_SCHEMA else 0
        if tries_ < CHITRA_MAX_RUNS:
            print(f"RUKA: Clause {num} Part {part_no} ka chitra abhi nahi bana (koshish {tries_}/{CHITRA_MAX_RUNS}; "
                  f"wajah: {str(cvs.get('last_err', '-'))[:160]}). Bina chitra ki reel nahi - agli run me dobara.")
            return
        print(f"Chitra {CHITRA_MAX_RUNS} runs me nahi bana - is part ki reel 'आपके काम में' line ke saath.")
    try:
        if HOOK_MODE == "pro" and not (SHOW_CHITRA and (part.get("chitra_v") or {}).get("ok")):
            ensure_kaam(plan, part)         # "आपके काम में" line - sirf jab chitra na bana ho (API bachat)
    except Exception as exc:
        print("  Kaam-line nahi bani:", str(exc)[:120])
    try:
        ensure_beats(plan, part)            # niyam ke yaad-tukde (ek baar banke save)
    except Exception as exc:
        print("  Yaad-tukde nahi bane:", str(exc)[:120])
    data_in = dict(part)
    data_in["title"] = plan.get("title_hi") or plan.get("title_en", "")
    data = prepare_data(data_in, num, part_no, total_parts=total, next_title=next_title,
                        syllabus=(order.index(num) + 1 if num in order else None, len(order)))
    data["episode"] = int(state.get("episode", 0)) + 1
    if "s2_start" not in state:
        state["s2_start"] = data["episode"]          # Season 2 yahin se (save reel banne ke baad)
    data["new_badge"] = data["episode"] < int(state["s2_start"]) + NEW_BADGE_EPISODES
    data["challenge"] = CHALLENGE_LINES[data["episode"] % len(CHALLENGE_LINES)]
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
    part["published_round"] = RESTART_ROUND
    remember_reel(out)
    state["episode"] = data["episode"]
    save_state(state)
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

    # STOCK: taiyar (pass, unpublished) reels READY_BUFFER se kam hon to aage ke clause pehle se banao
    def ready_count():
        return sum(1 for n_ in clauses for p_ in ((load_plan(n_) or {}).get("parts") or [])
                   if p_.get("auto_check") and not p_.get("published"))
    k_ = state["clause_no"]
    built = 0
    while ready_count() < READY_BUFFER and built < 2 and not _RUN_FLAGS["busy"] and k_ in clauses:
        if load_plan(k_) is None:
            try:
                print(f"Stock ke liye clause {k_} ka plan bana raha hoon...")
                build_plan(k_, clauses)
                built += 1
            except ProviderBusy:
                _RUN_FLAGS["busy"] = True
                break
            except Exception as exc:
                print("Plan abhi nahi bana (agle run me):", str(exc)[:150])
                break
        nk = next_clause_no(k_, order)
        if nk is None or nk == k_:
            break
        k_ = nk
    print(f"Stock: {ready_count()} taiyar reels")

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
