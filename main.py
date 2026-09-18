import os
import glob
import json
import time
import asyncio
import subprocess
import requests
import textwrap
from PIL import Image, ImageDraw, ImageFont
import edge_tts

# --- Environment Variables ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

GRAPH_API_BASE = "".join(["http", "s://", "graph.", "facebook", ".com/v19.0/"])
RUPLOAD_BASE = "https://rupload.facebook.com/ig-api-upload/v19.0/"

STATE_FILE = "progress_state.json"
DEV_FONT_PATH = "NotoSansDevanagari-Bold.ttf"
AUDIO_OUTPUT = "voice.mp3"
OUTPUT_VIDEO = "final_reel.mp4"
VOICE_NAME = "hi-IN-SwaraNeural"

# Assets Directory
ASSETS_DIR = "assets"
BOOK_3D_PATH = os.path.join(ASSETS_DIR, "3d_book.png")
POSTBOX_3D_PATH = os.path.join(ASSETS_DIR, "3d_postbox.png")
QUIZ_3D_PATH = os.path.join(ASSETS_DIR, "3d_quiz.png")

# Cross-version Pillow Compatibility
RESAMPLE_MODE = getattr(Image, "Resampling", Image).LANCZOS

# --- Official PO Guide Part 1 Master Catalog ---
POSTAL_CLAUSE_CATALOG = {
    1: {
        "name": "डाक विभाग का नियंत्रण व संगठन",
        "total_parts": 2,
        "part_1_focus": "संचार मंत्रालय के अधीन, महानिदेशक डाक सेवा शीर्ष प्रशासनिक प्रमुख, मुख्यालय डाक भवन नई दिल्ली।",
        "part_2_focus": "डाक सेवा बोर्ड (PSB) की संरचना: चेयरमैन (सचिव), 6 पूर्णकालिक सदस्य और बोर्ड सचिव के दायित्व।"
    },
    2: {
        "name": "डाकघरों के प्रकार और श्रेणियां",
        "total_parts": 2,
        "part_1_focus": "डाकघर की 3 श्रेणियां (HO, SO, BO)। प्रधान डाकघर (HO) मुख्य लेखा कार्यालय होता है और प्रथम श्रेणी HO का प्रभारी राजपत्रित पोस्टमास्टर होता है।",
        "part_2_focus": "उप डाकघर (SO) और शाखा डाकघर (BO)। ग्रामीण क्षेत्रों में BO के कार्य के घंटे न्यूनतम 4 और अधिकतम 5 घंटे, प्रभारी शाखा डाकपाल (BPM)।"
    },
    3: {
        "name": "रात्रि डाकघर के नियम",
        "total_parts": 2,
        "part_1_focus": "महानिदेशक (DG) द्वारा स्थापना और कार्य समय रात 8:30 बजे तक बढ़ाने का विशेष अधिकार।",
        "part_2_focus": "रविवार और राष्ट्रीय डाक अवकाश पर सुबह 10 से शाम 5 बजे तक कार्य, केवल सीमित बुकिंग और टिकट बिक्री।"
    },
    4: {
        "name": "मोबाइल डाकघर",
        "total_parts": 1,
        "part_1_focus": "बड़े शहरों में देर शाम तक डाक व पार्सल बुकिंग सुविधा, कोई बचत बैंक या मनीऑर्डर कार्य नहीं होता।"
    },
    55: {
        "name": "पोस्ट बॉक्स के नियम व किराया",
        "total_parts": 3,
        "part_1_focus": "केवल पूरी तरह प्रीपेड अपंजीकृत पत्रों के लिए, डाकपाल के विवेक पर आवंटन।",
        "part_2_focus": "वार्षिक किराया ₹150 (केवल बॉक्स) और ₹250 (बॉक्स व बैग दोनों), त्रैमासिक किराया ₹50 और ₹80।",
        "part_3_focus": "ताला-चाबी की सुरक्षा, चाबी खोने पर सूचना और नया ताला लगाने का निर्धारित शुल्क।"
    },
    56: {
        "name": "पोस्ट बैग एवं वितरण टिकट",
        "total_parts": 2,
        "part_1_focus": "सभी वितरण डाकघरों में सुविधा, किराएदार द्वारा मजबूत थैला लाने-ले जाने के नियम।",
        "part_2_focus": "डाक खिड़की से डाक प्राप्त करने के लिए अधिकृत प्रतिनिधि को वितरण टिकट (Delivery Ticket) प्रस्तुत करना अनिवार्य।"
    }
}

