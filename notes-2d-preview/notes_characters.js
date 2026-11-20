// Add the pair in free space while keeping the Notes cards readable.
(() => {
  const stage = document.getElementById('st');
  const sprites = D.characters ?? [];
  const actors = ['golu', 'postman'].map(role => {
    const canvas = document.createElement('canvas');
    canvas.width = 210;
    canvas.height = 322;
    canvas.style.cssText = 'display:none;position:absolute;z-index:2;pointer-events:none';
    stage.appendChild(canvas);
    return {role, canvas, context: canvas.getContext('2d')};
  });
  window.notesCharactersSeen = new Set();
  window.loadNotesCharacters = () => Promise.all(sprites.map(async sprite => {
    sprite.atlas = new Image();
    sprite.atlas.src = sprite.image;
    sprite.still = new Image();
    sprite.still.src = sprite.listener;
    await Promise.all([sprite.atlas.decode(), sprite.still.decode()]);
    stage.querySelector('[data-segment="' + sprite.segment + '"]').style.paddingBottom = '72px';
  }));
  window.drawNotesCharacter = time => {
    actors.forEach(({canvas}) => canvas.style.display = 'none');
    const sprite = sprites.find(s => time >= s.start && time < s.start + s.count / s.fps);
    if (!sprite) return;
    const scene = stage.querySelector('[data-segment="' + sprite.segment + '"]');
    if (!scene || Number(getComputedStyle(scene).opacity) < .97) return;
    const stageRect = stage.getBoundingClientRect();
    const bottom = Math.max(...[...scene.children].map(el => el.getBoundingClientRect().bottom)) - stageRect.top;
    const h = Math.min(211, Math.floor(898 - stageRect.top - bottom - 20));
    if (h < 83) return;
    const t = time - sprite.start;
    const frame = Math.min(sprite.count - 1, Math.floor(t * sprite.fps));
    for (const {role, canvas, context} of actors) {
      const speaking = role === sprite.role;
      const height = Math.round(h * (speaking ? 1 : .83));
      const width = Math.round(height * sprite.width / sprite.height);
      const left = role === 'golu' ? 88 : stageRect.width - width - 88;
      const floor = bottom + h + 10 - (speaking ? 0 : Math.sin(t * 4) * 2);
      Object.assign(canvas.style, {
        display: 'block', top: (floor - height) + 'px', left: left + 'px',
        width: width + 'px', height: height + 'px',
        opacity: Math.min(1, t * 7, (sprite.count / sprite.fps - t) * 9),
      });
      context.clearRect(0, 0, canvas.width, canvas.height);
      if (speaking) {
        context.drawImage(sprite.atlas, (frame % sprite.columns) * sprite.width,
          Math.floor(frame / sprite.columns) * sprite.height, sprite.width, sprite.height,
          0, 0, canvas.width, canvas.height);
        if (t > .28) window.notesCharactersSeen.add(role);
      } else {
        context.drawImage(sprite.still, 0, 0, canvas.width, canvas.height);
      }
    }
  };
})();
