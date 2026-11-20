"""Place the Postal Edge website at the top through the intro and the Notes reel."""

import sys
from PIL import Image, ImageDraw, ImageFont

image = Image.new("RGBA", (236, 47))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((1, 1, 234, 45), radius=14, fill="#13245c", outline="#ffe14d", width=2)
font = ImageFont.load_default(size=26)
draw.text((118, 23), "postaledge.in", fill="#fff5bc", anchor="mm", font=font)
image.save(sys.argv[1])
