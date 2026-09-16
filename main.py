import os
import glob
import json
import time
import textwrap
import subprocess
import requests
from pypdf import PdfReader
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

STATE_FILE = "progress_state.json"
FONT_PATH = "NotoSansDevanagari-Bold.ttf"

def ensure_hindi_font():
    if not os.path.exists(FONT_PATH):
        print("📥 Downloading Noto Sans Devanagari font...")
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        r = requests.get(url, timeout=30)
        with open(FONT_PATH, "wb") as f:
            f.write(r.content)
        print("✅ Font cached locally.")

def get_font(size):
    if os.path.exists(FONT_PATH):
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()

def get_target_pdf():
    pdf_files = glob.glob("*.pdf") + glob.glob("data/*.pdf")
    if not pdf_files:
        raise FileNotFoundError("Repo me koi PDF nahi mili!")
    for f in pdf_files:
        if "mts" in f.lower():
            return f
    return pdf_files[0]

def get_current_reading_window(pdf_path):
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    
    current_page = 0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                current_page = state.get("last_page", 0)
        except Exception:
            current_page = 0

    if current_page == 0:
        search_terms = ["खंड - 02", "खंड-02", "खंड 02", "खंड 2", "डाकघरों के प्रकार"]
        for idx, page in enumerate(reader.pages):
            txt = page.extract_text() or ""
            if any(term in txt for term in search_terms):
                current_page = idx
                print(f"✅ 'खंड - 02' पेज नंबर {idx + 1} पर मिल गया!")
                break

    end_page = min(current_page + 1, total_pages)
    extracted_text = ""
    for p in range(current_page, end_page):
        t = reader.pages[p].extract_text()
        if t:
            extracted_text += f"\n--- PAGE {p+1} ---\n" + t

    next_page = end_page if end_page < total_pages else 0
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"last_page": next_page}, f)
    except Exception:
        pass

    return extracted_text[:1400], current_page + 1

def generate_clause_script(pdf_content, page_num):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY missing in GitHub Secrets!")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
        "Content-Type": "application/json"
    }

    prompt = f"""
    You are an expert tutor for Postal MTS/Postman exam running Instagram page 'Postal Wala'.
    Teach and test the rule from this departmental section (Around Page {page_num}).

    DURATION & WORD COUNT:
    Total around 95-105 words in spoken Hindi (~45-50 seconds audio).
    STRICT RULE: NO EMOJIS, NO SYMBOLS.

    STRUCTURE:
    1. EXPLANATION (~32 seconds):
       - Direct topic name.
       - Explain the core rule in simple everyday conversational Hindi.
    2. QUIZ (~15 seconds):
       - 1 crisp exam MCQ with 4 options.
       - End line: "सही उत्तर है ऑप्शन [X]! रोज़ाना ऐसी तैयारी के लिए अभी फॉलो करें Postal Wala को!"

    PDF Content:
    {pdf_content}

    Format strictly matching these lines:
    TITLE: [Short Topic Name in Hindi]
    RULE_P1: [Rule point 1 in 8-10 Hindi words]
    RULE_P2: [Rule point 2 in 8-10 Hindi words]
    QUESTION: [1 short exam question in Hindi]
    OPT_A: [Option A text]
    OPT_B: [Option B text]
    OPT_C: [Option C text]
    OPT_D: [Option D text]
    CORRECT: [A/B/C/D]
    VOICEOVER: [Spoken Hindi Script of 95-105 words without emojis]
    CAPTION: [Instagram caption with #PostalWala #MTSExam #IndiaPost #Khand02]
    """

    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": 550
    }
    
    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
    res_json = res.json()

    if res.status_code != 200 or "choices" not in res_json:
        raise RuntimeError(f"Groq API Error: {res_json}")

    raw_text = res_json["choices"][0]["message"]["content"].strip()
    
    data = {
        "rule_title": "डाकघर नियम",
        "rule_p1": "नकद डाक भुगतान बड़े शहरों में न्यूनतम 500 पैकेट पर मिलता है",
        "rule_p2": "छोटे शहरों में यह सुविधा न्यूनतम 250 पैकेट पर उपलब्ध है",
        "question": "बड़े शहरों में नकद डाक भुगतान हेतु कम से कम कितने पैकेट चाहिए?",
        "opt_a": "A) 250 पैकेट",
        "opt_b": "B) 500 पैकेट",
        "opt_c": "C) 1000 पैकेट",
        "opt_d": "D) 100 पैकेट",
        "correct": "B",
        "voiceover": "पोस्टल परीक्षा की तैयारी के लिए यह महत्वपूर्ण नियम ध्यान से समझें! डाक विभाग में नकद में डाक शुल्क भुगतान की विशेष सुविधा मिलती है। बड़े शहरों के मुख्य डाकघरों में इसके लिए एक बार में कम से कम 500 पैकेट और छोटे शहरों में न्यूनतम 250 पैकेट पोस्ट करना अनिवार्य है। अब बताइए, बड़े शहरों में नकद डाक भुगतान हेतु न्यूनतम कितने पैकेट चाहिए? आपके पास हैं 5 सेकंड... इसका सही उत्तर है ऑप्शन B, 500 पैकेट! ऐसी सटीक तैयारी के लिए अभी फॉलो करें Postal Wala को!",
        "caption": "डाक विभाग परीक्षा तैयारी #PostalWala #MTSExam #Khand02"
    }
    
    for line in raw_text.splitlines():
        line_clean = line.strip()
        if line_clean.startswith("TITLE:"):
            data["rule_title"] = line_clean.replace("TITLE:", "").strip()
        elif line_clean.startswith("RULE_P1:"):
            data["rule_p1"] = line_clean.replace("RULE_P1:", "").strip()
        elif line_clean.startswith("RULE_P2:"):
            data["rule_p2"] = line_clean.replace("RULE_P2:", "").strip()
        elif line_clean.startswith("QUESTION:"):
            data["question"] = line_clean.replace("QUESTION:", "").strip()
        elif line_clean.startswith("OPT_A:"):
            data["opt_a"] = "A) " + line_clean.replace("OPT_A:", "").replace("A)", "").strip()
        elif line_clean.startswith("OPT_B:"):
            data["opt_b"] = "B) " + line_clean.replace("OPT_B:", "").replace("B)", "").strip()
        elif line_clean.startswith("OPT_C:"):
            data["opt_c"] = "C) " + line_clean.replace("OPT_C:", "").replace("C)", "").strip()
        elif line_clean.startswith("OPT_D:"):
            data["opt_d"] = "D) " + line_clean.replace("OPT_D:", "").replace("D)", "").strip()
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

