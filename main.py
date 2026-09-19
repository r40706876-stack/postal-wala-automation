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

# --- Viral Hook Catalog ---
VIRAL_HOOKS = [
    {
        "voice": "लिख कर ले लो! इस 40 सेकंड की रील से विभागीय परीक्षा में आपके दो नंबर पक्के होने वाले हैं!",
        "visual_badge": "लिख कर ले लो! 2 नंबर पक्के"
    },
    {
        "voice": "जीडीएस से एमटीएस और पोस्टमैन परीक्षा में नब्बे प्रतिशत लोग इस एक नियम में गलत उत्तर देकर आते हैं!",
        "visual_badge": "सावधान: 90% लोग फेल होते हैं!"
    },
    {
        "voice": "अगर आप सच में इस बार जीडीएस से प्रमोशन लेने की तैयारी कर रहे हैं, तो इस सवाल का सही जवाब दीजिए!",
        "visual_badge": "दम है तो सही उत्तर दो!"
    },
    {
        "voice": "डाक विभाग की परीक्षाओं में बार-बार दोहराया जाने वाला सबसे पसंदीदा नियम! आज इसे हमेशा के लिए रट लो!",
        "visual_badge": "बार-बार पूछा जाने वाला नियम"
    },
    {
        "voice": "अगर इस साल प्रमोशन पाकर पोस्टमैन या पी.ए. बनना है, तो इस रील को एक सेकंड भी स्किप मत करना!",
        "visual_badge": "प्रमोशन का पक्का मौका!"
    }
]

# --- Master PO Guide Part 1 Catalog ---
POSTAL_CLAUSE_CATALOG = {
    6: {
        "name": "रविवार और डाक अवकाश पर कार्य",
        "total_parts": 1,
        "part_1_focus": "रविवार और सोलह राजपत्रित अवकाशों पर सामान्य डाकघर पूर्णतः बंद रहते हैं, केवल रात्रि डाकघर सीमित सेवाएं देते हैं।"
    },
    7: {
        "name": "डाक टिकटों और लेखन-सामग्री का विक्रय",
        "total_parts": 2,
        "part_1_focus": "प्रत्येक डाकघर में कार्य के घंटों के दौरान जनता के लिए डाक टिकट और स्टेशनरी की उपलब्धता सुनिश्चित करना अनिवार्य है।",
        "part_2_focus": "डाक टिकट काउंटर पर फटे-पुराने नोट न देने और सही मुद्रा में भुगतान करने के विभागीय नियम हैं।"
    },
    8: {
        "name": "फिलाटेलिक ब्यूरो और डाक टिकट संग्रह",
        "total_parts": 1,
        "part_1_focus": "स्मारक डाक टिकटों की बिक्री, फिलाटेलिक डिपॉजिट अकाउंट खोलने और टिकट संग्राहकों के लिए विशेष सुविधाएं होती हैं।"
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
    }
}

def sanitize_devanagari(text):
    if not text:
        return ""
    # Emojis aur unsupported symbols ko filter out karta hai
    clean = re.sub(r'[^\u0900-\u097F\u0020-\u007E\u2010-\u2015\u0964\u0965\n]', '', text)
    return clean.strip()

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

# --- State Management (Clause 6 onwards) ---
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
        state["clause_no"] = clause + 1
        state["current_part"] = 1

    save_progress_state(state)

