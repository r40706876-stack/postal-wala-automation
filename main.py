import os
import asyncio
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
import edge_tts

# ==========================================
# 1. REEL CONFIGURATION & DATA
# ==========================================
WIDTH, HEIGHT = 1080, 1920
FPS = 30

# Colors
BG_COLOR = (11, 19, 37)          
CARD_BG = (18, 30, 56)           
CARD_BORDER = (40, 60, 100)      
TEXT_WHITE = (255, 255, 255)
ACCENT_RED = (220, 38, 38)       
ACCENT_GREEN = (34, 197, 94)     
ACCENT_YELLOW = (250, 204, 21)   
ACCENT_BLUE = (37, 99, 235)      
MUTED_TEXT = (148, 163, 184)

DATA = {
    "clause": "PO Guide Part 1 : Clause 2",
    "part": "भाग 3/3",
    "hook": "लिख कर ले लो! 2 नंबर पक्के",
    "question": "पार्सल को वितरण क्षेत्र से बाहर\nपुनः प्रेषित (Redirect) करने पर\nकितना डाक प्रभार लिया जाता है?",
    "options": [
        ("A", "आधा डाक प्रभार (50%)"),
        ("B", "पूर्ण डाक शुल्क (100%)"),
        ("C", "पूर्णतः निःशुल्क (Free)"),
        ("D", "दोगुना दंड प्रभार")
    ],
    "correct_option": "A",
    "correct_text": "आधा डाक प्रभार (50%)",
    "rule_line": "नियम: वितरण क्षेत्र से बाहर भेजने पर\nआधा डाक प्रभार (Half Forwarding Fee) देय होता है।"
}

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def draw_rounded_card(draw, box, radius, fill, outline=None, width=2):
    x1, y1, x2, y2 = box
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill, outline=outline, width=width)

def get_font(size):
    try:
        return ImageFont.truetype("Nirmala.ttf", size)
    except:
        return ImageFont.load_default()

