import os
import re
import json
import math
import asyncio
import subprocess
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
import edge_tts


# -------------------- CONFIG --------------------

OUTPUT_DIR = "generated_reels"
OUTPUT_VIDEO = "final_reel.mp4"
STATE_FILE = "progress_state.json"

VOICE_NAME = "hi-IN-SwaraNeural"
VOICE_RATE = "+8%"

W, H = 1080, 1920
FPS = 30

FONT_DEV = "NotoSansDevanagari-Bold.ttf"
FONT_EN_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Palette
BG = "#07111F"
CARD = "#0E1B2D"
CARD_2 = "#13263D"
WHITE = "#F8FAFC"
MUTED = "#9FB0C2"
RED = "#EF4444"
GREEN = "#22C55E"
YELLOW = "#F59E0B"
BLUE = "#2563EB"
CYAN = "#38BDF8"
PURPLE = "#8B5CF6"


# -------------------- VERIFIED CATALOG --------------------
# Keep these facts verified against your official study source.
# Do NOT let the AI invent facts outside these strings.

POSTAL_CLAUSE_CATALOG = {
    1: {
        "name": "डाक विभाग का नियंत्रण व संगठन",
        "total_parts": 2,
        "part_1_focus": "संचार मंत्रालय के अधीन महानिदेशक (DG Posts) शीर्ष प्रशासनिक प्रमुख हैं और मुख्यालय डाक भवन नई दिल्ली में स्थित है।",
        "part_2_focus": "डाक सेवा बोर्ड में एक चेयरमैन और 6 पूर्णकालिक सदस्य होते हैं।",
    },

    2: {
        "name": "डाकघरों के प्रकार और श्रेणियां",
        "total_parts": 3,
        "part_1_focus": "डाकघर की 3 प्रमुख श्रेणियां हैं: प्रधान डाकघर, उप डाकघर और शाखा डाकघर।",
        "part_2_focus": "उप डाकघर प्रधान डाकघर के अधीन रहकर लेन-देन करता है और दैनिक लेखा HO को भेजता है।",
        "part_3_focus": "ग्रामीण शाखा डाकघर के कार्य के घंटे न्यूनतम 4 घंटे और अधिकतम 5 घंटे प्रतिदिन निर्धारित किए जाते हैं।",
    },

    3: {
        "name": "रात्रि डाकघर के नियम",
        "total_parts": 3,
        "part_1_focus": "रात्रि डाकघर की स्थापना और कामकाज के घंटे रात 8:30 बजे तक बढ़ाने का विशेष अधिकार महानिदेशक (DG) को है।",
        "part_2_focus": "रविवार और राष्ट्रीय डाक अवकाशों पर रात्रि डाकघर सुबह 10 से शाम 5 बजे तक केवल सीमित सेवाएं देते हैं।",
        "part_3_focus": "रात्रि डाकघरों में रविवार और अवकाश के दिनों में मनीऑर्डर भुगतान या बचत बैंक निकासी कार्य नहीं होता।",
    },

    4: {
        "name": "मोबाइल डाकघर की व्यवस्था",
        "total_parts": 2,
        "part_1_focus": "मोबाइल डाकघर बड़े शहरों में देर शाम तक सामान्य डाक और पार्सल बुकिंग की सुविधा देते हैं।",
        "part_2_focus": "मोबाइल डाकघर में मनीऑर्डर, बचत बैंक और बीमा के वित्तीय कार्य प्रतिबंधित होते हैं।",
    },

    5: {
        "name": "डाकघर के कामकाज के घंटे",
        "total_parts": 3,
        "part_1_focus": "सामान्य डाक टिकट बिक्री और डाक बुकिंग पूरे कार्य समय तक होती है, जबकि बचत बैंक का समय पहले समाप्त होता है।",
        "part_2_focus": "सार्वजनिक काउंटर बंद होने के बाद निर्धारित लेट फीस का भुगतान करके ही डाक बुक की जा सकती है।",
        "part_3_focus": "शनिवार को सामान्य डाक लेन-देन के समय में विभागीय कटौती के नियम और समय-सारिणी लागू होती है।",
    },

    22: {
        "name": "डाक का पुनः निर्देशन",
        "total_parts": 3,
        "part_1_focus": "पतेदार के नया पता छोड़कर जाने पर प्रथम श्रेणी की अंतरदेशीय डाक का पुनः प्रेषण निःशुल्क होता है।",
        "part_2_focus": "पार्सल को वितरण क्षेत्र से बाहर पुनः प्रेषित करने पर आधा डाक प्रभार देय होता है।",
        "part_3_focus": "यदि पार्सल पतेदार द्वारा एक बार खोल दिया गया हो तो नए डाकभार के बिना पुनः निर्देशित नहीं किया जा सकता।",
    },

    23: {
        "name": "डाक पुनः प्रेषण के विशेष निर्देश",
        "total_parts": 2,
        "part_1_focus": "लिखित पुनः प्रेषण अनुदेश की वैधता अवधि अधिकतम 3 माह तक प्रभावी रहती है।",
        "part_2_focus": "विदेश जाने वाले पतेदारों और अस्थाई रूप से स्थान बदलने वाले व्यक्तियों के लिए विशेष डाक नियम लागू होते हैं।",
    },
}


