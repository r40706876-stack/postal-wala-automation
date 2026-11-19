"""Prepare and render the native Notes workflow preview in a disposable checkout."""

from pathlib import Path
import shutil

ROOT = Path.cwd()
EXTRAS = Path(__file__).resolve().parent


def replace_once(path, old, new):
    source = path.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise RuntimeError(f"Could not locate the Notes integration point in {path}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


shutil.copyfile(EXTRAS / "notes_characters.py", ROOT / "notes_characters.py")
notes = ROOT / "notes_reel.py"
replace_once(notes, '    html = open(SCENE, encoding="utf-8")',
             '    from notes_characters import make_sprites\n'
             '    data["characters"] = make_sprites(tmp, tl, track, sr)\n'
             '    html = open(SCENE, encoding="utf-8")')
scene = ROOT / "reels/src/notes_scene.html"
replace_once(scene, "el.className='s';el.innerHTML=html;",
             "el.className='s';el.dataset.segment=k;el.innerHTML=html;")
replace_once(scene, "</script>", "</script>\n<script>\n" +
             (EXTRAS / "notes_characters.js").read_text(encoding="utf-8") + "\n</script>")
renderer = ROOT / "reels/src/render.py"
replace_once(renderer, "    for i in range(n):",
             '    pg.evaluate("() => window.loadNotesCharacters()")\n    for i in range(n):')
replace_once(renderer, "        _brand.page_time(pg, t / 1000)",
             '        _brand.page_time(pg, t / 1000)\n'
             '        pg.evaluate("t => window.drawNotesCharacter(t)", t / 1000)')
replace_once(renderer, "    b.close()",
             '    seen = pg.evaluate("() => [...window.notesCharactersSeen]")\n'
             '    if sorted(seen) != ["golu", "postman"]:\n'
             '        raise RuntimeError(f"Both characters must appear without covering the notes: {seen}")\n'
             '    print("Notes characters rendered clear of the text:", seen, flush=True)\n'
             '    b.close()')

shutil.copyfile(EXTRAS / "preview_voice.py", ROOT / "preview_voice.py")
replace_once(notes, "    auds, sr, used = voice([s for _, s in order], lang)",
             '    from preview_voice import voice as preview_voice\n'
             '    auds, sr, used = preview_voice([s for _, s in order], lang)')
replace_once(notes, '    try:\n        res = main.as_dict(main._llm_json(prompt))\n    except Exception as exc:\n        print("  script AI fail',
             '    try:\n        res = {} if CUSTOM else main.as_dict(main._llm_json(prompt))\n    except Exception as exc:\n        print("  script AI fail')