def create_base_canvas():
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    font_bold = get_font(38)
    font_small = get_font(28)

    draw.text((60, 80), "POSTAL WALA", font=font_bold, fill=TEXT_WHITE)
    draw.text((60, 130), "@POSTAL_WALA", font=font_small, fill=MUTED_TEXT)

    draw_rounded_card(draw, (700, 85, 1020, 150), 12, fill=(6, 78, 59), outline=(16, 185, 129), width=2)
    draw.text((725, 100), "OFFICIAL SYLLABUS", font=get_font(24), fill=(110, 231, 183))

    draw_rounded_card(draw, (60, 200, 780, 260), 12, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw.text((85, 215), DATA["clause"], font=get_font(26), fill=ACCENT_YELLOW)

    draw_rounded_card(draw, (810, 200, 1020, 260), 12, fill=ACCENT_BLUE)
    draw.text((865, 215), DATA["part"], font=get_font(26), fill=TEXT_WHITE)

    draw_rounded_card(draw, (60, 1780, 1020, 1870), 20, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw.text((90, 1810), "GDS to MTS • Postman • Mail Guard • P.A.", font=get_font(30), fill=ACCENT_YELLOW)
    
    return img, draw

# ==========================================
# 3. SCENE GENERATORS
# ==========================================
def create_scene_1():
    img, draw = create_base_canvas()
    draw_rounded_card(draw, (60, 310, 1020, 430), 20, fill=ACCENT_RED)
    draw.text((100, 345), DATA["hook"], font=get_font(52), fill=TEXT_WHITE)

    draw_rounded_card(draw, (60, 480, 1020, 1100), 24, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw.text((100, 520), "विभागीय परीक्षा प्रश्न:", font=get_font(32), fill=ACCENT_YELLOW)
    draw.text((100, 620), DATA["question"], font=get_font(48), fill=TEXT_WHITE, spacing=25)

    draw_rounded_card(draw, (440, 1180, 640, 1380), 30, fill=(234, 88, 12))
    draw.text((515, 1220), "?", font=get_font(120), fill=TEXT_WHITE)
    draw.text((320, 1440), "अगली स्लाइड में 4 विकल्प देखें...", font=get_font(32), fill=MUTED_TEXT)
    return img

def create_scene_2(timer_val=3):
    img, draw = create_base_canvas()
    draw_rounded_card(draw, (60, 290, 1020, 500), 20, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw.text((90, 315), "प्रश्न: पार्सल Redirect करने पर डाक प्रभार?", font=get_font(38), fill=ACCENT_YELLOW)

    y_pos = 540
    for key, text in DATA["options"]:
        draw_rounded_card(draw, (60, y_pos, 1020, y_pos + 120), 18, fill=CARD_BG, outline=CARD_BORDER, width=2)
        draw_rounded_card(draw, (80, y_pos + 15, 170, y_pos + 105), 14, fill=ACCENT_BLUE)
        draw.text((105, y_pos + 32), key, font=get_font(42), fill=TEXT_WHITE)
        draw.text((210, y_pos + 36), text, font=get_font(38), fill=TEXT_WHITE)
        y_pos += 150

    draw_rounded_card(draw, (60, 1200, 1020, 1310), 20, fill=(180, 83, 9))
    draw.text((120, 1235), f"{timer_val} सेकंड में अपना उत्तर कमेंट करें (A, B, C, D)!", font=get_font(36), fill=TEXT_WHITE)
    draw.text((240, 1370), "⚡ 90% परीक्षार्थी यहाँ गलती करते हैं!", font=get_font(34), fill=ACCENT_RED)
    return img

def create_scene_3():
    img, draw = create_base_canvas()
    draw_rounded_card(draw, (60, 290, 1020, 470), 24, fill=(5, 46, 22), outline=ACCENT_GREEN, width=3)
    draw_rounded_card(draw, (90, 330, 190, 430), 16, fill=ACCENT_GREEN)
    draw.text((120, 345), "✓", font=get_font(56), fill=TEXT_WHITE)
    draw.text((220, 330), f"सही उत्तर: विकल्प {DATA['correct_option']}", font=get_font(34), fill=ACCENT_GREEN)
    draw.text((220, 385), DATA["correct_text"], font=get_font(42), fill=TEXT_WHITE)

    draw_rounded_card(draw, (60, 520, 1020, 860), 20, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw.text((100, 560), "डाक घर गाइड का आधिकारिक नियम:", font=get_font(34), fill=ACCENT_YELLOW)
    draw.text((100, 640), DATA["rule_line"], font=get_font(36), fill=TEXT_WHITE, spacing=20)

    draw_rounded_card(draw, (60, 920, 1020, 1220), 20, fill=(69, 10, 10), outline=ACCENT_RED, width=2)
    draw.text((100, 960), "सावधान! परीक्षा का सबसे बड़ा Trap:", font=get_font(34), fill=ACCENT_RED)
    trap_text = "यदि पार्सल को पतेदार द्वारा एक बार खोल दिया गया हो,\nतो नए डाक शुल्क के बिना पुनः प्रेषण नहीं होगा!"
    draw.text((100, 1040), trap_text, font=get_font(34), fill=TEXT_WHITE, spacing=15)
    return img

def create_scene_4():
    img, draw = create_base_canvas()
    draw_rounded_card(draw, (60, 500, 1020, 900), 24, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw.text((120, 580), "क्या आपका जवाब सही था?", font=get_font(48), fill=TEXT_WHITE)
    draw.text((120, 680), "कमेंट बॉक्स में 'YES' या 'NO' लिखें!", font=get_font(40), fill=ACCENT_YELLOW)

    draw_rounded_card(draw, (60, 960, 1020, 1100), 20, fill=ACCENT_RED)
    draw.text((180, 1005), "अगले भाग के लिए अभी फॉलो करें!", font=get_font(42), fill=TEXT_WHITE)
    return img

# ==========================================
# 4. AUDIO & VIDEO ASSEMBLY
# ==========================================
async def generate_voiceover():
    text = (
        "लिख कर ले लो! 2 नंबर पक्के। पार्सल को वितरण क्षेत्र से बाहर रीडायरेक्ट करने पर कितना डाक प्रभार लिया जाता है? "
        "तीन सेकंड में जवाब कमेंट करें। "
        "सही उत्तर है विकल्प ए, आधा डाक प्रभार। ध्यान रखें, खुला हुआ पार्सल नए शुल्क के बिना पुनः प्रेषित नहीं होगा।"
    )
    tts = edge_tts.Communicate(text, voice="hi-IN-MadhurNeural", rate="+15%")
    await tts.save("voiceover.mp3")

def build_final_video():
    asyncio.run(generate_voiceover())

    os.makedirs("temp_frames", exist_ok=True)
    create_scene_1().save("temp_frames/s1.png")
    create_scene_2(timer_val=3).save("temp_frames/s2_3.png")
    create_scene_2(timer_val=2).save("temp_frames/s2_2.png")
    create_scene_2(timer_val=1).save("temp_frames/s2_1.png")
    create_scene_3().save("temp_frames/s3.png")
    create_scene_4().save("temp_frames/s4.png")

    c1 = ImageClip("temp_frames/s1.png").set_duration(4.5)
    c2_3 = ImageClip("temp_frames/s2_3.png").set_duration(1.5)
    c2_2 = ImageClip("temp_frames/s2_2.png").set_duration(1.5)
    c2_1 = ImageClip("temp_frames/s2_1.png").set_duration(1.5)
    c3 = ImageClip("temp_frames/s3.png").set_duration(6.5)
    c4 = ImageClip("temp_frames/s4.png").set_duration(2.5)

    base_video = concatenate_videoclips([c1, c2_3, c2_2, c2_1, c3, c4])
    
    audio = AudioFileClip("voiceover.mp3")
    final_video = base_video.set_audio(audio)
    
    print("🎬 Rendering Final Optimized Reel...")
    final_video.write_videofile(
        "postal_viral_reel.mp4", 
        fps=FPS, 
        codec="libx264", 
        audio_codec="aac",
        preset="fast"
    )
    print("✅ Video ready: postal_viral_reel.mp4")

if __name__ == "__main__":
    build_final_video()
