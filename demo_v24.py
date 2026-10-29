"""
DEMO (ek baar, 2026-10-29): bharosa v24 "sawal pehle" - Clause 26 Part 5 (videshi pata), ASLI awaaz ke saath.
Kuch post nahi hota, state/progress nahi badalta. Chalana: Actions -> "Demo - v24 sawal pehle" -> Run workflow.
Nateeja: demo_out/bharosa_v24/demo_v24_clause26_part5.mp4
Pasand aaye -> main.py me BHAROSA_V2 chalu (bharosa.py me V2 default "1").
"""
import glob
import json
import os
import sys

os.environ["BHAROSA_V2"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main as M
import bharosa

PART = 4                                   # Part 5 (0 se ginti)
OUT = os.path.join("demo_out", "bharosa_v24")
os.makedirs(OUT, exist_ok=True)

plan = json.load(open("clause_plans/clause_26.json", encoding="utf-8"))
part = plan["parts"][PART]
for pn in part["chitra_v"]["panels"]:      # asli panel jpg build ke baad mit jaate hain -> bache frame lo
    if not os.path.exists(pn["img"]):
        base = pn["img"][:-4]
        key, idx = os.path.basename(base).split("_")[0], base.rsplit("_", 1)[1]
        c = (sorted(glob.glob(f"{base}f1.jpg")) + sorted(glob.glob(f"clause_plans/chitra_img/{key}_keep_*_{idx}.jpg"))
             + sorted(glob.glob(f"clause_plans/chitra_img/{key}_*{idx}f*.jpg"))
             + sorted(glob.glob(f"clause_plans/chitra_img/{key}_*.jpg")))
        pn["img"] = c[0]

data_in = dict(part)
data_in["title"] = plan.get("title_hi") or plan.get("title_en", "")
data = M.prepare_data(data_in, 26, PART + 1, total_parts=len(plan["parts"]), next_title="", syllabus=(25, 71))
data["episode"] = 100
bharosa.init(M)
out = os.path.join(OUT, "demo_v24_clause26_part5.mp4")
if os.path.exists(out):
    os.remove(out)
bharosa.build(data, out, plan, part)
for f in glob.glob(os.path.join(OUT, "*_bharosa_audio.wav")):
    os.remove(f)
print("DEMO BANI:", out)
