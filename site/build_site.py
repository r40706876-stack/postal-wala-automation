"""Postal Wala website builder.
Repo ke pyq_papers/pyq_bank.json + clause_plans/clause_*.json + site/notes/ se docs/ website banata hai.
Naye PYQ / clause / notes jodne ke baad bas:  python site/build_site.py
  --artifact  : Claude preview ke liye (bina PWA files)
"""
import json, glob, os, re, sys, shutil

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
ROOT = ARGS[0] if ARGS else "."
HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "site_template.html")
OUTDIR = ARGS[1] if len(ARGS) > 1 else os.path.join(ROOT, "docs")
OUT = os.path.join(OUTDIR, "index.html")
ARTIFACT = "--artifact" in sys.argv

# ---------- PYQ ----------
bank = json.load(open(os.path.join(ROOT, "pyq_papers", "pyq_bank.json"), encoding="utf-8"))
qmap_path = os.path.join(HERE, "notes", "qmap.json")
qmap = json.load(open(qmap_path, encoding="utf-8")) if os.path.exists(qmap_path) else {}
pyq = []
for it in bank.get("items", []):
    opts = it.get("opts") or []
    if len(opts) != 4 or it.get("ans") not in "ABCD":
        continue
    q = {"id": it["id"], "q": it["q"], "e": it.get("q_en", ""), "o": opts,
         "a": "ABCD".index(it["ans"]), "x": it.get("exams", [])}
    if it["id"] in qmap:
        v = qmap[it["id"]]  # [clause, x0, y0, x1, y1, text_key] notes PDF ka hissa
        q["nt"] = v[:5]
        txt = qmap.get("_texts", {}).get(v[5] if len(v) > 5 else "", {})
        if txt:
            q["nx"] = [txt.get("hi", ""), txt.get("en", "")]
    pyq.append(q)

# ---------- clause practice ----------
clauses = []
for f in glob.glob(os.path.join(ROOT, "clause_plans", "clause_*.json")):
    m = re.search(r"clause_(\d+)\.json$", f)
    if not m:
        continue
    c = json.load(open(f, encoding="utf-8"))
    parts = []
    for p in c.get("parts", []):
        if not (p.get("auto_check") or p.get("published")):
            continue
        if p.get("correct") not in list("ABCD"):
            continue
        parts.append({"q": p["question"], "o": [p["a"], p["b"], p["c"], p["d"]],
                      "a": "ABCD".index(p["correct"]), "f": p.get("fact", ""),
                      "y": p.get("yaad", ""), "e": (p.get("en") or {}).get("question", "")})
    if parts:
        clauses.append({"n": c["clause_no"], "h": c.get("title_hi", ""), "t": c.get("title_en", ""), "p": parts})
clauses.sort(key=lambda c: c["n"])

# ---------- PYQ jinke liye notes ka hissa nahi: PO Guide clause ka niyam (milte-julte sawal se) ----------
def grams(s):
    s = re.sub(r"[\s\?\.,।:;'\"\-–—()]+", "", s)
    return {s[i:i + 3] for i in range(len(s) - 2)}
cparts = [(c["n"], p, grams(p["q"] + " " + p["o"][p["a"]])) for c in clauses for p in c["p"]]
linked = 0
for q in pyq:
    if "nt" in q:
        continue
    g = grams(q["q"] + " " + q["o"][q["a"]])
    best = max(((len(g & cg) / max(1, len(g | cg)), n, p) for n, p, cg in cparts), default=None, key=lambda x: x[0])
    if best and best[0] >= 0.30 and best[2]["f"]:
        q["f"], q["c"] = best[2]["f"], best[1]
        linked += 1

data = json.dumps({"pyq": pyq, "clauses": clauses}, ensure_ascii=False, separators=(",", ":"))
html = open(TEMPLATE, encoding="utf-8").read().replace("/*__DATA__*/null", data)
html = html.replace("/*__LOGO__*/", open(os.path.join(HERE, "logo.txt")).read().strip())

os.makedirs(OUTDIR, exist_ok=True)
src_notes = os.path.join(HERE, "notes")
if os.path.isdir(src_notes):
    dst = os.path.join(OUTDIR, "notes")
    shutil.copytree(src_notes, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.json"))

if not ARTIFACT:  # GitHub Pages: pura HTML + phone me install (PWA) + offline
    pwa = ('<link rel="manifest" href="manifest.webmanifest">'
           '<link rel="apple-touch-icon" href="icon-192.png"><meta name="apple-mobile-web-app-capable" content="yes">')
    html = ('<!doctype html>\n<html lang="hi"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n' + pwa + "\n"
            + html.replace("<div class=\"airmail\"", "</head><body>\n<div class=\"airmail\"", 1)
            + "\n<script>if('serviceWorker' in navigator)navigator.serviceWorker.register('sw.js').catch(()=>{});</script>"
            + "\n</body></html>\n")
    for s in (192, 512):
        src = os.path.join(HERE, "icon.png")
        if os.path.exists(src):
            from PIL import Image
            Image.open(src).convert("RGB").resize((s, s), Image.LANCZOS).save(os.path.join(OUTDIR, f"icon-{s}.png"))
    json.dump({"name": "Postal Wala", "short_name": "Postal Wala", "start_url": "./", "display": "standalone",
               "background_color": "#FBF6EC", "theme_color": "#232E5C", "lang": "hi",
               "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
                         {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]},
              open(os.path.join(OUTDIR, "manifest.webmanifest"), "w"))
    imgs = sorted("notes/" + f for f in os.listdir(os.path.join(OUTDIR, "notes"))) if os.path.isdir(os.path.join(OUTDIR, "notes")) else []
    ver = str(abs(hash(data)) % 10**8)
    open(os.path.join(OUTDIR, "sw.js"), "w").write(
        "const C='pw-" + ver + "';const PRE=" + json.dumps(["./", "index.html"] + [i for i in imgs if i.endswith("_t.webp")]) + ";\n"
        "self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(C).then(c=>c.addAll(PRE)))});\n"
        "self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));\n"
        "self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request).then(res=>{"
        "if(res.ok&&new URL(e.request.url).origin===location.origin){const cp=res.clone();caches.open(C).then(c=>c.put(e.request,cp))}return res}).catch(()=>caches.match('index.html'))))});\n")

open(OUT, "w", encoding="utf-8").write(html)
print(f"OK: {len(pyq)} PYQ ({sum('nt' in q for q in pyq)} notes-PDF se, {linked} PO Guide niyam se), "
      f"{len(clauses)} clause, {sum(len(c['p']) for c in clauses)} sawal -> {OUT}")
