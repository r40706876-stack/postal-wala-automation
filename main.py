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
from pypdf import PdfReader

# --- Environment Variables ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

GRAPH_API_BASE = "https://graph.facebook.com/v19.0/"
RUPLOAD_BASE = "https://rupload.facebook.com/ig-api-upload/"

STATE_FILE = "progress_state.json"
PDF_FILE_PATH = "mts content .pdf"
FONT_PATH = "Mukta-Bold.ttf"

# --- Master Official Clause Titles (PO Guide Part 1) ---
OFFICIAL_CLAUSE_MAP = {
    1: "डाक विभाग का नियंत्रण एवं संगठन",
    2: "डाकघरों के प्रकार (प्रधान, उप व शाखा डाकघर)",
    3: "नाइट पोस्ट ऑफिस (रात्रि कालीन डाकघर)",
    4: "मोबाइल पोस्ट ऑफिस (चलते-फिरते डाकघर)",
    5: "सामान्य कार्य दिवस और कारोबार के घंटे",
    6: "हटाया गया नियम (Deleted)",
    7: "रविवार के दिन डाकघर का कार्य",
    8: "डाकघर के आधिकारिक अवकाश",
    9: "डाक शुल्क का अग्रिम भुगतान",
    10: "डाक टिकट और स्टेशनरी",
    11: "फ्रैंकिंग मशीन के नियम व शर्तें",
    12: "नकद में डाक शुल्क का अग्रिम भुगतान",
    13: "विरूपित अथवा खराब डाक टिकट",
    14: "जाली अथवा प्रयुक्त डाक टिकटों का निषेध",
    15: "डाक वस्तुओं की पैकिंग के नियम",
    16: "मुहरबंदी (Sealing) के नियम",
    17: "सिक्के और मूल्यवान वस्तुओं का प्रेषण",
    18: "पत्र-पेटियां (Letter Boxes) के नियम",
    19: "विशेष पत्र-पेटियों का प्रयोग",
    20: "डाक में वस्तुएं डालने के नियम",
    21: "विदेशी डाक वस्तुएं",
    22: "पते पर टिकट चिपकाने के नियम",
    23: "डाक टिकट चिपकाने का सही स्थान",
    24: "गैर-डाक टिकटों का निषेध",
    25: "पता लिखने के निर्देश",
    26: "पत्र पर पता लिखने की विधि",
    27: "पते में पिन कोड का महत्व",
    28: "सेना डाक सेवा को भेजे जाने वाले पत्र",
    29: "अपूर्ण पते वाली डाक वस्तुएं",
    30: "पत्रों पर अन्य निर्देश लिखना",
    31: "सरकारी डाक वस्तुएं (Official Postal Articles)",
    32: "सरकारी डाक पर प्रयुक्त टिकट",
    33: "डाक का प्रेषण और मार्ग",
    34: "डाक वस्तुओं की वापसी (Recall of Postal Articles)",
    35: "डाक वस्तुओं के वितरण की परिभाषा",
    36: "पंजीकृत वस्तुओं का वितरण",
    37: "पंजीकृत वस्तु लेने से इंकार",
    38: "फर्मों को पंजीकृत डाक वितरण की विशेष प्रक्रिया",
    39: "पर्दानशीं महिलाओं को डाक वितरण",
    40: "क्षतिग्रस्त पंजीकृत वस्तुओं का वितरण",
    41: "10 किलोग्राम से अधिक वजन के पार्सल का वितरण",
    42: "विशेष डाक वितरण व्यवस्था",
    43: "बीमाकृत वस्तुओं का वितरण",
    44: "मूल्य-देय (V.P.) वस्तुओं का वितरण",
    45: "अप्राप्त या अविभाजित डाक वस्तुएं",
    46: "लावारिस डाक वस्तुएं (Unclaimed Articles)",
    47: "पुनर्निर्देशन (Redirection) के नियम",
    48: "पुनर्निर्देशन शुल्क संबंधी निर्देश",
    49: "पार्सल का पुनर्निर्देशन",
    50: "पुनर्निर्देशन शुल्क से छूट",
    51: "पता परिवर्तन संबंधी निर्देश",
    52: "डाक रोकने संबंधी निर्देश",
    53: "डाक वस्तुओं का अस्थायी ठहराव",
    54: "मृत व्यक्तियों की डाक का निपटान",
    55: "पोस्ट बॉक्स (Post Boxes) की शर्तें व किराया",
    56: "पोस्ट बैग (Post Bags) के नियम व शुल्क"
}

