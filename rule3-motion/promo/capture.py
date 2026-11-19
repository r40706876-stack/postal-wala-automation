from pathlib import Path
import json
from playwright.sync_api import sync_playwright

out=Path(__file__).parent
A=dict(id='DEMO-A',cadre='abpm',from_state='MP',from_div='रीवा',from_dist='',to_state='MP',to_div='सतना',to_dist='')
B=dict(id='DEMO-B',cadre='bpm',from_state='UP',from_div='बाँदा',from_dist='',to_state='MP',to_div='रीवा',to_dist='')
C=dict(id='DEMO-C',cadre='dak-sevak',from_state='MP',from_div='जबलपुर',from_dist='',to_state='MP',to_div='सागर',to_dist='')
mine=dict(id='DEMO-MY-ROUTE',cadre='abpm',from_state='MP',from_div='सतना',from_dist='',to_state='MP',to_div='रीवा',to_dist='',updated='2026-11-20 00:00:00')
chosen=False
points={}
with sync_playwright() as w:
    b=w.chromium.launch(headless=True)
    p=b.new_page(viewport={'width':390,'height':735},device_scale_factor=2,locale='hi-IN')
    def route(r):
        global chosen
        from urllib.parse import urlparse,parse_qs
        address=urlparse(r.request.url)
        end=address.path.removeprefix('/api/acc/transfer/')
        if end=='list':
            items=[A] if parse_qs(address.query).get('view')==['matches'] else [A,B,C]
            data={'signedIn':True,'stats':{'active':3,'connected':0},'rows':items,'total':len(items)}
        elif end=='inbox':
            data={'own':mine if chosen else None,'items':[],'matches':1 if chosen else 0,'incoming':0}
        elif end=='publish' and r.request.method=='POST':
            chosen=True
            data={'id':mine['id']}
        else:
            r.abort()
            return
        r.fulfill(json=data)
    p.route('**/api/acc/transfer/**',route)
    p.route('https://**',lambda r:r.abort())
    p.goto('http://127.0.0.1:8779/transfer/',wait_until='networkidle',timeout=20000)
    p.locator('.board .route').last.wait_for()
    p.evaluate("""()=>{
      const item=document.createElement('div');
      item.textContent='डेमो • केवल उदाहरण';
      Object.assign(item.style,{position:'fixed',top:'8px',right:'8px',background:'#842344',color:'#fff',fontWeight:'850',fontSize:'12px',boxShadow:'0 4px 12px #35132666',padding:'7px 10px',borderRadius:'12px',zIndex:'2147483647',pointerEvents:'none'});
      document.body.append(item);
      document.querySelector('[data-t=open]').textContent='नमूना रूट';
      document.querySelector('#connected').parentElement.hidden=true;
    }""")
    def snap(name,selector=None,scroll=None):
        if scroll:p.locator(scroll).first.evaluate('el=>el.scrollIntoView({block:"start",behavior:"instant"})')
        if selector:
            r=p.locator(selector).first.bounding_box()
            points[name]=[r['x']+r['width']/2,r['y']+r['height']/2]
        p.screenshot(path=str(out/(name+'.jpg')),type='jpeg',quality=93,animations='disabled')
    snap('website','#start')
    snap('routes',scroll='#filter')
    p.locator('#start').click()
    p.locator('#post-route').wait_for()
    p.select_option('[name=cadre]','abpm')
    p.select_option('[name=from_state]','MP')
    p.fill('[name=from_div]','सतना')
    p.select_option('[name=to_state]','MP')
    p.fill('[name=to_div]','रीवा')
    snap('form','[name=to_div]',scroll='#view')
    p.fill('[name=phone]','0000000000')
    p.check('[name=consent]')
    p.locator('#post-route button[type=submit]').click()
    p.locator('#view .route').wait_for()
    assert chosen
    p.locator('[data-view=matches]').click()
    p.locator('#view .board .route').wait_for()
    p.get_by_text('DEMO-A',exact=False).wait_for()
    snap('match','.route-actions button',scroll='#tabs')
    b.close()
(out/'points.json').write_text(json.dumps(points))
