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
VOICE_RATE = "+10%"

W, H = 1080, 1920
FPS = 30

FONT_FILE = "Mukta-Bold.ttf"
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/mukta/Mukta-Bold.ttf"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Palette matching video
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


# -------------------- CURATED FALLBACK BANK --------------------

FALLBACK_SCRIPTS = {
    (1, 1): {
        "hook": "डाक विभाग का सर्वोच्च प्रशासनिक प्रमुख कौन होता है?",
        "question": "डाक विभाग का शीर्ष प्रशासनिक प्रमुख कौन होता है?",
        "a": "महानिदेशक (DG Posts)",
        "b": "डाक सचिव",
        "c": "पोस्टमास्टर जनरल",
        "d": "अधीक्षक डाकघर",
        "correct": "A",
        "fact": "संचार मंत्रालय के अधीन महानिदेशक (DG Posts) शीर्ष प्रशासनिक प्रमुख हैं।",
        "trap": "पोस्टमास्टर जनरल केवल सर्किल स्तर के प्रमुख होते हैं, विभाग के नहीं।"
    },
    (23, 1): {
        "hook": "डाक पुनः प्रेषण के लिखित निर्देश कितने समय मान्य रहते हैं?",
        "question": "लिखित पुनः प्रेषण अनुदेश (Redirection) की वैधता अवधि क्या है?",
        "a": "अधिकतम 3 माह",
        "b": "6 माह",
        "c": "1 वर्ष",
        "d": "1 माह",
        "correct": "A",
        "fact": "लिखित पुनः प्रेषण अनुदेश की वैधता अवधि अधिकतम 3 माह तक होती है।",
        "trap": "3 महीने पूरे होने के बाद नया लिखित निर्देश देना आवश्यक होता है।"
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

def rounded(draw, box, radius=35, fill=CARD, outline=None, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

def center_text(draw, text, y, size, fill=WHITE):
    font = get_font(size)
    draw.text((W / 2, y), text, font=font, fill=fill, anchor="mm")

def brand(draw):
    font = get_font(27)
    draw.text((55, 45), "POSTAL WALA", font=font, fill="#64748B", anchor="la")

def progress_bar(draw, ratio):
    left = 55
    right = W - 55
    y = 86
    draw.rounded_rectangle((left, y, right, y + 8), radius=4, fill="#1B2A3A")
    current = left + (right - left) * max(0.0, min(1.0, ratio))
    draw.rounded_rectangle((left, y, current, y + 8), radius=4, fill=CYAN)

def draw_scrolling_target_badge(draw, t):
    text = "GDS TO MTS / PM / PA"
    font_badge = get_font(38)
    bbox = draw.textbbox((0, 0), text, font=font_badge)
    text_w = bbox[2] - bbox[0]
    speed = 150 
    total_width = W + text_w
    x_pos = W - (t * speed) % total_width
    box = (100, 115, W - 100, 185)
    draw.rounded_rectangle(box, radius=18, fill="#881337", outline="#F43F5E", width=3)
    mask = Image.new('L', (W, H), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(box, radius=18, fill=255)
    text_img = Image.new('RGBA', (W, H), (0,0,0,0))
    text_draw = ImageDraw.Draw(text_img)
    text_draw.text((x_pos, 150), text, font=font_badge, fill=WHITE, anchor="lm")
    draw._image.paste(text_img, (0,0), mask)

def draw_animated_x(draw, cx, cy, progress, size=32):
    p1 = min(1.0, max(0.0, progress / 0.5))
    draw.line((cx - size, cy - size, cx - size + 2 * size * p1, cy - size + 2 * size * p1), fill=RED, width=12)
    if progress > 0.5:
        p2 = min(1.0, max(0.0, (progress - 0.5) / 0.5))
        draw.line((cx + size, cy - size, cx + size - 2 * size * p2, cy - size + 2 * size * p2), fill=RED, width=12)

def draw_animated_check(draw, cx, cy, progress, size=32):
    p1 = min(1.0, max(0.0, progress / 0.35))
    x0, y0 = cx - size, cy
    x1, y1 = cx - size // 3, cy + size
    curr_x1 = x0 + (x1 - x0) * p1
    curr_y1 = y0 + (y1 - y0) * p1
    draw.line((x0, y0, curr_x1, curr_y1), fill=GREEN, width=13)
    if progress > 0.35:
        p2 = min(1.0, max(0.0, (progress - 0.35) / 0.65))
        x2, y2 = cx + size, cy - size
        curr_x2 = x1 + (x2 - x1) * p2
        curr_y2 = y1 + (y2 - y1) * p2
        draw.line((x1, y1, curr_x2, curr_y2), fill=GREEN, width=13)

def draw_option_card(draw, letter, text, y, status=None, anim_prog=1.0):
    x1, x2 = 100, W - 100
    h = 160
    if status == "correct":
        fill = "#064E3B"
        outline = GREEN
        border_w = 4
        text_color = WHITE
    elif status == "wrong":
        fill = CARD_2
        outline = RED
        border_w = 4
        text_color = "#64748B"
    else:
        fill = CARD_2
        outline = "#1E2F47"
        border_w = 2
        text_color = WHITE

    rounded(draw, (x1, y, x2, y + h), 26, fill, outline, border_w)
    card_label = f"{letter}. {text}"
    center_text(draw, card_label, y + 80, 42, text_color)

    cx = (x1 + x2) // 2
    if status == "wrong":
        draw_animated_x(draw, cx, y + 105, progress=anim_prog, size=30)
    elif status == "correct":
        draw_animated_check(draw, cx, y + 105, progress=anim_prog, size=30)


# -------------------- SCRIPT --------------------

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

    if not GROQ_API_KEY:
        if (clause_no, part_no) in FALLBACK_SCRIPTS:
            data = FALLBACK_SCRIPTS[(clause_no, part_no)].copy()
            data["title"] = title
            data["clause_no"] = clause_no
            return data
        return None

    prompt = f"""
You are creating an authentic India Post departmental exam Multiple Choice Question (MCQ) in Hindi.

TOPIC: {title}
PART: {part_no}/{info["total_parts"]}
OFFICIAL VERIFIED FACT:
{focus}

Instructions:
1. Create 1 genuine departmental exam question directly testable from the verified fact.
2. HOOK: One sharp, curiosity question directly related to the fact (max 10 words).
3. QUESTION: Clear, precise Hindi exam question (max 14 words).
4. A, B, C, D: 4 plausible options (2-5 words each). One must strictly match the verified fact.
5. CORRECT: Single letter A, B, C, or D.
6. FACT: Concise one-sentence summary of the rule (max 18 words).
7. TRAP: One common misconception or exam confusion (max 16 words).
8. Absolutely no meta text, no dummy options. Do NOT use emojis.

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
            "clause_no": clause_no
        }
        if data["correct"] not in {"A", "B", "C", "D"}:
            raise ValueError("Invalid CORRECT field")
        required = ["hook", "question", "a", "b", "c", "d", "fact", "trap"]
        if not all(data.get(k) for k in required):
            raise ValueError("Incomplete generated script")
        return data

    except Exception as exc:
        print("Using Curated Fallback Script:", exc)
        if (clause_no, part_no) in FALLBACK_SCRIPTS:
            data = FALLBACK_SCRIPTS[(clause_no, part_no)].copy()
            data["title"] = title
            data["clause_no"] = clause_no
            return data
        return None


# -------------------- STATE --------------------

def load_state():
    default = {"clause_no": 23, "current_part": 1}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as file:
                saved = json.load(file)
                if isinstance(saved, dict):
                    default.update(saved)
        except Exception:
            pass
    if default["clause_no"] not in POSTAL_CLAUSE_CATALOG:
        default["clause_no"] = 23
        default["current_part"] = 1
    return default

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


# -------------------- AUDIO --------------------

async def make_audio(text, output):
    if os.path.exists(output):
        os.remove(output)
    tts = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate=VOICE_RATE)
    await tts.save(output)

def audio_duration(path):
    result = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ])
    return float(result.decode().strip())

def tighten_audio(path):
    temp = path + ".tmp.mp3"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", path, "-af",
            "silenceremove=start_periods=1:start_threshold=-38dB:stop_periods=-1:stop_duration=0.08:stop_threshold=-38dB",
            "-c:a", "libmp3lame", "-b:a", "192k", temp,
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.replace(temp, path)
    except Exception:
        if os.path.exists(temp):
            os.remove(temp)


# -------------------- NEW 5-SCENE TEXT (RETENTION OPTIMIZED) --------------------

def make_scene_text(data):
    return [
        f"{data['hook']} {data['question']}",                                          # 0: Hook & Q
        "ये रहे आपके विकल्प।",                                                          # 1: Options Reveal
        "5 सेकंड में अपना जवाब ए, बी, सी या डी कमेंट करें! जल्दी सोचिए...",                 # 2: Timer
        f"समय समाप्त! सही उत्तर है विकल्प {data['correct']}! नियम याद रखें: {data['fact']}", # 3: Answer & Rule
        f"परीक्षा में यह गलती मत करना! {data['trap']} . रिवीजन के लिए इस रील को सेव करें!"      # 4: Exam Trap & CTA
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
        "-filter_complex", filter_complex, "-map", "[outa]",
        "-c:a", "aac", "-b:a", "192k", output,
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# -------------------- NEW 5-SCENE VISUALS --------------------

def draw_base_question(d, data, t):
    brand(d)
    draw_scrolling_target_badge(d, t)
    rounded(d, (80, 240, 1000, 520), 40, CARD, "#334155", 4)
    center_text(d, "POSTAL EXAM RULE", 300, 40, MUTED)
    wrapped_q = wrap_text(d, data["question"], 52, 840)
    y_start = 400
    for line in wrapped_q.split("\n"):
        center_text(d, line, y_start, 52, WHITE)
        y_start += 65

def scene_0_hook_question(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    progress_bar(d, 0.2)
    draw_base_question(d, data, t)
    return im

def scene_1_options(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    progress_bar(d, 0.4)
    draw_base_question(d, data, t)
    options = [("A", data["a"]), ("B", data["b"]), ("C", data["c"]), ("D", data["d"])]
    y0 = 560
    for idx, (letter, txt) in enumerate(options):
        draw_option_card(d, letter, txt, y0 + idx * 175, status=None)
    return im

def scene_2_timer(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    progress_bar(d, 0.6)
    draw_base_question(d, data, t)
    options = [("A", data["a"]), ("B", data["b"]), ("C", data["c"]), ("D", data["d"])]
    y0 = 560
    for idx, (letter, txt) in enumerate(options):
        draw_option_card(d, letter, txt, y0 + idx * 175, status=None)
        
    time_left = max(1, math.ceil(5 - (t / max(duration, 0.1)) * 5))
    center_text(d, "अपना जवाब चुनिए", 1320, 46, YELLOW)
    center_text(d, "5 सेकंड में A / B / C / D कमेंट करें", 1400, 40, WHITE)
    
    font_timer = get_font(140)
    d.text((W/2, 1600), str(time_left), font=font_timer, fill=RED, anchor="mm")
    return im

def scene_3_reveal_rule(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    progress_bar(d, 0.8)
    draw_base_question(d, data, t)
    
    correct_key = data.get("correct", "A").upper()
    correct_text = data.get(correct_key.lower(), "")
    draw_option_card(d, correct_key, correct_text, 560, status="correct", anim_prog=min(1.0, t/0.3))
    
    if t > 0.3:
        rounded(d, (80, 800, 1000, 1300), 40, CARD_2, GREEN, 5)
        center_text(d, "महत्वपूर्ण नियम (VERIFIED RULE)", 870, 40, GREEN)
        fact = wrap_text(d, data["fact"], 46, 820)
        y_f = 980
        for line in fact.split("\n"):
            center_text(d, line, y_f, 46, WHITE)
            y_f += 65
    return im

def scene_4_trap(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    progress_bar(d, 1.0)
    draw_scrolling_target_badge(d, t)
    brand(d)
    
    rounded(d, (70, 270, 1010, 1400), 45, CARD, YELLOW, 5)
    center_text(d, "EXAM TRAP", 370, 62, YELLOW)
    center_text(d, "सावधानी: यहाँ गलती न करें!", 470, 42, MUTED)

    rounded(d, (120, 560, 960, 900), 30, CARD_2, RED, 4)
    center_text(d, "अक्सर होने वाला भ्रम", 640, 42, RED)
    x_prog = min(1.0, t / 0.2)
    draw_animated_x(d, 880, 640, progress=x_prog, size=24)
    
    trap_t = wrap_text(d, data["trap"], 44, 780)
    y = 740
    for line in trap_t.split("\n"):
        center_text(d, line, y, 44, WHITE)
        y += 60

    rounded(d, (120, 960, 960, 1300), 30, CARD_2, GREEN, 4)
    center_text(d, "याद रखने योग्य बात", 970, 42, GREEN)
    chk_prog = min(1.0, max(0.0, (t - 0.2) / 0.2))
    draw_animated_check(d, 880, 970, progress=chk_prog, size=24)
    
    fact_t = wrap_text(d, data["fact"], 42, 780)
    y_f = 1080
    for line in fact_t.split("\n"):
        center_text(d, line, y_f, 42, WHITE)
        y_f += 55
        
    center_text(d, "अगले Postal MCQ के लिए Follow करें", 1500, 46, CYAN)
    center_text(d, "@POSTAL_WALA", 1580, 56, WHITE)
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
            "ffmpeg", "-y",
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
    )


# -------------------- MAIN --------------------

def build_reel(data, output_video=None):
    if not output_video:
        output_video = os.path.join(OUTPUT_DIR, OUTPUT_VIDEO)
    os.makedirs(os.path.dirname(output_video), exist_ok=True)

    scene_audios = asyncio.run(generate_scene_audios(data))
    durations = [audio_duration(path) for path in scene_audios]

    scene_functions = [
        scene_0_hook_question,
        scene_1_options,
        scene_2_timer,
        scene_3_reveal_rule,
        scene_4_trap
    ]

    frame_paths = []
    for i, scene_func in enumerate(scene_functions):
        frame_paths += render_scene(
            scene_func,
            data,
            durations[i],
            f"scene_{i}",
        )

    silent = "silent_reel.mp4"
    frames_to_video(frame_paths, silent)
    master_audio = "master_audio.m4a"
    concat_audio(scene_audios, master_audio)
    mux(silent, master_audio, output_video)

    for path in frame_paths:
        try: os.remove(path)
        except OSError: pass

    for path in scene_audios + [silent, master_audio]:
        try: os.remove(path)
        except OSError: pass

    total = audio_duration(output_video)
    print(f"COMPLETE: {output_video} ({total:.2f}s)")

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
    print("Current State:", state)
    data = generate_script(state)
    
    if data:
        print("\nSCRIPT DATA:")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        reels_dir = OUTPUT_DIR
        os.makedirs(reels_dir, exist_ok=True)
        output_filename = f"reel_clause_{state['clause_no']}_part_{state['current_part']}.mp4"
        output_video_path = os.path.join(reels_dir, output_filename)
        build_reel(data, output_video_path)
        advance_state(state)
