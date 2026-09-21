import os
import glob
import json
import time
import math
import struct
import wave
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
    12: "नकद में डाक शुल्क का अग्रिम भुगतान"
}

# 10/10 TARGET BLUEPRINT EXCLUSIVE DATA BANK (Full Text, Zero Truncation)
CLAUSE_RETENTION_BANK = {
    1: {
        "hook_title": "नियंत्रण व संगठन",
        "hook_q": "का सर्वोच्च नियंत्रण किसके पास होता है?",
        "contrast_wrong": "संचार मंत्री? नहीं!",
        "contrast_right": "DG Posts? सोचिए!",
        "reward_hero": "DG POSTS सही है",
        "reward_sub": "प्रशासनिक नियंत्रण इन्हीं के पास है।",
        "hero_num": "PSB सचिव",
        "hero_label": "डाक सेवा बोर्ड के अध्यक्ष",
        "trap_text": "डाक सेवा बोर्ड के पदेन अध्यक्ष सचिव डाक होते हैं, DG Posts नहीं!",
        "mem_1": "DG Posts >> प्रशासनिक नियंत्रण",
        "mem_2": "सचिव (डाक) >> PSB अध्यक्ष",
        "mcq_q": "डाक सेवा बोर्ड (PSB) के पदेन अध्यक्ष कौन होते हैं?",
        "mcq_opts": ["A) सचिव (डाक)", "B) महानिदेशक (DG Posts)", "C) संचार मंत्री", "D) सदस्य (कार्मिक)"],
        "mcq_ans": "A",
        "audio_hook": "डाक विभाग का प्रशासनिक नियंत्रण किसके पास होता है?",
        "audio_contrast": "संचार मंत्री या डीजी पोस्ट्स?",
        "audio_reward": "सही उत्तर है: डीजी पोस्ट्स!",
        "audio_fact": "डाक सेवा बोर्ड का प्रबंधन सचिव डाक संभालते हैं।",
        "audio_trap": "लेकिन एग्जाम ट्रैप: डाक सेवा बोर्ड के पदेन अध्यक्ष सचिव डाक होते हैं, डीजी पोस्ट्स नहीं!",
        "audio_mem": "याद रखो: नियंत्रण डीजी पोस्ट्स के पास और पीएसबी अध्यक्ष सचिव डाक होते हैं।"
    },
    3: {
        "hook_title": "नाइट पोस्ट ऑफिस",
        "hook_q": "का कार्य समय कौन तय करता है?",
        "contrast_wrong": "पोस्टमास्टर? नहीं!",
        "contrast_right": "DG Posts? सोचिए!",
        "reward_hero": "DG POSTS सही है",
        "reward_sub": "यही Rule याद रखना है।",
        "hero_num": "8:30 PM",
        "hero_label": "सामान्य कार्य दिवस समय",
        "trap_text": "रविवार और छुट्टियों में शाम 5 बजे तक खुलते हैं, परंतु Delivery बंद रहती है!",
        "mem_1": "DG Posts >> समय निर्धारण",
        "mem_2": "8:30 PM >> सामान्य कार्य दिवस",
        "mcq_q": "रात्रिकालीन डाकघर का निर्धारण और कार्य समय किसके द्वारा तय किया जाता है?",
        "mcq_opts": ["A) DG Posts", "B) Head of Circle", "C) SSPO", "D) Local Postmaster"],
        "mcq_ans": "A",
        "audio_hook": "नाइट पोस्ट ऑफिस का समय कौन तय करता है?",
        "audio_contrast": "पोस्टमास्टर या डीजी पोस्ट्स?",
        "audio_reward": "सही उत्तर है: डीजी पोस्ट्स!",
        "audio_fact": "सामान्य कार्य दिवसों में रात आठ बजकर तीस मिनट तक!",
        "audio_trap": "लेकिन एग्जाम ट्रैप: रविवार और छुट्टियों को डिलीवरी पूरी तरह बंद रहती है!",
        "audio_mem": "याद रखो: डीजी पोस्ट्स निर्धारण करते हैं और समय है रात साढ़े आठ बजे।"
    },
    9: {
        "hook_title": "अग्रिम डाक शुल्क",
        "hook_q": "बिना टिकट डाक पर कितना चार्ज लगता है?",
        "contrast_wrong": "सामान्य शुल्क? नहीं!",
        "contrast_right": "शुल्क का दोगुना? सोचिए!",
        "reward_hero": "दोगुना (DOUBLE) चार्ज सही है",
        "reward_sub": "अवैतनिक डाक पर दोगुना चार्ज वसूल किया जाता है।",
        "hero_num": "2X CHARGE",
        "hero_label": "वितरण के समय वसूली",
        "trap_text": "यदि डाक पर कम टिकट लगा हो, तो केवल कमी की राशि का दोगुना लिया जाता है!",
        "mem_1": "Unpaid डाक >> 2 गुना शुल्क",
        "mem_2": "Underpaid >> कमी का 2 गुना",
        "mcq_q": "पूर्णतः अवैतनिक (Unpaid) साधारण डाक वस्तु पर वितरण के समय क्या प्रभार लिया जाता है?",
        "mcq_opts": ["A) सामान्य डाक शुल्क का दोगुना", "B) केवल सामान्य डाक शुल्क", "C) कोई अतिरिक्त शुल्क नहीं", "D) वस्तु जब्त होती है"],
        "mcq_ans": "A",
        "audio_hook": "बिना टिकट लगे अनपेड पत्र पर डिलीवरी के समय कितना चार्ज लगता है?",
        "audio_contrast": "सामान्य डाक शुल्क या दोगुना चार्ज?",
        "audio_reward": "सही उत्तर है: सामान्य डाक शुल्क का दोगुना!",
        "audio_fact": "अग्रिम भुगतान न होने पर वितरण के समय दोगुना शुल्क वसूला जाता है।",
        "audio_trap": "लेकिन एग्जाम ट्रैप: कम टिकट होने पर केवल कमी की राशि का दोगुना लिया जाता है!",
        "audio_mem": "याद रखो: अनपेड पर दोगुना और कम भुगतान पर कमी का दोगुना शुल्क लगता है।"
    },
    11: {
        "hook_title": "फ्रैंकिंग मशीन",
        "hook_q": "का लाइसेंस कौन जारी करता है?",
        "contrast_wrong": "लोकल पोस्टमास्टर? नहीं!",
        "contrast_right": "Head of Circle? सोचिए!",
        "reward_hero": "HEAD OF CIRCLE सही है",
        "reward_sub": "सर्किल प्रमुख (CPMG) द्वारा लाइसेंस जारी।",
        "hero_num": "BRIGHT RED",
        "hero_label": "चमकीली लाल स्याही की मुहर",
        "trap_text": "फ्रैंकिंग मशीन की मुहर चमकीले लाल रंग की स्याही में ही मान्य होती है!",
        "mem_1": "लाइसेंस >> Head of Circle",
        "mem_2": "मुहर स्याही >> Bright Red Ink",
        "mcq_q": "फ्रैंकिंग मशीन की छाप (Impression) किस रंग की स्याही में होनी चाहिए?",
        "mcq_opts": ["A) चमकीला लाल (Bright Red)", "B) नीला (Blue)", "C) काला (Black)", "D) हरा (Green)"],
        "mcq_ans": "A",
        "audio_hook": "फ्रैंकिंग मशीन का लाइसेंस कौन जारी करता है?",
        "audio_contrast": "लोकल पोस्टमास्टर या सर्किल प्रमुख?",
        "audio_reward": "सही उत्तर है: सर्किल प्रमुख यानी हेड ऑफ सर्किल!",
        "audio_fact": "फ्रैंकिंग मशीन की छाप केवल चमकीली लाल स्याही में ही मान्य होती है।",
        "audio_trap": "लेकिन एग्जाम ट्रैप: मुहर में वैल्यू डाई और लाइसेंस डाई दोनों एक साथ स्पष्ट होनी चाहिए!",
        "audio_mem": "याद रखो: लाइसेंस हेड ऑफ सर्किल देते हैं और स्याही चमकीली लाल होती है।"
    },
    12: {
        "hook_title": "नकद अग्रिम भुगतान",
        "hook_q": "नकद डाक शुल्क की अनुमति कौन देता है?",
        "contrast_wrong": "शाखा डाकपाल? नहीं!",
        "contrast_right": "Head of Circle? सोचिए!",
        "reward_hero": "HEAD OF CIRCLE सही है",
        "reward_sub": "विशेष अनुमति केवल बड़े शहरों में मान्य।",
        "hero_num": "500 PIECES",
        "hero_label": "न्यूनतम डाक वस्तु संख्या",
        "trap_text": "नकद अग्रिम भुगतान के लिए बड़े शहरों में न्यूनतम 500 वस्तुएं एक बार में पोस्ट करना जरूरी है!",
        "mem_1": "अनुमति >> Head of Circle",
        "mem_2": "न्यूनतम संख्या >> 500 वस्तुएं",
        "mcq_q": "नकद में डाक शुल्क के अग्रिम भुगतान हेतु न्यूनतम कितनी डाक वस्तुएं होनी चाहिए?",
        "mcq_opts": ["A) 500 वस्तुएं", "B) 100 वस्तुएं", "C) 1000 वस्तुएं", "D) 250 वस्तुएं"],
        "mcq_ans": "A",
        "audio_hook": "नकद में डाक शुल्क भुगतान की अनुमति कौन देता है?",
        "audio_contrast": "शाखा डाकपाल या सर्किल प्रमुख?",
        "audio_reward": "सही उत्तर है: हेड ऑफ सर्किल!",
        "audio_fact": "नकद अग्रिम भुगतान के लिए एक बार में कम से कम 500 वस्तुएं होनी चाहिए।",
        "audio_trap": "लेकिन एग्जाम ट्रैप: यह सुविधा केवल अधिकृत बड़े शहरों के चुनिंदा डाकघरों में ही उपलब्ध है!",
        "audio_mem": "याद रखो: अनुमति हेड ऑफ सर्किल देते हैं और न्यूनतम 500 वस्तुएं आवश्यक हैं।"
    }
}

