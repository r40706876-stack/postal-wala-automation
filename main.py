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
    body_font =
