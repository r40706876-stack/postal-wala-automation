import os
import glob
import json
import time
import asyncio
import subprocess
import requests
import textwrap
import re
import sys
from PIL import Image, ImageDraw, ImageFont
import edge_tts

# --- Environment Variables ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

GRAPH_API_BASE = "https://graph.facebook.com/v19.0/"
RUPLOAD_BASE = "https://rupload.facebook.com/ig-api-upload/v19.0/"

STATE_FILE = "progress_state.json"
DEV_FONT_PATH = "NotoSansDevanagari-Bold.ttf"
OUTPUT_VIDEO = "final_reel.mp4"
VOICE_NAME = "hi-IN-SwaraNeural"

# Assets Directory
ASSETS_DIR = "assets"
BOOK_3D_PATH = os.path.join(ASSETS_DIR, "3d_book.png")
POSTBOX_3D_PATH = os.path.join(ASSETS_DIR, "3d_postbox.png")
QUIZ_3D_PATH = os.path.join(ASSETS_DIR, "3d_quiz.png")

RESAMPLE_MODE = getattr(Image, "Resampling", Image).LANCZOS

# --- 6 High-Retention Rotating Viral Hooks ---
VIRAL_HOOKS = [
    {
        "voice": "लिख कर ले लो, डाक विभाग की परीक्षा में 2 नंबर पक्के हैं, ध्यान से समझो!",
        "visual_badge": "लिख कर ले लो! 2 नंबर पक्के"
    },
    {
        "voice": "90% लोग इस एक नियम में गलत उत्तर देकर आते हैं, क्या आपको सही नियम पता है?",
        "visual_badge": "सावधान: 90% लोग फेल होते हैं!"
    },
    {
        "voice": "अगर सच में जीडीएस से प्रमोशन की तैयारी कर रहे हैं, तो इस सवाल का सही जवाब देकर दिखाइए!",
        "visual_badge": "दम है तो सही उत्तर देकर दिखाओ!"
    },
    {
        "voice": "परीक्षा में बार-बार दोहराया जाने वाला यह नियम आज हमेशा के लिए दिमाग में बैठा लो!",
        "visual_badge": "परीक्षा में बार-बार पूछा जाने वाला नियम"
    },
    {
        "voice": "इस बार जीडीएस से पोस्टमैन या पी.ए. बनना है, तो इस जरूरी सवाल को मिस मत करना!",
        "visual_badge": "जीडीएस से प्रमोशन का पक्का मौका!"
    },
    {
        "voice": "डाक घर गाइड का यह छोटा सा नियम कई परीक्षार्थियों के नंबर कटवा देता है, आइए हल करते हैं!",
        "visual_badge": "चेतावनी: यह नियम नंबर कटवा सकता है!"
    }
]

# --- Master Catalog ---
POSTAL_CLAUSE_CATALOG = {
    1: {
        "name": "डाक विभाग का नियंत्रण व संगठन", "total_parts": 2,
        "part_1_focus": "संचार मंत्रालय के अधीन महानिदेशक (DG Posts) शीर्ष प्रशासनिक प्रमुख हैं और मुख्यालय डाक भवन नई दिल्ली में स्थित है।",
        "part_2_focus": "डाक सेवा बोर्ड (PSB) में एक चेयरमैन (सचिव डाक) और 6 पूर्णकालिक सदस्य होते हैं जो कार्मिक, प्रचालन व तकनीक का कार्य देखते हैं।"
    },
    2: {
        "name": "डाकघरों के प्रकार और श्रेणियां", "total_parts": 3,
        "part_1_focus": "डाकघर की 3 प्रमुख श्रेणियां हैं: प्रधान डाकघर (HO), उप डाकघर (SO) और शाखा डाकघर (BO)। HO मुख्य वित्तीय लेखा कार्यालय होता है।",
        "part_2_focus": "उप डाकघर (SO) प्रधान डाकघर के अधीन रहकर सभी प्रकार के लेन-देन करता है और दैनिक लेखा HO को प्रेषित करता है।",
        "part_3_focus": "ग्रामीण शाखा डाकघर (BO) के कार्य के घंटे न्यूनतम 4 घंटे और अधिकतम 5 घंटे प्रतिदिन निर्धारित किए जाते हैं।"
    },
    3: {
        "name": "रात्रि डाकघर के नियम", "total_parts": 3,
        "part_1_focus": "रात्रि डाकघर की स्थापना और कामकाज के घंटे रात 8:30 बजे तक बढ़ाने का विशेष अधिकार केवल महानिदेशक (DG) को है।",
        "part_2_focus": "रविवार और राष्ट्रीय डाक अवकाशों पर रात्रि डाकघर सुबह 10 से शाम 5 बजे तक केवल सीमित सेवाएं (रजिस्ट्री बुकिंग, टिकट विक्रय) देते हैं।",
        "part_3_focus": "रात्रि डाकघरों में रविवार और अवकाश के दिनों में कोई भी मनीऑर्डर भुगतान या बचत बैंक निकासी कार्य नहीं होता।"
    },
    4: {
        "name": "मोबाइल डाकघर की व्यवस्था", "total_parts": 2,
        "part_1_focus": "मोबाइल डाकघर बड़े शहरों में देर शाम तक सामान्य डाक व पार्सल बुकिंग की सुविधा जनता को उपलब्ध कराते हैं।",
        "part_2_focus": "मोबाइल डाकघर में मनीऑर्डर, बचत बैंक और बीमा का कोई भी वित्तीय कार्य करना पूर्णतः प्रतिबंधित होता है।"
    },
    5: {
        "name": "डाकघर के कामकाज के घंटे", "total_parts": 3,
        "part_1_focus": "सामान्य डाक टिकट बिक्री और डाक बुकिंग पूरे कार्य समय तक होती है, जबकि बचत बैंक और मनीऑर्डर का समय निर्धारित पहले समाप्त होता है।",
        "part_2_focus": "सार्वजनिक काउंटर बंद होने के बाद निर्धारित लेट फीस (Late Fee) का भुगतान करके ही डाक बुक की जा सकती है।",
        "part_3_focus": "शनिवार को सामान्य डाक लेन-देन के समय में कटौती के विभागीय नियम और नोटिस बोर्ड पर समय सारिणी प्रदर्शित करना।"
    },
    22: {
        "name": "डाक का पुनः निर्देशन (Redirection)", "total_parts": 3,
        "part_1_focus": "पतेदार के नया पता छोड़कर जाने पर प्रथम श्रेणी की अंतरदेशीय डाक का पुनः प्रेषण (Redirection) पूर्णतः निःशुल्क होता है।",
        "part_2_focus": "पार्सल पुनः प्रेषण के मामले में यदि पार्सल वितरण क्षेत्र से बाहर भेजा जाए तो आधा डाक प्रभार (Half Forwarding Fee) देय होता है।",
        "part_3_focus": "यदि पार्सल को पतेदार द्वारा एक बार खोल दिया गया हो तो उसे नए डाकभार के बिना पुनः निर्देशित नहीं किया जा सकता।"
    }
}

