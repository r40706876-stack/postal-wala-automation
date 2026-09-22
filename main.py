import os
import re
import json
import math
import shutil
import asyncio
import subprocess
import requests
from PIL import Image, ImageDraw, ImageFont
import edge_tts

# ============================================================
# POSTAL WALA — HIGH RETENTION REEL ENGINE v2 (AUTO-UPLOAD TO GITHUB)
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
STATE_FILE = "progress_state.json"
REELS_DIR = "generated_reels"
os.makedirs(REELS_DIR, exist_ok=True)

VOICE_NAME = "hi-IN-SwaraNeural"

W, H = 1080, 1920
FPS = 30
BG = "#07111F"
WHITE = "#F8FAFC"
MUTED = "#AAB7C7"
RED = "#EF4444"
GREEN = "#22C55E"
YELLOW = "#F59E0B"
BLUE = "#2563EB"
CYAN = "#38BDF8"
CARD = "#0E1B2D"
CARD2 = "#12243A"

FONT_DEV = "NotoSansDevanagari-Bold.ttf"
ASSETS = "assets"
os.makedirs(ASSETS, exist_ok=True)

# ------------------------------------------------------------
# 1) HOOK PATTERNS
# ------------------------------------------------------------
HOOK_PATTERNS = [
    ("question", "इस नियम में सबसे ज्यादा confusion कहाँ होता है?"),
    ("trap", "⚠️ परीक्षा में यही छोटा सा फर्क गलती करा सकता है।"),
    ("challenge", "देखते हैं आप इसका सही जवाब दे पाते हैं या नहीं।"),
    ("direct", "यह नियम 20 सेकंड में दिमाग में lock कर लो।"),
]

# ------------------------------------------------------------
# 2) POSTAL CLAUSE CATALOG
# ------------------------------------------------------------
POSTAL_CLAUSE_CATALOG = {
    1: {
        "name": "डाक विभाग का नियंत्रण व संगठन",
        "total_parts": 2,
        "part_1_focus": "संचार मंत्रालय के अधीन महानिदेशक (DG Posts) शीर्ष प्रशासनिक प्रमुख हैं और मुख्यालय डाक भवन नई दिल्ली में स्थित है।",
        "part_2_focus": "डाक सेवा बोर्ड (PSB) में एक चेयरमैन (सचिव डाक) और 6 पूर्णकालिक सदस्य होते हैं जो कार्मिक, प्रचालन व तकनीक का कार्य देखते हैं।",
    },
    2: {
        "name": "डाकघरों के प्रकार और श्रेणियां",
        "total_parts": 3,
        "part_1_focus": "डाकघर की 3 प्रमुख श्रेणियां हैं: प्रधान डाकघर (HO), उप डाकघर (SO) और शाखा डाकघर (BO)। HO मुख्य वित्तीय लेखा कार्यालय होता है।",
        "part_2_focus": "उप डाकघर (SO) प्रधान डाकघर के अधीन रहकर सभी प्रकार के लेन-देन करता है और दैनिक लेखा HO को प्रेषित करता है।",
        "part_3_focus": "ग्रामीण शाखा डाकघर (BO) के कार्य के घंटे न्यूनतम 4 घंटे और अधिकतम 5 घंटे प्रतिदिन निर्धारित किए जाते हैं।",
    },
    3: {
        "name": "रात्रि डाकघर के नियम",
        "total_parts": 3,
        "part_1_focus": "रात्रि डाकघर की स्थापना और कामकाज के घंटे रात 8:30 बजे तक बढ़ाने का विशेष अधिकार केवल महानिदेशक (DG) को है।",
        "part_2_focus": "रविवार और राष्ट्रीय डाक अवकाशों पर रात्रि डाकघर सुबह 10 से शाम 5 बजे तक केवल सीमित सेवाएं देते हैं।",
        "part_3_focus": "रात्रि डाकघरों में रविवार और अवकाश के दिनों में कोई भी मनीऑर्डर भुगतान या बचत बैंक निकासी कार्य नहीं होता।",
    },
    4: {
        "name": "मोबाइल डाकघर की व्यवस्था",
        "total_parts": 2,
        "part_1_focus": "मोबाइल डाकघर बड़े शहरों में देर शाम तक सामान्य डाक व पार्सल बुकिंग की सुविधा जनता को उपलब्ध कराते हैं।",
        "part_2_focus": "मोबाइल डाकघर में मनीऑर्डर, बचत बैंक और बीमा का कोई भी वित्तीय कार्य करना पूर्णतः प्रतिबंधित होता है।",
    },
    5: {
        "name": "डाकघर के कामकाज के घंटे",
        "total_parts": 3,
        "part_1_focus": "सामान्य डाक टिकट बिक्री और डाक बुकिंग पूरे कार्य समय तक होती है, जबकि बचत बैंक का समय पहले समाप्त होता है।",
        "part_2_focus": "सार्वजनिक काउंटर बंद होने के बाद निर्धारित लेट फीस का भुगतान करके ही डाक बुक की जा सकती है।",
        "part_3_focus": "शनिवार को सामान्य डाक लेन-देन के समय में कटौती के विभागीय नियम और नोटिस बोर्ड पर समय सारिणी प्रदर्शित करना।",
    },
    22: {
        "name": "डाक का पुनः निर्देशन (Redirection)",
        "total_parts": 3,
        "part_1_focus": "पतेदार के नया पता छोड़कर जाने पर प्रथम श्रेणी की अंतरदेशीय डाक का पुनः प्रेषण निःशुल्क होता है।",
        "part_2_focus": "पार्सल पुनः प्रेषण के मामले में यदि पार्सल वितरण क्षेत्र से बाहर भेजा जाए तो आधा डाक प्रभार देय होता है।",
        "part_3_focus": "यदि पार्सल को पतेदार द्वारा एक बार खोल दिया गया हो तो उसे नए डाकभार के बिना पुनः निर्देशित नहीं किया जा सकता।",
    },
    23: {
        "name": "डाक पुनः प्रेषण के विशेष निर्देश",
        "total_parts": 2,
        "part_1_focus": "लिखित पुनः प्रेषण अनुदेश की वैधता अवधि अधिकतम 3 माह तक प्रभावी रहती है।",
        "part_2_focus": "विदेश जाने वाले पतेदारों और अस्थाई रूप से स्थान बदलने वाले व्यक्तियों के लिए विशेष डाक नियम लागू होते हैं।",
    },
}

