from pathlib import Path
from functools import lru_cache
import json, math, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
P=Path(__file__).parent
sys.path.insert(0,str(P.parent))
import render as R

W,H=720,1280
bounds=json.loads((P/'timing.json').read_text())
end=bounds[-1]
screens=['website','routes','form','match']
points=json.loads((P/'points.json').read_text())
Y,X=np.mgrid[:H,:W]
def background():
    base=np.broadcast_to(np.array([18,23,49],float),(H,W,3)).copy()
    for x,y,s,color in [(145,400,335,[98,18,38]),(675,665,360,[22,39,104]),(301,1233,231,[79,48,11])]:
        factor=np.exp(-((X-x)**2+(Y-y)**2)/s**2)
        base+=factor[:,:,None]*np.array(color)
    out=Image.fromarray(base.clip(0,255).astype('uint8'))
    d=ImageDraw.Draw(out)
    for i in range(7):
        d.arc((-330-i*40,636+i*29,1095+i*23,1272+i*30),199,329,fill=(55+i*4,52+i*3,99+i*2),width=1)
    return out
BG=background()
def word(d,*a,**k):return R.word(d,*a,**k)
def rounded(d,*a,**k):return R.rr(d,*a,**k)
def start(t):
    im=BG.copy();d=ImageDraw.Draw(im)
    rounded(d,43,57,244,50,'#22243a','#c6abc1',16)
    R.envelope(d,57,70,33,'#ffb474',False)
    word(d,107,70,'POSTAL EDGE',22)
    rounded(d,439,61,235,42,'#673145','#eea5a1',14)
    word(d,556,70,'डेमो · केवल उदाहरण',21,'#fff3dd',True)
    d.line((47,1222,673,1222),fill='#74648f',width=2)
    d.line((47,1222,47+626*t/end,1222),fill='#ffd388',width=4)
    return im,d
@lru_cache(maxsize=85)
def device(name,width):
    p=Image.open(P/(name+'.jpg')).convert('RGB')
    body=Image.new('RGBA',(width,round((width-20)*735/390)+20))
    d=ImageDraw.Draw(body)
    rounded(d,1,1,width-3,body.height-3,'#100f1f','#c2b3d7',29)
    pic=p.resize((width-20,body.height-20),Image.Resampling.LANCZOS)
    m=Image.new('L',pic.size)
    ImageDraw.Draw(m).rounded_rectangle((0,0,pic.width-1,pic.height-1),21,fill=255)
    body.paste(pic,(10,10),m)
    return body
def phone(im,name,center,y,width,angle):
    item=device(name,width)
    d=ImageDraw.Draw(im)
    mark=Image.new('L',(width+74,item.height+53))
    ImageDraw.Draw(mark).rounded_rectangle((34,25,width+36,item.height+27),39,fill=165)
    im.paste('#020719',(round(center-mark.width/2),round(y+3)),mark.filter(ImageFilter.GaussianBlur(13)))
    if abs(angle)>.2:item=item.rotate(angle,Image.Resampling.BICUBIC,expand=True)
    x=round(center-item.width/2)
    im.paste(item,(x,round(y)),item)
    return x
def tap(d,x,y,u):
    if not 0<=u<=.94:return
    rad=10+23*R.ease(u/.42)
    d.ellipse((x-rad,y-rad,x+rad,y+rad),outline='#fff0c7',width=4)
    d.ellipse((x-rad+4,y-rad+4,x+rad-4,y+rad-4),outline='#e04266',width=3)
    d.ellipse((x-6,y-6,x+6,y+6),fill='#f997a8')
    if u<.64:
        d.polygon([(x+7,y+8),(x+31,y+22),(x+22,y+25),(x+18,y+34)],fill='#fff0d4',outline='#4d1f36')
