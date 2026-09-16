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
        font_url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        try:
            r = requests.get(font_url, timeout=30)
            if r.status_code == 200:
                with open(FONT_PATH, "wb") as f:
                    f.write(r.content)
        except Exception as e:
            print(f"Font download warning: {e}")

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

    return extracted_text[:1200], current_page + 1

def generate_clause_script(pdf_content, page_num):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY missing in GitHub Secrets!")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
        "Content-Type": "application/json"
    }

    target_model = "qwen/qwen3.8-27b"
    print(f"🚀 Using Groq model: {target_model}")

    prompt = f"""
    You are an expert postal exam teacher for 'Postal Wala' Instagram page.
    Create a crisp reel script based on this postal manual section (Around Page {page_num}).

    GUIDELINES:
    1. Language: Simple, energetic spoken Hindi (शुद्ध बोलचाल की सरल हिंदी).
    2. Voiceover: Around 85-95 words explaining the core rule + 1 MCQ + Outro: "आगे की तैयारी के लिए अभी फॉलो करें Postal Wala को!"
    3. Points: Give 3 short bullet points summarizing what is being taught (to display on screen).

    PDF Content:
    {pdf_content}

    Output format strictly matching these lines:
    TITLE: [Short topic name in Hindi]
    POINT1: [Key takeaway 1 in 6-8 Hindi words]
    POINT2: [Key takeaway 2 in 6-8 Hindi words]
    POINT3: [Key takeaway 3 in 6-8 Hindi words]
    VOICEOVER: [Complete spoken Hindi script]
    QUESTION: [1 short MCQ question in Hindi]
    OPT_A: [Option A]
    OPT_B: [Option B]
    OPT_C: [Option C]
    OPT_D: [Option D]
    CAPTION: [Instagram caption with #PostalWala #MTSExam #IndiaPost #Khand02]
    """

    payload = {
        "model": target_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": 400
    }
    
    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
    res_json = res.json()

    if res.status_code != 200 or "choices" not in res_json:
        raise RuntimeError(f"Groq API Error: {res_json}")

    raw_text = res_json["choices"][0]["message"]["content"].strip()
    
    data = {
        "rule_title": "डाकघर नियम",
        "point1": "कामकाज के निश्चित घंटे तय होते हैं",
        "point2": "शनिवार को काम केवल 3 घंटे होता है",
        "point3": "दोपहर 1 बजे काम बंद कर दिया जाता है",
        "voiceover": "",
        "question": "शनिवार को डाकघर में काउंटर काम कितने घंटे होता है?",
        "opt_a": "A) 2 घंटे",
        "opt_b": "B) 3 घंटे",
        "opt_c": "C) 5 घंटे",
        "opt_d": "D) पूरा दिन",
        "caption": "डाक विभाग परीक्षा तैयारी #PostalWala #MTSExam"
    }
    
    for line in raw_text.splitlines():
        line_clean = line.strip()
        if line_clean.startswith("TITLE:"):
            data["rule_title"] = line_clean.replace("TITLE:", "").strip()
        elif line_clean.startswith("POINT1:"):
            data["point1"] = line_clean.replace("POINT1:", "").strip()
        elif line_clean.startswith("POINT2:"):
            data["point2"] = line_clean.replace("POINT2:", "").strip()
        elif line_clean.startswith("POINT3:"):
            data["point3"] = line_clean.replace("POINT3:", "").strip()
        elif line_clean.startswith("VOICEOVER:"):
            data["voiceover"] = line_clean.replace("VOICEOVER:", "").strip()
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
        elif line_clean.startswith("CAPTION:"):
            data["caption"] = line_clean.replace("CAPTION:", "").strip()

    if not data["voiceover"]:
        data["voiceover"] = raw_text[:250]

    outro_line = " आगे की तैयारी और महत्वपूर्ण प्रश्नों के लिए अभी फॉलो करें Postal Wala को!"
    if "Postal Wala" not in data["voiceover"]:
        data["voiceover"] += outro_line

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
    split_time = max(5.0, total_dur - 16.0)

    font_brand = get_font(52)
    font_badge = get_font(34)
    font_title = get_font(46)
    font_h2 = get_font(40)
    font_body = get_font(38)
    font_cta = get_font(36)

    # --- SLIDE 1: RULE EXPLANATION ---
    img1 = Image.new("RGB", (1080, 1920), color="#0B1120")
    d1 = ImageDraw.Draw(img1)
    d1.rounded_rectangle([45, 100, 1035, 1820], radius=40, fill="#131D31", outline="#E11D48", width=6)
    d1.text((90, 150), "POSTAL WALA", fill="#F43F5E", font=font_brand)
    d1.text((90, 230), "@POSTAL_WALA", fill="#94A3B8", font=font_badge)

    d1.rounded_rectangle([85, 310, 995, 480], radius=25, fill="#1E293B", outline="#38BDF8", width=3)
    d1.text((120, 335), "📌 आज का नियम:", fill="#38BDF8", font=font_badge)
    wrapped_title = textwrap.fill(script_data["rule_title"], width=28)
    d1.text((120, 385), wrapped_title, fill="#FFFFFF", font=font_title)

    d1.rounded_rectangle([85, 520, 995, 1550], radius=30, fill="#0F172A", outline="#E2E8F0", width=2)
    d1.text((120, 560), "💡 मुख्य बातें समझें:", fill="#FBBF24", font=font_h2)

    points = [script_data["point1"], script_data["point2"], script_data["point3"]]
    py = 680
    for idx, pt in enumerate(points, 1):
        d1.rounded_rectangle([115, py, 965, py + 180], radius=20, fill="#1E293B")
        d1.text((140, py + 20), f"👉 नियम {idx}:", fill="#38BDF8", font=font_badge)
        wrapped_pt = textwrap.fill(pt, width=28)
        d1.text((140, py + 70), wrapped_pt, fill="#F8FAFC", font=font_body)
        py += 240

    d1.rounded_rectangle([85, 1610, 995, 1750], radius=25, fill="#E11D48")
    d1.text((220, 1655), "पूरी तैयारी के लिए फॉलो करें\n👉 @POSTAL_WALA", fill="#FFFFFF", font=font_cta, align="center")
    img1.save("slide1.png")

    # --- SLIDE 2: QUIZ & OPTIONS ---
    img2 = Image.new("RGB", (1080, 1920), color="#0B1120")
    d2 = ImageDraw.Draw(img2)
    d2.rounded_rectangle([45, 100, 1035, 1820], radius=40, fill="#131D31", outline="#E11D48", width=6)
    d2.text((90, 150), "POSTAL WALA", fill="#F43F5E", font=font_brand)
    d2.text((90, 230), "@POSTAL_WALA", fill="#94A3B8", font=font_badge)

    d2.rounded_rectangle([85, 310, 995, 480], radius=25, fill="#1E293B", outline="#FBBF24", width=3)
    d2.text((120, 335), "🎯 परीक्षा क्विज़:", fill="#FBBF24", font=font_badge)
    d2.text((120, 385), "सवाल का जवाब कमेंट में दें!", fill="#FFFFFF", font=font_title)

    d2.rounded_rectangle([85, 520, 995, 1550], radius=30, fill="#0F172A", outline="#38BDF8", width=2)
    d2.text((120, 560), "सवाल:", fill="#FBBF24", font=font_h2)
    wrapped_q = textwrap.fill(script_data["question"], width=28)
    d2.text((120, 640), wrapped_q, fill="#F8FAFC", font=font_body)

    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    oy = 960
    for opt in opts:
        d2.rounded_rectangle([115, oy, 965, oy + 95], radius=18, fill="#1E293B", outline="#38BDF8", width=1)
        d2.text((150, oy + 25), opt, fill="#FFFFFF", font=font_body)
        oy += 125

    d2.text((130, 1480), "कमेंट में अपना उत्तर बताएं 👇", fill="#F43F5E", font=font_badge)
    d2.rounded_rectangle([85, 1610, 995, 1750], radius=25, fill="#E11D48")
    d2.text((220, 1655), "पूरी तैयारी के लिए फॉलो करें\n👉 @POSTAL_WALA", fill="#FFFFFF", font=font_cta, align="center")
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
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print("✅ 2-Slide Visual Reel Created Successfully.")

