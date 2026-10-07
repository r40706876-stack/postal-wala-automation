# -*- coding: utf-8 -*-
"""
VISUAL DEMO (ek baar chalane ke liye): naya chitra-style + "Postal Wala भैया" kirdaar + flip-book + chehre par zoom.
GitHub Actions me "Visual Demo" workflow se chalta hai (Cloudflare/Gemini secrets wahi lagte hain).
Nateeje repo ke demo_out/ folder me aate hain: visual_demo.mp4, visual_demo_sheet.jpg, mascot.jpg
Roz ki reel par iska koi asar nahi (progress_state / clause_plans nahi chhedta).
"""
import os
import io
import json
import random
import importlib.util

os.environ.setdefault("DRY_RUN", "0")
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("postal_main", os.path.join(HERE, "main.py"))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
from PIL import Image, ImageDraw

OUT = os.path.join(HERE, "demo_out")
IMG = os.path.join(OUT, "img")
os.makedirs(IMG, exist_ok=True)

STYLE = ("Vibrant high-quality 2D digital illustration, premium Indian animated explainer style, rich saturated colours, "
         "warm cinematic lighting with soft rim light, sharp focus, clean confident outlines, expressive faces with clear "
         "emotions, natural hands with five fingers. Recognisable India Post world: bright red cylindrical pillar letter box, "
         "khaki postal uniform, brown leather mail bag, wooden post office counter. Simple uncluttered background with soft "
         "warm colours. Absolutely no text, no letters, no words, no numbers, no logos anywhere in the image.")

MASCOT = ("Character portrait of 'Postal Wala Bhaiya': a friendly Indian village postman (Gramin Dak Sevak), about 35 "
          "years old, neat black moustache, warm confident smile, short black hair, khaki India Post uniform shirt with "
          "shoulder flaps and a khaki cap, brown leather mail bag strap across his chest. Waist-up, standing behind a "
          "wooden post office counter, looking directly into the camera. ")

REF_TXT = ("Use the reference image: keep exactly the same postman (same face, moustache, khaki uniform, cap, mail bag) "
           "and the same art style and colours. New scene: ")

# Clause 20 (jaancha hua niyam): bade patra letter box me nahi -> van / daak khidki par haathon-haath
SCENES = [
    {"key": "p1", "mark": "none", "tag": "बड़ा पत्र", "tag_color": "dark",
     "text": "यह बड़ा पत्र लेटर बॉक्स के लिए बहुत बड़ा है।",
     "prompt": "The postman stands next to a bright red pillar letter box with a narrow slot, holding up a very large thick "
               "brown envelope that is clearly much bigger than the slot. He looks straight at the camera with a curious "
               "raised eyebrow, as if asking the viewer a question.",
     "target": "the very large brown envelope"},
    {"key": "p2a", "mark": "wrong", "frame_of": "p2",
     "prompt": "A young customer in a blue shirt tries to push the same very large brown envelope into the narrow slot of "
               "the bright red pillar letter box. The postman, standing beside it, raises his hand in alarm.",
     "target": "the envelope at the letter box slot"},
    {"key": "p2", "mark": "wrong", "tag": "लेटर बॉक्स में ठूँसना", "tag_color": "red",
     "text": "बड़े पत्र को लेटर बॉक्स में जबरदस्ती डालना गलत है।",
     "prompt": "The very large brown envelope is bent and crumpled, stuck halfway in the narrow slot of the bright red pillar "
               "letter box. The young customer looks frustrated; the postman holds his forehead, shocked.",
     "target": "the crumpled envelope stuck in the slot"},
    {"key": "p3", "mark": "right", "tag": "खिड़की पर हाथों-हाथ", "tag_color": "green",
     "text": "बड़े पत्र वैन या डाक खिड़की पर हाथों-हाथ लिए जाएंगे।",
     "prompt": "At the post office counter window, the smiling postman happily takes the very large brown envelope by hand "
               "from the relieved young customer in a blue shirt. Warm friendly moment, the envelope held between their hands.",
     "target": "the large envelope being handed over"},
]

FACE_PROMPT = """For each attached image, give the bounding box of the FACE of the person showing the strongest emotion
(the main character's face). Return ONLY JSON: {{"faces":[{{"box_2d":[ymin,xmin,ymax,xmax]}}]}} with values 0-1000,
one entry per image in order. Images: {n}
"""


def gen(prompt, ref=None, tries=3):
    last = None
    for _ in range(tries):
        try:
            return M._cf_image(prompt, ref=ref)
        except M.PhotoFlagged as exc:
            last = exc
            prompt = prompt + " Calm, friendly, simple everyday scene."
    raise RuntimeError(f"chitra nahi bana: {last}")


def save(b, name):
    im = Image.open(io.BytesIO(b)).convert("RGB")
    im.thumbnail((1024, 1024), Image.LANCZOS)
    path = os.path.join(IMG, name + ".jpg").replace("\\", "/")
    im.save(path, "JPEG", quality=92)
    return path


