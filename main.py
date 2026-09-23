import os
import re
import math
import random
import asyncio
import subprocess
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import edge_tts

# -------------------- CONFIGURATION --------------------
OUTPUT_DIR = "generated_reels"
OUTPUT_VIDEO = "final_postal_reel_v2.mp4"
TEMP_AUDIO = "temp_audio.mp3"

VOICE_NAME = "hi-IN-SwaraNeural"
VOICE_RATE = "+15%" # Tezi se bolne ke liye
FPS = 30
W, H = 1080, 1920

FONT_FILE = "Mukta-Bold.ttf"
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/mukta/Mukta-Bold.ttf"
FALLBACK_FONT = "arial.ttf"

# Premium Palette
BG_DARK = "#09101A"
CARD = "#112236"
WHITE = "#FFFFFF"
MUTED = "#64748B"
RED = "#EF4444"
GREEN = "#10B981"
YELLOW = "#FBBF24"
CYAN = "#06B6D4"

# -------------------- FONT & TTS RETRY LOGIC (Screenshot 5) --------------------
def get_font(size):
    if not os.path.exists(FONT_FILE):
        try:
            resp = requests.get(FONT_URL, timeout=10)
            Path(FONT_FILE).write_bytes(resp.content)
        except:
            return ImageFont.truetype(FALLBACK_FONT, int(size))
    try:
        return ImageFont.truetype(FONT_FILE, int(size), layout_engine=ImageFont.Layout.RAQM)
    except:
        return ImageFont.truetype(FONT_FILE, int(size))

