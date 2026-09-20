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
from PIL import Image, ImageDraw, ImageFont
import edge_tts
from pypdf import PdfReader

# --- Environment Variables ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

GRAPH_API_BASE = "https://graph.facebook.com/v19.0/"
RUPLOAD_BASE = "https://rupload.facebook.com/ig-api-upload/"

STATE_FILE = "progress_state.json"
PDF_FILE_PATH = "mts content .pdf"
FONT_PATH = "Mukta-Bold.ttf"

# --- Folders and Video Outputs ---
REELS_DIR = "generated_reels"
os.makedirs(REELS_DIR, exist_ok=True)

CONCEPT_VIDEO = "concept_reel.mp4" # Normal concept video (Untouched)
QUIZ_VIDEO = os.path.join(REELS_DIR, "quiz_reel.mp4") # 40-Sec Locked Professional Quiz Reel

BGM_OUTPUT = "bgm.mp3"
VOICE_NAME = "hi-IN-SwaraNeural"

ASSETS_DIR = "assets"
RESAMPLE_MODE = getattr(Image, "Resampling", Image).LANCZOS

# --- Official PO Guide Part 1 Clause Titles Dictionary ---
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

def extract_clause_from_pdf(clause_no, current_part=1, total_parts=1, pdf_path=PDF_FILE_PATH):
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
                if len(matched_text) >= 4000:
                    break

        full_text = matched_text.strip() if matched_text.strip() else default_text
        
        # --- Part-wise Chunking to prevent duplicate questions across parts ---
        if total_parts > 1 and len(full_text) > 200:
            chunk_len = max(100, len(full_text) // total_parts)
            start = (current_part - 1) * chunk_len
            end = start + chunk_len if current_part < total_parts else len(full_text)
            part_text = full_text[start:end]
            if len(part_text.strip()) < 50:
                part_text = full_text
        else:
            part_text = full_text

        return final_title[:60], clean_hindi_postal_terms(part_text[:2500])
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
    return "".join(c for c in text if ord(c) < 0x10000).strip()

def clean_hindi_postal_terms(text):
    if not text:
        return ""
    text = re.sub(r"^[:\-\s\.]+", "", text)
    replacements = {
        "पेन्टियों": "पत्र-पेटियों", "पेन्टी": "पत्र-पेटी",
        "घंटी वाली प्लेटें": "घंटे वाली प्लेटें", "घंटी वाली प्लेट": "घंटे वाली प्लेट"
    }
    for bad_w, good_w in replacements.items():
        text = text.replace(bad_w, good_w)
    return clean_text(text)

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
            
    _, pdf_text = extract_clause_from_pdf(state.get("clause_no", 1), state.get("current_part", 1), state.get("total_parts", 1))
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

def generate_clause_script(state):
    current_clause = state.get("clause_no", 1)
    current_part = state.get("current_part", 1)
    total_parts = state.get("total_parts", 1)

    official_title, official_pdf_text = extract_clause_from_pdf(current_clause, current_part, total_parts)

    fallback_data = {
        "clause_no": current_clause,
        "clause_name": official_title,
        "part_no": current_part,
        "total_parts": total_parts,
        "visual_hook_badge": f"[ ! ] क्लॉज {current_clause} स्पेशल",
        "hook_voice": f"ध्यान दें! पोस्टल गाइड क्लॉज {current_clause}। इस क्लॉज से पेपर में ये प्रश्न बन सकते हैं!",
        "hook_display_text": f"पोस्टल गाइड भाग 1 - क्लॉज {current_clause} के सबसे कठिन परीक्षा प्रश्न!",
        "sen1": f"डाक घर गाइड भाग 1 क्लॉज {current_clause} के अनुसार आधिकारिक नियम अनिवार्य रूप से लागू होता है।",
        "sen2": "विभागीय परीक्षा में इस नियम के अपवाद और विशेष प्रावधान से सबसे ज्यादा सवाल पूछे जाते हैं।",
        "param1_title": "परीक्षा मुख्य बिंदु",
        "param1_val": "आधिकारिक नियम मान्य",
        "param2_title": "विभागीय शर्त",
        "param2_val": "नियमों का पालन अनिवार्य",
        "trap_point": "इस नियम की अनदेखी करने पर नकारात्मक अंक मिल सकते हैं।",
        
        "q1": f"डाक गाइड क्लॉज {current_clause} के अनुसार मुख्य नियम क्या है?", "a1": "आधिकारिक नियम", "b1": "अन्य प्रावधान", "c1": "सामान्य निर्देश", "d1": "इनमें से कोई नहीं", "ans1": "A",
        "q2": "इस नियम के तहत परीक्षा में क्या विशेष ध्यान रखना चाहिए?", "a2": "सीमाएं व शर्तें", "b2": "अस्थायी छूट", "c2": "प्रतिबंध", "d2": "इनमें से कोई नहीं", "ans2": "B",
        "q3": "नियम का उल्लंघन होने पर विभाग द्वारा क्या कार्रवाई होती है?", "a3": "बुकिंग अस्वीकार", "b3": "छूट", "c3": "पुरस्कार", "d3": "कुछ नहीं", "ans3": "C",

        "caption": f"🚨 पोस्टल गाइड क्लॉज {current_clause} स्पेशल टेस्ट! डाक घर गाइड भाग 1 (भाग {current_part}/{total_parts})。\n\n💬 फ्री मॉक टेस्ट के लिए MOCK कमेंट करें और Postal Wala को फॉलो करें!\n\n#PostalWala #GDStoMTS #PostmanExam #IndiaPost #DepartmentalExam",
        "quiz_caption": f"🧠 क्विज़: डाक घर गाइड भाग 1 | क्लॉज {current_clause} (भाग {current_part}/{total_parts})。\n\n🎯 3 महत्वपूर्ण सवाल! फ्री मॉक टेस्ट के लिए MOCK कमेंट करें और फॉलो करें!\n\n#PostalQuiz #GDStoMTS #PostmanExam #DepartmentalQuiz"
    }

    if not GROQ_API_KEY:
        return fallback_data

    prompt = f"""
    You are the Senior Chief Examiner for India Post Departmental Examinations (GDS to MTS, Postman, Mail Guard).
    Topic: Post Office Guide Part 1, Clause: {current_clause}, Part: {current_part}/{total_parts}, Official Title: "{official_title}"

    OFFICIAL EXTRACTED TEXT FROM 'mts content .pdf' (Part {current_part} of {total_parts}):
    \"\"\"
    {official_pdf_text}
    \"\"\"

    STRICT RULES FOR EXAM GENERATION:
    1. Generate EXACTLY 3 distinct, highly accurate, exam-oriented MCQ questions based strictly on the provided text chunk.
    2. ABSOLUTE CONSTRAINT FOR OPTIONS (A, B, C, D): Every single option must use authentic postal terminology (e.g., प्रेषक, बीमा, पंजीकृत, आदि). Never use incorrect terms like लेखक.
    3. ANSWERS (ANS1, ANS2, ANS3): Must have varied and correct option letters (e.g., A, B, C, or D) corresponding to the right answer for each question. Do not make all answers 'A'.
    4. Keep questions and options short, clear, and in professional Hindi.

    Format strictly using these tags line-by-line:
    SEN1: ...
    SEN2: ...
    PARAM1_TITLE: ...
    PARAM1_VAL: ...
    PARAM2_TITLE: ...
    PARAM2_VAL: ...
    TRAP_POINT: ...
    Q1: ...
    A1: ...
    B1: ...
    C1: ...
    D1: ...
    ANS1: A
    Q2: ...
    A2: ...
    B2: ...
    C2: ...
    D2: ...
    ANS2: B
    Q3: ...
    A3: ...
    B3: ...
    C3: ...
    D3: ...
    ANS3: C
    """

    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"}
        payload = {"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 700}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            raw_text = res.json()["choices"][0]["message"]["content"].strip()
            for line in raw_text.split('\n'):
                if ':' in line:
                    parts = line.split(':', 1)
                    k = parts[0].strip().lower()
                    v = parts[1].strip().strip('"\'`*')
                    if k in fallback_data:
                        fallback_data[k] = clean_hindi_postal_terms(v)
                        if k.startswith("ans"):
                            fallback_data[k] = fallback_data[k].upper()[:1]
    except Exception as e:
        print(f"⚠️ Groq note: {e}")

    return fallback_data

async def generate_segment_audio(text, outfile, rate="+12%"):
    if os.path.exists(outfile):
        try: os.remove(outfile)
        except Exception: pass
    communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate=rate)
    await communicate.save(outfile)

def get_audio_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    return float(subprocess.check_output(cmd).decode().strip())

# --- NORMAL CONCEPT VIDEO (UNTOUCHED) ---
def render_concept_video(script_data, output_video=CONCEPT_VIDEO):
    ensure_fonts()
    segment_audios = [
        script_data["hook_voice"],
        script_data["sen1"],
        f"परीक्षा विशेष बिंदु: {script_data['sen2']}"
    ]
    durations = []
    for i, seg_text in enumerate(segment_audios):
        seg_file = f"audio_concept_{i}.mp3"
        asyncio.run(generate_segment_audio(seg_text, seg_file, rate="+0%"))
        durations.append(get_audio_duration(seg_file))

    concat_filter = "".join([f"[{i}:a]" for i in range(3)]) + "concat=n=3:v=0:a=1[aout]"
    ffmpeg_concat_cmd = ["ffmpeg", "-y"]
    for i in range(3):
        ffmpeg_concat_cmd.extend(["-i", f"audio_concept_{i}.mp3"])
    ffmpeg_concat_cmd.extend(["-filter_complex", concat_filter, "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "concept_master.mp3"])
    subprocess.run(ffmpeg_concat_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    total_dur = sum(durations)

    font_brand = get_font(44)
    font_sub = get_font(22)
    font_trust = get_font(20)
    font_badge = get_font(22)
    font_title = get_font(34)
    font_h1 = get_font(38)
    font_h2 = get_font(30)
    font_body = get_font(34)
    font_label = get_font(26)
    font_wa_hin = get_font(28)
    font_wa_num = get_font(28)
    font_cta = get_font(30)
    font_hook = get_font(36)

    def draw_base(d):
        d.rounded_rectangle([45, 50, 1035, 1710], radius=32, fill="#0B132B", outline="#1E293B", width=3)
        d.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        d.text((80, 130), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)
        d.rounded_rectangle([630, 80, 1000, 132], radius=16, fill="#064E3B", outline="#10B981", width=2)
        d.text((655, 93), "100% OFFICIAL SYLLABUS", fill="#D1FAE5", font=font_trust)

    def draw_whatsapp_strip(d):
        d.rounded_rectangle([80, 345, 1000, 455], radius=18, fill="#064E3B", outline="#34D399", width=2)
        d.text((110, 360), "GDS to MTS • Postman • Mail Guard • P.A.", fill="#FDE047", font=font_wa_num)
        d.text((110, 405), "कोर्स व फ्री टेस्ट हेतु व्हाट्सएप: 8989971379", fill="#FFFFFF", font=font_wa_hin)

    def draw_footer_cta(d):
        d.rounded_rectangle([80, 1580, 1000, 1680], radius=22, fill="#E11D48")
        d.text((120, 1605), "फ्री मॉक के लिए MOCK कमेंट करें और फॉलो करें!", fill="#FFFFFF", font=font_cta)

    frames = []
    frame_durs = []

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
            d.text((150, 1180), f"डाक घर गाइड भाग 1 | क्लॉज संख्या: {script_data['clause_no']}", fill="#94A3B8", font=font_body)
            d.rounded_rectangle([110, 1400, 970, 1490], radius=16, fill="#064E3B", outline="#10B981", width=2)
            d.text((200, 1425), ">> नियम को ध्यान से समझें!", fill="#34D399", font=font_h2)

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
        fn = f"c_1_blink_{b_idx}.png"
        build_slide1_frame(step=st_step, pill_state=st_on).save(fn)
        frames.append(fn)
        frame_durs.append(round(st_d, 2))

    img2a = Image.new("RGB", (1080, 1920), color="#060A17")
    d2a = ImageDraw.Draw(img2a)
    draw_base(d2a)
    d2a.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
    d2a.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d2a.text((120, 195), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d2a.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d2a.text((845, 195), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d2a.text((105, 255), clean_hindi_postal_terms(script_data["clause_name"]), fill="#FFFFFF", font=font_title)
    draw_whatsapp_strip(d2a)
    
    d2a.rounded_rectangle([80, 480, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
    d2a.rounded_rectangle([110, 520, 480, 575], radius=10, fill="#0B132B")
    d2a.text((150, 530), "नियम विश्लेषण #1:", fill="#38BDF8", font=font_label)
    wrapped_s2 = textwrap.fill(script_data['sen1'], width=24)
    d2a.multiline_text((120, 610), clean_hindi_postal_terms(wrapped_s2), fill="#F8FAFC", font=font_body, spacing=14)

    d2a.rounded_rectangle([110, 830, 970, 970], radius=16, fill="#082F49", outline="#38BDF8", width=2)
    d2a.rounded_rectangle([130, 850, 430, 895], radius=8, fill="#0284C7")
    d2a.text((145, 858), f"[ {script_data.get('param1_title', 'परीक्षा मुख्य बिंदु')} ]", fill="#FFFFFF", font=font_label)
    d2a.text((145, 915), script_data.get('param1_val', 'नियम अनुसार मान्य'), fill="#E0F2FE", font=font_h2)
    draw_footer_cta(d2a)
    img2a.save("c_2a.png")
    frames.append("c_2a.png")
    frame_durs.append(round(durations[1] * 0.45, 2))

    img2b = img2a.copy()
    d2b = ImageDraw.Draw(img2b)
    d2b.rounded_rectangle([110, 1010, 970, 1150], radius=16, fill="#451A03", outline="#F59E0B", width=2)
    d2b.rounded_rectangle([130, 1030, 430, 1075], radius=8, fill="#D97706")
    d2b.text((145, 1038), f"[ {script_data.get('param2_title', 'विभागीय शर्त')} ]", fill="#FFFFFF", font=font_label)
    d2b.text((145, 1095), script_data.get('param2_val', 'आधिकारिक नियम'), fill="#FEF3C7", font=font_h2)
    img2b.save("c_2b.png")
    frames.append("c_2b.png")
    frame_durs.append(round(durations[1] * 0.55, 2))

    img3a = Image.new("RGB", (1080, 1920), color="#060A17")
    d3a = ImageDraw.Draw(img3a)
    draw_base(d3a)
    d3a.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
    d3a.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d3a.text((120, 195), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d3a.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d3a.text((845, 195), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d3a.text((105, 255), clean_hindi_postal_terms(script_data["clause_name"]), fill="#FFFFFF", font=font_title)
    draw_whatsapp_strip(d3a)
    
    d3a.rounded_rectangle([80, 480, 1000, 1550], radius=24, fill="#1C2541", outline="#F59E0B", width=3)
    d3a.rounded_rectangle([110, 520, 480, 575], radius=10, fill="#0B132B")
    d3a.text((150, 530), "परीक्षा अपवाद #2:", fill="#FBBF24", font=font_label)
    
    wrapped_s3 = textwrap.fill(script_data['sen2'], width=24)
    d3a.multiline_text((120, 610), clean_hindi_postal_terms(wrapped_s3), fill="#F8FAFC", font=font_body, spacing=16)
    draw_footer_cta(d3a)
    img3a.save("c_3a.png")
    frames.append("c_3a.png")
    frame_durs.append(round(durations[2] * 0.40, 2))

    img3b = img3a.copy()
    d3b = ImageDraw.Draw(img3b)
    d3b.rounded_rectangle([80, 480, 1000, 1550], radius=24, outline="#EF4444", width=4)
    d3b.rounded_rectangle([110, 850, 970, 1200], radius=18, fill="#380A0A", outline="#EF4444", width=3)
    d3b.rounded_rectangle([130, 875, 460, 925], radius=8, fill="#7F1D1D")
    d3b.text((145, 883), "[ ! ] परीक्षा में फंसने वाला बिंदु", fill="#FECACA", font=font_label)
    
    trap_txt = script_data.get("trap_point", script_data["sen2"])
    wrapped_trap = textwrap.fill(clean_hindi_postal_terms(trap_txt), width=23)
    d3b.multiline_text((145, 960), wrapped_trap, fill="#FFFFFF", font=font_h2, spacing=14)
    img3b.save("c_3b.png")
    frames.append("c_3b.png")
    frame_durs.append(round(durations[2] * 0.60, 2))

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

    cmd = ["ffmpeg", "-y", *inputs, "-i", "concept_master.mp3"]
    voice_idx = len(frames)
    has_bgm = os.path.exists(BGM_OUTPUT)
    if has_bgm:
        cmd.extend(["-stream_loop", "-1", "-i", BGM_OUTPUT])
        bgm_idx = voice_idx + 1
        audio_filter = (
            f"[{voice_idx}:a]aresample=48000,volume=1.0[voice]; "
            f"[{bgm_idx}:a]aresample=48000,volume=0.10[bgm]; "
            f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2,aformat=channel_layouts=stereo[a]"
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
    print(f"✅ Concept Reel Created: {output_video}", flush=True)

# --- 3-QUESTION 40-SEC LOCKED QUIZ VIDEO (LARGER FONTS, CLEAN FINALE SCREEN) ---
def render_quiz_video(script_data, output_video=QUIZ_VIDEO):
    ensure_fonts()
    
    questions_list = [
        {"q_num": "सवाल 1/3", "q": script_data["q1"], "opts": [script_data["a1"], script_data["b1"], script_data["c1"], script_data["d1"]], "ans": script_data["ans1"]},
        {"q_num": "सवाल 2/3", "q": script_data["q2"], "opts": [script_data["a2"], script_data["b2"], script_data["c2"], script_data["d2"]], "ans": script_data["ans2"]},
        {"q_num": "सवाल 3/3", "q": script_data["q3"], "opts": [script_data["a3"], script_data["b3"], script_data["c3"], script_data["d3"]], "ans": script_data["ans3"]},
    ]

    intro_text = f"पोस्टल गाइड क्लॉज {script_data['clause_no']}! इस क्लॉज से पेपर में ये प्रश्न बन सकते हैं!"
    intro_audio_file = "audio_q_intro.mp3"
    asyncio.run(generate_segment_audio(intro_text, intro_audio_file, rate="+12%"))

    audio_files = [intro_audio_file]
    segment_durations = [get_audio_duration(intro_audio_file)]

    for idx, q_data in enumerate(questions_list):
        q_speech = f"{q_data['q']}"
        q_audio_file = f"audio_q_{idx+1}.mp3"
        asyncio.run(generate_segment_audio(q_speech, q_audio_file, rate="+12%"))
        audio_files.append(q_audio_file)
        segment_durations.append(get_audio_duration(q_audio_file))

    # --- UPDATED FINALE VOICE: Direct screen check prompt + MOCK comment & Follow CTA ---
    finale_speech = f"सारे प्रश्नों के सही उत्तर स्क्रीन पर चेक कर लो दोस्तों! फ्री मॉक टेस्ट के लिए MOCK कमेंट करें और Postal Wala को फॉलो करना न भूलें!"
    finale_audio_file = "audio_q_finale.mp3"
    asyncio.run(generate_segment_audio(finale_speech, finale_audio_file, rate="+12%"))
    audio_files.append(finale_audio_file)
    segment_durations.append(get_audio_duration(finale_audio_file))

    concat_filter_audio = ""
    for i in range(len(audio_files)):
        concat_filter_audio += f"[{i}:a]"
    concat_filter_audio += f"concat=n={len(audio_files)}:v=0:a=1[aout]"

    ffmpeg_audio_cmd = ["ffmpeg", "-y"]
    for af in audio_files:
        ffmpeg_audio_cmd.extend(["-i", af])
    ffmpeg_audio_cmd.extend(["-filter_complex", concat_filter_audio, "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "quiz_voice_master.mp3"])
    subprocess.run(ffmpeg_audio_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    font_brand = get_font(40)
    font_sub = get_font(20)
    font_trust = get_font(18)
    font_badge = get_font(20)
    font_title = get_font(32)
    
    # --- EVEN LARGER FONTS TO FILL EMPTY SCREEN SPACE ---
    font_q_text = get_font(34)   # Increased from 30 to fill space
    font_opt_text = get_font(28) # Increased from 25 to fill space
    font_h2 = get_font(24)
    font_cta = get_font(24)

    def draw_base(d):
        d.rounded_rectangle([45, 50, 1035, 1710], radius=32, fill="#0B132B", outline="#1E293B", width=3)
        d.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        d.text((80, 130), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)
        d.rounded_rectangle([630, 80, 1000, 132], radius=16, fill="#064E3B", outline="#10B981", width=2)
        d.text((655, 93), "100% EXAM ORIENTED", fill="#D1FAE5", font=font_trust)

    def draw_footer_cta(d):
        d.rounded_rectangle([80, 1580, 1000, 1680], radius=22, fill="#E11D48")
        d.text((95, 1605), "फ्री मॉक के लिए MOCK कमेंट करें और फॉलो करें!", fill="#FFFFFF", font=font_cta)

    base_img = Image.new("RGB", (1080, 1920), color="#060A17")
    d_base = ImageDraw.Draw(base_img)
    draw_base(d_base)
    d_base.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#FBBF24", width=2)
    d_base.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d_base.text((120, 195), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d_base.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d_base.text((845, 195), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d_base.text((105, 255), "विभागीय परीक्षा स्पेशल टेस्ट", fill="#FDE047", font=font_title)
    d_base.rounded_rectangle([80, 350, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
    draw_footer_cta(d_base)

    frames = []
    frame_durs = []

    intro_img = base_img.copy()
    d_intro = ImageDraw.Draw(intro_img)
    d_intro.rounded_rectangle([110, 520, 970, 880], radius=20, fill="#182848", outline="#FBBF24", width=3)
    d_intro.text((150, 600), f"📌 पोस्टल गाइड क्लॉज {script_data['clause_no']} स्पेशल!", fill="#FDE047", font=font_title)
    d_intro.text((150, 690), "पेपर में इससे ये प्रश्न बन सकते हैं!", fill="#FFFFFF", font=font_q_text)
    intro_frame_name = "quiz_intro_frame.png"
    intro_img.save(intro_frame_name)
    frames.append(intro_frame_name)
    frame_durs.append(segment_durations[0])

    labels = ["A", "B", "C", "D"]

    for idx, q_data in enumerate(questions_list):
        wrapped_q = textwrap.fill(clean_hindi_postal_terms(q_data["q"]), width=24)
        q_lines = wrapped_q.count("\n") + 1
        
        # --- LARGE GAP BETWEEN QUESTION AND OPTIONS TO PREVENT OVERLAP ---
        q_box_bottom = 400 + (q_lines * 42)
        start_oy = max(q_box_bottom + 25, 520)

        opt_heights = []
        wrapped_opts = []
        for opt in q_data["opts"]:
            w_opt = textwrap.fill(clean_hindi_postal_terms(opt), width=26)
            wrapped_opts.append(w_opt)
            o_lines = w_opt.count("\n") + 1
            opt_heights.append(max(95, o_lines * 36 + 22))

        q_audio_dur = segment_durations[idx + 1]
        step_dur = q_audio_dur / 3.0

        # --- STEP 1: Question + Option A ---
        img_s1 = base_img.copy()
        d1 = ImageDraw.Draw(img_s1)
        d1.rounded_rectangle([110, 380, 480, 435], radius=10, fill="#7F1D1D", outline="#F87171", width=2)
        d1.text((130, 390), q_data["q_num"], fill="#FECACA", font=font_h2)
        d1.multiline_text((110, 445), wrapped_q, fill="#F8FAFC", font=font_q_text, spacing=6)
        
        oy = start_oy
        d1.rounded_rectangle([110, oy, 970, oy + opt_heights[0]], radius=12, fill="#0B132B", outline="#38BDF8", width=2)
        d1.text((135, oy + 12), "A)", fill="#38BDF8", font=font_q_text)
        d1.multiline_text((180, oy + 10), wrapped_opts[0], fill="#FFFFFF", font=font_opt_text, spacing=4)
        
        f1_name = f"anim_q{idx+1}_step1.png"
        img_s1.save(f1_name)
        frames.append(f1_name)
        frame_durs.append(step_dur)

        # --- STEP 2: Options B & C ---
        img_s2 = img_s1.copy()
        d2 = ImageDraw.Draw(img_s2)
        
        curr_y = start_oy + opt_heights[0] + 16
        for o_idx in range(1, 3):
            d2.rounded_rectangle([110, curr_y, 970, curr_y + opt_heights[o_idx]], radius=12, fill="#0B132B", outline="#38BDF8", width=2)
            d2.text((135, curr_y + 12), f"{labels[o_idx]})", fill="#38BDF8", font=font_q_text)
            d2.multiline_text((180, curr_y + 10), wrapped_opts[o_idx], fill="#FFFFFF", font=font_opt_text, spacing=4)
            curr_y += opt_heights[o_idx] + 16
        
        f2_name = f"anim_q{idx+1}_step2.png"
        img_s2.save(f2_name)
        frames.append(f2_name)
        frame_durs.append(step_dur)

        # --- STEP 3: Option D + Timer box ---
        img_s3 = img_s2.copy()
        d3 = ImageDraw.Draw(img_s3)
        
        d3.rounded_rectangle([110, curr_y, 970, curr_y + opt_heights[3]], radius=12, fill="#0B132B", outline="#38BDF8", width=2)
        d3.text((135, curr_y + 12), "D)", fill="#38BDF8", font=font_q_text)
        d3.multiline_text((180, curr_y + 10), wrapped_opts[3], fill="#FFFFFF", font=font_opt_text, spacing=4)

        d3.rounded_rectangle([110, 1430, 970, 1510], radius=12, fill="#064E3B", outline="#10B981", width=3)
        d3.text((140, 1455), "⏱️ अपना उत्तर सोचें और नोट करें (उत्तर अंत में)", fill="#A7F3D0", font=font_h2)

        f3_name = f"anim_q{idx+1}_step3.png"
        img_s3.save(f3_name)
        frames.append(f3_name)
        frame_durs.append(step_dur)

    # --- GRAND FINALE SCREEN FOR 3 QUESTIONS (WITH CORRECT DYNAMIC ANSWERS) ---
    img_ans = base_img.copy()
    d_ans = ImageDraw.Draw(img_ans)
    
    d_ans.rounded_rectangle([110, 380, 680, 440], radius=10, fill="#064E3B", outline="#10B981", width=2)
    d_ans.text((130, 392), "🎉 महा-फिनाले: सभी 3 सवालों के सही उत्तर", fill="#34D399", font=font_h2)

    ans_y_start = 480
    answers_text = [
        f"सवाल 1 का सही उत्तर - [ {script_data.get('ans1', 'A')} ]",
        f"सवाल 2 का सही उत्तर - [ {script_data.get('ans2', 'B')} ]",
        f"सवाल 3 का सही उत्तर - [ {script_data.get('ans3', 'C')} ]"
    ]
    
    for a_idx, ans_str in enumerate(answers_text):
        ay = ans_y_start + (a_idx * 180)
        d_ans.rounded_rectangle([110, ay, 970, ay + 140], radius=16, fill="#182848", outline="#FBBF24", width=2)
        d_ans.text((140, ay + 45), clean_hindi_postal_terms(ans_str), fill="#FDE047", font=font_title)

    ans_fname = "quiz_answers_reveal.png"
    img_ans.save(ans_fname)
    frames.append(ans_fname)
    frame_durs.append(segment_durations[-1])

    total_dur = sum(frame_durs)
    print(f"⏱️ Total 3-Question Synced Quiz Reel Duration: {total_dur:.2f} seconds", flush=True)

    filter_parts = ""
    for i, fname in enumerate(frames):
        filter_parts += f"[{i}:v]loop=loop=-1:size=1:start=0,trim=duration={frame_durs[i]}[v{i}]; "

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
    cmd.extend(["-i", "quiz_voice_master.mp3"])

    voice_idx = len(frames)
    has_bgm = os.path.exists(BGM_OUTPUT)
    if has_bgm:
        cmd.extend(["-stream_loop", "-1", "-i", BGM_OUTPUT])
        bgm_idx = voice_idx + 1
        audio_filter = (
            f"[{voice_idx}:a]aresample=48000,volume=1.0[voice]; "
            f"[{bgm_idx}:a]aresample=48000,volume=0.10[bgm]; "
            f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2,aformat=channel_layouts=stereo[a]"
        )
    else:
        audio_filter = f"[{voice_idx}:a]aresample=48000,aformat=channel_layouts=stereo[a]"

    full_filter = f"{progress_bar_filter}; {audio_filter}"
    cmd.extend(["-filter_complex", full_filter, "-map", "[v]", "-map", "[a]"])
    cmd.extend([
        "-c:v", "libx264", "-preset", "medium", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-t", "40.0", output_video
    ])

    subprocess.run(cmd, check=True)
    print(f"✅ 3-Question 40-Sec Locked Quiz Reel Created: {output_video}", flush=True)

# --- Auto-Commit Function to Push Reels to GitHub Folder ---
def auto_commit_and_push_reels():
    try:
        print("📤 Committing and pushing reels to GitHub repository...", flush=True)
        subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", REELS_DIR + "/"], check=True)
        subprocess.run(["git", "commit", "-m", "Auto-upload 3-question 40s professional quiz reel [skip ci]"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("🎉 Successfully pushed professional quiz reel to GitHub folder!", flush=True)
    except Exception as e:
        print(f"⚠️ Git push note: {e}", flush=True)

# --- MAIN RUNNER ---
if __name__ == "__main__":
    st = load_progress_state()
    print(f"📌 Running Target: Clause {st['clause_no']} (Part {st['current_part']}/{st['total_parts']})", flush=True)
    
    script_data = generate_clause_script(st)
    
    # 1. Generate Normal Concept Video (Untouched)
    print("🎬 Generating Concept Reel...", flush=True)
    render_concept_video(script_data, CONCEPT_VIDEO)
    
    # 2. Generate 3-Question 40-Sec Locked Quiz Video inside folder
    print("🧠 Generating 3-Question 40-Sec Locked Quiz Reel...", flush=True)
    render_quiz_video(script_data, QUIZ_VIDEO)
    
    # 3. Auto push to GitHub folder
    auto_commit_and_push_reels()
    
    print("🎉 Done! 3-question 40-sec locked quiz reel generated inside the 'generated_reels' folder.", flush=True)
