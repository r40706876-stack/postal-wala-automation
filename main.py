import os
import re
import json
import math
import random
import asyncio
import subprocess
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import edge_tts


# -------------------- CONFIG --------------------

OUTPUT_DIR = "generated_reels"
OUTPUT_VIDEO = "final_reel.mp4"
STATE_FILE = "progress_state.json"

VOICE_NAME = "hi-IN-SwaraNeural"
VOICE_RATE = "+8%"

W, H = 1080, 1920
FPS = 30

FONT_FILE = "Mukta-Bold.ttf"
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/mukta/Mukta-Bold.ttf"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Palette
BG = "#07111F"
CARD = "#0E1B2D"
CARD_2 = "#13263D"
WHITE = "#F8FAFC"
MUTED = "#9FB0C2"
RED = "#EF4444"
GREEN = "#22C55E"
YELLOW = "#F59E0B"
BLUE = "#2563EB"
CYAN = "#38BDF8"
PURPLE = "#8B5CF6"


# -------------------- VERIFIED CATALOG --------------------

POSTAL_CLAUSE_CATALOG = {
    1: {
        "name": "डाक विभाग का नियंत्रण व संगठन",
        "total_parts": 2,
        "part_1_focus": "संचार मंत्रालय के अधीन महानिदेशक (DG Posts) शीर्ष प्रशासनिक प्रमुख हैं और मुख्यालय डाक भवन नई दिल्ली में स्थित है।",
        "part_2_focus": "डाक सेवा बोर्ड में एक चेयरमैन और 6 पूर्णकालिक सदस्य होते हैं।",
    },
    2: {
        "name": "डाकघरों के प्रकार और श्रेणियां",
        "total_parts": 3,
        "part_1_focus": "डाकघर की 3 प्रमुख श्रेणियां हैं: प्रधान डाकघर, उप डाकघर और शाखा डाकघर।",
        "part_2_focus": "उप डाकघर प्रधान डाकघर के अधीन रहकर लेन-देन करता है और दैनिक लेखा HO को भेजता है।",
        "part_3_focus": "ग्रामीण शाखा डाकघर के कार्य के घंटे न्यूनतम 4 घंटे और अधिकतम 5 घंटे प्रतिदिन निर्धारित किए जाते हैं।",
    },
    3: {
        "name": "रात्रि डाकघर के नियम",
        "total_parts": 3,
        "part_1_focus": "रात्रि डाकघर की स्थापना और कामकाज के घंटे रात 8:30 बजे तक बढ़ाने का विशेष अधिकार महानिदेशक (DG) को है।",
        "part_2_focus": "रविवार और राष्ट्रीय डाक अवकाशों पर रात्रि डाकघर सुबह 10 से शाम 5 बजे तक केवल सीमित सेवाएं देते हैं।",
        "part_3_focus": "रात्रि डाकघरों में रविवार और अवकाश के दिनों में मनीऑर्डर भुगतान या बचत बैंक निकासी कार्य नहीं होता।",
    },
    4: {
        "name": "मोबाइल डाकघर की व्यवस्था",
        "total_parts": 2,
        "part_1_focus": "मोबाइल डाकघर बड़े शहरों में देर शाम तक सामान्य डाक और पार्सल बुकिंग की सुविधा देते हैं।",
        "part_2_focus": "मोबाइल डाकघर में मनीऑर्डर, बचत बैंक और बीमा के वित्तीय कार्य प्रतिबंधित होते हैं।",
    },
    5: {
        "name": "डाकघर के कामकाज के घंटे",
        "total_parts": 3,
        "part_1_focus": "सामान्य डाक टिकट बिक्री और डाक बुकिंग पूरे कार्य समय तक होती है, जबकि बचत बैंक का समय पहले समाप्त होता है।",
        "part_2_focus": "सार्वजनिक काउंटर बंद होने के बाद निर्धारित लेट फीस का भुगतान करके ही डाक बुक की जा सकती है।",
        "part_3_focus": "शनिवार को सामान्य डाक लेन-देन के समय में विभागीय कटौती के नियम और समय-सारिणी लागू होती है।",
    },
    22: {
        "name": "डाक का पुनः निर्देशन",
        "total_parts": 3,
        "part_1_focus": "पतेदार के नया पता छोड़कर जाने पर प्रथम श्रेणी की अंतरदेशीय डाक का पुनः प्रेषण निःशुल्क होता है।",
        "part_2_focus": "पार्सल को वितरण क्षेत्र से बाहर पुनः प्रेषित करने पर आधा डाक प्रभार देय होता है।",
        "part_3_focus": "यदि पार्सल पतेदार द्वारा एक बार खोल दिया गया हो तो नए डाकभार के बिना पुनः निर्देशित नहीं किया जा सकता।",
    },
    23: {
        "name": "डाक पुनः प्रेषण के विशेष निर्देश",
        "total_parts": 2,
        "part_1_focus": "लिखित पुनः प्रेषण अनुदेश की वैधता अवधि अधिकतम 3 माह तक प्रभावी रहती है।",
        "part_2_focus": "विदेश जाने वाले पतेदारों और अस्थाई रूप से स्थान बदलने वाले व्यक्तियों के लिए विशेष डाक नियम लागू होते हैं।",
    },
}


# -------------------- CURATED FALLBACK BANK --------------------

