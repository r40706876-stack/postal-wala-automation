import os
import glob
import json
import time
import asyncio
import subprocess
import requests
import textwrap
import re
import sys
import shutil
from PIL import Image, ImageDraw, ImageFont
import edge_tts
from pypdf import PdfReader

# --- Environment Variables ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

PDF_FILE_PATH = "mts content .pdf"
FONT_PATH = "Mukta-Bold.ttf"
OUTPUT_VIDEO = "final_reel.mp4"
BGM_OUTPUT = "bgm.mp3"
VOICE_NAME = "hi-IN-SwaraNeural"
REELS_DIR = "generated_reels"

STATE_FILE = "progress_state.json"

RESAMPLE_MODE = getattr(Image, "Resampling", Image).LANCZOS

# --- Official PO Guide Part 1 Clause Titles Dictionary (100% Error-Free Guarantee) ---
OFFICIAL_PO_GUIDE_TITLES = {
    1: "पंजीकृत वस्तुएं",
    12: "डाक टिकट चिपकाने की विधि",
    13: "खराब या विकृत डाक टिकट",
    14: "काल्पनिक डाक टिकट",
    15: "पैकिंग",
    16: "सीलिंग",
    17: "मुद्राओं की पोस्टिंग",
    18: "बीमा नियम",
    19: "मूल्य देय डाक (वीपीपी)",
    20: "पंजीकृत समाचार पत्र"
}

# --- High-Retention Viral Hooks (<3.5s, No Word Repetition) ---
VIRAL_HOOKS = [
    {
        "voice": "विभागीय परीक्षा में यह एक नियम बार-बार आता है, देखिए!",
        "visual_badge": "[ ! ] 100% पक्का सवाल",
        "hook_text": "विभागीय परीक्षा में बार-बार दोहराया जाने वाला सबसे महत्वपूर्ण क्लॉज!"
    },
    {
        "voice": "जीडीएस परीक्षा में 90% छात्र इस एक नियम में फेल होते हैं!",
        "visual_badge": "[ ! ] 90% छात्र फेल",
        "hook_text": "इस क्लॉज के आधिकारिक अपवाद में सबसे ज्यादा परीक्षार्थी गलती करते हैं!"
    },
    {
        "voice": "प्रमोशन पक्का करने के लिए यह नियम आज ही समझ लीजिए!",
        "visual_badge": "[ ! ] मेरिट लिस्ट बूस्टर",
        "hook_text": "जीडीएस से पोस्टमैन व पी.ए. बनने के लिए इस नियम को आज ही रट लीजिए!"
    },
    {
        "voice": "डाक विभाग की परीक्षा का सबसे पसंदीदा नियम, ध्यान से समझें!",
        "visual_badge": "[ ! ] परीक्षक का पसंदीदा",
        "hook_text": "सीधे 2 अंक पक्के करने वाला डाक घर गाइड का अनिवार्य नियम!"
    },
    {
        "voice": "पोस्टमैन या पी.ए. बनना है तो यह रील बिल्कुल स्किप मत करना!",
        "visual_badge": "[ ! ] प्रमोशन स्पेशल",
        "hook_text": "विभागीय परीक्षा पास करने के लिए यह क्लॉज पढ़ना अनिवार्य है!"
    },
    {
        "voice": "डाक घर गाइड का यह नियम कई लोगों का प्रमोशन रोक देता है!",
        "visual_badge": "[ ! ] परीक्षा रेड अलर्ट",
        "hook_text": "सावधान: इस नियम की छोटी सी गलती आपका विभागीय प्रमोशन रोक सकती है!"
    }
]

# --- Direct Official PO Guide Title & Text Extractor ---
def extract_clause_from_pdf(clause_no, pdf_path=PDF_FILE_PATH):
    if clause_no in OFFICIAL_PO_GUIDE_TITLES:
        final_title = OFFICIAL_PO_GUIDE_TITLES[clause_no]
    else:
        final_title = f"पोस्टल गाइड भाग 1 क्लॉज {clause_no}"

    default_text = f"डाक घर गाइड भाग 1 के क्लॉज {clause_no} का आधिकारिक विभागीय नियम।"
    
    if not os.path.exists(pdf_path):
        return final_title, default_text

    try:
        reader = PdfReader(pdf_path)
        pattern = re.compile(rf"(?:क्लॉज|Clause|नियम)\s*[-:]?\s*{clause_no}\b", re.IGNORECASE)
        matched_text = ""

        for page in reader.pages:
            txt = page.extract_text() or ""
            if pattern.search(txt):
                matched_text += txt + "\n"
                if len(matched_text) >= 2500:
                    break

        final_text = matched_text.strip() if matched_text.strip() else default_text
        print(f"✅ Loaded Official Title: '{final_title}' for Clause {clause_no}", flush=True)
        return final_title[:60], clean_hindi_postal_terms(final_text[:2500])
    except Exception as e:
        print(f"⚠️ PDF Extraction Error: {e}", flush=True)
    return final_title, default_text

