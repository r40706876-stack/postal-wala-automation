"""Make reel/website assets from the built Hindi notes PDF.
usage: python3 assets.py FULL_Hindi.pdf outdir"""
import sys, subprocess, json, pathlib
import numpy as np
from PIL import Image
from scipy import ndimage

pdf, out = sys.argv[1], pathlib.Path(sys.argv[2]); out.mkdir(exist_ok=True)
GLANCE_PAGE = 27            # Registry / बीमा / VP box
FLIP = [1, 3, 8, 12, 16, 22, 27, 34, 40, 46]


def render(page, dpi, name):
    subprocess.run(['pdftoppm', '-r', str(dpi), '-png', '-singlefile', '-f', str(page), '-l', str(page), pdf,
                    str(out / name)], check=True)
    return Image.open(out / f'{name}.png').convert('RGB')


# 1. glance box crop + tile rectangles
im = render(GLANCE_PAGE, 220, 'g'); a = np.asarray(im).astype(int)
bg = np.array([244, 248, 255])
m = (np.abs(a - bg) < 4).all(2)
lab, n = ndimage.label(m); big = np.argmax(np.bincount(lab.ravel())[1:]) + 1
ys, xs = np.where(lab == big)
x0, y0, x1, y1 = xs.min() - 7, ys.min() - 7, xs.max() + 8, ys.max() + 8
box = a[y0:y1, x0:x1]
# white tiles inside the box
w = (box > 250).all(2)
lab2, n2 = ndimage.label(w)
tiles = []
for sl in ndimage.find_objects(lab2):
    h, wd = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
    if 100 < h < 220 and 180 < wd < 420:
        tiles.append([sl[1].start, sl[0].start, sl[1].stop, sl[0].stop])
tiles.sort(key=lambda r: (round(r[1] / 50), r[0]))
split = max(t[3] for t in tiles) + 12          # tiles above, trap/trick below
H, W = box.shape[:2]
Image.fromarray(box[:split].astype('uint8')).save(out / 'glance_tiles.png')
Image.fromarray(box[split:].astype('uint8')).save(out / 'glance_trap.png')
meta = {'W': W, 'Ht': split, 'Hb': H - split,
        'tiles': [[t[0] - 6, t[1] - 6, t[2] + 6, t[3] + 6] for t in tiles]}
for i, (l, t, r, b) in enumerate(meta['tiles']):
    Image.fromarray(box[t:b, l:r].astype('uint8')).save(out / f'tile{i}.png')
bot = box[split:-14, 12:-12]; bm = (np.abs(bot - bg) < 6).all(2)
col = bm[20:-30].mean(0); gap = [x for x in range(300, W - 300) if col[x] > 0.97]
mid = (gap[0] + gap[-1]) // 2 if gap else W // 2


def trim(arr):
    mm = ~(np.abs(arr - bg) < 6).all(2); yy, xx = np.where(mm)
    return arr[max(yy.min() - 6, 0):yy.max() + 10, max(xx.min() - 6, 0):xx.max() + 10]


Image.fromarray(trim(bot[:, :mid]).astype('uint8')).save(out / 'trap.png')
Image.fromarray(trim(bot[:, mid:]).astype('uint8')).save(out / 'trick.png')
meta['n_tiles'] = len(tiles)
json.dump(meta, open(out / 'glance.json', 'w'))
print('glance', meta)

# 2. flip pages (reel) + website samples
for p in FLIP:
    render(p, 150, f'pg{p:02d}')
print('pages', FLIP)
