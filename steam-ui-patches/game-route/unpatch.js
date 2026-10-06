// Unpatch game-route chooser.
(() => {
  try { window.__ftGameRoute?.dispose?.(); } catch {}
  return 'unpatched';
})()
