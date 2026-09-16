import os
import glob
import json
import asyncio
import random
import requests
from pypdf import PdfReader
import edge_tts
from groq import Groq

# Secrets
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

client = Groq(api_key=GROQ_API_KEY)

def extract_text_from_pdf():
    pdf_files = glob.glob("*.pdf") + glob.glob("data/*.pdf")
    if not pdf_files:
        raise FileNotFoundError("Repo me koi PDF nahi mili!")
    
    # mts content .pdf ko target karna
    target_pdf = pdf_files[0]
    for f in pdf_files:
        if "mts" in f.lower():
            target_pdf = f
            break
            
    print(f"Reading target PDF: {target_pdf}")
    reader = PdfReader(target_pdf)
    total_pages = len(reader.pages)
    print(f"Total Pages in PDF: {total_pages}")
    
    # Har baar alag clause uthane ke liye
    start_page = random.randint(0, max(0, total_pages - 2))
    text = ""
    for page in reader.pages[start_page : start_page + 2]:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"
    return text[:3000]

def generate_clause_content(pdf_content):
    prompt = f"""
    You are an expert tutor for Postal Department MTS / Postman exams running Instagram page 'Postal Wala'.
    Pick ONE specific Rule or Clause from this study material and explain it.

    STRICT GUIDELINES:
    1. Language: Very simple, everyday conversational Hindi (बोलचाल की बिल्कुल आसान हिंदी). No complex bookish jargon.
    2. Hook: Mention the Clause/Rule clearly (e.g. "डाकघर गाइड का ये नियम क्या कहता है? सीधा समझो...").
    3. Easy Explanation: Break it down in 2-3 very easy lines like talking to a friend.
    4. Magic Question: End with 1 exam MCQ asking viewers to comment their answer (A, B, C ya D).

    Content:
    {pdf_content}

    Return ONLY a valid raw JSON object. Do not include markdown ticks, no backticks, no explanations:
    {{
        "rule_title": "Clause / Rule Name",
        "voiceover": "Full conversational voiceover text without brackets, emojis or sound tags.",
        "question": "Question text",
        "options": "A) ... B) ... C) ... D) ...",
        "caption": "Instagram caption ready to post with Rule, Explanation, Question, Options, and hashtags #PostalWala #IndiaPost #MTSExam"
    }}
    """
    
    response = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6
    )
    
    raw = response.choices[0].message.content.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)

async def generate_voice(text, filename="voice.mp3"):
    communicate = edge_tts.Communicate(text, voice="hi-IN-MadhurNeural")
    await communicate.save(filename)

if __name__ == "__main__":
    print("🚀 Postal Wala Automation Started...")
    
    extracted_text = extract_text_from_pdf()
    print("✅ PDF read successfully.")

    data = generate_clause_content(extracted_text)
    print("\n--- SELECTED TOPIC ---")
    print(data.get("rule_title"))
    print("\n--- EASY VOICEOVER ---")
    print(data.get("voiceover"))
    print("\n--- MAGIC QUESTION ---")
    print(data.get("question"))
    print(data.get("options"))

    asyncio.run(generate_voice(data["voiceover"], "voice.mp3"))
    print("\n✅ Audio generated successfully (voice.mp3).")