def get_dynamic_total_parts(pdf_text):
    if not pdf_text:
        return 1
    char_count = len(pdf_text.strip())
    if char_count < 300:
        return 1
    elif char_count < 700:
        return 2
    elif char_count < 1200:
        return 3
    elif char_count < 1800:
        return 4
    else:
        return 5

def clean_text(text):
    if not text:
        return ""
    text = text.strip().strip("\"'`")
    text = "".join(c for c in text if ord(c) < 0x10000)
    return text.strip()

def clean_hindi_postal_terms(text):
    if not text:
        return ""
    text = re.sub(r"^[:\-\s\.]+", "", text)
    replacements = {
        "पेन्टियों": "पत्र-पेटियों", "पेन्टी": "पत्र-पेटी",
        "घंटी वाली प्लेटें": "घंटे वाली प्लेटें", "घंटी वाली प्लेट": "घंटे वाली प्लेट",
        "घंटी वाली": "घंटे वाली", "नित्य पत्र": "वित्तीय वर्ष", "नित्य वर्ष": "वित्तीय वर्ष"
    }
    for bad_w, good_w in replacements.items():
        text = text.replace(bad_w, good_w)
    text = re.sub(r"^[:\s]+", "", text)
    return clean_text(text)

def extract_field_block(text, field_name, next_fields):
    pattern = r"(?:^|\n)\s*(?:\*\*)?" + re.escape(field_name) + r"(?:\*\*)?\s*:\s*(.*?)(?=(?:\n\s*(?:\*\*)?(?:" + "|".join(next_fields) + r")(?:\*\*)?\s*:)|$)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        val = re.sub(r"^[\"\'`]+|[\"\'`]+$", "", val).strip()
        return " ".join(val.split())
    return None

def ensure_fonts():
    if not os.path.exists(FONT_PATH):
        url = "https://raw.githubusercontent.com/google/fonts/main/ofl/mukta/Mukta-Bold.ttf"
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                with open(FONT_PATH, "wb") as f:
                    f.write(r.content)
        except Exception:
            pass

def get_font(size):
    ensure_fonts()
    if os.path.exists(FONT_PATH):
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()

def load_progress_state():
    state = {"clause_no": 1, "current_part": 1, "total_parts": 1, "hook_index": 0}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                if isinstance(saved, dict) and "clause_no" in saved:
                    state.update(saved)
        except Exception:
            pass
            
    _, pdf_text = extract_clause_from_pdf(state.get("clause_no", 1))
    state["total_parts"] = get_dynamic_total_parts(pdf_text)
    
    if state["current_part"] > state["total_parts"]:
        state["current_part"] = 1
        
    save_progress_state(state)
    return state

def save_progress_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

def advance_progress_state(state):
    hook_idx = state.get("hook_index", 0)
    state["hook_index"] = (hook_idx + 1) % len(VIRAL_HOOKS)

    clause = state.get("clause_no", 1)
    part = state.get("current_part", 1)
    total_parts = state.get("total_parts", 1)

    if part < total_parts:
        state["current_part"] = part + 1
    else:
        next_clause = clause + 1 if clause < 60 else 1
        state["clause_no"] = next_clause
        state["current_part"] = 1
        
        _, next_pdf_text = extract_clause_from_pdf(next_clause)
        state["total_parts"] = get_dynamic_total_parts(next_pdf_text)

    save_progress_state(state)
    print(f"⏩ Advanced Progress to: Clause {state['clause_no']} (Part {state['current_part']}/{state['total_parts']})", flush=True)

