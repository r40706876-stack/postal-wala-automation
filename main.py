import os
import glob
import json
import time
import asyncio
import subprocess
import requests
import textwrap
from PIL import Image, ImageDraw, ImageFont
from groq import Groq
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

# --- Official India Post PO Guide Part 1 Master Catalog ---
POSTAL_CLAUSE_CATALOG = {
    1: {
        "name": "डाक विभाग का नियंत्रण व संगठन",
        "total_parts": 2,
        "part_1_focus": "संचार मंत्रालय के प्रशासनिक नियंत्रण, महानिदेशक (DG) शीर्ष प्रमुख, मुख्यालय डाक भवन नई दिल्ली।",
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
        "part_1_focus": "महानिदेशक द्वारा स्थापना और कार्य समय रात 8:30 बजे तक बढ़ाने का विशेष अधिकार।",
        "part_2_focus": "रविवार और डाक अवकाश पर सुबह 10 से शाम 5 बजे तक कार्य, केवल सीमित बुकिंग और टिकट बिक्री।"
    },
    4: {
        "name": "मोबाइल डाकघर",
        "total_parts": 1,
        "part_1_focus": "बड़े शहरों में देर शाम तक डाक बुकिंग सुविधा, कोई बचत बैंक या मनीऑर्डर कार्य नहीं होता।"
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
        "part_1_focus": "सभी वितरण डाकघरों में सुविधा, किराएदार द्वारा थैला लाने-ले जाने के नियम।",
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

# --- Font Management ---
def ensure_fonts():
    if not os.path.exists(DEV_FONT_PATH):
        print("📥 Downloading Noto Sans Devanagari font...", flush=True)
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        r = requests.get(url, timeout=30)
        with open(DEV_FONT_PATH, "wb") as f:
            f.write(r.content)
        print("✅ Font cached locally.", flush=True)

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
    state = {
        "clause_no": 2,
        "current_part": 1,
        "total_parts": 2
    }
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

# --- AI Script Generation ---
def generate_clause_script(state):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY missing in GitHub Secrets!")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
        "Content-Type": "application/json"
    }

    current_clause = state.get("clause_no", 2)
    current_part = state.get("current_part", 1)

    clause_info = POSTAL_CLAUSE_CATALOG.get(current_clause, POSTAL_CLAUSE_CATALOG[2])
    clause_name = clause_info["name"]
    total_parts = clause_info["total_parts"]
    part_focus = clause_info.get(f"part_{current_part}_focus", clause_info.get("part_1_focus", ""))

    prompt = f"""
    You are the Senior Chief Instructor for India Post Departmental Examinations (MTS, Postman, Mail Guard, Postal Assistant) running 'Postal Wala'.

    EXACT TOPIC TO TEACH:
    - Book: 'Post Office Guide Part 1' (पोस्ट ऑफिस गाइड भाग 1)
    - Clause Number: क्लॉज {current_clause}
    - Clause Official Title: {clause_name}
    - Part: भाग {current_part} (कुल {total_parts} भाग)
    - Sub-Rule Focus: "{part_focus}"

    MANDATORY SCRIPT & LANGUAGE RULES:
    1. Pure, flawless, official Devanagari Hindi. Zero grammatical errors, complete and natural sentences.
    2. Write exactly 3 authoritative teaching sentences (SEN1, SEN2, SEN3) about this specific sub-rule, each ~22-26 words long.
    3. EXACT VOICE PACING (CRITICAL):
       - The voiceover MUST be strictly between 115 and 122 words total.
       - It will naturally speak in 51-53 seconds. Do not exceed this length.
    4. MANDATORY INTRO & OUTRO SEQUENCE:
       - "नमस्कार साथियों! पोस्ट ऑफिस गाइड भाग 1 के क्लॉज {current_clause}, {clause_name} के भाग {current_part} में आपका स्वागत है, जिसे हम कुल {total_parts} भागों में पूरा करेंगे।"
       - "आज का महत्वपूर्ण प्रश्न है: [Question]?"
       - "इसका सही उत्तर जानने के लिए वीडियो में अंत तक बने रहें!"
       - [Explain SEN1, SEN2, and SEN3 calmly]
       - "तो दोस्तों, इसका सही उत्तर कमेंट्स में जरूर बताएं!"
       - If {current_part} < {total_parts}: "इस क्लॉज के अगले भाग को देखने के लिए अभी फॉलो कर लें!"
       - End with: "GDS to MTS, Postman और P.A. कोर्स हेतु स्क्रीन पर दिए गए नंबर पर WhatsApp करें।"
       - DO NOT speak the digits of the phone number.
       - DO NOT reveal or speak the correct answer.

    OUTPUT FORMAT (Do NOT use brackets in values):
    SEN1: [Rich Hindi sentence 1, ~24 words]
    SEN2: [Rich Hindi sentence 2, ~24 words]
    SEN3: [Rich Hindi sentence 3, ~24 words]
    QUESTION: [1 high-yield exam question in Hindi based strictly on this rule]
    OPT_A: [Option A]
    OPT_B: [Option B]
    OPT_C: [Option C]
    OPT_D: [Option D]
    CORRECT: [A/B/C/D]
    VOICEOVER: [Exact voiceover text strictly 115 to 122 words]
    CAPTION: [Instagram caption with #PostalWala #POGuidePart1 #Clause{current_clause} #MTSExam #PostmanExam]
    """

    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 850
    }

    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
    res_json = res.json()

    if res.status_code != 200 or "choices" not in res_json:
        raise RuntimeError(f"Groq API Error: {res_json}")

    raw_text = res_json["choices"][0]["message"]["content"].strip()

    data = {
        "clause_no": current_clause,
        "clause_name": clause_name,
        "part_no": current_part,
        "total_parts": total_parts,
        "sen1": "भारतीय डाक विभाग के अंतर्गत डाकघरों को मुख्य रूप से तीन श्रेणियों में विभाजित किया गया है, जिन्हें प्रधान डाकघर, उप डाकघर और शाखा डाकघर कहते हैं।",
        "sen2": "प्रधान डाकघर अपने क्षेत्राधिकार के सभी उप डाकघरों और शाखा डाकघरों का मुख्य लेखा कार्यालय यानी चीफ अकाउंट ऑफिस के रूप में कार्य करता है।",
        "sen3": "प्रथम श्रेणी के प्रधान डाकघर का प्रभारी राजपत्रित पोस्टमास्टर होता है, जो डाकघरों के अधीक्षक के समान प्रशासनिक व वित्तीय शक्तियां प्रयोग करता है।",
        "question": "अपने अधीनस्थ डाकघरों के लिए मुख्य लेखा कार्यालय के रूप में कौन कार्य करता है?",
        "opt_a": "प्रधान डाकघर",
        "opt_b": "उप डाकघर",
        "opt_c": "शाखा डाकघर",
        "opt_d": "मंडल कार्यालय",
        "correct": "A",
        "voiceover": f"नमस्कार साथियों! पोस्ट ऑफिस गाइड भाग 1 के क्लॉज {current_clause}, {clause_name} के भाग {current_part} में आपका स्वागत है, जिसे हम कुल {total_parts} भागों में पूरा करेंगे। आज का महत्वपूर्ण प्रश्न है: अपने अधीनस्थ डाकघरों के लिए मुख्य लेखा कार्यालय के रूप में कौन कार्य करता है? इसका सही उत्तर जानने के लिए वीडियो में अंत तक बने रहें! भारतीय डाक विभाग में डाकघरों को तीन श्रेणियों में बांटा गया है: प्रधान डाकघर, उप डाकघर और शाखा डाकघर। प्रधान डाकघर अपने अधीनस्थ सभी डाकघरों का मुख्य लेखा कार्यालय होता है। प्रथम श्रेणी प्रधान डाकघर का प्रभारी राजपत्रित पोस्टमास्टर होता है। तो दोस्तों, इसका सही उत्तर कमेंट्स में बताएं! अगले भाग के लिए अभी फॉलो करें, और विभागीय कोर्स हेतु स्क्रीन पर दिए नंबर पर WhatsApp करें।",
        "caption": f"पीओ गाइड भाग 1 क्लॉज {current_clause} संपूर्ण विश्लेषण #PostalWala #POGuidePart1 #Clause{current_clause} #MTSExam"
    }

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

