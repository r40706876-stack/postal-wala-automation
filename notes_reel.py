"""
POSTAL WALA - DAILY NOTES REEL (handnotes/ ke handwritten notes se)
====================================================================
Roz ek topic (notes ki ek laal/neeli patti = ek topic). Din 1 = topic 1 Hindi, din 2 = wahi topic English, ...
Reel: hook (PYQ thappa) -> topic ki khaas lines (asli handwriting, ek-ek karke) -> "एक नज़र" tiles ->
      परीक्षा ट्रैप -> याद रखो ट्रिक -> सवाल (jawab pehle comment me) -> PDF CTA + "कल का टॉपिक"
Awaaz: Gemini (main.py wali). Script sirf notes ki lines se - har number source me hona chahiye, warna wahi line padhi jaati hai.

  python notes_reel.py build            -> aaj ki reel (state ke hisaab se), notes_reels/ me
  python notes_reel.py build --demo 03:VPP:hi   -> demo (state nahi badalta)
  python notes_reel.py post             -> aaj bani reel Instagram par (ig_post.py ke functions se)
  python notes_reel.py list             -> saare topic
"""
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import wave

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
NOTES = os.path.join(ROOT, "handnotes")
OUT = os.path.join(ROOT, "notes_reels")
STATE = os.path.join(OUT, "state.json")
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
SITE = "r40706876-stack.github.io/postal-wala-automation"
MAX_LINES = 3

TXT = {
    "hi": {"trap": "⚠ परीक्षा ट्रैप", "trick": "याद रखो ट्रिक", "glance": "एक नज़र में", "q": "जवाब कमेंट करो ↓",
           "cta1": "ऐसे 66 टॉपिक · पूरी PDF", "cta2": "PDF लिंक बायो में ↑", "tom": "कल का टॉपिक", "pyq": "PYQ",
           "sure": "परीक्षा का पक्का टॉपिक", "day": "दिन", "follow": "रोज़ 1 टॉपिक · FOLLOW करो"},
    "en": {"trap": "⚠ EXAM TRAP", "trick": "MEMORY TRICK", "glance": "At a glance", "q": "Comment your answer ↓",
           "cta1": "66 topics like this · full PDF", "cta2": "PDF link in bio ↑", "tom": "Tomorrow", "pyq": "PYQ",
           "sure": "Sure-shot exam topic", "day": "Day", "follow": "1 topic daily · FOLLOW"},
}


# ------------------------------------------------------------------ topics (Playwright se notes padho)

JS_TOPICS = r"""
() => {
  const out = [];
  const hs = [...document.querySelectorAll('main h2')];
  hs.forEach((h, i) => {
    const hc = h.cloneNode(true); hc.querySelector('.cl')?.remove();
    const t = {i, title: hc.innerText.trim(), lines: [], glance: null, traps: [], tricks: [], pyq: []};
    let el = h.nextElementSibling;
    while (el && el.tagName !== 'H2') {
      if (el.matches('.mm, .cover, .src, .legend')) { el = el.nextElementSibling; continue; }
      if (el.matches('ul, ol')) el.querySelectorAll(':scope > li').forEach(li => t.lines.push(li));
      if (el.matches('table') || el.querySelector?.('table')) { const tb = el.matches('table') ? el : el.querySelector('table'); if (tb && !el.matches('.glance')) t.lines.push(tb); }
      if (el.matches('.glance')) t.glance = el;
      if (el.matches('.trap')) t.traps.push(el);
      if (el.matches('.trick')) t.tricks.push(el);
      if (el.matches('.two, .cols, .box, div') && !el.matches('.glance, .trap, .trick, .quiz, .mm'))
        el.querySelectorAll('li').forEach(li => t.lines.push(li));
      el = el.nextElementSibling;
    }
    if (t.glance) {
      t.glance.querySelectorAll('.trap').forEach(x => t.traps.push(x));
      t.glance.querySelectorAll('.trick').forEach(x => t.tricks.push(x));
    }
    const uniq = [...new Set(t.lines)];
    out.push({i, title: t.title,
      lines: uniq.map(li => ({text: li.innerText.replace(/\s+/g, ' ').trim(),
        say: (() => { const c = li.cloneNode(true); c.querySelectorAll('.pyq, .imp').forEach(x => x.remove()); return c.innerText.replace(/\s+/g, ' ').trim(); })(),
        score: 3 * !!li.querySelector('.imp') + 3 * !!li.querySelector('.pyq') + 2 * !!li.querySelector('mark') + !!li.querySelector('b'),
        pyq: [...li.querySelectorAll('.pyq')].map(p => p.innerText.replace(/^.*PYQ\s*·\s*/, '').trim()),
        tall: li.getBoundingClientRect().height})),
      tiles: t.glance ? [...t.glance.querySelectorAll('.tile')].map(x => x.innerText.replace(/\s+/g, ' ').trim()) : [],
      glanceTitle: t.glance ? (t.glance.querySelector('b')?.innerText || '') : '',
      trap: t.traps.map(x => x.innerText.replace(/\s+/g, ' ').trim()),
      trick: t.tricks.map(x => x.innerText.replace(/\s+/g, ' ').trim())});
    window.__T = window.__T || []; window.__T[i] = t;
  });
  const q = document.querySelector('.quiz');
  const quiz = q ? {qs: [...q.querySelectorAll('ol > li')].map(x => x.innerText.trim()),
                    ans: (q.querySelector('.ans')?.innerText || '')} : null;
  return {topics: out, quiz};
}
"""


