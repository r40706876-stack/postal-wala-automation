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

GRAPH_API_BASE = "".join(["http", "s://", "graph.", "facebook", ".com/v19.0/"])
RUPLOAD_BASE = "https://rupload.facebook.com/ig-api-upload/v19.0/"

STATE_FILE = "progress_state.json"
DEV_FONT_PATH = "NotoSansDevanagari-Bold.ttf"
OUTPUT_VIDEO = "final_reel.mp4"
BGM_OUTPUT = "bgm.mp3"
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
        "voice": "लिख कर ले लो! इस 40 सेकंड की रील से विभागीय परीक्षा में आपके 2 नंबर पक्के होने वाले हैं, आइए देखते हैं कैसे!",
        "visual_badge": "लिख कर ले लो! 2 नंबर पक्के"
    },
    {
        "voice": "जीडीएस से एमटीएस और पोस्टमैन परीक्षा में 90% लोग इस एक नियम में गलत उत्तर देकर आते हैं! क्या आप भी वही गलती कर रहे हैं?",
        "visual_badge": "सावधान: 90% लोग फेल होते हैं!"
    },
    {
        "voice": "अगर आप सच में इस बार जीडीएस से प्रमोशन लेने की तैयारी कर रहे हैं, तो पोस्टल वाला के इस सवाल का सही जवाब देकर दिखाइए!",
        "visual_badge": "दम है तो सही उत्तर देकर दिखाओ!"
    },
    {
        "voice": "डाक विभाग की परीक्षाओं में बार-बार दोहराया जाने वाला सबसे पसंदीदा नियम! आज 45 सेकंड में इसे हमेशा के लिए रट लो!",
        "visual_badge": "परीक्षा में बार-बार पूछा जाने वाला नियम"
    },
    {
        "voice": "अगर इस साल जीडीएस की नौकरी से प्रमोशन पाकर पोस्टमैन या पी.ए. बनना है, तो इस रील को 1 सेकंड भी स्किप मत करना!",
        "visual_badge": "जीडीएस से प्रमोशन का पक्का मौका!"
    },
    {
        "voice": "क्या आपको पता है? डाक घर गाइड का यह एक छोटा सा क्लॉज कई लोगों का प्रमोशन रोक देता है! आइए इस नियम को गहराई से समझें!",
        "visual_badge": "चेतावनी: यह नियम प्रमोशन रोक सकता है!"
    }
]

