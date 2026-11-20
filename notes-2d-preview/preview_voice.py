"""Synthesize the revised Notes script in the established Postal Edge voice."""

import numpy as np

VOICE = "hi-in-concierge-10"


def voice(segments, lang):
    import main

    if lang != "hi" or main.pick_gemini_voice() != VOICE:
        raise ValueError("This revision requires the approved Hindi narration voice")
    main.TTS_WAITS = (6, 18)
    main.GEMINI_TTS_STYLE = "Energetic Hindi teacher, conversational, clear and brisk. Read the script verbatim."
    specs = [
        {"name": "hook" if i == 0 else f"note-{i}", "segs": [("line", text)]}
        for i, text in enumerate(segments)
    ]
    parts = main.split_gemini_audio(main.gemini_tts_audio(segments, voice=VOICE), specs)
    if parts:
        audio = [part[0] for part in parts]
    else:
        audio = []
        for text in segments:
            sample = main.gemini_tts_audio([text], voice=VOICE)
            start, stop = main._speech_bounds(sample)
            audio.append(np.asarray(sample[round(start * main.SR):round(stop * main.SR)]))
    return audio, main.SR, {VOICE}
