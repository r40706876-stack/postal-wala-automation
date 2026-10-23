"""
POSTAL WALA -> INSTAGRAM (seedha post) - v23 (2026-10-23)
=========================================================
  python ig_post.py am       -> aaj ki 8 AM wali 7 PYQ quiz reel
  python ig_post.py series   -> aaj bani clause series reel (5 PM)
  python ig_post.py pm       -> aaj ki 9 PM wali 7 PYQ copy-panna reel + uska carousel
Har post: caption file ka upar wala hissa = caption (title + description + hashtags), "-----" ke neeche wala
hissa = pehla comment. Cover (thumbnail) = *_cover.jpg (repo public hai -> raw GitHub link se Instagram uthata hai).
Ek cheez kabhi do baar post nahi hoti (generated_reels/ig_posted.json). Kuch fail ho -> log me wajah, reel repo me
rehti hai (aap haath se daal sakte ho). Secrets: IG_ACCESS_TOKEN, IG_USER_ID (Postal Wala ke Instagram account ke).
Instagram API comment PIN nahi kar sakti - pehla comment apne aap jaata hai, PIN aap app se karo.
"""
import datetime
import glob
import json
import os
import subprocess
import sys
import time

import requests

IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "").strip()
IG_USER_ID = os.getenv("IG_USER_ID", "").strip()
GRAPH_VER = "v19.0"
GRAPH = f"https://graph.facebook.com/{GRAPH_VER}/"
REPO = os.getenv("GITHUB_REPOSITORY", "r40706876-stack/postal-wala-automation")
OUT = "generated_reels"
LOG = os.path.join(OUT, "ig_posted.json")
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"


def today():
    return datetime.datetime.now(IST).date().isoformat()


def load_log():
    try:
        with open(LOG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_log(lg):
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(lg, f, ensure_ascii=False, indent=1)


def raw_url(path):
    """Repo public hai: commit hui file ka seedha link (SHA wala - cache purana na mile)."""
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or "main"
    return f"https://raw.githubusercontent.com/{REPO}/{sha}/{path.replace(os.sep, '/')}"


def split_caption(path):
    if not path or not os.path.exists(path):
        return "", ""
    txt = open(path, encoding="utf-8").read()
    lines = txt.splitlines()
    cut = next((i for i, l in enumerate(lines) if l.strip().startswith("-----")), None)
    if cut is None:
        return txt.strip()[:2150], ""
    cap = "\n".join(lines[:cut]).strip()
    com = "\n".join(l for l in lines[cut + 1:] if not l.strip().startswith("-----")).strip()
    return cap[:2150], com[:2000]


def _wait_finished(cid, tries=40):
    status = ""
    for _ in range(tries):
        time.sleep(10)
        st = requests.get(f"{GRAPH}{cid}", params={"fields": "status_code,status", "access_token": IG_ACCESS_TOKEN},
                          timeout=30).json()
        status = st.get("status_code", "")
        print("  IG processing:", status)
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"IG processing {status}: {st}")
    raise RuntimeError("IG processing time-out")


def _publish(cid):
    pub = {}
    for k in range(3):
        pub = requests.post(f"{GRAPH}{IG_USER_ID}/media_publish",
                            data={"creation_id": cid, "access_token": IG_ACCESS_TOKEN}, timeout=60).json()
        if pub.get("id"):
            return pub["id"]
        print("  publish dobara:", pub)
        time.sleep(20)
    raise RuntimeError(f"IG publish fail: {pub}")


def _reel_once(video, caption, cover_url=None):
    body = {"media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true",
            "access_token": IG_ACCESS_TOKEN}
    if cover_url:
        body["cover_url"] = cover_url
    else:
        body["thumb_offset"] = "500"
    r = requests.post(f"{GRAPH}{IG_USER_ID}/media", data=body, timeout=60).json()
    cid = r.get("id")
    if not cid:
        raise RuntimeError(f"IG container nahi bana: {r}")
    print("  IG container:", cid)
    time.sleep(10)
    up_url = r.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{GRAPH_VER}/{cid}"
    size = os.path.getsize(video)
    with open(video, "rb") as vf:
        data = vf.read()
    up = None
    for k in range(3):
        up = requests.post(up_url, headers={"Authorization": f"OAuth {IG_ACCESS_TOKEN}", "offset": "0",
                                            "file_size": str(size), "Content-Type": "application/octet-stream"},
                           data=data, timeout=600)
        print(f"  upload try {k + 1}: HTTP {up.status_code} {up.text[:120]}")
        if up.status_code < 300:
            break
        time.sleep(15 * (k + 1))
    if up.status_code >= 300:
        raise RuntimeError(f"IG upload fail: {up.status_code} {up.text[:200]}")
    _wait_finished(cid)
    return _publish(cid)


def post_reel(video, caption, cover=None):
    cover_url = raw_url(cover) if cover and os.path.exists(cover) else None
    last = None
    for attempt in range(3):
        try:
            pid = _reel_once(video, caption, cover_url if attempt == 0 else None)   # cover na chale -> bina cover
            print("INSTAGRAM REEL POST:", pid)
            return pid
        except Exception as exc:
            last = exc
            print(f"  koshish {attempt + 1} fail:", str(exc)[:300])
            time.sleep(30)
    raise RuntimeError(f"Reel 3 baar fail: {last}")