# -------------------- FONT HELPERS --------------------

def ensure_fonts():
    if not os.path.exists(FONT_DEV):
        url = (
            "https://github.com/googlefonts/noto-fonts/raw/main/"
            "hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        )
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        Path(FONT_DEV).write_bytes(response.content)


def dev_font(size):
    ensure_fonts()
    return ImageFont.truetype(FONT_DEV, size)


def eng_font(size):
    for path in FONT_EN_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return dev_font(size)


def is_dev_char(ch):
    value = ord(ch)
    return 0x0900 <= value <= 0x097F


def mixed_width(draw, text, df, ef):
    total = 0
    for ch in text:
        total += draw.textlength(ch, font=df if is_dev_char(ch) else ef)
    return total


def draw_mixed(draw, x, y, text, size, fill=WHITE, anchor="lt"):
    df = dev_font(size)
    ef = eng_font(size)

    width = mixed_width(draw, text, df, ef)

    if anchor == "mm":
        x -= width / 2
    elif anchor == "ma":
        x -= width

    cursor = x
    for ch in text:
        font = df if is_dev_char(ch) else ef
        draw.text((cursor, y), ch, font=font, fill=fill)
        cursor += draw.textlength(ch, font=font)


def wrap_mixed(draw, text, size, max_width):
    # Word wrapping that works for Hindi and English.
    words = text.split()
    if not words:
        return ""

    lines = []
    current = ""

    df = dev_font(size)
    ef = eng_font(size)

    for word in words:
        candidate = word if not current else current + " " + word
        if mixed_width(draw, candidate, df, ef) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return "\n".join(lines)


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"[*_`#]+", "", text)
    text = text.replace("…", ".")
    return " ".join(text.split()).strip()


# -------------------- DRAWING HELPERS --------------------

def new_canvas():
    return Image.new("RGB", (W, H), BG)


def rounded(draw, box, radius=35, fill=CARD, outline=None, width=2):
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width,
    )


def center_text(draw, text, y, size, fill=WHITE):
    draw_mixed(draw, W / 2, y, text, size, fill, anchor="mm")


def brand(draw):
    draw_mixed(draw, 55, 45, "POSTAL WALA", 27, "#64748B")


def progress_bar(draw, ratio):
    left = 55
    right = W - 55
    y = 92

    draw.rounded_rectangle(
        (left, y, right, y + 8),
        radius=4,
        fill="#1B2A3A",
    )

    current = left + (right - left) * max(0.0, min(1.0, ratio))
    draw.rounded_rectangle(
        (left, y, current, y + 8),
        radius=4,
        fill=CYAN,
    )


