import os
import sys
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

PDF_PATH = "notes.pdf"
PROGRESS_FILE = "progress_state.json"
FRAME_IMG = "frame.png"
AUDIO_OUTPUT = "voiceover.mp3"
OUTPUT_VIDEO = "final_reel.mp4"

GRAPH_API_BASE = "".join(["http", "s://", "graph.", "facebook", ".com/v19.0/"])

VOICE_NAME = "hi-IN-SwaraNeural"
INSTAGRAM_PAGE_HANDLE = "@POSTAL_WALA"

def get_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("last_page", 0)
        except Exception:
            return 0
    return 0

def save_progress(page_num):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_page": page_num}, f, indent=4)

def extract_pdf_topic():
    pdf_files = [PDF_PATH] + [f for f in os.listdir() if f.endswith(".pdf") and f != PROGRESS_FILE]
    actual_pdf = None
    for p in pdf_files:
        if os.path.exists(p):
            actual_pdf = p
            break
            
    if not actual_pdf:
        raise FileNotFoundError("Repo me koi PDF nahi mili!")
    
    reader = PdfReader(actual_pdf)
    total_pages = len(reader.pages)
    if total_pages == 0:
        raise ValueError("PDF file khali hai!")
        
    last_page = get_progress()
    current_page = last_page % total_pages
    text = reader.pages[current_page].extract_text() or ""
    
    save_progress(current_page + 1)
    return text, current_page + 1, total_pages

def generate_exam_script(raw_text):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY GitHub Secrets me set nahi hai!")

    client = Groq(api_key=api_key)
    model_name = "qwen/qwen3.8-27b"
    print(f"Using Groq Model: {model_name}")

    prompt = f"""
    You are an expert tutor for Postal MTS/Postman exams running Instagram page 'Postal Wala'.
    Teach departmental rules thoroughly and completely from this running section.

    RULES:
    1. "spoken_script" MUST be in pure DEVANAGARI HINDI (हिंदी लिपि) with flawless grammar, explaining the rules clearly and ending with a high-value exam quiz question.
       - End with: "अपना सही जवाब कमेंट बॉक्स में लिखिए... और रोज़ाना ऐसी बेहतरीन तैयारी के लिए अभी फॉलो करें पोस्टल वाला को!"
    2. "hook_title" and "bullet_points" MUST be in clean ENGLISH or Devanagari for display on screen.
    3. Exactly 3 bullet points summarizing the rule clause.

    Return ONLY a valid JSON object:
    {{
      "hook_title": "POSTAL DEPARTMENT RULE",
      "spoken_script": "साथियों, विभागीय नियमों के अनुसार सभी डाक वस्तुओं का सुरक्षित प्रबंधन करना अनिवार्य होता है। प्रत्येक डाकघर में प्रविष्टि रजिस्टर में दर्ज की जाती है। आइए इस पर एक प्रश्न हल करें: विभागीय नियमों के उल्लंघन पर कार्रवाई का अधिकार किसे है? अपना सही जवाब कमेंट बॉक्स में लिखिए... और रोज़ाना ऐसी बेहतरीन तैयारी के लिए अभी फॉलो करें पोस्टल वाला को!",
      "bullet_points": ["Safe Management", "Mandatory Register Entry", "❓ Q: Who takes action?"],
      "caption": "डाक विभाग परीक्षा तैयारी संपूर्ण विश्लेषण #PostalWala #MTSExam #IndiaPost #Khand02"
    }}

    PDF Text:
    {raw_text[:2000]}
    """

    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    content = response.choices[0].message.content or "{}"
    clean_text = content.strip()
    if clean_text.startswith("```"):
        clean_text = clean_text.strip("`")
        if clean_text.startswith("json"):
            clean_text = clean_text[4:].strip()

    return json.loads(clean_text)

async def create_voiceover(text):
    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE_NAME,
        rate="-2%"
    )
    await communicate.save(AUDIO_OUTPUT)

def get_font(size):
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
    ]
    for p in font_paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def create_graphic_frame(reel_data):
    width, height = 1080, 1920
    img = Image.new("RGB", (width, height), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)

    title_font = get_font(46)
    body_font = get_font(34)
    promo_title_font = get_font(36)
    promo_num_font = get_font(44)

    draw.rounded_rectangle([(50, 180), (1030, 360)], radius=20, fill=(30, 41, 59), outline=(225, 29, 72), width=4)
    title = reel_data.get("hook_title", "POSTAL WALA").upper()
    draw.text((80, 245), f"📌 {title}", fill=(244, 63, 94), font=title_font)

    y_offset = 430
    for pt in reel_data.get("bullet_points", []):
        wrapped_lines = textwrap.wrap(pt, width=38)
        box_height = max(135, len(wrapped_lines) * 48 + 42)

        draw.rounded_rectangle([(50, y_offset), (1030, y_offset + box_height)], radius=18, fill=(30, 41, 59))
        
        text_y = y_offset + 24
        for idx, line in enumerate(wrapped_lines):
            prefix = "✔ " if (idx == 0 and not line.startswith("❓")) else ("" if line.startswith("❓") else "   ")
            text_color = (250, 204, 21) if "❓" in line else (255, 255, 255)
            draw.text((80, text_y), f"{prefix}{line}", fill=text_color, font=body_font)
            text_y += 48

        y_offset += box_height + 30

    promo_top = 1520
    promo_bottom = 1750
    draw.rounded_rectangle([(50, promo_top), (1030, promo_bottom)], radius=24, fill=(30, 41, 59), outline=(225, 29, 72), width=4)
    
    promo_text1 = "📚 DEPARTMENTAL EXAM PREPARATION"
    draw.text((90, promo_top + 35), promo_text1, fill=(250, 204, 21), font=promo_title_font)
    
    promo_text2 = f"🔥 FOLLOW: {INSTAGRAM_PAGE_HANDLE}"
    draw.text((90, promo_top + 105), promo_text2, fill=(56, 189, 248), font=promo_num_font)

    img.save(FRAME_IMG)

