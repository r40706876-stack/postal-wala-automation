import math

import numpy as np
from PIL import Image, ImageDraw
from lip_shapes import draw_mouth

ink = "#30232B"

def clamp(x):
    return max(0,min(1,x))

def blend(t, a, b):
    x = clamp((t-a)/(b-a))
    return x*x*(3-2*x)

def ramp(t,a,b,c,d):
    return blend(t,a,b)*(1-blend(t,c,d))

def puppet(is_golu, t, walking, facing, speaking, mood, action, gaze, airborne, movement):
    canvas=Image.new("RGBA",(340,520))
    d=ImageDraw.Draw(canvas)
    skin="#FFD0A3" if is_golu else "#EFB17F"
    hair="#253049" if is_golu else "#322429"
    shirt="#BFE4FE" if is_golu else "#EBD09B"
    trim="#6BA1CB" if is_golu else "#B89759"
    pants="#405B88" if is_golu else "#AD8A60"
    bag="#F05D64" if is_golu else "#825037"
    foot_phase=(t+.10*is_golu)*math.tau*2.7
    step=math.sin(foot_phase)*walking
    weight=movement*8
    voice_effort=0 if speaking is None else speaking[1]/22

    def edge(points, width, color, line=ink):
        d.line(points, fill=line, width=width+5, joint="curve")
        for x,y in points:
            d.ellipse((x-(width+5)/2,y-(width+5)/2,x+(width+5)/2,y+(width+5)/2),fill=line)
        d.line(points, fill=color, width=width, joint="curve")
        for x,y in points:
            d.ellipse((x-width/2,y-width/2,x+width/2,y+width/2),fill=color)

    for s in (-1,1):
        footx = 170+35*s + 28*step*s + s*15*airborne + weight*(1 if s==1 else .38)
        footy = 480 - 32*walking*max(0,math.cos(foot_phase)*s) - (14+11*s)*airborne - max(0,weight*s)*.9
        edge([(170+25*s,373),(170+34*s+10*step*s,425-(10+12*s)*airborne),(footx,footy)],36,pants)
        toe = 10 * (1 if facing>=0 else -1)
        d.rounded_rectangle((footx-23+toe,footy-6,footx+24+toe,footy+15),radius=10, fill="#F6F2E8" if is_golu else "#462C29",outline=ink,width=3)
        d.line((footx-13+toe,footy+10,footx+14+toe,footy+10),fill="#D34D51" if is_golu else "#7C5640",width=3)
    d.rounded_rectangle((95,239,243,388),radius=30,fill=shirt,outline=ink,width=4)
    if is_golu:
        mask=Image.new("L",canvas.size)
        ImageDraw.Draw(mask).rounded_rectangle((99,243,239,383),radius=27,fill=255)
        checks=Image.new("RGBA",canvas.size)
        c=ImageDraw.Draw(checks)
        for x in range(104,240,13): c.line((x,241,x,386),fill="#83BEE8",width=2)
        for y in range(246,385,12): c.line((97,y,241,y),fill="#E8F6FF",width=3)
        canvas.paste(checks,(0,0),Image.fromarray(np.minimum(np.array(mask), np.array(checks.getchannel("A")))))
    d.polygon([(123,239),(170,254),(212,239),(197,270),(171,260),(145,273)],fill=trim)
    for y in (278,307,337,366): d.ellipse((167,y,173,y+6), fill=ink if is_golu else "#917048")
    if not is_golu:
        for x in (116,192):
            d.rounded_rectangle((x,278,x+32,305), radius=3, fill="#D5B882",outline="#AA8A59",width=2)
        d.line((212,274,213,294),fill="#3B6696",width=4)
        d.rectangle((120,270,151,274), fill="#B2463C")
        d.rounded_rectangle((96,372,242,384),radius=4,fill="#725139")
        d.rectangle((161,369,178,386),fill="#F5C777",outline=ink,width=2)
    strap=((224,245),(107,376)) if is_golu else ((114,249),(237,374))
    d.line(strap,fill=bag,width=12)
    d.line(strap,fill="#F58577" if is_golu else "#A46E46",width=4)
    bx = 76 if is_golu else 216
    d.rounded_rectangle((bx,348,bx+52,414),radius=10, fill=bag, outline=ink,width=3)
    d.line((bx+3,368,bx+48,368),fill="#FF9F8C" if is_golu else "#B98255",width=3)
    d.ellipse((bx+24,373,bx+30,379),fill="#FBC66A")

    for s in (-1,1):
        sx=170+65*s
        sw=-step*s*21
        el=(sx+s*(12+10*walking),306+sw)
        hand=(sx+s*18+sw,356+sw*1.65)
        strength, gesture = action
        if is_golu:
            if gesture=="chin":
                elbow_target=(sx+s*34,282)
                target=(208,209) if s==1 else (74,309)
                lift=strength*(1 if s==1 else .28)
            elif gesture=="hop":
                elbow_target=(sx+s*(28+13*airborne),273-49*airborne)
                target=(sx+s*(39+14*airborne),240-68*airborne)
                lift=strength*(1-.15*(s==-1))
            else:
                elbow_target=(sx+s*32,292)
                target=(sx+s*50,253-5*s)
                lift=strength*(1-.24*(s==-1))
        else:
            primary=-1 if gesture in ("stop","left","welcome") else 1
            lift=strength*(1 if s==primary else .28)
            beat=7*voice_effort+4*math.sin(t*10)
            elbow_target=(sx+s*35,294-9*(gesture=="stop")-beat)
            target=(sx+s*37,223-beat) if gesture=="stop" else (sx+s*62,254-beat)
            if gesture=="welcome":
                target=(sx+s*47,270)
        el=tuple(a+(b-a)*lift for a,b in zip(el,elbow_target))
        hand=tuple(a+(b-a)*lift for a,b in zip(hand,target))
        shoulder=(sx,259)
        edge([shoulder, el, hand],21,skin)
        sleeve=tuple(a+(b-a)*.46 for a,b in zip(shoulder,el))
        edge([shoulder,sleeve],29,shirt)
        x,y=hand
        open_hand = lift>.50 and gesture in ("open","stop","right","left","hop","welcome")
        d.ellipse((x-11,y-11,x+11,y+11),fill=skin,outline=ink,width=2)
        if open_hand:
            if gesture == "stop":
                fingers=[((x+i*4,y-5),(x+i*4,y-16-2*(i==0))) for i in (-1,0,1)]
                fingers.append(((x-4,y+3),(x-12,y-3)))
            else:
                fingers=[((x+s*5,y+i*4),(x+s*(15+2*(i==0)),y+i*4-3)) for i in (-1,0,1)]
            for start,end in fingers:
                d.line((start,end),fill=ink,width=6)
                d.line((start,end),fill=skin,width=3)

    d.rounded_rectangle((150,211,188,254),radius=10,fill=skin,outline=ink,width=3)
    face=Image.new("RGBA",(340,300))
    f=ImageDraw.Draw(face)
    # Offset the nose, gaze and cheek asymmetry when a character turns.
    shift=12*facing
    for x in (101,239):
        f.ellipse((x-16,133,x+17,169),fill=skin,outline=ink,width=3)
    f.ellipse((97,64,245,236),fill=skin,outline=ink,width=4)
    f.arc((111,81,230,210),195,286,fill="#FFE4BF",width=3)
    if is_golu:
        f.polygon([(97,149),(89,110),(98,83),(85,81),(112,64),(108,53),(142,59),(149,39),(163,54),(192,31),(192,58),(213,46),(211,68),(235,63),(248,94),(245,139),(230,123),(224,99),(199,106),(180,91),(149,113),(127,103),(111,140)],fill=hair)
    else:
        f.polygon([(97,129),(95,99),(107,81),(143,68),(215,75),(243,96),(245,134),(230,124),(223,100),(158,101),(117,112),(109,135)],fill=hair)
        f.rounded_rectangle((83,56,252,95),radius=12,fill="#F2DCA4",outline=ink,width=4)
        f.rounded_rectangle((86,77,250,97),radius=6,fill="#A3423F",outline=ink,width=2)
        f.ellipse((162,66,178,85),fill="#EBC264",outline="#854738",width=2)
        f.ellipse((111,90,209,107),fill="#3C2B32")
    blink_time=(t+(0.6 if is_golu else 1.24))%2.72
    closed=.0 < blink_time < .095
    for index, bx in enumerate((136,199)):
        x=bx+shift*.62
        h=(19 if mood=="surprise" else 13)
        brow_y=118-(8 if mood=="surprise" else (3 if mood=="think" and index else 0))
        f.line((x-14,brow_y+4,x-3,brow_y,x+13,brow_y+(3 if mood!="think" else 8)),fill=hair,width=5,joint="curve")
        if closed:
            f.arc((x-14,136,x+14,149),0,180,fill=ink,width=3)
        else:
            f.ellipse((x-15,143-h,x+15,143+h),fill="#FFF7E8",outline=ink,width=2)
            px=x+6*gaze
            f.ellipse((px-5,136,px+6,150),fill="#382630")
            f.ellipse((px-2,137,px+1,140),fill="white")
        if is_golu:
            f.ellipse((x-24,119,x+24,165),outline="#282833",width=5)
    if is_golu:
        f.line((160+shift*.62,140,176+shift*.62,139),fill=ink,width=4)
    nx=169+shift
    f.line((nx,151,nx+5,167,nx-1,170),fill="#A86047",width=3,joint="curve")
    for x in (120,218):
        if mood in ("happy","surprise") or not is_golu:
            f.ellipse((x-8,174,x+8,182),fill="#EC9679")
    if not is_golu:
        for sign in (-1,1):
            f.ellipse((nx+sign*12-13,169,nx+sign*12+13,181),fill=hair)
    draw_mouth(f,nx,192,speaking,mood,ink,skin)
    nod = 2.8*math.sin(t*13)*airborne if is_golu else 0
    tilt = (-6 if mood=="think" else 0) + 3.5*voice_effort*math.sin(t*7) + 4*walking*math.sin(t*12) + nod
    face=face.rotate(tilt, Image.Resampling.BICUBIC, center=(170,225))
    canvas.alpha_composite(face,(0,0))
    return canvas