def post_carousel(images, caption):
    kids = []
    for p in images[:10]:
        r = requests.post(f"{GRAPH}{IG_USER_ID}/media", data={"image_url": raw_url(p), "is_carousel_item": "true",
                                                              "access_token": IG_ACCESS_TOKEN}, timeout=60).json()
        if not r.get("id"):
            raise RuntimeError(f"carousel slide nahi bani ({p}): {r}")
        kids.append(r["id"])
    r = requests.post(f"{GRAPH}{IG_USER_ID}/media", data={"media_type": "CAROUSEL", "children": ",".join(kids),
                                                          "caption": caption, "access_token": IG_ACCESS_TOKEN},
                      timeout=60).json()
    cid = r.get("id")
    if not cid:
        raise RuntimeError(f"carousel container nahi bana: {r}")
    _wait_finished(cid, 20)
    pid = _publish(cid)
    print("INSTAGRAM CAROUSEL POST:", pid)
    return pid


def post_comment(media_id, text):
    if not text:
        return None
    for attempt in range(4):
        time.sleep(15 if attempt == 0 else 25)
        try:
            r = requests.post(f"{GRAPH}{media_id}/comments", data={"message": text, "access_token": IG_ACCESS_TOKEN},
                              timeout=60).json()
        except Exception as exc:
            r = {"error": str(exc)[:150]}
        if r.get("id"):
            print("  Pehla comment ho gaya (PIN app se karo):", r["id"])
            return r["id"]
        print("  comment dobara:", str(r)[:200])
    return None


# ------------------------------------------------------------ aaj kya post karna hai

def items_for(job):
    d0 = today()
    out = []
    if job in ("am", "pm"):
        try:
            st = json.load(open(os.path.join(OUT, "pyq", "daily_state.json"), encoding="utf-8"))
        except Exception:
            st = {}
        f = (st.get(job) or {}).get(d0)
        if f:
            v = os.path.join(OUT, "pyq", f)
            out.append({"key": f, "video": v, "caption": v.replace(".mp4", "_caption.txt"),
                        "cover": v.replace(".mp4", "_cover.jpg")})
            if job == "pm":
                folder = os.path.join(OUT, "pyq", f"carousel_9pm_{d0}")
                imgs = sorted(glob.glob(os.path.join(folder, "*.jpg")))
                if len(imgs) >= 2:
                    out.append({"key": f"carousel_9pm_{d0}", "images": imgs, "caption": v.replace(".mp4", "_caption.txt")})
    elif job == "series":
        try:
            idx = json.load(open(os.path.join(OUT, "reel_index.json"), encoding="utf-8"))
        except Exception:
            idx = []
        made_today = [n for n in idx if n.startswith("reel_clause_") and os.path.exists(os.path.join(OUT, n))
                      and _made_on(os.path.join(OUT, n)) == d0]
        if made_today:
            v = os.path.join(OUT, made_today[-1])
            out.append({"key": made_today[-1], "video": v, "caption": v.replace(".mp4", "_caption.txt"),
                        "cover": v.replace(".mp4", "_cover.jpg")})
    return out


def _made_on(path):
    """GitHub checkout me file ka samay bharosemand nahi -> git commit ka din (IST); na mile to file ka samay."""
    r = subprocess.run(["git", "log", "-1", "--format=%cI", "--", path], capture_output=True, text=True).stdout.strip()
    try:
        return datetime.datetime.fromisoformat(r).astimezone(IST).date().isoformat()
    except Exception:
        return datetime.datetime.fromtimestamp(os.path.getmtime(path), IST).date().isoformat()


def run(job):
    if not IG_ACCESS_TOKEN or not IG_USER_ID:
        print("IG_ACCESS_TOKEN / IG_USER_ID secrets nahi - Instagram post skip (reel repo me bani hai).")
        return
    lg = load_log()
    items = items_for(job)
    if not items:
        print(f"{job}: aaj post karne layak kuch nahi mila")
        return
    for it in items:
        if it["key"] in lg:
            print("Pehle hi post ho chuka:", it["key"], lg[it["key"]])
            continue
        cap, com = split_caption(it.get("caption"))
        print(f"\nPOST ({job}): {it['key']}\n--- caption ---\n{cap[:300]}...\n")
        if DRY_RUN:
            continue
        try:
            if "images" in it:
                pid = post_carousel(it["images"], cap)
            else:
                pid = post_reel(it["video"], cap, it.get("cover"))
            cid = post_comment(pid, com) if com and "images" not in it else None
            lg[it["key"]] = {"id": pid, "comment": cid, "time": datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M")}
            save_log(lg)
        except Exception as exc:
            print(f"POST NAHI HUA ({it['key']}): {str(exc)[:300]}  -> reel repo me hai, haath se daal sakte ho")
            lg.setdefault("_fail", {})[it["key"]] = str(exc)[:200]
            save_log(lg)


def check():
    """Bina post kiye jaanch: token chalu hai? kaunsa account? publish ki ijaazat?"""
    if not IG_ACCESS_TOKEN or not IG_USER_ID:
        print("CHECK FAIL: IG_ACCESS_TOKEN / IG_USER_ID secrets nahi mile")
        return
    r = requests.get(f"{GRAPH}{IG_USER_ID}", params={"fields": "username,name,media_count,followers_count",
                                                       "access_token": IG_ACCESS_TOKEN}, timeout=30).json()
    if "error" in r:
        print("CHECK FAIL (token/user id):", r["error"].get("message", r))
        return
    print(f"CHECK OK: account @{r.get('username')} | posts {r.get('media_count')} | followers {r.get('followers_count')}")
    q = requests.get(f"{GRAPH}{IG_USER_ID}/content_publishing_limit",
                     params={"fields": "quota_usage,config", "access_token": IG_ACCESS_TOKEN}, timeout=30).json()
    print("CHECK publish ijaazat:", "OK" if "data" in q else f"FAIL {q.get('error', {}).get('message', q)}", str(q)[:200])


if __name__ == "__main__":
    arg = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    check() if arg == "check" else run(arg)
