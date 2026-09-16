import os
import glob
import json
import time
import subprocess
import requests
from pypdf import PdfReader
from gtts import gTTS
from html2image import Html2Image

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

STATE_FILE = "progress_state.json"

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
    
    current_page = 0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                current_page = state.get("last_page", 0)
        except Exception:
            current_page = 0

    if current_page == 0:
        search_terms = ["खंड - 02", "खंड-02", "खंड 02", "खंड 2", "डाकघरों के प्रकार"]
        for idx, page in enumerate(reader.pages):
            txt = page.extract_text() or ""
            if any(term in txt for term in search_terms):
                current_page = idx
                print(f"✅ 'खंड - 02' पेज नंबर {idx + 1} पर मिल गया!")
                break

    end_page = min(current_page + 1, total_pages)
    extracted_text = ""
    for p in range(current_page, end_page):
        t = reader.pages[p].extract_text()
        if t:
            extracted_text += f"\n--- PAGE {p+1} ---\n" + t

    next_page = end_page if end_page < total_pages else 0
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"last_page": next_page}, f)
    except Exception:
        pass

    return extracted_text[:1200], current_page + 1

def generate_clause_script(pdf_content, page_num):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY missing in GitHub Secrets!")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
        "Content-Type": "application/json"
    }

    target_model = "qwen/qwen3.8-27b"
    print(f"🚀 Using Groq model: {target_model}")

    prompt = f"""
    You are an expert postal exam teacher running 'Postal Wala' Instagram page.
    Explain the rule from this departmental section clearly (Page {page_num}).

    REQUIREMENTS:
    1. Spoken voiceover: Exactly 75-90 words in clear, easy Hindi. End strictly with: "आगे की तैयारी के लिए अभी फॉलो करें Postal Wala को!"
    2. Screen summary: 3 easy bullet points explaining the rule in Hindi.
    3. Quiz: 1 simple question with 4 options.

    PDF Content:
    {pdf_content}

    Format strictly matching these lines:
    TITLE: [Short Topic Name in Hindi]
    POINT1: [Key rule point 1]
    POINT2: [Key rule point 2]
    POINT3: [Key rule point 3]
    VOICEOVER: [Spoken text]
    QUESTION: [Exam Question in Hindi]
    OPT_A: [Option A text]
    OPT_B: [Option B text]
    OPT_C: [Option C text]
    OPT_D: [Option D text]
    CAPTION: [Instagram caption with #PostalWala #MTSExam #IndiaPost #Khand02]
    """

    payload = {
        "model": target_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": 400
    }
    
    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
    res_json = res.json()

    if res.status_code != 200 or "choices" not in res_json:
        raise RuntimeError(f"Groq API Error: {res_json}")

    raw_text = res_json["choices"][0]["message"]["content"].strip()
    
    data = {
        "rule_title": "डाकघर नियम",
        "point1": "रविवार और छुट्टियों पर सामान्य डाकघर बंद रहते हैं",
        "point2": "केवल रात्रि कालीन डाकघर खुले रहते हैं",
        "point3": "मशीन फ्रैंक किए गए पत्र केवल विशेष बॉक्स में डालें",
        "voiceover": "",
        "question": "रविवार को कौन से डाकघर खुले रहते हैं?",
        "opt_a": "A) प्रधान डाकघर",
        "opt_b": "B) रात्रि कालीन डाकघर",
        "opt_c": "C) उप डाकघर",
        "opt_d": "D) शाखा डाकघर",
        "caption": "डाक विभाग परीक्षा तैयारी #PostalWala #MTSExam"
    }
    
    for line in raw_text.splitlines():
        line_clean = line.strip()
        if line_clean.startswith("TITLE:"):
            data["rule_title"] = line_clean.replace("TITLE:", "").strip()
        elif line_clean.startswith("POINT1:"):
            data["point1"] = line_clean.replace("POINT1:", "").strip()
        elif line_clean.startswith("POINT2:"):
            data["point2"] = line_clean.replace("POINT2:", "").strip()
        elif line_clean.startswith("POINT3:"):
            data["point3"] = line_clean.replace("POINT3:", "").strip()
        elif line_clean.startswith("VOICEOVER:"):
            data["voiceover"] = line_clean.replace("VOICEOVER:", "").strip()
        elif line_clean.startswith("QUESTION:"):
            data["question"] = line_clean.replace("QUESTION:", "").strip()
        elif line_clean.startswith("OPT_A:"):
            data["opt_a"] = "A) " + line_clean.replace("OPT_A:", "").replace("A)", "").strip()
        elif line_clean.startswith("OPT_B:"):
            data["opt_b"] = "B) " + line_clean.replace("OPT_B:", "").replace("B)", "").strip()
        elif line_clean.startswith("OPT_C:"):
            data["opt_c"] = "C) " + line_clean.replace("OPT_C:", "").replace("C)", "").strip()
        elif line_clean.startswith("OPT_D:"):
            data["opt_d"] = "D) " + line_clean.replace("OPT_D:", "").replace("D)", "").strip()
        elif line_clean.startswith("CAPTION:"):
            data["caption"] = line_clean.replace("CAPTION:", "").strip()

    if not data["voiceover"]:
        data["voiceover"] = raw_text[:250]

    outro_line = " आगे की तैयारी और महत्वपूर्ण प्रश्नों के लिए अभी फॉलो करें Postal Wala को!"
    if "Postal Wala" not in data["voiceover"]:
        data["voiceover"] += outro_line

    return data

