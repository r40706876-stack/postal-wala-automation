import os
import re
import json
import math
import asyncio
import subprocess
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
import edge_tts


# -------------------- CONFIG --------------------

OUTPUT_DIR = "generated_reels"
OUTPUT_VIDEO = "final_reel.mp4"
STATE_FILE = "progress_state.json"

VOICE_NAME = "hi-IN-SwaraNeural"
VOICE_RATE = "+10%"

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
    },
}


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

def new_canvas():
    return Image.new("RGB", (W, H), BG)


def rounded(draw, box, radius=35, fill=CARD, outline=None, width=2):
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width,
    )


def center_text(draw, text, y, size, fill=WHITE):
    font = get_font(size)
    draw.text((W / 2, y), text, font=font, fill=fill, anchor="mm")


def brand(draw):
    font = get_font(27)
    draw.text((55, 45), "POSTAL WALA", font=font, fill="#64748B", anchor="la")


def progress_bar(draw, ratio):
    left = 55
    right = W - 55
    y = 86

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


def draw_blinking_target_badge(draw, t):
    """
    Rhythmic blinking exam badge for high CTR and retention.
    """
    is_bright = (int(t * 3.5) % 2) == 0
    bg_color = "#E11D48" if is_bright else "#881337"
    border_color = "#FDE047" if is_bright else "#F43F5E"

    box = (100, 115, W - 100, 185)
    draw.rounded_rectangle(box, radius=18, fill=bg_color, outline=border_color, width=3)

    font_badge = get_font(34)
    draw.text((W / 2, 150), "★ GDS TO MTS / PM / PA ★", font=font_badge, fill=WHITE, anchor="mm")


def draw_animated_x(draw, cx, cy, progress, size=32):
    """
    Progressive draw transition for Red X:
    Line 1 draws from 0.0 to 0.5, then Line 2 draws from 0.5 to 1.0
    """
    p1 = min(1.0, max(0.0, progress / 0.5))
    draw.line(
        (cx - size, cy - size, cx - size + 2 * size * p1, cy - size + 2 * size * p1),
        fill=RED,
        width=12,
    )
    if progress > 0.5:
        p2 = min(1.0, max(0.0, (progress - 0.5) / 0.5))
        draw.line(
            (cx + size, cy - size, cx + size - 2 * size * p2, cy - size + 2 * size * p2),
            fill=RED,
            width=12,
        )


def draw_animated_check(draw, cx, cy, progress, size=32):
    """
    Progressive draw transition for Green Checkmark:
    First short down-tick (0.0 to 0.35), then long up-tick (0.35 to 1.0)
    """
    p1 = min(1.0, max(0.0, progress / 0.35))
    x0, y0 = cx - size, cy
    x1, y1 = cx - size // 3, cy + size
    curr_x1 = x0 + (x1 - x0) * p1
    curr_y1 = y0 + (y1 - y0) * p1
    draw.line((x0, y0, curr_x1, curr_y1), fill=GREEN, width=13)

    if progress > 0.35:
        p2 = min(1.0, max(0.0, (progress - 0.35) / 0.65))
        x2, y2 = cx + size, cy - size
        curr_x2 = x1 + (x2 - x1) * p2
        curr_y2 = y1 + (y2 - y1) * p2
        draw.line((x1, y1, curr_x2, curr_y2), fill=GREEN, width=13)


def draw_option_card(draw, letter, text, y, status=None, anim_prog=1.0, slide_offset=0):
    """
    Renders option card with animated slide-in, progressive tick/cross,
    and pulsating green glow for the correct answer.
    """
    x1, x2 = 75 + slide_offset, W - 75 + slide_offset
    h = 145

    if status == "correct":
        fill = "#064E3B"
        outline = GREEN
        badge_fill = GREEN
        badge_text = WHITE
        text_color = WHITE
        border_w = 4
        # Outer glow transition ring
        glow_pad = int(3 * (anim_prog % 1.0))
        draw.rounded_rectangle(
            (x1 - glow_pad, y - glow_pad, x2 + glow_pad, y + h + glow_pad),
            radius=26,
            outline="#059669",
            width=2,
        )
    elif status == "wrong":
        fill = "#151F2E"
        outline = RED
        badge_fill = "#2A151F"
        badge_text = RED
        text_color = "#64748B"
        border_w = 3
    else:
        fill = CARD_2
        outline = "#2A4058"
        badge_fill = "#1E293B"
        badge_text = CYAN
        text_color = WHITE
        border_w = 2

    rounded(draw, (x1, y, x2, y + h), 24, fill, outline, border_w)

    # Letter badge
    bx = x1 + 25
    by = y + 25
    draw.rounded_rectangle((bx, by, bx + 95, by + 95), radius=16, fill=badge_fill)
    f_badge = get_font(42)
    draw.text((bx + 47, by + 47), letter, font=f_badge, fill=badge_text, anchor="mm")

    # Text
    f_txt = get_font(38)
    draw.text((bx + 125, y + 72), text[:32], font=f_txt, fill=text_color, anchor="lm")

    # Animated Stamp Transitions
    cx = x2 - 70
    cy = y + 72
    if status == "wrong":
        draw_animated_x(draw, cx, cy, progress=anim_prog, size=28)
    elif status == "correct":
        draw_animated_check(draw, cx, cy, progress=anim_prog, size=28)


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


