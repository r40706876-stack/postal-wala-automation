"""Publish one already-approved Postal Edge Reel at the fixed IST slot."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import time

import requests

sys.path.insert(0, os.getcwd())
import ig_post as ig

TARGET = datetime.fromisoformat("2026-11-21T07:00:00+05:30")
EXPECTED = {
    "reel.mp4": "4b5fd6b48e4a5573da93bd6fb17a8053f53fa9e4134bb3bdb9a03940c9e8f8b8",
    "cover.jpg": "8381efa8708825460c6b4db078b766aa015288d8cf5132aa5c66e6dd6e661ee8",
}
TITLE = "3 साल की GDS सेवा पर Postman का पेपर?"
CAPTION = f"""{TITLE}

Postman और Mail Guard की परीक्षा के लिए नियमित GDS सेवा की शर्त 5 साल से घटाकर 3 साल करने का प्रस्ताव है। यह 20 नवंबर 2026 का मसौदा है। अंतिम अधिसूचना बाकी है।

रील में दिल्ली की Pay Level 3 सैलरी का उदाहरण भी है। फ्री PO Guide डेमो क्लास के लिए postaledge.in देखें।

इस अपडेट को अपने GDS साथियों के साथ शेयर करें।

#PostalEdge #PostalWala #GDS #PostmanExam #IndiaPost"""
OUT = Path("../release-result")
BASE = os.environ["APPROVED_SOURCE_URL"].rstrip("/")
SESSION = requests.Session()

def get(path, **params):
    response = SESSION.get(ig.GRAPH + path,params={**params,"access_token":ig.IG_ACCESS_TOKEN},timeout=30)
    data = response.json()
    if not response.ok or "error" in data:
        raise RuntimeError(f"Instagram read failed with HTTP {response.status_code}")
    return data

def already_published():
    for item in get(ig.IG_USER_ID+"/media",fields="id,caption,permalink,timestamp",limit=30)["data"]:
        caption = item.get("caption") or ""
        timestamp = item.get("timestamp")
        if timestamp and caption.startswith(TITLE) and datetime.fromisoformat(timestamp) >= TARGET:
            return item
    return None

def receipt(item):
    result = {"status":"published","account":"@postal_edge","scheduled_for":TARGET.isoformat(),
              "media_id":item["id"],"permalink":item.get("permalink"),"published_at":item.get("timestamp")}
    (OUT/"receipt.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False),flush=True)

def now():
    return datetime.now(timezone.utc)

def main():
    OUT.mkdir(exist_ok=True)
    assert now().timestamp() < TARGET.timestamp()+180, "Scheduled publication window has passed"
    for name,digest in EXPECTED.items():
        response = SESSION.get(BASE+"/"+name,timeout=90)
        response.raise_for_status()
        if sha256(response.content).hexdigest()!=digest:
            raise RuntimeError(f"Approved asset checksum mismatch for {name}")
    account = get(ig.IG_USER_ID,fields="username")["username"].lower()
    if account!="postal_edge":
        raise RuntimeError("The configured Instagram identity is not @postal_edge")
    prior=already_published()
    if prior:
        receipt(prior)
        return
    token_check = SESSION.get(ig.GRAPH+"debug_token",params={
        "input_token":ig.IG_ACCESS_TOKEN,"access_token":ig.IG_ACCESS_TOKEN},timeout=35).json()
    status=token_check.get("data")
    if status is not None:
        expiry=status.get("expires_at")
        if status.get("is_valid") is False or expiry and expiry<TARGET.timestamp()+180:
            raise RuntimeError("Instagram authorization will not be valid at 07:00 IST")
    response=SESSION.post(ig.GRAPH+ig.IG_USER_ID+"/media",data={
        "media_type":"REELS","video_url":BASE+"/reel.mp4","cover_url":BASE+"/cover.jpg",
        "caption":CAPTION,"share_to_feed":"true","access_token":ig.IG_ACCESS_TOKEN},timeout=65)
    data=response.json()
    container=data.get("id")
    if not container:
        error=data.get("error",{})
        raise RuntimeError(f"Instagram rejected the private reel container (HTTP {response.status_code}, code {error.get('code')}, subcode {error.get('error_subcode')})")
    ig._wait_finished(container,45)
    remaining=TARGET.timestamp()-now().timestamp()
    print(f"READY: Verified @postal_edge, approved video and exact custom cover. Meta processing FINISHED. Publication gate {TARGET.isoformat()}.",flush=True)
    if remaining>0:
        time.sleep(remaining)
    if now().timestamp()>TARGET.timestamp()+180:
        raise RuntimeError("Scheduled publication window has passed")
    try:
        media=ig._publish(container)
    except (RuntimeError, requests.RequestException):
        prior=already_published()
        if prior:
            receipt(prior)
            return
        raise
    receipt({"id":media})
    receipt(get(media,fields="id,permalink,timestamp"))

if __name__=="__main__":
    main()
