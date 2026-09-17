import os
import glob
import json
import time
import asyncio
import subprocess
import requests
import textwrap
from pypdf import PdfReader
from PIL import Image, ImageDraw, ImageFont
from groq import Groq
import edge_tts

# --- Environment Variables ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

GRAPH_API_BASE = "".join(["http", "s://", "graph.", "facebook", ".com/v19.0/"])
RUPLOAD_BASE = "https://rupload.facebook.com/ig-api-upload/v19.0/"

STATE_FILE = "progress_state.json"
DEV_FONT_PATH = "NotoSansDevanagari-Bold.ttf"
AUDIO_OUTPUT = "voice.mp3"
OUTPUT_VIDEO = "final_reel.mp4"
VOICE_NAME = "hi-IN-SwaraNeural"

# --- Font Management ---
def ensure_fonts():
    if not os.path.exists(DEV_FONT_PATH):
        print("📥 Downloading Noto Sans Devanagari font...", flush=True)
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        r = requests.get(url, timeout=30)
        with open(DEV_FONT_PATH, "wb") as f:
            f.write(r.content)
        print("✅ Font cached locally.", flush=True)

def get_dev_font(size):
    ensure_fonts()
    try:
        return ImageFont.truetype(DEV_FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()

def get_eng_font(size):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return get_dev_font(size)

# --- PDF & State Tracking ---
def get_target_pdf():
    pdf_files = glob.glob("*.pdf") + glob.glob("data/*.pdf")
    if not pdf_files:
        raise FileNotFoundError("Repo me koi PDF nahi mili! Kripya PDF repo me rakhein.")
    for f in pdf_files:
        if "mts" in f.lower():
            return f
    return pdf_files[0]

def load_progress_state():
    state = {
        "clause_no": 1,
        "current_part": 1,
        "total_parts": 1,
        "last_page": 0,
        "char_offset": 0
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state.update(json.load(f))
        except Exception:
            pass
    return state

def save_progress_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"⚠️ Warning saving state: {e}", flush=True)

def get_pdf_context_snippet(pdf_path, state):
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)

    page_idx = state.get("last_page", 0)
    if page_idx >= total_pages:
        page_idx = 0
        state["last_page"] = 0
        state["char_offset"] = 0

    page_text = reader.pages[page_idx].extract_text() or ""
    offset = state.get("char_offset", 0)
    chunk = page_text[offset:offset + 1200]

    if not chunk.strip() or (offset + 1200 >= len(page_text)):
        if page_idx + 1 < total_pages:
            next_page_text = reader.pages[page_idx + 1].extract_text() or ""
            chunk = (chunk + "\n" + next_page_text)[:1200]

    return chunk, page_idx + 1

