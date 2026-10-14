"""TEST: SadTalker - ek photo + awaaz -> bolta chehra (sirf test, roz ki reel se alag)."""
import os, subprocess, sys, time, glob, shutil
OUT = "voice_check_out"; os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "talk_log.txt"), "w")
def sh(cmd, check=True):
    t = time.time(); print(">>", cmd, flush=True); LOG.write(f">> {cmd}\n"); LOG.flush()
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    tail = (r.stdout + r.stderr)[-3000:]
    LOG.write(tail + f"\n[exit {r.returncode}, {time.time()-t:.0f}s]\n\n"); LOG.flush(); print(tail)
    if check and r.returncode: raise SystemExit(f"FAIL: {cmd}")
    return r
try:
    sh("git clone --depth 1 https://github.com/OpenTalker/SadTalker /tmp/st")
    sh(f"{sys.executable} -m pip install -q torch==2.0.1 torchvision==0.15.2 --index-url https://download.pytorch.org/whl/cpu")
    sh(f"{sys.executable} -m pip install -q numpy==1.23.5 face_alignment==1.3.5 imageio==2.19.3 imageio-ffmpeg==0.4.7 "
       "librosa==0.9.2 numba resampy==0.3.1 pydub==0.25.1 scipy==1.10.1 kornia==0.6.8 tqdm yacs==0.1.8 pyyaml "
       "joblib==1.1.0 scikit-image==0.19.3 basicsr==1.4.2 facexlib==0.3.0 gfpgan av safetensors")
    sh("cd /tmp/st && bash scripts/download_models.sh")
    img, wav = os.path.abspath("talk_test/postman.png"), os.path.abspath("talk_test/voice.wav")
    for name, extra in (("still_full", "--still --preprocess full"), ("move_crop", "--preprocess crop")):
        res = f"/tmp/res_{name}"
        sh(f"cd /tmp/st && {sys.executable} inference.py --driven_audio {wav} --source_image {img} --result_dir {res} "
           f"--cpu --size 256 --enhancer gfpgan {extra}", check=False)
        vids = sorted(glob.glob(f"{res}/**/*.mp4", recursive=True), key=os.path.getmtime)
        if vids:
            shutil.copy(vids[-1], os.path.join(OUT, f"talk_{name}.mp4"))
            LOG.write(f"BANA: {name} -> {vids[-1]}\n")
        else:
            LOG.write(f"NAHI BANA: {name}\n")
finally:
    LOG.close()
