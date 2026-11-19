"""Use one fixed-voice TTS request for this preview, then align the existing Notes scenes."""

import numpy as np

def voice(segments, lang):
    import main

    main.TTS_WAITS = (8,)
    main.GEMINI_TTS_STYLE = "energetic, friendly teacher, clear Hindi, lively pace"
    specs = [{"name": "hook" if i == 0 else f"note-{i}", "segs": [("line", s)]}
             for i, s in enumerate(segments)]
    audio = main.gemini_tts_audio(segments)
    split = main.split_gemini_audio(audio, specs)
    if split:
        chunks = [item[0] for item in split]
    else:
        chunks = []
        for line in segments:
            sample = main.gemini_tts_audio([line])
            a, b = main._speech_bounds(sample)
            chunks.append(np.asarray(sample[round(a * main.SR):round(b * main.SR)]))
    return chunks, main.SR, {"gemini"}