def upload_to_instagram_direct(video_path, caption):
    if not IG_ACCESS_TOKEN or not IG_USER_ID:
        raise ValueError("CRITICAL: IG_ACCESS_TOKEN ya IG_USER_ID missing hai!")

    file_size = os.path.getsize(video_path)
    print(f"📦 Video size: {file_size / (1024*1024):.2f} MB")

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

    with open(video_path, "rb") as f:
        video_data = f.read()

    headers = {
        "Authorization": f"OAuth {IG_ACCESS_TOKEN}",
        "Offset": "0",
        "Content-Length": str(file_size),
        "X-Entity-Length": str(file_size),
        "X-Entity-Name": "final_reel.mp4",
        "X-Entity-Type": "video/mp4"
    }

    s = requests.Session()
    req = requests.Request("POST", upload_url, data=video_data, headers=headers)
    prepped = s.prepare_request(req)

    if "Transfer-Encoding" in prepped.headers:
        del prepped.headers["Transfer-Encoding"]

    r_upload = s.send(prepped, timeout=180)

    if r_upload.status_code not in [200, 201]:
        raise RuntimeError(f"Direct byte upload failed ({r_upload.status_code}): {r_upload.text}")

    print("✅ Video uploaded directly to Instagram servers.")

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
    print("✅ Natural Audio Voiceover Ready.")

    create_video_ffmpeg(script_data, "voice.mp3", "final_reel.mp4")

    upload_to_instagram_direct("final_reel.mp4", script_data.get("caption", ""))
