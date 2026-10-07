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
         "emotions, natural hands with five fingers. Recognisable India Post world. Plain painted walls with nothing on "
         "them: no posters, no notice boards, no screens, no signboards. Absolutely no text, no letters, no words, no "
         "numbers, no logos anywhere in the image.")

MASCOT = ("Character portrait of 'Postal Wala Bhaiya': a friendly Indian village postman (Gramin Dak Sevak), about 35 "
          "years old, neat black moustache, warm confident smile, short black hair, khaki India Post uniform shirt with "
          "shoulder flaps, a khaki cap, a brown leather mail bag strap across his chest, and a small plain dark navy-blue "
          "rectangular name badge (completely blank) on his right chest above the pocket. Waist-up, standing behind a "
          "wooden post office counter, looking directly into the camera. Plain warm wall behind him. ")

CUSTOMER = ("Character portrait of a young Indian man, about 25, short black hair, light stubble, light blue checked shirt, "
            "dark trousers, a small red cloth shoulder bag. Friendly face, waist-up, plain warm background, looking at the "
            "camera. ")

REF_TXT = ("Use the reference images: keep exactly the same postman (same face, moustache, khaki uniform, cap, mail bag, "
           "blank navy name badge) and the same young customer (same face, light blue checked shirt, red shoulder bag), "
           "and the same art style and colours. New scene: ")

SETTING_OUT = ("Outside a small Indian post office on a sunny street: a bright red cylindrical India Post pillar letter "
               "box with a narrow letter slot stands on the pavement. ")
SETTING_IN = ("Inside a small Indian post office: a wooden counter with a clear glass service window that has a small "
              "opening at the bottom, the postman sits behind the window. ")
SETTING_VAN = ("On a street: a bright red India Post mail van (no writing on it) with its back doors open, parked; the "
               "postman stands at the open back of the van. ")

# Clause 20 (jaancha hua niyam): bade patra letter box me nahi -> van ya daak khidki par haathon-haath
SCENES = [
    {"key": "p1", "mark": "none", "tag": "बड़ा पत्र", "tag_color": "dark", "pan": "lr",
     "text": "ग्राहक का पत्र लेटर बॉक्स के मुँह से बहुत बड़ा है।",
     "prompt": SETTING_OUT + "The young customer stands next to the letter box holding a very large thick brown envelope, "
               "clearly much wider than the narrow slot. He looks straight at the camera, puzzled, one eyebrow raised.",
     "target": "the very large brown envelope"},
    {"key": "p2a", "mark": "wrong", "frame_of": "p2",
     "prompt": SETTING_OUT + "The young customer starts pushing the very large brown envelope into the narrow slot of the "
               "red pillar letter box with both hands. Determined face.",
     "target": "the envelope at the slot"},
    {"key": "p2b", "mark": "wrong", "frame_of": "p2",
     "prompt": SETTING_OUT + "The very large brown envelope bends and crumples as the young customer forces it harder into "
               "the narrow slot of the red pillar letter box. Strained face.",
     "target": "the bending envelope at the slot"},
    {"key": "p2", "mark": "wrong", "tag": "लेटर बॉक्स में ठूँसना", "tag_color": "red",
     "text": "बड़े पत्र को लेटर बॉक्स में जबरदस्ती डालना गलत है।",
     "prompt": SETTING_OUT + "The very large brown envelope is torn and stuck halfway in the slot of the red pillar letter "
               "box. The young customer looks shocked. The postman rushes in from the side with one hand raised, "
               "saying stop.",
     "target": "the torn envelope stuck in the slot"},
    {"key": "p3a", "mark": "right", "frame_of": "p3",
     "prompt": SETTING_IN + "The young customer walks up to the glass service window holding the very large brown "
               "envelope. The smiling postman behind the window waves him over.",
     "target": "the large envelope"},
    {"key": "p3", "mark": "right", "tag": "डाक खिड़की पर हाथों-हाथ", "tag_color": "green",
     "text": "बड़ा पत्र डाक खिड़की पर हाथों-हाथ दिया जाता है।",
     "prompt": SETTING_IN + "The young customer hands the very large brown envelope through the opening of the glass "
               "service window directly into the hands of the smiling postman. Both smile.",
     "target": "the large envelope passing through the window"},
    {"key": "p4", "mark": "right", "tag": "या डाक वैन पर", "tag_color": "green", "pan": "rl",
     "text": "या फिर डाक वैन पर भी हाथों-हाथ दिया जा सकता है।",
     "prompt": SETTING_VAN + "The young customer hands the very large brown envelope by hand to the smiling postman at "
               "the open back of the red mail van. The postman gives a thumbs up.",
     "target": "the large envelope being handed over at the van"},
]

