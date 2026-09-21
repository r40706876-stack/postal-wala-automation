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

# --- Master Official Clause Titles (PO Guide Part 1 Source of Truth) ---
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

# --- Standard Context Fallbacks (Guaranteed Authentic PO Guide Part 1 Content) ---
OFFICIAL_CLAUSE_CONTEXT = {
    1: "डाक विभाग संचार मंत्रालय के तहत कार्य करता है। इसका प्रशासनिक नियंत्रण महानिदेशक डाक सेवा (DG Posts) के अधीन होता है। शीर्ष प्रबंधन निकाय डाक सेवा बोर्ड (PSB) है जिसके पदेन अध्यक्ष सचिव (डाक) होते हैं।",
    2: "डाकघर गाइड भाग 1 के क्लॉज 2 के तहत डाकघरों को तीन वर्गों में विभाजित किया गया है: 1. प्रधान डाकघर (Head Post Office), 2. उप डाकघर (Sub Post Office), और 3. शाखा डाकघर (Branch Post Office)। प्रधान डाकघर डाक मंडल का मुख्य लेखा कार्यालय होता है। शाखा डाकघर का अधिकतम कार्य समय 5 घंटे निर्धारित है।",
    3: "रात्रि कालीन डाकघर (Night Post Office) का निर्धारण और कार्य समय महानिदेशक (DG Posts) द्वारा तय किया जाता है। ये सामान्यतः कार्य दिवसों में रात 8:30 बजे तक कार्य करते हैं तथा रविवार और छुट्टियों के दिन भी सीमित सेवाओं हेतु खुले रहते हैं।",
    4: "चलते-फिरते डाकघर (Mobile Post Office) उन क्षेत्रों में सेवा देते हैं जहां स्थायी डाकघर नहीं होते। ये रविवार और डाकघर छुट्टियों पर बंद रहते हैं। इनमें मनी ऑर्डर और वीपी पार्सल स्वीकार नहीं किए जाते।",
    5: "सामान्य कार्य दिवसों में विभिन्न सेवाओं के कार्य घंटे (Business Hours) सर्किल प्रमुख (Head of Circle/CPMG) द्वारा तय किए जाते हैं। बचत बैंक व मनी ऑर्डर लगभग 5 घंटे, रजिस्ट्री व पार्सल 6-7 घंटे और टिकट बिक्री पूरे समय होती है।"
}

# --- Folders and Video Outputs ---
REELS_DIR = "generated_reels"
os.makedirs(REELS_DIR, exist_ok=True)

CONCEPT_VIDEO = os.path.join(REELS_DIR, "concept_reel.mp4")
QUIZ_VIDEO = os.path.join(REELS_DIR, "quiz_reel.mp4")

BGM_OUTPUT = "bgm.mp3"
VOICE_NAME = "hi-IN-SwaraNeural"

ASSETS_DIR = "assets"
RESAMPLE_MODE = getattr(Image, "Resampling", Image).LANCZOS

# --- Crisp, Unique & Exam-Targeted Hooks (GDS to MTS, Postman, PA) (<3.5s) ---
VIRAL_HOOKS = [
    {
        "voice": "जीडीएस से एमटीएस, पोस्टमैन और पी.ए. परीक्षा में यह नियम बार-बार आता है!",
        "visual_badge": "[ ! ] GDS to MTS, PM, PA स्पेशल",
        "hook_text": "GDS to MTS, Postman & PA परीक्षा का सबसे महत्वपूर्ण और पक्का नियम!"
    },
    {
        "voice": "जीडीएस से पोस्टमैन व एमटीएस परीक्षा में नब्बे प्रतिशत छात्र इस नियम में गलती करते हैं!",
        "visual_badge": "[ ! ] 90% छात्र फेल",
        "hook_text": "GDS to MTS, Postman, PA परीक्षा में सबसे ज्यादा गलत होने वाला क्लॉज!"
    },
    {
        "voice": "जीडीएस से एमटीएस, पोस्टमैन या पी.ए. में प्रमोशन पक्का करने के लिए यह नियम रट लीजिए!",
        "visual_badge": "[ ! ] मेरिट लिस्ट बूस्टर",
        "hook_text": "GDS to MTS, PM & PA मेरिट लिस्ट में नाम लाने वाला सबसे जरूरी नियम!"
    },
    {
        "voice": "जीडीएस से एमटीएस और पोस्टमैन परीक्षा का सबसे पसंदीदा सवाल, ध्यान से देखें!",
        "visual_badge": "[ ! ] सीधे 2 अंक पक्के",
        "hook_text": "GDS to MTS, Postman & PA एग्जाम में हर साल आने वाला 100% पक्का सवाल!"
    },
    {
        "voice": "जीडीएस से पोस्टमैन, एमटीएस या पी.ए. बनना है तो यह रील बिल्कुल मिस मत करना!",
        "visual_badge": "[ ! ] प्रमोशन स्पेशल",
        "hook_text": "GDS to MTS, Postman & PA विभागीय परीक्षा पास कराने वाला अनिवार्य क्लॉज!"
    },
    {
        "voice": "जीडीएस से पोस्टमैन और पी.ए. बनने के लिए इस नियम को समझना बहुत जरूरी है!",
        "visual_badge": "[ ! ] परीक्षा रेड अलर्ट",
        "hook_text": "GDS to MTS, PM, PA परीक्षा में नेगेटिव मार्किंग से बचने का जरूरी नियम!"
    }
]

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

