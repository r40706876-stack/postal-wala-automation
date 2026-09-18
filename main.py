import os
import glob
import json
import time
import asyncio
import subprocess
import requests
import textwrap
import re
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
BGM_OUTPUT = "bgm.mp3"
OUTPUT_VIDEO = "final_reel.mp4"
VOICE_NAME = "hi-IN-SwaraNeural"

# Assets Directory
ASSETS_DIR = "assets"
BOOK_3D_PATH = os.path.join(ASSETS_DIR, "3d_book.png")
POSTBOX_3D_PATH = os.path.join(ASSETS_DIR, "3d_postbox.png")
QUIZ_3D_PATH = os.path.join(ASSETS_DIR, "3d_quiz.png")

RESAMPLE_MODE = getattr(Image, "Resampling", Image).LANCZOS

# --- 6 High-Retention Rotating Viral Hooks (Voice & Visual Badges) ---
VIRAL_HOOKS = [
    {
        "voice": "लिख कर ले लो! इस 40 सेकंड की रील से विभागीय परीक्षा में आपके 2 नंबर पक्के होने वाले हैं, आइए देखते हैं कैसे!",
        "visual_badge": "🔥 लिख कर ले लो! इस रील से 2 नंबर पक्के"
    },
    {
        "voice": "जीडीएस से एमटीएस और पोस्टमैन परीक्षा में 90% लोग इस एक नियम में गलत उत्तर देकर आते हैं! क्या आप भी वही गलती कर रहे हैं?",
        "visual_badge": "⚠️ 90% लोग इस नियम में फेल होते हैं!"
    },
    {
        "voice": "अगर आप सच में इस बार जीडीएस से प्रमोशन लेने की तैयारी कर रहे हैं, तो पोस्टल वाला के इस सवाल का सही जवाब देकर दिखाइए!",
        "visual_badge": "🎯 दम है तो सही उत्तर देकर दिखाओ!"
    },
    {
        "voice": "डाक विभाग की परीक्षाओं में बार-बार दोहराया जाने वाला सबसे पसंदीदा नियम! आज 45 सेकंड में इसे हमेशा के लिए रट लो!",
        "visual_badge": "📌 परीक्षा में बार-बार पूछा जाने वाला नियम"
    },
    {
        "voice": "अगर इस साल जीडीएस की नौकरी से प्रमोशन पाकर पोस्टमैन या पी.ए. बनना है, तो इस रील को 1 सेकंड भी स्किप मत करना!",
        "visual_badge": "🚀 जीडीएस से प्रमोशन का पक्का मौका!"
    },
    {
        "voice": "क्या आपको पता है? डाक घर गाइड का यह एक छोटा सा क्लॉज कई लोगों का प्रमोशन रोक देता है! आइए इस नियम को गहराई से समझें!",
        "visual_badge": "⚡ चेतावनी: यह नियम प्रमोशन रोक सकता है!"
    }
]