# --- STRICT 100% PURE HINDI SCRIPT GENERATOR ---
def generate_clause_script(state):
    current_clause = state.get("clause_no", 1)
    current_part = state.get("current_part", 1)
    total_parts = state.get("total_parts", 1)
    hook_idx = state.get("hook_index", 0) % len(VIRAL_HOOKS)
    hook_obj = VIRAL_HOOKS[hook_idx]

    official_title, official_pdf_text = extract_clause_from_pdf(current_clause)

    fallback_data = {
        "clause_no": current_clause,
        "clause_name": official_title,
        "part_no": current_part,
        "total_parts": total_parts,
        "visual_hook_badge": hook_obj["visual_badge"],
        "hook_voice": hook_obj["voice"],
        "hook_display_text": hook_obj["hook_text"],
        "sen1": f"डाक घर गाइड भाग 1 क्लॉज {current_clause} के अनुसार आधिकारिक नियम अनिवार्य रूप से लागू होता है।",
        "sen2": "विभागीय परीक्षा में इस नियम के अपवाद और विशेष प्रावधान से सबसे ज्यादा सवाल पूछे जाते हैं।",
        "param1_title": "परीक्षा मुख्य बिंदु",
        "param1_val": "आधिकारिक नियम मान्य",
        "param2_title": "विभागीय शर्त",
        "param2_val": "नियमों का पालन अनिवार्य",
        "trap_point": "इस नियम की अनदेखी करने पर विभागीय परीक्षा में नकारात्मक अंक मिल सकते हैं।",
        "question": "डाक घर गाइड भाग 1 के क्लॉज किस विषय से संबंधित है?",
        "opt_a": "आधिकारिक विभागीय नियम",
        "opt_b": "अतिरिक्त शुल्क प्रावधान",
        "opt_c": "केवल सामान्य निर्देश",
        "opt_d": "इनमें से कोई नहीं",
        "caption": f"🚨 डाक घर गाइड भाग 1 | क्लॉज {current_clause} (भाग {current_part}/{total_parts}) - 10/10 Retention Master Solution。\n\n💬 अपना सही उत्तर कमेंट करें!\n🔥 अगला Postal Trap कल!\n\n#PostalWala #GDStoMTS #PostmanExam #IndiaPost #DepartmentalExam"
    }

    if not GROQ_API_KEY:
        return fallback_data

    prompt = f"""
    You are the Senior Chief Examiner for India Post Departmental Examinations.
    Topic: Post Office Guide Part 1, Clause: {current_clause}, Part: {current_part}/{total_parts}, Official Title: "{official_title}"

    OFFICIAL EXTRACTED TEXT FROM 'mts content .pdf':
    \"\"\"
    {official_pdf_text}
    \"\"\"

    STRICT 100% PURE HINDI RULES (TEMPERATURE 0.0):
    1. Base all facts, rules, and questions STRICTLY and SOLELY on the extracted text above, focusing specifically on Part {current_part} of {total_parts}.
    2. ALL SCREEN TEXT MUST BE IN FLUID, ERROR-FREE HINDI ONLY. NO ENGLISH WORDS.
    3. SEN1: State the exact operational rule for this part in clear Hindi (max 12-14 words).
    4. SEN2: State the specific legal exception, trap or penalty in clear Hindi (max 12-14 words).
    5. PARAM1_TITLE & PARAM1_VAL: First core condition in concise Hindi.
    6. PARAM2_TITLE & PARAM2_VAL: Second core condition in concise Hindi.
    7. TRAP_POINT: Clear penalty/trap note for Slide 3 red box in concise Hindi (max 8-10 words).
    8. QUESTION: High-yield departmental MCQ question directly from this part in Hindi (max 12 words).
    9. OPT_A: The 100% correct answer in concise Hindi (max 2-4 words).
    10. OPT_B, OPT_C, OPT_D: 3 plausible departmental distractors in concise Hindi (max 2-4 words each).

    FORMAT:
    SEN1: ...
    SEN2: ...
    PARAM1_TITLE: ...
    PARAM1_VAL: ...
    PARAM2_TITLE: ...
    PARAM2_VAL: ...
    TRAP_POINT: ...
    QUESTION: ...
    OPT_A: ...
    OPT_B: ...
    OPT_C: ...
    OPT_D: ...
    """

    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"}
        payload = {"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.0, "max_tokens": 450}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            raw_text = res.json()["choices"][0]["message"]["content"].strip()
            q = extract_field_block(raw_text, "QUESTION", ["SEN1", "OPT_A"])
            s1 = extract_field_block(raw_text, "SEN1", ["SEN2", "QUESTION"])
            s2 = extract_field_block(raw_text, "SEN2", ["PARAM1_TITLE", "QUESTION"])
            p1t = extract_field_block(raw_text, "PARAM1_TITLE", ["PARAM1_VAL", "PARAM2_TITLE"])
            p1v = extract_field_block(raw_text, "PARAM1_VAL", ["PARAM2_TITLE", "QUESTION"])
            p2t = extract_field_block(raw_text, "PARAM2_TITLE", ["PARAM2_VAL", "QUESTION"])
            p2v = extract_field_block(raw_text, "PARAM2_VAL", ["TRAP_POINT", "QUESTION"])
            tp = extract_field_block(raw_text, "TRAP_POINT", ["QUESTION", "OPT_A"])
            oa = extract_field_block(raw_text, "OPT_A", ["OPT_B", "OPT_C"])
            ob = extract_field_block(raw_text, "OPT_B", ["OPT_C", "OPT_D"])
            oc = extract_field_block(raw_text, "OPT_C", ["OPT_D"])
            od = extract_field_block(raw_text, "OPT_D", [])

            if q: fallback_data["question"] = clean_hindi_postal_terms(q)
            if s1: fallback_data["sen1"] = clean_hindi_postal_terms(s1)
            if s2: fallback_data["sen2"] = clean_hindi_postal_terms(s2)
            if p1t: fallback_data["param1_title"] = clean_hindi_postal_terms(p1t)
            if p1v: fallback_data["param1_val"] = clean_hindi_postal_terms(p1v)
            if p2t: fallback_data["param2_title"] = clean_hindi_postal_terms(p2t)
            if p2v: fallback_data["param2_val"] = clean_hindi_postal_terms(p2v)
            if tp: fallback_data["trap_point"] = clean_hindi_postal_terms(tp)
            if oa: fallback_data["opt_a"] = clean_hindi_postal_terms(oa)
            if ob: fallback_data["opt_b"] = clean_hindi_postal_terms(ob)
            if oc: fallback_data["opt_c"] = clean_hindi_postal_terms(oc)
            if od: fallback_data["opt_d"] = clean_hindi_postal_terms(od)
    except Exception as e:
        print(f"⚠️ Groq note: {e}")

    return fallback_data

def get_slide_segments(script_data):
    return [
        f"{script_data['hook_voice']}",
        f"{script_data['sen1']}",
        f"परीक्षा विशेष बिंदु: {script_data['sen2']}",
        f"सवाल स्क्रीन पर है! सही उत्तर A, B, C या D कमेंट करें और अगला Postal Trap कल देखें!"
    ]

async def generate_segment_audio(text, outfile):
    if os.path.exists(outfile):
        try: os.remove(outfile)
        except Exception: pass
    communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+0%")
    await communicate.save(outfile)

def get_audio_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    return float(subprocess.check_output(cmd).decode().strip())

def render_and_sync_video(script_data, output_video=OUTPUT_VIDEO):
    ensure_fonts()

    segment_audios = get_slide_segments(script_data)
    durations = []
    
    for i, seg_text in enumerate(segment_audios):
        seg_file = f"audio_seg_{i}.mp3"
        asyncio.run(generate_segment_audio(seg_text, seg_file))
        durations.append(get_audio_duration(seg_file))

    concat_filter = "".join([f"[{i}:a]" for i in range(4)]) + "concat=n=4:v=0:a=1[aout]"
    ffmpeg_concat_cmd = ["ffmpeg", "-y"]
    for i in range(4):
        ffmpeg_concat_cmd.extend(["-i", f"audio_seg_{i}.mp3"])
    ffmpeg_concat_cmd.extend(["-filter_complex", concat_filter, "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "final_master.mp3"])
    subprocess.run(ffmpeg_concat_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    total_dur = sum(durations)
    print(f"🎵 Kinetic Flow Audio: Total {total_dur:.1f}s | Durations: {[round(d, 1) for d in durations]}", flush=True)

    font_brand = get_font(44)
    font_sub = get_font(22)
    font_trust = get_font(20)
    font_badge = get_font(22)
    font_title = get_font(34)
    font_h1 = get_font(38)
    font_h2 = get_font(30)
    font_body = get_font(34)
    font_label = get_font(26)
    font_cta = get_font(30)
    font_opt = get_font(28)
    font_hook = get_font(36)
    font_timer = get_font(32)

    def draw_base(d):
        d.rounded_rectangle([45, 50, 1035, 1710], radius=32, fill="#0B132B", outline="#1E293B", width=3)
        d.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        d.text((80, 130), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)
        d.rounded_rectangle([630, 80, 1000, 132], radius=16, fill="#064E3B", outline="#10B981", width=2)
        d.text((655, 93), "100% OFFICIAL SYLLABUS", fill="#D1FAE5", font=font_trust)

    def draw_footer_cta(d):
        d.rounded_rectangle([80, 1580, 1000, 1680], radius=22, fill="#E11D48")
        d.text((120, 1605), "🔥 अगला Postal Trap कल  |  @POSTAL_WALA", fill="#FFFFFF", font=font_cta)

    frames = []
    frame_durs = []

    # =========================================================================
    # SLIDE 1 (HOOK): REAL-TIME SIREN BLINK ENGINE
    # =========================================================================
    def build_slide1_frame(step, pill_state=True):
        img = Image.new("RGB", (1080, 1920), color="#060A17")
        d = ImageDraw.Draw(img)
        draw_base(d)
        d.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
        d.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
        d.text((120, 195), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
        d.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
        d.text((845, 195), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
        d.text((105, 255), clean_hindi_postal_terms(script_data["clause_name"]), fill="#FFFFFF", font=font_title)
        d.rounded_rectangle([80, 360, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
        
        if pill_state:
            d.rounded_rectangle([110, 395, 410, 445], radius=12, fill="#DC2626", outline="#F87171", width=3)
            d.text((130, 402), "[ ! ] LIVE EXAM ALERT", fill="#FFFFFF", font=font_label)
        else:
            d.rounded_rectangle([110, 395, 410, 445], radius=12, fill="#180C0E", outline="#3F1215", width=1)
            d.text((130, 402), "[ ! ] LIVE EXAM ALERT", fill="#7F1D1D", font=font_label)

        d.rounded_rectangle([110, 470, 970, 580], radius=16, fill="#991B1B", outline="#FBBF24", width=3)
        d.text((150, 500), clean_hindi_postal_terms(script_data["visual_hook_badge"]), fill="#FEF08A", font=font_hook)

        if step >= 2:
            d.rounded_rectangle([110, 630, 480, 685], radius=10, fill="#0B132B", outline="#38BDF8", width=2)
            d.text((130, 640), "विभागीय परीक्षा विशेष:", fill="#38BDF8", font=font_label)
            wrapped_hook = textwrap.fill(clean_hindi_postal_terms(script_data["hook_display_text"]), width=20)
            d.multiline_text((115, 730), wrapped_hook, fill="#FFFFFF", font=font_h1, spacing=16)

        if step >= 3:
            d.rounded_rectangle([110, 1080, 970, 1260], radius=18, fill="#0B132B", outline="#FBBF24", width=2)
            d.text((150, 1115), f"विषय: {clean_hindi_postal_terms(script_data['clause_name'])}", fill="#FDE047", font=font_h2)
            d.text((150, 1180), f"डाक घर गाइड भाग 1 | क्लॉज संख्या: {script_data['clause_no']}", fill="#94A3B8", font=font_opt)
            d.rounded_rectangle([110, 1400, 970, 1490], radius=16, fill="#064E3B", outline="#10B981", width=2)
            d.text((200, 1425), ">> 25 सेकंड में पूरा नियम समझें!", fill="#34D399", font=font_h2)

        draw_footer_cta(d)
        return img

    s1_dur = max(3.0, durations[0])
    blink_seq = [
        (1, True,  0.35),
        (1, False, 0.25),
        (2, True,  0.40),
        (2, False, 0.25),
        (3, True,  0.45),
        (3, False, 0.25),
        (3, True,  max(0.6, s1_dur - 1.95))
    ]
    for b_idx, (st_step, st_on, st_d) in enumerate(blink_seq):
        fn = f"f_1_blink_{b_idx}.png"
        build_slide1_frame(step=st_step, pill_state=st_on).save(fn)
        frames.append(fn)
        frame_durs.append(round(st_d, 2))

    # =========================================================================
    # SLIDE 2 (RULE): 2 BALANCED PARAMETER CARDS
    # =========================================================================
    img2a = Image.new("RGB", (1080, 1920), color="#060A17")
    d2a = ImageDraw.Draw(img2a)
    draw_base(d2a)
    d2a.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
    d2a.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d2a.text((120, 195), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d2a.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d2a.text((845, 195), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d2a.text((105, 255), clean_hindi_postal_terms(script_data["clause_name"]), fill="#FFFFFF", font=font_title)
    
    d2a.rounded_rectangle([80, 360, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
    d2a.rounded_rectangle([110, 400, 480, 455], radius=10, fill="#0B132B")
    d2a.text((150, 410), "नियम विश्लेषण #1:", fill="#38BDF8", font=font_label)
    wrapped_s2 = textwrap.fill(script_data['sen1'], width=24)
    d2a.multiline_text((120, 490), clean_hindi_postal_terms(wrapped_s2), fill="#F8FAFC", font=font_body, spacing=14)

    # Parameter Card 1 (Cyan Box)
    d2a.rounded_rectangle([110, 750, 970, 890], radius=16, fill="#082F49", outline="#38BDF8", width=2)
    d2a.rounded_rectangle([130, 770, 430, 815], radius=8, fill="#0284C7")
    d2a.text((145, 778), f"[ {script_data.get('param1_title', 'परीक्षा मुख्य बिंदु')} ]", fill="#FFFFFF", font=font_label)
    d2a.text((145, 835), script_data.get('param1_val', 'नियम अनुसार मान्य'), fill="#E0F2FE", font=font_h2)
    
    draw_footer_cta(d2a)
    img2a.save("f_2a.png")
    frames.append("f_2a.png")
    frame_durs.append(round(durations[1] * 0.40, 2))

    # Parameter Card 2 (Amber Box)
    img2b = img2a.copy()
    d2b = ImageDraw.Draw(img2b)
    d2b.rounded_rectangle([110, 930, 970, 1070], radius=16, fill="#451A03", outline="#F59E0B", width=2)
    d2b.rounded_rectangle([130, 950, 430, 995], radius=8, fill="#D97706")
    d2b.text((145, 958), f"[ {script_data.get('param2_title', 'विभागीय शर्त')} ]", fill="#FFFFFF", font=font_label)
    d2b.text((145, 1015), script_data.get('param2_val', 'आधिकारिक नियम'), fill="#FEF3C7", font=font_h2)
    img2b.save("f_2b.png")
    frames.append("f_2b.png")
    frame_durs.append(round(durations[1] * 0.35, 2))

    # Teaser Action Box Drops
    img2c = img2b.copy()
    d2c = ImageDraw.Draw(img2c)
    d2c.rounded_rectangle([110, 1370, 970, 1470], radius=14, fill="#0B132B", outline="#38BDF8", width=2)
    d2c.text((160, 1400), "आगे देखिए: इस नियम का परीक्षा ट्रैप बिंदु >>", fill="#38BDF8", font=font_h2)
    img2c.save("f_2c.png")
    frames.append("f_2c.png")
    frame_durs.append(round(durations[1] * 0.25, 2))

    # =========================================================================
    # SLIDE 3 (TRAP): FULL TEXT INSIDE RED WARNING BOX
    # =========================================================================
    img3a = Image.new("RGB", (1080, 1920), color="#060A17")
    d3a = ImageDraw.Draw(img3a)
    draw_base(d3a)
    d3a.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
    d3a.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d3a.text((120, 195), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d3a.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d3a.text((845, 195), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d3a.text((105, 255), clean_hindi_postal_terms(script_data["clause_name"]), fill="#FFFFFF", font=font_title)
    
    d3a.rounded_rectangle([80, 360, 1000, 1550], radius=24, fill="#1C2541", outline="#F59E0B", width=3)
    d3a.rounded_rectangle([110, 400, 480, 455], radius=10, fill="#0B132B")
    d3a.text((150, 410), "परीक्षा अपवाद #2:", fill="#FBBF24", font=font_label)
    
    wrapped_s3 = textwrap.fill(script_data['sen2'], width=24)
    d3a.multiline_text((120, 490), clean_hindi_postal_terms(wrapped_s3), fill="#F8FAFC", font=font_body, spacing=16)
    draw_footer_cta(d3a)
    img3a.save("f_3a.png")
    frames.append("f_3a.png")
    frame_durs.append(round(durations[2] * 0.35, 2))

    # Red Warning Box Appears WITH FULL TEXT INSIDE
    img3b = img3a.copy()
    d3b = ImageDraw.Draw(img3b)
    d3b.rounded_rectangle([80, 360, 1000, 1550], radius=24, outline="#EF4444", width=4)
    d3b.rounded_rectangle([110, 750, 970, 1150], radius=18, fill="#380A0A", outline="#EF4444", width=3)
    d3b.rounded_rectangle([130, 775, 460, 825], radius=8, fill="#7F1D1D")
    d3b.text((145, 783), "[ ! ] परीक्षा में फंसने वाला बिंदु", fill="#FECACA", font=font_label)
    
    trap_txt = script_data.get("trap_point", script_data["sen2"])
    wrapped_trap = textwrap.fill(clean_hindi_postal_terms(trap_txt), width=23)
    d3b.multiline_text((145, 860), wrapped_trap, fill="#FFFFFF", font=font_h2, spacing=14)
    img3b.save("f_3b.png")
    frames.append("f_3b.png")
    frame_durs.append(round(durations[2] * 0.35, 2))

    # Quiz Alert Banner Drops
    img3c = img3b.copy()
    d3c = ImageDraw.Draw(img3c)
    d3c.rounded_rectangle([110, 1370, 970, 1470], radius=14, fill="#0B132B", outline="#FBBF24", width=2)
    d3c.text((180, 1400), "अब आज का सवाल: उत्तर कमेंट करें >>", fill="#FDE047", font=font_h2)
    img3c.save("f_3c.png")
    frames.append("f_3c.png")
    frame_durs.append(round(durations[2] * 0.30, 2))

    # =========================================================================
    # SLIDE 4 (QUIZ): KBC STAGGER + BALANCED SPACING + LIVE 5-SECOND TIMER
    # =========================================================================
    img4a = Image.new("RGB", (1080, 1920), color="#060A17")
    d4a = ImageDraw.Draw(img4a)
    draw_base(d4a)
    d4a.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#FBBF24", width=2)
    d4a.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d4a.text((120, 195), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d4a.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d4a.text((845, 195), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d4a.text((105, 255), "परीक्षा क्विज़: उत्तर कमेंट करें", fill="#FDE047", font=font_title)
    d4a.rounded_rectangle([80, 350, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
    d4a.rounded_rectangle([110, 380, 360, 435], radius=10, fill="#0B132B")
    d4a.text((140, 390), "आज का सवाल:", fill="#FBBF24", font=font_h2)
    wrapped_q4 = textwrap.fill(clean_hindi_postal_terms(script_data["question"]), width=25)
    d4a.multiline_text((110, 460), wrapped_q4, fill="#F8FAFC", font=font_h2, spacing=10)
    draw_footer_cta(d4a)
    img4a.save("f_4a.png")
    frames.append("f_4a.png")
    frame_durs.append(round(durations[3] * 0.15, 2))

    # Option A & B Drop
    img4b = img4a.copy()
    d4b = ImageDraw.Draw(img4b)
    q_lines = wrapped_q4.count("\n") + 1
    start_oy = 460 + (q_lines * 42) + 40
    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    labels = ["A", "B", "C", "D"]
    for o_idx in range(2):
        oy = start_oy + (o_idx * 125)
        d4b.rounded_rectangle([110, oy, 970, oy + 90], radius=16, fill="#0B132B", outline="#38BDF8", width=2)
        d4b.text((135, oy + 22), f"{labels[o_idx]})", fill="#38BDF8", font=font_h2)
        d4b.text((200, oy + 24), textwrap.fill(clean_hindi_postal_terms(opts[o_idx]), width=25), fill="#FFFFFF", font=font_opt)
    img4b.save("f_4b.png")
    frames.append("f_4b.png")
    frame_durs.append(round(durations[3] * 0.15, 2))

    # Option C & D Drop
    img4c = img4b.copy()
    d4c = ImageDraw.Draw(img4c)
    for o_idx in range(2, 4):
        oy = start_oy + (o_idx * 125)
        d4c.rounded_rectangle([110, oy, 970, oy + 90], radius=16, fill="#0B132B", outline="#38BDF8", width=2)
        d4c.text((135, oy + 22), f"{labels[o_idx]})", fill="#38BDF8", font=font_h2)
        d4c.text((200, oy + 24), textwrap.fill(clean_hindi_postal_terms(opts[o_idx]), width=25), fill="#FFFFFF", font=font_opt)
    img4c.save("f_4c.png")
    frames.append("f_4c.png")
    frame_durs.append(round(durations[3] * 0.15, 2))

    # 5-SECOND DYNAMIC COUNTDOWN TIMER WITH PROGRAMMATIC SFX TICKS
    countdown_steps = [
        ("05", "#FDE047", "#064E3B", "#34D399"),
        ("04", "#FDE047", "#064E3B", "#34D399"),
        ("03", "#FB923C", "#7C2D12", "#FB923C"),
        ("02", "#F87171", "#7F1D1D", "#EF4444"),
        ("01", "#EF4444", "#991B1B", "#FCA5A5")
    ]
    
    quiz_rem_dur = max(3.5, durations[3] * 0.55)
    per_timer_dur = round(quiz_rem_dur / 5.0, 2)

    for c_idx, (sec_str, timer_color, bar_bg, bar_outline) in enumerate(countdown_steps):
        img_cd = img4c.copy()
        d_cd = ImageDraw.Draw(img_cd)
        
        d_cd.rounded_rectangle([110, 1180, 970, 1255], radius=14, fill="#0B132B", outline=timer_color, width=2)
        d_cd.text((260, 1195), f"⏳ समय शेष: {sec_str} सेकंड", fill=timer_color, font=font_timer)

        d_cd.rounded_rectangle([110, 1275, 970, 1370], radius=18, fill=bar_bg, outline=bar_outline, width=3)
        d_cd.text((160, 1305), "💬 अपना उत्तर A / B / C / D कमेंट करें!", fill="#FFFFFF", font=font_h2)

        cd_fname = f"f_4_timer_{c_idx}.png"
        img_cd.save(cd_fname)
        frames.append(cd_fname)
        frame_durs.append(per_timer_dur)

    # =========================================================================
    # ADVANCED FFMPEG RENDER WITH PROGRAMMATIC SFX MIXING & PROGRESS BAR
    # =========================================================================
    inputs = []
    filter_parts = ""
    for i, fname in enumerate(frames):
        inputs.extend(["-i", fname])
        safe_dur = max(0.2, frame_durs[i])
        filter_parts += f"[{i}:v]loop=loop=-1:size=1:start=0,trim=duration={safe_dur}[v{i}]; "

    concat_str = "".join([f"[v{i}]" for i in range(len(frames))])
    base_v_filter = f"{filter_parts}{concat_str}concat=n={len(frames)}:v=1:a=0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
    
    progress_bar_filter = (
        f"{base_v_filter},"
        f"drawbox=x=0:y=0:w=iw:h=14:color=#1E293B@1:t=fill,"
        f"drawbox=x=0:y=0:w='iw*(t/{total_dur})':h=14:color=#F43F5E@1:t=fill,"
        f"drawbox=x='max(0, iw*(t/{total_dur})-20)':y=0:w=20:h=14:color=#FEF08A@1:t=fill[v]"
    )

    cmd = ["ffmpeg", "-y"]
    for fname in frames:
        cmd.extend(["-i", fname])
    
    cmd.extend(["-i", "final_master.mp3"])
    voice_idx = len(frames)

    has_bgm = os.path.exists(BGM_OUTPUT)
    if has_bgm:
        cmd.extend(["-stream_loop", "-1", "-i", BGM_OUTPUT])
        bgm_idx = voice_idx + 1
        # Programmatic crisp audio SFX generation filter for pops and ticks
        audio_filter = (
            f"aevalsrc='sin(2*PI*800*t)*exp(-10*t)':d=0.08[sfx_pop];"
            f"aevalsrc='sin(2*PI*1200*t)*exp(-15*t)':d=0.05[sfx_tick];"
            f"[{voice_idx}:a]aresample=48000,volume=1.0[voice]; "
            f"[{bgm_idx}:a]aresample=48000,volume=0.08[bgm]; "
            f"[sfx_pop]adelay=300|300[p1];"
            f"[sfx_tick]adelay=10000|10000[t1];"
            f"[voice][bgm][p1][t1]amix=inputs=4:duration=first:dropout_transition=2,aformat=channel_layouts=stereo[a]"
        )
    else:
        audio_filter = f"[{voice_idx}:a]aresample=48000,aformat=channel_layouts=stereo[a]"

    full_filter = f"{progress_bar_filter}; {audio_filter}"
    cmd.extend(["-filter_complex", full_filter, "-map", "[v]", "-map", "[a]"])
    cmd.extend([
        "-c:v", "libx264", "-preset", "medium", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-shortest", output_video
    ])

    subprocess.run(cmd, check=True)
    print(f"✅ 10/10 Retention Master Reel Created with SFX: {output_video}", flush=True)

# --- LOCAL GENERATED REELS SAVER PROTOCOL ---
def save_reel_to_local_folder(video_file, script_data):
    os.makedirs(REELS_DIR, exist_ok=True)
    
    clause_no = script_data.get("clause_no", 1)
    part_no = script_data.get("part_no", 1)
    
    dest_video = os.path.join(REELS_DIR, f"clause_{clause_no}_part_{part_no}.mp4")
    dest_txt = os.path.join(REELS_DIR, f"clause_{clause_no}_part_{part_no}_caption.txt")
    
    try:
        shutil.copy(video_file, dest_video)
        with open(dest_txt, "w", encoding="utf-8") as f:
            f.write(script_data.get("caption", ""))
            
        print(f"📁 Reel successfully saved locally to: {dest_video}", flush=True)
        print(f"📝 Caption saved to: {dest_txt}", flush=True)
        return True
    except Exception as e:
        print(f"⚠️ Local Save Error: {e}", flush=True)
        return False

# --- MAIN RUNNER ---
if __name__ == "__main__":
    st = load_progress_state()
    print(f"📌 Running Target: Clause {st['clause_no']} (Part {st['current_part']}/{st['total_parts']})", flush=True)
    
    script_data = generate_clause_script(st)
    render_and_sync_video(script_data, OUTPUT_VIDEO)

    saved_ok = save_reel_to_local_folder(OUTPUT_VIDEO, script_data)
    
    if saved_ok:
        advance_progress_state(st)
        print("✅ Reel successfully stored in generated reels folder and state shifted to next part.", flush=True)
    else:
        print("❌ Reel local save failed. State preserved.", flush=True)
        sys.exit(1)
