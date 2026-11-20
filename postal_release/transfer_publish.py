"""Publish the approved transfer reel once on November 20."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

import requests

sys.path.insert(0, os.getcwd())
import ig_post as instagram

RELEASE_DAY = "2026-11-20"
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
        "release_date_ist": RELEASE_DAY,
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
    if sys.argv[3] != "now":
        raise RuntimeError("Immediate publication mode required")
    if sha256(video.read_bytes()).hexdigest() != APPROVED_HASH:
        raise RuntimeError("The video is not the approved render")
    if not cover.is_file():
        raise RuntimeError("Cover missing")
    user = get(instagram.IG_USER_ID, fields="username")["username"].lower()
    known = {item["id"] for item in recent()}
    if user != "postal_edge" or "18185947558425623" not in known:
        raise RuntimeError("Postal Edge Instagram account ownership not verified")
    print(f"Verified approved video hash, cover and Instagram account @{user}", flush=True)
    prior = existing()
    if prior:
        record(get(prior["id"], fields="id,timestamp,permalink"), user, reconciled=True)
        return
    cover_url = instagram.media_url(str(cover))
    original_publish = instagram._publish

    def publish_once(container):
        prior_media = existing()
        if prior_media:
            return prior_media["id"]
        return original_publish(container)

    instagram._publish = publish_once
    try:
        media_id = instagram._reel_by_url(str(video), CAPTION, cover_url)
    except (requests.RequestException, RuntimeError):
        prior = existing()
        if not prior:
            raise
        record(get(prior["id"], fields="id,timestamp,permalink"), user, reconciled=True)
        return
    # Persist the media ID even if the follow-up permalink read fails.
    record({"id": media_id}, user)
    media = get(media_id, fields="id,timestamp,permalink")
    if not media.get("permalink"):
        raise RuntimeError("Instagram has not returned a permalink")
    record(media, user)


if __name__ == "__main__":
    main()