# --- AI Script Generation (Exhaustive & Accurate) ---
def generate_partwise_clause_script(pdf_snippet, state):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY missing in GitHub Secrets!")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
        "Content-Type": "application/json"
    }

    current_clause = state.get("clause_no", 1)
    current_part = state.get("current_part", 1)

    prompt = f"""
    You are the Senior Chief Instructor for India Post Departmental Examinations (MTS, Postman, Mail Guard, Postal Assistant) running the preparation channel 'Postal Wala'.

    CORE MANDATE:
    Teach the departmental rules from Post Office Guide Part 1 thoroughly, accurately, and clause-by-clause.
    Do NOT rush. If a clause is large, break it down honestly across multiple parts (e.g. 2, 3, 4 parts).
    Current Position: Working on Clause #{current_clause}, Part #{current_part}.

    Reference section from study material:
    \"\"\"{pdf_snippet}\"\"\"

    OPERATIONAL INSTRUCTIONS:
    1. REFERENCE ONLY: Use the reference text solely to identify which official PO Guide Part 1 Clause / Topic is currently being covered.
    2. AUTHORITATIVE KNOWLEDGE: Do NOT copy OCR typographical mistakes or broken syllables. Retrieve authentic, updated official India Post rules with 100% factual accuracy (e.g. 'सक्षम प्राधिकारी', 'वित्तीय वर्ष', 'वितरण टिकट', 'अनपेड डाक').
    3. EXHAUSTIVE SUB-PART COVERAGE:
       - Decide TOTAL_PARTS needed to thoroughly teach this clause.
       - In Part #{current_part}, focus on this specific sub-rule with complete precision (timelines, authorities, conditions, exceptions).
    4. SCRIPT CONSTRAINTS:
       - Pure Hindi (Devanagari script only), flawless grammar, authoritative exam terminology, zero spelling mistakes, no English words, no emojis.
       - Total speaking duration strictly under 45-50 seconds (max 85 words total).
    5. VOICE HOOK SEQUENCE:
       - Warm greeting.
       - Ask the QUESTION immediately.
       - Say EXACTLY: "इसका जवाब जानने के लिए वीडियो में अंत तक बने रहें!".
       - Explain SEN1 to SEN4 clearly.
       - Say EXACTLY: "तो दोस्तों, इसका सही उत्तर कमेंट्स में जरूर बताएं!".
       - If {current_part} < TOTAL_PARTS: "इस नियम के अगले भाग को जानने के लिए अभी फॉलो कर लें!"
       - End with: "GDS to MTS, Postman और P.A. कोर्स हेतु 8989971379 पर WhatsApp करें।"
       - DO NOT reveal or speak the correct answer anywhere in the audio.

    FORMAT STRICTLY MATCHING:
    CLAUSE_NO: [{current_clause}]
    PART_NO: [{current_part}]
    TOTAL_PARTS: [Total parts for this clause, e.g. 2]
    TITLE: [क्लॉज {current_clause} (भाग {current_part}/TOTAL_PARTS): नियम का नाम]
    SEN1: [Flawless exam rule sentence 1]
    SEN2: [Flawless exam rule sentence 2]
    SEN3: [Flawless exam rule sentence 3]
    SEN4: [Flawless exam rule sentence 4]
    QUESTION: [1 high-value exam question based strictly on this rule in Hindi]
    OPT_A: [Option A]
    OPT_B: [Option B]
    OPT_C: [Option C]
    OPT_D: [Option D]
    CORRECT: [A/B/C/D]
    VOICEOVER: [Exact full voiceover following the hook sequence]
    CAPTION: [Instagram caption with #PostalWala #MTSExam #PostmanExam #POGuidePart1]
    """

    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 900
    }

    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
    res_json = res.json()

    if res.status_code != 200 or "choices" not in res_json:
        raise RuntimeError(f"Groq API Error: {res_json}")

    raw_text = res_json["choices"][0]["message"]["content"].strip()

    data = {
        "clause_no": current_clause,
        "part_no": current_part,
        "total_parts": 2,
        "rule_title": f"क्लॉज {current_clause} (भाग {current_part}/2): डाक विभाग के नियम",
        "sen1": "विभागीय नियमों के अनुसार सभी डाक वस्तुओं का सुरक्षित प्रबंधन अनिवार्य है।",
        "sen2": "प्रत्येक डाकघर में प्राप्त सामग्री की प्रविष्टि आधिकारिक रजिस्टर में दर्ज की जाती है।",
        "sen3": "नियमों का उल्लंघन पाए जाने पर उच्च अधिकारियों द्वारा सख्त कार्रवाई की जाती है।",
        "sen4": "सभी अभ्यर्थियों को परीक्षा की दृष्टि से इन महत्वपूर्ण प्रावधानों को याद रखना चाहिए।",
        "question": "विभागीय नियमों के उल्लंघन पर कार्रवाई करने का अधिकार किसे प्राप्त है?",
        "opt_a": "स्थानीय डाकपाल",
        "opt_b": "उच्च अधिकारियों को",
        "opt_c": "प्रेषक को",
        "opt_d": "इनमें से कोई नहीं",
        "correct": "B",
        "voiceover": f"नमस्कार साथियों, पोस्टल वाला में आपका स्वागत है। आज का महत्वपूर्ण प्रश्न है: विभागीय नियमों के उल्लंघन पर कार्रवाई करने का अधिकार किसे प्राप्त है? इसका जवाब जानने के लिए वीडियो में अंत तक बने रहें! विभागीय नियमों के अनुसार सभी डाक वस्तुओं का सुरक्षित प्रबंधन अनिवार्य है। प्रत्येक डाकघर में प्राप्त सामग्री की प्रविष्टि आधिकारिक रजिस्टर में दर्ज होती है। नियमों के उल्लंघन पर उच्च अधिकारियों द्वारा सख्त कार्रवाई की जाती है। इन नियमों को परीक्षा हेतु अच्छी तरह याद रखें। तो दोस्तों, इसका सही उत्तर कमेंट्स में जरूर बताएं! GDS to MTS, Postman और P.A. कोर्स हेतु 8989971379 पर WhatsApp करें।",
        "caption": f"डाक विभाग परीक्षा तैयारी क्लॉज {current_clause} संपूर्ण विश्लेषण #PostalWala #MTSExam #POGuidePart1"
    }

    for line in raw_text.splitlines():
        line_clean = line.strip()
        if line_clean.startswith("CLAUSE_NO:"):
            try:
                data["clause_no"] = int(line_clean.replace("CLAUSE_NO:", "").strip())
            except Exception:
                pass
        elif line_clean.startswith("PART_NO:"):
            try:
                data["part_no"] = int(line_clean.replace("PART_NO:", "").strip())
            except Exception:
                pass
        elif line_clean.startswith("TOTAL_PARTS:"):
            try:
                data["total_parts"] = int(line_clean.replace("TOTAL_PARTS:", "").strip())
            except Exception:
                pass
        elif line_clean.startswith("TITLE:"):
            data["rule_title"] = line_clean.replace("TITLE:", "").strip()
        elif line_clean.startswith("SEN1:"):
            data["sen1"] = line_clean.replace("SEN1:", "").strip()
        elif line_clean.startswith("SEN2:"):
            data["sen2"] = line_clean.replace("SEN2:", "").strip()
        elif line_clean.startswith("SEN3:"):
            data["sen3"] = line_clean.replace("SEN3:", "").strip()
        elif line_clean.startswith("SEN4:"):
            data["sen4"] = line_clean.replace("SEN4:", "").strip()
        elif line_clean.startswith("QUESTION:"):
            data["question"] = line_clean.replace("QUESTION:", "").strip()
        elif line_clean.startswith("OPT_A:"):
            data["opt_a"] = line_clean.replace("OPT_A:", "").strip()
        elif line_clean.startswith("OPT_B:"):
            data["opt_b"] = line_clean.replace("OPT_B:", "").strip()
        elif line_clean.startswith("OPT_C:"):
            data["opt_c"] = line_clean.replace("OPT_C:", "").strip()
        elif line_clean.startswith("OPT_D:"):
            data["opt_d"] = line_clean.replace("OPT_D:", "").strip()
        elif line_clean.startswith("CORRECT:"):
            data["correct"] = line_clean.replace("CORRECT:", "").strip().upper()[:1]
        elif line_clean.startswith("VOICEOVER:"):
            data["voiceover"] = line_clean.replace("VOICEOVER:", "").strip()
        elif line_clean.startswith("CAPTION:"):
            data["caption"] = line_clean.replace("CAPTION:", "").strip()

    for k in data:
        if isinstance(data[k], str):
            data[k] = "".join(c for c in data[k] if ord(c) < 0x10000)

    return data