FACE_PROMPT = """For each attached image (in order), give:
- "face": bounding box of the face of the person showing the strongest emotion,
- "badge": bounding box of the small dark-blue name badge on the postman's chest, or null if it is not visible.
Return ONLY JSON: {{"images":[{{"face":[ymin,xmin,ymax,xmax],"badge":[ymin,xmin,ymax,xmax]}}]}} with values 0-1000,
one entry per image. Number of images: {n}
"""


def small_box(v):
    """Chhote dabbe (naam-patti) ke liye: _photo_box chhote dabbe ko phenk deta hai."""
    try:
        vals = [float(a) for a in v][:4]
        if len(vals) != 4 or max(vals) <= 0:
            return None
        div = 1.0 if max(vals) <= 1.5 else 1000.0
        y0, x0, y1, x1 = [a / div for a in vals]
        x0, x1 = sorted((max(0, x0), min(1, x1)))
        y0, y1 = sorted((max(0, y0), min(1, y1)))
        return [x0, y0, x1, y1] if (x1 - x0) > 0.01 and (y1 - y0) > 0.005 else None
    except (TypeError, ValueError):
        return None


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
    print("   grahak (customer) kirdaar...")
    cust_b = gen(CUSTOMER + STYLE)
    save(cust_b, "customer")
    ref = [M._ref_png(mascot_b), M._ref_png(cust_b)]

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
                       "text": sc["text"], "mark": sc["mark"], "desc": sc["prompt"], **({"pan": sc["pan"]} if sc.get("pan") else {})})

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

    print("4) Chehre + naam-patti kahan hain...")
    all_keys = [sc["key"] for sc in SCENES]
    info = {}
    try:
        res = M.as_dict(M._gemini_vision(FACE_PROMPT.format(n=len(all_keys)), [imgs[k] for k in all_keys]))
        rows = res.get("images") if isinstance(res.get("images"), list) else []
        for k, r_ in zip(all_keys, rows):
            if isinstance(r_, dict):
                info[k] = {"face": M._photo_box(r_.get("face")), "badge": small_box(r_.get("badge"))}
    except Exception as exc:
        print("   chehra-jaanch nahi chali:", str(exc)[:120])

    for i, k in enumerate(main_keys):
        panels[i]["img"] = save(imgs[k], k)
        panels[i]["box"] = good.get(i) or [0.3, 0.32, 0.7, 0.72]
        if (info.get(k) or {}).get("face"):
            panels[i]["face"] = info[k]["face"]
        if (info.get(k) or {}).get("badge"):
            panels[i]["badge"] = info[k]["badge"]
    for sc in SCENES:
        if "frame_of" in sc:
            j = main_keys.index(sc["frame_of"])
            panels[j].setdefault("frames", []).append(save(imgs[sc["key"]], sc["key"]))
    # mascot photo par bhi naam-patti (dekhne ke liye)
    try:
        mb = M.as_dict(M._gemini_vision(FACE_PROMPT.format(n=1), [mascot_b]))
        bb = small_box(((mb.get("images") or [{}])[0] or {}).get("badge"))
        if bb:
            pm = {"img": os.path.join(IMG, "mascot.jpg"), "box": [0.3, 0.3, 0.7, 0.7], "badge": bb, "mark": "none"}
            M.photo_frame(pm, 1024, 0, 0, 0).convert("RGB").save(os.path.join(OUT, "mascot.jpg"), quality=92)
    except Exception:
        pass

    with open(os.path.join(OUT, "panels.json"), "w", encoding="utf-8") as f:
        json.dump(panels, f, ensure_ascii=False, indent=1)
    sheet(panels)

    print("5) Demo reel ban rahi hai...")
    cv_ = {"kit": "photo", "ok": True, "v": M.CHITRA_SCHEMA, "pv": M.PHOTO_V, "panels": panels,
           "caps": [p["text"] for p in panels]}
    part = {"fact": "बड़े पत्र जो लेटर बॉक्स में नहीं आ सकते, वैन या डाक खिड़की पर हाथों-हाथ लिए जाएंगे।",
            "question": "बड़े आकार के पत्र जो लेटर बॉक्स में नहीं आ सकते, वे कैसे स्वीकार किए जाएंगे?",
            "a": "डाकघर के पीछे", "b": "केवल डाकिया द्वारा", "c": "कूरियर के माध्यम से", "d": "खिड़की पर हाथों-हाथ",
            "correct": "D", "trap": "", "yaad": "बड़ा पत्र = खिड़की / वैन पर हाथों-हाथ", "title": "बड़े पत्र", "chitra_v": cv_,
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
    items = [(os.path.join(OUT, "mascot.jpg"), "किरदार", (240, 190, 40)),
             (os.path.join(IMG, "customer.jpg"), "ग्राहक", (240, 190, 40))] + items
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