def clean_text(text):
    if not text:
        return ""
    text = text.strip().strip("[](){}\"'`")
    text = "".join(c for c in text if ord(c) < 0x10000)
    strip_ranges = [
        (0x2190, 0x21FF), (0x2300, 0x23FF), (0x25A0, 0x25FF),
        (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0xFE0F, 0xFE0F),
    ]
    text = "".join(c for c in text if not any(lo <= ord(c) <= hi for lo, hi in strip_ranges))
    return text.strip()

def is_latin_run_char(ch):
    o = ord(ch)
    return (0x41 <= o <= 0x5A) or (0x61 <= o <= 0x7A)

def draw_mixed_line(draw, x, y, text, dev_font, eng_font, fill):
    cx = x
    run = ""
    run_is_latin = None
    for ch in text:
        latin = is_latin_run_char(ch)
        if run_is_latin is None:
            run_is_latin = latin
        if latin != run_is_latin:
            f = eng_font if run_is_latin else dev_font
            draw.text((cx, y), run, font=f, fill=fill)
            cx += draw.textlength(run, font=f)
            run = ""
            run_is_latin = latin
        run += ch
    if run:
        f = eng_font if run_is_latin else dev_font
        draw.text((cx, y), run, font=f, fill=fill)

def draw_mixed_multiline(draw, x, y, wrapped_text, dev_font, eng_font, fill, line_height):
    for i, line in enumerate(wrapped_text.split("\n")):
        draw_mixed_line(draw, x, y + i * line_height, line, dev_font, eng_font, fill)

def clean_hindi_postal_terms(text):
    if not text:
        return ""
    replacements = {
        "पेन्टियों": "पत्र-पेटियों", "पेन्टी": "पत्र-पेटी",
        "घंटी वाली प्लेटें": "घंटे वाली प्लेटें", "घंटी वाली प्लेट": "घंटे वाली प्लेट",
        "नित्य पत्र": "वित्तीय वर्ष", "नित्य वर्ष": "वित्तीय वर्ष"
    }
    for bad_w, good_w in replacements.items():
        text = text.replace(bad_w, good_w)
    return clean_text(text)

def extract_field_block(text, field_name, next_fields):
    pattern = r"(?:^|\n)\s*(?:\*\*)?" + re.escape(field_name) + r"(?:\*\*)?\s*:\s*(.*?)(?=(?:\n\s*(?:\*\*)?(?:" + "|".join(next_fields) + r")(?:\*\*)?\s*:)|$)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        val = re.sub(r"^[\"\'`]+|[\"\'`]+$", "", val).strip()
        return " ".join(val.split())
    return None

