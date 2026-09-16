import os
import glob
import json
import asyncio
import requests
from pypdf import PdfReader
import edge_tts

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

# 1. खंड 2 से शुरू करना और आगे का प्रोग्रेस याद रखना
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

    # पहली बार चलने पर खंड 2 खोजना
    if current_page == 0:
        found_khand2 = False
        for idx, page in enumerate(reader.pages):
            txt = page.extract_text() or ""
            if any(term in txt for term in ["खंड 2", "खंड-2", "खण्ड 2", "Section 2", "Part 2", "Khand 2"]):
                current_page = idx
                found_khand2 = True
                print(f"✅ 'खंड 2' page {idx + 1} par mil gaya!")
                break
        if not found_khand2:
            print("⚠️ खंड 2 का हेडर नहीं मिला, पेज 1 से शुरू कर रहे हैं।")
            current_page = 0

    # एक रील के लिए 2 पेजों का कंटेंट
    end_page = min(current_page + 2, total_pages)
    extracted_text = ""
    for p in range(current_page, end_page):
        t = reader.pages[p].extract_text()
        if t:
            extracted_text += f"\n--- PAGE {p+1} ---\n" + t

    # अगली रील के लिए नया पेज नंबर सेव करना
    next_page = end_page if end_page < total_pages else 0
    with open(STATE_FILE, "w") as f:
        json.dump({"last_page": next_page}, f)

    return extracted_text[:3500], current_page + 1

# 2. 60-80 सेकंड का डिटेल्ड और आसान एक्सप्लेनेशन + क्विज़
def generate_clause_script(pdf_content, page_num):
    prompt = f"""
    You are an expert tutor for Postal MTS/Postman/Mail Guard exam running Instagram page 'Postal Wala'.
    Teach the next specific rule/clause from this departmental PDF section (Page around {page_num}).

    REEL FORMAT & TIMING INSTRUCTIONS:
    1. Duration: 60 to 80 SECONDS of spoken audio (around 160 to 190 words in spoken Hindi).
    2. Language: Super simple, everyday conversational Hindi (बोलचाल की बिल्कुल सरल हिंदी). No difficult bookish terms.
    3. Step-by-step Structure:
       - HOOK: Rule/Clause name or number clearly mention karo.
       - DETAILED EXPLANATION: Is clause ka aasan bhasha me matlab aur daily life ka practical example dekar samjhao. Agar clause lamba hai to is video me specific hissa cover karo aur bolo ki baki hissa agle part me cover hoga.
       - MAGIC QUESTION (Quiz): End with 1 exam-style MCQ based on this clause, and ask viewers to comment their answer (A, B, C or D).

    PDF Content:
    {pdf_content}

    Return ONLY raw valid JSON (no markdown ticks, no backticks, no markdown codeblocks):
    {{
        "rule_title": "Clause/Rule Name",
        "voiceover": "Detailed Hindi voiceover text of around 160-190 words. Speak both explanation, practical example, and the quiz question naturally.",
        "question": "Question text",
        "options": "A) ... B) ... C) ... D) ...",
        "caption": "Instagram Caption with Part number, Explanation, MCQ Question, Options, and hashtags #PostalWala #MTSExam #IndiaPost #Khand2"
    }}
    """

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"Groq API Error: {response.text}")
        
    res_data = response.json()
    raw = res_data["choices"][0]["message"]["content"].strip()
    
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)

# 3. Edge-TTS Natural Voice
async def generate_voice(text, filename="voice.mp3"):
    communicate = edge_tts.Communicate(text, voice="hi-IN-MadhurNeural")
    await communicate.save(filename)

if __name__ == "__main__":
    print("🚀 Postal Wala Serial Automation Starting...")
    
    target_pdf = get_target_pdf()
    pdf_content, page_num = get_current_reading_window(target_pdf)
    print(f"✅ Extracted content starting near page {page_num}.")

    script_data = generate_clause_script(pdf_content, page_num)
    print("\n--- TOPIC ---")
    print(script_data.get("rule_title"))
    print("\n--- 60-80s VOICEOVER SCRIPT ---")
    print(script_data.get("voiceover"))
    print("\n--- QUIZ QUESTION ---")
    print(script_data.get("question"))
    print(script_data.get("options"))

    asyncio.run(generate_voice(script_data["voiceover"], "voice.mp3"))
    print("\n✅ Audio generated successfully (voice.mp3).")
