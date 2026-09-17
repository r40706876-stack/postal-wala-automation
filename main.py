import os
import glob
import json
import time
import textwrap
import subprocess
import requests
from pypdf import PdfReader
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

STATE_FILE = "progress_state.json"
DEV_FONT_PATH = "NotoSansDevanagari-Bold.ttf"

def ensure_fonts():
    if not os.path.exists(DEV_FONT_PATH):
        print("📥 Downloading Noto Sans Devanagari font...")
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        r = requests.get(url, timeout=30)
        with open(DEV_FONT_PATH, "wb") as f:
            f.write(r.content)
        print("✅ Font cached locally.")

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

def get_target_pdf():
    pdf_files = glob.glob("*.pdf") + glob.glob("data/*.pdf")
    if not pdf_files:
        raise FileNotFoundError("Repo me koi PDF nahi mili!")
    for f in pdf_files:
        if "mts" in f.lower():
            return f
    return pdf_files[0]

def get_current_reading_window(pdf_path):
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    
    state = {"last_page": 0, "char_offset": 0}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
        except Exception:
            pass

    current_page = state.get("last_page", 0)
    char_offset = state.get("char_offset", 0)

    if current_page >= total_pages:
        current_page = 0
        char_offset = 0

    page_text = reader.pages[current_page].extract_text() or ""
    
    # Take a continuous chunk from where it left off, ensuring deep clause coverage
    chunk_size = 1200
    sub_text = page_text[char_offset:char_offset + chunk_size]

    # If the page chunk is finishing, move to next page
    next_offset = char_offset + chunk_size
    next_page = current_page
    if next_offset >= len(page_text):
        next_page += 1
        next_offset = 0

    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"last_page": next_page, "char_offset": next_offset}, f)
    except Exception:
        pass

    return sub_text, current_page + 1