async def generate_tts_with_retry(text, output_path, retries=3):
    for attempt in range(retries):
        try:
            if os.path.exists(output_path): os.remove(output_path)
            communicate = edge_tts.Communicate(text, VOICE_NAME, rate=VOICE_RATE)
            await communicate.save(output_path)
            
            # Silence removal & trimming via FFmpeg (Screenshot 2)
            trimmed_path = output_path.replace(".mp3", "_trimmed.mp3")
            subprocess.run([
                "ffmpeg", "-y", "-i", output_path, 
                "-af", "silenceremove=start_periods=1:start_threshold=-40dB:stop_periods=-1:stop_duration=0.1:stop_threshold=-40dB", 
                trimmed_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            os.replace(trimmed_path, output_path)
            return True
        except Exception as e:
            if attempt == retries - 1: print(f"TTS Failed: {e}")
            await asyncio.sleep(1)
    return False

# -------------------- VISUAL TEXTURES (Screenshot 2 & 4) --------------------
_texture_cache = None
def get_textured_bg():
    global _texture_cache
    if _texture_cache: return _texture_cache.copy()
    
    im = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(im)
    
    # 1. Gradient
    for y in range(H):
        ratio = y / H
        r = int(17 * (1 - ratio) + 9)
        g = int(34 * (1 - ratio) + 16)
        b = int(54 * (1 - ratio) + 26)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
        
    # 2. Vignette (Dark Edges)
    vig = Image.new("RGBA", (W, H), (0,0,0,0))
    vig_d = ImageDraw.Draw(vig)
    vig_d.ellipse((-400, -200, W+400, H+200), fill=(0,0,0,0), outline=(0,0,0,180), width=300)
    vig = vig.filter(ImageFilter.GaussianBlur(100))
    im.paste(vig, (0,0), vig)
    
    # 3. Grain Effect (Lightweight)
    grain = Image.new("RGBA", (W, H), (0,0,0,0))
    pixels = grain.load()
    for _ in range(30000): # Sparse grain
        x, y = random.randint(0, W-1), random.randint(0, H-1)
        pixels[x, y] = (255, 255, 255, 15)
    im.paste(grain, (0,0), grain)
    
    _texture_cache = im
    return im.copy()

# -------------------- UI ELEMENTS: BADGES & CHIPS (Screenshot 5) --------------------
def draw_badge(draw, text, cx, cy, size, bg_color, text_color):
    font = get_font(size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    
    pad_x, pad_y = 30, 15
    draw.rounded_rectangle((cx - tw/2 - pad_x, cy - th/2 - pad_y, cx + tw/2 + pad_x, cy + th/2 + pad_y), radius=15, fill=bg_color)
    draw.text((cx, cy - 5), text, font=font, fill=text_color, anchor="mm")

# -------------------- WORD-BY-WORD HIGHLIGHT (Screenshot 4) --------------------
def draw_word_by_word(draw, text, y_start, font_size, max_w, t, words_per_sec=3.5, active_color=CYAN, inactive_color=MUTED):
    font = get_font(font_size)
    words = text.split()
    revealed_count = int(t * words_per_sec)
    
    x, y = W/2, y_start
    lines = []
    current_line = []
    
    # Pre-calculate word wrapping
    for w in words:
        test_line = " ".join([wd[0] for wd in current_line] + [w])
        if draw.textlength(test_line, font=font) <= max_w:
            current_line.append((w, len(lines)*100 + len(current_line))) # word, global index
        else:
            lines.append(current_line)
            current_line = [(w, len(lines)*100)] # Approximated index logic
    if current_line: lines.append(current_line)
    
    # Draw words
    global_idx = 0
    for line in lines:
        line_w = sum(draw.textlength(wd[0] + " ", font=font) for wd in line)
        cx = W/2 - line_w/2
        for wd, _ in line:
            color = active_color if global_idx <= revealed_count else inactive_color
            draw.text((cx, y), wd, font=font, fill=color, anchor="lm")
            cx += draw.textlength(wd + " ", font=font)
            global_idx += 1
        y += font_size * 1.5

# -------------------- ANIMATION MATH --------------------
def ease_out_elastic(x):
    c4 = (2 * math.pi) / 3
    return 1 if x == 1 else math.pow(2, -10 * x) * math.sin((x * 10 - 0.75) * c4) + 1

# -------------------- SCENES WITH CAMERA MOTION --------------------
def scene_hook(data, t, dur):
    im = get_textured_bg()
    d = ImageDraw.Draw(im)
    
    # Camera motion (slow zoom in)
    camera_scale = 1.0 + (t / dur) * 0.08 
    
    cy = H//2 - 100
    w_box, h_box = 940 * camera_scale, 600 * camera_scale
    box = (W/2 - w_box/2, cy - h_box/2, W/2 + w_box/2, cy + h_box/2)
    
    # Shadow and Perforation (Stamp Theme)
    d.rounded_rectangle((box[0]+10, box[1]+20, box[2]+10, box[3]+20), 30, fill=(0,0,0,100))
    d.rounded_rectangle(box, 30, fill=CARD, outline=CYAN, width=4)
    for x in range(int(box[0]) + 50, int(box[2]) - 50, 40):
        d.ellipse((x-10, box[1]-10, x+10, box[1]+10), fill=BG_DARK) # Perforation

    # Badges / Chips
    draw_badge(d, "EXAM ALERT", W/2, cy - 200*camera_scale, 40, RED, WHITE)
    
    # Hook Text
    font = get_font(60 * camera_scale)
    wrapped = "\n".join(data["hook"].split(" में ")) # Manual split for impact
    d.text((W/2, cy + 20*camera_scale), wrapped, font=font, fill=WHITE, anchor="mm", align="center", spacing=20)
    
    return im

def scene_rule_highlight(data, t, dur):
    im = get_textured_bg()
    d = ImageDraw.Draw(im)
    
    camera_y = math.sin(t) * 10 # Slight float effect
    
    draw_badge(d, "VERIFIED RULE", W/2, 300 + camera_y, 45, CYAN, BG_DARK)
    
    # Word-by-word reveal (Screenshot 4)
    draw_word_by_word(d, data["fact"], 450 + camera_y, 55, 900, t, words_per_sec=4, active_color=GREEN, inactive_color=MUTED)
    
    # Trick Badge (Chips Layout)
    if t > 2.0:
        anim_t = min(1.0, (t - 2.0) * 2)
        scale = ease_out_elastic(anim_t)
        trick_y = 1000 + camera_y
        
        draw_badge(d, "TRICK", W/2, trick_y, int(40*scale), YELLOW, BG_DARK)
        
        trick_font = get_font(50 * scale)
        d.text((W/2, trick_y + 100), data["trick"], font=trick_font, fill=WHITE, anchor="mm")

    return im

def scene_cta_teaser(data, t, dur):
    im = get_textured_bg()
    d = ImageDraw.Draw(im)
    
    scale = min(1.0, t * 3)
    cy = H//2
    
    draw_badge(d, "SAVE FOR EXAM", W/2, cy - 200, int(45*scale), GREEN, WHITE)
    d.text((W/2, cy - 50), "@POSTAL_WALA", font=get_font(int(70*scale)), fill=CYAN, anchor="mm")
    
    # Next part teaser (Screenshot 2)
    if t > 1.5:
        d.rounded_rectangle((100, cy + 150, 980, cy + 300), 30, fill=CARD, outline=YELLOW, width=3)
        draw_badge(d, "UPCOMING", 250, cy + 150, 30, YELLOW, BG_DARK)
        d.text((W/2, cy + 230), "Clause 5: कामकाज के घंटे", font=get_font(50), fill=WHITE, anchor="mm")

    return im

# -------------------- MAIN PIPELINE --------------------
def build_video():
    # Simplified data for architecture demonstration
    data = {
        "hook": "क्या आपको पता है\nमोबाइल डाकघर में कौन सा काम मना है?",
        "fact": "मोबाइल डाकघर में मनीऑर्डर बचत बैंक और बीमा कार्य पूरी तरह प्रतिबंधित होते हैं।",
        "trick": "नो मनी, नो बैंक!"
    }
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("🎙️ Generating Edge-TTS Audio (with retry & cleanup)...")
    full_script = f"{data['hook']} नियम याद रखें। {data['fact']} इसकी ट्रिक है {data['trick']}। इसे सेव करें और अगला क्लॉज़ देखें।"
    audio_path = os.path.join(OUTPUT_DIR, "final_voice.mp3")
    asyncio.run(generate_tts_with_retry(full_script, audio_path))
    
    # Estimate duration based on TTS (dummy fallback if ffmpeg probe fails)
    try:
        dur_raw = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path])
        total_audio_dur = float(dur_raw)
    except:
        total_audio_dur = 15.0 # fallback

    print(f"⏱️ Audio Duration: {total_audio_dur:.2f}s. Allocating scenes...")
    
    # Distribute time: Hook(30%), Rule(45%), CTA(25%)
    dur_hook = total_audio_dur * 0.3
    dur_rule = total_audio_dur * 0.45
    dur_cta = total_audio_dur * 0.25
    
    scenes = [(scene_hook, dur_hook), (scene_rule_highlight, dur_rule), (scene_cta_teaser, dur_cta)]
    all_frames = []
    
    print("🎨 Rendering Frames (Grain, Camera Motion, Badges)...")
    for i, (func, dur) in enumerate(scenes):
        frames_count = int(dur * FPS)
        for f in range(frames_count):
            img = func(data, f/FPS, dur)
            p = os.path.join(OUTPUT_DIR, f"s{i}_{f:04d}.jpg")
            img.save(p, quality=85)
            all_frames.append(p)
            
    print("🎬 Muxing Video & Audio (FFmpeg)...")
    list_path = os.path.join(OUTPUT_DIR, "list.txt")
    with open(list_path, "w") as f:
        for fr in all_frames: f.write(f"file '{os.path.abspath(fr)}'\n")
        
    final_video = os.path.join(OUTPUT_DIR, OUTPUT_VIDEO)
    subprocess.run([
        "ffmpeg", "-y", "-r", str(FPS), "-f", "concat", "-safe", "0", 
        "-i", list_path, "-i", audio_path, 
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", 
        "-c:a", "copy", "-pix_fmt", "yuv420p", "-shortest", final_video
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Cleanup
    for fr in all_frames: os.remove(fr)
    os.remove(list_path)
    print(f"✅ Video successfully created at {final_video}")

if __name__ == "__main__":
    build_video()
