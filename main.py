import os
import re
import json
import math
import shutil
import asyncio
import subprocess
import requests
from PIL import Image, ImageDraw, ImageFont
import edge_tts

# ============================================================
# POSTAL WALA — PRODUCTION REEL ENGINE v3 (FIXED RENDERING)
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
STATE_FILE = "progress_state.json"
REELS_DIR = "generated_reels"
os.makedirs(REELS_DIR, exist_ok=True)

VOICE_NAME = "hi-IN-SwaraNeural"

W, H = 1080, 1920
FPS = 30
BG = "#08101E"
WHITE = "#F8FAFC"
MUTED = "#94A3B8"
RED = "#EF4444"
GREEN = "#22C55E"
YELLOW = "#F59E0B"
CYAN = "#38BDF8"
CARD = "#0F1E36"
CARD2 = "#152847"

FONT_DEV = "NotoSansDevanagari-Bold.ttf"
ASSETS = "assets"
os.makedirs(ASSETS, exist_ok=True)

# ------------------------------------------------------------
# 1) VERIFIED POSTAL CATALOG WITH REAL MCQ FALLBACKS
# ------------------------------------------------------------
POSTAL_CLAUSE_CATALOG = {
    1: {
        "name": "डाक विभाग का नियंत्रण व संगठन",
        "total_parts": 2,
        "part_1_focus": "संचार मंत्रालय के अधीन महानिदेशक (DG Posts) शीर्ष प्रशासनिक प्रमुख हैं और मुख्यालय डाक भवन नई दिल्ली है।",
        "part_2_focus": "डाक सेवा बोर्ड (PSB) में एक चेयरमैन (सचिव डाक) और 6 पूर्णकालिक सदस्य होते हैं।",
        "fallback_mcq": {
            "question": "डाक विभाग का प्रशासनिक प्रमुख कौन होता है?",
            "a": "महानिदेशक (DG Posts)", "b": "सचिव डाक", "c": "पोस्टमार्क अधीक्षक", "d": "मुख्य पोस्टमास्टर",
            "correct": "A", "fact": "संचार मंत्रालय के अधीन महानिदेशक ही शीर्ष प्रशासनिक प्रमुख होते हैं।", "trap": "चेयरमैन और महानिदेशक के पद में अंतर याद रखें।"
        }
    },
    2: {
        "name": "डाकघरों के प्रकार और श्रेणियां",
        "total_parts": 3,
        "part_1_focus": "डाकघर की 3 श्रेणियां हैं: प्रधान डाकघर (HO), उप डाकघर (SO) और शाखा डाकघर (BO)। HO मुख्य वित्तीय लेखा कार्यालय है।",
        "part_2_focus": "उप डाकघर (SO) प्रधान डाकघर के अधीन रहकर सभी प्रकार के लेन-देन करता है और दैनिक लेखा HO को भेजता है।",
        "part_3_focus": "ग्रामीण शाखा डाकघर (BO) के कार्य के घंटे न्यूनतम 4 घंटे और अधिकतम 5 घंटे प्रतिदिन होते हैं।",
        "fallback_mcq": {
            "question": "शाखा डाकघर (BO) के दैनिक कार्य के अधिकतम घंटे कितने होते हैं?",
            "a": "4 घंटे", "b": "5 घंटे", "c": "6 घंटे", "d": "8 घंटे",
            "correct": "B", "fact": "शाखा डाकघर के कार्य के घंटे न्यूनतम 4 और अधिकतम 5 घंटे होते हैं।", "trap": "न्यूनतम 4 घंटे और अधिकतम 5 घंटे में अंतर ध्यान रखें।"
        }
    },
    3: {
        "name": "रात्रि डाकघर के नियम",
        "total_parts": 3,
        "part_1_focus": "रात्रि डाकघर के कामकाज के घंटे रात 8:30 बजे तक बढ़ाने का विशेष अधिकार केवल महानिदेशक (DG) को है।",
        "part_2_focus": "रविवार और राष्ट्रीय डाक अवकाशों पर रात्रि डाकघर सुबह 10 से शाम 5 बजे तक सीमित सेवाएं देते हैं।",
        "part_3_focus": "रात्रि डाकघरों में रविवार और अवकाश के दिनों में कोई मनीऑर्डर भुगतान या बचत बैंक निकासी नहीं होती।",
        "fallback_mcq": {
            "question": "रात्रि डाकघर के कामकाज के घंटे बढ़ाने का अधिकार किसे है?",
            "a": "महानिदेशक (DG)", "b": "पोस्टमास्टर जनरल", "c": "डाक अधीक्षक", "d": "सर्कल हेड",
            "correct": "A", "fact": "रात 8:30 बजे तक समय बढ़ाने का अधिकार केवल महानिदेशक (DG) को है।", "trap": "सर्कल हेड नहीं, केवल महानिदेशक को यह विशेष अधिकार है।"
        }
    },
    22: {
        "name": "डाक का पुनः निर्देशन (Redirection)",
        "total_parts": 3,
        "part_1_focus": "पतेदार के नया पता छोड़कर जाने पर प्रथम श्रेणी की अंतरदेशीय डाक का पुनः प्रेषण पूर्णतः निःशुल्क होता है।",
        "part_2_focus": "पार्सल पुनः प्रेषण में यदि पार्सल मूल वितरण क्षेत्र से बाहर भेजा जाए तो आधा डाक प्रभार देय होता है।",
        "part_3_focus": "यदि पार्सल को पतेदार द्वारा एक बार खोल दिया गया हो तो उसे नए डाकभार के बिना पुनः प्रेषित नहीं कर सकते।",
        "fallback_mcq": {
            "question": "मूल वितरण क्षेत्र से बाहर पार्सल पुनः प्रेषित करने पर कितना प्रभार लगेगा?",
            "a": "आधा डाक प्रभार", "b": "पूर्ण डाक प्रभार", "c": "निःशुल्क", "d": "दोगुना प्रभार",
            "correct": "A", "fact": "वितरण क्षेत्र से बाहर भेजे जाने पर आधा डाक प्रभार देय होता है।", "trap": "प्रथम श्रेणी डाक निःशुल्क है, परंतु पार्सल पर आधा प्रभार लगता है।"
        }
    }
}

