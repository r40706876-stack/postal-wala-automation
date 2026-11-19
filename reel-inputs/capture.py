from pathlib import Path
import json
import shutil
from playwright.sync_api import sync_playwright

out = Path("reel-inputs")
out.mkdir(exist_ok=True)
base = "http://127.0.0.1:8871/"
points = {}
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    pg = b.new_page(viewport={"width":420,"height":790},device_scale_factor=2,is_mobile=True,has_touch=True)
    pg.route("https://**", lambda r: r.abort())
    pg.route("**/api/**",lambda r:r.fulfill(json={"ok":False,"user":None,"own":[]}))
    pg.on("pageerror",lambda e: print("Page:",e,flush=True))
    def go(hash=""):
        pg.goto(base+hash,wait_until="domcontentloaded",timeout=25000)
        pg.wait_for_function("!!window.__PED && !document.querySelector('#app .seo-pre')",timeout=22000)
        pg.wait_for_timeout(330)
    def center(el, y=225):
        el.evaluate("(el,y)=>window.scrollTo({top:Math.max(0,el.getBoundingClientRect().top+scrollY-y),behavior:'instant'})",y)
        pg.wait_for_timeout(260)
    def grab(name, focus=None, y=None):
        el = pg.locator(focus).first if focus else None
        if el is not None:
            el.wait_for(timeout=6000)
            if y is not None:
                center(el,y)
            q=el.bounding_box()
            points[name]=[round(q["x"]+q["width"]/2),round(q["y"]+q["height"]/2)]
        pg.screenshot(path=str(out/(name+".jpg")),type="jpeg",quality=90,animations="disabled",timeout=10000)
        print("Captured",name,points.get(name),flush=True)
    go()
    grab("home","[data-hdv]",132)
    pg.locator("[data-hdv]").first.click()
    pg.wait_for_timeout(800)
    grab("demo","#dvCov",215)
    go("#mock")
    grab("mock",'[data-mode="10"]')
    go("#quiz")
    grab("daily","#go",295)
    pg.locator("#go").click()
    pg.locator(".opt").nth(1).click()
    pg.wait_for_timeout(240)
    explain=pg.locator(".anx,.an,.deep,.wrong").first
    if explain.count(): center(explain,165)
    grab("answer")
    go("#papers")
    grab("papers", ".prow[href='#exam-mts']")
    pg.locator(".prow[href='#exam-mts']").click()
    pg.wait_for_timeout(450)
    tab=pg.locator("button[data-etab='p']").first
    if tab.count(): tab.click()
    pg.wait_for_timeout(300)
    grab("paperlist")
    go("#notes")
    link=".book.cl"
    grab("notes",link,270)
    pg.locator(link).first.click()
    pg.wait_for_timeout(600)
    if pg.locator(".thead").count()==0:
        raise RuntimeError("Clause page did not open")
    grab("clause")
    go("#plans")
    grab("mts","#pl-mts",112)
    grab("postman","#pl-pm",112)
    b.close()
(out/"points.json").write_text(json.dumps(points))
for name in ("bhaiya.webp", "bhaiya_shabaash.webp","bhaiya_batata.webp","golu.webp","golu_chauka.webp"):
    path=Path("docs/img")/name
    if path.is_file(): shutil.copy(path,out/name)