def advance_progress_state(state, data):
    cur_part = data.get("part_no", state.get("current_part", 1))
    total_parts = data.get("total_parts", state.get("total_parts", 2))

    if cur_part < total_parts:
        state["current_part"] = cur_part + 1
        state["total_parts"] = total_parts
        print(f"📌 Clause {state['clause_no']} in progress: Next run will do Part {state['current_part']}/{total_parts}", flush=True)
    else:
        # Move to next Clause in Catalog
        catalog_keys = sorted(POSTAL_CLAUSE_CATALOG.keys())
        current_idx = catalog_keys.index(state["clause_no"]) if state["clause_no"] in catalog_keys else 0
        next_idx = (current_idx + 1) % len(catalog_keys)
        state["clause_no"] = catalog_keys[next_idx]
        state["current_part"] = 1
        state["total_parts"] = POSTAL_CLAUSE_CATALOG[state["clause_no"]]["total_parts"]
        print(f"🎉 Clause completed! Next run will start Clause {state['clause_no']} (Part 1)", flush=True)

    save_progress_state(state)

# --- Voice Generation ---
async def generate_voice(text, filename="voice.mp3"):
    communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+0%")
    await communicate.save(filename)

def get_audio_duration(audio_file):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_file]
    output = subprocess.check_output(cmd).decode().strip()
    return float(output)

