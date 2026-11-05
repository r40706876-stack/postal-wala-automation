"""Gemini voice for a promo reel: each line is spoken at its own start time, then muxed onto the silent video.
Runs in GitHub Actions (needs GEMINI_API_KEY). Uses main.py's Gemini TTS (same voice as the Postal Wala reels).
usage: python reels/src/voice_mux.py reels/voice/reel5.json
JSON: {"video": "...mp4", "out": "...mp4", "style": "...", "lines": [[start_sec, slot_end_sec, "text"], ...]}"""
import sys, os, json, asyncio, subprocess, tempfile
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import main  # noqa: E402

cfg = json.load(open(sys.argv[1], encoding="utf-8"))
SR = main.SR
if cfg.get("style"):
    main.GEMINI_TTS_STYLE = cfg["style"]


def ff_decode(path):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def speak(text):
    try:
        return main.gemini_tts_audio([text]), "gemini"
    except Exception as exc:  # Gemini na chale to purani awaaz (reel na ruke)
        print("  Gemini fail -> edge-tts:", exc)
        tmp = tempfile.mktemp(suffix=".mp3")
        asyncio.run(main.tts_save(text, tmp))
        return ff_decode(tmp), "edge"


def trim(a, thr=0.012):
    idx = np.where(np.abs(a) > thr)[0]
    return a[max(idx[0] - int(.03 * SR), 0): idx[-1] + int(.12 * SR)] if len(idx) else a


def tempo(a, factor):
    tmp_in, tmp_out = tempfile.mktemp(suffix=".wav"), tempfile.mktemp(suffix=".wav")
    write_wav(tmp_in, a)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", tmp_in, "-filter:a", f"atempo={factor:.3f}", tmp_out], check=True)
    return ff_decode(tmp_out)


def write_wav(path, a):
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())


vid_len = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", cfg["video"]],
                               capture_output=True, text=True, check=True).stdout)
segs, end = [], 0.0
for start, slot_end, text in cfg["lines"]:
    a, src = speak(text)
    a = trim(a)
    dur, slot = len(a) / SR, slot_end - start
    if dur > slot:                                   # thoda tez (max 1.15x), fir bhi lamba ho to video aage badhega
        a = tempo(a, min(dur / slot, 1.15))
    start = max(start, end + 0.15) if segs else start   # pichhli line se takraav na ho
    print(f"  {start:5.1f}s  {len(a) / SR:4.1f}s/{slot:.1f}s  [{src}]  {text}")
    segs.append((start, a)); end = max(end, start + len(a) / SR)

total = max(vid_len, end + 0.6)
track = np.zeros(int(total * SR) + SR, dtype=np.float32)
for start, a in segs:
    i = int(start * SR); track[i:i + len(a)] += a
track = track[:int(total * SR)]
track *= 0.95 / max(np.abs(track).max(), 1e-6)
wav = tempfile.mktemp(suffix=".wav"); write_wav(wav, track)
pad = max(total - vid_len, 0)
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", cfg["video"], "-i", wav,
                "-filter_complex", f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.2f}[v];[1:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]",
                "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{total:.2f}", cfg["out"]], check=True)
print("OK", cfg["out"], f"{total:.1f}s")
