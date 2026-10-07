import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

export type ThemePreference = 'light' | 'dark' | 'system';
const ThemeContext = createContext<{
  preference: ThemePreference;
  setPreference: (preference: ThemePreference) => void;
} | null>(null);

function validate(value: unknown): ThemePreference {
  return value === 'light' || value === 'dark' ? value : 'system';
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() =>
    validate(document.documentElement.dataset.themePreference),
  );

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const root = document.documentElement;
    function apply() {
      root.dataset.themePreference = preference;
      root.dataset.theme = preference === 'system' ? (media.matches ? 'dark' : 'light') : preference;
      root.style.colorScheme = root.dataset.theme;
    }
    apply();
    media.addEventListener('change', apply);
    // Two frames allow the initial palette to paint before enabling transitions.
    let secondFrame = 0;
    const firstFrame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(() => { root.dataset.themeReady = ''; });
    });
    return () => {
      media.removeEventListener('change', apply);
      cancelAnimationFrame(firstFrame);
      cancelAnimationFrame(secondFrame);
    };
  }, [preference]);

  useEffect(() => {
    function sync(event: StorageEvent) {
      if (event.storageArea === localStorage && (event.key === 'mentra-theme' || event.key === null)) {
        setPreferenceState(validate(event.newValue));
      }
    }
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);

  function setPreference(next: ThemePreference) {
    setPreferenceState(next);
    try { localStorage.setItem('mentra-theme', next); } catch { /* Keep the session usable. */ }
  }

  return <ThemeContext.Provider value={{ preference, setPreference }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const theme = useContext(ThemeContext);
  if (!theme) throw new Error('useTheme requires ThemeProvider');
  return theme;
}
