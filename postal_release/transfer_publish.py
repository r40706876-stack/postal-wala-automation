"""Publish the approved transfer reel in its reserved Instagram slot."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import time

import requests

sys.path.insert(0, os.getcwd())
import ig_post as instagram

TARGET = datetime.fromisoformat("2026-11-21T18:30:00+05:30")
DEADLINE = TARGET + timedelta(seconds=90)
APPROVED_HASH = "762bee6cc40df5a5ed5312430ba29010de794191f2437cb7e62b77a9369eb033"
KEY = "postal_edge_transfer_demo_" + APPROVED_HASH[:12]
TITLE = "गोलू और भैया के साथ | Postal Edge ट्रांसफ़र डेमो"
CAPTION = f"""{TITLE}

म्यूचुअल ट्रांसफ़र का साथी कैसे खोजें? अपना कैडर, मौजूदा डिवीज़न और मनचाही डिवीज़न भरें। उलटी दिशा का रूट मिले तो ‘मेरे मैच’ में देखें।

🔗 postaledge.in/transfer
रूट दर्ज करना मुफ़्त है। वीडियो में दिखाए रूट डेमो हैं। आधिकारिक आवेदन और मंज़ूरी डाक विभाग के माध्यम से होती है।

अपने GDS साथी को भेजें।
#PostalEdge #PostalWala #GDSTransfer #IndiaPost #MutualTransfer"""
OUT = Path("doubts_reels/transfer_demo_20261121_receipt.json")


def get(path, **params):
    response = requests.get(
        instagram.GRAPH + path,
        params={**params, "access_token": instagram.IG_ACCESS_TOKEN},
        timeout=35,
    )
    if not response.ok or "error" in response.json():
        raise RuntimeError(f"Instagram read failed (HTTP {response.status_code})")
    return response.json()


def recent():
    return get(instagram.IG_USER_ID + "/media", fields="id,caption,timestamp,permalink", limit=50)["data"]


def existing():
    saved = instagram.load_log().get(KEY)
    if saved:
        return saved
    return next((item for item in recent() if TITLE in (item.get("caption") or "")), None)


def record(media, username, reconciled=False):
    receipt = {
        "status": "published",
        "username": username,
        "media_id": media["id"],
        "permalink": media.get("permalink"),
        "published_at": media.get("timestamp") or media.get("time") or datetime.now(timezone.utc).isoformat(),
        "scheduled_at_ist": TARGET.isoformat(),
        "sha256": APPROVED_HASH,
        "reconciled": reconciled,
    }
    log = instagram.load_log()
    log[KEY] = {"id": media["id"], "time": receipt["published_at"], "permalink": receipt["permalink"]}
    instagram.save_log(log)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False), flush=True)


def main():
    video, cover = map(Path, sys.argv[1:3])
    verify = sys.argv[3] == "verify"
    if sha256(video.read_bytes()).hexdigest() != APPROVED_HASH:
        raise RuntimeError("The video is not the approved render")
    if not cover.is_file():
        raise RuntimeError("Cover missing")
    user = get(instagram.IG_USER_ID, fields="username")["username"].lower()
    known = {item["id"] for item in recent()}
    if user != "postal_edge" or "18185947558425623" not in known:
        raise RuntimeError("Postal Edge Instagram account ownership not verified")
    print(f"Verified approved video hash, cover and Instagram account @{user}", flush=True)
    if verify:
        return
    prior = existing()
    if prior:
        record(prior, user, reconciled=True)
        return
    if not TARGET - timedelta(minutes=50) <= datetime.now(timezone.utc) < TARGET:
        raise RuntimeError("Preparation is outside the approved publishing window")
    cover_url = instagram.media_url(str(cover))
    original_publish = instagram._publish

    def publish_at_target(container):
        print(f"Instagram processed reel {container}. Release at {TARGET.isoformat()}", flush=True)
        while (seconds := (TARGET - datetime.now(timezone.utc)).total_seconds()) > 0:
            time.sleep(min(seconds, 15))
        prior_media = existing()
        if prior_media:
            return prior_media["id"]
        if datetime.now(timezone.utc) > DEADLINE:
            raise RuntimeError("Instagram publication window expired")
        return original_publish(container)

    instagram._publish = publish_at_target
    media_id = instagram._reel_by_url(str(video), CAPTION, cover_url)
    # Persist the media ID even if the follow-up permalink read fails.
    record({"id": media_id}, user)
    media = get(media_id, fields="id,timestamp,permalink")
    record(media, user)


if __name__ == "__main__":
    main()