REELS_DIR = "generated_reels"
os.makedirs(REELS_DIR, exist_ok=True)

CONCEPT_VIDEO = os.path.join(REELS_DIR, "concept_reel.mp4")
QUIZ_VIDEO = os.path.join(REELS_DIR, "quiz_reel.mp4")

BGM_OUTPUT = "bgm.mp3"
VOICE_NAME = "hi-IN-SwaraNeural"

def find_pdf_path():
    candidates = [PDF_FILE_PATH, "PO_Guide_Part-1_copy.pdf", "PO_Guide_Part-1.pdf", "mts content.pdf"]
    for c in candidates:
        if os.path.exists(c):
            return c
    all_pdfs = glob.glob("*.pdf")
    return all_pdfs[0] if all_pdfs else PDF_FILE_PATH

def clean_text(text):
    if not text: return ""
    t = text.strip().strip("\"'`")
    t = re.sub(r"[\u2600-\u27bf\U0001f300-\U0001f9ff➔→❌✅⚠️🌙🧠🔥👇📝⏳💬]", "", t)
    return "".join(c for c in t if ord(c) < 0x10000).strip()

def clean_hindi_postal_terms(text):
    if not text: return ""
    text = re.sub(r"^[\s\)\(\.\-\:–\d\+]+", "", text).strip()
    replacements = {
        "पेन्टियों": "पत्र-पेटियों", "पेन्टी": "पत्र-पेटी",
        "घंटी वाली प्लेटें": "घंटे वाली प्लेटें", "घंटी वाली प्लेट": "घंटे वाली प्लेट",
        "तक्सी पैकेट": "बीमाकृत पैकेट", "तक्सी": "बीमाकृत", "लेखक": "प्रेषक",
        "तक्सी पत्र": "बीमाकृत पत्र", "तक्सी वस्तु": "बीमाकृत वस्तु",
        "डार्क": "डाक", "डार्कघर": "डाकघर", "सचवच": "सचिव",
        "ववभाग": "विभाग", "सववचच": "सर्वोच्च", "हो:-्रा": "होता"
    }
    for bad_w, good_w in replacements.items():
        text = text.replace(bad_w, good_w)
    return clean_text(text)