def advance_progress_state(state, data):
    cur_part = data.get("part_no", state.get("current_part", 1))
    total_parts = data.get("total_parts", state.get("total_parts", 1))

    if cur_part < total_parts:
        state["current_part"] = cur_part + 1
        state["total_parts"] = total_parts
        print(f"📌 Clause {state['clause_no']} in progress: next run will do Part {state['current_part']}/{total_parts}", flush=True)
    else:
        state["clause_no"] = state.get("clause_no", 1) + 1
        state["current_part"] = 1
        state["total_parts"] = 1
        state["char_offset"] = state.get("char_offset", 0) + 1200
        print(f"🎉 Clause completed! Next run will start Clause {state['clause_no']} (Part 1)", flush=True)

    save_progress_state(state)

# --- Voice Generation ---
async def generate_voice(text, filename="voice.mp3"):
    communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+10%")
    await communicate.save(filename)

def get_audio_duration(audio_file):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_file]
    output = subprocess.check_output(cmd).decode().strip()
    return float(output)

# --- Video Rendering (Safe Zones & Clean Graphics) ---
def create_video_ffmpeg(script_data, audio_file="voice.mp3", output_video="final_reel.mp4"):
    ensure_fonts()
    total_dur = get_audio_duration(audio_file)

    # 60-Second Hard Limit Protection
    if total_dur > 57.0:
        tempo = round(total_dur / 54.0, 2)
        print(f"⚡ Audio duration ({total_dur:.1f}s) > 57s. Adjusting speed by {tempo}x...", flush=True)
        adjusted_audio = "voice_fast.mp3"
        cmd_speed = ["ffmpeg", "-y", "-i", audio_file, "-filter:a", f"atempo={tempo}", adjusted_audio]
        subprocess.run(cmd_speed, check=True)
        audio_file = adjusted_audio
        total_dur = get_audio_duration(audio_file)

    min_slide = 2.0
    n_slides = 5
    if total_dur <= min_slide * n_slides:
        durations = [total_dur / n_slides] * n_slides
    else:
        weights = [1.0, 1.0, 1.0, 1.0, 1.3]
        total_weight = sum(weights)
        durations = [max(min_slide, total_dur * w / total_weight) for w in weights]
        scale = total_dur / sum(durations)
        durations = [d * scale for d in durations]

    # Fonts
    font_brand = get_eng_font(46)
    font_sub = get_eng_font(24)
    font_title = get_dev_font(34)
    font_h2 = get_dev_font(30)
    font_body = get_dev_font(32)
    font_label = get_dev_font(24)
    
    font_cta_hin = get_dev_font(28)
    font_cta_eng = get_eng_font(28)
    font_wa_eng = get_eng_font(26)
    font_wa_dev = get_dev_font(26)
    font_opt_eng = get_eng_font(32)

    def draw_base(draw_obj):
        draw_obj.rounded_rectangle([45, 50, 1035, 1860], radius=30, fill="#1E293B", outline="#E11D48", width=4)
        draw_obj.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        draw_obj.text((80, 130), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)

    def draw_footer(draw_obj):
        # 1. Green WhatsApp Banner (Safe Zone: Y=1365 to 1475)
        draw_obj.rounded_rectangle([80, 1365, 1000, 1475], radius=20, fill="#15803D", outline="#22C55E", width=2)
        draw_obj.text((110, 1380), "GDS to MTS | Postman | Mail Guard | P.A.", fill="#FEF08A", font=font_wa_eng)
        draw_obj.text((110, 1425), "कोर्स व फ्री मॉक टेस्ट हेतु व्हाट्सएप: 8989971379", fill="#FFFFFF", font=font_wa_dev)

        # 2. Red Follow Banner (Safe Zone: Y=1495 to 1575)
        draw_obj.rounded_rectangle([80, 1495, 1000, 1575], radius=20, fill="#E11D48")
        draw_obj.text((120, 1520), "पूरी तैयारी के लिए फॉलो करें:", fill="#FFFFFF", font=font_cta_hin)
        draw_obj.text((610, 1520), "@POSTAL_WALA", fill="#FFFFFF", font=font_cta_eng)

    sentences = [script_data["sen1"], script_data["sen2"], script_data["sen3"], script_data["sen4"]]
    slide_filenames = []

    for idx, sentence in enumerate(sentences, 1):
        img = Image.new("RGB", (1080, 1920), color="#0F172A")
        d = ImageDraw.Draw(img)
        draw_base(d)

        # Topic Title Box
        d.rounded_rectangle([80, 180, 1000, 315], radius=20, fill="#0F172A", outline="#38BDF8", width=2)
        d.text((110, 195), f"संपूर्ण नियम ({idx}/4):", fill="#38BDF8", font=font_label)
        d.text((110, 235), textwrap.fill(script_data["rule_title"], width=34), fill="#FFFFFF", font=font_title)

        # Explanation Box
        d.rounded_rectangle([80, 335, 1000, 1340], radius=22, fill="#0F172A")
        d.text((110, 360), "विस्तृत व्याख्या:", fill="#FBBF24", font=font_h2)

        d.rounded_rectangle([110, 420, 970, 1310], radius=20, fill="#1E293B", outline="#38BDF8", width=2)
        d.text((135, 450), "मुख्य बिंदु:", fill="#38BDF8", font=font_label)

        wrapped_text = textwrap.fill(sentence, width=24)
        d.text((135, 520), wrapped_text, fill="#F8FAFC", font=font_body)

        draw_footer(d)
        fname = f"slide_{idx}.png"
        img.save(fname)
        slide_filenames.append(fname)

    # Slide 5 (Quiz Slide - No answer revealed)
    img5 = Image.new("RGB", (1080, 1920), color="#0F172A")
    d5 = ImageDraw.Draw(img5)
    draw_base(d5)

    d5.rounded_rectangle([80, 180, 1000, 315], radius=20, fill="#0F172A", outline="#FBBF24", width=2)
    d5.text((110, 195), "परीक्षा क्विज़:", fill="#FBBF24", font=font_label)
    d5.text((110, 235), "सवाल का जवाब दें!", fill="#FFFFFF", font=font_title)

    d5.rounded_rectangle([80, 335, 1000, 1340], radius=22, fill="#0F172A")
    d5.text((110, 360), "सवाल:", fill="#FBBF24", font=font_h2)

    q_wrapped = textwrap.fill(script_data["question"], width=26)
    d5.text((110, 410), q_wrapped, fill="#F8FAFC", font=font_body)

    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    oy = 660
    for idx, opt in enumerate(opts):
        box_bg = "#1E293B"
        border_c = "#38BDF8"
        text_c = "#FFFFFF"

        d5.rounded_rectangle([110, oy, 970, oy + 85], radius=16, fill=box_bg, outline=border_c, width=2)
        
        # A), B), C), D) in English font to eliminate tofu boxes
        opt_badge = f"{chr(65+idx)})"
        d5.text((135, oy + 22), opt_badge, fill="#38BDF8", font=font_opt_eng)
        
        # Option text in Devanagari font
        d5.text((195, oy + 20), textwrap.fill(opt, width=26), fill=text_c, font=font_body)
        oy += 105

    draw_footer(d5)
    img5.save("slide_5.png")
    slide_filenames.append("slide_5.png")

    inputs = ""
    filter_parts = ""
    for i, fname in enumerate(slide_filenames):
        inputs += f"-i {fname} "

    for i, dur in enumerate(durations):
        safe_dur = max(1.0, dur)
        filter_parts += f"[{i}:v]loop=loop=-1:size=1:start=0,trim=duration={safe_dur}[v{i}]; "

    concat_str = "".join([f"[v{i}]" for i in range(len(slide_filenames))])
    filter_complex = f"{filter_parts}{concat_str}concat=n={len(slide_filenames)}:v=1:a=0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p[v]"

    cmd = ["ffmpeg", "-y"]
    cmd.extend(inputs.strip().split())
    cmd.extend([
        "-i", audio_file,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", f"{len(slide_filenames)}:a",
        "-c:v", "libx264",
        "-preset", "medium",
        "-profile:v", "main",
        "-level", "4.0",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-g", "60",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-movflags", "+faststart",
        "-shortest", output_video
    ])
    subprocess.run(cmd, check=True)
    print("✅ Meta-Optimized 1080x1920 Instagram Reel Created.", flush=True)