def clean_text(text):
    if not text:
        return ""
    text = text.strip().strip("[](){}\"'`")
    text = "".join(c for c in text if ord(c) < 0x10000)
    return text.strip()

def clean_hindi_postal_terms(text):
    if not text:
        return ""
    replacements = {
        "पेन्टियों": "पत्र-पेटियों",
        "पेन्टी": "पत्र-पेटी",
        "घंटी वाली प्लेटें": "घंटे वाली प्लेटें",
        "घंटी वाली प्लेट": "घंटे वाली प्लेट",
        "घंटी वाली": "घंटे वाली",
        "नित्य पत्र": "वित्तीय वर्ष",
        "नित्य वर्ष": "वित्तीय वर्ष",
        "कतलेरी कटेट": "वितरण टिकट",
        "कटलेरी कटेट": "वितरण टिकट",
        "कतलेरी": "वितरण टिकट",
        "कटेट": "टिकट"
    }
    for bad_w, good_w in replacements.items():
        text = text.replace(bad_w, good_w)
    return clean_text(text)

# --- 100% Offline 3D Graphic Renderer (Zero External Dependency) ---
def ensure_auto_icons():
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # 1. 3D PO Guide Rulebook (Slide 1)
    if not os.path.exists(BOOK_3D_PATH):
        try:
            bk = Image.new("RGBA", (300, 420), (0, 0, 0, 0))
            db = ImageDraw.Draw(bk)
            # Soft Shadow
            db.ellipse([40, 360, 260, 400], fill="#0A0F1D")
            # Back Cover Edge
            db.rounded_rectangle([55, 60, 245, 360], radius=14, fill="#1E3A8A")
            # Pages Stack (Cream paper look)
            db.rounded_rectangle([75, 65, 240, 350], radius=8, fill="#F8FAFC", outline="#CBD5E1", width=2)
            # Front Cover
            db.rounded_rectangle([55, 55, 230, 350], radius=12, fill="#1D4ED8", outline="#60A5FA", width=3)
            # Golden Spine Band
            db.rectangle([55, 55, 82, 350], fill="#F59E0B")
            db.rectangle([78, 55, 84, 350], fill="#FDE047")
            # Golden Emblem on Book
            db.ellipse([115, 150, 185, 220], fill="#F59E0B", outline="#FEF08A", width=3)
            db.polygon([(150, 162), (155, 178), (172, 178), (158, 188), (163, 204), (150, 194), (137, 204), (142, 188), (128, 178), (145, 178)], fill="#FFFFFF")
            # Red Ribbon Bookmark
            db.polygon([(140, 330), (162, 330), (162, 385), (151, 372), (140, 385)], fill="#DC2626")
            bk.save(BOOK_3D_PATH, "PNG")
        except Exception:
            pass

    # 2. 3D Red Pillar Postbox (Slide 2 & 3)
    if not os.path.exists(POSTBOX_3D_PATH):
        try:
            box = Image.new("RGBA", (300, 420), (0, 0, 0, 0))
            d = ImageDraw.Draw(box)
            # Ground Shadow
            d.ellipse([50, 375, 250, 410], fill="#0A0F1D")
            # Postbox Base
            d.rounded_rectangle([65, 340, 235, 385], radius=15, fill="#1E293B", outline="#475569", width=3)
            # Main Red Cylinder (3D Shading)
            d.rounded_rectangle([75, 120, 225, 350], radius=12, fill="#991B1B")
            d.rounded_rectangle([95, 120, 205, 350], radius=8, fill="#DC2626")
            d.rounded_rectangle([115, 120, 160, 350], radius=6, fill="#EF4444")
            # Golden Postal Ribbon
            d.rectangle([75, 165, 225, 182], fill="#F59E0B")
            d.rectangle([115, 165, 160, 182], fill="#FDE047")
            # Letter Slot with envelope
            d.rounded_rectangle([90, 195, 210, 215], radius=5, fill="#0F172A")
            d.rectangle([110, 200, 190, 225], fill="#FFFFFF", outline="#CBD5E1", width=1)
            d.polygon([(110, 200), (150, 215), (190, 200)], fill="#E2E8F0")
            # Collection Keyhole
            d.ellipse([140, 270, 160, 290], fill="#F59E0B", outline="#78350F", width=2)
            d.ellipse([147, 277, 153, 283], fill="#0F172A")
            # 3D Dome Top
            d.chord([70, 40, 230, 150], start=180, end=0, fill="#B91C1C", outline="#F87171", width=3)
            d.chord([95, 50, 205, 140], start=180, end=0, fill="#EF4444")
            d.ellipse([135, 30, 165, 55], fill="#F59E0B", outline="#FEF08A", width=2)
            box.save(POSTBOX_3D_PATH, "PNG")
        except Exception:
            pass

    # 3. 3D Golden Trophy (Slide 4: Quiz)
    if not os.path.exists(QUIZ_3D_PATH):
        try:
            q = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
            dq = ImageDraw.Draw(q)
            dq.ellipse([50, 355, 250, 395], fill="#0A0F1D")
            dq.rounded_rectangle([75, 320, 225, 365], radius=10, fill="#1E293B", outline="#38BDF8", width=3)
            dq.rectangle([135, 240, 165, 325], fill="#D97706")
            dq.rectangle([142, 240, 158, 325], fill="#FDE047")
            dq.chord([60, 70, 240, 250], start=0, end=180, fill="#D97706", outline="#B45309", width=4)
            dq.chord([80, 75, 220, 240], start=0, end=180, fill="#F59E0B")
            dq.chord([110, 85, 190, 230], start=0, end=180, fill="#FEF08A")
            dq.arc([35, 95, 95, 175], start=90, end=270, fill="#FBBF24", width=12)
            dq.arc([205, 95, 265, 175], start=270, end=90, fill="#FBBF24", width=12)
            dq.polygon([(150, 115), (157, 137), (180, 137), (162, 152), (169, 174), (150, 160), (131, 174), (138, 152), (120, 137), (143, 137)], fill="#FFFFFF")
            q.save(QUIZ_3D_PATH, "PNG")
        except Exception:
            pass