# --- Video Rendering Engine ---
def create_video_ffmpeg(script_data, audio_file="voice.mp3", output_video="final_reel.mp4"):
    ensure_fonts()
    total_dur = get_audio_duration(audio_file)
    print(f"🎵 Generated Voiceover Duration: {total_dur:.1f} seconds (Target: 50-55s)", flush=True)

    # 58-second hard limit safety guard
    if total_dur > 57.0:
        tempo = round(total_dur / 54.0, 2)
        print(f"⚡ Audio exceeds 57s ({total_dur:.1f}s). Minor adjustment by {tempo}x...", flush=True)
        adjusted_audio = "voice_fast.mp3"
        cmd_speed = ["ffmpeg", "-y", "-i", audio_file, "-filter:a", f"atempo={tempo}", adjusted_audio]
        subprocess.run(cmd_speed, check=True)
        audio_file = adjusted_audio
        total_dur = get_audio_duration(audio_file)

    # 4 Slides: Point 1, Point 2, Point 3, Quiz Slide
    n_slides = 4
    weights = [1.0, 1.0, 1.0, 1.3]
    total_weight = sum(weights)
    durations = [total_dur * (w / total_weight) for w in weights]

    # Typography
    font_brand = get_eng_font(46)
    font_sub = get_eng_font(24)
    font_badge = get_dev_font(24)
    font_title = get_dev_font(34)
    font_h2 = get_dev_font(32)
    font_body = get_dev_font(42)  # Large readable font
    font_label = get_dev_font(26)
    
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

    def draw_footer(draw_obj):
        # 1. WhatsApp Action Banner (Safe Zone: Y=1365 to 1475)
        draw_obj.rounded_rectangle([80, 1365, 1000, 1475], radius=20, fill="#15803D", outline="#22C55E", width=2)
        draw_obj.text((110, 1380), "GDS to MTS | Postman | Mail Guard | P.A.", fill="#FEF08A", font=font_wa_eng)
        draw_obj.text((110, 1425), "कोर्स व फ्री मॉक टेस्ट हेतु व्हाट्सएप: 8989971379", fill="#FFFFFF", font=font_wa_dev)

        # 2. Follow Banner (Safe Zone: Y=1495 to 1575)
        draw_obj.rounded_rectangle([80, 1495, 1000, 1575], radius=20, fill="#E11D48")
        draw_obj.text((120, 1520), "पूरी तैयारी के लिए फॉलो करें:", fill="#FFFFFF", font=font_cta_hin)
        draw_obj.text((610, 1520), "@POSTAL_WALA", fill="#FFFFFF", font=font_cta_eng)

    # 100% Pure Devanagari Badge (Zero Tofu Boxes)
    badge_text = f"पीओ गाइड भाग 1  •  क्लॉज {script_data['clause_no']}"
    clause_title = f"{script_data['clause_name']} (भाग {script_data['part_no']}/{script_data['total_parts']})"

    sentences = [script_data["sen1"], script_data["sen2"], script_data["sen3"]]
    slide_filenames = []

    # Slides 1 to 3 (Core Points)
    for idx, sentence in enumerate(sentences, 1):
        img = Image.new("RGB", (1080, 1920), color="#0F172A")
        d = ImageDraw.Draw(img)
        draw_base(d)

        # Top Header Box
        d.rounded_rectangle([80, 180, 1000, 340], radius=20, fill="#0F172A", outline="#38BDF8", width=2)
        # Golden Badge
        d.rounded_rectangle([105, 195, 590, 240], radius=10, fill="#F59E0B")
        d.text((120, 202), badge_text, fill="#000000", font=font_badge)
        d.text((110, 255), textwrap.fill(clause_title, width=30), fill="#FFFFFF", font=font_title)

        # Explanation Box
        d.rounded_rectangle([80, 360, 1000, 1340], radius=22, fill="#0F172A")
        d.text((110, 385), "विस्तृत नियम विश्लेषण:", fill="#FBBF24", font=font_h2)

        # Inner Content Card
        d.rounded_rectangle([110, 445, 970, 1310], radius=20, fill="#1E293B", outline="#38BDF8", width=2)
        d.text((140, 480), f"महत्वपूर्ण परीक्षा बिंदु #{idx}:", fill="#38BDF8", font=font_label)

        wrapped_text = textwrap.fill(sentence, width=22)
        d.multiline_text((140, 560), wrapped_text, fill="#F8FAFC", font=font_body, spacing=18)

        draw_footer(d)
        fname = f"slide_{idx}.png"
        img.save(fname)
        slide_filenames.append(fname)

    # Slide 4 (Quiz Slide)
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
        box_bg = "#1E293B"
        border_c = "#38BDF8"
        text_c = "#FFFFFF"

        dq.rounded_rectangle([110, oy, 970, oy + 105], radius=16, fill=box_bg, outline=border_c, width=2)
        opt_badge = f"{chr(65+idx)})"
        dq.text((135, oy + 30), opt_badge, fill="#38BDF8", font=font_opt_eng)
        dq.text((205, oy + 28), textwrap.fill(opt, width=24), fill=text_c, font=font_opt_hin)
        oy += 125

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
    print("✅ Meta-Optimized 1080x1920 Instagram Reel Created.", flush=True)

