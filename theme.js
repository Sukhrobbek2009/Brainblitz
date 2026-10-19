/* BrainBlitz light/dark theme. Loaded in <head> (before the page paints) so there is no flash.
   Uses the saved choice, else the system setting. The choice is remembered in localStorage. */
(() => {
  const KEY = 'brainblitz-theme', root = document.documentElement;
  const mq = matchMedia('(prefers-color-scheme: light)');
  const saved = () => { try { const v = localStorage.getItem(KEY); return v === 'light' || v === 'dark' ? v : null; } catch { return null; } };
  const current = () => saved() || (mq.matches ? 'light' : 'dark');
  const apply = (t) => {
    root.dataset.theme = t;
    document.querySelectorAll('[data-theme-toggle]').forEach((b) => {
      const label = t === 'light' ? 'Switch to dark mode' : 'Switch to light mode'; // the label names the action, so no aria-pressed
      b.setAttribute('aria-label', label); b.title = label;
    });
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', t === 'light' ? '#F7F4FF' : '#0E0720');
  };
  const set = (t) => { try { localStorage.setItem(KEY, t); } catch {} apply(t); window.dispatchEvent(new CustomEvent('bb-theme', { detail: t })); };
  apply(current());
  mq.addEventListener('change', () => { if (!saved()) apply(current()); });  // follows the system until the user picks
  addEventListener('storage', (e) => { if (e.key === KEY) apply(current()); }); // another tab changed it
  const wire = () => { document.querySelectorAll('[data-theme-toggle]').forEach((b) => { b.addEventListener('click', () => set(root.dataset.theme === 'light' ? 'dark' : 'light')); }); apply(current()); };
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', wire) : wire();
  window.BBTheme = { get: () => root.dataset.theme, set };
})();
