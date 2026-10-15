"""
NAYA FORMAT (v21) - series reel, demo4 + demo7 milake (user ne pasand kiya, 2026-10-14)
==========================================================================================
Kram (~24s):
  1. SABOOT   : PO Guide Part I ka ASLI panna, niyam wali line peele highlighter se, camera us line pe jaata hai
               (upar "GDS की गलती #N", neeche "PO Guide की ये 1 लाइन याद रखो!")
  2. KAHANI   : chitra-panne poori screen pe (POV: आप डाकघर में हो), bade subtitle, galti pe ❌
  3. रुको!     : "रुको! पहले सोचो" + bada ? + do vikalp + 3-2-1 ginti + "सही जवाब कमेंट करो"
  4. JAWAB    : sahi wala chitra, hara ghera + ✓
  5. NIYAM    : "पूरा नियम" card (likha hua) ...
  6. TRAP     : ... usi card ke NEECHE EXAM TRAP: ❌ galat soch / ✓ sahi baat  (niyam pehle, nishaan baad me)
  7. ANT      : याद रखो साथियों + share button + "इसी नियम का असली पेपर सवाल: अगली रील" + "कल: गलती #N+1"

main.py ke chitra (photo kit), awaaz (make_voices = Gemini/fallback), font, sfx yahin se use hote hain.
Kuch bhi fail ho to main.py purane format se reel banata hai (koi din khaali nahi).
"""
import json
import math
import os
import re
import subprocess
import tempfile
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

M = None            # main module (init se) - main.py ke globals (chuni hui awaaz waghaira) wahi rahen
W, H, FPS = 1080, 1920, 30

NAYA_VERSION = "v21.2-naya (2026-10-15): sawal-pehle hook (3s) + ek kahani drishya + सोचो 2s + chhota jawab + kitaab ki line bade akshar + TRAP ❌/✓ + asli paper sawal ka jawab (answer key se jaancha) + याद/Follow ant (~26s)"

POV_LINE = "POV: आप डाकघर में हो"
PROOF_VOICE = "GDS साथियों! PO Guide की ये एक लाइन याद रखो!"
END_VOICE = "याद रखो साथियों!"
TRANS = 0.2                 # scene badalne ka samay
CD_STEP = 0.3               # 3-2-1 ka ek kadam (v21.2: 0.62 -> 0.3, "सोचो" ~2s - user plan)
NAYA_SPEED = 1.15           # v21.2: naye format ki awaaz (main ki 0.96 ke upar) -> demo7 jaisi gati, reel ~26s
RUKO_VOICE = "सही विकल्प कौन-सा है?"
HOOK_TAIL = " नियम देखो!"

NAVY = (16, 28, 64)
GOLD = (255, 205, 40)
RED_C = (210, 30, 45)
GREEN_C = (22, 150, 70)
CREAM = (255, 253, 244)


def init(mod):
    global M, W, H, FPS
    M = mod
    W, H, FPS = M.W, M.H, M.FPS


# ============================================================ chhote helpers

def font(sz):
    return M.get_font(int(sz))


def font_reg(sz):
    try:
        return M.get_font_reg(int(sz))
    except Exception:
        return M.get_font(int(sz))


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def tw(text, f):
    return f.getlength(text)


def wrap(text, f, max_w):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        nx = (cur + " " + w_).strip()
        if cur and tw(nx, f) > max_w:
            lines.append(cur)
            cur = w_
        else:
            cur = nx
    if cur:
        lines.append(cur)
    return lines


def fit_wrap(text, max_w, size, max_lines, min_size=30, reg=False):
    s = size
    while True:
        f = font_reg(s) if reg else font(s)
        ls = wrap(text, f, max_w)
        if len(ls) <= max_lines or s <= min_size:
            return f, s, ls
        s -= 3


def stroke_text(d, xy, text, f, fill, stroke=7, anchor="mm", sfill=(0, 0, 0)):
    d.text(xy, text, font=f, fill=fill, stroke_width=stroke, stroke_fill=sfill, anchor=anchor)


