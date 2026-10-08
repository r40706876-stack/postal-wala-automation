"""
PAKKE 5  (Format 3 - subah 9 baje wali reel)
=============================================
Ek reel = 5 tez sawal (4 option ke saath) + sochne ka timer. JAWAB REEL ME NAHI - sirf PIN comment me
(caption file ke neeche "PIN comment" taiyar milta hai). Aakhir me: "apne jawab comment karo: 1-B 2-A ...".

Content KABHI naya nahi gadha jaata: sirf clause_plans ke wo parts jo pehle se jaanch (auto_check)
pass kar chuke hain - wahi sawal, wahi sahi jawab. Isliye galat niyam ka khatra nahi.

Har reel ka hook alag "variant" (A/B/C) ghoomta hai aur generated_reels/pakke5/experiments.csv me
likha jaata hai - views/skip baad me bhar ke dekh sakte hain kaunsa hook chala.

Chalana:  python pakke5.py            (din me ek baar; dobara chalao to skip)
          DRY_RUN=1 python pakke5.py  (bina awaaz ke test, state nahi badalti)
          python pakke5.py --force    (aaj ki ban chuki ho tab bhi nayi)
"""
import csv
import datetime
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

import main as M

OUT_DIR = os.path.join(M.OUTPUT_DIR, "pakke5")
STATE = os.path.join(OUT_DIR, "state.json")
EXP_LOG = os.path.join(OUT_DIR, "experiments.csv")
N_ITEMS = int(os.getenv("PAKKE5_ITEMS", "5"))
THINK = 2.0            # sawal bolne ke baad options padhne + sochne ka samay (timer ring)
A_HOLD = 0.45          # jawab ke baad thehrav
HOOK_HOLD = 0.25
END_MIN = 2.6
MAX_LEN = 38.0         # isse lambi bane to sabse lamba sawal hata ke 4 karo
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# Hook variant (sach hi bolte hain - koi nakli daava nahi). Har reel agla variant.
HOOKS = [
    {"id": "A", "big": "ये {n} सवाल हल करो!", "small": "जवाब पिन कमेंट में मिलेंगे",
     "voice": "ये {n} सवाल हल करो, जवाब पिन कमेंट में!"},
    {"id": "B", "big": "{n} सवाल, आपका स्कोर?", "small": "{n} में से कितने आते हैं?",
     "voice": "{n} सवाल. देखते हैं आपके कितने सही होते हैं!"},
    {"id": "C", "big": "GDS से MTS: {n} सवाल", "small": "PO Guide से, सीधे परीक्षा के लिए",
     "voice": "GDS से MTS परीक्षा के, {n} सवाल. तैयार?"},
]


# ---------------------------------------------------------------- content

def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"used": [], "made": {}, "n": 0}


def save_state(st):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def clean(t):
    return " ".join(M.strip_brackets(str(t or "")).split()).strip()


def pool():
    """Jaanch-pass parts, clause ke kram me: (key, clause_no, title, question, answer)."""
    out = []
    files = [f for f in os.listdir(M.PLAN_DIR) if f.startswith("clause_") and f.endswith(".json")]
    for fn in sorted(files, key=lambda x: int(x.split("_")[1].split(".")[0])):
        try:
            with open(os.path.join(M.PLAN_DIR, fn), encoding="utf-8") as f:
                plan = json.load(f)
        except Exception:
            continue
        num = int(plan.get("clause_no") or fn.split("_")[1].split(".")[0])
        title = clean(plan.get("title_hi") or "")
        for i, p in enumerate(plan.get("parts") or []):
            if not p.get("auto_check"):
                continue                                  # sirf jaanch-pass (sahi) parts
            c = M.norm_correct(p.get("correct")).lower()
            q, a = clean(p.get("question")), clean(p.get(c) if c else "")
            opts = [clean(p.get(k)) for k in "abcd"]
            if not (q and a and all(opts)) or len(q.split()) > 18 or max(len(o.split()) for o in opts) > 7:
                continue                                  # bahut lamba - tez format me nahi
            out.append({"key": f"{num}:{i}", "clause": num, "title": title, "q": q, "a": a,
                        "opts": opts, "correct": c.upper(), "published": bool(p.get("published"))})
    return out