def generate_clause_script(pdf_content, page_num):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY missing in GitHub Secrets!")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
        "Content-Type": "application/json"
    }

    prompt = f"""
    You are an expert tutor for Postal MTS/Postman exam running Instagram page 'Postal Wala'.
    Continue teaching the department rules deeply and thoroughly from this running section (Page {page_num}). 
    DO NOT abruptly jump topics. Continue from the exact flow of the text provided below. Give a detailed, comprehensive explanation spanning 4 sequential sentences (SEN1, SEN2, SEN3, SEN4).

    RULES:
    1. Pure Hindi (Devanagari script only), no English words, no emojis, no bullet symbols.
    2. Provide 4 progressive detailed sentences covering the topic thoroughly.

    PDF Section:
    {pdf_content}

    Format strictly matching these lines:
    TITLE: [Topic Name in Hindi]
    SEN1: [Detailed sentence 1]
    SEN2: [Detailed sentence 2]
    SEN3: [Detailed sentence 3]
    SEN4: [Detailed sentence 4]
    QUESTION: [1 deep exam question based on this text in Hindi]
    OPT_A: [Option A]
    OPT_B: [Option B]
    OPT_C: [Option C]
    OPT_D: [Option D]
    CORRECT: [A/B/C/D]
    VOICEOVER: [Full spoken script combining SEN1, SEN2, SEN3, SEN4 + Quiz + Outro at normal calm teaching speed]
    CAPTION: [Instagram caption with #PostalWala #MTSExam #IndiaPost #Khand02]
    """

    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 700
    }
    
    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
    res_json = res.json()

    if res.status_code != 200 or "choices" not in res_json:
        raise RuntimeError(f"Groq API Error: {res_json}")

    raw_text = res_json["choices"][0]["message"]["content"].strip()
    
    data = {
        "rule_title": "डाक सेवाओं का विस्तृत नियम",
        "sen1": "डाल विभाग के नियमों के अनुसार डाक वस्तुओं का वितरण सुचारू रूप से होना अनिवार्य है।",
        "sen2": "प्रत्येक डाकघर को प्राप्त होने वाली डाक की छँटाई निर्धारित समय पर करनी होती है।",
        "sen3": "यदि किसी वस्तु पर पता स्पष्ट नहीं है तो उसे संबंधित शाखा में भेजा जाता है।",
        "sen4": "इन सभी प्रक्रियाओं का उद्देश्य ग्राहकों को समय पर सेवा प्रदान करना है।",
        "question": "अस्पष्ट पते वाली डाक वस्तु को कहाँ भेजा जाता है?",
        "opt_a": "मुख्य शाखा",
        "opt_b": "संबंधित शाखा या डेड लेटर कार्यालय",
        "opt_c": "नष्ट करने हेतु",
        "opt_d": "प्रेषक को तुरंत वापस",
        "correct": "B",
        "voiceover": "नमस्कार साथियों, पोस्टल वाला में आपका स्वागत है। आज हम पिछले क्लाउज़ को आगे बढ़ाते हुए डाक विभाग के अगले महत्वपूर्ण नियमों को गहराई से समझेंगे। डाक विभाग के नियमों के अनुसार डाक वस्तुओं का वितरण सुचारू रूप से होना अनिवार्य है। प्रत्येक डाकघर को प्राप्त होने वाली डाक की छँटाई निर्धारित समय पर करनी होती है। यदि किसी वस्तु पर पता स्पष्ट नहीं है तो उसे संबंधित शाखा में भेजा जाता है। इन सभी प्रक्रियाओं का उद्देश्य ग्राहकों को समय पर सेवा प्रदान करना है। आइए अब इस नियम पर आधारित एक महत्वपूर्ण परीक्षा प्रश्न हल करें। अस्पष्ट पते वाली डाक वस्तु को कहाँ भेजा जाता है? सही उत्तर है ऑप्शन बी, संबंधित शाखा या डेड लेटर कार्यालय। रोज़ाना ऐसी विस्तृत तैयारी के लिए अभी फॉलो करें पोस्टल वाला को!",
        "caption": "डाक विभाग परीक्षा तैयारी निरंतरता #PostalWala #MTSExam #Khand02"
    }
    
    for line in raw_text.splitlines():
        line_clean = line.strip()
        if line_clean.startswith("TITLE:"):
            data["rule_title"] = line_clean.replace("TITLE:", "").strip()
        elif line_clean.startswith("SEN1:"):
            data["sen1"] = line_clean.replace("SEN1:", "").strip()
        elif line_clean.startswith("SEN2:"):
            data["sen2"] = line_clean.replace("SEN2:", "").strip()
        elif line_clean.startswith("SEN3:"):
            data["sen3"] = line_clean.replace("SEN3:", "").strip()
        elif line_clean.startswith("SEN4:"):
            data["sen4"] = line_clean.replace("SEN4:", "").strip()
        elif line_clean.startswith("QUESTION:"):
            data["question"] = line_clean.replace("QUESTION:", "").strip()
        elif line_clean.startswith("OPT_A:"):
            data["opt_a"] = line_clean.replace("OPT_A:", "").strip()
        elif line_clean.startswith("OPT_B:"):
            data["opt_b"] = line_clean.replace("OPT_B:", "").strip()
        elif line_clean.startswith("OPT_C:"):
            data["opt_c"] = line_clean.replace("OPT_C:", "").strip()
        elif line_clean.startswith("OPT_D:"):
            data["opt_d"] = line_clean.replace("OPT_D:", "").strip()
        elif line_clean.startswith("CORRECT:"):
            data["correct"] = line_clean.replace("CORRECT:", "").strip().upper()[:1]
        elif line_clean.startswith("VOICEOVER:"):
            data["voiceover"] = line_clean.replace("VOICEOVER:", "").strip()
        elif line_clean.startswith("CAPTION:"):
            data["caption"] = line_clean.replace("CAPTION:", "").strip()

    for k in data:
        if isinstance(data[k], str):
            data[k] = "".join(c for c in data[k] if ord(c) < 0x10000)

    return data

def generate_voice(text, filename="voice.mp3"):
    # slow=False with natural sentence pacing for clear teaching audio
    tts = gTTS(text=text, lang="hi", slow=False)
    tts.save(filename)

def get_audio_duration(audio_file):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_file]
    output = subprocess.check_output(cmd).decode().strip()
    return float(output)

