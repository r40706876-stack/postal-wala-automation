"""Render the PO Guide notes preview with the approved Postal Edge rig."""

import math
import json
from pathlib import Path
import subprocess
import sys
import wave

import numpy as np
from PIL import ImageDraw

import render as rig

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "Postal_Edge_Clause_13_14_2D_Preview.mp4"
VOICE_NAME = "hi-in-concierge-10"

BEATS = (
    (True, "भैया, टिकट फट गया है। टेप लगा दूँ तो डाक शुल्क में चल जाएगा?",
     "टिकट फट गया?", "टेप लगाकर चलेगा?", "फटा टिकट", "तभी तो गोलू पूछ रहा है"),
    (False, "गोलू, कटा, फटा या अधूरा टिकट डाक शुल्क में मान्य नहीं है। पूरा टिकट लगाओ।",
     "कटा, फटा या अधूरा", "डाक शुल्क में अमान्य", "फटा टिकट", "तीनों स्थितियों में नियम एक"),
    (True, "और ये पुराना टिकट? इस पर डाकघर की मोहर पहले से लगी है।",
     "पहले से मोहर लगी?", "दोबारा लगा सकते हैं?", "मोहर लगा टिकट", "गोलू का दूसरा सवाल"),
    (False, "मोहर लगा टिकट दोबारा नहीं चलेगा। और छपे लिफाफे से अलग किया टिकट भी मान्य नहीं है।",
     "मोहर लगा या काटकर निकाला?", "दोनों अमान्य", "इस्तेमाल किया टिकट", "छपे लिफाफे से अलग किया टिकट भी"),
    (False, "नकली टिकट भी अमान्य है। याद रखो, फटा, मोहर लगा या नकली, तीनों से डाक शुल्क नहीं चुकता।",
     "फटा, मोहर लगा, नकली", "तीनों अमान्य", "डाक टिकट की पहचान", "स्क्रीनशॉट के लिए पूरी सूची"),
)


def generate_voice():
    sys.path.insert(0, str(HERE.parent / "core"))
    import main as tts

    assert tts.pick_gemini_voice() == VOICE_NAME
    tts.TTS_WAITS = (8,)
    lines = [beat[1] for beat in BEATS]
    specs = [{"name": "hook" if i == 0 else f"beat-{i}", "segs": [("dialogue", line)]}
             for i, line in enumerate(lines)]
    audio = tts.gemini_tts_audio(lines, voice=VOICE_NAME)
    split = tts.split_gemini_audio(audio, specs)
    if split:
        chunks = [part[0] for part in split]
    else:
        chunks = []
        for line in lines:
            voice = tts.gemini_tts_audio([line], voice=VOICE_NAME)
            start, stop = tts._speech_bounds(voice)
            trimmed = voice[round(start * tts.SR):round(stop * tts.SR)]
            chunks.append(tts._compress_pauses(trimmed, .24)[0])

    pieces = []
    times = [0.0]
    for i, chunk in enumerate(chunks):
        hold = .24 if i < len(chunks) - 1 else 1.1
        clip = np.pad(chunk, (round(.09 * tts.SR), round(hold * tts.SR)))
        pieces.append(clip)
        times.append(times[-1] + len(clip) / tts.SR)
    pcm = (np.clip(np.concatenate(pieces), -1, 1) * 32767).astype("<i2")
    with wave.open(str(HERE / "narration.wav"), "wb") as out:
        out.setparams((1, 2, tts.SR, 0, "NONE", "not compressed"))
        out.writeframes(pcm.tobytes())
    (HERE / "notes_timing.json").write_text(json.dumps(times))
    print("Scene boundaries:", [round(t, 2) for t in times], flush=True)


