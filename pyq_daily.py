"""
POSTAL WALA - ROZ KI 2 PYQ REEL (v22, 2026-10-23)
=================================================
  python pyq_daily.py am   -> subah 8 baje wali: 7 asli PYQ quiz (pehle 1 bada sawal -> zoom-out me 7),
                              5 sec ghadi, fir 1.5 sec me sahi jawab hare ✓ se, loop (~6.5s)
  python pyq_daily.py pm   -> raat 9 baje wali: "डाक विभाग के 7 PYQ" copy-panna (sawal + Ans), 4 sec loop
                              + usi ka 9 slide CAROUSEL (cover + 7 sawal + SAVE/kament slide)
  python pyq_daily.py bank -> sirf sawal-bank badhao (papers se)
  --force  : aaj ki ban chuki ho tab bhi dobara
  DRY_RUN=1: test (state/bank nahi badalta, AI nahi)

SAWAL KAHAN SE: pyq_papers/ ke asli papers (paper_index) -> sirf saaf padhe gaye sawal (4 option a-d) ->
  JAWAB HAMESHA paper ki ANSWER KEY se (key_map), AI kabhi jawab nahi chunta. AI (Gemini) sirf Hindi anuvaad karta hai
  aur maths/reasoning/English/chitra wale sawal hatata hai. Anuvaad me option ka kram wahi; ank (number) jaanch code me.
"""
import datetime
import hashlib
import json
import math
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

import pyq_reel as P

M = P.M
W, H, FPS = 1080, 1920, 30
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
VERSION = "pyq_daily v22 (2026-10-23): 8 AM 7-PYQ quiz + 9 PM copy-panna 7 PYQ + carousel"

OUT_DIR = os.path.join(M.OUTPUT_DIR, "pyq")
STATE = os.path.join(OUT_DIR, "daily_state.json")
N_Q = 7
BANK_MIN_FREE = 28            # itne se kam naye (bina use) sawal bache -> bank badhao
BANK_BATCH = 12               # ek AI call me itne sawal
BANK_MAX_CALLS = 3            # ek run me itni AI calls (credit bachat)

NAVY, GOLD, GOLD_L, GREYT, LINEC, RED = P.NAVY, P.GOLD, P.GOLD_L, P.GREYT, P.LINEC, P.RED
GRN = (22, 150, 80)
INK, PAPER_C, PEN_BLUE, PEN_RED, WHITE = (22, 24, 34), (252, 250, 242), (24, 70, 190), (200, 30, 40), (248, 250, 252)

BAD_ANS = re.compile(r"उपरोक्त|इनमें से|इनमे से|दोनों|सभी|कोई नहीं|उपर्युक्त")


# ============================================================ state / bank

def today():
    return datetime.datetime.now(IST).date().isoformat()


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        st = {"used": [], "am": {}, "pm": {}}
        try:                                         # purani 3-sawal reel me aa chuke sawal = 'used'
            old = P.load_state()
            for k in old.get("done_sets") or []:
                st["used"] += [i for i in k.split("|") if i not in st["used"]]
        except Exception:
            pass
        return st


def save_state(st):
    if M.DRY_RUN:
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def read_bank():
    with open(P.BANK, encoding="utf-8") as f:
        return json.load(f)


def write_bank(b):
    if M.DRY_RUN:
        return
    with open(P.BANK, "w", encoding="utf-8") as f:
        json.dump(b, f, ensure_ascii=False, indent=1)


def bank_items():
    out = []
    for x in read_bank().get("items") or []:
        if x.get("ans") in ("A", "B", "C", "D") and len(x.get("opts") or []) == 4 and x.get("q"):
            out.append(x)
    return out


# ============================================================ bank builder (papers -> jaancha hua sawal)

_OPT = re.compile(r"(?:^|\s)\(?([a-dA-D])\s*[\).:]\s+")
_JUNK = re.compile(r"(?i)question paper|postal ?a ?b ?c|\b[a-d]\)|[ऀ-ॿ]")


def _sig(q):
    return " ".join(re.findall(r"[a-z0-9]+", q.lower())[:14])


def paper_candidates():
    """Saaf padhe gaye sawal (4 option a-d, chhote) + answer key. Wahi sawal kai paper me -> exams jod do."""
    groups = {}
    for c in P.paper_index():
        if not c.get("trust"):
            continue
        key = P.key_map(c["file"]).get(int(c["no"]))
        if key not in ("A", "B", "C", "D"):
            continue
        t, seq = c["text"], []
        for m in _OPT.finditer(t):
            if len(seq) < 4 and m.group(1).lower() == "abcd"[len(seq)]:
                seq.append(m)
        if len(seq) != 4:
            continue
        q = t[:seq[0].start()].strip()
        opts = [t[seq[i].end():(seq[i + 1].start() if i < 3 else len(t))].strip(" ;,.") for i in range(4)]
        if len(q) < 15 or _JUNK.search(q) or any(not o or len(o) > 60 or _JUNK.search(o) for o in opts):
            continue
        g = groups.setdefault(_sig(q), {"q_en": q, "opts_en": opts, "keys": set(), "exams": [], "src": []})
        g["keys"].add(key)
        if c["exam"] not in g["exams"]:
            g["exams"].append(c["exam"])
        g["src"].append(f"{c['file']}#Q{c['no']}")
    out = []
    for sig, g in groups.items():
        if len(g["keys"]) != 1:                      # do paper ki key alag -> bharosa nahi
            continue
        g["ans"] = next(iter(g["keys"]))
        g["id"] = "p_" + hashlib.md5(sig.encode()).hexdigest()[:10]
        out.append(g)
    out.sort(key=lambda g: (-len(g["exams"]), g["id"]))
    return out