def render_video():
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", FRAME_IMG,
        "-i", AUDIO_OUTPUT,
        "-filter_complex",
        "zoompan=z='min(zoom+0.0003,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1500:s=1080x1920:fps=30",
        "-c:v", "libx264",
        "-profile:v", "high",
        "-level", "4.2",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        "-t", "50",
        OUTPUT_VIDEO
    ]
    subprocess.run(cmd, check=True)

def post_reel_to_instagram_direct(video_file, caption):
    access_token = os.environ.get("IG_ACCESS_TOKEN")
    user_id = os.environ.get("IG_USER_ID")
    
    if not access_token or not user_id:
        raise ValueError("IG_ACCESS_TOKEN ya IG_USER_ID secrets me missing hai!")

    file_size = os.path.getsize(video_file)
    print(f"Video size: {file_size} bytes. Initializing resumable upload container...")

    init_url = GRAPH_API_BASE + str(user_id).strip() + "/media"
    init_params = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "length": file_size,
        "access_token": access_token
    }
    
    r = None
    for attempt in range(3):
        try:
            r = requests.post(init_url, data=init_params, timeout=30)
            if r.status_code == 200:
                break
        except Exception as e:
            print(f"Init attempt {attempt+1} failed: {e}")
            time.sleep(5)
            
    if not r or r.status_code != 200:
        raise RuntimeError(f"Upload init fail hua: {r.text if r else 'No response'}")
        
    init_data = r.json()
    video_id = init_data.get("id")
    upload_url = init_data.get("upload_url") or init_data.get("uri")

    if not video_id or not upload_url:
        raise RuntimeError(f"Upload init invalid response: {init_data}")

    print("Uploading video binary data directly via resumable session...")
    with open(video_file, "rb") as vf:
        video_bytes = vf.read()

    headers = {
        "Authorization": f"OAuth {access_token}",
        "Offset": "0",
        "Content-Length": str(file_size),
        "X-Entity-Length": str(file_size),
        "Content-Type": "application/octet-stream"
    }
    
    upload_res = requests.post(upload_url, headers=headers, data=video_bytes, timeout=300)
    if upload_res.status_code not in [200, 201]:
        raise RuntimeError(f"Video binary upload fail hua ({upload_res.status_code}): {upload_res.text}")

    print("Waiting for Instagram video processing...")
    status_url = GRAPH_API_BASE + str(video_id).strip()
    for attempt in range(40):
        time.sleep(10)
        try:
            status_res = requests.get(status_url, params={"fields": "status_code", "access_token": access_token}, timeout=30).json()
            status = status_res.get("status_code")
            print(f"Check {attempt+1}: Status -> {status}")
            if status == "FINISHED":
                break
            elif status in ["ERROR", "EXPIRED"]:
                raise RuntimeError(f"Instagram processing failed with status: {status_res}")
        except Exception as e:
            print(f"Polling warning: {e}")

    print("Publishing Reel...")
    publish_url = GRAPH_API_BASE + str(user_id).strip() + "/media_publish"
    pub_res = requests.post(publish_url, data={"creation_id": video_id, "access_token": access_token}, timeout=30).json()

    if "id" in pub_res:
        print(f"🎉 Reel successfully published on Instagram! Post ID: {pub_res['id']}")
    else:
        raise RuntimeError(f"Publish fail hua: {pub_res}")

def main():
    print("🚀 [Step 1] Reading topic from PDF...")
    raw_text, page_num, total = extract_pdf_topic()
    print(f"Loaded Page {page_num} of {total}")

    print("🤖 [Step 2] Generating Script with Groq...")
    reel_data = generate_exam_script(raw_text)
    print(f"Topic: {reel_data.get('hook_title')}")

    print(f"🎙️ [Step 3] Generating Voiceover ({VOICE_NAME})...")
    asyncio.run(create_voiceover(reel_data.get("spoken_script")))

    print("🖼️ [Step 4] Creating Poster Frame...")
    create_graphic_frame(reel_data)

    print("🎬 [Step 5] Rendering Zoom Video (FFmpeg)...")
    render_video()

    caption_base = reel_data.get("caption", "")
    promo_caption = (
        f"\n\n💬 सही जवाब नीचे कमेंट्स में दें!\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Postal MTS/Postman परीक्षा की संपूर्ण तैयारी के लिए फॉलो करें!\n"
        f"📲 अभी सब्सक्राइब करें: {INSTAGRAM_PAGE_HANDLE}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    final_caption = f"{caption_base}\n{promo_caption}"

    print("📲 [Step 6] Uploading directly to Instagram via Resumable API...")
    post_reel_to_instagram_direct(OUTPUT_VIDEO, final_caption)

    print("\n✅ Entire workflow completed successfully!")

if __name__ == "__main__":
    main()