# --- Strict PDF Extractor (Confined to PO Guide Part 1 Section) ---
def extract_clause_from_pdf(clause_no, current_part=1, total_parts=1):
    official_title = OFFICIAL_CLAUSE_MAP.get(clause_no, f"पोस्टल गाइड भाग 1 क्लॉज {clause_no}")
    default_text = OFFICIAL_CLAUSE_CONTEXT.get(
        clause_no,
        f"डाक घर गाइड भाग 1 के क्लॉज {clause_no} ({official_title}) का आधिकारिक विभागीय नियम।"
    )
    
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

        start_pattern = re.compile(
            rf"(?:(?:क्लॉज|Clause|नियम)\s*[-:]?\s*{clause_no}\b)",
            re.IGNORECASE
        )
        next_clause = clause_no + 1
        next_pattern = re.compile(
            rf"(?:(?:क्लॉज|Clause|नियम)\s*[-:]?\s*{next_clause}\b)",
            re.IGNORECASE
        )

        lines = full_pdf_text.split('\n')
        capturing = False
        matched_text = ""
        
        for line in lines:
            line_str = line.strip()
            if start_pattern.search(line_str) and not capturing:
                if re.match(rf"^\s*[\(\[]?{clause_no}\s*[\)\]]", line_str):
                    continue
                capturing = True
                continue
            
            if capturing:
                if next_pattern.search(line_str) and len(matched_text.strip()) > 30:
                    break
                matched_text += line + "\n"

        unwanted_keywords = ["संतोष", "बाल जीवन बीमा", "सुरक्षा", "सुविधा", "युगल सुरक्षा", "प्रीमियम दर"]
        if any(w in matched_text for w in unwanted_keywords):
            matched_text = ""

        full_text = matched_text.strip() if len(matched_text.strip()) > 40 else default_text
        
        if total_parts > 1 and len(full_text) > 200:
            chunk_len = max(100, len(full_text) // total_parts)
            start = (current_part - 1) * chunk_len
            end = start + chunk_len if current_part < total_parts else len(full_text)
            part_text = full_text[start:end]
            if len(part_text.strip()) < 50:
                part_text = full_text
        else:
            part_text = full_text

        return official_title, clean_hindi_postal_terms(part_text[:3500])
    except Exception as e:
        print(f"⚠️ PDF Extraction Note: {e}", flush=True)
    return official_title, default_text

def get_dynamic_total_parts(pdf_text):
    if not pdf_text:
        return 1
    char_count = len(pdf_text.strip())
    calculated_parts = max(1, (char_count // 350) + (1 if char_count % 350 > 0 else 0))
    return calculated_parts

def extract_field_block(text, field_name, next_fields):
    pattern = r"(?:^|\n)\s*(?:\*\*)?" + re.escape(field_name) + r"(?:\*\*)?\s*:\s*(.*?)(?=(?:\n\s*(?:\*\*)?(?:" + "|".join(next_fields) + r")(?:\*\*)?\s*:)|$)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        val = re.sub(r"^[\"\'`]+|[\"\'`]+$", "", val).strip()
        return " ".join(val.split())
    return None

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
    state = {"clause_no": 2, "current_part": 1, "total_parts": 1, "hook_index": 0}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                if isinstance(saved, dict) and "clause_no" in saved:
                    state.update(saved)
        except Exception:
            pass
            
    _, pdf_text = extract_clause_from_pdf(state.get("clause_no", 2), state.get("current_part", 1), state.get("total_parts", 1))
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
    current_clause = state.get("clause_no", 2)
    current_part = state.get("current_part", 1)
    total_parts = state.get("total_parts", 1)
    hook_idx = state.get("hook_index", 0) % len(VIRAL_HOOKS)
    hook_obj = VIRAL_HOOKS[hook_idx]

    official_title, official_pdf_text = extract_clause_from_pdf(current_clause, current_part, total_parts)

    if current_clause == 2:
        fallback_data = {
            "clause_no": 2,
            "clause_name": "डाकघरों के प्रकार (प्रधान, उप व शाखा डाकघर)",
            "part_no": current_part,
            "total_parts": total_parts,
            "visual_hook_badge": hook_obj["visual_badge"],
            "hook_voice": hook_obj["voice"],
            "hook_display_text": hook_obj["hook_text"],
            "sen1": "डाकघर गाइड भाग 1 के क्लॉज 2 के अनुसार डाकघर तीन श्रेणियों में विभाजित हैं: प्रधान, उप और शाखा डाकघर।",
            "sen2": "प्रधान डाकघर मंडल का मुख्य लेखा कार्यालय होता है और शाखा डाकघर का अधिकतम कार्य समय 5 घंटे होता है।",
            "param1_title": "डाकघर के वर्ग",
            "param1_val": "कुल 3 श्रेणियां (HO, SO, BO)",
            "param2_title": "शाखा डाकघर कार्य समय",
            "param2_val": "अधिकतम 5 घंटे निर्धारित",
            "trap_point": "शाखा डाकघर सीधे प्रधान डाकघर या उप डाकघर दोनों में से किसी के भी लेखा अधिकार क्षेत्र में हो सकता है।",
            "question": "डाकघर गाइड भाग 1 के अनुसार डाकघरों को कुल कितने वर्गों (Classes) में बांटा गया है?",
            "opt_a": "3 वर्ग (प्रधान, उप, शाखा डाकघर)",
            "opt_b": "2 वर्ग (केवल प्रधान व उप)",
            "opt_c": "4 वर्ग (प्रथम, द्वितीय, तृतीय श्रेणी)",
            "opt_d": "5 वर्ग",
            "q1": "शाखा डाकघर (Branch Post Office) का अधिकतम दैनिक कार्य समय कितना निर्धारित है?",
            "a1": "अधिकतम 5 घंटे",
            "b1": "अधिकतम 8 घंटे",
            "c1": "अधिकतम 3 घंटे",
            "d1": "पूरे 7 घंटे",
            "ans1": "A",
            "q2": "डाक मंडल में लेखा और वित्तीय हिसाब-किताब का मुख्य कार्यालय कौन सा होता है?",
            "a2": "उप डाकघर",
            "b2": "प्रधान डाकघर (Head Post Office)",
            "c2": "रेल डाक सेवा (RMS)",
            "d2": "सर्किल कार्यालय",
            "ans2": "B",
            "q3": "उप डाकघर (Sub Post Office) का प्रभारी अधिकारी कौन होता है?",
            "a3": "मंडल अधीक्षक (SSPO)",
            "b3": "शाखा डाकपाल (BPM)",
            "c3": "उप डाकपाल (Sub Postmaster)",
            "d3": "पोस्टमैन",
            "ans3": "C",
            "caption": f"🚨 पीओ गाइड भाग 1 क्लॉज {current_clause} स्पेशल टेस्ट! (भाग {current_part}/{total_parts})。\n\n💬 फ्री मॉक टेस्ट के लिए MOCK कमेंट करें और Postal Wala को फॉलो करें!\n\n#PostalWala #GDStoMTS #PostmanExam #IndiaPost #DepartmentalExam",
            "quiz_caption": f"🧠 क्विज़: पीओ गाइड भाग 1 | क्लॉज {current_clause} (भाग {current_part}/{total_parts})。\n\n🎯 3 महत्वपूर्ण सवाल! फ्री मॉक टेस्ट के लिए MOCK कमेंट करें और फॉलो करें!\n\n#PostalQuiz #GDStoMTS #PostmanExam #DepartmentalQuiz"
        }
    else:
        fallback_data = {
            "clause_no": current_clause,
            "clause_name": official_title,
            "part_no": current_part,
            "total_parts": total_parts,
            "visual_hook_badge": hook_obj["visual_badge"],
            "hook_voice": hook_obj["voice"],
            "hook_display_text": hook_obj["hook_text"],
            "sen1": f"डाक घर गाइड भाग 1 क्लॉज {current_clause} के अनुसार आधिकारिक विभागीय नियम मान्य होता है।",
            "sen2": f"विभागीय परीक्षा में क्लॉज {current_clause} के अपवाद और शर्तों से सीधे सवाल पूछे जाते हैं।",
            "param1_title": "परीक्षा मुख्य बिंदु",
            "param1_val": "आधिकारिक नियम मान्य",
            "param2_title": "विभागीय शर्त",
            "param2_val": "नियमों का पालन अनिवार्य",
            "trap_point": "इस नियम की अनदेखी करने पर विभागीय परीक्षा में अंक कट सकते हैं।",
            "question": f"डाक घर गाइड भाग 1 के क्लॉज {current_clause} का मुख्य विषय क्या है?",
            "opt_a": official_title,
            "opt_b": "अतिरिक्त सामान्य निर्देश",
            "opt_c": "सर्किल प्रमुख का विशेष आदेश",
            "opt_d": "महानिदेशक की पूर्व अनुमति",
            "q1": f"डाक गाइड क्लॉज {current_clause} के अनुसार मुख्य प्रावधान क्या है?", "a1": "आधिकारिक विभागीय नियम", "b1": "अतिरिक्त छूट", "c1": "सामान्य निर्देश", "d1": "विशेष छूट", "ans1": "A",
            "q2": "इस नियम के तहत परीक्षा में क्या विशेष ध्यान रखना चाहिए?", "a2": "अस्थायी छूट", "b2": "आधिकारिक शर्तें व सीमाएं", "c2": "प्रतिबंध", "d2": "वार्षिक बदलाव", "ans2": "B",
            "q3": "नियम का उल्लंघन होने पर विभाग द्वारा क्या कार्रवाई होती है?", "a3": "अतिरिक्त जांच", "b3": "चेतावनी", "c3": "बुकिंग अस्वीकार", "d3": "फीस माफी", "ans3": "C",
            "caption": f"🚨 पोस्टल गाइड क्लॉज {current_clause} स्पेशल टेस्ट! डाक घर गाइड भाग 1 (भाग {current_part}/{total_parts})。\n\n💬 फ्री मॉक टेस्ट के लिए MOCK कमेंट करें और Postal Wala को फॉलो करें!\n\n#PostalWala #GDStoMTS #PostmanExam #IndiaPost #DepartmentalExam",
            "quiz_caption": f"🧠 क्विज़: डाक घर गाइड भाग 1 | क्लॉज {current_clause} (भाग {current_part}/{total_parts})。\n\n🎯 3 महत्वपूर्ण सवाल! फ्री मॉक टेस्ट के लिए MOCK कमेंट करें और फॉलो करें!\n\n#PostalQuiz #GDStoMTS #PostmanExam #DepartmentalQuiz"
        }

    if not GROQ_API_KEY:
        return fallback_data

    prompt = f"""
    You are the Senior Chief Examiner for India Post Departmental Examinations (GDS to MTS, Postman, Mail Guard, Postal Assistant).
    Topic: Post Office Guide Part 1, Clause: {current_clause}, Part: {current_part}/{total_parts}, Official Subject: "{official_title}"

    Reference Context:
    \"\"\"
    {official_pdf_text}
    \"\"\"

    STRICT SYLLABUS BOUNDARY & EXAM INTEGRITY:
    1. EXCLUSIVELY POST OFFICE GUIDE PART 1 (CLAUSE {current_clause}):
       - Generate questions ONLY on "{official_title}".
       - STRICT NEGATIVE CONSTRAINT: DO NOT generate questions on PLI, RPLI (e.g., Santosh, Suraksha, Bal Jeevan Bima, Suvidha), Savings Certificates, or General Knowledge. Any mention of insurance schemes is strictly forbidden.
    2. AUTHENTIC POSTAL QUESTIONS: Test Competent Authorities (DG Posts, Head of Circle, SSPO, Postmaster), Working Hours, Account Relationships, Categories of Offices (HO, SO, BO).
    3. NO SILLY OPTIONS: Every option must be a genuine postal designation, accurate duration, or official rule. Never use 'पुरस्कार', 'कुछ नहीं', 'कोई नहीं', or truncated words.
    4. QUESTION INTEGRITY: Ensure QUESTION, Q1, Q2, and Q3 are full, grammatically complete question sentences.
    5. DIVERSE ANSWERS: ANS1, ANS2, ANS3 must NOT all be the same option letter.

    Format strictly using these tags line-by-line:
    SEN1: ...
    SEN2: ...
    PARAM1_TITLE: ...
    PARAM1_VAL: ...
    PARAM2_TITLE: ...
    PARAM2_VAL: ...
    TRAP_POINT: ...
    QUESTION: ...
    OPT_A: ...
    OPT_B: ...
    OPT_C: ...
    OPT_D: ...
    Q1: ...
    A1: ...
    B1: ...
    C1: ...
    D1: ...
    ANS1: A
    Q2: ...
    A2: ...
    B2: ...
    C2: ...
    D2: ...
    ANS2: B
    Q3: ...
    A3: ...
    B3: ...
    C3: ...
    D3: ...
    ANS3: C
    """

    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"}
        payload = {"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.0, "max_tokens": 800}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=25)
        if res.status_code == 200:
            raw_text = res.json()["choices"][0]["message"]["content"].strip()
            
            q_val = extract_field_block(raw_text, "QUESTION", ["OPT_A", "SEN1"])
            oa_val = extract_field_block(raw_text, "OPT_A", ["OPT_B", "QUESTION"])
            ob_val = extract_field_block(raw_text, "OPT_B", ["OPT_C", "QUESTION"])
            oc_val = extract_field_block(raw_text, "OPT_C", ["OPT_D", "QUESTION"])
            od_val = extract_field_block(raw_text, "OPT_D", ["Q1", "QUESTION"])

            if q_val and len(q_val) > 10: fallback_data["question"] = clean_hindi_postal_terms(q_val)
            if oa_val: fallback_data["opt_a"] = clean_hindi_postal_terms(oa_val)
            if ob_val: fallback_data["opt_b"] = clean_hindi_postal_terms(ob_val)
            if oc_val: fallback_data["opt_c"] = clean_hindi_postal_terms(oc_val)
            if od_val: fallback_data["opt_d"] = clean_hindi_postal_terms(od_val)

            for line in raw_text.split('\n'):
                if ':' in line:
                    parts = line.split(':', 1)
                    k = parts[0].strip().lower()
                    v = parts[1].strip().strip('"\'`*')
                    if k in fallback_data:
                        clean_v = clean_hindi_postal_terms(v)
                        unwanted = ["पुरस्कार", "कुछ नहीं", "संतोष", "बाल जीवन बीमा", "सुरक्षा"]
                        if not any(u in clean_v for u in unwanted) and len(clean_v) > 1:
                            fallback_data[k] = clean_v
                        if k.startswith("ans"):
                            fallback_data[k] = fallback_data[k].upper()[:1]
    except Exception as e:
        print(f"⚠️ Groq note: {e}")

    if fallback_data.get("ans1") == fallback_data.get("ans2") == fallback_data.get("ans3"):
        fallback_data["ans1"] = "A"
        fallback_data["ans2"] = "B"
        fallback_data["ans3"] = "C"

    return fallback_data

# --- AUDIO GENERATION (TTS Sanitized & Fluent) ---
async def generate_segment_audio(text, outfile, rate="+0%"):
    if os.path.exists(outfile):
        try: os.remove(outfile)
        except Exception: pass
        
    clean_audio_text = re.sub(r"[\*#`_~\[\]\(\)]", " ", text)
    clean_audio_text = " ".join(clean_audio_text.split()).strip()

    success = False
    if GEMINI_API_KEY:
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-3.1-flash-tts-preview",
                contents=clean_audio_text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Puck"
                            )
                        )
                    )
                )
            )
            
            audio_bytes = None
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.inline_data and part.inline_data.data:
                            audio_bytes = part.inline_data.data
                            break
                if audio_bytes:
                    break
                    
            if audio_bytes:
                temp_pcm = outfile + ".pcm"
                with open(temp_pcm, "wb") as f:
                    f.write(audio_bytes)
                
                subprocess.run([
                    "ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                    "-i", temp_pcm, "-codec:a", "libmp3lame", "-b:a", "192k", outfile
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if os.path.exists(temp_pcm):
                    os.remove(temp_pcm)
                    
                if os.path.exists(outfile) and os.path.getsize(outfile) > 1000:
                    success = True
                    print(f"🎙️ Audio generated via Gemini TTS", flush=True)
        except Exception as e:
            print(f"⚠️ Gemini TTS fallback to Edge-TTS: {e}", flush=True)

    if not success:
        communicate = edge_tts.Communicate(text=clean_audio_text, voice=VOICE_NAME, rate=rate)
        await communicate.save(outfile)
        print(f"🎙️ Audio generated via Edge-TTS (SwaraNeural)", flush=True)

def get_audio_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    return float(subprocess.check_output(cmd).decode().strip())

# --- CONCEPT RULE VIDEO ---
def render_concept_video(script_data, output_video=CONCEPT_VIDEO):
    ensure_fonts()
    segment_audios = [
        script_data["hook_voice"],
        script_data["sen1"],
        f"परीक्षा विशेष बिंदु: {script_data['sen2']}",
        "सवाल स्क्रीन पर है! सही उत्तर A, B, C या D कमेंट करें! इस क्लॉज से जुड़े 100% एग्जाम में आने वाले क्वेश्चन अगली रील में हैं! तो फॉलो करो और जाकर देखो"
    ]
    durations = []
    for i, seg_text in enumerate(segment_audios):
        seg_file = f"audio_concept_{i}.mp3"
        asyncio.run(generate_segment_audio(seg_text, seg_file, rate="+0%"))
        durations.append(get_audio_duration(seg_file))

    concat_filter = "".join([f"[{i}:a]" for i in range(4)]) + "concat=n=4:v=0:a=1[aout]"
    ffmpeg_concat_cmd = ["ffmpeg", "-y"]
    for i in range(4):
        ffmpeg_concat_cmd.extend(["-i", f"audio_concept_{i}.mp3"])
    ffmpeg_concat_cmd.extend(["-filter_complex", concat_filter, "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "concept_master.mp3"])
    subprocess.run(ffmpeg_concat_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    total_dur = sum(durations)

    font_brand = get_font(44)
    font_sub = get_font(22)
    font_trust = get_font(20)
    font_badge = get_font(22)
    font_title = get_font(32)
    font_h1 = get_font(38)
    font_h2 = get_font(30)
    font_body = get_font(34)
    font_label = get_font(26)
    font_wa_hin = get_font(28)
    font_wa_num = get_font(28)
    font_cta = get_font(30)
    font_opt = get_font(28)
    font_hook = get_font(36)
    font_timer = get_font(32)

    def draw_base(d):
        d.rounded_rectangle([45, 50, 1035, 1710], radius=32, fill="#0B132B", outline="#1E293B", width=3)
        d.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        d.text((80, 130), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)
        d.rounded_rectangle([630, 80, 1000, 132], radius=16, fill="#064E3B", outline="#10B981", width=2)
        d.text((655, 93), "100% OFFICIAL SYLLABUS", fill="#D1FAE5", font=font_trust)

    def draw_whatsapp_strip(d):
        d.rounded_rectangle([80, 345, 1000, 455], radius=18, fill="#064E3B", outline="#34D399", width=2)
        d.text((110, 360), "GDS to MTS • Postman • Mail Guard • P.A.", fill="#FDE047", font=font_wa_num)
        d.text((110, 405), "कोर्स व फ्री टेस्ट हेतु व्हाट्सएप: 8989971379", fill="#FFFFFF", font=font_wa_hin)

    def draw_footer_cta(d):
        d.rounded_rectangle([80, 1580, 1000, 1680], radius=22, fill="#E11D48")
        d.text((120, 1605), "पूरी तैयारी के लिए फॉलो करें:  @POSTAL_WALA", fill="#FFFFFF", font=font_cta)

    def draw_header_card(d):
        d.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
        d.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
        d.text((120, 195), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
        d.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
        d.text((845, 195), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
        
        clean_title = clean_hindi_postal_terms(script_data["clause_name"])
        if len(clean_title) > 38:
            clean_title = clean_title[:36] + "..."
        d.text((105, 255), clean_title, fill="#FFFFFF", font=font_title)

    frames = []
    frame_durs = []

    def build_slide1_frame(step, pill_state=True):
        img = Image.new("RGB", (1080, 1920), color="#060A17")
        d = ImageDraw.Draw(img)
        draw_base(d)
        draw_header_card(d)

        d.rounded_rectangle([80, 360, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
        
        if pill_state:
            d.rounded_rectangle([110, 395, 410, 445], radius=12, fill="#DC2626", outline="#F87171", width=3)
            d.text((130, 402), "[ ! ] LIVE EXAM ALERT", fill="#FFFFFF", font=font_label)
        else:
            d.rounded_rectangle([110, 395, 410, 445], radius=12, fill="#180C0E", outline="#3F1215", width=1)
            d.text((130, 402), "[ ! ] LIVE EXAM ALERT", fill="#7F1D1D", font=font_label)

        d.rounded_rectangle([110, 470, 970, 580], radius=16, fill="#991B1B", outline="#FBBF24", width=3)
        d.text((150, 500), clean_hindi_postal_terms(script_data["visual_hook_badge"]), fill="#FEF08A", font=font_hook)

        if step >= 2:
            d.rounded_rectangle([110, 620, 970, 680], radius=12, fill="#0F172A", outline="#38BDF8", width=2)
            d.text((135, 633), "🎯 टारगेट: GDS to MTS • Postman • Mail Guard • P.A.", fill="#38BDF8", font=font_h2)
            wrapped_hook = textwrap.fill(clean_hindi_postal_terms(script_data["hook_display_text"]), width=20)
            d.multiline_text((115, 725), wrapped_hook, fill="#FFFFFF", font=font_h1, spacing=16)

        if step >= 3:
            d.rounded_rectangle([110, 1060, 970, 1240], radius=18, fill="#0B132B", outline="#FBBF24", width=2)
            d.text((150, 1095), f"विषय: {clean_hindi_postal_terms(script_data['clause_name'])[:35]}", fill="#FDE047", font=font_h2)
            d.text((150, 1160), f"डाक घर गाइड भाग 1 | क्लॉज संख्या: {script_data['clause_no']}", fill="#94A3B8", font=font_opt)
            
            d.rounded_rectangle([110, 1275, 970, 1365], radius=14, fill="#082F49", outline="#38BDF8", width=2)
            d.text((145, 1300), "🎯 100% सटीक तैयारी: GDS to MTS • Postman • P.A.", fill="#7DD3FC", font=font_h2)

            d.rounded_rectangle([110, 1400, 970, 1490], radius=16, fill="#064E3B", outline="#10B981", width=2)
            d.text((200, 1425), ">> 25 सेकंड में पूरा नियम समझें!", fill="#34D399", font=font_h2)

        draw_footer_cta(d)
        return img

    s1_dur = max(3.0, durations[0])
    blink_seq = [
        (1, True,  0.35),
        (1, False, 0.25),
        (2, True,  0.40),
        (2, False, 0.25),
        (3, True,  0.45),
        (3, False, 0.25),
        (3, True,  max(0.6, s1_dur - 1.95))
    ]
    for b_idx, (st_step, st_on, st_d) in enumerate(blink_seq):
        fn = f"c_1_blink_{b_idx}.png"
        build_slide1_frame(step=st_step, pill_state=st_on).save(fn)
        frames.append(fn)
        frame_durs.append(round(st_d, 2))

    # Slide 2: Rule with 2 Parameter Cards
    img2a = Image.new("RGB", (1080, 1920), color="#060A17")
    d2a = ImageDraw.Draw(img2a)
    draw_base(d2a)
    draw_header_card(d2a)
    draw_whatsapp_strip(d2a)
    
    d2a.rounded_rectangle([80, 480, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
    d2a.rounded_rectangle([110, 520, 480, 575], radius=10, fill="#0B132B")
    d2a.text((150, 530), "नियम विश्लेषण #1:", fill="#38BDF8", font=font_label)
    wrapped_s2 = textwrap.fill(script_data['sen1'], width=24)
    d2a.multiline_text((120, 610), clean_hindi_postal_terms(wrapped_s2), fill="#F8FAFC", font=font_body, spacing=14)

    d2a.rounded_rectangle([110, 830, 970, 970], radius=16, fill="#082F49", outline="#38BDF8", width=2)
    d2a.rounded_rectangle([130, 850, 430, 895], radius=8, fill="#0284C7")
    d2a.text((145, 858), f"[ {script_data.get('param1_title', 'परीक्षा मुख्य बिंदु')} ]", fill="#FFFFFF", font=font_label)
    d2a.text((145, 915), script_data.get('param1_val', 'नियम अनुसार मान्य'), fill="#E0F2FE", font=font_h2)
    
    draw_footer_cta(d2a)
    img2a.save("c_2a.png")
    frames.append("c_2a.png")
    frame_durs.append(round(durations[1] * 0.40, 2))

    img2b = img2a.copy()
    d2b = ImageDraw.Draw(img2b)
    d2b.rounded_rectangle([110, 1010, 970, 1150], radius=16, fill="#451A03", outline="#F59E0B", width=2)
    d2b.rounded_rectangle([130, 1030, 430, 1075], radius=8, fill="#D97706")
    d2b.text((145, 1038), f"[ {script_data.get('param2_title', 'विभागीय शर्त')} ]", fill="#FFFFFF", font=font_label)
    d2b.text((145, 1095), script_data.get('param2_val', 'आधिकारिक नियम'), fill="#FEF3C7", font=font_h2)
    img2b.save("c_2b.png")
    frames.append("c_2b.png")
    frame_durs.append(round(durations[1] * 0.35, 2))

    img2c = img2b.copy()
    d2c = ImageDraw.Draw(img2c)
    d2c.rounded_rectangle([110, 1370, 970, 1470], radius=14, fill="#0B132B", outline="#38BDF8", width=2)
    d2c.text((160, 1400), "आगे देखिए: इस नियम का परीक्षा ट्रैप बिंदु >>", fill="#38BDF8", font=font_h2)
    img2c.save("c_2c.png")
    frames.append("c_2c.png")
    frame_durs.append(round(durations[1] * 0.25, 2))

    # Slide 3: Trap Point (Full Width Utilization - Guaranteed Zero Overlap)
    img3a = Image.new("RGB", (1080, 1920), color="#060A17")
    d3a = ImageDraw.Draw(img3a)
    draw_base(d3a)
    draw_header_card(d3a)
    draw_whatsapp_strip(d3a)
    
    d3a.rounded_rectangle([80, 480, 1000, 1550], radius=24, fill="#1C2541", outline="#FBBF24", width=3)
    d3a.rounded_rectangle([110, 510, 450, 565], radius=10, fill="#0B132B")
    d3a.text((130, 520), "परीक्षा अपवाद #2:", fill="#FBBF24", font=font_label)
    
    wrapped_s3 = textwrap.fill(clean_hindi_postal_terms(script_data['sen2']), width=40)
    d3a.multiline_text((120, 590), wrapped_s3, fill="#F8FAFC", font=font_body, spacing=14)
    
    s3_bbox = d3a.multiline_textbbox((120, 590), wrapped_s3, font=font_body, spacing=14)
    sen2_bottom = s3_bbox[3]
    
    draw_footer_cta(d3a)
    img3a.save("c_3a.png")
    frames.append("c_3a.png")
    frame_durs.append(round(durations[2] * 0.35, 2))

    img3b = img3a.copy()
    d3b = ImageDraw.Draw(img3b)
    d3b.rounded_rectangle([80, 480, 1000, 1550], radius=24, outline="#EF4444", width=4)
    
    trap_txt = script_data.get("trap_point", script_data["sen2"])
    wrapped_trap = textwrap.fill(clean_hindi_postal_terms(trap_txt), width=42)
    
    trap_top = max(sen2_bottom + 40, 750)
    dummy_trap_bbox = d3b.multiline_textbbox((140, trap_top + 80), wrapped_trap, font=font_h2, spacing=12)
    trap_bottom = min(1360, dummy_trap_bbox[3] + 35)

    d3b.rounded_rectangle([110, trap_top, 970, trap_bottom], radius=18, fill="#380A0A", outline="#EF4444", width=3)
    d3b.rounded_rectangle([130, trap_top + 15, 460, trap_top + 65], radius=8, fill="#7F1D1D")
    d3b.text((145, trap_top + 23), "[ ! ] परीक्षा में फंसने वाला बिंदु", fill="#FECACA", font=font_label)
    
    d3b.multiline_text((140, trap_top + 80), wrapped_trap, fill="#FFFFFF", font=font_h2, spacing=12)
    img3b.save("c_3b.png")
    frames.append("c_3b.png")
    frame_durs.append(round(durations[2] * 0.35, 2))

    img3c = img3b.copy()
    d3c = ImageDraw.Draw(img3c)
    d3c.rounded_rectangle([110, 1380, 970, 1470], radius=14, fill="#0B132B", outline="#FBBF24", width=2)
    d3c.text((180, 1410), "अब आज का सवाल: उत्तर कमेंट करें >>", fill="#FDE047", font=font_h2)
    img3c.save("c_3c.png")
    frames.append("c_3c.png")
    frame_durs.append(round(durations[2] * 0.30, 2))

    # Slide 4: Question & Live Countdown Timer
    img4a = Image.new("RGB", (1080, 1920), color="#060A17")
    d4a = ImageDraw.Draw(img4a)
    draw_base(d4a)
    draw_header_card(d4a)
    d4a.rounded_rectangle([80, 350, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
    d4a.rounded_rectangle([110, 380, 360, 435], radius=10, fill="#0B132B")
    d4a.text((140, 390), "आज का सवाल:", fill="#FBBF24", font=font_h2)

    d4a.rounded_rectangle([390, 380, 970, 435], radius=10, fill="#064E3B", outline="#10B981", width=2)
    d4a.text((415, 393), "🎯 GDS to MTS • Postman • P.A. परीक्षा", fill="#A7F3D0", font=font_badge)

    wrapped_q4 = textwrap.fill(clean_hindi_postal_terms(script_data["question"]), width=25)
    d4a.multiline_text((110, 460), wrapped_q4, fill="#F8FAFC", font=font_h2, spacing=10)
    draw_footer_cta(d4a)
    img4a.save("c_4a.png")
    frames.append("c_4a.png")
    frame_durs.append(round(durations[3] * 0.15, 2))

    img4b = img4a.copy()
    d4b = ImageDraw.Draw(img4b)
    q_lines = wrapped_q4.count("\n") + 1
    start_oy = 460 + (q_lines * 42) + 50
    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    labels = ["A", "B", "C", "D"]
    for o_idx in range(2):
        oy = start_oy + (o_idx * 135)
        d4b.rounded_rectangle([110, oy, 970, oy + 95], radius=16, fill="#0B132B", outline="#38BDF8", width=2)
        d4b.text((135, oy + 24), f"{labels[o_idx]})", fill="#38BDF8", font=font_h2)
        d4b.text((200, oy + 26), textwrap.fill(clean_hindi_postal_terms(opts[o_idx]), width=25), fill="#FFFFFF", font=font_opt)
    img4b.save("c_4b.png")
    frames.append("c_4b.png")
    frame_durs.append(round(durations[3] * 0.15, 2))

    img4c = img4b.copy()
    d4c = ImageDraw.Draw(img4c)
    for o_idx in range(2, 4):
        oy = start_oy + (o_idx * 135)
        d4c.rounded_rectangle([110, oy, 970, oy + 95], radius=16, fill="#0B132B", outline="#38BDF8", width=2)
        d4c.text((135, oy + 24), f"{labels[o_idx]})", fill="#38BDF8", font=font_h2)
        d4c.text((200, oy + 26), textwrap.fill(clean_hindi_postal_terms(opts[o_idx]), width=25), fill="#FFFFFF", font=font_opt)
    img4c.save("c_4c.png")
    frames.append("c_4c.png")
    frame_durs.append(round(durations[3] * 0.15, 2))

    countdown_steps = [
        ("05", "#FDE047", "#064E3B", "#34D399"),
        ("04", "#FDE047", "#064E3B", "#34D399"),
        ("03", "#FB923C", "#7C2D12", "#FB923C"),
        ("02", "#F87171", "#7F1D1D", "#EF4444"),
        ("01", "#EF4444", "#991B1B", "#FCA5A5")
    ]
    
    quiz_rem_dur = max(3.5, durations[3] * 0.55)
    per_timer_dur = round(quiz_rem_dur / 5.0, 2)

    for c_idx, (sec_str, timer_color, bar_bg, bar_outline) in enumerate(countdown_steps):
        img_cd = img4c.copy()
        d_cd = ImageDraw.Draw(img_cd)
        
        d_cd.rounded_rectangle([110, 1270, 970, 1345], radius=14, fill="#0B132B", outline=timer_color, width=2)
        d_cd.text((260, 1285), f"⏳ समय शेष: {sec_str} सेकंड", fill=timer_color, font=font_timer)

        d_cd.rounded_rectangle([110, 1375, 970, 1490], radius=18, fill=bar_bg, outline=bar_outline, width=3)
        d_cd.text((180, 1415), ">> अपना उत्तर (A, B, C, D) कमेंट करें!", fill="#FFFFFF", font=font_h2)

        cd_fname = f"c_4_timer_{c_idx}.png"
        img_cd.save(cd_fname)
        frames.append(cd_fname)
        frame_durs.append(per_timer_dur)

    inputs = []
    filter_parts = ""
    for i, fname in enumerate(frames):
        inputs.extend(["-i", fname])
        safe_dur = max(0.2, frame_durs[i])
        filter_parts += f"[{i}:v]loop=loop=-1:size=1:start=0,trim=duration={safe_dur}[v{i}]; "

    concat_str = "".join([f"[v{i}]" for i in range(len(frames))])
    base_v_filter = f"{filter_parts}{concat_str}concat=n={len(frames)}:v=1:a=0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
    
    progress_bar_filter = (
        f"{base_v_filter},"
        f"drawbox=x=0:y=0:w=iw:h=14:color=#1E293B@1:t=fill,"
        f"drawbox=x=0:y=0:w='iw*(t/{total_dur})':h=14:color=#F43F5E@1:t=fill,"
        f"drawbox=x='max(0, iw*(t/{total_dur})-20)':y=0:w=20:h=14:color=#FEF08A@1:t=fill[v]"
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
        "-c:v", "libx264", "-preset", "medium", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-shortest", output_video
    ])

    subprocess.run(cmd, check=True)
    print(f"✅ Concept Rule Reel Created (Clean & Accurate): {output_video}", flush=True)

# --- 3-QUESTION 40-SEC LOCKED QUIZ VIDEO ---
def render_quiz_video(script_data, output_video=QUIZ_VIDEO):
    ensure_fonts()
    
    questions_list = [
        {"q_num": "सवाल 1/3", "q": clean_hindi_postal_terms(script_data["q1"]), "opts": [clean_hindi_postal_terms(script_data["a1"]), clean_hindi_postal_terms(script_data["b1"]), clean_hindi_postal_terms(script_data["c1"]), clean_hindi_postal_terms(script_data["d1"])], "ans": script_data["ans1"]},
        {"q_num": "सवाल 2/3", "q": clean_hindi_postal_terms(script_data["q2"]), "opts": [clean_hindi_postal_terms(script_data["a2"]), clean_hindi_postal_terms(script_data["b2"]), clean_hindi_postal_terms(script_data["c2"]), clean_hindi_postal_terms(script_data["d2"])], "ans": script_data["ans2"]},
        {"q_num": "सवाल 3/3", "q": clean_hindi_postal_terms(script_data["q3"]), "opts": [clean_hindi_postal_terms(script_data["a3"]), clean_hindi_postal_terms(script_data["b3"]), clean_hindi_postal_terms(script_data["c3"]), clean_hindi_postal_terms(script_data["d3"])], "ans": script_data["ans3"]},
    ]

    # Crisp, exam-targeted quiz intro hook
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

        # Step 1: Question + Option A
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

        # Step 2: Options B & C
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

        # Step 3: Option D + Timer box
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

    # Grand Finale Screen
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
    
    # 1. Generate Concept Rule Reel First
    print("🎬 Generating Concept Rule Reel...", flush=True)
    render_concept_video(script_data, CONCEPT_VIDEO)
    
    # 2. Generate 3-Question Quiz Reel Second
    print("🧠 Generating 3-Question Quiz Reel...", flush=True)
    render_quiz_video(script_data, QUIZ_VIDEO)
    
    # --- AUTOMATIC PROGRESS INCREMENT LOGIC (STRICT SEQUENTIAL) ---
    if st["current_part"] < st["total_parts"]:
        st["current_part"] += 1
    else:
        st["current_part"] = 1
        st["clause_no"] += 1
        
    _, pdf_text = extract_clause_from_pdf(st["clause_no"], st["current_part"])
    st["total_parts"] = get_dynamic_total_parts(pdf_text)
    
    save_progress_state(st)
    print(f"🔄 Next Target Set -> Clause {st['clause_no']} Part {st['current_part']}/{st['total_parts']}", flush=True)
    
    # 3. Auto push both reels to GitHub
    auto_commit_and_push_reels()
    
    print("🎉 Done! Both reels generated and progress updated successfully.", flush=True)