def create_video_ffmpeg(script_data, audio_file="voice.mp3", output_video="final_reel.mp4"):
    ensure_fonts()
    total_dur = get_audio_duration(audio_file)
    
    step_dur = max(4.0, (total_dur - 15.0) / 4.0)
    t1, t2, t3, t4 = step_dur, step_dur*2, step_dur*3, max(10.0, total_dur - 15.0)

    font_brand = get_eng_font(52)
    font_sub = get_eng_font(30)
    font_cta_eng = get_eng_font(36)

    font_title = get_dev_font(42)
    font_h2 = get_dev_font(40)
    font_body = get_dev_font(36)
    font_label = get_dev_font(30)
    font_cta_hin = get_dev_font(34)

    def draw_base(draw_obj):
        draw_obj.rounded_rectangle([45, 90, 1035, 1830], radius=35, fill="#1E293B", outline="#E11D48", width=6)
        draw_obj.text((90, 140), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        draw_obj.text((90, 220), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)

    def draw_footer(draw_obj):
        draw_obj.rounded_rectangle([85, 1610, 995, 1750], radius=25, fill="#E11D48")
        draw_obj.text((180, 1635), "पूरी तैयारी के लिए फॉलो करें:", fill="#FFFFFF", font=font_cta_hin)
        draw_obj.text((370, 1685), "@POSTAL_WALA", fill="#FFFFFF", font=font_cta_eng)

    sentences = [script_data["sen1"], script_data["sen2"], script_data["sen3"], script_data["sen4"]]
    slide_filenames = []

    for idx, sentence in enumerate(sentences, 1):
        img = Image.new("RGB", (1080, 1920), color="#0F172A")
        d = ImageDraw.Draw(img)
        draw_base(d)

        d.rounded_rectangle([85, 290, 995, 470], radius=25, fill="#0F172A", outline="#38BDF8", width=3)
        d.text((115, 315), f"जारी नियम ({idx}/4):", fill="#38BDF8", font=font_label)
        d.text((115, 355), textwrap.fill(script_data["rule_title"], width=30), fill="#FFFFFF", font=font_title)

        d.rounded_rectangle([85, 500, 995, 1550], radius=30, fill="#0F172A")
        d.text((120, 540), "विस्तृत व्याख्या:", fill="#FBBF24", font=font_h2)

        # Active Live Spoken Sentence Box
        d.rounded_rectangle([115, 700, 965, 1250], radius=25, fill="#1E293B", outline="#38BDF8", width=3)
        d.text((140, 740), "मुख्य बात:", fill="#38BDF8", font=font_label)
        d.text((140, 820), textwrap.fill(sentence, width=25), fill="#F8FAFC", font=font_body)

        draw_footer(d)
        fname = f"slide_{idx}.png"
        img.save(fname)
        slide_filenames.append(fname)

    # Quiz Slide
    img5 = Image.new("RGB", (1080, 1920), color="#0F172A")
    d5 = ImageDraw.Draw(img5)
    draw_base(d5)

    d5.rounded_rectangle([85, 290, 995, 470], radius=25, fill="#0F172A", outline="#FBBF24", width=3)
    d5.text((115, 315), "परीक्षा क्विज़:", fill="#FBBF24", font=font_label)
    d5.text((115, 355), "सवाल का जवाब दें!", fill="#FFFFFF", font=font_title)

    d5.rounded_rectangle([85, 500, 995, 1550], radius=30, fill="#0F172A")
    d5.text((120, 540), "सवाल:", fill="#FBBF24", font=font_h2)
    d5.text((120, 620), textwrap.fill(script_data["question"], width=26), fill="#F8FAFC", font=font_body)

    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    correct = script_data.get("correct", "B")
    oy = 950
    for idx, opt in enumerate(opts):
        is_ans = (correct == chr(65 + idx))
        box_bg = "#064E3B" if is_ans else "#1E293B"
        border_c = "#10B981" if is_ans else "#38BDF8"
        text_c = "#34D399" if is_ans else "#FFFFFF"

        d5.rounded_rectangle([115, oy, 965, oy + 95], radius=18, fill=box_bg, outline=border_c, width=2)
        d5.text((145, oy + 25), f"{chr(65+idx)}) {textwrap.fill(opt, width=32)}", fill=text_c, font=font_body)
        oy += 120

    draw_footer(d5)
    img5.save("slide_5.png")
    slide_filenames.append("slide_5.png")

    durations = [t1, t2 - t1, t3 - t2, t4 - t3, total_dur - t4]
    inputs = ""
    filter_parts = ""
    for i, fname in enumerate(slide_filenames):
        inputs += f"-i {fname} "
    
    for i, dur in enumerate(durations):
        filter_parts += f"[{i}:v]loop=loop=-1:size=1:start=0,trim=duration={max(1.0, dur)}[v{i}]; "
    
    concat_str = "".join([f"[v{i}]" for i in range(len(slide_filenames))])
    filter_complex = f"{filter_parts}{concat_str}concat=n={len(slide_filenames)}:v=1:a=0,format=yuv420p[v]"

    cmd = ["ffmpeg", "-y"]
    cmd.extend(inputs.strip().split())
    cmd.extend([
        "-i", audio_file,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", f"{len(slide_filenames)}:a",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-profile:v", "main",
        "-level:v", "4.0",
        "-r", "30",
        "-g", "60",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-movflags", "+faststart",
        "-shortest", output_video
    ])
    subprocess.run(cmd, check=True)
    print("✅ Perfectly Synced Continuous Reel Created.")

def upload_to_instagram_direct(video_path, caption):
    if not IG_ACCESS_TOKEN or not IG_USER_ID:
        raise ValueError("CRITICAL: IG_ACCESS_TOKEN ya IG_USER_ID missing hai!")

    file_size = os.path.getsize(video_path)
    print(f"📦 Video size: {file_size / (1024*1024):.2f} MB")

    init_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    init_payload = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN
    }
    r_init = requests.post(init_url, data=init_payload)
    init_data = r_init.json()

    video_id = init_data.get("id")
    upload_url = init_data.get("uri")

    if not video_id or not upload_url:
        raise RuntimeError(f"Session initialization failed: {init_data}")

    headers = {
        "Authorization": f"OAuth {IG_ACCESS_TOKEN}",
        "offset": "0",
        "file_size": str(file_size)
    }

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    r_upload = requests.post(upload_url, headers=headers, data=video_bytes, timeout=180)

    if r_upload.status_code not in [200, 201]:
        raise RuntimeError(f"Meta byte upload failed ({r_upload.status_code}): {r_upload.text}")

    status_url = f"https://graph.facebook.com/v19.0/{video_id}?fields=status_code&access_token={IG_ACCESS_TOKEN}"

    for attempt in range(1, 40):
        time.sleep(8)
        status_res = requests.get(status_url).json()
        code = status_res.get("status_code")
        print(f"🔄 Check {attempt}: {code}")

        if code == "FINISHED":
            print("✅ Transcoding FINISHED!")
            break
        elif code in ["ERROR", "EXPIRED"]:
            raise RuntimeError(f"Instagram rejected video: {status_res}")
    else:
        print("⚠️ Polling timeout, attempting to publish...")

    pub_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    pub_res = requests.post(pub_url, data={"creation_id": video_id, "access_token": IG_ACCESS_TOKEN})
    pub_json = pub_res.json()

    if "id" in pub_json:
        print(f"🎉 SUCCESS! Reel Live on Instagram! Post ID: {pub_json['id']}")
    else:
        raise RuntimeError(f"Publish Failed: {pub_json}")

if __name__ == "__main__":
    print("🚀 Postal Wala Continuous Automation Starting...")
    
    target_pdf = get_target_pdf()
    pdf_content, page_num = get_current_reading_window(target_pdf)
    print(f"✅ Read Page {page_num} with continuous offset.")

    script_data = generate_clause_script(pdf_content, page_num)
    print("✅ AI Script Ready for Ongoing Clause.")

    generate_voice(script_data["voiceover"], "voice.mp3")
    print("✅ Voiceover Ready at Normal Speed.")

    create_video_ffmpeg(script_data, "voice.mp3", "final_reel.mp4")

    upload_to_instagram_direct("final_reel.mp4", script_data.get("caption", ""))
