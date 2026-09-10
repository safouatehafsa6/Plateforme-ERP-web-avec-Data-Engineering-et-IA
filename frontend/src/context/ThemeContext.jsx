import { createContext, useContext, useState, useEffect, useCallback } from "react";

export const THEMES = [
  { code: "clair", nom: "Clair" },
  { code: "sombre", nom: "Sombre" },
  { code: "professionnel", nom: "Pro" },
];

const ThemeContext = createContext(null);

function themeInitial() {
  const enregistre = localStorage.getItem("erp_theme");
  if (enregistre && THEMES.some((t) => t.code === enregistre)) return enregistre;
  // Respecte la préférence système si l'utilisateur n'a encore rien choisi.
  if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) return "sombre";
  return "clair";
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(themeInitial);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("erp_theme", theme);
  }, [theme]);

  const changerTheme = useCallback((code) => setTheme(code), []);

  return (
    <ThemeContext.Provider value={{ theme, changerTheme, themes: THEMES }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme doit être utilisé à l'intérieur de <ThemeProvider>");
  return ctx;
}
