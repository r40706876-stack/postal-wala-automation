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
import shutil
from PIL import Image, ImageDraw, ImageFont
import edge_tts

# --- Environment Variables ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

STATE_FILE = "progress_state.json"
DEV_FONT_PATH = "NotoSansDevanagari-Bold.ttf"
OUTPUT_VIDEO = "final_reel.mp4"
BGM_OUTPUT = "bgm.mp3"
VOICE_NAME = "hi-IN-SwaraNeural"
REELS_DIR = "generated_reels"

# Assets Directory
ASSETS_DIR = "assets"
BOOK_3D_PATH = os.path.join(ASSETS_DIR, "3d_book.png")
POSTBOX_3D_PATH = os.path.join(ASSETS_DIR, "3d_postbox.png")
QUIZ_3D_PATH = os.path.join(ASSETS_DIR, "3d_quiz.png")

RESAMPLE_MODE = getattr(Image, "Resampling", Image).LANCZOS

# --- HIGH-RETENTION HOOKS ---
# Short hooks only. Avoid unsupported claims such as "90% people fail" or
# guaranteed marks/promotions. The hook creates a real challenge instead.
VIRAL_HOOKS = [
    {
        "voice": "5 सेकंड में बताइए — इस सवाल का सही जवाब क्या है?",
        "visual_badge": "5 सेकंड में सही जवाब बताओ"
    },
    {
        "voice": "Postal exam की तैयारी कर रहे हैं? पहले खुद इसका जवाब दीजिए.",
        "visual_badge": "पहले खुद जवाब दो"
    },
    {
        "voice": "ये सवाल आसान दिखता है… लेकिन एक शब्द पूरा जवाब बदल सकता है.",
        "visual_badge": "एक शब्द पर ध्यान दो"
    },
    {
        "voice": "बिना उत्तर देखे बताइए — A, B, C या D?",
        "visual_badge": "A / B / C / D ?"
    },
    {
        "voice": "रुकिए — पहले सवाल solve कीजिए, फिर अपना जवाब मिलाइए.",
        "visual_badge": "पहले Solve करो"
    },
    {
        "voice": "आज सिर्फ एक नियम: इसे समझ लिया तो अगला MCQ आसान लगेगा.",
        "visual_badge": "एक नियम • एक MCQ"
    }
]