def main():
    print("1) Postal Wala भैया (kirdaar) ban raha hai...")
    mascot_b = gen(MASCOT + STYLE)
    save(mascot_b, "mascot")
    Image.open(os.path.join(IMG, "mascot.jpg")).save(os.path.join(OUT, "mascot.jpg"), quality=92)
    ref = M._ref_png(mascot_b)

    print("2) Clause 20 ki chitra-kahani (kirdaar ke saath)...")
    imgs = {}
    for sc in SCENES:
        print("   -", sc["key"])
        imgs[sc["key"]] = gen(REF_TXT + sc["prompt"] + " " + STYLE, ref=ref)

    main_keys = [sc["key"] for sc in SCENES if "frame_of" not in sc]
    panels = []
    for sc in SCENES:
        if "frame_of" in sc:
            continue
        panels.append({"prompt": sc["prompt"], "target": sc["target"], "tag": sc["tag"], "tag_color": sc["tag_color"],
                       "text": sc["text"], "mark": sc["mark"], "desc": sc["prompt"]})

    print("3) Aankh-jaanch: cheez kahan hai (box)...")
    order = list(range(len(main_keys)))
    blist = [imgs[k] for k in main_keys]
    try:
        good, bad = M._photo_check(panels, order, blist, M.PHOTO_MIN_LAST)
    except Exception as exc:
        print("   aankh-jaanch nahi chali:", str(exc)[:120])
        good, bad = {}, {}
    for i, k in enumerate(main_keys):
        if i in bad:                                   # ek baar dobara (demo - zyada credit nahi)
            print(f"   {k} kamzor ({bad[i][:80]}) -> ek baar dobara")
            imgs[k] = gen(REF_TXT + SCENES[[s["key"] for s in SCENES].index(k)]["prompt"] + " " + STYLE, ref=ref)
            try:
                g2, _b2 = M._photo_check(panels, [i], [None] * i + [imgs[k]] + [None] * (len(main_keys) - i - 1),
                                         M.PHOTO_MIN_LAST)
                good.update(g2)
            except Exception:
                pass

    print("4) Chehre kahan hain...")
    blist = [imgs[k] for k in main_keys]
    faces = {}
    try:
        res = M.as_dict(M._gemini_vision(FACE_PROMPT.format(n=len(main_keys)), blist))
        rows = res.get("faces") if isinstance(res.get("faces"), list) else []
        for i, r_ in enumerate(rows[:len(main_keys)]):
            fb = M._photo_box((r_ or {}).get("box_2d") if isinstance(r_, dict) else r_)
            if fb:
                faces[i] = fb
    except Exception as exc:
        print("   chehra-jaanch nahi chali:", str(exc)[:120])

    for i, k in enumerate(main_keys):
        panels[i]["img"] = save(imgs[k], k)
        panels[i]["box"] = good.get(i) or [0.3, 0.32, 0.7, 0.72]
        if i in faces:
            panels[i]["face"] = faces[i]
    for sc in SCENES:
        if "frame_of" in sc:
            j = main_keys.index(sc["frame_of"])
            panels[j].setdefault("frames", []).append(save(imgs[sc["key"]], sc["key"]))

    with open(os.path.join(OUT, "panels.json"), "w", encoding="utf-8") as f:
        json.dump(panels, f, ensure_ascii=False, indent=1)
    sheet(panels)

    print("5) Demo reel ban rahi hai...")
    cv_ = {"kit": "photo", "ok": True, "v": M.CHITRA_SCHEMA, "pv": M.PHOTO_V, "panels": panels,
           "caps": [p["text"] for p in panels]}
    part = {"fact": "बड़े पत्र जो लेटर बॉक्स में नहीं आ सकते, वैन या डाक खिड़की पर हाथों-हाथ लिए जाएंगे।",
            "question": "बड़े आकार के पत्र जो लेटर बॉक्स में नहीं आ सकते, वे कैसे स्वीकार किए जाएंगे?",
            "a": "डाकघर के पीछे", "b": "केवल डाकिया द्वारा", "c": "कूरियर के माध्यम से", "d": "खिड़की पर हाथों-हाथ",
            "correct": "D", "trap": "", "yaad": "बड़ा पत्र = खिड़की पर हाथों-हाथ", "title": "बड़े पत्र", "chitra_v": cv_,
            "hook_v": {"ok": True, "text": "बड़ा लिफाफा लेटर बॉक्स में नहीं आ रहा, ग्राहक को क्या कहें?"},
            "basis": "guide", "source_quote": "x"}
    d = M.prepare_data(part, 20, 1, total_parts=2, syllabus=(20, 71))
    d.update(episode=1, new_badge=False, challenge="", teaser="")
    d["bonus"] = None
    M.build_reel(d, os.path.join(OUT, "visual_demo.mp4"))
    print("\nDEMO TAIYAR: demo_out/visual_demo.mp4 , demo_out/visual_demo_sheet.jpg , demo_out/mascot.jpg")


def sheet(panels):
    """Saare chitra ek jagah (frames bhi) - jaldi dekhne ke liye."""
    items = []
    for p in panels:
        for f_ in p.get("frames") or []:
            items.append((f_, "हलचल", (230, 120, 40)))
        items.append((p["img"], {"none": "स्थिति", "wrong": "गलत", "right": "सही"}[p["mark"]],
                      {"none": (60, 140, 220), "wrong": (220, 50, 60), "right": (40, 170, 90)}[p["mark"]]))
    S, pad = 520, 24
    items = [(os.path.join(IMG, "mascot.jpg"), "किरदार", (240, 190, 40))] + items
    out = Image.new("RGB", (pad + len(items) * (S + pad), S + 110), (14, 22, 42))
    d = ImageDraw.Draw(out)
    for i, (path, lab, col) in enumerate(items):
        x = pad + i * (S + pad)
        im = Image.open(path).convert("RGB").resize((S, S), Image.LANCZOS)
        d.rectangle((x - 5, pad - 5, x + S + 5, pad + S + 5), fill=col)
        out.paste(im, (x, pad))
        d.text((x + S / 2, pad + S + 45), lab, font=M.get_font(40), fill=col, anchor="mm")
    out.save(os.path.join(OUT, "visual_demo_sheet.jpg"), quality=90)


if __name__ == "__main__":
    main()
