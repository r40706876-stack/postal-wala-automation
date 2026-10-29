"""
Blender 3D shot ke liye lifaafe ka saamne wala chitra (PIL) - Air Mail kinara, mohar, Roman pata.
Hindi/likhai Blender me bigadti hai, isliye likhai yahin tasveer me.
Chalana: python b3d_texture.py OUT.png "To," "Mr. John Smith" "123, Main Road" "London, UK"
"""
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 2200, 1400


def font(sz, bold=True):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def make(out, lines):
    im = Image.new("RGB", (W, H), (250, 247, 238))
    d = ImageDraw.Draw(im)
    # Air Mail kinara: laal-neeli tirchhi pattiyan
    band, step = 70, 120
    for i in range(-H, W + H, step):
        col = (205, 35, 45) if (i // step) % 2 == 0 else (25, 60, 150)
        for (x0, y0, x1, y1) in ((0, 0, W, band), (0, H - band, W, H)):
            d.polygon([(i, y1), (i + step / 2, y1), (i + step / 2 + band, y0), (i + band, y0)], fill=col)
        for (x0, x1) in ((0, band), (W - band, W)):
            d.polygon([(x0, i), (x1, i + band), (x1, i + band + step / 2), (x0, i + step / 2)], fill=col)
    d.rectangle((band, band, W - band, H - band), fill=(250, 247, 238))
    # flap ki halki rekha
    d.line((band, band, W / 2, H * 0.48), fill=(222, 214, 196), width=8)
    d.line((W - band, band, W / 2, H * 0.48), fill=(222, 214, 196), width=8)
    # BY AIR MAIL label
    d.rounded_rectangle((150, 150, 760, 300), 18, fill=(25, 60, 150))
    d.text((455, 225), "BY AIR MAIL", font=font(70), fill="white", anchor="mm")
    # mohar (stamp)
    d.rectangle((1720, 150, 2010, 470), fill=(214, 60, 60), outline=(255, 255, 255), width=14)
    d.text((1865, 275), "INDIA", font=font(56), fill="white", anchor="mm")
    d.text((1865, 370), "POST", font=font(56), fill="white", anchor="mm")
    d.ellipse((1560, 260, 1820, 520), outline=(40, 40, 60), width=8)
    for k in range(4):
        d.arc((1480 + k * 8, 300 + k * 30, 1900, 330 + k * 30), 190, 350, fill=(40, 40, 60), width=6)
    # pata (Roman akshar + Arabic ank) - sahi tarika
    y = 640
    for i, ln in enumerate(lines[:5]):
        f = font(96 if i else 84)
        d.text((820, y), ln, font=f, fill=(20, 30, 80), anchor="lm")
        y += 140
    d.line((820, y - 60, 1960, y - 60), fill=(20, 140, 70), width=10)
    im.save(out)
    print("TEXTURE", out)


if __name__ == "__main__":
    args = sys.argv[1:]
    make(args[0] if args else "lifaafa_tex.png",
         args[1:] or ["To,", "Mr. John Smith", "123, Main Road", "London, UK"])