# --- Dynamic 7-Point Retention Bank for Guaranteed Accuracy ---
CLAUSE_RETENTION_BANK = {
    1: {
        "hook_question": "डाक विभाग का प्रशासनिक नियंत्रण किसके पास होता है?",
        "reward_line1": "महानिदेशक डाक सेवा (DG Posts)",
        "reward_line2": "मुख्यालय: डाक भवन, नई दिल्ली",
        "single_fact": "डाक सेवा बोर्ड (PSB) के पदेन अध्यक्ष 'सचिव (डाक)' होते हैं!",
        "mcq_q": "डाक सेवा बोर्ड (Postal Services Board) के पदेन अध्यक्ष कौन होते हैं?",
        "mcq_opts": ["सचिव (डाक)", "महानिदेशक (DG Posts)", "संचार मंत्री", "सदस्य (कार्मिक)"],
        "mcq_ans": "A"
    },
    2: {
        "hook_question": "शाखा डाकघर (BO) का अधिकतम कार्य समय कितना होता है?",
        "reward_line1": "अधिकतम 5 घंटे (न्यूनतम 4 घंटे)",
        "reward_line2": "प्रभारी अधिकारी: शाखा डाकपाल (BPM)",
        "single_fact": "प्रधान डाकघर (HO) पूरे डाक मंडल का मुख्य लेखा कार्यालय होता है!",
        "mcq_q": "डाकघर गाइड भाग 1 के अनुसार डाकघरों को कुल कितने वर्गों में बांटा गया है?",
        "mcq_opts": ["3 वर्ग (HO, SO, BO)", "2 वर्ग (HO व SO)", "4 वर्ग", "5 वर्ग"],
        "mcq_ans": "A"
    },
    3: {
        "hook_question": "Night Post Office का समय कौन तय करता है?",
        "reward_line1": "केवल DG (Posts) — महानिदेशक",
        "reward_line2": "सामान्य दिन: रात 8:30 बजे तक",
        "single_fact": "रविवार और छुट्टियों को शाम 5:00 बजे तक (Delivery पूरी तरह बंद)!",
        "mcq_q": "रविवार और अवकाश के दिन Night Post Office में क्या बंद रहता है?",
        "mcq_opts": ["टिकट बिक्री", "डाक वितरण (Delivery)", "रजिस्ट्री बुकिंग", "इनमें से कोई नहीं"],
        "mcq_ans": "B"
    },
    4: {
        "hook_question": "Mobile Post Office में कौन-सी सेवा पूरी तरह वर्जित है?",
        "reward_line1": "मनी ऑर्डर और वीपी (V.P.) पार्सल",
        "reward_line2": "बचत बैंक खाते की सेवाएं बंद",
        "single_fact": "मोबाइल पोस्ट ऑफिस रविवार और आधिकारिक छुट्टियों पर बंद रहते हैं!",
        "mcq_q": "मोबाइल डाकघर (चलते-फिरते डाकघर) में क्या स्वीकार नहीं किया जाता?",
        "mcq_opts": ["मनी ऑर्डर और वीपी वस्तुएं", "साधारण पत्र", "डाक टिकट बिक्री", "पंजीकृत पत्र"],
        "mcq_ans": "A"
    },
    5: {
        "hook_question": "डाकघर के कारोबार के घंटे (Business Hours) कौन तय करता है?",
        "reward_line1": "सर्किल प्रमुख (Head of Circle / CPMG)",
        "reward_line2": "जनता की सुविधा के अनुसार निर्धारण",
        "single_fact": "बचत बैंक व मनी ऑर्डर लगभग 5 घंटे, रजिस्ट्री 6-7 घंटे कार्य करती है!",
        "mcq_q": "डाकघर में विभिन्न सेवाओं के कार्य घंटे (Business Hours) कौन निश्चित करता है?",
        "mcq_opts": ["सर्किल प्रमुख (CPMG)", "डाक महानिदेशक (DG Posts)", "स्थानीय पोस्टमास्टर", "मंडल अधीक्षक (SSPO)"],
        "mcq_ans": "A"
    },
    7: {
        "hook_question": "रविवार के दिन डाकघर में कौन-सा काम पूरी तरह बंद रहता है?",
        "reward_line1": "सामान्य डाकघर पूर्णतः बंद रहते हैं",
        "reward_line2": "डाक वितरण (Delivery) पूरी तरह बंद",
        "single_fact": "रविवार को केवल नाइट पोस्ट ऑफिस और RMS सीमित सेवाओं हेतु खुलते हैं!",
        "mcq_q": "डाकघर गाइड भाग 1 क्लॉज 7 के अनुसार रविवार को क्या पूरी तरह बंद रहता है?",
        "mcq_opts": ["डाक वितरण (Delivery)", "पत्र-पेटी में पत्र डालना", "आरएमएस कार्य", "नाइट पोस्ट ऑफिस कार्य"],
        "mcq_ans": "A"
    },
    8: {
        "hook_question": "डाक विभाग में साल में कुल कितने राष्ट्रीय अनिवार्य अवकाश होते हैं?",
        "reward_line1": "कुल 3 राष्ट्रीय अवकाश (17 कुल अवकाश)",
        "reward_line2": "26 जनवरी, 15 अगस्त, 2 अक्टूबर",
        "single_fact": "अनिवार्य अवकाशों के दिन भी नाइट पोस्ट ऑफिस सीमित समय हेतु खुलते हैं!",
        "mcq_q": "डाकघर में निम्नलिखित में से कौन-सा राष्ट्रीय अवकाश अनिवार्य रूप से मनाया जाता है?",
        "mcq_opts": ["15 अगस्त (स्वतंत्रता दिवस)", "होली", "दीपावली", "रक्षाबंधन"],
        "mcq_ans": "A"
    }
}

REELS_DIR = "generated_reels"
os.makedirs(REELS_DIR, exist_ok=True)

CONCEPT_VIDEO = os.path.join(REELS_DIR, "concept_reel.mp4")
QUIZ_VIDEO = os.path.join(REELS_DIR, "quiz_reel.mp4")

BGM_OUTPUT = "bgm.mp3"
VOICE_NAME = "hi-IN-SwaraNeural"

ASSETS_DIR = "assets"

