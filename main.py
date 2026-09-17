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

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

GRAPH_API_BASE = "".join(["http", "s://", "graph.", "facebook", ".com/v19.0/"])
STATE_FILE = "progress_state.json"
DEV_FONT_PATH = "NotoSansDevanagari-Bold.ttf"
AUDIO_OUTPUT = "voice.mp3"
OUTPUT_VIDEO = "final_reel.mp4"
VOICE_NAME = "hi-IN-SwaraNeural"

def ensure_fonts():
    if not os.path.exists(DEV_FONT_PATH):
        print("📥 Downloading Noto Sans Devanagari font...")
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        r = requests.get(url, timeout=30)
        with open(DEV_FONT_PATH, "wb") as f:
            f.write(r.content)
        print("✅ Font cached locally.")

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
    
    state = {"last_page": 0, "char_offset": 0}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
        except Exception:
            pass

    current_page = state.get("last_page", 0)
    char_offset = state.get("char_offset", 0)

    if current_page >= total_pages:
        current_page = 0
        char_offset = 0

    page_text = reader.pages[current_page].extract_text() or ""
    chunk_size = 1400
    sub_text = page_text[char_offset:char_offset + chunk_size]

    next_offset = char_offset + chunk_size
    next_page = current_page
    if next_offset >= len(page_text):
        next_page += 1
        next_offset = 0

    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"last_page": next_page, "char_offset": next_offset}, f)
    except Exception:
        pass

    return sub_text, current_page + 1

def generate_clause_script(pdf_content, page_num):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY missing in GitHub Secrets!")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
        "Content-Type": "application/json"
    }

    # Prompt updated for the ultimate engagement hook (asking to comment the answer)
    prompt = f"""
    You are an expert tutor for Postal MTS/Postman exam running Instagram page 'Postal Wala'.
    Teach the departmental rules thoroughly and completely from this running section (Page {page_num}). 
    Do NOT cut short or leave the clause half-explained. Provide a comprehensive, uninterrupted explanation spanning 4 rich, grammatically flawless Hindi sentences (SEN1, SEN2, SEN3, SEN4).

    RULES:
    1. Pure Hindi (Devanagari script only), flawless grammar, zero spelling mistakes, no English words, no emojis, no bullet symbols.
    2. Keep each sentence natural and focused on a single complete rule aspect.

    PDF Section:
    {pdf_content}

    Format strictly matching these lines:
    TITLE: [Topic Name in pure Hindi]
    SEN1: [Flawless sentence 1]
    SEN2: [Flawless sentence 2]
    SEN3: [Flawless sentence 3]
    SEN4: [Flawless sentence 4]
    QUESTION: [1 high-value exam question based strictly on this text in Hindi]
    OPT_A: [Option A]
    OPT_B: [Option B]
    OPT_C: [Option C]
    OPT_D: [Option D]
    CORRECT: [A/B/C/D]
    VOICEOVER: [Voiceover MUST follow this exact sequence: 1. Warm greeting. 2. Ask the QUESTION immediately. 3. Say EXACTLY: "इसका जवाब जानने के लिए वीडियो में अंत तक बने रहें!". 4. Explain SEN1 to SEN4 clearly. 5. Say EXACTLY: "तो दोस्तों, इसका सही जवाब कमेंट्स में जरूर बताएं!". 6. End with call-to-action: "रोज़ाना ऐसी बेहतरीन तैयारी के लिए अभी फॉलो करें पोस्टल वाला को! GDS to MTS, Postman और P.A. के लिए कोर्स और फ्री मॉक टेस्ट के लिए 8989971379 पर WhatsApp करें।" IMPORTANT: DO NOT speak or reveal the correct answer anywhere.]
    CAPTION: [Instagram caption with #PostalWala #MTSExam #IndiaPost #Khand02]
    """

    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 800
    }
    
    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
    res_json = res.json()

    if res.status_code != 200 or "choices" not in res_json:
        raise RuntimeError(f"Groq API Error: {res_json}")

    raw_text = res_json["choices"][0]["message"]["content"].strip()
    
    data = {
        "rule_title": "डाक नियमों की विस्तृत जानकारी",
        "sen1": "विभागीय नियमों के अनुसार सभी डाक वस्तुओं का सुरक्षित प्रबंधन करना अनिवार्य होता है।",
        "sen2": "प्रत्येक डाकघर में प्राप्त होने वाली सामग्री की प्रविष्टि आधिकारिक रजिस्टर में दर्ज की जाती है।",
        "sen3": "नियमों का उल्लंघन पाए जाने पर उच्च अधिकारियों द्वारा सख्त अनुशासनात्मक कार्रवाई की जाती है।",
        "sen4": "सभी अभ्यर्थियों को परीक्षा की दृष्टि से इन प्रावधानों को पूरी तरह याद रखना चाहिए।",
        "question": "विभागीय नियमों के उल्लंघन पर कार्रवाई करने का अधिकार किसे प्राप्त है?",
        "opt_a": "स्थानीय डाकपाल",
        "opt_b": "उच्च अधिकारियों",
        "opt_c": "प्रेषक को",
        "opt_d": "इनमें से कोई नहीं",
        "correct": "B",
        "voiceover": "नमस्कार साथियों, पोस्टल वाला में आपका स्वागत है। आज का सवाल है: विभागीय नियमों के उल्लंघन पर कार्रवाई करने का अधिकार किसे प्राप्त है? इसका जवाब जानने के लिए वीडियो में अंत तक बने रहें! विभागीय नियमों के