TR_PROMPT = """You prepare REAL previous-year questions of the India Post departmental exam (GDS to MTS / Postman / PA)
for Hindi Instagram reels. For EACH item below:
1. "keep": true only if it is a postal / India Post / PO Guide / postal-GK question (rules, articles, services,
   offices, schemes, history of the department, Post Office Savings, PLI, Speed Post etc.).
   false for: maths, reasoning, English grammar, computer, general science, questions that need a picture, a passage
   or "match the following", and questions whose answer is likely outdated (rates, limits that change).
2. "key_doubt": true if the given ANSWER (letter) is clearly wrong as per India Post rules (we then skip it).
3. "q": natural, simple Hindi translation of the question (Devanagari; keep terms like PIN, VP, RLO, PLI, MTS as is).
4. "opts": the 4 options translated to Hindi IN THE SAME ORDER (A, B, C, D). Never reorder, merge or change meaning.
   Keep every number exactly. Short words; English abbreviations may stay.
5. "list_q": the same question in at most 12 Hindi words (for a quick revision list), or "" if not possible.
6. "list_a": the correct answer (the given letter's option) in at most 4 Hindi words, or "".
Do not add facts. Do not answer from your own knowledge - the answer letter is fixed by the official key.

ITEMS:
{items}

Return ONLY JSON: {{"items": [{{"id": "", "keep": true, "key_doubt": false, "q": "", "opts": ["", "", "", ""],
"list_q": "", "list_a": ""}}]}}
"""


def _digits(s):
    return re.findall(r"\d+", s or "")


def grow_bank(need_free=BANK_MIN_FREE, st=None):
    """Bina-use sawal kam hon -> papers se agle sawal Hindi me (jawab key se). Ek run me BANK_MAX_CALLS tak."""
    st = st or load_state()
    b = read_bank()
    have = {x["id"] for x in b.get("items") or []}
    skip = set(b.get("rejected") or [])
    used = set(st.get("used") or [])
    free = [x for x in b.get("items") or [] if x["id"] not in used]
    if len(free) >= need_free:
        return 0
    todo = [g for g in paper_candidates() if g["id"] not in have and g["id"] not in skip]
    if not todo:
        print("Bank: papers ke saare saaf sawal le liye gaye - naye papers pyq_papers/ me daaliye")
        return 0
    if M.DRY_RUN:
        print(f"Bank (DRY_RUN): {len(todo)} naye paper-sawal taiyar, AI anuvaad nahi chalaya")
        return 0
    added = 0
    for call in range(BANK_MAX_CALLS):
        batch = todo[call * BANK_BATCH:(call + 1) * BANK_BATCH]
        if not batch:
            break
        txt = "\n".join(json.dumps({"id": g["id"], "question": g["q_en"], "A": g["opts_en"][0], "B": g["opts_en"][1],
                                    "C": g["opts_en"][2], "D": g["opts_en"][3], "answer": g["ans"]},
                                   ensure_ascii=False) for g in batch)
        try:
            res = M._llm_json(TR_PROMPT.format(items=txt), only="gemini") if M.GEMINI_API_KEY \
                else M._llm_json(TR_PROMPT.format(items=txt))
        except Exception as exc:
            print("Bank: AI anuvaad nahi hua (agli run me):", str(exc)[:150])
            break
        by = {g["id"]: g for g in batch}
        got = {str(x.get("id")): x for x in (res or {}).get("items") or [] if isinstance(x, dict)}
        for gid, g in by.items():
            x = got.get(gid)
            if not x:
                continue                                 # jawab nahi aaya -> agli baar
            opts = [" ".join(str(o).split()) for o in (x.get("opts") or [])]
            q = " ".join(str(x.get("q") or "").split())
            why = ""
            if not x.get("keep"):
                why = "postal nahi / chitra / maths"
            elif x.get("key_doubt"):
                why = "key pe shak"
            elif len(opts) != 4 or not all(opts) or not re.search(r"[ऀ-ॿ]", q):
                why = "anuvaad adhoora"
            elif any(_digits(e) != _digits(h) for e, h in zip(g["opts_en"], opts)) or \
                    _digits(g["q_en"]) and sorted(_digits(g["q_en"])) != sorted(_digits(q)):
                why = "anuvaad me ank badle"
            elif len(set(opts)) < 4:
                why = "do option ek jaise"
            if why:
                b.setdefault("rejected", []).append(gid)
                continue
            b.setdefault("items", []).append({
                "id": gid, "q": q, "opts": opts, "ans": g["ans"], "exams": g["exams"], "q_en": g["q_en"],
                "src": g["src"][:3], "list_q": " ".join(str(x.get("list_q") or "").split()),
                "list_a": " ".join(str(x.get("list_a") or "").split()), "auto": VERSION.split(" ")[1]})
            added += 1
        write_bank(b)
    print(f"Bank: {added} naye jaanche sawal jude (jawab = paper ki answer key)")
    return added


