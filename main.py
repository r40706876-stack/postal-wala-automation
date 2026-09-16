import os
import glob
import json
import time
import subprocess
import requests
from pypdf import PdfReader
from gtts import gTTS
from PIL import Image, ImageDraw

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

STATE_FILE = "progress_state.json"

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
    with open(STATE_FILE, "w") as f:
        json.dump({"last_page": next_page}, f)

    return extracted_text[:3000], current_page + 1

def generate_clause_script(pdf_content, page_num):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY missing in GitHub Secrets!")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
        "Content-Type": "application/json"
    }

    prompt = f"""
    You are an expert tutor for Postal MTS/Postman exam running Instagram page 'Postal Wala'.
    Teach the next specific rule/clause from this departmental PDF section (Around Page {page_num}).

    REEL GUIDELINES:
    1. Duration: 60 to 80 SECONDS of spoken audio (around 160-190 words in spoken Hindi).
    2. Language: Super simple, everyday conversational Hindi (बोलचाल की बिल्कुल सरल देसी हिंदी).
    3. Step-by-step Structure:
       - Hook: Rule/Topic name clearly mention karo.
       - Detailed Explanation: Rule ko daily life practical example se samjhao.
       - Magic Question (Quiz): End me 1 exam-style MCQ pucho aur bolo comments me answer dene ko.

    PDF Content:
    {pdf_content}

    Return ONLY raw valid JSON (no markdown ticks, no backticks, no codeblocks):
    {{
        "rule_title": "Topic / Clause Name",
        "voiceover": "Detailed conversational Hindi voiceover of around 160-190 words covering explanation and quiz question clearly.",
        "question": "Question text",
        "options": "A) ... B) ... C) ... D) ...",
        "caption": "Instagram Caption with Topic, Easy Explanation, MCQ Question, Options, and hashtags #PostalWala #MTSExam #IndiaPost #Khand02"
    }}
    """

    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6
    }
    
    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
    res_json = res.json()

    if res.status_code != 200 or "choices" not in res_json:
        raise RuntimeError(f"Groq API Error ({res.status_code}): {res_json}")

    raw = res_json["choices"][0]["message"]["content"].strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)

def generate_voice(text, filename="voice.mp3"):
    tts = gTTS(text=text, lang="hi", slow=False)
    tts.save(filename)

def create_video_ffmpeg(title, question, options, audio_file="voice.mp3", output_video="final_reel.mp4"):
    img = Image.new("RGB", (1080, 1920), color="#0F172A")
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([60, 160, 1020, 1760], radius=40, fill="#1E293B", outline="#E11D48", width=6)
    draw.text((120, 220), "POSTAL WALA", fill="#F43F5E")
    draw.text((120, 320), f"Topic: {title[:40]}", fill="#FFFFFF")
    draw.text((120, 550), "RULE BREAKDOWN & QUIZ", fill="#38BDF8")

    draw.rounded_rectangle([100, 720, 980, 1520], radius=30, fill="#0F172A")
    draw.text((130, 780), "सवाल (Comment Your Answer):", fill="#FBBF24")
    draw.text((130, 880), f"{question[:120]}...", fill="#FFFFFF")
    draw.text((130, 1100), f"{options[:160]}", fill="#94A3B8")

    frame_path = "frame.png"
    img.save(frame_path)

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", frame_path,
        "-i", audio_file,
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
    print("✅ Video encoded strictly for Instagram Reels.")

def upload_to_instagram_direct(video_path, caption):
    if not IG_ACCESS_TOKEN or not IG_USER_ID:
        raise ValueError("CRITICAL: IG_ACCESS_TOKEN ya IG_USER_ID missing hai!")

    file_size = os.path.getsize(video_path)
    print(f"📦 Video file size: {file_size / (1024*1024):.2f} MB")

    # Step 1: Session init
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

    # Step 2: Meta Resumable Protocol (Exact required headers)
    headers = {
        "Authorization": f"OAuth {IG_ACCESS_TOKEN}",
        "Offset": "0",
        "Content-Type": "application/octet-stream",
        "Content-Length": str(file_size)
    }
    with open(video_path, "rb") as f:
        video_data = f.read()

    r_upload = requests.post(upload_url, headers=headers, data=video_data, timeout=180)

    if r_upload.status_code not in [200, 201]:
        raise RuntimeError(f"Direct byte upload failed ({r_upload.status_code}): {r_upload.text}")

    print("✅ Video uploaded directly to Instagram servers.")

    # Step 3: Transcode Status Check
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

    # Step 4: Publish
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

    generate_voice(script_data["voiceover"], "voice.mp3")
    print("✅ Audio Voiceover Ready.")

    create_video_ffmpeg(
        script_data.get("rule_title", "Postal Manual"),
        script_data.get("question", ""),
        script_data.get("options", ""),
        "voice.mp3",
        "final_reel.mp4"
    )

    upload_to_instagram_direct("final_reel.mp4", script_data.get("caption", ""))