# --- Resumable Instagram Upload ---
def post_reel_to_instagram_multipart(video_file, caption, max_container_attempts=3):
    access_token = os.getenv("IG_ACCESS_TOKEN")
    user_id = os.getenv("IG_USER_ID")

    if not access_token or not user_id:
        raise ValueError("IG_ACCESS_TOKEN ya IG_USER_ID secrets me missing hai!")

    last_error = None
    for container_attempt in range(1, max_container_attempts + 1):
        print(f"--- Reel upload attempt {container_attempt}/{max_container_attempts} ---", flush=True)
        try:
            video_id = _create_reel_container(video_file, caption, user_id, access_token)
            status = _poll_container_status(video_id, access_token)

            if status == "FINISHED":
                _publish_reel(video_id, user_id, access_token)
                return
            else:
                last_error = f"Container ended with non-FINISHED status: {status}"
                print(f"⚠️ {last_error}. Retrying with a brand-new container...", flush=True)
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ Attempt {container_attempt} failed: {last_error}. Retrying...", flush=True)

        if container_attempt < max_container_attempts:
            time.sleep(20)

    raise RuntimeError(f"All {max_container_attempts} attempts failed. Last error: {last_error}")

def _create_reel_container(video_file, caption, user_id, access_token):
    print("Step 1/2: Creating resumable-upload Reel container...", flush=True)
    init_url = GRAPH_API_BASE + str(user_id).strip() + "/media"
    data = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "access_token": access_token
    }
    r = requests.post(init_url, data=data, timeout=60)

    if r.status_code != 200:
        raise RuntimeError(f"Container init fail hua: {r.text}")

    init_data = r.json()
    video_id = init_data.get("id")

    if not video_id:
        raise RuntimeError(f"Container ID invalid response: {init_data}")

    # Meta Sync Pause
    print(f"Container created with ID: {video_id}. Meta sync ke liye 5 sec wait kar rahe hain...", flush=True)
    time.sleep(5)

    print(f"Uploading video bytes to rupload.facebook.com...", flush=True)
    file_size = os.path.getsize(video_file)
    upload_url = RUPLOAD_BASE + str(video_id).strip()
    upload_headers = {
        "Authorization": f"OAuth {access_token}",
        "offset": "0",
        "file_size": str(file_size),
    }

    with open(video_file, "rb") as vf:
        up_r = requests.post(upload_url, headers=upload_headers, data=vf, timeout=600)

    if up_r.status_code != 200:
        raise RuntimeError(f"Video byte upload fail hua: {up_r.text}")

    up_json = up_r.json()
    if not up_json.get("success"):
        raise RuntimeError(f"Video byte upload did not report success: {up_json}")

    print("Step 2/2: Video bytes uploaded successfully. Waiting for Instagram processing...", flush=True)
    return video_id

