"""handnotes/notes_*.html -> handnotes/out/*.pdf (A4, handwriting font Kalam).
GitHub Actions par chalta hai (wahan internet hai, font Google Fonts se aata hai).
Local: pip install playwright && playwright install chromium && python handnotes/build_pdf.py
"""
import glob, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
files = sorted(glob.glob(os.path.join(HERE, "notes_*.html")))
foot = ('<div style="width:100%;font-size:8pt;color:#888;text-align:center;font-family:sans-serif">'
        'PO Guide Part I · Short Notes · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
with sync_playwright() as p:
    exe = os.environ.get("CHROME_PATH")
    b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
    for f in files:
        pg = b.new_page()
        pg.goto("file://" + f, wait_until="networkidle")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(800)
        name = os.path.splitext(os.path.basename(f))[0]
        dst = os.path.join(OUT, f"PO_Guide_Short_Notes_{name.split('_')[-1]}.pdf")
        pg.pdf(path=dst, format="A4", print_background=True, prefer_css_page_size=True,
               display_header_footer=True, header_template="<div></div>", footer_template=foot)
        print("OK", dst)
    b.close()
