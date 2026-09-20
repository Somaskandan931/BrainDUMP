"use client";

import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";

export type Theme = "dark" | "light";

const STORAGE_KEY = "bd-theme";

interface ThemeContextValue {
  theme: Theme;
  /** Set the theme locally (instant, persisted to localStorage). Doesn't
   * touch the backend — callers that also want it remembered in Settings
   * (the toggle on /settings) should call settingsApi.update separately. */
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function applyThemeClass(theme: Theme) {
  document.documentElement.classList.toggle("light", theme === "light");
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Matches the inline script in app/layout.tsx, which already set the
  // class before first paint — this just brings React state in sync so
  // components (the Settings toggle) can read/set it.
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    setThemeState(stored === "light" ? "light" : "dark");
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    window.localStorage.setItem(STORAGE_KEY, next);
    applyThemeClass(next);
  }, []);

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

/** Inlined into app/layout.tsx <head> as a blocking script (not imported
 * as a module) so the right theme class is on <html> before first paint —
 * otherwise a dark-preferring user sees a flash of the light theme (or
 * vice versa) on every load. Keep this in sync with STORAGE_KEY above. */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem('${STORAGE_KEY}');if(t==='light')document.documentElement.classList.add('light');}catch(e){}})();`;
