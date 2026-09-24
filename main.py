"""
POSTAL WALA - Retention Reel Engine v2
--------------------------------------
Flow (curiosity loop, answer sabse aakhir me):
  0 HOOK        -> frame 0 se text + motion, "EXAM TRAP" stamp slam
  1 QUESTION    -> sawal + options voice ke saath ek-ek karke slide-in
  2 COUNTDOWN   -> 3-2-1 ring timer, "comment me lock karo"
  3 HINT        -> clue (answer nahi batata, viewer ko smart feel karata hai)
  4 ELIMINATE   -> galat options ek-ek karke kat-te hain, "bache 2" suspense
  5 REVEAL      -> sahi option zoom + burst + confetti + ding
  6 RULE + TRAP -> niyam + exam trap (keywords highlight)
  7 CTA/LOOP    -> comment prompt + agle part ka teaser

Run:                         python main.py
Test (bina internet/TTS):    DRY_RUN=1 python main.py
Requirements:                pip install edge-tts pillow numpy requests   (+ ffmpeg installed)
"""

import os
import re
import json
import math
import wave
import random
import asyncio
import subprocess
from pathlib import Path
from functools import lru_cache

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, features


# ==================== CONFIG ====================

OUTPUT_DIR = "generated_reels"
STATE_FILE = "progress_state.json"

VOICE_NAME = "hi-IN-SwaraNeural"
VOICE_RATE = "+12%"
VOICE_PITCH = "+2Hz"

W, H = 1080, 1920
FPS = 30
SR = 44100
COUNTDOWN_SECONDS = 3

DRY_RUN = os.getenv("DRY_RUN", "0") == "1"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