def ensure_auto_icons():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    try:
        bk = Image.new("RGBA", (300, 420), (0, 0, 0, 0))
        db = ImageDraw.Draw(bk)
        db.rounded_rectangle([60, 55, 240, 365], radius=14, fill="#1E3A8A")
        db.rounded_rectangle([78, 62, 232, 358], radius=10, fill="#2563EB")
        db.rounded_rectangle([90, 62, 100, 358], fill="#1D4ED8")
        for ly in range(90, 340, 34):
            db.rounded_rectangle([112, ly, 214, ly + 10], radius=4, fill="#DBEAFE")
        bk.save(BOOK_3D_PATH, "PNG")
    except Exception:
        pass

    try:
        box = Image.new("RGBA", (300, 420), (0, 0, 0, 0))
        d = ImageDraw.Draw(box)
        d.rounded_rectangle([70, 160, 230, 350], radius=18, fill="#7F1D1D")
        d.pieslice([70, 90, 230, 250], start=180, end=360, fill="#7F1D1D")
        d.rounded_rectangle([85, 175, 215, 335], radius=14, fill="#DC2626")
        d.pieslice([85, 105, 215, 245], start=180, end=360, fill="#DC2626")
        d.rounded_rectangle([100, 195, 200, 212], radius=6, fill="#7F1D1D")
        d.polygon([(200, 130), (255, 110), (255, 160)], fill="#FBBF24")
        d.rounded_rectangle([195, 125, 208, 200], radius=4, fill="#4B5563")
        d.rounded_rectangle([40, 350, 260, 375], radius=10, fill="#374151")
        box.save(POSTBOX_3D_PATH, "PNG")
    except Exception:
        pass

    try:
        q = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
        dq = ImageDraw.Draw(q)
        dq.rounded_rectangle([40, 40, 260, 260], radius=40, fill="#D97706")
        dq.polygon([(110, 250), (150, 250), (110, 310)], fill="#D97706")
        try:
            qfont = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 150)
        except Exception:
            qfont = ImageFont.load_default()
        bbox = dq.textbbox((0, 0), "?", font=qfont)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        dq.text((150 - tw / 2 - bbox[0], 150 - th / 2 - bbox[1]), "?", fill="#FFFBEB", font=qfont)
        q.save(QUIZ_3D_PATH, "PNG")
    except Exception:
        pass

def ensure_fonts():
    if not os.path.exists(DEV_FONT_PATH):
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        r = requests.get(url, timeout=30)
        with open(DEV_FONT_PATH, "wb") as f:
            f.write(r.content)

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

def load_progress_state():
    state = {"clause_no": 22, "current_part": 2, "total_parts": 3, "hook_index": 1}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                if isinstance(saved, dict) and "clause_no" in saved:
                    state.update(saved)
        except Exception:
            pass
    current_clause = state.get("clause_no", 22)
    state["total_parts"] = POSTAL_CLAUSE_CATALOG.get(current_clause, {}).get("total_parts", 1)
    save_progress_state(state)
    return state

def save_progress_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

def advance_progress_state(state):
    hook_idx = state.get("hook_index", 0)
    state["hook_index"] = (hook_idx + 1) % len(VIRAL_HOOKS)

    clause = state.get("clause_no", 22)
    part = state.get("current_part", 2)
    clause_info = POSTAL_CLAUSE_CATALOG.get(clause, {"total_parts": 1})
    total_parts = clause_info.get("total_parts", 1)

    if part < total_parts:
        state["current_part"] = part + 1
        state["total_parts"] = total_parts
    else:
        catalog_keys = sorted(POSTAL_CLAUSE_CATALOG.keys())
        current_idx = catalog_keys.index(clause) if clause in catalog_keys else 0
        next_idx = (current_idx + 1) % len(catalog_keys)
        next_clause = catalog_keys[next_idx]
        state["clause_no"] = next_clause
        state["current_part"] = 1
        state["total_parts"] = POSTAL_CLAUSE_CATALOG.get(next_clause, {}).get("total_parts", 1)

    save_progress_state(state)
    print(f"⏩ Next State: Clause {state['clause_no']} (Part {state['current_part']}/{state['total_parts']})", flush=True)