def draw_clock(draw, cx, cy, radius=180, hour=8, minute=30):
    draw.ellipse(
        (cx-radius, cy-radius, cx+radius, cy+radius),
        fill="#F8FAFC",
        outline="#CBD5E1",
        width=8,
    )

    # Hour ticks
    for i in range(12):
        angle = math.radians(i * 30 - 90)
        x1 = cx + math.cos(angle) * (radius - 22)
        y1 = cy + math.sin(angle) * (radius - 22)
        x2 = cx + math.cos(angle) * (radius - 42)
        y2 = cy + math.sin(angle) * (radius - 42)
        draw.line((x1, y1, x2, y2), fill="#334155", width=7)

    # 8:30
    hour_angle = math.radians((hour % 12) * 30 + minute * 0.5 - 90)
    minute_angle = math.radians(minute * 6 - 90)

    hx = cx + math.cos(hour_angle) * radius * 0.48
    hy = cy + math.sin(hour_angle) * radius * 0.48

    mx = cx + math.cos(minute_angle) * radius * 0.68
    my = cy + math.sin(minute_angle) * radius * 0.68

    draw.line((cx, cy, hx, hy), fill=RED, width=13)
    draw.line((cx, cy, mx, my), fill=BLUE, width=10)
    draw.ellipse((cx-12, cy-12, cx+12, cy+12), fill="#0F172A")


def draw_post_office(draw, cx, cy, scale=1.0, night=False):
    width = int(620 * scale)
    height = int(390 * scale)

    left = int(cx - width / 2)
    top = int(cy - height / 2)
    right = int(cx + width / 2)
    bottom = int(cy + height / 2)

    # Building
    draw.rectangle(
        (left, top + 80, right, bottom),
        fill="#E5E7EB",
        outline="#CBD5E1",
        width=6,
    )

    # Roof
    draw.polygon(
        [
            (left - 25, top + 90),
            (cx, top - 70),
            (right + 25, top + 90),
        ],
        fill="#991B1B" if night else "#B91C1C",
    )

    # Sign
    sign_left = left + 65
    sign_right = right - 65
    sign_top = top + 115
    sign_bottom = top + 195

    draw.rectangle(
        (sign_left, sign_top, sign_right, sign_bottom),
        fill="#FFFFFF",
        outline="#CBD5E1",
        width=4,
    )
    draw_mixed(
        draw,
        cx,
        sign_top + 18,
        "POST OFFICE",
        32,
        "#991B1B",
        anchor="mm",
    )

    # Door
    door_w = int(105 * scale)
    draw.rectangle(
        (
            cx - door_w,
            bottom - 190,
            cx + door_w,
            bottom,
        ),
        fill="#334155",
    )

    # Windows
    for offset in (-210, 210):
        wx = cx + int(offset * scale)
        draw.rectangle(
            (wx-65, bottom-180, wx+65, bottom-55),
            fill="#93C5FD",
            outline="#1E3A8A",
            width=5,
        )

    # Post box
    box_x = right - int(115 * scale)
    box_y = bottom - int(105 * scale)
    draw.rectangle(
        (box_x-65, box_y-100, box_x+65, box_y+100),
        fill="#B91C1C",
        outline="#7F1D1D",
        width=5,
    )
    draw.rectangle(
        (box_x-42, box_y-50, box_x+42, box_y-20),
        fill="#F8FAFC",
    )

    if night:
        draw.ellipse(
            (right-125, top-120, right-45, top-40),
            fill="#F8FAFC",
        )


def draw_x(draw, cx, cy, size=95):
    draw.line(
        (cx-size, cy-size, cx+size, cy+size),
        fill=RED,
        width=22,
    )
    draw.line(
        (cx+size, cy-size, cx-size, cy+size),
        fill=RED,
        width=22,
    )