FALLBACK_SCRIPTS = {
    (1, 1): {
        "hook": "डाक विभाग का सर्वोच्च प्रशासनिक प्रमुख कौन होता है?",
        "question": "डाक विभाग का शीर्ष प्रशासनिक प्रमुख कौन होता है?",
        "a": "महानिदेशक (DG Posts)",
        "b": "डाक सचिव",
        "c": "पोस्टमास्टर जनरल",
        "d": "अधीक्षक डाकघर",
        "correct": "A",
        "fact": "संचार मंत्रालय के अधीन महानिदेशक (DG Posts) शीर्ष प्रशासनिक प्रमुख हैं।",
        "trap": "पोस्टमास्टर जनरल केवल सर्किल स्तर के प्रमुख होते हैं, विभाग के नहीं।",
        "trick": "ट्रिक: बॉस हमेशा महानिदेशक होता है।"
    },
    (1, 2): {
        "hook": "डाक सेवा बोर्ड में कितने पूर्णकालिक सदस्य होते हैं?",
        "question": "डाक सेवा बोर्ड में कुल कितने पूर्णकालिक सदस्य होते हैं?",
        "a": "6 सदस्य",
        "b": "4 सदस्य",
        "c": "5 सदस्य",
        "d": "8 सदस्य",
        "correct": "A",
        "fact": "डाक सेवा बोर्ड में एक चेयरमैन और 6 पूर्णकालिक सदस्य होते हैं।",
        "trap": "चेयरमैन को मिलाकर कुल 7 होते हैं, पूर्णकालिक सदस्य 6 ही हैं।",
        "trick": "ट्रिक: 1 चेयरमैन + 6 सदस्य = कुल 7।"
    },
    (2, 1): {
        "hook": "डाकघर को मुख्य रूप से कितनी श्रेणियों में बांटा गया है?",
        "question": "डाकघर की कितनी प्रमुख श्रेणियां निर्धारित हैं?",
        "a": "3 श्रेणियां",
        "b": "2 श्रेणियां",
        "c": "4 श्रेणियां",
        "d": "5 श्रेणियां",
        "correct": "A",
        "fact": "डाकघर की 3 श्रेणियां हैं: प्रधान डाकघर, उप डाकघर और शाखा डाकघर।",
        "trap": "मोबाइल डाकघर अलग श्रेणी नहीं बल्कि एक विशेष सेवा व्यवस्था है।",
        "trick": "ट्रिक: HO, SO, BO यानी 3 श्रेणियां।"
    },
    (2, 2): {
        "hook": "उप डाकघर अपना दैनिक हिसाब किसे भेजता है?",
        "question": "उप डाकघर (SO) अपना दैनिक लेखा किसे प्रेषित करता है?",
        "a": "प्रधान डाकघर (HO)",
        "b": "मंडल कार्यालय",
        "c": "सर्किल कार्यालय",
        "d": "मुख्यालय",
        "correct": "A",
        "fact": "उप डाकघर दैनिक लेखा अपने प्रधान डाकघर (HO) को भेजता है।",
        "trap": "SO सीधे मंडल अधीक्षक को दैनिक लेखा नहीं भेजता।",
        "trick": "ट्रिक: SO का बॉस HO होता है।"
    },
    (2, 3): {
        "hook": "शाखा डाकघर के अधिकतम कार्य के घंटे कितने हैं?",
        "question": "ग्रामीण शाखा डाकघर (BO) के अधिकतम कार्य घंटे कितने हैं?",
        "a": "5 घंटे",
        "b": "4 घंटे",
        "c": "6 घंटे",
        "d": "8 घंटे",
        "correct": "A",
        "fact": "शाखा डाकघर के कार्य घंटे न्यूनतम 4 और अधिकतम 5 घंटे होते हैं।",
        "trap": "न्यूनतम 4 घंटे और अधिकतम 5 घंटे में भ्रमित न हों।",
        "trick": "ट्रिक: गाँव में 4-5 घंटे काम होता है।"
    },
    (3, 1): {
        "hook": "रात्रि डाकघर का समय 8:30 बजे तक कौन बढ़ा सकता है?",
        "question": "रात्रि डाकघर के घंटे 8:30 बजे तक बढ़ाने का अधिकार किसे है?",
        "a": "महानिदेशक (DG)",
        "b": "Postmaster",
        "c": "SSPO",
        "d": "CPMG",
        "correct": "A",
        "fact": "रात्रि डाकघर के घंटे 8:30 बजे तक बढ़ाने का विशेष अधिकार DG को है।",
        "trap": "यह अधिकार स्थानीय पोस्टमास्टर या SSPO के पास नहीं होता।",
        "trick": "ट्रिक: समय बढ़ाने का अधिकार केवल DG को।"
    },
    (3, 2): {
        "hook": "रविवार को रात्रि डाकघर कितने बजे तक सेवा देता है?",
        "question": "रविवार और राष्ट्रीय अवकाश पर रात्रि डाकघर का समय क्या है?",
        "a": "सुबह 10 से शाम 5",
        "b": "सुबह 8 से दोपहर 2",
        "c": "दोपहर 12 से शाम 8",
        "d": "पूरे दिन",
        "correct": "A",
        "fact": "रविवार और अवकाश के दिन सीमित सेवाएं सुबह 10 से शाम 5 बजे तक मिलती हैं।",
        "trap": "रविवार को रात 8:30 बजे वाला नियम लागू नहीं होता।",
        "trick": "ट्रिक: छुट्टी के दिन 10 से 5 बजे तक।"
    },
    (3, 3): {
        "hook": "रविवार को रात्रि डाकघर में कौन-सा काम नहीं होता?",
        "question": "रविवार और अवकाश के दिन रात्रि डाकघर में क्या नहीं होता?",
        "a": "मनीऑर्डर व बचत बैंक",
        "b": "डाक टिकट बिक्री",
        "c": "स्पीड पोस्ट बुकिंग",
        "d": "पंजीकृत डाक",
        "correct": "A",
        "fact": "रविवार और अवकाश के दिन मनीऑर्डर भुगतान और बचत बैंक कार्य नहीं होता।",
        "trap": "सीमित बुकिंग चालू रहती है, लेकिन वित्तीय निकासी बंद होती है।",
        "trick": "ट्रिक: छुट्टी के दिन पैसे का कोई लेन-देन नहीं।"
    },
    (4, 1): {
        "hook": "मोबाइल डाकघर मुख्य रूप से कौन-सी सुविधा देते हैं?",
        "question": "मोबाइल डाकघर में मुख्य रूप से कौन-सा कार्य होता है?",
        "a": "डाक व पार्सल बुकिंग",
        "b": "मनीऑर्डर भुगतान",
        "c": "बचत बैंक खाता",
        "d": "डाक जीवन बीमा",
        "correct": "A",
        "fact": "मोबाइल डाकघर शाम तक सामान्य डाक और पार्सल बुकिंग की सुविधा देते हैं।",
        "trap": "मोबाइल वैन में बैंकिंग और वित्तीय सुविधाएं उपलब्ध नहीं होती हैं।",
        "trick": "ट्रिक: वैन में सिर्फ पार्सल और डाक।"
    },
    (4, 2): {
        "hook": "मोबाइल डाकघर में कौन-सा कार्य पूरी तरह प्रतिबंधित है?",
        "question": "मोबाइल डाकघर में किस कार्य की अनुमति नहीं होती है?",
        "a": "मनीऑर्डर व बचत बैंक",
        "b": "साधारण डाक बुकिंग",
        "c": "पार्सल बुकिंग",
        "d": "लेट फीस डाक",
        "correct": "A",
        "fact": "मोबाइल डाकघर में मनीऑर्डर, बचत बैंक और बीमा कार्य प्रतिबंधित होते हैं।",
        "trap": "केवल डाक और पार्सल बुकिंग की ही अनुमति होती है।",
        "trick": "ट्रिक: मोबाइल वैन में नो मनी, नो बैंक।"
    },
    (5, 1): {
        "hook": "डाकघर में डाक टिकटों की बिक्री कब तक होती है?",
        "question": "डाक टिकटों की बिक्री काउंटर पर कब तक उपलब्ध रहती है?",
        "a": "पूरे कार्य समय तक",
        "b": "केवल 2 घंटे",
        "c": "दोपहर 12 बजे तक",
        "d": "शाम 4 बजे तक",
        "correct": "A",
        "fact": "सामान्य टिकट बिक्री और डाक बुकिंग पूरे कार्य समय तक खुली रहती है।",
        "trap": "बचत बैंक काउंटर जल्दी बंद होता है, लेकिन टिकट पूरे समय मिलते हैं।",
        "trick": "ट्रिक: टिकट पूरे दिन मिलते हैं।"
    },
    (5, 2): {
        "hook": "काउंटर बंद होने के बाद डाक कैसे बुक कराई जा सकती है?",
        "question": "सार्वजनिक काउंटर बंद होने के बाद डाक कैसे स्वीकार की जाती है?",
        "a": "लेट फीस भुगतान करके",
        "b": "लिखित आवेदन से",
        "c": "दोगुने टिकट लगाकर",
        "d": "अगले कार्यदिवस पर",
        "correct": "A",
        "fact": "सार्वजनिक काउंटर बंद होने के बाद निर्धारित लेट फीस देकर डाक बुक होती है।",
        "trap": "बिना लेट फीस के काउंटर समय के बाद डाक स्वीकार नहीं होती।",
        "trick": "ट्रिक: लेट फीस दो, काम करवाओ।"
    },
    (5, 3): {
        "hook": "शनिवार को डाकघर के कामकाज का क्या नियम है?",
        "question": "शनिवार को सामान्य डाक लेन-देन के समय में क्या लागू होता है?",
        "a": "विभागीय समयावधि कटौती",
        "b": "सामान्य दिनों जैसा समय",
        "c": "पूर्ण अवकाश",
        "d": "रविवार के नियम",
        "correct": "A",
        "fact": "शनिवार को सामान्य डाक लेन-देन के समय में निर्धारित कटौती लागू होती है।",
        "trap": "शनिवार को सामान्य कार्यदिवसों जितना पूरा समय नहीं मिलता।",
        "trick": "ट्रिक: शनिवार हाफ-डे, समय में कटौती।"
    },
    (22, 1): {
        "hook": "क्या प्रथम श्रेणी डाक का पुनः प्रेषण पूरी तरह मुफ्त है?",
        "question": "प्रथम श्रेणी की अंतरदेशीय डाक का पुनः प्रेषण शुल्क कितना है?",
        "a": "पूर्णतः निःशुल्क",
        "b": "आधा डाक प्रभार",
        "c": "पूरा डाक प्रभार",
        "d": "दस रुपये",
        "correct": "A",
        "fact": "प्रथम श्रेणी की अंतरदेशीय डाक का पुनः प्रेषण पूरी तरह निःशुल्क होता है।",
        "trap": "पार्सल पर प्रभार लगता है, लेकिन प्रथम श्रेणी डाक निःशुल्क होती है।",
        "trick": "ट्रिक: प्रथम श्रेणी की डाक बिलकुल फ्री में फॉरवर्ड।"
    },
    (22, 2): {
        "hook": "पार्सल दूसरे वितरण क्षेत्र में भेजने पर कितना प्रभार लगता है?",
        "question": "वितरण क्षेत्र से बाहर पार्सल पुनः प्रेषित करने पर कितना प्रभार है?",
        "a": "आधा डाक प्रभार",
        "b": "पूर्ण डाक प्रभार",
        "c": "निःशुल्क",
        "d": "दोगुना प्रभार",
        "correct": "A",
        "fact": "वितरण क्षेत्र से बाहर भेजे जाने पर आधा डाक प्रभार देय होता है।",
        "trap": "उसी वितरण क्षेत्र में निःशुल्क होता है, बाहर भेजने पर आधा प्रभार लगता है।",
        "trick": "ट्रिक: क्षेत्र बदला, आधा चार्ज लगा।"
    },
    (22, 3): {
        "hook": "खोला गया पार्सल दोबारा कैसे भेजा जा सकता है?",
        "question": "एक बार खुले हुए पार्सल को पुनः प्रेषित करने की क्या शर्त है?",
        "a": "नया डाकभार देना होगा",
        "b": "आधा डाकभार लगेगा",
        "c": "निःशुल्क भेजा जाएगा",
        "d": "विशेष छूट मिलेगी",
        "correct": "A",
        "fact": "खोला गया पार्सल नए डाकभार के बिना पुनः प्रेषित नहीं किया जा सकता।",
        "trap": "बिना खुले पार्सल पर आधा प्रभार, लेकिन खुले पर पूरा नया चार्ज लगता है।",
        "trick": "ट्रिक: पार्सल खुला, नया चार्ज लगेगा।"
    },
    (23, 1): {
        "hook": "डाक पुनः प्रेषण के लिखित निर्देश कितने समय मान्य रहते हैं?",
        "question": "लिखित पुनः प्रेषण अनुदेश (Redirection) की वैधता अवधि क्या है?",
        "a": "अधिकतम 3 माह",
        "b": "6 माह",
        "c": "1 वर्ष",
        "d": "1 माह",
        "correct": "A",
        "fact": "लिखित पुनः प्रेषण अनुदेश की वैधता अवधि अधिकतम 3 माह तक होती है।",
        "trap": "3 महीने पूरे होने के बाद नया लिखित निर्देश देना आवश्यक होता है।",
        "trick": "ट्रिक: redirection सिर्फ 3 महीने के लिए।"
    },
    (23, 2): {
        "hook": "विदेश जाने वाले पतेदारों की डाक के क्या नियम हैं?",
        "question": "विदेश जाने वाले पतेदारों के डाक पुनः प्रेषण पर क्या लागू होता है?",
        "a": "विशेष डाक नियम",
        "b": "सामान्य घरेलू नियम",
        "c": "कोई नियम नहीं",
        "d": "निःशुल्क विदेशी डाक",
        "correct": "A",
        "fact": "विदेश जाने वाले पतेदारों के लिए विशेष डाक नियम लागू होते हैं।",
        "trap": "अंतर्देशीय साधारण नियम विदेश जाने वाली डाक पर सीधे लागू नहीं होते।",
        "trick": "ट्रिक: विदेश जाने पर विशेष नियम।"
    },
}