# ------------------------------------------------------------
# 3) TEXT / FONT HELPERS
# ------------------------------------------------------------
def ensure_font():
    if os.path.exists(FONT_DEV):
        return
    url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with open(FONT_DEV, "wb") as f:
        f.write(r.content)

def dev_font(size):
    ensure_font()
    return ImageFont.truetype(FONT_DEV, size)

def eng_font(size):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return dev_font(size)

def is_dev(ch):
    o = ord(ch)
    return 0x0900 <= o <= 0x097F

def mixed_width(draw, text, df, ef):
    total = 0
    for ch in text:
        total += draw.textlength(ch, font=df if is_dev(ch) else ef)
    return total

def draw_mixed(draw, xy, text, df, ef, fill=WHITE, anchor=None):
    x, y = xy
    if anchor == "mm":
        w = mixed_width(draw, text, df, ef)
        x -= w / 2
    elif anchor == "ma":
        w = mixed_width(draw, text, df, ef)
        x -= w
    cx = x
    for ch in text:
        f = df if is_dev(ch) else ef
        draw.text((cx, y), ch, font=f, fill=fill)
        cx += draw.textlength(ch, font=f)

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, cur = [], ""
    for word in words:
        test = word if not cur else cur + " " + word
        if draw.textlength(test, font=font) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return "\n".join(lines)

def clean_text(s):
    if not s:
        return ""
    s = re.sub(r"[*_`#]+", "", s)
    s = s.replace("…", ".")
    return " ".join(s.split()).strip()

# ------------------------------------------------------------
# 4) SCRIPT GENERATION
# ------------------------------------------------------------
def extract_field(raw, name, next_names):
    pat = rf"(?:^|\n)\s*{re.escape(name)}\s*:\s*(.*?)(?=(?:\n\s*(?:{'|'.join(map(re.escape,next_names))})\s*:)|$)"
    m = re.search(pat, raw, re.I | re.S)
    return clean_text(m.group(1)) if m else ""

