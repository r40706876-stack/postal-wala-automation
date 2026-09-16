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
        print("📥 Downloading Noto Sans Devanagari Font...")
        font_url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        try:
            r = requests.get(font_url, timeout=30)
            if r.status_code == 200:
                with open(FONT_PATH, "wb") as f:
                    f.write(r.content)
                print("✅ Font downloaded successfully.")
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
    You are an energetic tutor for Postal MTS/Postman exam running Instagram page 'Postal Wala'.
    Teach the next specific rule/clause from this departmental PDF section (Around Page {page_num}).

    REEL GUIDELINES:
    1. Tone: Fast-paced, engaging, sharp, conversational Hindi (बोलचाल की सरल व जोश भरी हिंदी).
    2. Word Count: 85 to 110 words total.
    3. Mandatory Structure:
       - Hook: Rule/Topic name clearly mention karo.
       - Explanation: Rule ko practical example se 2-3 short lines me samjhao.
       - Quiz: End me 1 MCQ pucho aur bolo comment me answer de.
       - Outro (COMPULSORY): Last line must strictly be: "इससे आगे की जानकारी और परीक्षा से जुड़े महत्वपूर्ण प्रश्नों के लिए अभी फॉलो करें Postal Wala को!"

    PDF Content:
    {pdf_content}

    Output format strictly matching these lines:
    TITLE: [Short Topic Name in Hindi]
    VOICEOVER: [Spoken Hindi explanation with quiz and compulsory Postal Wala follow outro line]
    QUESTION: [1 Crisp MCQ Question in Hindi]
    OPTIONS: [A) ... B) ... C) ... D) ...]
    CAPTION: [Instagram Caption with Topic, Question, Options, and hashtags #PostalWala #MTSExam #IndiaPost #Khand02]
    """

    payload = {
        "model": target_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": 350
    }
    
    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
    res_json = res.json()

    if res.status_code != 200 or "choices" not in res_json:
        raise RuntimeError(f"Groq API Error: {res_json}")

    raw_text = res_json["choices"][0]["message"]["content"].strip()
    
    data = {
        "rule_title": "डाकघर नियम",
        "voiceover": "",
        "question": "आज का सवाल",
        "options": "A) HO\nB) SO\nC) BO\nD) इनमें से कोई नहीं",
        "caption": "डाक विभाग परीक्षा तैयारी #PostalWala #MTSExam"
    }
    
    current_key = None
    for line in raw_text.splitlines():
        line_clean = line.strip()
        if line_clean.startswith("TITLE:"):
            data["rule_title"] = line_clean.replace("TITLE:", "").strip()
            current_key = "rule_title"
        elif line_clean.startswith("VOICEOVER:"):
            data["voiceover"] = line_clean.replace("VOICEOVER:", "").strip()
            current_key = "voiceover"
        elif line_clean.startswith("QUESTION:"):
            data["question"] = line_clean.replace("QUESTION:", "").strip()
            current_key = "question"
        elif line_clean.startswith("OPTIONS:"):
            data["options"] = line_clean.replace("OPTIONS:", "").strip()
            current_key = "options"
        elif line_clean.startswith("CAPTION:"):
            data["caption"] = line_clean.replace("CAPTION:", "").strip()
            current_key = "caption"
        elif current_key and line_clean:
            data[current_key] += " " + line_clean

    outro_line = " इससे आगे की जानकारी और परीक्षा से जुड़े महत्वपूर्ण प्रश्नों के लिए अभी फॉलो करें Postal Wala को!"
    if "Postal Wala" not in data["voiceover"]:
        data["voiceover"] += outro_line

    return data

def generate_voice(text, filename="raw_voice.mp3"):
    tts = gTTS(text=text, lang="hi", slow=False)
    tts.save(filename)

def create_video_ffmpeg(title, question, options, raw_audio="raw_voice.mp3", output_video="final_reel.mp4"):
    ensure_hindi_font()

    img = Image.new("RGB", (1080, 1920), color="#0B1120")
    draw = ImageDraw.Draw(img)

    font_brand = get_font(52)
    font_badge = get_font(34)
    font_title = get_font(42)
    font_q_head = get_font(40)
    font_q_body = get_font(36)
    font_opts = get_font(34)
    font_cta = get_font(34)

    # Outer Neon Border
    draw.rounded_rectangle([45, 100, 1035, 1820], radius=40, fill="#131D31", outline="#E11D48", width=5)

    # Header
    draw.text((90, 145), "POSTAL WALA", fill="#F43F5E", font=font_brand)
    draw.text((90, 220), "@POSTAL_WALA", fill="#94A3B8", font=font_badge)

    # Topic Card
    draw.rounded_rectangle([85, 290, 995, 470], radius=25, fill="#1E293B", outline="#38BDF8", width=2)
    draw.text((115, 315), "टॉपिक / नियम:", fill="#38BDF8", font=font_badge)
    wrapped_title = textwrap.fill(title, width=30)
    draw.text((115, 365), wrapped_title, fill="#FFFFFF", font=font_title)

    # Quiz Card
    draw.rounded_rectangle([85, 510, 995, 1550], radius=30, fill="#0F172A", outline="#E2E8F0", width=2)
    draw.text((120, 545), "🎯 आज का सवाल (Quiz):", fill="#FBBF24", font=font_q_head)

    # Question Text
    wrapped_q = textwrap.fill(question, width=28)
    draw.text((120, 625), wrapped_q, fill="#F8FAFC", font=font_q_body)

    # Options Display
    opts_clean = options.replace("B)", "\nB)").replace("C)", "\nC)").replace("D)", "\nD)")
    opt_y = 960
    for line in opts_clean.split("\n"):
        line_s = line.strip()
        if line_s:
            draw.rounded_rectangle([115, opt_y - 10, 965, opt_y + 65], radius=15, fill="#1E293B")
            draw.text((140, opt_y), line_s, fill="#38BDF8", font=font_opts)
            opt_y += 95

    # Comment Prompt Inside Card
    draw.text((130, 1460), "अपना उत्तर कमेंट बॉक्स में लिखें 👇", fill="#F43F5E", font=font_cta)

    # Bottom Banner
    draw.rounded_rectangle([85, 1600, 995, 1750], radius=25, fill="#E11D48")
    cta_text = "आगे की तैयारी के लिए FOLLOW करें\n👉 @POSTAL_WALA"
    draw.text((170, 1630), cta_text, fill="#FFFFFF", font=font_cta, align="center")

    frame_path = "frame.png"
    img.save(frame_path)

    # atempo=1.22 boosts audio pace cleanly
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", frame_path,
        "-i", raw_audio,
        "-filter:a", "atempo=1.22",
        "-c:v", "libx264",
        "-profile:v", "main",
        "-level:v", "4.0",
        "-r", "30",
        "-g", "60",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-movflags", "+faststart",
        "-shortest", output_video
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print("✅ High-speed, energetic Reel created with clean Hindi fonts.")

def upload_to_instagram_direct(video_path, caption):
    if not IG_ACCESS_TOKEN or not IG_USER_ID:
        raise ValueError("CRITICAL: IG_ACCESS_TOKEN ya IG_USER_ID missing hai!")

    file_size = os.path.getsize(video_path)
    print(f"📦 Video file size: {file_size / (1024*1024):.2f} MB")

    # Step 1: Session Init
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
        raise RuntimeError(f"Session failed: {init_data}")

    print(f"✅ Container ID: {video_id}")
    print("📤 Uploading video bytes directly to Instagram...")

    # Step 2: Meta Binary Stream with exact headers
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

    # Step 3: Wait for transcode
    print("⏳ Processing on Instagram servers...")
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

    # Step 4: Publish Reel
    print("🚀 Publishing Reel now...")
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

    generate_voice(script_data["voiceover"], "raw_voice.mp3")
    print("✅ Audio Voiceover Ready.")

    create_video_ffmpeg(
        script_data.get("rule_title", "Postal Manual"),
        script_data.get("question", ""),
        script_data.get("options", ""),
        "raw_voice.mp3",
        "final_reel.mp4"
    )

    upload_to_instagram_direct("final_reel.mp4", script_data.get("caption", ""))