@lru_cache(maxsize=64)
def pill(text, size, fg, bg, border=None, padx=34, pady=14, reg=False):
    f = font_reg(size) if reg else font(size)
    bb = f.getbbox(text)
    w, h = int(tw(text, f) + 2 * padx), int(bb[3] - bb[1] + 2 * pady)
    im = Image.new("RGBA", (w + 12, h + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((6, 10, w + 6, h + 10), radius=h // 2, fill=(0, 0, 0, 90))
    d.rounded_rectangle((6, 6, w + 6, h + 6), radius=h // 2, fill=bg + (255,),
                        outline=(border + (255,)) if border else None, width=4 if border else 0)
    d.text((6 + w / 2, 6 + h / 2), text, font=f, fill=fg + (255,), anchor="mm")
    return im


def put(cv, sp, cx, cy, scale=1.0, alpha=1.0, angle=0.0):
    M.place(cv, sp, cx, cy, scale=scale, alpha=alpha, angle=angle)


def brand(cv):
    d = ImageDraw.Draw(cv)
    d.text((40, 44), "POSTAL WALA", font=font(30), fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))


def bands(cv, top=300, bottom_from=1250, top_a=200, bot_a=230):
    """Upar-neeche halka andhera (likhai har chitra pe padhi jaaye)."""
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in range(0, top):
        d.line([(0, y), (W, y)], fill=(8, 10, 18, int(top_a * (1 - y / top) ** 1.4)))
    span = H - bottom_from
    for y in range(bottom_from, H):
        d.line([(0, y), (W, y)], fill=(8, 10, 18, int(bot_a * min(1.0, (y - bottom_from) / (span * 0.55)) ** 0.8)))
    cv.alpha_composite(ov)


_BANDS = {}


def bands_fast(cv, key=(300, 1250, 200, 230)):
    if key not in _BANDS:
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bands(im, *key)
        _BANDS[key] = im
    cv.alpha_composite(_BANDS[key])


# ============================================================ subtitle (shabd-dar-shabd)

def chunks_of(words, f, max_w=940, maxn=4):
    out, cur = [], []
    for w_ in words:
        nx = cur + [w_]
        if cur and (len(nx) > maxn or tw(" ".join(nx), f) > max_w):
            out.append(cur)
            cur = [w_]
        else:
            cur = nx
    if cur:
        out.append(cur)
    return out


def caption(cv, text, p, cy=1420, size=84):
    """Jo bola ja raha hai uska 2-4 shabd ka tukda; bolta shabd peela (demo jaisa)."""
    words = (text or "").split()
    if not words or p <= 0:
        return
    f = font(size)
    th = M.word_thresholds(words)
    cur = max([i for i, a in enumerate(th) if p >= a] or [0])
    chs = chunks_of(words, f)
    k, acc = 0, 0
    for j, c in enumerate(chs):
        if cur < acc + len(c):
            k = j
            break
        acc += len(c)
    ch = chs[k]
    d = ImageDraw.Draw(cv)
    space = tw(" ", f)
    total = sum(tw(w_, f) for w_ in ch) + space * (len(ch) - 1)
    x = W / 2 - total / 2
    for i, w_ in enumerate(ch):
        gi = acc + i
        col = (255, 214, 40) if gi == cur else (255, 255, 255)
        d.text((x, cy), w_, font=f, fill=col, stroke_width=8, stroke_fill=(0, 0, 0), anchor="lm")
        x += tw(w_, f) + space


# ============================================================ chitra poori screen

def _focus_center(pn, size, zk, punch, pan):
    """main.photo_frame jaisa hi hisaab: zoom ke baad mukhya cheez (box) ka x kahan hai (crop isi pe)."""
    box = pn.get("box") or [0.3, 0.3, 0.7, 0.7]
    base = M.photo_focus(pn["img"], box, pn.get("bg_text"))
    bw, bh = base.size
    side = min(bw, bh)
    fx, fy = (box[0] + box[2]) / 2 * bw, (box[1] + box[3]) / 2 * bh
    face = pn.get("face") if (punch > 0.01 and M.FACE_PUNCH) else None
    if face:
        pz = M.ease_in_out(M.clamp(punch))
        fx += ((face[0] + face[2]) / 2 * bw - fx) * pz
        z = 1.0 + M.PHOTO_ZOOM * M.ease_in_out(M.clamp(zk)) + M.PHOTO_FACE_PUNCH * pz
    else:
        z = 1.0 + M.PHOTO_ZOOM * M.ease_in_out(M.clamp(zk)) + M.PHOTO_PUNCH * M.clamp(punch)
    if pan and pn.get("pan") and not face:
        z = max(z, 1.22)
        fx = bw * (0.30 + 0.40 * M.ease_in_out(M.clamp(zk))) if pn["pan"] != "rl" else \
            bw * (0.70 - 0.40 * M.ease_in_out(M.clamp(zk)))
    win = side / z
    fk = min(1.0, (z - 1) / M.PHOTO_ZOOM * 0.7) if M.PHOTO_ZOOM else 0.0
    if face:
        fk = max(fk, M.ease_in_out(M.clamp(punch)))
    if pan and pn.get("pan") and not face:
        fk = 1.0
    cx = bw / 2 + (fx - bw / 2) * fk
    x0 = min(max(cx - win / 2, 0), bw - win)
    bx = (box[0] + box[2]) / 2 * bw
    return (bx - x0) * size / win


def panel_full(pn, zk=0.0, rk=0.0, tk=0.0, sk=0.0, punch=0.0):
    """
    Ek chitra 1080x1920 me (main.photo_frame ka ghera/spotlight/camera wahi). Parchi (tag) aur pata-card
    poori screen me subtitle se takraate - unhe yahan screen ke hisaab se alag jagah lagaya jaata hai.
    """
    S = H
    bare = {k: v for k, v in pn.items() if k not in ("tag", "card")}
    sq = M.photo_frame(bare, S, zk, rk, 0.0, sk, punch, pan=True)
    try:
        cx = _focus_center(pn, S, zk, punch, True)
    except Exception:
        cx = S / 2
    x0 = int(min(max(cx - W / 2, 0), S - W))
    cv = sq.crop((x0, 0, x0 + W, H)).convert("RGBA")
    if tk > 0.01:
        k = M.ease_out_back(M.clamp(tk))
        if pn.get("card"):
            cs = M.card_close_sprite(pn["card"], pn.get("mark", "none"), 620)
            put(cv, cs, W / 2, 1290 - cs.height / 2, scale=max(0.05, k))
        elif pn.get("tag"):
            fg, bg, ol = M.TAG_COLORS.get(pn.get("tag_color"), M.TAG_COLORS["dark"])
            put(cv, pill(pn["tag"], 50, fg, bg, ol), W / 2, 1270, scale=max(0.05, k))
    return cv


_BLUR = {}


def blurred_bg(pn, dark=0.55, radius=14):
    key = (pn.get("img"), dark, radius)
    if key not in _BLUR:
        im = panel_full(pn, 0.6, 0, 0, 0, 0).convert("RGB")
        small = im.resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(radius / 4))
        im = small.resize((W, H), Image.BILINEAR)
        im = Image.blend(im, Image.new("RGB", (W, H), (10, 10, 16)), dark)
        _BLUR[key] = im.convert("RGBA")
    return _BLUR[key].copy()


# ============================================================ 1) ASLI PO GUIDE PANNA

def _tok(s):
    s = (s or "").lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return [t for t in re.sub(r"[^a-z0-9]+", " ", s.replace("-", "")).split() if t]


def _is_english(s):
    s = s or ""
    letters = re.findall(r"[A-Za-zऀ-ॿ]", s)
    return bool(letters) and sum(1 for c in letters if c.isascii()) / len(letters) > 0.85 and len(_tok(s)) >= 5


_BBOX = {}


def _guide_words(pdf):
    """PDF ke har shabd ka (page, x0, y0, x1, y1, text) - pdftotext -bbox se (ek baar per run)."""
    if pdf in _BBOX:
        return _BBOX[pdf]
    out = os.path.join(tempfile.gettempdir(), "_pw_guide_bbox.html")
    subprocess.run(["pdftotext", "-bbox", pdf, out], check=True, capture_output=True)
    html = open(out, encoding="utf-8", errors="ignore").read()
    pages = []
    for pm in re.finditer(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', html, re.S):
        ws = [(float(a), float(b), float(c), float(e), t) for a, b, c, e, t in
              re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>',
                         pm.group(3))]
        pages.append({"w": float(pm.group(1)), "h": float(pm.group(2)), "words": ws})
    _BBOX[pdf] = pages
    return pages


def _unescape(t):
    return t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")


def locate_sentence(pdf, sentence, min_frac=0.72):
    """Sentence PDF me kahan hai: (page_index, [line rects in pt]) ya None. Line-todne wale '-' bhi sambhale."""
    S = _tok(sentence)
    if len(S) < 4:
        return None
    best = None
    for pi, pg in enumerate(_guide_words(pdf)):
        toks = [(_tok(_unescape(w[4])), w) for w in pg["words"]]
        flat = [(t, w) for ts, w in toks for t in ts]       # "8:30" / "P.M." / "sender’s" ke saare tukde
        n = len(flat)
        for i in range(n):
            if flat[i][0] != S[0]:
                continue
            if i + 2 < n and len(S) > 2 and not (flat[i + 1][0] == S[1] or flat[i + 1][0] + flat[i + 2][0] == S[1]
                                                 or flat[i + 1][0] == S[1] + S[2]):
                continue
            j, k, miss, used = 0, i, 0, []
            while j < len(S) and k < n and miss <= 3:
                if flat[k][0] == S[j]:
                    used.append(flat[k][1]); j += 1; k += 1
                elif k + 1 < n and flat[k][0] + flat[k + 1][0] == S[j]:
                    used += [flat[k][1], flat[k + 1][1]]; j += 1; k += 2
                elif j + 1 < len(S) and flat[k][0] == S[j] + S[j + 1]:
                    used.append(flat[k][1]); j += 2; k += 1
                else:
                    miss += 1; j += 1; k += 1
            frac = len(used) / len(S)
            if frac >= min_frac and (best is None or frac > best[0]):
                best = (frac, pi, used)
    if not best:
        return None
    _, pi, used = best
    lines = {}
    for (x0, y0, x1, y1, _t) in used:
        key = round(y0 / 3)
        r = lines.get(key)
        lines[key] = (min(r[0], x0), min(r[1], y0), max(r[2], x1), max(r[3], y1)) if r else (x0, y0, x1, y1)
    rects = sorted(lines.values(), key=lambda r: r[1])
    seen, words = set(), []                          # zoom-card ke liye asli shabd (kram me, dohraav nahi)
    for w in used:
        if id(w) not in seen:
            seen.add(id(w))
            words.append(w)
    words.sort(key=lambda w: (round(w[1] / 3), w[0]))
    return pi, rects, words


def clause_first(clause):
    """Clause ki pehli asli line (aage ka '26.' / '(1)' number chhod ke, kam se kam 6 shabd)."""
    txt = re.sub(r"^\s*\d+\s*[.)]\s*", "", clause or "")
    for s in re.split(r"(?<=[.;:])\s+", txt):
        s = re.sub(r"^\(?[0-9a-z]{1,3}\)\s*", "", s.strip())
        if len(_tok(s)) >= 6:
            return " ".join(s.split()[:40])
    return ""


GUIDE_PICK_PROMPT ="""You are given the official English text of PO Guide Part I, Clause {num}, and ONE rule taught in a Hindi exam reel.
Return the ONE sentence (or sentence-part) from the clause text that states THIS rule, copied EXACTLY,
character-for-character (same words, same order). If the clause text says something DIFFERENT from the rule
(rule changed later) or no sentence states it, return an empty string.

Rule (Hindi): {fact}
Question of the reel (Hindi): {question}
Correct answer (Hindi): {answer}

Clause {num} text:
\"\"\"{clause}\"\"\"

Return JSON: {{"sentence": "<exact copy or empty>"}}"""


def guide_line(plan, part, data):
    """Niyam ki asli English line (PO Guide) - ek baar dhoondh ke part["guide_line_v"] me (dobara API nahi)."""
    gv = part.get("guide_line_v") if isinstance(part.get("guide_line_v"), dict) else {}
    if gv.get("v") == 1:
        return gv
    clause = " ".join((plan.get("clause_text_en") or "").split())
    sent, kind = "", ""
    sq = " ".join((part.get("source_quote") or "").split())
    if _is_english(sq):                           # plan banate waqt PO Guide se hi li gayi line (PDF me milaan aage)
        sent, kind = sq, "line"
    elif clause and not M.DRY_RUN:
        try:
            js = M._llm_json(GUIDE_PICK_PROMPT.format(num=plan.get("clause_no"), fact=data.get("fact", ""),
                                                      question=data.get("question", ""),
                                                      answer=data.get("correct_text", ""), clause=clause[:9000]))
            cand = " ".join(str((js or {}).get("sentence") or "").split())
            if cand and len(_tok(cand)) >= 5 and " ".join(_tok(cand)) in " ".join(_tok(clause)):
                sent, kind = cand, "line"
        except Exception as exc:
            print("  Guide-line nahi chuni (clause ki shuruaat dikhegi):", str(exc)[:120])
    if not sent and clause:                       # niyam ki line na mile -> clause ki pehli line (asli panna to dikhe)
        sent, kind = clause_first(clause), "clause"
    gv = {"v": 1, "sentence": sent, "kind": kind}
    part["guide_line_v"] = gv
    return gv


def proof_assets(plan, part, data):
    """(page_png, page_w_pt, page_h_pt, rects) ya None."""
    try:
        gv = guide_line(plan, part, data)
        if not gv.get("sentence"):
            return None
        pdf = M.find_guide_pdf()
        loc = locate_sentence(pdf, gv["sentence"])
        if not loc:                                  # (table wali line) -> clause ki pehli line hi sahi
            first = clause_first(" ".join((plan.get("clause_text_en") or "").split()))
            loc = locate_sentence(pdf, first) if first else None
            if loc:
                gv = dict(gv, kind="clause-start")
        if not loc:
            print("  PO Guide panne pe line nahi mili - saboot wala drishya chhoda")
            return None
        pi, rects, words = loc
        pg = _guide_words(pdf)[pi]
        out = os.path.join(tempfile.gettempdir(), f"_pw_page_{pi + 1}")
        subprocess.run(["pdftoppm", "-f", str(pi + 1), "-l", str(pi + 1), "-r", "360", "-png", "-singlefile", pdf, out],
                       check=True, capture_output=True)
        print(f"  Saboot: PO Guide page {pi + 1}, {len(rects)} line highlight ({gv['kind']}): {gv['sentence'][:90]}")
        return {"png": out + ".png", "pw": pg["w"], "ph": pg["h"], "rects": rects, "words": words, "page": pi + 1}
    except Exception as exc:
        print("  Saboot wala panna nahi bana (reel bina iske):", str(exc)[:140])
        return None


class Proof:
    def __init__(self, a, clause_no, ep):
        self.a, self.clause_no, self.ep = a, clause_no, ep
        img = Image.open(a["png"]).convert("RGB")
        self.k = img.width / a["pw"]                 # px per pt
        pad = int(300 * self.k)
        base = Image.new("RGB", (img.width + 2 * pad, img.height + 2 * pad), (255, 255, 255))
        base.paste(img, (pad, pad))
        self.pad, self.base = pad, base
        r = a["rects"]
        self.cx = (min(x[0] for x in r) + max(x[2] for x in r)) / 2
        self.cy = (min(x[1] for x in r) + max(x[3] for x in r)) / 2
        self.tot = sum(x[2] - x[0] for x in r)
        # page ka text-hissa (hashiye chhod ke) poori chaudai me
        xs = [w[0] for w in _guide_words(M.find_guide_pdf())[a["page"] - 1]["words"]] or [60]
        xe = [w[2] for w in _guide_words(M.find_guide_pdf())[a["page"] - 1]["words"]] or [a["pw"] - 60]
        self.view_w = (max(xe) - min(xs)) + 30
        self.ov = self._overlay()
        try:
            self.card = self._card(a.get("words") or [])
        except Exception as exc:
            print("  Zoom-card nahi bana (sirf panna dikhega):", str(exc)[:120])
            self.card = None

    def _card(self, words):
        """Asli panne ke wahi shabd (PDF ke pixel) bade karke card me - phone pe line padhi jaaye."""
        if len(words) < 4:
            return None
        lh_pt = max(w[3] - w[1] for w in words)
        cw, padx, pady = 980, 44, 36
        words = list(words)
        for ppt in (5.4, 5.0, 4.6):                  # v21.2: kam se kam 4.6 px/pt (~55px akshar), max 5 line
            sc = ppt / self.k
            crops = []
            for (x0, y0, x1, y1, _t) in words:
                a_, b_ = self.P(x0 - 0.6, y0 - 0.25 * lh_pt), self.P(x1 + 0.6, y0 + 1.25 * lh_pt)
                c = self.base.crop((int(a_[0]), int(a_[1]), int(b_[0]), int(b_[1])))
                crops.append(c.resize((max(1, int(c.width * sc)), max(1, int(c.height * sc))), Image.LANCZOS))
            lh, sp = int(1.6 * lh_pt * ppt), int(0.33 * lh_pt * ppt)
            place, x, y = [], padx, pady
            for c in crops:
                if x + c.width > cw - padx:
                    x, y = padx, y + lh
                place.append((x, y, c))
                x += c.width + sp
            if (y - pady) // lh + 1 <= 5:
                break
            if ppt == 4.6 and len(words) > 8:          # 5 line me na aaye -> aakhri shabd hatao (asli line ka shuru)
                while words and (y - pady) // lh + 1 > 5:
                    words = words[:-1]
                    crops = crops[:len(words)]
                    place, x, y = [], padx, pady
                    for c in crops:
                        if x + c.width > cw - padx:
                            x, y = padx, y + lh
                        place.append((x, y, c))
                        x += c.width + sp
                break
        else:
            return None
        ch = y + lh + pady - int(0.2 * lh)
        img = Image.new("RGB", (cw, ch), CREAM)
        for x, y, c in place:
            img.paste(c, (x, y))
        return {"img": img, "place": place, "w": cw, "h": ch, "tot": sum(c.width for _, _, c in place)}

    def _card_frame(self, t):
        cd = self.card
        hl = Image.new("RGB", (cd["w"], cd["h"]), (255, 255, 255))
        d = ImageDraw.Draw(hl)
        left = ease((t - 0.25) / 0.7) * cd["tot"]
        for x, y, c in cd["place"]:
            if left <= 0:
                break
            seg = min(left, c.width)
            left -= seg
            d.rectangle([x - 6, y + int(c.height * 0.12), x + seg + 6, y + c.height - 2], fill=(255, 226, 70))
        from PIL import ImageChops
        img = ImageChops.multiply(cd["img"], hl)
        m = 18
        out = Image.new("RGBA", (cd["w"] + 2 * m, cd["h"] + 2 * m + 70), (0, 0, 0, 0))
        dd = ImageDraw.Draw(out)
        dd.rounded_rectangle([m + 6, 70 + m + 10, m + cd["w"] + 6, 70 + m + cd["h"] + 10], radius=26, fill=(0, 0, 0, 120))
        mask = Image.new("L", (cd["w"], cd["h"]), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, cd["w"] - 1, cd["h"] - 1], radius=24, fill=255)
        out.paste(img, (m, 70 + m), mask)
        dd.rounded_rectangle([m, 70 + m, m + cd["w"] - 1, 70 + m + cd["h"] - 1], radius=24, outline=GOLD, width=6)
        out.alpha_composite(pill("PO Guide में लिखा है:", 38, (25, 25, 25), GOLD), (m - 6, 0))
        return out

    def P(self, x, y):
        return x * self.k + self.pad, y * self.k + self.pad

    def _overlay(self):
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bands(ov, 330, 1300, 215, 240)
        brand(ov)
        put(ov, pill(f"GDS की गलती #{self.ep}", 40, (25, 25, 25), GOLD), W / 2, 125)
        lab = f"असली PO Guide  •  Part I  •  Clause {self.clause_no}"
        put(ov, pill(lab, 38, (255, 255, 255), RED_C), W / 2, 230)
        d = ImageDraw.Draw(ov)
        stroke_text(d, (W / 2, 1540), "PO Guide की ये 1 लाइन", font(88), (255, 214, 40), 8)
        stroke_text(d, (W / 2, 1655), "याद रखो !", font(88), (255, 255, 255), 8)
        return ov

    def frame(self, t, dur):
        hl = Image.new("RGBA", self.base.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(hl)
        left = ease((t - 0.15) / 0.9) * self.tot
        for (x0, y0, x1, y1) in self.a["rects"]:
            if left <= 0:
                break
            seg = min(left, x1 - x0)
            left -= seg
            d.rounded_rectangle([self.P(x0 - 1.5, y0 - 1.2), self.P(x0 + seg + 1.0, y1 + 1.2)],
                                radius=int(2 * self.k), fill=(255, 222, 40, 150))
        z = 1.3 + 0.9 * ease(t / max(0.5, dur))                   # camera line ki taraf (shuru se hi paas)
        wp = self.view_w / z
        hp = wp * H / W
        a = self.P(self.cx - wp / 2, self.cy - hp / 2 - 40 / z)
        b = self.P(self.cx + wp / 2, self.cy + hp / 2 - 40 / z)
        page = Image.alpha_composite(self.base.convert("RGBA").crop((int(a[0]), int(a[1]), int(b[0]), int(b[1]))),
                                     hl.crop((int(a[0]), int(a[1]), int(b[0]), int(b[1]))))
        fr = page.resize((W, H), Image.BILINEAR)
        t_card = 1.05                                   # pehle asli panna + highlight, fir wahi shabd bade
        if self.card and t >= t_card:
            k = ease((t - t_card) / 0.22)
            fr.alpha_composite(Image.new("RGBA", (W, H), (10, 10, 10, int(150 * k))))
            cf = self._card_frame(t - t_card)
            s = 0.82 + 0.18 * k
            cf = cf.resize((int(cf.width * s), int(cf.height * s)), Image.LANCZOS)
            if k < 1:
                cf.putalpha(cf.getchannel("A").point(lambda v: int(v * k)))
            cy = 760 - cf.height // 2 if cf.height < 1000 else 330
            fr.alpha_composite(cf, ((W - cf.width) // 2, max(300, cy) + int((1 - k) * 60)))
        fr.alpha_composite(self.ov)
        return fr


# ============================================================ asli paper ka sawal (ant me)

PDF_LINE = "पाओ FREE PDF"
PYQ_SAY_MAX = 16                                     # isse lamba sawal bola nahi jaata (reel ~30s rahe)
PYQ_SHORT_VOICE = "असली पेपर का सवाल! पढ़ो और जवाब कमेंट करो!"


def pyq_for(plan, part, data):
    """
    Reel ke ant ka ASLI paper sawal: (item, related) ya (None, False).
    1) usi niyam ka asli PYQ (pyq_papers + answer key se milaan, pyq_reel.find_pyq) - ek baar dhoondh ke part["pyq_v"]
    2) na mile -> bank ka jaancha hua asli sawal (tab 'isi niyam' nahi kehte)
    """
    import sys as _sys
    _sys.modules.setdefault("main", M)            # pyq_reel 'import main' -> yahi chalta module (dobara load nahi)
    import pyq_reel as P
    pv = part.get("pyq_v") if isinstance(part.get("pyq_v"), dict) else {}
    if int(pv.get("v") or 0) < getattr(P, "PYQ_V", 2):   # v21.2: purani khoj me jawab answer key se nahi milaya tha
        pv = {}
    items = [x for x in (pv.get("items") or []) if x.get("q") and len(x.get("opts") or []) == 4]
    if not items and not pv.get("searched"):
        gv = part.get("guide_line_v") if isinstance(part.get("guide_line_v"), dict) else {}
        en = part.get("en") if isinstance(part.get("en"), dict) else {}
        entry = {"clause": data.get("clause_no"), "part_no": data.get("part_no"),
                 "guide_line": gv.get("sentence", ""), "en_question": en.get("question", ""),
                 "en_fact": en.get("fact", ""), "source_quote": part.get("source_quote", ""),
                 "trap_quote": part.get("trap_quote", ""), "fact": data.get("fact", ""),
                 "question": data.get("question", ""), "answer": data.get("correct_text", "")}
        try:
            items = P.find_pyq(entry)
        except Exception as exc:
            print("  Ant ka PYQ nahi dhoondha:", str(exc)[:140])
            items = []
        if not M.DRY_RUN:
            part["pyq_v"] = {"items": items, "searched": True, "v": getattr(P, "PYQ_V", 2)}
    items = [x for x in items if x.get("key_ok")]      # sirf answer key se jaanche jawab wale
    if items:                                          # sabse chhota sawal (reel me padha ja sake)
        return dict(min(items, key=lambda x: len(x["q"]) + sum(len(o) for o in x["opts"])), key_ok=True), True
    try:                                            # bank: asli paper ka jaancha hua sawal (episode se ghoomta)
        bank, _sets = P.load_bank()
        ids = sorted(bank)
        if ids:
            it = dict(bank[ids[int(data.get("episode") or 0) % len(ids)]], key_ok=True)   # bank = pehle se jaancha
            return it, False
    except Exception as exc:
        print("  Bank sawal nahi mila:", str(exc)[:120])
    return None, False


PAPER = (250, 248, 242)


@lru_cache(maxsize=4)
def _paper_bg():
    im = Image.new("RGBA", (W, H), PAPER + (255,))
    d = ImageDraw.Draw(im)
    for x in range(-40, W + 40, 56):                 # upar laal-safed patti (asli paper/lifaafa jaisa)
        d.polygon([(x, 0), (x + 28, 0), (x + 8, 16), (x - 20, 16)], fill=RED_C + (255,))
    d.text((40, 44), "POSTAL WALA", font=font(30), fill=NAVY + (255,))
    return im


@lru_cache(maxsize=32)
def opt_row(letter, text):
    w = 940
    f, s_, ls = fit_wrap(text, w - 170, 46, 2, 32, reg=True)
    lh = int(s_ * 1.25)
    h = max(108, 34 + len(ls) * lh)
    im = Image.new("RGBA", (w + 16, h + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((8, 12, 8 + w, 12 + h), radius=22, fill=(0, 0, 0, 30))
    d.rounded_rectangle((8, 8, 8 + w, 8 + h), radius=22, fill=(255, 255, 255, 255), outline=(222, 224, 232, 255), width=3)
    d.ellipse((34, 8 + h / 2 - 32, 98, 8 + h / 2 + 32), fill=NAVY + (255,))
    d.text((66, 8 + h / 2), letter, font=font(38), fill=(255, 214, 40, 255), anchor="mm")
    y = 8 + (h - len(ls) * lh) / 2
    for ln in ls:
        d.text((130, y + lh / 2), ln, font=f, fill=(25, 30, 45, 255), anchor="lm")
        y += lh
    return im


# ============================================================ scenes

def trap_pair(trap):
    """
    'पार्सल लिखना गलत, क्योंकि ...' -> (❌ 'पार्सल लिखना', ✓ 'क्योंकि ...'). ❌ ke saath 'गलत' shabd nahi rehta
    (❌ + 'गलत' = ulta padhta). Saaf na tute to None (tab ek hi ⚠ line).
    """
    if not trap:
        return None
    sp = M.split_trap(trap)
    if not sp:
        return None
    a, b = sp
    a2 = re.sub(r"\s*(समझना|मानना|सोचना)?\s*गलत(\s*(है|हैं))?\s*[।.!]?\s*$", "", a).strip(" ,")
    if len(a2.split()) < 2 or "गलत" in a2:
        return None
    return a2, b.strip()


def story_split(panels):
    """Kahani (jawab se pehle) aur jawab wala chitra."""
    ri = next((i for i, p in enumerate(panels) if p.get("mark") == "right"), None)
    if ri is None or ri == 0:
        return panels[:-1] or panels[:1], panels[-1]
    return panels[:ri], panels[ri]


def vs_letters(data):
    pair = data.get("vs_pair") or []
    lo = {txt: l for l, txt in data.get("options") or []}
    out = [(lo.get(t_, ""), t_) for t_ in pair if t_ in lo]
    if len(out) == 2 and all(len(t_.split()) <= 6 for _, t_ in out):
        return out
    return []


def ruko_q(data):
    hq = (data.get("hook_q") or "").strip()
    q = hq if hq and len(hq.split()) <= 12 else (data.get("question") or "")
    return " ".join(q.split())


def hook_text(data):
    """Pehle second ka sawal: punch line (3-6 shabd) ya chhota hook sawal."""
    pv = data.get("punch_v") if isinstance(data.get("punch_v"), dict) else {}
    if pv.get("ok") and pv.get("text"):
        return pv["text"].strip()
    return ruko_q(data)


def ans_voice(data):
    ct = " ".join((data.get("correct_text") or "").split())
    return f"सही जवाब: {ct}!" if ct and len(ct.split()) <= 7 else f"सही जवाब, विकल्प {data.get('correct', '')}!"


def pyq_ans_voice(it):
    o = it["opts"]["ABCD".index(it["ans"])]
    return f"सही जवाब: {o}!" if len(o.split()) <= 5 else f"सही जवाब, विकल्प {it['ans']}!"


def build_specs(data, story, ans_pn, has_proof, pyq=None):
    """v21.2 kram (user ka Final Editing Plan): hook -> kahani -> सोचो -> jawab -> niyam -> TRAP -> asli sawal -> याद."""
    specs = [{"name": "hook", "segs": [("h", hook_text(data) + (HOOK_TAIL if has_proof else ""))]},
             {"name": "s0", "segs": [("c0", story[0].get("text") or "")]},
             {"name": "ruko", "segs": [("r", RUKO_VOICE)]},
             {"name": "ans", "segs": [("a", ans_voice(data))]},
             {"name": "rule", "segs": [("f", "नियम: " + data["fact"])]}]
    if data.get("trap"):
        specs.append({"name": "trap", "segs": [("t", "ट्रैप: " + data["trap"])]})
    if pyq:
        specs.append({"name": "pyq", "segs": [("q", "असली पेपर का सवाल!")]})
        if pyq.get("key_ok"):
            specs.append({"name": "pyqa", "segs": [("qa", pyq_ans_voice(pyq))]})
    specs.append({"name": "end", "segs": [("e", END_VOICE)]})
    return specs


def plan_timeline(specs, voices, data):
    tl, cur = [], 0.0
    for sp, v in zip(specs, voices):
        a = v[0]
        vd = len(a) / M.SR
        n = sp["name"]
        if n == "pyqa":                                # pyq drishya ke andar: 3-2-1 ke baad jawab ki awaaz
            sc = tl[-1]
            sc["rev"] = sc["cd0"] + 3 * CD_STEP + 0.05
            sc["audio2"], sc["vd2"] = a, vd
            new = sc["rev"] + vd + 0.55
            cur += new - sc["dur"]
            sc["dur"] = new
            continue
        lead = 0.08
        if n == "hook":                                # 0-0.5 close-up | 0.5 sawal | 2.3 kitaab ki line
            dur = max(3.0, lead + vd + 0.25)
        elif n.startswith("s"):
            dur = lead + vd + 0.35
        elif n == "ruko":                              # ? -> do vikalp -> 3-2-1 (~2s)
            cd0 = max(0.7, lead + vd - 0.25)
            dur = cd0 + 3 * CD_STEP + 0.1
        elif n == "ans":
            lead = 0.2
            dur = lead + vd + 0.35
        elif n == "rule":
            dur = max(4.0, lead + vd + 0.4)
        elif n == "trap":
            lead = 0.3                                 # pehle TRAP thappa, fir awaaz
            dur = lead + vd + 0.4
        elif n == "pyq":
            lead = 0.1
            cd0 = lead + vd + 0.2
            dur = cd0 + 3 * CD_STEP + 0.6              # (jawab na ho to) 3-2-1 + "जवाब कमेंट करो"
        else:                                          # end
            dur = max(2.3, lead + vd + 0.9)
        sc = {"name": n, "start": cur, "dur": dur, "lead": lead, "vd": vd, "audio": a,
              "text": " ".join(t for _, t in sp["segs"])}
        if n in ("ruko", "pyq"):
            sc["cd0"] = cd0
        tl.append(sc)
        cur += dur
    return tl, cur


def _closeup(pn, z, zk=0.0):
    """Mukhya cheez (box) ka close-up poori screen pe (hook) - parchi/ghera nahi (jawab na khule)."""
    pn = {k: v for k, v in pn.items() if k != "badge"}     # close-up me chhati ki naam-patti badi hoke kat-ti thi
    base = panel_full(pn, zk, 0.0, 0.0, 0.0, 0.0)
    box = pn.get("box") or [0.3, 0.3, 0.7, 0.7]
    try:
        cx = _focus_center(pn, H, zk, 0.0, True) - max(0, 0)
        x0 = min(max(cx - W / 2, 0), H - W)
        cx = cx - x0
    except Exception:
        cx = W / 2
    cy = (box[1] + box[3]) / 2 * H
    vw, vh = W / z, H / z
    l = min(max(cx - vw / 2, 0), W - vw)
    t_ = min(max(cy - vh / 2, 0), H - vh)
    return base.crop((int(l), int(t_), int(l + vw), int(t_ + vh))).resize((W, H), Image.BILINEAR), \
        ((cx - l) * z, (cy - t_) * z)


def headline(cv, text, y=330, size=104, col=(255, 214, 40), k=1.0):
    if k <= 0.02:
        return
    f, s_, ls = fit_wrap(text, 990, size, 2, int(size * 0.62))
    lh = int(s_ * 1.18)
    lay = Image.new("RGBA", (W, lh * 2 + 80), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    y0 = lay.height / 2 - (len(ls) - 1) * lh / 2
    for i, ln in enumerate(ls[:2]):
        stroke_text(d, (W / 2, y0 + i * lh), ln, f, col, max(6, s_ // 9))
    put(cv, lay, W / 2, y, alpha=min(1.0, k), scale=max(0.05, 0.85 + 0.15 * M.ease_out_back(min(1.0, k))))


class Reel:
    def __init__(self, data, story, ans_pn, proof, pyq=None, pyq_related=False):
        self.data, self.story, self.ans_pn, self.proof = data, story, ans_pn, proof
        self.pyq, self.pyq_related = pyq, pyq_related
        self.ep = int(data.get("episode") or 0)
        self.cno = data.get("clause_no")
        self.trap_pair = trap_pair(data.get("trap") or "")
        self.wrong = next((p for p in story if p.get("mark") == "wrong"), story[-1])
        self._last = {}

    def _card(self, t, scale=1.0):
        if not (self.proof and self.proof.card):
            return None
        cf = self.proof._card_frame(t)
        if scale != 1.0:
            cf = cf.resize((int(cf.width * scale), int(cf.height * scale)), Image.LANCZOS)
        return cf

    # ---- 0-3s: sawal pehle (user plan) - close-up -> bada sawal -> ? -> kitaab ki line ka chhota highlight
    def sc_hook(self, sc, t):
        pn = self.wrong
        cv, (ox, oy) = _closeup(pn, 1.45 + 0.35 * ease(t / max(0.5, sc["dur"])), 0.6)
        cv = cv.convert("RGBA")
        bands_fast(cv)
        brand(cv)
        if t >= 0.5:
            headline(cv, hook_text(self.data), 330, 108, k=(t - 0.5) / 0.18)
        t_card = 2.3 if self.proof and self.proof.card else 99
        if 1.5 <= t < t_card:
            k = M.ease_out_back(M.prog(t, 1.5, 0.25)) * (1 + 0.06 * math.sin(t * 9))
            put(cv, big_q(), min(W - 200, max(200, ox)), min(1150, max(700, oy)), scale=max(0.05, 0.7 * k))
        if t >= t_card:
            k = M.ease_out_cubic(M.prog(t, t_card, 0.18))
            cv.alpha_composite(Image.new("RGBA", (W, H), (8, 8, 14, int(120 * k))))
            cf = self._card(t - t_card + 0.1, 0.86)
            put(cv, cf, W / 2, 860 + 30 * (1 - k), alpha=k)
        caption(cv, sc["text"], (t - sc["lead"]) / max(0.3, sc["vd"]))
        return cv

    # ---- kahani: action (flip pal) -> camera cheez par -> ❌ (parchi nahi - jawab "सोचो" ke baad)
    def sc_story(self, sc, t, i=0):
        dur = sc["dur"]
        first, pn = self.story[0], self.wrong
        frames = [f_ for f_ in (pn.get("frames") or []) if f_ and os.path.exists(f_)]
        t_mk = sc["lead"] + sc["vd"] - 0.15
        t1 = 0.0 if first is pn else min(1.0, dur * 0.3)            # pehle pal: ghatna (agar alag chitra ho)
        if t < t1:
            cv = panel_full(first, t / max(0.3, t1), 0.0, 0.0, 0.3, 0.0)
        else:
            tt = t - t1
            step = 0.28
            if frames and tt < step * len(frames):
                pnf = dict(pn, img=frames[min(len(frames) - 1, int(tt / step))], tag="", card=None, badge=None, face=None)
                cv = panel_full(pnf, 0.2, 0.0, 0.0, 0.0, 0.0)
            else:
                t2 = tt - step * len(frames)
                zk = M.clamp(t2 / max(0.5, dur - t1 - step * len(frames)))
                cv = panel_full(pn, 0.3 + 0.7 * zk, M.prog(t, t_mk - 0.35, 0.4), 0.0, M.prog(t2, 0.0, 0.5),
                                M._punch(t, t_mk))
        bands_fast(cv)
        brand(cv)
        d = ImageDraw.Draw(cv)
        stroke_text(d, (W / 2, 150), POV_LINE, font(58), (255, 255, 255), 7)
        headline(cv, "गलती कहाँ होगी?", 300, 96, k=t / 0.15)
        if t >= t_mk:
            km = M.ease_out_back(M.prog(t, t_mk, 0.3))
            put(cv, M.x_mark_sprite(160), W - 150, 470, scale=max(0.05, 1.6 - 0.6 * km))
        caption(cv, sc["text"], (t - sc["lead"]) / max(0.3, sc["vd"]))
        return cv

    # ---- सोचो (~2s): ? -> do vikalp -> 3-2-1. Koi CTA nahi.
    def sc_ruko(self, sc, t):
        key = ("ruko_bg", self.wrong.get("img"))
        if key not in self._last:
            im = panel_full(self.wrong, 1.0, 0.0, 0.0, 1.0, 0.0).convert("RGB").filter(ImageFilter.GaussianBlur(5))
            self._last[key] = Image.blend(im, Image.new("RGB", (W, H), (8, 8, 14)), 0.6).convert("RGBA")
        cv = self._last[key].copy()
        bands_fast(cv)
        brand(cv)
        put(cv, pill("रुको !  पहले सोचो", 56, (255, 255, 255), RED_C), W / 2, 230,
            scale=max(0.05, M.ease_out_back(M.prog(t, 0.0, 0.25))))
        pulse = 1.0 + 0.06 * math.sin(t * 8)
        put(cv, big_q(), W / 2, 640, scale=max(0.05, M.ease_out_back(M.prog(t, 0.05, 0.3))) * pulse)
        vs = vs_letters(self.data)
        if vs:
            for j, (L, txt) in enumerate(vs):
                kj = M.ease_out_back(M.prog(t, 0.45 + 0.12 * j, 0.25))
                jig = 5 * math.sin(t * 40) if t > sc["cd0"] else 0.0
                put(cv, pill(f"{L}  ·  {txt}", 50, NAVY, (255, 255, 255), GOLD), W / 2 + (jig if j else -jig),
                    930 + j * 124, scale=max(0.05, kj))
            put(cv, pill("या", 34, (255, 255, 255), (60, 60, 70)), W / 2, 992,
                scale=max(0.05, M.ease_out_back(M.prog(t, 0.6, 0.2))))
        cd0 = sc["cd0"]
        if t >= cd0:
            n = 3 - min(2, int((t - cd0) / CD_STEP))
            kk = M.ease_out_back(M.prog(t, cd0 + (3 - n) * CD_STEP, 0.15))
            put(cv, countdown(n), W / 2 + 300, 640, scale=max(0.05, 1.35 - 0.35 * kk))
        caption(cv, sc["text"], (t - sc["lead"]) / max(0.3, sc["vd"]), cy=1450)
        return cv

    def sc_ans(self, sc, t):
        pn = self.ans_pn
        dur = sc["dur"]
        cv = panel_full(pn, 0.3 + 0.5 * t / dur, M.prog(t, 0.15, 0.4), M.prog(t, 0.35, 0.35),
                        M.prog(t, 0.1, 0.4), M._punch(t, 0.25))
        bands_fast(cv)
        brand(cv)
        put(cv, pill("सही जवाब", 54, (255, 255, 255), GREEN_C), W / 2, 210,
            scale=max(0.05, M.ease_out_back(M.prog(t, 0.0, 0.25))))
        if t >= 0.25:
            km = M.ease_out_back(M.prog(t, 0.25, 0.25))
            put(cv, M.check_sprite(160), W - 150, 390, scale=max(0.05, 1.6 - 0.6 * km))
        caption(cv, sc["text"], (t - sc["lead"]) / max(0.3, sc["vd"]))
        return cv

    def _blur(self, dark=0.62):
        key = ("rule_bg", dark)
        if key not in self._last:
            self._last[key] = blurred_bg(self.ans_pn, dark)
        cv = self._last[key].copy()
        brand(cv)
        return cv

    # ---- niyam: pehle PO Guide ki asli line (bade akshar + highlighter), fir aasan Hindi
    def sc_rule(self, sc, t):
        cv = self._blur()
        t_hi = min(2.2, sc["dur"] * 0.45) if (self.proof and self.proof.card) else 0.0
        if t < t_hi:
            cf = self._card(t, 1.0)
            put(cv, cf, W / 2, 780, alpha=M.clamp(t / 0.15))
        else:
            k = M.ease_out_cubic(M.clamp((t - t_hi) / 0.25))
            put(cv, pill("आसान भाषा में", 50, (25, 25, 25), GOLD), W / 2, 330, scale=max(0.05, M.ease_out_back(min(1, k))))
            card = rule_card(self.data["fact"], self.cno)
            put(cv, card, W / 2, 420 + card.height / 2 + 40 * (1 - k), alpha=k)
        caption(cv, sc["text"], (t - sc["lead"]) / max(0.3, sc["vd"]), cy=1560)
        return cv

    # ---- TRAP: thappa -> ❌ galat soch -> ✓ sahi baat (niyam card nahi - ek waqt me ek baat)
    def sc_trap(self, sc, t, _unused=0.0):
        cv = self._blur(0.66)
        st = trap_stamp()
        put(cv, st, W / 2, 330, scale=max(0.05, 1.8 - 0.8 * M.ease_out_cubic(M.prog(t, 0.0, 0.22))), angle=-4)
        y = 720
        if self.trap_pair:
            wrong, right = self.trap_pair
            put(cv, trap_row(wrong, False), W / 2, y, scale=max(0.05, M.ease_out_back(M.prog(t, sc["lead"], 0.3))))
            t2 = sc["lead"] + sc["vd"] * 0.45
            put(cv, trap_row(right, True), W / 2, y + 210, scale=max(0.05, M.ease_out_back(M.prog(t, t2, 0.3))))
        else:
            put(cv, trap_row(self.data["trap"], None), W / 2, y + 80,
                scale=max(0.05, M.ease_out_back(M.prog(t, sc["lead"], 0.3))))
        caption(cv, sc["text"], (t - sc["lead"]) / max(0.3, sc["vd"]), cy=1560)
        return cv

    # ---- asli paper ka sawal: sawal + 4 vikalp EK SAATH -> 3-2-1 -> sahi vikalp hara + answer key ka naam
    def sc_pyq(self, sc, t):
        it = self.pyq
        rev = sc.get("rev")
        cv = _paper_bg().copy()
        d = ImageDraw.Draw(cv)
        put(cv, pill("असली पेपर का सवाल", 52, (255, 255, 255), RED_C), W / 2, 190,
            scale=max(0.05, M.ease_out_back(M.prog(t, 0.0, 0.25))))
        ex = [e for e in (it.get("exams") or []) if e][:3]
        y = 268
        if ex:
            d.text((W / 2, y), "  •  ".join(ex), font=font(36), fill=(150, 108, 0), anchor="mm")
            y += 60
        if self.pyq_related:
            put(cv, pill(f"इसी नियम पर पूछा गया  •  Clause {self.cno}", 30, NAVY, (255, 246, 214), GOLD, reg=True),
                W / 2, y + 8)
            y += 76
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dl = ImageDraw.Draw(lay)
        f, s_, ls = fit_wrap(it["q"], 940, 64, 4, 42)
        lh = int(s_ * 1.28)
        y += 26
        for ln in ls:
            dl.text((W / 2, y + lh / 2), ln, font=f, fill=NAVY + (255,), anchor="mm")
            y += lh
        y += 30
        shown = rev is not None and t >= rev
        rows_y = []
        for j, (L, o) in enumerate(zip("ABCD", it["opts"])):
            state = ("right" if L == it["ans"] else "dim") if shown else "norm"
            row = opt_row2(L, o, state)
            sc_ = (1 + 0.05 * (1 - ease((t - rev) / 0.25))) if (shown and state == "right") else 1.0
            put(lay, row, W / 2, y + row.height / 2, scale=sc_)
            rows_y.append(y + row.height / 2)
            y += row.height + 14
        k = M.ease_out_cubic(M.prog(t, 0.0, 0.18))
        put(cv, lay, W / 2, H / 2 + 40 * (1 - k), alpha=k)
        y = min(y + 70, 1600)
        cd0 = sc["cd0"]
        if cd0 <= t < cd0 + 3 * CD_STEP:
            n = 3 - min(2, int((t - cd0) / CD_STEP))
            kk = M.ease_out_back(M.prog(t, cd0 + (3 - n) * CD_STEP, 0.15))
            put(cv, countdown(n), W / 2, y + 40, scale=max(0.05, 1.3 - 0.3 * kk))
        if shown:
            put(cv, M.check_sprite(110), W - 110, rows_y["ABCD".index(it["ans"])],
                scale=max(0.05, M.ease_out_back(M.prog(t, rev, 0.2))))
            src = "उत्तर कुंजी" + (f": {ex[0]}" if ex else "") + "  •  सही जवाब " + it["ans"]
            put(cv, pill(src, 38, (255, 255, 255), NAVY, GOLD, reg=True), W / 2, y + 40,
                scale=max(0.05, M.ease_out_back(M.prog(t, rev + 0.25, 0.2))))
        elif rev is None and t >= cd0 + 3 * CD_STEP:
            put(cv, pill("जवाब कमेंट करो", 52, (25, 25, 25), GOLD), W / 2, y + 40,
                scale=max(0.05, M.ease_out_back(M.prog(t, cd0 + 3 * CD_STEP, 0.25))))
        return cv

    # ---- ant: याद रखो (pramukh) -> chhota Follow -> chhota logo. Ek hi CTA.
    def sc_end(self, sc, t):
        key = ("end_bg",)
        if key not in self._last:
            self._last[key] = blurred_bg(self.ans_pn, 0.68)
        cv = self._last[key].copy()
        d = ImageDraw.Draw(cv)
        put(cv, pill("याद रखो साथियों", 52, (25, 25, 25), GOLD), W / 2, 380,
            scale=max(0.05, M.ease_out_back(M.prog(t, 0.0, 0.25))))
        f, s_, ls = fit_wrap(self.data.get("yaad") or self.data["fact"], 980, 92, 3, 56)
        y0 = 540
        for i, ln in enumerate(ls):
            stroke_text(d, (W / 2, y0 + i * int(s_ * 1.25)), ln, f, (255, 255, 255), 8)
        yb = y0 + len(ls) * int(s_ * 1.25) + 120
        put(cv, pill("ऐसे और Postal Exam सवालों के लिए  FOLLOW करो", 42, (25, 25, 25), GOLD), W / 2, yb,
            scale=max(0.05, M.ease_out_back(M.prog(t, 0.7, 0.25))))
        put(cv, pill("POSTAL WALA", 34, GOLD, NAVY, GOLD), W / 2, yb + 120,
            scale=max(0.05, M.ease_out_back(M.prog(t, 1.5, 0.25))))
        return cv

    def frame(self, tl, gt):
        si = 0
        while si + 1 < len(tl) and gt >= tl[si + 1]["start"]:
            si += 1
        return self.render(tl, si, gt - tl[si]["start"]), si

    def render(self, tl, si, t):
        sc = tl[si]
        n = sc["name"]
        if n == "hook":
            return self.sc_hook(sc, t)
        if n.startswith("s"):
            return self.sc_story(sc, t, int(n[1:]))
        if n == "ruko":
            return self.sc_ruko(sc, t)
        if n == "ans":
            return self.sc_ans(sc, t)
        if n == "rule":
            return self.sc_rule(sc, t)
        if n == "trap":
            return self.sc_trap(sc, t)
        if n == "pyq":
            return self.sc_pyq(sc, t)
        return self.sc_end(sc, t)


@lru_cache(maxsize=32)
def opt_row2(letter, text, state):
    """Vikalp ki patti: norm / right (hara + ✓ jagah) / dim (feeka)."""
    w = 940
    f, s_, ls = fit_wrap(text, w - 170, 50, 2, 34, reg=True)
    lh = int(s_ * 1.25)
    h = max(112, 36 + len(ls) * lh)
    fill = (222, 248, 230) if state == "right" else (255, 255, 255)
    border = GREEN_C if state == "right" else (222, 224, 232)
    txt = (165, 170, 185) if state == "dim" else (25, 30, 45)
    im = Image.new("RGBA", (w + 16, h + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((8, 12, 8 + w, 12 + h), radius=22, fill=(0, 0, 0, 30))
    d.rounded_rectangle((8, 8, 8 + w, 8 + h), radius=22, fill=fill + (255,), outline=border + (255,),
                        width=7 if state == "right" else 3)
    d.ellipse((34, 8 + h / 2 - 32, 98, 8 + h / 2 + 32), fill=(GREEN_C if state == "right" else NAVY) + (255,))
    d.text((66, 8 + h / 2), letter, font=font(38), fill=(255, 255, 255, 255) if state == "right" else (255, 214, 40, 255),
           anchor="mm")
    y = 8 + (h - len(ls) * lh) / 2
    for ln in ls:
        d.text((130, y + lh / 2), ln, font=f, fill=txt + (255,), anchor="lm")
        y += lh
    return im


@lru_cache(maxsize=2)
def big_q():
    f = font(300)
    im = Image.new("RGBA", (360, 400), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((180, 200), "?", font=f, fill=(255, 214, 40, 255), stroke_width=14, stroke_fill=(0, 0, 0, 255), anchor="mm")
    return im


@lru_cache(maxsize=4)
def countdown(n):
    r = 96
    im = Image.new("RGBA", (2 * r + 20, 2 * r + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((10, 10, 10 + 2 * r, 10 + 2 * r), fill=(255, 255, 255, 240), outline=RED_C + (255,), width=12)
    d.text((10 + r, 10 + r), str(n), font=font(130), fill=RED_C + (255,), anchor="mm")
    return im


@lru_cache(maxsize=4)
def trap_stamp():
    f = font(76)
    txt = "EXAM TRAP !"
    w, h = int(tw(txt, f) + 70), 130
    im = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((10, 10, 10 + w, 10 + h), radius=18, fill=(150, 20, 30, 200), outline=(255, 70, 80, 255), width=8)
    d.text((10 + w / 2, 10 + h / 2), txt, font=f, fill=(255, 235, 235, 255), anchor="mm")
    return im


@lru_cache(maxsize=16)
def rule_card(fact, clause_no):
    w = 980
    f, s_, ls = fit_wrap(fact, w - 100, 66, 5, 42)
    lh = int(s_ * 1.32)
    h = 120 + len(ls) * lh + 80
    im = Image.new("RGBA", (w + 24, h + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((12, 20, 12 + w, 20 + h), radius=30, fill=(0, 0, 0, 110))
    d.rounded_rectangle((12, 12, 12 + w, 12 + h), radius=30, fill=CREAM + (255,), outline=GOLD + (255,), width=6)
    lab = pill("पूरा नियम", 34, (255, 255, 255), RED_C)
    im.alpha_composite(lab, (50, 36))
    y = 12 + 120
    for ln in ls:
        d.text((12 + w / 2, y + lh / 2), ln, font=f, fill=NAVY + (255,), anchor="mm")
        y += lh
    d.text((12 + w / 2, 12 + h - 42), f"PO Guide Part I  •  Clause {clause_no}", font=font_reg(30),
           fill=(110, 110, 120, 255), anchor="mm")
    return im


@lru_cache(maxsize=16)
def trap_row(text, good):
    w = 980
    f, s_, ls = fit_wrap(text, w - 200, 58, 3, 38)
    lh = int(s_ * 1.25)
    h = max(160, 56 + len(ls) * lh)
    col = GREEN_C if good else (RED_C if good is False else (230, 140, 20))
    fill = (225, 250, 232) if good else ((255, 228, 230) if good is False else (255, 240, 210))
    im = Image.new("RGBA", (w + 24, h + 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((12, 18, 12 + w, 18 + h), radius=28, fill=(0, 0, 0, 100))
    d.rounded_rectangle((12, 12, 12 + w, 12 + h), radius=28, fill=fill + (255,), outline=col + (255,), width=6)
    icon = M.check_sprite(96) if good else (M.x_mark_sprite(96) if good is False else None)
    if icon is not None:
        im.alpha_composite(icon, (48, int(12 + h / 2 - 48)))
    else:
        d.text((96, 12 + h / 2), "!", font=font(90), fill=col + (255,), anchor="mm")
    y = 12 + (h - len(ls) * lh) / 2
    for ln in ls:
        d.text((180, y + lh / 2), ln, font=f, fill=(30, 30, 40, 255), anchor="lm")
        y += lh
    return im


@lru_cache(maxsize=2)
def share_btn():
    w, h = 900, 170
    im = Image.new("RGBA", (w + 24, h + 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((12, 20, 12 + w, 20 + h), radius=34, fill=(0, 0, 0, 110))
    d.rounded_rectangle((12, 12, 12 + w, 12 + h), radius=34, fill=GOLD + (255,), outline=(255, 245, 200, 255), width=4)
    d.polygon([(70, 12 + h / 2 - 40), (150, 12 + h / 2), (70, 12 + h / 2 + 40), (90, 12 + h / 2)], fill=(20, 20, 20, 255))
    d.text((12 + w / 2 + 50, 12 + h / 2 - 28), "उस साथी को भेजो", font=font(56), fill=(20, 20, 20, 255), anchor="mm")
    d.text((12 + w / 2 + 50, 12 + h / 2 + 38), "जो ये गलती करता है", font=font_reg(38), fill=(40, 40, 40, 255),
           anchor="mm")
    return im


# ============================================================ awaaz + sfx

def build_audio(tl, total, path):
    n = int(total * M.SR) + M.SR
    vt = np.zeros(n, dtype=np.float32)
    for sc in tl:
        M.add_at(vt, sc["audio"], sc["start"] + sc["lead"])
    win = int(0.15 * M.SR)
    env = np.convolve(np.abs(vt), np.ones(win, dtype=np.float32) / win, mode="same")
    duck = 1.0 - np.clip(env * 6, 0, 0.6)
    buf = np.zeros(n, dtype=np.float32)
    bed = M.music_bed(n / M.SR)
    m = min(len(bed), n)
    buf[:m] += bed[:m] * duck[:m]
    for i, sc in enumerate(tl):
        s, nm = sc["start"], sc["name"]
        if i > 0 and nm != "trap":
            M.add_at(buf, M.sfx_whoosh(0.3, 0.32), max(0.0, s - 0.12), 0.9)
        if nm == "hook":
            M.add_at(buf, M.sfx_whoosh(0.3, 0.35), s)
            M.add_at(buf, M.sfx_thud(0.8), s + 0.5)                  # sawal aate hi
            M.add_at(buf, M.sfx_pop(0.4), s + 1.5)
            M.add_at(buf, M.sfx_riser(0.6, 0.1), s + 2.2)
        elif nm == "ruko":
            M.add_at(buf, M.sfx_thud(0.8), s + 0.02)
            for k in range(3):
                M.add_at(buf, M.sfx_tick(0.5), s + sc["cd0"] + k * CD_STEP)
                M.add_at(buf, M.sfx_heartbeat(0.4), s + sc["cd0"] + k * CD_STEP)
        elif nm == "ans":
            M.add_at(buf, M.sfx_ding(0.5), s + 0.3)
            M.add_at(buf, M.sfx_thud(0.5), s + 0.3)
        elif nm == "rule":
            M.add_at(buf, M.sfx_pop(0.32), s + 0.05)
        elif nm == "trap":
            M.add_at(buf, M.sfx_thud(0.9), s + 0.05)
            M.add_at(buf, M.sfx_buzz(0.22), s + sc["lead"] + 0.1)
        elif nm == "pyq":
            M.add_at(buf, M.sfx_pop(0.36), s + 0.05)
            for k in range(3):
                M.add_at(buf, M.sfx_tick(0.5), s + sc["cd0"] + k * CD_STEP)
            if sc.get("rev") is not None:
                M.add_at(buf, M.sfx_ding(0.55), s + sc["rev"])
                M.add_at(vt, sc["audio2"], s + sc["rev"] + 0.05)
        elif nm == "end":
            M.add_at(buf, M.sfx_pop(0.4), s + 0.7)
    # ❌ wale chitra pe buzz
    for sc in tl:
        if sc["name"].startswith("s") and sc.get("wrong"):
            M.add_at(buf, M.sfx_buzz(0.33), sc["start"] + sc["lead"] + sc["vd"] - 0.15)
    out = buf + vt
    peak = float(np.max(np.abs(out))) or 1.0
    if peak > 0.98:
        out = out * (0.98 / peak)
    import wave
    with wave.open(path, "wb") as w_:
        w_.setnchannels(1)
        w_.setsampwidth(2)
        w_.setframerate(M.SR)
        w_.writeframes((np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes())


# ============================================================ poori reel

def usable(data):
    ch = data.get("chitra") or {}
    return ch.get("kit") == "photo" and len(ch.get("panels") or []) >= 2 and all(
        p.get("img") and os.path.exists(p["img"]) for p in ch["panels"])


def build(data, out, plan=None, part=None):
    """Naya format reel. Fail -> exception (main.py purane format se banata hai)."""
    if not usable(data):
        raise RuntimeError("naya format ke liye photo-chitra nahi (purana format chalega)")
    M.resolve_font()
    panels = data["chitra"]["panels"]
    story, ans_pn = story_split(panels)
    proof = None
    if plan is not None and part is not None:
        a = proof_assets(plan, part, data)
        if a:
            proof = Proof(a, data.get("clause_no"), int(data.get("episode") or 0))
    pyq, pyq_rel = None, False
    if plan is not None and part is not None:
        try:
            pyq, pyq_rel = pyq_for(plan, part, data)
        except Exception as exc:
            print("  Ant ka asli paper sawal nahi juda (reel bina iske):", str(exc)[:140])
    if pyq:
        print(f"  Ant me asli paper sawal ({'isi niyam ka' if pyq_rel else 'bank se'}): {pyq['q'][:80]} | jawab {pyq['ans']}")
        data["naya_pyq"] = {"q": pyq["q"], "opts": pyq["opts"], "ans": pyq["ans"], "exams": pyq.get("exams") or [],
                            "related": pyq_rel}
    specs = build_specs(data, story, ans_pn, bool(proof), pyq)
    print(f"NAYA FORMAT ({NAYA_VERSION.split(':')[0]}): awaaz ban rahi hai ({len(specs)} tukde)...")
    voices = M.make_voices(specs)
    voices = [tuple([M.speed_voice(v[0], NAYA_SPEED)] + list(v[1:])) for v in voices]
    tl, total = plan_timeline(specs, voices, data)
    for sc in tl:
        if sc["name"].startswith("s"):
            sc["wrong"] = any(p.get("mark") == "wrong" for p in story)
    print("  NAYA TIMELINE (drishya | shuru | lambai | awaaz)")
    for sc in tl:
        print(f"  {sc['name']:<6} {sc['start']:5.2f}s  {sc['dur']:4.2f}s  voice {sc['vd']:4.2f}s")
    reel = Reel(data, story, ans_pn, proof, pyq, pyq_rel)
    apath = out.replace(".mp4", "_naya_audio.wav")
    build_audio(tl, total, apath)
    n_frames = int(math.ceil(total * FPS))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", apath, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium",
           "-crf", str(M.VIDEO_CRF), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    prev = {}
    try:
        for fi in range(n_frames):
            gt = fi / FPS
            fr, si = reel.frame(tl, gt)
            tt = gt - tl[si]["start"]
            if si > 0 and tt < TRANS and tl[si]["name"] != "trap":
                if si not in prev:
                    prev = {si: reel.render(tl, si - 1, tl[si - 1]["dur"] - 1.0 / FPS)}
                k = M.ease_in_out(tt / TRANS)
                base = Image.new("RGBA", (W, H), (0, 0, 0, 255))
                base.alpha_composite(prev[si], (int(-k * W * 0.35), 0))
                cur = fr.copy()
                cur.putalpha(int(255 * min(1.0, k * 1.6)))
                base.alpha_composite(cur, (int((1 - k) * W * 0.5), 0))
                fr = base
            proc.stdin.write(fr.convert("RGB").tobytes())
            if fi % 120 == 0:
                print(f"  frame {fi}/{n_frames}")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    ret = proc.wait()
    if os.path.exists(apath):
        os.remove(apath)
    if ret != 0:
        raise RuntimeError("ffmpeg (naya format) fail")
    print(f"COMPLETE (naya format): {out} ({total:.2f}s)")
    return total
