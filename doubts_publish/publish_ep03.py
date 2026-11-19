"""Publish one explicitly QA-approved episode through existing ig_post URL pipeline."""
import os,sys,json,hashlib,datetime,pathlib,time,requests
sys.path.insert(0,os.getcwd())
import ig_post as P
from PIL import Image
OUT=pathlib.Path("doubts_reels");OUT.mkdir(exist_ok=True)
M=json.loads(pathlib.Path("../production/doubts_publish/ep03_manifest.json").read_text())
assert M["episode"]==3 and M["qa_passed"] is True and os.environ.get("FB_POST")=="0"
TARGET=datetime.datetime.fromisoformat(M["target_ist"])
def api(path,params=None):
    r=requests.get(P.GRAPH+path,params={**(params or {}),"access_token":P.IG_ACCESS_TOKEN},timeout=45)
    d=r.json()
    if "error" in d:raise RuntimeError("Instagram API: "+d["error"].get("message","unknown"))
    return d
def recent():
    return api(P.IG_USER_ID+"/media",{"fields":"id,caption,permalink,timestamp","limit":75}).get("data",[])
def duplicate(log,media):
    for k,v in log.items():
        if k.startswith("doubts_ep03_") or v.get("series_episode")==3:return v
    for m in media:
        c="".join(m.get("caption","").split()).replace("०","0").replace("२","2")
        if any(x in c for x in ("डाकविभागकेडाउट्स|भाग03:", "डाकविभागकेडाउट्स|भाग3:", "डाकविभागकेडाउट्स—भाग03:")):
            return {"id":m["id"],"permalink":m.get("permalink"),"time":m.get("timestamp"),"duplicate_reconciled":True}
def fetch(asset):
    d=M[asset];r=requests.get(d["url"],timeout=120);r.raise_for_status()
    assert hashlib.sha256(r.content).hexdigest()==d["sha256"],asset+" hash mismatch"
    p=OUT/d["filename"];p.write_bytes(r.content);return p
user=api(P.IG_USER_ID,{"fields":"username"})
assert user.get("username","").lower()=="postal_wala","Wrong Instagram account"
print("VERIFIED_ACCOUNT @postal_wala",flush=True)
log=P.load_log()
assert any(k.startswith("doubts_ep02_") for k in log),"Episode 02 receipt missing in log"
existing=duplicate(log,recent())
if existing:raise RuntimeError("Episode 03 already published: "+str(existing.get("id")))
now=datetime.datetime.now(P.IST)
assert now.date()==TARGET.date() and now<=TARGET,"Missed preparation target; do not publish late"
v=fetch("video");cover=fetch("cover");capfile=fetch("caption")
with Image.open(cover) as im:
    w,h=im.size;assert abs(w/h-9/16)<.015,"Cover aspect mismatch"
cap=capfile.read_text().strip()
assert "भाग 03" in cap and len(cap)<2200 and "17-12/2025-GDS" in cap and "45" in cap
P.FB_ON=False
P.raw_url=lambda path:M["video"]["url"]
real_publish=P._publish
def punctual_publish(cid):
    checkpoint={"status":"container_processed_waiting_target","container_id":cid,"target":TARGET.isoformat(),"episode":3,"manifest":M}
    (OUT/"ep03_container_checkpoint.json").write_text(json.dumps(checkpoint,ensure_ascii=False,indent=2))
    print("CONTAINER_READY "+str(cid)+" TARGET "+TARGET.isoformat(),flush=True)
    while datetime.datetime.now(P.IST)<TARGET:
        time.sleep(min(20,max(.1,(TARGET-datetime.datetime.now(P.IST)).total_seconds())))
    assert (datetime.datetime.now(P.IST)-TARGET).total_seconds()<=90,"Target missed"
    assert not duplicate(P.load_log(),recent()),"Episode appeared during processing; stop duplicate"
    return real_publish(cid)
P._publish=punctual_publish
# Direct cover-preserving route. No wrapper, tags, collaborator, or FB publishing.
pid=P._reel_by_url(str(v),cap,M["cover"]["url"])
stamp=datetime.datetime.now(P.IST).isoformat()
key="doubts_ep03_"+M["video"]["sha256"][:12]
log=P.load_log();log[key]={"id":pid,"time":stamp,"series_episode":3,"video_sha256":M["video"]["sha256"],"cover_sha256":M["cover"]["sha256"]}
P.save_log(log)
receipt={"status":"published","username":"postal_wala","media_id":pid,"published_at_ist":stamp,"episode":3,"manifest":M,"facebook_crosspost":False}
(OUT/"ep03_publication_receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
detail=api(pid,{"fields":"id,permalink,timestamp"})
receipt["permalink"]=detail.get("permalink");log[key]["permalink"]=detail.get("permalink");P.save_log(log)
(OUT/"ep03_publication_receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
print("PUBLICATION_RECEIPT "+json.dumps(receipt,ensure_ascii=False),flush=True)