def pick_items(st):
    """Agle N na-use hue parts (pehle wo jo series me aa chuke). Sab use ho gaye to dobara shuru."""
    pl = pool()
    used = set(st.get("used") or [])
    fresh = [x for x in pl if x["key"] not in used]
    if len(fresh) < N_ITEMS:
        print("PAKKE5: saare parts ek baar aa chuke - dobara shuru se (naya round)")
        st["used"] = []
        st["round"] = int(st.get("round", 1)) + 1
        fresh = pl
    fresh.sort(key=lambda x: (not x["published"], x["clause"]))   # padhaye ja chuke pehle (kram wahi)
    return [shuffle_opts(x) for x in fresh[:N_ITEMS]]


def shuffle_opts(it):
    """Options ka kram badlo (sahi jawab wahi, akshar naya) - warna ek set me sab 'B' ho sakta hai.
    Kram key se tay (har baar same), sahi jawab ka text milaake naya akshar."""
    import random
    rnd = random.Random(it["key"])
    opts = list(it["opts"])
    rnd.shuffle(opts)
    if it["a"] not in opts:
        return it
    out = dict(it, opts=opts, correct="ABCD"[opts.index(it["a"])])
    return out


def topic_of(items):
    titles = {x["title"] for x in items if x["title"]}
    cls = sorted({x["clause"] for x in items})
    if len(titles) == 1:
        return titles.pop(), cls
    return "PO Guide Part I", cls


# ---------------------------------------------------------------- timing / voice

def make_specs(items, hk):
    n = len(items)
    specs = [{"name": "hook", "segs": [("hk", hk["voice"].format(n=n))]}]
    for i, it in enumerate(items):
        specs.append({"name": f"q{i}", "segs": [("q", it["q"])]})
    specs.append({"name": "end", "segs": [("e", "अपने जवाब कमेंट में लिखो. सही जवाब, पिन कमेंट में है!")]})
    return specs


def voice_len(v):
    return len(v[0]) / M.SR if v and v[0] is not None else 0.0


def timeline(specs, voices):
    tl, t = [], 0.0
    for sp, v in zip(specs, voices):
        vd = voice_len(v)
        if sp["name"] == "hook":
            d = max(1.6, vd + HOOK_HOLD)
        elif sp["name"].startswith("q"):
            d = vd + THINK
        else:
            d = max(END_MIN, vd + 0.6)
        tl.append({"name": sp["name"], "start": t, "dur": d, "vdur": vd})
        t += d
    return tl, t


def get_voices(specs):
    try:
        return M.make_voices(specs)
    except M.VoiceUnavailable:
        print("PAKKE5: Gemini awaaz nahi mili -> purani awaaz (Swara)")
        M._VOICE_FLAGS["allow_edge"] = True
        return M.make_voices(specs)


def build_audio(voices, tl, total, path):
    n = int(total * M.SR) + M.SR
    vt = np.zeros(n, dtype=np.float32)
    for sc, v in zip(tl, voices):
        if v and v[0] is not None:
            M.add_at(vt, v[0], sc["start"] + M.VOICE_LEAD)
    env = np.convolve(np.abs(vt), np.ones(int(0.15 * M.SR), dtype=np.float32) / int(0.15 * M.SR), mode="same")
    duck = 1.0 - np.clip(env * 6, 0, 0.6)
    buf = np.zeros(n, dtype=np.float32)
    bed = M.music_bed(n / M.SR)
    m = min(len(bed), n)
    buf[:m] += bed[:m] * duck[:m]
    for sc in tl:
        s, nm = sc["start"], sc["name"]
        if nm == "hook":
            M.add_at(buf, M.sfx_thud(0.8), s)
            M.add_at(buf, M.sfx_pop(0.45), s + 0.08)
        elif nm.startswith("q"):
            M.add_at(buf, M.sfx_whoosh(0.25, 0.3), max(0.0, s - 0.1))
            k = sc["vdur"] + 0.05
            while k < sc["dur"] - 0.1:                         # sochne ka tick-tick
                M.add_at(buf, M.sfx_tick(0.3), s + k)
                k += 0.3
        elif nm == "end":
            M.add_at(buf, M.sfx_pop(0.45), s)
    buf += vt
    peak = float(np.max(np.abs(buf))) or 1.0
    buf = buf / max(1.0, peak / 0.95)
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", str(M.SR), "-ac", "1", "-i", "-", path],
                   input=pcm.tobytes(), check=True)


