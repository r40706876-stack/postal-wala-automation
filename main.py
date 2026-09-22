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
VOICE_RATE = "+14%"  # Brisk, energetic pacing

W, H = 1080, 1920
FPS = 30

FONT_FILE = "Mukta-Bold.ttf"
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/mukta/Mukta-Bold.ttf"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Sleek Dark Palette
BG = "#080E18"
CARD_BG = "#111C2E"
CARD_BORDER = "#1E2F47"
WHITE = "#FFFFFF"
MUTED = "#8EA0B5"
CYAN = "#38BDF8"
GREEN = "#10B981"
RED = "#EF4444"
YELLOW = "#F59E0B"


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

FALLBACK_SCRIPTS = {
    (23, 1): {
        "hook": "डाक रिडायरेक्शन का यह नियम 90% छात्र भूल जाते हैं!",
        "question": "लिखित पुनः प्रेषण अनुदेश (Redirection) की वैधता अधिकतम कितने समय तक रहती है?",
        "a": "अधिकतम 3 माह",
        "b": "6 माह",
        "c": "1 वर्ष",
        "d": "1 माह",
        "correct": "A",
        "fact": "लिखित पुनः प्रेषण अनुदेश की वैधता अवधि अधिकतम 3 माह तक मान्य रहती है।",
        "trap": "3 माह बाद नया लिखित आवेदन देना अनिवार्य होता है, स्वतः नवीनीकरण नहीं होता।",
    },
    (1, 1): {
        "hook": "डाक विभाग का सर्वोच्च प्रशासनिक प्रमुख कौन होता है?",
        "question": "संचार मंत्रालय के अधीन डाक विभाग का शीर्ष प्रशासनिक प्रमुख कौन है?",
        "a": "महानिदेशक (DG Posts)",
        "b": "डाक सचिव",
        "c": "पोस्टमास्टर जनरल",
        "d": "अधीक्षक डाकघर",
        "correct": "A",
        "fact": "महानिदेशक (DG Posts) विभाग के शीर्ष प्रशासनिक प्रमुख होते हैं।",
        "trap": "पोस्टमास्टर जनरल केवल सर्किल स्तर के प्रमुख होते हैं, पूरे विभाग के नहीं।",
    }
}


# -------------------- FONT & SHAPING HELPERS --------------------

def ensure_fonts():
    if not os.path.exists(FONT_FILE) or os.path.getsize(FONT_FILE) < 50000:
        response = requests.get(FONT_URL, timeout=30)
        response.raise_for_status()
        Path(FONT_FILE).write_bytes(response.content)