def draw_check(draw, cx, cy, size=95):
    draw.line(
        (cx-size, cy, cx-size//3, cy+size),
        fill=GREEN,
        width=22,
    )
    draw.line(
        (cx-size//3, cy+size, cx+size, cy-size),
        fill=GREEN,
        width=22,
    )


def draw_authority_card(draw, label, x1, y1, x2, y2, status=None):
    outline = (
        GREEN if status == "correct"
        else RED if status == "wrong"
        else "#334155"
    )

    rounded(draw, (x1, y1, x2, y2), 30, CARD_2, outline, 5)
    center_text(draw, label, y1 + 58, 43, WHITE)

    if status == "wrong":
        draw_x(draw, (x1+x2)//2, y1+160, 52)
    elif status == "correct":
        draw_check(draw, (x1+x2)//2, y1+160, 52)


# -------------------- SCRIPT --------------------

def extract_field(raw, name, next_names):
    next_part = "|".join(re.escape(x) for x in next_names)

    if next_part:
        pattern = (
            rf"(?:^|\n)\s*{re.escape(name)}\s*:\s*(.*?)"
            rf"(?=(?:\n\s*(?:{next_part})\s*:)|$)"
        )
    else:
        pattern = rf"(?:^|\n)\s*{re.escape(name)}\s*:\s*(.*)$"

    match = re.search(pattern, raw, re.I | re.S)
    return clean_text(match.group(1)) if match else ""


def fallback_script(clause_no, part_no, focus, title):
    # Explicit verified script for Night Post Office part 3.
    if clause_no == 3 and part_no == 3:
        return {
            "title": title,
            "hook": "रविवार को रात्रि डाकघर में कौन-सा काम नहीं होता?",
            "question": "रविवार और अवकाश के दिन रात्रि डाकघर में क्या नहीं होता?",
            "a": "मनीऑर्डर भुगतान",
            "b": "डाक स्वीकारना",
            "c": "सीमित सेवा",
            "d": "जनता की सेवा",
            "correct": "A",
            "fact": "रविवार और अवकाश के दिन मनीऑर्डर भुगतान तथा बचत बैंक निकासी नहीं होती।",
            "trap": "सीमित सेवाएं चल सकती हैं, लेकिन ये वित्तीय कार्य नहीं होते।",
        }

    # Explicit verified script for Night Post Office part 1.
    if clause_no == 3 and part_no == 1:
        return {
            "title": title,
            "hook": "रात्रि डाकघर का समय 8:30 बजे तक कौन बढ़ा सकता है?",
            "question": "रात्रि डाकघर के कामकाज के घंटे 8:30 बजे तक बढ़ाने का अधिकार किसे है?",
            "a": "महानिदेशक",
            "b": "Postmaster",
            "c": "SSPO",
            "d": "Head of Circle",
            "correct": "A",
            "fact": "रात्रि डाकघर के घंटे 8:30 बजे तक बढ़ाने का विशेष अधिकार महानिदेशक को है।",
            "trap": "यह अधिकार सामान्य स्थानीय अधिकारी को नहीं, महानिदेशक को दिया गया है।",
        }

    if clause_no == 3 and part_no == 2:
        return {
            "title": title,
            "hook": "रविवार को रात्रि डाकघर कितने बजे तक सीमित सेवा देता है?",
            "question": "रविवार और राष्ट्रीय डाक अवकाश पर रात्रि डाकघर का समय क्या है?",
            "a": "सुबह 10 से शाम 5",
            "b": "सुबह 8 से दोपहर 2",
            "c": "दोपहर 12 से शाम 6",
            "d": "पूरे दिन",
            "correct": "A",
            "fact": "रविवार और राष्ट्रीय डाक अवकाश पर सीमित सेवाएं सुबह 10 से शाम 5 बजे तक दी जाती हैं।",
            "trap": "यह सामान्य कार्यदिवस का 8:30 बजे वाला नियम नहीं है।",
        }

    # Clause 22 part 2 from the supplied catalog.
    if clause_no == 22 and part_no == 2:
        return {
            "title": title,
            "hook": "पार्सल दूसरे वितरण क्षेत्र में भेजने पर कितना प्रभार लगता है?",
            "question": "वितरण क्षेत्र से बाहर पार्सल पुनः प्रेषित करने पर कितना डाक प्रभार है?",
            "a": "आधा डाक प्रभार",
            "b": "पूर्ण डाक प्रभार",
            "c": "निःशुल्क",
            "d": "दोगुना प्रभार",
            "correct": "A",
            "fact": "वितरण क्षेत्र से बाहर भेजे जाने पर आधा डाक प्रभार देय होता है।",
            "trap": "वितरण क्षेत्र से बाहर जाने पर नियम बदलता है: आधा प्रभार याद रखें।",
        }

    return {
        "title": title,
        "hook": f"{title} का यह नियम ध्यान से देखिए।",
        "question": "दिए गए नियम के अनुसार सही बात कौन-सी है?",
        "a": "ऊपर दिया नियम",
        "b": "अलग नियम",
        "c": "कोई नियम नहीं",
        "d": "इनमें से कोई नहीं",
        "correct": "A",
        "fact": focus,
        "trap": "परीक्षा में शब्दों और अपवादों को ध्यान से पढ़ें।",
    }


def generate_script(state):
    clause_no = state["clause_no"]
    part_no = state["current_part"]

    info = POSTAL_CLAUSE_CATALOG[clause_no]
    title = info["name"]
    focus = info.get(f"part_{part_no}_focus", info["part_1_focus"])

    if not GROQ_API_KEY:
        return fallback_script(clause_no, part_no, focus, title)

    prompt = f"""
You are writing one short educational India Post departmental exam Reel.

TOPIC: {title}
PART: {part_no}/{info["total_parts"]}
VERIFIED FACT:
{focus}

Rules:
1. Use only the verified fact above.
2. Never invent statistics or claims.
3. Do not say 90 percent, 2 marks guaranteed, promotion guaranteed,
   most asked, repeated question, or similar unless the verified fact proves it.
4. Hook must be a direct curiosity question.
5. One rule only.
6. MCQ must be answerable directly from the verified fact.
7. Use simple Hindi.
8. Avoid emojis and decorative symbols.

Return exactly:
HOOK: [maximum 11 words]
QUESTION: [maximum 15 words]
A: [2-6 words]
B: [2-6 words]
C: [2-6 words]
D: [2-6 words]
CORRECT: [A/B/C/D]
FACT: [maximum 18 words]
TRAP: [maximum 16 words]
"""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": GROQ_API_KEY.strip(),
                "Content-Type": "application/json",
            },
            json={
                "model": "qwen/qwen3-32b",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 450,
            },
            timeout=25,
        )

        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]

        data = {
            "title": title,
            "hook": extract_field(raw, "HOOK", ["QUESTION"]),
            "question": extract_field(raw, "QUESTION", ["A"]),
            "a": extract_field(raw, "A", ["B"]),
            "b": extract_field(raw, "B", ["C"]),
            "c": extract_field(raw, "C", ["D"]),
            "d": extract_field(raw, "D", ["CORRECT"]),
            "correct": extract_field(raw, "CORRECT", ["FACT"]).upper(),
            "fact": extract_field(raw, "FACT", ["TRAP"]),
            "trap": extract_field(raw, "TRAP", []),
        }

        if data["correct"] not in {"A", "B", "C", "D"}:
            raise ValueError("Invalid CORRECT field")

        required = ["hook", "question", "a", "b", "c", "d", "fact", "trap"]
        if not all(data[k] for k in required):
            raise ValueError("Incomplete generated script")

        return data

    except Exception as exc:
        print("AI script fallback:", exc)
        return fallback_script(clause_no, part_no, focus, title)


# -------------------- STATE --------------------

def load_state():
    default = {
        # Set to 3/1 if you want the 8:30 PM authority Reel.
        # Set to 3/3 for the Sunday/holiday financial-service Reel.
        "clause_no": 3,
        "current_part": 1,
    }

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as file:
                saved = json.load(file)
                if isinstance(saved, dict):
                    default.update(saved)
        except Exception:
            pass

    if default["clause_no"] not in POSTAL_CLAUSE_CATALOG:
        default["clause_no"] = 3
        default["current_part"] = 1

    return default


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


# -------------------- AUDIO --------------------

async def make_audio(text, output):
    if os.path.exists(output):
        os.remove(output)

    tts = edge_tts.Communicate(
        text=text,
        voice=VOICE_NAME,
        rate=VOICE_RATE,
    )
    await tts.save(output)


def audio_duration(path):
    result = subprocess.check_output([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ])
    return float(result.decode().strip())


def tighten_audio(path):
    temp = path + ".tmp.mp3"

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", path,
                "-af",
                (
                    "silenceremove="
                    "start_periods=1:"
                    "start_threshold=-38dB:"
                    "stop_periods=-1:"
                    "stop_duration=0.08:"
                    "stop_threshold=-38dB"
                ),
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                temp,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.replace(temp, path)
    except Exception:
        if os.path.exists(temp):
            os.remove(temp)


# -------------------- SCENE AUDIO --------------------

def make_scene_text(data):
    # Short, direct sentences.
    # These correspond to the visual chapters exactly.
    return [
        data["hook"],
        "पहले सोचिए।",
        "गलत विकल्प हटाइए। सही अधिकारी या सही नियम कौन-सा है?",
        data["fact"],
        "परीक्षा का ट्रैप: " + data["trap"],
        (
            "अब सवाल देखिए। " + data["question"] +
            " विकल्प हैं: A, " + data["a"] +
            ". B, " + data["b"] +
            ". C, " + data["c"] +
            ". D, " + data["d"] + "."
        ),
        "आपका जवाब क्या है? पांच सेकंड में A, B, C या D कमेंट करें।",
        "सही उत्तर है विकल्प " + data["correct"] + ".",
    ]


async def generate_scene_audios(data):
    texts = make_scene_text(data)
    paths = []

    for index, text in enumerate(texts):
        path = f"scene_{index}.mp3"
        await make_audio(text, path)
        tighten_audio(path)
        paths.append(path)

    return paths


def concat_audio(scene_paths, output):
    command = ["ffmpeg", "-y"]

    for path in scene_paths:
        command += ["-i", path]

    inputs = "".join(f"[{i}:a]" for i in range(len(scene_paths)))
    filter_complex = (
        inputs +
        f"concat=n={len(scene_paths)}:v=0:a=1[outa]"
    )

    command += [
        "-filter_complex", filter_complex,
        "-map", "[outa]",
        "-c:a", "aac",
        "-b:a", "192k",
        output,
    ]

    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# -------------------- SCENES --------------------

def scene_hook(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.05)

    # Topic-specific Night Post Office visual.
    draw_post_office(d, W//2, 650, 0.72, night=True)

    # Clock enters after the first beat.
    if t > min(0.35, duration * 0.25):
        draw_clock(d, W//2, 1030, 130)

    center_text(d, data["hook"], 1260, 58, WHITE)
    center_text(d, "पहले जवाब मत देखिए", 1400, 36, YELLOW)

    return im


def scene_guess(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.14)

    center_text(d, "आप क्या चुनेंगे?", 260, 60, WHITE)

    # Three authority cards. The correct one is not revealed yet.
    labels = ["Postmaster", "SSPO", "DG Posts"]

    for i, label in enumerate(labels):
        y = 500 + i * 300
        draw_authority_card(
            d,
            label,
            170,
            y,
            910,
            y + 220,
            None,
        )

    center_text(d, "सोचिए", 1450, 46, YELLOW)
    return im


def scene_elimination(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.22)

    center_text(d, "दो विकल्प हटते हैं", 270, 54, WHITE)

    labels = ["Postmaster", "SSPO", "DG Posts"]

    # Sequential elimination.
    for i, label in enumerate(labels):
        status = None
        if i < 2 and t > 0.45 + i * 0.55:
            status = "wrong"
        if i == 2 and t > 1.5:
            status = "correct"

        y = 500 + i * 300
        draw_authority_card(
            d,
            label,
            170,
            y,
            910,
            y + 220,
            status,
        )

    return im


def scene_answer(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.30)

    center_text(d, "सही उत्तर", 300, 50, MUTED)

    # Visual event: clock + DG.
    draw_clock(d, W//2, 690, 190)

    center_text(d, "8:30 PM", 950, 78, CYAN)
    center_text(d, "DG Posts", 1090, 76, GREEN)
    center_text(d, "यही point याद रखें", 1260, 38, WHITE)

    return im


def scene_fact(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.39)

    draw_post_office(d, W//2, 620, 0.65, night=True)

    # Event: clock appears, then arrow to authority.
    if t > 0.35:
        draw_clock(d, W//2, 1010, 105)

    if t > 0.9:
        center_text(d, "DG Posts", 1210, 60, GREEN)

    fact = wrap_mixed(d, data["fact"], 42, 880)
    y = 1380
    for line in fact.split("\n"):
        center_text(d, line, y, 42, WHITE)
        y += 62

    return im


def scene_trap(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.50)

    rounded(d, (70, 270, 1010, 1570), 45, CARD, YELLOW, 5)

    center_text(d, "EXAM TRAP", 390, 62, YELLOW)

    # Wrong authority gets crossed out.
    if t < 0.8:
        center_text(d, "स्थानीय अधिकारी", 650, 55, WHITE)
    else:
        center_text(d, "स्थानीय अधिकारी", 650, 55, WHITE)
        draw_x(d, W//2, 790, 55)

    center_text(d, "DG Posts", 1020, 68, GREEN)
    draw_check(d, W//2, 1160, 55)

    trap = wrap_mixed(d, data["trap"], 38, 820)
    y = 1320
    for line in trap.split("\n"):
        center_text(d, line, y, 38, WHITE)
        y += 58

    return im


def draw_option_row(draw, letter, text, y, active=False):
    outline = CYAN if active else "#2A4058"
    rounded(draw, (65, y, 1015, y+145), 28, CARD_2, outline, 4)

    draw_mixed(draw, 105, y+43, letter + ".", 38, CYAN)
    draw_mixed(draw, 175, y+43, text, 38, WHITE)


def scene_mcq(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.64)

    center_text(d, "POSTAL MCQ", 245, 58, CYAN)

    question = wrap_mixed(d, data["question"], 47, 900)
    y = 365

    for line in question.split("\n"):
        center_text(d, line, y, 47, WHITE)
        y += 68

    options = [
        ("A", data["a"]),
        ("B", data["b"]),
        ("C", data["c"]),
        ("D", data["d"]),
    ]

    y0 = 610

    # Sequential option reveal.
    for i, (letter, text) in enumerate(options):
        reveal_at = i * 0.30
        if t >= reveal_at:
            draw_option_row(
                d,
                letter,
                text,
                y0 + i * 190,
                active=(t < reveal_at + 0.25),
            )

    return im


def scene_countdown(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.82)

    center_text(d, "अपना जवाब चुनिए", 270, 54, WHITE)

    # Keep the options visible, but do NOT reveal correct answer.
    options = [
        ("A", data["a"]),
        ("B", data["b"]),
        ("C", data["c"]),
        ("D", data["d"]),
    ]

    y0 = 500

    for i, (letter, text) in enumerate(options):
        draw_option_row(
            d,
            letter,
            text,
            y0 + i * 190,
            False,
        )

    remaining = max(1, 5 - int(t))
    center_text(d, str(remaining), 1510, 100, YELLOW)
    center_text(d, "A / B / C / D कमेंट करें", 1660, 42, WHITE)

    return im


def scene_result(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.96)

    center_text(d, "सही उत्तर", 360, 55, MUTED)

    rounded(
        d,
        (100, 500, 980, 1180),
        50,
        CARD,
        GREEN,
        6,
    )

    center_text(d, data["correct"], 650, 120, GREEN)

    key = {
        "A": "a",
        "B": "b",
        "C": "c",
        "D": "d",
    }[data["correct"]]

    center_text(d, data[key], 850, 48, WHITE)
    center_text(d, "नियम को ऐसे याद रखें", 1060, 38, MUTED)

    center_text(d, "अगले Postal MCQ के लिए", 1370, 38, WHITE)
    center_text(d, "@POSTAL_WALA", 1450, 48, CYAN)

    return im


# -------------------- FRAME / VIDEO BUILD --------------------

def render_scene(scene_function, data, duration, prefix):
    count = max(1, int(math.ceil(duration * FPS)))
    paths = []

    for index in range(count):
        t = index / FPS
        image = scene_function(data, t, duration)

        path = f"{prefix}_{index:05d}.jpg"
        image.save(path, quality=94, optimize=False)
        paths.append(path)

    return paths


def frames_to_video(frame_paths, output_path):
    concat_path = "frames.txt"

    with open(concat_path, "w", encoding="utf-8") as file:
        for frame in frame_paths:
            file.write(f"file '{os.path.abspath(frame)}'\n")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-r", str(FPS),
            "-f", "concat",
            "-safe", "0",
            "-i", concat_path,
            "-vf", f"fps={FPS},format=yuv420p",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "19",
            output_path,
        ],
        check=True,
    )

    os.remove(concat_path)


def mux(video, audio, output):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", video,
            "-i", audio,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output,
        ],
        check=True,
    )


# -------------------- MAIN --------------------

def build_reel(data, output_video=None):
    if not output_video:
        output_video = os.path.join(OUTPUT_DIR, OUTPUT_VIDEO)

    os.makedirs(os.path.dirname(output_video), exist_ok=True)

    scene_audios = asyncio.run(generate_scene_audios(data))

    # Exact audio duration for every scene = exact visual duration.
    durations = [audio_duration(path) for path in scene_audios]

    # Hard retention limits.
    # If TTS creates an excessively long scene, the voice is shortened by
    # the script constraints rather than stretching the visual.
    max_scene = [3.2, 2.4, 2.8, 3.5, 3.4, 6.8, 5.5, 3.0]

    for i in range(len(durations)):
        if durations[i] > max_scene[i]:
            print(
                f"WARNING: scene {i} is {durations[i]:.2f}s; "
                f"target max is {max_scene[i]:.2f}s."
            )

    # Use actual audio durations so visuals and speech never drift.
    scene_functions = [
        scene_hook,
        scene_guess,
        scene_elimination,
        scene_answer,
        scene_fact,
        scene_trap,
        scene_mcq,
        scene_countdown,
        scene_result,
    ]

    # We have 9 visual scenes but 8 audio chapters.
    # Chapter 2/3 share one audio chapter, so split it visually.
    audio_chapter_map = [
        (0, scene_functions[0]),
        (1, scene_functions[1]),
        (2, scene_functions[2]),
        (2, scene_functions[3]),
        (3, scene_functions[4]),
        (4, scene_functions[5]),
        (5, scene_functions[6]),
        (6, scene_functions[7]),
        (7, scene_functions[8]),
    ]

    # Allocate each visual scene from the corresponding audio chapter.
    chapter_remaining = durations[:]
    visual_durations = []

    # Fixed visual allocation inside the "elimination + answer" chapter.
    for scene_index, chapter_index in enumerate([0, 1, 2, 2, 3, 4, 5, 6, 7]):
        if scene_index == 2:
            visual_durations.append(chapter_remaining[2] * 0.48)
        elif scene_index == 3:
            visual_durations.append(chapter_remaining[2] * 0.52)
        else:
            visual_durations.append(chapter_remaining[chapter_index])

    # Render all scenes.
    frame_paths = []

    for i, (chapter_index, scene_function) in enumerate(audio_chapter_map):
        frame_paths += render_scene(
            scene_function,
            data,
            visual_durations[i],
            f"scene_{i}",
        )

    silent = "silent_reel.mp4"
    frames_to_video(frame_paths, silent)

    master_audio = "master_audio.m4a"
    concat_audio(scene_audios, master_audio)

    mux(silent, master_audio, output_video)

    # Cleanup
    for path in frame_paths:
        try:
            os.remove(path)
        except OSError:
            pass

    for path in scene_audios + [silent, master_audio]:
        try:
            os.remove(path)
        except OSError:
            pass

    total = audio_duration(output_video)

    print()
    print("==============================================")
    print("POSTAL WALA REEL V3 COMPLETE")
    print("==============================================")
    print(f"Output: {output_video}")
    print(f"Duration: {total:.2f} seconds")
    print("Structure:")
    print("Hook -> Guess -> Elimination -> Answer -> Rule")
    print("-> Exam Trap -> MCQ -> 5-second Countdown -> Answer Lock")
    print("No fake statistics. No long logo outro.")
    print("==============================================")


def advance_state(state):
    clause = state["clause_no"]
    part = state["current_part"]

    info = POSTAL_CLAUSE_CATALOG[clause]

    if part < info["total_parts"]:
        state["current_part"] = part + 1
    else:
        keys = sorted(POSTAL_CLAUSE_CATALOG)
        current_index = keys.index(clause)
        state["clause_no"] = keys[
            (current_index + 1) % len(keys)
        ]
        state["current_part"] = 1

    save_state(state)


if __name__ == "__main__":
    state = load_state()

    print("Current:", state)

    data = generate_script(state)

    print()
    print("SCRIPT")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    reels_dir = "generated_reels"
    os.makedirs(reels_dir, exist_ok=True)
    output_filename = f"reel_clause_{state['clause_no']}_part_{state['current_part']}.mp4"
    output_video_path = os.path.join(reels_dir, output_filename)

    build_reel(data, output_video_path)

    # Advance only after successful rendering.
    advance_state(state)