def generate_voice(text, filename="voice.mp3"):
    tts = gTTS(text=text, lang="hi", slow=False)
    tts.save(filename)

def get_audio_duration(audio_file):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_file]
    output = subprocess.check_output(cmd).decode().strip()
    return float(output)

def create_video_ffmpeg(script_data, audio_file="voice.mp3", output_video="final_reel.mp4"):
    ensure_hindi_font()
    total_dur = get_audio_duration(audio_file)
    split_time = max(10.0, total_dur - 15.0)

    font_header = get_font(52)
    font_sub = get_font(32)
    font_title = get_font(44)
    font_h2 = get_font(42)
    font_body = get_font(38)
    font_cta = get_font(36)

    # --- SLIDE 1: EXPLANATION ---
    img1 = Image.new("RGB", (1080, 1920), color="#0F172A")
    d1 = ImageDraw.Draw(img1)
    d1.rounded_rectangle([45, 90, 1035, 1830], radius=35, fill="#1E293B", outline="#E11D48", width=6)
    d1.text((90, 140), "POSTAL WALA", fill="#F43F5E", font=font_header)
    d1.text((90, 220), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)

    d1.rounded_rectangle([85, 290, 995, 470], radius=25, fill="#0F172A", outline="#38BDF8", width=3)
    d1.text((115, 315), "आज का नियम:", fill="#38BDF8", font=font_sub)
    d1.text((115, 365), textwrap.fill(script_data["rule_title"], width=28), fill="#FFFFFF", font=font_title)

    d1.rounded_rectangle([85, 520, 995, 1550], radius=30, fill="#0F172A")
    d1.text((120, 560), "नियम को ध्यान से समझें:", fill="#FBBF24", font=font_h2)

    d1.rounded_rectangle([115, 680, 965, 880], radius=20, fill="#1E293B")
    d1.text((140, 700), "1. मुख्य बिंदु:", fill="#38BDF8", font=font_sub)
    d1.text((140, 750), textwrap.fill(script_data["rule_p1"], width=28), fill="#F8FAFC", font=font_body)

    d1.rounded_rectangle([115, 940, 965, 1140], radius=20, fill="#1E293B")
    d1.text((140, 960), "2. मुख्य बिंदु:", fill="#38BDF8", font=font_sub)
    d1.text((140, 1010), textwrap.fill(script_data["rule_p2"], width=28), fill="#F8FAFC", font=font_body)

    d1.rounded_rectangle([85, 1610, 995, 1750], radius=25, fill="#E11D48")
    d1.text((220, 1655), "पूरी तैयारी के लिए फॉलो करें:\n@POSTAL_WALA", fill="#FFFFFF", font=font_cta, align="center")
    img1.save("slide1.png")

    # --- SLIDE 2: QUIZ & ANSWER ---
    img2 = Image.new("RGB", (1080, 1920), color="#0F172A")
    d2 = ImageDraw.Draw(img2)
    d2.rounded_rectangle([45, 90, 1035, 1830], radius=35, fill="#1E293B", outline="#E11D48", width=6)
    d2.text((90, 140), "POSTAL WALA", fill="#F43F5E", font=font_header)
    d2.text((90, 220), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)

    d2.rounded_rectangle([85, 290, 995, 470], radius=25, fill="#0F172A", outline="#FBBF24", width=3)
    d2.text((115, 315), "परीक्षा क्विज़:", fill="#FBBF24", font=font_sub)
    d2.text((115, 365), "सवाल का जवाब सोचें!", fill="#FFFFFF", font=font_title)

    d2.rounded_rectangle([85, 520, 995, 1550], radius=30, fill="#0F172A")
    d2.text((120, 560), "सवाल:", fill="#FBBF24", font=font_h2)
    d2.text((120, 640), textwrap.fill(script_data["question"], width=28), fill="#F8FAFC", font=font_body)

    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    correct = script_data.get("correct", "B")
    oy = 960
    for idx, opt in enumerate(opts):
        is_ans = (correct == chr(65 + idx))
        box_bg = "#064E3B" if is_ans else "#1E293B"
        border_c = "#10B981" if is_ans else "#38BDF8"
        text_c = "#34D399" if is_ans else "#FFFFFF"

        d2.rounded_rectangle([115, oy, 965, oy + 95], radius=18, fill=box_bg, outline=border_c, width=2)
        d2.text((150, oy + 25), opt, fill=text_c, font=font_body)
        oy += 125

    d2.rounded_rectangle([85, 1610, 995, 1750], radius=25, fill="#E11D48")
    d2.text((220, 1655), "पूरी तैयारी के लिए फॉलो करें:\n@POSTAL_WALA", fill="#FFFFFF", font=font_cta, align="center")
    img2.save("slide2.png")

    filter_complex = (
        f"[0:v]loop=loop=-1:size=1:start=0,trim=duration={split_time}[v0]; "
        f"[1:v]loop=loop=-1:size=1:start=0,trim=duration={total_dur - split_time}[v1]; "
        f"[v0][v1]concat=n=2:v=1:a=0,format=yuv420p[v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", "slide1.png",
        "-i", "slide2.png",
        "-i", audio_file,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "2:a",
        "-c:v", "libx264",
        "-profile:v", "main",
        "-level:v", "4.0",
        "-r", "30",
        "-g", "60",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-movflags", "+faststart",
        "-shortest", output_video
    ]
    subprocess.run(cmd, check=True)
    print("✅ 2-Slide Visual Reel Created Cleanly.")