# --- Font Management ---
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

# --- State Management ---
def load_progress_state():
    state = {"clause_no": 3, "current_part": 1, "total_parts": 2}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state.update(json.load(f))
        except Exception:
            pass
    return state

def save_progress_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"⚠️ Warning saving state: {e}", flush=True)

# --- Script Generation ---
def generate_clause_script(state):
    current_clause = state.get("clause_no", 3)
    current_part = state.get("current_part", 1)

    clause_info = POSTAL_CLAUSE_CATALOG.get(current_clause, POSTAL_CLAUSE_CATALOG[3])
    clause_name = clause_info["name"]
    total_parts = clause_info["total_parts"]
    part_focus = clause_info.get(f"part_{current_part}_focus", clause_info.get("part_1_focus", ""))

    fallback_data = {
        "clause_no": current_clause,
        "clause_name": clause_name,
        "part_no": current_part,
        "total_parts": total_parts,
        "sen1": f"भारतीय डाक विभाग के अनुसार {clause_name} से संबंधित नियम डाक घर गाइड भाग 1 के क्लॉज {current_clause} में परिभाषित हैं।",
        "sen2": f"इस नियम के मुख्य प्रावधान के अंतर्गत {part_focus}",
        "sen3": "विभागीय परीक्षाओं में इस नियम के अधिकार, कार्य समय और संचालन शर्तों पर सीधे प्रश्न पूछे जाते हैं।",
        "question": f"डाक घर गाइड भाग 1 के क्लॉज {current_clause} का संबंध मुख्य रूप से किससे है?",
        "opt_a": clause_name,
        "opt_b": "डाक विभाग का बजट",
        "opt_c": "मनीऑर्डर नियम",
        "opt_d": "इनमें से कोई नहीं",
        "correct": "A",
        "voiceover": f"नमस्कार साथियों! पोस्ट ऑफिस गाइड भाग 1 के क्लॉज {current_clause}, {clause_name} के भाग {current_part} में आपका स्वागत है, जिसे हम कुल {total_parts} भागों में पूरा करेंगे। आज का महत्वपूर्ण प्रश्न है: क्लॉज {current_clause} का संबंध किससे है? इसका सही उत्तर जानने के लिए वीडियो में अंत तक बने रहें! {part_focus} विभागीय परीक्षा में इस नियम से संबंधित प्रश्न अक्सर पूछे जाते हैं। तो दोस्तों, इसका सही उत्तर कमेंट्स में जरूर बताएं! विभागीय परीक्षा में अच्छे नंबर लाने के लिए पोस्टल वाला को अभी फॉलो करें, और पूरे कोर्स हेतु स्क्रीन पर दिए नंबर पर WhatsApp करें।",
        "caption": f"पीओ गाइड भाग 1 क्लॉज {current_clause} संपूर्ण विश्लेषण #PostalWala #POGuidePart1 #Clause{current_clause} #MTSExam #PostmanExam"
    }

    if not GROQ_API_KEY:
        return fallback_data

    prompt = f"""
    You are the Senior Chief Instructor for India Post Departmental Examinations running 'Postal Wala'.
    EXACT TOPIC:
    - Book: 'Post Office Guide Part 1' (पोस्ट ऑफिस गाइड भाग 1)
    - Clause Number: क्लॉज {current_clause}
    - Official Title: {clause_name}
    - Part: भाग {current_part} (कुल {total_parts} भाग)
    - Sub-Rule Focus: "{part_focus}"

    RULES:
    1. Flawless Devanagari Hindi. Complete sentences.
    2. Write exactly 3 authoritative teaching sentences (SEN1, SEN2, SEN3) about this specific rule, each ~22-26 words long.
    3. The voiceover MUST be strictly between 115 and 122 words total (naturally 51-53 seconds).
    4. Follow this voiceover layout strictly:
       - "नमस्कार साथियों! पोस्ट ऑफिस गाइड भाग 1 के क्लॉज {current_clause}, {clause_name} के भाग {current_part} में आपका स्वागत है, जिसे हम कुल {total_parts} भागों में पूरा करेंगे।"
       - "आज का महत्वपूर्ण प्रश्न है: [Question]?"
       - "इसका सही उत्तर जानने के लिए वीडियो में अंत तक बने रहें!"
       - [Explain SEN1, SEN2, and SEN3 calmly]
       - "तो दोस्तों, इसका सही उत्तर कमेंट्स में जरूर बताएं!"
       - "विभागीय परीक्षा में अच्छे नंबर लाने के लिए पोस्टल वाला को अभी फॉलो करें!"
       - End with: "GDS to MTS, Postman और P.A. कोर्स हेतु स्क्रीन पर दिए गए नंबर पर WhatsApp करें।"
       - DO NOT speak the digits of the phone number.
       - DO NOT reveal the correct answer.

    OUTPUT FORMAT:
    SEN1: [Rich Hindi sentence 1, ~24 words]
    SEN2: [Rich Hindi sentence 2, ~24 words]
    SEN3: [Rich Hindi sentence 3, ~24 words]
    QUESTION: [1 high-yield exam question in Hindi]
    OPT_A: [Option A]
    OPT_B: [Option B]
    OPT_C: [Option C]
    OPT_D: [Option D]
    CORRECT: [A/B/C/D]
    VOICEOVER: [Exact voiceover text strictly 115 to 122 words]
    CAPTION: [Instagram caption]
    """

    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"}
        payload = {"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 850}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=25)
        res_json = res.json()

        if res.status_code == 200 and "choices" in res_json:
            raw_text = res_json["choices"][0]["message"]["content"].strip()
            data = fallback_data.copy()

            for line in raw_text.splitlines():
                clean_l = line.strip()
                if clean_l.startswith("SEN1:"):
                    data["sen1"] = clean_hindi_postal_terms(clean_l.replace("SEN1:", ""))
                elif clean_l.startswith("SEN2:"):
                    data["sen2"] = clean_hindi_postal_terms(clean_l.replace("SEN2:", ""))
                elif clean_l.startswith("SEN3:"):
                    data["sen3"] = clean_hindi_postal_terms(clean_l.replace("SEN3:", ""))
                elif clean_l.startswith("QUESTION:"):
                    data["question"] = clean_hindi_postal_terms(clean_l.replace("QUESTION:", ""))
                elif clean_l.startswith("OPT_A:"):
                    data["opt_a"] = clean_hindi_postal_terms(clean_l.replace("OPT_A:", ""))
                elif clean_l.startswith("OPT_B:"):
                    data["opt_b"] = clean_hindi_postal_terms(clean_l.replace("OPT_B:", ""))
                elif clean_l.startswith("OPT_C:"):
                    data["opt_c"] = clean_hindi_postal_terms(clean_l.replace("OPT_C:", ""))
                elif clean_l.startswith("OPT_D:"):
                    data["opt_d"] = clean_hindi_postal_terms(clean_l.replace("OPT_D:", ""))
                elif clean_l.startswith("CORRECT:"):
                    data["correct"] = clean_text(clean_l.replace("CORRECT:", "")).upper()[:1]
                elif clean_l.startswith("VOICEOVER:"):
                    data["voiceover"] = clean_hindi_postal_terms(clean_l.replace("VOICEOVER:", ""))
                elif clean_l.startswith("CAPTION:"):
                    data["caption"] = clean_text(clean_l.replace("CAPTION:", ""))

            return data
    except Exception as e:
        print(f"⚠️ Groq API warning: {e}. Safe fallback active.", flush=True)

    return fallback_data

def advance_progress_state(state, data):
    cur_part = data.get("part_no", state.get("current_part", 1))
    total_parts = data.get("total_parts", state.get("total_parts", 2))

    if cur_part < total_parts:
        state["current_part"] = cur_part + 1
        state["total_parts"] = total_parts
    else:
        catalog_keys = sorted(POSTAL_CLAUSE_CATALOG.keys())
        current_idx = catalog_keys.index(state["clause_no"]) if state["clause_no"] in catalog_keys else 0
        next_idx = (current_idx + 1) % len(catalog_keys)
        state["clause_no"] = catalog_keys[next_idx]
        state["current_part"] = 1
        state["total_parts"] = POSTAL_CLAUSE_CATALOG[state["clause_no"]]["total_parts"]

    save_progress_state(state)

# --- Voice Generation ---
async def generate_voice(text, filename="voice.mp3"):
    communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+0%")
    await communicate.save(filename)

def get_audio_duration(audio_file):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_file]
    output = subprocess.check_output(cmd).decode().strip()
    return float(output)

