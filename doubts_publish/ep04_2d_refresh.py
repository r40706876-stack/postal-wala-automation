"""Rebuild existing mock/deep visuals with the exact approved 2D pair; never synthesize audio."""
import os,json,hashlib,subprocess,sys,math,base64
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import requests
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
from postal_edge_puppet import puppet
from postal_edge_lip_shapes import measure_mouth
O=ROOT/'doubts_reels';O.mkdir(exist_ok=True)
url='https://raw.githubusercontent.com/r40706876-stack/postal-wala-automation/3b3cda98dcf347175d4f89df3f0e4484e2879745/doubts-preview/ep04_cutoff_gemini.mp4'
old=O/'ep04_voice_verified.mp4';r=requests.get(url,timeout=120);r.raise_for_status();old.write_bytes(r.content)
assert hashlib.sha256(r.content).hexdigest()=='377af56b46b4bc8fa00ed85358e6bc9314faef5ad003474103e68cb66c103d53'
# Existing HTML route, no deep_demo main or TTS invocation.
subprocess.run([sys.executable,'doubts_ep04.py','--html'],check=True)
h=O/'ep04_cutoff_gemini.html';text=h.read_text()
samples=np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-i',str(old),'-f','f32le','-ac','1','-ar','16000','-']),dtype=np.float32)
mouth=measure_mouth(samples,15,len(samples)/16000)
frames=O/'ep04_2d_frames';frames.mkdir(exist_ok=True)
# One animated frame per 1/15 second, deterministic seek in the existing mock engine.
cues=json.loads((O/'ep04_cutoff_gemini.mp4.cues.json').read_text())
moods=[('h1',True,'think','chin'),('z0',False,'happy','right'),('o1',True,'surprise','open'),('d1',False,'happy','welcome'),('m1',False,'happy','open')]
n=math.ceil(42.034*15);urls=[]
for i in range(n):
 t=i/15
 spec=moods[0]
 for s in moods:
  if t>=cues[s[0]]['t']-.2:spec=s
 _,golu,mood,gesture=spec
 speaking=mouth[min(i,len(mouth)-1)]
 facing=.68 if golu else -.63
 walk=.22*math.exp(-max(0,t-cues[spec[0]]['t'])*3)
 im=puppet(golu,t,walk,facing,speaking,mood,(.56+.18*math.sin(t*3),gesture),facing,0,.02*math.sin(t*2))
 p=frames/f'f{i:04d}.png';im.save(p)
 urls.append(p.as_uri())
addon='<script>window.APPROVED_2D='+json.dumps(urls)+r""";
window.READY=async()=>{window.APPROVED_FRAMES=await Promise.all(APPROVED_2D.map(src=>new Promise((resolve,reject)=>{let i=new Image();i.onload=()=>resolve(i);i.onerror=reject;i.src=src})))};
const oldSeek=window.seek;window.seek=function(t){oldSeek(t);let im=window.APPROVED_FRAMES&&window.APPROVED_FRAMES[Math.min(APPROVED_FRAMES.length-1,Math.max(0,Math.floor(t*15)))];if(im){document.querySelectorAll('#chr img').forEach(e=>{if(+e.style.opacity>.5)e.src=im.src})}};
</script>"""
# renderer synchronously decodes all changed images before screenshot (see workflow patch).
h.write_text(text.replace('</body>',addon+'</body>'))
subprocess.run([sys.executable,'deep/render_deep.py',str(h),str(O/'ep04_2d_silent.mp4'),str(O/'ep04_cutoff_gemini.mp4.cues.json')],check=True)
final=O/'ep04_cutoff_concierge10_2d.mp4'
subprocess.run(['ffmpeg','-y','-v','error','-i',str(O/'ep04_2d_silent.mp4'),'-i',str(old),'-map','0:v:0','-map','1:a:0','-c','copy','-shortest',str(final)],check=True)
subprocess.run(['ffmpeg','-v','error','-i',str(final),'-f','null','-'],check=True)
# Topic-specific cover, approved blue/yellow/red style and exact approved pair.
im=Image.new('RGB',(1080,1920),'#123d8a');d=ImageDraw.Draw(im)
d.polygon([(0,1020),(1080,860),(1080,1920),(0,1920)],fill='#ffdc36')
font='/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf'
def txt(y,s,size,fill):
 f=ImageFont.truetype(font,size);box=d.textbbox((0,0),s,font=f);d.text(((1080-(box[2]-box[0]))/2,y),s,font=f,fill=fill,stroke_width=1)
txt(70,'डाक विभाग के डाउट्स',57,'white');txt(180,'भाग 04',64,'#ffdf39')
txt(340,'जॉइनिंग या',115,'white');txt(515,'कटऑफ?',150,'#ffdd35')
d.rounded_rectangle((90,790,990,920),35,fill='#d32a32');txt(795,'3 साल कब पूरे होने चाहिए?',49,'white')
for golu,x in [(True,5),(False,515)]:
 p=puppet(golu,1,0,.68 if golu else -.63,None,'think' if golu else 'happy',(.7,'chin' if golu else 'right'),0,0,0).resize((560,856),Image.Resampling.LANCZOS)
 im.paste(p,(x,970),p)
d=ImageDraw.Draw(im);d.rounded_rectangle((70,1730,1010,1835),25,fill='#c32632');txt(1738,'2026 अधिसूचना का उदाहरण',46,'white');txt(1844,'Postal Edge • by Postal Wala',32,'#153579')
cover=O/'ep04_2d_cover.jpg';im.save(cover,quality=96)
# Contact sheet from final output, never trust render success alone.
shots=[]
for t in [1,8,15,20,26,32,38]:
 p=O/f'ep04_2d_{t}.jpg';subprocess.run(['ffmpeg','-y','-v','error','-ss',str(t),'-i',str(final),'-frames:v','1',str(p)],check=True)
 shots.append(Image.open(p).resize((270,480)))
sheet=Image.new('RGB',(270*4,480*2),'white')
for i,s in enumerate(shots):sheet.paste(s,((i%4)*270,(i//4)*480))
sheet.save(O/'ep04_2d_contact.jpg',quality=95)
report={'voice':'hi-in-concierge-10','audio_source_sha256':'377af56b46b4bc8fa00ed85358e6bc9314faef5ad003474103e68cb66c103d53','tts_calls':0,'route':'mock_reel.page30 -> deep/render_deep.py; exact approved puppet; original verified Concierge10 MP4 audio stream copied','character_source':'postal_edge_puppet.py approved transfer-demo models','run':os.environ['GITHUB_RUN_ID'],'narration_audit_run':'44736881625','qa_pending':'final visual review','video_sha256':hashlib.sha256(final.read_bytes()).hexdigest(),'cover_sha256':hashlib.sha256(cover.read_bytes()).hexdigest()}
(O/'ep04_2d_build.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
