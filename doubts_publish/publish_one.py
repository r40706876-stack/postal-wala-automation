import os,sys,json,hashlib,datetime,pathlib,requests
sys.path.insert(0,os.getcwd())
import ig_post as P
ROOT=pathlib.Path.cwd(); OUT=ROOT/"doubts_reels";OUT.mkdir(exist_ok=True)
KEY="doubts_ep01_rule3_4ba1006c4586"
MEDIA="https://raw.githubusercontent.com/r40706876-stack/postal-wala-automation/8ea54acc942848c599dddcb0b380181f9ef990d9/doubts/ep01/"
def api(path,params=None):
 d=requests.get(P.GRAPH+path,params={**(params or {}),"access_token":P.IG_ACCESS_TOKEN},timeout=45).json()
 if "error" in d:raise RuntimeError("Instagram API: "+d["error"].get("message","unknown"))
 return d
def fetch(name,sha):
 r=requests.get(MEDIA+name,timeout=120)
 if r.status_code!=200:raise RuntimeError("Asset unavailable: "+name)
 if hashlib.sha256(r.content).hexdigest()!=sha:raise RuntimeError("Asset hash mismatch: "+name)
 p=OUT/name;p.write_bytes(r.content);return p
assert os.environ.get("FB_POST")=="0"
u=api(P.IG_USER_ID,{"fields":"username"})
assert u.get("username","").lower()=="postal_wala","Wrong Instagram username"
print("VERIFIED_ACCOUNT @"+u["username"],flush=True)
log=P.load_log();existing=log.get(KEY)
recent=api(P.IG_USER_ID+"/media",{"fields":"id,caption,permalink,timestamp","limit":50}).get("data",[])
for m in recent:
 c=m.get("caption","").replace(" ","").replace("०","0").replace("१","1")
 if ("डाकविभागकेडाउट्स" in c and ("भाग01" in c or "भाग1:" in c) and ("GDS" in c or "ट्रांसफर" in c)):
  existing={"id":m["id"],"permalink":m.get("permalink"),"time":m.get("timestamp"),"duplicate_reconciled":True};break
if existing:
 log[KEY]=existing;P.save_log(log);receipt={"status":"already_published","username":u["username"],**existing}
else:
 # User explicitly released review HOLD. This run selects episode 01 only.
 v=fetch("Postal_Wala_GDS_Rule3.mp4","4ba1006c458654bc3ac6166bd158b807e38ce959d3f720165b83c463484d6766")
 cover=fetch("cover_A.jpg","bf0bfa03b33a450254b25f52891bd3192942c1f09334e33c7935a410f1fd1b00")
 source=fetch("cover_A_source.png","13062a768ddf2e8e0c747acf7302a9396505df1d5c922e71f5d6f2a6e7da0ce8")
 from PIL import Image
 with Image.open(cover) as im,Image.open(source) as src:assert im.size==src.size==(941,1672)
 cap=requests.get(MEDIA+"caption.txt",timeout=45).text.strip()
 assert "भाग 01" in cap and len(cap)<2200 and "कल भाग 02" in cap
 now=datetime.datetime.now(P.IST)
 assert now.date().isoformat()=="2026-11-16","Do not publish a stale next-day teaser"
 P.FB_ON=False
 P.raw_url=lambda path:MEDIA+pathlib.Path(path).name
 # Existing private-core URL upload -> processing wait -> publish; never call coverless retry wrapper.
 pid=P._reel_by_url(str(v),cap,MEDIA+"cover_A.jpg")
 stamp=datetime.datetime.now(P.IST).isoformat()
 log=P.load_log();log[KEY]={"id":pid,"time":stamp,"series_episode":1,"video_sha256":"4ba1006c458654bc3ac6166bd158b807e38ce959d3f720165b83c463484d6766","cover_library_file_id":"libfile_5ead5667a6c081919f524b0763e6ebfa","cover_sha256":"bf0bfa03b33a450254b25f52891bd3192942c1f09334e33c7935a410f1fd1b00"}
 P.save_log(log)
 detail=api(pid,{"fields":"id,permalink,timestamp"})
 log[KEY]["permalink"]=detail.get("permalink");P.save_log(log)
 receipt={"status":"published","username":u["username"],"media_id":pid,"permalink":detail.get("permalink"),"published_at_ist":stamp,"episode":1,"cover_selection":"A blue/yellow/red; format conversion only","cover_source_sha256":"13062a768ddf2e8e0c747acf7302a9396505df1d5c922e71f5d6f2a6e7da0ce8","source_verified":"https://utilities.cept.gov.in/dop/pdfbind.ashx?id=14939","facebook_crosspost":False}
(OUT/"ep01_publication_receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
print("PUBLICATION_RECEIPT "+json.dumps(receipt,ensure_ascii=False),flush=True)
