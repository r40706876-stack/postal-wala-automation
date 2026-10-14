"""TEST: naye format demo ki awaaz (ek Gemini call) - har line alag wav. Reel/state nahi chhuta."""
import json, os, wave
import numpy as np
import main as M
OUT = "voice_check_out"; os.makedirs(OUT, exist_ok=True)
lines = json.load(open("fmt_test/lines.json", encoding="utf-8"))
M.GEMINI_TTS_STYLE = "excited energetic storyteller, expressive and dramatic, natural conversational pace, short pauses"
M.apply_voice({"id": "hi-in-training-1", "name": "Training Voiceover 1", "gender": "male"})
specs = [{"name": k, "segs": [(k, t)]} for k, t in lines]
vs = M.make_voices(specs)
info = [f"chali: {M._CURRENT.get('used')}"]
for (k, _), v in zip(lines, vs):
    a = np.asarray(v[0], dtype=np.float32)
    with wave.open(os.path.join(OUT, f"{k}.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(M.SR)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes())
    info.append(f"{k}: {len(a)/M.SR:.2f}s")
open(os.path.join(OUT, "RESULT.txt"), "w", encoding="utf-8").write("\n".join(info)); print("\n".join(info))