# ------------------------------------------------------------
# 2) FONT & ROBUST TEXT RENDERING (NO BROKEN MATRAS)
# ------------------------------------------------------------
def ensure_font():
    if os.path.exists(FONT_DEV):
        return
    url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with open(FONT_DEV, "wb") as f:
        f.write(r.content)

def get_font(size):
    ensure_font()
    return ImageFont.truetype(FONT_DEV, size)

def wrap_text_lines(draw, text, font, max_width):
    words = text.split()
    lines, cur = [], ""
    for word in words:
        test = word if not cur else f"{cur} {word}"
        if draw.textlength(test, font=font) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines

def clean_text(s):
    if not s:
        return ""
    s = re.sub(r"[*_`#]+", "", s)
    s = s.replace("…", ".")
    return " ".join(s.split()).strip()

# ------------------------------------------------------------
# 3) VECTOR DRAWING (REPLACES MISSING EMOJIS & WAX GRAPHICS)
# ------------------------------------------------------------
def draw_alert_badge(draw, cx, cy, size=40):
    half = size
    pts = [(cx, cy - half), (cx - half, cy + half), (cx + half, cy + half)]
    draw.polygon(pts, fill=YELLOW)
    f = get_font(int(size * 0.85))
    draw.text((cx, cy + 5), "!", font=f, fill=BG, anchor="mm")

def draw_checkmark(draw, cx, cy, radius=45):
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=GREEN)
    draw.line([(cx - 20, cy), (cx - 5, cy + 18), (cx + 22, cy - 15)], fill=WHITE, width=8)

# ------------------------------------------------------------
# 4) SCRIPT GENERATION & CLEAN FALLBACK
# ------------------------------------------------------------
def extract_field(raw, name, next_names):
    pat = rf"(?:^|\n)\s*{re.escape(name)}\s*:\s*(.*?)(?=(?:\n\s*(?:{'|'.join(map(re.escape,next_names))})\s*:)|$)"
    m = re.search(pat, raw, re.I | re.S)
    return clean_text(m.group(1)) if m else ""

