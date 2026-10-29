"""
POORI REEL BLENDER ME (demo v25, 2026-10-29) - TAIYAARI. Clause 26 Part 5.
User: "sari chize blender se animate karwao". Kirdaar = wahi pasand ki tasveeren, cutout bana ke 3D stage par
(2.5D kaagaz-theatre); counter/deewar/lifaafa/mohar/globe/kitaab/✓❌ asli 3D. Hindi likhai Blender me bigadti hai
-> saari likhai yahan PIL tasveer (texture) banti hai; caption/patti baad me b3d_assemble.py lagata hai.

Nateeja: b3d_job/plan.json + b3d_job/tex/*.png + b3d_job/audio.wav
Chalana: python b3d_prep.py   (GEMINI_API_KEY ho to asli awaaz, warna Swara)
"""
import glob
import json
import math
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["BHAROSA_V2"] = "1"
import main as M
import bharosa as B

FPS = 24
JOB = "b3d_job"
TEX = os.path.join(JOB, "tex")
os.makedirs(TEX, exist_ok=True)
# Kaunsa part: env B3D_CLAUSE + B3D_PART (1 se ginti), warna aaj ki series reel (series_today.json) ka
def _which():
    import re
    if os.getenv("B3D_CLAUSE") and os.getenv("B3D_PART"):
        return int(os.environ["B3D_CLAUSE"]), int(os.environ["B3D_PART"]) - 1
    st = json.load(open(os.path.join("generated_reels", "series_today.json"), encoding="utf-8"))
    m = re.search(r"clause_(\d+)_part_(\d+)", st.get("file", ""))
    if not m:
        raise SystemExit("B3D: aaj ki series reel ka clause/part nahi mila")
    return int(m.group(1)), int(m.group(2)) - 1


CLAUSE, PART = _which()
print("B3D_PREP Clause", CLAUSE, "Part", PART + 1)

B.init(M)
N = B.N
NAVY, GOLD, RED, GRN, INK = B.NAVY, B.GOLD, B.RED, B.GRN, B.INK
F, FR = B.F, B.FR


def save(im, name):
    """Path plan.json ke folder se relative (matrix runners par bhi chale)."""
    im.save(os.path.join(TEX, name))
    return f"tex/{name}"


def card(w, h, fill=(255, 255, 255), outline=GOLD, ow=10, r=40):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=fill, outline=outline, width=ow)
    return im


def text_c(d, xy, t, maxw, size, minsize, fill, lines=3, bold=True):
    f, s_, ls = M.fit_lines(t, maxw, lines, size, minsize)
    x, y = xy
    y -= (len(ls) - 1) * s_ * 0.65
    for ln in ls:
        d.text((x, y), " ".join(ln), font=f, fill=fill, anchor="mm")
        y += int(s_ * 1.3)


# ---------------- data (demo_v24 jaisa) ----------------
plan = json.load(open(f"clause_plans/clause_{CLAUSE}.json", encoding="utf-8"))
part = plan["parts"][PART]
for pn in part["chitra_v"]["panels"]:
    if not os.path.exists(pn["img"]):
        base = pn["img"][:-4]
        key, idx = os.path.basename(base).split("_")[0], base.rsplit("_", 1)[1]
        c = (sorted(glob.glob(f"{base}f1.jpg")) + sorted(glob.glob(f"clause_plans/chitra_img/{key}_keep_*_{idx}.jpg"))
             + sorted(glob.glob(f"clause_plans/chitra_img/{key}_*{idx}f*.jpg"))
             + sorted(glob.glob(f"clause_plans/chitra_img/{key}_*.jpg")))
        if c:
            pn["img"] = c[0]
data_in = dict(part)
data_in["title"] = plan.get("title_hi") or plan.get("title_en", "")
data = M.prepare_data(data_in, CLAUSE, PART + 1, total_parts=len(plan["parts"]), next_title="", syllabus=None)
try:
    data["episode"] = int(json.load(open("progress_state.json", encoding="utf-8")).get("episode", 0))
except Exception:
    data["episode"] = 0
_en = " ".join(str(v) for v in (data.get("en") or {}).values()) if isinstance(data.get("en"), dict) else ""
FOREIGN = ("विदेश" in (data.get("fact", "") + data.get("question", ""))) or ("foreign" in _en.lower())
story, ans_pn = N.story_split(data["chitra"]["panels"])