def upload_to_instagram_direct(video_path, caption):
    if not IG_ACCESS_TOKEN or not IG_USER_ID:
        raise ValueError("CRITICAL: IG_ACCESS_TOKEN ya IG_USER_ID missing hai!")

    file_size = os.path.getsize(video_path)
    print(f"📦 Video size: {file_size / (1024*1024):.2f} MB")

    # Step 1: Initialize Resumable Upload
    print("🚀 Initializing Instagram Resumable Upload Session...")
    init_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    init_payload = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN
    }
    r_init = requests.post(init_url, data=init_payload)
    init_data = r_init.json()

    video_id = init_data.get("id")
    upload_url = init_data.get("uri")

    if not video_id or not upload_url:
        raise RuntimeError(f"Session initialization failed: {init_data}")

    print(f"✅ Container ID: {video_id}")
    print(f"📤 Uploading bytes directly to Meta: {upload_url}")

    # Step 2: Meta Official Binary Upload (Exact headers specification)
    headers = {
        "Authorization": f"OAuth {IG_ACCESS_TOKEN}",
        "offset": "0",
        "file_size": str(file_size)
    }

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    r_upload = requests.post(upload_url, headers=headers, data=video_bytes, timeout=180)

    if r_upload.status_code not in [200, 201]:
        raise RuntimeError(f"Meta byte upload failed ({r_upload.status_code}): {r_upload.text}")

    print("✅ Video binary uploaded directly to Meta servers.")

    # Step 3: Wait for transcoding status
    status_url = f"https://graph.facebook.com/v19.0/{video_id}?fields=status_code&access_token={IG_ACCESS_TOKEN}"

    for attempt in range(1, 40):
        time.sleep(8)
        status_res = requests.get(status_url).json()
        code = status_res.get("status_code")
        print(f"🔄 Check {attempt}: {code}")

        if code == "FINISHED":
            print("✅ Transcoding FINISHED!")
            break
        elif code in ["ERROR", "EXPIRED"]:
            raise RuntimeError(f"Instagram rejected video: {status_res}")
    else:
        print("⚠️ Polling timeout, attempting to publish...")

    # Step 4: Live Publish
    pub_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    pub_res = requests.post(pub_url, data={"creation_id": video_id, "access_token": IG_ACCESS_TOKEN})
    pub_json = pub_res.json()

    if "id" in pub_json:
        print(f"🎉 SUCCESS! Reel Live on Instagram! Post ID: {pub_json['id']}")
    else:
        raise RuntimeError(f"Publish Failed: {pub_json}")

if __name__ == "__main__":
    print("🚀 Postal Wala Automation Starting...")
    
    target_pdf = get_target_pdf()
    pdf_content, page_num = get_current_reading_window(target_pdf)
    print(f"✅ Read Page {page_num}.")

    script_data = generate_clause_script(pdf_content, page_num)
    print("✅ AI Script Ready.")

    generate_voice(script_data["voiceover"], "voice.mp3")
    print("✅ Voiceover Ready.")

    create_video_ffmpeg(script_data, "voice.mp3", "final_reel.mp4")

    upload_to_instagram_direct("final_reel.mp4", script_data.get("caption", ""))