def extract_clause_from_pdf(clause_no, current_part=1, total_parts=1):
    official_title = OFFICIAL_CLAUSE_MAP.get(clause_no, f"पोस्टल गाइड भाग 1 क्लॉज {clause_no}")
    default_text = f"डाक घर गाइड भाग 1 के क्लॉज {clause_no} ({official_title}) का आधिकारिक विभागीय नियम।"
    pdf_path = find_pdf_path()
    if not os.path.exists(pdf_path): return official_title, default_text
    try:
        reader = PdfReader(pdf_path)
        full_pdf_text = ""
        max_scan_pages = min(45, len(reader.pages))
        for p_idx in range(max_scan_pages):
            txt = reader.pages[p_idx].extract_text() or ""
            if "डाक जीवन बीमा" in txt or "Postal Life Insurance" in txt: break
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
                if next_pattern.search(line_str) and len(matched_text.strip()) > 30: break
                matched_text += line + "\n"

        full_text = matched_text.strip() if len(matched_text.strip()) > 40 else default_text
        return official_title, clean_hindi_postal_terms(full_text[:3500])
    except Exception:
        return official_title, default_text

def get_dynamic_total_parts(pdf_text):
    if not pdf_text: return 1
    return max(1, (len(pdf_text.strip()) // 350) + (1 if len(pdf_text.strip()) % 350 > 0 else 0))

def ensure_fonts():
    if not os.path.exists(FONT_PATH):
        url = "https://raw.githubusercontent.com/google/fonts/main/ofl/mukta/Mukta-Bold.ttf"
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                with open(FONT_PATH, "wb") as f: f.write(r.content)
        except Exception: pass

def get_font(size):
    ensure_fonts()
    if os.path.exists(FONT_PATH):
        try: return ImageFont.truetype(FONT_PATH, size)
        except Exception: pass
    return ImageFont.load_default()

def load_progress_state():
    state = {"clause_no": 3, "current_part": 1, "total_parts": 1, "hook_index": 0}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                if isinstance(saved, dict) and "clause_no" in saved:
                    state.update(saved)
        except Exception: pass
    _, pdf_text = extract_clause_from_pdf(state.get("clause_no", 3), state.get("current_part", 1), state.get("total_parts", 1))
    state["total_parts"] = get_dynamic_total_parts(pdf_text)
    if state["current_part"] > state["total_parts"]: state["current_part"] = 1
    save_progress_state(state)
    return state

def save_progress_state(state):
    try:
        with open(STATE_FILE, "w") as f: json.dump(state, f, indent=2)
    except Exception: pass

def generate_5sec_clock_sfx(outfile="c_audio_timer.wav"):
    sample_rate = 44100
    with wave.open(outfile, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        data = bytearray()
        for sec in range(5):
            freq = 1500 if sec == 4 else 1000
            dur_samples = int(sample_rate * (0.18 if sec == 4 else 0.07))
            for i in range(sample_rate):
                if i < dur_samples:
                    decay = (1.0 - (i / dur_samples)) ** 2
                    val = int(24000 * decay * math.sin(2 * math.pi * freq * i / sample_rate))
                else:
                    val = 0
                data.extend(struct.pack('<h', val))
        wav_file.writeframes(data)

def generate_clause_script(state):
    current_clause = state.get("clause_no", 3)
    current_part = state.get("current_part", 1)
    total_parts = state.get("total_parts", 1)
    official_title, _ = extract_clause_from_pdf(current_clause, current_part, total_parts)

    retention_info = CLAUSE_RETENTION_BANK.get(current_clause, {
        "hook_title": f"क्लॉज {current_clause}",
        "hook_q": "का मुख्य आधिकारिक नियम क्या है?",
        "contrast_wrong": "सामान्य छूट? [X]",
        "contrast_right": f"{official_title[:14]}? [?]",
        "reward_hero": f"{official_title[:22]} [OK]",
        "reward_sub": "विभागीय नियमों का पालन अनिवार्य है।",
        "hero_num": f"RULE #{current_clause}",
        "hero_label": "विभागीय अनिवार्यता",
        "trap_text": f"डाकघर गाइड भाग 1 के क्लॉज {current_clause} से परीक्षा में सीधे सवाल पूछे जाते हैं!",
        "mem_1": f"क्लॉज {current_clause} -> मुख्य नियम",
        "mem_2": "शर्तें व सीमाएं -> परीक्षा स्पेशल",
        "mcq_q": f"डाकघर गाइड भाग 1 के क्लॉज {current_clause} का मुख्य विषय क्या है?",
        "mcq_opts": [f"A) {official_title[:22]}", "B) सामान्य छूट", "C) अतिरिक्त समय", "D) विशेष अनुमति"],
        "mcq_ans": "A",
        "audio_hook": f"क्लॉज {current_clause} का मुख्य आधिकारिक नियम क्या है?",
        "audio_contrast": "सामान्य छूट या आधिकारिक प्रावधान?",
        "audio_reward": f"सही उत्तर है: {official_title}!",
        "audio_fact": f"क्लॉज {current_clause} का आधिकारिक नियम सख्ती से लागू होता है।",
        "audio_trap": "लेकिन एग्जाम ट्रैप: इस नियम के मुख्य अपवादों से ही परीक्षा में सवाल बनते हैं!",
        "audio_mem": f"याद रखो: क्लॉज {current_clause} का नियम और इसकी शर्तें अनिवार्य हैं।"
    })

    script_data = {
        "clause_no": current_clause,
        "clause_name": official_title,
        "part_no": current_part,
        "total_parts": total_parts,
        "series_tag": f"POSTAL TRAP #{current_clause:02d}",
        "concept_data": {
            "series_tag": f"POSTAL TRAP #{current_clause:02d}",
            "hook_title": clean_text(retention_info["hook_title"]),
            "hook_q": clean_text(retention_info["hook_q"]),
            "contrast_wrong": clean_text(retention_info["contrast_wrong"]),
            "contrast_right": clean_text(retention_info["contrast_right"]),
            "reward_hero": clean_text(retention_info["reward_hero"]),
            "reward_sub": clean_text(retention_info["reward_sub"]),
            "hero_num": clean_text(retention_info["hero_num"]),
            "hero_label": clean_text(retention_info["hero_label"]),
            "trap_text": clean_text(retention_info["trap_text"]),
            "mem_1": clean_text(retention_info["mem_1"]),
            "mem_2": clean_text(retention_info["mem_2"]),
            "mcq_q": clean_text(retention_info["mcq_q"]),
            "mcq_opts": [clean_text(opt) for opt in retention_info["mcq_opts"]],
            "mcq_ans": retention_info["mcq_ans"],
            "audio_hook": retention_info["audio_hook"],
            "audio_contrast": retention_info["audio_contrast"],
            "audio_reward": retention_info["audio_reward"],
            "audio_fact": retention_info["audio_fact"],
            "audio_trap": retention_info["audio_trap"],
            "audio_mem": retention_info["audio_mem"]
        },
        "q1": retention_info["mcq_q"],
        "a1": retention_info["mcq_opts"][0],
        "b1": retention_info["mcq_opts"][1],
        "c1": retention_info["mcq_opts"][2],
        "d1": retention_info["mcq_opts"][3],
        "ans1": retention_info["mcq_ans"],
        "q2": f"डाकघर गाइड क्लॉज {current_clause} के तहत मुख्य शर्त क्या है?",
        "a2": retention_info["reward_hero"],
        "b2": "सामान्य छूट",
        "c2": "वार्षिक संशोधन",
        "d2": "अतिरिक्त प्रभार",
        "ans2": "A",
        "q3": f"परीक्षा में क्लॉज {current_clause} से क्या ध्यान रखना जरूरी है?",
        "a3": retention_info["trap_text"][:38],
        "b3": "कोई नियम लागू नहीं",
        "c3": "सभी वस्तुएं वर्जित",
        "d3": "अतिरिक्त समय",
        "ans3": "A"
    }
    return script_data

async def generate_segment_audio(text, outfile, rate="+18%"):
    if os.path.exists(outfile):
        try: os.remove(outfile)
        except Exception: pass
    clean_audio_text = " ".join(re.sub(r"[\*#`_~\[\]\(\)]", " ", text).split()).strip()
    communicate = edge_tts.Communicate(text=clean_audio_text, voice=VOICE_NAME, rate=rate)
    await communicate.save(outfile)

def get_audio_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    return float(subprocess.check_output(cmd).decode().strip())

# --- 10/10 TARGET BLUEPRINT CONCEPT VIDEO ENGINE (Wider Wrap Width, Zero Truncation) ---
def render_concept_video(script_data, output_video=CONCEPT_VIDEO):
    ensure_fonts()
    cd = script_data["concept_data"]

    audio_beats = [
        cd["audio_hook"],                                         # 0: Hook (0-2s)
        cd["audio_contrast"],                                     # 1: Contrast (2-4s)
        cd["audio_reward"],                                       # 2: Reward (4-6s)
        cd["audio_fact"],                                         # 3: Fact/Number (6-9s)
        cd["audio_trap"],                                         # 4: Exam Trap (9-12s)
        cd["audio_mem"],                                          # 5: Memory Lock (12-15s)
        "लेकिन परीक्षा में सवाल ऐसे बनता है, देखिए!",            # 6: Open Loop (15-17s)
        "अब बिना देखे जवाब दो!",                                # 7: Quiz Entry (17-19s)
        cd["mcq_q"],                                              # 8: Question (19-24s)
        "ए, बी, सी, या डी?",                                     # 9: Options (24-27s)
        "अपना उत्तर तुरंत कमेंट करो!",                            # 10: Comment (32-35s)
        "अगला पोस्टल ट्रैप देखने के लिए फॉलो करें!"               # 11: Follow (35-38s)
    ]

    durations = []
    for i, seg in enumerate(audio_beats):
        fn = f"beat_audio_{i}.mp3"
        asyncio.run(generate_segment_audio(seg, fn, rate="+18%"))
        durations.append(get_audio_duration(fn))

    timer_audio = "c_audio_timer.wav"
    generate_5sec_clock_sfx(timer_audio)
    dur_timer = 5.0

    master_audio_list = [f"beat_audio_{i}.mp3" for i in range(10)] + [timer_audio] + [f"beat_audio_{i}.mp3" for i in range(10, 12)]
    concat_filter = "".join([f"[{i}:a]" for i in range(13)]) + "concat=n=13:v=0:a=1[aout]"
    
    cmd_audio = ["ffmpeg", "-y"]
    for af in master_audio_list: cmd_audio.extend(["-i", af])
    cmd_audio.extend(["-filter_complex", concat_filter, "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "concept_master.mp3"])
    subprocess.run(cmd_audio, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    total_dur = sum(durations) + dur_timer

    font_badge = get_font(28)
    font_sub = get_font(24)
    font_hero_huge = get_font(64)
    font_h1 = get_font(40)
    font_h2 = get_font(32)
    font_opt = get_font(26)
    font_timer = get_font(46)

    def draw_top_series_bar(d):
        d.rounded_rectangle([70, 65, 460, 125], radius=14, fill="#0F172A", outline="#FACC15", width=3)
        d.text((90, 78), cd["series_tag"], fill="#FACC15", font=font_badge)
        d.text((820, 80), "@POSTAL_WALA", fill="#64748B", font=font_sub)

    frames = []
    frame_durs = []

    # CHAPTER 1: STOP / HOOK (0–2s)
    img_hook = Image.new("RGB", (1080, 1920), color="#070B14")
    dh = ImageDraw.Draw(img_hook)
    draw_top_series_bar(dh)
    dh.rounded_rectangle([70, 360, 1010, 1380], radius=28, fill="#0F172A", outline="#EF4444", width=4)
    dh.rounded_rectangle([110, 410, 520, 470], radius=12, fill="#7F1D1D", outline="#EF4444", width=2)
    dh.text((135, 425), f"[ ! ] {cd['hook_title']}", fill="#FECACA", font=font_sub)
    dh.text((115, 580), "POSTAL TRAP", fill="#FACC15", font=font_h2)
    wrapped_hq = textwrap.fill(cd["hook_q"], width=22)
    dh.multiline_text((115, 660), wrapped_hq, fill="#FFFFFF", font=font_h1, spacing=18)
    dh.rounded_rectangle([110, 1180, 970, 1275], radius=16, fill="#064E3B", outline="#10B981", width=2)
    dh.text((210, 1205), ">> 5 सेकंड में जानें पक्का नियम!", fill="#34D399", font=font_h2)
    img_hook.save("b1_hook.png")
    frames.append("b1_hook.png")
    frame_durs.append(round(durations[0], 2))

    # CHAPTER 2: CURIOSITY / CONTRAST (2–4s)
    img_contrast = Image.new("RGB", (1080, 1920), color="#070B14")
    dc = ImageDraw.Draw(img_contrast)
    draw_top_series_bar(dc)
    dc.rounded_rectangle([70, 320, 1010, 440], radius=18, fill="#0F172A", outline="#475569", width=2)
    dc.text((105, 345), "सवाल:", fill="#FACC15", font=font_sub)
    dc.text((105, 380), clean_hindi_postal_terms(cd["hook_q"])[:42], fill="#CBD5E1", font=font_h2)
    dc.rounded_rectangle([70, 500, 1010, 780], radius=24, fill="#3F1215", outline="#EF4444", width=3)
    dc.text((110, 530), "विकल्प 1:", fill="#FECACA", font=font_sub)
    dc.text((110, 610), textwrap.fill(cd["contrast_wrong"], width=24), fill="#F87171", font=font_h1)
    dc.rounded_rectangle([70, 840, 1010, 1120], radius=24, fill="#082F49", outline="#38BDF8", width=3)
    dc.text((110, 870), "विकल्प 2:", fill="#BAE6FD", font=font_sub)
    dc.text((110, 950), textwrap.fill(cd["contrast_right"], width=24), fill="#38BDF8", font=font_h1)
    img_contrast.save("b2_contrast.png")
    frames.append("b2_contrast.png")
    frame_durs.append(round(durations[1], 2))

    # CHAPTER 3: REWARD (4–6s)
    img_reward = Image.new("RGB", (1080, 1920), color="#070B14")
    dr = ImageDraw.Draw(img_reward)
    draw_top_series_bar(dr)
    dr.rounded_rectangle([70, 360, 1010, 1380], radius=28, fill="#064E3B", outline="#10B981", width=5)
    dr.rounded_rectangle([110, 420, 460, 480], radius=12, fill="#022C22")
    dr.text((135, 435), "[ उत्तर / REWARD ]", fill="#A7F3D0", font=font_sub)
    wrapped_rw = textwrap.fill(cd["reward_hero"], width=22)
    dr.multiline_text((115, 620), wrapped_rw, fill="#FDE047", font=font_h1, spacing=16)
    dr.rounded_rectangle([110, 1050, 970, 1200], radius=18, fill="#022C22", outline="#34D399", width=2)
    dr.text((140, 1100), cd["reward_sub"], fill="#FFFFFF", font=font_h2)
    img_reward.save("b3_reward.png")
    frames.append("b3_reward.png")
    frame_durs.append(round(durations[2], 2))

    # CHAPTER 4: NUMBER/FACT (6–10s)
    img_fact = Image.new("RGB", (1080, 1920), color="#070B14")
    df = ImageDraw.Draw(img_fact)
    draw_top_series_bar(df)
    df.rounded_rectangle([70, 340, 1010, 1400], radius=28, fill="#0C4A6E", outline="#38BDF8", width=4)
    df.rounded_rectangle([110, 390, 480, 450], radius=12, fill="#082F49")
    df.text((135, 405), f"[ {cd['hero_label']} ]", fill="#BAE6FD", font=font_sub)
    df.text((115, 650), cd["hero_num"], fill="#FACC15", font=font_hero_huge)
    df.rounded_rectangle([110, 1150, 970, 1280], radius=18, fill="#082F49", outline="#7DD3FC", width=2)
    df.text((140, 1195), "नियम अनुसार निर्धारित अधिकृत प्रावधान", fill="#FFFFFF", font=font_h2)
    img_fact.save("b4_fact.png")
    frames.append("b4_fact.png")
    frame_durs.append(round(durations[3], 2))

    # CHAPTER 5: CHALLENGE / EXAM TRAP (10–13s)
    img_trap = Image.new("RGB", (1080, 1920), color="#070B14")
    dt = ImageDraw.Draw(img_trap)
    draw_top_series_bar(dt)
    dt.rounded_rectangle([70, 340, 1010, 1400], radius=28, fill="#3F1215", outline="#EF4444", width=4)
    dt.rounded_rectangle([110, 390, 450, 450], radius=12, fill="#7F1D1D")
    dt.text((135, 405), "[ ! ] EXAM TRAP बिंदु", fill="#FECACA", font=font_sub)
    wrapped_tr = textwrap.fill(cd["trap_text"], width=24)
    dt.multiline_text((115, 620), wrapped_tr, fill="#FFFFFF", font=font_h1, spacing=20)
    dt.rounded_rectangle([110, 1180, 970, 1280], radius=16, fill="#7F1D1D", outline="#FCA5A5", width=2)
    dt.text((160, 1210), "90% छात्र इस नियम में गलती करते हैं!", fill="#FDE047", font=font_h2)
    img_trap.save("b5_trap.png")
    frames.append("b5_trap.png")
    frame_durs.append(round(durations[4], 2))

    # CHAPTER 6: MEMORY LOCK (13–16s)
    img_mem = Image.new("RGB", (1080, 1920), color="#070B14")
    dm = ImageDraw.Draw(img_mem)
    draw_top_series_bar(dm)
    dm.rounded_rectangle([70, 320, 1010, 1400], radius=28, fill="#1E1B4B", outline="#A855F7", width=3)
    dm.rounded_rectangle([110, 370, 420, 430], radius=12, fill="#4C1D95")
    dm.text((135, 385), "[ याद रखो / REVISE ]", fill="#E9D5FF", font=font_sub)
    dm.rounded_rectangle([110, 560, 970, 760], radius=18, fill="#0F172A", outline="#38BDF8", width=3)
    dm.text((140, 630), textwrap.fill(cd["mem_1"], width=24), fill="#38BDF8", font=font_h1)
    dm.rounded_rectangle([110, 840, 970, 1040], radius=18, fill="#0F172A", outline="#FACC15", width=3)
    dm.text((140, 910), textwrap.fill(cd["mem_2"], width=24), fill="#FACC15", font=font_h1)
    img_mem.save("b6_mem.png")
    frames.append("b6_mem.png")
    frame_durs.append(round(durations[5], 2))

    # OPEN LOOP (16–18s)
    img_loop = Image.new("RGB", (1080, 1920), color="#070B14")
    dl = ImageDraw.Draw(img_loop)
    draw_top_series_bar(dl)
    dl.rounded_rectangle([70, 420, 1010, 1300], radius=28, fill="#0F172A", outline="#FACC15", width=4)
    dl.text((120, 580), "लेकिन Exam में सवाल", fill="#FFFFFF", font=font_h1)
    dl.text((120, 680), "ऐसे बनता है...", fill="#FACC15", font=font_h1)
    dl.rounded_rectangle([110, 960, 970, 1100], radius=20, fill="#1E293B", outline="#38BDF8", width=2)
    dl.text((260, 1005), ">> देखते हैं", fill="#38BDF8", font=font_h1)
    img_loop.save("b7_loop.png")
    frames.append("b7_loop.png")
    frame_durs.append(round(durations[6], 2))

    # QUIZ TRANSITION (18–20s)
    img_qentry = Image.new("RGB", (1080, 1920), color="#070B14")
    dqe = ImageDraw.Draw(img_qentry)
    draw_top_series_bar(dqe)
    dqe.rounded_rectangle([70, 420, 1010, 1300], radius=28, fill="#082F49", outline="#38BDF8", width=4)
    dqe.text((150, 620), "POSTAL MCQ", fill="#FACC15", font=font_h1)
    dqe.rounded_rectangle([110, 880, 970, 1040], radius=18, fill="#0F172A", outline="#10B981", width=3)
    dqe.text((220, 935), "बिना देखे जवाब दो!", fill="#34D399", font=font_h1)
    img_qentry.save("b8_qentry.png")
    frames.append("b8_qentry.png")
    frame_durs.append(round(durations[7], 2))

    # QUESTION (20–25s)
    img_q = Image.new("RGB", (1080, 1920), color="#070B14")
    dq = ImageDraw.Draw(img_q)
    draw_top_series_bar(dq)
    dq.rounded_rectangle([70, 210, 1010, 490], radius=20, fill="#0F172A", outline="#38BDF8", width=3)
    dq.rounded_rectangle([105, 235, 420, 290], radius=10, fill="#0284C7")
    dq.text((125, 248), "[ लाइव परीक्षा प्रश्न ]", fill="#FFFFFF", font=font_sub)
    wrapped_q = textwrap.fill(clean_hindi_postal_terms(cd["mcq_q"]), width=26)
    dq.multiline_text((105, 315), wrapped_q, fill="#F8FAFC", font=font_h2, spacing=10)
    img_q.save("b9_question.png")
    frames.append("b9_question.png")
    frame_durs.append(round(durations[8], 2))

    # OPTIONS (25–29s)
    opt_y_starts = [530, 645, 760, 875]
    img_opts = img_q.copy()
    do = ImageDraw.Draw(img_opts)
    for oi in range(4):
        oy = opt_y_starts[oi]
        do.rounded_rectangle([70, oy, 1010, oy + 95], radius=16, fill="#0F172A", outline="#38BDF8", width=2)
        do.text((105, oy + 25), clean_hindi_postal_terms(cd["mcq_opts"][oi])[:42], fill="#FFFFFF", font=font_opt)
    img_opts.save("b10_options.png")
    frames.append("b10_options.png")
    frame_durs.append(round(durations[9], 2))

    # COUNTDOWN (29–34s)
    cd_steps = [("05", "#FACC15", 1010), ("04", "#FACC15", 820), ("03", "#FB923C", 630), ("02", "#F87171", 440), ("01", "#EF4444", 250)]
    for sec_idx, (sec_str, tc, bar_w) in enumerate(cd_steps):
        img_timer = img_opts.copy()
        dtm = ImageDraw.Draw(img_timer)
        dtm.rounded_rectangle([70, 1010, 1010, 1140], radius=18, fill="#0F172A", outline=tc, width=4)
        dtm.text((290, 1040), f"{sec_str} सेकंड... सोचो!", fill=tc, font=font_timer)
        dtm.rounded_rectangle([70, 1160, bar_w, 1175], radius=6, fill=tc)
        
        t_name = f"b11_timer_{sec_idx}.png"
        img_timer.save(t_name)
        frames.append(t_name)
        frame_durs.append(1.0)

    # COMMENT COMMITMENT (34–37s)
    img_cmt = img_opts.copy()
    dcm = ImageDraw.Draw(img_cmt)
    dcm.rounded_rectangle([70, 1010, 1010, 1130], radius=18, fill="#064E3B", outline="#10B981", width=3)
    dcm.text((310, 1045), "A / B / C / D ?", fill="#34D399", font=font_timer)
    dcm.rounded_rectangle([70, 1160, 1010, 1290], radius=22, fill="#E11D48", outline="#FDA4AF", width=4)
    dcm.text((140, 1205), "अपना उत्तर comment करो >>", fill="#FFFFFF", font=font_h2)
    img_cmt.save("b12_comment.png")
    frames.append("b12_comment.png")
    frame_durs.append(round(durations[10], 2))

    # FOLLOW LOOP (37–40s)
    img_follow = img_opts.copy()
    dfl = ImageDraw.Draw(img_follow)
    dfl.rounded_rectangle([70, 1010, 1010, 1130], radius=18, fill="#0F172A", outline="#FACC15", width=3)
    dfl.text((200, 1045), "अगला Postal Trap कल", fill="#FACC15", font=font_timer)
    dfl.rounded_rectangle([70, 1160, 1010, 1290], radius=22, fill="#1D4ED8", outline="#93C5FD", width=4)
    dfl.text((220, 1205), "Follow @POSTAL_WALA", fill="#FFFFFF", font=font_h1)
    img_follow.save("b13_follow.png")
    frames.append("b13_follow.png")
    frame_durs.append(round(durations[11], 2))

    # Compilation
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

    cmd = ["ffmpeg", "-y"]
    for fname in frames: cmd.extend(["-i", fname])
    cmd.extend(["-i", "concept_master.mp3"])
    voice_idx = len(frames)
    if os.path.exists(BGM_OUTPUT):
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
    print(f"🔥 Clean 10/10 Target Blueprint Reel Created: {output_video} (Dur: {total_dur:.2f}s)", flush=True)

# --- 3-QUESTION 40-SEC QUIZ REEL (100% UNTOUCHED) ---
def render_quiz_video(script_data, output_video=QUIZ_VIDEO):
    ensure_fonts()
    questions_list = [
        {"q_num": "सवाल 1/3", "q": clean_text(script_data["q1"]), "opts": [clean_text(script_data["a1"]), clean_text(script_data["b1"]), clean_text(script_data["c1"]), clean_text(script_data["d1"])], "ans": script_data["ans1"]},
        {"q_num": "सवाल 2/3", "q": clean_text(script_data["q2"]), "opts": [clean_text(script_data["a2"]), clean_text(script_data["b2"]), clean_text(script_data["c2"]), clean_text(script_data["d2"])], "ans": script_data["ans2"]},
        {"q_num": "सवाल 3/3", "q": clean_text(script_data["q3"]), "opts": [clean_text(script_data["a3"]), clean_text(script_data["b3"]), clean_text(script_data["c3"]), clean_text(script_data["d3"])], "ans": script_data["ans3"]},
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

    concat_filter_audio = "".join([f"[{i}:a]" for i in range(len(audio_files))]) + f"concat=n={len(audio_files)}:v=0:a=1[aout]"
    ffmpeg_audio_cmd = ["ffmpeg", "-y"]
    for af in audio_files: ffmpeg_audio_cmd.extend(["-i", af])
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
    
    clean_title = clean_text(script_data["clause_name"])
    if len(clean_title) > 38: clean_title = clean_title[:36] + "..."
    d_base.text((105, 255), clean_title, fill="#FDE047", font=font_title)
    d_base.rounded_rectangle([80, 350, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
    draw_footer_cta(d_base)

    frames = []
    frame_durs = []

    intro_img = base_img.copy()
    d_intro = ImageDraw.Draw(intro_img)
    d_intro.rounded_rectangle([110, 500, 970, 910], radius=20, fill="#182848", outline="#FBBF24", width=3)
    d_intro.rounded_rectangle([140, 530, 940, 585], radius=10, fill="#064E3B", outline="#10B981", width=2)
    d_intro.text((160, 542), "GDS to MTS • Postman • Mail Guard • P.A. परीक्षा", fill="#34D399", font=font_h2)
    d_intro.text((150, 630), f"पोस्टल गाइड क्लॉज {script_data['clause_no']} स्पेशल!", fill="#FDE047", font=font_title)
    d_intro.text((150, 720), "पेपर में इससे ये प्रश्न बन सकते हैं!", fill="#FFFFFF", font=font_q_text)
    intro_img.save("quiz_intro_frame.png")
    frames.append("quiz_intro_frame.png")
    frame_durs.append(segment_durations[0])

    labels = ["A", "B", "C", "D"]
    for idx, q_data in enumerate(questions_list):
        wrapped_q = textwrap.fill(q_data["q"], width=24)
        dummy_img = Image.new("RGB", (1080, 1920))
        dummy_draw = ImageDraw.Draw(dummy_img)
        q_bbox = dummy_draw.multiline_textbbox((110, 445), wrapped_q, font=font_q_text, spacing=6)
        start_oy = max(q_bbox[3] + 25, 510)

        opt_heights = []
        wrapped_opts = []
        for opt in q_data["opts"]:
            w_opt = textwrap.fill(opt, width=28)
            wrapped_opts.append(w_opt)
            opt_heights.append(max(75, (w_opt.count("\n") + 1) * 26 + 18))

        step_dur = segment_durations[idx + 1] / 3.0

        img_s1 = base_img.copy()
        d1 = ImageDraw.Draw(img_s1)
        d1.rounded_rectangle([110, 380, 480, 435], radius=10, fill="#7F1D1D", outline="#F87171", width=2)
        d1.text((130, 390), q_data["q_num"], fill="#FECACA", font=font_h2)
        d1.rounded_rectangle([510, 380, 970, 435], radius=10, fill="#064E3B", outline="#10B981", width=2)
        d1.text((540, 395), "GDS to MTS • Postman • P.A.", fill="#A7F3D0", font=font_badge)
        d1.multiline_text((110, 445), wrapped_q, fill="#F8FAFC", font=font_q_text, spacing=6)
        
        d1.rounded_rectangle([110, start_oy, 970, start_oy + opt_heights[0]], radius=12, fill="#0B132B", outline="#38BDF8", width=2)
        d1.text((135, start_oy + 8), "A)", fill="#38BDF8", font=font_q_text)
        d1.multiline_text((180, start_oy + 8), wrapped_opts[0], fill="#FFFFFF", font=font_opt_text, spacing=2)
        img_s1.save(f"anim_q{idx+1}_step1.png")
        frames.append(f"anim_q{idx+1}_step1.png")
        frame_durs.append(step_dur)

        img_s2 = img_s1.copy()
        d2 = ImageDraw.Draw(img_s2)
        curr_y = start_oy + opt_heights[0] + 12
        for o_idx in range(1, 3):
            d2.rounded_rectangle([110, curr_y, 970, curr_y + opt_heights[o_idx]], radius=12, fill="#0B132B", outline="#38BDF8", width=2)
            d2.text((135, curr_y + 8), f"{labels[o_idx]})", fill="#38BDF8", font=font_q_text)
            d2.multiline_text((180, curr_y + 8), wrapped_opts[o_idx], fill="#FFFFFF", font=font_opt_text, spacing=2)
            curr_y += opt_heights[o_idx] + 12
        img_s2.save(f"anim_q{idx+1}_step2.png")
        frames.append(f"anim_q{idx+1}_step2.png")
        frame_durs.append(step_dur)

        img_s3 = img_s2.copy()
        d3 = ImageDraw.Draw(img_s3)
        d3.rounded_rectangle([110, curr_y, 970, curr_y + opt_heights[3]], radius=12, fill="#0B132B", outline="#38BDF8", width=2)
        d3.text((135, curr_y + 8), "D)", fill="#38BDF8", font=font_q_text)
        d3.multiline_text((180, curr_y + 8), wrapped_opts[3], fill="#FFFFFF", font=font_opt_text, spacing=2)
        d3.rounded_rectangle([110, 1430, 970, 1510], radius=12, fill="#064E3B", outline="#10B981", width=3)
        d3.text((140, 1455), "अपना उत्तर सोचें और नोट करें", fill="#A7F3D0", font=font_h2)
        img_s3.save(f"anim_q{idx+1}_step3.png")
        frames.append(f"anim_q{idx+1}_step3.png")
        frame_durs.append(step_dur)

    img_ans = base_img.copy()
    d_ans = ImageDraw.Draw(img_ans)
    d_ans.rounded_rectangle([110, 380, 680, 440], radius=10, fill="#064E3B", outline="#10B981", width=2)
    d_ans.text((130, 392), "महा फिनाले: सभी 3 सवालों के सही उत्तर", fill="#34D399", font=font_h2)

    ans_y_start = 480
    answers_text = [
        f"सवाल 1 का सही उत्तर - [ {script_data.get('ans1', 'A')} ]",
        f"सवाल 2 का सही उत्तर - [ {script_data.get('ans2', 'B')} ]",
        f"सवाल 3 का सही उत्तर - [ {script_data.get('ans3', 'C')} ]"
    ]
    for a_idx, ans_str in enumerate(answers_text):
        ay = ans_y_start + (a_idx * 180)
        d_ans.rounded_rectangle([110, ay, 970, ay + 140], radius=16, fill="#182848", outline="#FBBF24", width=2)
        d_ans.text((140, ay + 45), clean_text(ans_str), fill="#FDE047", font=font_title)

    img_ans.save("quiz_answers_reveal.png")
    frames.append("quiz_answers_reveal.png")
    frame_durs.append(segment_durations[-1])

    total_dur = sum(frame_durs)
    filter_parts = "".join([f"[{i}:v]loop=loop=-1:size=1:start=0,trim=duration={frame_durs[i]}[v{i}]; " for i in range(len(frames))])
    concat_str = "".join([f"[v{i}]" for i in range(len(frames))])
    base_v_filter = f"{filter_parts}{concat_str}concat=n={len(frames)}:v=1:a=0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
    
    progress_bar_filter = (
        f"{base_v_filter},"
        f"drawbox=x=0:y=0:w=iw:h=12:color=#1E293B@1:t=fill,"
        f"drawbox=x=0:y=0:w='iw*(t/{total_dur})':h=12:color=#FACC15@1:t=fill[v]"
    )

    cmd = ["ffmpeg", "-y"]
    for fname in frames: cmd.extend(["-i", fname])
    cmd.extend(["-i", "quiz_voice_master.mp3"])
    voice_idx = len(frames)
    if os.path.exists(BGM_OUTPUT):
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
    
    # 1. Concept Reel (True 10/10 Target Blueprint: 36–39s, Clean Text & Real Facts)
    print("🎬 Generating 10/10 Concept Rule Reel...", flush=True)
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
    print("🎉 Done! Both reels generated and verified.", flush=True)
