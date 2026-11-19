import json, math, subprocess, sys, wave
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageFilter
P=Path(__file__).parent
W,H=720,1280
NAVY='#1a292d'; WINE='#661c2d'; RED='#a53141'; GOLD='#ffd178'; CREAM='#ffefd4'; MINT='#d7e5ae'; WHITE='#fff9ee'
times=[0,4.5,9.5,17,23,30]
if (P/'timing.json').exists():times=json.loads((P/'timing.json').read_text())
END=times[-1]
FP=Path('/usr/share/fonts/truetype/noto')
@lru_cache(maxsize=80)
def font(s,dev): return ImageFont.truetype(str(FP/('NotoSansDevanagari-Bold.ttf' if dev else 'NotoSans-Bold.ttf')),s)
@lru_cache(maxsize=200)
def spans(s,size):
    runs=[]
    for ch in s:
        d=0x900<=ord(ch)<=0x97f or ch=='\u200d' or ch=='\u200c'
        if ch.isspace() and runs:d=runs[-1][0]
        if runs and d==runs[-1][0]:runs[-1]=(d,runs[-1][1]+ch)
        else:runs.append((d,ch))
    return [(v,font(size,d),font(size,d).getlength(v)) for d,v in runs]
def word(d,x,y,s,size,col=WHITE,center=False,maxw=652,stroke=0):
    while sum(k[2] for k in spans(s,size))>maxw:size-=1
    a=spans(s,size)
    if center:x-=sum(q[2] for q in a)/2
    for t,f,w in a:
        d.text((x,y+.85*size),t,font=f,fill=col,anchor='ls',language='hi',stroke_width=stroke,stroke_fill=NAVY)
        x+=w
def ease(v):
    x=min(1,max(0,v));return 1-(1-x)**3
def rr(d,x,y,w,h,c,edge=None,r=18):
    d.rounded_rectangle((int(x),int(y),int(x+w),int(y+h)),r,fill=c,outline=edge,width=2)

def cutout(src):
    return Image.open(P/'assets'/src).convert('RGBA')
chars={k:cutout(k+'.png') for k in ('golu','golu_think','bhaiya','bhaiya_yes')}
@lru_cache(maxsize=100)
def sprite(name,height,flip):
    raw=chars[name]; w=round(height*raw.width/raw.height); raw=raw.resize((w,height),Image.Resampling.LANCZOS)
    return raw.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if flip else raw

def actor(im,name,x,y,h,l,walking=False,flip=False):
    bounce=math.sin(l*(15 if walking else 5.4))
    h=int(h*(1+.012*bounce))
    pic=sprite(name,h,flip)
    turn=3.8*bounce if walking else 1.3*math.sin(l*3.2)
    pic=pic.rotate(turn,Image.Resampling.BICUBIC,expand=True)
    sh=Image.new('L',(pic.width+44,100))
    ImageDraw.Draw(sh).ellipse((18,28,pic.width+28,65),fill=133)
    sh=sh.filter(ImageFilter.GaussianBlur(13));im.paste('#211611',(int(x-sh.width/2),int(y-50)),sh)
    im.paste(pic,(int(x-pic.width/2),int(y-pic.height-8*bounce)),pic)
def envelope(d,x,y,w,tint=CREAM,seal=True):
    h=w*.61; rr(d,x,y,w,h,tint,'#d2a480',max(5,round(w*.11)))
    d.line((x+5,y+6,x+w/2,y+h*.57,x+w-5,y+6),fill='#bd8e6b',width=max(2,round(w*.025)))
    if seal:
        q=w*.09;d.ellipse((x+w*.5-q,y+h*.53-q,x+w*.5+q,y+h*.53+q),fill=RED)
def arrow(d,x,y,w,ink):
    d.line((x,y,x+w,y),fill=ink,width=5)
    d.line((x+w-12,y-10,x+w,y,x+w-12,y+10),fill=ink,width=5)