# -------------------- EASING & ANIMATION HELPERS --------------------

def ease_out_back(x):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * math.pow(x - 1, 3) + c1 * math.pow(x - 1, 2) if x < 1 else 1

def pulse(t, speed=5, amount=0.03):
    return 1.0 + math.sin(t * speed) * amount

# -------------------- FONT & SHAPING HELPERS --------------------

def ensure_fonts():
    if not os.path.exists(FONT_FILE) or os.path.getsize(FONT_FILE) < 50000:
        response = requests.get(FONT_URL, timeout=30)
        response.raise_for_status()
        Path(FONT_FILE).write_bytes(response.content)


def get_font(size):
    ensure_fonts()
    try:
        return ImageFont.truetype(FONT_FILE, size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        return ImageFont.truetype(FONT_FILE, size)


def wrap_text(draw, text, size, max_width):
    words = text.split()
    if not words:
        return ""

    font = get_font(size)
    lines = []
    current = ""

    for word in words:
        candidate = word if not current else current + " " + word
        bbox = draw.textbbox((0, 0), candidate, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return "\n".join(lines)


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"[*_`#]+", "", text)
    text = text.replace("…", ".")
    return " ".join(text.split()).strip()


# -------------------- DRAWING HELPERS --------------------

_bg_cache = None
def new_canvas():
    global _bg_cache
    if _bg_cache: return _bg_cache.copy()
    
    im = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(im)
    
    # 1. Background gradient & Grain[span_6](start_span)[span_6](end_span)[span_7](start_span)[span_7](end_span)
    for y in range(H):
        ratio = y / H
        r = int(15 * (1 - ratio) + 4)
        g = int(32 * (1 - ratio) + 10)
        b = int(60 * (1 - ratio) + 20)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
        
    # 2. Vignette[span_8](start_span)[span_8](end_span)[span_9](start_span)[span_9](end_span)
    vig = Image.new("RGBA", (W, H), (0,0,0,0))
    vig_d = ImageDraw.Draw(vig)
    vig_d.ellipse((-300, -200, W+300, H+200), outline=(0,0,0,150), width=200)
    vig = vig.filter(ImageFilter.GaussianBlur(80))
    im.paste(vig, (0,0), vig)
    
    _bg_cache = im
    return im.copy()


def draw_shadow(im, box, radius, fill=(0,0,0, 100)):
    shadow = Image.new("RGBA", (W, H), (0,0,0,0))
    d = ImageDraw.Draw(shadow)
    d.rounded_rectangle((box[0]+15, box[1]+15, box[2]+15, box[3]+15), radius, fill=fill)
    shadow = shadow.filter(ImageFilter.GaussianBlur(20))
    im.paste(shadow, (0,0), shadow)


def draw_badge(draw, text, cx, cy, size, bg_color, text_color):
    font = get_font(size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.rounded_rectangle((cx - tw/2 - 25, cy - th/2 - 15, cx + tw/2 + 25, cy + th/2 + 15), radius=15, fill=bg_color)
    draw.text((cx, cy - 5), text, font=font, fill=text_color, anchor="mm")


def rounded(draw, box, radius=35, fill=CARD, outline=None, width=2):
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width,
    )


def center_text(draw, text, y, size, fill=WHITE, scale=1.0):
    font = get_font(int(size * scale))
    draw.text((W / 2, y), text, font=font, fill=fill, anchor="mm")


def brand(draw):
    font = get_font(27)
    draw.text((55, 45), "POSTAL WALA", font=font, fill="#64748B", anchor="la")


def progress_bar(draw, ratio):
    left = 55
    right = W - 55
    y = 92

    draw.rounded_rectangle(
        (left, y, right, y + 8),
        radius=4,
        fill="#1B2A3A",
    )

    current = left + (right - left) * max(0.0, min(1.0, ratio))
    draw.rounded_rectangle(
        (left, y, current, y + 8),
        radius=4,
        fill=CYAN,
    )


def draw_x(draw, cx, cy, size=45, scale=1.0):
    s = int(size * scale)
    draw.line((cx - s, cy - s, cx + s, cy + s), fill=RED, width=int(14*scale))
    draw.line((cx + s, cy - s, cx - s, cy + s), fill=RED, width=int(14*scale))


def draw_check(draw, cx, cy, size=45, scale=1.0):
    s = int(size * scale)
    draw.line((cx - s, cy, cx - s // 3, cy + s), fill=GREEN, width=int(14*scale))
    draw.line((cx - s // 3, cy + s, cx + s, cy - s), fill=GREEN, width=int(14*scale))


def draw_authority_card(im, draw, label, x1, y1, x2, y2, status=None, x_offset=0):
    x1, x2 = x1 + x_offset, x2 + x_offset
    outline = (
        GREEN if status == "correct"
        else RED if status == "wrong"
        else "#2A4058"
    )

    draw_shadow(im, (x1, y1, x2, y2), 26)
    rounded(draw, (x1, y1, x2, y2), 26, CARD_2, outline, 4)
    max_w = (x2 - x1) - 60
    wrapped = wrap_text(draw, label, 38, max_w)
    lines = wrapped.split("\n")

    cx = (x1 + x2) // 2
    if status:
        text_y = y1 + 52 if len(lines) == 1 else y1 + 40
        for line in lines:
            center_text(draw, line, text_y, 36, WHITE)
            text_y += 46
        if status == "wrong":
            draw_x(draw, cx, y1 + 138, 32)
        elif status == "correct":
            draw_check(draw, cx, y1 + 138, 32)
    else:
        text_y = (y1 + y2) // 2 - (len(lines) - 1) * 23
        for line in lines:
            center_text(draw, line, text_y, 38, WHITE)
            text_y += 48


# Word-by-word text drawing logic[span_10](start_span)[span_10](end_span)[span_11](start_span)[span_11](end_span)
def draw_word_by_word(draw, text, y_start, font_size, max_w, t, words_per_sec=3.5):
    font = get_font(font_size)
    words = text.split()
    revealed_count = int(t * words_per_sec)
    
    y = y_start
    lines = []
    current_line = []
    
    for w in words:
        test_line = " ".join([wd[0] for wd in current_line] + [w])
        if draw.textlength(test_line, font=font) <= max_w:
            current_line.append((w, len(lines)*100 + len(current_line))) 
        else:
            lines.append(current_line)
            current_line = [(w, len(lines)*100)]
    if current_line: lines.append(current_line)
    
    global_idx = 0
    for line in lines:
        line_w = sum(draw.textlength(wd[0] + " ", font=font) for wd in line)
        cx = W/2 - line_w/2
        for wd, _ in line:
            color = WHITE if global_idx <= revealed_count else MUTED
            draw.text((cx, y), wd, font=font, fill=color, anchor="lm")
            cx += draw.textlength(wd + " ", font=font)
            global_idx += 1
        y += font_size * 1.5


# Confetti Animation[span_12](start_span)[span_12](end_span)[span_13](start_span)[span_13](end_span)
class Confetti:
    def __init__(self):
        self.particles = [{"x": random.randint(100, W-100), "y": random.randint(-400, -50), "s": random.randint(15, 30), "c": random.choice([GREEN, YELLOW, CYAN, WHITE]), "vy": random.randint(20, 35)} for _ in range(60)]
    def draw(self, draw, t):
        for part in self.particles:
            cy = part["y"] + part["vy"] * (t*30)
            if 0 < cy < H:
                draw.rectangle((part["x"], cy, part["x"]+part["s"], cy+part["s"]), fill=part["c"])

_confetti = Confetti()


# -------------------- SCRIPT --------------------

def extract_field(raw, name, next_names):
    next_part = "|".join(re.escape(x) for x in next_names)

    if next_part:
        pattern = (
            rf"(?:^|\n)\s*{re.escape(name)}\s*:\s*(.*?)"
            rf"(?=(?:\n\s*(?:{next_part})\s*:)|$)"
        )
    else:
        pattern = rf"(?:^|\n)\s*{re.escape(name)}\s*:\s*(.*)$"

    match = re.search(pattern, raw, re.I | re.S)
    return clean_text(match.group(1)) if match else ""


def shuffle_data(data):
    # Shuffling logic so that the correct answer is not always A[span_14](start_span)[span_14](end_span)[span_15](start_span)[span_15](end_span)
    options = [data["a"], data["b"], data["c"], data["d"]]
    correct_text = data[data["correct"].lower()]
    random.shuffle(options)
    
    data["a"], data["b"], data["c"], data["d"] = options
    for letter in ["a", "b", "c", "d"]:
        if data[letter] == correct_text:
            data["correct"] = letter.upper()
            break
    return data


def fallback_script(clause_no, part_no, focus, title):
    if (clause_no, part_no) in FALLBACK_SCRIPTS:
        data = FALLBACK_SCRIPTS[(clause_no, part_no)].copy()
        data["title"] = title
        return shuffle_data(data)

    data = {
        "title": title,
        "hook": f"{title} का यह नियम अवश्य जानें।",
        "question": f"{title} के अनुसार कौन-सा कथन सत्य है?",
        "a": focus[:30],
        "b": "कोई विशेष छूट नहीं",
        "c": "अधीक्षक का अनुमोदन",
        "d": "इनमें से कोई नहीं",
        "correct": "A",
        "fact": focus,
        "trap": "परीक्षा में शब्दों और नियमों को ध्यान से पढ़ें।",
        "trick": "ट्रिक: नियम को अच्छी तरह समझ लें।"
    }
    return shuffle_data(data)


def generate_script(state):
    clause_no = state["clause_no"]
    part_no = state["current_part"]

    info = POSTAL_CLAUSE_CATALOG[clause_no]
    title = info["name"]
    focus = info.get(f"part_{part_no}_focus", info["part_1_focus"])

    if not GROQ_API_KEY:
        return fallback_script(clause_no, part_no, focus, title)

    # Added rule to generate a short trick/mnemonic[span_16](start_span)[span_16](end_span)[span_17](start_span)[span_17](end_span)
    prompt = f"""
You are creating an authentic India Post departmental exam Multiple Choice Question (MCQ) in Hindi.

TOPIC: {title}
PART: {part_no}/{info["total_parts"]}
OFFICIAL VERIFIED FACT:
{focus}

Instructions:
1. Create 1 genuine departmental exam question directly testable from the verified fact.
2. HOOK: One sharp, honest curiosity question directly related to the fact (max 10 words). No fake statistics.
3. QUESTION: Clear, precise Hindi exam question (max 14 words).
4. A, B, C, D: 4 plausible options (2-5 words each). One must strictly match the verified fact.
5. CORRECT: Single letter A, B, C, or D.
6. FACT: Concise one-sentence summary of the rule (max 18 words).
7. TRAP: One common misconception or exam confusion (max 16 words).
8. TRICK: One short memory trick or mnemonic to remember the rule (max 10 words).
9. Absolutely no meta text, no dummy options.

Format exactly:
HOOK: ...
QUESTION: ...
A: ...
B: ...
C: ...
D: ...
CORRECT: [A/B/C/D]
FACT: ...
TRAP: ...
TRICK: ...
"""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 450,
            },
            timeout=25,
        )

        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]

        data = {
            "title": title,
            "hook": extract_field(raw, "HOOK", ["QUESTION"]),
            "question": extract_field(raw, "QUESTION", ["A"]),
            "a": extract_field(raw, "A", ["B"]),
            "b": extract_field(raw, "B", ["C"]),
            "c": extract_field(raw, "C", ["D"]),
            "d": extract_field(raw, "D", ["CORRECT"]),
            "correct": extract_field(raw, "CORRECT", ["FACT"]).upper(),
            "fact": extract_field(raw, "FACT", ["TRAP"]),
            "trap": extract_field(raw, "TRAP", ["TRICK"]),
            "trick": extract_field(raw, "TRICK", []),
        }

        if data["correct"] not in {"A", "B", "C", "D"}:
            raise ValueError("Invalid CORRECT field")

        required = ["hook", "question", "a", "b", "c", "d", "fact", "trap"]
        if not all(data[k] for k in required):
            raise ValueError("Incomplete generated script")

        return shuffle_data(data)

    except Exception as exc:
        print("Using Curated Fallback Script:", exc)
        return fallback_script(clause_no, part_no, focus, title)


# -------------------- STATE --------------------

def load_state():
    default = {
        "clause_no": 23,
        "current_part": 1,
    }

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as file:
                saved = json.load(file)
                if isinstance(saved, dict):
                    default.update(saved)
        except Exception:
            pass

    if default["clause_no"] not in POSTAL_CLAUSE_CATALOG:
        default["clause_no"] = 23
        default["current_part"] = 1

    return default


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


# -------------------- AUDIO --------------------

async def make_audio(text, output):
    # TTS retry logic[span_18](start_span)[span_18](end_span)
    for attempt in range(3):
        try:
            if os.path.exists(output):
                os.remove(output)
            tts = edge_tts.Communicate(
                text=text,
                voice=VOICE_NAME,
                rate=VOICE_RATE,
            )
            await tts.save(output)
            return
        except Exception as e:
            if attempt == 2:
                print(f"Audio creation failed: {e}")
            await asyncio.sleep(1)


def audio_duration(path):
    result = subprocess.check_output([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ])
    return float(result.decode().strip())


def tighten_audio(path):
    temp = path + ".tmp.mp3"

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", path,
                "-af",
                (
                    "silenceremove="
                    "start_periods=1:"
                    "start_threshold=-38dB:"
                    "stop_periods=-1:"
                    "stop_duration=0.08:"
                    "stop_threshold=-38dB"
                ),
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                temp,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.replace(temp, path)
    except Exception:
        if os.path.exists(temp):
            os.remove(temp)


# -------------------- SCENE AUDIO --------------------

def make_scene_text(data):
    trick_audio = data.get("trick", "")
    return [
        data["hook"],
        "पहले सोचिए।",
        "गलत विकल्प हटाइए। सही नियम कौन-सा है?",
        data["fact"],
        "परीक्षा का ट्रैप: " + data["trap"] + " " + trick_audio,
        (
            "अब सवाल देखिए। " + data["question"] +
            " विकल्प हैं: A, " + data["a"] +
            ". B, " + data["b"] +
            ". C, " + data["c"] +
            ". D, " + data["d"] + "."
        ),
        "आपका जवाब क्या है? पांच सेकंड में A, B, C या D कमेंट करें।",
        "सही उत्तर है विकल्प " + data["correct"] + ".",
    ]


async def generate_scene_audios(data):
    texts = make_scene_text(data)
    paths = []

    for index, text in enumerate(texts):
        path = f"scene_{index}.mp3"
        await make_audio(text, path)
        tighten_audio(path)
        paths.append(path)

    return paths


def concat_audio(scene_paths, output):
    command = ["ffmpeg", "-y"]

    for path in scene_paths:
        command += ["-i", path]

    inputs = "".join(f"[{i}:a]" for i in range(len(scene_paths)))
    filter_complex = inputs + f"concat=n={len(scene_paths)}:v=0:a=1[outa]"

    command += [
        "-filter_complex", filter_complex,
        "-map", "[outa]",
        "-c:a", "aac",
        "-b:a", "192k",
        output,
    ]

    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# -------------------- DYNAMIC OPTIONS HELPER --------------------

def get_display_choices(data):
    correct = data.get("correct", "A").upper()
    keys = ["A", "B", "C", "D"]
    
    choices = []
    for k in keys:
        choices.append({
            "key": k,
            "text": f"{k}. {data.get(k.lower(), '')}",
            "is_correct": (k == correct),
        })
    return choices


# -------------------- SCENES --------------------

def scene_hook(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.05)

    scale = ease_out_back(min(t*1.5, 1.0)) # Camera motion[span_19](start_span)[span_19](end_span)

    box = (120, 360, 960, 465)
    draw_shadow(im, box, 24)
    rounded(d, box, 24, CARD_2, CYAN, 3)
    
    # Stamp perforation effect[span_20](start_span)[span_20](end_span)[span_21](start_span)[span_21](end_span)[span_22](start_span)[span_22](end_span)
    for x in range(160, 920, 35):
        d.ellipse((x-8, 360-8, x+8, 360+8), fill=BG)
        d.ellipse((x-8, 465-8, x+8, 465+8), fill=BG)

    center_text(d, data["title"], 412, 38, CYAN)

    main_box = (80, 520, 1000, 1260)
    draw_shadow(im, main_box, 40)
    rounded(d, main_box, 40, CARD, "#334155", 4)
    
    # Badge inside hook[span_23](start_span)[span_23](end_span)
    draw_badge(d, "POSTAL EXAM RULE", W/2, 615, 38, "#334155", MUTED)

    wrapped_hook = wrap_text(d, data["hook"], 54, 840)
    lines = wrapped_hook.split("\n")
    y_start = 850 - (len(lines) - 1) * 38
    for line in lines:
        center_text(d, line, y_start, 54, WHITE, scale)
        y_start += 76

    center_text(d, "पहले जवाब मत देखिए", 1460, 38, YELLOW, pulse(t, 6, 0.05))
    return im


def scene_guess(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.14)

    center_text(d, "आप क्या चुनेंगे?", 260, 60, WHITE)

    choices = get_display_choices(data)
    for i, item in enumerate(choices):
        # Easing and option reveal timing[span_24](start_span)[span_24](end_span)[span_25](start_span)[span_25](end_span)
        anim_t = min(1.0, max(0.0, (t - i*0.2) * 2))
        slide = (1.0 - ease_out_back(anim_t)) * 300
        
        y = 480 + i * 270
        draw_authority_card(im, d, item["text"], 110, y, 970, y + 210, None, x_offset=slide if i%2==0 else -slide)

    center_text(d, "सोचिए...", 1450, 46, YELLOW)
    return im


def scene_elimination(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.22)

    center_text(d, "गलत विकल्प हटते हैं", 270, 54, WHITE)

    choices = get_display_choices(data)
    wrong_count = 0
    for i, item in enumerate(choices):
        status = None
        shake = 0
        if not item["is_correct"]:
            if t > 0.35 + wrong_count * 0.45:
                status = "wrong"
                shake = math.sin(t * 30) * 10 # Elimination shake[span_26](start_span)[span_26](end_span)
            wrong_count += 1
        else:
            if t > 1.25:
                status = "correct"

        y = 480 + i * 270
        draw_authority_card(im, d, item["text"], 110, y, 970, y + 210, status, x_offset=shake)

    return im


def scene_answer(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.30)
    
    _confetti.draw(d, t) # Confetti effect[span_27](start_span)[span_27](end_span)[span_28](start_span)[span_28](end_span)

    center_text(d, "सही उत्तर", 320, 52, MUTED)

    scale = ease_out_back(min(t*2, 1.0))
    box = (100, 460, 980, 1140)
    
    # Ring animation for correct reveal[span_29](start_span)[span_29](end_span)
    ring_s = t * 60
    if t < 1.0:
        d.rounded_rectangle((box[0]-ring_s, box[1]-ring_s, box[2]+ring_s, box[3]+ring_s), int(45+ring_s), outline=GREEN, width=int(max(1, 8-ring_s/8)))

    draw_shadow(im, box, 45)
    rounded(d, box, 45, CARD_2, GREEN, 6)
    draw_check(d, W // 2, 590, 48, scale)

    correct_key = data.get("correct", "A").upper()
    correct_text = data.get(correct_key.lower(), "")

    center_text(d, f"विकल्प {correct_key}", 740, 72, GREEN)

    wrapped = wrap_text(d, correct_text, 46, 800)
    y = 860
    for line in wrapped.split("\n"):
        center_text(d, line, y, 46, WHITE)
        y += 64

    center_text(d, "यही point परीक्षा में याद रखें", 1320, 40, CYAN)
    return im


def scene_fact(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.39)

    center_text(d, "महत्वपूर्ण नियम", 270, 52, CYAN)

    rounded(d, (120, 360, 960, 455), 22, CARD_2, "#334155", 3)
    center_text(d, data["title"], 408, 36, YELLOW)

    box = (80, 510, 1000, 1370)
    draw_shadow(im, box, 40)
    rounded(d, box, 40, CARD, GREEN, 5)
    
    draw_badge(d, "VERIFIED RULE", W/2, 610, 42, GREEN, BG)

    # Word-by-word highlight applied[span_30](start_span)[span_30](end_span)[span_31](start_span)[span_31](end_span)
    draw_word_by_word(d, data["fact"], 750, 46, 820, t)

    center_text(d, "सीधे परीक्षा में पूछा जाने वाला नियम", 1520, 36, MUTED)
    return im


def scene_trap(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.50)
    
    trap_scale = pulse(t, 8, 0.02) # Multi-beat pulse[span_32](start_span)[span_32](end_span)

    rounded(d, (70, 270, 1010, 1570), 45, CARD, YELLOW, 5)
    center_text(d, "EXAM TRAP", 370, 62, YELLOW, trap_scale)
    center_text(d, "सावधानी: यहाँ गलती न करें!", 460, 36, MUTED)

    rounded(d, (120, 550, 960, 880), 30, CARD_2, RED, 4)
    center_text(d, "अक्सर होने वाला भ्रम", 620, 38, RED)
    draw_x(d, W // 2, 740, 40)
    
    trap = wrap_text(d, data["trap"], 40, 780)
    y = 960
    for line in trap.split("\n"):
        center_text(d, line, y, 40, WHITE)
        y += 50

    # Trick layout added inside Trap scene[span_33](start_span)[span_33](end_span)[span_34](start_span)[span_34](end_span)
    trick_text = data.get("trick", "")
    if trick_text:
        trick_y = 1250
        rounded(d, (120, trick_y, 960, trick_y + 250), 30, "#3B2A00", YELLOW, 4)
        draw_badge(d, "TRICK", W/2, trick_y + 50, 35, YELLOW, "#3B2A00")
        trick_wrapped = wrap_text(d, trick_text, 45, 780)
        ty = trick_y + 120
        for l in trick_wrapped.split("\n"):
            center_text(d, l, ty, 45, WHITE)
            ty += 60
            
    return im


def draw_option_row(im, draw, letter, text, y, active=False):
    outline = CYAN if active else "#2A4058"
    box = (65, y, 1015, y + 145)
    draw_shadow(im, box, 28)
    rounded(draw, box, 28, CARD_2, outline, 4)

    font = get_font(38)
    draw.text((105, y + 72), letter + ".", font=font, fill=CYAN, anchor="lm")
    draw.text((175, y + 72), text, font=font, fill=WHITE, anchor="lm")


def scene_mcq(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.64)

    center_text(d, "POSTAL MCQ", 245, 58, CYAN)

    question = wrap_text(d, data["question"], 47, 900)
    y = 365
    for line in question.split("\n"):
        center_text(d, line, y, 47, WHITE)
        y += 68

    options = [
        ("A", data["a"]),
        ("B", data["b"]),
        ("C", data["c"]),
        ("D", data["d"]),
    ]

    y0 = 610
    for i, (letter, text) in enumerate(options):
        reveal_at = i * 0.30
        if t >= reveal_at:
            draw_option_row(im, d, letter, text, y0 + i * 190, active=(t < reveal_at + 0.25))

    return im


def scene_countdown(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.82)

    center_text(d, "अपना जवाब चुनिए", 270, 54, WHITE)

    options = [
        ("A", data["a"]),
        ("B", data["b"]),
        ("C", data["c"]),
        ("D", data["d"]),
    ]

    y0 = 500
    for i, (letter, text) in enumerate(options):
        draw_option_row(im, d, letter, text, y0 + i * 190, False)

    remaining = max(1, 5 - int(t))
    center_text(d, str(remaining), 1510, 100, YELLOW, pulse(t, 10, 0.05)) # Countdown pulse[span_35](start_span)[span_35](end_span)
    center_text(d, "A / B / C / D कमेंट करें", 1660, 42, WHITE)
    return im


def scene_result(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.96)

    center_text(d, "सही उत्तर", 360, 55, MUTED)

    rounded(d, (100, 500, 980, 1180), 50, CARD, GREEN, 6)
    center_text(d, data["correct"], 650, 120, GREEN)

    key = {"A": "a", "B": "b", "C": "c", "D": "d"}[data["correct"]]

    center_text(d, data[key], 850, 48, WHITE)
    
    # CTA Script Teaser for the next part[span_36](start_span)[span_36](end_span)[span_37](start_span)[span_37](end_span)
    teaser_y = 1350
    draw_shadow(im, (150, teaser_y, 930, teaser_y + 180), 30)
    rounded(d, (150, teaser_y, 930, teaser_y + 180), 30, CARD_2, YELLOW, 3)
    draw_badge(d, "UPCOMING NEXT", W/2, teaser_y, 30, YELLOW, BG)
    center_text(d, "अगले नियम के लिए Save करें", teaser_y + 100, 40, WHITE)

    center_text(d, "@POSTAL_WALA", 1650, 48, CYAN)
    return im


# -------------------- FRAME / VIDEO BUILD --------------------

def render_scene(scene_function, data, duration, prefix):
    count = max(1, int(math.ceil(duration * FPS)))
    paths = []

    for index in range(count):
        t = index / FPS
        image = scene_function(data, t, duration)
        path = f"{prefix}_{index:05d}.jpg"
        image.save(path, quality=94, optimize=False)
        paths.append(path)

    return paths


def frames_to_video(frame_paths, output_path):
    concat_path = "frames.txt"
    with open(concat_path, "w", encoding="utf-8") as file:
        for frame in frame_paths:
            file.write(f"file '{os.path.abspath(frame)}'\n")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-r", str(FPS),
            "-f", "concat",
            "-safe", "0",
            "-i", concat_path,
            "-vf", f"fps={FPS},format=yuv420p",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "19",
            output_path,
        ],
        check=True,
    )
    os.remove(concat_path)


def mux(video, audio, output):
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video,
            "-i", audio,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output,
        ],
        check=True,
    )