# --- Proven Resumable Instagram Upload (With 5s Meta Sync) ---
def post_reel_to_instagram_multipart(video_file, caption, max_container_attempts=3):
    access_token = os.getenv("IG_ACCESS_TOKEN")
    user_id = os.getenv("IG_USER_ID")

    if not access_token or not user_id:
        raise ValueError("IG_ACCESS_TOKEN ya IG_USER_ID secrets me missing hai!")

    last_error = None
    for container_attempt in range(1, max_container_attempts + 1):
        print(f"--- Reel upload attempt {container_attempt}/{max_container_attempts} ---", flush=True)
        try:
            video_id = _create_reel_container(video_file, caption, user_id, access_token)
            status = _poll_container_status(video_id, access_token)

            if status == "FINISHED":
                _publish_reel(video_id, user_id, access_token)
                return
            else:
                last_error = f"Container ended with non-FINISHED status: {status}"
                print(f"⚠️ {last_error}. Retrying with a brand-new container...", flush=True)
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ Attempt {container_attempt} failed: {last_error}. Retrying...", flush=True)

        if container_attempt < max_container_attempts:
            time.sleep(20)

    raise RuntimeError(f"All {max_container_attempts} attempts failed. Last error: {last_error}")

def _create_reel_container(video_file, caption, user_id, access_token):
    print("Step 1/2: Creating resumable-upload Reel container...", flush=True)
    init_url = GRAPH_API_BASE + str(user_id).strip() + "/media"
    data = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "access_token": access_token
    }
    r = requests.post(init_url, data=data, timeout=60)

    if r.status_code != 200:
        raise RuntimeError(f"Container init fail hua: {r.text}")

    init_data = r.json()
    video_id = init_data.get("id")

    if not video_id:
        raise RuntimeError(f"Container ID invalid response: {init_data}")

    # Meta Sync Pause: 5 seconds for Meta server registration
    print(f"Container created with ID: {video_id}. Meta sync ke liye 5 sec wait kar rahe hain...", flush=True)
    time.sleep(5)

    print(f"Uploading video bytes to rupload.facebook.com...", flush=True)
    file_size = os.path.getsize(video_file)
    upload_url = RUPLOAD_BASE + str(video_id).strip()
    upload_headers = {
        "Authorization": f"OAuth {access_token}",
        "offset": "0",
        "file_size": str(file_size),
    }

    with open(video_file, "rb") as vf:
        up_r = requests.post(upload_url, headers=upload_headers, data=vf, timeout=600)

    if up_r.status_code != 200:
        raise RuntimeError(f"Video byte upload fail hua: {up_r.text}")

    up_json = up_r.json()
    if not up_json.get("success"):
        raise RuntimeError(f"Video byte upload did not report success: {up_json}")

    print("Step 2/2: Video bytes uploaded successfully. Waiting for Instagram processing...", flush=True)
    return video_id

