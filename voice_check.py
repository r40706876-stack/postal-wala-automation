"""TEST v2: SadTalker halka - 4s awaaz, bina enhancer, 25 min seema, har 2 min progress branch me."""
import os, subprocess, sys, time, glob, shutil
OUT = "voice_check_out"; os.makedirs(OUT, exist_ok=True)
BR = os.getenv("TEST_BRANCH", "test-talking")
LOGP = os.path.join(OUT, "talk_log.txt"); LOG = open(LOGP, "w")
subprocess.run('git config user.name "github-actions[bot]"; git config user.email "github-actions[bot]@users.noreply.github.com"', shell=True)
T0 = time.time()
def note(s):
    LOG.write(f"[{time.time()-T0:5.0f}s] {s}\n"); LOG.flush(); print(s, flush=True)
def push(msg):
    subprocess.run(f'git add -f {OUT} && git commit -q -m "{msg} [skip ci]" && git push -q origin HEAD:{BR}', shell=True)
def sh(cmd, check=True, limit=1800):
    note(">> " + cmd)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        note("TIMEOUT"); push("progress: timeout"); raise SystemExit("timeout")
    note((r.stdout + r.stderr)[-1500:] + f"\n[exit {r.returncode}]")
    if check and r.returncode:
        push("progress: fail"); raise SystemExit("FAIL")
    return r
try:
    sh("sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc /opt/hostedtoolcache/CodeQL; df -h / | tail -1; nproc; free -g | head -2", check=False)
    sh("git clone --depth 1 https://github.com/OpenTalker/SadTalker /tmp/st")
    sh(f"{sys.executable} -m pip install -q torch==2.0.1 torchvision==0.15.2 --index-url https://download.pytorch.org/whl/cpu")
    sh(f"{sys.executable} -m pip install -q numpy==1.23.5 face_alignment==1.3.5 imageio==2.19.3 imageio-ffmpeg==0.4.7 "
       "librosa==0.9.2 numba resampy==0.3.1 pydub==0.25.1 scipy==1.10.1 kornia==0.6.8 tqdm yacs==0.1.8 pyyaml "
       "joblib==1.1.0 scikit-image==0.19.3 av safetensors cython lmdb opencv-python-headless addict future yapf")
    sh(f"{sys.executable} -m pip install -q --no-build-isolation basicsr==1.4.2 facexlib==0.3.0 gfpgan")
    sh(f"{sys.executable} -m pip install -q torch==2.0.1 torchvision==0.15.2 numpy==1.23.5 --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple")
    sh("cd /tmp/st && bash scripts/download_models.sh")
    push("progress: install ho gaya")
    img = os.path.abspath("talk_test/postman.png")
    wav = "/tmp/v4.wav"
    sh(f"ffmpeg -v error -y -i talk_test/voice.wav -t 4 -ar 16000 -ac 1 {wav}")
    res = "/tmp/res"
    cmd = (f"cd /tmp/st && {sys.executable} inference.py --driven_audio {wav} --source_image {img} --result_dir {res} "
           f"--cpu --size 256 --still --preprocess full")
    note(">> " + cmd)
    lf = open(os.path.join(OUT, "inference_out.txt"), "w")
    p = subprocess.Popen(cmd, shell=True, stdout=lf, stderr=subprocess.STDOUT)
    t1 = time.time(); last = t1
    while p.poll() is None:
        time.sleep(10)
        if time.time() - t1 > 25 * 60:
            p.kill(); note("25 min seema paar - roka"); break
        if time.time() - last > 120:
            last = time.time(); lf.flush(); push(f"progress: inference {int(time.time()-t1)}s")
    lf.close()
    vids = sorted(glob.glob(f"{res}/**/*.mp4", recursive=True), key=os.path.getmtime)
    if vids:
        shutil.copy(vids[-1], os.path.join(OUT, "talk_still_full.mp4")); note(f"BANA: {vids[-1]} ({int(time.time()-t1)}s)")
    else:
        note(f"VIDEO NAHI BANA (exit {p.returncode})")
finally:
    LOG.close()