def find_pdf_path():
    candidates = [
        PDF_FILE_PATH,
        "PO_Guide_Part-1_copy.pdf",
        "PO_Guide_Part-1.pdf",
        "mts content.pdf"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    all_pdfs = glob.glob("*.pdf")
    if all_pdfs:
        return all_pdfs[0]
    return PDF_FILE_PATH

def clean_text(text):
    if not text:
        return ""
    text = text.strip().strip("\"'`")
    return "".join(c for c in text if ord(c) < 0x10000).strip()

def has_english_leakage(text):
    if not text:
        return False
    letters = len(re.findall(r'[a-zA-Z]', text))
    hindi = len(re.findall(r'[\u0900-\u097F]', text))
    return letters > 5 and letters > hindi

def clean_hindi_postal_terms(text):
    if not text:
        return ""
    text = re.sub(r"^[\s\)\(\.\-\:–\d\+]+", "", text).strip()
    replacements = {
        "पेन्टियों": "पत्र-पेटियों", "पेन्टी": "पत्र-पेटी",
        "घंटी वाली प्लेटें": "घंटे वाली प्लेटें", "घंटी वाली प्लेट": "घंटे वाली प्लेट",
        "तक्सी पैकेट": "बीमाकृत पैकेट", "तक्सी": "बीमाकृत", "लेखक": "प्रेषक",
        "तक्सी पत्र": "बीमाकृत पत्र", "तक्सी वस्तु": "बीमाकृत वस्तु",
        "डार्क": "डाक", "डार्कघर": "डाकघर", "सचवच": "सचिव",
        "ववभाग": "विभाग", "सववचच": "सर्वोच्च", "हो:-्रा": "होता", "हो:-्रा हे": "होता है"
    }
    for bad_w, good_w in replacements.items():
        text = text.replace(bad_w, good_w)
    return clean_text(text)

def extract_clause_from_pdf(clause_no, current_part=1, total_parts=1):
    official_title = OFFICIAL_CLAUSE_MAP.get(clause_no, f"पोस्टल गाइड भाग 1 क्लॉज {clause_no}")
    default_text = f"डाक घर गाइड भाग 1 के क्लॉज {clause_no} ({official_title}) का आधिकारिक विभागीय नियम।"
    
    pdf_path = find_pdf_path()
    if not os.path.exists(pdf_path):
        return official_title, default_text

    try:
        reader = PdfReader(pdf_path)
        full_pdf_text = ""
        max_scan_pages = min(45, len(reader.pages))
        for p_idx in range(max_scan_pages):
            txt = reader.pages[p_idx].extract_text() or ""
            if "डाक जीवन बीमा" in txt or "Postal Life Insurance" in txt or "RPLI" in txt:
                break
            full_pdf_text += txt + "\n"

        start_pattern = re.compile(rf"(?:(?:क्लॉज|Clause|नियम)\s*[-:]?\s*{clause_no}\b)", re.IGNORECASE)
        next_clause = clause_no + 1
        next_pattern = re.compile(rf"(?:(?:क्लॉज|Clause|नियम)\s*[-:]?\s*{next_clause}\b)", re.IGNORECASE)

        lines = full_pdf_text.split('\n')
        capturing = False
        matched_text = ""
        for line in lines:
            line_str = line.strip()
            if start_pattern.search(line_str) and not capturing:
                capturing = True
                continue
            if capturing:
                if next_pattern.search(line_str) and len(matched_text.strip()) > 30:
                    break
                matched_text += line + "\n"

        full_text = matched_text.strip() if len(matched_text.strip()) > 40 else default_text
        return official_title, clean_hindi_postal_terms(full_text[:3500])
    except Exception as e:
        print(f"⚠️ PDF Extraction Note: {e}", flush=True)
    return official_title, default_text

def get_dynamic_total_parts(pdf_text):
    if not pdf_text:
        return 1
    char_count = len(pdf_text.strip())
    return max(1, (char_count // 350) + (1 if char_count % 350 > 0 else 0))

def ensure_fonts():
    if not os.path.exists(FONT_PATH):
        url = "https://raw.githubusercontent.com/google/fonts/main/ofl/mukta/Mukta-Bold.ttf"
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                with open(FONT_PATH, "wb") as f:
                    f.write(r.content)
        except Exception:
            pass

def get_font(size):
    ensure_fonts()
    if os.path.exists(FONT_PATH):
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()

def load_progress_state():
    state = {"clause_no": 3, "current_part": 1, "total_parts": 1, "hook_index": 0}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                if isinstance(saved, dict) and "clause_no" in saved:
                    state.update(saved)
        except Exception:
            pass
            
    _, pdf_text = extract_clause_from_pdf(state.get("clause_no", 3), state.get("current_part", 1), state.get("total_parts", 1))
    state["total_parts"] = get_dynamic_total_parts(pdf_text)
    if state["current_part"] > state["total_parts"]:
        state["current_part"] = 1
        
    save_progress_state(state)
    return state

def save_progress_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

def generate_clause_script(state):
    current_clause = state.get("clause_no", 3)
    current_part = state.get("current_part", 1)
    total_parts = state.get("total_parts", 1)

    official_title, official_pdf_text = extract_clause_from_pdf(current_clause, current_part, total_parts)

    retention_info = CLAUSE_RETENTION_BANK.get(current_clause, {
        "hook_question": f"क्लॉज {current_clause}: परीक्षा में बार-बार आने वाला नियम क्या है?",
        "reward_line1": f"{official_title} का आधिकारिक नियम मान्य है",
        "reward_line2": "नियमों का उल्लंघन होने पर बुकिंग अस्वीकार होती है",
        "single_fact": "विभागीय परीक्षा में इसके अपवादों से सीधे सवाल बनते हैं!",
        "mcq_q": f"डाकघर गाइड भाग 1 के क्लॉज {current_clause} का मुख्य विषय क्या है?",
        "mcq_opts": [official_title, "सामान्य निर्देश", "अतिरिक्त छूट", "सर्किल प्रमुख का आदेश"],
        "mcq_ans": "A"
    })

    script_data = {
        "clause_no": current_clause,
        "clause_name": official_title,
        "part_no": current_part,
        "total_parts": total_parts,
        "series_tag": f"POSTAL TRAP #{current_clause:02d}",
        "concept_data": {
            "series_tag": f"POSTAL TRAP #{current_clause:02d}",
            "hook_question": retention_info["hook_question"],
            "reward_line1": retention_info["reward_line1"],
            "reward_line2": retention_info["reward_line2"],
            "single_fact": retention_info["single_fact"],
            "mcq_q": retention_info["mcq_q"],
            "mcq_opts": retention_info["mcq_opts"],
            "mcq_ans": retention_info["mcq_ans"]
        },
        "q1": f"डाकघर गाइड भाग 1 क्लॉज {current_clause} ({official_title}) का मुख्य नियम क्या है?",
        "a1": retention_info["reward_line1"],
        "b1": "अतिरिक्त सामान्य छूट",
        "c1": "स्थानीय पोस्टमास्टर का आदेश",
        "d1": "इनमें से कोई नहीं",
        "ans1": "A",
        "q2": retention_info["mcq_q"],
        "a2": retention_info["mcq_opts"][0],
        "b2": retention_info["mcq_opts"][1],
        "c2": retention_info["mcq_opts"][2],
        "d2": retention_info["mcq_opts"][3],
        "ans2": retention_info["mcq_ans"],
        "q3": f"क्लॉज {current_clause} के तहत परीक्षा में क्या ध्यान रखना चाहिए?",
        "a3": retention_info["single_fact"],
        "b3": "कोई नियम लागू नहीं होता",
        "c3": "वार्षिक संशोधन",
        "d3": "अतिरिक्त समय",
        "ans3": "A"
    }

    if not GROQ_API_KEY:
        return script_data

    prompt = f"""
    You are the Chief Examiner for India Post Departmental Exams.
    Generate 3 authentic exam questions for PO Guide Part 1 Clause {current_clause} ("{official_title}").
    MANDATORY RULES:
    1. 100% PURE HINDI (DEVANAGARI SCRIPT ONLY). STRICTLY NO ENGLISH SENTENCES.
    2. Format strictly:
    Q1: ...
    A1: ...
    B1: ...
    C1: ...
    D1: ...
    ANS1: [A/B/C/D]
    Q2: ...
    A2: ...
    B2: ...
    C2: ...
    D2: ...
    ANS2: [A/B/C/D]
    Q3: ...
    A3: ...
    B3: ...
    C3: ...
    D3: ...
    ANS3: [A/B/C/D]
    """

    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"}
        payload = {"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.0, "max_tokens": 700}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            raw_text = res.json()["choices"][0]["message"]["content"].strip()
            for line in raw_text.split('\n'):
                if ':' in line:
                    parts = line.split(':', 1)
                    k = re.sub(r'[\*\s_]', '', parts[0]).lower()
                    v = parts[1].strip().strip('"\'`*')
                    if k in script_data and not has_english_leakage(v):
                        clean_v = clean_hindi_postal_terms(v)
                        if len(clean_v) > 0:
                            if k.startswith("ans"):
                                m_opt = re.search(r"[A-D]", clean_v.upper())
                                if m_opt:
                                    script_data[k] = m_opt.group(0)
                            else:
                                script_data[k] = clean_v
    except Exception as e:
        print(f"⚠️ Groq note: {e}")

    return script_data

# --- AUDIO GENERATION ---
async def generate_segment_audio(text, outfile, rate="+5%"):
    if os.path.exists(outfile):
        try: os.remove(outfile)
        except Exception: pass
        
    clean_audio_text = re.sub(r"[\*#`_~\[\]\(\)]", " ", text)
    clean_audio_text = " ".join(clean_audio_text.split()).strip()

    communicate = edge_tts.Communicate(text=clean_audio_text, voice=VOICE_NAME, rate=rate)
    await communicate.save(outfile)

def get_audio_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    return float(subprocess.check_output(cmd).decode().strip())

# --- 100% ATTRACTIVE ANIMATED CONCEPT VIDEO (TYPEWRITER + FAKE POLL + MOTION) ---
def render_concept_video(script_data, output_video=CONCEPT_VIDEO):
    ensure_fonts()
    cd = script_data["concept_data"]

    # 1. Voiceover Flow
    audio_segments = [
        cd["hook_question"],
        f"इसका निर्धारण {cd['reward_line1']} करते हैं, और {cd['reward_line2']}।",
        cd["single_fact"],
        f"अब इस सवाल का उत्तर दो: {cd['mcq_q']}",
        "सही उत्तर A, B, C या D... तुरंत कमेंट करो!"
    ]

    durations = []
    for i, seg in enumerate(audio_segments):
        fn = f"c_audio_{i}.mp3"
        asyncio.run(generate_segment_audio(seg, fn, rate="+8%"))
        durations.append(get_audio_duration(fn))

    timer_audio = "c_audio_timer.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", "5.0", "-c:a", "libmp3lame", "-b:a", "192k", timer_audio
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    timer_dur = 5.0

    all_audios = ["c_audio_0.mp3", "c_audio_1.mp3", "c_audio_2.mp3", "c_audio_3.mp3", timer_audio, "c_audio_4.mp3"]
    concat_filter = "".join([f"[{i}:a]" for i in range(6)]) + "concat=n=6:v=0:a=1[aout]"
    
    cmd_audio = ["ffmpeg", "-y"]
    for af in all_audios:
        cmd_audio.extend(["-i", af])
    cmd_audio.extend(["-filter_complex", concat_filter, "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "concept_master.mp3"])
    subprocess.run(cmd_audio, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    total_dur = sum(durations) + timer_dur

    font_badge = get_font(28)
    font_sub = get_font(24)
    font_tracker = get_font(22)
    font_h1 = get_font(42)
    font_h2 = get_font(34)
    font_opt = get_font(28)
    font_timer = get_font(36)
    font_big_pulse = get_font(46)
    font_poll = get_font(24)

    def draw_top_series_bar(d, tracker_state=1):
        d.rounded_rectangle([70, 65, 460, 125], radius=14, fill="#0F172A", outline="#FACC15", width=3)
        d.text((90, 78), cd["series_tag"], fill="#FACC15", font=font_badge)
        d.text((820, 80), "@POSTAL_WALA", fill="#64748B", font=font_sub)

        track_boxes = [
            ("[✔] नियम", "#10B981" if tracker_state >= 1 else "#334155"),
            ("[✔] समय", "#38BDF8" if tracker_state >= 2 else "#334155"),
            ("[⏳] सवाल", "#FACC15" if tracker_state >= 3 else "#334155")
        ]
        x_st = 70
        for label, col in track_boxes:
            d.rounded_rectangle([x_st, 140, x_st + 290, 185], radius=8, fill="#0F172A", outline=col, width=2)
            d.text((x_st + 70, 148), label, fill=col, font=font_tracker)
            x_st += 340

    frames = []
    frame_durs = []

    # --- ANIMATION 1: TYPEWRITER EFFECT + BLINKING CURSOR ON HOOK (00:00 - 00:02.5s) ---
    hook_full = clean_hindi_postal_terms(cd["hook_question"])
    hook_words = hook_full.split()
    total_w = len(hook_words)
    
    # 5 progressive slices for smooth typewriter feel
    slice_indices = [
        max(1, int(total_w * 0.25)),
        max(2, int(total_w * 0.50)),
        max(3, int(total_w * 0.75)),
        total_w,
        total_w
    ]
    tw_slice_durs = [0.25, 0.25, 0.30, 0.35, max(0.5, durations[0] - 1.15)]

    for tw_idx, w_count in enumerate(slice_indices):
        img_tw = Image.new("RGB", (1080, 1920), color="#080D1A")
        d_tw = ImageDraw.Draw(img_tw)
        draw_top_series_bar(d_tw, tracker_state=1)

        d_tw.rounded_rectangle([70, 340, 1010, 1420], radius=28, fill="#0F172A", outline="#FACC15", width=3)
        d_tw.rounded_rectangle([110, 390, 480, 450], radius=12, fill="#7F1D1D", outline="#EF4444", width=2)
        d_tw.text((135, 405), "[ ⚠️ सीधा परीक्षा सवाल ]", fill="#FECACA", font=font_sub)

        # Typewriter text with blinking yellow cursor
        curr_text = " ".join(hook_words[:w_count])
        if tw_idx < 4:
            curr_text += "  |"  # Blinking cursor
        wrapped_hook = textwrap.fill(curr_text, width=19)
        d_tw.multiline_text((115, 600), wrapped_hook, fill="#FFFFFF", font=font_h1, spacing=20)

        d_tw.rounded_rectangle([110, 1180, 970, 1275], radius=16, fill="#064E3B", outline="#10B981", width=2)
        d_tw.text((210, 1205), ">> 5 सेकंड में जानें पक्का नियम!", fill="#34D399", font=font_h2)

        tw_name = f"anim_tw_{tw_idx}.png"
        img_tw.save(tw_name)
        frames.append(tw_name)
        frame_durs.append(tw_slice_durs[tw_idx])

    # --- ANIMATION 2: CASCADING REWARD CARDS POP (00:02.5 - 00:07s) ---
    img2a = Image.new("RGB", (1080, 1920), color="#080D1A")
    d2a = ImageDraw.Draw(img2a)
    draw_top_series_bar(d2a, tracker_state=2)
    d2a.rounded_rectangle([70, 210, 1010, 325], radius=16, fill="#0F172A", outline="#475569", width=2)
    d2a.text((105, 230), "सवाल:", fill="#FACC15", font=font_sub)
    d2a.text((105, 268), clean_hindi_postal_terms(cd["hook_question"])[:40], fill="#CBD5E1", font=font_h2)

    d2a.rounded_rectangle([70, 370, 1010, 800], radius=24, fill="#064E3B", outline="#10B981", width=4)
    d2a.rounded_rectangle([105, 405, 440, 460], radius=10, fill="#022C22")
    d2a.text((125, 417), "[ ✅ सही उत्तर / निर्धारण ]", fill="#A7F3D0", font=font_sub)
    wrapped_rew1 = textwrap.fill(clean_hindi_postal_terms(cd["reward_line1"]), width=21)
    d2a.multiline_text((105, 530), wrapped_rew1, fill="#FDE047", font=font_h1, spacing=16)

    img2a.save("anim_c2_a.png")
    frames.append("anim_c2_a.png")
    frame_durs.append(round(durations[1] * 0.45, 2))

    img2b = img2a.copy()
    d2b = ImageDraw.Draw(img2b)
    d2b.rounded_rectangle([70, 850, 1010, 1280], radius=24, fill="#0C4A6E", outline="#38BDF8", width=4)
    d2b.rounded_rectangle([105, 885, 420, 940], radius=10, fill="#082F49")
    d2b.text((125, 897), "[ 🕒 कार्य समय / शर्त ]", fill="#BAE6FD", font=font_sub)
    wrapped_rew2 = textwrap.fill(clean_hindi_postal_terms(cd["reward_line2"]), width=21)
    d2b.multiline_text((105, 1010), wrapped_rew2, fill="#FFFFFF", font=font_h1, spacing=16)

    img2b.save("anim_c2_b.png")
    frames.append("anim_c2_b.png")
    frame_durs.append(round(durations[1] * 0.55, 2))

    # --- ANIMATION 3: SINGLE FACT WITH PULSING ALERT (00:07 - 00:11s) ---
    img3 = Image.new("RGB", (1080, 1920), color="#080D1A")
    d3 = ImageDraw.Draw(img3)
    draw_top_series_bar(d3, tracker_state=2)
    d3.rounded_rectangle([70, 320, 1010, 1340], radius=28, fill="#1E1B4B", outline="#A855F7", width=3)
    d3.rounded_rectangle([110, 365, 560, 425], radius=12, fill="#4C1D95")
    d3.text((130, 380), "[ 📌 परीक्षा स्पेशल अपवाद ]", fill="#E9D5FF", font=font_sub)
    wrapped_fact = textwrap.fill(clean_hindi_postal_terms(cd["single_fact"]), width=20)
    d3.multiline_text((115, 540), wrapped_fact, fill="#FFFFFF", font=font_h1, spacing=18)

    d3.rounded_rectangle([110, 1000, 970, 1140], radius=18, fill="#450A0A", outline="#EF4444", width=3)
    d3.text((140, 1045), "⚠️ 90% छात्र इस नियम में गलती करते हैं!", fill="#FCA5A5", font=font_h2)

    d3.rounded_rectangle([110, 1200, 970, 1290], radius=16, fill="#064E3B", outline="#10B981", width=2)
    d3.text((220, 1225), "🎯 अब दीजिए परीक्षा प्रश्न का उत्तर >>", fill="#34D399", font=font_h2)

    img3.save("anim_c3.png")
    frames.append("anim_c3.png")
    frame_durs.append(round(durations[2], 2))

    # --- ANIMATION 4: STAGGERED MCQ ENTRY (00:11 - 00:16s) ---
    img_mcq = Image.new("RGB", (1080, 1920), color="#080D1A")
    dm = ImageDraw.Draw(img_mcq)
    draw_top_series_bar(dm, tracker_state=3)
    dm.rounded_rectangle([70, 210, 1010, 490], radius=20, fill="#0F172A", outline="#38BDF8", width=3)
    dm.rounded_rectangle([105, 235, 420, 290], radius=10, fill="#0284C7")
    dm.text((125, 248), "[ 🎯 लाइव परीक्षा प्रश्न ]", fill="#FFFFFF", font=font_sub)
    wrapped_mcq_q = textwrap.fill(clean_hindi_postal_terms(cd["mcq_q"]), width=23)
    dm.multiline_text((105, 315), wrapped_mcq_q, fill="#F8FAFC", font=font_h2, spacing=10)

    labels = ["A", "B", "C", "D"]
    opt_y_starts = [530, 645, 760, 875]
    mcq_dur = durations[3]
    sub_dur = mcq_dur / 3.0

    # Step 1: Option A & B
    img_m1 = img_mcq.copy()
    dm1 = ImageDraw.Draw(img_m1)
    for oi in range(2):
        oy = opt_y_starts[oi]
        dm1.rounded_rectangle([70, oy, 1010, oy + 95], radius=16, fill="#0F172A", outline="#38BDF8", width=2)
        dm1.text((105, oy + 25), f"{labels[oi]})", fill="#38BDF8", font=font_h2)
        dm1.text((170, oy + 27), clean_hindi_postal_terms(cd["mcq_opts"][oi])[:35], fill="#FFFFFF", font=font_opt)
    img_m1.save("anim_mcq_1.png")
    frames.append("anim_mcq_1.png")
    frame_durs.append(round(sub_dur, 2))

    # Step 2: All 4 Options visible
    img_m2 = img_m1.copy()
    dm2 = ImageDraw.Draw(img_m2)
    for oi in range(2, 4):
        oy = opt_y_starts[oi]
        dm2.rounded_rectangle([70, oy, 1010, oy + 95], radius=16, fill="#0F172A", outline="#38BDF8", width=2)
        dm2.text((105, oy + 25), f"{labels[oi]})", fill="#38BDF8", font=font_h2)
        dm2.text((170, oy + 27), clean_hindi_postal_terms(cd["mcq_opts"][oi])[:35], fill="#FFFFFF", font=font_opt)
    img_m2.save("anim_mcq_2.png")
    frames.append("anim_mcq_2.png")
    frame_durs.append(round(sub_dur * 2.0, 2))

    # --- ANIMATION 5: LIVE FAKE POLL BAR FILLING + PULSING TIMER (00:16 - 00:21s) ---
    # Distribution based on correct answer (Winner gets ~72% majority)
    ans_key = cd.get("mcq_ans", "A").upper()
    poll_distributions = {
        "A": [72, 14, 8, 6],
        "B": [14, 71, 9, 6],
        "C": [12, 11, 70, 7],
        "D": [11, 13, 8, 68]
    }
    target_pcts = poll_distributions.get(ans_key, [72, 14, 8, 6])

    cd_steps = [
        ("05", "#FACC15", "#064E3B", 1010, 0.25),
        ("04", "#FACC15", "#064E3B", 820,  0.45),
        ("03", "#FB923C", "#7C2D12", 630,  0.65),
        ("02", "#F87171", "#7F1D1D", 440,  0.85),
        ("01", "#EF4444", "#991B1B", 250,  1.00)
    ]

    for sec_idx, (sec_str, tc, bgc, bar_w, fill_ratio) in enumerate(cd_steps):
        # Frame with Live Poll filling up inside option containers
        img_poll = img_mcq.copy()
        dp = ImageDraw.Draw(img_poll)

        for oi in range(4):
            oy = opt_y_starts[oi]
            curr_pct = int(target_pcts[oi] * fill_ratio)
            bar_fill_w = int(940 * (curr_pct / 100.0))
            is_winner = (labels[oi] == ans_key)

            # Draw outer box
            box_outline = "#10B981" if (is_winner and fill_ratio >= 0.85) else "#334155"
            dp.rounded_rectangle([70, oy, 1010, oy + 95], radius=16, fill="#0B132B", outline=box_outline, width=2)

            # Draw animated poll progress bar inside
            bar_color = "#064E3B" if is_winner else "#1E293B"
            if bar_fill_w > 10:
                dp.rounded_rectangle([72, oy + 2, 70 + bar_fill_w, oy + 93], radius=14, fill=bar_color)

            # Option Label & Text
            dp.text((105, oy + 25), f"{labels[oi]})", fill="#38BDF8", font=font_h2)
            dp.text((170, oy + 27), clean_hindi_postal_terms(cd["mcq_opts"][oi])[:30], fill="#FFFFFF", font=font_opt)

            # Live Percentage Badge on the right
            pct_color = "#34D399" if is_winner else "#94A3B8"
            dp.text((915, oy + 30), f"{curr_pct}%", fill=pct_color, font=font_poll)

        # Pulse Frame (0.35s)
        dp.rounded_rectangle([70, 1010, 1010, 1130], radius=18, fill="#0F172A", outline=tc, width=4)
        dp.text((290, 1035), f"⏱️ समय: {sec_str} सेकंड", fill=tc, font=font_big_pulse)
        dp.rounded_rectangle([70, 1150, bar_w, 1165], radius=6, fill=tc)
        dp.rounded_rectangle([70, 1190, 1010, 1290], radius=18, fill=bgc, outline=tc, width=2)
        dp.text((250, 1215), ">> अपना उत्तर सोचें और नोट करें!", fill="#FFFFFF", font=font_h2)

        p_name = f"anim_p_{sec_idx}.png"
        img_poll.save(p_name)
        frames.append(p_name)
        frame_durs.append(0.35)

        # Hold Frame (0.65s)
        img_hold = img_poll.copy()
        dh = ImageDraw.Draw(img_hold)
        dh.rounded_rectangle([70, 1020, 1010, 1120], radius=16, fill="#0F172A", outline=tc, width=2)
        dh.text((310, 1045), f"⏱️ समय शेष: {sec_str} सेकंड", fill=tc, font=font_timer)
        dh.rounded_rectangle([70, 1150, bar_w, 1165], radius=6, fill=tc)
        dh.rounded_rectangle([70, 1190, 1010, 1290], radius=18, fill=bgc, outline=tc, width=2)
        dh.text((250, 1215), ">> अपना उत्तर सोचें और नोट करें!", fill="#FFFFFF", font=font_h2)

        h_name = f"anim_h_{sec_idx}.png"
        img_hold.save(h_name)
        frames.append(h_name)
        frame_durs.append(0.65)

    # --- ANIMATION 6: BREATHING PULSE CTA BUTTON (00:21 - 00:23.5s) ---
    cta_pulses = [
        {"grow": 6, "bg": "#F43F5E", "dur": 0.4},
        {"grow": 0, "bg": "#E11D48", "dur": 0.4},
        {"grow": 8, "bg": "#BE123C", "dur": 0.4},
        {"grow": 0, "bg": "#E11D48", "dur": max(0.4, durations[4] - 1.2)}
    ]
    for c_i, c_step in enumerate(cta_pulses):
        img_cta = img_hold.copy()
        dc = ImageDraw.Draw(img_cta)
        dc.rounded_rectangle([70, 1020, 1010, 1120], radius=16, fill="#064E3B", outline="#10B981", width=3)
        dc.text((310, 1045), "⏱️ समय समाप्त! उत्तर दें", fill="#34D399", font=font_timer)

        g = c_step["grow"]
        dc.rounded_rectangle([70 - g, 1160 - g, 1010 + g, 1280 + g], radius=22, fill=c_step["bg"], outline="#FEF08A", width=4)
        dc.text((150, 1195), "💬 कमेंट करो: A, B, C या D?", fill="#FFFFFF", font=font_h1)

        cta_fn = f"anim_cta_{c_i}.png"
        img_cta.save(cta_fn)
        frames.append(cta_fn)
        frame_durs.append(round(c_step["dur"], 2))

    # --- FFMPEG COMPILATION WITH TOP PROGRESS BAR ---
    inputs = []
    filter_parts = ""
    for i, fname in enumerate(frames):
        inputs.extend(["-i", fname])
        safe_dur = max(0.1, frame_durs[i])
        filter_parts += f"[{i}:v]loop=loop=-1:size=1:start=0,trim=duration={safe_dur}[v{i}]; "

    concat_str = "".join([f"[v{i}]" for i in range(len(frames))])
    base_v_filter = f"{filter_parts}{concat_str}concat=n={len(frames)}:v=1:a=0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
    
    progress_bar_filter = (
        f"{base_v_filter},"
        f"drawbox=x=0:y=0:w=iw:h=12:color=#1E293B@1:t=fill,"
        f"drawbox=x=0:y=0:w='iw*(t/{total_dur})':h=12:color=#FACC15@1:t=fill[v]"
    )

    cmd = ["ffmpeg", "-y", *inputs, "-i", "concept_master.mp3"]
    voice_idx = len(frames)
    has_bgm = os.path.exists(BGM_OUTPUT)
    if has_bgm:
        cmd.extend(["-stream_loop", "-1", "-i", BGM_OUTPUT])
        bgm_idx = voice_idx + 1
        audio_filter = (
            f"[{voice_idx}:a]aresample=48000,volume=1.0[voice]; "
            f"[{bgm_idx}:a]aresample=48000,volume=0.10[bgm]; "
            f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2,aformat=channel_layouts=stereo[a]"
        )
    else:
        audio_filter = f"[{voice_idx}:a]aresample=48000,aformat=channel_layouts=stereo[a]"

    full_filter = f"{progress_bar_filter}; {audio_filter}"
    cmd.extend(["-filter_complex", full_filter, "-map", "[v]", "-map", "[a]"])
    cmd.extend([
        "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-shortest", output_video
    ])

    subprocess.run(cmd, check=True)
    print(f"🔥 Typewriter + Fake Poll Animated Reel Created: {output_video} (Dur: {total_dur:.2f}s)", flush=True)

# --- 3-QUESTION 40-SEC QUIZ REEL (EXACT ORIGINAL FROM MAIN 14.PY - 100% UNTOUCHED) ---
def render_quiz_video(script_data, output_video=QUIZ_VIDEO):
    ensure_fonts()
    
    questions_list = [
        {"q_num": "सवाल 1/3", "q": clean_hindi_postal_terms(script_data["q1"]), "opts": [clean_hindi_postal_terms(script_data["a1"]), clean_hindi_postal_terms(script_data["b1"]), clean_hindi_postal_terms(script_data["c1"]), clean_hindi_postal_terms(script_data["d1"])], "ans": script_data["ans1"]},
        {"q_num": "सवाल 2/3", "q": clean_hindi_postal_terms(script_data["q2"]), "opts": [clean_hindi_postal_terms(script_data["a2"]), clean_hindi_postal_terms(script_data["b2"]), clean_hindi_postal_terms(script_data["c2"]), clean_hindi_postal_terms(script_data["d2"])], "ans": script_data["ans2"]},
        {"q_num": "सवाल 3/3", "q": clean_hindi_postal_terms(script_data["q3"]), "opts": [clean_hindi_postal_terms(script_data["a3"]), clean_hindi_postal_terms(script_data["b3"]), clean_hindi_postal_terms(script_data["c3"]), clean_hindi_postal_terms(script_data["d3"])], "ans": script_data["ans3"]},
    ]

    intro_text = f"जीडीएस से एमटीएस, पोस्टमैन और पी.ए. परीक्षा! क्लॉज {script_data['clause_no']} से पेपर में ये प्रश्न बन सकते हैं!"
    intro_audio_file = "audio_q_intro.mp3"
    asyncio.run(generate_segment_audio(intro_text, intro_audio_file, rate="+10%"))

    audio_files = [intro_audio_file]
    segment_durations = [get_audio_duration(intro_audio_file)]

    for idx, q_data in enumerate(questions_list):
        q_speech = f"{q_data['q']}"
        q_audio_file = f"audio_q_{idx+1}.mp3"
        asyncio.run(generate_segment_audio(q_speech, q_audio_file, rate="+10%"))
        audio_files.append(q_audio_file)
        segment_durations.append(get_audio_duration(q_audio_file))

    finale_speech = f"सारे प्रश्नों के सही उत्तर स्क्रीन पर चेक कर लो दोस्तों! फ्री मॉक टेस्ट के लिए MOCK कमेंट करें और Postal Wala को फॉलो करना न भूलें!"
    finale_audio_file = "audio_q_finale.mp3"
    asyncio.run(generate_segment_audio(finale_speech, finale_audio_file, rate="+10%"))
    audio_files.append(finale_audio_file)
    segment_durations.append(get_audio_duration(finale_audio_file))

    concat_filter_audio = ""
    for i in range(len(audio_files)):
        concat_filter_audio += f"[{i}:a]"
    concat_filter_audio += f"concat=n={len(audio_files)}:v=0:a=1[aout]"

    ffmpeg_audio_cmd = ["ffmpeg", "-y"]
    for af in audio_files:
        ffmpeg_audio_cmd.extend(["-i", af])
    ffmpeg_audio_cmd.extend(["-filter_complex", concat_filter_audio, "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "quiz_voice_master.mp3"])
    subprocess.run(ffmpeg_audio_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    font_brand = get_font(40)
    font_sub = get_font(20)
    font_trust = get_font(18)
    font_badge = get_font(20)
    font_title = get_font(32)
    font_q_text = get_font(28)
    font_opt_text = get_font(24)
    font_h2 = get_font(24)
    font_cta = get_font(24)

    def draw_base(d):
        d.rounded_rectangle([45, 50, 1035, 1710], radius=32, fill="#0B132B", outline="#1E293B", width=3)
        d.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        d.text((80, 130), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)
        d.rounded_rectangle([630, 80, 1000, 132], radius=16, fill="#064E3B", outline="#10B981", width=2)
        d.text((655, 93), "100% EXAM ORIENTED", fill="#D1FAE5", font=font_trust)

    def draw_footer_cta(d):
        d.rounded_rectangle([80, 1580, 1000, 1680], radius=22, fill="#E11D48")
        d.text((95, 1605), "फ्री मॉक के लिए MOCK कमेंट करें और फॉलो करें!", fill="#FFFFFF", font=font_cta)

    base_img = Image.new("RGB", (1080, 1920), color="#060A17")
    d_base = ImageDraw.Draw(base_img)
    draw_base(d_base)
    d_base.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#FBBF24", width=2)
    d_base.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d_base.text((120, 195), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d_base.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d_base.text((845, 195), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    
    clean_title = clean_hindi_postal_terms(script_data["clause_name"])
    if len(clean_title) > 38:
        clean_title = clean_title[:36] + "..."
    d_base.text((105, 255), clean_title, fill="#FDE047", font=font_title)
    
    d_base.rounded_rectangle([80, 350, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
    draw_footer_cta(d_base)

    frames = []
    frame_durs = []

    intro_img = base_img.copy()
    d_intro = ImageDraw.Draw(intro_img)
    d_intro.rounded_rectangle([110, 500, 970, 910], radius=20, fill="#182848", outline="#FBBF24", width=3)
    
    d_intro.rounded_rectangle([140, 530, 940, 585], radius=10, fill="#064E3B", outline="#10B981", width=2)
    d_intro.text((160, 542), "🎯 GDS to MTS • Postman • Mail Guard • P.A. परीक्षा", fill="#34D399", font=font_h2)

    d_intro.text((150, 630), f"📌 पोस्टल गाइड क्लॉज {script_data['clause_no']} स्पेशल!", fill="#FDE047", font=font_title)
    d_intro.text((150, 720), "पेपर में इससे ये प्रश्न बन सकते हैं!", fill="#FFFFFF", font=font_q_text)
    intro_frame_name = "quiz_intro_frame.png"
    intro_img.save(intro_frame_name)
    frames.append(intro_frame_name)
    frame_durs.append(segment_durations[0])

    labels = ["A", "B", "C", "D"]

    for idx, q_data in enumerate(questions_list):
        wrapped_q = textwrap.fill(q_data["q"], width=24)
        
        dummy_img = Image.new("RGB", (1080, 1920))
        dummy_draw = ImageDraw.Draw(dummy_img)
        q_bbox = dummy_draw.multiline_textbbox((110, 445), wrapped_q, font=font_q_text, spacing=6)
        q_bottom_y = q_bbox[3]
        
        start_oy = max(q_bottom_y + 25, 510)

        opt_heights = []
        wrapped_opts = []
        for opt in q_data["opts"]:
            w_opt = textwrap.fill(opt, width=28)
            wrapped_opts.append(w_opt)
            o_lines = w_opt.count("\n") + 1
            opt_heights.append(max(75, o_lines * 26 + 18))

        q_audio_dur = segment_durations[idx + 1]
        step_dur = q_audio_dur / 3.0

        img_s1 = base_img.copy()
        d1 = ImageDraw.Draw(img_s1)
        d1.rounded_rectangle([110, 380, 480, 435], radius=10, fill="#7F1D1D", outline="#F87171", width=2)
        d1.text((130, 390), q_data["q_num"], fill="#FECACA", font=font_h2)

        d1.rounded_rectangle([510, 380, 970, 435], radius=10, fill="#064E3B", outline="#10B981", width=2)
        d1.text((540, 395), "🎯 GDS to MTS • Postman • P.A.", fill="#A7F3D0", font=font_badge)

        d1.multiline_text((110, 445), wrapped_q, fill="#F8FAFC", font=font_q_text, spacing=6)
        
        oy = start_oy
        d1.rounded_rectangle([110, oy, 970, oy + opt_heights[0]], radius=12, fill="#0B132B", outline="#38BDF8", width=2)
        d1.text((135, oy + 8), "A)", fill="#38BDF8", font=font_q_text)
        d1.multiline_text((180, oy + 8), wrapped_opts[0], fill="#FFFFFF", font=font_opt_text, spacing=2)
        
        f1_name = f"anim_q{idx+1}_step1.png"
        img_s1.save(f1_name)
        frames.append(f1_name)
        frame_durs.append(step_dur)

        img_s2 = img_s1.copy()
        d2 = ImageDraw.Draw(img_s2)
        
        curr_y = start_oy + opt_heights[0] + 12
        for o_idx in range(1, 3):
            d2.rounded_rectangle([110, curr_y, 970, curr_y + opt_heights[o_idx]], radius=12, fill="#0B132B", outline="#38BDF8", width=2)
            d2.text((135, curr_y + 8), f"{labels[o_idx]})", fill="#38BDF8", font=font_q_text)
            d2.multiline_text((180, curr_y + 8), wrapped_opts[o_idx], fill="#FFFFFF", font=font_opt_text, spacing=2)
            curr_y += opt_heights[o_idx] + 12
        
        f2_name = f"anim_q{idx+1}_step2.png"
        img_s2.save(f2_name)
        frames.append(f2_name)
        frame_durs.append(step_dur)

        img_s3 = img_s2.copy()
        d3 = ImageDraw.Draw(img_s3)
        
        d3.rounded_rectangle([110, curr_y, 970, curr_y + opt_heights[3]], radius=12, fill="#0B132B", outline="#38BDF8", width=2)
        d3.text((135, curr_y + 8), "D)", fill="#38BDF8", font=font_q_text)
        d3.multiline_text((180, curr_y + 8), wrapped_opts[3], fill="#FFFFFF", font=font_opt_text, spacing=2)

        d3.rounded_rectangle([110, 1430, 970, 1510], radius=12, fill="#064E3B", outline="#10B981", width=3)
        d3.text((140, 1455), "⏱️ अपना उत्तर सोचें और नोट करें (उत्तर अंत में)", fill="#A7F3D0", font=font_h2)

        f3_name = f"anim_q{idx+1}_step3.png"
        img_s3.save(f3_name)
        frames.append(f3_name)
        frame_durs.append(step_dur)

    img_ans = base_img.copy()
    d_ans = ImageDraw.Draw(img_ans)
    
    d_ans.rounded_rectangle([110, 380, 680, 440], radius=10, fill="#064E3B", outline="#10B981", width=2)
    d_ans.text((130, 392), "🎉 महा-फिनाले: सभी 3 सवालों के सही उत्तर", fill="#34D399", font=font_h2)

    ans_y_start = 480
    answers_text = [
        f"सवाल 1 का सही उत्तर - [ {script_data.get('ans1', 'A')} ]",
        f"सवाल 2 का सही उत्तर - [ {script_data.get('ans2', 'B')} ]",
        f"सवाल 3 का सही उत्तर - [ {script_data.get('ans3', 'C')} ]"
    ]
    
    for a_idx, ans_str in enumerate(answers_text):
        ay = ans_y_start + (a_idx * 180)
        d_ans.rounded_rectangle([110, ay, 970, ay + 140], radius=16, fill="#182848", outline="#FBBF24", width=2)
        d_ans.text((140, ay + 45), clean_hindi_postal_terms(ans_str), fill="#FDE047", font=font_title)

    ans_fname = "quiz_answers_reveal.png"
    img_ans.save(ans_fname)
    frames.append(ans_fname)
    frame_durs.append(segment_durations[-1])

    total_dur = sum(frame_durs)
    print(f"⏱️ Total Quiz Reel Duration: {total_dur:.2f}s", flush=True)

    filter_parts = ""
    for i, fname in enumerate(frames):
        filter_parts += f"[{i}:v]loop=loop=-1:size=1:start=0,trim=duration={frame_durs[i]}[v{i}]; "

    concat_str = "".join([f"[v{i}]" for i in range(len(frames))])
    base_v_filter = f"{filter_parts}{concat_str}concat=n={len(frames)}:v=1:a=0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
    
    progress_bar_filter = (
        f"{base_v_filter},"
        f"drawbox=x=0:y=0:w=iw:h=14:color=#1E293B@1:t=fill,"
        f"drawbox=x=0:y=0:w='iw*(t/{total_dur})':h=14:color=#F43F5E@1:t=fill,"
        f"drawbox=x='max(0, iw*(t/{total_dur})-20)':y=0:w=20:h=14:color=#FEF08A@1:t=fill[v]"
    )

    cmd = ["ffmpeg", "-y"]
    for fname in frames:
        cmd.extend(["-i", fname])
    cmd.extend(["-i", "quiz_voice_master.mp3"])

    voice_idx = len(frames)
    has_bgm = os.path.exists(BGM_OUTPUT)
    if has_bgm:
        cmd.extend(["-stream_loop", "-1", "-i", BGM_OUTPUT])
        bgm_idx = voice_idx + 1
        audio_filter = (
            f"[{voice_idx}:a]aresample=48000,volume=1.0[voice]; "
            f"[{bgm_idx}:a]aresample=48000,volume=0.10[bgm]; "
            f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2,aformat=channel_layouts=stereo[a]"
        )
    else:
        audio_filter = f"[{voice_idx}:a]aresample=48000,aformat=channel_layouts=stereo[a]"

    full_filter = f"{progress_bar_filter}; {audio_filter}"
    cmd.extend(["-filter_complex", full_filter, "-map", "[v]", "-map", "[a]"])
    cmd.extend([
        "-c:v", "libx264", "-preset", "medium", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-t", "40.0", output_video
    ])

    subprocess.run(cmd, check=True)
    print(f"✅ Quiz Reel Created Successfully: {output_video}", flush=True)

# --- AUTO-COMMIT & PUSH ---
def auto_commit_and_push_reels():
    try:
        print("📤 Committing and pushing reels to GitHub...", flush=True)
        subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", REELS_DIR + "/"], check=True)
        subprocess.run(["git", "commit", "-m", "Auto-upload Rule and Quiz reels [skip ci]"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("🎉 Successfully pushed reels to GitHub!", flush=True)
    except Exception as e:
        print(f"⚠️ Git push note: {e}", flush=True)

# --- MAIN RUNNER ---
if __name__ == "__main__":
    st = load_progress_state()
    print(f"📌 Running Target: Clause {st['clause_no']} (Part {st['current_part']}/{st['total_parts']})", flush=True)
    
    script_data = generate_clause_script(st)
    
    # 1. Concept Reel (Typewriter + Fake Poll Animated 7-Point Framework)
    print("🎬 Generating Concept Rule Reel...", flush=True)
    render_concept_video(script_data, CONCEPT_VIDEO)
    
    # 2. Quiz Reel (Exact Original Logic Locked)
    print("🧠 Generating 3-Question Quiz Reel...", flush=True)
    render_quiz_video(script_data, QUIZ_VIDEO)
    
    # Progress Increment Logic
    if st["current_part"] < st["total_parts"]:
        st["current_part"] += 1
    else:
        st["current_part"] = 1
        st["clause_no"] += 1
        
    _, pdf_text = extract_clause_from_pdf(st["clause_no"], st["current_part"])
    st["total_parts"] = get_dynamic_total_parts(pdf_text)
    
    save_progress_state(st)
    print(f"🔄 Next Target Set -> Clause {st['clause_no']} Part {st['current_part']}/{st['total_parts']}", flush=True)
    
    auto_commit_and_push_reels()
    print("🎉 Done! Both reels generated and progress updated successfully.", flush=True)