# ============================================================ chunav (selection)

def quiz_fit(it):
    """8 AM card me sawal 2 line aur chaaron option ek line me (bina kate) aate hain?"""
    f, s_, ls = M.fit_lines(it["q"], 790, 2, 38, 28)
    if sum(len(x) for x in ls) < len(it["q"].split()):                 # 2 line me poora nahi aaya
        return False
    fo, fb = M.get_font_reg(29), M.get_font(29)
    w = sum(26 + fo.getlength(o) + 34 for o in it["opts"]) + 60
    return w <= 790 and all(fb.getlength(o) < 300 for o in it["opts"])


def list_pair(it):
    """9 PM copy-panne ki line: (sawal, jawab) ya None."""
    a = it.get("list_a") or P.ans_text(it)
    q = it.get("list_q") or it["q"]
    if len(q.split()) > 14 or len(a.split()) > 4 or BAD_ANS.search(a) or re.search(r"नहीं|गलत|असत्य|निम्न", q):
        return None
    return q, a


def pick(st, ok, n=N_Q, avoid=()):
    items = [x for x in bank_items() if ok(x) and x["id"] not in avoid]
    used = list(st.get("used") or [])
    fresh = [x for x in items if x["id"] not in used]
    fresh.sort(key=lambda x: (-len(x.get("exams") or []), x["id"]))
    out = fresh[:n]
    if len(out) < n:                                 # naye khatam -> sabse purane dohrao (revision)
        old = sorted((x for x in items if x["id"] in used and x not in out), key=lambda x: used.index(x["id"]))
        out += old[:n - len(out)]
        if len(out) and len(fresh) < n:
            print(f"  Sirf {len(fresh)} naye sawal the - {n - len(fresh)} purane dohraaye (bank badhaiye)")
    return out


def mark_used(st, items):
    for x in items:
        if x["id"] in st["used"]:
            st["used"].remove(x["id"])
        st["used"].append(x["id"])


# ============================================================ audio helpers

def encode(frame_fn, n_frames, wav, out, static=False):
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", wav, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium",
           "-crf", str(M.VIDEO_CRF), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        last = None
        for fi in range(n_frames):
            if not (static and last is not None):
                last = frame_fn(fi / FPS).convert("RGB").tobytes()
            proc.stdin.write(last)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg fail")


def write_wav(buf, path):
    peak = float(np.max(np.abs(buf))) or 1.0
    buf = buf / max(1.0, peak / 0.95)
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", str(M.SR), "-ac", "1", "-i", "-", path],
                   input=pcm.tobytes(), check=True)


def beat_music(dur, seed=7):
    """Loop-wali beat (4 sec = 8 beat, jod pe jhatka nahi) - MinuteMe list jaisi."""
    SR = M.SR
    out = np.zeros(int(dur * SR), dtype=np.float32)
    rng = np.random.default_rng(seed)

    def add(sig, s, g):
        i = int(s * SR)
        e = min(len(out), i + len(sig))
        if e > i:
            out[i:e] += (sig[:e - i] * g).astype(np.float32)
    kt = np.arange(int(0.25 * SR)) / SR
    kick = np.sin(2 * math.pi * np.cumsum(55 + 110 * np.exp(-kt * 30)) / SR) * np.exp(-kt * 9)
    ht = np.arange(int(0.05 * SR)) / SR
    hat = rng.normal(0, 1, len(ht)) * np.exp(-ht * 90)
    for bt in range(int(round(dur / 0.5))):
        add(kick, bt * 0.5, 0.55)
        add(hat, bt * 0.5 + 0.25, 0.10)
    roots = [[110.0, 130.81, 164.81], [98.0, 123.47, 146.83], [87.31, 110.0, 130.81], [98.0, 123.47, 146.83]]
    for k in range(int(round(dur / 2))):
        ch = roots[k % 4]
        tt = np.arange(int(2 * SR)) / SR
        env = np.minimum(1, tt / 0.05) * np.minimum(1, (2 - tt) / 0.08)
        seg = (sum(np.sin(2 * math.pi * f * 2 * tt) for f in ch) / 3 * 0.07
               + np.sin(2 * math.pi * ch[0] / 2 * tt) * 0.10) * env
        add(seg, k * 2, 1.0)
    return out / (float(np.max(np.abs(out))) or 1.0) * 0.8


