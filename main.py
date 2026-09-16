import os
import glob
import json
import time
import subprocess
import requests
from pypdf import PdfReader
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont

# Secrets
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

# 1. 'खंड - 02' से पढ़ना और अगली बार के लिए पेज याद रखना
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

    return extracted_text[:3500], current_page + 1

# 2. AI Script & Quiz Generator
def generate_clause_script(pdf_content, page_num):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
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
        "voiceover": "Detailed conversational Hindi voiceover of around 160-190 words covering the explanation and the quiz question clearly.",
        "question": "Question text",
        "options": "A) ... B) ... C) ... D) ...",
        "caption": "Instagram Caption with Topic, Easy Explanation, MCQ Question, Options, and hashtags #PostalWala #MTSExam #IndiaPost #Khand02"
    }}
    """

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6
    }
    
    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
    raw = res.json()["choices"][0]["message"]["content"].strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)

# 3. Clean Hindi Audio
def generate_voice(text, filename="voice.mp3"):
    tts = gTTS(text=text, lang="hi", slow=False)
    tts.save(filename)

# 4. Reel Video Creation (FFmpeg Image + Audio to 1080x1920 MP4)
def create_video_ffmpeg(title, question, options, audio_file="voice.mp3", output_video="reel.mp4"):
    # Create 9:16 frame image
    img = Image.new("RGB", (1080, 1920), color="#0F172A")
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([60, 160, 1020, 1760], radius=40, fill="#1E293B", outline="#E11D48", width=6)
    draw.text((120, 220), "POSTAL WALA", fill="#F43F5E")
    draw.text((120, 320), f"Topic: {title[:40]}", fill="#FFFFFF")
    draw.text((120, 550), "RULE BREAKDOWN & QUIZ", fill="#38BDF8")

    # Quiz Box
    draw.rounded_rectangle([100, 720, 980, 1520], radius=30, fill="#0F172A")
    draw.text((130, 780), "सवाल (Comment Your Answer):", fill="#FBBF24")
    draw.text((130, 880), f"{question[:120]}...", fill="#FFFFFF")
    draw.text((130, 1100), f"{options[:160]}", fill="#94A3B8")

    frame_path = "frame.png"
    img.save(frame_path)

    # Use system ffmpeg to merge image + audio
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", frame_path,
        "-i", audio_file,
        "-c:v", "libx264", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest", output_video
    ]
    subprocess.run(cmd, check=True)
    print("✅ FFmpeg Reel Created Successfully.")

# 5. Instagram Direct Auto-Upload
def upload_to_instagram(video_path, caption):
    if not IG_ACCESS_TOKEN or not IG_USER_ID:
        print("⚠️ IG_ACCESS_TOKEN ya IG_USER_ID missing hai! Upload skip ho raha hai.")
        return

    print("📤 Uploading video to public host...")
    with open(video_path, "rb") as f:
        res = requests.post("https://file.io", files={"file": f})
    video_url = res.json().get("link")
    print(f"Public video link: {video_url}")

    # Create Reel Container
    url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN
    }
    r = requests.post(url, data=payload)
    res_json = r.json()
    container_id = res_json.get("id")

    if not container_id:
        print(f"❌ Error creating IG container: {r.text}")
        return

    print("⏳ Video processing on Instagram servers...")
    time.sleep(35)

    # Publish
    pub_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    pub_res = requests.post(pub_url, data={"creation_id": container_id, "access_token": IG_ACCESS_TOKEN})
    print("🚀 Reel Published Successfully:", pub_res.text)

if __name__ == "__main__":
    print("🚀 Postal Wala Complete Automation Running...")
    
    target_pdf = get_target_pdf()
    pdf_content, page_num = get_current_reading_window(target_pdf)
    print(f"✅ Reading Page {page_num}...")

    script_data = generate_clause_script(pdf_content, page_num)
    print("✅ Script Generated.")

    generate_voice(script_data["voiceover"], "voice.mp3")
    print("✅ Audio Generated.")

    create_video_ffmpeg(
        script_data.get("rule_title", "Postal Manual"),
        script_data.get("question", ""),
        script_data.get("options", ""),
        "voice.mp3",
        "final_reel.mp4"
    )

    upload_to_instagram("final_reel.mp4", script_data.get("caption", ""))
