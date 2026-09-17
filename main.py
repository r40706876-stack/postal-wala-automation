import os
import glob
import json
import time
import asyncio
import subprocess
import requests
import textwrap
from pypdf import PdfReader
from PIL import Image, ImageDraw, ImageFont
from groq import Groq
import edge_tts

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

GRAPH_API_BASE = "".join(["http", "s://", "graph.", "facebook", ".com/v19.0/"])
STATE_FILE = "progress_state.json"
DEV_FONT_PATH = "NotoSansDevanagari-Bold.ttf"
AUDIO_OUTPUT = "voice.mp3"
OUTPUT_VIDEO = "final_reel.mp4"
VOICE_NAME = "hi-IN-SwaraNeural"

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
    chunk_size = 1400
    sub_text = page_text[char_offset:char_offset + chunk_size]

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
    Teach the departmental rules thoroughly and completely from this running section (Page {page_num}). 
    Do NOT cut short or leave the clause half-explained. Provide a comprehensive, uninterrupted explanation spanning 4 rich, grammatically flawless Hindi sentences (SEN1, SEN2, SEN3, SEN4).

    RULES:
    1. Pure Hindi (Devanagari script only), flawless grammar, zero spelling mistakes, no English words, no emojis, no bullet symbols.
    2. Keep each sentence natural and focused on a single complete rule aspect.

    PDF Section:
    {pdf_content}

    Format strictly matching these lines:
    TITLE: [Topic Name in pure Hindi]
    SEN1: [Flawless sentence 1]
    SEN2: [Flawless sentence 2]
    SEN3: [Flawless sentence 3]
    SEN4: [Flawless sentence 4]
    QUESTION: [1 high-value exam question based strictly on this text in Hindi]
    OPT_A: [Option A]
    OPT_B: [Option B]
    OPT_C: [Option C]
    OPT_D: [Option D]
    CORRECT: [A/B/C/D]
    VOICEOVER: [Full natural teaching voiceover combining a warm greeting, clear explanation of SEN1 to SEN4, the quiz question, and a strong call-to-action ending with: रोज़ाना ऐसी बेहतरीन तैयारी के लिए अभी फॉलो करें पोस्टल वाला को!]
    CAPTION: [Instagram caption with #PostalWala #MTSExam #IndiaPost #Khand02]
    """

    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 800
    }
    
    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
    res_json = res.json()

    if res.status_code != 200 or "choices" not in res_json:
        raise RuntimeError(f"Groq API Error: {res_json}")

    raw_text = res_json["choices"][0]["message"]["content"].strip()
    
    data = {
        "rule_title": "डाक नियमों की विस्तृत जानकारी",
        "sen1": "विभागीय नियमों के अनुसार सभी डाक वस्तुओं का सुरक्षित प्रबंधन करना अनिवार्य होता है।",
        "sen2": "प्रत्येक डाकघर में प्राप्त होने वाली सामग्री की प्रविष्टि आधिकारिक रजिस्टर में दर्ज की जाती है।",
        "sen3": "नियमों का उल्लंघन पाए जाने पर उच्च अधिकारियों द्वारा सख्त अनुशासनात्मक कार्रवाई की जाती है।",
        "sen4": "सभी अभ्यर्थियों को परीक्षा की दृष्टि से इन प्रावधानों को पूरी तरह याद रखना चाहिए।",
        "question": "विभागीय नियमों के उल्लंघन पर कार्रवाई करने का अधिकार किसे प्राप्त है?",
        "opt_a": "स्थानीय डाकपाल",
        "opt_b": "उच्च अधिकारियों",
        "opt_c": "प्रेषक को",
        "opt_d": "इनमें से कोई नहीं",
        "correct": "B",
        "voiceover": "नमस्कार साथियों, पोस्टल वाला में आपका स्वागत है। आज हम डाक विभाग के नियमों को बिल्कुल विस्तार से और गहराई से समझेंगे ताकि परीक्षा में आपका एक भी नंबर न कटे। विभागीय नियमों के अनुसार सभी डाक वस्तुओं का सुरक्षित प्रबंधन करना अनिवार्य होता है। प्रत्येक डाकघर में प्राप्त होने वाली सामग्री की प्रविष्टि आधिकारिक रजिस्टर में दर्ज की जाती है। नियमों का उल्लंघन पाए जाने पर उच्च अधिकारियों द्वारा सख्त अनुशासनात्मक कार्रवाई की जाती है। सभी अभ्यर्थियों को परीक्षा की दृष्टि से इन प्रावधानों को पूरी तरह याद रखना चाहिए। आइए अब इस नियम पर आधारित एक महत्वपूर्ण प्रश्न हल करें। विभागीय नियमों के उल्लंघन पर कार्रवाई करने का अधिकार किसे प्राप्त है? सही उत्तर है ऑप्शन बी, उच्च अधिकारियों। ऐसी ही शानदार और संपूर्ण तैयारी के लिए अभी फॉलो करें पोस्टल वाला को!",
        "caption": "डाक विभाग परीक्षा तैयारी संपूर्ण विश्लेषण #PostalWala #MTSExam #Khand02"
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

async def generate_voice(text, filename="voice.mp3"):
    communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="-2%")
    await communicate.save(filename)

def get_audio_duration(audio_file):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_file]
    output = subprocess.check_output(cmd).decode().strip()
    return float(output)

def create_video_ffmpeg(script_data, audio_file="voice.mp3", output_video="final_reel.mp4"):
    ensure_fonts()
    total_dur = get_audio_duration(audio_file)
    
    step_dur = max(4.5, (total_dur - 15.0) / 4.0)
    t1, t2, t3, t4 = step_dur, step_dur*2, step_dur*3, max(12.0, total_dur - 15.0)

    font_brand = get_eng_font(48)
    font_sub = get_eng_font(26)

    font_title = get_dev_font(36)
    font_h2 = get_dev_font(32)
    font_body = get_dev_font(32)
    font_label = get_dev_font(26)
    font_cta_hin = get_dev_font(30)
    font_cta_eng = get_eng_font(30)

    def draw_base(draw_obj):
        draw_obj.rounded_rectangle([45, 50, 1035, 1770], radius=30, fill="#1E293B", outline="#E11D48", width=4)
        draw_obj.text((80, 80), "POSTAL WALA", fill="#F43F5E", font=font_brand)
        draw_obj.text((80, 135), "@POSTAL_WALA", fill="#94A3B8", font=font_sub)

    def draw_footer(draw_obj):
        draw_obj.rounded_rectangle([80, 1590, 1000, 1720], radius=22, fill="#E11D48")
        draw_obj.text((120, 1622), "पूरी तैयारी के लिए फॉलो करें:", fill="#FFFFFF", font=font_cta_hin)
        draw_obj.text((610, 1622), "@POSTAL_WALA", fill="#FFFFFF", font=font_cta_eng)

    sentences = [script_data["sen1"], script_data["sen2"], script_data["sen3"], script_data["sen4"]]
    slide_filenames = []

    for idx, sentence in enumerate(sentences, 1):
        img = Image.new("RGB", (1080, 1920), color="#0F172A")
        d = ImageDraw.Draw(img)
        draw_base(d)

        d.rounded_rectangle([80, 190, 1000, 330], radius=20, fill="#0F172A", outline="#38BDF8", width=2)
        d.text((110, 205), f"संपूर्ण नियम ({idx}/4):", fill="#38BDF8", font=font_label)
        d.text((110, 245), textwrap.fill(script_data["rule_title"], width=34), fill="#FFFFFF", font=font_title)

        d.rounded_rectangle([80, 360, 1000, 1550], radius=22, fill="#0F172A")
        d.text((110, 390), "विस्तृत व्याख्या:", fill="#FBBF24", font=font_h2)

        d.rounded_rectangle([110, 480, 970, 1520], radius=20, fill="#1E293B", outline="#38BDF8", width=2)
        d.text((135, 510), "मुख्य बिंदु:", fill="#38BDF8", font=font_label)
        
        wrapped_text = textwrap.fill(sentence, width=24)
        d.text((135, 580), wrapped_text, fill="#F8FAFC", font=font_body)

        draw_footer(d)
        fname = f"slide_{idx}.png"
        img.save(fname)
        slide_filenames.append(fname)

    # Quiz Slide (Slide 5)
    img5 = Image.new("RGB", (1080, 1920), color="#0F172A")
    d5 = ImageDraw.Draw(img5)
    draw_base(d5)

    d5.rounded_rectangle([80, 190, 1000, 330], radius=20, fill="#0F172A", outline="#FBBF24", width=2)
    d5.text((110, 205), "परीक्षा क्विज़:", fill="#FBBF24", font=font_label)
    d5.text((110, 245), "सवाल का जवाब दें!", fill="#FFFFFF", font=font_title)

    d5.rounded_rectangle([80, 360, 1000, 1550], radius=22, fill="#0F172A")
    d5.text((110, 390), "सवाल:", fill="#FBBF24", font=font_h2)
    
    q_wrapped = textwrap.fill(script_data["question"], width=26)
    d5.text((110, 450), q_wrapped, fill="#F8FAFC", font=font_body)

    opts = [script_data["opt_a"], script_data["opt_b"], script_data["opt_c"], script_data["opt_d"]]
    correct = script_data.get("correct", "B")
    oy = 790
    for idx, opt in enumerate(opts):
        is_ans = (correct == chr(65 + idx))
        box_bg = "#064E3B" if is_ans else "#1E293B"
        border_c = "#10B981" if is_ans else "#38BDF8"
        text_c = "#34D399" if is_ans else "#FFFFFF"

        d5.rounded_rectangle([110, oy, 970, oy + 95], radius=16, fill=box_bg, outline=border_c, width=2)
        opt_text = f"{chr(65+idx)}) {textwrap.fill(opt, width=28)}"
        d5.text((135, oy + 22), opt_text, fill=text_c, font=font_body)
        oy += 115

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
        "-preset", "ultrafast",
        "-profile:v", "baseline",
        "-level", "3.0",
        "-pix_fmt", "yuv420p",
        "-bf", "0",
        "-r", "30",
        "-g", "30",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-movflags", "+faststart",
        "-shortest", output_video
    ])
    subprocess.run(cmd, check=True)
    print("✅ Strict Instagram-Compatible Baseline Reel Created.")

def post_reel_to_instagram_direct(video_file, caption):
    access_token = os.getenv("IG_ACCESS_TOKEN")
    user_id = os.getenv("IG_USER_ID")
    
    if not access_token or not user_id:
        raise ValueError("IG_ACCESS_TOKEN ya IG_USER_ID secrets me missing hai!")

    file_size = os.path.getsize(video_file)
    print(f"Video size: {file_size} bytes. Initializing Instagram Resumable Session...")

    init_url = GRAPH_API_BASE + str(user_id).strip() + "/media"
    init_params = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "access_token": access_token
    }
    
    r = requests.post(init_url, data=init_params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Upload init fail hua: {r.text}")
        
    init_data = r.json()
    video_id = init_data.get("id")
    upload_url = init_data.get("upload_url") or init_data.get("uri")

    if not video_id or not upload_url:
        raise RuntimeError(f"Upload init invalid response: {init_data}")

    print(f"Uploading video file via strict binary stream to Meta...")
    
    with open(video_file, "rb") as vf:
        # FIXED: Meta requires BOTH Content-Length and X-Entity-Length matching file size for raw stream uploads
        headers = {
            "Authorization": f"OAuth {access_token}",
            "Offset": "0",
            "Content-Length": str(file_size),
            "X-Entity-Length": str(file_size),
            "Content-Type": "application/octet-stream"
        }
        upload_res = requests.post(upload_url, headers=headers, data=vf, timeout=300)

    if upload_res.status_code not in [200, 201]:
        raise RuntimeError(f"Video binary upload fail hua ({upload_res.status_code}): {upload_res.text}")

    print("Waiting for Instagram video processing...")
    status_url = GRAPH_API_BASE + str(video_id).strip()
    for attempt in range(40):
        time.sleep(10)
        try:
            status_res = requests.get(status_url, params={"fields": "status_code", "access_token": access_token}, timeout=30).json()
            status = status_res.get("status_code")
            print(f"Check {attempt+1}: Status -> {status}")
            if status == "FINISHED":
                break
            elif status in ["ERROR", "EXPIRED"]:
                raise RuntimeError(f"Instagram processing failed with status: {status_res}")
        except Exception as e:
            print(f"Polling warning: {e}")

    print("Publishing Reel...")
    publish_url = GRAPH_API_BASE + str(user_id).strip() + "/media_publish"
    pub_res = requests.post(publish_url, data={"creation_id": video_id, "access_token": access_token}, timeout=30).json()

    if "id" in pub_res:
        print(f"🎉 Reel successfully published on Instagram! Post ID: {pub_res['id']}")
    else:
        raise RuntimeError(f"Publish fail hua: {pub_res}")

if __name__ == "__main__":
    print("🚀 Postal Wala Deep Continuous Automation Starting...")
    
    target_pdf = get_target_pdf()
    pdf_content, page_num = get_current_reading_window(target_pdf)
    print(f"✅ Read Page {page_num} with deep continuous tracking.")

    script_data = generate_clause_script(pdf_content, page_num)
    print("✅ AI Script Ready with Thorough Explanation.")

    asyncio.run(generate_voice(script_data["voiceover"], AUDIO_OUTPUT))
    print("✅ Voiceover Ready with Natural Teaching Pacing.")

    create_video_ffmpeg(script_data, AUDIO_OUTPUT, OUTPUT_VIDEO)

    post_reel_to_instagram_direct(OUTPUT_VIDEO, script_data.get("caption", ""))