def make_fallback(clause_no, part_no, focus, title):
    if clause_no == 22 and part_no == 2:
        return {
            "title": title,
            "hook": "पार्सल को दूसरे वितरण क्षेत्र में भेजने पर कितना प्रभार लगता है?",
            "question": "वितरण क्षेत्र से बाहर पार्सल पुनः प्रेषित करने पर कितना डाक प्रभार है?",
            "a": "आधा डाक प्रभार",
            "b": "पूर्ण डाक प्रभार",
            "c": "निःशुल्क",
            "d": "दोगुना प्रभार",
            "correct": "A",
            "fact": "वितरण क्षेत्र से बाहर भेजे जाने पर आधा डाक प्रभार देय होता है।",
            "trap": "क्षेत्र के बाहर जाने पर नियम बदलता है: आधा प्रभार याद रखें।",
        }

    return {
        "title": title,
        "hook": f"{title} का यह नियम ध्यान से देखिए।",
        "question": "इस नियम के अनुसार सही बात कौन-सी है?",
        "a": "ऊपर दिया नियम",
        "b": "अलग नियम",
        "c": "कोई नियम नहीं",
        "d": "इनमें से कोई नहीं",
        "correct": "A",
        "fact": focus,
        "trap": "परीक्षा में शब्दों और अपवादों को ध्यान से पढ़ें।",
    }

def generate_script(state):
    clause_no = state["clause_no"]
    part_no = state["current_part"]
    info = POSTAL_CLAUSE_CATALOG.get(clause_no)
    if not info:
        raise ValueError(f"Clause {clause_no} is not present in POSTAL_CLAUSE_CATALOG.")
    title = info["name"]
    focus = info.get(f"part_{part_no}_focus", info.get("part_1_focus", ""))

    if not GROQ_API_KEY:
        return make_fallback(clause_no, part_no, focus, title)

    prompt = f"""
You are writing ONE short India Post departmental-exam educational Reel.

TOPIC: {title}
PART: {part_no}/{info.get('total_parts',1)}
VERIFIED CORE FACT: {focus}

Rules:
- Never invent statistics.
- Never say "90% लोग", "2 नंबर पक्के", "पक्का प्रमोशन" unless explicitly proved.
- One clear rule only.
- Keep language simple Hindi suitable for a 20–30 second Reel.

Return EXACTLY:
HOOK: [max 10 words]
QUESTION: [max 15 words]
A: [2-6 words]
B: [2-6 words]
C: [2-6 words]
D: [2-6 words]
CORRECT: [A/B/C/D]
FACT: [max 18 words]
TRAP: [max 14 words]
"""

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.15,
                "max_tokens": 400,
            },
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
            "correct": extract_field(raw, "CORRECT", ["FACT"]).upper(),
            "fact": extract_field(raw, "FACT", ["TRAP"]),
            "trap": extract_field(raw, "TRAP", []),
        }

        if data["correct"] not in "ABCD":
            raise ValueError("Invalid correct option")
        if not all(data[k] for k in ["hook","question","a","b","c","d","fact","trap"]):
            raise ValueError("Incomplete AI script")

        return data
    except Exception as e:
        print("Groq fallback notice:", e)
        return make_fallback(clause_no, part_no, focus, title)