def _browser():
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    b = pw.chromium.launch()
    return pw, b


def read_topics(page, part, lang):
    page.goto("file://" + os.path.join(NOTES, f"notes_{part}_{lang}.html"))
    page.wait_for_load_state("networkidle")
    page.evaluate("document.fonts.ready")
    return page.evaluate(JS_TOPICS)


def all_topics():
    pw, b = _browser()
    pg = b.new_page(viewport={"width": 760, "height": 1200})
    res = []
    for k in range(1, 7):
        part = f"{k:02d}"
        hi = read_topics(pg, part, "hi")["topics"]
        en = read_topics(pg, part, "en")["topics"]
        for i, t in enumerate(hi):
            res.append({"part": part, "i": i, "hi": t["title"], "en": en[i]["title"] if i < len(en) else t["title"],
                        "n_lines": len(t["lines"])})
    b.close(); pw.stop()
    return [t for t in res if t["n_lines"] >= 2]          # khaali/sirf-tasveer wale topic chhodo


# ------------------------------------------------------------------ screenshots

def shoot(page, part, lang, i, tmp):
    data = read_topics(page, part, lang)
    t = data["topics"][i]
    page.evaluate("""() => { document.querySelectorAll('.pyq').forEach(e => e.style.whiteSpace = 'nowrap'); }""")
    order = sorted(range(len(t["lines"])), key=lambda k: -t["lines"][k]["score"])
    pick = sorted(order[:MAX_LINES]) if len(t["lines"]) > MAX_LINES else list(range(len(t["lines"])))
    shots = {"title": os.path.join(tmp, "title.png"), "lines": [], "tiles": [], "trap": None, "trick": None}
    h = page.locator("main h2").nth(i)
    h.scroll_into_view_if_needed(); h.screenshot(path=shots["title"])
    for n, k in enumerate(pick):
        p = os.path.join(tmp, f"line{n}.png")
        el = page.evaluate_handle("([i,k]) => [...new Set(window.__T[i].lines)][k]", [i, k])
        el.as_element().screenshot(path=p)
        shots["lines"].append(p)
    if t["tiles"]:
        tiles = page.evaluate_handle(f"() => [...window.__T[{i}].glance.querySelectorAll('.tile')]")
        for n in range(min(len(t["tiles"]), 6)):
            p = os.path.join(tmp, f"tile{n}.png")
            tiles.evaluate_handle(f"a => a[{n}]").as_element().screenshot(path=p)
            shots["tiles"].append(p)
    for kind in ("trap", "trick"):
        if t[kind]:
            p = os.path.join(tmp, f"{kind}.png")
            arr = "traps" if kind == "trap" else "tricks"
            page.evaluate_handle(f"() => window.__T[{i}].{arr}[0]").as_element().screenshot(path=p)
            shots[kind] = p
    sel = {"title": t["title"], "lines": [t["lines"][k] for k in pick], "tiles": t["tiles"][:6],
           "glanceTitle": t["glanceTitle"], "trap": t["trap"][:1], "trick": t["trick"][:1],
           "pyq": sorted({p for ln in t["lines"] for p in ln["pyq"]})}
    return sel, shots, data["quiz"]


# ------------------------------------------------------------------ script (Gemini) + jaanch

def _nums(s):
    return set(re.findall(r"\d+(?:[.,]\d+)?", s or ""))


def _clean(s):
    s = re.sub(r"📝|PYQ\s*·[^·]*$", "", s)
    return re.sub(r"\s+", " ", s.replace("·", ",").replace("→", ",")).strip(" ,")


