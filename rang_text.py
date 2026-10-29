"""
RANG-BIRANGE TEXT (v26): har shabd alag chamakdaar rang (gradient), mota safed/kaala kinara, parchhai,
shabd-shabd "pop" (uchhal ke aana) + bolte shabd par halka jhoolna. Hindi theek (PIL + raqm).
  words_frame(cv, text, t, x, y, maxw, size, rate)  -> cv par likhta hai (t = drishya ka samay)
  badge(text, size, colors)                         -> chamakdaar pill (RGBA)
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

PALETTE = [((255, 230, 60), (255, 140, 0)),      # sunehra -> narangi
           ((90, 255, 160), (0, 175, 90)),       # hara
           ((120, 220, 255), (40, 110, 255)),    # neela
           ((255, 130, 190), (230, 30, 110)),    # gulabi
           ((255, 255, 255), (210, 225, 255)),   # safed
           ((200, 150, 255), (120, 60, 230))]    # baingani
_FC = {}


def font(sz):
    if sz not in _FC:
        for p in (os.getenv("FONT_FILE", "Mukta-ExtraBold.ttf"), "Mukta-Bold.ttf",
                  "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Black.ttf",
                  "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
                  "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
                  "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"):
            if os.path.exists(p) and os.path.getsize(p) > 50000:
                try:
                    _FC[sz] = ImageFont.truetype(p, sz, layout_engine=ImageFont.Layout.RAQM)
                except Exception:
                    _FC[sz] = ImageFont.truetype(p, sz)
                break
        else:
            _FC[sz] = ImageFont.load_default()
    return _FC[sz]


def ease_back(x):
    x = max(0.0, min(1.0, x))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


_WC = {}


def word_sprite(w, sz, ci):
    """Ek shabd: gradient bharaav + mota kaala kinara + safed andar ki rekha + neeche parchhai."""
    key = (w, sz, ci)
    if key in _WC:
        return _WC[key]
    f = font(sz)
    l, t, r, b = f.getbbox(w)
    pad = int(sz * 0.22)
    W_, H_ = r - l + pad * 2, b - t + pad * 2
    mask = Image.new("L", (W_, H_), 0)
    ImageDraw.Draw(mask).text((pad - l, pad - t), w, font=f, fill=255)
    out = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    sh = Image.new("L", (W_, H_), 0)                                       # parchhai
    ImageDraw.Draw(sh).text((pad - l + sz * 0.06, pad - t + sz * 0.08), w, font=f, fill=180,
                            stroke_width=max(4, sz // 9), stroke_fill=180)
    out.paste((0, 0, 0, 255), (0, 0), sh.filter(ImageFilter.GaussianBlur(sz * 0.04)))
    st = Image.new("L", (W_, H_), 0)
    ImageDraw.Draw(st).text((pad - l, pad - t), w, font=f, fill=255, stroke_width=max(4, sz // 9), stroke_fill=255)
    out.paste((15, 10, 25, 255), (0, 0), st)
    c1, c2 = PALETTE[ci % len(PALETTE)]
    grad = Image.new("RGBA", (1, H_))
    for y in range(H_):
        k = max(0.0, min(1.0, (y - pad) / max(1, H_ - 2 * pad)))
        grad.putpixel((0, y), tuple(int(c1[j] + (c2[j] - c1[j]) * k) for j in range(3)) + (255,))
    grad = grad.resize((W_, H_))
    out.paste(grad, (0, 0), mask)
    hl = Image.new("L", (W_, H_), 0)                                       # upar chamak
    ImageDraw.Draw(hl).rectangle((0, 0, W_, pad + (b - t) * 0.38), fill=70)
    out.paste((255, 255, 255, 255), (0, 0), Image.composite(hl, Image.new("L", (W_, H_), 0), mask))
    _WC[key] = out
    return out


def layout(text, size, maxw):
    ws = text.split()
    sp = font(size).getlength(" ")
    lines, cur, cw = [], [], 0
    for w in ws:
        ww = font(size).getlength(w)
        if cur and cw + sp + ww > maxw:
            lines.append(cur)
            cur, cw = [], 0
        cur.append(w)
        cw += (sp if cw else 0) + ww
    if cur:
        lines.append(cur)
    return lines


def words_frame(cv, text, t, x, y, maxw=960, size=92, rate=0.22, color_seed=0, max_lines=3, start=0.0):
    """Shabd ek-ek karke uchhal ke aate (har `rate` sec), sab alag rang. y = beech ki oonchai."""
    size_ = size
    lines = layout(text, size_, maxw)
    while len(lines) > max_lines and size_ > 46:
        size_ -= 6
        lines = layout(text, size_, maxw)
    lh = int(size_ * 1.32)
    y0 = y - (len(lines) - 1) * lh / 2
    k = 0
    for li, ln in enumerate(lines):
        sps = [word_sprite(w, size_, (color_seed + k + j)) for j, w in enumerate(ln)]
        gap = int(size_ * 0.12)
        tw = sum(s.width for s in sps) + gap * (len(sps) - 1)
        cx = x - tw / 2
        for j, sp in enumerate(sps):
            tk = (t - start - (k + j) * rate) / 0.28
            if tk > 0:
                s = max(0.05, ease_back(tk))
                wob = 1.0 + 0.04 * math.sin((t - (k + j) * rate) * 9) * max(0.0, 1 - (tk - 1) / 2)
                s *= wob
                im = sp.resize((max(1, int(sp.width * s)), max(1, int(sp.height * s))), Image.BICUBIC)
                ang = 6 * (1 - min(1.0, tk)) * (1 if (k + j) % 2 else -1)
                if abs(ang) > 0.3:
                    im = im.rotate(ang, expand=True, resample=Image.BICUBIC)
                cv.alpha_composite(im, (int(cx + sp.width / 2 - im.width / 2), int(y0 + li * lh - im.height / 2)))
            cx += sp.width + gap
        k += len(ln)
    return cv


def badge(text, size=54, c1=(255, 70, 90), c2=(200, 20, 60), fg=(255, 255, 255)):
    f = font(size)
    l, t, r, b = f.getbbox(text)
    W_, H_ = r - l + size, b - t + int(size * 0.7)
    im = Image.new("RGBA", (W_ + 16, H_ + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((8, 12, W_ + 8, H_ + 12), H_ // 2, fill=(0, 0, 0, 120))
    for y in range(H_):
        k = y / max(1, H_ - 1)
        col = tuple(int(c1[j] + (c2[j] - c1[j]) * k) for j in range(3))
        d.line((8, 4 + y, W_ + 8, 4 + y), fill=col)
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((8, 4, W_ + 8, H_ + 4), H_ // 2, fill=255)
    base = Image.new("RGBA", im.size, (0, 0, 0, 0))
    base.paste(im, (0, 0), m)
    sh = im.copy()
    sh.putalpha(Image.new("L", im.size, 0))
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle((8, 12, W_ + 8, H_ + 12), H_ // 2, fill=(0, 0, 0, 110))
    out.alpha_composite(base)
    ImageDraw.Draw(out).rounded_rectangle((8, 4, W_ + 8, H_ + 4), H_ // 2, outline=(255, 255, 255), width=4)
    ImageDraw.Draw(out).text((8 + W_ / 2, 4 + H_ / 2), text, font=f, fill=fg, anchor="mm",
                             stroke_width=3, stroke_fill=(60, 0, 20))
    return out