FONT_FILE = os.getenv("FONT_FILE", "Mukta-ExtraBold.ttf")
FONT_URLS = [
    "https://raw.githubusercontent.com/google/fonts/main/ofl/mukta/Mukta-ExtraBold.ttf",
    "https://raw.githubusercontent.com/google/fonts/main/ofl/mukta/Mukta-Bold.ttf",
]
FALLBACK_FONTS = [
    "Mukta-Bold.ttf",
    "C:/Windows/Fonts/NirmalaB.ttf",
    "C:/Windows/Fonts/Nirmala.ttf",
    "C:/Windows/Fonts/Nirmala.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]

# Palette
BG_TOP = (5, 10, 22)
BG_BOTTOM = (10, 24, 44)
CARD = (14, 27, 45)
CARD_2 = (19, 38, 61)
WHITE = (248, 250, 252)
MUTED = (159, 176, 194)
RED = (239, 68, 68)
GREEN = (34, 197, 94)
YELLOW = (250, 204, 21)
ORANGE = (245, 158, 11)
CYAN = (56, 189, 248)
BLUE = (37, 99, 235)
PURPLE = (139, 92, 246)

MOODS = {
    "red": (190, 30, 45),
    "blue": (30, 90, 200),
    "yellow": (200, 140, 10),
    "green": (20, 150, 80),
    "purple": (110, 60, 200),
}


# ==================== VERIFIED CATALOG ====================

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


# ==================== CURATED FALLBACK BANK ====================
# hook = challenge + stake (bina fake statistic)
# hint = clue jo answer seedha nahi batata

FALLBACK_SCRIPTS = {
    (1, 1): {
        "hook": "डाक विभाग का सबसे बड़ा अफसर कौन? तीन सेकंड में बताइए!",
        "question": "डाक विभाग का शीर्ष प्रशासनिक प्रमुख कौन होता है?",
        "a": "महानिदेशक (DG Posts)", "b": "डाक सचिव", "c": "पोस्टमास्टर जनरल", "d": "अधीक्षक डाकघर",
        "correct": "A",
        "hint": "सर्किल का नहीं, पूरे देश के विभाग का प्रमुख सोचिए।",
        "fact": "संचार मंत्रालय के अधीन महानिदेशक (DG Posts) शीर्ष प्रशासनिक प्रमुख हैं।",
        "trap": "पोस्टमास्टर जनरल केवल सर्किल स्तर के प्रमुख होते हैं, विभाग के नहीं।",
    },
    (1, 2): {
        "hook": "डाक सेवा बोर्ड में कितने पूर्णकालिक सदस्य? गिनती में यहीं गड़बड़ होती है!",
        "question": "डाक सेवा बोर्ड में कुल कितने पूर्णकालिक सदस्य होते हैं?",
        "a": "6 सदस्य", "b": "4 सदस्य", "c": "5 सदस्य", "d": "8 सदस्य",
        "correct": "A",
        "hint": "चेयरमैन को अलग रखकर गिनिए।",
        "fact": "डाक सेवा बोर्ड में एक चेयरमैन और 6 पूर्णकालिक सदस्य होते हैं।",
        "trap": "चेयरमैन को मिलाकर कुल 7 होते हैं, पूर्णकालिक सदस्य 6 ही हैं।",
    },
    (2, 1): {
        "hook": "डाकघर कितनी श्रेणियों के होते हैं? सिर्फ तीन सेकंड हैं आपके पास!",
        "question": "डाकघर की कितनी प्रमुख श्रेणियां निर्धारित हैं?",
        "a": "3 श्रेणियां", "b": "2 श्रेणियां", "c": "4 श्रेणियां", "d": "5 श्रेणियां",
        "correct": "A",
        "hint": "प्रधान, उप और गाँव वाला डाकघर याद कीजिए।",
        "fact": "डाकघर की 3 श्रेणियां हैं: प्रधान डाकघर, उप डाकघर और शाखा डाकघर।",
        "trap": "मोबाइल डाकघर अलग श्रेणी नहीं बल्कि एक विशेष सेवा व्यवस्था है।",
    },
    (2, 2): {
        "hook": "उप डाकघर रोज़ का हिसाब किसे भेजता है? सीधा ऊपर नहीं जाता!",
        "question": "उप डाकघर (SO) अपना दैनिक लेखा किसे प्रेषित करता है?",
        "a": "प्रधान डाकघर (HO)", "b": "मंडल कार्यालय", "c": "सर्किल कार्यालय", "d": "मुख्यालय",
        "correct": "A",
        "hint": "SO किसके अधीन काम करता है, जवाब वहीं है।",
        "fact": "उप डाकघर दैनिक लेखा अपने प्रधान डाकघर (HO) को भेजता है।",
        "trap": "SO सीधे मंडल अधीक्षक को दैनिक लेखा नहीं भेजता।",
    },
    (2, 3): {
        "hook": "गाँव का शाखा डाकघर ज़्यादा से ज़्यादा कितने घंटे खुलता है?",
        "question": "ग्रामीण शाखा डाकघर (BO) के अधिकतम कार्य घंटे कितने हैं?",
        "a": "5 घंटे", "b": "4 घंटे", "c": "6 घंटे", "d": "8 घंटे",
        "correct": "A",
        "hint": "न्यूनतम और अधिकतम में सिर्फ एक घंटे का फर्क है।",
        "fact": "शाखा डाकघर के कार्य घंटे न्यूनतम 4 और अधिकतम 5 घंटे होते हैं।",
        "trap": "न्यूनतम 4 घंटे और अधिकतम 5 घंटे में भ्रमित न हों।",
    },
    (3, 1): {
        "hook": "रात्रि डाकघर को रात साढ़े आठ तक खोलने की पावर किसके पास है?",
        "question": "रात्रि डाकघर के घंटे 8:30 बजे तक बढ़ाने का अधिकार किसे है?",
        "a": "महानिदेशक (DG)", "b": "Postmaster", "c": "SSPO", "d": "CPMG",
        "correct": "A",
        "hint": "यह पावर लोकल अफसर के पास नहीं, सबसे ऊपर है।",
        "fact": "रात्रि डाकघर के घंटे 8:30 बजे तक बढ़ाने का विशेष अधिकार DG को है।",
        "trap": "यह अधिकार स्थानीय पोस्टमास्टर या SSPO के पास नहीं होता।",
    },
    (3, 2): {
        "hook": "रविवार को रात्रि डाकघर कब खुलता है? रात वाला नियम यहाँ नहीं चलता!",
        "question": "रविवार और राष्ट्रीय अवकाश पर रात्रि डाकघर का समय क्या है?",
        "a": "सुबह 10 से शाम 5", "b": "सुबह 8 से दोपहर 2", "c": "दोपहर 12 से शाम 8", "d": "पूरे दिन",
        "correct": "A",
        "hint": "छुट्टी के दिन समय दिन का ही रहता है, सुबह से शाम।",
        "fact": "रविवार और अवकाश के दिन सीमित सेवाएं सुबह 10 से शाम 5 बजे तक मिलती हैं।",
        "trap": "रविवार को रात 8:30 बजे वाला नियम लागू नहीं होता।",
    },
    (3, 3): {
        "hook": "रविवार को रात्रि डाकघर में ये काम भूलकर भी मत माँगना!",
        "question": "रविवार और अवकाश के दिन रात्रि डाकघर में क्या नहीं होता?",
        "a": "मनीऑर्डर व बचत बैंक", "b": "डाक टिकट बिक्री", "c": "स्पीड पोस्ट बुकिंग", "d": "पंजीकृत डाक",
        "correct": "A",
        "hint": "छुट्टी के दिन पैसों वाला काम बंद रहता है।",
        "fact": "रविवार और अवकाश के दिन मनीऑर्डर भुगतान और बचत बैंक कार्य नहीं होता।",
        "trap": "सीमित बुकिंग चालू रहती है, लेकिन वित्तीय निकासी बंद होती है।",
    },
    (4, 1): {
        "hook": "चलता-फिरता डाकघर! आखिर इसमें होता क्या है?",
        "question": "मोबाइल डाकघर में मुख्य रूप से कौन-सा कार्य होता है?",
        "a": "डाक व पार्सल बुकिंग", "b": "मनीऑर्डर भुगतान", "c": "बचत बैंक खाता", "d": "डाक जीवन बीमा",
        "correct": "A",
        "hint": "नाम में ही डाक है, पैसों का काम नहीं।",
        "fact": "मोबाइल डाकघर शाम तक सामान्य डाक और पार्सल बुकिंग की सुविधा देते हैं।",
        "trap": "मोबाइल वैन में बैंकिंग और वित्तीय सुविधाएं उपलब्ध नहीं होती हैं।",
    },
    (4, 2): {
        "hook": "मोबाइल डाकघर में ये काम करवाया, तो सीधा नियम टूटेगा!",
        "question": "मोबाइल डाकघर में किस कार्य की अनुमति नहीं होती है?",
        "a": "मनीऑर्डर व बचत बैंक", "b": "साधारण डाक बुकिंग", "c": "पार्सल बुकिंग", "d": "लेट फीस डाक",
        "correct": "A",
        "hint": "सोचिए, चलती वैन में पैसों का लेन-देन कितना सुरक्षित होगा?",
        "fact": "मोबाइल डाकघर में मनीऑर्डर, बचत बैंक और बीमा कार्य प्रतिबंधित होते हैं।",
        "trap": "केवल डाक और पार्सल बुकिंग की ही अनुमति होती है।",
    },
    (5, 1): {
        "hook": "डाक टिकट कब तक मिलते हैं? बचत बैंक के टाइम से कन्फ्यूज़ मत होना!",
        "question": "डाक टिकटों की बिक्री काउंटर पर कब तक उपलब्ध रहती है?",
        "a": "पूरे कार्य समय तक", "b": "केवल 2 घंटे", "c": "दोपहर 12 बजे तक", "d": "शाम 4 बजे तक",
        "correct": "A",
        "hint": "बचत बैंक जल्दी बंद होता है, टिकट काउंटर नहीं।",
        "fact": "सामान्य टिकट बिक्री और डाक बुकिंग पूरे कार्य समय तक खुली रहती है।",
        "trap": "बचत बैंक काउंटर जल्दी बंद होता है, लेकिन टिकट पूरे समय मिलते हैं।",
    },
    (5, 2): {
        "hook": "काउंटर बंद हो गया, फिर भी डाक बुक हो सकती है! कैसे?",
        "question": "सार्वजनिक काउंटर बंद होने के बाद डाक कैसे स्वीकार की जाती है?",
        "a": "लेट फीस भुगतान करके", "b": "लिखित आवेदन से", "c": "दोगुने टिकट लगाकर", "d": "अगले कार्यदिवस पर",
        "correct": "A",
        "hint": "देर से आए हैं, तो कुछ एक्स्ट्रा देना पड़ेगा।",
        "fact": "सार्वजनिक काउंटर बंद होने के बाद निर्धारित लेट फीस देकर डाक बुक होती है।",
        "trap": "बिना लेट फीस के काउंटर समय के बाद डाक स्वीकार नहीं होती।",
    },
    (5, 3): {
        "hook": "शनिवार को भी डाकघर का टाइम वही रहता है? ज़रा रुकिए!",
        "question": "शनिवार को सामान्य डाक लेन-देन के समय में क्या लागू होता है?",
        "a": "विभागीय समयावधि कटौती", "b": "सामान्य दिनों जैसा समय", "c": "पूर्ण अवकाश", "d": "रविवार के नियम",
        "correct": "A",
        "hint": "शनिवार को पूरा समय नहीं मिलता।",
        "fact": "शनिवार को सामान्य डाक लेन-देन के समय में निर्धारित कटौती लागू होती है।",
        "trap": "शनिवार को सामान्य कार्यदिवसों जितना पूरा समय नहीं मिलता।",
    },
    (22, 1): {
        "hook": "पता बदल गया, तो चिट्ठी आगे भेजने के पैसे लगेंगे?",
        "question": "प्रथम श्रेणी की अंतरदेशीय डाक का पुनः प्रेषण शुल्क कितना है?",
        "a": "पूर्णतः निःशुल्क", "b": "आधा डाक प्रभार", "c": "पूरा डाक प्रभार", "d": "दस रुपये",
        "correct": "A",
        "hint": "प्रथम श्रेणी डाक को यहाँ खास राहत मिलती है।",
        "fact": "प्रथम श्रेणी की अंतरदेशीय डाक का पुनः प्रेषण पूरी तरह निःशुल्क होता है।",
        "trap": "पार्सल पर प्रभार लगता है, लेकिन प्रथम श्रेणी डाक निःशुल्क होती है।",
    },
    (22, 2): {
        "hook": "पार्सल दूसरे इलाके में भेजना है, कितना चार्ज लगेगा?",
        "question": "वितरण क्षेत्र से बाहर पार्सल पुनः प्रेषित करने पर कितना प्रभार है?",
        "a": "आधा डाक प्रभार", "b": "पूर्ण डाक प्रभार", "c": "निःशुल्क", "d": "दोगुना प्रभार",
        "correct": "A",
        "hint": "न पूरा चार्ज, न मुफ्त, बीच का रास्ता।",
        "fact": "वितरण क्षेत्र से बाहर भेजे जाने पर आधा डाक प्रभार देय होता है।",
        "trap": "उसी वितरण क्षेत्र में निःशुल्क होता है, बाहर भेजने पर आधा प्रभार लगता है।",
    },
    (22, 3): {
        "hook": "पार्सल एक बार खोल दिया, अब आगे भेजना है? बड़ा ट्रैप!",
        "question": "एक बार खुले हुए पार्सल को पुनः प्रेषित करने की क्या शर्त है?",
        "a": "नया डाकभार देना होगा", "b": "आधा डाकभार लगेगा", "c": "निःशुल्क भेजा जाएगा", "d": "विशेष छूट मिलेगी",
        "correct": "A",
        "hint": "खुला पार्सल मतलब नई बुकिंग जैसा मामला।",
        "fact": "खोला गया पार्सल नए डाकभार के बिना पुनः प्रेषित नहीं किया जा सकता।",
        "trap": "बिना खुले पार्सल पर आधा प्रभार, लेकिन खुले पर पूरा नया चार्ज लगता है।",
    },
    (23, 1): {
        "hook": "पता बदलने का लिखित निर्देश कितने दिन चलता है? यहीं नंबर कटते हैं!",
        "question": "लिखित पुनः प्रेषण अनुदेश (Redirection) की वैधता अवधि क्या है?",
        "a": "अधिकतम 3 माह", "b": "6 माह", "c": "1 वर्ष", "d": "1 माह",
        "correct": "A",
        "hint": "एक तिमाही याद रखिए।",
        "fact": "लिखित पुनः प्रेषण अनुदेश की वैधता अवधि अधिकतम 3 माह तक होती है।",
        "trap": "3 महीने पूरे होने के बाद नया लिखित निर्देश देना आवश्यक होता है।",
    },
    (23, 2): {
        "hook": "विदेश जाने वाले की डाक का क्या होगा? सामान्य नियम नहीं चलेगा!",
        "question": "विदेश जाने वाले पतेदारों के डाक पुनः प्रेषण पर क्या लागू होता है?",
        "a": "विशेष डाक नियम", "b": "सामान्य घरेलू नियम", "c": "कोई नियम नहीं", "d": "निःशुल्क विदेशी डाक",
        "correct": "A",
        "hint": "विदेश का मामला मतलब अलग व्यवस्था।",
        "fact": "विदेश जाने वाले पतेदारों के लिए विशेष डाक नियम लागू होते हैं।",
        "trap": "अंतर्देशीय साधारण नियम विदेश जाने वाली डाक पर सीधे लागू नहीं होते।",
    },
}


# ==================== TEXT HELPERS ====================

_ALLOWED = re.compile(r"[^\u0900-\u097F\u0020-\u007E\u00A0-\u00FF\u2010-\u2027\u20B9]")


def clean_text(text):
    """Emoji / unsupported glyph hata deta hai (purane video me yahi box ban rahe the)."""
    if not text:
        return ""
    text = re.sub(r"[*_`#]+", "", str(text))
    text = text.replace("…", "...").replace("—", "-").replace("–", "-")
    text = _ALLOWED.sub("", text)
    return " ".join(text.split()).strip()


# ==================== FONTS ====================

_font_path = None
_raqm_warned = False


def resolve_font():
    global _font_path
    if _font_path:
        return _font_path

    if os.path.exists(FONT_FILE) and os.path.getsize(FONT_FILE) > 50000:
        _font_path = FONT_FILE
        return _font_path

    if not DRY_RUN:
        for url in FONT_URLS:
            try:
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                if len(r.content) > 50000:
                    Path(FONT_FILE).write_bytes(r.content)
                    _font_path = FONT_FILE
                    return _font_path
            except Exception:
                continue

    for path in FALLBACK_FONTS:
        if os.path.exists(path) and os.path.getsize(path) > 50000:
            print("Local font use ho raha hai:", path)
            _font_path = path
            return _font_path

    raise RuntimeError("Koi Devanagari font nahi mila. Mukta-Bold.ttf script ke folder me rakhiye.")


@lru_cache(maxsize=256)
def get_font(size):
    global _raqm_warned
    path = resolve_font()
    if features.check("raqm"):
        return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)
    if not _raqm_warned:
        print("WARNING: libraqm nahi mila - Hindi matra galat dikh sakti hai. `pip install --upgrade pillow` karein.")
        _raqm_warned = True
    return ImageFont.truetype(path, size)