def generate_voice(text, filename="voice.mp3"):
    tts = gTTS(text=text, lang="hi", slow=False)
    tts.save(filename)

def get_audio_duration(audio_file):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_file]
    output = subprocess.check_output(cmd).decode().strip()
    return float(output)

def render_html_slides(script_data):
    hti = Html2Image(size=(1080, 1920))
    hti.browser.flags = ['--no-sandbox', '--disable-gpu']

    html1 = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@600;800&display=swap');
      * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Noto Sans Devanagari', sans-serif; }}
      body {{ width: 1080px; height: 1920px; background: #0B1120; padding: 80px 60px; color: white; }}
      .box {{ border: 6px solid #E11D48; border-radius: 45px; background: #131D31; padding: 60px; height: 100%; display: flex; flex-direction: column; justify-content: space-between; }}
      .brand {{ color: #F43F5E; font-size: 58px; font-weight: 800; }}
      .handle {{ color: #94A3B8; font-size: 36px; margin-top: 5px; }}
      .topic-card {{ background: #1E293B; border: 3px solid #38BDF8; border-radius: 30px; padding: 40px; margin-top: 40px; }}
      .tag {{ color: #38BDF8; font-size: 36px; font-weight: 800; }}
      .title {{ color: #FFFFFF; font-size: 52px; font-weight: 800; margin-top: 15px; line-height: 1.3; }}
      .content-card {{ background: #0F172A; border-radius: 35px; padding: 50px; margin-top: 40px; flex-grow: 1; }}
      .heading {{ color: #FBBF24; font-size: 46px; font-weight: 800; margin-bottom: 40px; }}
      .point {{ background: #1E293B; border-radius: 25px; padding: 35px; margin-bottom: 30px; border-left: 10px solid #38BDF8; }}
      .p-tag {{ color: #38BDF8; font-size: 34px; font-weight: 800; }}
      .p-text {{ color: #F8FAFC; font-size: 42px; font-weight: 600; margin-top: 10px; line-height: 1.4; }}
      .cta {{ background: #E11D48; border-radius: 30px; padding: 40px; text-align: center; font-size: 42px; font-weight: 800; margin-top: 40px; }}
    </style>
    </head>
    <body>
      <div class="box">
        <div>
          <div class="brand">POSTAL WALA</div>
          <div class="handle">@POSTAL_WALA</div>
          <div class="topic-card">
            <div class="tag">📌 आज का नियम:</div>
            <div class="title">{script_data['rule_title']}</div>
          </div>
          <div class="content-card">
            <div class="heading">💡 मुख्य बातें समझें:</div>
            <div class="point"><div class="p-tag">👉 नियम 1:</div><div class="p-text">{script_data['point1']}</div></div>
            <div class="point"><div class="p-tag">👉 नियम 2:</div><div class="p-text">{script_data['point2']}</div></div>
            <div class="point"><div class="p-tag">👉 नियम 3:</div><div class="p-text">{script_data['point3']}</div></div>
          </div>
        </div>
        <div class="cta">पूरी तैयारी के लिए फॉलो करें<br>👉 @POSTAL_WALA</div>
      </div>
    </body>
    </html>
    """

    html2 = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@600;800&display=swap');
      * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Noto Sans Devanagari', sans-serif; }}
      body {{ width: 1080px; height: 1920px; background: #0B1120; padding: 80px 60px; color: white; }}
      .box {{ border: 6px solid #E11D48; border-radius: 45px; background: #131D31; padding: 60px; height: 100%; display: flex; flex-direction: column; justify-content: space-between; }}
      .brand {{ color: #F43F5E; font-size: 58px; font-weight: 800; }}
      .handle {{ color: #94A3B8; font-size: 36px; margin-top: 5px; }}
      .topic-card {{ background: #1E293B; border: 3px solid #FBBF24; border-radius: 30px; padding: 40px; margin-top: 40px; }}
      .tag {{ color: #FBBF24; font-size: 36px; font-weight: 800; }}
      .title {{ color: #FFFFFF; font-size: 50px; font-weight: 800; margin-top: 15px; }}
      .content-card {{ background: #0F172A; border: 3px solid #38BDF8; border-radius: 35px; padding: 50px; margin-top: 40px; flex-grow: 1; }}
      .q-tag {{ color: #FBBF24; font-size: 44px; font-weight: 800; margin-bottom: 20px; }}
      .q-text {{ color: #F8FAFC; font-size: 46px; font-weight: 700; line-height: 1.4; margin-bottom: 50px; }}
      .opt {{ background: #1E293B; border: 2px solid #38BDF8; border-radius: 25px; padding: 30px 40px; font-size: 44px; font-weight: 600; margin-bottom: 25px; color: #FFFFFF; }}
      .comm {{ color: #F43F5E; font-size: 40px; font-weight: 800; text-align: center; margin-top: 20px; }}
      .cta {{ background: #E11D48; border-radius: 30px; padding: 40px; text-align: center; font-size: 42px; font-weight: 800; margin-top: 40px; }}
    </style>
    </head>
    <body>
      <div class="box">
        <div>
          <div class="brand">POSTAL WALA</div>
          <div class="handle">@POSTAL_WALA</div>
          <div class="topic-card">
            <div class="tag">🎯 परीक्षा क्विज़:</div>
            <div class="title">सवाल का जवाब कमेंट में दें!</div>
          </div>
          <div class="content-card">
            <div class="q-tag">सवाल:</div>
            <div class="q-text">{script_data['question']}</div>
            <div class="opt">{script_data['opt_a']}</div>
            <div class="opt">{script_data['opt_b']}</div>
            <div class="opt">{script_data['opt_c']}</div>
            <div class="opt">{script_data['opt_d']}</div>
            <div class="comm">अपना उत्तर कमेंट बॉक्स में लिखें 👇</div>
          </div>
        </div>
        <div class="cta">पूरी तैयारी के लिए फॉलो करें<br>👉 @POSTAL_WALA</div>
      </div>
    </body>
    </html>
    """

    hti.screenshot(html_str=html1, save_as='slide1.png')
    hti.screenshot(html_str=html2, save_as='slide2.png')
    print("✅ Hindi HTML slides generated without any boxes.")

def create_video_ffmpeg(script_data, audio_file="voice.mp3", output_video="final_reel.mp4"):
    render_html_slides(script_data)
    total_dur = get_audio_duration(audio_file)
    split_time = max(5.0, total_dur - 18.0)

    filter_complex = (
        f"[0:v]loop=loop=-1:size=1:start=0,trim=duration={split_time}[v0]; "
        f"[1:v]loop=loop=-1:size=1:start=0,trim=duration={total_dur - split_time}[v1]; "
        f"[v0][v1]concat=n=2:v=1:a=0,format=yuv420p[v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", "slide1.png",
        "-i", "slide2.png",
        "-i", audio_file,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "2:a",
        "-c:v", "libx264",
        "-profile:v", "main",
        "-level:v", "4.0",
        "-r", "30",
        "-g", "60",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-movflags", "+faststart",
        "-shortest", output_video
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print("✅ High quality 2-Slide Visual Reel Created.")

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
        raise RuntimeError(f"Session failed: {init_data}")

    print(f"✅ Container ID: {video_id}")
    print("📤 Uploading video bytes directly to Instagram...")

    with open(video_path, "rb") as f:
        video_data = f.read()

    headers = {
        "Authorization": f"OAuth {IG_ACCESS_TOKEN}",
        "Offset": "0",
        "Content-Length": str(file_size),
        "X-Entity-Length": str(file_size),
        "X-Entity-Name": "final_reel.mp4",
        "X-Entity-Type": "video/mp4"
    }

    s = requests.Session()
    req = requests.Request("POST", upload_url, data=video_data, headers=headers)
    prepped = s.prepare_request(req)

    if "Transfer-Encoding" in prepped.headers:
        del prepped.headers["Transfer-Encoding"]

    r_upload = s.send(prepped, timeout=180)

    if r_upload.status_code not in [200, 201]:
        raise RuntimeError(f"Direct byte upload failed ({r_upload.status_code}): {r_upload.text}")

    print("✅ Video uploaded directly to Instagram servers.")

    status_url = f"https://graph.facebook.com/v19.0/{video_id}?fields=status_code&access_token={IG_ACCESS_TOKEN}"

    for attempt in range(1, 35):
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
        print("⚠️ Polling timeout, trying to publish...")

    pub_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    pub_res = requests.post(pub_url, data={"creation_id": video_id, "access_token": IG_ACCESS_TOKEN})
    pub_json = pub_res.json()

    if "id" in pub_json:
        print(f"🎉 SUCCESS! Reel Live on Instagram! Post ID: {pub_json['id']}")
    else:
        raise RuntimeError(f"Publish Failed: {pub_json}")

if __name__ == "__main__":
    print("🚀 Postal Wala Automation Starting...")
    
    target_pdf = get_target_pdf()
    pdf_content, page_num = get_current_reading_window(target_pdf)
    print(f"✅ Read Page {page_num}.")

    script_data = generate_clause_script(pdf_content, page_num)
    print("✅ AI Script Ready.")

    generate_voice(script_data["voiceover"], "voice.mp3")
    print("✅ Voiceover Ready.")

    create_video_ffmpeg(script_data, "voice.mp3", "final_reel.mp4")

    upload_to_instagram_direct("final_reel.mp4", script_data.get("caption", ""))
