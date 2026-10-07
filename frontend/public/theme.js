// Runs before styles and React so the first frame uses the correct palette.
(() => {
  const root = document.documentElement;
  let preference = 'system';
  try {
    const saved = localStorage.getItem('mentra-theme');
    if (['light', 'dark', 'system'].includes(saved)) preference = saved;
  } catch { /* Storage may be unavailable; System still works. */ }
  root.dataset.themePreference = preference;
  root.dataset.theme = preference === 'system'
    ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : preference;
  root.style.colorScheme = root.dataset.theme;
})();