# ---------------- kirdaar cutout (PNG, alpha) ----------------
CH = {}
for nm, ex in (("bhaiya", "sochta"), ("bhaiya", "batata"), ("bhaiya", "chauka"), ("bhaiya", "shabaash"),
               ("grahak", ""), ("grahak", "sochta"), ("grahak", "udaas"), ("grahak", "khush")):
    p = B.char_file(nm, ex) if ex else os.path.join("clause_plans", "characters", "grahak.jpg")
    if p and os.path.exists(p):
        CH[f"{nm}_{ex or 'base'}"] = save(B.cutout(p, 1000), f"ch_{nm}_{ex or 'base'}.png")


def ch(nm, *prefs):
    for e in prefs:
        if f"{nm}_{e}" in CH:
            return CH[f"{nm}_{e}"]
    return CH.get(f"{nm}_base") or next(iter(CH.values()))


# ---------------- likhai ki tasveeren ----------------
def q_board():
    im = card(1500, 1500, (255, 255, 255), GOLD, 16, 60)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((60, 50, 1440, 150), 40, fill=NAVY)
    d.text((750, 100), "GDS से MTS / Postman / PA परीक्षा", font=F(54), fill=GOLD, anchor="mm")
    text_c(d, (750, 360), " ".join((data.get("question") or "").split()), 1300, 84, 52, INK, 4)
    y = 640
    for L, txt in (data.get("options") or [])[:4]:
        d.rounded_rectangle((90, y, 1410, y + 170), 34, fill=(244, 246, 252), outline=(210, 215, 230), width=4)
        d.ellipse((115, y + 30, 225, y + 140), fill=NAVY)
        d.text((170, y + 85), L, font=F(60), fill=GOLD, anchor="mm")
        f, s_, ls = M.fit_lines(txt, 1100, 1, 60, 38)
        d.text((260, y + 85), " ".join(ls[0]), font=f, fill=INK, anchor="lm")
        y += 195
    return im


def bubble(t, tail_left=True):
    im = Image.new("RGBA", (1200, 520), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((10, 10, 1190, 400), 80, fill=(255, 255, 255), outline=NAVY, width=10)
    tx = 250 if tail_left else 950
    d.polygon([(tx - 60, 395), (tx + 60, 395), (tx - 20 if tail_left else tx + 20, 515)], fill=(255, 255, 255))
    d.line((tx - 60, 398, tx - 20 if tail_left else tx + 20, 512), fill=NAVY, width=10)
    d.line((tx + 60, 398, tx - 20 if tail_left else tx + 20, 512), fill=NAVY, width=10)
    text_c(d, (600, 205), t, 1060, 76, 46, INK, 3)
    return im


def env_tex(lines, wrong=False):
    im = Image.new("RGB", (2200, 1400), (250, 247, 238))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 2199, 1399), outline=(200, 190, 170), width=16)
    d.line((0, 0, 1100, 660), fill=(225, 218, 200), width=10)
    d.line((2200, 0, 1100, 660), fill=(225, 218, 200), width=10)
    d.rectangle((1760, 120, 2060, 440), fill=(214, 60, 60), outline=(255, 255, 255), width=14)
    d.text((1910, 280), "₹", font=F(150), fill="white", anchor="mm")
    y = 760
    for ln in (lines or [])[:4]:
        f, s_, ls = M.fit_lines(str(ln), 1500, 1, 120, 70)
        d.text((500, y), " ".join(ls[0]), font=f, fill=(30, 40, 90), anchor="lm")
        y += int(s_ * 1.35)
    return im