# ---------------------------------------------------------------- drawing

def text_block(cv, text, cy, max_w, size, min_size, color, lines_max=4, stroke=0):
    f, s_, lines = M.fit_lines(text, max_w, lines_max, size, min_size)
    lh = int(s_ * 1.28)
    y0 = cy - (len(lines) - 1) * lh / 2
    d = ImageDraw.Draw(cv)
    for k, ln in enumerate(lines):
        d.text((M.W / 2, y0 + k * lh), " ".join(ln), font=f, fill=color, anchor="mm",
               stroke_width=stroke, stroke_fill=(5, 10, 22))
    return len(lines) * lh


def dots(cv, n, cur, done_upto, y):
    """Kitne sawal hue / baaki: 1-5 gol, abhi wala bada peela, ho chuke hare."""
    d = ImageDraw.Draw(cv)
    gap = 120
    x0 = M.W / 2 - gap * (n - 1) / 2
    f = M.get_font(40)
    for i in range(n):
        x = x0 + i * gap
        r = 42 if i == cur else 32
        if i < done_upto:
            col, fg = (120, 140, 175), M.WHITE              # ho chuka (sahi/galat ka ishaara nahi)
        elif i == cur:
            col, fg = M.YELLOW, (30, 20, 0)
        else:
            col, fg = (50, 64, 96), (170, 180, 200)
        d.ellipse((x - r, y - r, x + r, y + r), fill=col, outline=(255, 255, 255) if i == cur else None,
                  width=4 if i == cur else 0)
        d.text((x, y), str(i + 1), font=f, fill=fg, anchor="mm")


def answer_card(text, w=940):
    f, s_, lines = M.fit_lines(text, w - 200, 3, 70, 44)
    lh = int(s_ * 1.25)
    h = max(190, lh * len(lines) + 90)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=40, fill=(18, 110, 60, 255), outline=(120, 240, 160, 255),
                        width=6)
    ck = M.check_sprite(110)
    im.paste(ck, (40, int(h / 2 - 55)), ck)
    y0 = h / 2 - (len(lines) - 1) * lh / 2
    for k, ln in enumerate(lines):
        d.text((w / 2 + 70, y0 + k * lh), " ".join(ln), font=f, fill=M.WHITE, anchor="mm")
    return im


def think_ring(cv, x, y, k):
    """Sochne ka gol timer: k 0->1 me bharta hai."""
    d = ImageDraw.Draw(cv)
    r = 62
    d.ellipse((x - r, y - r, x + r, y + r), outline=(60, 76, 110), width=12)
    if k > 0.01:
        d.arc((x - r, y - r, x + r, y + r), -90, -90 + 360 * k, fill=M.YELLOW, width=12)
    d.text((x, y), "?", font=M.get_font(64), fill=M.YELLOW, anchor="mm")


