from hashlib import sha256
import json
import os
from pathlib import Path
import sys

import requests

sys.path.insert(0, os.getcwd())
import ig_post as ig

ASSETS = {
    "reel.mp4": "8942add800a0fdc1216c5a157562c1c8647e38f70370111a2685566e1500ad2e",
    "cover.jpg": "d62e313d1d29599a06a25a1767d6654d114975adb576412d3b246ac2afa17519",
}
ACCOUNT = "postal_edge"
TITLE = "GDS से पोस्टमैन: तीन साल पूरे? अब फॉर्म भरें?"
CAPTION = f"""{TITLE}

GDS से Postman और Mail Guard परीक्षा की पात्रता में 3 साल की सेवा का प्रस्ताव क्या कहता है? रील में मसौदे और अंतिम अधिसूचना का फर्क समझिए।

फ्री वीडियो, नोट्स और मॉक टेस्ट के लिए postaledge.in देखें।

#PostalEdge #GDS #PostmanExam #IndiaPost"""
FIELDS = "id,permalink,timestamp"
SESSION = requests.Session()


def read_instagram(path, **params):
    response = SESSION.get(
        ig.GRAPH + path,
        params={**params, "access_token": ig.IG_ACCESS_TOKEN},
        timeout=30,
    )
    data = response.json()
    if not response.ok or "error" in data:
        code = data.get("error", {}).get("code")
        raise RuntimeError(f"Instagram read failed (HTTP {response.status_code}, code {code})")
    return data


def find_existing():
    for item in read_instagram(ig.IG_USER_ID + "/media", fields=FIELDS + ",caption", limit=50)["data"]:
        if (item.get("caption") or "").split("\n", 1)[0] == TITLE:
            return item
    return None


def main():
    account = read_instagram(ig.IG_USER_ID, fields="username")["username"].lower()
    if account != ACCOUNT:
        raise RuntimeError("Configured Instagram account differs from @postal_edge")
    print("Verified @postal_edge", flush=True)

    base_url = (
        f"https://raw.githubusercontent.com/{os.environ['GITHUB_REPOSITORY']}/"
        f"{os.environ['GITHUB_SHA']}/postal_release/postman_final_20261121"
    )
    for filename, checksum in ASSETS.items():
        response = SESSION.get(f"{base_url}/{filename}", timeout=60)
        if not response.ok or sha256(response.content).hexdigest() != checksum:
            raise RuntimeError(f"Approved file unavailable or does not match: {filename}")
    print("Verified final MP4 and approved custom cover", flush=True)

    media = find_existing()
    if media is None:
        response = SESSION.post(
            ig.GRAPH + ig.IG_USER_ID + "/media",
            data={
                "media_type": "REELS",
                "video_url": base_url + "/reel.mp4",
                "cover_url": base_url + "/cover.jpg",
                "caption": CAPTION,
                "share_to_feed": "true",
                "access_token": ig.IG_ACCESS_TOKEN,
            },
            timeout=60,
        )
        data = response.json()
        container = data.get("id")
        if not response.ok or not container:
            error = data.get("error", {})
            raise RuntimeError(
                f"Instagram rejected reel with custom cover (HTTP {response.status_code}, "
                f"code {error.get('code')}, subcode {error.get('error_subcode')})"
            )
        ig._wait_finished(container, tries=45)
        try:
            media_id = ig._publish(container)
        except (requests.RequestException, RuntimeError):
            media = find_existing()
            if media is None:
                raise
        else:
            media = read_instagram(media_id, fields=FIELDS)

    if not media.get("permalink"):
        raise RuntimeError(f"Instagram did not return a permalink for media {media['id']}")
    receipt = {
        "status": "published",
        "account": "@" + ACCOUNT,
        "media_id": media["id"],
        "permalink": media["permalink"],
        "published_at": media["timestamp"],
    }
    Path("../release-result").mkdir(exist_ok=True)
    Path("../release-result/receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("PUBLICATION_RECEIPT " + json.dumps(receipt, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