def guide_page():
    gv = N.guide_line(plan, part, data) or {}
    sent = gv.get("sentence") or (data.get("en") or {}).get("fact") or data.get("fact", "")
    im = Image.new("RGB", (1400, 1800), (250, 246, 232))
    d = ImageDraw.Draw(im)
    d.text((700, 120), "POST OFFICE GUIDE - PART I", font=F(56), fill=(60, 50, 40), anchor="mm")
    d.text((700, 200), f"Clause {CLAUSE}  -  Method of Address", font=FR(46), fill=(90, 80, 70), anchor="mm")
    for k in range(4):                                     # aas-paas ki dhundhli lines
        d.rectangle((110, 330 + k * 70, 1290 - (k % 2) * 200, 352 + k * 70), fill=(205, 198, 182))
    f, s_, ls = M.fit_lines_f(sent, 1180, 7, 58, 40, FR) if hasattr(M, "fit_lines_f") else (FR(50), 50, [[sent]])
    y = 680
    for ln in ls:
        w_ = f.getlength(" ".join(ln))
        d.rectangle((105, y - 10, 115 + w_, y + s_ + 14), fill=(255, 232, 80))
        d.text((110, y), " ".join(ln), font=f, fill=(25, 25, 30))
        y += int(s_ * 1.45)
    for k in range(5):
        d.rectangle((110, y + 60 + k * 70, 1290 - (k % 3) * 150, y + 82 + k * 70), fill=(205, 198, 182))
    return im


def notes_card():
    im = card(1500, 760, (255, 248, 230), GOLD, 14, 50)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((50, 30, 700, 140), 40, fill=NAVY)
    d.text((375, 85), "1 लाइन नोट्स", font=F(66), fill=GOLD, anchor="mm")
    text_c(d, (750, 380), data.get("fact") or "", 1350, 86, 54, INK, 3)
    d.text((750, 680), "SAVE करो  •  स्क्रीनशॉट लो", font=F(58), fill=RED, anchor="mm")
    return im


def share_card():
    im = card(1500, 380, GRN, (255, 255, 255), 10, 70)
    d = ImageDraw.Draw(im)
    d.polygon([(330, 190), (200, 90), (200, 145), (90, 145), (90, 235), (200, 235), (200, 290)], fill="white")
    d.text((900, 130), "उस GDS साथी को भेजो", font=F(84), fill="white", anchor="mm")
    d.text((900, 255), "जो ये गलती करता है!", font=F(84), fill=(255, 235, 120), anchor="mm")
    return im


def mock_card():
    im = card(1500, 320, (255, 255, 255), GOLD, 12, 60)
    d = ImageDraw.Draw(im)
    d.text((750, 110), f"कमेंट करो:  {M.MOCK_KEYWORD}", font=F(104), fill=RED, anchor="mm")
    d.text((750, 240), "FREE मॉक टेस्ट — असली परीक्षा जैसे सवाल", font=F(60), fill=NAVY, anchor="mm")
    return im


def follow_card():
    im = card(1100, 180, RED, (255, 255, 255), 8, 90)
    ImageDraw.Draw(im).text((550, 90), "+ FOLLOW  @postal_wala", font=F(78), fill="white", anchor="mm")
    return im


def mark(kind):
    s = M.x_mark_sprite(600) if kind == "wrong" else M.check_sprite(600)
    return s


# ---------------- awaaz + timeline (bharosa v24 jaisa) ----------------
ep = data["episode"]
specs = [{"name": "ruko", "segs": [("r", B.V2_OPEN_GUIDE[ep % len(B.V2_OPEN_GUIDE)])]}]
wrong_i = max([i for i, pn in enumerate(story) if pn.get("mark") == "wrong"], default=None)
for i, pn in enumerate(story):
    specs.append({"name": f"s{i}", "segs": [(f"c{i}", pn.get("text") or "")]})
    if i == wrong_i:
        specs.append({"name": "galti", "segs": [("x", B.galti_line(part, data, pn))]})
specs.append({"name": "ans", "segs": [("a", ans_pn.get("text") or f"सही जवाब है, {data['correct_text']}!")]})
specs.append({"name": "guide2", "segs": [("g", B.V2_GUIDE_VOICE)]})
specs.append({"name": "end", "segs": [("e", B.V2_END_VOICE)]})
voices = M.make_voices(specs)
mins = {"guide2": 1.8, "galti": 2.6, "end": 3.2, "ans": 3.0}
tl, cur = [], 0.0
for sp, v in zip(specs, voices):
    a = B.clean_voice(v[0])
    vd = len(a) / M.SR
    nm = sp["name"]
    lead = 0.2 if nm in ("ans",) else 0.08
    dur = max(mins.get(nm, 1.6), lead + vd + 0.25)
    if nm == "ruko":
        nq = len((data.get("question") or "").split())
        dur = max(dur, min(5.0, 1.2 + 0.28 * nq))
    if nm == "galti":
        lead = 1.6
        dur = max(2.6, lead + vd + 0.25)
    sc = {"name": nm, "start": cur, "dur": dur, "lead": lead, "vd": vd, "audio": a,
          "text": " ".join(t for _, t in sp["segs"])}
    if nm.startswith("s") and nm[1:].isdigit():
        sc["wrong"] = story[int(nm[1:])].get("mark") == "wrong"
    tl.append(sc)
    cur += dur
