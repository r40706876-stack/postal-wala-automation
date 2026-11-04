"""Contact sheet of a scene at given seconds. usage: peek.py scene.html out.png t1 t2 ..."""
import sys, pathlib, io
from playwright.sync_api import sync_playwright
from PIL import Image
html, out, ts = sys.argv[1], sys.argv[2], [float(x) for x in sys.argv[3:]]
ims = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={'width': 540, 'height': 960})
    pg.goto(pathlib.Path(html).resolve().as_uri()); pg.wait_for_timeout(400)
    for t in ts:
        pg.evaluate("t=>{for(const a of document.getAnimations()){a.pause();a.currentTime=t}}", t * 1000)
        ims.append(Image.open(io.BytesIO(pg.screenshot())))
    b.close()
sheet = Image.new('RGB', (270 * len(ims), 480), 'white')
for i, im in enumerate(ims): sheet.paste(im.resize((270, 480)), (270 * i, 0))
sheet.save(out)