@lru_cache(maxsize=50)
def frameplate(raw_name,zoom,dx,dy):
    path=P/'assets'/raw_name
    if not path.is_file():
        image=Image.new('RGB',(W,H),'#9a6354')
        b=ImageDraw.Draw(image)
        b.rectangle((0,230,W,833),fill='#8d593c')
        b.rectangle((196,320,502,795),fill='#2e493f')
        b.rectangle((0,840,W,H),fill='#6e5940')
        return image
    img=Image.open(path).convert('RGB')
    scale=max(W/img.width,H/img.height)*zoom/100
    nw,nh=round(img.width*scale),round(img.height*scale)
    pic=img.resize((nw,nh),Image.Resampling.LANCZOS)
    x=min(nw-W,max(0,(nw-W)//2+dx));y=min(nh-H,max(0,(nh-H)//2+dy))
    return pic.crop((x,y,x+W,y+H))

def cinema(t,scene):
    l=t-times[scene]
    zoom=[107,119,113,128,108][scene]+int(min(l,8)*.72)
    dx=[-9,34,-17,21,0][scene]+int(9*math.sin(l*.36))
    dy=[-1,18,-18,17,-4][scene]+int(7*math.sin(l*.29))
    im=frameplate('post-office.jpg',zoom,dx,dy).copy()
    shadow=Image.new('L',(1,H))
    shadow.putdata([max(36,round(153*max(0,1-y/600)),round(131*max(0,(y-900)/H*3.3))) for y in range(H)])
    im.paste('#2d1d20',(0,0,W,H),shadow.resize((W,H)))
    d=ImageDraw.Draw(im)
    for i in range(17):
        x=(i*83+int(t*(7+i%5)))%W
        y=(i*111-int(t*(9+i%3)))%1040+80
        if (i+round(t*.7))%5:d.ellipse((x,y,x+(i%3)+1,y+(i%3)+1),fill='#e8b47c')
    return im

def bar(d,t):
    rr(d,46,57,251,51,'#342529','#e2b485',20)
    envelope(d,60,69,33,GOLD,False);word(d,104,72,'POSTAL EDGE',22,WHITE)
    rr(d,532,59,139,44,WINE,'#d39393',17);word(d,602,70,'GDS RULE 3',17,WHITE,True)
    # Keep small but readable, in the safe zone of the vertical frame.
    rr(d,52,1160,616,43,'#332b31',None,12)
    word(d,360,1170,'DoP FAQ · 21 मई 2026   |   Postal Edge',16,CREAM,True)
    d.line((52,1217,668,1217),fill='#af8168',width=2)
    d.line((52,1217,52+616*t/END,1217),fill=GOLD,width=4)

def subtitle(d,y,s):
    rr(d,47,y,626,80,'#29252c','#f1c089',17)
    word(d,360,y+19,s,35,WHITE,True,573)

def scene0(t):
    l=t
    im=cinema(t,0);d=ImageDraw.Draw(im);bar(d,t)
    rr(d,52,156,616,245,WINE,'#ffce90',24)
    word(d,360,170,'GDS में 1 साल पूरा?',57,WHITE,True)
    word(d,360,259,'फॉर्म भर दूँ?',79,GOLD,True)
    x=389-179*ease((l+.25)/.95)
    actor(im,'golu' if l<1.15 or l>3.2 else 'golu_think',x,1057,498,l,l<1.05)
    actor(im,'bhaiya',568,1006,393,l)
    d=ImageDraw.Draw(im)
    if l>.58:
        z=ease((l-.58)/.64)
        envelope(d,389-28*z,834-52*z,103,CREAM)
    if l>1.85:subtitle(d,1066,'गोलू का सवाल')
    return im
def scene1(t):
    l=t-times[1];span=times[2]-times[1];im=cinema(t,1)
    x=636-130*ease(l/.85)
    actor(im,'bhaiya' if l<span*.65 else 'bhaiya_yes',x,1090,550,l,l<.85)
    actor(im,'golu_think',143,1049,332,l)
    d=ImageDraw.Draw(im);bar(d,t)
    rr(d,50,148,620,117,'#38272d','#f7c78a',18)
    word(d,360,174,'रुक गोलू! कौन-सा ट्रांसफ़र?',42,WHITE,True)
    for i,(label,helptext,col) in enumerate([('सामान्य','अकेले जगह बदलनी है',WINE),('म्यूचुअल','साथी से पोस्टिंग बदलनी है','#284c42')]):
        v=ease((l-span*.37*i)/.59)
        if v<=0: continue
        y=316+i*134
        x=57+int(80*(1-v))
        rr(d,x,y,602,111,col,'#d9a881',18)
        word(d,x+27,y+15,label,33,GOLD)
        word(d,x+27,y+64,helptext,28,WHITE)
        envelope(d,x+511,y+30,59,GOLD)
    return im

def circle_scene(t):
    l=t-times[2];span=times[3]-times[2];im=cinema(t,2);d=ImageDraw.Draw(im);bar(d,t)
    word(d,360,149,'कितनी लगातार सेवा?',53,WHITE,True,645,2)
    for j,(label,number,color,start) in enumerate([('म्यूचुअल','1','#234b40',0),('सामान्य','2',WINE,.34),('PwBD GDS','1','#234b40',.69)]):
        v=ease((l-span*start)/.53)
        if v<=0: continue
        x=57+int(67*(1-v));y=280+j*182
        rr(d,x,y,603,149,color,'#f4c990',21)
        word(d,x+31,y+48,label,41,WHITE,maxw=380)
        rr(d,x+405,y+20,172,106,CREAM,None,16)
        word(d,x+490,y+40,number+' साल',46,color,True,maxw=150)
    actor(im,'golu' if l>span*.75 else 'golu_think',140,1125,316,l)
    actor(im,'bhaiya_yes',579,1129,323,l)
    d=ImageDraw.Draw(im);rr(d,220,940,279,66,'#f2c676',None,15)
    word(d,359,958,'अन्य शर्तें भी लागू',26,WINE,True)
    return im
def files(t):
    l=t-times[3];span=times[4]-times[3];im=cinema(t,3);d=ImageDraw.Draw(im);bar(d,t)
    rr(d,47,141,626,181,WINE,'#f7cc94',23)
    word(d,360,157,'सेवा कब तक गिनोगे?',52,WHITE,True)
    word(d,360,240,'आवेदन की आख़िरी तारीख़ तक',38,GOLD,True)
    rr(d,47,361,626,191,CREAM,'#ddad8c',19)
    word(d,71,389,'नियमित एंगेजमेंट',31,NAVY,maxw=278)
    word(d,461,389,'अंतिम तारीख़',31,NAVY,maxw=190)
    arrow(d,76,488,round(30+534*ease(l/1.65)),WINE)
    for j,label in enumerate(['लागू प्रमाणपत्र','शिक्षा','पुलिस सत्यापन']):
        v=ease((l-span*(.30+j*.17))/.42)
        if v<=0:continue
        x=62+round(60*(1-v));y=614+j*107
        rr(d,x,y,538,82,CREAM,'#d4a982',14)
        d.ellipse((x+15,y+15,x+66,y+66),fill='#35664d')
        d.line((x+27,y+43,x+36,y+50,x+51,y+33),fill=WHITE,width=4)
        word(d,x+86,y+19,label,34,NAVY)
    actor(im,'bhaiya',574,1119,302,l)
    return im
def finish(t):
    l=t-times[4];im=cinema(t,4);d=ImageDraw.Draw(im);bar(d,t)
    rr(d,49,150,622,111,WINE,'#f7c189',22)
    word(d,360,176,'म्यूचुअल साथी कहाँ मिलेगा?',44,WHITE,True)
    rr(d,48,310,624,268,CREAM,'#d7a887',22)
    word(d,79,353,'आपकी जगह',31,WINE)
    word(d,456,353,'मनचाही जगह',29,WINE)
    arrow(d,103,447,506,'#b85b61')
    x=102+506*ease(l/1.42)
    envelope(d,x-34,411,74,GOLD,True)
    word(d,360,508,'उलटी दिशा वाले साथी खोजें',29,NAVY,True)
    actor(im,'golu',181,960,365,l,l<.6)
    actor(im,'bhaiya_yes',548,962,365,l)
    d=ImageDraw.Draw(im);rr(d,50,935,620,139,WINE,'#f8cd93',21)
    word(d,360,953,'postaledge.in/transfer',44,WHITE,True)
    word(d,360,1019,'अपना रूट मुफ़्त डालो',32,GOLD,True)
    word(d,360,1102,'आवेदन की तारीख़ · विभागीय नोटिस में देखें',23,WHITE,True,620,1)
    return im

scenes=[scene0,scene1,circle_scene,files,finish]
def frame(t):
    i=max(j for j,x in enumerate(times[:5]) if x<=t)
    im=scenes[i](t)
    dt=t-times[i]
    if i and dt<.11:im=Image.blend(scenes[i-1](times[i]-.002),im,ease(dt/.11))
    return im

def score():
    sr=44100; x=np.zeros((round(sr*END),2))
    def note(at,n,dur,amp,p):
        t=np.arange(round(sr*dur))/sr
        env=np.minimum(t*190,1)*np.exp(-t*6)*np.minimum((dur-t)*11,1)
        f=440*2**((n-69)/12)
        a=env*(np.sin(2*np.pi*f*t)+.32*np.sin(4*np.pi*f*t))*amp
        start=round(sr*at);k=min(len(a),len(x)-start)
        if k<=0:return
        x[start:start+k,0]+=a[:k]*(1-p);x[start:start+k,1]+=a[:k]*p
    for j in range(4*math.ceil(END/2)):
        n=[57,64,60,67,55,62,59,64][j%8]
        note(.12+j*.50,n,.83,.10,.38 if j%2 else .64)
        if j%4==0:note(.13+j*.5,n-12,1.2,.11,.5)
    for i,v in enumerate(times[:-1]):
        note(v+.07,85-i*.5,.32,.13,.51)
    x*=np.clip((len(x)-np.arange(len(x)))/(sr*.44),0,1)[:,None]
    with wave.open(str(P/'music.wav'),'wb') as f:
        f.setparams((2,2,sr,0,'NONE','not compressed'))
        f.writeframes((x*32767).clip(-32768,32767).astype('<i2').tobytes())
def preview():
    out=Image.new('RGB',(1000,356),'#271e25')
    for i in range(5):
        t=times[i]+(times[i+1]-times[i])*.84
        out.paste(frame(t).resize((200,355)),(i*200,0))
    out.save(P/'preview.jpg',quality=91)
if __name__=='__main__':
    preview()
    if 'preview' in sys.argv:sys.exit()
    score()
    output=P/'Postal_Edge_Rule3_Transfer_Story.mp4'
    ff=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','720x1280','-r','30','-i','-','-i',str(P/'narration.wav'),'-i',str(P/'music.wav'),
      '-filter_complex','[0:v]scale=1080:1920:flags=lanczos[v];[1:a]highpass=f=80,acompressor=threshold=.14:ratio=2.3:attack=7:release=150:makeup=1.47,apad[a];[2:a]volume=.33[m];[a][m]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=.85:level=false[o]',
      '-map','[v]','-map','[o]','-t',str(END),'-threads','4','-pix_fmt','yuv420p','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-b:a','192k','-movflags','+faststart',str(output)],stdin=subprocess.PIPE)
    try:
        for i in range(round(END*30)):
            ff.stdin.write(frame(i/30).tobytes())
            if i%240==0:print(f'{i/30:.0f}s',flush=True)
    finally:ff.stdin.close()
    sys.exit(ff.wait())
