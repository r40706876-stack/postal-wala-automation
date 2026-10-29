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


out = os.path.join(OUT_DIR, f"blender_reel_clause{plan['clause']}_part{plan['part']}.mp4")
audio = os.path.join(JOB, "audio.wav")
cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
       "-i", "-", "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium",
       "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", out]
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
missing = []
for i, sc in enumerate(scenes):
    fd = os.path.join(JOB, f"frames_{i}")
    files = sorted(f for f in os.listdir(fd) if f.endswith(".png")) if os.path.isdir(fd) else []
    if not files:
        missing.append(sc["name"])
    n = int(sc["frames"])
    k_story = 0
    for f_i in range(n):
        t = f_i / FPS
        if files:
            cv = Image.open(os.path.join(fd, files[min(len(files) - 1, f_i)])).convert("RGB").resize((W, H),
                                                                                             Image.LANCZOS)
            cv = cv.convert("RGBA")
        else:
            cv = B.bg().copy()
        kind = sc["kind"]
        piece = {"ruko": "सवाल", "galti": "गलती", "ans": f"टुकड़ा {PIECE}/{PIECE}", "guide": "सबूत",
                 "end": "याद"}.get(kind, f"टुकड़ा {int(sc.get('idx', 0)) + 1}/{PIECE}")
        p = (t - sc["lead"]) / max(0.3, sc["vd"])
        if kind == "ruko":
            N.caption(cv, sc["text"], p, cy=1700, size=70)
        elif kind == "story":
            N.caption(cv, sc["text"], p, cy=1720, size=72)
        elif kind == "galti":
            N.caption(cv, sc["text"], p, cy=1500)
        elif kind == "ans":
            N.caption(cv, sc["text"], p, cy=1720, size=72)
            N.put(cv, N.pill("सही जवाब", 46, (255, 255, 255), N.GREEN_C), W / 2, 230,
                  scale=max(0.05, M.ease_out_back(M.prog(t, 0.0, 0.3))))
            B.confetti(cv, t - 1.75)
        elif kind == "guide":
            N.put(cv, N.pill("देखो! PO Guide में यहीं लिखा है", 50, B.NAVY, B.GOLD), W / 2, 260,
                  scale=max(0.05, M.ease_out_back(M.prog(t, 0.0, 0.3))))
        if not files:
            N.caption(cv, sc["text"], 1.0, cy=960)
        strip(cv, piece)
        proc.stdin.write(cv.convert("RGB").tobytes())
proc.stdin.close()
if proc.wait() != 0:
    raise SystemExit("ffmpeg (jodna) fail")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", out, "-vf", "fps=0.5,scale=216:384,tile=7x2", "-frames:v", "1",
                os.path.join(OUT_DIR, "blender_reel_contact.jpg")], check=False)
print("B3D_REEL_DONE", out, f"{plan['total']:.1f}s")
if missing:
    print("CHETAVNI: in drishyon ke Blender frame nahi mile (saada parda laga):", ", ".join(missing))
