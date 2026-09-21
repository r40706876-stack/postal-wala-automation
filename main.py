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
        return final_title[:60], clean_hindi_postal_terms(final_text[:2500])
    except Exception as e:
        print(f"⚠️ PDF Extraction Error: {e}", flush=True)
    return final_title, default_text

def get_dynamic_total_parts(pdf_text):
    if not pdf_text: return 1
    char_count = len(pdf_text.strip())
    if char_count < 300: return 1
    elif char_count < 700: return 2
    elif char_count < 1200: return 3
    elif char_count < 1800: return 4
    else: return 5

def clean_text(text):
    if not text: return ""
    text = text.strip().strip("\"'`")
    return "".join(c for c in text if ord(c) < 0x10000).strip()

def clean_hindi_postal_terms(text):
    if not text: return ""
    text = re.sub(r"^[:\-\s\.]+", "", text)
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
                with open(FONT_PATH, "wb") as f: f.write(r.content)
        except Exception: pass

def get_font(size):
    ensure_fonts()
    if os.path.exists(FONT_PATH):
        try: return ImageFont.truetype(FONT_PATH, size)
        except Exception: pass
    return ImageFont.load_default()

def load_progress_state():
    state = {"clause_no": 16, "current_part": 1, "total_parts": 1}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                if isinstance(saved, dict) and "clause_no" in saved:
                    state.update(saved)
        except Exception: pass
    _, pdf_text = extract_clause_from_pdf(state.get("clause_no", 16))
    state["total_parts"] = get_dynamic_total_parts(pdf_text)
    save_progress_state(state)
    return state

def save_progress_state(state):
    try:
        with open(STATE_FILE, "w") as f: json.dump(state, f, indent=2)
    except Exception: pass

def advance_progress_state(state):
    clause = state.get("clause_no", 16)
    part = state.get("current_part", 1)
    total_parts = state.get("total_parts", 1)
    if part < total_parts:
        state["current_part"] = part + 1
    else:
        state["clause_no"] = clause + 1 if clause < 60 else 1
        state["current_part"] = 1
    save_progress_state(state)

