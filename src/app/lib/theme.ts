import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

const THEME_KEY = "sicurre_theme";
const THEME_EVENT = "sicurre:theme-change";

export function getStoredTheme(): Theme {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * Persist the theme and notify every mounted consumer. The sidebar toggle and
 * the Préférences select both write through here, so neither can leave the
 * other showing a stale value.
 */
export function applyTheme(theme: Theme): void {
  localStorage.setItem(THEME_KEY, theme);
  document.documentElement.classList.toggle("dark", theme === "dark");
  window.dispatchEvent(new CustomEvent<Theme>(THEME_EVENT, { detail: theme }));
}

export function useTheme(): [Theme, (theme: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(getStoredTheme);

  useEffect(() => {
    const onChange = (event: Event) => {
      const next = (event as CustomEvent<Theme>).detail;
      if (next === "light" || next === "dark") setTheme(next);
    };
    window.addEventListener(THEME_EVENT, onChange);
    return () => window.removeEventListener(THEME_EVENT, onChange);
  }, []);

  return [theme, applyTheme];
}