def fallback_script(clause_no, part_no, focus, title):
    if (clause_no, part_no) in FALLBACK_SCRIPTS:
        data = FALLBACK_SCRIPTS[(clause_no, part_no)].copy()
        data["title"] = title
        return data

    return {
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
    }


def generate_script(state):
    clause_no = state["clause_no"]
    part_no = state["current_part"]

    info = POSTAL_CLAUSE_CATALOG[clause_no]
    title = info["name"]
    focus = info.get(f"part_{part_no}_focus", info["part_1_focus"])

    if not GROQ_API_KEY:
        return fallback_script(clause_no, part_no, focus, title)

    prompt = f"""
You are creating an authentic India Post departmental exam Multiple Choice Question (MCQ) in Hindi.

TOPIC: {title}
PART: {part_no}/{info["total_parts"]}
OFFICIAL VERIFIED FACT:
{focus}

Instructions:
1. Create 1 genuine departmental exam question directly testable from the verified fact.
2. HOOK: One sharp, curiosity question directly related to the fact (max 10 words).
3. QUESTION: Clear, precise Hindi exam question (max 14 words).
4. A, B, C, D: 4 plausible options (2-5 words each). One must strictly match the verified fact.
5. CORRECT: Single letter A, B, C, or D.
6. FACT: Concise one-sentence summary of the rule (max 18 words).
7. TRAP: One common misconception or exam confusion (max 16 words).
8. Absolutely no meta text, no dummy options.

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
            "trap": extract_field(raw, "TRAP", []),
        }

        if data["correct"] not in {"A", "B", "C", "D"}:
            raise ValueError("Invalid CORRECT field")

        required = ["hook", "question", "a", "b", "c", "d", "fact", "trap"]
        if not all(data[k] for k in required):
            raise ValueError("Incomplete generated script")

        return data

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
    if os.path.exists(output):
        os.remove(output)

    tts = edge_tts.Communicate(
        text=text,
        voice=VOICE_NAME,
        rate=VOICE_RATE,
    )
    await tts.save(output)


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
    return [
        f"{data['hook']} सवाल है: {data['question']}",
        "अपना जवाब सोचिए। 5 सेकंड में कमेंट करें!",
        f"गलत विकल्प हटाइए। सही उत्तर है विकल्प {data['correct']}!",
        f"विभागीय नियम याद रखें: {data['fact']}",
        f"परीक्षा का ट्रैप: {data['trap']}",
        "रिवीजन के लिए इस रील को सेव करें और शेयर करें।",
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


# -------------------- SCENES --------------------

def scene_question(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.15)
    draw_blinking_target_badge(d, t)

    # Question Box
    rounded(d, (65, 215, W - 65, 545), 28, CARD, "#334155", 3)
    center_text(d, data["title"], 265, 34, CYAN)

    question_text = wrap_text(d, data["question"], 44, 880)
    lines = question_text.split("\n")
    y_start = 345 - (len(lines) - 1) * 25
    for line in lines:
        center_text(d, line, y_start, 44, WHITE)
        y_start += 56

    # 4 Options with TV-Quiz style staggered slide-in transitions
    options = [("A", data["a"]), ("B", data["b"]), ("C", data["c"]), ("D", data["d"])]
    y0 = 600
    for idx, (letter, txt) in enumerate(options):
        # Entry delay per option (0.15s stagger)
        start_delay = idx * 0.18
        if t < start_delay:
            continue
        # Slide progress from right to position
        slide_p = min(1.0, (t - start_delay) / 0.22)
        # Ease out quadratic
        ease_p = 1.0 - (1.0 - slide_p) * (1.0 - slide_p)
        slide_offset = int((1.0 - ease_p) * 220)

        draw_option_card(d, letter, txt, y0 + idx * 175, status=None, slide_offset=slide_offset)

    center_text(d, "ध्यान से प्रश्न को समझें...", 1380, 38, MUTED)
    return im


def scene_countdown(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.35)
    draw_blinking_target_badge(d, t)

    # Compact question box
    rounded(d, (65, 215, W - 65, 485), 28, CARD, "#334155", 3)
    center_text(d, "DEPARTMENTAL EXAM QUESTION", 260, 32, MUTED)
    question_text = wrap_text(d, data["question"], 40, 880)
    lines = question_text.split("\n")
    y_start = 325
    for line in lines:
        center_text(d, line, y_start, 40, WHITE)
        y_start += 52

    # Options stay locked in place
    options = [("A", data["a"]), ("B", data["b"]), ("C", data["c"]), ("D", data["d"])]
    y0 = 530
    for idx, (letter, txt) in enumerate(options):
        draw_option_card(d, letter, txt, y0 + idx * 170, status=None)

    # Animated depleting countdown bar
    progress = max(0.0, min(1.0, 1.0 - (t / max(duration, 0.1))))
    remaining = max(1, 5 - int((1.0 - progress) * 5))

    rounded(d, (100, 1260, W - 100, 1490), 28, CARD, YELLOW, 3)
    center_text(d, f"TIME LEFT: {remaining}s", 1325, 60, YELLOW)

    bx1, bx2 = 140, W - 140
    d.rounded_rectangle((bx1, 1395, bx2, 1407), radius=6, fill="#1B2A3A")
    d.rounded_rectangle((bx1, 1395, bx1 + (bx2 - bx1) * progress, 1407), radius=6, fill=YELLOW)

    center_text(d, "A / B / C / D कमेंट करें! 👇", 1540, 44, WHITE)
    return im


def scene_elimination(data, t, duration):
    """
    Dramatic progressive elimination transition:
    Wrong options are crossed out with dynamic red line draw animations,
    and correct option pops up with a progressive green check and pulsing glow.
    """
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.55)
    draw_blinking_target_badge(d, t)

    center_text(d, "गलत विकल्प हटते हैं...", 240, 48, CYAN)

    correct_letter = data.get("correct", "A").upper()
    options = [("A", data["a"]), ("B", data["b"]), ("C", data["c"]), ("D", data["d"])]
    wrong_keys = [k for k, _ in options if k != correct_letter]

    # Staggered animation triggers
    t_stage1 = duration * 0.15
    t_stage2 = duration * 0.40
    t_stage3 = duration * 0.65
    t_correct = duration * 0.82

    y0 = 330
    for idx, (letter, txt) in enumerate(options):
        status = None
        anim_prog = 1.0

        if letter in wrong_keys:
            wrong_idx = wrong_keys.index(letter)
            if wrong_idx == 0 and t >= t_stage1:
                status = "wrong"
                anim_prog = min(1.0, (t - t_stage1) / 0.22)
            elif wrong_idx == 1 and t >= t_stage2:
                status = "wrong"
                anim_prog = min(1.0, (t - t_stage2) / 0.22)
            elif wrong_idx == 2 and t >= t_stage3:
                status = "wrong"
                anim_prog = min(1.0, (t - t_stage3) / 0.22)
        else:
            if t >= t_correct:
                status = "correct"
                anim_prog = min(1.0, (t - t_correct) / 0.22)

        draw_option_card(d, letter, txt, y0 + idx * 180, status=status, anim_prog=anim_prog)

    if t >= t_correct:
        center_text(d, f"✓ सही उत्तर है: विकल्प {correct_letter}", 1120, 50, GREEN)
    else:
        center_text(d, "सोचिए सही नियम कौन-सा है...", 1120, 40, YELLOW)

    return im


def scene_fact(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.72)
    draw_blinking_target_badge(d, t)

    center_text(d, "महत्वपूर्ण विभागीय नियम", 240, 48, CYAN)

    rounded(d, (100, 310, W - 100, 400), 20, CARD_2, "#334155", 3)
    center_text(d, data["title"], 355, 36, YELLOW)

    # Fact Box with expanding animated entrance
    grow_p = min(1.0, t / 0.3)
    ease_grow = 1.0 - (1.0 - grow_p) * (1.0 - grow_p)
    f_w = int((W - 140) * ease_grow)
    left = (W - f_w) // 2
    right = left + f_w

    rounded(d, (left, 440, right, 1160), 36, CARD, GREEN, 5)

    if t > 0.2:
        check_p = min(1.0, (t - 0.2) / 0.3)
        draw_animated_check(d, W // 2, 530, progress=check_p, size=38)
        center_text(d, "VERIFIED POSTAL RULE", 620, 40, GREEN)

        fact_text = wrap_text(d, data["fact"], 44, 820)
        lines = fact_text.split("\n")
        y = 750 - (len(lines) - 1) * 32
        for line in lines:
            center_text(d, line, y, 44, WHITE)
            y += 64

        center_text(d, "सीधे परीक्षा में पूछा जाने वाला नियम", 1260, 38, MUTED)

    return im


def scene_trap(data, t, duration):
    """
    Enhanced 2-step staggered reveal:
    1. Trap mistake box pops and stamps animated Red X.
    2. Correct memory box pops and stamps animated Green Checkmark.
    """
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.88)
    draw_blinking_target_badge(d, t)

    rounded(d, (70, 240, W - 70, 1420), 40, CARD, YELLOW, 5)
    center_text(d, "EXAM TRAP ⚠️", 330, 60, YELLOW)
    center_text(d, "सावधानी: यहाँ 90% छात्र गलती करते हैं!", 410, 36, MUTED)

    # Trap Mistake Box (Stamps Red X at t = 0.2s)
    rounded(d, (110, 490, W - 110, 780), 28, CARD_2, RED, 4)
    center_text(d, "अक्सर होने वाला भ्रम", 560, 36, RED)
    x_prog = min(1.0, max(0.0, (t - 0.15) / 0.28))
    draw_animated_x(d, W // 2, 665, progress=x_prog, size=32)

    # Correct Knowledge Box (Stamps Green Tick at t = 0.65s)
    if t >= 0.55:
        rounded(d, (110, 830, W - 110, 1340), 28, CARD_2, GREEN, 4)
        center_text(d, "याद रखने योग्य बात", 900, 36, GREEN)

        chk_prog = min(1.0, max(0.0, (t - 0.65) / 0.30))
        draw_animated_check(d, W - 170, 900, progress=chk_prog, size=24)

        trap_text = wrap_text(d, data["trap"], 40, 760)
        y = 1010
        for line in trap_text.split("\n"):
            center_text(d, line, y, 40, WHITE)
            y += 58

    return im


def scene_result(data, t, duration):
    im = new_canvas()
    d = ImageDraw.Draw(im)
    brand(d)
    progress_bar(d, 0.98)
    draw_blinking_target_badge(d, t)

    # Outro Card
    rounded(d, (90, 380, W - 90, 1260), 40, CARD, CYAN, 4)

    center_text(d, "POSTAL EXAM PREPARATION", 490, 42, MUTED)
    center_text(d, "@POSTAL_WALA", 610, 70, CYAN)

    rounded(d, (130, 730, W - 130, 930), 26, CARD_2, GREEN, 4)
    chk_prog = min(1.0, t / 0.3)
    draw_animated_check(d, W // 2, 795, progress=chk_prog, size=32)
    center_text(d, f"सही उत्तर: विकल्प {data['correct']}", 870, 44, GREEN)

    center_text(d, "नियम याद रखने के लिए Reel को Save करें", 1020, 38, WHITE)
    center_text(d, "और अपने सहकर्मियों के साथ Share करें! 🚀", 1090, 38, YELLOW)

    center_text(d, "अगले Postal Rule के लिए फॉलो करें", 1400, 42, CYAN)
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
        scene_question,     # 0: Hook + Staggered slide-in options
        scene_countdown,    # 1: 5s Animated countdown timer
        scene_elimination,  # 2: Progressive Cross & Tick draw transitions
        scene_fact,         # 3: Verified rule explanation with scale-in
        scene_trap,         # 4: Staggered animated trap & memory check
        scene_result,       # 5: Outro save/share CTA
    ]

    frame_paths = []
    for i, scene_func in enumerate(scene_functions):
        frame_paths += render_scene(
            scene_func,
            data,
            durations[i],
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

    reels_dir = OUTPUT_DIR
    os.makedirs(reels_dir, exist_ok=True)
    output_filename = f"reel_clause_{state['clause_no']}_part_{state['current_part']}.mp4"
    output_video_path = os.path.join(reels_dir, output_filename)

    build_reel(data, output_video_path)
    advance_state(state)
