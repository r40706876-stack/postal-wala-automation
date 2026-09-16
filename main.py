import os
import glob
import json
import time
import subprocess
import requests
from pypdf import PdfReader
from gtts import gTTS

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

STATE_FILE = "progress_state.json"
FONTS_DIR = os.path.abspath("custom_fonts")
FONT_FILE = os.path.join(FONTS_DIR, "NotoSansDevanagari-Bold.ttf")

def ensure_hindi_font():
    os.makedirs(FONTS_DIR, exist_ok=True)
    if not os.path.exists(FONT_FILE):
        print("📥 Downloading Noto Sans Devanagari font...")
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        r = requests.get(url, timeout=30)
        with open(FONT_FILE, "wb") as f:
            f.write(r.content)
        print("✅ Font cached in dedicated folder.")

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

    STRUCTURE:
    1. EXPLANATION (~32 seconds):
       - Direct hook.
       - Explain the core rule in simple everyday conversational Hindi.
    2. QUIZ (~15 seconds):
       - 1 crisp exam MCQ with 4 options.
       - End line: "सही उत्तर है ऑप्शन [X]! रोज़ाना ऐसी तैयारी के लिए अभी फॉलो करें Postal Wala को!"

    PDF Content:
    {pdf_content}

    Format strictly matching these lines:
    TITLE: [Short Topic Name in Hindi]
    RULE_P1: [Rule point 1 in 8-10 words]
    RULE_P2: [Rule point 2 in 8-10 words]
    QUESTION: [1 short exam question in Hindi]
    OPT_A: [Option A text]
    OPT_B: [Option B text]
    OPT_C: [Option C text]
    OPT_D: [Option D text]
    CORRECT: [A/B/C/D]
    VOICEOVER: [Spoken Hindi Script of 95-105 words]
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

    return data

def generate_voice(text, filename="voice.mp3"):
    tts = gTTS(text=text, lang="hi", slow=False)
    tts.save(filename)

def get_audio_duration(audio_file):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_file]
    output = subprocess.check_output(cmd).decode().strip()
    return float(output)

def generate_ass_subtitles(script_data, total_duration, output_ass="subs.ass"):
    quiz_start = max(15.0, total_duration - 15.0)
    reveal_time = total_duration - 5.0
    correct_opt = script_data.get("correct", "B")
    green_c = "\\c&H00FF00&\\b1"

    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Header,Noto Sans Devanagari,50,&H00481DE1,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,3,0,8,60,60,150,1
Style: Topic,Noto Sans Devanagari,40,&H00F8BD38,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,8,60,60,250,1
Style: BodyHead,Noto Sans Devanagari,44,&H00FBBF24,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,3,0,5,80,80,680,1
Style: BodyText,Noto Sans Devanagari,38,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,5,90,90,520,1
Style: Opt,Noto Sans Devanagari,38,&H00F8FAFC,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,5,80,80,300,1
Style: Footer,Noto Sans Devanagari,36,&H00FFFFFF,&H000000FF,&H00E11D48,&H00000000,1,0,0,0,100,100,0,0,1,3,0,2,60,60,140,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:{total_duration:05.2f},Header,,0,0,0,,POSTAL WALA\\N{{\\fs32\\c&H94A3B8&}}@POSTAL_WALA
Dialogue: 0,0:00:00.00,0:00:{total_duration:05.2f},Footer,,0,0,0,,पूरी तैयारी के लिए FOLLOW करें 👉 @POSTAL_WALA

Dialogue: 0,0:00:00.00,0:00:{quiz_start:05.2f},Topic,,0,0,0,,📌 आज का नियम: {script_data['rule_title']}
Dialogue: 0,0:00:00.00,0:00:{quiz_start:05.2f},BodyHead,,0,0,680,,💡 नियम को ध्यान से समझें:
Dialogue: 0,0:00:00.00,0:00:{quiz_start:05.2f},BodyText,,0,0,500,,👉 1. {script_data['rule_p1']}
Dialogue: 0,0:00:00.00,0:00:{quiz_start:05.2f},BodyText,,0,0,320,,👉 2. {script_data['rule_p2']}

Dialogue: 0,0:00:{quiz_start:05.2f},0:00:{total_duration:05.2f},Topic,,0,0,0,,🎯 परीक्षा क्विज़ (Quiz Time)
Dialogue: 0,0:00:{quiz_start:05.2f},0:00:{total_duration:05.2f},BodyHead,,0,0,680,,{script_data['question']}

