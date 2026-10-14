"""
VOICE CHECK (sirf test - koi reel/chitra nahi, state/plan nahi badalta).
Asli reel wale raaste se awaaz banata hai:
  1) Gemini (pakki awaaz)  2) Gemini band karke edge-tts fallback
aur har ek ka gender (pitch se), gati aur kaun si awaaz chali - voice_check_out/ me likhta hai.
"""
import os
import wave

import numpy as np

import main as M

OUT = "voice_check_out"
os.makedirs(OUT, exist_ok=True)
SPECS = [
    {"name": "hook", "segs": [("hk", "अपना पता कहाँ लिखें?")]},
    {"name": "question", "segs": [("lock", "जवाब कमेंट करो!")]},
    {"name": "chitra", "segs": [("c1", "ग्राहक पत्र पर प्रेषक का पता लिखना चाहता है।")],
     "clips": [("c2", "भैया, पता कहाँ लिखूँ?"), ("c3", "पते वाली साइड नीचे बाएं कोने में लिखो।")]},
    {"name": "verdict", "segs": [("rev", "सही जवाब, पते वाली साइड नीचे बाएं कोने में!")]},
    {"name": "cta", "segs": [("yaad", "याद रखिए!")]},
]


def save(name, voices):
    parts = []
    for v in voices:
        parts.append(v[0])
        if len(v) > 3 and v[3]:
            parts += list(v[3].values())
    a = np.concatenate([np.asarray(p, dtype=np.float32) for p in parts])
    path = os.path.join(OUT, name + ".wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(M.SR)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes())
    return a, path


def pitch(a, sr):
    hop, fr = int(.01 * sr), int(.04 * sr)
    f0 = []
    for i in range(0, len(a) - fr, hop * 3):
        seg = a[i:i + fr].astype(float)
        if np.sqrt(np.mean(seg ** 2)) < 0.02:
            continue
        seg = seg - seg.mean()
        ac = np.correlate(seg, seg, "full")[len(seg) - 1:]
        lo, hi = int(sr / 300), int(sr / 70)
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.4 * ac[0]:
            f0.append(sr / k)
    return float(np.median(f0)) if f0 else 0.0


lines = [f"ENGINE: {M.ENGINE_VERSION[:120]}",
         f"Gemini awaaz: {M.GEMINI_TTS_VOICE} | gender: {M.GEMINI_TTS_GENDER} | rotation: {M.rotation_active()}",
         f"Fallback edge-tts: {M.VOICE_NAME} (backup {M.EDGE_BACKUP_VOICE})", ""]
M.apply_voice({"id": M.GEMINI_TTS_VOICE, "name": "Training Voiceover 1", "gender": M.GEMINI_TTS_GENDER})
ok = True
for tag, use_gemini in (("1_gemini_pakki_awaaz", True), ("2_fallback_edge", False)):
    M.USE_GEMINI_TTS = use_gemini
    M._CURRENT["used"] = None
    try:
        v = M.make_voices(SPECS)
        a, path = save(tag, v)
        f0 = pitch(a, M.SR)
        male = 0 < f0 < 165
        ok &= male
        lines.append(f"{tag}: chali = {M._CURRENT['used']} | lambai {len(a) / M.SR:.1f}s | pitch {f0:.0f}Hz -> "
                     f"{'PURUSH (male) OK' if male else 'MALE NAHI!'}")
    except Exception as exc:
        ok = False
        lines.append(f"{tag}: FAIL - {str(exc)[:200]}")
lines.append("")
lines.append("NATEEJA: " + ("PASS - dono raaste male awaaz" if ok else "FAIL - upar dekhiye"))
txt = "\n".join(lines)
print(txt)
open(os.path.join(OUT, "RESULT.txt"), "w", encoding="utf-8").write(txt)