def pick_quiz(quiz, topic_text):
    """Notes ke 'खुद को परखो' me se wo sawal jo sach me isi topic ka ho (sawal ke shabd + jawab dono topic me)."""
    if not quiz or not quiz.get("ans"):
        return None
    ans = re.sub(r"^\s*(जवाब|Answers?)\s*:\s*", "", quiz["ans"])
    parts = re.split(r"\s*·\s*(?=\d+\s)", ans)
    low = topic_text.lower()
    best, best_sc = None, 0.0
    for n, q in enumerate(quiz["qs"]):
        a = next((re.sub(r"^\d+\s+", "", p) for p in parts if p.strip().startswith(str(n + 1) + " ")), None)
        if not a:
            continue
        key = re.sub(r"\(.*?\)", "", a).strip().lower()
        if not key or key not in low:
            continue
        words = [w for w in re.findall(r"[\w\u0900-\u097F]+", q.lower()) if len(w) >= 2]
        stop = {"का", "की", "के", "में", "से", "को", "है", "क्या", "कितने", "कितना", "कौन", "किन", "the", "what", "how",
                "which", "of", "in", "is", "a", "an", "to", "for", "can", "be"}
        words = [w for w in words if w not in stop]
        sc = sum(w in low for w in words) / max(len(words), 1)
        if sc > best_sc:
            best, best_sc = {"q": q, "a": a}, sc
    return best if best_sc >= 0.5 else None


def write_script(sel, lang, quiz):
    import main
    L = "Hindi (simple spoken Hindi, Devanagari)" if lang == "hi" else "simple spoken Indian English"
    src = {"title": sel["title"], "lines": [l["text"] for l in sel["lines"]], "tiles": sel["tiles"],
           "trap": sel["trap"], "trick": sel["trick"], "pyq": sel["pyq"]}
    prompt = f"""You write the voiceover for a 30-40 second Instagram reel for India Post GDS -> MTS/Postman exam aspirants.
Language: {L}. Use ONLY facts from the notes below. Never add any number, rule or name that is not in the notes.
Notes (JSON): {json.dumps(src, ensure_ascii=False)}
Return JSON:
{{"hook": "one punchy line (max 14 words) that makes them stop - a question or 'this comes in exam' style, built from the most important fact; {'mention the PYQ state-year' if sel['pyq'] else 'no state/year'}",
 "lines": ["one short spoken sentence (max 14 words) for EACH notes line, same order, explaining it simply"],
 "tiles": "one short sentence with only the 3 most important numbers from tiles (only if tiles exist, else empty)",
 "trap": "one sentence: where students get it wrong (only from trap text, else empty)",
 "trick": "one sentence memory trick (only from trick text, else empty)"}}
Rules: no line repeats another; no greetings; numbers spoken naturally; lines array length must be {len(src['lines'])}."""
    try:
        res = main.as_dict(main._llm_json(prompt))
    except Exception as exc:
        print("  script AI fail -> notes ki lines hi:", str(exc)[:200])
        res = {}
    out = {"hook": "", "lines": [], "tiles": "", "trap": "", "trick": ""}
    allsrc = json.dumps(src, ensure_ascii=False)
    # har line: AI ka number source me ho, warna notes ki line
    ai_lines = res.get("lines") if isinstance(res.get("lines"), list) else []
    for n, l in enumerate(sel["lines"]):
        a = str(ai_lines[n]) if n < len(ai_lines) else ""
        out["lines"].append(a if a and _nums(a) <= _nums(l["text"]) else _clean(l["say"]))
    for k, srcs in (("tiles", " ".join(sel["tiles"])), ("trap", " ".join(sel["trap"])), ("trick", " ".join(sel["trick"]))):
        if not srcs:
            continue
        a = str(res.get(k) or "")
        out[k] = a if a and _nums(a) <= _nums(srcs) else _clean(srcs)
    h = str(res.get("hook") or "")
    if not h or not _nums(h) <= _nums(allsrc):
        h = (f"{sel['title']} — परीक्षा में ऐसे पूछा गया!" if lang == "hi" else f"{sel['title']} — asked in the exam!") \
            if sel["pyq"] else (f"{sel['title']} — ये गलती मत करना!" if lang == "hi" else f"{sel['title']} — don't make this mistake!")
    out["hook"] = re.sub(r"[📝💡⚠✓★]", "", h)
    if quiz:
        out["quiz"] = ("अब बताओ: " if lang == "hi" else "Now tell me: ") + quiz["q"] + \
                      (" जवाब कमेंट करो!" if lang == "hi" else " Comment your answer!")
    out["cta"] = ("पूरी PDF का लिंक बायो में। रोज़ एक टॉपिक के लिए फॉलो करो!" if lang == "hi"
                  else "Full PDF link in bio. Follow for one topic every day!")
    return out


