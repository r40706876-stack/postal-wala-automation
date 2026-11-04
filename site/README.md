# Postal Wala website

Free website: notes (chitra), mock test, PYQ, clause practice, GDS tools.
Live: https://r40706876-stack.github.io/postal-wala-automation/

## Update kaise karein
1. Naye PYQ `pyq_papers/pyq_bank.json` me, naye clause `clause_plans/` me jodo.
2. Naye clause ke notes: page images `site/notes/cXX_notes.webp`, `cXX_chitra.webp`, `cXX_sketch.webp`
   (+ chhoti `_t.webp`) daalo aur `site/site_template.html` me `NOTES` list me clause jodo.
3. Mock ke galat sawal ka PDF explanation: `site/notes/qmap.json` me
   `"pyq_id": [clause, x0, y0, x1, y1, "text_key"]` aur `_texts` me us hisse ki baat.
4. Rates / DA / chhuttiyan badlein to `site/site_template.html` me `INFO` block badlo.
5. Phir chalao:  `python site/build_site.py . docs`  aur `docs/` commit karo.