# --- 100% Mirror Audio-Text Segments ---
def get_script_segments(state):
    clause = state.get("clause_no", 6)
    part = state.get("current_part", 1)
    hook = VIRAL_HOOKS[state.get("hook_index", 0) % len(VIRAL_HOOKS)]
    
    info = POSTAL_CLAUSE_CATALOG.get(clause, POSTAL_CLAUSE_CATALOG[6])
    name = info["name"]
    focus = info.get(f"part_{part}_focus", info.get("part_1_focus", ""))

    hook_voice = hook["voice"]
    hook_badge = hook["visual_badge"]

    # Segment 1: Hook aur Rule ka perfect dual audio-visual sync
    seg1_audio = f"{hook_voice} डाक घर गाइड भाग 1 क्लॉज {clause} के अनुसार {focus}"
    seg1_rule_text = f"डाक घर गाइड भाग 1 : क्लॉज {clause}\n{focus}"

    # Segment 2
    seg2_audio = "रविवार और सभी सोलह राजपत्रित अवकाशों पर सामान्य डाकघर पूरी तरह बंद रहते हैं, जिससे नियमित सेवाएं स्थगित रहती हैं।"
    seg2_screen = "रविवार और सभी 16 राजपत्रित अवकाशों पर सामान्य डाकघर पूरी तरह बंद रहते हैं, जिससे नियमित सेवाएं स्थगित रहती हैं।"

    # Segment 3
    seg3_audio = "केवल रात्रि डाकघर ही ऐसे अवकाशों पर सीमित सेवाएं प्रदान करते हैं। विभागीय परीक्षा हेतु यह अति महत्वपूर्ण नियम है।"
    seg3_screen = "केवल रात्रि डाकघर ही ऐसे अवकाशों पर सीमित सेवाएं प्रदान करते हैं। विभागीय परीक्षा हेतु यह अति महत्वपूर्ण नियम है।"

    # Segment 4 (Quiz)
    q_txt = f"क्लॉज {clause} के अनुसार रविवार व राष्ट्रीय अवकाश पर सामान्य डाकघर की क्या स्थिति होती है?"
    quiz_voice = f"आज का सवाल: {q_txt} सही उत्तर कमेंट में बताएं! फ्री मॉक टेस्ट के लिए स्क्रीन पर दिए नंबर पर व्हाट्सएप करें!"

    return {
        "clause_no": clause,
        "clause_name": name,
        "part_no": part,
        "total_parts": info["total_parts"],
        "caption": f"डाक घर गाइड भाग 1 क्लॉज {clause} | विभागीय परीक्षा (GDS to MTS, Postman, PA) विशेष तैयारी। #PostalWala #GDStoMTS #PostmanExam #IndiaPost #POGuidePart1",
        "segments": [
            {
                "audio": seg1_audio, 
                "screen": seg1_rule_text, 
                "hook_badge": hook_badge, 
                "label": "परीक्षा बिंदु 1",
                "is_hook": True
            },
            {
                "audio": seg2_audio, 
                "screen": seg2_screen, 
                "label": "परीक्षा बिंदु 2",
                "is_hook": False
            },
            {
                "audio": seg3_audio, 
                "screen": seg3_screen, 
                "label": "परीक्षा बिंदु 3",
                "is_hook": False
            },
            {
                "audio": quiz_voice,
                "question": q_txt,
                "opt_a": "पूर्णतः खुले रहते हैं",
                "opt_b": "पूर्णतः बंद रहते हैं",
                "opt_c": "केवल बचत बैंक कार्य होता है",
                "opt_d": "इनमें से कोई नहीं",
                "label": "परीक्षा क्विज़"
            }
        ]
    }

async def generate_segment_audio(text, outfile):
    if os.path.exists(outfile):
        try: os.remove(outfile)
        except Exception: pass
    communicate = edge_tts.Communicate(text=text, voice=VOICE_NAME, rate="+0%")
    await communicate.save(outfile)

def get_audio_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    return float(subprocess.check_output(cmd).decode().strip())

