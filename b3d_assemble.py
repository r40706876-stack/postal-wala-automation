"""
POORI REEL BLENDER ME (demo v25) - JODNA. Har drishya ke Blender frames (b3d_job/frames_<i>/) + upar ki patti +
karaoke caption (Hindi, PIL - Blender me Hindi bigadti) + jashn (confetti) + awaaz (b3d_job/audio.wav).
Nateeja: demo_out/blender_full/blender_reel_clause26_part5.mp4 (+ contact sheet)
Kisi drishya ke frame na hon -> wahan saada parda + likhai (reel phir bhi banti hai, log me CHETAVNI).
"""
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["BHAROSA_V2"] = "1"
import main as M
import bharosa as B

B.init(M)
print("Font:", M.resolve_font())
N = B.N
W, H = 1080, 1920
JOB = os.environ.get("B3D_JOB", "b3d_job")
OUT_DIR = os.path.join("demo_out", "blender_full")
os.makedirs(OUT_DIR, exist_ok=True)
plan = json.load(open(os.path.join(JOB, "plan.json"), encoding="utf-8"))
FPS = plan.get("fps", 24)
scenes = plan["scenes"]
n_story = sum(1 for s in scenes if s["kind"] == "story")
PIECE = n_story + 1


def strip(cv, piece):
    d = ImageDraw.Draw(cv)
    d.rectangle((0, 0, W, 150), fill=(8, 12, 30))
    d.rounded_rectangle((30, 36, 520, 108), 36, fill=B.GRN)
    d.text((275, 72), "100% परीक्षा वाला नियम", font=B.F(38), fill="white", anchor="mm")
    d.rounded_rectangle((550, 36, 1050, 108), 36, fill=B.GOLD)
    d.text((800, 72), f"चित्रों से आसान • {piece}", font=B.F(36), fill=B.NAVY, anchor="mm")


out = os.environ.get("B3D_OUT_MP4") or os.path.join(OUT_DIR, f"blender_reel_clause{plan['clause']}_part{plan['part']}.mp4")
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
audio = os.path.join(JOB, "audio.wav")
cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
       "-i", "-", "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium",
       "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", out]
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
missing = []
import rang_text as RT


def card_img(rel, w):
    im = Image.open(os.path.join(JOB, rel)).convert("RGBA")
    return im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)


def put_pop(cv, im, cx, cy, t, t0):
    k = RT.ease_back((t - t0) / 0.3)
    if k <= 0.02:
        return
    im2 = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.BICUBIC)
    cv.alpha_composite(im2, (int(cx - im2.width / 2), int(cy - im2.height / 2)))


for i, sc in enumerate(scenes):
    fd = os.path.join(JOB, f"frames_{i}")
    have = {}
    if os.path.isdir(fd):
        for f in os.listdir(fd):
            if f.endswith(".png") and f[2:6].isdigit():
                have[int(f[2:6])] = os.path.join(fd, f)
    if not have:
        missing.append(sc["name"])
    n = int(sc["frames"])
    kind = sc["kind"]
    words = len(sc["text"].split())
    rate = max(0.08, sc["vd"] / max(1, words) * 0.9)
    cards = None
    if kind == "end":
        cards = [(card_img(sc["notes"], 920), 430, 0.05), (card_img(sc["share"], 880), 760, 0.45),
                 (card_img(sc["mock"], 840), 975, 0.9), (card_img(sc["follow"], 600), 1145, 1.3)]
    last = None
    for f_i in range(n):
        t = f_i / FPS
        fn = have.get(f_i + 1)
        if fn is None and have:                               # tukda chhoota -> paas wala frame
            fn = have[min(have, key=lambda k: abs(k - (f_i + 1)))]
        if fn:
            cv = Image.open(fn).convert("RGB").resize((W, H), Image.LANCZOS).convert("RGBA")
        else:
            cv = B.bg().copy()
        piece = {"ruko": "सवाल", "galti": "गलती", "ans": f"टुकड़ा {PIECE}/{PIECE}", "guide": "सबूत",
                 "end": "याद"}.get(kind, f"टुकड़ा {int(sc.get('idx', 0)) + 1}/{PIECE}")
        cy = {"galti": 1180, "end": 1720}.get(kind, 1690)
        if kind != "end":
            RT.words_frame(cv, sc["text"], t, W / 2, cy, 880, 84, rate, color_seed=i * 3, start=sc["lead"])
        if kind == "ruko":
            put_pop(cv, RT.badge("रुको! पहले सोचो", 56, (255, 80, 90), (200, 20, 50)), W / 2, 220, t, 0.05)
        elif kind == "ans":
            put_pop(cv, RT.badge("सही जवाब!", 60, (70, 230, 130), (0, 150, 70)), W / 2, 230, t, 0.0)
            B.confetti(cv, t - 1.15)
        elif kind == "galti":
            if t > 1.45:
                put_pop(cv, RT.badge("गलती!", 70, (255, 80, 80), (190, 10, 30)), W / 2, 240, t, 1.45)
        elif kind == "guide":
            put_pop(cv, RT.badge("देखो! PO Guide में यहीं लिखा है", 46, (255, 210, 60), (255, 140, 0), (50, 20, 0)),
                    W / 2, 250, t, 0.0)
        elif kind == "end":
            for im, y, t0 in cards:
                put_pop(cv, im, W / 2, y, t, t0)
        strip(cv, piece)
        proc.stdin.write(cv.convert("RGB").tobytes())
proc.stdin.close()
if proc.wait() != 0:
    raise SystemExit("ffmpeg (jodna) fail")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", out, "-vf", "fps=0.5,scale=216:384,tile=7x2", "-frames:v", "1",
                out.replace(".mp4", "_contact.jpg")], check=False)
print("B3D_REEL_DONE", out, f"{plan['total']:.1f}s")
if missing:
    print("CHETAVNI: in drishyon ke Blender frame nahi mile (saada parda laga):", ", ".join(missing))
    if os.getenv("B3D_STRICT") == "1":                 # series: adhoori 3D reel post nahi - purani reel jaayegi
        os.remove(out)
        raise SystemExit("B3D_STRICT: drishya adhoore - 3D reel nahi")