total = cur
B.build_audio(tl, total, os.path.join(JOB, "audio.wav"))
print("TIMELINE:", " | ".join(f"{s['name']} {s['start']:.1f}+{s['dur']:.1f}" for s in tl), f"= {total:.1f}s")

# ---------------- har drishya ka plan ----------------
scenes = []
tex_q = save(q_board(), "q_board.png")
tex_stamp = save(B.stamp_img("परीक्षा का पक्का नियम", "PO Guide Part I"), "stamp_rule.png")
tex_galti = save(B.stamp_img("गलती!"), "stamp_galti.png")
tex_x, tex_ok = save(mark("wrong"), "mark_x.png"), save(mark("right"), "mark_ok.png")
for sc in tl:
    nm = sc["name"]
    item = {"name": nm, "dur": sc["dur"], "frames": int(math.ceil(sc["dur"] * FPS)), "lead": sc["lead"],
            "vd": sc["vd"], "text": sc["text"]}
    if nm == "ruko":
        item.update(kind="ruko", board=tex_q, stamp=tex_stamp, bhaiya=ch("bhaiya", "sochta"),
                    golu=ch("grahak", "sochta", "base"))
    elif nm.startswith("s") and nm[1:].isdigit():
        i = int(nm[1:])
        pn = story[i]
        who = ((pn.get("say") or {}).get("who") or "customer")
        say = (pn.get("say") or {}).get("text") or pn.get("text") or ""
        item.update(kind="story", idx=i, who=who, bubble=save(bubble(say, tail_left=(who != "postman")), f"bub_{i}.png"),
                    env=save(env_tex((pn.get("card") or {}).get("lines") or []), f"env_{i}.png"),
                    mark=(tex_x if pn.get("mark") == "wrong" else tex_ok if pn.get("mark") == "right" else ""),
                    t_mark=sc["lead"] + sc["vd"] - 0.15,
                    bhaiya=ch("bhaiya", "batata" if who == "postman" else "sochta"),
                    golu=ch("grahak", "sochta" if pn.get("mark") == "wrong" else "base"))
    elif nm == "galti":
        pn = story[wrong_i]
        item.update(kind="galti", env=save(env_tex((pn.get("card") or {}).get("lines") or []), "env_galti.png"),
                    stamp=tex_galti, bhaiya=ch("bhaiya", "chauka"), golu=ch("grahak", "udaas", "base"))
    elif nm == "ans":
        lines = [l for l in ((ans_pn.get("card") or {}).get("lines") or []) if l]
        if FOREIGN:                                   # videshi niyam -> Air Mail lifaafa + globe
            import b3d_texture
            lines = lines if len(lines) >= 3 else ["To,", "Mr. John Smith", "123, Main Road", "London, UK"]
            b3d_texture.make(os.path.join(TEX, "env_ans.png"), lines)
            env_rel = "tex/env_ans.png"
        else:
            env_rel = save(env_tex(lines), "env_ans.png")
        item.update(kind="ans", env=env_rel, foreign=FOREIGN, bhaiya=ch("bhaiya", "shabaash"),
                    golu=ch("grahak", "khush", "base"))
    elif nm == "guide2":
        item.update(kind="guide", page=save(guide_page(), "guide_page.png"))
    elif nm == "end":
        item.update(kind="end", notes=save(notes_card(), "notes.png"), share=save(share_card(), "share.png"),
                    mock=save(mock_card(), "mock.png"), follow=save(follow_card(), "follow.png"),
                    bhaiya=ch("bhaiya", "shabaash"))
    scenes.append(item)

json.dump({"fps": FPS, "total": total, "clause": CLAUSE, "part": PART + 1, "scenes": scenes,
           "fact": data.get("fact", "")},
          open(os.path.join(JOB, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("B3D_PLAN_READY", len(scenes), "drishya")
