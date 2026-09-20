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
RUPLOAD_BASE = "https://rupload.facebook.com/ig-api-upload/"

STATE_FILE = "progress_state.json"
FONT_PATH = "Mukta-Bold.ttf"
OUTPUT_VIDEO = "final_reel.mp4"
BGM_OUTPUT = "bgm.mp3"
VOICE_NAME = "hi-IN-SwaraNeural"

# Assets Directory
ASSETS_DIR = "assets"
BOOK_3D_PATH = os.path.join(ASSETS_DIR, "3d_book.png")
POSTBOX_3D_PATH = os.path.join(ASSETS_DIR, "3d_postbox.png")
QUIZ_3D_PATH = os.path.join(ASSETS_DIR, "3d_quiz.png")

RESAMPLE_MODE = getattr(Image, "Resampling", Image).LANCZOS

# --- High-Retention Hooks (Crisp & Fast) ---
VIRAL_HOOKS = [
    {
        "voice": "लिख कर ले लो! विभागीय परीक्षा में यह नियम बार-बार पूछा जाता है, आइए देखते हैं!",
        "visual_badge": "लिख कर ले लो! 2 नंबर पक्के",
        "hook_text": "विभागीय परीक्षा में बार-बार आने वाला सबसे महत्वपूर्ण नियम!"
    },
    {
        "voice": "जीडीएस से एमटीएस और पोस्टमैन परीक्षा में 90% लोग इस एक नियम में गलती करते हैं!",
        "visual_badge": "सावधान: 90% लोग फेल होते हैं!",
        "hook_text": "90% परीक्षार्थी इस नियम में गलत उत्तर देकर आते हैं!"
    },
    {
        "voice": "अगर इस बार प्रमोशन पक्का करना है, तो इस नियम को ध्यान से समझ लो!",
        "visual_badge": "दम है तो सही उत्तर देकर दिखाओ!",
        "hook_text": "इस बार जीडीएस से प्रमोशन पक्का करने के लिए यह नियम समझें!"
    },
    {
        "voice": "डाक विभाग की परीक्षा का सबसे पसंदीदा नियम! 25 सेकंड में इसे हमेशा के लिए रट लो!",
        "visual_badge": "परीक्षा में बार-बार आने वाला नियम",
        "hook_text": "डाक विभाग की परीक्षाओं में बार-बार दोहराया जाने वाला क्लॉज!"
    },
    {
        "voice": "अगर पोस्टमैन या पी.ए. बनना है, तो इस रील को 1 सेकंड भी स्किप मत करना!",
        "visual_badge": "जीडीएस से प्रमोशन का पक्का मौका!",
        "hook_text": "जीडीएस से पोस्टमैन या पी.ए. बनने के लिए अनिवार्य नियम!"
    },
    {
        "voice": "क्या आपको पता है? डाक घर गाइड का यह नियम कई लोगों का प्रमोशन रोक देता है!",
        "visual_badge": "चेतावनी: यह नियम प्रमोशन रोक सकता है!",
        "hook_text": "सावधान: इस नियम की गलती आपका प्रमोशन रोक सकती है!"
    }
]

