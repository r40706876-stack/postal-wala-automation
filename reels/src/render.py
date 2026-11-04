"""Render an HTML scene with CSS animations into an MP4 (1080x1920).
usage: python3 render.py scene.html seconds out.mp4 [fps]
Every CSS animation is paused and seeked to t for each frame -> deterministic."""
import sys, subprocess, pathlib, shutil
from playwright.sync_api import sync_playwright

html, secs, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
fps = int(sys.argv[4]) if len(sys.argv) > 4 else 30
fdir = pathlib.Path(out).with_suffix('.frames'); shutil.rmtree(fdir, True); fdir.mkdir()
n = int(secs * fps)
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 540, 'height': 960}, device_scale_factor=2)
    pg.goto(pathlib.Path(html).resolve().as_uri()); pg.wait_for_timeout(400)
    for i in range(n):
        t = i * 1000 / fps
        pg.evaluate("t=>{for(const a of document.getAnimations()){a.pause();a.currentTime=t}}", t)
        pg.screenshot(path=str(fdir / f'f{i:04d}.jpg'), type='jpeg', quality=92)
    b.close()
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(fps), '-i', str(fdir / 'f%04d.jpg'),
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart', out], check=True)
shutil.rmtree(fdir)
print('ok', out, n, 'frames')
