import json
from pathlib import Path
import subprocess

root = Path(__file__).parent
# Cut points aligned to the pinned narration take.
cuts = [0, 3.78, 6.63, 12.65, 17.11, 22.38]
trim_start = 0.14
pace = 1.06
subprocess.run([
    "ffmpeg", "-y", "-v", "error", "-i", str(root / "narration_raw.wav"),
    "-af", f"atrim=start={trim_start}:end={cuts[-1]},asetpts=PTS-STARTPTS,atempo={pace}",
    str(root / "narration.wav"),
], check=True)
with (root / "timing.json").open("w") as file:
    json.dump([max(0, (point - trim_start) / pace) for point in cuts], file)