def text_w(text, font):
    return font.getlength(text)


def wrap_words(text, font, max_w):
    words = text.split()
    lines, cur = [], []
    for w in words:
        trial = " ".join(cur + [w])
        if cur and text_w(trial, font) > max_w:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def fit_lines(text, max_w, max_lines, size, min_size=26):
    s = size
    while s >= min_size:
        f = get_font(s)
        lines = wrap_words(text, f, max_w)
        if len(lines) <= max_lines and all(text_w(" ".join(l), f) <= max_w for l in lines):
            return f, s, lines
        s -= 2
    f = get_font(min_size)
    return f, min_size, wrap_words(text, f, max_w)


# ==================== EASING / MATH ====================

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(t, start, dur):
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    return clamp((t - start) / dur)


def ease_out_cubic(x):
    return 1 - (1 - x) ** 3


def ease_out_back(x, s=1.70158):
    x = x - 1
    return x * x * ((s + 1) * x + s) + 1


def with_alpha(color, a):
    return (color[0], color[1], color[2], int(255 * clamp(a)))


def mix(c1, c2, k):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * k) for i in range(3))


# ==================== SPRITES ====================

def place(canvas, sprite, cx, cy, scale=1.0, alpha=1.0, angle=0.0):
    if sprite is None or alpha <= 0.01 or scale <= 0.01:
        return
    sp = sprite
    if abs(scale - 1.0) > 0.005:
        nw, nh = max(1, int(sp.width * scale)), max(1, int(sp.height * scale))
        sp = sp.resize((nw, nh), Image.BILINEAR)
    if abs(angle) > 0.05:
        sp = sp.rotate(angle, resample=Image.BICUBIC, expand=True)
    if alpha < 0.99:
        sp = sp.copy()
        a = sp.getchannel("A").point(lambda v: int(v * alpha))
        sp.putalpha(a)
    canvas.paste(sp, (int(cx - sp.width / 2), int(cy - sp.height / 2)), sp)