def generate_script(state):
    clause_no = state["clause_no"]
    part_no = state["current_part"]
    info = POSTAL_CLAUSE_CATALOG.get(clause_no, POSTAL_CLAUSE_CATALOG[1])
    title = info["name"]
    focus = info.get(f"part_{part_no}_focus", info.get("part_1_focus", ""))

    fb = info.get("fallback_mcq", POSTAL_CLAUSE_CATALOG[1]["fallback_mcq"])
    fallback_data = {
        "title": title,
        "hook": f"{title} का यह मुख्य नियम याद रखें।",
        "question": fb["question"],
        "a": fb["a"], "b": fb["b"], "c": fb["c"], "d": fb["d"],
        "correct": fb["correct"],
        "fact": fb["fact"],
        "trap": fb["trap"],
    }

    if not GROQ_API_KEY:
        return fallback_data

    prompt = f"""
Write ONE high-retention departmental exam educational Reel script in Hindi.
TOPIC: {title}
RULE TO COVER: {focus}

Strict rules:
- No generic placeholders like "ऊपर दिया नियम".
- The 4 options (A, B, C, D) must be realistic options for a postal exam.
- The trap must highlight a common exam mistake.

Return EXACTLY:
HOOK: [max 10 words, catchy curiosity line]
QUESTION: [max 14 words MCQ question]
A: [2-5 words]
B: [2-5 words]
C: [2-5 words]
D: [2-5 words]
CORRECT: [A/B/C/D]
FACT: [max 16 words core explanation]
TRAP: [max 12 words warning]
"""
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 450,
            },
            timeout=20,
        )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]

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

        if data["correct"] in ["A", "B", "C", "D"] and all(data.values()):
            return data
    except Exception as e:
        print("Using curated fallback:", e)

    return fallback_data

# ------------------------------------------------------------
# 5) AUDIO ENGINE
# ------------------------------------------------------------
def audio_duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ])
    return float(out.decode().strip())

async def make_audio(text, path):
    if os.path.exists(path):
        os.remove(path)
    tts = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+12%", pitch="+0Hz")
    await tts.save(path)

def tighten_audio(path):
    tmp = path + ".tmp.mp3"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", path,
            "-af", "silenceremove=start_periods=1:start_threshold=-38dB:stop_periods=-1:stop_duration=0.08:stop_threshold=-38dB",
            "-c:a", "libmp3lame", "-b:a", "192k", tmp
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)

# ------------------------------------------------------------
# 6) SCENE VISUALS (UNIVERSAL & FULLY WRAPPED)
# ------------------------------------------------------------
def base_canvas():
    return Image.new("RGB", (W, H), BG)

def draw_header(draw, title, ratio):
    f_brand = get_font(28)
    draw.text((60, 55), "POSTAL WALA", font=f_brand, fill="#64748B")

    # Progress bar
    x1, x2, y = 60, W - 60, 100
    draw.rounded_rectangle((x1, y, x2, y + 8), 4, fill="#1E293B")
    draw.rounded_rectangle((x1, y, x1 + (x2 - x1) * max(0.0, min(1.0, ratio)), y + 8), 4, fill=CYAN)

    # Category Tag
    tag_font = get_font(30)
    draw.rounded_rectangle((60, 130, 60 + draw.textlength(title, font=tag_font) + 40, 185), 12, fill="#0B1B32")
    draw.text((80, 142), title, font=tag_font, fill=CYAN)