# --- Official PO Guide Part 1 Catalog ---
POSTAL_CLAUSE_CATALOG = {
    1: {"name": "डाक विभाग का नियंत्रण व संगठन", "total_parts": 2, "part_1_focus": "संचार मंत्रालय के अधीन, महानिदेशक डाक सेवा शीर्ष प्रशासनिक प्रमुख, मुख्यालय डाक भवन नई दिल्ली।", "part_2_focus": "डाक सेवा बोर्ड (PSB) की संरचना: चेयरमैन (सचिव), 6 पूर्णकालिक सदस्य और बोर्ड सचिव के दायित्व।"},
    2: {"name": "डाकघरों के प्रकार और श्रेणियां", "total_parts": 2, "part_1_focus": "डाकघर की 3 श्रेणियां (HO, SO, BO)। प्रधान डाकघर (HO) मुख्य लेखा कार्यालय होता है।", "part_2_focus": "उप डाकघर (SO) और शाखा डाकघर (BO)। ग्रामीण क्षेत्रों में BO के कार्य के घंटे न्यूनतम 4 और अधिकतम 5 घंटे।"},
    3: {"name": "रात्रि डाकघर के नियम", "total_parts": 2, "part_1_focus": "महानिदेशक (DG) द्वारा स्थापना और कार्य समय रात 8:30 बजे तक बढ़ाने का विशेष अधिकार।", "part_2_focus": "रविवार और राष्ट्रीय डाक अवकाश पर सुबह 10 से शाम 5 बजे तक कार्य, केवल सीमित सेवाएं।"},
    4: {"name": "मोबाइल डाकघर", "total_parts": 1, "part_1_focus": "बड़े शहरों में देर शाम तक डाक व पार्सल बुकिंग सुविधा, कोई बचत बैंक या मनीऑर्डर कार्य नहीं होता।"},
    5: {"name": "डाकघर के कामकाज के घंटे", "total_parts": 2, "part_1_focus": "सामान्य डाक लेन-देन, रजिस्ट्री बुकिंग, मनीऑर्डर और बचत बैंक के अलग-अलग निर्धारित समय सीमा के नियम।", "part_2_focus": "सार्वजनिक कार्य के घंटे समाप्त होने के बाद लेट फीस के साथ डाक स्वीकार करने के नियम।"},
    6: {"name": "रविवार और डाक अवकाश पर कार्य", "total_parts": 1, "part_1_focus": "रविवार और 16 राजपत्रित अवकाशों पर सामान्य डाकघर पूर्णतः बंद रहते हैं, केवल रात्रि डाकघर सीमित सेवाएं देते हैं।"},
    7: {"name": "डाक टिकटों और लेखन-सामग्री का विक्रय", "total_parts": 2, "part_1_focus": "प्रत्येक डाकघर में कार्य के घंटों के दौरान डाक टिकट और स्टेशनरी की उपलब्धता अनिवार्य।", "part_2_focus": "डाक टिकट काउंटर पर फटे-पुराने नोट न देने और सही मुद्रा में भुगतान करने के नियम।"},
    8: {"name": "फिलाटेलिक ब्यूरो और डाक टिकट संग्रह", "total_parts": 1, "part_1_focus": "स्मारक डाक टिकटों की बिक्री, फिलाटेलिक डिपॉजिट अकाउंट (PDA) खोलने की सुविधाएं।"},
    9: {"name": "फ्रैंकिंग मशीन के नियम व लाइसेंस", "total_parts": 2, "part_1_focus": "डाक महानिदेशक या मंडल प्रमुख द्वारा लाइसेंस जारी करना, लाल रंग की स्याही की छाप।", "part_2_focus": "फ्रैंकिंग मीटर रीसेट, एडवांस भुगतान पर छूट और पोस्टिंग की शर्तें।"},
    10: {"name": "अप्रयुक्त व जाली टिकटों का निषेध", "total_parts": 1, "part_1_focus": "काटे गए, फटे या जाली टिकटों का उपयोग आईपीसी की धारा 263-A के तहत दंडनीय अपराध है।"}
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
        "पेन्टियों": "पत्र-पेटियों", "पेन्टी": "पत्र-पेटी",
        "घंटी वाली प्लेटें": "घंटे वाली प्लेटें", "घंटी वाली प्लेट": "घंटे वाली प्लेट",
        "घंटी वाली": "घंटे वाली", "नित्य पत्र": "वित्तीय वर्ष", "नित्य वर्ष": "वित्तीय वर्ष"
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
    if not os.path.exists(BOOK_3D_PATH):
        try:
            bk = Image.new("RGBA", (300, 420), (0, 0, 0, 0))
            db = ImageDraw.Draw(bk)
            db.rounded_rectangle([55, 60, 245, 360], radius=14, fill="#1E3A8A")
            db.rounded_rectangle([75, 65, 240, 350], radius=8, fill="#F8FAFC")
            db.rounded_rectangle([55, 55, 230, 350], radius=12, fill="#1D4ED8")
            bk.save(BOOK_3D_PATH, "PNG")
        except Exception:
            pass

    if not os.path.exists(POSTBOX_3D_PATH):
        try:
            box = Image.new("RGBA", (300, 420), (0, 0, 0, 0))
            d = ImageDraw.Draw(box)
            d.rounded_rectangle([75, 120, 225, 350], radius=12, fill="#991B1B")
            d.rounded_rectangle([95, 120, 205, 350], radius=8, fill="#DC2626")
            box.save(POSTBOX_3D_PATH, "PNG")
        except Exception:
            pass

    if not os.path.exists(QUIZ_3D_PATH):
        try:
            q = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
            dq = ImageDraw.Draw(q)
            dq.chord([60, 70, 240, 250], start=0, end=180, fill="#D97706")
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

def ensure_bgm(bgm_path="bgm.mp3", state_index=0):
    if os.path.exists(bgm_path):
        try: os.remove(bgm_path)
        except Exception: pass
    if os.path.exists(os.path.join(ASSETS_DIR, "bgm.mp3")):
        return os.path.join(ASSETS_DIR, "bgm.mp3")

    chord_presets = [
        "0.12*sin(2*PI*220*t)+0.08*sin(2*PI*277.18*t)+0.08*sin(2*PI*329.63*t)",
        "0.12*sin(2*PI*196*t)+0.08*sin(2*PI*246.94*t)+0.08*sin(2*PI*293.66*t)"
    ]
    selected_expr = chord_presets[state_index % len(chord_presets)]

    try:
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"aevalsrc=exprs='{selected_expr}':s=48000:d=70",
            "-c:a", "libmp3lame", "-b:a", "192k", bgm_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return bgm_path
    except Exception:
        return None

def load_progress_state():
    state = {"clause_no": 6, "current_part": 1, "total_parts": 1, "hook_index": 0}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if data.get("clause_no", 0) < 6:
                    data["clause_no"] = 6
                    data["current_part"] = 1
                state.update(data)
        except Exception:
            pass
    else:
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

    clause = state.get("clause_no", 6)
    part = state.get("current_part", 1)
    clause_info = POSTAL_CLAUSE_CATALOG.get(clause, {"total_parts": 1})
    total_parts = clause_info.get("total_parts", 1)

    if part < total_parts:
        state["current_part"] = part + 1
    else:
        catalog_keys = sorted(POSTAL_CLAUSE_CATALOG.keys())
        current_idx = catalog_keys.index(clause) if clause in catalog_keys else 0
        next_idx = (current_idx + 1) % len(catalog_keys)
        state["clause_no"] = catalog_keys[next_idx]
        state["current_part"] = 1

    save_progress_state(state)

def generate_clause_script(state):
    current_clause = state.get("clause_no", 6)
    current_part = state.get("current_part", 1)
    hook_idx = state.get("hook_index", 0) % len(VIRAL_HOOKS)
    hook_obj = VIRAL_HOOKS[hook_idx]

    clause_info = POSTAL_CLAUSE_CATALOG.get(current_clause, POSTAL_CLAUSE_CATALOG[6])
    clause_name = clause_info["name"]
    total_parts = clause_info["total_parts"]
    part_focus = clause_info.get(f"part_{current_part}_focus", clause_info.get("part_1_focus", ""))

    fallback_data = {
        "clause_no": current_clause,
        "clause_name": clause_name,
        "part_no": current_part,
        "total_parts": total_parts,
        "visual_hook_badge": hook_obj["visual_badge"],
        "hook_voice": hook_obj["voice"],
        "question": f"डाक घर गाइड भाग 1 के क्लॉज {current_clause} के अनुसार रविवार और राष्ट्रीय अवकाश पर सामान्य डाकघर की क्या स्थिति होती है?",
        "sen1": f"डाक घर गाइड भाग 1 के क्लॉज {current_clause} के अनुसार {part_focus}",
        "sen2": "रविवार और सभी 16 राजपत्रित अवकाशों पर सामान्य डाकघर पूरी तरह बंद रहते हैं, जिससे नियमित सेवाएं स्थगित रहती हैं।",
        "sen3": "केवल रात्रि डाकघर ही ऐसे अवकाशों पर सीमित सेवाएं प्रदान करते हैं। विभागीय परीक्षा हेतु यह अति महत्वपूर्ण नियम है।",
        "opt_a": "पूर्णतः खुले रहते हैं",
        "opt_b": "पूर्णतः बंद रहते हैं",
        "opt_c": "केवल बचत बैंक कार्य होता है",
        "opt_d": "इनमें से कोई नहीं",
        "caption": f"डाक घर गाइड भाग 1 क्लॉज {current_clause} | विभागीय परीक्षा (GDS to MTS, Postman, PA) तैयारी। #PostalWala #GDStoMTS #PostmanExam #IndiaPost"
    }

    if not GROQ_API_KEY:
        return fallback_data

    prompt = f"""
    You are the Senior Chief Instructor for India Post Departmental Examinations running 'Postal Wala'.
    TOPIC: Book: 'Post Office Guide Part 1'
    Clause Number: क्लॉज {current_clause}, Title: {clause_name}, Part: {current_part}/{total_parts}
    Sub-Rule Focus: "{part_focus}"

    Generate:
    QUESTION: [1 crisp high-yield exam question directly on this clause]
    SEN1: [Core rule explanation, ~22 words]
    SEN2: [Key conditions/working hours, ~22 words]
    SEN3: [Official exception or trap, ~22 words]
    OPT_A: [Option A]
    OPT_B: [Option B]
    OPT_C: [Option C]
    OPT_D: [Option D]
    """
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"}
        payload = {"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 550}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            raw_text = res.json()["choices"][0]["message"]["content"].strip()
            q = extract_field_block(raw_text, "QUESTION", ["SEN1", "OPT_A"])
            s1 = extract_field_block(raw_text, "SEN1", ["SEN2", "QUESTION"])
            s2 = extract_field_block(raw_text, "SEN2", ["SEN3", "QUESTION"])
            s3 = extract_field_block(raw_text, "SEN3", ["QUESTION", "OPT_A"])
            oa = extract_field_block(raw_text, "OPT_A", ["OPT_B", "OPT_C"])
            ob = extract_field_block(raw_text, "OPT_B", ["OPT_C", "OPT_D"])
            oc = extract_field_block(raw_text, "OPT_C", ["OPT_D"])
            od = extract_field_block(raw_text, "OPT_D", [])

            if q: fallback_data["question"] = clean_hindi_postal_terms(q)
            if s1: fallback_data["sen1"] = clean_hindi_postal_terms(s1)
            if s2: fallback_data["sen2"] = clean_hindi_postal_terms(s2)
            if s3: fallback_data["sen3"] = clean_hindi_postal_terms(s3)
            if oa: fallback_data["opt_a"] = clean_hindi_postal_terms(oa)
            if ob: fallback_data["opt_b"] = clean_hindi_postal_terms(ob)
            if oc: fallback_data["opt_c"] = clean_hindi_postal_terms(oc)
            if od: fallback_data["opt_d"] = clean_hindi_postal_terms(od)
    except Exception as e:
        print(f"⚠️ Groq note: {e}")

    return fallback_data

def get_slide_segments(script_data):
    q_txt = script_data["question"]
    hook_v = script_data["hook_voice"]
    return [
        f"{hook_v} आज का महत्वपूर्ण प्रश्न है: {q_txt} इसका सही उत्तर जानने के लिए वीडियो में अंत तक बने रहें!",
        f"आइए नियम को समझें। {script_data['sen1']} {script_data['sen2']}",
        f"विभागीय परीक्षा की दृष्टि से ध्यान दें! {script_data['sen3']}",
        f"तो साथियों, {q_txt} इसका सही उत्तर आप सभी कमेंट बॉक्स में दीजिए! फ्री मॉक टेस्ट के लिए स्क्रीन पर दिए नंबर पर व्हाट्सएप करें, और अपना विभागीय परीक्षा निकालने के लिए पोस्टल वाला को फॉलो करना न भूलें!"
    ]

async def generate_segment_audio(text, outfile):
    if os.path.exists(outfile):
        try: os.remove(outfile)
        except Exception: pass
    communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+5%")
    await communicate.save(outfile)

def get_audio_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    return float(subprocess.check_output(cmd).decode().strip())

# --- 100% Synced Rendering With Automatic Proportional Speed Clamp (<54s) ---
def render_and_sync_video(script_data, output_video=OUTPUT_VIDEO):
    ensure_fonts()
    ensure_auto_icons()
    
    current_state = load_progress_state()
    active_bgm = ensure_bgm(BGM_OUTPUT, state_index=current_state.get("hook_index", 0))

    segment_audios = get_slide_segments(script_data)
    raw_durations = []
    
    for i, seg_text in enumerate(segment_audios):
        seg_file = f"audio_seg_{i}.mp3"
        asyncio.run(generate_segment_audio(seg_text, seg_file))
        raw_durations.append(get_audio_duration(seg_file))

    # Concat raw audios
    with open("audio_concat.txt", "w") as f:
        for i in range(4):
            f.write(f"file 'audio_seg_{i}.mp3'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "audio_concat.txt", "-c", "copy", "raw_master.mp3"], check=True)
    
    total_dur = get_audio_duration("raw_master.mp3")
    print(f"🎵 Initial Voiceover Duration: {total_dur:.1f}s", flush=True)

    # If duration > 54s, speed-up proportionally keeping 100% slide sync
    if total_dur > 54.0:
        tempo = round(total_dur / 52.0, 2)
        subprocess.run(["ffmpeg", "-y", "-i", "raw_master.mp3", "-filter:a", f"atempo={tempo}", "final_master.mp3"], check=True)
        durations = [d / (total_dur / 52.0) for d in raw_durations]
        print(f"⏩ Speed-adjusted master audio to: {sum(durations):.1f}s", flush=True)
    else:
        durations = raw_durations
        os.replace("raw_master.mp3", "final_master.mp3")

    font_brand = get_eng_font(44)
    font_sub = get_eng_font(22)
    font_trust = get_eng_font(20)
    font_badge = get_dev_font(22)
    font_title = get_dev_font(34)
    font_h2 = get_dev_font(30)
    font_body = get_dev_font(34)
    font_label = get_dev_font(26)
    font_wa_hin = get_dev_font(30)
    font_wa_num = get_eng_font(30)
    font_cta = get_eng_font(30)
    font_cta_dev = get_dev_font(30)
    font_opt = get_dev_font(28)
    font_hook = get_dev_font(30)

    def draw_base(d):
        d.rounded_rectangle([45, 50, 1035, 1710], radius=32, fill="#0B132B", outline="#1E293B", width=3)
        d.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        d.text((80, 130), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)
        d.rounded_rectangle([630, 80, 1000, 132], radius=16, fill="#064E3B", outline="#10B981", width=2)
        d.text((655, 93), "100% OFFICIAL SYLLABUS", fill="#D1FAE5", font=font_trust)

    def draw_whatsapp_strip(d):
        d.rounded_rectangle([80, 345, 1000, 475], radius=18, fill="#064E3B", outline="#34D399", width=2)
        d.text((110, 362), "GDS to MTS • Postman • Mail Guard • P.A.", fill="#FDE047", font=font_wa_num)
        d.text((110, 412), "कोर्स व फ्री टेस्ट हेतु व्हाट्सएप: 8989971379", fill="#FFFFFF", font=font_wa_hin)

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

    slide_filenames = []

    # Slide 1: Hook + Sawal
    img1 = Image.new("RGB", (1080, 1920), color="#060A17")
    d1 = ImageDraw.Draw(img1)
    draw_base(d1)
    d1.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
    d1.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d1.text((120, 198), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d1.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d1.text((845, 198), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d1.text((105, 255), clean_hindi_postal_terms(script_data["clause_name"]), fill="#FFFFFF", font=font_title)
    draw_whatsapp_strip(d1)
    d1.rounded_rectangle([80, 505, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)
    d1.rounded_rectangle([110, 535, 970, 605], radius=14, fill="#991B1B", outline="#FBBF24", width=2)
    d1.text((175, 550), clean_hindi_postal_terms(script_data["visual_hook_badge"]), fill="#FEF08A", font=font_hook)
    d1.rounded_rectangle([110, 625, 480, 675], radius=10, fill="#0B132B")
    d1.text((165, 635), "आज का प्रश्न:", fill="#38BDF8", font=font_label)
    wrapped_q1 = textwrap.fill(f"आज का महत्वपूर्ण सवाल:\n{script_data['question']}\n\nसही उत्तर वीडियो में अंत तक समझें!", width=24)
    d1.multiline_text((115, 700), clean_hindi_postal_terms(wrapped_q1), fill="#F8FAFC", font=font_body, spacing=16)
    paste_safe_asset(img1, BOOK_3D_PATH, pos=(400, 1120))
    draw_footer_cta(d1)
    img1.save("slide_1.png")
    slide_filenames.append("slide_1.png")

    # Slide 2: Niyam Analysis
    img2 = Image.new("RGB", (1080, 1920), color="#060A17")
    d2 = ImageDraw.Draw(img2)
    draw_base(d2)
    d2.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
    d2.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d2.text((120, 198), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d2.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d2.text((845, 198), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d2.text((105, 255), clean_hindi_postal_terms(script_data["clause_name"]), fill="#FFFFFF", font=font_title)
    draw_whatsapp_strip(d2)
    d2.rounded_rectangle([80, 505, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)
    d2.rounded_rectangle([110, 535, 480, 585], radius=10, fill="#0B132B")
    d2.text((165, 545), "नियम विश्लेषण #1:", fill="#38BDF8", font=font_label)
    wrapped_s2 = textwrap.fill(f"{script_data['sen1']}\n\n{script_data['sen2']}", width=24)
    d2.multiline_text((115, 610), clean_hindi_postal_terms(wrapped_s2), fill="#F8FAFC", font=font_body, spacing=16)
    paste_safe_asset(img2, POSTBOX_3D_PATH, pos=(400, 1120))
    draw_footer_cta(d2)
    img2.save("slide_2.png")
    slide_filenames.append("slide_2.png")

    # Slide 3: Rule Point 2 / Trap
    img3 = Image.new("RGB", (1080, 1920), color="#060A17")
    d3 = ImageDraw.Draw(img3)
    draw_base(d3)
    d3.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
    d3.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d3.text((120, 198), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d3.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d3.text((845, 198), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d3.text((105, 255), clean_hindi_postal_terms(script_data["clause_name"]), fill="#FFFFFF", font=font_title)
    draw_whatsapp_strip(d3)
    d3.rounded_rectangle([80, 505, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)
    d3.rounded_rectangle([110, 535, 480, 585], radius=10, fill="#0B132B")
    d3.text((165, 545), "परीक्षा अपवाद #2:", fill="#38BDF8", font=font_label)
    wrapped_s3 = textwrap.fill(f"परीक्षा विशेष बिंदु:\n\n{script_data['sen3']}", width=24)
    d3.multiline_text((115, 610), clean_hindi_postal_terms(wrapped_s3), fill="#F8FAFC", font=font_body, spacing=16)
    paste_safe_asset(img3, POSTBOX_3D_PATH, pos=(400, 1120))
    draw_footer_cta(d3)
    img3.save("slide_3.png")
    slide_filenames.append("slide_3.png")

    # Slide 4: Quiz
    img4 = Image.new("RGB", (1080, 1920), color="#060A17")
    d4 = ImageDraw.Draw(img4)
    draw_base(d4)
    d4.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#FBBF24", width=2)
    d4.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d4.text((120, 198), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d4.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d4.text((845, 198), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d4.text((105, 255), "परीक्षा क्विज़: उत्तर कमेंट करें", fill="#FDE047", font=font_title)
    draw_whatsapp_strip(d4)
    d4.rounded_rectangle([80, 505, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)
    d4.rounded_rectangle([110, 530, 360, 575], radius=12, fill="#0B132B")
    d4.text((160, 538), "आज का सवाल:", fill="#FBBF24", font=font_h2)
    d4.multiline_text((110, 595), textwrap.fill(clean_hindi_postal_terms(script_data["question"]), width=24), fill="#F8FAFC", font=font_h2, spacing=8)

    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    oy = 715
    for o_idx, opt in enumerate(opts):
        d4.rounded_rectangle([110, oy, 970, oy + 75], radius=12, fill="#0B132B", outline="#38BDF8", width=2)
        d4.text((135, oy + 18), f"{chr(65+o_idx)})", fill="#38BDF8", font=font_h2)
        d4.text((200, oy + 18), textwrap.fill(clean_hindi_postal_terms(opt), width=23), fill="#FFFFFF", font=font_opt)
        oy += 95

    d4.rounded_rectangle([110, 1370, 970, 1490], radius=18, fill="#0B132B", outline="#F59E0B", width=2)
    d4.text((185, 1410), "अपना सही जवाब अभी कमेंट करें!", fill="#FDE047", font=font_h2)
    draw_footer_cta(d4)
    img4.save("slide_4.png")
    slide_filenames.append("slide_4.png")

    inputs = []
    filter_parts = ""
    for i, fname in enumerate(slide_filenames):
        inputs.extend(["-i", fname])
        safe_dur = max(1.0, durations[i])
        filter_parts += f"[{i}:v]loop=loop=-1:size=1:start=0,trim=duration={safe_dur}[v{i}]; "

    concat_str = "".join([f"[v{i}]" for i in range(len(slide_filenames))])
    video_filter = f"{filter_parts}{concat_str}concat=n={len(slide_filenames)}:v=1:a=0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p[v]"

    cmd = ["ffmpeg", "-y", *inputs, "-i", "final_master.mp3"]
    voice_idx = len(slide_filenames)

    if active_bgm and os.path.exists(active_bgm) and os.path.getsize(active_bgm) > 2000:
        bgm_idx = voice_idx + 1
        cmd.extend(["-stream_loop", "-1", "-i", active_bgm])
        full_filter = f"{video_filter}; [{voice_idx}:a]aresample=48000,volume=1.0[v_aud]; [{bgm_idx}:a]aresample=48000,volume=0.22[bgm_aud]; [v_aud][bgm_aud]amix=inputs=2:duration=first:dropout_transition=2[a]"
        cmd.extend(["-filter_complex", full_filter, "-map", "[v]", "-map", "[a]"])
    else:
        cmd.extend(["-filter_complex", video_filter, "-map", "[v]", "-map", f"{voice_idx}:a"])

    cmd.extend([
        "-c:v", "libx264", "-preset", "medium", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", "-shortest", output_video
    ])

    subprocess.run(cmd, check=True)
    print("✅ 100% Synced & Duration-Locked (<54s) Reel Created.", flush=True)

# --- Exact Working Resumable Upload Architecture With Full Terminal Logs ---
def post_reel_to_instagram_multipart(video_file, caption, max_container_attempts=3):
    access_token = os.getenv("IG_ACCESS_TOKEN")
    user_id = os.getenv("IG_USER_ID")

    if not access_token or not user_id:
        print("⚠️ IG credentials missing!")
        return False

    last_error = None
    for container_attempt in range(1, max_container_attempts + 1):
        print(f"\n🚀 [UPLOAD] Starting Attempt {container_attempt} of {max_container_attempts}...", flush=True)
        try:
            video_id = _create_reel_container(video_file, caption, user_id, access_token)
            print(f"📦 Container created with ID: {video_id}", flush=True)

            status = _poll_container_status(video_id, access_token)
            print(f"📊 Container status: {status}", flush=True)

            if status == "FINISHED":
                _publish_reel(video_id, user_id, access_token)
                print(f"🎉 Reel published on Attempt {container_attempt}!", flush=True)
                return True
            else:
                last_error = f"Status: {status}"
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ Attempt {container_attempt} error: {last_error}", flush=True)

        if container_attempt < max_container_attempts:
            print(f"⏳ Waiting 25s before retry Attempt {container_attempt + 1}...", flush=True)
            time.sleep(25)

    print(f"\n❌ Upload failed after 3 attempts: {last_error}", flush=True)
    return False

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

    res_json = r.json()
    video_id = res_json.get("id")
    upload_url = res_json.get("uri") or (RUPLOAD_BASE + str(video_id).strip())

    time.sleep(12)

    file_size = os.path.getsize(video_file)
    upload_headers = {
        "Authorization": f"OAuth {access_token}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "application/octet-stream"
    }

    with open(video_file, "rb") as vf:
        video_bytes = vf.read()

    up_r = requests.post(upload_url, headers=upload_headers, data=video_bytes, timeout=600)

    if up_r.status_code != 200 or not up_r.json().get("success"):
        raise RuntimeError(f"Upload fail: {up_r.text}")

    return video_id

def _poll_container_status(video_id, access_token, max_checks=40, wait_seconds=15):
    status_url = GRAPH_API_BASE + str(video_id).strip()
    for check_idx in range(1, max_checks + 1):
        time.sleep(wait_seconds)
        try:
            res = requests.get(status_url, params={"fields": "status_code,status", "access_token": access_token}, timeout=30).json()
            status = res.get("status_code")
            print(f"   ⏳ Polling Instagram status ({check_idx}/{max_checks}): {status}", flush=True)
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
        print(f"🎉 Post published! Instagram Media ID: {pub_res['id']}", flush=True)
    else:
        raise RuntimeError(f"Publish fail: {pub_res}")

# --- Main Entry Point ---
if __name__ == "__main__":
    st = load_progress_state()
    script_data = generate_clause_script(st)

    render_and_sync_video(script_data, OUTPUT_VIDEO)

    upload_ok = post_reel_to_instagram_multipart(OUTPUT_VIDEO, script_data.get("caption", ""))
    if upload_ok:
        advance_progress_state(st)
        print("✅ Progress state successfully updated for next run.", flush=True)
    else:
        print("❌ Reel upload failed after 3 attempts. Progress state retained.", flush=True)
        sys.exit(1)
