"""
3D kirdaar demo ka nateeja jodna (PIL/ffmpeg): demo_out/b3d_chars/
  bhaav_sheet.jpg  - 7 bhaav, Hindi naam ke saath (rang-birange)
  saamaan.jpg      - saara 3D saamaan
  motion_test.mp4  - chalti jhalak + rang-birange text
"""
import glob
import os
import subprocess
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rang_text as RT

SRC = os.environ.get("B3D_SRC", "b3d_out")
OUT = os.path.join("demo_out", "b3d_chars")
os.makedirs(OUT, exist_ok=True)
NAMES = ["खुश", "शाबाश!", "समझाना", "सोचना", "चौंकना", "उदास", "गुस्सा"]


def frames(mode):
    return sorted(glob.glob(os.path.join(SRC, mode, "*.png")))


fs = frames("sheet")
if fs:
    tiles = []
    for i, f in enumerate(fs):
        im = Image.open(f).convert("RGBA").resize((640, 360))
        RT.words_frame(im, NAMES[i % len(NAMES)], 5.0, 320, 40, 600, 50, 0.0, color_seed=i, max_lines=1)
        tiles.append(im)
    cols = 2
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (640 * cols, 360 * rows), (20, 24, 40))
    for i, t in enumerate(tiles):
        sheet.paste(t.convert("RGB"), ((i % cols) * 640, (i // cols) * 360))
    sheet.save(os.path.join(OUT, "bhaav_sheet.jpg"), quality=90)
    Image.open(fs[0]).save(os.path.join(OUT, "bhaav_khush_bada.png"))
    print("SHEET", len(fs))

fp = frames("props")
if fp:
    im = Image.open(fp[0]).convert("RGBA")
    RT.words_frame(im, "Postal Wala का 3D सामान", 5.0, 640, 70, 1200, 64, 0.0, color_seed=2, max_lines=1)
    im.convert("RGB").save(os.path.join(OUT, "saamaan.jpg"), quality=92)
    print("PROPS ok")

fm = frames("motion")
if fm:
    W, H = 1080, 1920
    out = os.path.join(OUT, "motion_test.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "24",
           "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    lines = [(0.0, 1.2, "GDS भाइयो, रुको!", 0), (1.25, 2.2, "विदेश की चिट्ठी पर पता कैसे?", 2),
             (2.2, 9.9, "रोमन अक्षर + अरबी अंक!", 1)]
    for i, f in enumerate(fm):
        t = i / 24
        cv = Image.open(f).convert("RGBA").resize((W, H), Image.LANCZOS)
        d = ImageDraw.Draw(cv)
        d.rectangle((0, 0, W, 130), fill=(8, 12, 30))
        cv.alpha_composite(RT.badge("100% परीक्षा वाला नियम", 40, (60, 220, 120), (0, 150, 70)), (24, 18))
        cv.alpha_composite(RT.badge("Clause 26 • Part 5", 40, (255, 210, 60), (255, 140, 0), (40, 20, 0)), (620, 18))
        for t0, t1, txt, seed in lines:
            if t0 <= t < t1:
                RT.words_frame(cv, txt, t, W / 2, 1560, 980, 104, 0.16, color_seed=seed, start=t0)
        p.stdin.write(cv.convert("RGB").tobytes())
    p.stdin.close()
    p.wait()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", out, "-vf", "fps=3,scale=216:384,tile=6x2", "-frames:v", "1",
                    os.path.join(OUT, "motion_contact.jpg")], check=False)
    print("MOTION", len(fm), "frames")
