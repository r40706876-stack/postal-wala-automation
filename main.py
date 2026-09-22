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

# --- Environment Variables ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

GRAPH_API_BASE = "https://graph.facebook.com/v19.0/"
RUPLOAD_BASE = "https://rupload.facebook.com/ig-api-upload/v19.0/"

STATE_FILE = "progress_state.json"
DEV_FONT_PATH = "NotoSansDevanagari-Bold.ttf"
OUTPUT_VIDEO = "final_reel.mp4"
BGM_OUTPUT = "bgm.mp3"
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
        "voice": "लिख कर ले लो, 2 नंबर पक्के हैं इस रील में, आइए देखते हैं कैसे",
        "visual_badge": "लिख कर ले लो! 2 नंबर पक्के"
    },
    {
        "voice": "90% लोग इस एक नियम में गलत उत्तर देकर आते हैं, क्या आप भी वही गलती कर रहे हैं",
        "visual_badge": "सावधान: 90% लोग फेल होते हैं!"
    },
    {
        "voice": "अगर सच में जीडीएस से प्रमोशन की तैयारी कर रहे हैं, तो इस सवाल का सही जवाब देकर दिखाइए",
        "visual_badge": "दम है तो सही उत्तर देकर दिखाओ!"
    },
    {
        "voice": "परीक्षा में बार-बार दोहराया जाने वाला यह नियम आज हमेशा के लिए रट लो",
        "visual_badge": "परीक्षा में बार-बार पूछा जाने वाला नियम"
    },
    {
        "voice": "इस साल जीडीएस से पोस्टमैन या पी.ए. बनना है, तो इस रील को स्किप मत करना",
        "visual_badge": "जीडीएस से प्रमोशन का पक्का मौका!"
    },
    {
        "voice": "डाक घर गाइड का यह छोटा सा क्लॉज कई लोगों का प्रमोशन रोक देता है, चलिए समझते हैं",
        "visual_badge": "चेतावनी: यह नियम प्रमोशन रोक सकता है!"
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
    strip_ranges = [
        (0x2190, 0x21FF), (0x2300, 0x23FF), (0x25A0, 0x25FF),
        (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0xFE0F, 0xFE0F),
    ]
    text = "".join(c for c in text if not any(lo <= ord(c) <= hi for lo, hi in strip_ranges))
    return text.strip()

def is_latin_run_char(ch):
    o = ord(ch)
    return (0x41 <= o <= 0x5A) or (0x61 <= o <= 0x7A)

def draw_mixed_line(draw, x, y, text, dev_font, eng_font, fill):
    cx = x
    run = ""
    run_is_latin = None
    for ch in text:
        latin = is_latin_run_char(ch)
        if run_is_latin is None:
            run_is_latin = latin
        if latin != run_is_latin:
            f = eng_font if run_is_latin else dev_font
            draw.text((cx, y), run, font=f, fill=fill)
            cx += draw.textlength(run, font=f)
            run = ""
            run_is_latin = latin
        run += ch
    if run:
        f = eng_font if run_is_latin else dev_font
        draw.text((cx, y), run, font=f, fill=fill)

def draw_mixed_multiline(draw, x, y, wrapped_text, dev_font, eng_font, fill, line_height):
    for i, line in enumerate(wrapped_text.split("\n")):
        draw_mixed_line(draw, x, y + i * line_height, line, dev_font, eng_font, fill)

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
    try:
        bk = Image.new("RGBA", (300, 420), (0, 0, 0, 0))
        db = ImageDraw.Draw(bk)
        db.rounded_rectangle([60, 55, 240, 365], radius=14, fill="#1E3A8A")
        db.rounded_rectangle([78, 62, 232, 358], radius=10, fill="#2563EB")
        db.rounded_rectangle([90, 62, 100, 358], fill="#1D4ED8")
        for ly in range(90, 340, 34):
            db.rounded_rectangle([112, ly, 214, ly + 10], radius=4, fill="#DBEAFE")
        bk.save(BOOK_3D_PATH, "PNG")
    except Exception:
        pass

    try:
        box = Image.new("RGBA", (300, 420), (0, 0, 0, 0))
        d = ImageDraw.Draw(box)
        d.rounded_rectangle([70, 160, 230, 350], radius=18, fill="#7F1D1D")
        d.pieslice([70, 90, 230, 250], start=180, end=360, fill="#7F1D1D")
        d.rounded_rectangle([85, 175, 215, 335], radius=14, fill="#DC2626")
        d.pieslice([85, 105, 215, 245], start=180, end=360, fill="#DC2626")
        d.rounded_rectangle([100, 195, 200, 212], radius=6, fill="#7F1D1D")
        d.polygon([(200, 130), (255, 110), (255, 160)], fill="#FBBF24")
        d.rounded_rectangle([195, 125, 208, 200], radius=4, fill="#4B5563")
        d.rounded_rectangle([40, 350, 260, 375], radius=10, fill="#374151")
        box.save(POSTBOX_3D_PATH, "PNG")
    except Exception:
        pass

    try:
        q = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
        dq = ImageDraw.Draw(q)
        dq.rounded_rectangle([40, 40, 260, 260], radius=40, fill="#D97706")
        dq.polygon([(110, 250), (150, 250), (110, 310)], fill="#D97706")
        try:
            qfont = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 150)
        except Exception:
            qfont = ImageFont.load_default()
        bbox = dq.textbbox((0, 0), "?", font=qfont)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        dq.text((150 - tw / 2 - bbox[0], 150 - th / 2 - bbox[1]), "?", fill="#FFFBEB", font=qfont)
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

    variety_idx = (current_clause * 7 + current_part) % 4
    question_bank = [
        f"डाक घर गाइड भाग 1, क्लॉज {current_clause} (भाग {current_part}) के अनुसार निम्नलिखित में से कौन सा कथन सही है?",
        f"क्लॉज {current_clause} भाग {current_part} में बताए गए नियम पर आधारित यह सवाल परीक्षा में बार-बार आता है - सही विकल्प चुनिए:",
        f"डाक घर गाइड भाग 1, क्लॉज {current_clause} (भाग {current_part}) से जुड़ा यह प्रश्न विभागीय परीक्षा में पूछा गया था:",
        f"क्लॉज {current_clause} भाग {current_part} पढ़कर बताइए, इनमें से कौन सा नियम के अनुसार सही है?",
    ]

    # FIX (retention bug — the big one): when the Groq call fails or the key
    # is missing, EVERY educational beat after the hook (sen2, sen3, and all
    # 4 MCQ options) used to come from these generic, clause-agnostic banks
    # below, and the correct answer was always hardcoded to "B". That means
    # on any video where Groq silently failed, the "quiz" was fake — no real
    # postal rule was ever tested, which guts the entire value proposition
    # ("100% official syllabus") the moment a repeat viewer notices the
    # pattern. This block now builds sen2/sen3/options from OTHER real parts
    # of the SAME clause (genuine distractor facts) whenever they exist, so
    # even a Groq-less fallback video still teaches something true and the
    # correct option/letter varies per video instead of always being B.
    other_part_texts = [
        clause_info[k] for k in clause_info
        if k.startswith("part_") and k.endswith("_focus") and k != part_key
    ]

    def _short(txt, max_chars=60):
        txt = txt.strip()
        return txt if len(txt) <= max_chars else txt[:max_chars - 1].rstrip() + "…"

    if other_part_texts:
        sen2_fallback = f"इसी नियम का एक और अहम पहलू: {_short(other_part_texts[0])}"
    else:
        sen2_fallback = f"{clause_name} से जुड़ी शर्तों को याद न रखने पर परीक्षा में सीधे नंबर कट जाते हैं।"

    sen3_bank = [
        f"ध्यान दें: {clause_name} के इस हिस्से में परीक्षार्थी अक्सर जल्दबाज़ी में गलत विकल्प चुन लेते हैं।",
        f"ज्यादातर उम्मीदवार {clause_name} के इस नियम को पूरा पढ़े बिना ही जवाब दे देते हैं।",
        f"{clause_name} के इस बिंदु में शब्दों का हल्का फेरबदल करके गलत विकल्प सही जैसा दिखाया जाता है।",
        f"{clause_name} से जुड़ा यह भाग हर वर्ष परीक्षा में दोहराया जाता है, ध्यान से पढ़ें।",
    ]

    # Build MCQ options from real clause content instead of static placeholders.
    correct_opt = _short(part_focus, 40)
    distractor_pool = [_short(t, 40) for t in other_part_texts] or [
        f"{clause_name} पर यह नियम लागू नहीं होता"
    ]
    opts = [correct_opt] + distractor_pool[:2] + ["इनमें से कोई नहीं"]
    while len(opts) < 4:
        opts.append("इनमें से कोई नहीं")
    opts = opts[:4]
    correct_letter = "ABCD"[0]  # correct_opt is placed first, then rotated below
    rotate = variety_idx % 4
    opts = opts[rotate:] + opts[:rotate]
    correct_letter = "ABCD"[opts.index(correct_opt)]

    fallback_data = {
        "clause_no": current_clause,
        "clause_name": clause_name,
        "part_no": current_part,
        "total_parts": total_parts,
        "visual_hook_badge": hook_obj["visual_badge"],
        "hook_voice": hook_obj["voice"],
        "question": question_bank[variety_idx],
        "sen1": f"डाक घर गाइड भाग 1 के क्लॉज {current_clause} के अनुसार {part_focus}",
        "sen2": sen2_fallback,
        "sen3": sen3_bank[variety_idx],
        "opt_a": opts[0],
        "opt_b": opts[1],
        "opt_c": opts[2],
        "opt_d": opts[3],
        "correct_letter": correct_letter,
        "caption": f"🚨 90% लोग इस नियम में गलती करते हैं! डाक घर गाइड भाग 1 | क्लॉज {current_clause} (भाग {current_part}/{total_parts})। सही उत्तर वीडियो में है, जवाब मिला तो 🔥 कमेंट करें! फ्री विभागीय नोट्स व टेस्ट हेतु WhatsApp करें: 8989971379 #PostalWala #GDStoMTS #PostmanExam #IndiaPost"
    }

    if not GROQ_API_KEY:
        print("🛑 GROQ_API_KEY is not set - using clause-specific fallback script (Groq unavailable).", flush=True)
        return fallback_data

    prompt = f"""
    You are the Senior Chief Instructor for India Post Departmental Examinations running 'Postal Wala'.
    TOPIC: Book: 'Post Office Guide Part 1'
    Clause Number: क्लॉज {current_clause}, Title: {clause_name}, Part: {current_part}/{total_parts}
    Sub-Rule Specific Focus for this Part: "{part_focus}"

    Generate strictly based on this part's sub-rule. Keep every sentence SHORT and punchy (max ~16 words) - this is a fast-paced Reel, not an essay:
    QUESTION: [1 crisp high-yield departmental exam MCQ question directly testing this specific part focus, max 18 words]
    SEN1: [Core explanation of this part's rule in pure simple Hindi, max 16 words]
    SEN2: [Crucial condition, timing, limit or penalty for this part, max 16 words]
    SEN3: [Official departmental exception or exam trap point, max 16 words]
    OPT_A: [Option A - max 6 words]
    OPT_B: [Option B - max 6 words]
    OPT_C: [Option C - max 6 words]
    OPT_D: [Option D - max 6 words]
    CORRECT: [Only the single correct letter: A, B, C or D]
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
            print("✅ Groq: AI-generated clause-specific content used for this video.", flush=True)
    except Exception as e:
        print(f"🛑 Groq call failed ({e}) - falling back to clause-specific template for this video.", flush=True)

    return fallback_data

def get_correct_option_text(script_data):
    letter = script_data.get("correct_letter", "B").strip().upper()
    key = f"opt_{letter.lower()}"
    return letter, script_data.get(key, script_data.get("opt_b", ""))

def get_slide_segments(script_data):
    q_txt = script_data["question"]
    hook_v = script_data["hook_voice"]
    letter, correct_text = get_correct_option_text(script_data)
    return [
        f"{hook_v}",
        f"आज का सवाल: {q_txt}",
        f"{script_data['sen1']}",
        f"{script_data['sen2']}",
        f"परीक्षा ट्रैप: {script_data['sen3']} अपना जवाब कमेंट करें!",
        f"सही जवाब है विकल्प {letter}: {correct_text}। सही था तो कमेंट करें, और अगले भाग के लिए फॉलो करें!"
    ]

async def generate_segment_audio(text, outfile):
    if os.path.exists(outfile):
        try: os.remove(outfile)
        except Exception: pass
    communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+5%")
    await communicate.save(outfile)
    _tighten_audio_silence(outfile)

def _tighten_audio_silence(path):
    tmp_path = path + ".tight.mp3"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", path,
            "-af", "silenceremove=start_periods=1:start_duration=0:start_threshold=-35dB:"
                   "stop_periods=-1:stop_duration=0.15:stop_threshold=-35dB:window=0.05:detection=peak",
            "-c:a", "libmp3lame", "-b:a", "192k", tmp_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 500:
            os.replace(tmp_path, path)
    except Exception as e:
        print(f"⚠️ Silence-trim skipped for {path}: {e}", flush=True)
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except Exception: pass

def get_audio_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    return float(subprocess.check_output(cmd).decode().strip())

def render_and_sync_video(script_data, output_video=OUTPUT_VIDEO):
    ensure_fonts()
    ensure_auto_icons()

    segment_audios = get_slide_segments(script_data)
    raw_durations = []
    
    n_segments = len(segment_audios)
    for i, seg_text in enumerate(segment_audios):
        seg_file = f"audio_seg_{i}.mp3"
        asyncio.run(generate_segment_audio(seg_text, seg_file))
        raw_durations.append(get_audio_duration(seg_file))

    concat_filter = "".join([f"[{i}:a]" for i in range(n_segments)]) + f"concat=n={n_segments}:v=0:a=1[aout]"
    ffmpeg_concat_cmd = ["ffmpeg", "-y"]
    for i in range(n_segments):
        ffmpeg_concat_cmd.extend(["-i", f"audio_seg_{i}.mp3"])
    ffmpeg_concat_cmd.extend(["-filter_complex", concat_filter, "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "raw_master.mp3"])
    subprocess.run(ffmpeg_concat_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    total_dur = get_audio_duration("raw_master.mp3")
    print(f"🎵 Raw Master Duration: {total_dur:.2f}s", flush=True)

    MIN_TARGET_DUR = 22.0
    MAX_TARGET_DUR = 34.0
    if total_dur < MIN_TARGET_DUR:
        tempo_scale = max(0.88, round(total_dur / MIN_TARGET_DUR, 4))
    elif total_dur > MAX_TARGET_DUR:
        tempo_scale = min(1.22, round(total_dur / MAX_TARGET_DUR, 4))
    else:
        tempo_scale = 1.0

    if tempo_scale != 1.0:
        subprocess.run(["ffmpeg", "-y", "-i", "raw_master.mp3", "-filter:a", f"atempo={tempo_scale}", "final_master.mp3"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run(["ffmpeg", "-y", "-i", "raw_master.mp3", "-c:a", "copy", "final_master.mp3"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    durations = [d / tempo_scale for d in raw_durations]
    print(f"🎬 Final Video Duration: {sum(durations):.1f}s (Pace Scale: {tempo_scale})", flush=True)

    font_brand = get_eng_font(44)
    font_sub = get_eng_font(22)
    font_trust = get_eng_font(20)
    font_badge = get_dev_font(22)
    font_title = get_dev_font(34)
    font_h2 = get_dev_font(30)
    font_body = get_dev_font(32)
    font_label = get_dev_font(26)
    font_wa_hin = get_dev_font(30)
    font_wa_num = get_eng_font(30)
    font_cta = get_eng_font(30)
    font_cta_dev = get_dev_font(30)
    font_opt = get_dev_font(26)
    font_hook = get_dev_font(30)
    font_title_eng = get_eng_font(34)
    font_body_eng = get_eng_font(32)
    font_opt_eng = get_eng_font(26)
    font_hook_eng = get_eng_font(30)
    font_h2_eng = get_eng_font(30)

    def draw_base(d):
        d.rounded_rectangle([45, 50, 1035, 1710], radius=32, fill="#0B132B", outline="#1E293B", width=3)
        d.text((80, 75), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        d.text((80, 130), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)
        d.rounded_rectangle([630, 80, 1000, 132], radius=16, fill="#064E3B", outline="#10B981", width=2)
        d.text((655, 93), "100% OFFICIAL SYLLABUS", fill="#D1FAE5", font=font_trust)

    def draw_whatsapp_strip_at(d, y=345):
        d.rounded_rectangle([80, y, 1000, y + 130], radius=18, fill="#064E3B", outline="#34D399", width=2)
        d.text((110, y + 17), "GDS to MTS • Postman • Mail Guard • P.A.", fill="#FDE047", font=font_wa_num)
        d.text((110, y + 67), "कोर्स व फ्री टेस्ट हेतु व्हाट्सएप: 8989971379", fill="#FFFFFF", font=font_wa_hin)

    def draw_footer_cta(d):
        d.rounded_rectangle([80, 1580, 1000, 1680], radius=22, fill="#E11D48")
        d.text((120, 1605), "पूरी तैयारी के लिए फॉलो करें:", fill="#FFFFFF", font=font_cta_dev)
        d.text((580, 1605), "@POSTAL_WALA", fill="#FFFFFF", font=font_cta)

    def paste_safe_asset(base_img, path, pos, size=(280, 360)):
        if os.path.exists(path):
            try:
                ic = Image.open(path).convert("RGBA").resize(size, RESAMPLE_MODE)
                base_img.paste(ic, pos, ic)
            except Exception:
                pass

    def draw_progress_dots(d, current_idx, total):
        dot_r = 9
        gap = 28
        total_w = (total - 1) * gap
        start_x = 540 - total_w // 2
        y = 158
        for i in range(total):
            cx = start_x + i * gap
            if i == current_idx:
                d.ellipse([cx - dot_r, y - dot_r, cx + dot_r, y + dot_r], fill="#F43F5E")
            else:
                d.ellipse([cx - 6, y - 6, cx + 6, y + 6], fill="#334155")

    def draw_header(d, script_data, title_override=None):
        d.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
        d.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
        d.text((120, 198), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
        d.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
        d.text((845, 198), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
        title_text = title_override if title_override else clean_hindi_postal_terms(script_data["clause_name"])
        draw_mixed_line(d, 105, 255, title_text, font_title, font_title_eng, "#FFFFFF")

    def draw_checkmark(base_img, cx, cy, r=46):
        dchk = ImageDraw.Draw(base_img)
        dchk.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#10B981")
        dchk.line([cx - r * 0.5, cy, cx - r * 0.12, cy + r * 0.4], fill="#FFFFFF", width=10)
        dchk.line([cx - r * 0.12, cy + r * 0.4, cx + r * 0.55, cy - r * 0.4], fill="#FFFFFF", width=10)

    slide_filenames = []
    TOTAL_SLIDES = 6

    letter, correct_text = get_correct_option_text(script_data)

    img1 = Image.new("RGB", (1080, 1920), color="#060A17")
    d1 = ImageDraw.Draw(img1)
    draw_base(d1)
    draw_progress_dots(d1, 0, TOTAL_SLIDES)
    draw_header(d1, script_data)
    d1.rounded_rectangle([80, 420, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)
    d1.rounded_rectangle([110, 460, 970, 560], radius=14, fill="#991B1B", outline="#FBBF24", width=3)
    wrapped_hook = textwrap.fill(clean_hindi_postal_terms(script_data["visual_hook_badge"]), width=22)
    draw_mixed_multiline(d1, 160, 480, wrapped_hook, font_hook, font_hook_eng, "#FEF08A", line_height=40)
    # FIX (retention bug): previously the first ~7s of the video showed ONLY
    # a decorative "?" icon and a vague "wait till the end" line — zero real
    # information within the critical 0-2s skip window. This adds a concrete,
    # topic-specific teaser (drawn from the actual rule text) so a viewer
    # gets real substance in the very first frame, not just clickbait.
    d1.rounded_rectangle([110, 585, 970, 685], radius=14, fill="#0B132B", outline="#38BDF8", width=2)
    teaser_source = script_data.get("sen1", "") or script_data.get("clause_name", "")
    teaser_text = clean_hindi_postal_terms(teaser_source)
    if len(teaser_text) > 70:
        teaser_text = teaser_text[:68].rstrip() + "..."
    wrapped_teaser = textwrap.fill(teaser_text, width=28)
    draw_mixed_multiline(d1, 140, 605, wrapped_teaser, font_label, font_h2_eng, "#7DD3FC", line_height=32)
    paste_safe_asset(img1, QUIZ_3D_PATH, pos=(390, 760), size=(280, 360))
    d1.rounded_rectangle([110, 1180, 970, 1290], radius=16, fill="#064E3B", outline="#34D399", width=2)
    d1.text((150, 1218), ">> अंत तक रुको, सही जवाब वहीं मिलेगा!", fill="#D1FAE5", font=font_label)
    draw_footer_cta(d1)
    img1.save("slide_1.png")
    slide_filenames.append("slide_1.png")

    img2 = Image.new("RGB", (1080, 1920), color="#060A17")
    d2 = ImageDraw.Draw(img2)
    draw_base(d2)
    draw_progress_dots(d2, 1, TOTAL_SLIDES)
    draw_header(d2, script_data)
    d2.rounded_rectangle([80, 420, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)
    d2.rounded_rectangle([110, 460, 400, 515], radius=10, fill="#0B132B")
    d2.text((140, 470), "आज का सवाल:", fill="#38BDF8", font=font_label)
    wrapped_q = textwrap.fill(clean_hindi_postal_terms(script_data["question"]), width=23)
    draw_mixed_multiline(d2, 115, 555, wrapped_q, font_title, font_title_eng, "#F8FAFC", line_height=48)
    paste_safe_asset(img2, QUIZ_3D_PATH, pos=(390, 1080), size=(300, 400))
    draw_footer_cta(d2)
    img2.save("slide_2.png")
    slide_filenames.append("slide_2.png")

    img3 = Image.new("RGB", (1080, 1920), color="#060A17")
    d3 = ImageDraw.Draw(img3)
    draw_base(d3)
    draw_progress_dots(d3, 2, TOTAL_SLIDES)
    draw_header(d3, script_data)
    d3.rounded_rectangle([80, 420, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)
    d3.rounded_rectangle([110, 460, 480, 510], radius=10, fill="#0B132B")
    d3.text((150, 468), "नियम क्या कहता है:", fill="#38BDF8", font=font_label)
    wrapped_s1 = textwrap.fill(clean_hindi_postal_terms(script_data['sen1']), width=22)
    draw_mixed_multiline(d3, 115, 545, wrapped_s1, font_body, font_body_eng, "#F8FAFC", line_height=50)
    paste_safe_asset(img3, POSTBOX_3D_PATH, pos=(400, 1150))
    draw_footer_cta(d3)
    img3.save("slide_3.png")
    slide_filenames.append("slide_3.png")

    img4 = Image.new("RGB", (1080, 1920), color="#060A17")
    d4 = ImageDraw.Draw(img4)
    draw_base(d4)
    draw_progress_dots(d4, 3, TOTAL_SLIDES)
    draw_header(d4, script_data)
    d4.rounded_rectangle([80, 420, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)
    d4.rounded_rectangle([110, 460, 480, 510], radius=10, fill="#0B132B")
    d4.text((150, 468), "जरूरी शर्त / सीमा:", fill="#FBBF24", font=font_label)
    wrapped_s2 = textwrap.fill(clean_hindi_postal_terms(script_data['sen2']), width=22)
    draw_mixed_multiline(d4, 115, 545, wrapped_s2, font_body, font_body_eng, "#F8FAFC", line_height=50)
    paste_safe_asset(img4, BOOK_3D_PATH, pos=(400, 1150))
    draw_footer_cta(d4)
    img4.save("slide_4.png")
    slide_filenames.append("slide_4.png")

    img5 = Image.new("RGB", (1080, 1920), color="#060A17")
    d5 = ImageDraw.Draw(img5)
    draw_base(d5)
    draw_progress_dots(d5, 4, TOTAL_SLIDES)
    draw_header(d5, script_data, title_override="परीक्षा ट्रैप: जवाब चुनो")
    d5.rounded_rectangle([80, 420, 1000, 1550], radius=24, fill="#1C2541", outline="#FBBF24", width=2)
    d5.rounded_rectangle([110, 448, 480, 498], radius=10, fill="#0B132B")
    d5.text((150, 456), "परीक्षा में फंसाने वाला बिंदु:", fill="#F87171", font=font_label)
    wrapped_trap = textwrap.fill(clean_hindi_postal_terms(script_data['sen3']), width=30)
    trap_lines = wrapped_trap.count("\n") + 1
    draw_mixed_multiline(d5, 115, 515, wrapped_trap, font_opt, font_opt_eng, "#F8FAFC", line_height=42)

    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    oy = 515 + (trap_lines * 42) + 25
    for o_idx, opt in enumerate(opts):
        d5.rounded_rectangle([110, oy, 970, oy + 68], radius=12, fill="#0B132B", outline="#38BDF8", width=2)
        d5.text((135, oy + 16), f"{chr(65+o_idx)})", fill="#38BDF8", font=font_h2_eng)
        wrapped_opt = textwrap.fill(clean_hindi_postal_terms(opt), width=24)
        draw_mixed_multiline(d5, 200, oy + 17, wrapped_opt, font_opt, font_opt_eng, "#FFFFFF", line_height=34)
        oy += 80

    cta_y = min(1460, oy + 15)
    d5.rounded_rectangle([110, cta_y, 970, cta_y + 70], radius=18, fill="#0B132B", outline="#F59E0B", width=2)
    d5.text((150, cta_y + 20), "अपना जवाब अभी कमेंट करें!", fill="#FDE047", font=font_h2)
    draw_footer_cta(d5)
    img5.save("slide_5.png")
    slide_filenames.append("slide_5.png")

    img6 = Image.new("RGB", (1080, 1920), color="#060A17")
    d6 = ImageDraw.Draw(img6)
    draw_base(d6)
    draw_progress_dots(d6, 5, TOTAL_SLIDES)
    draw_header(d6, script_data, title_override="सही जवाब यहां देखो!")
    d6.rounded_rectangle([80, 420, 1000, 1550], radius=24, fill="#1C2541", outline="#10B981", width=3)
    draw_checkmark(img6, 165, 500, r=40)
    draw_mixed_line(d6, 225, 470, f"सही उत्तर: विकल्प {letter}", font_title, font_title_eng, "#34D399")
    d6.rounded_rectangle([110, 560, 970, 700], radius=16, fill="#064E3B", outline="#10B981", width=3)
    wrapped_correct = textwrap.fill(clean_hindi_postal_terms(correct_text), width=26)
    draw_mixed_multiline(d6, 145, 590, wrapped_correct, font_h2, font_h2_eng, "#ECFDF5", line_height=42)
    d6.rounded_rectangle([110, 745, 970, 845], radius=16, fill="#0B132B", outline="#FBBF24", width=2)
    d6.text((145, 775), "सही मिला? कमेंट में जरूर लिखो!", fill="#FDE047", font=font_h2)
    draw_whatsapp_strip_at(d6, y=880)
    d6.rounded_rectangle([110, 1010, 970, 1110], radius=16, fill="#1E293B", outline="#38BDF8", width=2)
    d6.text((145, 1042), "अगला भाग जल्द आ रहा है — मिस मत करना!", fill="#93C5FD", font=font_label)
    draw_footer_cta(d6)
    img6.save("slide_6.png")
    slide_filenames.append("slide_6.png")

    FPS = 30
    inputs = []
    filter_parts = ""
    for i, fname in enumerate(slide_filenames):
        inputs.extend(["-i", fname])
        safe_dur = max(1.0, durations[i])
        frames = max(1, round(safe_dur * FPS))
        fade_d = min(0.2, safe_dur / 5)
        fade_out_start = max(0.0, safe_dur - fade_d)
        settle_frames = max(1, min(10, frames // 3))
        # FIX (retention bug): old formula zoomed up to 1.12x and cropped
        # centered, which pushed the "POSTAL WALA" header/badge off the top
        # of the frame for most of every slide's runtime. Capped at 1.05x
        # and anchored to the top (y='0') so the header stays fully visible
        # for the entire video; only the lower, less critical area trims.
        zoom_expr = (
            f"if(lte(on,{settle_frames}),1.05-(0.05*on/{settle_frames}),"
            f"min(1.0+0.0007*(on-{settle_frames}),1.05))"
        )
        filter_parts += (
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            f"zoompan=z='{zoom_expr}':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='0':s=1080x1920:fps={FPS},"
            f"fade=t=in:st=0:d={fade_d},fade=t=out:st={fade_out_start}:d={fade_d},"
            f"format=yuv420p[v{i}]; "
        )

    concat_str = "".join([f"[v{i}]" for i in range(len(slide_filenames))])
    TOTAL_VIDEO_DUR = sum(max(1.0, d) for d in durations)
    video_filter = (
        f"{filter_parts}{concat_str}concat=n={len(slide_filenames)}:v=1:a=0,"
        f"drawbox=x=0:y=0:w='iw*min(t/{TOTAL_VIDEO_DUR},1)':h=10:color=#F43F5E:t=fill,"
        f"format=yuv420p[v]"
    )

    cmd = ["ffmpeg", "-y", *inputs, "-i", "final_master.mp3"]
    voice_idx = len(slide_filenames)

    full_filter = f"{video_filter}; [{voice_idx}:a]aresample=48000,aformat=channel_layouts=stereo[a]"
    cmd.extend(["-filter_complex", full_filter, "-map", "[v]", "-map", "[a]"])
    cmd.extend([
        "-c:v", "libx264", "-preset", "medium", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-shortest", output_video
    ])

    subprocess.run(cmd, check=True)
    print(f"✅ Reel Created: {output_video}", flush=True)

# --- MAIN RUNNER ---
if __name__ == "__main__":
    st = load_progress_state()
    print(f"📌 Running Target: Clause {st['clause_no']} (Part {st['current_part']}/{st['total_parts']})", flush=True)
    
    script_data = generate_clause_script(st)
    render_and_sync_video(script_data, OUTPUT_VIDEO)

    # Save to generated_reels section folder for GitHub
    os.makedirs("generated_reels", exist_ok=True)
    target_reel_path = os.path.join("generated_reels", f"reel_clause_{st['clause_no']}_part_{st['current_part']}.mp4")
    with open(OUTPUT_VIDEO, "rb") as src, open(target_reel_path, "wb") as dst:
        dst.write(src.read())
    print(f"✅ Reel saved to generated reels section: {target_reel_path}", flush=True)

    advance_progress_state(st)
    print("✅ State successfully shifted to next part.", flush=True)