def _poll_container_status(video_id, access_token, max_checks=40, wait_seconds=15):
    status_url = GRAPH_API_BASE + str(video_id).strip()

    for attempt in range(max_checks):
        time.sleep(wait_seconds)

        try:
            status_res = requests.get(
                status_url,
                params={"fields": "status_code,status", "access_token": access_token},
                timeout=30
            ).json()
        except Exception as e:
            print(f"Polling network warning (will retry): {e}", flush=True)
            continue

        status = status_res.get("status_code")
        print(f"Check {attempt + 1}: Status -> {status}", flush=True)

        if status == "FINISHED":
            return "FINISHED"
        elif status in ["ERROR", "EXPIRED"]:
            print(f"❌ Instagram reported a definitive failure: {status_res}", flush=True)
            return status

    return "TIMEOUT"

def _publish_reel(video_id, user_id, access_token):
    print("Publishing Reel...", flush=True)
    publish_url = GRAPH_API_BASE + str(user_id).strip() + "/media_publish"
    pub_res = requests.post(publish_url, data={"creation_id": video_id, "access_token": access_token}, timeout=30).json()

    if "id" in pub_res:
        print(f"🎉 Reel successfully published on Instagram! Post ID: {pub_res['id']}", flush=True)
    else:
        raise RuntimeError(f"Publish fail hua: {pub_res}")

# --- Execution Entry Point ---
if __name__ == "__main__":
    print("🚀 Postal Wala Multi-Part Clause Automation Starting...", flush=True)

    state = load_progress_state()
    print(f"📋 Current Tracking -> Clause: {state.get('clause_no', 1)}, Part: {state.get('current_part', 1)}", flush=True)

    target_pdf = get_target_pdf()
    pdf_snippet, page_num = get_pdf_context_snippet(target_pdf, state)
    print(f"✅ Extracted reference context from PDF (Page {page_num}).", flush=True)

    script_data = generate_partwise_clause_script(pdf_snippet, state)
    print(f"✅ AI Script Ready: {script_data.get('rule_title')}", flush=True)

    asyncio.run(generate_voice(script_data["voiceover"], AUDIO_OUTPUT))
    print("✅ Voiceover Ready with Clean Audio.", flush=True)

    create_video_ffmpeg(script_data, AUDIO_OUTPUT, OUTPUT_VIDEO)

    post_reel_to_instagram_multipart(OUTPUT_VIDEO, script_data.get("caption", ""))

    advance_progress_state(state, script_data)
