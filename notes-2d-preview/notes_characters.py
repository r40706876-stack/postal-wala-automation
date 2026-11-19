"""Build timed sprites from the approved Notes narration and Postal Edge artwork."""

from pathlib import Path

from PIL import Image
from scipy.signal import resample_poly

from postal_edge_lip_shapes import measure_mouth
from postal_edge_puppet import puppet, ramp

FPS = 15
WIDTH, HEIGHT = 176, 270
COLUMNS = 8


def make_sprites(tmp, timeline, narration, rate):
    work = Path(tmp)
    sound = resample_poly(narration, 16_000, rate)
    scenes = [s for s in timeline if s["k"] in ("hook", "trap", "trick")
              or s["k"].startswith("line")]
    selected = scenes[:4]
    if len(selected) < 2:
        raise RuntimeError("The Notes preview needs at least two spoken notes segments")
    sprites = []
    for i, segment in enumerate(selected):
        role_is_golu = i % 2 == 0
        name = "golu" if role_is_golu else "postman"
        start = segment["t"] + 0.37
        duration = min(4.9, segment["d"] - 0.39)
        count = round(FPS * duration)
        if count < FPS // 2:
            continue
        facing = .68 if role_is_golu else -.63
        offset = round(16_000 * start)
        sample = sound[offset:offset + round(16_000 * duration)]
        shapes = measure_mouth(sample, FPS, duration)
        atlas = Image.new("RGBA", (WIDTH * COLUMNS, HEIGHT * ((count + COLUMNS - 1) // COLUMNS)))
        for f, shape in enumerate(shapes):
            t = f / FPS
            strength = .82 * ramp(t, .18, .58, max(.6, duration - .53), duration)
            actor = puppet(role_is_golu, t, 0, facing, shape, "rest",
                           (strength, "open" if role_is_golu else "left"), facing, 0, 0)
            actor = actor.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            atlas.paste(actor, ((f % COLUMNS) * WIDTH, (f // COLUMNS) * HEIGHT))
        image = f"notes-character-{i}.webp"
        atlas.save(work / image, lossless=True)
        sprites.append({"segment": segment["k"], "role": name, "start": start,
                        "count": count, "fps": FPS, "width": WIDTH, "height": HEIGHT,
                        "columns": COLUMNS, "image": image})
    return sprites