# --- Master Catalog: Naturally Sized Parts (1 to 7 parts based on clause complexity) ---
POSTAL_CLAUSE_CATALOG = {
    1: {
        "name": "डाक विभाग का नियंत्रण व संगठन", "total_parts": 2,
        "part_1_focus": "संचार मंत्रालय के अधीन महानिदेशक (DG Posts) शीर्ष प्रशासनिक प्रमुख हैं और मुख्यालय डाक भवन नई दिल्ली में स्थित है।",
        "part_2_focus": "डाक सेवा बोर्ड (PSB) में एक चेयरमैन (सचिव डाक) और 6 पूर्णकालिक सदस्य होते हैं जो कार्मिक, प्रचालन व तकनीक का कार्य देखते हैं।"
    },
    2: {
        "name": "डाकघरों के प्रकार और श्रेणियां", "total_parts": 3,
        "part_1_focus": "डाकघर की 3 प्रमुख श्रेणियां हैं: प्रधान डाकघर (HO), उप डाकघर (SO) और शाखा डाकघर (BO)। HO मुख्य वित्तीय लेखा कार्यालय होता है।",
        "part_2_focus": "उप डाकघर (SO) प्रधान डाकघर के अधीन रहकर सभी प्रकार के लेन-देन करता है और दैनिक लेखा HO को प्रेषित करता है।",
        "part_3_focus": "ग्रामीण शाखा डाकघर (BO) के कार्य के घंटे न्यूनतम 4 घंटे और अधिकतम 5 घंटे प्रतिदिन निर्धारित किए जाते हैं।"
    },
    3: {
        "name": "रात्रि डाकघर के नियम", "total_parts": 3,
        "part_1_focus": "रात्रि डाकघर की स्थापना और कामकाज के घंटे रात 8:30 बजे तक बढ़ाने का विशेष अधिकार केवल महानिदेशक (DG) को है।",
        "part_2_focus": "रविवार और राष्ट्रीय डाक अवकाशों पर रात्रि डाकघर सुबह 10 से शाम 5 बजे तक केवल सीमित सेवाएं (रजिस्ट्री बुकिंग, टिकट विक्रय) देते हैं।",
        "part_3_focus": "रात्रि डाकघरों में रविवार और अवकाश के दिनों में कोई भी मनीऑर्डर भुगतान या बचत बैंक निकासी कार्य नहीं होता।"
    },
    4: {
        "name": "मोबाइल डाकघर की व्यवस्था", "total_parts": 2,
        "part_1_focus": "मोबाइल डाकघर बड़े शहरों में देर शाम तक सामान्य डाक व पार्सल बुकिंग की सुविधा जनता को उपलब्ध कराते हैं।",
        "part_2_focus": "मोबाइल डाकघर में मनीऑर्डर, बचत बैंक और बीमा का कोई भी वित्तीय कार्य करना पूर्णतः प्रतिबंधित होता है।"
    },
    5: {
        "name": "डाकघर के कामकाज के घंटे", "total_parts": 3,
        "part_1_focus": "सामान्य डाक टिकट बिक्री और डाक बुकिंग पूरे कार्य समय तक होती है, जबकि बचत बैंक और मनीऑर्डर का समय निर्धारित पहले समाप्त होता है।",
        "part_2_focus": "सार्वजनिक काउंटर बंद होने के बाद निर्धारित लेट फीस (Late Fee) का भुगतान करके ही डाक बुक की जा सकती है।",
        "part_3_focus": "शनिवार को सामान्य डाक लेन-देन के समय में कटौती के विभागीय नियम और नोटिस बोर्ड पर समय सारिणी प्रदर्शित करना।"
    },
    6: {
        "name": "रविवार और डाक अवकाश पर कार्य", "total_parts": 2,
        "part_1_focus": "रविवार और 16 राजपत्रित अवकाशों पर सामान्य डाकघर पूरी तरह बंद रहते हैं और कोई नियमित वितरण नहीं होता।",
        "part_2_focus": "रविवार और डाक अवकाशों पर केवल रात्रि डाकघर सुबह 10 से शाम 5 बजे तक कार्य करते हैं, पर कोई मनीऑर्डर या बचत बैंक कार्य नहीं होता।"
    },
    7: {
        "name": "डाक टिकटों और लेखन-सामग्री का विक्रय", "total_parts": 2,
        "part_1_focus": "प्रत्येक डाकघर में कार्य के निर्धारित घंटों के दौरान जनता के लिए डाक टिकट और स्टेशनरी काउंटर पर उपलब्ध कराना अनिवार्य है।",
        "part_2_focus": "डाक टिकट क्रय करते समय काउंटर पर फटे-पुराने नोट देना वर्जित है और सही मुद्रा में भुगतान करना ग्राहक का दायित्व है।"
    },
    8: {
        "name": "फिलाटेलिक ब्यूरो और डाक टिकट संग्रह", "total_parts": 2,
        "part_1_focus": "फिलाटेलिक ब्यूरो विशेष स्मारक डाक टिकटों और फर्स्ट डे कवर्स (FDC) का वितरण और बिक्री करते हैं।",
        "part_2_focus": "फिलाटेलिक डिपॉजिट अकाउंट (PDA) खोलकर देश-विदेश के संग्राहक नए जारी होने वाले डाक टिकट घर बैठे मंगा सकते हैं।"
    },
    9: {
        "name": "फ्रैंकिंग मशीन के विस्तृत नियम", "total_parts": 5,
        "part_1_focus": "फ्रैंकिंग मशीन का लाइसेंस डाक महानिदेशक या मंडल प्रमुख (SSP/SP) द्वारा वाणिज्यिक व व्यक्तिगत उपयोग हेतु जारी किया जाता है।",
        "part_2_focus": "फ्रैंकिंग मशीन की छाप में वैल्यू डाई और लाइसेंस डाई चमकीले लाल (Bright Red) रंग की स्याही में छपना अनिवार्य है।",
        "part_3_focus": "फ्रैंकिंग मशीन के अग्रिम रीसेट भुगतान पर सरकार द्वारा निर्धारित प्रतिशत का अग्रिम रिबेट (कमीशन छूट) प्रदान किया जाता है।",
        "part_4_focus": "फ्रैंक की गई डाक को सामान्य लेटर बॉक्स में डालना वर्जित है; इसे डाकघर खिड़की पर स्पेशल विंडो टिकट व SO-1/SO-2 पर्ची के साथ देना होता है।",
        "part_5_focus": "यदि फ्रैंकिंग मशीन में गलत मूल्य की छाप लग जाए तो 3 माह के भीतर 5% कटौती के बाद रिफंड का दावा किया जा सकता है।"
    },
    10: {
        "name": "अप्रयुक्त व जाली टिकटों का निषेध", "total_parts": 1,
        "part_1_focus": "काटे गए, फटे हुए या पूर्व-प्रयुक्त डाक टिकटों का पुनः उपयोग करना भारतीय दंड संहिता की धारा 263-A के तहत गैर-जमानती दंडनीय अपराध है।"
    },
    11: {
        "name": "डाक महसूल का अग्रिम भुगतान", "total_parts": 2,
        "part_1_focus": "डाक वस्तुओं पर डाकभार का पूर्ण अग्रिम भुगतान अनिवार्य है ताकि डाक का त्वरित और निर्बाध प्रेषण सुनिश्चित हो सके।",
        "part_2_focus": "अवैतनिक (Unpaid) या कम भुगतान वाली (Underpaid) डाक पर वितरण के समय सामान्य डाक शुल्क से दोगुना प्रभार वसूला जाता है।"
    },
    12: {
        "name": "डाक टिकट चिपकाने की सही विधि", "total_parts": 1,
        "part_1_focus": "लिफाफे या पैकेट के पते वाले भाग पर ऊपर दाहिने कोने (Top Right Corner) में ही डाक टिकट चिपकाना अनिवार्य विभागीय नियम है।"
    },
    13: {
        "name": "विशेष सुरक्षा लिफाफों का प्रयोग", "total_parts": 1,
        "part_1_focus": "मूल्यवान वस्तुओं और रजिस्टर्ड डाक हेतु डाक विभाग द्वारा निर्मित प्रमाणित वाटरप्रूफ सुरक्षा लिफाफों का उपयोग अनुशंसित है।"
    },
    14: {
        "name": "पत्र-पेटी (Letter Box) में पोस्टिंग", "total_parts": 3,
        "part_1_focus": "लेटर बॉक्स में केवल सामान्य पत्र और पोस्टकार्ड ही डाले जाने चाहिए, जिन्हें नियमित निकासी समय के अनुसार निकाला जाता है।",
        "part_2_focus": "बड़े पैकेट, पार्सल या रजिस्ट्री यदि लेटर बॉक्स में डाले जाएं तो उन्हें अवैतनिक मानकर दोगुना दंड प्रभार लगाया जाता है।",
        "part_3_focus": "ग्रीन लेटर बॉक्स (लोकल डाक हेतु) और ब्लू लेटर बॉक्स (मेट्रो शहरों हेतु) के विशिष्ट पोस्टिंग और छंटाई नियम।"
    },
    15: {
        "name": "पोस्टिंग का समय व निकासी घंटे", "total_parts": 1,
        "part_1_focus": "लेटर बॉक्स निकासी प्लेट पर अंकित घंटों के अनुसार ही डाकिया पत्र-पेटी खोलता है और अंतिम निकासी के बाद पोस्टिंग पर लेट फीस लगती है।"
    },
    16: {
        "name": "डाक पर पता लिखने की सही विधि", "total_parts": 2,
        "part_1_focus": "प्राप्तकर्ता का नाम, मकान संख्या, गली, मोहल्ला, सही पिन कोड और मोबाइल नंबर पते पर स्पष्ट अक्षरों में लिखना अनिवार्य है।",
        "part_2_focus": "प्रेषक (Sender) का पूरा नाम व पता हमेशा वस्तु के निचले बाएं कोने (Bottom Left Corner) में 'From' लिखकर दर्ज होना चाहिए।"
    },
    17: {
        "name": "पिन कोड (PIN Code) प्रणाली", "total_parts": 2,
        "part_1_focus": "6 अंकों का पिन कोड: पहला अंक भौगोलिक ज़ोन (1 से 8 नागरिक, 9 सेना), दूसरा उप-ज़ोन तथा तीसरा अंक जिले की पहचान करता है।",
        "part_2_focus": "पिन कोड के अंतिम तीन अंक उस विशिष्ट वितरण डाकघर (Delivery Post Office) को दर्शाते हैं जहां से डाक बांटी जाती है।"
    },
    18: {
        "name": "पोस्टमैन और खिड़की वितरण नियम", "total_parts": 2,
        "part_1_focus": "डाकघर की खिड़की पर विशेष वितरण हेतु अनुमति लेनी होती है और डिलीवरी स्लिप पर हस्ताक्षर करना अनिवार्य होता है।",
        "part_2_focus": "डाकिया द्वारा घर-घर वितरण के दौरान पतेदार के न मिलने पर सूचना पर्ची (Intimation Slip) जारी की जाती है।"
    },
    19: {
        "name": "पोस्ट बॉक्स (Post Box) सुविधा", "total_parts": 3,
        "part_1_focus": "पोस्ट बॉक्स का वार्षिक और त्रैमासिक किराया देकर केवल पूर्ण भुगतान वाले अनरजिस्टर्ड पत्रों का वितरण प्राप्त किया जा सकता है।",
        "part_2_focus": "पोस्ट बॉक्स की चाबी खोने पर किराएदार को नया ताला-चाबी लगाने का शुल्क देना होता है और इसकी सूचना तुरंत डाकघर को देनी होती है।",
        "part_3_focus": "यदि किराएदार निर्धारित समय तक डाक की निकासी नहीं करता तो डाकघर नोटिस जारी कर पोस्ट बॉक्स का आवंटन रद्द कर सकता है।"
    },
    20: {
        "name": "पोस्ट बैग (Post Bag) सुविधा", "total_parts": 2,
        "part_1_focus": "पोस्ट बैग की सुविधा उन फर्मों के लिए है जिनकी भारी डाक आती है, इसमें एक बंद थैले में डाक डिलीवर की जाती है।",
        "part_2_focus": "पोस्ट बॉक्स और पोस्ट बैग को एक साथ संयुक्त रूप से किराए पर लेने पर रियायती संयुक्त वार्षिक शुल्क लागू होता है।"
    },
    21: {
        "name": "विशेष पहचान पत्र (Postal ID)", "total_parts": 1,
        "part_1_focus": "डाकघर द्वारा आम नागरिकों के लिए जारी पहचान पत्र 3 वर्ष की अवधि तक वैध रहता है और खिड़की पर पहचान सत्यापन हेतु मान्य है।"
    },
    22: {
        "name": "डाक का पुनः निर्देशन (Redirection)", "total_parts": 3,
        "part_1_focus": "पतेदार के नया पता छोड़कर जाने पर प्रथम श्रेणी की अंतरदेशीय डाक का पुनः प्रेषण (Redirection) पूर्णतः निःशुल्क होता है।",
        "part_2_focus": "पार्सल पुनः प्रेषण के मामले में यदि पार्सल वितरण क्षेत्र से बाहर भेजा जाए तो आधा डाक प्रभार (Half Forwarding Fee) देय होता है।",
        "part_3_focus": "यदि पार्सल को पतेदार द्वारा खोल दिया गया हो तो उसे नए डाकभार के बिना पुनः निर्देशित नहीं किया जा सकता।"
    },
    23: {
        "name": "पुनः प्रेषण निर्देश की वैधता", "total_parts": 1,
        "part_1_focus": "पतेदार द्वारा डाक को नए पते पर भेजने के लिए दिए गए लिखित निर्देश की अधिकतम वैधता अवधि 3 महीने होती है।"
    },
    24: {
        "name": "लावारिस व अवितरित डाक (RLO)", "total_parts": 3,
        "part_1_focus": "अवितरित डाक को डाकघर में निर्धारित अवधि (सामान्यतः 7 दिन) तक सुरक्षित रखने के बाद RLO (Returned Letter Office) भेजा जाता है।",
        "part_2_focus": "RLO में बिना पते और बिना प्रेषक वाली वस्तुओं को अधिकृत अधिकारियों द्वारा खोलकर प्रेषक की पहचान खोजी जाती है।",
        "part_3_focus": "RLO में 1 वर्ष तक लावारिस रहने वाली मूल्यवान वस्तुओं का नियमानुसार सार्वजनिक नीलामी द्वारा निपटारा किया जाता है।"
    },
    25: {
        "name": "डाक वापस लेना (Recall of Articles)", "total_parts": 2,
        "part_1_focus": "वितरण से पूर्व प्रेषक निर्धारित शुल्क का भुगतान करके अपने द्वारा पोस्ट किए गए पत्र को वापस मंगा सकता है।",
        "part_2_focus": "डाक वापस लेने के लिए प्रेषक को अपनी वास्तविक पहचान और पोस्टिंग का आधिकारिक प्रमाण प्रस्तुत करना अनिवार्य है।"
    },
    26: {
        "name": "वितरण प्रमाणपत्र (Certificate of Posting)", "total_parts": 1,
        "part_1_focus": "प्रमाणपत्र केवल डाकघर में पत्र प्रस्तुत करने का साक्ष्य था, आधुनिक डाक व्यवस्था में इसे विधिक रूप से समाप्त कर दिया गया है।"
    },
    27: {
        "name": "प्रतिबंधित वस्तुएं (Prohibited Articles)", "total_parts": 5,
        "part_1_focus": "विस्फोटक, ज्वलनशील पदार्थ, माचिस, तेजाब और घातक रसायनों का डाक द्वारा प्रेषण पूर्णतः गैर-कानूनी और दंडनीय है।",
        "part_2_focus": "नशीले पदार्थ (Narcotics), अफीम, गांजा और गैर-लाइसेंसी दवाएं डाक द्वारा भेजना एनडीपीएस एक्ट के तहत गंभीर अपराध है।",
        "part_3_focus": "जीवित प्राणी, बिच्छू, जहरीले कीड़े केवल अधिकृत वैज्ञानिक अनुसंधान के विशेष नियमों के अतिरिक्त भेजना निषिद्ध है।",
        "part_4_focus": "तीक्ष्ण धारदार वस्तुएं जैसे चाकू, कैंची बिना मजबूत और सुरक्षित आवरण के भेजना पूरी तरह प्रतिबंधित है।",
        "part_5_focus": "अश्लील, मानहानिकारक या देश की संप्रभुता को नुकसान पहुंचाने वाली सामग्री पाए जाने पर डाक को तुरंत जब्त किया जाता है।"
    },
    28: {
        "name": "विशिष्ट पैकिंग और सीलिंग शर्तें", "total_parts": 2,
        "part_1_focus": "तरल पदार्थों को भेजने हेतु मजबूत रिसाव-रोधी डिब्बे और पर्याप्त सोखने वाले कुशनिंग पदार्थ का उपयोग अनिवार्य है।",
        "part_2_focus": "कांच और नाजुक वस्तुओं की पैकिंग ऐसी होनी चाहिए कि रास्ते में परिवहन के दबाव से अन्य डाक वस्तुएं खराब न हों।"
    },
    29: {
        "name": "शासकीय डाक वस्तुएं (Official Articles)", "total_parts": 2,
        "part_1_focus": "सरकारी डाक पर 'On India Government Service' (OIGS) लिखा होना और अधिकृत अधिकारी के पदनाम की सील अनिवार्य है।",
        "part_2_focus": "शासकीय डाक पर केवल सरकारी सेवा डाक टिकटों (Service Stamps) का ही उपयोग किया जा सकता है, सामान्य टिकटों का नहीं।"
    },
    30: {
        "name": "शिकायतें और सुझाव दर्ज करना", "total_parts": 1,
        "part_1_focus": "प्रत्येक डाकघर में जनता के लिए शिकायत पुस्तिका (Complaint Book) उपलब्ध रखना और ऑनलाइन CPGRAMS निवारण अनिवार्य है।"
    },
    31: {
        "name": "पत्र डाक (Letters) की सीमाएं व वजन", "total_parts": 2,
        "part_1_focus": "पत्र डाक (Letter) का अधिकतम वजन 2 किलोग्राम तक हो सकता है, इससे अधिक वजनी वस्तु को पार्सल माना जाएगा।",
        "part_2_focus": "पत्र का आकार न्यूनतम 11 सेमी × 7 सेमी और अधिकतम लंबाई, चौड़ाई व मोटाई का संयुक्त माप 90 सेमी से अधिक नहीं होना चाहिए।"
    },
    32: {
        "name": "पोस्टकार्ड (Postcards) के नियम", "total_parts": 2,
        "part_1_focus": "मानक एकल पोस्टकार्ड का माप 14 सेमी × 9 सेमी होता है और इसका उपयोग केवल खुले संचार हेतु किया जाता है।",
        "part_2_focus": "पोस्टकार्ड पर टिकट के अलावा कुछ भी अतिरिक्त कागज चिपकाना वर्जित है, उल्लंघन करने पर पत्र दर से शुल्क वसूला जाएगा।"
    },
    33: {
        "name": "प्रिंटेड और मेघदूत पोस्टकार्ड", "total_parts": 2,
        "part_1_focus": "प्रिंटेड पोस्टकार्ड पर मुद्रित विज्ञापन या संदेश होते हैं और इनकी डाक दर सामान्य पोस्टकार्ड से अधिक निर्धारित होती है।",
        "part_2_focus": "मेघदूत पोस्टकार्ड ग्रामीण क्षेत्रों में सरकारी व सामाजिक विज्ञापनों हेतु रियायती आधी दर पर उपलब्ध कराया जाता है।"
    },
    34: {
        "name": "अंतरदेशीय पत्र कार्ड (ILC)", "total_parts": 2,
        "part_1_focus": "अंतर्देशीय पत्र कार्ड (ILC) का अधिकतम वजन 5 ग्राम होता है और यह केवल भारत की भौगोलिक सीमा के भीतर मान्य है।",
        "part_2_focus": "ILC के अंदर कोई भी अतिरिक्त पत्र, फोटो या सामग्री रखना निषिद्ध है; उल्लंघन पर इसे पूर्ण पत्र मानकर टैक्स वसूला जाएगा।"
    },
    35: {
        "name": "बुक पैकेट (Book Packets) के नियम", "total_parts": 2,
        "part_1_focus": "बुक पैकेट का अधिकतम वजन 5 किलोग्राम हो सकता है और इसे खुला भेजा जाना चाहिए ताकि डाक कर्मचारी सामग्री की जांच कर सकें।",
        "part_2_focus": "बुक पैकेट के भीतर कोई भी व्यक्तिगत पत्राचार या बंद लिफाफा रखना पूर्णतः वर्जित है, ऐसा पाए जाने पर भारी दंड लगता है।"
    },
    36: {
        "name": "मुद्रित पुस्तकें पैकेट (Printed Books)", "total_parts": 1,
        "part_1_focus": "केवल मुद्रित पुस्तकों वाले बुक पैकेट पर विशेष रियायती डाक दरें लागू होती हैं, जिनमें कोई विज्ञापन या व्यक्तिगत पत्राचार न हो।"
    },
    37: {
        "name": "सामयिक पत्रिका पैकेट (Periodicals)", "total_parts": 1,
        "part_1_focus": "भारत के समाचार पत्र पंजीयक (RNI) में पंजीकृत पत्र-पत्रिकाओं को रियायती दरों पर भेजने की विशेष सुविधा मिलती है।"
    },
    38: {
        "name": "पैटर्न और सैंपल पैकेट", "total_parts": 1,
        "part_1_focus": "व्यापारिक नमूनों के सैंपल पैकेट का अधिकतम वजन 2 किलोग्राम तक हो सकता है और इनका कोई विक्रय मूल्य नहीं होना चाहिए।"
    },
    39: {
        "name": "ब्लाइंड लिटरेचर पैकेट (दृष्टिहीनों हेतु)", "total_parts": 2,
        "part_1_focus": "दृष्टिहीनों के उभरे हुए ब्रेल अक्षरों वाली अध्ययन सामग्री का पैकेट अधिकतम 7 किलोग्राम तक भेजा जा सकता है।",
        "part_2_focus": "ब्लाइंड लिटरेचर पैकेट डाक शुल्क, रजिस्ट्री शुल्क और पावती (AD) शुल्क से शत-प्रतिशत पूरी तरह मुक्त (Free) होता है।"
    },
    40: {
        "name": "पंजीकृत समाचार पत्र (Regd. Newspaper)", "total_parts": 3,
        "part_1_focus": "समाचार पत्र का प्रकाशन 31 दिनों से अनधिक अंतराल पर होना चाहिए और इसमें प्रामाणिक ग्राहकों की वैध सूची होनी चाहिए।",
        "part_2_focus": "डाक अधीक्षक (SP) द्वारा समाचार पत्र का पंजीकरण लाइसेंस जारी किया जाता है जिसे प्रति 3 वर्ष में नवीनीकृत कराना होता है।",
        "part_3_focus": "पंजीकृत समाचार पत्र के पैकेट पर 'Registered Newspaper' और डाक लाइसेंस संख्या का स्पष्ट मुद्रण अनिवार्य है।"
    },
    41: {
        "name": "पार्सल (Parcel) के विस्तृत नियम", "total_parts": 4,
        "part_1_focus": "अनरजिस्टर्ड पार्सल का अधिकतम वजन 4 किग्रा तथा रजिस्टर्ड पार्सल का अधिकतम वजन 20 किग्रा (BO में 10 किग्रा) हो सकता है।",
        "part_2_focus": "पार्सल की अधिकतम लंबाई 1 मीटर से अधिक और लंबाई व परिधि का संयुक्त घेरा 1.80 मीटर से अधिक नहीं होना चाहिए।",
        "part_3_focus": "पार्सल में कोई भी व्यक्तिगत पत्र संलग्न करना प्रतिबंधित है; ऐसा पाए जाने पर पत्र पर पृथक पत्र डाक शुल्क और जुर्माना लगेगा।",
        "part_4_focus": "घर-घर पार्सल वितरण के नियम: 5 किग्रा तक का पार्सल डाकिया घर पर देगा, 5 किग्रा से अधिक का पार्सल खिड़की से प्राप्त करना होगा।"
    },
    42: {
        "name": "अनिवार्य पंजीकरण (Compulsory Regn.)", "total_parts": 2,
        "part_1_focus": "4 किलोग्राम से अधिक वजनी पार्सल, बीमित वस्तुएं और वीपीपी (VPP) वस्तुओं का काउंटर पर अनिवार्य पंजीकरण कराना होता है।",
        "part_2_focus": "यदि किसी लावारिस या लेटर बॉक्स से निकाले गए पत्र पर 'Registered' शब्द लिखा हो, तो उसका अनिवार्य पंजीकरण किया जाएगा।"
    },
    43: {
        "name": "रजिस्ट्री की पावती (Acknowledgment - AD)", "total_parts": 1,
        "part_1_focus": "प्रेषक द्वारा निर्धारित पावती शुल्क जमा करने पर वितरण के समय प्राप्तकर्ता के मूल हस्ताक्षर वाली पावती लौटाई जाती है।"
    },
    44: {
        "name": "डाक बीमा (Insurance) की सीमाएं", "total_parts": 3,
        "part_1_focus": "शाखा डाकघर (BO) में अधिकतम ₹600 तक और विभागीय डाकघरों (SO/HO) में अधिकतम ₹1,00,000 तक बीमा स्वीकार्य होता है।",
        "part_2_focus": "सोने के सिक्के, करेंसी नोट, आभूषण और कीमती रत्नों को डाक द्वारा भेजते समय उनका वास्तविक मूल्य पर अनिवार्य बीमा कराना होता है।",
        "part_3_focus": "यदि अनिवार्य बीमा वाली वस्तु बिना बीमा के डाक में पाई जाए तो उसे वितरण पर अनिवार्य बीमा शुल्क और जुर्माना लेकर दिया जाएगा।"
    },
    45: {
        "name": "बीमित वस्तुओं की सीलिंग व पैकिंग", "total_parts": 2,
        "part_1_focus": "बीमित वस्तु की पैकिंग मजबूत होनी चाहिए और सभी जोड़ों पर एक ही रंग की लाख (Sealing Wax) की स्पष्ट सील अनिवार्य है।",
        "part_2_focus": "सील पर किसी सिक्के या सामान्य वस्तु की छाप नहीं होनी चाहिए, प्रेषक की निजी विशिष्ट मुहर की स्पष्ट छाप होना अनिवार्य है।"
    },
    46: {
        "name": "मूल्य देय डाक (VPP - Value Payable)", "total_parts": 3,
        "part_1_focus": "वीपीपी के माध्यम से वस्तु का मूल्य अधिकतम ₹5,000 तक डिलीवरी के समय ग्राहक से वसूल कर प्रेषक को भेजा जाता है।",
        "part_2_focus": "वीपीपी वस्तु पर प्रेषक का नाम, पूरा पता और वसूली जाने वाली सही धनराशि अंकों व शब्दों में साफ लिखी होनी चाहिए।",
        "part_3_focus": "यदि पतेदार वीपीपी वस्तु को लेने से मना कर दे या 7 दिन में न ले, तो उसे तुरंत प्रेषक को बिना किसी अतिरिक्त शुल्क के लौटा दिया जाता है।"
    },
    47: {
        "name": "मनीऑर्डर (Money Order) प्रणाली", "total_parts": 3,
        "part_1_focus": "इलेक्ट्रॉनिक मनीऑर्डर (eMO) के माध्यम से एक प्रेषक द्वारा अधिकतम ₹5,000 तक की धनराशि सुरक्षित भेजी जा सकती है।",
        "part_2_focus": "प्रेषक निर्धारित शुल्क देकर भुगतान से पूर्व आहरण कार्यालय या प्राप्तकर्ता का नाम बदलने का लिखित आवेदन कर सकता है।",
        "part_3_focus": "यदि प्राप्तकर्ता मनीऑर्डर लेने से मना कर दे, तो राशि बिना अतिरिक्त कमीशन के मूल प्रेषक को वापस लौटा दी जाती है।"
    },
    48: {
        "name": "इलेक्ट्रॉनिक पोस्टल ऑर्डर (e-IPO)", "total_parts": 1,
        "part_1_focus": "विदेशों में रहने वाले भारतीय नागरिकों और देशवासियों हेतु आरटीआई (RTI) शुल्क के ऑनलाइन डिजिटल भुगतान हेतु e-IPO शुरू किया गया है।"
    },
    49: {
        "name": "भारतीय पोस्टल ऑर्डर (IPO) के नियम", "total_parts": 2,
        "part_1_focus": "आईपीओ विभिन्न मूल्यवर्गों (₹1 से ₹100) में उपलब्ध होते हैं और क्रॉस (Crossed) किए गए आईपीओ केवल बैंक खाते में ही जमा होते हैं।",
        "part_2_focus": "आईपीओ की वैधता जारी होने के महीने के अंतिम दिन से 24 माह तक होती है, दूसरे वर्ष में भुगतान पर नवीनीकरण शुल्क लगता है।"
    },
    50: {
        "name": "डाकघर बचत बैंक (POSB) का संगठन", "total_parts": 2,
        "part_1_focus": "डाकघर बचत बैंक भारत सरकार के वित्त मंत्रालय की राष्ट्रीय लघु बचत योजनाओं को ग्रामीण व शहरी स्तर पर संचालित करता है।",
        "part_2_focus": "डाकघर के बचत खातों में जमा संपूर्ण राशि पर भारत सरकार की 100% संप्रभु सुरक्षा (Sovereign Guarantee) प्राप्त होती है।"
    },
    51: {
        "name": "बचत खाता (Savings Account) नियम", "total_parts": 4,
        "part_1_focus": "डाकघर बचत खाता न्यूनतम ₹500 से खोला जा सकता है और खाते में हमेशा न्यूनतम ₹500 का बैलेंस बनाए रखना अनिवार्य होता है।",
        "part_2_focus": "यदि खाते में न्यूनतम शेष ₹500 न हो, तो वित्तीय वर्ष के अंत में ₹50 रखरखाव शुल्क (Maintenance Fee) काटा जाएगा।",
        "part_3_focus": "यदि लगातार 3 वित्तीय वर्षों तक खाते में कोई लेन-देन न हो, तो खाता निष्क्रिय या साइलेंट (Silent/Dormant) हो जाता है।",
        "part_4_focus": "बचत खाते पर आयकर अधिनियम की धारा 80TTA के तहत ₹10,000 तक का वार्षिक ब्याज पूर्णतः कर-मुक्त होता है।"
    },
    52: {
        "name": "आवर्ती जमा खाता (RD Account)", "total_parts": 5,
        "part_1_focus": "5 वर्ष की अवधि वाले आरडी खाते में न्यूनतम ₹100 प्रतिमाह (₹10 के गुणक में) जमा होता है और अधिकतम की कोई सीमा नहीं है।",
        "part_2_focus": "महीने के 1 से 15 तारीख के बीच खुले खाते की किस्त 15 तारीख तक और 16 के बाद खुले खाते की किस्त माह के अंतिम दिन तक देय होती है।",
        "part_3_focus": "किस्त समय पर न देने पर प्रति ₹100 पर ₹1 डिफ़ॉल्ट शुल्क लगता है; लगातार 4 डिफ़ॉल्ट पर खाता बंद (Discontinued) हो जाता है।",
        "part_4_focus": "1 वर्ष तक नियमित 12 किस्तें जमा रहने पर खाते में जमा राशि का 50% तक ऋण (Loan) लेने की सुविधा मिलती है।",
        "part_5_focus": "आरडी खाते को 3 वर्ष नियमित चलने के बाद समय से पूर्व (Premature Closure) बंद कराया जा सकता है, जिस पर बचत बैंक ब्याज दर मिलेगी।"
    },
    53: {
        "name": "सावधि जमा खाता (TD Account)", "total_parts": 3,
        "part_1_focus": "डाकघर टीडी खाते 1, 2, 3 और 5 वर्ष की अवधि हेतु न्यूनतम ₹1,000 से खोले जा सकते हैं जिनकी ब्याज दरें त्रैमासिक तय होती हैं।",
        "part_2_focus": "5 वर्षीय टीडी खाते में जमा की गई राशि पर आयकर अधिनियम की धारा 80C के तहत ₹1.5 लाख तक कर छूट का लाभ प्राप्त होता है।",
        "part_3_focus": "टीडी खाते को 6 माह से पहले बंद नहीं कराया जा सकता; 6 से 12 माह के बीच बंद करने पर केवल साधारण बचत बैंक ब्याज देय होगा।"
    },
    54: {
        "name": "मासिक आय योजना (MIS Account)", "total_parts": 4,
        "part_1_focus": "एमआईएस खाते की परिपक्वता अवधि 5 वर्ष है; इसमें एकल खाते में अधिकतम ₹9 लाख और संयुक्त खाते में ₹15 लाख जमा हो सकते हैं।",
        "part_2_focus": "एमआईएस खाते का ब्याज प्रतिमाह डाकघर बचत खाते में स्वतः ऑटो-क्रेडिट होता है, जिस पर कोई टीडीएस नहीं काटा जाता।",
        "part_3_focus": "1 वर्ष से पूर्व खाता बंद करने की अनुमति नहीं है; 1 से 3 वर्ष के बीच बंद करने पर 2% और 3 से 5 वर्ष के बीच 1% मूलधन काटा जाता है।",
        "part_4_focus": "एमआईएस खाते में संयुक्त खाता 3 वयस्कों द्वारा समान हिस्सेदारी में खोला जा सकता है।"
    },
    55: {
        "name": "वरिष्ठ नागरिक बचत योजना (SCSS)", "total_parts": 3,
        "part_1_focus": "60 वर्ष या उससे अधिक आयु के वरिष्ठ नागरिकों हेतु न्यूनतम ₹1,000 और अधिकतम ₹30 लाख की एकमुश्त जमा सीमा निर्धारित है।",
        "part_2_focus": "55 से 60 वर्ष के वीआरएस (VRS) सेवानिवृत्त कर्मचारी सेवानिवृत्ति लाभ मिलने के 1 माह के भीतर यह खाता खोल सकते हैं।",
        "part_3_focus": "इस खाते की अवधि 5 वर्ष होती है जिसे 3 वर्ष हेतु बढ़ाया जा सकता है और ब्याज का भुगतान त्रैमासिक आधार पर किया जाता है।"
    },
    56: {
        "name": "पब्लिक प्रोविडेंट फंड (PPF Account)", "total_parts": 4,
        "part_1_focus": "पीपीएफ खाते की परिपक्वता अवधि 15 वर्ष है; एक वित्तीय वर्ष में न्यूनतम ₹500 और अधिकतम ₹1.5 लाख तक जमा किए जा सकते हैं।",
        "part_2_focus": "पीपीएफ को ईईई (EEE) कर दर्जा प्राप्त है (जमा, ब्याज और निकासी तीनों आयकर से पूर्णतः मुक्त होते हैं)।",
        "part_3_focus": "खाते के तीसरे वित्तीय वर्ष से ऋण की सुविधा और सातवें वित्तीय वर्ष से 50% आंशिक निकासी की सुविधा मिलती है।",
        "part_4_focus": "किसी भी न्यायालय के आदेश द्वारा किसी कर्ज या देनदारी के विरुद्ध पीपीएफ खाते की राशि को कुर्क नहीं किया जा सकता।"
    },
    57: {
        "name": "सुकन्या समृद्धि योजना (SSA Account)", "total_parts": 4,
        "part_1_focus": "10 वर्ष से कम आयु की बालिकाओं हेतु न्यूनतम ₹250 से खाता खुलता है; एक परिवार में अधिकतम 2 बेटियों हेतु खाता मान्य है।",
        "part_2_focus": "एक वित्तीय वर्ष में न्यूनतम ₹250 और अधिकतम ₹1.5 लाख तक 15 वर्षों तक जमा किया जाना अनिवार्य होता है।",
        "part_3_focus": "बालिका के 18 वर्ष पूर्ण होने या 10वीं कक्षा उत्तीर्ण करने पर उच्च शिक्षा हेतु खाते के 50% बैलेंस की निकासी मान्य है।",
        "part_4_focus": "यह खाता 21 वर्ष पूर्ण होने पर अथवा 18 वर्ष की आयु के बाद बालिका के विवाह के समय पूर्ण परिपक्व होता है।"
    },
    58: {
        "name": "राष्ट्रीय बचत पत्र (NSC - VIII Issue)", "total_parts": 2,
        "part_1_focus": "एनएससी 5 वर्ष की लॉक-इन अवधि का सुरक्षित प्रमाण पत्र है, जिसमें ब्याज की राशि वार्षिक रूप से पुनर्निवेशित मानी जाती है।",
        "part_2_focus": "ऋण प्राप्त करने हेतु एनएससी को बैंकों या सरकारी वित्तीय संस्थानों के पक्ष में आधिकारिक रूप से बंधक (Pledge) रखा जा सकता है।"
    },
    59: {
        "name": "किसान विकास पत्र (KVP Scheme)", "total_parts": 2,
        "part_1_focus": "केवीपी भारत सरकार की निश्चित ब्याज दर पर निवेश की गई मूल राशि को निर्धारित महीनों में दोगुना (Double) करने वाली योजना है।",
        "part_2_focus": "केवीपी में न्यूनतम ₹1,000 का निवेश होता है तथा अधिकतम की कोई सीमा नहीं, और 2 वर्ष 6 माह बाद समयपूर्व निकासी मान्य है।"
    },
    60: {
        "name": "डाक जीवन बीमा (PLI व RPLI विस्तृत)", "total_parts": 7,
        "part_1_focus": "1884 में स्थापित पीएलआई (PLI) केंद्र, राज्य, रक्षा, सार्वजनिक उपक्रम व मान्यता प्राप्त शैक्षणिक संस्थानों के कर्मचारियों हेतु है।",
        "part_2_focus": "पीएलआई में सुरक्षा (Whole Life), संतोष (Endowment), सुविधा (Convertible), युगल सुरक्षा और सुमंगल (Anticipated) योजनाएं हैं।",
        "part_3_focus": "पीएलआई में न्यूनतम बीमा राशि ₹20,000 और अधिकतम बीमा राशि ₹50 लाख तक निर्धारित की गई है।",
        "part_4_focus": "1995 में मल्होत्रा समिति की सिफारिश पर प्रारंभ आरपीएलआई (RPLI) ग्रामीण क्षेत्र के सभी नागरिकों हेतु संचालित है।",
        "part_5_focus": "आरपीएलआई में ग्राम सुरक्षा, ग्राम संतोष, ग्राम सुविधा, ग्राम सुमंगल (Money Back) और बाल जीवन बीमा उपलब्ध हैं।",
        "part_6_focus": "आरपीएलआई में न्यूनतम बीमा राशि ₹10,000 तथा अधिकतम बीमा राशि ₹10 लाख तक निर्धारित है।",
        "part_7_focus": "पीएलआई और आरपीएलआई दोनों में 3 वर्ष बाद समर्पण (Surrender) और पॉलिसी पर ऋण (Loan) लेने की आधिकारिक सुविधा मिलती है।"
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

def load_progress_state():
    state = {"clause_no": 6, "current_part": 2, "total_parts": 2, "hook_index": 0}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                if isinstance(saved, dict) and "clause_no" in saved:
                    state.update(saved)
        except Exception:
            pass
    current_clause = state.get("clause_no", 6)
    state["total_parts"] = POSTAL_CLAUSE_CATALOG.get(current_clause, {}).get("total_parts", 1)
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
    part = state.get("current_part", 2)
    clause_info = POSTAL_CLAUSE_CATALOG.get(clause, {"total_parts": 1})
    total_parts = clause_info.get("total_parts", 1)

    if part < total_parts:
        state["current_part"] = part + 1
        state["total_parts"] = total_parts
    else:
        catalog_keys = sorted(POSTAL_CLAUSE_CATALOG.keys())
        current_idx = catalog_keys.index(clause) if clause in catalog_keys else 0
        next_idx = (current_idx + 1) % len(catalog_keys)
        next_clause = catalog_keys[next_idx]
        state["clause_no"] = next_clause
        state["current_part"] = 1
        state["total_parts"] = POSTAL_CLAUSE_CATALOG.get(next_clause, {}).get("total_parts", 1)

    save_progress_state(state)
    print(f"⏩ Advanced Progress to: Clause {state['clause_no']} (Part {state['current_part']}/{state['total_parts']})", flush=True)

def generate_clause_script(state):
    current_clause = state.get("clause_no", 6)
    current_part = state.get("current_part", 2)
    hook_idx = state.get("hook_index", 0) % len(VIRAL_HOOKS)
    hook_obj = VIRAL_HOOKS[hook_idx]

    clause_info = POSTAL_CLAUSE_CATALOG.get(current_clause, POSTAL_CLAUSE_CATALOG[6])
    clause_name = clause_info["name"]
    total_parts = clause_info.get("total_parts", 1)
    
    part_key = f"part_{current_part}_focus"
    part_focus = clause_info.get(part_key, clause_info.get("part_1_focus", ""))

    fallback_data = {
        "clause_no": current_clause,
        "clause_name": clause_name,
        "part_no": current_part,
        "total_parts": total_parts,
        "visual_hook_badge": hook_obj["visual_badge"],
        "hook_voice": hook_obj["voice"],
        "question": f"डाक घर गाइड भाग 1 के क्लॉज {current_clause}, भाग {current_part} के अनुसार सही नियम क्या है?",
        "sen1": f"क्लॉज {current_clause} के अनुसार {part_focus}",
        "sen2": "ध्यान रखें: प्रश्न में दी गई सीमा, समय या शर्त को ही सही उत्तर का आधार बनाएं।",
        "sen3": "परीक्षा ट्रैप: मिलते-जुलते नियमों को आपस में न मिलाएं।",
        "opt_a": "उपलब्ध नियम के अनुसार",
        "opt_b": "दिए गए नियम के अनुसार",
        "opt_c": "उल्लिखित शर्त के अनुसार",
        "opt_d": "इनमें से कोई नहीं",
        "correct_letter": "B",
        "caption": (
            f"क्लॉज {current_clause} | भाग {current_part}/{total_parts} — "
            f"पहले MCQ खुद solve करें, फिर answer check करें। "
            f"#PostalWala #GDStoMTS #PostmanExam #IndiaPost"
        )
    }

    if not GROQ_API_KEY:
        return fallback_data

    prompt = f"""
You create ONE accurate, high-retention MCQ for India Post departmental exam preparation.

SOURCE:
Book: Post Office Guide Part 1
Clause: {current_clause}
Title: {clause_name}
Part: {current_part}/{total_parts}
Exact focus supplied by the source catalog:
"{part_focus}"

RULES:
- Stay strictly within the supplied focus. Do not invent an exception, number, penalty, date or limit.
- Make the question answerable from this focus alone.
- Keep QUESTION short enough for a mobile Reel.
- Options must be plausible and mutually distinct.
- Only one option can be correct.
- SEN1: one very simple Hindi explanation, maximum ~18 words.
- SEN2: one important condition/limit/trap, maximum ~16 words.
- SEN3: one short memory cue, maximum ~12 words.
- Do not claim "90%", "100%", "guaranteed marks", "promotion guaranteed", or similar unsupported claims.
- Output ONLY these fields, one per line:

QUESTION: ...
SEN1: ...
SEN2: ...
SEN3: ...
OPT_A: ...
OPT_B: ...
OPT_C: ...
OPT_D: ...
CORRECT: A/B/C/D
"""

    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"}
        payload = {"model": "qwen/qwen3-32b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 550}
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
            od = extract_field_block(raw_text, "OPT_D", ["CORRECT"])
            correct = extract_field_block(raw_text, "CORRECT", [])

            if q: fallback_data["question"] = clean_hindi_postal_terms(q)
            if s1: fallback_data["sen1"] = clean_hindi_postal_terms(s1)
            if s2: fallback_data["sen2"] = clean_hindi_postal_terms(s2)
            if s3: fallback_data["sen3"] = clean_hindi_postal_terms(s3)
            if oa: fallback_data["opt_a"] = clean_hindi_postal_terms(oa)
            if ob: fallback_data["opt_b"] = clean_hindi_postal_terms(ob)
            if oc: fallback_data["opt_c"] = clean_hindi_postal_terms(oc)
            if od: fallback_data["opt_d"] = clean_hindi_postal_terms(od)
            if correct:
                letter_match = re.search(r"[ABCDabcd]", correct)
                if letter_match:
                    fallback_data["correct_letter"] = letter_match.group(0).upper()
    except Exception as e:
        print(f"⚠️ Groq note: {e}")

    return fallback_data

def get_correct_option_text(script_data):
    letter = script_data.get("correct_letter", "B").strip().upper()
    key = f"opt_{letter.lower()}"
    return letter, script_data.get(key, script_data.get("opt_b", ""))

def get_slide_segments(script_data):
    q_txt = script_data["question"]
    letter, correct_text = get_correct_option_text(script_data)
    return [
        # 0: Hook + challenge
        f"{script_data['hook_voice']} अपना जवाब दिमाग में चुनिए.",
        # 1: Question + options
        f"सवाल: {q_txt} विकल्प हैं — A: {script_data['opt_a']}; B: {script_data['opt_b']}; C: {script_data['opt_c']}; D: {script_data['opt_d']}.",
        # 2: Short suspense / participation
        "तीन सेकंड… अपना जवाब लॉक कीजिए. तीन… दो… एक…",
        # 3: Answer + real explanation
        f"सही उत्तर है विकल्प {letter}: {correct_text}. {script_data['sen1']}",
        # 4: Trap + compact CTA
        f"याद रखने की बात: {script_data['sen2']} {script_data['sen3']} ऐसे MCQ के लिए फॉलो करें."
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

def render_and_sync_video(script_data, output_video=OUTPUT_VIDEO):
    """
    Retention-first renderer:
    - 5 scenes instead of 6 long slides
    - question/options appear immediately
    - no fake waiting/loading screen
    - countdown creates genuine participation
    - answer is delivered quickly
    - CTA is short and comes after value
    - each scene has a subtle push/zoom rather than a long static hold
    """
    ensure_fonts()
    ensure_auto_icons()

    segment_audios = get_slide_segments(script_data)
    raw_durations = []

    for i, seg_text in enumerate(segment_audios):
        seg_file = f"audio_seg_{i}.mp3"
        asyncio.run(generate_segment_audio(seg_text, seg_file))
        raw_durations.append(get_audio_duration(seg_file))

    # Keep narration natural. Do not stretch a short script into a long Reel.
    concat_filter = "".join([f"[{i}:a]" for i in range(len(segment_audios))])
    concat_filter += f"concat=n={len(segment_audios)}:v=0:a=1[aout]"

    ffmpeg_concat_cmd = ["ffmpeg", "-y"]
    for i in range(len(segment_audios)):
        ffmpeg_concat_cmd.extend(["-i", f"audio_seg_{i}.mp3"])
    ffmpeg_concat_cmd.extend([
        "-filter_complex", concat_filter,
        "-map", "[aout]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        "raw_master.mp3"
    ])
    subprocess.run(ffmpeg_concat_cmd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    total_dur = get_audio_duration("raw_master.mp3")
    print(f"🎵 Raw narration: {total_dur:.2f}s", flush=True)

    # Target is intentionally tight. If narration is too long, speed it up mildly;
    # never slow a short Reel just to hit an arbitrary minimum.
    MAX_TARGET_DUR = 24.0
    MIN_TARGET_DUR = 15.0

    if total_dur > MAX_TARGET_DUR:
        tempo_scale = min(1.20, round(total_dur / MAX_TARGET_DUR, 4))
    else:
        tempo_scale = 1.0

    if tempo_scale != 1.0:
        subprocess.run([
            "ffmpeg", "-y", "-i", "raw_master.mp3",
            "-filter:a", f"atempo={tempo_scale}",
            "final_master.mp3"
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run([
            "ffmpeg", "-y", "-i", "raw_master.mp3",
            "-c:a", "copy", "final_master.mp3"
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    durations = [d / tempo_scale for d in raw_durations]
    final_duration = sum(durations)
    print(f"🎬 Final duration: {final_duration:.1f}s", flush=True)

    # Fonts
    font_brand = get_eng_font(38)
    font_sub = get_eng_font(20)
    font_badge = get_dev_font(22)
    font_title = get_dev_font(42)
    font_h2 = get_dev_font(34)
    font_body = get_dev_font(30)
    font_small = get_dev_font(24)
    font_opt = get_dev_font(28)
    font_big = get_dev_font(74)
    font_cta = get_dev_font(27)
    font_num = get_eng_font(30)

    W, H = 1080, 1920

    def draw_base(d):
        # Cleaner hierarchy: content dominates, branding is secondary.
        d.rectangle([0, 0, W, H], fill="#07111F")
        d.rounded_rectangle([38, 38, 1042, 1882], radius=34,
                            fill="#0B1730", outline="#243B5A", width=3)

        d.text((72, 72), "POSTAL WALA", fill="#FFFFFF", font=font_brand)
        d.text((72, 122), "@POSTAL_WALA", fill="#8FA6C0", font=font_sub)

        # Tiny trust label; no giant promo strip.
        d.rounded_rectangle([735, 70, 1000, 126], radius=16,
                            fill="#123D35", outline="#2ED6A1", width=2)
        d.text((765, 87), "EXAM MCQ", fill="#B9FFE9", font=font_badge)

    def draw_top_progress(d, idx, total):
        # Thin progress bar gives the viewer a visible sense of progress.
        left, right = 72, 1008
        y = 205
        d.rounded_rectangle([left, y, right, y + 10], radius=5, fill="#1C2A42")
        progress = left + (right - left) * ((idx + 1) / total)
        d.rounded_rectangle([left, y, progress, y + 10], radius=5, fill="#22D3EE")

    def draw_footer(d, text=""):
        if not text:
            return
        d.text((72, 1788), text, fill="#8FA6C0", font=font_small)

    def draw_center_badge(d, text, y=285):
        d.rounded_rectangle([100, y, 980, y + 105], radius=24,
                            fill="#172A46", outline="#F59E0B", width=3)
        d.multiline_text((135, y + 18), textwrap.fill(clean_hindi_postal_terms(text), 28),
                         fill="#FFE9A6", font=font_h2, spacing=6, align="center")

    def draw_option(d, letter, value, y, active=False):
        fill = "#123D35" if active else "#101F36"
        outline = "#2ED6A1" if active else "#38506D"
        d.rounded_rectangle([90, y, 990, y + 118], radius=22,
                            fill=fill, outline=outline, width=3)
        d.ellipse([115, y + 24, 185, y + 94],
                   fill="#1E4B73" if not active else "#0F8B68")
        d.text((139, y + 42), letter, fill="#FFFFFF", font=font_num)

        wrapped = textwrap.fill(clean_hindi_postal_terms(value), width=28)
        d.multiline_text((215, y + 20), wrapped, fill="#FFFFFF",
                         font=font_opt, spacing=5)

    letter, correct_text = get_correct_option_text(script_data)
    opts = [
        script_data["opt_a"], script_data["opt_b"],
        script_data["opt_c"], script_data["opt_d"]
    ]

    # ---------- SCENE 1: HOOK ----------
    img1 = Image.new("RGB", (W, H), "#07111F")
    d1 = ImageDraw.Draw(img1)
    draw_base(d1); draw_top_progress(d1, 0, 5)
    draw_center_badge(d1, script_data["visual_hook_badge"], 290)

    d1.text((90, 475), "आज का CHALLENGE", fill="#22D3EE", font=font_small)
    d1.multiline_text(
        (90, 555),
        "पहले जवाब सोचिए.\nउत्तर अभी मत देखिए.",
        fill="#FFFFFF", font=font_title, spacing=18
    )

    # Strong visual focal point, but no 8-second loading screen.
    paste_safe_asset(img1, QUIZ_3D_PATH, pos=(390, 920), size=(300, 400))
    d1.rounded_rectangle([180, 1370, 900, 1490], radius=28,
                         fill="#7C2D12", outline="#F59E0B", width=3)
    d1.text((330, 1404), "A  •  B  •  C  •  D", fill="#FFE9A6", font=font_h2)
    draw_footer(d1, "एक सवाल • एक सही जवाब • एक जरूरी नियम")
    img1.save("slide_1.png")

    # ---------- SCENE 2: QUESTION + OPTIONS ----------
    img2 = Image.new("RGB", (W, H), "#07111F")
    d2 = ImageDraw.Draw(img2)
    draw_base(d2); draw_top_progress(d2, 1, 5)

    d2.text((90, 275), "सवाल", fill="#22D3EE", font=font_h2)
    q = textwrap.fill(clean_hindi_postal_terms(script_data["question"]), width=31)
    d2.multiline_text((90, 360), q, fill="#FFFFFF", font=font_title, spacing=12)

    oy = 770
    for i, opt in enumerate(opts):
        draw_option(d2, chr(65 + i), opt, oy)
        oy += 145

    draw_footer(d2, "अपना उत्तर दिमाग में लॉक कीजिए")
    img2.save("slide_2.png")

    # ---------- SCENE 3: COUNTDOWN ----------
    img3 = Image.new("RGB", (W, H), "#07111F")
    d3 = ImageDraw.Draw(img3)
    draw_base(d3); draw_top_progress(d3, 2, 5)

    d3.text((90, 300), "आपका जवाब?", fill="#FFFFFF", font=font_title)
    d3.text((90, 410), "3 सेकंड में LOCK करें", fill="#FBBF24", font=font_h2)

    d3.ellipse([300, 610, 780, 1090], fill="#102B4A", outline="#22D3EE", width=8)
    d3.text((425, 745), "3", fill="#FFFFFF", font=font_big)
    d3.text((90, 1190), "सोचिए…", fill="#8FA6C0", font=font_h2)
    d3.text((90, 1260), "फिर answer मिलाइए.", fill="#FFFFFF", font=font_h2)
    d3.rounded_rectangle([90, 1430, 990, 1550], radius=24,
                         fill="#172A46", outline="#38506D", width=3)
    d3.text((260, 1465), "A / B / C / D  —  LOCK!", fill="#FFFFFF", font=font_h2)
    draw_footer(d3, "Viewer को passive नहीं, participant बनाएं")
    img3.save("slide_3.png")

    # ---------- SCENE 4: ANSWER + EXPLANATION ----------
    img4 = Image.new("RGB", (W, H), "#07111F")
    d4 = ImageDraw.Draw(img4)
    draw_base(d4); draw_top_progress(d4, 3, 5)

    d4.text((90, 280), "सही उत्तर", fill="#2ED6A1", font=font_h2)
    d4.rounded_rectangle([90, 380, 990, 610], radius=28,
                         fill="#123D35", outline="#2ED6A1", width=4)
    d4.ellipse([125, 440, 235, 550], fill="#0F8B68")
    d4.text((160, 460), letter, fill="#FFFFFF", font=font_h2)
    d4.multiline_text(
        (275, 425),
        textwrap.fill(clean_hindi_postal_terms(correct_text), 25),
        fill="#E9FFF8", font=font_h2, spacing=7
    )

    d4.text((90, 720), "क्यों?", fill="#22D3EE", font=font_h2)
    d4.multiline_text(
        (90, 810),
        textwrap.fill(clean_hindi_postal_terms(script_data["sen1"]), 34),
        fill="#FFFFFF", font=font_body, spacing=12
    )

    d4.rounded_rectangle([90, 1220, 990, 1390], radius=24,
                         fill="#172A46", outline="#FBBF24", width=3)
    d4.text((125, 1250), "याद रखें", fill="#FBBF24", font=font_small)
    d4.multiline_text(
        (125, 1300),
        textwrap.fill(clean_hindi_postal_terms(script_data["sen2"]), 35),
        fill="#FFFFFF", font=font_small, spacing=7
    )
    draw_footer(d4, "Answer के तुरंत बाद value दें")
    img4.save("slide_4.png")

    # ---------- SCENE 5: TRAP + CTA ----------
    img5 = Image.new("RGB", (W, H), "#07111F")
    d5 = ImageDraw.Draw(img5)
    draw_base(d5); draw_top_progress(d5, 4, 5)

    d5.text((90, 280), "EXAM TRAP", fill="#FBBF24", font=font_h2)
    d5.multiline_text(
        (90, 380),
        textwrap.fill(clean_hindi_postal_terms(script_data["sen3"]), 32),
        fill="#FFFFFF", font=font_title, spacing=12
    )

    d5.rounded_rectangle([90, 820, 990, 1030], radius=26,
                         fill="#10253A", outline="#22D3EE", width=3)
    d5.text((125, 855), "एक लाइन में याद करें", fill="#22D3EE", font=font_small)
    d5.multiline_text(
        (125, 910),
        textwrap.fill(clean_hindi_postal_terms(script_data["sen2"]), 34),
        fill="#FFFFFF", font=font_h2, spacing=8
    )

    d5.rounded_rectangle([90, 1190, 990, 1395], radius=28,
                         fill="#7C2D12", outline="#F59E0B", width=3)
    d5.multiline_text(
        (135, 1230),
        "अगला MCQ भी ऐसे ही\nपहले खुद solve कीजिए.",
        fill="#FFE9A6", font=font_h2, spacing=10
    )

    d5.rounded_rectangle([90, 1480, 990, 1610], radius=24,
                         fill="#E11D48")
    d5.text((300, 1520), "FOLLOW @POSTAL_WALA", fill="#FFFFFF", font=font_cta)
    draw_footer(d5, "Value पहले • CTA बाद में")
    img5.save("slide_5.png")

    slide_filenames = [f"slide_{i}.png" for i in range(1, 6)]

    # Give each slide its narration duration, with a small safety floor.
    FPS = 30
    inputs = []
    filter_parts = ""

    for i, fname in enumerate(slide_filenames):
        inputs.extend(["-loop", "1", "-i", fname])
        safe_dur = max(1.0, durations[i])

        # Tiny per-scene motion. The image itself is not static in playback.
        frames = max(1, round(safe_dur * FPS))
        zoom_step = ["0.0018", "0.0012", "0.0020", "0.0010", "0.0016"][i]
        fade_d = min(0.12, safe_dur / 5)
        fade_out_start = max(0.0, safe_dur - fade_d)

        filter_parts += (
            f"[{i}:v]"
            f"scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            f"zoompan=z='min(zoom+{zoom_step},1.055)':"
            f"d={frames}:"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"s=1080x1920:fps={FPS},"
            f"fade=t=in:st=0:d={fade_d},"
            f"fade=t=out:st={fade_out_start}:d={fade_d},"
            f"format=yuv420p[v{i}];"
        )

    concat_str = "".join([f"[v{i}]" for i in range(5)])
    video_filter = (
        f"{filter_parts}{concat_str}"
        f"concat=n=5:v=1:a=0,format=yuv420p[v]"
    )

    cmd = ["ffmpeg", "-y", *inputs, "-i", "final_master.mp3"]
    voice_idx = 5
    full_filter = (
        f"{video_filter};"
        f"[{voice_idx}:a]aresample=48000,"
        f"aformat=channel_layouts=stereo[a]"
    )
    cmd.extend([
        "-filter_complex", full_filter,
        "-map", "[v]", "-map", "[a]",
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
        "-ac", "2",
        "-movflags", "+faststart",
        "-shortest",
        output_video
    ])

    subprocess.run(cmd, check=True)
    print(f"✅ Retention-first Reel created: {output_video}", flush=True)

# --- LOCAL FOLDER SAVER FOR GITHUB WORKFLOW ---
def save_reel_to_local_folder(video_file, script_data):
    os.makedirs(REELS_DIR, exist_ok=True)
    clause_no = script_data.get("clause_no", 6)
    part_no = script_data.get("part_no", 1)
    dest_video = os.path.join(REELS_DIR, f"clause_{clause_no}_part_{part_no}.mp4")
    dest_txt = os.path.join(REELS_DIR, f"clause_{clause_no}_part_{part_no}_caption.txt")
    
    try:
        shutil.copy(video_file, dest_video)
        with open(dest_txt, "w", encoding="utf-8") as f:
            f.write(script_data.get("caption", ""))
        print(f"📁 Reel saved locally to: {dest_video}", flush=True)
        return True
    except Exception as e:
        print(f"⚠️ Local Save Error: {e}", flush=True)
        return False

# --- MAIN RUNNER (INSTAGRAM UPLOAD REMOVED, SAVES LOCALLY) ---
if __name__ == "__main__":
    st = load_progress_state()
    print(f"📌 Retention-first Reel: Clause {st['clause_no']} (Part {st['current_part']}/{st['total_parts']})", flush=True)
    
    script_data = generate_clause_script(st)
    render_and_sync_video(script_data, OUTPUT_VIDEO)

    saved_ok = save_reel_to_local_folder(OUTPUT_VIDEO, script_data)
    if saved_ok:
        advance_progress_state(st)
        print("✅ Reel generated, stored locally in generated_reels, and state updated.", flush=True)
    else:
        print("❌ Local save failed.", flush=True)
        sys.exit(1)