def generate_clause_script(state):
    current_clause = state.get("clause_no", 22)
    current_part = state.get("current_part", 2)
    hook_idx = state.get("hook_index", 0) % len(VIRAL_HOOKS)
    hook_obj = VIRAL_HOOKS[hook_idx]

    clause_info = POSTAL_CLAUSE_CATALOG.get(current_clause, {
        "name": f"क्लॉज {current_clause}",
        "total_parts": 1,
        "part_1_focus": "डाक घर गाइड भाग 1 के आधिकारिक नियमों का पालन अनिवार्य है।"
    })
    clause_name = clause_info["name"]
    total_parts = clause_info.get("total_parts", 1)
    part_focus = clause_info.get(f"part_{current_part}_focus", clause_info.get("part_1_focus", ""))

    # Robust clause-specific exam question fallback (NO text truncation or broken ellipsis)
    fallback_data = {
        "clause_no": current_clause,
        "clause_name": clause_name,
        "part_no": current_part,
        "total_parts": total_parts,
        "visual_hook_badge": hook_obj["visual_badge"],
        "hook_voice": hook_obj["voice"],
        "question": f"पार्सल को वितरण क्षेत्र से बाहर पुनः प्रेषित (Redirect) करने पर कितना डाक प्रभार लिया जाता है?",
        "opt_a": "आधा डाक प्रभार (50%)",
        "opt_b": "पूर्ण डाक शुल्क (100%)",
        "opt_c": "पूर्णतः निःशुल्क (Free)",
        "opt_d": "दोगुना दंड प्रभार",
        "correct_letter": "A",
        "sen1": "पार्सल पुनः प्रेषण में वितरण क्षेत्र से बाहर भेजे जाने पर आधा डाक प्रभार (Half Forwarding Fee) देय होता है।",
        "sen2": "यदि पार्सल को पतेदार द्वारा एक बार खोल दिया गया हो, तो नए डाक शुल्क के बिना पुनः प्रेषण नहीं होगा।",
        "caption": f"🚨 90% लोग इस नियम में गलती करते हैं! डाक घर गाइड भाग 1 | क्लॉज {current_clause} (भाग {current_part}/{total_parts})। सही उत्तर वीडियो में है! फ्री विभागीय नोट्स हेतु WhatsApp करें: 8989971379 #PostalWala #GDStoMTS #PostmanExam #IndiaPost"
    }

    if current_clause == 22 and current_part == 1:
        fallback_data["question"] = "पतेदार के नया पता छोड़कर जाने पर प्रथम श्रेणी अंतरदेशीय डाक का पुनः प्रेषण शुल्क कितना है?"
        fallback_data["opt_a"] = "पूर्ण डाक प्रभार",
        fallback_data["opt_b"] = "पूर्णतः निःशुल्क",
        fallback_data["opt_c"] = "आधा डाक शुल्क",
        fallback_data["opt_d"] = "दस रुपये अतिरिक्त शुल्क",
        fallback_data["correct_letter"] = "B"
        fallback_data["sen1"] = "पतेदार के नया पता छोड़कर जाने पर प्रथम श्रेणी की अंतरदेशीय डाक का पुनः प्रेषण पूरी तरह निःशुल्क होता है।"
        fallback_data["sen2"] = "लिखित पुनः प्रेषण निर्देश की अधिकतम वैधता अवधि केवल 3 महीने तक ही मान्य होती है।"

    if not GROQ_API_KEY:
        print("🛑 GROQ_API_KEY missing - using curated exam fallback.", flush=True)
        return fallback_data

    prompt = f"""
    You are the Senior Examiner for India Post Departmental Exams (GDS to MTS, Postman, Postal Assistant) running 'Postal Wala'.
    Topic: Post Office Guide Part 1
    Clause: क्लॉज {current_clause}, Title: {clause_name}, Part: {current_part}/{total_parts}
    Sub-rule Core Fact: "{part_focus}"

    Create an intense, highly engaging exam quiz reel script. Do NOT ask generic questions like 'Which statement is true'. Ask a direct, high-yield scenario question testing the exact rule, fee, condition or exception.
    Format your response EXACTLY as follows:
    QUESTION: [1 direct, crisp exam scenario question in pure Hindi, max 16 words]
    OPT_A: [Option A, 2 to 5 words, complete phrase, NO ellipsis]
    OPT_B: [Option B, 2 to 5 words, complete phrase, NO ellipsis]
    OPT_C: [Option C, 2 to 5 words, complete phrase, NO ellipsis]
    OPT_D: [Option D, 2 to 5 words, complete phrase, NO ellipsis]
    CORRECT: [Only single letter: A, B, C or D]
    SEN1: [Core official rule explaining why this answer is correct in simple Hindi, max 18 words, complete sentence]
    SEN2: [Crucial exam trap, exception, or departmental warning for this part, max 18 words, complete sentence]
    """
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"}
        payload = {"model": "qwen/qwen3-32b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 500}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            raw_text = res.json()["choices"][0]["message"]["content"].strip()
            q = extract_field_block(raw_text, "QUESTION", ["OPT_A", "SEN1"])
            oa = extract_field_block(raw_text, "OPT_A", ["OPT_B"])
            ob = extract_field_block(raw_text, "OPT_B", ["OPT_C"])
            oc = extract_field_block(raw_text, "OPT_C", ["OPT_D"])
            od = extract_field_block(raw_text, "OPT_D", ["CORRECT"])
            correct = extract_field_block(raw_text, "CORRECT", ["SEN1"])
            s1 = extract_field_block(raw_text, "SEN1", ["SEN2"])
            s2 = extract_field_block(raw_text, "SEN2", [])

            if q: fallback_data["question"] = clean_hindi_postal_terms(q)
            if oa: fallback_data["opt_a"] = clean_hindi_postal_terms(oa)
            if ob: fallback_data["opt_b"] = clean_hindi_postal_terms(ob)
            if oc: fallback_data["opt_c"] = clean_hindi_postal_terms(oc)
            if od: fallback_data["opt_d"] = clean_hindi_postal_terms(od)
            if s1: fallback_data["sen1"] = clean_hindi_postal_terms(s1)
            if s2: fallback_data["sen2"] = clean_hindi_postal_terms(s2)
            if correct:
                m = re.search(r"[ABCDabcd]", correct)
                if m:
                    fallback_data["correct_letter"] = m.group(0).upper()
            print("✅ Groq: Fresh departmental MCQ generated successfully.", flush=True)
    except Exception as e:
        print(f"🛑 Groq call failed ({e}) - using solid exam template.", flush=True)

    return fallback_data

def get_correct_option_text(script_data):
    letter = script_data.get("correct_letter", "A").strip().upper()
    key = f"opt_{letter.lower()}"
    return letter, script_data.get(key, script_data.get("opt_a", ""))

def get_slide_segments(script_data):
    letter, correct_text = get_correct_option_text(script_data)
    return [
        # Slide 1: Viral Hook
        f"{script_data['hook_voice']}",
        # Slide 2: Direct Exam Question
        f"आज का परीक्षा प्रश्न ध्यान से देखें: {script_data['question']}",
        # Slide 3: Options + Suspense + Comment trigger
        f"विकल्प ध्यान से देखिए: ए, बी, सी या डी? 90% परीक्षार्थी यहां गलती करते हैं, अपना जवाब तुरंत कमेंट करें!",
        # Slide 4: Answer Reveal + Core Official Rule
        f"सही उत्तर है विकल्प {letter}: {correct_text}। डाक घर गाइड के अनुसार {script_data['sen1']}",
        # Slide 5: Exam Trap / Critical Condition
        f"परीक्षा का सबसे बड़ा ट्रैप याद रखें: {script_data['sen2']}",
        # Slide 6: Engagement & Next Part CTA
        f"क्या आपका जवाब सही था? कमेंट में यस लिखें! डाक विभाग की पक्की तैयारी और अगले भाग के लिए अभी फॉलो करें!"
    ]

async def generate_segment_audio(text, outfile):
    if os.path.exists(outfile):
        try: os.remove(outfile)
        except Exception: pass
    communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+6%")
    await communicate.save(outfile)
    _tighten_audio_silence(outfile)

def _tighten_audio_silence(path):
    tmp_path = path + ".tight.mp3"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", path,
            "-af", "silenceremove=start_periods=1:start_duration=0:start_threshold=-35dB:"
                   "stop_periods=-1:stop_duration=0.12:stop_threshold=-35dB:window=0.05:detection=peak",
            "-c:a", "libmp3lame", "-b:a", "192k", tmp_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 500:
            os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except Exception: pass

def get_audio_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    return float(subprocess.check_output(cmd).decode().strip())

def render_and_sync_video(script_data, output_video=OUTPUT_VIDEO):
    ensure_fonts()
    ensure_auto_icons()

    segment_audios = get_slide_segments(script_data)
    raw_durations = []
    
    n_segments = len(segment_audios)
    for i, seg_text in enumerate(segment_audios):
        seg_file = f"audio_seg_{i}.mp3"
        asyncio.run(generate_segment_audio(seg_text, seg_file))
        raw_durations.append(get_audio_duration(seg_file))

    concat_filter = "".join([f"[{i}:a]" for i in range(n_segments)]) + f"concat=n={n_segments}:v=0:a=1[aout]"
    ffmpeg_concat_cmd = ["ffmpeg", "-y"]
    for i in range(n_segments):
        ffmpeg_concat_cmd.extend(["-i", f"audio_seg_{i}.mp3"])
    ffmpeg_concat_cmd.extend(["-filter_complex", concat_filter, "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "raw_master.mp3"])
    subprocess.run(ffmpeg_concat_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    total_dur = get_audio_duration("raw_master.mp3")
    print(f"🎵 Raw Audio Duration: {total_dur:.2f}s", flush=True)

    MIN_TARGET_DUR = 22.0
    MAX_TARGET_DUR = 32.0
    if total_dur < MIN_TARGET_DUR:
        tempo_scale = max(0.88, round(total_dur / MIN_TARGET_DUR, 4))
    elif total_dur > MAX_TARGET_DUR:
        tempo_scale = min(1.20, round(total_dur / MAX_TARGET_DUR, 4))
    else:
        tempo_scale = 1.0

    if tempo_scale != 1.0:
        subprocess.run(["ffmpeg", "-y", "-i", "raw_master.mp3", "-filter:a", f"atempo={tempo_scale}", "final_master.mp3"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run(["ffmpeg", "-y", "-i", "raw_master.mp3", "-c:a", "copy", "final_master.mp3"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    durations = [d / tempo_scale for d in raw_durations]
    print(f"🎬 Synced Video Duration: {sum(durations):.1f}s (Speed factor: {tempo_scale})", flush=True)

    font_brand = get_eng_font(44)
    font_sub = get_eng_font(22)
    font_trust = get_eng_font(20)
    font_badge = get_dev_font(22)
    font_title = get_dev_font(34)
    font_h2 = get_dev_font(30)
    font_body = get_dev_font(30)
    font_label = get_dev_font(26)
    font_wa_hin = get_dev_font(30)
    font_wa_num = get_eng_font(30)
    font_cta = get_eng_font(30)
    font_cta_dev = get_dev_font(30)
    font_opt = get_dev_font(26)
    font_hook = get_dev_font(32)
    font_title_eng = get_eng_font(34)
    font_body_eng = get_eng_font(30)
    font_opt_eng = get_eng_font(26)
    font_hook_eng = get_eng_font(32)
    font_h2_eng = get_eng_font(30)

    def draw_base(d):
        d.rounded_rectangle([45, 50, 1035, 1710], radius=32, fill="#0B132B", outline="#1E293B", width=3)
        d.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        d.text((80, 130), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)
        d.rounded_rectangle([630, 80, 1000, 132], radius=16, fill="#064E3B", outline="#10B981", width=2)
        d.text((655, 93), "100% OFFICIAL SYLLABUS", fill="#D1FAE5", font=font_trust)

    def draw_whatsapp_strip_at(d, y=345):
        d.rounded_rectangle([80, y, 1000, y + 130], radius=18, fill="#064E3B", outline="#34D399", width=2)
        d.text((110, y + 17), "GDS to MTS • Postman • Mail Guard • P.A.", fill="#FDE047", font=font_wa_num)
        d.text((110, y + 67), "कोर्स व फ्री टेस्ट हेतु व्हाट्सएप: 8989971379", fill="#FFFFFF", font=font_wa_hin)

    def draw_footer_cta(d):
        d.rounded_rectangle([80, 1580, 1000, 1680], radius=22, fill="#E11D48")
        d.text((120, 1605), "पूरी तैयारी के लिए फॉलो करें:", fill="#FFFFFF", font=font_cta_dev)
        d.text((580, 1605), "@POSTAL_WALA", fill="#FFFFFF", font=font_cta)

    def paste_safe_asset(base_img, path, pos, size=(280, 360)):
        if os.path.exists(path):
            try:
                ic = Image.open(path).convert("RGBA").resize(size, RESAMPLE_MODE)
                base_img.paste(ic, pos, ic)
            except Exception:
                pass

    def draw_progress_dots(d, current_idx, total):
        dot_r = 9
        gap = 28
        total_w = (total - 1) * gap
        start_x = 540 - total_w // 2
        y = 158
        for i in range(total):
            cx = start_x + i * gap
            if i == current_idx:
                d.ellipse([cx - dot_r, y - dot_r, cx + dot_r, y + dot_r], fill="#F43F5E")
            else:
                d.ellipse([cx - 6, y - 6, cx + 6, y + 6], fill="#334155")

    def draw_header(d, script_data, title_override=None):
        d.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
        d.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
        d.text((120, 198), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
        d.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
        d.text((845, 198), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
        title_text = title_override if title_override else clean_hindi_postal_terms(script_data["clause_name"])
        draw_mixed_line(d, 105, 255, title_text, font_title, font_title_eng, "#FFFFFF")

    def draw_checkmark(base_img, cx, cy, r=46):
        dchk = ImageDraw.Draw(base_img)
        dchk.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#10B981")
        dchk.line([cx - r * 0.5, cy, cx - r * 0.12, cy + r * 0.4], fill="#FFFFFF", width=10)
        dchk.line([cx - r * 0.12, cy + r * 0.4, cx + r * 0.55, cy - r * 0.4], fill="#FFFFFF", width=10)

    slide_filenames = []
    TOTAL_SLIDES = 6
    letter, correct_text = get_correct_option_text(script_data)

    # ---------------- SLIDE 1: VIRAL HOOK ----------------
    img1 = Image.new("RGB", (1080, 1920), color="#060A17")
    d1 = ImageDraw.Draw(img1)
    draw_base(d1)
    draw_progress_dots(d1, 0, TOTAL_SLIDES)
    draw_header(d1, script_data)
    d1.rounded_rectangle([80, 420, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)
    
    # Urgent Hook Badge
    d1.rounded_rectangle([110, 460, 970, 580], radius=16, fill="#991B1B", outline="#FBBF24", width=3)
    wrapped_hook = textwrap.fill(clean_hindi_postal_terms(script_data["visual_hook_badge"]), width=22)
    draw_mixed_multiline(d1, 150, 485, wrapped_hook, font_hook, font_hook_eng, "#FEF08A", line_height=42)

    # Intriguing question teaser
    d1.rounded_rectangle([110, 610, 970, 780], radius=16, fill="#0B132B", outline="#38BDF8", width=2)
    draw_mixed_line(d1, 140, 630, "🎯 आज का परीक्षा चैलेंज:", font_h2, font_h2_eng, "#38BDF8")
    wrapped_q_teaser = textwrap.fill(clean_hindi_postal_terms(script_data["question"]), width=26)
    draw_mixed_multiline(d1, 140, 680, wrapped_q_teaser, font_opt, font_opt_eng, "#F8FAFC", line_height=36)

    paste_safe_asset(img1, QUIZ_3D_PATH, pos=(390, 830), size=(300, 380))

    d1.rounded_rectangle([110, 1260, 970, 1370], radius=16, fill="#064E3B", outline="#34D399", width=2)
    d1.text((150, 1298), ">> अंत तक देखें, सही उत्तर और नियम समझें!", fill="#D1FAE5", font=font_label)
    draw_footer_cta(d1)
    img1.save("slide_1.png")
    slide_filenames.append("slide_1.png")

    # ---------------- SLIDE 2: DIRECT QUESTION ----------------
    img2 = Image.new("RGB", (1080, 1920), color="#060A17")
    d2 = ImageDraw.Draw(img2)
    draw_base(d2)
    draw_progress_dots(d2, 1, TOTAL_SLIDES)
    draw_header(d2, script_data)
    d2.rounded_rectangle([80, 420, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=2)
    
    d2.rounded_rectangle([110, 460, 520, 520], radius=12, fill="#0B132B")
    d2.text((140, 472), "🎯 विभागीय परीक्षा प्रश्न:", fill="#FBBF24", font=font_label)
    
    wrapped_q = textwrap.fill(clean_hindi_postal_terms(script_data["question"]), width=23)
    draw_mixed_multiline(d2, 120, 560, wrapped_q, font_title, font_title_eng, "#FFFFFF", line_height=52)
    
    paste_safe_asset(img2, BOOK_3D_PATH, pos=(390, 920), size=(300, 380))

    d2.rounded_rectangle([110, 1360, 970, 1460], radius=16, fill="#0B132B", outline="#F59E0B", width=2)
    d2.text((150, 1395), "अगली स्लाइड में विकल्प देखें और जवाब दें...", fill="#FDE047", font=font_label)
    draw_footer_cta(d2)
    img2.save("slide_2.png")
    slide_filenames.append("slide_2.png")

    # ---------------- SLIDE 3: OPTIONS & ENGAGEMENT ----------------
    img3 = Image.new("RGB", (1080, 1920), color="#060A17")
    d3 = ImageDraw.Draw(img3)
    draw_base(d3)
    draw_progress_dots(d3, 2, TOTAL_SLIDES)
    draw_header(d3, script_data, title_override="परीक्षा क्विज: सही विकल्प चुनें")
    d3.rounded_rectangle([80, 420, 1000, 1550], radius=24, fill="#1C2541", outline="#FBBF24", width=2)
    
    d3.rounded_rectangle([110, 450, 620, 505], radius=10, fill="#0B132B")
    d3.text((140, 462), "🤔 अपना जवाब कमेंट में लिखें:", fill="#38BDF8", font=font_label)

    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    opt_y = 530
    for idx, opt in enumerate(opts):
        letter_char = chr(65 + idx)
        d3.rounded_rectangle([110, opt_y, 970, opt_y + 110], radius=16, fill="#0B132B", outline="#38BDF8", width=2)
        
        # Circle badge for letter
        d3.rounded_rectangle([130, opt_y + 20, 195, opt_y + 90], radius=10, fill="#1E3A8A")
        d3.text((148, opt_y + 28), letter_char, fill="#93C5FD", font=font_h2_eng)
        
        wrapped_opt = textwrap.fill(clean_hindi_postal_terms(opt), width=24)
        draw_mixed_multiline(d3, 220, opt_y + 25, wrapped_opt, font_body, font_body_eng, "#FFFFFF", line_height=38)
        opt_y += 135

    # Countdown / Comment prompt
    d3.rounded_rectangle([110, 1100, 970, 1210], radius=18, fill="#7F1D1D", outline="#F87171", width=2)
    d3.text((150, 1135), "👇 3 सेकंड में अपना उत्तर कमेंट करें (A, B, C, D)!", fill="#FEF08A", font=font_h2)

    draw_whatsapp_strip_at(d3, y=1250)
    draw_footer_cta(d3)
    img3.save("slide_3.png")
    slide_filenames.append("slide_3.png")

    # ---------------- SLIDE 4: ANSWER REVEAL & CORE RULE ----------------
    img4 = Image.new("RGB", (1080, 1920), color="#060A17")
    d4 = ImageDraw.Draw(img4)
    draw_base(d4)
    draw_progress_dots(d4, 3, TOTAL_SLIDES)
    draw_header(d4, script_data, title_override="सही उत्तर व आधिकारिक नियम")
    d4.rounded_rectangle([80, 420, 1000, 1550], radius=24, fill="#1C2541", outline="#10B981", width=3)
    
    # Correct Option Card
    d4.rounded_rectangle([110, 450, 970, 620], radius=18, fill="#064E3B", outline="#34D399", width=3)
    draw_checkmark(img4, 175, 535, r=40)
    draw_mixed_line(d4, 240, 480, f"सही उत्तर: विकल्प {letter}", font_title, font_title_eng, "#34D399")
    wrapped_ans = textwrap.fill(clean_hindi_postal_terms(correct_text), width=24)
    draw_mixed_multiline(d4, 240, 540, wrapped_ans, font_h2, font_h2_eng, "#FFFFFF", line_height=38)

    # Explanation Header
    d4.rounded_rectangle([110, 650, 580, 705], radius=10, fill="#0B132B")
    d4.text((140, 662), "📖 डाक घर गाइड का नियम:", fill="#38BDF8", font=font_label)

    # Core Rule Full Text (No truncation!)
    wrapped_s1 = textwrap.fill(clean_hindi_postal_terms(script_data['sen1']), width=23)
    draw_mixed_multiline(d4, 120, 730, wrapped_s1, font_body, font_body_eng, "#F8FAFC", line_height=48)

    paste_safe_asset(img4, POSTBOX_3D_PATH, pos=(400, 1140), size=(280, 360))
    draw_footer_cta(d4)
    img4.save("slide_4.png")
    slide_filenames.append("slide_4.png")

    # ---------------- SLIDE 5: EXAM TRAP / CONDITION ----------------
    img5 = Image.new("RGB", (1080, 1920), color="#060A17")
    d5 = ImageDraw.Draw(img5)
    draw_base(d5)
    draw_progress_dots(d5, 4, TOTAL_SLIDES)
    draw_header(d5, script_data, title_override="परीक्षा में फंसाने वाला बिंदु")
    d5.rounded_rectangle([80, 420, 1000, 1550], radius=24, fill="#1C2541", outline="#F87171", width=2)
    
    d5.rounded_rectangle([110, 450, 620, 505], radius=10, fill="#7F1D1D")
    d5.text((140, 462), "⚠️ ध्यान दें: मुख्य अपवाद / शर्त:", fill="#FEF08A", font=font_label)

    # Trap Explanation Full Text (No truncation!)
    wrapped_s2 = textwrap.fill(clean_hindi_postal_terms(script_data['sen2']), width=23)
    draw_mixed_multiline(d5, 120, 540, wrapped_s2, font_body, font_body_eng, "#FFFFFF", line_height=48)

    # Important exam note card
    d5.rounded_rectangle([110, 900, 970, 1060], radius=16, fill="#0B132B", outline="#FBBF24", width=2)
    d5.text((140, 925), "💡 परीक्षार्थी ध्यान रखें:", fill="#FBBF24", font=font_label)
    d5.text((140, 975), "हल्के से शब्द बदलने पर विकल्प बदल जाता है!", fill="#93C5FD", font=font_opt)

    draw_whatsapp_strip_at(d5, y=1110)
    draw_footer_cta(d5)
    img5.save("slide_5.png")
    slide_filenames.append("slide_5.png")

    # ---------------- SLIDE 6: SCORE & CTA ----------------
    img6 = Image.new("RGB", (1080, 1920), color="#060A17")
    d6 = ImageDraw.Draw(img6)
    draw_base(d6)
    draw_progress_dots(d6, 5, TOTAL_SLIDES)
    draw_header(d6, script_data, title_override="रिजल्ट & अगली तैयारी")
    d6.rounded_rectangle([80, 420, 1000, 1550], radius=24, fill="#1C2541", outline="#10B981", width=3)
    
    # Did you get it right?
    d6.rounded_rectangle([110, 460, 970, 580], radius=16, fill="#064E3B", outline="#34D399", width=2)
    d6.text((150, 485), "🔥 क्या आपका जवाब सही निकला?", fill="#FFFFFF", font=font_title)
    d6.text((150, 535), "कमेंट बॉक्स में 'YES' या 'NO' जरूर लिखें!", fill="#FDE047", font=font_h2)

    # WhatsApp Offer Card
    draw_whatsapp_strip_at(d6, y=620)

    # Next part teaser
    d6.rounded_rectangle([110, 780, 970, 900], radius=16, fill="#0B132B", outline="#38BDF8", width=2)
    d6.text((140, 810), f"अगला भाग ({script_data['clause_name']}) जल्द आ रहा है!", fill="#38BDF8", font=font_h2)
    d6.text((140, 855), "नोटिफिकेशन पाने के लिए अभी फॉलो करें।", fill="#94A3B8", font=font_opt)

    paste_safe_asset(img6, QUIZ_3D_PATH, pos=(390, 960), size=(300, 380))
    draw_footer_cta(d6)
    img6.save("slide_6.png")
    slide_filenames.append("slide_6.png")

    # ---------------- FFMPEG ASSEMBLY ----------------
    FPS = 30
    inputs = []
    filter_parts = ""
    for i, fname in enumerate(slide_filenames):
        inputs.extend(["-i", fname])
        safe_dur = max(1.0, durations[i])
        frames = max(1, round(safe_dur * FPS))
        fade_d = min(0.2, safe_dur / 5)
        fade_out_start = max(0.0, safe_dur - fade_d)
        settle_frames = max(1, min(8, frames // 3))
        
        # Subtle, stable zoom that preserves top and bottom UI
        zoom_expr = (
            f"if(lte(on,{settle_frames}),1.03-(0.03*on/{settle_frames}),"
            f"min(1.0+0.0005*(on-{settle_frames}),1.03))"
        )
        filter_parts += (
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            f"zoompan=z='{zoom_expr}':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='0':s=1080x1920:fps={FPS},"
            f"fade=t=in:st=0:d={fade_d},fade=t=out:st={fade_out_start}:d={fade_d},"
            f"format=yuv420p[v{i}]; "
        )

    concat_str = "".join([f"[v{i}]" for i in range(len(slide_filenames))])
    TOTAL_VIDEO_DUR = sum(max(1.0, d) for d in durations)
    video_filter = (
        f"{filter_parts}{concat_str}concat=n={len(slide_filenames)}:v=1:a=0,"
        f"drawbox=x=0:y=0:w='iw*min(t/{TOTAL_VIDEO_DUR},1)':h=12:color=#F43F5E:t=fill,"
        f"format=yuv420p[v]"
    )

    cmd = ["ffmpeg", "-y", *inputs, "-i", "final_master.mp3"]
    voice_idx = len(slide_filenames)

    full_filter = f"{video_filter}; [{voice_idx}:a]aresample=48000,aformat=channel_layouts=stereo[a]"
    cmd.extend(["-filter_complex", full_filter, "-map", "[v]", "-map", "[a]"])
    cmd.extend([
        "-c:v", "libx264", "-preset", "medium", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-shortest", output_video
    ])

    subprocess.run(cmd, check=True)
    print(f"✅ High-Retention Reel Created: {output_video}", flush=True)

# --- MAIN RUNNER ---
if __name__ == "__main__":
    st = load_progress_state()
    print(f"📌 Generating Target: Clause {st['clause_no']} (Part {st['current_part']}/{st['total_parts']})", flush=True)
    
    script_data = generate_clause_script(st)
    render_and_sync_video(script_data, OUTPUT_VIDEO)

    # Save to generated_reels folder
    os.makedirs("generated_reels", exist_ok=True)
    target_reel_path = os.path.join("generated_reels", f"reel_clause_{st['clause_no']}_part_{st['current_part']}.mp4")
    with open(OUTPUT_VIDEO, "rb") as src, open(target_reel_path, "wb") as dst:
        dst.write(src.read())
    print(f"✅ Reel saved: {target_reel_path}", flush=True)

    advance_progress_state(st)
    print("✅ Automation pipeline successfully updated.", flush=True)