# --- Video Engine with 3D Assets ---
def create_video_ffmpeg(script_data, audio_file="voice.mp3", output_video="final_reel.mp4"):
    ensure_fonts()
    ensure_auto_icons()

    total_dur = get_audio_duration(audio_file)
    print(f"🎵 Voiceover Duration: {total_dur:.1f}s", flush=True)

    if total_dur > 57.0:
        tempo = round(total_dur / 54.0, 2)
        adjusted_audio = "voice_fast.mp3"
        cmd_speed = ["ffmpeg", "-y", "-i", audio_file, "-filter:a", f"atempo={tempo}", adjusted_audio]
        subprocess.run(cmd_speed, check=True)
        audio_file = adjusted_audio
        total_dur = get_audio_duration(audio_file)

    n_slides = 4
    weights = [1.0, 1.0, 1.0, 1.3]
    total_weight = sum(weights)
    durations = [total_dur * (w / total_weight) for w in weights]

    font_brand = get_eng_font(46)
    font_sub = get_eng_font(24)
    font_badge = get_dev_font(24)
    font_title = get_dev_font(34)
    font_h2 = get_dev_font(32)
    font_body = get_dev_font(42)
    font_label = get_dev_font(26)
    font_trust = get_eng_font(20)
    
    font_cta_hin = get_dev_font(28)
    font_cta_eng = get_eng_font(28)
    font_wa_eng = get_eng_font(26)
    font_wa_dev = get_dev_font(26)
    font_opt_eng = get_eng_font(36)
    font_opt_hin = get_dev_font(34)

    def draw_base(draw_obj):
        draw_obj.rounded_rectangle([45, 50, 1035, 1860], radius=30, fill="#1E293B", outline="#E11D48", width=4)
        draw_obj.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        draw_obj.text((80, 130), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)

        # Trust Pill
        draw_obj.rounded_rectangle([630, 80, 1000, 130], radius=16, fill="#065F46", outline="#34D399", width=2)
        draw_obj.text((655, 93), "✓ 100% OFFICIAL SYLLABUS", fill="#ECFDF5", font=font_trust)

    def draw_footer(draw_obj):
        draw_obj.rounded_rectangle([80, 1365, 1000, 1475], radius=20, fill="#15803D", outline="#22C55E", width=2)
        draw_obj.text((110, 1380), "GDS to MTS | Postman | Mail Guard | P.A.", fill="#FEF08A", font=font_wa_eng)
        draw_obj.text((110, 1425), "कोर्स व फ्री मॉक टेस्ट हेतु व्हाट्सएप: 8989971379", fill="#FFFFFF", font=font_wa_dev)

        draw_obj.rounded_rectangle([80, 1495, 1000, 1575], radius=20, fill="#E11D48")
        draw_obj.text((120, 1520), "पूरी तैयारी के लिए फॉलो करें:", fill="#FFFFFF", font=font_cta_hin)
        draw_obj.text((610, 1520), "@POSTAL_WALA", fill="#FFFFFF", font=font_cta_eng)

    def paste_safe_asset(base_img, path, pos, size=(240, 335)):
        if os.path.exists(path):
            try:
                ic = Image.open(path).convert("RGBA")
                ic = ic.resize(size, RESAMPLE_MODE)
                base_img.paste(ic, pos, ic)
            except Exception:
                pass

    badge_text = f"पीओ गाइड भाग 1  •  क्लॉज {script_data['clause_no']}"
    clause_title = f"{script_data['clause_name']} (भाग {script_data['part_no']}/{script_data['total_parts']})"

    sentences = [script_data["sen1"], script_data["sen2"], script_data["sen3"]]
    slide_filenames = []

    # Slides 1 to 3
    for idx, sentence in enumerate(sentences, 1):
        img = Image.new("RGB", (1080, 1920), color="#0F172A")
        d = ImageDraw.Draw(img)
        draw_base(d)

        d.rounded_rectangle([80, 180, 1000, 340], radius=20, fill="#0F172A", outline="#38BDF8", width=2)
        d.rounded_rectangle([105, 195, 590, 240], radius=10, fill="#F59E0B")
        d.text((120, 202), badge_text, fill="#000000", font=font_badge)
        d.text((110, 255), textwrap.fill(clause_title, width=28), fill="#FFFFFF", font=font_title)

        d.rounded_rectangle([80, 360, 1000, 1340], radius=22, fill="#0F172A")
        d.text((110, 385), "विस्तृत नियम विश्लेषण:", fill="#FBBF24", font=font_h2)

        d.rounded_rectangle([110, 445, 970, 1310], radius=20, fill="#1E293B", outline="#38BDF8", width=2)
        d.text((140, 480), f"महत्वपूर्ण परीक्षा बिंदु #{idx}:", fill="#38BDF8", font=font_label)

        wrapped_text = textwrap.fill(sentence, width=22)
        d.multiline_text((140, 560), wrapped_text, fill="#F8FAFC", font=font_body, spacing=18)

        # Slide 1 gets 3D Rulebook; Slide 2 & 3 get 3D Postbox
        if idx == 1:
            paste_safe_asset(img, BOOK_3D_PATH, pos=(710, 960), size=(240, 335))
        else:
            paste_safe_asset(img, POSTBOX_3D_PATH, pos=(710, 960), size=(240, 335))

        draw_footer(d)
        fname = f"slide_{idx}.png"
        img.save(fname)
        slide_filenames.append(fname)

    # Slide 4: Quiz
    img_quiz = Image.new("RGB", (1080, 1920), color="#0F172A")
    dq = ImageDraw.Draw(img_quiz)
    draw_base(dq)

    dq.rounded_rectangle([80, 180, 1000, 340], radius=20, fill="#0F172A", outline="#FBBF24", width=2)
    dq.rounded_rectangle([105, 195, 590, 240], radius=10, fill="#F59E0B")
    dq.text((120, 202), badge_text, fill="#000000", font=font_badge)
    dq.text((110, 255), "परीक्षा क्विज़: सवाल का सही जवाब दें!", fill="#FFFFFF", font=font_title)

    dq.rounded_rectangle([80, 360, 1000, 1340], radius=22, fill="#0F172A")
    dq.text((110, 385), "आज का सवाल:", fill="#FBBF24", font=font_h2)

    q_wrapped = textwrap.fill(script_data["question"], width=24)
    dq.multiline_text((110, 445), q_wrapped, fill="#F8FAFC", font=font_h2, spacing=12)

    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    oy = 680
    for idx, opt in enumerate(opts):
        dq.rounded_rectangle([110, oy, 970, oy + 105], radius=16, fill="#1E293B", outline="#38BDF8", width=2)
        opt_badge = f"{chr(65+idx)})"
        dq.text((135, oy + 30), opt_badge, fill="#38BDF8", font=font_opt_eng)
        dq.text((205, oy + 28), textwrap.fill(opt, width=24), fill="#FFFFFF", font=font_opt_hin)
        oy += 125

    # 3D Trophy on Quiz Slide
    paste_safe_asset(img_quiz, QUIZ_3D_PATH, pos=(790, 360), size=(170, 225))

    draw_footer(dq)
    img_quiz.save("slide_4.png")
    slide_filenames.append("slide_4.png")

    inputs = []
    filter_parts = ""
    for i, fname in enumerate(slide_filenames):
        inputs.extend(["-i", fname])
        safe_dur = max(1.0, durations[i])
        filter_parts += f"[{i}:v]loop=loop=-1:size=1:start=0,trim=duration={safe_dur}[v{i}]; "

    concat_str = "".join([f"[v{i}]" for i in range(len(slide_filenames))])
    filter_complex = f"{filter_parts}{concat_str}concat=n={len(slide_filenames)}:v=1:a=0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p[v]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-i", audio_file,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", f"{len(slide_filenames)}:a",
        "-c:v", "libx264",
        "-preset", "medium",
        "-profile:v", "main",
        "-level", "4.0",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-g", "60",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-movflags", "+faststart",
        "-shortest", output_video
    ]
    subprocess.run(cmd, check=True)
    print("✅ Meta-Optimized 1080x1920 Reel Created with 3D Assets.", flush=True)