# --- Master Catalog: Naturally Sized Parts (Clauses 1 to 60 Complete) ---
POSTAL_CLAUSE_CATALOG = {
    1: {
        "name": "डाक विभाग का नियंत्रण व संगठन", "total_parts": 2,
        "part_1_focus": "संचार मंत्रालय के अधीन महानिदेशक शीर्ष प्रशासनिक प्रमुख हैं और मुख्यालय डाक भवन नई दिल्ली में है।",
        "part_2_focus": "डाक सेवा बोर्ड में एक चेयरमैन और 6 पूर्णकालिक सदस्य होते हैं जो कार्मिक, प्रचालन व तकनीक देखते हैं।"
    },
    2: {
        "name": "डाकघरों के प्रकार और श्रेणियां", "total_parts": 3,
        "part_1_focus": "डाकघर की 3 प्रमुख श्रेणियां हैं: प्रधान डाकघर, उप डाकघर और शाखा डाकघर। प्रधान डाकघर मुख्य लेखा कार्यालय है।",
        "part_2_focus": "उप डाकघर प्रधान डाकघर के अधीन रहकर लेन-देन करता है और दैनिक लेखा प्रेषित करता है।",
        "part_3_focus": "शाखा डाकघर के कार्य के घंटे न्यूनतम 4 घंटे और अधिकतम 5 घंटे प्रतिदिन निर्धारित हैं।"
    },
    3: {
        "name": "रात्रि डाकघर के नियम", "total_parts": 3,
        "part_1_focus": "रात्रि डाकघर के कामकाज के घंटे रात 8:30 बजे तक बढ़ाने का विशेष अधिकार केवल महानिदेशक को है।",
        "part_2_focus": "रविवार और अवकाशों पर रात्रि डाकघर सुबह 10 से शाम 5 बजे तक केवल सीमित सेवाएं देते हैं।",
        "part_3_focus": "रात्रि डाकघरों में रविवार और अवकाश के दिनों में कोई भी मनीऑर्डर या बचत बैंक कार्य नहीं होता।"
    },
    4: {
        "name": "मोबाइल डाकघर की व्यवस्था", "total_parts": 2,
        "part_1_focus": "मोबाइल डाकघर बड़े शहरों में देर शाम तक सामान्य डाक व पार्सल बुकिंग की सुविधा देते हैं।",
        "part_2_focus": "मोबाइल डाकघर में मनीऑर्डर, बचत बैंक और बीमा का कोई भी कार्य करना पूर्णतः प्रतिबंधित है।"
    },
    5: {
        "name": "डाकघर के कामकाज के घंटे", "total_parts": 3,
        "part_1_focus": "सामान्य डाक टिकट बिक्री पूरे समय तक होती है, जबकि बचत बैंक और मनीऑर्डर कार्य पहले समाप्त होता है।",
        "part_2_focus": "सार्वजनिक काउंटर बंद होने के बाद निर्धारित लेट फीस का भुगतान करके ही डाक बुक होती है।",
        "part_3_focus": "शनिवार को सामान्य डाक लेन-देन के समय में कटौती के विभागीय नियम लागू होते हैं।"
    },
    6: {
        "name": "रविवार और डाक अवकाश पर कार्य", "total_parts": 2,
        "part_1_focus": "रविवार और 16 राजपत्रित अवकाशों पर सामान्य डाकघर पूरी तरह बंद रहते हैं।",
        "part_2_focus": "रविवार और डाक अवकाशों पर रात्रि डाकघर में कोई मनीऑर्डर या बचत बैंक निकासी कार्य नहीं होता।"
    },
    7: {
        "name": "डाक टिकटों और लेखन-सामग्री का विक्रय", "total_parts": 2,
        "part_1_focus": "प्रत्येक डाकघर में कार्य के निर्धारित घंटों के दौरान जनता के लिए डाक टिकट उपलब्ध कराना अनिवार्य है।",
        "part_2_focus": "डाक टिकट क्रय करते समय काउंटर पर सही और वैध मुद्रा में भुगतान करना ग्राहक का दायित्व है।"
    },
    8: {
        "name": "फिलाटेलिक ब्यूरो और डाक टिकट संग्रह", "total_parts": 2,
        "part_1_focus": "फिलाटेलिक ब्यूरो विशेष स्मारक डाक टिकटों और प्रथम दिवस आवरण का वितरण और बिक्री करते हैं।",
        "part_2_focus": "फिलाटेलिक डिपॉजिट खाता खोलकर संग्राहक नए जारी होने वाले डाक टिकट सीधे घर बैठे मंगा सकते हैं।"
    },
    9: {
        "name": "फ्रैंकिंग मशीन के विस्तृत नियम", "total_parts": 5,
        "part_1_focus": "फ्रैंकिंग मशीन का लाइसेंस डाक महानिदेशक या मंडल प्रमुख द्वारा जारी किया जाता है।",
        "part_2_focus": "फ्रैंकिंग मशीन की छाप चमकीले लाल रंग की स्याही में छपना अनिवार्य है।",
        "part_3_focus": "फ्रैंकिंग मशीन के अग्रिम रीसेट भुगतान पर निर्धारित प्रतिशत का विभागीय कमीशन छूट मिलता है।",
        "part_4_focus": "फ्रैंक की गई डाक को सामान्य लेटर बॉक्स में डालना वर्जित है, इसे खिड़की पर देना होता है।",
        "part_5_focus": "गलत छाप लग जाने पर 3 माह के भीतर 5% कटौती के बाद रिफंड का दावा किया जा सकता है।"
    },
    10: {
        "name": "अप्रयुक्त व जाली टिकटों का निषेध", "total_parts": 1,
        "part_1_focus": "प्रयुक्त डाक टिकटों का पुनः उपयोग करना भारतीय कानून के तहत दंडनीय अपराध है।"
    },
    11: {
        "name": "डाक महसूल का अग्रिम भुगतान", "total_parts": 2,
        "part_1_focus": "डाक वस्तुओं पर डाकभार का पूर्ण अग्रिम भुगतान अनिवार्य है ताकि डाक का त्वरित प्रेषण हो।",
        "part_2_focus": "अवैतनिक या कम भुगतान वाली डाक पर वितरण के समय सामान्य डाक शुल्क से दोगुना प्रभार वसूला जाता है।"
    },
    12: {
        "name": "डाक टिकट चिपकाने की सही विधि", "total_parts": 1,
        "part_1_focus": "लिफाफे के पते वाले भाग पर ऊपर दाहिने कोने में ही डाक टिकट चिपकाना अनिवार्य नियम है।",
    },
    13: {
        "name": "विशेष सुरक्षा लिफाफों का प्रयोग", "total_parts": 1,
        "part_1_focus": "मूल्यवान वस्तुओं और रजिस्टर्ड डाक हेतु वाटरप्रूफ सुरक्षा लिफाफों का उपयोग अनुशंसित है।"
    },
    14: {
        "name": "पत्र-पेटी में पोस्टिंग के नियम", "total_parts": 3,
        "part_1_focus": "लेटर बॉक्स में केवल सामान्य पत्र और पोस्टकार्ड ही डाले जाने चाहिए।",
        "part_2_focus": "पार्सल या रजिस्ट्री यदि लेटर बॉक्स में डाले जाएं तो उन्हें अवैतनिक मानकर दोगुना शुल्क लगता है।",
        "part_3_focus": "ग्रीन लेटर बॉक्स लोकल डाक हेतु और ब्लू लेटर बॉक्स मेट्रो शहरों की डाक हेतु होते हैं।"
    },
    15: {
        "name": "पोस्टिंग का समय व निकासी घंटे", "total_parts": 1,
        "part_1_focus": "लेटर बॉक्स निकासी प्लेट पर अंकित घंटों के अनुसार ही डाकिया पत्र-पेटी खोलता है।"
    },
    16: {
        "name": "डाक पर पता लिखने की सही विधि", "total_parts": 2,
        "part_1_focus": "प्राप्तकर्ता का नाम, सही पिन कोड और मोबाइल नंबर पते पर स्पष्ट अक्षरों में लिखना अनिवार्य है।",
        "part_2_focus": "प्रेषक का पूरा नाम व पता हमेशा वस्तु के निचले बाएं कोने में 'From' लिखकर दर्ज होना चाहिए।"
    },
    17: {
        "name": "पिन कोड प्रणाली", "total_parts": 2,
        "part_1_focus": "6 अंकों के पिन कोड में पहला अंक भौगोलिक ज़ोन और दूसरा अंक उप-ज़ोन दर्शाता है।",
        "part_2_focus": "पिन कोड के अंतिम तीन अंक उस विशिष्ट वितरण डाकघर की पहचान करते हैं।"
    },
    18: {
        "name": "पोस्टमैन और खिड़की वितरण नियम", "total_parts": 2,
        "part_1_focus": "डाकघर की खिड़की पर विशेष वितरण हेतु अनुमति लेनी होती है और हस्ताक्षर अनिवार्य हैं।",
        "part_2_focus": "डाकिया द्वारा वितरण के दौरान पतेदार के न मिलने पर सूचना पर्ची जारी की जाती है।"
    },
    19: {
        "name": "पोस्ट बॉक्स सुविधा", "total_parts": 3,
        "part_1_focus": "पोस्ट बॉक्स का किराया देकर केवल पूर्ण भुगतान वाले अपंजीकृत पत्रों का वितरण प्राप्त होता है।",
        "part_2_focus": "पोस्ट बॉक्स की चाबी खोने पर किराएदार को नया ताला लगाने का शुल्क देना होता है।",
        "part_3_focus": "नियमित डाक निकासी न करने पर डाकघर पोस्ट बॉक्स का आवंटन रद्द कर सकता है।"
    },
    20: {
        "name": "पोस्ट बैग सुविधा", "total_parts": 2,
        "part_1_focus": "पोस्ट बैग की सुविधा उन फर्मों के लिए है जिनकी भारी डाक आती है, इसमें बंद थैला मिलता है।",
        "part_2_focus": "पोस्ट बॉक्स और पोस्ट बैग संयुक्त रूप से किराए पर लेने पर रियायती वार्षिक शुल्क लगता है।"
    },
    21: {
        "name": "विशेष पहचान पत्र", "total_parts": 1,
        "part_1_focus": "डाकघर द्वारा जारी पहचान पत्र 3 वर्ष की अवधि तक वैध रहता है।"
    },
    22: {
        "name": "डाक का पुनः निर्देशन", "total_parts": 3,
        "part_1_focus": "पतेदार के स्थान बदलने पर प्रथम श्रेणी अंतरदेशीय डाक का पुनः प्रेषण निःशुल्क होता है।",
        "part_2_focus": "पार्सल पुनः प्रेषण में वितरण क्षेत्र से बाहर जाने पर आधा डाक प्रभार देय होता है।",
        "part_3_focus": "खोले जा चुके पार्सल को बिना नए डाक शुल्क के पुनः निर्देशित नहीं किया जा सकता।"
    },
    23: {
        "name": "पुनः प्रेषण निर्देश की वैधता", "total_parts": 1,
        "part_1_focus": "डाक को नए पते पर भेजने हेतु दिए गए लिखित निर्देश की अधिकतम वैधता 3 महीने होती है।"
    },
    24: {
        "name": "लावारिस व अवितरित डाक", "total_parts": 3,
        "part_1_focus": "अवितरित डाक को 7 दिन सुरक्षित रखने के बाद पुनः प्रेषण केंद्र भेजा जाता है।",
        "part_2_focus": "बिना पते और बिना प्रेषक वाली वस्तुओं को अधिकृत अधिकारी द्वारा खोलकर प्रेषक तलाशा जाता है।",
        "part_3_focus": "1 वर्ष तक लावारिस रहने वाली मूल्यवान वस्तुओं का नियमानुसार सार्वजनिक नीलामी द्वारा निपटारा होता है।"
    },
    25: {
        "name": "डाक वापस लेना", "total_parts": 2,
        "part_1_focus": "वितरण से पूर्व प्रेषक निर्धारित शुल्क देकर अपने पोस्ट किए पत्र को वापस मंगा सकता है।",
        "part_2_focus": "डाक वापस लेने के लिए प्रेषक को अपनी पहचान और पोस्टिंग का आधिकारिक प्रमाण देना होता है।"
    },
    26: {
        "name": "वितरण प्रमाणपत्र", "total_parts": 1,
        "part_1_focus": "पोस्टिंग प्रमाणपत्र व्यवस्था को आधुनिक डाक प्रणाली में विधिक रूप से समाप्त कर दिया गया है।"
    },
    27: {
        "name": "प्रतिबंधित वस्तुएं", "total_parts": 5,
        "part_1_focus": "विस्फोटक, ज्वलनशील पदार्थ, तेजाब और खतरनाक रसायनों का डाक प्रेषण पूर्णतः गैर-कानूनी है।",
        "part_2_focus": "नशीले पदार्थ, अफीम और गैर-लाइसेंसी दवाएं डाक द्वारा भेजना गंभीर अपराध है।",
        "part_3_focus": "जीवित प्राणी, जहरीले जीव-जंतु डाक द्वारा भेजना पूरी तरह निषिद्ध है।",
        "part_4_focus": "तीक्ष्ण धारदार वस्तुएं बिना मजबूत आवरण के भेजना पूरी तरह प्रतिबंधित है।",
        "part_5_focus": "मानहानिकारक या देशहित के विरुद्ध सामग्री पाए जाने पर डाक को तुरंत जब्त किया जाता है।"
    },
    28: {
        "name": "विशिष्ट पैकिंग और सीलिंग शर्तें", "total_parts": 2,
        "part_1_focus": "तरल पदार्थों को भेजने हेतु मजबूत रिसाव-रोधी डिब्बे और सुरक्षात्मक सामग्री अनिवार्य है।",
        "part_2_focus": "कांच की वस्तुओं की पैकिंग ऐसी हो जिससे रास्ते में अन्य डाक वस्तुएं खराब न हों।"
    },
    29: {
        "name": "शासकीय डाक वस्तुएं", "total_parts": 2,
        "part_1_focus": "सरकारी डाक पर अधिकृत अधिकारी के पदनाम की सील और विशेष पहचान अनिवार्य है।",
        "part_2_focus": "शासकीय डाक पर केवल सरकारी सेवा डाक टिकटों का ही उपयोग किया जा सकता है।"
    },
    30: {
        "name": "शिकायतें और सुझाव दर्ज करना", "total_parts": 1,
        "part_1_focus": "प्रत्येक डाकघर में जनता के लिए शिकायत पुस्तिका और ऑनलाइन निवारण पोर्टल उपलब्ध है।"
    },
    31: {
        "name": "पत्र डाक की सीमाएं व वजन", "total_parts": 2,
        "part_1_focus": "पत्र डाक का अधिकतम वजन 2 किलोग्राम तक ही हो सकता है, इससे अधिक पर पार्सल माना जाता है।",
        "part_2_focus": "पत्र का आकार न्यूनतम 11 × 7 सेमी और अधिकतम संयुक्त माप 90 सेमी से अधिक न हो।"
    },
    32: {
        "name": "पोस्टकार्ड के नियम", "total_parts": 2,
        "part_1_focus": "मानक एकल पोस्टकार्ड का माप 14 सेमी × 9 सेमी होता है।",
        "part_2_focus": "पोस्टकार्ड पर टिकट के अलावा कुछ भी अतिरिक्त कागज चिपकाना वर्जित है।"
    },
    33: {
        "name": "प्रिंटेड और मेघदूत पोस्टकार्ड", "total_parts": 2,
        "part_1_focus": "प्रिंटेड पोस्टकार्ड पर मुद्रित विज्ञापन होते हैं और इनकी दर सामान्य से अधिक होती है।",
        "part_2_focus": "मेघदूत पोस्टकार्ड ग्रामीण विज्ञापन हेतु रियायती आधी दर पर उपलब्ध कराया जाता है।"
    },
    34: {
        "name": "अंतरदेशीय पत्र कार्ड", "total_parts": 2,
        "part_1_focus": "अंतर्देशीय पत्र कार्ड का अधिकतम वजन 5 ग्राम होता है और यह केवल भारत में मान्य है।",
        "part_2_focus": "इसके अंदर कोई भी अतिरिक्त पत्र या सामग्री रखना पूर्णतः निषिद्ध है।"
    },
    35: {
        "name": "बुक पैकेट के नियम", "total_parts": 2,
        "part_1_focus": "बुक पैकेट का अधिकतम वजन 5 किलोग्राम हो सकता है और इसे खुला भेजा जाना चाहिए।",
        "part_2_focus": "बुक पैकेट के भीतर कोई भी व्यक्तिगत पत्राचार रखना पूरी तरह वर्जित है।"
    },
    36: {
        "name": "मुद्रित पुस्तकें पैकेट", "total_parts": 1,
        "part_1_focus": "केवल मुद्रित पुस्तकों वाले बुक पैकेट पर विशेष रियायती डाक दरें लागू होती हैं।"
    },
    37: {
        "name": "सामयिक पत्रिका पैकेट", "total_parts": 1,
        "part_1_focus": "पंजीकृत पत्र-पत्रिकाओं को रियायती दरों पर भेजने की विशेष विभागीय सुविधा मिलती है।"
    },
    38: {
        "name": "पैटर्न और सैंपल पैकेट", "total_parts": 1,
        "part_1_focus": "व्यापारिक नमूनों के सैंपल पैकेट का अधिकतम वजन 2 किलोग्राम तक हो सकता है।"
    },
    39: {
        "name": "ब्लाइंड लिटरेचर पैकेट", "total_parts": 2,
        "part_1_focus": "दृष्टिहीनों के ब्रेल अध्ययन सामग्री का पैकेट अधिकतम 7 किलोग्राम तक भेजा जा सकता है।",
        "part_2_focus": "ब्लाइंड लिटरेचर पैकेट डाक शुल्क और रजिस्ट्री शुल्क से 100% पूरी तरह मुक्त होता है।"
    },
    40: {
        "name": "पंजीकृत समाचार पत्र", "total_parts": 3,
        "part_1_focus": "समाचार पत्र का प्रकाशन 31 दिनों के अंतराल पर होना चाहिए।",
        "part_2_focus": "डाक अधीक्षक द्वारा समाचार पत्र का पंजीकरण लाइसेंस 3 वर्ष हेतु जारी किया जाता है।",
        "part_3_focus": "समाचार पत्र पैकेट पर डाक लाइसेंस संख्या का स्पष्ट मुद्रण अनिवार्य है।"
    },
    41: {
        "name": "पार्सल के विस्तृत नियम", "total_parts": 4,
        "part_1_focus": "अनरजिस्टर्ड पार्सल 4 किग्रा और रजिस्टर्ड पार्सल अधिकतम 20 किग्रा तक हो सकता है।",
        "part_2_focus": "पार्सल की अधिकतम लंबाई 1 मीटर और संयुक्त घेरा 1.80 मीटर से अधिक न हो।",
        "part_3_focus": "पार्सल में कोई भी व्यक्तिगत पत्र संलग्न करना पूरी तरह प्रतिबंधित है।",
        "part_4_focus": "5 किग्रा तक का पार्सल डाकिया घर पर देगा, उससे भारी पार्सल खिड़की से मिलेगा।"
    },
    42: {
        "name": "अनिवार्य पंजीकरण", "total_parts": 2,
        "part_1_focus": "4 किलोग्राम से अधिक वजनी पार्सल और बीमित वस्तुओं का अनिवार्य पंजीकरण कराना होता है।",
        "part_2_focus": "लेटर बॉक्स से निकाले गए पत्र पर 'Registered' लिखा हो तो अनिवार्य पंजीकरण होगा।"
    },
    43: {
        "name": "रजिस्ट्री की पावती", "total_parts": 1,
        "part_1_focus": "पावती शुल्क जमा करने पर वितरण पर प्राप्तकर्ता के मूल हस्ताक्षर वाली रसीद मिलती है।"
    },
    44: {
        "name": "डाक बीमा की सीमाएं", "total_parts": 3,
        "part_1_focus": "शाखा डाकघर में ₹600 और विभागीय डाकघरों में ₹1 लाख तक बीमा स्वीकार्य है।",
        "part_2_focus": "सोने के सिक्के और करेंसी नोट भेजते समय उनका अनिवार्य बीमा कराना होता है।",
        "part_3_focus": "अनिवार्य बीमा वाली वस्तु बिना बीमा के पाए जाने पर भारी जुर्माना लगता है।"
    },
    45: {
        "name": "बीमित वस्तुओं की सीलिंग व पैकिंग", "total_parts": 2,
        "part_1_focus": "बीमित वस्तु के सभी जोड़ों पर एक ही रंग की मोम की सील अनिवार्य है।",
        "part_2_focus": "सील पर प्रेषक की निजी विशिष्ट मुहर की स्पष्ट छाप होना आवश्यक है।"
    },
    46: {
        "name": "मूल्य देय डाक", "total_parts": 3,
        "part_1_focus": "वीपीपी के माध्यम से अधिकतम ₹5,000 तक की वसूली की जा सकती है।",
        "part_2_focus": "वीपीपी वस्तु पर वसूली जाने वाली राशि साफ अक्षरों में लिखी होनी चाहिए।",
        "part_3_focus": "ग्राहक द्वारा लेने से मना करने पर वस्तु प्रेषक को लौटा दी जाती है।"
    },
    47: {
        "name": "मनीऑर्डर प्रणाली", "total_parts": 3,
        "part_1_focus": "इलेक्ट्रॉनिक मनीऑर्डर के जरिए अधिकतम ₹5,000 तक की धनराशि भेजी जा सकती है।",
        "part_2_focus": "प्रेषक शुल्क देकर भुगतान से पूर्व प्राप्तकर्ता का नाम बदल सकता है।",
        "part_3_focus": "प्राप्तकर्ता द्वारा मना करने पर राशि मूल प्रेषक को वापस लौटा दी जाती है।"
    },
    48: {
        "name": "इलेक्ट्रॉनिक पोस्टल ऑर्डर", "total_parts": 1,
        "part_1_focus": "आरटीआई शुल्क के ऑनलाइन डिजिटल भुगतान हेतु e-IPO की शुरुआत की गई है।"
    },
    49: {
        "name": "भारतीय पोस्टल ऑर्डर के नियम", "total_parts": 2,
        "part_1_focus": "क्रॉस किए गए आईपीओ केवल बैंक खाते में ही जमा किए जा सकते हैं।",
        "part_2_focus": "आईपीओ की वैधता जारी होने की तिथि से 24 माह तक होती है।"
    },
    50: {
        "name": "डाकघर बचत बैंक का संगठन", "total_parts": 2,
        "part_1_focus": "डाकघर बचत बैंक वित्त मंत्रालय की राष्ट्रीय लघु बचत योजनाओं को संचालित करता है।",
        "part_2_focus": "डाकघर खातों में जमा संपूर्ण राशि पर सरकार की 100% संप्रभु सुरक्षा मिलती है।"
    },
    51: {
        "name": "बचत खाता नियम", "total_parts": 4,
        "part_1_focus": "डाकघर बचत खाता न्यूनतम ₹500 से खोला जा सकता है और न्यूनतम शेष ₹500 अनिवार्य है।",
        "part_2_focus": "न्यूनतम शेष न रखने पर वित्तीय वर्ष के अंत में ₹50 रखरखाव शुल्क कटता है।",
        "part_3_focus": "लगातार 3 वित्तीय वर्षों तक कोई लेन-देन न होने पर खाता साइलेंट हो जाता है।",
        "part_4_focus": "बचत खाते पर ₹10,000 तक का वार्षिक ब्याज आयकर से मुक्त होता है।"
    },
    52: {
        "name": "आवर्ती जमा खाता", "total_parts": 5,
        "part_1_focus": "5 वर्षीय आरडी खाते में न्यूनतम ₹100 प्रतिमाह जमा होता है।",
        "part_2_focus": "महीने की निर्धारित तारीख तक किस्त जमा न करने पर डिफ़ॉल्ट शुल्क लगता है।",
        "part_3_focus": "लगातार 4 डिफ़ॉल्ट होने पर आरडी खाता बंद हो जाता है।",
        "part_4_focus": "1 वर्ष नियमित चलने के बाद खाते के 50% बैलेंस पर ऋण की सुविधा मिलती है।",
        "part_5_focus": "3 वर्ष बाद आरडी खाते को समय से पूर्व बंद कराया जा सकता है।"
    },
    53: {
        "name": "सावधि जमा खाता", "total_parts": 3,
        "part_1_focus": "डाकघर टीडी खाते 1, 2, 3 और 5 वर्ष की अवधि हेतु न्यूनतम ₹1,000 से खुलते हैं।",
        "part_2_focus": "5 वर्षीय टीडी खाते पर धारा 80C के तहत ₹1.5 लाख तक कर छूट मिलती है।",
        "part_3_focus": "टीडी खाते को 6 माह से पहले बंद करने की अनुमति नहीं होती।"
    },
    54: {
        "name": "मासिक आय योजना", "total_parts": 4,
        "part_1_focus": "एमआईएस में एकल खाते में ₹9 लाख और संयुक्त खाते में ₹15 लाख तक जमा होते हैं।",
        "part_2_focus": "मासिक ब्याज सीधे बचत खाते में ऑटो-क्रेडिट होता है।",
        "part_3_focus": "1 से 3 वर्ष के बीच खाता बंद करने पर 2% मूलधन काटा जाता है।",
        "part_4_focus": "संयुक्त खाता अधिकतम 3 वयस्कों द्वारा खोला जा सकता है।"
    },
    55: {
        "name": "वरिष्ठ नागरिक बचत योजना", "total_parts": 3,
        "part_1_focus": "60 वर्ष या उससे अधिक आयु के नागरिकों हेतु अधिकतम ₹30 लाख की जमा सीमा है।",
        "part_2_focus": "वीआरएस सेवानिवृत्त कर्मचारी 1 माह के भीतर यह खाता खोल सकते हैं।",
        "part_3_focus": "इस खाते की मूल अवधि 5 वर्ष होती है और ब्याज त्रैमासिक मिलता है।"
    },
    56: {
        "name": "पब्लिक प्रोविडेंट फंड", "total_parts": 4,
        "part_1_focus": "पीपीएफ की अवधि 15 वर्ष है और वार्षिक अधिकतम ₹1.5 लाख तक जमा होते हैं।",
        "part_2_focus": "पीपीएफ का जमा, ब्याज और निकासी तीनों आयकर से पूर्णतः मुक्त होते हैं।",
        "part_3_focus": "तीसरे वर्ष से ऋण और सातवें वर्ष से 50% आंशिक निकासी मान्य है।",
        "part_4_focus": "न्यायालय के आदेश द्वारा भी पीपीएफ खाते को कुर्क नहीं किया जा सकता।"
    },
    57: {
        "name": "सुकन्या समृद्धि योजना", "total_parts": 4,
        "part_1_focus": "10 वर्ष से कम आयु की बालिकाओं हेतु न्यूनतम ₹250 से खाता खुलता है।",
        "part_2_focus": "एक वित्तीय वर्ष में न्यूनतम ₹250 और अधिकतम ₹1.5 लाख जमा करना होता है।",
        "part_3_focus": "18 वर्ष पूर्ण होने पर उच्च शिक्षा हेतु 50% निकासी की अनुमति है।",
        "part_4_focus": "यह खाता 21 वर्ष पूर्ण होने पर पूरी तरह परिपक्व होता है।"
    },
    58: {
        "name": "राष्ट्रीय बचत पत्र", "total_parts": 2,
        "part_1_focus": "एनएससी 5 वर्ष की लॉक-इन अवधि का सुरक्षित सरकारी प्रमाण पत्र है।",
        "part_2_focus": "ऋण लेने हेतु इसे बैंकों के पक्ष में बंधक रखा जा सकता है।"
    },
    59: {
        "name": "किसान विकास पत्र", "total_parts": 2,
        "part_1_focus": "केवीपी में जमा की गई राशि निर्धारित महीनों में दोगुनी हो जाती है।",
        "part_2_focus": "केवीपी में न्यूनतम ₹1,000 का निवेश होता है और ढाई साल बाद निकासी मान्य है।"
    },
    60: {
        "name": "डाक जीवन बीमा", "total_parts": 7,
        "part_1_focus": "1884 में स्थापित पीएलआई सरकारी और मान्यता प्राप्त संस्थानों के कर्मचारियों हेतु है।",
        "part_2_focus": "पीएलआई में सुरक्षा, संतोष, सुविधा, युगल सुरक्षा और सुमंगल योजनाएं हैं।",
        "part_3_focus": "पीएलआई में न्यूनतम ₹20,000 और अधिकतम ₹50 लाख तक बीमा मिलता है।",
        "part_4_focus": "ग्रामीण नागरिकों हेतु 1995 में आरपीएलआई योजना प्रारंभ की गई थी।",
        "part_5_focus": "आरपीएलआई में ग्राम सुरक्षा, ग्राम संतोष और बाल जीवन बीमा योजनाएं हैं।",
        "part_6_focus": "आरपीएलआई में न्यूनतम ₹10,000 और अधिकतम ₹10 लाख तक बीमा होता है।",
        "part_7_focus": "3 वर्ष चलने के बाद पॉलिसी पर समर्पण और ऋण लेने की सुविधा मिलती है।"
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
    state = {"clause_no": 8, "current_part": 1, "total_parts": 2, "hook_index": 0}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                if isinstance(saved, dict) and "clause_no" in saved:
                    state.update(saved)
        except Exception:
            pass
    current_clause = state.get("clause_no", 8)
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

    clause = state.get("clause_no", 8)
    part = state.get("current_part", 1)
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
    current_clause = state.get("clause_no", 8)
    current_part = state.get("current_part", 1)
    hook_idx = state.get("hook_index", 0) % len(VIRAL_HOOKS)
    hook_obj = VIRAL_HOOKS[hook_idx]

    clause_info = POSTAL_CLAUSE_CATALOG.get(current_clause, POSTAL_CLAUSE_CATALOG[8])
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
        "hook_display_text": hook_obj["hook_text"],
        "question": "फिलाटेलिक ब्यूरो विशेष स्मारक टिकटों का वितरण किसके जरिए करते हैं?",
        "sen1": f"डाक घर गाइड भाग 1 के क्लॉज {current_clause} के अनुसार {part_focus}",
        "sen2": "परीक्षार्थी ध्यान रखें कि इसके आधिकारिक अपवादों में ही अक्सर गलतियां होती हैं।",
        "opt_a": "केवल प्रथम दिवस पर",
        "opt_b": "पूरे वर्ष के दौरान",
        "opt_c": "केवल रविवार को",
        "opt_d": "केवल त्योहारों पर",
        "caption": f"🚨 90% लोग इस नियम में गलती करते हैं! डाक घर गाइड भाग 1 | क्लॉज {current_clause} (भाग {current_part}/{total_parts})। सही उत्तर कमेंट करें! फ्री विभागीय नोट्स व टेस्ट हेतु WhatsApp करें: 8989971379 #PostalWala #GDStoMTS #PostmanExam #IndiaPost"
    }

    if not GROQ_API_KEY:
        return fallback_data

    prompt = f"""
    You are the Senior Chief Instructor for India Post Examinations for 'Postal Wala'.
    Topic: 'Post Office Guide Part 1', Clause: {current_clause}, Title: {clause_name}, Part: {current_part}/{total_parts}
    Core Rule Focus: "{part_focus}"

    Generate crisp pure Hindi exam content (Strictly 12-14 words per sentence, No Repetition):
    QUESTION: [1 short departmental exam MCQ question, max 12 words]
    SEN1: [Core rule statement in simple Hindi, exactly 12-14 words]
    SEN2: [Crucial exam exception or trap point, exactly 12-14 words]
    OPT_A: [Option A, 2-4 words]
    OPT_B: [Option B, 2-4 words]
    OPT_C: [Option C, 2-4 words]
    OPT_D: [Option D, 2-4 words]
    """
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY.strip()}", "Content-Type": "application/json"}
        payload = {"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 350}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            raw_text = res.json()["choices"][0]["message"]["content"].strip()
            q = extract_field_block(raw_text, "QUESTION", ["SEN1", "OPT_A"])
            s1 = extract_field_block(raw_text, "SEN1", ["SEN2", "QUESTION"])
            s2 = extract_field_block(raw_text, "SEN2", ["OPT_A", "QUESTION"])
            oa = extract_field_block(raw_text, "OPT_A", ["OPT_B", "OPT_C"])
            ob = extract_field_block(raw_text, "OPT_B", ["OPT_C", "OPT_D"])
            oc = extract_field_block(raw_text, "OPT_C", ["OPT_D"])
            od = extract_field_block(raw_text, "OPT_D", [])

            if q: fallback_data["question"] = clean_hindi_postal_terms(q)
            if s1: fallback_data["sen1"] = clean_hindi_postal_terms(s1)
            if s2: fallback_data["sen2"] = clean_hindi_postal_terms(s2)
            if oa: fallback_data["opt_a"] = clean_hindi_postal_terms(oa)
            if ob: fallback_data["opt_b"] = clean_hindi_postal_terms(ob)
            if oc: fallback_data["opt_c"] = clean_hindi_postal_terms(oc)
            if od: fallback_data["opt_d"] = clean_hindi_postal_terms(od)
    except Exception as e:
        print(f"⚠️ Groq note: {e}")

    return fallback_data

def get_slide_segments(script_data):
    return [
        f"{script_data['hook_voice']}",
        f"{script_data['sen1']}",
        f"परीक्षा विशेष बिंदु: {script_data['sen2']}",
        f"सवाल स्क्रीन पर है! सही उत्तर A, B, C या D कमेंट करें और पोस्टल वाला को फॉलो करें!"
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

def render_and_sync_video(script_data, output_video=OUTPUT_VIDEO):
    ensure_fonts()

    segment_audios = get_slide_segments(script_data)
    durations = []
    
    for i, seg_text in enumerate(segment_audios):
        seg_file = f"audio_seg_{i}.mp3"
        asyncio.run(generate_segment_audio(seg_text, seg_file))
        durations.append(get_audio_duration(seg_file))

    concat_filter = "".join([f"[{i}:a]" for i in range(4)]) + "concat=n=4:v=0:a=1[aout]"
    ffmpeg_concat_cmd = ["ffmpeg", "-y"]
    for i in range(4):
        ffmpeg_concat_cmd.extend(["-i", f"audio_seg_{i}.mp3"])
    ffmpeg_concat_cmd.extend(["-filter_complex", concat_filter, "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "final_master.mp3"])
    subprocess.run(ffmpeg_concat_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    total_dur = sum(durations)
    print(f"🎵 Audio Flow Generated: Total {total_dur:.1f}s | Segment Durations: {[round(d, 1) for d in durations]}", flush=True)

    font_brand = get_font(44)
    font_sub = get_font(22)
    font_trust = get_font(20)
    font_badge = get_font(22)
    font_title = get_font(34)
    font_h1 = get_font(38)
    font_h2 = get_font(30)
    font_body = get_font(34)
    font_label = get_font(26)
    font_wa_hin = get_font(28)
    font_wa_num = get_font(28)
    font_cta = get_font(30)
    font_opt = get_font(28)
    font_hook = get_font(36)

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

    # -------------------------------------------------------------------------
    # PROGRESSIVE MULTI-FRAME ANIMATION BUILDER
    # Every 1.5 - 2.5s the screen triggers a new visual element!
    # -------------------------------------------------------------------------
    frames = []
    frame_durs = []

    # ==================== SLIDE 1 (HOOK) ====================
    # Step 1A: Alert Badge Explodes on screen
    img1a = Image.new("RGB", (1080, 1920), color="#060A17")
    d1a = ImageDraw.Draw(img1a)
    draw_base(d1a)
    d1a.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
    d1a.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d1a.text((120, 195), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d1a.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d1a.text((845, 195), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d1a.text((105, 255), clean_hindi_postal_terms(script_data["clause_name"]), fill="#FFFFFF", font=font_title)
    d1a.rounded_rectangle([80, 360, 1000, 1550], radius=24, fill="#1C2541", outline="#38BDF8", width=3)
    d1a.rounded_rectangle([110, 430, 970, 550], radius=16, fill="#991B1B", outline="#FBBF24", width=3)
    d1a.text((150, 465), clean_hindi_postal_terms(script_data["visual_hook_badge"]), fill="#FEF08A", font=font_hook)
    draw_footer_cta(d1a)
    img1a.save("f_1a.png")
    frames.append("f_1a.png")
    frame_durs.append(round(durations[0] * 0.40, 2))

    # Step 1B: Headline + Topic Card Pop
    img1b = img1a.copy()
    d1b = ImageDraw.Draw(img1b)
    d1b.rounded_rectangle([110, 620, 450, 675], radius=10, fill="#0B132B", outline="#38BDF8", width=2)
    d1b.text((130, 630), "विभागीय परीक्षा विशेष:", fill="#38BDF8", font=font_label)
    wrapped_hook = textwrap.fill(clean_hindi_postal_terms(script_data["hook_display_text"]), width=20)
    d1b.multiline_text((115, 730), wrapped_hook, fill="#FFFFFF", font=font_h1, spacing=16)
    d1b.rounded_rectangle([110, 1080, 970, 1260], radius=18, fill="#0B132B", outline="#FBBF24", width=2)
    d1b.text((150, 1115), f"विषय: {clean_hindi_postal_terms(script_data['clause_name'])}", fill="#FDE047", font=font_h2)
    d1b.text((150, 1180), f"डाक घर गाइड भाग 1 | क्लॉज संख्या: {script_data['clause_no']}", fill="#94A3B8", font=font_opt)
    d1b.rounded_rectangle([110, 1400, 970, 1490], radius=16, fill="#064E3B", outline="#10B981", width=2)
    d1b.text((200, 1425), "👉 25 सेकंड में पूरा नियम समझें!", fill="#34D399", font=font_h2)
    img1b.save("f_1b.png")
    frames.append("f_1b.png")
    frame_durs.append(round(durations[0] * 0.60, 2))

    # ==================== SLIDE 2 (RULE ANALYSIS) ====================
    # Step 2A: Rule Statement Card
    img2a = Image.new("RGB", (1080, 1920), color="#060A17")
    d2a = ImageDraw.Draw(img2a)
    draw_base(d2a)
    d2a.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
    d2a.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d2a.text((120, 195), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d2a.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d2a.text((845, 195), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d2a.text((105, 255), clean_hindi_postal_terms(script_data["clause_name"]), fill="#FFFFFF", font=font_title)
    draw_whatsapp_strip(d2a)
    d2a.rounded_rectangle([80, 480, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)
    d2a.rounded_rectangle([110, 530, 480, 585], radius=10, fill="#0B132B")
    d2a.text((150, 540), "नियम विश्लेषण #1:", fill="#38BDF8", font=font_label)
    wrapped_s2 = textwrap.fill(script_data['sen1'], width=22)
    d2a.multiline_text((120, 680), clean_hindi_postal_terms(wrapped_s2), fill="#F8FAFC", font=font_body, spacing=20)
    draw_footer_cta(d2a)
    img2a.save("f_2a.png")
    frames.append("f_2a.png")
    frame_durs.append(round(durations[1] * 0.50, 2))

    # Step 2B: Dynamic Bottom Teaser Appears
    img2b = img2a.copy()
    d2b = ImageDraw.Draw(img2b)
    d2b.rounded_rectangle([110, 1370, 970, 1470], radius=14, fill="#0B132B", outline="#38BDF8", width=2)
    d2b.text((160, 1400), "आगे देखिए: इस नियम का परीक्षा ट्रैप बिंदु 👉", fill="#38BDF8", font=font_h2)
    img2b.save("f_2b.png")
    frames.append("f_2b.png")
    frame_durs.append(round(durations[1] * 0.50, 2))

    # ==================== SLIDE 3 (TRAP POINT) ====================
    # Step 3A: Trap Header Card
    img3a = Image.new("RGB", (1080, 1920), color="#060A17")
    d3a = ImageDraw.Draw(img3a)
    draw_base(d3a)
    d3a.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#38BDF8", width=2)
    d3a.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d3a.text((120, 195), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d3a.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d3a.text((845, 195), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d3a.text((105, 255), clean_hindi_postal_terms(script_data["clause_name"]), fill="#FFFFFF", font=font_title)
    draw_whatsapp_strip(d3a)
    d3a.rounded_rectangle([80, 480, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)
    d3a.rounded_rectangle([110, 530, 480, 585], radius=10, fill="#0B132B")
    d3a.text((150, 540), "परीक्षा अपवाद #2:", fill="#FBBF24", font=font_label)
    wrapped_s3 = textwrap.fill(f"परीक्षा विशेष बिंदु:\n\n{script_data['sen2']}", width=22)
    d3a.multiline_text((120, 680), clean_hindi_postal_terms(wrapped_s3), fill="#F8FAFC", font=font_body, spacing=20)
    draw_footer_cta(d3a)
    img3a.save("f_3a.png")
    frames.append("f_3a.png")
    frame_durs.append(round(durations[2] * 0.50, 2))

    # Step 3B: Quiz Alert Banner Appears
    img3b = img3a.copy()
    d3b = ImageDraw.Draw(img3b)
    d3b.rounded_rectangle([110, 1370, 970, 1470], radius=14, fill="#0B132B", outline="#FBBF24", width=2)
    d3b.text((180, 1400), "अब आज का सवाल: उत्तर कमेंट करें 👉", fill="#FDE047", font=font_h2)
    img3b.save("f_3b.png")
    frames.append("f_3b.png")
    frame_durs.append(round(durations[2] * 0.50, 2))

    # ==================== SLIDE 4 (QUIZ & OPTIONS) ====================
    # Step 4A: Question Only (Viewer concentrates on question)
    img4a = Image.new("RGB", (1080, 1920), color="#060A17")
    d4a = ImageDraw.Draw(img4a)
    draw_base(d4a)
    d4a.rounded_rectangle([80, 175, 1000, 320], radius=18, fill="#1C2541", outline="#FBBF24", width=2)
    d4a.rounded_rectangle([105, 190, 560, 235], radius=10, fill="#F59E0B")
    d4a.text((120, 195), f"पीओ गाइड भाग 1 : क्लॉज {script_data['clause_no']}", fill="#000000", font=font_badge)
    d4a.rounded_rectangle([820, 190, 975, 235], radius=10, fill="#1D4ED8")
    d4a.text((845, 195), f"भाग {script_data['part_no']}/{script_data['total_parts']}", fill="#FFFFFF", font=font_badge)
    d4a.text((105, 255), "परीक्षा क्विज़: उत्तर कमेंट करें", fill="#FDE047", font=font_title)
    d4a.rounded_rectangle([80, 350, 1000, 1550], radius=24, fill="#1C2541", outline="#334155", width=2)
    d4a.rounded_rectangle([110, 380, 360, 435], radius=10, fill="#0B132B")
    d4a.text((140, 390), "आज का सवाल:", fill="#FBBF24", font=font_h2)
    wrapped_q4 = textwrap.fill(clean_hindi_postal_terms(script_data["question"]), width=23)
    d4a.multiline_text((110, 460), wrapped_q4, fill="#F8FAFC", font=font_h2, spacing=10)
    draw_footer_cta(d4a)
    img4a.save("f_4a.png")
    frames.append("f_4a.png")
    frame_durs.append(round(durations[3] * 0.35, 2))

    # Step 4B: Options A, B, C, D + Glowing Comment CTA Pop In
    img4b = img4a.copy()
    d4b = ImageDraw.Draw(img4b)
    q_lines = wrapped_q4.count("\n") + 1
    start_oy = 460 + (q_lines * 42) + 50
    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    labels = ["A", "B", "C", "D"]
    oy = start_oy
    for o_idx, opt in enumerate(opts):
        d4b.rounded_rectangle([110, oy, 970, oy + 90], radius=16, fill="#0B132B", outline="#38BDF8", width=2)
        d4b.text((135, oy + 22), f"{labels[o_idx]})", fill="#38BDF8", font=font_h2)
        d4b.text((200, oy + 24), textwrap.fill(clean_hindi_postal_terms(opt), width=23), fill="#FFFFFF", font=font_opt)
        oy += 120
    d4b.rounded_rectangle([110, 1370, 970, 1490], radius=18, fill="#064E3B", outline="#34D399", width=2)
    d4b.text((180, 1410), "💬 अपना उत्तर (A, B, C, D) कमेंट करें!", fill="#FDE047", font=font_h2)
    img4b.save("f_4b.png")
    frames.append("f_4b.png")
    frame_durs.append(round(durations[3] * 0.65, 2))

    # =========================================================================
    # FFMPEG RENDER (8 STEPS REVEAL + LIVE MOTION PROGRESS BAR)
    # =========================================================================
    inputs = []
    filter_parts = ""
    for i, fname in enumerate(frames):
        inputs.extend(["-i", fname])
        safe_dur = max(0.5, frame_durs[i])
        filter_parts += f"[{i}:v]loop=loop=-1:size=1:start=0,trim=duration={safe_dur}[v{i}]; "

    concat_str = "".join([f"[v{i}]" for i in range(len(frames))])
    base_v_filter = f"{filter_parts}{concat_str}concat=n={len(frames)}:v=1:a=0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
    
    # Animated Progress Bar that travels across top edge
    progress_bar_filter = f"{base_v_filter},drawbox=x=0:y=0:w='iw*(t/{total_dur})':h=12:color=#F43F5E@1:t=fill[v]"

    cmd = ["ffmpeg", "-y", *inputs, "-i", "final_master.mp3"]
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
    print(f"✅ Dynamic 8-Step Progressive Animated Reel Created: {output_video}", flush=True)

# --- RESUMABLE PROTOCOL UPLOADER ---
def _create_reel_container(video_file, caption, user_id, access_token):
    print("📤 Initializing Meta Resumable Upload Session...", flush=True)
    init_url = f"{GRAPH_API_BASE}{str(user_id).strip()}/media"
    init_payload = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "access_token": access_token
    }
    r = requests.post(init_url, data=init_payload, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Container Init Failed ({r.status_code}): {r.text}")

    res_json = r.json()
    video_id = res_json.get("id")
    upload_url = res_json.get("uri") or f"{RUPLOAD_BASE}{str(video_id).strip()}"
    print(f"📦 Container initialized. ID: {video_id}", flush=True)
    
    time.sleep(5)

    file_size = os.path.getsize(video_file)
    with open(video_file, "rb") as vf:
        video_data = vf.read()

    upload_headers = {
        "Authorization": f"OAuth {access_token}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "application/octet-stream",
        "Content-Length": str(file_size)
    }

    print(f"🚀 Uploading binary stream to Meta (Size: {file_size} bytes)...", flush=True)
    up_r = requests.post(upload_url, headers=upload_headers, data=video_data, timeout=600)

    if up_r.status_code not in [200, 201]:
        raise RuntimeError(f"Binary Upload Failed ({up_r.status_code}): {up_r.text}")

    print(f"✅ Binary upload completed for ID: {video_id}", flush=True)
    return video_id

def _poll_container_status(video_id, access_token, max_checks=45, wait_seconds=15):
    status_url = f"{GRAPH_API_BASE}{str(video_id).strip()}"
    for check_idx in range(1, max_checks + 1):
        time.sleep(wait_seconds)
        try:
            res = requests.get(
                status_url,
                params={"fields": "status_code,status", "access_token": access_token},
                timeout=30
            ).json()
            status = res.get("status_code")
            print(f"   ⏳ Polling status ({check_idx}/{max_checks}): {status}", flush=True)
            if status == "FINISHED":
                return "FINISHED"
            elif status in ["ERROR", "EXPIRED"]:
                print(f"   ⚠️ FULL Meta payload: {json.dumps(res, ensure_ascii=False)}", flush=True)
                return status
        except Exception as e:
            print(f"   ⚠️ Poll error: {e}", flush=True)
            continue
    return "TIMEOUT"

def _publish_reel(video_id, user_id, access_token):
    publish_url = f"{GRAPH_API_BASE}{str(user_id).strip()}/media_publish"
    pub_res = requests.post(
        publish_url,
        data={"creation_id": video_id, "access_token": access_token},
        timeout=30
    )
    pub_res_data = pub_res.json()
    if "id" in pub_res_data:
        print(f"🎉 Post published! Instagram Media ID: {pub_res_data['id']}", flush=True)
    else:
        raise RuntimeError(f"Publish fail: {pub_res.text}")

def post_reel_to_instagram_multipart(video_file, caption, max_container_attempts=3):
    access_token = os.getenv("IG_ACCESS_TOKEN")
    user_id = os.getenv("IG_USER_ID")

    if not access_token or not user_id:
        print("⚠️ IG credentials missing!")
        return False

    last_error = None
    for container_attempt in range(1, max_container_attempts + 1):
        print(f"\n🚀 [UPLOAD] Starting Attempt {container_attempt} of {max_container_attempts}...", flush=True)
        try:
            video_id = _create_reel_container(video_file, caption, user_id, access_token)
            status = _poll_container_status(video_id, access_token)

            if status == "FINISHED":
                _publish_reel(video_id, user_id, access_token)
                print(f"🎉 Reel published on Attempt {container_attempt}!", flush=True)
                return True
            else:
                last_error = f"Status: {status}"
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ Attempt {container_attempt} error: {last_error}", flush=True)

        if container_attempt < max_container_attempts:
            print(f"⏳ Waiting 25s before retry Attempt {container_attempt + 1}...", flush=True)
            time.sleep(25)

    print(f"\n❌ Upload failed after 3 attempts: {last_error}", flush=True)
    return False

# --- MAIN RUNNER ---
if __name__ == "__main__":
    st = load_progress_state()
    print(f"📌 Running Target: Clause {st['clause_no']} (Part {st['current_part']}/{st['total_parts']})", flush=True)
    
    script_data = generate_clause_script(st)
    render_and_sync_video(script_data, OUTPUT_VIDEO)

    upload_ok = post_reel_to_instagram_multipart(OUTPUT_VIDEO, script_data.get("caption", ""))
    if upload_ok:
        advance_progress_state(st)
        print("✅ Reel posted and state successfully shifted to next part.", flush=True)
    else:
        print("❌ Reel upload failed after 3 attempts. State preserved.", flush=True)
        sys.exit(1)