def still(i,t):
    local=t-bounds[i]; duration=bounds[i+1]-bounds[i];u=R.ease(local/.32)
    im,d=start(t)
    headline=['ट्रांसफ़र पेज खोलो','3 नमूना रूट','अपना रूट दर्ज करो','उलटी दिशा का मैच','अब अपना रूट डालो'][i]
    word(d,44,146,headline,51)
    if i<4:
        caption=['postaledge.in/transfer','ये केवल उदाहरण हैं','कैडर · अभी की डिवीज़न · मनचाही डिवीज़न','मेरे मैच में देखें'][i]
        word(d,48,218,caption,28,'#ffd68e')
        width=399+round(11*R.ease(local/max(duration,.1)))
        x=348+round((1-u)*(45 if i%2==0 else -53))
        y=282+30*(1-u)
        angle=(6 if i%2==0 else -5)*(1-u)
        sx=phone(im,screens[i],x,y,width,angle)
        if i in (0,2,3) and screens[i] in points and abs(angle)<.22:
            px,py=points[screens[i]];k=(width-20)/390
            tap(ImageDraw.Draw(im),sx+10+px*k,y+10+py*k,local-duration*.57)
        R.actor(im,i%2==0,99 if i%2==0 else 619,1100,198,t,talk=True,mood='happy',
          gesture='open' if i%2==0 else 'left',strength=.55+.24*math.sin(local*4)**2)
        d=ImageDraw.Draw(im)
        rounded(d,58,1128,604,52,'#281e39','#9685b0',13)
        word(d,360,1141,'डेमो स्क्रीन · ये वास्तविक अनुरोध नहीं हैं',25,'#fff1d7',True)
    else:
        word(d,46,224,'मुफ़्त में म्यूचुअल साथी खोजो',37,'#ffd58b')
        x=135+451*R.ease(local/1.25)
        d.line((127,397,596,397),fill='#ccae8b',width=4)
        R.envelope(d,x-35,373,70,'#ffce83')
        R.actor(im,True,190,897,374,t,talk=False,mood='happy',gesture='open',strength=.68,walk=R.ramp(local,-.15,.09,.29,.58))
        R.actor(im,False,531,897,367,t,talk=True,mood='happy',gesture='welcome',strength=.64)
        d=ImageDraw.Draw(im)
        rounded(d,48,902,625,108,'#9e324b','#f6b77d',24)
        word(d,360,933,'postaledge.in/transfer',46,'#fff6e8',True)
        word(d,360,1047,'अपने GDS साथी को भेजो',32,'#ffd76d',True)
        word(d,360,1128,'ट्रांसफ़र मंज़ूरी विभाग देता है',23,'#dfcbe2',True)
    return im
def frame(t):
    i=max(j for j,x in enumerate(bounds[:-1]) if x<=t)
    im=still(i,t)
    dt=t-bounds[i]
    if i and dt<.18:
        old=still(i-1,bounds[i]-.001)
        blur=Image.blend(old,im,R.ease(dt/.18))
        return blur
    return im
def clip():
    R.P=P
    R.END=end
    R.times=bounds
    R.VOICE=R.animate_mouth()
    R.score()
    out=P/'website-cut.mp4'
    ff=subprocess.Popen(['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','720x1280','-r','30','-i','-','-i',str(P/'narration.wav'),'-i',str(P/'music.wav'),'-filter_complex',
    '[0:v]scale=1080:1920:flags=lanczos[v];[1:a]highpass=f=80,acompressor=threshold=.14:ratio=2.3:attack=7:release=150:makeup=1.47,apad[a];[2:a]volume=.33[m];[a][m]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=.85:level=false[o]',
    '-map','[v]','-map','[o]','-t',str(end),'-threads','4','-pix_fmt','yuv420p','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-b:a','192k',str(out)],stdin=subprocess.PIPE)
    try:
        for i in range(round(end*30)):
            ff.stdin.write(frame(i/30).tobytes())
    finally:ff.stdin.close()
    if ff.wait():raise SystemExit('Demo render failed')
    qa=Image.new('RGB',(1000,356))
    for i,t in enumerate(bounds[:-1]):qa.paste(frame(t+(bounds[i+1]-t)*.65).resize((200,355)),(i*200,0))
    qa.save(P/'preview.jpg',quality=91)
    base=P/'Postal_Edge_Rule3_Transfer_Story_Animated.mp4'
    final=P/'Postal_Edge_Rule3_Transfer_Website_Demo.mp4'
    # Keep the approved Rule 3 explanation and dissolve into the new phone demo.
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(base),'-i',str(out),'-filter_complex',
      '[0:v]trim=end=19.10,setpts=PTS-STARTPTS,fps=30,settb=AVTB,setsar=1,format=yuv420p[v0];[1:v]setpts=PTS-STARTPTS,fps=30,settb=AVTB,setsar=1,format=yuv420p[v1];[v0][v1]xfade=transition=fade:duration=0.20:offset=18.90[v];[0:a]atrim=end=19.10,asetpts=PTS-STARTPTS[a0];[a0][1:a]acrossfade=d=0.20[a]',
      '-map','[v]','-map','[a]','-threads','4','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(final)],check=True)
if __name__=='__main__':clip()
