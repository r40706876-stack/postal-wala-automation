// Reserve only genuinely empty space around the existing Notes cards.
(() => {
  const stage = document.getElementById('st');
  const canvas = document.createElement('canvas');
  canvas.width = 200;
  canvas.height = 308;
  canvas.style.cssText = 'display:none;position:absolute;z-index:2;pointer-events:none';
  stage.appendChild(canvas);
  const context = canvas.getContext('2d');
  const sprites = D.characters ?? [];
  window.notesCharactersSeen = new Set();
  window.loadNotesCharacters = () => Promise.all(sprites.map(async sprite => {
    sprite.atlas = new Image();
    sprite.atlas.src = sprite.image;
    await sprite.atlas.decode();
  }));
  window.drawNotesCharacter = time => {
    canvas.style.display = 'none';
    const sprite = sprites.find(s => time >= s.start && time < s.start + s.count / s.fps);
    if (!sprite) return;
    const scene = stage.querySelector('[data-segment="' + sprite.segment + '"]');
    if (!scene || Number(getComputedStyle(scene).opacity) < .97) return;
    const stageRect = stage.getBoundingClientRect();
    const children = [...scene.children].map(el => el.getBoundingClientRect());
    const top = Math.min(...children.map(r => r.top)) - stageRect.top;
    const bottom = Math.max(...children.map(r => r.bottom)) - stageRect.top;
    const below = stageRect.height - bottom;
    const putBelow = below >= top;
    const space = putBelow ? below : top;
    const h = Math.min(174, Math.floor(space - 24));
    if (h < 78) return;
    const w = Math.round(h * sprite.width / sprite.height);
    const t = time - sprite.start;
    const f = Math.min(sprite.count - 1, Math.floor(t * sprite.fps));
    const left = sprite.role === 'golu' ? 48 : stageRect.width - w - 48;
    const y = putBelow ? bottom + 12 : top - h - 12;
    Object.assign(canvas.style, {
      display: 'block', top: y + 'px', left: left + 'px', width: w + 'px',
      height: h + 'px', opacity: Math.min(1, t * 7, (sprite.count / sprite.fps - t) * 9),
      transform: 'translateY(' + Math.max(0, 9 - t * 40) + 'px)'
    });
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(sprite.atlas, (f % sprite.columns) * sprite.width,
      Math.floor(f / sprite.columns) * sprite.height, sprite.width, sprite.height,
      0, 0, canvas.width, canvas.height);
    if (t > .28) window.notesCharactersSeen.add(sprite.role);
  };
})();
