from pathlib import Path
import subprocess,wave,json
import numpy as np
p=Path(__file__).parent
with wave.open(str(p/'narration_raw.wav'),'rb') as f:
    sr=f.getframerate();raw=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2')
assert abs(len(raw)/sr-29.8)<.02
gaps=[(2.817,3.248),(4.536,5.221),(5.914,6.313),(9.704,10.370),(11.473,11.992),(13.280,13.936),(15.695,16.335),(20.364,20.896),(21.906,22.736),(23.590,24.106),(26.170,26.763),(28.651,29.121)]
cuts=[(a+.097,b-.097) for a,b in gaps]+[(29.7,len(raw)/sr)]
pieces=[];position=0
for a,b in cuts:
    pieces.append(raw[round(position*sr):round(a*sr)]);position=b
with wave.open(str(p/'narration.wav'),'wb') as f:
    f.setparams((1,2,sr,0,'NONE','not compressed'));f.writeframes(np.concatenate(pieces).tobytes())
def new(t):return t-sum(max(0,min(t,b)-a) for a,b in cuts)
bound=[0]+[round(new(t),3) for t in [5.125,10.275,16.238,22.639]]+[round(new(29.7)+.7,3)]
(p/'timing.json').write_text(json.dumps(bound))
print(bound)