Dialogue: 0,0:00:{quiz_start:05.2f},0:00:{reveal_time:05.2f},Opt,,0,0,450,,{script_data['opt_a']}
Dialogue: 0,0:00:{quiz_start:05.2f},0:00:{reveal_time:05.2f},Opt,,0,0,350,,{script_data['opt_b']}
Dialogue: 0,0:00:{quiz_start:05.2f},0:00:{reveal_time:05.2f},Opt,,0,0,250,,{script_data['opt_c']}
Dialogue: 0,0:00:{quiz_start:05.2f},0:00:{reveal_time:05.2f},Opt,,0,0,150,,{script_data['opt_d']}

Dialogue: 0,0:00:{reveal_time:05.2f},0:00:{total_duration:05.2f},Opt,,0,0,450,,{{{green_c if correct_opt=='A' else ''}}}{script_data['opt_a']}
Dialogue: 0,0:00:{reveal_time:05.2f},0:00:{total_duration:05.2f},Opt,,0,0,350,,{{{green_c if correct_opt=='B' else ''}}}{script_data['opt_b']}
Dialogue: 0,0:00:{reveal_time:05.2f},0:00:{total_duration:05.2f},Opt,,0,0,250,,{{{green_c if correct_opt=='C' else ''}}}{script_data['opt_c']}
Dialogue: 0,0:00:{reveal_time:05.2f},0:00:{total_duration:05.2f},Opt,,0,0,150,,{{{green_c if correct_opt=='D' else ''}}}{script_data['opt_d']}
"""
    with open(output_ass, "w", encoding="utf-8") as f:
        f.write(ass_content)

def create_video_ffmpeg(script_data, audio_file="voice.mp3", output_video="final_reel.mp4"):
    ensure_hindi_font()
    total_dur = get_audio_duration(audio_file)
    generate_ass_subtitles(script_data, total_dur, "subs.ass")

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=#0F172A:s=1080x1920:d={total_dur}",
        "-i", audio_file,
        "-vf", f"subtitles=subs.ass:fontsdir={FONTS_DIR}",
        "-c:v", "libx264",
        "-preset", "veryfast",
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
    print("✅ Video generated cleanly with proper font isolation.")

def upload_to_instagram_direct(video_path, caption):
    if not IG_ACCESS_TOKEN or not IG_USER_ID:
        raise ValueError("CRITICAL: IG_ACCESS_TOKEN ya IG_USER_ID missing hai!")

    file_size = os.path.getsize(video_path)
    print(f"📦 Video size: {file_size / (1024*1024):.2f} MB")

    # Step 1: Session Init
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
        raise RuntimeError(f"Session failed: {init_data}")

    print(f"✅ Container ID: {video_id}")
    print("📤 Uploading video bytes directly to Instagram...")

    # Step 2: Meta standard resumable upload
    headers = {
        "Authorization": f"OAuth {IG_ACCESS_TOKEN}",
        "file_offset": "0"
    }

    with open(video_path, "rb") as f:
        r_upload = requests.post(upload_url, headers=headers, files={"video_file": f}, timeout=180)

    if r_upload.status_code not in [200, 201]:
        raise RuntimeError(f"Direct byte upload failed ({r_upload.status_code}): {r_upload.text}")

    print("✅ Video uploaded directly to Instagram servers.")

    # Step 3: Polling for transcode status
    status_url = f"https://graph.facebook.com/v19.0/{video_id}?fields=status_code&access_token={IG_ACCESS_TOKEN}"

    for attempt in range(1, 35):
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
        print("⚠️ Polling timeout, trying to publish...")

    # Step 4: Publish
    pub_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    pub_res = requests.post(pub_url, data={"creation_id": video_id, "access_token": IG_ACCESS_TOKEN})
    pub_json = pub_res.json()

    if "id" in pub_json:
        print(f"🎉 SUCCESS! Reel Live on Instagram! Post ID: {pub_json['id']}")
    else:
        raise RuntimeError(f"Publish Failed: {pub_json}")

if __name__ == "__main__":
    print("🚀 Postal Wala Automation Starting (50s Concept + Quiz)...")
    
    target_pdf = get_target_pdf()
    pdf_content, page_num = get_current_reading_window(target_pdf)
    print(f"✅ Read Page {page_num}.")

    script_data = generate_clause_script(pdf_content, page_num)
    print("✅ AI Script Ready.")

    generate_voice(script_data["voiceover"], "voice.mp3")
    print("✅ Voiceover Ready.")

    create_video_ffmpeg(script_data, "voice.mp3", "final_reel.mp4")

    upload_to_instagram_direct("final_reel.mp4", script_data.get("caption", ""))