# -------------------- MAIN --------------------

def build_reel(data, output_video=None):
    if not output_video:
        output_video = os.path.join(OUTPUT_DIR, OUTPUT_VIDEO)

    os.makedirs(os.path.dirname(output_video), exist_ok=True)

    scene_audios = asyncio.run(generate_scene_audios(data))
    durations = [audio_duration(path) for path in scene_audios]

    scene_functions = [
        scene_hook,
        scene_guess,
        scene_elimination,
        scene_answer,
        scene_fact,
        scene_trap,
        scene_mcq,
        scene_countdown,
        scene_result,
    ]

    audio_chapter_map = [
        (0, scene_functions[0]),
        (1, scene_functions[1]),
        (2, scene_functions[2]),
        (2, scene_functions[3]),
        (3, scene_functions[4]),
        (4, scene_functions[5]),
        (5, scene_functions[6]),
        (6, scene_functions[7]),
        (7, scene_functions[8]),
    ]

    chapter_remaining = durations[:]
    visual_durations = []

    for scene_index, chapter_index in enumerate([0, 1, 2, 2, 3, 4, 5, 6, 7]):
        if scene_index == 2:
            visual_durations.append(chapter_remaining[2] * 0.48)
        elif scene_index == 3:
            visual_durations.append(chapter_remaining[2] * 0.52)
        else:
            visual_durations.append(chapter_remaining[chapter_index])

    frame_paths = []
    for i, (chapter_index, scene_function) in enumerate(audio_chapter_map):
        frame_paths += render_scene(
            scene_function,
            data,
            visual_durations[i],
            f"scene_{i}",
        )

    silent = "silent_reel.mp4"
    frames_to_video(frame_paths, silent)

    master_audio = "master_audio.m4a"
    concat_audio(scene_audios, master_audio)

    mux(silent, master_audio, output_video)

    for path in frame_paths:
        try:
            os.remove(path)
        except OSError:
            pass

    for path in scene_audios + [silent, master_audio]:
        try:
            os.remove(path)
        except OSError:
            pass

    total = audio_duration(output_video)
    print(f"COMPLETE: {output_video} ({total:.2f}s)")


def advance_state(state):
    clause = state["clause_no"]
    part = state["current_part"]

    info = POSTAL_CLAUSE_CATALOG[clause]

    if part < info["total_parts"]:
        state["current_part"] = part + 1
    else:
        keys = sorted(POSTAL_CLAUSE_CATALOG)
        current_index = keys.index(clause)
        state["clause_no"] = keys[(current_index + 1) % len(keys)]
        state["current_part"] = 1

    save_state(state)


if __name__ == "__main__":
    state = load_state()
    print("Current State:", state)

    data = generate_script(state)
    print("\nSCRIPT DATA:")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    reels_dir = "generated_reels"
    os.makedirs(reels_dir, exist_ok=True)
    output_filename = f"reel_clause_{state['clause_no']}_part_{state['current_part']}.mp4"
    output_video_path = os.path.join(reels_dir, output_filename)

    build_reel(data, output_video_path)
    advance_state(state)