@lru_cache(maxsize=64)
def glow_sprite(radius, color, strength=110):
    size = radius * 2
    y, x = np.ogrid[:size, :size]
    d = np.sqrt((x - radius) ** 2 + (y - radius) ** 2) / radius
    a = np.clip(1 - d, 0, 1) ** 2 * strength
    arr = np.zeros((size, size, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = color
    arr[..., 3] = np.clip(a, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


@lru_cache(maxsize=64)
def card_sprite(w, h, fill=CARD_2, outline=(42, 64, 88), width=4, radius=32, shadow=True):
    pad = 30 if shadow else 0
    im = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if shadow:
        for i in range(6, 0, -1):
            d.rounded_rectangle((pad - i * 3, pad - i * 3 + 10, pad + w + i * 3, pad + h + i * 3 + 10),
                                radius=radius + i * 3, fill=(0, 0, 0, 12))
    d.rounded_rectangle((pad, pad, pad + w, pad + h), radius=radius, fill=fill + (255,),
                        outline=outline + (255,), width=width)
    # soft top-light gradient (glass depth)
    arr = np.array(im).astype(np.float32)
    ramp = np.clip(1 - (np.arange(im.height) - pad) / max(1, h * 0.6), 0, 1)[:, None] * 16
    inside = arr[..., 3] > 250
    for c in range(3):
        arr[..., c] = np.where(inside, np.clip(arr[..., c] + ramp, 0, 255), arr[..., c])
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


@lru_cache(maxsize=128)
def option_sprite(letter, text, w, h, state):
    styles = {
        "normal": (CARD_2, (42, 64, 88), 4, CYAN, WHITE),
        "active": ((24, 52, 82), CYAN, 6, CYAN, WHITE),
        "wrong": ((42, 20, 28), RED, 5, RED, MUTED),
        "correct": ((14, 52, 34), GREEN, 7, GREEN, WHITE),
    }
    fill, outline, width, badge, tcol = styles[state]
    im = card_sprite(w, h, fill, outline, width, 30).copy()
    d = ImageDraw.Draw(im)
    pad = 30
    bx, by, br = pad + 70, pad + h // 2, 40
    d.ellipse((bx - br, by - br, bx + br, by + br), fill=badge + (255,))
    d.text((bx, by), letter, font=get_font(46), fill=(8, 16, 30, 255), anchor="mm")

    f, s, lines = fit_lines(text, w - 170, 2, 46, 30)
    lh = int(s * 1.32)
    y0 = by - (len(lines) - 1) * lh / 2
    for i, ln in enumerate(lines):
        d.text((pad + 135, y0 + i * lh), " ".join(ln), font=f, fill=tcol + (255,), anchor="lm")

    if state == "wrong":
        tw = max(text_w(" ".join(l), f) for l in lines)
        d.line((pad + 130, by, pad + 140 + tw, by), fill=RED + (230,), width=6)
    return im


@lru_cache(maxsize=8)
def x_mark_sprite(size=120):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=RED + (255,))
    m = size * 0.3
    d.line((m, m, size - m, size - m), fill=WHITE + (255,), width=size // 9)
    d.line((size - m, m, m, size - m), fill=WHITE + (255,), width=size // 9)
    return im


@lru_cache(maxsize=8)
def check_sprite(size=140):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=GREEN + (255,))
    s = size
    d.line((s * 0.27, s * 0.52, s * 0.43, s * 0.68), fill=WHITE + (255,), width=s // 10)
    d.line((s * 0.43, s * 0.68, s * 0.74, s * 0.34), fill=WHITE + (255,), width=s // 10)
    return im


@lru_cache(maxsize=4)
def envelope_sprite(w=280):
    h = int(w * 0.68)
    im = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    o = 10
    d.rounded_rectangle((o, o, o + w, o + h), radius=18, fill=(245, 236, 220, 255),
                        outline=(200, 60, 60, 255), width=6)
    d.line((o + 6, o + 8, o + w / 2, o + h * 0.58), fill=(200, 60, 60, 255), width=7)
    d.line((o + w - 6, o + 8, o + w / 2, o + h * 0.58), fill=(200, 60, 60, 255), width=7)
    cx, cy, r = o + w / 2, o + h * 0.58, w * 0.12
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(200, 30, 45, 255))
    d.text((cx, cy), "?", font=get_font(int(r * 1.5)), fill=WHITE + (255,), anchor="mm")
    return im


@lru_cache(maxsize=4)
def stamp_sprite(text="EXAM TRAP"):
    f = get_font(80)
    tw = int(text_w(text, f))
    w, h = tw + 100, 160
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((6, 6, w - 6, h - 6), radius=22, outline=RED + (255,), width=10, fill=(60, 8, 14, 215))
    d.rounded_rectangle((22, 22, w - 22, h - 22), radius=14, outline=RED + (170,), width=3)
    d.text((w / 2, h / 2 + 2), text, font=f, fill=RED + (255,), anchor="mm")
    # grunge ink texture
    rng = random.Random(7)
    arr = np.array(im)
    for _ in range(320):
        x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
        r = rng.randint(1, 3)
        arr[max(0, y - r):y + r, max(0, x - r):x + r, 3] = (arr[max(0, y - r):y + r, max(0, x - r):x + r, 3] * 0.25).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


@lru_cache(maxsize=4)
def bulb_sprite(size=240):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy, r = size / 2, size * 0.40, size * 0.26
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=YELLOW + (255,))
    d.rectangle((cx - r * 0.45, cy + r * 0.7, cx + r * 0.45, cy + r * 1.25), fill=YELLOW + (255,))
    for i in range(3):
        yy = cy + r * 1.3 + i * 13
        d.rounded_rectangle((cx - r * 0.5, yy, cx + r * 0.5, yy + 9), radius=4, fill=(150, 160, 175, 255))
    d.line((cx - r * 0.25, cy + r * 0.1, cx, cy + r * 0.5, cx + r * 0.25, cy + r * 0.1),
           fill=(255, 250, 220, 255), width=5)
    return im


@lru_cache(maxsize=4)
def lock_sprite(size=120):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = max(6, size // 10)
    d.arc((size * 0.25, size * 0.05, size * 0.75, size * 0.6), 180, 360, fill=YELLOW + (255,), width=lw)
    d.line((size * 0.25, size * 0.32, size * 0.25, size * 0.5), fill=YELLOW + (255,), width=lw)
    d.line((size * 0.75, size * 0.32, size * 0.75, size * 0.5), fill=YELLOW + (255,), width=lw)
    d.rounded_rectangle((size * 0.12, size * 0.45, size * 0.88, size * 0.95), radius=size // 9, fill=YELLOW + (255,))
    d.ellipse((size * 0.44, size * 0.6, size * 0.56, size * 0.72), fill=(40, 30, 0, 255))
    return im


@lru_cache(maxsize=4)
def rays_sprite(size=1000):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = size / 2
    for i in range(16):
        a0 = math.radians(i * 22.5)
        a1 = math.radians(i * 22.5 + 9)
        d.polygon([(c, c), (c + math.cos(a0) * c, c + math.sin(a0) * c),
                   (c + math.cos(a1) * c, c + math.sin(a1) * c)], fill=GREEN + (60,))
    mask = np.array(glow_sprite(size // 2, (255, 255, 255), 255).getchannel("A"), dtype=np.float32)
    a = np.array(im.getchannel("A"), dtype=np.float32) * mask / 255.0
    im.putalpha(Image.fromarray(a.astype(np.uint8)))
    return im


@lru_cache(maxsize=32)
def pill_sprite(text, size, fg, bg, outline):
    f = get_font(size)
    w = int(text_w(text, f)) + size * 2
    h = int(size * 1.9)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((2, 2, w - 2, h - 2), radius=h // 2, fill=bg + (235,), outline=outline + (255,), width=3)
    d.text((w / 2, h / 2), text, font=f, fill=fg + (255,), anchor="mm")
    return im


# ==================== BACKGROUND (texture + depth) ====================

@lru_cache(maxsize=8)
def background(mood):
    bw, bh = W + 120, H + 120
    yy, xx = np.mgrid[0:bh, 0:bw].astype(np.float32)
    ty = yy / bh
    base = np.zeros((bh, bw, 3), dtype=np.float32)
    for i in range(3):
        base[..., i] = BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * ty

    col = MOODS[mood]
    for (gx, gy, gr, k) in [(0.2, 0.18, 0.55, 0.55), (0.9, 0.75, 0.6, 0.35)]:
        d = np.sqrt((xx - gx * bw) ** 2 + (yy - gy * bh) ** 2) / (gr * bw)
        g = np.clip(1 - d, 0, 1) ** 2 * k
        for i in range(3):
            base[..., i] += col[i] * g * 0.55

    # subtle exam-paper grid
    grid = ((xx % 60 < 1.5) | (yy % 60 < 1.5)).astype(np.float32) * 5
    base += grid[..., None]

    # vignette
    d = np.sqrt(((xx - bw / 2) / (bw / 2)) ** 2 + ((yy - bh / 2) / (bh / 2)) ** 2)
    base *= np.clip(1.15 - 0.45 * d, 0.45, 1)[..., None]

    # film grain
    rng = np.random.default_rng(3)
    base += rng.normal(0, 4.0, (bh, bw, 1))
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")


def bg_frame(mood, gt):
    im = background(mood)
    ox = int(60 + 40 * math.sin(gt * 0.45))
    oy = int(60 + 40 * math.cos(gt * 0.33))
    return im.crop((ox, oy, ox + W, oy + H))


# ==================== KINETIC TYPOGRAPHY ====================

def word_thresholds(words):
    weights = [len(w) + (3 if re.search(r"[,.!?।]$", w) else 0) + 1 for w in words]
    total = float(sum(weights))
    out, acc = [], 0.0
    for w in weights:
        out.append(acc / total)
        acc += w
    return out


def text_block_h(text, max_w, size, max_lines=4, min_size=30, line_h=1.34):
    _, s, lines = fit_lines(text, max_w, max_lines, size, min_size)
    return int(s * line_h) * len(lines)


def draw_kinetic(canvas, text, cx, top, max_w, size, p, max_lines=4, color=WHITE,
                 hl_words=(), hl_color=YELLOW, karaoke=True, ghost=0.0, min_size=30, line_h=1.34,
                 center_y=None):
    """Voice ke saath word-by-word text. p = 0..1 speech progress. Returns bottom y."""
    font, s, lines = fit_lines(text, max_w, max_lines, size, min_size)
    lh = int(s * line_h)
    if center_y is not None:
        top = center_y - lh * len(lines) / 2
    all_words = [w for ln in lines for w in ln]
    if not all_words:
        return top
    th = word_thresholds(all_words)
    n = len(all_words)
    space = text_w(" ", font)

    layer = Image.new("RGBA", (int(max_w) + 80, lh * len(lines) + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    hl = set(hl_words)

    idx = 0
    for li, ln in enumerate(lines):
        line_w = sum(text_w(w, font) for w in ln) + space * (len(ln) - 1)
        x = (layer.width - line_w) / 2
        y = 20 + li * lh + lh / 2
        for w in ln:
            start = th[idx]
            nxt = th[idx + 1] if idx + 1 < n else 1.0
            a = clamp((p - start) / 0.06 + (0.4 if idx == 0 else 0.0))
            e = ease_out_cubic(a)
            if a <= 0:
                alpha, dy = ghost, 0
            else:
                alpha, dy = max(ghost, e), (1 - e) * 22
            key = re.sub(r"[,.!?।:()]", "", w)
            col = color
            if key in hl and a > 0:
                col = hl_color
            if karaoke and start <= p < nxt and p < 0.999:
                col = YELLOW
            if alpha > 0.01:
                d.text((x, y + dy), w, font=font, fill=with_alpha(col, alpha), anchor="lm")
            x += text_w(w, font) + space
            idx += 1

    canvas.paste(layer, (int(cx - layer.width / 2), int(top - 20)), layer)
    return top + lh * len(lines)


# ==================== SCRIPT GENERATION ====================

def extract_field(raw, name, next_names):
    next_part = "|".join(re.escape(x) for x in next_names)
    if next_part:
        pattern = rf"(?:^|\n)\s*{re.escape(name)}\s*:\s*(.*?)(?=(?:\n\s*(?:{next_part})\s*:)|$)"
    else:
        pattern = rf"(?:^|\n)\s*{re.escape(name)}\s*:\s*(.*)$"
    m = re.search(pattern, raw, re.I | re.S)
    return clean_text(m.group(1)) if m else ""


def fallback_script(clause_no, part_no, focus, title):
    if (clause_no, part_no) in FALLBACK_SCRIPTS:
        data = dict(FALLBACK_SCRIPTS[(clause_no, part_no)])
        data["title"] = title
        return data
    return {
        "title": title,
        "hook": f"{title} का ये नियम परीक्षा में सीधा पूछा जाता है!",
        "question": f"{title} के अनुसार कौन-सा कथन सत्य है?",
        "a": focus[:40], "b": "कोई विशेष छूट नहीं", "c": "अधीक्षक का अनुमोदन", "d": "इनमें से कोई नहीं",
        "correct": "A",
        "hint": "नियम के शब्दों पर ध्यान दीजिए।",
        "fact": focus,
        "trap": "परीक्षा में शब्दों और नियमों को ध्यान से पढ़ें।",
    }


def generate_script(state):
    clause_no, part_no = state["clause_no"], state["current_part"]
    info = POSTAL_CLAUSE_CATALOG[clause_no]
    title = info["name"]
    focus = info.get(f"part_{part_no}_focus", info["part_1_focus"])

    if not GROQ_API_KEY or DRY_RUN:
        return fallback_script(clause_no, part_no, focus, title)

    prompt = f"""
You write viral-yet-accurate Hindi MCQ reels for India Post departmental exams (GDS to MTS/PA/IP).

TOPIC: {title}
PART: {part_no}/{info["total_parts"]}
OFFICIAL VERIFIED FACT (only source of truth):
{focus}

Rules:
1. HOOK: conversational spoken Hindi, max 12 words, a challenge or a stake. NO fake percentages, NO emojis.
2. QUESTION: clear exam-style Hindi question, max 14 words.
3. A, B, C, D: 2-5 words each, all plausible. Exactly one matches the fact.
4. CORRECT: single letter.
5. HINT: one-line clue (max 12 words) that points toward the answer WITHOUT stating it.
6. FACT: one sentence, max 18 words.
7. TRAP: the common confusion, max 16 words.
8. No meta text. No emojis. Devanagari Hindi only (English acronyms allowed).

Format exactly:
HOOK: ...
QUESTION: ...
A: ...
B: ...
C: ...
D: ...
CORRECT: ...
HINT: ...
FACT: ...
TRAP: ...
"""
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile",
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.3, "max_tokens": 500},
            timeout=25,
        )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]
        data = {
            "title": title,
            "hook": extract_field(raw, "HOOK", ["QUESTION"]),
            "question": extract_field(raw, "QUESTION", ["A"]),
            "a": extract_field(raw, "A", ["B"]),
            "b": extract_field(raw, "B", ["C"]),
            "c": extract_field(raw, "C", ["D"]),
            "d": extract_field(raw, "D", ["CORRECT"]),
            "correct": extract_field(raw, "CORRECT", ["HINT"]).upper()[:1],
            "hint": extract_field(raw, "HINT", ["FACT"]),
            "fact": extract_field(raw, "FACT", ["TRAP"]),
            "trap": extract_field(raw, "TRAP", []),
        }
        if data["correct"] not in {"A", "B", "C", "D"}:
            raise ValueError("Invalid CORRECT")
        if not all(data[k] for k in ["hook", "question", "a", "b", "c", "d", "hint", "fact", "trap"]):
            raise ValueError("Incomplete script")
        if len(data["hook"]) > 90 or any(len(data[k]) > 45 for k in "abcd"):
            raise ValueError("Text too long")
        return data
    except Exception as exc:
        print("Curated fallback script use ho rahi hai:", exc)
        return fallback_script(clause_no, part_no, focus, title)


def prepare_data(data, clause_no, part_no):
    """Clean + options shuffle (pehle har baar A sahi hota tha - viewer pattern pakad leta tha)."""
    data = {k: clean_text(v) if isinstance(v, str) else v for k, v in data.items()}
    correct_key = (data.get("correct") or "A").upper()
    if correct_key not in ("A", "B", "C", "D"):
        correct_key = "A"
    rng = random.Random(clause_no * 1000 + part_no * 37 + 11)
    right = (data[correct_key.lower()], True)
    wrongs = [(data[k.lower()], False) for k in "ABCD" if k != correct_key]
    rng.shuffle(wrongs)
    pos = (clause_no * 7 + part_no * 3) % 4          # sahi answer har reel me alag position pe
    items = wrongs[:pos] + [right] + wrongs[pos:]
    letters = "ABCD"
    data["options"] = [(letters[i], txt) for i, (txt, _) in enumerate(items)]
    ci = next(i for i, (_, ok) in enumerate(items) if ok)
    data["correct"] = letters[ci]
    data["correct_text"] = items[ci][0]
    for i, (txt, _) in enumerate(items):
        data[letters[i].lower()] = txt
    wrong = [l for l, _ in data["options"] if l != data["correct"]]
    rng.shuffle(wrong)
    data["elim_order"] = wrong
    data["clause_no"], data["part_no"] = clause_no, part_no
    data["total_parts"] = POSTAL_CLAUSE_CATALOG[clause_no]["total_parts"]
    data["hl_words"] = [re.sub(r"[,.!?।:()]", "", w) for w in data["correct_text"].split() if len(w) > 1]
    data["next_title"] = next_topic_title(clause_no, part_no)
    return data


# ==================== STATE ====================

def load_state():
    default = {"clause_no": 23, "current_part": 1}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                default.update(saved)
        except Exception:
            pass
    try:
        default["clause_no"] = int(default["clause_no"])
        default["current_part"] = int(default["current_part"])
    except (TypeError, ValueError):
        default = {"clause_no": 23, "current_part": 1}
    if default["clause_no"] not in POSTAL_CLAUSE_CATALOG:
        default = {"clause_no": 23, "current_part": 1}
    total = POSTAL_CLAUSE_CATALOG[default["clause_no"]]["total_parts"]
    if not (1 <= default["current_part"] <= total):
        default["current_part"] = 1
    return default


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def next_position(clause, part):
    info = POSTAL_CLAUSE_CATALOG[clause]
    if part < info["total_parts"]:
        return clause, part + 1
    keys = sorted(POSTAL_CLAUSE_CATALOG)
    return keys[(keys.index(clause) + 1) % len(keys)], 1


def next_topic_title(clause, part):
    c, _ = next_position(clause, part)
    return POSTAL_CLAUSE_CATALOG[c]["name"]


def advance_state(state):
    state["clause_no"], state["current_part"] = next_position(state["clause_no"], state["current_part"])
    save_state(state)


# ==================== SCENE SCRIPT (voice segments) ====================

def build_scene_specs(data):
    return [
        {"name": "hook", "mood": "red", "tail": 0.15, "min": 2.2,
         "segs": [("hook", data["hook"])]},
        {"name": "question", "mood": "blue", "tail": 1.1, "min": 3.2,
         "segs": [("q", data["question"])]},
        {"name": "countdown", "mood": "purple", "tail": 0.15, "min": 3.45,
         "segs": [("lock", "कमेंट में जवाब लॉक कीजिए, तीन सेकंड!")]},
        {"name": "hint", "mood": "yellow", "tail": 0.25, "min": 2.5,
         "segs": [("pre", "एक हिंट सुनिए।"), ("hint", data["hint"])]},
        {"name": "eliminate", "mood": "red", "tail": 0.35, "min": 3.5,
         "segs": [("pre", "अब गलत हटाते हैं।"), ("x1", "ये नहीं।"), ("x2", "ये भी नहीं।"),
                  ("left", "बचे दो, सही कौन?"), ("x3", "ये भी नहीं!")]},
        {"name": "reveal", "mood": "green", "tail": 0.4, "min": 2.4,
         "segs": [("rev", f"सही जवाब है, {data['correct']}, {data['correct_text']}!")]},
        {"name": "rule", "mood": "blue", "tail": 0.3, "min": 0,
         "segs": [("fact", data["fact"]),
                  ("trapx", "और ट्रैप ये है,"), ("trap", data["trap"])]},
        {"name": "cta", "mood": "purple", "tail": 0.6, "min": 3.0,
         "segs": [("cta", "सही था? कमेंट में लिखिए, पक्का! अगला सवाल और भी मुश्किल है!")]},
    ]


def seg_weight(text):
    return len(text.replace(" ", "")) + 4 * len(re.findall(r"[,.!?।]", text)) + 2


def compute_marks(segs, voice_dur):
    total = sum(seg_weight(t) for _, t in segs)
    marks, acc = {}, 0.0
    for key, text in segs:
        w = seg_weight(text)
        marks[key] = (voice_dur * acc / total, voice_dur * (acc + w) / total)
        acc += w
    return marks


# ==================== AUDIO: TTS ====================

async def tts_save(text, path):
    import edge_tts
    last = None
    for attempt in range(4):
        try:
            com = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate=VOICE_RATE, pitch=VOICE_PITCH)
            await com.save(path)
            if os.path.exists(path) and os.path.getsize(path) > 1000:
                return
        except Exception as exc:
            last = exc
        await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"TTS fail: {last}")


def decode_voice(path):
    cmd = [
        "ffmpeg", "-v", "error", "-i", path,
        "-af", ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                "silenceremove=start_periods=1:start_threshold=-45dB,areverse"),
        "-ac", "1", "-ar", str(SR), "-f", "s16le", "-",
    ]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if len(arr) < SR * 0.2:
        raise RuntimeError(f"Voice file khali hai: {path}")
    return arr


def make_voices(specs):
    voices = []
    for i, sp in enumerate(specs):
        text = " ".join(t for _, t in sp["segs"])
        if DRY_RUN:
            est = max(0.8, seg_weight(text) * 0.055)
            voices.append(np.zeros(int(est * SR), dtype=np.float32))
            continue
        path = f"_voice_{i}.mp3"
        asyncio.run(tts_save(text, path))
        voices.append(decode_voice(path))
        os.remove(path)
    return voices


# ==================== AUDIO: SFX (synthesized, no downloads) ====================

def _t(d):
    return np.arange(int(d * SR)) / SR


def sfx_whoosh(d=0.35, amp=0.35):
    rng = np.random.default_rng(1)
    n = rng.normal(0, 1, int(d * SR)).astype(np.float32)
    out = np.zeros_like(n)
    y = 0.0
    ln = len(n)
    for i in range(ln):
        k = 0.02 + 0.25 * math.sin(math.pi * i / ln)
        y += k * (n[i] - y)
        out[i] = y
    env = np.sin(np.linspace(0, math.pi, ln)) ** 2
    return out * env * amp * 2.2


def sfx_pop(amp=0.4):
    t = _t(0.09)
    f = 900 - 5000 * t
    return np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 40) * amp


def sfx_tick(amp=0.35):
    t = _t(0.04)
    return np.sin(2 * math.pi * 2200 * t) * np.exp(-t * 120) * amp


def sfx_buzz(amp=0.3):
    t = _t(0.28)
    sq = np.sign(np.sin(2 * math.pi * 110 * t)) * 0.6 + np.sin(2 * math.pi * 55 * t) * 0.4
    return sq * np.exp(-t * 6) * amp


def sfx_ding(amp=0.4):
    t = _t(1.1)
    s = (np.sin(2 * math.pi * 1318.5 * t) + 0.6 * np.sin(2 * math.pi * 1975.5 * t)
         + 0.3 * np.sin(2 * math.pi * 2637 * t))
    return s * np.exp(-t * 4.5) * amp / 1.9


def sfx_thud(amp=0.7):
    t = _t(0.45)
    f = 90 - 60 * t
    s = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    rng = np.random.default_rng(2)
    s[:600] += rng.normal(0, 0.5, 600) * np.exp(-np.arange(600) / 120)
    return s * amp


def sfx_riser(d=1.0, amp=0.18):
    t = _t(d)
    f = 200 + 700 * (t / d) ** 2
    rng = np.random.default_rng(4)
    s = np.sin(2 * math.pi * np.cumsum(f) / SR) * 0.6 + rng.normal(0, 0.25, len(t))
    return s * (t / d) ** 2 * amp


def sfx_heartbeat(amp=0.45):
    b = sfx_thud(amp)
    out = np.zeros(int(0.5 * SR), dtype=np.float64)
    n = min(len(b), len(out))
    out[:n] += b[:n]
    s = int(0.18 * SR)
    n2 = min(len(b), len(out) - s)
    out[s:s + n2] += b[:n2] * 0.7
    return out


def music_bed(total):
    """Halka tension pad + soft pulse (copyright-free, code se bana)."""
    t = np.arange(int(total * SR)) / SR
    chord = [110.0, 164.81, 220.0, 261.63]
    pad = sum(np.sin(2 * math.pi * f * t + i) for i, f in enumerate(chord)) / len(chord)
    lfo = 0.6 + 0.4 * np.sin(2 * math.pi * 0.25 * t)
    pulse = np.sin(2 * math.pi * 55 * t) * np.exp(-((t % 0.5) * 14))
    return (pad * lfo * 0.05 + pulse * 0.05).astype(np.float32)


def add_at(buf, clip, t_sec, gain=1.0):
    s = int(t_sec * SR)
    if s >= len(buf) or s < 0:
        return
    e = min(len(buf), s + len(clip))
    buf[s:e] += (clip[:e - s] * gain).astype(np.float32)


def build_audio(voices, timeline, total, out_path):
    n = int(total * SR) + SR
    buf = np.zeros(n, dtype=np.float32)
    voice_track = np.zeros(n, dtype=np.float32)
    for sc, v in zip(timeline, voices):
        add_at(voice_track, v, sc["start"])

    # ducking: voice ke time music neeche
    env = np.abs(voice_track)
    win = int(0.15 * SR)
    env = np.convolve(env, np.ones(win, dtype=np.float32) / win, mode="same")
    duck = 1.0 - np.clip(env * 6, 0, 0.6)
    bed = music_bed(n / SR)
    m = min(len(bed), n)
    buf[:m] += bed[:m] * duck[:m]

    whoosh = sfx_whoosh()
    for sc in timeline:
        s, mk, name = sc["start"], sc["marks"], sc["name"]
        if sc["index"] > 0:
            add_at(buf, whoosh, max(0.0, s - 0.12), 0.8)
        if name == "hook":
            add_at(buf, sfx_pop(0.5), s + 0.02)
            add_at(buf, sfx_thud(0.9), s + sc["stamp_t"])
        elif name == "question":
            for ot in sc["opt_t"]:
                add_at(buf, sfx_pop(0.35), s + ot)
        elif name == "countdown":
            for k in range(COUNTDOWN_SECONDS):
                add_at(buf, sfx_tick(0.5), s + k)
                add_at(buf, sfx_heartbeat(0.5), s + k)
            add_at(buf, sfx_pop(0.45), s + COUNTDOWN_SECONDS)
        elif name == "hint":
            add_at(buf, sfx_ding(0.18), s + 0.05)
        elif name == "eliminate":
            for k in ("x1", "x2", "x3"):
                add_at(buf, sfx_buzz(0.35), s + mk[k][0])
            add_at(buf, sfx_riser(max(0.3, mk["x3"][0] - mk["left"][0])), s + mk["left"][0])
        elif name == "reveal":
            add_at(buf, sfx_ding(0.5), s)
            add_at(buf, sfx_thud(0.5), s)
        elif name == "rule":
            add_at(buf, sfx_pop(0.3), s + mk["fact"][0])
            add_at(buf, sfx_buzz(0.18), s + mk["trapx"][0])
        elif name == "cta":
            add_at(buf, sfx_pop(0.4), s + 0.05)

    buf += voice_track
    buf = buf[:int(total * SR)]
    peak = float(np.max(np.abs(buf))) if len(buf) else 1.0
    if peak > 0.95:
        buf = buf / peak * 0.95
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# ==================== COMMON OVERLAYS ====================

def draw_header(canvas, data, gt, total):
    d = ImageDraw.Draw(canvas)
    d.text((60, 70), "POSTAL WALA", font=get_font(34), fill=(148, 163, 184), anchor="lm")
    chip = pill_sprite(f"Clause {data['clause_no']}  |  Part {data['part_no']}/{data['total_parts']}",
                       26, YELLOW, (40, 32, 8), ORANGE)
    place(canvas, chip, W - 60 - chip.width / 2, 70)
    x0, x1, y = 60, W - 60, 118
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((x0, y, x1, y + 10), radius=5, fill=(27, 42, 58))
    cur = x0 + (x1 - x0) * clamp(gt / total)
    d.rounded_rectangle((x0, y, max(x0 + 10, cur), y + 10), radius=5, fill=CYAN)
    place(canvas, glow_sprite(22, CYAN, 200), cur, y + 5)


def topic_chip(canvas, data, y, a=1.0):
    chip = pill_sprite(data["title"], 32, CYAN, (10, 30, 50), (40, 100, 150))
    place(canvas, chip, W / 2, y, alpha=a)


def opt_positions(n=4, y0=720, gap=190):
    return [y0 + i * gap for i in range(n)]


# ==================== SCENES ====================

def scene_hook(cv, data, t, dur, m, vd, sc):
    stamp_t = sc["stamp_t"]
    e = ease_out_back(prog(t, 0, 0.35))
    bob = math.sin(t * 5) * 8
    place(cv, glow_sprite(260, RED, 90), W / 2, 430)
    place(cv, envelope_sprite(), W / 2, 430 + bob, scale=0.6 + 0.4 * e, angle=math.sin(t * 3) * 4)

    chip = pill_sprite("GDS  |  MTS  |  PA  |  IP  EXAM", 30, YELLOW, (45, 30, 5), ORANGE)
    place(cv, chip, W / 2, 230, alpha=0.4 + 0.6 * prog(t, 0, 0.2))

    p = clamp(t / max(0.1, vd))
    draw_kinetic(cv, data["hook"], W / 2, 0, 920, 80, p, max_lines=4, min_size=50,
                 ghost=0.22, center_y=880)

    fx = {}
    if t >= stamp_t:
        k = prog(t, stamp_t, 0.18)
        place(cv, stamp_sprite(), W / 2, 1310, scale=2.3 - 1.3 * ease_out_cubic(k), angle=-9,
              alpha=clamp(k * 3))
        if t < stamp_t + 0.35:
            fx["shake"] = 16 * (1 - prog(t, stamp_t + 0.05, 0.3))
        fx["flash"] = 0.25 * (1 - prog(t, stamp_t, 0.12))

    blink = 0.55 + 0.45 * math.sin(t * 7)
    d = ImageDraw.Draw(cv)
    d.text((W / 2, 1500), "जवाब सबसे आखिर में, पहले खुद सोचिए", font=get_font(38),
           fill=mix(BG_BOTTOM, YELLOW, blink), anchor="mm")
    return fx


def scene_question(cv, data, t, dur, m, vd, sc):
    place(cv, pill_sprite("सवाल", 34, WHITE, (37, 60, 140), BLUE), W / 2, 215)
    topic_chip(cv, data, 300, a=0.9)

    q0, q1 = m["q"]
    qp = clamp((t - q0) / max(0.1, q1 - q0))
    draw_kinetic(cv, data["question"], W / 2, 390, 920, 58, qp, max_lines=3, min_size=40, ghost=0.15)

    ys = opt_positions()
    for i, (l, txt) in enumerate(data["options"]):
        s0 = sc["opt_t"][i]
        k = prog(t, s0, 0.3)
        if k <= 0:
            place(cv, option_sprite(l, txt, 900, 150, "normal"), W / 2, ys[i], alpha=0.12)
            continue
        active = s0 <= t < s0 + 0.35
        e = ease_out_back(k)
        place(cv, option_sprite(l, txt, 900, 150, "active" if active else "normal"),
              W / 2 + (1 - e) * 500, ys[i], alpha=clamp(k * 2), scale=1.04 if active else 1.0)
    return {}


def scene_countdown(cv, data, t, dur, m, vd, sc):
    d = ImageDraw.Draw(cv)
    d.text((W / 2, 230), "अपना जवाब लॉक कीजिए!", font=get_font(62), fill=WHITE, anchor="mm")
    ys = opt_positions(y0=420, gap=165)
    pulse = 1 + 0.015 * math.sin(t * 10)
    for i, (l, txt) in enumerate(data["options"]):
        place(cv, option_sprite(l, txt, 860, 132, "normal"), W / 2, ys[i], scale=pulse)

    cx, cy, r = W / 2, 1270, 150
    cd = COUNTDOWN_SECONDS
    done = t >= cd
    num = max(1, cd - int(t))
    frac = t - int(t)
    place(cv, glow_sprite(260, PURPLE, 120), cx, cy)
    d = ImageDraw.Draw(cv)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(20, 16, 40), outline=(60, 50, 100), width=14)
    remain = 0.0 if done else clamp(1 - t / cd)
    if remain > 0.002:
        d.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * remain, fill=YELLOW, width=14)
    if done:
        place(cv, lock_sprite(150), cx, cy, scale=max(0.05, ease_out_back(prog(t, cd, 0.3))))
    else:
        s = 1.35 - 0.35 * ease_out_cubic(clamp(frac * 3))
        d.text((cx, cy), str(num), font=get_font(int(150 * s)), fill=YELLOW, anchor="mm")

    d.text((W / 2, 1520), "कमेंट करें:  A  /  B  /  C  /  D", font=get_font(46), fill=WHITE, anchor="mm")
    return {"shake": 5 if (not done and frac < 0.08 and t > 0.05) else 0}


def scene_hint(cv, data, t, dur, m, vd, sc):
    k = ease_out_back(prog(t, 0, 0.35))
    glow = 0.7 + 0.3 * math.sin(t * 6)
    place(cv, glow_sprite(280, YELLOW, int(120 * glow)), W / 2, 470)
    place(cv, bulb_sprite(240), W / 2, 470, scale=max(0.05, 0.5 + 0.5 * k), angle=math.sin(t * 4) * 5)
    place(cv, pill_sprite("HINT", 44, (30, 20, 0), YELLOW, YELLOW), W / 2, 690, scale=max(0.05, k))

    bh = text_block_h(data["hint"], 820, 64, 4, 42)
    ch = bh + 140
    place(cv, card_sprite(940, ch, CARD, ORANGE, 5, 40), W / 2, 1000, alpha=clamp(k))
    h0, h1 = m["hint"]
    p = clamp((t - h0) / max(0.1, h1 - h0))
    draw_kinetic(cv, data["hint"], W / 2, 0, 820, 64, p, max_lines=4, min_size=42, ghost=0.12, center_y=1000)

    d = ImageDraw.Draw(cv)
    d.text((W / 2, 1000 + ch / 2 + 110), "अब भी वही जवाब?", font=get_font(46), fill=MUTED, anchor="mm")
    return {}


def scene_eliminate(cv, data, t, dur, m, vd, sc):
    d = ImageDraw.Draw(cv)
    suspense_phase = m["left"][0] <= t < m["x3"][0]
    if t >= m["x3"][0]:
        title, tcol = "सिर्फ एक बचा!", GREEN
    elif suspense_phase:
        title, tcol = "बचे दो... सही कौन?", YELLOW
    else:
        title, tcol = "गलत हटाओ!", WHITE
    d.text((W / 2, 250), title, font=get_font(66), fill=tcol, anchor="mm")

    ys = opt_positions(y0=520, gap=200)
    fx = {}
    order = data["elim_order"]
    kill_t = {order[0]: m["x1"][0], order[1]: m["x2"][0], order[2]: m["x3"][0]}
    for i, (l, txt) in enumerate(data["options"]):
        y = ys[i]
        if l in kill_t and t >= kill_t[l]:
            k = prog(t, kill_t[l], 0.25)
            shake = math.sin(k * 40) * 18 * (1 - k)
            place(cv, option_sprite(l, txt, 900, 150, "wrong"), W / 2 + shake, y,
                  alpha=1 - 0.55 * k, scale=1 - 0.06 * k)
            place(cv, x_mark_sprite(), W / 2 + 390, y, scale=max(0.05, 1.8 - 0.8 * ease_out_back(k)))
            if t - kill_t[l] < 0.1:
                fx["shake"] = 8
        else:
            suspense = t >= m["left"][0]
            sc_ = 1 + (0.03 * math.sin(t * 12) if suspense else 0)
            place(cv, option_sprite(l, txt, 900, 150, "active" if suspense else "normal"), W / 2, y, scale=sc_)

    if suspense_phase:
        heart = 0.5 + 0.5 * math.sin(t * 14)
        d = ImageDraw.Draw(cv)
        d.text((W / 2, 1400), "? ? ?", font=get_font(70), fill=mix(BG_BOTTOM, YELLOW, heart), anchor="mm")
    return fx


def scene_reveal(cv, data, t, dur, m, vd, sc):
    place(cv, rays_sprite(), W / 2, 860, angle=t * 25, scale=1.1)
    place(cv, glow_sprite(360, GREEN, 140), W / 2, 860)

    d = ImageDraw.Draw(cv)
    d.text((W / 2, 290), "सही जवाब", font=get_font(72), fill=GREEN, anchor="mm")

    k = ease_out_back(prog(t, 0, 0.4))
    place(cv, check_sprite(170), W / 2, 560, scale=max(0.05, 0.3 + 0.7 * k))
    place(cv, option_sprite(data["correct"], data["correct_text"], 920, 170, "correct"),
          W / 2, 860, scale=max(0.05, 0.7 + 0.35 * k))

    rng = random.Random(9)
    d = ImageDraw.Draw(cv)
    for _ in range(70):
        ang = rng.uniform(0, 2 * math.pi)
        sp = rng.uniform(500, 1300)
        col = rng.choice([GREEN, YELLOW, CYAN, WHITE, ORANGE])
        sz = rng.randint(8, 16)
        x = W / 2 + math.cos(ang) * sp * t * 0.9
        y = 860 + math.sin(ang) * sp * t * 0.9 + 900 * t * t
        if 0 < x < W and 0 < y < H and t < 1.8:
            d.rectangle((x, y, x + sz, y + sz * 0.6), fill=col)

    d.text((W / 2, 1160), "आपका जवाब सही था?", font=get_font(48), fill=WHITE, anchor="mm")
    return {"flash": 0.28 * (1 - prog(t, 0, 0.12))}


def scene_rule(cv, data, t, dur, m, vd, sc):
    topic_chip(cv, data, 230)
    fh = text_block_h(data["fact"], 860, 58, 5, 38) + 150
    th = text_block_h(data["trap"], 860, 54, 4, 36) + 150
    gap = 110
    top = max(330, (330 + 1560) / 2 - (fh + gap + th) / 2)
    fc, tc = top + fh / 2, top + fh + gap + th / 2

    k1 = ease_out_back(prog(t, 0, 0.35))
    place(cv, card_sprite(960, int(fh), (12, 36, 28), GREEN, 5, 40), W / 2, fc,
          scale=0.92 + 0.08 * k1, alpha=clamp(k1))
    place(cv, pill_sprite("नियम", 40, (5, 30, 15), GREEN, GREEN), W / 2, fc - fh / 2, scale=max(0.05, k1))
    f0, f1 = m["fact"]
    fp = clamp((t - f0) / max(0.1, f1 - f0))
    draw_kinetic(cv, data["fact"], W / 2, 0, 860, 58, fp, max_lines=5, min_size=38,
                 hl_words=data["hl_words"], hl_color=GREEN, ghost=0.12, center_y=fc + 10)

    ts = m["trapx"][0]
    fx = {}
    if t >= ts - 0.1:
        k2 = ease_out_back(prog(t, ts - 0.1, 0.35))
        place(cv, card_sprite(960, int(th), (48, 16, 22), RED, 5, 40), W / 2, tc,
              scale=0.9 + 0.1 * k2, alpha=clamp(k2))
        place(cv, pill_sprite("EXAM TRAP", 40, WHITE, RED, RED), W / 2, tc - th / 2,
              scale=max(0.05, k2), angle=-3)
        t0, t1 = m["trap"]
        tp = clamp((t - t0) / max(0.1, t1 - t0))
        draw_kinetic(cv, data["trap"], W / 2, 0, 860, 54, tp, max_lines=4, min_size=36,
                     ghost=0.12, center_y=tc + 10)
        if t - ts < 0.12:
            fx["shake"] = 6
    else:
        d = ImageDraw.Draw(cv)
        a = 0.5 + 0.5 * math.sin(t * 6)
        d.text((W / 2, tc), "लेकिन असली ट्रैप अभी बाकी है...", font=get_font(46),
               fill=mix(BG_BOTTOM, ORANGE, a), anchor="mm")
    return fx


def scene_cta(cv, data, t, dur, m, vd, sc):
    k = ease_out_back(prog(t, 0, 0.35))
    place(cv, check_sprite(150), W / 2, 330, scale=max(0.05, k))
    d = ImageDraw.Draw(cv)
    d.text((W / 2, 500), "सही किया?", font=get_font(84), fill=WHITE, anchor="mm")
    place(cv, pill_sprite("कमेंट करें:  पक्का", 52, (5, 30, 15), GREEN, GREEN), W / 2, 640,
          scale=max(0.05, 0.6 + 0.4 * k))

    k2 = ease_out_back(prog(t, 0.35, 0.4))
    place(cv, card_sprite(940, 360, CARD, PURPLE, 5, 40), W / 2, 990, alpha=clamp(k2), scale=0.9 + 0.1 * k2)
    if k2 > 0.2:
        d = ImageDraw.Draw(cv)
        d.text((W / 2, 880), "अगला सवाल और भी मुश्किल", font=get_font(44), fill=YELLOW, anchor="mm")
        f, s, lines = fit_lines(data["next_title"], 700, 2, 50, 34)
        for i, ln in enumerate(lines):
            d.text((W / 2 + 50, 985 + i * s * 1.3), " ".join(ln), font=f, fill=WHITE, anchor="mm")
        place(cv, lock_sprite(90), W / 2 - 390, 1005, angle=math.sin(t * 6) * 8)

    pulse = 1 + 0.05 * math.sin(t * 8)
    place(cv, glow_sprite(230, RED, 110), W / 2, 1320)
    place(cv, pill_sprite("FOLLOW  @POSTAL_WALA", 50, WHITE, (220, 38, 38), (255, 120, 120)),
          W / 2, 1320, scale=pulse)
    d = ImageDraw.Draw(cv)
    d.text((W / 2, 1460), "रोज़ 1 नियम, सीधा परीक्षा से", font=get_font(40), fill=MUTED, anchor="mm")
    return {}


SCENES = {
    "hook": scene_hook, "question": scene_question, "countdown": scene_countdown,
    "hint": scene_hint, "eliminate": scene_eliminate, "reveal": scene_reveal,
    "rule": scene_rule, "cta": scene_cta,
}


# ==================== RENDER ====================

def render_frame(sc, data, gt, total):
    t = gt - sc["start"]
    cv = bg_frame(sc["mood"], gt)
    fx = SCENES[sc["name"]](cv, data, t, sc["dur"], sc["marks"], sc["vdur"], sc) or {}
    draw_header(cv, data, gt, total)

    # scene-entry punch zoom
    if sc["index"] > 0 and t < 0.2:
        z = 1 + 0.07 * (1 - ease_out_cubic(t / 0.2))
        nw, nh = int(W * z), int(H * z)
        big = cv.resize((nw, nh), Image.BILINEAR)
        ox, oy = (nw - W) // 2, (nh - H) // 2
        cv = big.crop((ox, oy, ox + W, oy + H))

    shake = fx.get("shake", 0) or 0
    if shake > 0.5:
        rng = random.Random(int(gt * 1000))
        s = int(shake)
        dx, dy = rng.randint(-s, s), rng.randint(-s, s)
        base = Image.new("RGB", (W, H), BG_TOP)
        base.paste(cv, (dx, dy))
        cv = base

    flash = fx.get("flash", 0) or 0
    if flash > 0.01:
        cv = Image.blend(cv, Image.new("RGB", (W, H), (255, 255, 255)), clamp(flash))
    return cv


def build_timeline(specs, voices, data):
    timeline, cur = [], 0.0
    for i, (sp, v) in enumerate(zip(specs, voices)):
        vdur = len(v) / SR
        dur = max(vdur + sp["tail"], sp["min"])
        sc = {
            "index": i, "name": sp["name"], "mood": sp["mood"], "start": cur, "dur": dur,
            "vdur": vdur, "marks": compute_marks(sp["segs"], vdur), "data": data,
        }
        if sp["name"] == "hook":
            sc["stamp_t"] = min(max(0.6, vdur * 0.55), dur - 0.5)
        if sp["name"] == "question":
            first = max(0.4, vdur * 0.55)
            sc["opt_t"] = [first + j * 0.22 for j in range(4)]
        timeline.append(sc)
        cur += dur
    return timeline, cur


def build_reel(data, output_video):
    os.makedirs(os.path.dirname(output_video) or ".", exist_ok=True)
    resolve_font()

    specs = build_scene_specs(data)
    print("Voice ban rahi hai...")
    voices = make_voices(specs)
    timeline, total = build_timeline(specs, voices, data)
    for sc in timeline:
        print(f"  {sc['name']:<10} start {sc['start']:5.2f}s  dur {sc['dur']:4.2f}s")

    audio_path = "_master_audio.wav"
    build_audio(voices, timeline, total, audio_path)

    n_frames = int(math.ceil(total * FPS))
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
        output_video,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        si = 0
        for fi in range(n_frames):
            gt = fi / FPS
            while si + 1 < len(timeline) and gt >= timeline[si + 1]["start"]:
                si += 1
            frame = render_frame(timeline[si], data, gt, total)
            proc.stdin.write(frame.tobytes())
            if fi % 90 == 0:
                print(f"  frame {fi}/{n_frames}")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    ret = proc.wait()
    if os.path.exists(audio_path):
        os.remove(audio_path)
    if ret != 0:
        raise RuntimeError("ffmpeg encoding fail hua")
    print(f"COMPLETE: {output_video} ({total:.2f}s)")


# ==================== MAIN ====================

if __name__ == "__main__":
    state = load_state()
    print("Current State:", state)

    raw = generate_script(state)
    data = prepare_data(raw, state["clause_no"], state["current_part"])
    print("\nSCRIPT DATA:")
    print(json.dumps({k: v for k, v in data.items() if k != "hl_words"}, ensure_ascii=False, indent=2))

    out = os.path.join(OUTPUT_DIR, f"reel_clause_{state['clause_no']}_part_{state['current_part']}.mp4")
    build_reel(data, out)
    if not DRY_RUN:
        advance_state(state)
