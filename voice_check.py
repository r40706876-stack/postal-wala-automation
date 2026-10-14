"""TEST: asli awaaz ke saath aaj ki PYQ reel (state/log runner me hi rehte hain, repo me nahi jaate)."""
import glob, os, shutil, subprocess, sys
os.makedirs("voice_check_out", exist_ok=True)
r = subprocess.run([sys.executable, "pyq_reel.py", "--force"], capture_output=True, text=True)
log = (r.stdout + "\n" + r.stderr)[-6000:]
print(log)
open("voice_check_out/pyq_log.txt", "w", encoding="utf-8").write(log)
for f in glob.glob("generated_reels/pyq/pyq_*.mp4") + glob.glob("generated_reels/pyq/pyq_*_caption.txt"):
    shutil.copy(f, "voice_check_out/")
