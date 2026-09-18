import os
import glob
import json
import time
import asyncio
import subprocess
import requests
import textwrap
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
OUTPUT_VIDEO = "final_reel.mp4"
VOICE_NAME = "hi-IN-SwaraNeural"

# Assets Directory
ASSETS_DIR = "assets"
BOOK_3D_PATH = os.path.join(ASSETS_DIR, "3d_book.png")
POSTBOX_3D_PATH = os.path.join(ASSETS_DIR, "3d_postbox.png")
QUIZ_3D_PATH = os.path.join(ASSETS_DIR, "3d_quiz.png")

# Cross-version Pillow Compatibility
RESAMPLE_MODE = getattr(Image, "Resampling", Image).LANCZOS

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

# --- 100% Offline 3D Graphic Renderer ---
def ensure_auto_icons():
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # 1. 3D PO Guide Rulebook (Slide 1)
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

    # 2. 3D Red Pillar Postbox (Slide 2 & 3)
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

    # 3. 3D Golden Trophy (Slide 4)
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

# --- State Management ---
def load_progress_state():
    state = {"clause_no": 55, "current_part": 2, "total_parts": 3}
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

# --- Script Generation With Deep Rule Explanation ---
def generate_clause_script(state):
    current_clause = state.get("clause_no", 55)
    current_part = state.get("current_part", 2)

    clause_info = POSTAL_CLAUSE_CATALOG.get(current_clause, POSTAL_CLAUSE_CATALOG[55])
    clause_name = clause_info["name"]
    total_parts = clause_info["total_parts"]
    part_focus = clause_info.get(f"part_{current_part}_focus", clause_info.get("part_1_focus", ""))

    fallback_data = {
        "clause_no": current_clause,
        "clause_name": clause_name,
        "part_no": current_part,
        "total_parts": total_parts,
        "sen1": f"भारतीय डाक विभाग के नियमों के अनुसार {clause_name} का विस्तृत विवरण डाक घर गाइड भाग 1 के क्लॉज {current_clause} में निर्धारित किया गया है।",
        "sen2": f"इस नियम के मुख्य कानूनी प्रावधान के अंतर्गत {part_focus}",
        "sen3": "विभागीय परीक्षाओं जैसे MTS, Postman और PA में इस क्लॉज के शुल्क, समय सीमा और संचालन शर्तों पर सीधे प्रश्न पूछे जाते हैं।",
        "question": f"डाक घर गाइड भाग 1 के क्लॉज {current_clause} का संबंध मुख्य रूप से किससे है?",
        "opt_a": clause_name,
        "opt_b": "डाक विभाग का बजट",
        "opt_c": "मनीऑर्डर नियम",
        "opt_d": "इनमें से कोई नहीं",
        "correct": "A",
        "voiceover": f"जीडीएस से प्रमोशन लेने के लिए आपका स्वागत है पोस्टल वाला में! आज का महत्वपूर्ण प्रश्न है: क्लॉज {current_clause}, {clause_name} का संबंध किससे है? इसका सही उत्तर जानने के लिए वीडियो में अंत तक बने रहें! डाक विभाग के नियमानुसार {part_focus} विभागीय परीक्षा की दृष्टि से यह नियम अत्यंत महत्वपूर्ण है क्योंकि इसमें से सीधे ऑब्जेक्टिव प्रश्न पूछे जाते हैं। तो दोस्तों, इसका सही उत्तर कमेंट्स में जरूर बताएं! फ्री मॉक टेस्ट के लिए स्क्रीन पर दिए नंबर पर व्हाट्सएप करें, और प्रमोशन पाने के लिए पोस्टल वाला को फॉलो करना न भूलें!",
        "caption": f"जीडीएस से प्रमोशन के लिए पीओ गाइड भाग 1 क्लॉज {current_clause} संपूर्ण विश्लेषण #PostalWala #GDS_to_MTS #PostmanExam #POGuidePart1 #Clause{current_clause}"
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

    GOAL:
    We saved time by removing the spoken WhatsApp promotion. Dedicate 100% of the remaining video time to deep, authoritative postal rule teaching so students understand the concept completely.

    RULES:
    1. Flawless Devanagari Hindi. Complete professional sentences.
    2. Write exactly 3 authoritative teaching sentences (SEN1, SEN2, SEN3), each ~24-28 words long, clearly explaining the rule, official conditions, fees, and exam traps.
    3. The voiceover MUST be strictly between 118 and 125 words total (natural, deep-teaching pace ~51-53 seconds).
    4. Follow this voiceover layout strictly:
       - OPENING HOOK (Exact words): "जीडीएस से प्रमोशन लेने के लिए आपका स्वागत है पोस्टल वाला में!"
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
    VOICEOVER: [Exact voiceover text strictly 118 to 125 words]
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
    except Exception as e:
        print(f"⚠️ Groq API warning: {e}. Safe fallback active.", flush=True)

    return fallback_data

# --- Automatic Intelligent Clause Progression ---
def advance_progress_state(state, data):
    cur_part = data.get("part_no", state.get("current_part", 1))
    total_parts = data.get("total_parts", state.get("total_parts", 2))

    if cur_part < total_parts:
        state["current_part"] = cur_part + 1
        state["total_parts"] = total_parts
    else:
        cur_clause = state.get("clause_no")

        # 1. Clause 56 pura hote hi seedhe Clause 5 par jump
        if cur_clause == 56:
            state["clause_no"] = 5
        # 2. Clause 54 pura hote hi 55-56 skip karke seedhe Clause 57 par jump
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

# --- Voice Generation ---
async def generate_voice(text, filename="voice.mp3"):
    communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+0%")
    await communicate.save(filename)

def get_audio_duration(audio_file):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_file]
    output = subprocess.check_output(cmd).decode().strip()
    return float(output)

