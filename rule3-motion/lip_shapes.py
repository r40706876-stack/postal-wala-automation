from functools import lru_cache

import numpy as np
from scipy.linalg import solve_toeplitz
from scipy.ndimage import median_filter
from scipy.signal import resample_poly

CLOSED = (28, 1.1, 0, 0)

@lru_cache
def window(length):
    return np.hamming(length)

def measure_mouth(sound, fps, duration):
    signal = resample_poly(sound, 5, 8)
    preemphasis = np.r_[signal[0], signal[1:] - .94*signal[:-1]]
    rows = []
    previous_vowel = np.array([34, 12, .55, .2])
    for frame in range(round(duration*fps)):
        center = round(10000 * (frame/fps + .013))
        segment = signal[max(0, center-160):center+160]
        lift = preemphasis[max(0, center-160):center+160]
        energy = np.sqrt(np.mean(segment**2)) if len(segment) else 0
        if energy < .016 or len(segment) < 295:
            rows.append(CLOSED)
            continue
        correlated = np.correlate(segment, segment, "full")[len(segment)-1:]
        periodicity = float(np.max(correlated[28:124]) / max(correlated[0], 1e-6))
        centered = lift * window(len(lift))
        auto = np.correlate(centered, centered, "full")[len(lift)-1:]
        if periodicity < .32:
            bright = np.sqrt(np.mean(lift**2)) / max(energy, 1e-6)
            dims = (30, 5, .75, 0) if bright > .70 else (26, 2.4, .18, 0)
            rows.append(dims)
            continue
        coeffs = solve_toeplitz((auto[:12],auto[:12]), -auto[1:13])
        roots = np.roots(np.r_[1., coeffs])
        poles = [(np.angle(root)*10000/(2*np.pi), -np.log(abs(root))*10000/np.pi)
                 for root in roots if np.imag(root)>0 and abs(root)>0]
        freqs = [f for f,bw in sorted(poles) if 240<f<3200 and 0<bw<530]
        if len(freqs) >= 2:
            f1 = np.clip((freqs[0]-300)/520, 0, 1)
            # A lower second formant generally accompanies the rounded vowels in this voice.
            front = np.clip((freqs[1]-850)/1250, 0, 1)
            rounded = (1-front) * (1-.25*f1)
            dims = np.array([25+15*front-8*rounded, 9+13*f1+3*rounded, .24+.65*front, rounded])
            previous_vowel = .27*previous_vowel + .73*dims
        amp = np.clip((energy-.012)/.07, .23, 1)
        w,h,teeth,rounded = previous_vowel
        rows.append((w, 2+(h-2)*amp, teeth, rounded))
    values = np.asarray(rows)
    smoothed = median_filter(values,size=(3,1),mode="nearest")
    # Keep closures at real spoken pauses. Smooth only transitions between articulated shapes.
    return np.where(values[:,1:2] < 3, values, .38*values+.62*smoothed)

def draw_mouth(draw, x, y, shape, mood, ink, skin):
    if shape is None or shape[1] < 3:
        lift = 5 if mood == "happy" else (2 if mood == "rest" else 0)
        width = 16 if mood == "happy" else (11 if mood == "surprise" else 14)
        points = [(x+width*u/6, y+lift*(1-(u/6)**2)) for u in range(-6,7)]
        draw.line(points, fill=ink, width=3, joint="curve")
        return
    width, height, teeth, rounded = shape
    half = width/2
    top = height*(.20+.23*rounded)
    bottom = height-top
    outer = []
    for i in range(21):
        u = i/10-1
        curve = max(0,1-u*u)**(.65 if rounded>.5 else .88)
        outer.append((x+half*u,y-top*curve-.6*u))
    for i in range(20,-1,-1):
        u = i/10-1
        curve = max(0,1-u*u)**.72
        outer.append((x+half*u,y+bottom*curve-.6*u))
    draw.polygon(outer,fill="#552934")
    draw.line(outer+[outer[0]],fill=ink,width=2,joint="curve")
    if height>5 and teeth>.36 and rounded<.56:
        tw=half*(.66+.12*teeth)
        draw.polygon([(x-tw,y-top*.35),(x-tw*.55,y-top*.73),(x+tw*.55,y-top*.73),
                      (x+tw,y-top*.4),(x+tw*.70,y+1),(x-tw*.64,y+1)],fill="#FFF3D9")
    if height>15:
        draw.ellipse((x-half*.44,y+bottom*.54,x+half*.46,y+bottom*.83),fill="#BD6767")