# --- Official PO Guide Part 1 Complete Master Catalog (Clauses 1 to 60) ---
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
    5: {
        "name": "डाकघर के कामकाज के घंटे",
        "total_parts": 2,
        "part_1_focus": "सामान्य डाक लेन-देन, रजिस्ट्री बुकिंग, मनीऑर्डर और बचत बैंक के अलग-अलग निर्धारित समय सीमा के नियम।",
        "part_2_focus": "सार्वजनिक कार्य के घंटे समाप्त होने के बाद खिड़कियां बंद करने और लेट फीस के साथ डाक स्वीकार करने के नियम।"
    },
    6: {
        "name": "रविवार और डाक अवकाश पर कार्य",
        "total_parts": 1,
        "part_1_focus": "रविवार और 16 राजपत्रित अवकाशों पर सामान्य डाकघर पूर्णतः बंद रहते हैं, केवल रात्रि डाकघर सीमित सेवाएं देते हैं।"
    },
    7: {
        "name": "डाक टिकटों और लेखन-सामग्री का विक्रय",
        "total_parts": 2,
        "part_1_focus": "प्रत्येक डाकघर में कार्य के घंटों के दौरान जनता के लिए डाक टिकट और स्टेशनरी की उपलब्धता सुनिश्चित करना अनिवार्य।",
        "part_2_focus": "डाक टिकट काउंटर पर फटे-पुराने नोट न देने और सही मुद्रा में भुगतान करने के विभागीय नियम।"
    },
    8: {
        "name": "फिलाटेलिक ब्यूरो और डाक टिकट संग्रह",
        "total_parts": 1,
        "part_1_focus": "स्मारक डाक टिकटों की बिक्री, फिलाटेलिक डिपॉजिट अकाउंट (PDA) खोलने और टिकट संग्राहकों के लिए विशेष सुविधाएं।"
    },
    9: {
        "name": "फ्रैंकिंग मशीन के नियम व लाइसेंस",
        "total_parts": 2,
        "part_1_focus": "डाक महानिदेशक या मंडल प्रमुख द्वारा लाइसेंस जारी करना, लाल रंग की स्याही की छाप और लाइसेंस शुल्क के नियम।",
        "part_2_focus": "फ्रैंकिंग मीटर रीसेट, एडवांस भुगतान पर मिलने वाली छूट और पोस्टिंग के लिए निर्धारित डाकघर की शर्तें।"
    },
    10: {
        "name": "अप्रयुक्त व जाली टिकटों का निषेध",
        "total_parts": 1,
        "part_1_focus": "काटे गए, फटे, पूर्व-उपयोग किए गए या जाली टिकटों का उपयोग आईपीसी की धारा 263-A के तहत दंडनीय अपराध है।"
    },
    11: {
        "name": "डाकभार का पूर्व-भुगतान",
        "total_parts": 1,
        "part_1_focus": "डाकभार का पूर्ण पूर्व-भुगतान डाक टिकटों से किया जाना अनिवार्य, बिना डाकभार पत्रों पर दोगुना डाक शुल्क वसूलने का नियम।"
    },
    12: {
        "name": "बिना डाकभार व कम डाकभार वाली वस्तुएं",
        "total_parts": 2,
        "part_1_focus": "अनपेड डाक वस्तुओं पर वितरण के समय दोगुना शुल्क और कम डाकभार पर कमी का दोगुना शुल्क वसूलना।",
        "part_2_focus": "यदि प्राप्तकर्ता अनपेड डाक लेने से इनकार करता है, तो शुल्क प्रेषक से कानूनी रूप से वसूल किया जाता है।"
    },
    13: {
        "name": "पैकिंग और सीलिंग की सामान्य शर्तें",
        "total_parts": 2,
        "part_1_focus": "डाक वस्तुओं की मजबूत पैकिंग ताकि परिवहन के दौरान अन्य डाक वस्तुओं और डाक कर्मचारियों को नुकसान न पहुंचे।",
        "part_2_focus": "कीमती सामान और पार्सल पर विशेष मोहर, वैक्स सील और मजबूत धागे के उपयोग से संबंधित अनिवार्य निर्देश।"
    },
    14: {
        "name": "पता लिखने का सही प्रारूप",
        "total_parts": 2,
        "part_1_focus": "पत्र के मुख भाग पर समानांतर दिशा में दाईं ओर प्राप्तकर्ता का पूरा नाम, पता और पिन कोड लिखना।",
        "part_2_focus": "पत्र के निचले बाएं कोने या पिछले हिस्से पर प्रेषक का नाम व पता लिखना ताकि अवितरित होने पर वापस भेजा जा सके।"
    },
    15: {
        "name": "पिन कोड प्रणाली के नियम",
        "total_parts": 1,
        "part_1_focus": "6 अंकों का पिन कोड (पहला अंक जोन, दूसरा उप-जोन, तीसरा जिला, अंतिम तीन अंक वितरण डाकघर) डाक छंटाई को तीव्र बनाता है।"
    },
    16: {
        "name": "पोस्टिंग का प्रमाण पत्र (UPC)",
        "total_parts": 1,
        "part_1_focus": "डाकघर में सामान्य डाक डालने के लिखित साक्ष्य के रूप में पोस्टिंग का प्रमाण पत्र जारी करने के नियम।"
    },
    17: {
        "name": "डाक वस्तुओं की वापसी (Recall of Articles)",
        "total_parts": 2,
        "part_1_focus": "प्रेषक द्वारा डाक वितरण से पूर्व पत्र वापस बुलाने का अधिकार, निर्धारित आवेदन शुल्क और प्रक्रिया।",
        "part_2_focus": "डाक वापसी के लिए प्रेषक द्वारा अपनी पहचान सिद्ध करना और सक्षम डाक प्राधिकारी की लिखित अनुमति।"
    },
    18: {
        "name": "पत्र पेटियों में डाक पोस्ट करने के नियम",
        "total_parts": 1,
        "part_1_focus": "लेटर बॉक्स में केवल पूरी तरह प्रीपेड अनरजिस्टर्ड पत्र डालना, पार्सल व बीमित पत्र डालना सख्त वर्जित।"
    },
    19: {
        "name": "अंतर्देशीय डाक वस्तुओं की श्रेणियां",
        "total_parts": 1,
        "part_1_focus": "प्रथम श्रेणी डाक (पत्र, पोस्टकार्ड, आईएलसी) जिन्हें बिना अतिरिक्त हवाई अधिभार स्वतः एयर ट्रांसमिशन मिलता है।"
    },
    20: {
        "name": "पत्र (Letters) के वजन व आकार सीमाएं",
        "total_parts": 2,
        "part_1_focus": "पत्र का अधिकतम वजन 2 किलोग्राम तक, लंबाई-चौड़ाई और रोल फार्म के लिए निर्धारित न्यूनतम-अधिकतम सीमाएं।",
        "part_2_focus": "प्रत्येक 20 ग्राम या उसके भाग पर निर्धारित डाक शुल्क दरें और कम डाकभार पर दोगुनी वसूली के नियम।"
    },
    21: {
        "name": "अंतर्देशीय पत्र कार्ड (ILC) के नियम",
        "total_parts": 1,
        "part_1_focus": "आईएलसी केवल भारत के भीतर मान्य, अधिकतम वजन 5 ग्राम और इसके भीतर कोई भी अतिरिक्त सामग्री रखना वर्जित।"
    },
    22: {
        "name": "पोस्टकार्ड की श्रेणियां व दरें",
        "total_parts": 2,
        "part_1_focus": "एकल पोस्टकार्ड (Single), जवाबी पोस्टकार्ड (Reply), मुद्रित और मेघदूत पोस्टकार्ड की निर्धारित दरें व माप।",
        "part_2_focus": "पोस्टकार्ड पर कुछ भी चिपकाने या मोड़ने पर उसे सामान्य पत्र मानकर अतिरिक्त शुल्क वसूलने का नियम।"
    },
    23: {
        "name": "बुक पैकेट (Book Packets) के नियम",
        "total_parts": 2,
        "part_1_focus": "बुक पैकेट का अधिकतम वजन 5 किलोग्राम, खुला और बिना सील का होना अनिवार्य ताकि जांच की जा सके।",
        "part_2_focus": "बुक पैकेट में कोई भी व्यक्तिगत पत्र व्यवहार या बंद संदेश रखना सख्त वर्जित और दंडनीय।"
    },
    24: {
        "name": "मुद्रित पुस्तकों का बुक पैकेट",
        "total_parts": 1,
        "part_1_focus": "केवल मुद्रित पुस्तकों के पैकेट पर विशेष रियायती डाक दरें और विज्ञापन सामग्री न होने की अनिवार्य शर्त।"
    },
    25: {
        "name": "अंध साहित्य पैकेट (Blind Literature)",
        "total_parts": 1,
        "part_1_focus": "ब्रेल लिपि में दृष्टिहीनों के साहित्य के लिए 7 किलोग्राम तक पूर्ण डाकभार व पंजीकरण शुल्क से छूट (एयर सरचार्ज छोड़कर)।"
    },
    26: {
        "name": "नमूना और पैटर्न पैकेट (Sample Packets)",
        "total_parts": 1,
        "part_1_focus": "व्यापारिक नमूनों के लिए अधिकतम वजन 2 किग्रा, जिसका कोई स्वतंत्र विक्रय मूल्य न हो।"
    },
    27: {
        "name": "पंजीकृत समाचार पत्र (Registered Newspapers)",
        "total_parts": 2,
        "part_1_focus": "समाचार पत्र का डाक विभाग में पंजीकरण, 31 दिनों से अधिक के अंतराल पर प्रकाशित न होना और रियायती दरें।",
        "part_2_focus": "पंजीकरण संख्या (RNI) का मुखपृष्ठ पर मुद्रण और पोस्टिंग के लिए निर्धारित डाकघरों की सूची।"
    },
    28: {
        "name": "समाचार पत्रों के पैकेट के नियम",
        "total_parts": 1,
        "part_1_focus": "एक ही पते पर भेजे जाने वाले एक से अधिक समाचार पत्रों के पैकेट के लिए विशेष डाक दरें और वजन सीमा।"
    },
    29: {
        "name": "पार्सल (Parcel) के सामान्य नियम",
        "total_parts": 2,
        "part_1_focus": "पार्सल की मजबूत पैकेजिंग, गैर-वितरण शाखा डाकघर (BO) के लिए अधिकतम वजन 10 किलोग्राम और अन्य के लिए 20 किग्रा।",
        "part_2_focus": "पार्सल में केवल प्रेषक और प्राप्तकर्ता से संबंधित एक ही लिखित पत्र या इनवॉइस रखने की अनुमति।"
    },
    30: {
        "name": "अपंजीकृत पार्सल की वजन सीमा",
        "total_parts": 1,
        "part_1_focus": "अपंजीकृत पार्सल का अधिकतम वजन 4 किलोग्राम, 4 किग्रा से अधिक होने पर अनिवार्य रूप से रजिस्ट्री कराना आवश्यक।"
    },
    31: {
        "name": "अनिवार्य पंजीकरण (Compulsory Registration)",
        "total_parts": 2,
        "part_1_focus": "4 किलोग्राम से अधिक वजन का पार्सल, बीमित वस्तुएं और सीमा शुल्क वाली वस्तुओं का अनिवार्य पंजीकरण।",
        "part_2_focus": "यदि लेटर बॉक्स में कोई ऐसी वस्तु पाई जाती है जिसे रजिस्टर होना चाहिए था, तो दोगुनी फीस वसूल कर रजिस्ट्री की जाती है।"
    },
    32: {
        "name": "हवाई डाक (Air Mail) नियम व अधिभार",
        "total_parts": 1,
        "part_1_focus": "द्वितीय श्रेणी डाक (पार्सल, बुक पैकेट) पर हवाई ट्रांसमिशन के लिए निर्धारित अतिरिक्त एयर मेल शुल्क।"
    },
    33: {
        "name": "बीमा (Insurance) की सामान्य शर्तें",
        "total_parts": 2,
        "part_1_focus": "डाक वस्तुओं के खोने या नुकसान से सुरक्षा हेतु बीमा, अनिवार्य वैक्स सील और निर्धारित बीमा शुल्क संरचना।",
        "part_2_focus": "बीमित वस्तु के वास्तविक मूल्य से अधिक का बीमा कराना वर्जित और कपटपूर्ण दावों का निषेध।"
    },
    34: {
        "name": "अनिवार्य बीमा वाली वस्तुएं",
        "total_parts": 1,
        "part_1_focus": "मुद्रा नोट, सिक्के, सोने-चांदी के आभूषण और कीमती पत्थरों को डाक से भेजने पर बीमा कराना पूर्णतः अनिवार्य।"
    },
    35: {
        "name": "बीमा की अधिकतम सीमाएं व शाखा डाकघर",
        "total_parts": 1,
        "part_1_focus": "शाखा डाकघरों (BO) में अधिकतम ₹600 तक बीमा स्वीकार्य, विभागीय प्रधान डाकघरों में ₹1,00,000 तक की सीमा।"
    },
    36: {
        "name": "मूल्यदेय डाक (Value Payable Post - VPP)",
        "total_parts": 2,
        "part_1_focus": "वीपीपी के अंतर्गत अधिकतम ₹5,000 तक की वसूली, केवल वास्तविक व्यापारिक वस्तुओं और दस्तावेजों के लिए मान्य।",
        "part_2_focus": "वीपीपी वस्तु के वितरण के समय राशि प्राप्त न होने पर डाकघर में अधिकतम 7 दिनों तक रखने के नियम।"
    },
    37: {
        "name": "वीपीपी वस्तु की बुकिंग व वितरण शर्तें",
        "total_parts": 1,
        "part_1_focus": "प्रेषक द्वारा वीपीपी फॉर्म भरना, पार्सल या पत्र पर स्पष्ट 'V.P.' लिखना और देय राशि का अंकन।"
    },
    38: {
        "name": "डाक वस्तुओं का पंजीकरण (Registration)",
        "total_parts": 2,
        "part_1_focus": "रजिस्ट्री कराने पर विशेष रसीद जारी होना, सुरक्षित हैंड-टू-हैंड ट्रांसमिशन और निर्धारित रजिस्ट्री शुल्क ₹17।",
        "part_2_focus": "खो जाने की स्थिति में विभागीय जांच और अंतर्देशीय पंजीकृत पत्रों के लिए निर्धारित क्षतिपूर्ति राशि।"
    },
    39: {
        "name": "रजिस्ट्री पावती (Acknowledgement - AD)",
        "total_parts": 1,
        "part_1_focus": "प्राप्तकर्ता के हस्ताक्षर युक्त पावती (AD कार्ड) प्रेषक को वापस भेजने का निर्धारित शुल्क ₹3 और इसके नियम।"
    },
    40: {
        "name": "डाक वितरण की सामान्य व्यवस्था",
        "total_parts": 2,
        "part_1_focus": "डाकिए द्वारा क्षेत्र में घर-घर जाकर डाक वितरण, सुरक्षित डिलीवरी और हस्ताक्षर प्राप्त करने की प्रक्रिया।",
        "part_2_focus": "नाबालिग या मानसिक अस्वस्थ व्यक्तियों के नाम आई डाक के वितरण हेतु कानूनी अभिभावक के अधिकार।"
    },
    41: {
        "name": "वितरण के समय देय डाकभार की वसूली",
        "total_parts": 1,
        "part_1_focus": "कम या बिना डाकभार वाली वस्तुओं को सुपुर्द करने से पहले देय राशि नकद वसूलना और रसीद देना।"
    },
    42: {
        "name": "क्षतिग्रस्त व फटी हुई डाक वस्तुओं की डिलीवरी",
        "total_parts": 1,
        "part_1_focus": "रास्ते में फटे या क्षतिग्रस्त पार्सल को डाकपाल की उपस्थिति में डाक खिड़की पर खोलकर जांच कर डिलीवरी देना।"
    },
    43: {
        "name": "अवितरित डाक (Undelivered Articles)",
        "total_parts": 2,
        "part_1_focus": "प्राप्तकर्ता न मिलने पर डाकिए द्वारा 7 दिनों तक डाकघर में रखना, 'पता न मिलने' पर प्रेषक को वापसी।",
        "part_2_focus": "यदि प्रेषक का पता भी न हो, तो डाक वस्तु को रिटर्न लेटर ऑफिस (RLO) भेजने की अनिवार्य प्रक्रिया।"
    },
    44: {
        "name": "रिटर्न लेटर ऑफिस (RLO) के कार्य",
        "total_parts": 1,
        "part_1_focus": "अवितरित और लावारिस डाक वस्तुओं को खोलकर प्रेषक या पाने वाले का पता खोजने और सुरक्षित निस्तारण का कार्यालय।"
    },
    45: {
        "name": "डाक का पुन:प्रेषण (Redirection) शुल्क नियम",
        "total_parts": 1,
        "part_1_focus": "प्रथम श्रेणी डाक का पुनर्निर्देशन पूर्णतः निःशुल्क, पार्सल के पुनर्निर्देशन पर आधा डाक शुल्क वसूलने का नियम।"
    },
    46: {
        "name": "शासकीय डाक वस्तुएं (Official Postal Articles)",
        "total_parts": 2,
        "part_1_focus": "सरकारी कार्यालयों द्वारा प्रेषित डाक, सर्विस स्टैम्प्स (Service Postage Stamps) का अनिवार्य प्रयोग।",
        "part_2_focus": "शासकीय डाक के लिफाफे पर 'On India Government Service' (OIGS) या 'On Service' का स्पष्ट मुद्रण।"
    },
    47: {
        "name": "सर्विस स्टैम्प्स के दुरुपयोग पर दंड",
        "total_parts": 1,
        "part_1_focus": "सरकारी सेवा टिकटों का निजी कार्य में उपयोग करना गंभीर कानूनी अपराध और आईपीसी के तहत दंडनीय।"
    },
    48: {
        "name": "कैंप डाक और विशेष बैग व्यवस्था",
        "total_parts": 1,
        "part_1_focus": "महामहिम राष्ट्रपति, उपराष्ट्रपति और उच्च गणमान्य व्यक्तियों के दौरे के समय विशेष कैंप डाक बैग के नियम।"
    },
    49: {
        "name": "सैन्य डाक सेवा (APO / FPO) के नियम",
        "total_parts": 2,
        "part_1_focus": "सेना डाक सेवा (APS) को 56 APO और 99 APO के माध्यम से डाक प्रेषण, नागरिक पिन कोड का प्रयोग न करना।",
        "part_2_focus": "सैनिकों के लिए वीपीपी और मनीऑर्डर भेजने की विशेष शर्तें और सैन्य पते का निर्धारित प्रारूप।"
    },
    50: {
        "name": "डाक में निषिद्ध वस्तुएं (Prohibited Articles)",
        "total_parts": 2,
        "part_1_focus": "विस्फोटक, ज्वलनशील पदार्थ, जीवित कीड़े, मादक द्रव्य और खतरनाक रसायनों को डाक से भेजना पूर्णतः प्रतिबंधित।",
        "part_2_focus": "निषिद्ध वस्तुएं पाए जाने पर डाक वस्तु को जब्त करना, नष्ट करना और भेजने वाले पर कानूनी कार्रवाई।"
    },
    51: {
        "name": "मनीऑर्डर (Money Order) की सामान्य शर्तें",
        "total_parts": 2,
        "part_1_focus": "इलेक्ट्रॉनिक मनीऑर्डर (eMO) द्वारा अधिकतम ₹5,000 तक की धनराशि प्रेषण और 5% कमीशन शुल्क संरचना।",
        "part_2_focus": "मनीऑर्डर के भुगतान के समय प्राप्तकर्ता की पहचान, अंगूठा निशानी या हस्ताक्षर के अनिवार्य नियम।"
    },
    52: {
        "name": "मनीऑर्डर का पता परिवर्तन व भुगतान रोकना",
        "total_parts": 1,
        "part_1_focus": "भुगतान से पूर्व प्रेषक द्वारा बिना अतिरिक्त शुल्क प्राप्तकर्ता का नाम या पता बदलने और राशि वापस लेने का अधिकार।"
    },
    53: {
        "name": "डाक जीवन बीमा (PLI) सामान्य परिचय",
        "total_parts": 1,
        "part_1_focus": "1884 में स्थापित सबसे पुरानी बीमा योजना, सरकारी व अर्ध-सरकारी कर्मचारियों के लिए कम प्रीमियम और अधिक बोनस।"
    },
    54: {
        "name": "ग्रामीण डाक जीवन बीमा (RPLI)",
        "total_parts": 1,
        "part_1_focus": "1995 में मल्होत्रा समिति की सिफारिश पर शुरू, ग्रामीण जनता के लिए 6 प्रमुख बीमा पॉलिसियां और सुरक्षा।"
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
    },
    57: {
        "name": "पोस्ट बॉक्स व पोस्ट बैग के संयुक्त नियम",
        "total_parts": 1,
        "part_1_focus": "बॉक्स और बैग दोनों एक साथ किराए पर लेने के संयुक्त नियम और ₹250 वार्षिक शुल्क के प्रावधान।"
    },
    58: {
        "name": "विशेष वितरण व्यवस्था (विंडो डिलीवरी)",
        "total_parts": 1,
        "part_1_focus": "फर्मों और भारी डाक प्राप्तकर्ताओं के लिए डाक खिड़की से डाक प्राप्त करने की विशेष व्यवस्था।"
    },
    59: {
        "name": "डाक का पुन:प्रेषण (Redirection)",
        "total_parts": 2,
        "part_1_focus": "पता बदलने की स्थिति में डाक को नए पते पर भेजने की शर्तें और अंतर्देशीय डाक पर कोई अतिरिक्त शुल्क न लगना।",
        "part_2_focus": "पार्सल के रीडायरेक्शन पर लगने वाला आधा डाक शुल्क और प्रेषक के लिखित निर्देश के नियम।"
    },
    60: {
        "name": "डाक लौटाने के निर्देश (Instruction regarding Delivery)",
        "total_parts": 1,
        "part_1_focus": "प्राप्तकर्ता द्वारा अनुपस्थिति में डाक रोकने या किसी अन्य व्यक्ति को सौंपने के लिखित आदेश की 3 वर्ष की वैधता।"
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

# Robust Multi-line Regex Extractor
def extract_field_block(text, field_name, next_fields):
    pattern = r"(?:^|\n)\s*(?:\*\*)?" + re.escape(field_name) + r"(?:\*\*)?\s*:\s*(.*?)(?=(?:\n\s*(?:\*\*)?(?:" + "|".join(next_fields) + r")(?:\*\*)?\s*:)|$)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        val = re.sub(r"^[\"\'`]+|[\"\'`]+$", "", val).strip()
        val = " ".join(val.split())
        return val
    return None

# --- 100% Offline 3D Graphic Renderer ---
def ensure_auto_icons():
    os.makedirs(ASSETS_DIR, exist_ok=True)

    if not os.path.exists(BOOK_3D_PATH):
        try:
            bk = Image.new("RGBA", (300, 420), (0, 0, 0, 0))
            db = ImageDraw.Draw(bk)
            db.ellipse([40, 360, 260, 400], fill="#0A0F1D")
            db.rounded_rectangle([55, 60, 245, 360], radius=14, fill="#1E3A8A")
            db.rounded_rectangle([75, 65, 240, 350], radius=8, fill="#F8FAFC", outline="#CBD5E1", width=2)
            db.rounded_rectangle([55, 55, 230, 350], radius=12, fill="#1D4ED8", outline="#60A5FA", width=3)
            db.rectangle([55, 55, 82, 350], fill="#F59E0B")
            db.rectangle([78, 55, 84, 350], fill="#FDE047")
            db.ellipse([115, 150, 185, 220], fill="#F59E0B", outline="#FEF08A", width=3)
            db.polygon([(150, 162), (155, 178), (172, 178), (158, 188), (163, 204), (150, 194), (137, 204), (142, 188), (128, 178), (145, 178)], fill="#FFFFFF")
            db.polygon([(140, 330), (162, 330), (162, 385), (151, 372), (140, 385)], fill="#DC2626")
            bk.save(BOOK_3D_PATH, "PNG")
        except Exception:
            pass

    if not os.path.exists(POSTBOX_3D_PATH):
        try:
            box = Image.new("RGBA", (300, 420), (0, 0, 0, 0))
            d = ImageDraw.Draw(box)
            d.ellipse([50, 375, 250, 410], fill="#0A0F1D")
            d.rounded_rectangle([65, 340, 235, 385], radius=15, fill="#1E293B", outline="#475569", width=3)
            d.rounded_rectangle([75, 120, 225, 350], radius=12, fill="#991B1B")
            d.rounded_rectangle([95, 120, 205, 350], radius=8, fill="#DC2626")
            d.rounded_rectangle([115, 120, 160, 350], radius=6, fill="#EF4444")
            d.rectangle([75, 165, 225, 182], fill="#F59E0B")
            d.rectangle([115, 165, 160, 182], fill="#FDE047")
            d.rounded_rectangle([90, 195, 210, 215], radius=5, fill="#0F172A")
            d.rectangle([110, 200, 190, 225], fill="#FFFFFF", outline="#CBD5E1", width=1)
            d.polygon([(110, 200), (150, 215), (190, 200)], fill="#E2E8F0")
            d.ellipse([140, 270, 160, 290], fill="#F59E0B", outline="#78350F", width=2)
            d.ellipse([147, 277, 153, 283], fill="#0F172A")
            d.chord([70, 40, 230, 150], start=180, end=0, fill="#B91C1C", outline="#F87171", width=3)
            d.chord([95, 50, 205, 140], start=180, end=0, fill="#EF4444")
            d.ellipse([135, 30, 165, 55], fill="#F59E0B", outline="#FEF08A", width=2)
            box.save(POSTBOX_3D_PATH, "PNG")
        except Exception:
            pass

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

# --- Background Music Auto-Synthesis Engine ---
def ensure_bgm(bgm_path="bgm.mp3"):
    if os.path.exists(bgm_path) and os.path.getsize(bgm_path) > 2000:
        return bgm_path
    if os.path.exists(os.path.join(ASSETS_DIR, "bgm.mp3")):
        return os.path.join(ASSETS_DIR, "bgm.mp3")

    try:
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "aevalsrc=exprs='0.035*sin(2*PI*110*t)+0.025*sin(2*PI*164.81*t)+0.02*sin(2*PI*220*t)':s=48000:d=70,lowpass=f=450",
            "-c:a", "libmp3lame", "-b:a", "128k", bgm_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(bgm_path) and os.path.getsize(bgm_path) > 2000:
            print(f"🎵 Generated ambient background audio: {bgm_path}", flush=True)
            return bgm_path
    except Exception as e:
        print(f"⚠️ BGM notice: {e}", flush=True)
    return None

# --- State Management With Hook Loop Tracking ---
def load_progress_state():
    state = {"clause_no": 55, "current_part": 2, "total_parts": 3, "hook_index": 0}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state.update(json.load(f))
        except Exception:
            pass
    if "hook_index" not in state:
        state["hook_index"] = 0
    return state

def save_progress_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"⚠️ Warning saving state: {e}", flush=True)