def postage_stamp(draw, x, y, width, kind):
    height = round(width * .7)
    ink = "#aa394d" if kind == "damaged" else "#466c5e"
    right = x + width
    bottom = y + height
    rig.rr(draw, x, y, width, height, "#fff2d9", "#eec996", 8)
    draw.rectangle((x + 8, y + 8, right - 8, bottom - 8), outline=ink, width=3)
    for tooth in range(x + 12, right - 5, 11):
        draw.ellipse((tooth - 2, y - 2, tooth + 2, y + 2), fill="#29433c")
    rig.word(draw, x + width / 2, y + height * .17, "डाक", max(18, width // 4), ink, True, width - 18)
    if kind == "damaged":
        draw.polygon([(right - 29, bottom), (right - 15, bottom - 21), (right, bottom - 9),
                      (right + 1, bottom + 1)], fill="#29433c")
    if kind == "used":
        draw.ellipse((right - 44, y + 14, right - 5, y + 53), outline="#523746", width=4)
        draw.line((right - 58, y + 32, right - 6, y + 46), fill="#523746", width=3)


def frame(t):
    idx = max(i for i, start in enumerate(rig.times[:-1]) if t >= start)
    local = t - rig.times[idx]
    length = rig.times[idx + 1] - rig.times[idx]
    golu, _, heading, answer, prop, footer = BEATS[idx]
    im = rig.cinema(t, idx)
    enter = rig.ease((local + .12) / .75)
    move = rig.ramp(local, -.12, .17, .55, .95)
    speak = rig.ramp(local, -.13, .29, max(.7, length - .65), length)
    turn = 4 * math.sin(local * 2.4)
    rig.actor(im, True, (190 if golu else 155) - 36 * (1 - enter) + turn, 1019,
              449 if golu else 365, t, walk=move if golu else 0, talk=golu,
              mood="think" if golu else "surprise", gesture="open" if golu else "chin",
              strength=(.76 if golu else .37) * speak)
    rig.actor(im, False, (566 if golu else 525) + 38 * (1 - enter) - turn, 1019,
              355 if golu else 455, t, walk=move if not golu else 0, talk=not golu,
              mood="rest", gesture="left" if idx % 2 == 0 else "stop",
              strength=(.32 if golu else .86) * speak)
    d = ImageDraw.Draw(im)
    rig.rr(d, 47, 61, 293, 48, "#332629", "#e5b78b", 18)
    rig.envelope(d, 60, 74, 30, rig.GOLD, False)
    rig.word(d, 103, 72, "POSTAL EDGE  /  NOTES", 20, rig.CREAM)
    rig.rr(d, 493, 63, 178, 44, rig.WINE, "#e5b78b", 15)
    rig.word(d, 582, 73, "CLAUSE 13–14", 20, rig.CREAM, True)
    y = 150 + 13 * (1 - enter)
    rig.rr(d, 44, y, 632, 220, rig.WINE, "#f1bf89", 26)
    rig.word(d, 360, y + 35, heading, 56, rig.WHITE, True, 579)
    rig.word(d, 360, y + 112, answer, 65, rig.GOLD, True, 580)
    if idx == len(BEATS) - 1:
        for i, (label, kind) in enumerate((("फटा", "damaged"), ("मोहर लगा", "used"), ("नकली", "fake"))):
            zoom = rig.ease((local - .12 * i + .08) / .41)
            if zoom <= 0:
                continue
            x = 55 + i * 207
            tile_y = 397 + 23 * (1 - zoom)
            rig.rr(d, x, tile_y, 193, 142, "#29433c", "#e5b78b", 18)
            postage_stamp(d, x + 63, round(tile_y + 17), 67, kind)
            rig.word(d, x + 96, tile_y + 91, label, 32, rig.CREAM, True)
    else:
        tile_x = round(204 + 35 * (1 - enter))
        tile_y = round(404 + 7 * math.sin(local * 2.7) * enter)
        rig.rr(d, tile_x, tile_y, 312, 151, "#29433c", "#e5b78b", 20)
        postage_stamp(d, tile_x + 100, tile_y + 14, 108, "damaged" if idx < 2 else "used")
        rig.word(d, tile_x + 156, tile_y + 101, prop, 31, rig.CREAM, True, 287)
    rig.subtitle(d, 1018, footer)
    rig.rr(d, 80, 1128, 560, 48, "#332629", None, 14)
    rig.word(d, 360, 1140, "PO Guide Part I  •  Postal Edge by Postal Wala", 19, rig.CREAM, True, 523)
    d.line((80, 1199, 640, 1199), fill="#bd9474", width=3)
    d.line((80, 1199, 80 + 560 * t / rig.END, 1199), fill=rig.GOLD, width=5)
    return im


def render():
    rig.times = json.loads((HERE / "notes_timing.json").read_text())
    rig.END = rig.times[-1]
    rig.VOICE = rig.animate_mouth()
    frame(rig.times[-2] + .65).save(HERE / "notes_preview.jpg", quality=92)
    rig.score()
    command = [
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", "720x1280", "-r", str(rig.FPS), "-i", "-", "-i", str(HERE / "narration.wav"),
        "-i", str(HERE / "music.wav"), "-filter_complex",
        "[0:v]scale=1080:1920:flags=lanczos[v];"
        "[1:a]highpass=f=80,acompressor=threshold=.14:ratio=2:makeup=1.35,apad[a];"
        "[2:a]volume=.23[m];[a][m]amix=inputs=2:normalize=0,alimiter=limit=.85[o]",
        "-map", "[v]", "-map", "[o]", "-t", str(rig.END), "-threads", "4",
        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "fast", "-crf", "19",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(OUTPUT),
    ]
    with subprocess.Popen(command, stdin=subprocess.PIPE) as ffmpeg:
        for i in range(round(rig.END * rig.FPS)):
            ffmpeg.stdin.write(frame(i / rig.FPS).tobytes())
        ffmpeg.stdin.close()
        if ffmpeg.wait():
            raise RuntimeError("Video encoding failed")


if __name__ == "__main__":
    generate_voice()
    render()