# --- Resumable Instagram Upload ---
def post_reel_to_instagram_multipart(video_file, caption, max_container_attempts=3):
    access_token = os.getenv("IG_ACCESS_TOKEN")
    user_id = os.getenv("IG_USER_ID")

    if not access_token or not user_id:
        raise ValueError("IG_ACCESS_TOKEN ya IG_USER_ID missing!")

    last_error = None
    for container_attempt in range(1, max_container_attempts + 1):
        try:
            video_id = _create_reel_container(video_file, caption, user_id, access_token)
            status = _poll_container_status(video_id, access_token)

            if status == "FINISHED":
                _publish_reel(video_id, user_id, access_token)
                return
            else:
                last_error = f"Status: {status}"
        except Exception as e:
            last_error = str(e)

        if container_attempt < max_container_attempts:
            time.sleep(20)

    raise RuntimeError(f"Upload failed: {last_error}")

def _create_reel_container(video_file, caption, user_id, access_token):
    init_url = GRAPH_API_BASE + str(user_id).strip() + "/media"
    data = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "access_token": access_token
    }
    r = requests.post(init_url, data=data, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Container init fail: {r.text}")

    video_id = r.json().get("id")
    time.sleep(5)

    file_size = os.path.getsize(video_file)
    upload_url = RUPLOAD_BASE + str(video_id).strip()
    upload_headers = {
        "Authorization": f"OAuth {access_token}",
        "offset": "0",
        "file_size": str(file_size),
    }

    with open(video_file, "rb") as vf:
        up_r = requests.post(upload_url, headers=upload_headers, data=vf, timeout=600)

    if up_r.status_code != 200 or not up_r.json().get("success"):
        raise RuntimeError(f"Upload fail: {up_r.text}")

    return video_id

def _poll_container_status(video_id, access_token, max_checks=40, wait_seconds=15):
    status_url = GRAPH_API_BASE + str(video_id).strip()
    for _ in range(max_checks):
        time.sleep(wait_seconds)
        try:
            res = requests.get(status_url, params={"fields": "status_code,status", "access_token": access_token}, timeout=30).json()
            status = res.get("status_code")
            if status == "FINISHED":
                return "FINISHED"
            elif status in ["ERROR", "EXPIRED"]:
                return status
        except Exception:
            continue
    return "TIMEOUT"

def _publish_reel(video_id, user_id, access_token):
    publish_url = GRAPH_API_BASE + str(user_id).strip() + "/media_publish"
    pub_res = requests.post(publish_url, data={"creation_id": video_id, "access_token": access_token}, timeout=30).json()
    if "id" in pub_res:
        print(f"🎉 Reel successfully published on Instagram! Post ID: {pub_res['id']}", flush=True)
    else:
        raise RuntimeError(f"Publish fail: {pub_res}")

# --- Main Entry Point ---
if __name__ == "__main__":
    state = load_progress_state()
    script_data = generate_clause_script(state)

    asyncio.run(generate_voice(script_data["voiceover"], AUDIO_OUTPUT))
    create_video_ffmpeg(script_data, AUDIO_OUTPUT, OUTPUT_VIDEO)
    post_reel_to_instagram_multipart(OUTPUT_VIDEO, script_data.get("caption", ""))
    advance_progress_state(state, script_data)