# --- Script Generation With Full Length & Full Paragraphs ---
def generate_clause_script(state):
    current_clause = state.get("clause_no", 55)
    current_part = state.get("current_part", 2)
    hook_idx = state.get("hook_index", 0) % len(VIRAL_HOOKS)
    hook_obj = VIRAL_HOOKS[hook_idx]
    active_hook_voice = hook_obj["voice"]
    active_hook_badge = hook_obj["visual_badge"]

    clause_info = POSTAL_CLAUSE_CATALOG.get(current_clause, POSTAL_CLAUSE_CATALOG[55])
    clause_name = clause_info["name"]
    total_parts = clause_info["total_parts"]
    part_focus = clause_info.get(f"part_{current_part}_focus", clause_info.get("part_1_focus", ""))

    fallback_data = {
        "clause_no": current_clause,
        "clause_name": clause_name,
        "part_no": current_part,
        "total_parts": total_parts,
        "visual_hook_badge": active_hook_badge,
        "sen1": f"भारतीय डाक विभाग के नियमों के अनुसार {clause_name} का विस्तृत विवरण डाक घर गाइड भाग 1 के क्लॉज {current_clause} में निर्धारित किया गया है।",
        "sen2": f"इस नियम के मुख्य कानूनी प्रावधान के अंतर्गत {part_focus}",
        "sen3": "विभागीय परीक्षाओं जैसे MTS, Postman और PA में इस क्लॉज के शुल्क, समय सीमा और संचालन शर्तों पर सीधे प्रश्न पूछे जाते हैं।",
        "question": f"डाक घर गाइड भाग 1 के क्लॉज {current_clause} का संबंध मुख्य रूप से किससे है?",
        "opt_a": clause_name,
        "opt_b": "डाक विभाग का बजट",
        "opt_c": "मनीऑर्डर नियम",
        "opt_d": "इनमें से कोई नहीं",
        "correct": "A",
        "voiceover": f"{active_hook_voice} आज का महत्वपूर्ण प्रश्न है: क्लॉज {current_clause}, {clause_name} का संबंध किससे है? इसका सही उत्तर जानने के लिए वीडियो में अंत तक बने रहें! डाक विभाग के नियमानुसार {part_focus} विभागीय परीक्षा की दृष्टि से यह नियम अत्यंत महत्वपूर्ण है क्योंकि इसमें से सीधे ऑब्जेक्टिव प्रश्न पूछे जाते हैं। तो दोस्तों, इसका सही उत्तर कमेंट्स में जरूर बताएं! फ्री मॉक टेस्ट के लिए स्क्रीन पर दिए नंबर पर व्हाट्सएप करें, और प्रमोशन पाने के लिए पोस्टल वाला को फॉलो करना न भूलें!",
        "caption": f"{active_hook_badge} | डाक घर गाइड भाग 1 क्लॉज {current_clause} संपूर्ण विश्लेषण। विभागीय परीक्षा (MTS / Postman / PA) की तैयारी के लिए फॉलो करें। #PostalWala #GDStoMTS #PostmanExam #GDSExam #IndiaPost #DepartmentalExam #POGuidePart1"
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

    MANDATORY OPENING HOOK (Use these EXACT words as the very first sentence of voiceover):
    "{active_hook_voice}"

    RULES:
    1. Flawless Devanagari Hindi. Complete professional sentences.
    2. Write exactly 3 authoritative teaching sentences (SEN1, SEN2, SEN3), each ~24-28 words long, clearly explaining the rule, official conditions, fees, and exam traps.
    3. The voiceover MUST be strictly between 118 and 125 words total (natural, deep-teaching pace ~51-53 seconds). Keep the full teaching intact!
    4. Follow this voiceover layout strictly:
       - OPENING: Use the MANDATORY OPENING HOOK word-for-word.
       - QUESTION HOOK: "आज का महत्वपूर्ण प्रश्न है: [Question]? इसका सही उत्तर वीडियो में अंत तक समझें!"
       - DEEP TEACHING: Thoroughly explain SEN1, SEN2, and SEN3 calmly, covering why this rule matters in postal operations and departmental exams.
       - UNIFIED CLOSING (Exact flow without repeating words):
         "तो दोस्तों, इसका सही उत्तर कमेंट्स में जरूर बताएं! फ्री मॉक टेस्ट के लिए स्क्रीन पर दिए नंबर पर व्हाट्सएप करें, और प्रमोशन पाने के लिए पोस्टल वाला को फॉलो करना न भूलें!"
       - DO NOT speak the digits of the phone number.
       - DO NOT repeat follow or whatsapp phrases anywhere else.
       - DO NOT reveal the correct answer.

    OUTPUT FORMAT:
    SEN1: [Rich Hindi sentence 1, ~26 words]
    SEN2: [Rich Hindi sentence 2, ~26 words]
    SEN3: [Rich Hindi sentence 3, ~26 words]
    QUESTION: [1 high-yield exam question in Hindi]
    OPT_A: [Option A]
    OPT_B: [Option B]
    OPT_C: [Option C]
    OPT_D: [Option D]
    CORRECT: [A/B/C/D]
    VOICEOVER: [Exact voiceover text strictly 118 to 125 words starting with the active hook]
    CAPTION: [Instagram caption with targeted hashtags]
    """

    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"}
        payload = {"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 850}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=25)
        res_json = res.json()

        if res.status_code == 200 and "choices" in res_json:
            raw_text = res_json["choices"][0]["message"]["content"].strip()
            data = fallback_data.copy()

            s1 = extract_field_block(raw_text, "SEN1", ["SEN2", "SEN3", "QUESTION"])
            s2 = extract_field_block(raw_text, "SEN2", ["SEN3", "QUESTION"])
            s3 = extract_field_block(raw_text, "SEN3", ["QUESTION"])
            q = extract_field_block(raw_text, "QUESTION", ["OPT_A", "OPT_B"])
            oa = extract_field_block(raw_text, "OPT_A", ["OPT_B", "OPT_C"])
            ob = extract_field_block(raw_text, "OPT_B", ["OPT_C", "OPT_D"])
            oc = extract_field_block(raw_text, "OPT_C", ["OPT_D", "CORRECT"])
            od = extract_field_block(raw_text, "OPT_D", ["CORRECT", "VOICEOVER"])
            c = extract_field_block(raw_text, "CORRECT", ["VOICEOVER", "CAPTION"])
            vo = extract_field_block(raw_text, "VOICEOVER", ["CAPTION"])
            cap = extract_field_block(raw_text, "CAPTION", ["VOICEOVER"])

            if s1 and len(s1) > 10: data["sen1"] = clean_hindi_postal_terms(s1)
            if s2 and len(s2) > 10: data["sen2"] = clean_hindi_postal_terms(s2)
            if s3 and len(s3) > 10: data["sen3"] = clean_hindi_postal_terms(s3)
            if q and len(q) > 8: data["question"] = clean_hindi_postal_terms(q)
            if oa and len(oa) > 1: data["opt_a"] = clean_hindi_postal_terms(oa)
            if ob and len(ob) > 1: data["opt_b"] = clean_hindi_postal_terms(ob)
            if oc and len(oc) > 1: data["opt_c"] = clean_hindi_postal_terms(oc)
            if od and len(od) > 1: data["opt_d"] = clean_hindi_postal_terms(od)
            if c: data["correct"] = clean_text(c).upper()[:1]
            if vo and len(vo) > 35: data["voiceover"] = clean_hindi_postal_terms(vo)
            if cap and len(cap) > 10: data["caption"] = clean_text(cap)

            if not data.get("voiceover") or len(data["voiceover"].strip()) < 35:
                data["voiceover"] = fallback_data["voiceover"]

            data["visual_hook_badge"] = active_hook_badge
            return data
    except Exception as e:
        print(f"⚠️ Groq API warning: {e}. Safe fallback active.", flush=True)

    return fallback_data

# --- Automatic Intelligent Clause & Hook Progression ---
def advance_progress_state(state, data):
    current_hook_idx = state.get("hook_index", 0)
    state["hook_index"] = (current_hook_idx + 1) % len(VIRAL_HOOKS)

    cur_part = data.get("part_no", state.get("current_part", 1))
    total_parts = data.get("total_parts", state.get("total_parts", 2))

    if cur_part < total_parts:
        state["current_part"] = cur_part + 1
        state["total_parts"] = total_parts
    else:
        cur_clause = state.get("clause_no")

        if cur_clause == 56:
            state["clause_no"] = 5
        elif cur_clause == 54:
            state["clause_no"] = 57
        else:
            catalog_keys = sorted(POSTAL_CLAUSE_CATALOG.keys())
            current_idx = catalog_keys.index(cur_clause) if cur_clause in catalog_keys else 0
            next_idx = (current_idx + 1) % len(catalog_keys)
            next_clause = catalog_keys[next_idx]

            if next_clause in [55, 56] and cur_clause != 55:
                next_clause = 57

            state["clause_no"] = next_clause

        state["current_part"] = 1
        state["total_parts"] = POSTAL_CLAUSE_CATALOG.get(state["clause_no"], {}).get("total_parts", 2)

    save_progress_state(state)

# --- Safe Voice Generation With Auto-Retry & Size Verification ---
async def generate_voice(text, filename="voice.mp3", max_retries=3):
    if not text or len(text.strip()) < 25:
        print("⚠️ Warning: Text too short, using emergency default text.", flush=True)
        text = "जीडीएस से प्रमोशन लेने के लिए आपका स्वागत है पोस्टल वाला में! विभागीय परीक्षा की पक्की तैयारी के लिए पोस्टल वाला को फॉलो करें और फ्री मॉक टेस्ट के लिए स्क्रीन पर दिए नंबर पर व्हाट्सएप करें!"

    for attempt in range(1, max_retries + 1):
        try:
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except Exception:
                    pass

            communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+0%")
            await communicate.save(filename)

            if os.path.exists(filename) and os.path.getsize(filename) > 5000:
                print(f"✅ Voice generated successfully ({os.path.getsize(filename)} bytes) on attempt {attempt}", flush=True)
                return
            else:
                size_now = os.path.getsize(filename) if os.path.exists(filename) else 0
                print(f"⚠️ Audio file too small ({size_now} bytes) on attempt {attempt}, retrying...", flush=True)
        except Exception as e:
            print(f"⚠️ Edge-TTS attempt {attempt} failed: {e}", flush=True)

        await asyncio.sleep(2)

    if not os.path.exists(filename) or os.path.getsize(filename) < 2000:
        raise RuntimeError("Edge-TTS failed to generate valid MP3 audio after retries!")

def get_audio_duration(audio_file):
    if not os.path.exists(audio_file) or os.path.getsize(audio_file) < 2000:
        raise ValueError(f"Audio file is corrupted or empty: {audio_file}")

    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_file]
    output = subprocess.check_output(cmd).decode().strip()
    return float(output)

# --- Balanced Professional Mobile Layout Engine With Audio Mix ---
def create_video_ffmpeg(script_data, audio_file="voice.mp3", output_video="final_reel.mp4"):
    ensure_fonts()
    ensure_auto_icons()
    active_bgm = ensure_bgm(BGM_OUTPUT)

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

    font_brand = get_eng_font(44)
    font_sub = get_eng_font(22)
    font_trust = get_eng_font(20)
    font_badge = get_dev_font(23)
    font_part_tag = get_dev_font(22)
    font_title = get_dev_font(36)
    font_h2 = get_dev_font(32)
    font_body = get_dev_font(46)
    font_label = get_dev_font(26)
    font_hook_alert = get_dev_font(30)

    # 100% Devanagari Hindi font to prevent tofu boxes [▯▯▯▯]
    font_wa_hin = get_dev_font(32)
    font_wa_num = get_eng_font(30)

    font_cta = get_eng_font(30)
    font_cta_dev = get_dev_font(30)
    font_opt_eng = get_eng_font(36)
    font_opt_hin = get_dev_font(34)

    def draw_base(draw_obj):
        draw_obj.rounded_rectangle([45, 50, 1035, 1710], radius=32, fill="#0B132B", outline="#1E293B", width=3)
        draw_obj.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        draw_obj.text((80, 130), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)

        draw_obj.rounded_rectangle([630, 80, 1000, 132], radius=16, fill="#064E3B", outline="#10B981", width=2)
        draw_obj.text((655, 93), "✓ 100% OFFICIAL SYLLABUS", fill="#D1FAE5", font=font_trust)

    def draw_sleek_whatsapp_strip(draw_obj):
        draw_obj.rounded_rectangle([80, 345, 1000, 475], radius=18, fill="#064E3B", outline="#34D399", width=2)
        draw_obj.text((110, 362), "GDS to MTS • Postman • Mail Guard • P.A.", fill="#FDE047", font=font_wa_num)
        draw_obj.text((110, 412), "कोर्स व फ्री टेस्ट हेतु व्हाट्सएप: 8989971379", fill="#FFFFFF", font=font_wa_hin)

    def draw_footer_cta(draw_obj):
        draw_obj.rounded_rectangle([80, 1580, 1000, 1680], radius=22, fill="#E11D48")
        draw_obj.text((120, 1605), "पूरी तैयारी के लिए फॉलो करें:", fill="#FFFFFF", font=font_cta_dev)
        draw_obj.text((580, 1605), "@POSTAL_WALA", fill="#FFFFFF", font=font_cta)

    def paste_safe_asset(base_img, path, pos, size=(300, 420)):
        if os.path.exists(path):
            try:
                ic = Image.open(path).convert("RGBA")
                ic = ic.resize(size, RESAMPLE_MODE)
                base_img.paste(ic, pos, ic)
            except Exception:
                pass

    badge_text = f"पीओ गाइड भाग 1  •  क्लॉज {script_data['clause_no']}"
    part_tag_text = f"भाग {script_data['part_no']}/{script_data['total_parts']}"
    clause_title = script_data['clause_name']
    visual_hook_text = script_data.get("visual_hook_badge", "🔥 लिख कर ले लो! इस रील से 2 नंबर पक्के")

    sentences = [script_data["sen1"], script_data["sen2"], script_data["sen3"]]
    slide_filenames = []

    # Slides 1 to 3
    for idx, sentence in enumerate(sentences, 1):
        img = Image.new("RGB", (1080, 1920), color="#060A17")
        d = ImageDraw.Draw(img)
        draw_base(d)

        # Title Card (y: 175 to 320)
        d.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
        
        # Left Badge: Clause Number (Golden Pill)
        d.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
        d.text((120, 198), badge_text, fill="#000000", font=font_badge)

        # Right Badge: Part Tag (Electric Blue Pill)
        d.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8", outline="#60A5FA", width=1)
        d.text((845, 198), part_tag_text, fill="#FFFFFF", font=font_part_tag)

        # Clean Single Title Line (Bold White)
        d.text((105, 255), clause_title, fill="#FFFFFF", font=font_title)

        draw_sleek_whatsapp_strip(d)

        # Main Teaching Card (y: 505 to 1550)
        d.rounded_rectangle([80, 505, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)

        # Slide 1 Visual Hook Alert Card
        if idx == 1:
            d.rounded_rectangle([110, 530, 970, 600], radius=14, fill="#991B1B", outline="#FBBF24", width=2)
            d.text((130, 545), visual_hook_text, fill="#FEF08A", font=font_hook_alert)

            d.rounded_rectangle([110, 620, 450, 670], radius=10, fill="#0B132B")
            d.text((125, 630), "परीक्षा बिंदु #1:", fill="#38BDF8", font=font_label)

            wrapped_text = textwrap.fill(sentence, width=22)
            d.multiline_text((115, 695), wrapped_text, fill="#F8FAFC", font=font_body, spacing=20)
            paste_safe_asset(img, BOOK_3D_PATH, pos=(390, 1100), size=(300, 410))
        else:
            d.rounded_rectangle([110, 535, 470, 588], radius=12, fill="#0B132B")
            d.text((130, 545), f"परीक्षा बिंदु #{idx}:", fill="#38BDF8", font=font_label)

            wrapped_text = textwrap.fill(sentence, width=21)
            d.multiline_text((115, 625), wrapped_text, fill="#F8FAFC", font=font_body, spacing=24)
            paste_safe_asset(img, POSTBOX_3D_PATH, pos=(390, 1080), size=(300, 420))

        draw_footer_cta(d)
        fname = f"slide_{idx}.png"
        img.save(fname)
        slide_filenames.append(fname)

    # Slide 4: Quiz
    img_quiz = Image.new("RGB", (1080, 1920), color="#060A17")
    dq = ImageDraw.Draw(img_quiz)
    draw_base(dq)

    dq.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#FBBF24", width=2)
    
    dq.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    dq.text((120, 198), badge_text, fill="#000000", font=font_badge)

    dq.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8", outline="#60A5FA", width=1)
    dq.text((845, 198), part_tag_text, fill="#FFFFFF", font=font_part_tag)

    dq.text((105, 255), "परीक्षा क्विज़: सही उत्तर कमेंट करें!", fill="#FDE047", font=font_title)

    draw_sleek_whatsapp_strip(dq)

    dq.rounded_rectangle([80, 505, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)

    dq.rounded_rectangle([110, 530, 330, 575], radius=12, fill="#0B132B")
    dq.text((120, 538), "आज का सवाल:", fill="#FBBF24", font=font_h2)

    q_wrapped = textwrap.fill(script_data["question"], width=23)
    dq.multiline_text((110, 595), q_wrapped, fill="#F8FAFC", font=font_h2, spacing=10)

    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    oy = 745
    for idx, opt in enumerate(opts):
        dq.rounded_rectangle([110, oy, 970, oy + 105], radius=16, fill="#0B132B", outline="#38BDF8", width=2)
        opt_badge = f"{chr(65+idx)})"
        dq.text((135, oy + 28), opt_badge, fill="#38BDF8", font=font_opt_eng)
        dq.text((205, oy + 28), textwrap.fill(opt, width=24), fill="#FFFFFF", font=font_opt_hin)
        oy += 125

    # Bottom Engagement Pill
    dq.rounded_rectangle([110, 1370, 970, 1490], radius=18, fill="#0B132B", outline="#F59E0B", width=2)
    dq.text((220, 1395), "✍️ अपना सही जवाब अभी कमेंट करें!", fill="#FDE047", font=font_h2)
    dq.text((195, 1445), "देखते हैं कितने साथी सही उत्तर देते हैं!", fill="#94A3B8", font=font_badge)

    paste_safe_asset(img_quiz, QUIZ_3D_PATH, pos=(815, 520), size=(150, 195))

    draw_footer_cta(dq)
    img_quiz.save("slide_4.png")
    slide_filenames.append("slide_4.png")

    inputs = []
    filter_parts = ""
    for i, fname in enumerate(slide_filenames):
        inputs.extend(["-i", fname])
        safe_dur = max(1.0, durations[i])
        filter_parts += f"[{i}:v]loop=loop=-1:size=1:start=0,trim=duration={safe_dur}[v{i}]; "

    concat_str = "".join([f"[v{i}]" for i in range(len(slide_filenames))])
    video_filter = f"{filter_parts}{concat_str}concat=n={len(slide_filenames)}:v=1:a=0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p[v]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-i", audio_file
    ]

    # Robust Dual-Stream Audio Mixing with Auto-BGM
    voice_idx = len(slide_filenames)
    if active_bgm and os.path.exists(active_bgm) and os.path.getsize(active_bgm) > 2000:
        bgm_idx = voice_idx + 1
        cmd.extend(["-stream_loop", "-1", "-i", active_bgm])
        full_filter = f"{video_filter}; [{voice_idx}:a]aresample=48000,volume=1.0[v_aud]; [{bgm_idx}:a]aresample=48000,volume=0.08[bgm_aud]; [v_aud][bgm_aud]amix=inputs=2:duration=first:dropout_transition=2[a]"
        cmd.extend([
            "-filter_complex", full_filter,
            "-map", "[v]",
            "-map", "[a]"
        ])
    else:
        cmd.extend([
            "-filter_complex", video_filter,
            "-map", "[v]",
            "-map", f"{voice_idx}:a"
        ])

    cmd.extend([
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
    ])

    subprocess.run(cmd, check=True)
    print("✅ Meta-Optimized 1080x1920 Reel Created with High-Retention BGM Mix.", flush=True)

# --- Bulletproof Resumable Instagram Upload ---
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
            time.sleep(25)

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

    if not script_data.get("voiceover") or len(script_data["voiceover"].strip()) < 30:
        hook_obj = VIRAL_HOOKS[state.get("hook_index", 0) % len(VIRAL_HOOKS)]
        script_data["voiceover"] = f"{hook_obj['voice']} आज का महत्वपूर्ण प्रश्न है: क्लॉज {state.get('clause_no', 55)} का संबंध किससे है? इसका सही उत्तर जानने के लिए वीडियो अंत तक समझें! विभागीय परीक्षा की पक्की तैयारी के लिए पोस्टल वाला को फॉलो करें और फ्री मॉक टेस्ट के लिए स्क्रीन पर दिए नंबर पर व्हाट्सएप करें!"

    asyncio.run(generate_voice(script_data["voiceover"], AUDIO_OUTPUT))
    create_video_ffmpeg(script_data, AUDIO_OUTPUT, OUTPUT_VIDEO)
    post_reel_to_instagram_multipart(OUTPUT_VIDEO, script_data.get("caption", ""))
    advance_progress_state(state, script_data)