# --- CLEAN & NATURAL HINDI SCRIPT GENERATOR ---
def generate_clause_script(state):
    current_clause = state.get("clause_no", 16)
    current_part = state.get("current_part", 1)
    total_parts = state.get("total_parts", 1)
    official_title, official_pdf_text = extract_clause_from_pdf(current_clause)

    fallback_data = {
        "clause_no": current_clause,
        "clause_name": official_title,
        "part_no": current_part,
        "total_parts": total_parts,
        "hook_text": "सीलिंग वैक्स से पत्र की सुरक्षा कैसे करें?",
        "guess_wrong": "सीधे वैक्स लगाने से कोई नुकसान नहीं होता।",
        "reward_right": "गलत! पहले पारदर्शी कागज की पतली परत लगानी जरूरी है।",
        "fact_desc": "पारदर्शी कागज की पतली परत",
        "exam_trap": "सीधे वैक्स लगाने पर पत्र चिपककर नुकसान होगा।",
        "question": "सीलिंग वैक्स लगाने से पहले क्या रखना चाहिए?",
        "opt_a": "पारदर्शी कागज की पतली परत",
        "opt_b": "मोटे गत्ते की परत",
        "opt_c": "चिपकने वाला टेप",
        "opt_d": "सादा कपड़ा",
        "caption": f"🚨 डाक घर गाइड भाग 1 | क्लॉज {current_clause} - विभागीय परीक्षा महत्वपूर्ण नियम।\n\n💬 अपना सही उत्तर कमेंट करें (A/B/C/D)!\n\n#PostalWala #GDStoMTS #PostmanExam #IndiaPost"
    }

    if not GROQ_API_KEY:
        return fallback_data

    prompt = f"""
    You are an expert postal exam creator. Read the official text and create a natural, high-engagement script in pure Devanagari Hindi. NO English words. NO random numbers.
    Text: {official_pdf_text}

    Provide fields:
    HOOK_TEXT: A powerful scroll-stopping hook question in Hindi (max 12 words).
    GUESS_WRONG: A common wrong assumption in Hindi (max 10 words).
    REWARD_RIGHT: The exact correct correction in Hindi (max 10 words).
    FACT_DESC: Short precise label for screen text (max 5 words).
    EXAM_TRAP: A strict exam warning or consequence in Hindi (max 12 words).
    QUESTION: A crisp MCQ question in Hindi (max 12 words).
    OPT_A: Correct option.
    OPT_B, OPT_C, OPT_D: Distractors.

    FORMAT:
    HOOK_TEXT: ...
    GUESS_WRONG: ...
    REWARD_RIGHT: ...
    FACT_DESC: ...
    EXAM_TRAP: ...
    QUESTION: ...
    OPT_A: ...
    OPT_B: ...
    OPT_C: ...
    OPT_D: ...
    """

    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"}
        payload = {"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 500}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            raw_text = res.json()["choices"][0]["message"]["content"].strip()
            ht = extract_field_block(raw_text, "HOOK_TEXT", ["GUESS_WRONG"])
            gw = extract_field_block(raw_text, "GUESS_WRONG", ["REWARD_RIGHT"])
            rr = extract_field_block(raw_text, "REWARD_RIGHT", ["FACT_DESC"])
            fd = extract_field_block(raw_text, "FACT_DESC", ["EXAM_TRAP"])
            et = extract_field_block(raw_text, "EXAM_TRAP", ["QUESTION"])
            q = extract_field_block(raw_text, "QUESTION", ["OPT_A"])
            oa = extract_field_block(raw_text, "OPT_A", ["OPT_B"])
            ob = extract_field_block(raw_text, "OPT_B", ["OPT_C"])
            oc = extract_field_block(raw_text, "OPT_C", ["OPT_D"])
            od = extract_field_block(raw_text, "OPT_D", [])

            if ht: fallback_data["hook_text"] = clean_hindi_postal_terms(ht)
            if gw: fallback_data["guess_wrong"] = clean_hindi_postal_terms(gw)
            if rr: fallback_data["reward_right"] = clean_hindi_postal_terms(rr)
            if fd: fallback_data["fact_desc"] = clean_hindi_postal_terms(fd)
            if et: fallback_data["exam_trap"] = clean_hindi_postal_terms(et)
            if q: fallback_data["question"] = clean_hindi_postal_terms(q)
            if oa: fallback_data["opt_a"] = clean_hindi_postal_terms(oa)
            if ob: fallback_data["opt_b"] = clean_hindi_postal_terms(ob)
            if oc: fallback_data["opt_c"] = clean_hindi_postal_terms(oc)
            if od: fallback_data["opt_d"] = clean_hindi_postal_terms(od)
    except Exception as e:
        print(f"⚠️ Groq note: {e}")

    return fallback_data

# --- AUDIO SEGMENTS WITH DETAILED VOICEOVER & CLEAN SCREEN TEXT ---
def get_slide_segments(script_data):
    return [
        f"ध्यान दें! {script_data['hook_text']}",
        f"क्या आपको लगता है कि {script_data['guess_wrong']}? {script_data['reward_right']}",
        f"अधिकारिक नियम को विस्तार से समझें: {script_data['fact_desc']}। पार्सल की सुरक्षा और गोपनीयता बनाए रखने के लिए यह प्रक्रिया बेहद जरूरी है।",
        f"सावधान! परीक्षा ट्रैप: {script_data['exam_trap']}",
        f"अब विभागीय परीक्षा का यह मुख्य सवाल आपके सामने है। सही विकल्प सोचकर पाँच सेकंड में कमेंट करें!"
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
        d = get_audio_duration(seg_file)
        durations.append(max(3.0, d))

    concat_filter = "".join([f"[{i}:a]" for i in range(5)]) + "concat=n=5:v=0:a=1[aout]"
    ffmpeg_concat_cmd = ["ffmpeg", "-y"]
    for i in range(5):
        ffmpeg_concat_cmd.extend(["-i", f"audio_seg_{i}.mp3"])
    ffmpeg_concat_cmd.extend(["-filter_complex", concat_filter, "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "final_master.mp3"])
    subprocess.run(ffmpeg_concat_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    total_dur = sum(durations)

    font_brand = get_font(40)
    font_h1 = get_font(34)
    font_h2 = get_font(26)
    font_body = get_font(25)
    font_label = get_font(24)
    font_cta = get_font(26)
    font_opt = get_font(24)
    font_timer = get_font(30)

    def draw_base(d):
        d.rounded_rectangle([45, 50, 1035, 1710], radius=32, fill="#0B132B", outline="#1E293B", width=3)
        d.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        d.text((80, 125), "@POSTAL_WALA", fill="#94A3B8", font=font_label)

    def draw_footer_cta(d):
        d.rounded_rectangle([80, 1580, 1000, 1680], radius=22, fill="#E11D48")
        d.text((120, 1605), "🔥 अगला Postal Trap कल  |  Follow @POSTAL_WALA", fill="#FFFFFF", font=font_cta)

    frames = []
    frame_durs = []

    # 1. HOOK FRAME
    img_hook = Image.new("RGB", (1080, 1920), color="#060A17")
    dh = ImageDraw.Draw(img_hook)
    draw_base(dh)
    dh.rounded_rectangle([80, 180, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
    dh.rounded_rectangle([110, 230, 420, 290], radius=12, fill="#DC2626", outline="#F87171", width=2)
    dh.text((130, 242), "⚠️ ध्यान दें", fill="#FFFFFF", font=font_label)
    wrapped_hk = textwrap.fill(script_data["hook_text"], width=21)
    dh.multiline_text((115, 420), wrapped_hk, fill="#FFFFFF", font=font_h1, spacing=16)
    draw_footer_cta(dh)
    img_hook.save("f_hook.png")
    frames.append("f_hook.png")
    frame_durs.append(durations[0])

    # 2. GUESS & REWARD FRAME
    img_rew = Image.new("RGB", (1080, 1920), color="#060A17")
    dr = ImageDraw.Draw(img_rew)
    draw_base(dr)
    dr.rounded_rectangle([80, 180, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
    
    dr.rounded_rectangle([110, 235, 970, 495], radius=18, fill="#3F1215", outline="#EF4444", width=3)
    wrapped_gw = textwrap.fill(script_data["guess_wrong"], width=22)
    dr.multiline_text((135, 310), f"❌ {wrapped_gw}", fill="#FCA5A5", font=font_h2, spacing=10)

    dr.rounded_rectangle([110, 535, 970, 865], radius=18, fill="#064E3B", outline="#10B981", width=3)
    wrapped_rr = textwrap.fill(script_data["reward_right"], width=22)
    dr.multiline_text((135, 605), f"✅ {wrapped_rr}", fill="#A7F3D0", font=font_h1, spacing=10)
    dr.text((135, 785), "📌 आधिकारिक विभागीय नियम", fill="#D1FAE5", font=font_body)
    
    draw_footer_cta(dr)
    img_rew.save("f_reward.png")
    frames.append("f_reward.png")
    frame_durs.append(durations[1])

    # 3. FACT FRAME (Clean Screen Text, Detailed Audio)
    img_fact = Image.new("RGB", (1080, 1920), color="#060A17")
    df = ImageDraw.Draw(img_fact)
    draw_base(df)
    df.rounded_rectangle([80, 180, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
    df.text((120, 260), "🧠 आधिकारिक नियम", fill="#94A3B8", font=font_h2)
    df.rounded_rectangle([110, 360, 970, 750], radius=20, fill="#1D4ED8", outline="#60A5FA", width=3)
    wrapped_fd = textwrap.fill(script_data["fact_desc"], width=20)
    df.multiline_text((135, 520), f"📌\n\n{wrapped_fd}", fill="#FFFFFF", font=font_h1, spacing=14)
    draw_footer_cta(df)
    img_fact.save("f_fact.png")
    frames.append("f_fact.png")
    frame_durs.append(durations[2])

    # 4. EXAM TRAP FRAME
    img_trap = Image.new("RGB", (1080, 1920), color="#060A17")
    dt = ImageDraw.Draw(img_trap)
    draw_base(dt)
    dt.rounded_rectangle([80, 180, 1000, 1550], radius=24, fill="#1C2541", outline="#EF4444", width=3)
    dt.rounded_rectangle([110, 230, 480, 290], radius=12, fill="#7F1D1D", outline="#EF4444", width=2)
    dt.text((130, 242), "⚠️ परीक्षा ट्रैप", fill="#FECACA", font=font_label)
    wrapped_trap = textwrap.fill(script_data["exam_trap"], width=21)
    dt.multiline_text((115, 450), wrapped_trap, fill="#FFFFFF", font=font_h1, spacing=16)
    draw_footer_cta(dt)
    img_trap.save("f_trap.png")
    frames.append("f_trap.png")
    frame_durs.append(durations[3])

    # 5. MCQ FRAME
    img_mcq = Image.new("RGB", (1080, 1920), color="#060A17")
    dm = ImageDraw.Draw(img_mcq)
    draw_base(dm)
    dm.rounded_rectangle([80, 180, 1000, 1550], radius=24, fill="#1C2541", outline="#FBBF24", width=3)
    dm.text((110, 205), "📝 विभागीय प्रश्न (MCQ)", fill="#FDE047", font=font_h2)
    wrapped_q = textwrap.fill(script_data["question"], width=22)
    dm.multiline_text((110, 260), wrapped_q, fill="#FFFFFF", font=font_body, spacing=6)
    
    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    labels = ["A", "B", "C", "D"]
    for o_idx in range(4):
        oy = 510 + (o_idx * 135)
        dm.rounded_rectangle([110, oy, 970, oy + 120], radius=16, fill="#0B132B", outline="#38BDF8", width=2)
        dm.text((135, oy + 38), f"{labels[o_idx]})", fill="#38BDF8", font=font_h2)
        dm.text((195, oy + 38), textwrap.fill(opts[o_idx], width=20), fill="#FFFFFF", font=font_opt)
    
    draw_footer_cta(dm)
    img_mcq.save("f_mcq.png")
    frames.append("f_mcq.png")
    mcq_speech_dur = durations[4]
    countdown_total_dur = 3.5
    mcq_frame_dur = max(2.5, mcq_speech_dur - countdown_total_dur)
    frame_durs.append(mcq_frame_dur)

    # Countdown Frames
    countdown_steps = [
        ("05", "#FDE047", "#064E3B", "#34D399"),
        ("04", "#FDE047", "#064E3B", "#34D399"),
        ("03", "#FB923C", "#7C2D12", "#FB923C"),
        ("02", "#F87171", "#7F1D1D", "#EF4444"),
        ("01", "#EF4444", "#991B1B", "#FCA5A5")
    ]
    per_timer_dur = round(countdown_total_dur / 5.0, 2)

    for c_idx, (sec_str, timer_color, bar_bg, bar_outline) in enumerate(countdown_steps):
        img_cd = img_mcq.copy()
        d_cd = ImageDraw.Draw(img_cd)
        d_cd.rounded_rectangle([110, 1180, 970, 1255], radius=14, fill="#0B132B", outline=timer_color, width=2)
        d_cd.text((260, 1195), f"⏳ समय शेष: {sec_str} सेकंड", fill=timer_color, font=font_timer)
        d_cd.rounded_rectangle([110, 1275, 970, 1370], radius=18, fill=bar_bg, outline=bar_outline, width=3)
        d_cd.text((160, 1305), "💬 A / B / C / D कमेंट करो 👇", fill="#FFFFFF", font=font_h2)

        cd_fname = f"f_4_timer_{c_idx}.png"
        img_cd.save(cd_fname)
        frames.append(cd_fname)
        frame_durs.append(per_timer_dur)

    # =========================================================================
    # FFMPEG RENDER WITH SFX
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
        audio_filter = (
            f"aevalsrc='sin(2*PI*800*t)*exp(-10*t)':d=0.08[sfx_pop];"
            f"[{voice_idx}:a]aresample=48000,volume=1.0[voice]; "
            f"[{bgm_idx}:a]aresample=48000,volume=0.08[bgm]; "
            f"[sfx_pop]adelay=300|300[p1];"
            f"[voice][bgm][p1]amix=inputs=3:duration=first:dropout_transition=2,aformat=channel_layouts=stereo[a]"
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
    print(f"✅ Clean Professional Reel Created: {output_video}", flush=True)

def save_reel_to_local_folder(video_file, script_data):
    os.makedirs(REELS_DIR, exist_ok=True)
    clause_no = script_data.get("clause_no", 16)
    part_no = script_data.get("part_no", 1)
    dest_video = os.path.join(REELS_DIR, f"clause_{clause_no}_part_{part_no}.mp4")
    dest_txt = os.path.join(REELS_DIR, f"clause_{clause_no}_part_{part_no}_caption.txt")
    
    try:
        shutil.copy(video_file, dest_video)
        with open(dest_txt, "w", encoding="utf-8") as f:
            f.write(script_data.get("caption", ""))
        print(f"📁 Saved to: {dest_video}", flush=True)
        return True
    except Exception as e:
        print(f"⚠️ Local Save Error: {e}", flush=True)
        return False

if __name__ == "__main__":
    st = load_progress_state()
    print(f"📌 Target: Clause {st['clause_no']} (Part {st['current_part']}/{st['total_parts']})", flush=True)
    script_data = generate_clause_script(st)
    render_and_sync_video(script_data, OUTPUT_VIDEO)
    saved_ok = save_reel_to_local_folder(OUTPUT_VIDEO, script_data)
    
    if saved_ok:
        advance_progress_state(state=st)
        print("✅ Reel stored successfully & state updated.", flush=True)
    else:
        print("❌ Save failed.", flush=True)
        sys.exit(1)