def frame_hook(data, t):
    cv = M.bg_frame("red", t).convert("RGB")
    n, hk = len(data["items"]), data["hook"]
    M.place(cv, M.pill_sprite("GDS → MTS / POSTMAN / PA", 38, (30, 20, 0), M.YELLOW, M.ORANGE), M.W / 2, 150)
    # bada "5" - frame 0 se poora (thumbnail jaisa), halka dhadakta
    M.place(cv, M.glow_sprite(330, M.YELLOW, 90), M.W / 2, 640)
    d = ImageDraw.Draw(cv)
    pulse = 1.0 + 0.04 * math.sin(t * 8)
    big = M.get_font(int(470 * pulse))
    d.text((M.W / 2, 640), str(n), font=big, fill=M.YELLOW, anchor="mm", stroke_width=14, stroke_fill=(60, 10, 10))
    text_block(cv, hk["big"].format(n=n), 1090, 1000, 100, 64, M.WHITE, 2, stroke=9)
    text_block(cv, hk["small"].format(n=n), 1290, 980, 54, 40, (255, 225, 150), 2, stroke=6)
    tp = data["topic"]
    M.place(cv, M.pill_sprite(f"विषय: {tp}"[:46], 40, M.WHITE, (40, 56, 96), (110, 140, 200)), M.W / 2, 1450)
    dots(cv, n, -1, 0, 1640)
    return cv


def opt_tile(letter, text, w=480, h=190):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=30, fill=(28, 44, 82, 255), outline=(90, 130, 210, 255), width=4)
    d.ellipse((18, h / 2 - 34, 86, h / 2 + 34), fill=M.YELLOW + (255,))
    d.text((52, h / 2), letter, font=M.get_font(42), fill=(30, 20, 0), anchor="mm")
    f, s_, lines = M.fit_lines(text, w - 130, 2, 50, 32)
    lh = int(s_ * 1.22)
    y0 = h / 2 - (len(lines) - 1) * lh / 2
    for k, ln in enumerate(lines):
        d.text((100 + (w - 110) / 2, y0 + k * lh), " ".join(ln), font=f, fill=M.WHITE, anchor="mm")
    return im