# ============================================================ 8 AM: 7 sawal quiz

AM_END = 5.0           # ghadi khatam -> jawab
AM_DUR = 6.5
INTRO, ZOOM = 1.0, 0.35
CX0, CW, CH, GAP, Y0 = 40, 920, 166, 10, 300
AM_VOICE = "GDS साथियो! पाँच सेकंड, सात असली सवाल!"


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


class Quiz:
    def __init__(self, items):
        self.items = items
        self.cache = {}

    def card(self, i, hot, rev):
        k = (i, hot, rev)
        if k in self.cache:
            return self.cache[k]
        it = self.items[i]
        c = P.shadow_card(CW, CH, r=26, border=(GRN if rev else GOLD if hot else LINEC), bw=(5 if (hot or rev) else 2),
                          sh=12, sh_a=20).copy()
        pad = 24
        d = ImageDraw.Draw(c)
        cx, cy = pad + 52, pad + 58
        d.ellipse((cx - 32, cy - 32, cx + 32, cy + 32), fill=(GOLD if hot else NAVY))
        d.text((cx, cy), str(i + 1), font=M.get_font(40), fill=(NAVY if hot else GOLD_L), anchor="mm")
        f, s_, ls = M.fit_lines(it["q"], CW - 130, 2, 38, 28)
        step = int(s_ * 1.2)
        y = pad + 36 if len(ls) == 1 else pad + 22
        for kk, ln in enumerate(ls):
            d.text((pad + 104, y + kk * step), " ".join(ln), font=f, fill=NAVY, anchor="lm")
        fo, fb = M.get_font_reg(29), M.get_font(29)
        x, yo = pad + 104, pad + CH - 40
        for L, o in zip("ABCD", it["opts"]):
            if rev and L == it["ans"]:
                w = 26 + fb.getlength(o) + 56
                d.rounded_rectangle((x - 12, yo - 24, x + w, yo + 24), 24, fill=GRN)
                d.text((x, yo), L, font=fb, fill=(255, 255, 255), anchor="lm")
                d.text((x + 26, yo), o, font=fb, fill=(255, 255, 255), anchor="lm")
                tx = x + w - 34
                d.line((tx, yo, tx + 7, yo + 8, tx + 20, yo - 9), fill=(255, 255, 255), width=5, joint="curve")
                x += w + 24
                continue
            d.text((x, yo), L, font=fb, fill=((200, 200, 200) if rev else GOLD), anchor="lm")
            x += 26
            d.text((x, yo), o, font=fo, fill=((190, 194, 204) if rev else GREYT), anchor="lm")
            x += fo.getlength(o) + 34
        self.cache[k] = c
        return c

    def big(self):
        if "big" in self.cache:
            return self.cache["big"]
        it = self.items[0]
        w, h = 980, 760
        c = P.shadow_card(w, h, r=40, border=GOLD, bw=6, sh=20, sh_a=30).copy()
        pad = 40
        d = ImageDraw.Draw(c)
        d.rounded_rectangle((pad + 40, pad + 36, pad + 250, pad + 100), 32, fill=NAVY)
        d.text((pad + 145, pad + 68), f"सवाल 1/{len(self.items)}", font=M.get_font(36), fill=GOLD_L, anchor="mm")
        ex = it.get("exams") or []
        if ex:
            d.text((pad + w - 40, pad + 68), (f"{len(ex)} पेपरों में आया" if len(ex) > 1 else f"पेपर: {ex[0]}"),
                   font=M.get_font(34), fill=(160, 110, 0), anchor="rm")
        f, s_, ls = M.fit_lines(it["q"], w - 100, 3, 78, 54)
        step = int(s_ * 1.25)
        for kk, ln in enumerate(ls):
            d.text((pad + w / 2, pad + 200 + kk * step), " ".join(ln), font=f, fill=NAVY, anchor="mm")
        oy = pad + 230 + len(ls) * step
        for j, (L, o) in enumerate(zip("ABCD", it["opts"])):
            x, y = pad + 40 + (j % 2) * 460, oy + (j // 2) * 130
            d.rounded_rectangle((x, y, x + 420, y + 110), 26, fill=(246, 244, 238), outline=LINEC, width=3)
            d.ellipse((x + 22, y + 25, x + 82, y + 85), fill=NAVY)
            d.text((x + 52, y + 55), L, font=M.get_font(36), fill=GOLD_L, anchor="mm")
            fo2, so2, lo2 = M.fit_lines(o, 300, 2, 48, 28)
            st2 = int(so2 * 1.1)
            for kk, ln in enumerate(lo2):
                d.text((x + 104, y + 55 + (kk - (len(lo2) - 1) / 2) * st2), " ".join(ln), font=fo2, fill=NAVY,
                       anchor="lm")
        self.cache["big"] = c
        return c

    def frame(self, t):
        n = len(self.items)
        cv = P.paper_bg().copy().convert("RGBA")
        P.TXT["top"] = "रुको! स्क्रीन रोको और 7 सवाल हल करो" if t < AM_END else "जवाब मिलाओ!  रोको और देखो"
        P.header(cv, 1 - min(1, t / AM_END), 0, 1)
        d = ImageDraw.Draw(cv)
        d.rectangle((176, 106, 760, 142), fill=(255, 255, 255))
        d.text((180, 124), "PYQ टेस्ट सीरीज़ · GDS से MTS / Postman", font=M.get_font_reg(30), fill=GREYT, anchor="lm")
        if t < INTRO + ZOOM:
            k = ease((t - INTRO) / ZOOM)
            if k < 1:
                a = int(255 * (1 - k))
                d.text((540, 380), "सिर्फ GDS से MTS / Postman वालों के लिए", font=M.get_font(44), fill=RED + (a,),
                       anchor="mm")
                d.text((540, 470), f"{n} असली सवाल  •  5 सेकंड", font=M.get_font(64), fill=NAVY + (a,), anchor="mm")
            for i in range(1, n):
                kk = ease((t - INTRO - (i - 1) * 0.03) / ZOOM)
                if kk > 0:
                    cv.alpha_composite(self.card(i, False, False),
                                       (CX0 - 24, int(Y0 + i * (CH + GAP) - 24 + (1 - kk) * 700)))
            if k < 1:
                big = self.big()
                tw = int(big.width * (1 - k) + (CW + 48) * k)
                th = int(big.height * (1 - k) + (CH + 48) * k)
                pop = 1.0 if t > 0.12 else 0.85 + 0.15 * ease(t / 0.12)
                bb = big.resize((max(1, int(tw * pop)), max(1, int(th * pop))))
                cx = 540 * (1 - k) + (CX0 + CW / 2) * k
                cy = 1050 * (1 - k) + (Y0 + CH / 2) * k
                cv.alpha_composite(bb, (int(cx - bb.width / 2), int(cy - bb.height / 2)))
            else:
                cv.alpha_composite(self.card(0, True, False), (CX0 - 24, Y0 - 24))
        else:
            hot = 1 + int((t - INTRO - ZOOM) / ((AM_END - INTRO - ZOOM) / (n - 1))) if t < AM_END else -1
            for i in range(n):
                rev = t >= AM_END + i * 0.08
                cv.alpha_composite(self.card(i, i == hot, rev), (CX0 - 24, Y0 + i * (CH + GAP) - 24))
            d = ImageDraw.Draw(cv)
            y = Y0 + n * (CH + GAP) + 4
            if t < AM_END:
                d.rounded_rectangle((40, y, 960, y + 76), 38, fill=NAVY)
                d.text((500, y + 38), "जवाब 5 सेकंड में आएँगे... तैयार?", font=M.get_font(36), fill=GOLD_L, anchor="mm")
            else:
                d.rounded_rectangle((40, y, 960, y + 76), 38, fill=GRN)
                d.text((500, y + 38), f"कितने सही? स्कोर कमेंट करो: __/{n}", font=M.get_font(38), fill=(255, 255, 255),
                       anchor="mm")
        return cv


def am_audio(path):
    n = int(AM_DUR * M.SR)
    buf = np.zeros(n, dtype=np.float32)
    bed = M.music_bed(AM_DUR)
    m = min(n, len(bed))
    buf[:m] += bed[:m] * 0.55
    try:
        vs = P.get_voices([{"name": "h", "segs": [("h", AM_VOICE)]}])
        v = M.speed_voice(vs[0][0], 1.12)
        M.add_at(buf, v, 0.08)
    except Exception as exc:
        print("  8 AM awaaz nahi bani (sirf sangeet):", str(exc)[:120])
    for k in range(1, int(AM_END)):
        M.add_at(buf, M.sfx_tick(0.35), float(k))
    for i in range(N_Q):
        M.add_at(buf, M.sfx_pop(0.3), AM_END + i * 0.08)
    M.add_at(buf, M.sfx_ding(0.4), AM_END + 0.6)
    write_wav(buf, path)


def am_caption(items, path):
    n = len(items)
    pin = "  ".join(f"{k + 1}-{it['ans']}" for k, it in enumerate(items))
    ex_all = sorted({e for it in items for e in it.get("exams") or []})
    lines = [
        f"⏱ 5 सेकंड, {n} असली PYQ — कितने सही? | GDS से MTS / Postman / PA परीक्षा",
        "",
        f"रील रोको, हल करो, फिर जवाब मिलाओ ✅  अपना स्कोर कमेंट करो: __/{n}",
        "📝 पिछले सालों के असली विभागीय पेपर से (" + ", ".join(ex_all[:6]) + (" ..." if len(ex_all) > 6 else "") + ")",
        "🎨 शाम 5 बजे: PO Guide का नियम चित्रों से  •  📒 रात 9 बजे: 7 PYQ की revision list",
        f"🎯 FREE MOCK TEST चाहिए? कमेंट करें: {M.MOCK_KEYWORD}",
        "",
        M.HASHTAGS,
        "",
        "----- PIN करने वाला पहला कमेंट -----",
        f"स्कोर लिखो __/{n} 👇  सबसे पहले {n}/{n} वाले का कमेंट PIN होगा!",
        f"✅ जवाब: {pin}",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run_am(force=False):
    st = load_state()
    d0 = today()
    if d0 in st["am"] and not force and not M.DRY_RUN:
        print(f"8 AM: {d0} ki reel pehle se bani ({st['am'][d0]}) - skip")
        return
    grow_bank(st=st)
    items = pick(st, quiz_fit)
    if len(items) < N_Q:
        print(f"8 AM: sirf {len(items)} sawal fit hue - aaj reel nahi (bank badhne do)")
        return
    items.sort(key=lambda x: (-len(x.get("exams") or []), len(x["q"])))   # pehla = sabse chhota + sabse zyada paper
    first = min(items[:3], key=lambda x: len(x["q"]))
    items.remove(first)
    items.insert(0, first)
    print("8 AM sawal:", [x["id"] for x in items])
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"pyq_8am_{d0}.mp4")
    wav = out.replace(".mp4", "_a.wav")
    am_audio(wav)
    qz = Quiz(items)
    encode(qz.frame, int(AM_DUR * FPS), wav, out)
    os.remove(wav)
    am_caption(items, out.replace(".mp4", "_caption.txt"))
    print(f"8 AM REEL BANI: {out}")
    if M.DRY_RUN:
        return
    mark_used(st, items)
    st["am"][d0] = os.path.basename(out)
    save_state(st)


# ============================================================ 9 PM: copy-panna 7 PYQ + carousel

PM_DUR = 4.0


def notebook_bg(w, h, top=200):
    im = Image.new("RGB", (w, h), PAPER_C)
    d = ImageDraw.Draw(im)
    for y in range(top, h - 120, 56):
        d.line((0, y, w, y), fill=(200, 215, 240), width=2)
    d.line((110, 0, 110, h), fill=(240, 150, 150), width=3)
    return im


def pm_hook(items):
    rep = sum(1 for it in items if len(it.get("exams") or []) >= 2)
    return f"इनमें से {rep} सवाल 2+ पेपरों में आ चुके हैं!" if rep >= 2 else "परीक्षा से पहले ये 7 ज़रूर देख लो!"


def pm_frame(items, pairs):
    cv = notebook_bg(W, H)
    d = ImageDraw.Draw(cv)
    hk = pm_hook(items)
    fh = next((M.get_font(z) for z in (50, 46, 42, 38) if M.get_font(z).getlength(hk) + 70 <= W - 140), M.get_font(36))
    wh = fh.getlength(hk) + 70
    d.rounded_rectangle((W / 2 - wh / 2 + 6, 126, W / 2 + wh / 2 + 6, 196), radius=18, fill=(120, 10, 20))
    d.rounded_rectangle((W / 2 - wh / 2, 120, W / 2 + wh / 2, 190), radius=18, fill=PEN_RED)
    d.text((W / 2, 155), hk, font=fh, fill=WHITE, anchor="mm")
    d.text((W / 2, 245), f"डाक विभाग के {len(pairs)} PYQ", font=M.get_font(84), fill=PEN_BLUE, anchor="mm")
    d.line((200, 300, W - 200, 300), fill=PEN_BLUE, width=5)
    d.text((W / 2, 335), "असली पिछले पेपर  •  SAVE करो", font=M.get_font(34), fill=PEN_RED, anchor="mm")
    ex = "GDS से MTS  •  Postman  •  PA/SA  •  सभी सर्किल"
    fe = M.get_font(32)
    we = fe.getlength(ex) + 40
    d.rounded_rectangle((W / 2 - we / 2, 357, W / 2 + we / 2, 397), radius=20, fill=(18, 32, 72))
    d.text((W / 2, 377), ex, font=fe, fill=(255, 225, 90), anchor="mm")
    top, bottom = 420, 1540
    for size in (42, 40, 38, 36, 34, 32):
        blocks = []
        for k, (q, a) in enumerate(pairs):
            f, s_, lines = M.fit_lines(f"{k + 1}. {q}", 900, 2, size, size)
            blocks.append((f, int(s_ * 1.22), lines[:2], a))
        need = sum(lh * len(ls) + int(size * 1.35) for _, lh, ls, _ in blocks)
        if need + 14 * (len(pairs) - 1) <= bottom - top:
            break
    gap = max(0, (bottom - top - need) / max(1, len(pairs) - 1))
    y, fa = top, M.get_font(size + 2)
    for f, lh, lines, ans in blocks:
        for j, ln in enumerate(lines):
            d.text((140, y + j * lh), " ".join(ln), font=f, fill=INK, anchor="la")
        y += lh * len(lines) + 2
        d.text((175, y), "Ans :  ", font=fa, fill=PEN_BLUE, anchor="la")
        d.text((175 + fa.getlength("Ans :  "), y), ans, font=fa, fill=PEN_BLUE, anchor="la")
        y += int(size * 1.35) + gap
    cv = cv.convert("RGBA")
    M.place(cv, P.stamp_logo(64), 190, 1632, angle=-4)
    d = ImageDraw.Draw(cv)
    d.text((245, 1618), "@postal_wala", font=M.get_font(36), fill=INK, anchor="lm")
    d.text((245, 1660), f"कितने पहले से आते थे?  कमेंट करो __/{len(pairs)}   •   दोस्तों को भेजो",
           font=M.get_font(30), fill=PEN_RED, anchor="lm")
    return cv


CW_, CH_ = 1080, 1350


def car_base(n, tot):
    bg = notebook_bg(CW_, CH_, top=180).convert("RGBA")
    d = ImageDraw.Draw(bg)
    P.airmail_stripe(bg, 0, 12)
    M.place(bg, P.stamp_logo(84), 84, 84, angle=-4)
    d.text((146, 70), "POSTAL WALA", font=M.get_font(40), fill=NAVY, anchor="lm")
    d.text((148, 110), "असली पेपर PYQ · GDS से MTS / Postman", font=M.get_font_reg(28), fill=GREYT, anchor="lm")
    d.text((CW_ - 50, 84), f"{n}/{tot}", font=M.get_font(36), fill=GREYT, anchor="rm")
    return bg, d


def car_swipe(d):
    d.rounded_rectangle((CW_ - 360, CH_ - 120, CW_ - 50, CH_ - 50), 35, fill=NAVY)
    d.text((CW_ - 205, CH_ - 85), "स्वाइप करो  ›››", font=M.get_font(34), fill=GOLD_L, anchor="mm")


def carousel(items, folder):
    os.makedirs(folder, exist_ok=True)
    tot = len(items) + 2
    bg, d = car_base(1, tot)
    d.text((540, 330), "GDS से MTS / Postman", font=M.get_font(52), fill=PEN_RED, anchor="mm")
    d.text((540, 470), f"{len(items)} असली PYQ", font=M.get_font(140), fill=NAVY, anchor="mm")
    d.text((540, 600), "पिछले सालों के असली पेपर से", font=M.get_font_reg(44), fill=GREYT, anchor="mm")
    d.rounded_rectangle((140, 700, 940, 860), 40, fill=(255, 246, 214), outline=GOLD, width=5)
    d.text((540, 780), "SAVE करो — परीक्षा से पहले दोहराना", font=M.get_font(48), fill=NAVY, anchor="mm")
    d.text((540, 960), "हर स्लाइड पर 1 सवाल + सही जवाब", font=M.get_font_reg(38), fill=GREYT, anchor="mm")
    car_swipe(d)
    bg.convert("RGB").save(os.path.join(folder, "01.jpg"), quality=93)
    for i, it in enumerate(items):
        bg, d = car_base(i + 2, tot)
        y0 = 200
        d.rounded_rectangle((70, y0, 1010, y0 + 76), 38, fill=NAVY)
        d.text((540, y0 + 38), f"सवाल {i + 1}/{len(items)}", font=M.get_font(40), fill=GOLD_L, anchor="mm")
        f, s_, ls = M.fit_lines(it["q"], 900, 4, 64, 40)
        step = int(s_ * 1.25)
        y = y0 + 150
        for ln in ls:
            d.text((540, y), " ".join(ln), font=f, fill=INK, anchor="mm")
            y += step
        y += 30
        for L, o in zip("ABCD", it["opts"]):
            ok = L == it["ans"]
            d.rounded_rectangle((110, y, 970, y + 104), 28, fill=(GRN if ok else (255, 255, 255)),
                                outline=(GRN if ok else LINEC), width=3)
            d.ellipse((132, y + 22, 192, y + 82), fill=((255, 255, 255) if ok else NAVY))
            d.text((162, y + 52), L, font=M.get_font(34), fill=(GRN if ok else GOLD_L), anchor="mm")
            fo, so, lo = M.fit_lines(o, 640, 2, 44, 28)
            for kk, ln in enumerate(lo):
                d.text((220, y + 52 + (kk - (len(lo) - 1) / 2) * int(so * 1.1)), " ".join(ln), font=fo,
                       fill=((255, 255, 255) if ok else INK), anchor="lm")
            if ok:
                d.line((910, y + 52, 924, y + 66, 950, y + 36), fill=(255, 255, 255), width=8, joint="curve")
            y += 124
        ex = it.get("exams") or []
        if ex:
            d.text((540, min(y + 40, CH_ - 170)), "पूछा गया: " + ", ".join(ex[:3]), font=M.get_font_reg(32),
                   fill=GREYT, anchor="mm")
        car_swipe(d)
        bg.convert("RGB").save(os.path.join(folder, f"{i + 2:02d}.jpg"), quality=93)
    bg, d = car_base(tot, tot)
    d.text((540, 300), "कितने पहले से आते थे?", font=M.get_font(76), fill=NAVY, anchor="mm")
    d.rounded_rectangle((140, 400, 940, 560), 40, fill=(255, 255, 255), outline=GOLD, width=6)
    d.text((540, 480), f"कमेंट करो: __/{len(items)}", font=M.get_font(72), fill=PEN_RED, anchor="mm")
    d.text((540, 650), "SAVE करो  •  उस दोस्त को भेजो जिसकी परीक्षा है", font=M.get_font(40), fill=INK, anchor="mm")
    d.rounded_rectangle((140, 760, 940, 960), 40, fill=NAVY)
    d.text((540, 830), "रोज़: सुबह 8 • शाम 5 • रात 9", font=M.get_font(48), fill=GOLD_L, anchor="mm")
    d.text((540, 900), "असली PYQ + नियम चित्रों से — फॉलो करो @postal_wala", font=M.get_font_reg(34),
           fill=(255, 255, 255), anchor="mm")
    bg.convert("RGB").save(os.path.join(folder, f"{tot:02d}.jpg"), quality=93)
    return tot


def pm_caption(items, pairs, path):
    n = len(pairs)
    lines = [f"📒 डाक विभाग के {n} PYQ — GDS से MTS / Postman / PA परीक्षा (SAVE करो)", ""]
    lines += [f"{k + 1}. {q} → {a}" for k, (q, a) in enumerate(pairs)]
    ex_all = sorted({e for it in items for e in it.get("exams") or []})
    lines += ["", f"💬 कितने पहले से आते थे? कमेंट करो: __/{n}",
              "📤 SAVE करो + उस साथी को भेजो जिसकी परीक्षा है",
              "📝 पिछले सालों के असली विभागीय पेपर से (" + ", ".join(ex_all[:6]) + (" ..." if len(ex_all) > 6 else "") + ")",
              "🌅 सुबह 8 बजे: 5 सेकंड में 7 सवाल  •  🎨 शाम 5 बजे: नियम चित्रों से",
              f"🎯 FREE MOCK TEST: कमेंट करें {M.MOCK_KEYWORD}", "", M.HASHTAGS, "",
              "----- PIN करने वाला पहला कमेंट -----",
              f"आपके कितने आते थे? __/{n} लिखो 👇  कल सुबह 8 बजे नए 7 सवाल!"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run_pm(force=False):
    st = load_state()
    d0 = today()
    if d0 in st["pm"] and not force and not M.DRY_RUN:
        print(f"9 PM: {d0} ki reel pehle se bani ({st['pm'][d0]}) - skip")
        return
    grow_bank(st=st)
    am_ids = set()
    try:                                             # aaj subah wale sawal raat me dobara nahi
        am_file = st["am"].get(d0)
        if am_file:
            am_ids = set(st["used"][-N_Q:])
    except Exception:
        pass
    items = pick(st, lambda x: list_pair(x) is not None, avoid=am_ids)
    if len(items) < N_Q:
        print(f"9 PM: sirf {len(items)} chhote sawal mile - aaj reel nahi (bank badhne do)")
        return
    pairs = [list_pair(x) for x in items]
    print("9 PM sawal:", [x["id"] for x in items])
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"pyq_9pm_{d0}.mp4")
    wav = out.replace(".mp4", "_a.wav")
    write_wav(beat_music(PM_DUR), wav)
    fr = pm_frame(items, pairs)
    encode(lambda t: fr, int(PM_DUR * FPS), wav, out, static=True)
    os.remove(wav)
    folder = os.path.join(OUT_DIR, f"carousel_9pm_{d0}")
    n = carousel(items, folder)
    pm_caption(items, pairs, out.replace(".mp4", "_caption.txt"))
    print(f"9 PM REEL BANI: {out}  |  CAROUSEL: {folder} ({n} slide)")
    if M.DRY_RUN:
        return
    mark_used(st, items)
    st["pm"][d0] = os.path.basename(out)
    save_state(st)


if __name__ == "__main__":
    print(VERSION)
    job = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    force = "--force" in sys.argv[1:]
    M.resolve_font()
    try:
        if job == "am":
            run_am(force)
        elif job == "pm":
            run_pm(force)
        elif job == "bank":
            grow_bank(need_free=10 ** 6)
        else:
            print("Istemaal: python pyq_daily.py am | pm | bank")
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"PYQ ({job}) reel nahi bani ({type(exc).__name__}: {str(exc)[:200]}) - agli run me dobara")