# ------------------------------------------------------------------ awaaz

def _wav(path, a, sr):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())


def _trim(a, sr, thr=0.012):
    idx = np.where(np.abs(a) > thr)[0]
    return a[max(idx[0] - int(.03 * sr), 0): idx[-1] + int(.1 * sr)] if len(idx) else a


def voice(segments, lang):
    """Har hissa alag awaaz (sahi timing ke liye). Gemini na chale -> edge-tts (reel na ruke)."""
    import asyncio
    import main
    main.GEMINI_TTS_STYLE = ("energetic, friendly teacher making an Instagram reel, clear, lively pace"
                             if lang == "hi" else "energetic friendly Indian teacher, clear Indian English, lively pace")
    if lang == "en":
        main.VOICE_NAME = "en-IN-PrabhatNeural"
    sr = main.SR
    outs, used = [], set()
    gem_ok = True
    for text in segments:
        a = None
        if gem_ok:
            try:
                a = main.gemini_tts_audio([text]); used.add("gemini")
            except Exception as exc:
                print("  Gemini awaaz fail -> edge-tts:", str(exc)[:160]); gem_ok = False
        if a is None:
            mp = tempfile.mktemp(suffix=".mp3")
            asyncio.run(main.tts_save(text, mp))
            raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", mp, "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"],
                                 capture_output=True, check=True).stdout
            a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0; used.add("edge")
        outs.append(_trim(a, sr))
    return outs, sr, used


# ------------------------------------------------------------------ scene + render

SCENE = os.path.join(ROOT, "reels", "src", "notes_scene.html")