def get_font(size):
    ensure_fonts()
    try:
        return ImageFont.truetype(FONT_FILE, size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        return ImageFont.truetype(FONT_FILE, size)


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


def rounded(draw, box, radius=28, fill=CARD_BG, outline=None, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def center_text(draw, text, y, size, fill=WHITE):
    font = get_font(size)
    draw.text((W / 2, y), text, font=font, fill=fill, anchor="mm")


def draw_top_bar(draw, title, global_ratio):
    # Brand Tag
    font_brand = get_font(28)
    draw.text((60, 48), "POSTAL EXAM WALA", font=font_brand, fill=CYAN, anchor="la")

    # Clause Pill
    font_pill = get_font(24)
    pill_text = f"CLAUSE TEST • {title[:20]}"
    draw.text((W - 60, 48), pill_text, font=font_pill, fill=MUTED, anchor="ra")

    # Global Progress Bar
    left, right, y = 60, W - 60, 95
    draw.rounded_rectangle((left, y, right, y + 8), radius=4, fill="#1B2B3E")
    cur = left + (right - left) * max(0.0, min(1.0, global_ratio))
    draw.rounded_rectangle((left, y, cur, y + 8), radius=4, fill=CYAN)


def draw_option_card(draw, letter, text, y, state="normal"):
    """
    state can be: 'normal', 'highlight', 'correct', 'wrong'
    """
    x1, x2 = 70, W - 70
    h = 135

    if state == "correct":
        fill = "#064E3B"
        border = GREEN
        border_w = 4
        text_color = WHITE
        badge_fill = GREEN
        badge_text = WHITE
    elif state == "wrong":
        fill = "#0D1522"
        border = "#1E2A3A"
        border_w = 2
        text_color = "#52657A"
        badge_fill = "#1E2A3A"
        badge_text = "#52657A"
    elif state == "highlight":
        fill = "#1A2E47"
        border = CYAN
        border_w = 3
        text_color = WHITE
        badge_fill = CYAN
        badge_text = BG
    else:  # normal
        fill = CARD_BG
        border = CARD_BORDER
        border_w = 2
        text_color = WHITE
        badge_fill = "#1C2D42"
        badge_text = CYAN

    rounded(draw, (x1, y, x2, y + h), radius=24, fill=fill, outline=border, width=border_w)

    # Option Letter Badge (Circle/Square)
    bx, by = x1 + 30, y + 25
    draw.rounded_rectangle((bx, by, bx + 85, by + 85), radius=16, fill=badge_fill)
    f_badge = get_font(42)
    draw.text((bx + 42, by + 42), letter, font=f_badge, fill=badge_text, anchor="mm")

    # Option Text
    font_text = get_font(38)
    # Truncate slightly if line overflows
    draw.text((bx + 115, y + 67), text[:32], font=font_text, fill=text_color, anchor="lm")

    # Checkmark if correct
    if state == "correct":
        cx, cy = x2 - 60, y + 67
        # Draw bold green check
        draw.line((cx - 24, cy, cx - 8, cy + 18), fill=GREEN, width=8)
        draw.line((cx - 8, cy + 18, cx + 24, cy - 18), fill=GREEN, width=8)


# -------------------- SCRIPT GENERATOR --------------------

def extract_field(raw, name, next_names):
    next_part = "|".join(re.escape(x) for x in next_names)
    if next_part:
        pattern = rf"(?:^|\n)\s*{re.escape(name)}\s*:\s*(.*?)(?=(?:\n\s*(?:{next_part})\s*:)|$)"
    else:
        pattern = rf"(?:^|\n)\s*{re.escape(name)}\s*:\s*(.*)$"
    match = re.search(pattern, raw, re.I | re.S)
    return clean_text(match.group(1)) if match else ""


def generate_script(state):
    clause_no = state["clause_no"]
    part_no = state["current_part"]
    info = POSTAL_CLAUSE_CATALOG[clause_no]
    title = info["name"]
    focus = info.get(f"part_{part_no}_focus", info["part_1_focus"])

    if (clause_no, part_no) in FALLBACK_SCRIPTS:
        data = FALLBACK_SCRIPTS[(clause_no, part_no)].copy()
        data["title"] = title
        return data

    if not GROQ_API_KEY:
        return {
            "title": title,
            "hook": f"{title} का यह नियम परीक्षा में बार-बार पूछा जाता है!",
            "question": f"{title} के अनुसार कौन-सा विकल्प बिल्कुल सही है?",
            "a": focus[:32],
            "b": "कोई विशेष छूट लागू नहीं",
            "c": "अधीक्षक का पूर्व अनुमोदन",
            "d": "इनमें से कोई नहीं",
            "correct": "A",
            "fact": focus,
            "trap": "परीक्षा में शब्दों के हेरफेर से बचें।",
        }

    prompt = f"""
You are creating an ultra-fast high-retention MCQ for India Post departmental exams (PA/SA, Postman, MTS) in Hindi.

TOPIC: {title}
FACT: {focus}

Requirements:
1. HOOK: One high-curiosity sentence asking or challenging the viewer (max 10 words).
2. QUESTION: Clear, precise Hindi exam question directly testing this fact (max 13 words).
3. A, B, C, D: 4 short realistic options (2 to 4 words each). Exactly one must match the fact.
4. CORRECT: Single letter A, B, C, or D.
5. FACT: 1 crisp sentence explaining why it is correct (max 14 words).
6. TRAP: 1 common student mistake or confusion in exam (max 12 words).

Format exactly:
HOOK: ...
QUESTION: ...
A: ...
B: ...
C: ...
D: ...
CORRECT: [A/B/C/D]
FACT: ...
TRAP: ...
"""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 400,
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
            data["correct"] = "A"
        return data
    except Exception as exc:
        print("Fallback Triggered:", exc)
        return {
            "title": title,
            "hook": f"{title} का यह नियम परीक्षा में बार-बार पूछा जाता है!",
            "question": f"{title} के अनुसार कौन-सा विकल्प सत्य है?",
            "a": focus[:30],
            "b": "विभागीय अनुमोदन अनिवार्य",
            "c": "अतिरिक्त प्रभार देय होगा",
            "d": "केवल मंडल स्तर पर मान्य",
            "correct": "A",
            "fact": focus,
            "trap": "नियमों के अपवादों को ध्यान से याद रखें।",
        }


# -------------------- AUDIO GENERATION --------------------

async def make_audio(text, output):
    if os.path.exists(output):
        os.remove(output)
    tts = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate=VOICE_RATE)
    await tts.save(output)


def audio_duration(path):
    result = subprocess.check_output([
        "ffprobe", "-v", "error",
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
                "ffmpeg", "-y", "-i", path,
                "-af", "silenceremove=start_periods=1:start_threshold=-36dB:stop_periods=-1:stop_duration=0.06:stop_threshold=-36dB",
                "-c:a", "libmp3lame", "-b:a", "192k", temp,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.replace(temp, path)
    except Exception:
        if os.path.exists(temp):
            os.remove(temp)


def make_scene_scripts(data):
    """
    Streamlined 4-act script structure.
    Zero option-reading to eliminate waste and maximize retention!
    """
    return [
        # Scene 0: Hook & Question (Fast delivery)
        f"{data['hook']} सवाल है: {data['question']}",
        # Scene 1: Rapid Challenge & Countdown (Forces comment engagement!)
        "पांच सेकंड हैं आपके पास! सही विकल्प A, B, C या D कमेंट कीजिए।",
        # Scene 2: Snap Answer Reveal
        f"सही जवाब है, ऑप्शन {data['correct']}!",
        # Scene 3: High-Value Postal Rule & Exam Trap (Forces saves & shares)
        f"नियम याद रखें: {data['fact']} और परीक्षा का ट्रैप: {data['trap']}",
        # Scene 4: Quick Loop / Outro
        "अगले पोस्टल नियम के लिए अभी सेव और फॉलो करें।"
    ]


async def generate_all_audios(data):
    texts = make_scene_scripts(data)
    paths = []
    for idx, txt in enumerate(texts):
        path = f"part_{idx}.mp3"
        await make_audio(txt, path)
        tighten_audio(path)
        paths.append(path)
    return paths


def concat_audio(scene_paths, output):
    command = ["ffmpeg", "-y"]
    for p in scene_paths:
        command += ["-i", p]
    inputs = "".join(f"[{i}:a]" for i in range(len(scene_paths)))
    filter_complex = inputs + f"concat=n={len(scene_paths)}:v=0:a=1[outa]"
    command += [
        "-filter_complex", filter_complex,
        "-map", "[outa]",
        "-c:a", "aac",
        "-b:a", "192k",
        output,
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# -------------------- VISUAL SCENES --------------------

def render_question_box(draw, data):
    # Question Card
    rounded(draw, (65, 140, W - 65, 520), radius=32, fill=CARD_BG, outline=CARD_BORDER, width=3)

    # Category Pill
    draw.rounded_rectangle((100, 175, 410, 230), radius=14, fill="#192A40")
    f_pill = get_font(26)
    draw.text((255, 202), "DEPARTMENTAL MCQ", font=f_pill, fill=CYAN, anchor="mm")

    # Question Text
    font_q = get_font(44)
    wrapped = wrap_text(draw, data["question"], 44, 880)
    lines = wrapped.split("\n")[:4]
    y_start = 280
    for line in lines:
        draw.text((100, y_start), line, font=font_q, fill=WHITE, anchor="la")
        y_start += 58


def scene_0_question(data, t, dur, global_ratio):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    draw_top_bar(d, data["title"], global_ratio)
    render_question_box(d, data)

    # Show 4 options sequentially or all together
    options = [("A", data["a"]), ("B", data["b"]), ("C", data["c"]), ("D", data["d"])]
    y0 = 570
    for idx, (letter, text) in enumerate(options):
        draw_option_card(d, letter, text, y0 + idx * 160, state="normal")

    # Bottom Prompt
    center_text(d, "प्रश्न को ध्यान से पढ़ें...", 1380, 36, MUTED)
    return im


def scene_1_countdown(data, t, dur, global_ratio):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    draw_top_bar(d, data["title"], global_ratio)
    render_question_box(d, data)

    # All options visible
    options = [("A", data["a"]), ("B", data["b"]), ("C", data["c"]), ("D", data["d"])]
    y0 = 570
    for idx, (letter, text) in enumerate(options):
        draw_option_card(d, letter, text, y0 + idx * 160, state="normal")

    # Animated 5-Second Timer Bar & Pulsing Callout
    rem = max(1, 5 - int((t / max(dur, 0.1)) * 5))

    # Timer Card Bottom
    rounded(d, (100, 1260, W - 100, 1500), radius=28, fill="#132338", outline=YELLOW, width=3)
    center_text(d, f"TIME LEFT: {rem}s", 1330, 48, YELLOW)
    center_text(d, "अपना उत्तर A, B, C या D कमेंट करें! 👇", 1430, 38, WHITE)

    # Dynamic Depleting Bar
    progress = 1.0 - (t / max(dur, 0.01))
    bx1, bx2 = 140, W - 140
    draw.rounded_rectangle((bx1, 1375, bx2, 1387), radius=6, fill="#0A1420")
    draw.rounded_rectangle((bx1, 1375, bx1 + (bx2 - bx1) * max(0.0, min(1.0, progress)), 1387), radius=6, fill=YELLOW)

    return im


def scene_2_reveal(data, t, dur, global_ratio):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    draw_top_bar(d, data["title"], global_ratio)
    render_question_box(d, data)

    correct_key = data.get("correct", "A").upper()
    options = [("A", data["a"]), ("B", data["b"]), ("C", data["c"]), ("D", data["d"])]
    y0 = 570

    for idx, (letter, text) in enumerate(options):
        if letter == correct_key:
            draw_option_card(d, letter, text, y0 + idx * 160, state="correct")
        else:
            draw_option_card(d, letter, text, y0 + idx * 160, state="wrong")

    # Victory Prompt
    center_text(d, f"✓ सही उत्तर है: विकल्प {correct_key}", 1380, 52, GREEN)
    return im


def scene_3_rule_and_trap(data, t, dur, global_ratio):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    draw_top_bar(d, data["title"], global_ratio)

    center_text(d, "परीक्षा के लिए अति-महत्वपूर्ण नियम", 230, 48, CYAN)

    # Rule Card (Green Accent)
    rounded(d, (70, 330, W - 70, 780), radius=32, fill="#072019", outline=GREEN, width=4)
    # Rule Badge
    draw.rounded_rectangle((110, 370, 420, 430), radius=14, fill="#0E3D30")
    f_b = get_font(28)
    draw.text((265, 400), "VERIFIED RULE", font=f_b, fill=GREEN, anchor="mm")

    wrapped_rule = wrap_text(d, data["fact"], 42, 850)
    lines_r = wrapped_rule.split("\n")[:5]
    yr = 470
    for line in lines_r:
        draw.text((110, yr), line, font=get_font(42), fill=WHITE, anchor="la")
        yr += 58

    # Trap Card (Amber / Red Accent)
    rounded(d, (70, 840, W - 70, 1340), radius=32, fill="#231508", outline=YELLOW, width=4)
    # Trap Badge
    draw.rounded_rectangle((110, 880, 420, 940), radius=14, fill="#422606")
    draw.text((265, 910), "EXAM TRAP ⚠️", font=f_b, fill=YELLOW, anchor="mm")

    wrapped_trap = wrap_text(d, data["trap"], 42, 850)
    lines_t = wrapped_trap.split("\n")[:5]
    yt = 980
    for line in lines_t:
        draw.text((110, yt), line, font=get_font(42), fill=WHITE, anchor="la")
        yt += 58

    center_text(d, "यहीं पर 90% छात्र गलती करते हैं!", 1450, 40, MUTED)
    return im


def scene_4_outro(data, t, dur, global_ratio):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    draw_top_bar(d, data["title"], global_ratio)

    # Revision Card
    rounded(d, (90, 440, W - 90, 1260), radius=40, fill=CARD_BG, outline=CYAN, width=4)

    center_text(d, "POSTAL EXAM REVISION", 560, 44, MUTED)
    center_text(d, "@POSTAL_WALA", 680, 72, CYAN)

    center_text(d, "नियम याद रखने के लिए Reel को Save करें", 860, 40, WHITE)
    center_text(d, "और अपने सहकर्मियों के साथ Share करें! 🚀", 940, 40, YELLOW)

    rounded(d, (200, 1060, W - 200, 1160), radius=25, fill=CYAN)
    f_btn = get_font(38)
    draw.text((W / 2, 1110), "DAILY POSTAL RULES", font=f_btn, fill=BG, anchor="mm")
    return im


# -------------------- RENDER PIPELINE --------------------

def render_scene(scene_fn, data, duration, prefix, start_global_t, total_duration):
    count = max(1, int(math.ceil(duration * FPS)))
    paths = []
    for idx in range(count):
        t = idx / FPS
        current_global_t = start_global_t + t
        global_ratio = current_global_t / max(total_duration, 0.01)

        im = scene_fn(data, t, duration, global_ratio)
        path = f"{prefix}_{idx:05d}.jpg"
        im.save(path, quality=93, optimize=False)
        paths.append(path)
    return paths


def frames_to_video(frame_paths, output_path):
    concat_path = "frames.txt"
    with open(concat_path, "w", encoding="utf-8") as f:
        for p in frame_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-r", str(FPS),
            "-f", "concat",
            "-safe", "0",
            "-i", concat_path,
            "-vf", f"fps={FPS},format=yuv420p",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            output_path,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if os.path.exists(concat_path):
        os.remove(concat_path)


def mux(video, audio, output):
    subprocess.run(
        [
            "ffmpeg", "-y",
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# -------------------- MAIN BUILD REEL --------------------

def build_reel(data, output_video=None):
    if not output_video:
        output_video = os.path.join(OUTPUT_DIR, OUTPUT_VIDEO)

    os.makedirs(os.path.dirname(output_video), exist_ok=True)

    print("Generating audio scenes...")
    scene_audios = asyncio.run(generate_all_audios(data))
    durations = [audio_duration(p) for p in scene_audios]
    total_audio_time = sum(durations)
    print(f"Total Reel Duration: {total_audio_time:.2f}s (Optimal for High Retention)")

    scene_functions = [
        scene_0_question,
        scene_1_countdown,
        scene_2_reveal,
        scene_3_rule_and_trap,
        scene_4_outro,
    ]

    frame_paths = []
    accumulated_time = 0.0

    print("Rendering video frames...")
    for idx, scene_fn in enumerate(scene_functions):
        dur = durations[idx]
        frame_paths += render_scene(
            scene_fn,
            data,
            dur,
            f"sc_{idx}",
            accumulated_time,
            total_audio_time,
        )
        accumulated_time += dur

    silent_video = "temp_silent.mp4"
    frames_to_video(frame_paths, silent_video)

    master_audio = "temp_audio.m4a"
    concat_audio(scene_audios, master_audio)

    print("Final Muxing...")
    mux(silent_video, master_audio, output_video)

    # Cleanup temp files
    for p in frame_paths:
        try:
            os.remove(p)
        except OSError:
            pass

    for p in scene_audios + [silent_video, master_audio]:
        try:
            os.remove(p)
        except OSError:
            pass

    print(f"SUCCESS: Video generated at '{output_video}'")


# -------------------- STATE ENGINE --------------------

def load_state():
    default = {"clause_no": 23, "current_part": 1}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    default.update(saved)
        except Exception:
            pass
    if default["clause_no"] not in POSTAL_CLAUSE_CATALOG:
        default["clause_no"] = 23
        default["current_part"] = 1
    return default


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def advance_state(state):
    clause = state["clause_no"]
    part = state["current_part"]
    info = POSTAL_CLAUSE_CATALOG[clause]

    if part < info["total_parts"]:
        state["current_part"] = part + 1
    else:
        keys = sorted(POSTAL_CLAUSE_CATALOG)
        current_index = keys.index(clause)
        state["clause_no"] = keys[(current_index + 1) % len(keys)]
        state["current_part"] = 1

    save_state(state)


if __name__ == "__main__":
    state = load_state()
    print("Processing State:", state)

    data = generate_script(state)
    print("\nGenerated Script Payload:")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    reels_dir = OUTPUT_DIR
    os.makedirs(reels_dir, exist_ok=True)
    out_file = os.path.join(reels_dir, f"postal_rule_{state['clause_no']}_p{state['current_part']}.mp4")

    build_reel(data, out_file)
    advance_state(state)