# --- Video Engine With High-Impact Middle WhatsApp Banner ---
def create_video_ffmpeg(script_data, audio_file="voice.mp3", output_video="final_reel.mp4"):
    ensure_fonts()
    ensure_auto_icons()

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

    font_brand = get_eng_font(46)
    font_sub = get_eng_font(24)
    font_badge = get_dev_font(24)
    font_title = get_dev_font(34)
    font_h2 = get_dev_font(32)
    font_body = get_dev_font(40)
    font_label = get_dev_font(26)
    font_trust = get_eng_font(20)

    # High-impact fonts for WhatsApp Middle Banner
    font_wa_eng = get_eng_font(32)
    font_wa_dev = get_dev_font(36)

    font_cta_hin = get_dev_font(28)
    font_cta_eng = get_eng_font(28)
    font_opt_eng = get_eng_font(34)
    font_opt_hin = get_dev_font(32)

    def draw_base(draw_obj):
        draw_obj.rounded_rectangle([45, 50, 1035, 1860], radius=30, fill="#1E293B", outline="#E11D48", width=4)
        draw_obj.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        draw_obj.text((80, 130), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)

        draw_obj.rounded_rectangle([630, 80, 1000, 130], radius=16, fill="#065F46", outline="#34D399", width=2)
        draw_obj.text((655, 93), "✓ 100% OFFICIAL SYLLABUS", fill="#ECFDF5", font=font_trust)

    # High-impact Middle Green Banner (Height 150px)
    def draw_middle_whatsapp_banner(draw_obj):
        draw_obj.rounded_rectangle([80, 320, 1000, 470], radius=20, fill="#15803D", outline="#22C55E", width=3)
        draw_obj.text((110, 338), "GDS to MTS | Postman | Mail Guard | P.A.", fill="#FEF08A", font=font_wa_eng)
        draw_obj.text((110, 396), "कोर्स व टेस्ट हेतु WhatsApp: 8989971379", fill="#FFFFFF", font=font_wa_dev)

    # Clean Red Follow Button in Safe Bottom Zone
    def draw_footer_cta(draw_obj):
        draw_obj.rounded_rectangle([80, 1460, 1000, 1550], radius=20, fill="#E11D48")
        draw_obj.text((120, 1485), "पूरी तैयारी के लिए फॉलो करें:", fill="#FFFFFF", font=font_cta_hin)
        draw_obj.text((610, 1485), "@POSTAL_WALA", fill="#FFFFFF", font=font_cta_eng)

    def paste_safe_asset(base_img, path, pos, size=(240, 335)):
        if os.path.exists(path):
            try:
                ic = Image.open(path).convert("RGBA")
                ic = ic.resize(size, RESAMPLE_MODE)
                base_img.paste(ic, pos, ic)
            except Exception:
                pass

    badge_text = f"पीओ गाइड भाग 1  •  क्लॉज {script_data['clause_no']}"
    clause_title = f"{script_data['clause_name']} (भाग {script_data['part_no']}/{script_data['total_parts']})"

    sentences = [script_data["sen1"], script_data["sen2"], script_data["sen3"]]
    slide_filenames = []

    # Slides 1 to 3
    for idx, sentence in enumerate(sentences, 1):
        img = Image.new("RGB", (1080, 1920), color="#0F172A")
        d = ImageDraw.Draw(img)
        draw_base(d)

        d.rounded_rectangle([80, 175, 1000, 305], radius=18, fill="#0F172A", outline="#38BDF8", width=2)
        d.rounded_rectangle([105, 188, 590, 230], radius=10, fill="#F59E0B")
        d.text((120, 195), badge_text, fill="#000000", font=font_badge)
        d.text((110, 240), textwrap.fill(clause_title, width=28), fill="#FFFFFF", font=font_title)

        draw_middle_whatsapp_banner(d)

        d.rounded_rectangle([80, 490, 1000, 1420], radius=22, fill="#0F172A")
        d.text((110, 510), "विस्तृत नियम विश्लेषण:", fill="#FBBF24", font=font_h2)

        d.rounded_rectangle([110, 560, 970, 1390], radius=20, fill="#1E293B", outline="#38BDF8", width=2)
        d.text((140, 585), f"महत्वपूर्ण परीक्षा बिंदु #{idx}:", fill="#38BDF8", font=font_label)

        wrapped_text = textwrap.fill(sentence, width=23)
        d.multiline_text((140, 650), wrapped_text, fill="#F8FAFC", font=font_body, spacing=16)

        if idx == 1:
            paste_safe_asset(img, BOOK_3D_PATH, pos=(710, 1040), size=(240, 335))
        else:
            paste_safe_asset(img, POSTBOX_3D_PATH, pos=(710, 1040), size=(240, 335))

        draw_footer_cta(d)
        fname = f"slide_{idx}.png"
        img.save(fname)
        slide_filenames.append(fname)

    # Slide 4: Quiz
    img_quiz = Image.new("RGB", (1080, 1920), color="#0F172A")
    dq = ImageDraw.Draw(img_quiz)
    draw_base(dq)

    dq.rounded_rectangle([80, 175, 1000, 305], radius=18, fill="#0F172A", outline="#FBBF24", width=2)
    dq.rounded_rectangle([105, 188, 590, 230], radius=10, fill="#F59E0B")
    dq.text((120, 195), badge_text, fill="#000000", font=font_badge)
    dq.text((110, 240), "परीक्षा क्विज़: सही उत्तर कमेंट करें!", fill="#FFFFFF", font=font_title)

    draw_middle_whatsapp_banner(dq)

    dq.rounded_rectangle([80, 490, 1000, 1420], radius=22, fill="#0F172A")
    dq.text((110, 510), "आज का सवाल:", fill="#FBBF24", font=font_h2)

    q_wrapped = textwrap.fill(script_data["question"], width=23)
    dq.multiline_text((110, 560), q_wrapped, fill="#F8FAFC", font=font_h2, spacing=10)

    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    oy = 745
    for idx, opt in enumerate(opts):
        dq.rounded_rectangle([110, oy, 970, oy + 95], radius=16, fill="#1E293B", outline="#38BDF8", width=2)
        opt_badge = f"{chr(65+idx)})"
        dq.text((135, oy + 25), opt_badge, fill="#38BDF8", font=font_opt_eng)
        dq.text((205, oy + 25), textwrap.fill(opt, width=24), fill="#FFFFFF", font=font_opt_hin)
        oy += 115

    paste_safe_asset(img_quiz, QUIZ_3D_PATH, pos=(810, 500), size=(150, 200))

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
    print("✅ Meta-Optimized 1080x1920 Reel Created with Deep-Teaching Script & Assets.", flush=True)

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

    asyncio.run(generate_voice(script_data["voiceover"], AUDIO_OUTPUT))
    create_video_ffmpeg(script_data, AUDIO_OUTPUT, OUTPUT_VIDEO)
    post_reel_to_instagram_multipart(OUTPUT_VIDEO, script_data.get("caption", ""))
    advance_progress_state(state, script_data)
