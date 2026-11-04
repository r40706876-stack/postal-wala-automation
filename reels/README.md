# Notes PDF promo reels (1080x1920, 30fps, no voice)
| File | Format | Length |
|---|---|---|
| PostalWala_Reel3_EkNazar.mp4 | "एक नज़र" box: 6 tiles pop → trap + trick → CTA | 15.5s |
| PostalWala_Reel5_KitabVsPDF.mp4 | मोटी किताब (162) vs Short Notes (46) → flip-through → CTA | 14.5s |

Re-render (e.g. after adding price to the CTA text in src/*.html):
```
cd reels/src
python3 assets.py ../../handnotes/out/PO_Guide_Short_Notes_FULL_Hindi.pdf a
python3 -c "m=open('a/glance.json').read();open('reel3_b.html','w').write(open('reel3.html').read().replace('__META__',m))"
python3 render.py reel3_b.html 15.5 ../PostalWala_Reel3_EkNazar.mp4
python3 render.py reel5.html 14.5 ../PostalWala_Reel5_KitabVsPDF.mp4
```
Glance box page is set in assets.py (GLANCE_PAGE) — change it to make a new "एक नज़र" reel for another topic.
Add trending audio inside Instagram.
