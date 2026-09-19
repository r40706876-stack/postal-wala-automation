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

# --- Zero Box Font Sanitizer ---
def sanitize_devanagari(text):
    if not text:
        return ""
    clean = re.sub(r'[^\u0900-\u097F\u0020-\u007E\u2010-\u2015\u0964\u0965\n]', '', text)
    return clean.strip()

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
        "नित्य वर्ष": "वित्तीय वर्ष"
    }
    for bad_w, good_w in replacements.items():
        text = text.replace(bad_w, good_w)
    return sanitize_devanagari(text)

def extract_field_block(text, field_name, next_fields):
    pattern = r"(?:^|\n)\s*(?:\*\*)?" + re.escape(field_name) + r"(?:\*\*)?\s*:\s*(.*?)(?=(?:\n\s*(?:\*\*)?(?:" + "|".join(next_fields) + r")(?:\*\*)?\s*:)|$)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        val = re.sub(r"^[\"\'`]+|[\"\'`]+$", "", val).strip()
        val = " ".join(val.split())
        return val
    return None

# --- Native Pillow Vector Emojis (Zero Tofu/Dabba) ---
def draw_visual_emoji(draw_obj, emoji_type, x, y, size=36):
    cx = x + size // 2
    cy = y + size // 2

    if emoji_type == "cross":
        draw_obj.ellipse([x, y, x + size, y + size], fill="#DC2626")
        pad = size // 4
        draw_obj.line([(x + pad, y + pad), (x + size - pad, y + size - pad)], fill="#FFFFFF", width=4)
        draw_obj.line([(x + pad, y + size - pad), (x + size - pad, y + pad)], fill="#FFFFFF", width=4)

    elif emoji_type == "check":
        draw_obj.ellipse([x, y, x + size, y + size], fill="#16A34A")
        draw_obj.line([(x + size // 4, cy), (cx - 2, y + size - size // 4)], fill="#FFFFFF", width=4)
        draw_obj.line([(cx - 2, y + size - size // 4), (x + size - size // 4, y + size // 3)], fill="#FFFFFF", width=4)

    elif emoji_type == "warning":
        pts = [(cx, y + 2), (x + size - 2, y + size - 4), (x + 2, y + size - 4)]
        draw_obj.polygon(pts, fill="#F59E0B")
        draw_obj.line([(cx, y + 10), (cx, y + size - 14)], fill="#000000", width=3)
        draw_obj.ellipse([cx - 2, y + size - 10, cx + 2, y + size - 6], fill="#000000")

    elif emoji_type == "question":
        draw_obj.ellipse([x, y, x + size, y + size], fill="#1D4ED8")
        draw_obj.arc([x + 10, y + 8, x + size - 10, y + size - 14], start=180, end=0, fill="#FFFFFF", width=3)
        draw_obj.line([(cx, y + 18), (cx, y + size - 12)], fill="#FFFFFF", width=3)
        draw_obj.ellipse([cx - 2, y + size - 8, cx + 2, y + size - 4], fill="#FFFFFF")

    elif emoji_type == "postbox":
        draw_obj.rounded_rectangle([x + 4, y + 4, x + size - 4, y + size - 4], radius=6, fill="#DC2626", outline="#FBBF24", width=2)
        draw_obj.rectangle([x + 8, y + 10, x + size - 8, y + 15], fill="#0F172A")

def draw_vector_arrow(draw_obj, center_x, start_y, length=30):
    end_y = start_y + length
    draw_obj.line([(center_x, start_y), (center_x, end_y)], fill="#38BDF8", width=4)
    draw_obj.polygon([(center_x - 8, end_y - 10), (center_x + 8, end_y - 10), (center_x, end_y + 2)], fill="#38BDF8")

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
    mp3_files = sorted(glob.glob(os.path.join(ASSETS_DIR, "*.mp3")))
    if mp3_files:
        return mp3_files[state_index % len(mp3_files)]

    cached_bgm = os.path.join(ASSETS_DIR, f"bgm_{state_index % 3}.mp3")
    if os.path.exists(cached_bgm) and os.path.getsize(cached_bgm) > 10000:
        return cached_bgm

    lofi_urls = [
        "https://upload.wikimedia.org/wikipedia/commons/e/eb/Bensound-relaxing.mp3",
        "https://upload.wikimedia.org/wikipedia/commons/4/4b/Bensound-slowmotion.mp3"
    ]
    try:
        r = requests.get(lofi_urls[state_index % len(lofi_urls)], timeout=12)
        if r.status_code == 200:
            with open(cached_bgm, "wb") as f:
                f.write(r.content)
            return cached_bgm
    except Exception:
        pass

    try:
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "aevalsrc=exprs='0.15*sin(2*PI*65*t)*exp(-3*mod(t,0.5))+0.10*sin(2*PI*261.63*t)':s=48000:d=70",
            "-af", "volume=1.5",
            "-c:a", "libmp3lame", "-b:a", "192k", bgm_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return bgm_path
    except Exception:
        return None

# --- State Management (Hard-Locked to Clause 6, Part 1) ---
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

# --- Script Generation Engine (Groq AI with Full Catalog Fallback) ---
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
    SEN1: [Core rule explanation, ~25 words]
    SEN2: [Key conditions/working hours, ~25 words]
    SEN3: [Official exception or trap, ~25 words]
    OPT_A: [Option A]
    OPT_B: [Option B]
    OPT_C: [Option C]
    OPT_D: [Option D]
    """
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"}
        payload = {"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 600}
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
        print(f"⚠️ Groq API note: {e}, using master catalog fallback.")

    return fallback_data

# --- The 100% Locked Viral Segment Structure ---
def build_segments(script_data):
    q_txt = script_data["question"]
    hook_v = script_data["hook_voice"]
    hook_b = script_data["visual_hook_badge"]

    # Segment 1: Hook + Shuru me Prashn
    s1_voice = f"{hook_v} आज का महत्वपूर्ण प्रश्न है: {q_txt} इसका सही उत्तर जानने के लिए वीडियो में अंत तक बने रहें!"
    s1_text = f"आज का महत्वपूर्ण सवाल:\n{q_txt}\n\nसही उत्तर वीडियो में अंत तक समझें!"

    # Segment 2: Rule Detail 1
    s2_voice = f"आइए नियम को समझें। {script_data['sen1']} {script_data['sen2']}"
    s2_text = f"{script_data['sen1']}\n\n{script_data['sen2']}"

    # Segment 3: Rule Detail 2 / Exception
    s3_voice = f"विभागीय परीक्षा की दृष्टि से ध्यान दें! {script_data['sen3']}"
    s3_text = f"परीक्षा विशेष बिंदु:\n\n{script_data['sen3']}"

    # Segment 4: Options bolna BAND - Direct Question, Comment CTA aur Ending Follow Call
    quiz_voice = f"तो साथियों, {q_txt} इसका सही उत्तर आप सभी कमेंट बॉक्स में दीजिए! फ्री मॉक टेस्ट के लिए स्क्रीन पर दिए नंबर पर व्हाट्सएप करें, और अपना विभागीय परीक्षा निकालने के लिए पोस्टल वाला को फॉलो करना न भूलें!"

    return [
        {
            "audio": s1_voice,
            "screen": s1_text,
            "hook_badge": hook_b,
            "label": "आज का प्रश्न",
            "emoji": "question",
            "is_hook": True
        },
        {
            "audio": s2_voice,
            "screen": s2_text,
            "label": "नियम विश्लेषण #1",
            "emoji": "postbox",
            "is_hook": False
        },
        {
            "audio": s3_voice,
            "screen": s3_text,
            "label": "परीक्षा अपवाद #2",
            "emoji": "warning",
            "is_hook": False
        },
        {
            "audio": quiz_voice,
            "question": q_txt,
            "opt_a": script_data["opt_a"],
            "opt_b": script_data["opt_b"],
            "opt_c": script_data["opt_c"],
            "opt_d": script_data["opt_d"],
            "label": "परीक्षा क्विज़"
        }
    ]

async def generate_segment_audio(text, outfile):
    if os.path.exists(outfile):
        try: os.remove(outfile)
        except Exception: pass
    communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+0%")
    await communicate.save(outfile)

def get_audio_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    return float(subprocess.check_output(cmd).decode().strip())

# --- Precise Video Rendering Engine (Zero Text Overflow) ---
def render_and_sync_video(script_data, segments, output_video):
    ensure_fonts()
    ensure_auto_icons()
    state = load_progress_state()
    active_bgm = ensure_bgm(BGM_OUTPUT, state.get("hook_index", 0))

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

    def draw_common_ui(d, title_text):
        d.rounded_rectangle([45, 50, 1035, 1710], radius=32, fill="#0B132B", outline="#1E293B", width=3)
        d.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        d.text((80, 130), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)

        d.rounded_rectangle([630, 80, 1000, 132], radius=16, fill="#064E3B", outline="#10B981", width=2)
        d.text((655, 93), "100% OFFICIAL SYLLABUS", fill="#D1FAE5", font=font_trust)

        d.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
        d.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
        d.text((120, 198), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)

        d.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
        d.text((845, 198), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)

        d.text((105, 255), sanitize_devanagari(title_text), fill="#FFFFFF", font=font_title)

        d.rounded_rectangle([80, 345, 1000, 475], radius=18, fill="#064E3B", outline="#34D399", width=2)
        d.text((110, 362), "GDS to MTS • Postman • Mail Guard • P.A.", fill="#FDE047", font=font_wa_num)
        d.text((110, 412), "कोर्स व फ्री टेस्ट हेतु व्हाट्सएप: 8989971379", fill="#FFFFFF", font=font_wa_hin)

        d.rounded_rectangle([80, 1580, 1000, 1680], radius=22, fill="#E11D48")
        d.text((120, 1605), "पूरी तैयारी के लिए फॉलो करें:", fill="#FFFFFF", font=font_cta_dev)
        d.text((580, 1605), "@POSTAL_WALA", fill="#FFFFFF", font=font_cta)

    slide_videos = []

    for idx, seg in enumerate(segments):
        audio_seg_file = f"seg_audio_{idx}.mp3"
        asyncio.run(generate_segment_audio(seg["audio"], audio_seg_file))
        seg_dur = get_audio_duration(audio_seg_file)

        img = Image.new("RGB", (1080, 1920), color="#060A17")
        d = ImageDraw.Draw(img)
        draw_common_ui(d, script_data["clause_name"] if idx < 3 else "परीक्षा क्विज़: उत्तर कमेंट करें")

        # Main Teaching Card
        d.rounded_rectangle([80, 505, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)

        if idx < 3:
            sy = 535
            if seg.get("is_hook"):
                d.rounded_rectangle([110, sy, 970, sy + 70], radius=14, fill="#991B1B", outline="#FBBF24", width=2)
                draw_visual_emoji(d, "warning", 125, sy + 16, size=36)
                d.text((175, sy + 15), sanitize_devanagari(seg["hook_badge"]), fill="#FEF08A", font=font_hook)
                sy += 90

            d.rounded_rectangle([110, sy, 480, sy + 50], radius=10, fill="#0B132B")
            draw_visual_emoji(d, seg.get("emoji", "check"), 120, sy + 8, size=34)
            d.text((165, sy + 10), seg["label"], fill="#38BDF8", font=font_label)

            clean_txt = sanitize_devanagari(seg["screen"])
            wrapped = textwrap.fill(clean_txt, width=24)
            d.multiline_text((115, sy + 75), wrapped, fill="#F8FAFC", font=font_body, spacing=16)

            draw_vector_arrow(d, center_x=540, start_y=sy + 360, length=40)

            asset_path = BOOK_3D_PATH if idx == 0 else POSTBOX_3D_PATH
            if os.path.exists(asset_path):
                ic = Image.open(asset_path).convert("RGBA").resize((280, 360), RESAMPLE_MODE)
                img.paste(ic, (400, 1120), ic)
        else:
            # Slide 4: Quiz
            d.rounded_rectangle([110, 530, 360, 575], radius=12, fill="#0B132B")
            draw_visual_emoji(d, "question", 120, 536, size=32)
            d.text((160, 538), "आज का सवाल:", fill="#FBBF24", font=font_h2)

            q_wrapped = textwrap.fill(sanitize_devanagari(seg["question"]), width=24)
            d.multiline_text((110, 595), q_wrapped, fill="#F8FAFC", font=font_h2, spacing=8)

            opts = [seg["opt_a"], seg["opt_b"], seg["opt_c"], seg["opt_d"]]
            oy = 720
            for o_idx, opt in enumerate(opts):
                d.rounded_rectangle([110, oy, 970, oy + 85], radius=14, fill="#0B132B", outline="#38BDF8", width=2)
                d.text((135, oy + 24), f"{chr(65+o_idx)})", fill="#38BDF8", font=font_h2)
                opt_clean = textwrap.fill(sanitize_devanagari(opt), width=22)
                d.text((205, oy + 24), opt_clean, fill="#FFFFFF", font=font_opt)
                oy += 105

            d.rounded_rectangle([110, 1370, 970, 1490], radius=18, fill="#0B132B", outline="#F59E0B", width=2)
            draw_visual_emoji(d, "check", 130, 1405, size=40)
            d.text((185, 1410), "अपना सही जवाब अभी कमेंट करें!", fill="#FDE047", font=font_h2)

        slide_img = f"slide_seg_{idx}.png"
        img.save(slide_img)

        part_vid = f"part_{idx}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", slide_img,
            "-i", audio_seg_file,
            "-c:v", "libx264", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-t", str(seg_dur),
            part_vid
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        slide_videos.append(part_vid)

    with open("concat_list.txt", "w") as f:
        for sv in slide_videos:
            f.write(f"file '{sv}'\n")

    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat_list.txt",
        "-c", "copy", "temp_merged.mp4"
    ]
    subprocess.run(cmd_concat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if active_bgm and os.path.exists(active_bgm):
        mix_cmd = [
            "ffmpeg", "-y",
            "-i", "temp_merged.mp4",
            "-stream_loop", "-1", "-i", active_bgm,
            "-filter_complex", "[0:a]volume=1.0[v_aud]; [1:a]volume=0.35[bgm]; [v_aud][bgm]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
            output_video
        ]
        subprocess.run(mix_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        os.rename("temp_merged.mp4", output_video)

    print(f"✅ Reel created successfully from Clause 6: {output_video}")

# --- Robust Resumable Instagram Upload ---
def post_reel_to_instagram_multipart(video_file, caption, max_container_attempts=3):
    access_token = os.getenv("IG_ACCESS_TOKEN")
    user_id = os.getenv("IG_USER_ID")

    if not access_token or not user_id:
        print("⚠️ IG credentials missing, skipping upload.")
        return

    last_error = None
    for container_attempt in range(1, max_container_attempts + 1):
        try:
            init_url = GRAPH_API_BASE + str(user_id).strip() + "/media"
            data = {"media_type": "REELS", "upload_type": "resumable", "caption": caption, "access_token": access_token}
            r = requests.post(init_url, data=data, timeout=60)
            if r.status_code != 200:
                raise RuntimeError(f"Init fail: {r.text}")

            res_json = r.json()
            video_id = res_json.get("id")
            upload_url = res_json.get("uri") or (RUPLOAD_BASE + str(video_id).strip())

            time.sleep(10)

            file_size = os.path.getsize(video_file)
            headers = {"Authorization": f"OAuth {access_token}", "offset": "0", "file_size": str(file_size), "Content-Type": "application/octet-stream"}

            with open(video_file, "rb") as vf:
                up_r = requests.post(upload_url, headers=headers, data=vf.read(), timeout=600)

            if up_r.status_code != 200 or not up_r.json().get("success"):
                raise RuntimeError(f"Upload fail: {up_r.text}")

            for _ in range(35):
                time.sleep(12)
                st_res = requests.get(GRAPH_API_BASE + str(video_id).strip(), params={"fields": "status_code", "access_token": access_token}, timeout=30).json()
                if st_res.get("status_code") == "FINISHED":
                    pub_res = requests.post(GRAPH_API_BASE + str(user_id).strip() + "/media_publish", data={"creation_id": video_id, "access_token": access_token}, timeout=30).json()
                    if "id" in pub_res:
                        print(f"🎉 Reel published successfully! Post ID: {pub_res['id']}")
                        return
                elif st_res.get("status_code") in ["ERROR", "EXPIRED"]:
                    raise RuntimeError(f"Status: {st_res.get('status_code')}")
        except Exception as e:
            last_error = str(e)
            time.sleep(20)

    print(f"⚠️ Upload notice: {last_error}")

if __name__ == "__main__":
    st = load_progress_state()
    script_data = generate_clause_script(st)
    segments = build_segments(script_data)
    render_and_sync_video(script_data, segments, OUTPUT_VIDEO)
    post_reel_to_instagram_multipart(OUTPUT_VIDEO, script_data.get("caption", ""))
    advance_progress_state(st)
