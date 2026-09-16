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

# 1. 'खंड - 02' से शुरू करना और क्रमवार आगे बढ़ना
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

    # पहली बार चलने पर 'खंड - 02' खोजना
    if current_page == 0:
        search_terms = ["खंड - 02", "खंड-02", "खंड 02", "खंड 2", "डाकघरों के प्रकार"]
        for idx, page in enumerate(reader.pages):
            txt = page.extract_text() or ""
            if any(term in txt for term in search_terms):
                current_page = idx
                print(f"✅ 'खंड - 02' पेज नंबर {idx + 1} पर मिल गया!")
                break
        else:
            print("⚠️ 'खंड - 02' नहीं मिला, पेज 1 से शुरू कर रहे हैं।")
            current_page = 0

    # 1 रील के लिए कंटेंट उठाना
    end_page = min(current_page + 1, total_pages)
    extracted_text = ""
    for p in range(current_page, end_page):
        t = reader.pages[p].extract_text()
        if t:
            extracted_text += f"\n--- PAGE {p+1} ---\n" + t

    # अगली रील के लिए प्रोग्रेस सेव करना
    next_page = end_page if end_page < total_pages else 0
    with open(STATE_FILE, "w") as f:
        json.dump({"last_page": next_page}, f)

    return extracted_text[:3500], current_page + 1

# 2. Groq Llama-3 से 60-80s की आसान देसी हिंदी स्क्रिप्ट और क्विज़
def generate_clause_script(pdf_content, page_num):
    prompt = f"""
    You are an expert tutor for Postal MTS/Postman exam running Instagram page 'Postal Wala'.
    Teach the next specific rule/clause from this departmental PDF section (Around Page {page_num}).
    Topic includes: Head Office (HO), Sub Office (SO), Branch Office (BO) or related clauses.

    REEL GUIDELINES:
    1. Duration: 60 to 80 SECONDS of spoken audio (around 160-190 words in spoken Hindi).
    2. Language: Super simple, everyday conversational Hindi (बोलचाल की बिल्कुल सरल देसी हिंदी). Kitabi bhasha ko aasan daily life example me badlo.
    3. Step-by-step Structure:
       - Hook: Rule/Topic clearly batao (jaise: 'Head Office aur Sub Office me asli antar kya hota hai?').
       - Detailed Explanation: HO, SO ya BO ke rule ko 3-4 simple lines me samjhao. Agar topic lamba hai to specific part samjhao aur bolo baki agle part me aayega.
       - Magic Question (Quiz): End me 1 exam-style MCQ question pucho aur bolo ki iska sahi jawab comments me batao (A, B, C ya D).

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

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama3-8b-8192",
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

# 3. Edge-TTS Natural Hindi Voice
async def generate_voice(text, filename="voice.mp3"):
    communicate = edge_tts.Communicate(text, voice="hi-IN-MadhurNeural")
    await communicate.save(filename)

if __name__ == "__main__":
    print("🚀 Postal Wala Serial Automation Starting...")
    
    target_pdf = get_target_pdf()
    pdf_content, page_num = get_current_reading_window(target_pdf)
    print(f"✅ Extracted content starting near page {page_num}.")

    script_data = generate_clause_script(pdf_content, page_num)
    print("\n--- SELECTED TOPIC ---")
    print(script_data.get("rule_title"))
    print("\n--- 60-80s VOICEOVER SCRIPT ---")
    print(script_data.get("voiceover"))
    print("\n--- MAGIC QUIZ QUESTION ---")
    print(script_data.get("question"))
    print(script_data.get("options"))

    asyncio.run(generate_voice(script_data["voiceover"], "voice.mp3"))
    print("\n✅ Audio generated successfully (voice.mp3).")