def build(spec=None):
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    topics = all_topics()
    st = json.load(open(STATE)) if os.path.exists(STATE) else {"next": 0}
    if spec:                                   # "03:VPP:hi"
        part, needle, lang = spec.split(":")
        k = next(n for n, t in enumerate(topics) if t["part"] == part and needle.lower() in t["hi"].lower() + t["en"].lower())
        day = None
    else:
        day = st["next"]
        k, lang = day // 2, ("hi" if day % 2 == 0 else "en")
        if k >= len(topics):
            print("Saare topic ho gaye - shuru se"); day = 0; k, lang = 0, "hi"
    t = topics[k]
    nxt = topics[(k + 1) % len(topics)] if lang == "en" else t
    tmp = tempfile.mkdtemp(dir=OUT, prefix="tmp_")
    pw = sync_playwright().start(); b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 370, "height": 1600}, device_scale_factor=3)
    sel, shots, quiz = shoot(pg, t["part"], lang, t["i"], tmp)
    b.close(); pw.stop()
    topic_text = " ".join([sel["title"]] + [l["text"] for l in sel["lines"]] + sel["tiles"] + sel["trap"] + sel["trick"])
    q = pick_quiz(quiz, topic_text)
    sc = write_script(sel, lang, q)
    print(json.dumps(sc, ensure_ascii=False, indent=1))
    order = [("hook", sc["hook"])] + [(f"line{n}", s) for n, s in enumerate(sc["lines"])]
    for k2 in ("tiles", "trap", "trick", "quiz"):
        if sc.get(k2) and (k2 != "tiles" or shots["tiles"]) and (k2 not in ("trap", "trick") or shots[k2]):
            order.append((k2, sc[k2]))
    order.append(("cta", sc["cta"]))
    auds, sr, used = voice([s for _, s in order], lang)
    gap = 0.25
    tl, cur = [], 0.35
    for (name, _), a in zip(order, auds):
        d = len(a) / sr
        tl.append({"k": name, "t": round(cur, 2), "d": round(d, 2)})
        cur += d + gap
    total = cur + 1.0
    track = np.zeros(int(total * sr) + sr, dtype=np.float32)
    for seg, a in zip(tl, auds):
        i0 = int(seg["t"] * sr); track[i0:i0 + len(a)] += a
    track = track[:int(total * sr)]; track *= 0.95 / max(np.abs(track).max(), 1e-6)
    wav = os.path.join(tmp, "voice.wav"); _wav(wav, track, sr)
    # scene data
    rel = lambda p: os.path.relpath(p, tmp) if p else None
    dayno = (day // 2 + 1) if day is not None else k + 1
    data = {"lang": lang, "T": TXT[lang], "tl": tl, "total": round(total, 2), "title": rel(shots["title"]),
            "lines": [rel(p) for p in shots["lines"]], "tiles": [rel(p) for p in shots["tiles"]],
            "trap": rel(shots["trap"]), "trick": rel(shots["trick"]), "pyq": sel["pyq"][:2],
            "quiz": q["q"] if q and "quiz" in [o[0] for o in order] else "", "hook": sc["hook"],
            "next": nxt["hi"] if lang == "hi" else nxt["en"], "nextSame": nxt is t, "day": dayno, "site": SITE, "ntopics": len(topics)}
    html = open(SCENE, encoding="utf-8").read().replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    scene = os.path.join(tmp, "scene.html"); open(scene, "w", encoding="utf-8").write(html)
    stamp = datetime.datetime.now(IST).strftime("%Y-%m-%d")
    name = f"notes_{stamp}_{t['part']}-{t['i']:02d}_{lang}" if not spec else f"demo_{t['part']}-{t['i']:02d}_{lang}"
    silent = os.path.join(tmp, "silent.mp4")
    subprocess.run([sys.executable, os.path.join(ROOT, "reels", "src", "render.py"), scene, str(total), silent, "30"], check=True)
    mp4 = os.path.join(OUT, name + ".mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", silent, "-i", wav, "-filter_complex",
                    "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]", "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-shortest", "-movflags", "+faststart", mp4], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(tl[1]["t"] + 0.8 if len(tl) > 1 else 1), "-i", silent,
                    "-frames:v", "1", "-q:v", "3", os.path.join(OUT, name + "_cover.jpg")], check=True)
    # caption + pehla comment
    title = sel["title"]
    if lang == "hi":
        cap = (f"📮 {title} | PO Guide Part I · दिन {dayno}\n{sc['hook']}\n\n"
               f"✅ आसान भाषा · परीक्षा ट्रैप · PYQ · याद रखने की ट्रिक\n📚 पूरी हैंडराइटिंग नोट्स PDF — लिंक बायो में\n"
               f"🔔 रोज़ 1 टॉपिक — FOLLOW @postal_wala\n\n#postalwala #gdstomts #gdstopostman #poguide #indiapost "
               f"#mtsexam #postmanexam #gds #dakvibhag #postalexam")
    else:
        cap = (f"📮 {title} | PO Guide Part I · Day {dayno}\n{sc['hook']}\n\n"
               f"✅ Simple notes · Exam traps · PYQs · Memory tricks\n📚 Full handwritten notes PDF — link in bio\n"
               f"🔔 1 topic daily — FOLLOW @postal_wala\n\n#postalwala #gdstomts #gdstopostman #poguide #indiapost "
               f"#mtsexam #postmanexam #gds #postalexam")
    com = (f"✅ जवाब: {q['a']}" if lang == "hi" else f"✅ Answer: {q['a']}") if data["quiz"] else \
          ("👇 इस टॉपिक की सबसे ज़रूरी लाइन कौन-सी लगी? कमेंट करो" if lang == "hi" else "👇 Which line will you remember? Comment")
    open(os.path.join(OUT, name + "_caption.txt"), "w", encoding="utf-8").write(cap + "\n-----\n" + com + "\n")
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    if not spec:
        st["next"] = day + 1
        st["today"] = {"date": stamp, "file": name + ".mp4", "topic": title, "lang": lang}
        json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=1)
    print(f"OK {mp4}  {total:.1f}s  awaaz: {','.join(sorted(used))}")


def post():
    import ig_post
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    td = st.get("today") or {}
    if td.get("date") != datetime.datetime.now(IST).strftime("%Y-%m-%d"):
        print("Aaj ki notes reel nahi bani - post nahi"); return
    v = os.path.join(OUT, td["file"])
    lg = ig_post.load_log()
    if td["file"] in lg:
        print("Pehle hi post:", lg[td["file"]]); return
    if not ig_post.IG_ACCESS_TOKEN or not ig_post.IG_USER_ID:
        print("IG secrets nahi - post skip"); return
    cap, com = ig_post.split_caption(v.replace(".mp4", "_caption.txt"))
    try:
        pid = ig_post.post_reel(v, cap, v.replace(".mp4", "_cover.jpg"))
        cid = ig_post.post_comment(pid, com)
        lg[td["file"]] = {"id": pid, "comment": cid, "time": datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M")}
    except Exception as exc:
        print("POST NAHI HUA:", str(exc)[:300]); lg.setdefault("_fail", {})[td["file"]] = str(exc)[:200]
    ig_post.save_log(lg)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "list":
        for n, t in enumerate(all_topics()):
            print(n, t["part"], t["i"], t["hi"], "|", t["en"], t["n_lines"])
    elif cmd == "build":
        demo = sys.argv[sys.argv.index("--demo") + 1] if "--demo" in sys.argv else None
        for d in (demo.split(",") if demo else [None]):
            build(d.strip() if d else None)
    elif cmd == "post":
        post()
