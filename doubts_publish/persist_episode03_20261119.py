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
        body={"message":"Record confirmed doubts ep03 result [skip ci]","branch":"main","content":base64.b64encode(json.dumps(data,ensure_ascii=False,indent=2).encode()).decode()}
        if sha:body["sha"]=sha
        r=requests.put("https://api.github.com/repos/"+REPO+"/contents/"+path,headers=H,json=body,timeout=45)
        if r.status_code in (409,422) and attempt<2:time.sleep(2);continue
        r.raise_for_status();print("PERSISTED "+path,flush=True);return
receipt=ROOT/"ep03_publication_receipt.json"
if receipt.exists():
    r=json.loads(receipt.read_text())
    assert r["status"]=="published" and r["episode"]==3
    key="doubts_ep03_"+r["manifest"]["video"]["sha256"][:12]
    e={"id":r["media_id"],"time":r["published_at_ist"],"permalink":r.get("permalink"),"series_episode":3,"video_sha256":r["manifest"]["video"]["sha256"],"cover_sha256":r["manifest"]["cover"]["sha256"],"facebook_crosspost":False,"username":r["username"]}
    put("generated_reels/ig_posted.json",{key:e},merge=True)
    put("doubts_reels/ep03_publication_receipt.json",r)
p=ROOT/"ep03_container_checkpoint.json"
if p.exists():put("doubts_reels/ep03_container_checkpoint.json",json.loads(p.read_text()))