def scene_hook(data, t):
    im = base_canvas()
    d = ImageDraw.Draw(im)
    draw_header(d, data["title"], 0.1)

    # Centered Focus Box
    d.rounded_rectangle((70, 420, W - 70, 1220), 40, fill=CARD, outline="#1E3A5F", width=3)
    draw_alert_badge(d, W // 2, 540, 45)

    f_sub = get_font(36)
    d.text((W // 2, 640), "परीक्षा में बार-बार पूछे जाने वाला नियम", font=f_sub, fill=YELLOW, anchor="mm")

    f_hook = get_font(56)
    lines = wrap_text_lines(d, data["hook"], f_hook, 850)
    yy = 800 - (len(lines) * 35)
    for line in lines:
        d.text((W // 2, yy), line, font=f_hook, fill=WHITE, anchor="mm")
        yy += 75

    f_wait = get_font(38)
    d.text((W // 2, 1100), "रुकिए — पहले नियम को समझें!", font=f_wait, fill=CYAN, anchor="mm")
    return im

def scene_fact(data, t):
    im = base_canvas()
    d = ImageDraw.Draw(im)
    draw_header(d, data["title"], 0.35)

    d.rounded_rectangle((70, 380, W - 70, 1260), 40, fill=CARD, outline=GREEN, width=4)

    # Fact Header Badge
    d.rounded_rectangle((W // 2 - 180, 340, W // 2 + 180, 420), 20, fill=GREEN)
    f_badge = get_font(36)
    d.text((W // 2, 380), "प्रमाणित नियम (RULE)", font=f_badge, fill=WHITE, anchor="mm")

    f_fact = get_font(52)
    lines = wrap_text_lines(d, data["fact"], f_fact, 850)
    yy = 680 - (len(lines) * 35)
    for line in lines:
        d.text((W // 2, yy), line, font=f_fact, fill=WHITE, anchor="mm")
        yy += 80

    # Animated Sub-card for retention
    d.rounded_rectangle((120, 1040, W - 120, 1180), 24, fill=CARD2)
    f_sub = get_font(36)
    d.text((W // 2, 1110), "📌 इसे अभी नोट कर लें", font=f_sub, fill=MUTED, anchor="mm")
    return im

def scene_trap(data, t):
    im = base_canvas()
    d = ImageDraw.Draw(im)
    draw_header(d, data["title"], 0.55)

    d.rounded_rectangle((70, 380, W - 70, 1260), 40, fill=CARD, outline=YELLOW, width=4)
    draw_alert_badge(d, W // 2, 470, 40)

    f_alert = get_font(46)
    d.text((W // 2, 570), "EXAM TRAP (सावधानी)", font=f_alert, fill=YELLOW, anchor="mm")

    f_trap = get_font(50)
    lines = wrap_text_lines(d, data["trap"], f_trap, 850)
    yy = 780 - (len(lines) * 35)
    for line in lines:
        d.text((W // 2, yy), line, font=f_trap, fill=WHITE, anchor="mm")
        yy += 75

    d.rounded_rectangle((120, 1050, W - 120, 1170), 20, fill="#231A10", outline=YELLOW, width=2)
    f_sub = get_font(34)
    d.text((W // 2, 1110), "अपवाद और शब्दों पर विशेष ध्यान दें", font=f_sub, fill="#FDE68A", anchor="mm")
    return im

def scene_mcq(data, t, countdown=False):
    im = base_canvas()
    d = ImageDraw.Draw(im)
    draw_header(d, data["title"], 0.75 if not countdown else 0.88)

    # MCQ Title
    f_mcq = get_font(42)
    d.text((W // 2, 260), "अभ्यास प्रश्न (POSTAL MCQ)", font=f_mcq, fill=CYAN, anchor="mm")

    # Question (Safely wrapped)
    qf = get_font(46)
    qlines = wrap_text_lines(d, data["question"], qf, 940)
    yy = 340
    for line in qlines:
        d.text((W // 2, yy), line, font=qf, fill=WHITE, anchor="mm")
        yy += 65

    # Options A, B, C, D
    opts = [("A", data["a"]), ("B", data["b"]), ("C", data["c"]), ("D", data["d"])]
    y0 = max(yy + 40, 560)
    opt_font = get_font(38)

    for i, (letter, text) in enumerate(opts):
        y_box = y0 + (i * 150)
        outline = CYAN if (countdown and i == 0) else "#1E2E48"
        d.rounded_rectangle((80, y_box, W - 80, y_box + 120), 24, fill=CARD2, outline=outline, width=3)
        
        # Circle for letter
        d.ellipse([110, y_box + 25, 180, y_box + 95], fill="#0A1628")
        d.text((145, y_box + 60), letter, font=opt_font, fill=CYAN, anchor="mm")
        
        # Option Text
        d.text((210, y_box + 60), text, font=opt_font, fill=WHITE, anchor="lm")

    if countdown:
        rem = max(1, 4 - int(t))
        d.rounded_rectangle((W // 2 - 80, 1420, W // 2 + 80, 1540), 20, fill=YELLOW)
        d.text((W // 2, 1480), str(rem), font=get_font(70), fill=BG, anchor="mm")
        d.text((W // 2, 1600), "अपना उत्तर तुरंत Comment करें!", font=get_font(36), fill=WHITE, anchor="mm")

    return im

def scene_result(data, t):
    im = base_canvas()
    d = ImageDraw.Draw(im)
    draw_header(d, data["title"], 1.0)

    d.rounded_rectangle((80, 400, W - 80, 1200), 40, fill=CARD, outline=GREEN, width=4)
    draw_checkmark(d, W // 2, 530, 55)

    f_res = get_font(46)
    d.text((W // 2, 650), "सही उत्तर", font=f_res, fill=GREEN, anchor="mm")

    # Correct Letter
    d.text((W // 2, 790), data["correct"], font=get_font(120), fill=WHITE, anchor="mm")

    # Correct Option Full Text
    opt_key = data["correct"].lower()
    correct_text = data.get(opt_key, "")
    f_ans = get_font(44)
    lines = wrap_text_lines(d, correct_text, f_ans, 800)
    yy = 940
    for line in lines:
        d.text((W // 2, yy), line, font=f_ans, fill=CYAN, anchor="mm")
        yy += 60

    # Call to action
    d.text((W // 2, 1400), "अगले नियम के लिए अभी Follow करें", font=get_font(38), fill=MUTED, anchor="mm")
    d.text((W // 2, 1470), "@POSTAL_WALA", font=get_font(48), fill=CYAN, anchor="mm")
    return im

# ------------------------------------------------------------
# 7) VIDEO ASSEMBLY
# ------------------------------------------------------------
def make_frames(scene_fn, duration, prefix, *args):
    count = max(1, int(math.ceil(duration * FPS)))
    paths = []
    for i in range(count):
        t = i / FPS
        im = scene_fn(*args, t)
        p = f"{prefix}_{i:05d}.jpg"
        im.save(p, quality=95)
        paths.append(p)
    return paths

def assemble_video(frame_paths, audio_path, output_path):
    concat_file = "frames_list.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for p in frame_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    silent = "temp_silent.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-r", str(FPS), "-f", "concat", "-safe", "0",
        "-i", concat_file, "-vf", f"fps={FPS},format=yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", silent
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    subprocess.run([
        "ffmpeg", "-y", "-i", silent, "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", output_path
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Cleanup
    for p in frame_paths + [concat_file, silent, audio_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

def build_reel(data, output_file):
    # DYNAMIC VOICE OVER - NO HARDCODED STRINGS!
    voice = (
        f"{data['hook']} "
        f"नियम यह है कि: {data['fact']} "
        f"लेकिन परीक्षा में ध्यान दें: {data['trap']} "
        f"अब सवाल का उत्तर दें: {data['question']} "
        f"विकल्प हैं: A {data['a']}, B {data['b']}, C {data['c']}, या D {data['d']}. "
        f"अपना उत्तर कमेंट करें। "
        f"सही उत्तर है विकल्प {data['correct']}."
    )

    audio = "master_voice.mp3"
    asyncio.run(make_audio(voice, audio))
    tighten_audio(audio)

    total_dur = audio_duration(audio)
    print(f"🎙️ Audio Generated: {total_dur:.2f} seconds")

    # Time budget
    t_hook = total_dur * 0.18
    t_fact = total_dur * 0.22
    t_trap = total_dur * 0.20
    t_mcq  = total_dur * 0.26
    t_res  = total_dur * 0.14

    frames = []
    frames += make_frames(scene_hook, t_hook, "f_hook", data)
    frames += make_frames(scene_fact, t_fact, "f_fact", data)
    frames += make_frames(scene_trap, t_trap, "f_trap", data)
    frames += make_frames(lambda d, t: scene_mcq(d, t, False), t_mcq * 0.6, "f_mcq", data)
    frames += make_frames(lambda d, t: scene_mcq(d, t, True), t_mcq * 0.4, "f_count", data)
    frames += make_frames(scene_result, t_res, "f_res", data)

    assemble_video(frames, audio, output_file)
    print(f"🎬 Video rendered successfully: {output_file}")

# ------------------------------------------------------------
# 8) EXECUTION & GITHUB AUTO-PUSH
# ------------------------------------------------------------
def load_state():
    state = {"clause_no": 3, "current_part": 1}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state.update(json.load(f))
        except Exception:
            pass
    return state

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def push_if_local(target_video, state_file):
    if os.getenv("GITHUB_ACTIONS"):
        return
    try:
        subprocess.run(["git", "add", target_video, state_file], check=True)
        commit_msg = f"Add reel: {os.path.basename(target_video)} [skip ci]"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "push"], check=True)
        print("🚀 Successfully pushed to GitHub!")
    except Exception as e:
        print("Git Push notice:", e)

if __name__ == "__main__":
    state = load_state()
    clause_no = state["clause_no"]
    part_no = state["current_part"]

    target_video_name = f"reel_clause_{clause_no}_part_{part_no}.mp4"
    target_output_path = os.path.join(REELS_DIR, target_video_name)

    data = generate_script(state)
    print("\n--- GENERATED DATA ---")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    build_reel(data, target_output_path)

    # Optional root copy
    try:
        shutil.copy(target_output_path, "final_reel.mp4")
    except Exception:
        pass

    # Advance to next part or next clause
    info = POSTAL_CLAUSE_CATALOG.get(clause_no, POSTAL_CLAUSE_CATALOG[1])
    if part_no < info["total_parts"]:
        state["current_part"] += 1
    else:
        keys = sorted(POSTAL_CLAUSE_CATALOG.keys())
        idx = keys.index(clause_no)
        state["clause_no"] = keys[(idx + 1) % len(keys)]
        state["current_part"] = 1
    save_state(state)

    push_if_local(target_output_path, STATE_FILE)
