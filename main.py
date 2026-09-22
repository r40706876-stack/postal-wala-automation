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


# -------------------- FONT & SHAPING HELPERS --------------------

def ensure_fonts():
    if not os.path.exists(FONT_DEV):
        url = (
            "https://github.com/googlefonts/noto-fonts/raw/main/"
            "hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        )
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        Path(FONT_DEV).write_bytes(response.content)


def get_font(size):
    ensure_fonts()
    try:
        return ImageFont.truetype(FONT_DEV, size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        return ImageFont.truetype(FONT_DEV, size)


def wrap_text(draw, text, size, max_width):
    words = text.split()
    if not words:
        return ""

    font = get_font(size)
    lines = []
    current = ""

    for word in words:
        candidate = word if not current else current + " " + word
        bbox = draw.textbbox((0, 0), candidate, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
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
    font = get_font(size)
    draw.text((W / 2, y), text, font=font, fill=fill, anchor="mm")


def brand(draw):
    font = get_font(27)
    draw.text((55, 45), "POSTAL WALA", font=font, fill="#64748B", anchor="la")


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
        (cx - radius, cy - radius, cx + radius, cy + radius),
        fill="#F8FAFC",
        outline="#CBD5E1",
        width=8,
    )

    for i in range(12):
        angle = math.radians(i * 30 - 90)
        x1 = cx + math.cos(angle) * (radius - 22)
        y1 = cy + math.sin(angle) * (radius - 22)
        x2 = cx + math.cos(angle) * (radius - 42)
        y2 = cy + math.sin(angle) * (radius - 42)
        draw.line((x1, y1, x2, y2), fill="#334155", width=7)

    hour_angle = math.radians((hour % 12) * 30 + minute * 0.5 - 90)
    minute_angle = math.radians(minute * 6 - 90)

    hx = cx + math.cos(hour_angle) * radius * 0.48
    hy = cy + math.sin(hour_angle) * radius * 0.48

    mx = cx + math.cos(minute_angle) * radius * 0.68
    my = cy + math.sin(minute_angle) * radius * 0.68

    draw.line((cx, cy, hx, hy), fill=RED, width=13)
    draw.line((cx, cy, mx, my), fill=BLUE, width=10)
    draw.ellipse((cx - 12, cy - 12, cx + 12, cy + 12), fill="#0F172A")


def draw_post_office(draw, cx, cy, scale=1.0, night=False):
    width = int(620 * scale)
    height = int(390 * scale)

    left = int(cx - width / 2)
    top = int(cy - height / 2)
    right = int(cx + width / 2)
    bottom = int(cy + height / 2)

    draw.rectangle(
        (left, top + 80, right, bottom),
        fill="#E5E7EB",
        outline="#CBD5E1",
        width=6,
    )

    draw.polygon(
        [
            (left - 25, top + 90),
            (cx, top - 70),
            (right + 25, top + 90),
        ],
        fill="#991B1B" if night else "#B91C1C",
    )

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
    font = get_font(32)
    draw.text((cx, sign_top + 38), "POST OFFICE", font=font, fill="#991B1B", anchor="mm")

    door_w = int(105 * scale)
    draw.rectangle(
        (cx - door_w, bottom - 190, cx + door_w, bottom),
        fill="#334155",
    )

    for offset in (-210, 210):
        wx = cx + int(offset * scale)
        draw.rectangle(
            (wx - 65, bottom - 180, wx + 65, bottom - 55),
            fill="#93C5FD",
            outline="#1E3A8A",
            width=5,
        )

    box_x = right - int(115 * scale)
    box_y = bottom - int(105 * scale)
    draw.rectangle(
        (box_x - 65, box_y - 100, box_x + 65, box_y + 100),
        fill="#B91C1C",
        outline="#7F1D1D",
        width=5,
    )
    draw.rectangle(
        (box_x - 42, box_y - 50, box_x + 42, box_y - 20),
        fill="#F8FAFC",
    )

    if night:
        draw.ellipse(
            (right - 125, top - 120, right - 45, top - 40),
            fill="#F8FAFC",
        )


def draw_x(draw, cx, cy, size=95):
    draw.line((cx - size, cy - size, cx + size, cy + size), fill=RED, width=22)
    draw.line((cx + size, cy - size, cx - size, cy + size), fill=RED, width=22)


def draw_check(draw, cx, cy, size=95):
    draw.line((cx - size, cy, cx - size // 3, cy + size), fill=GREEN, width=22)
    draw.line((cx - size // 3, cy + size, cx + size, cy - size), fill=GREEN, width=22)


def draw_authority_card(draw, label, x1, y1, x2, y2, status=None):
    outline = (
        GREEN if status == "correct"
        else RED if status == "wrong"
        else "#334155"
    )

    rounded(draw, (x1, y1, x2, y2), 30, CARD_2, outline, 5)
    center_text(draw, label, y1 + 58, 43, WHITE)

    if status == "wrong":
        draw_x(draw, (x1 + x2) // 2, y1 + 160, 52)
    elif status == "correct":
        draw_check(draw, (x1 + x2) // 2, y1 + 160, 52)


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

    if clause_no == 22 and part_no == 3:
        return {
            "title": title,
            "hook": "क्या खुला हुआ पार्सल दोबारा मुफ्त में भेजा जा सकता है?",
            "question": "यदि पतेदार ने पार्सल खोल दिया हो, तो पुनः प्रेषण का नियम क्या है?",
            "a": "नया डाकभार लगेगा",
            "b": "केवल आधा डाकभार लगेगा",
            "c": "पुनः प्रेषण निःशुल्क होगा",
            "d": "पुनः प्रेषण प्रतिबंधित है",
            "correct": "A",
            "fact": "एक बार खोले गए पार्सल को बिना नए डाकभार के पुनः प्रेषित नहीं किया जा सकता।",
            "trap": "पार्सल बंद होने पर आधा प्रभार लगता है, पर खुलते ही पूरा नया डाकभार लगेगा।",
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
        "clause_no": 22,
        "current_part": 2,
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
        default["clause_no"] = 22
        default["current_part"] = 2

    return default


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


def advance_state(state):
    clause_no = state["clause_no"]
    part_no = state["current_part"]

    total_parts = POSTAL_CLAUSE_CATALOG.get(clause_no, {}).get("total_parts", 1)

    if part_no < total_parts:
        state["current_part"] += 1
    else:
        all_clauses = sorted(POSTAL_CLAUSE_CATALOG.keys())
        try:
            current_index = all_clauses.index(clause_no)
            next_index = (current_index + 1) % len(all_clauses)
            state["clause_no"] = all_clauses[next_index]
            state["current_part"] = 1
        except ValueError:
            state["clause_no"] = all_clauses[0]
            state["current_part"] = 1

    save_state(state)
    print(f"अगले रन के लिए स्टेट सेट हुआ: Clause {state['clause_no']}, Part {state['current_part']}")
    return state


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
    filter_complex = inputs + f"concat=n={len(scene_paths)}:v=0:a=1[outa]"

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


# -------------------- SCENES RENDERING --------------------

def scene_0(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.12)

    draw_post_office(d, W // 2, 600, 0.72, night=True)

    if t > min(0.35, duration * 0.25):
        draw_clock(d, W // 2, 980, 130)

    wrapped_hook = wrap_text(d, data["hook"], 52, 950)
    lines = wrapped_hook.split("\n")
    y_start = 1200 - (len(lines) - 1) * 35
    for line in lines:
        center_text(d, line, y_start, 52, WHITE)
        y_start += 72

    center_text(d, "पहले जवाब मत देखिए", 1550, 36, MUTED)
    return im


def scene_1(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.25)

    rounded(d, (100, 450, W - 100, 1350), 40, CARD, CYAN, 4)
    center_text(d, "🧠 सोचिए और समझिए", 600, 56, YELLOW)

    wrapped_q = wrap_text(d, data["question"], 46, 820)
    lines = wrapped_q.split("\n")
    y_start = 800
    for line in lines:
        center_text(d, line, y_start, 46, WHITE)
        y_start += 65

    center_text(d, "क्या आपको नियम याद है?", 1150, 38, MUTED)
    return im


def scene_2(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.38)

    center_text(d, "गलत विकल्प हटाइए", 320, 50, CYAN)

    draw_authority_card(d, "सामान्य डाक नियम (गलत अनुमान)", 100, 500, W - 100, 780, status="wrong")
    draw_authority_card(d, "विभागीय सत्यापित नियम", 100, 880, W - 100, 1160, status="correct")

    center_text(d, "सही क्लॉज को पहचानें", 1350, 36, MUTED)
    return im


def scene_3(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.52)

    rounded(d, (80, 420, W - 80, 1420), 40, CARD_2, GREEN, 4)
    center_text(d, "📜 आधिकारिक नियम (Fact)", 560, 52, GREEN)

    wrapped_fact = wrap_text(d, data["fact"], 45, 840)
    lines = wrapped_fact.split("\n")
    y_start = 780
    for line in lines:
        center_text(d, line, y_start, 45, WHITE)
        y_start += 65

    center_text(d, f"विषय: {data['title']}", 1250, 34, MUTED)
    return im


def scene_4(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.65)

    rounded(d, (80, 420, W - 80, 1420), 40, CARD_2, RED, 4)
    center_text(d, "⚠️ परीक्षा का ट्रैप (Caution)", 560, 52, RED)

    wrapped_trap = wrap_text(d, data["trap"], 45, 840)
    lines = wrapped_trap.split("\n")
    y_start = 800
    for line in lines:
        center_text(d, line, y_start, 45, WHITE)
        y_start += 65

    center_text(d, "परीक्षा में ऐसी गलतियों से बचें!", 1250, 36, YELLOW)
    return im


def draw_options(d, data, highlighted=None):
    opts = [
        ("A", data["a"]),
        ("B", data["b"]),
        ("C", data["c"]),
        ("D", data["d"]),
    ]

    y = 820
    for key, text in opts:
        is_correct = (key == highlighted)
        box_fill = CARD_2
        outline = GREEN if is_correct else "#334155"
        text_color = GREEN if is_correct else WHITE

        rounded(d, (90, y, W - 90, y + 115), 25, box_fill, outline, 4 if is_correct else 2)

        font = get_font(38)
        d.text((130, y + 57), f"{key}.", font=font, fill=CYAN if not is_correct else GREEN, anchor="lm")
        d.text((210, y + 57), text, font=font, fill=text_color, anchor="lm")

        if is_correct:
            draw_check(d, W - 150, y + 57, 28)

        y += 140


def scene_5(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.78)

    rounded(d, (80, 260, W - 80, 680), 30, CARD, "#334155", 2)
    center_text(d, "प्रश्न (Question)", 340, 42, YELLOW)

    wrapped_q = wrap_text(d, data["question"], 40, 840)
    lines = wrapped_q.split("\n")
    y_start = 430
    for line in lines:
        center_text(d, line, y_start, 40, WHITE)
        y_start += 56

    draw_options(d, data)
    return im


def scene_6(data, t, duration):
    im = scene_5(data, t, duration)
    d = ImageDraw.Draw(im)
    progress_bar(d, 0.90)

    countdown = max(1, 5 - int(t))
    rounded(d, (W // 2 - 140, 1460, W // 2 + 140, 1600), 70, "#1E293B", YELLOW, 5)
    center_text(d, f"⏱️ {countdown}", 1530, 52, YELLOW)
    center_text(d, "जल्दी कमेंट करें!", 1680, 36, CYAN)
    return im


def scene_7(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 1.0)

    rounded(d, (80, 260, W - 80, 680), 30, CARD, GREEN, 3)
    center_text(d, "सही उत्तर (Correct Answer)", 340, 42, GREEN)

    wrapped_q = wrap_text(d, data["question"], 40, 840)
    lines = wrapped_q.split("\n")
    y_start = 430
    for line in lines:
        center_text(d, line, y_start, 40, WHITE)
        y_start += 56

    draw_options(d, data, highlighted=data["correct"])
    center_text(d, f"उत्तर है विकल्प {data['correct']}", 1530, 48, GREEN)
    return im


SCENE_RENDERERS = [
    scene_0,
    scene_1,
    scene_2,
    scene_3,
    scene_4,
    scene_5,
    scene_6,
    scene_7,
]


# -------------------- MAIN PIPELINE --------------------

async def main():
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    ensure_fonts()

    state = load_state()
    print(f"शुरू हो रहा है: Clause {state['clause_no']}, Part {state['current_part']}")

    data = generate_script(state)
    print("तैयार स्क्रिप्ट:", data["hook"])

    audio_files = await generate_scene_audios(data)
    durations = [audio_duration(p) for p in audio_files]

    combined_audio = "final_audio.aac"
    concat_audio(audio_files, combined_audio)

    # FFmpeg Video Process (Direct Pipe for optimal speed)
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{W}x{H}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "-",
        "-i", combined_audio,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        OUTPUT_VIDEO,
    ]

    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

    for idx, renderer in enumerate(SCENE_RENDERERS):
        duration = durations[idx]
        total_frames = max(1, int(round(duration * FPS)))

        for f in range(total_frames):
            t = f / FPS
            img = renderer(data, t, duration)
            proc.stdin.write(img.tobytes())

    proc.stdin.close()
    proc.wait()

    # Clean temporary audio files
    for p in audio_files:
        if os.path.exists(p):
            os.remove(p)
    if os.path.exists(combined_audio):
        os.remove(combined_audio)

    print(f"वीडियो सफलता से तैयार हो गया: {OUTPUT_VIDEO}")

    # अगली वीडियो के लिए स्टेट अपने आप अपडेट करें
    advance_state(state)


if __name__ == "__main__":
    asyncio.run(main())