def frame_item(data, i, t_in_q):
    """Sawal + 4 option. Jawab KABHI nahi dikhta (pin comment me)."""
    n = len(data["items"])
    it = data["items"][i]
    sc = data["_q_sc"]
    cv = M.bg_frame("blue", data["_gt"]).convert("RGB")
    M.place(cv, M.pill_sprite(f"सवाल {i + 1}/{n}", 46, (30, 20, 0), M.YELLOW, M.ORANGE), M.W / 2, 150)
    dots(cv, n, i, i, 290)
    k = M.ease_out_cubic(M.clamp(t_in_q / 0.25))
    lay = Image.new("RGBA", (M.W, 620), (0, 0, 0, 0))
    text_block(lay, it["q"], 310, 980, 84, 52, M.WHITE, 4, stroke=7)
    M.place(cv, lay, M.W / 2, 640 - 40 * (1 - k), alpha=k)
    for j, (L, o) in enumerate(zip("ABCD", it["opts"])):
        kj = M.ease_out_back(M.clamp((t_in_q - 0.15 - 0.08 * j) / 0.3))
        x = M.W / 2 + (-255 if j % 2 == 0 else 255)
        y = 1080 + (j // 2) * 220
        M.place(cv, opt_tile(L, o), x, y, scale=max(0.05, 0.85 + 0.15 * kj), alpha=M.clamp(kj * 1.5))
    left = sc["dur"] - t_in_q
    think_k = 1.0 - M.clamp(left / sc["dur"])
    think_ring(cv, M.W / 2, 1560, think_k)
    if left < 1.2:
        ImageDraw.Draw(cv).text((M.W / 2, 1690), "अपना जवाब चुनो!", font=M.get_font(50), fill=(255, 225, 150),
                                anchor="mm")
    src = f"PO Guide Part I, Clause {it['clause']}"
    ImageDraw.Draw(cv).text((M.W / 2, 1830), src, font=M.get_font(32), fill=(150, 165, 195), anchor="mm")
    return cv


def frame_end(data, t):
    n = len(data["items"])
    cv = M.bg_frame("purple", data["_gt"]).convert("RGB")
    dots(cv, n, -1, n, 260)
    k = M.ease_out_back(M.clamp(t / 0.3))
    M.place(cv, M.pill_sprite("जवाब कमेंट करो!", 96, (30, 20, 0), M.YELLOW, M.ORANGE), M.W / 2, 520,
            scale=max(0.05, k), angle=-3)
    eg = "  ".join(f"{j + 1}-?" for j in range(n))
    k2 = M.ease_out_back(M.clamp((t - 0.3) / 0.3))
    M.place(cv, M.pill_sprite(eg, 66, M.WHITE, (40, 56, 96), (110, 140, 200)), M.W / 2, 700, scale=max(0.05, k2))
    text_block(cv, "ऐसे लिखो: 1-B  2-A  3-D ...", 830, 960, 50, 38, (255, 225, 150), 1, stroke=5)
    k3 = M.ease_out_back(M.clamp((t - 0.6) / 0.3))
    M.place(cv, M.pill_sprite("सही जवाब: पिन कमेंट में", 70, M.WHITE, M.RED, (255, 150, 150)), M.W / 2, 1020,
            scale=max(0.05, k3))
    text_block(cv, "SAVE करो, परीक्षा से पहले दोहराना", 1160, 960, 50, 38, M.WHITE, 1, stroke=5)
    if M.host_ready():
        M.host_bubble(cv, "रोज़ सुबह 9 बजे नए 5 सवाल!", t, 0.8, 1560, "batata")
    else:
        text_block(cv, "रोज़ सुबह 9 बजे नए 5 सवाल!", 1560, 900, 52, 40, M.WHITE, 1)
    return cv


def render(data, tl, total, gt):
    data["_gt"] = gt
    si = 0
    while si + 1 < len(tl) and gt >= tl[si + 1]["start"]:
        si += 1
    sc = tl[si]
    t = gt - sc["start"]
    nm = sc["name"]
    if nm == "hook":
        return frame_hook(data, t)
    if nm == "end":
        return frame_end(data, t)
    data["_q_sc"] = sc
    return frame_item(data, int(nm[1:]), t)


def build_video(data, out):
    M.resolve_font()
    specs = make_specs(data["items"], data["hook"])
    print("PAKKE5: awaaz ban rahi hai...")
    voices = get_voices(specs)
    tl, total = timeline(specs, voices)
    while total > MAX_LEN and len(data["items"]) > 3:          # lambi ho gayi -> sabse lamba sawal hatao
        j = max(range(len(data["items"])), key=lambda k: len(data["items"][k]["q"]) + len(data["items"][k]["a"]))
        print(f"PAKKE5: reel {total:.1f}s > {MAX_LEN}s -> ek sawal kam ({data['items'][j]['key']})")
        data["items"].pop(j)
        specs = make_specs(data["items"], data["hook"])
        voices = get_voices(specs)
        tl, total = timeline(specs, voices)
    for sc in tl:
        print(f"  {sc['name']:<5} {sc['start']:5.2f}s  {sc['dur']:4.2f}s  voice {sc['vdur']:4.2f}s")
    apath = out.replace(".mp4", "_audio.wav")
    build_audio(voices, tl, total, apath)
    n_frames = int(math.ceil(total * M.FPS))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{M.W}x{M.H}",
           "-r", str(M.FPS), "-i", "-", "-i", apath, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264",
           "-preset", "medium", "-crf", str(M.VIDEO_CRF), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-shortest", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for fi in range(n_frames):
            proc.stdin.write(render(data, tl, total, fi / M.FPS).tobytes())
            if fi % 150 == 0:
                print(f"  frame {fi}/{n_frames}")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    ret = proc.wait()
    if os.path.exists(apath):
        os.remove(apath)
    if ret != 0:
        raise RuntimeError("ffmpeg fail")
    print(f"PAKKE5 BANI: {out} ({total:.1f}s)")
    return total


# ---------------------------------------------------------------- caption / log

def write_caption(data, path):
    n, items = len(data["items"]), data["items"]
    cls = ", ".join(str(c) for c in data["clauses"])
    pin = "  ".join(f"{k + 1}-{it['correct']}" for k, it in enumerate(items))
    lines = [
        f"GDS to MTS / Postman / PA परीक्षा | {data['topic']} के {n} सवाल | PO Guide Part I",
        "",
        f"{n} सवाल, अपने जवाब कमेंट में लिखो (जैसे 1-B 2-A ...)",
        "सही जवाब पिन कमेंट में 📌",
        "",
        f"📘 स्रोत: PO Guide Part I, Clause {cls}",
        "🔖 SAVE करो - परीक्षा से पहले एक बार दोहराना",
        f"🎯 FREE MOCK TEST चाहिए? कमेंट करें: {M.MOCK_KEYWORD}",
        "🔔 रोज़ सुबह 9 बजे नए 5 सवाल | शाम को PO Guide का एक नियम विस्तार से",
        "",
        M.HASHTAGS + " #gdsexam #postalexam",
        "",
        "----- PIN करने वाला पहला कमेंट (reel डालने के 1 घंटे बाद पिन करें) -----",
        f"✅ सही जवाब: {pin}",
        *[f"{k + 1}. {it['q']} → {it['correct']}) {it['a']}" for k, it in enumerate(items)],
        f"आपके कितने सही हुए? __/{n} लिखो 👇",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("Caption:", path)


def log_experiment(data, out, total):
    new = not os.path.exists(EXP_LOG)
    with open(EXP_LOG, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["post_date", "file", "format", "hook_variant", "items", "clauses", "length_sec",
                        "views", "skip_rate", "avg_watch_sec", "saves", "shares", "comments", "follows"])
        w.writerow([data["post_date"], os.path.basename(out), "pakke5", data["hook"]["id"], len(data["items"]),
                    " ".join(str(c) for c in data["clauses"]), f"{total:.1f}", "", "", "", "", "", "", ""])


# ---------------------------------------------------------------- run

def post_date_now():
    """Shaam 3 baje ke baad bane to KAL subah 9 baje ki reel (raat me taiyar mile)."""
    now = datetime.datetime.now(IST)
    d = now.date() + datetime.timedelta(days=1 if now.hour >= 15 else 0)
    return d.isoformat()


def run(force=False):
    os.makedirs(OUT_DIR, exist_ok=True)
    st = load_state()
    pdate = post_date_now()
    if pdate in (st.get("made") or {}) and not force and not M.DRY_RUN:
        print(f"PAKKE5: {pdate} ki reel pehle se bani hai ({st['made'][pdate]}) - skip")
        return
    items = pick_items(st)
    if len(items) < 3:
        print("PAKKE5: jaanch-pass parts kam hain - reel nahi")
        return
    topic, cls = topic_of(items)
    hk = HOOKS[int(st.get("n", 0)) % len(HOOKS)]
    data = {"items": items, "hook": hk, "topic": topic, "clauses": cls, "post_date": pdate}
    print(f"PAKKE5 {pdate} | hook {hk['id']} | vishay: {topic} | parts: {[x['key'] for x in items]}")
    out = os.path.join(OUT_DIR, f"pakke5_{pdate}.mp4")
    k = 2
    while os.path.exists(out) and not M.DRY_RUN:
        out = os.path.join(OUT_DIR, f"pakke5_{pdate}_v{k}.mp4")
        k += 1
    total = build_video(data, out)
    data["clauses"] = sorted({x["clause"] for x in data["items"]})
    write_caption(data, out.replace(".mp4", "_caption.txt"))
    if M.DRY_RUN:
        return
    st.setdefault("used", []).extend(x["key"] for x in data["items"])
    st.setdefault("made", {})[pdate] = os.path.basename(out)
    st["n"] = int(st.get("n", 0)) + 1
    save_state(st)
    log_experiment(data, out, total)


if __name__ == "__main__":
    try:
        run(force="--force" in sys.argv[1:])
    except Exception as exc:                      # series wali reel kabhi na ruke
        print(f"PAKKE5 nahi bani ({type(exc).__name__}: {str(exc)[:200]}) - agli run me dobara")
