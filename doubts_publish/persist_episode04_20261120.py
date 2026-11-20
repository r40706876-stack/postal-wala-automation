"""Persist only this actual publication into fresh remote state; preserve other schedules' entries."""
import os,json,base64,time,pathlib,requests
REPO="r40706876-stack/postal-wala-core"
H={"Authorization":"Bearer "+os.environ["CORE_TOKEN"],"Accept":"application/vnd.github+json"}
ROOT=pathlib.Path("doubts_reels")
def get(path):
    r=requests.get("https://api.github.com/repos/"+REPO+"/contents/"+path,headers=H,params={"ref":"main"},timeout=45)
    if r.status_code==404:return None,None
    r.raise_for_status();d=r.json()
    return json.loads(base64.b64decode(d["content"])),d["sha"]
def put(path,obj,merge=False):
    for attempt in range(3):
        old,sha=get(path)
        data=obj
        if merge:
            data=old or {}
            key=next(iter(obj))
            prior=data.get(key)
            if prior and prior.get("id")!=obj[key]["id"]:raise RuntimeError("Conflicting publication id; do not overwrite")
            data.update(obj)
        elif old and old.get("status")=="published" and old.get("media_id")!=obj.get("media_id"):
            raise RuntimeError("Conflicting episode receipt; do not overwrite")
        body={"message":"Record confirmed doubts ep04 result [skip ci]","branch":"main","content":base64.b64encode(json.dumps(data,ensure_ascii=False,indent=2).encode()).decode()}
        if sha:body["sha"]=sha
        r=requests.put("https://api.github.com/repos/"+REPO+"/contents/"+path,headers=H,json=body,timeout=45)
        if r.status_code in (409,422) and attempt<2:time.sleep(2);continue
        r.raise_for_status();print("PERSISTED "+path,flush=True);return
receipt=ROOT/"ep04_publication_receipt.json"
if receipt.exists():
    r=json.loads(receipt.read_text())
    assert r["status"]=="published" and r["episode"]==4
    key="doubts_ep04_"+r["manifest"]["video"]["sha256"][:12]
    e={"id":r["media_id"],"time":r["published_at_ist"],"permalink":r.get("permalink"),"series_episode":4,"video_sha256":r["manifest"]["video"]["sha256"],"cover_sha256":r["manifest"]["cover"]["sha256"],"facebook_crosspost":False,"username":r["username"]}
    put("generated_reels/ig_posted.json",{key:e},merge=True)
    put("doubts_reels/ep04_publication_receipt.json",r)
p=ROOT/"ep04_container_checkpoint.json"
if p.exists():put("doubts_reels/ep04_container_checkpoint.json",json.loads(p.read_text()))

if receipt.exists():
    r=json.loads(receipt.read_text())
    previous,_=get("doubts_reels/series_readiness_2026-11-19.json")
    state=previous or {}
    state["checked_at"]="2026-11-20"
    state["episode04"]={"status":"PUBLISHED","media_id":r["media_id"],"permalink":r.get("permalink"),"published_at_ist":r["published_at_ist"],"manifest":r["manifest"],"receipt":"doubts_reels/ep04_publication_receipt.json"}
    state["reserved_2026_11_21"]={"target_ist":"2026-11-21T18:30:00+05:30","only_media":"approved40sRule3+PostalEdgewebsite transferdemo","run":44594468241,"sha256":"762bee6cc40df5a5ed5312430ba29010de794191f2437cb7e62b77a9369eb033","workflow":".github/workflows/postal_edge_transfer_release.yml","marker":"postal_release/start_20261121.txt","no_other_series_publisher":True}
    state["next_normal_episode"]={"episode":5,"topic":"MTS-only local-language PaperIII","preproduction":"doubts_publish/ep05_preproduction.json","earliest_ist":"2026-11-22T18:30:00+05:30","rendered":False}
    state["standing_voice"]="hi-in-concierge-10"
    state["standing_characters"]="Only exact approved2D Golu/Bhaiya models from approved transferdemo"
    state["ongoing_series_active"]=True
    put("doubts_reels/series_readiness_2026-11-20.json",state)