# --- Perfect Sync Video Rendering Engine ---
def render_and_sync_video(script_data, output_video):
    ensure_fonts()
    ensure_auto_icons()
    state = load_progress_state()
    active_bgm = ensure_bgm(BGM_OUTPUT, state.get("hook_index", 0))

    font_brand = get_eng_font(44)
    font_sub = get_eng_font(22)
    font_trust = get_eng_font(20)
    font_badge = get_dev_font(22)
    font_title = get_dev_font(34)
    font_h2 = get_dev_font(32)
    font_body = get_dev_font(36)
    font_label = get_dev_font(26)
    font_wa_hin = get_dev_font(30)
    font_wa_num = get_eng_font(30)
    font_cta = get_eng_font(30)
    font_cta_dev = get_dev_font(30)
    font_opt = get_dev_font(32)
    font_hook_alert = get_dev_font(30)

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

    for idx, seg in enumerate(script_data["segments"]):
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
                # Top Hook Card
                d.rounded_rectangle([110, sy, 970, sy + 70], radius=14, fill="#991B1B", outline="#FBBF24", width=2)
                d.text((130, sy + 15), sanitize_devanagari(seg["hook_badge"]), fill="#FEF08A", font=font_hook_alert)
                sy += 90

            d.rounded_rectangle([110, sy, 460, sy + 50], radius=10, fill="#0B132B")
            d.text((125, sy + 10), seg["label"], fill="#38BDF8", font=font_label)

            clean_content = sanitize_devanagari(seg["screen"])
            wrapped = textwrap.fill(clean_content, width=23)
            d.multiline_text((115, sy + 75), wrapped, fill="#F8FAFC", font=font_body, spacing=16)

            asset_path = BOOK_3D_PATH if idx == 0 else POSTBOX_3D_PATH
            if os.path.exists(asset_path):
                ic = Image.open(asset_path).convert("RGBA").resize((280, 360), RESAMPLE_MODE)
                img.paste(ic, (400, 1120), ic)
        else:
            # Slide 4: Quiz
            d.rounded_rectangle([110, 530, 330, 575], radius=12, fill="#0B132B")
            d.text((120, 538), "आज का सवाल:", fill="#FBBF24", font=font_h2)

            q_wrapped = textwrap.fill(sanitize_devanagari(seg["question"]), width=23)
            d.multiline_text((110, 595), q_wrapped, fill="#F8FAFC", font=font_h2, spacing=10)

            opts = [seg["opt_a"], seg["opt_b"], seg["opt_c"], seg["opt_d"]]
            oy = 740
            for o_idx, opt in enumerate(opts):
                d.rounded_rectangle([110, oy, 970, oy + 95], radius=16, fill="#0B132B", outline="#38BDF8", width=2)
                d.text((135, oy + 25), f"{chr(65+o_idx)})", fill="#38BDF8", font=font_h2)
                d.text((205, oy + 25), sanitize_devanagari(opt), fill="#FFFFFF", font=font_opt)
                oy += 115

            d.rounded_rectangle([110, 1370, 970, 1490], radius=18, fill="#0B132B", outline="#F59E0B", width=2)
            d.text((220, 1410), "अपना सही जवाब अभी कमेंट करें!", fill="#FDE047", font=font_h2)

        slide_img = f"slide_seg_{idx}.png"
        img.save(slide_img)

        # Millisecond-accurate segment generation
        part_vid = f"part_{idx}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", slide_img,
            "-i", audio_seg_file,
            "-c:v", "libx264", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-fflags", "+shortest",
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

    # Balanced Background Music Integration
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

    print(f"✅ Final Audited Video Successfully Created: {output_video}")

# --- Instagram Upload ---
def post_reel_to_instagram_multipart(video_file, caption):
    if not IG_ACCESS_TOKEN or not IG_USER_ID:
        print("⚠️ IG credentials missing, skipping upload.")
        return

    init_url = GRAPH_API_BASE + str(IG_USER_ID).strip() + "/media"
    data = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN
    }
    r = requests.post(init_url, data=data, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Init failed: {r.text}")

    video_id = r.json().get("id")
    upload_url = r.json().get("uri") or (RUPLOAD_BASE + str(video_id).strip())

    file_size = os.path.getsize(video_file)
    headers = {
        "Authorization": f"OAuth {IG_ACCESS_TOKEN}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "application/octet-stream"
    }

    with open(video_file, "rb") as vf:
        requests.post(upload_url, headers=headers, data=vf.read(), timeout=600)

    status_url = GRAPH_API_BASE + str(video_id).strip()
    for _ in range(30):
        time.sleep(10)
        res = requests.get(status_url, params={"fields": "status_code", "access_token": IG_ACCESS_TOKEN}).json()
        if res.get("status_code") == "FINISHED":
            break

    pub_url = GRAPH_API_BASE + str(IG_USER_ID).strip() + "/media_publish"
    pub_res = requests.post(pub_url, data={"creation_id": video_id, "access_token": IG_ACCESS_TOKEN}).json()
    if "id" in pub_res:
        print(f"🎉 Reel published successfully! ID: {pub_res['id']}")

if __name__ == "__main__":
    st = load_progress_state()
    data = get_script_segments(st)
    render_and_sync_video(data, OUTPUT_VIDEO)
    post_reel_to_instagram_multipart(OUTPUT_VIDEO, data.get("caption", ""))
    advance_progress_state(st)