def _poll_container_status(video_id, access_token, max_checks=40, wait_seconds=15):
    status_url = GRAPH_API_BASE + str(video_id).strip()

    for attempt in range(max_checks):
        time.sleep(wait_seconds)

        try:
            status_res = requests.get(
                status_url,
                params={"fields": "status_code,status", "access_token": access_token},
                timeout=30
            ).json()
        except Exception as e:
            print(f"Polling network warning (will retry): {e}", flush=True)
            continue

        status = status_res.get("status_code")
        print(f"Check {attempt + 1}: Status -> {status}", flush=True)

        if status == "FINISHED":
            return "FINISHED"
        elif status in ["ERROR", "EXPIRED"]:
            print(f"❌ Instagram reported a definitive failure: {status_res}", flush=True)
            return status

    return "TIMEOUT"

def _publish_reel(video_id, user_id, access_token):
    print("Publishing Reel...", flush=True)
    publish_url = GRAPH_API_BASE + str(user_id).strip() + "/media_publish"
    pub_res = requests.post(publish_url, data={"creation_id": video_id, "access_token": access_token}, timeout=30).json()

    if "id" in pub_res:
        print(f"🎉 Reel successfully published on Instagram! Post ID: {pub_res['id']}", flush=True)
    else:
        raise RuntimeError(f"Publish fail hua: {pub_res}")

# --- Execution Entry Point ---
if __name__ == "__main__":
    print("🚀 Postal Wala Zero-Error Pipeline Starting...", flush=True)

    state = load_progress_state()
    print(f"📋 Current Tracking -> Clause: {state.get('clause_no', 2)}, Part: {state.get('current_part', 1)}", flush=True)

    script_data = generate_clause_script(state)
    print(f"✅ Generated Script: क्लॉज {script_data['clause_no']} - {script_data['clause_name']} (भाग {script_data['part_no']}/{script_data['total_parts']})", flush=True)

    asyncio.run(generate_voice(script_data["voiceover"], AUDIO_OUTPUT))
    print("✅ Voiceover Ready with Natural Pacing.", flush=True)

    create_video_ffmpeg(script_data, AUDIO_OUTPUT, OUTPUT_VIDEO)

    post_reel_to_instagram_multipart(OUTPUT_VIDEO, script_data.get("caption", ""))

    advance_progress_state(state, script_data)
