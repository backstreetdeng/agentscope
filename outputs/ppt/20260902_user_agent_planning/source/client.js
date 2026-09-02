// 只负责画布缩放和控件桥接；翻页、总览、讲稿、演讲者视图沿用 Skill runtime。
(() => {
  function fit() {
    const reserved = new URLSearchParams(location.search).has('preview') ? 0 : 52;
    const scale = Math.min(window.innerWidth / 1920, Math.max(1, window.innerHeight - reserved) / 1080);
    document.documentElement.style.setProperty('--control-space', reserved + 'px');
    document.documentElement.style.setProperty('--deck-scale', String(scale));
  }
  fit();
  window.addEventListener('resize', fit);
  document.querySelectorAll('[data-key]').forEach(button => {
    button.addEventListener('click', () => {
      document.dispatchEvent(new KeyboardEvent('keydown', {key: button.dataset.key, bubbles: true}));
    });
  });
  let start = null;
  document.querySelector('.deck').addEventListener('touchstart', e => {
    if(e.touches.length === 1) start = {x:e.touches[0].clientX,y:e.touches[0].clientY};
  }, {passive:true});
  document.querySelector('.deck').addEventListener('touchend', e => {
    if(!start || !e.changedTouches.length) return;
    const dx = e.changedTouches[0].clientX - start.x;
    const dy = e.changedTouches[0].clientY - start.y;
    if(Math.abs(dx)>60 && Math.abs(dx)>Math.abs(dy)*1.5) document.dispatchEvent(new KeyboardEvent('keydown',{key:dx<0?'ArrowRight':'ArrowLeft',bubbles:true}));
    start = null;
  }, {passive:true});
})();