# ------------------------------------------------------------
# 5) STATE MANAGEMENT
# ------------------------------------------------------------
def load_state():
    state = {
        "clause_no": 22,
        "current_part": 2,
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state.update(json.load(f))
        except Exception:
            pass
    return state

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ------------------------------------------------------------
# 6) AUDIO ENGINE
# ------------------------------------------------------------
def audio_duration(path):
    out = subprocess.check_output([
        "ffprobe","-v","error",
        "-show_entries","format=duration",
        "-of","default=noprint_wrappers=1:nokey=1",path
    ])
    return float(out.decode().strip())

async def make_audio(text, path):
    if os.path.exists(path):
        os.remove(path)
    tts = edge_tts.Communicate(
        text=text,
        voice=VOICE_NAME,
        rate="+10%",
        pitch="+0Hz",
    )
    await tts.save(path)

def tighten_audio(path):
    tmp = path + ".tmp.mp3"
    try:
        subprocess.run([
            "ffmpeg","-y","-i",path,
            "-af",
            "silenceremove=start_periods=1:start_threshold=-38dB:"
            "stop_periods=-1:stop_duration=0.08:stop_threshold=-38dB",
            "-c:a","libmp3lame","-b:a","192k",tmp
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.replace(tmp,path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)

# ------------------------------------------------------------
# 7) VISUAL RENDERING
# ------------------------------------------------------------
def base():
    return Image.new("RGB", (W,H), BG)

def rounded(draw, box, radius=36, fill=CARD, outline=None, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

def centered(draw, text, y, size, fill=WHITE):
    df, ef = dev_font(size), eng_font(size)
    draw_mixed(draw, (W//2, y), text, df, ef, fill, anchor="mm")

def brand(draw):
    f = eng_font(28)
    draw.text((55,55), "POSTAL WALA", font=f, fill="#6E8299")

def progress(draw, ratio):
    x1, x2, y = 55, W-55, 95
    draw.rounded_rectangle((x1,y,x2,y+8), 4, fill="#1C2A3A")
    draw.rounded_rectangle((x1,y,x1+(x2-x1)*max(0,min(1,ratio)),y+8), 4, fill=CYAN)

def draw_stamp(draw, cx, cy, scale=1.0):
    s = int(230*scale)
    box = [cx-s//2, cy-s//2, cx+s//2, cy+s//2]
    draw.rectangle(box, fill="#F8FAFC", outline="#CBD5E1", width=max(2,int(5*scale)))
    draw.rectangle(
        [box[0]+14,box[1]+14,box[2]-14,box[3]-14],
        outline=RED, width=max(2,int(5*scale))
    )
    centered_y = cy - int(55*scale)
    df = dev_font(max(22,int(42*scale)))
    ef = eng_font(max(22,int(42*scale)))
    draw_mixed(draw,(cx,centered_y),"डाक",df,ef,RED,anchor="mm")
    f = eng_font(max(16,int(28*scale)))
    t="INDIA POST"
    tw=draw.textlength(t,font=f)
    draw.text((cx-tw/2,cy+int(15*scale)),t,font=f,fill="#334155")

def draw_wax(draw, cx, cy, scale=1.0, crack=False):
    r=int(115*scale)
    draw.ellipse([cx-r,cy-r,cx+r,cy+r],fill="#9F1239",outline="#F43F5E",width=max(2,int(6*scale)))
    draw.ellipse([cx-r+15,cy-r+15,cx+r-15,cy+r-15],outline="#4C0519",width=max(2,int(4*scale)))
    if crack:
        pts=[(cx-15,cy-70),(cx+5,cy-15),(cx-20,cy+15),(cx+18,cy+65)]
        draw.line(pts,fill="#F8FAFC",width=max(2,int(7*scale)))
    centered(draw,"मोम",cy-30,int(35*scale),WHITE)

def draw_paper(draw, cx, cy, scale=1.0):
    w,h=int(420*scale),int(270*scale)
    box=[cx-w//2,cy-h//2,cx+w//2,cy+h//2]
    draw.rounded_rectangle(box,18,fill="#F8FAFC",outline="#CBD5E1",width=5)
    for i in range(4):
        yy=box[1]+55+i*42
        draw.line((box[0]+35,yy,box[2]-35,yy),fill="#94A3B8",width=4)

def scene_hook(data, t):
    im=base(); d=ImageDraw.Draw(im); brand(d); progress(d,0.06)
    if t < 0.45:
        draw_wax(d,W//2,650,0.9)
    else:
        draw_wax(d,W//2,650,0.9)
        draw_stamp(d,W//2,500+int(min(120,t*130)),0.72)
    centered(d,data["hook"],980,62,WHITE)
    centered(d,"रुकिए — पहले जवाब मत देखना",1110,34,YELLOW)
    return im

def scene_guess(data, t):
    im=base(); d=ImageDraw.Draw(im); brand(d); progress(d,0.13)
    centered(d,"आप क्या चुनेंगे?",330,64,WHITE)
    rounded(d,(90,560,500,1030),40,CARD2,RED,5)
    centered(d,"❌",650,110,RED)
    centered(d,"सीधे मोम पर",820,42,WHITE)
    rounded(d,(580,560,990,1030),40,CARD2,GREEN,5)
    centered(d,"❓",650,110,YELLOW)
    centered(d,"कागज के साथ?",820,42,WHITE)
    centered(d,"सोचिए…",1240,48,YELLOW)
    return im

def scene_answer(data, t):
    im=base(); d=ImageDraw.Draw(im); brand(d); progress(d,0.20)
    centered(d,"सही तरीका",330,48,MUTED)
    sc = min(1.0,0.78 + t*0.18)
    draw_paper(d,W//2,650,sc)
    draw_stamp(d,W//2,650,sc*0.62)
    centered(d,"पहले कागज  →  फिर टिकट",1030,58,GREEN)
    centered(d,"यही point याद रखें",1150,38,WHITE)
    return im

def scene_fact(data, t):
    im=base(); d=ImageDraw.Draw(im); brand(d); progress(d,0.31)
    if t < 0.7:
        draw_wax(d,W//2,650,0.82)
    elif t < 1.35:
        draw_wax(d,W//2,650,0.82)
        draw_paper(d,W//2,650,0.75)
    else:
        draw_wax(d,W//2,650,0.82)
        draw_paper(d,W//2,650,0.75)
        draw_stamp(d,W//2,650,0.50)
    centered(d,data["fact"],1060,45,WHITE)
    return im

def scene_trap(data, t):
    im=base(); d=ImageDraw.Draw(im); brand(d); progress(d,0.42)
    rounded(d,(70,300,1010,1500),45,CARD, YELLOW, 5)
    centered(d,"⚠️ EXAM TRAP",450,60,YELLOW)
    centered(d,"सीधे मोम पर",680,54,RED)
    centered(d,"❌",800,100,RED)
    centered(d,"पहले कागज",990,54,GREEN)
    centered(d,"फिर टिकट",1090,54,GREEN)
    centered(d,data["trap"],1310,38,WHITE)
    return im

def scene_mcq(data, t, countdown=False):
    im=base(); d=ImageDraw.Draw(im); brand(d); progress(d,0.62 if not countdown else 0.78)
    centered(d,"📝 POSTAL MCQ",260,54,CYAN)
    qf=dev_font(50)
    q=wrap_text(d,data["question"],qf,900)
    lines=q.split("\n")
    yy=390
    for line in lines:
        centered(d,line,yy,50,WHITE); yy+=70

    opts=[("A",data["a"]),("B",data["b"]),("C",data["c"]),("D",data["d"])]
    y0=650
    for i,(letter,text) in enumerate(opts):
        y=y0+i*210
        if t < i*0.35:
            continue
        outline=CYAN if countdown and i == 0 else "#24384F"
        rounded(d,(80,y,1000,y+160),32,CARD2,outline,4)
        df,ef=dev_font(38),eng_font(38)
        draw_mixed(d,(130,y+53),f"{letter}. {text}",df,ef,WHITE)

    if countdown:
        remaining=max(1,5-int(t))
        centered(d,str(remaining),1580,90,YELLOW)
        centered(d,"अपना A / B / C / D अभी comment करें",1720,38,WHITE)
    return im

def scene_result(data, t):
    im=base(); d=ImageDraw.Draw(im); brand(d); progress(d,0.93)
    rounded(d,(90,430,990,1150),50,CARD,GREEN,6)
    centered(d,"✅ सही उत्तर",570,64,GREEN)
    centered(d,data["correct"],760,120,WHITE)
    correct_text=data[{"A":"a","B":"b","C":"c","D":"d"}[data["correct"]]]
    centered(d,correct_text,960,44,WHITE)
    centered(d,"अगले Postal MCQ के लिए Follow",1320,42,WHITE)
    centered(d,"@POSTAL_WALA",1430,48,CYAN)
    return im

# ------------------------------------------------------------
# 8) VIDEO BUILD & EXPORT
# ------------------------------------------------------------
def save_frame(im, path):
    im.save(path, quality=95)

def make_scene_frames(scene_fn, duration, prefix, *args):
    n=max(1,int(math.ceil(duration*FPS)))
    paths=[]
    for i in range(n):
        t=i/FPS
        im=scene_fn(*args,t)
        p=f"{prefix}_{i:05d}.jpg"
        save_frame(im,p)
        paths.append(p)
    return paths

def frames_to_video(frame_paths, out_path):
    concat_file="frames_concat.txt"
    with open(concat_file,"w",encoding="utf-8") as f:
        for p in frame_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    subprocess.run([
        "ffmpeg","-y","-r",str(FPS),"-f","concat","-safe","0",
        "-i",concat_file,"-vf",f"fps={FPS},format=yuv420p",
        "-c:v","libx264","-preset","medium","-crf","19",
        out_path
    ],check=True)
    if os.path.exists(concat_file):
        os.remove(concat_file)

def mux(video_path, audio_path, output):
    subprocess.run([
        "ffmpeg","-y",
        "-i",video_path,
        "-i",audio_path,
        "-map","0:v:0","-map","1:a:0",
        "-c:v","copy","-c:a","aac","-b:a","192k",
        "-shortest",output
    ],check=True)

def build_reel(data, output_file):
    voice = (
        f"{data['hook']} "
        f"सोचिए... "
        f"सही तरीका है: पहले कागज, फिर टिकट। "
        f"{data['fact']} "
        f"लेकिन परीक्षा में ध्यान रहे: {data['trap']} "
        f"अब सवाल देखिए: {data['question']} "
        f"विकल्प हैं: A {data['a']}. B {data['b']}. C {data['c']}. D {data['d']}. "
        f"आपका जवाब क्या है? A, B, C या D कमेंट करें। "
        f"सही उत्तर है {data['correct']}."
    )

    audio="master_voice.mp3"
    asyncio.run(make_audio(voice,audio))
    tighten_audio(audio)

    dur=audio_duration(audio)
    target=min(max(dur,25.0),31.0)

    d1=target*0.09
    d2=target*0.10
    d3=target*0.10
    d4=target*0.12
    d5=target*0.12
    d6=target*0.30
    d7=target*0.17

    all_frames=[]
    all_frames += make_scene_frames(scene_hook,d1,"fr_hook",data)
    all_frames += make_scene_frames(scene_guess,d2,"fr_guess",data)
    all_frames += make_scene_frames(scene_answer,d3,"fr_answer",data)
    all_frames += make_scene_frames(scene_fact,d4,"fr_fact",data)
    all_frames += make_scene_frames(scene_trap,d5,"fr_trap",data)
    all_frames += make_scene_frames(lambda d,t: scene_mcq(d,t,False),d6*0.62,"fr_mcq",data)
    all_frames += make_scene_frames(lambda d,t: scene_mcq(d,t,True),d6*0.38,"fr_count",data)
    all_frames += make_scene_frames(scene_result,d7,"fr_result",data)

    silent="silent_reel.mp4"
    frames_to_video(all_frames,silent)
    mux(silent,audio,output_file)

    # Clean temporary frame files
    for p in all_frames:
        try: os.remove(p)
        except: pass
    for p in [audio,silent]:
        try: os.remove(p)
        except: pass

    print(f"\n✅ REEL READY: {output_file}")

# ------------------------------------------------------------
# 9) AUTO COMMIT / PUSH (IF RUN LOCALLY)
# ------------------------------------------------------------
def push_if_local(target_video, state_file):
    # If running inside GitHub Actions, the workflow YAML handles the push.
    if os.getenv("GITHUB_ACTIONS"):
        print("Running in GitHub Actions - workflow will commit the reel automatically.")
        return

    try:
        subprocess.run(["git", "add", target_video, state_file], check=True)
        commit_msg = f"Add reel: {os.path.basename(target_video)} [skip ci]"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "push"], check=True)
        print("🚀 Successfully pushed video to GitHub repository!")
    except Exception as e:
        print("Local git push notice (workflow may handle it):", e)

# ------------------------------------------------------------
# 10) MAIN EXECUTION
# ------------------------------------------------------------
if __name__ == "__main__":
    state = load_state()
    clause_no = state["clause_no"]
    part_no = state["current_part"]

    # 1. Target output path inside generated_reels folder
    target_reel_name = f"reel_clause_{clause_no}_part_{part_no}.mp4"
    target_output_path = os.path.join(REELS_DIR, target_reel_name)

    # 2. Generate script and render video
    data = generate_script(state)
    print("\nSCRIPT:")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    build_reel(data, target_output_path)

    # Optional root fallback copy for existing setups
    try:
        shutil.copy(target_output_path, "final_reel.mp4")
    except Exception:
        pass

    # 3. Advance state for next cycle
    info = POSTAL_CLAUSE_CATALOG[clause_no]
    if part_no < info["total_parts"]:
        state["current_part"] += 1
    else:
        keys = sorted(POSTAL_CLAUSE_CATALOG.keys())
        idx = keys.index(clause_no)
        state["clause_no"] = keys[(idx + 1) % len(keys)]
        state["current_part"] = 1
    save_state(state)

    # 4. Push to GitHub if running locally
    push_if_local(target_output_path, STATE_FILE)
