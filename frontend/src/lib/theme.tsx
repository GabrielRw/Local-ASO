import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

// Light/dark follows the system by default. Implemented here (not next-themes)
// because the dashboard CSP forbids inline scripts.

export type ThemePreference = "system" | "light" | "dark";
const STORAGE_KEY = "local-aso-theme";

interface ThemeState {
  theme: ThemePreference;
  resolvedTheme: "light" | "dark";
  setTheme: (value: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeState | null>(null);

function readPreference(): ThemePreference {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

function systemTheme(): "light" | "dark" {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemePreference>(readPreference);
  const [system, setSystem] = useState<"light" | "dark">(systemTheme);

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setSystem(query.matches ? "dark" : "light");
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  const resolvedTheme = theme === "system" ? system : theme;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolvedTheme === "dark");
    document.documentElement.style.colorScheme = resolvedTheme;
  }, [resolvedTheme]);

  const value = useMemo<ThemeState>(
    () => ({
      theme,
      resolvedTheme,
      setTheme: (next) => {
        setThemeState(next);
        try {
          window.localStorage.setItem(STORAGE_KEY, next);
        } catch {
          // Storage can be unavailable; the preference then lasts for this session.
        }
      },
    }),
    [theme, resolvedTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside ThemeProvider");
  return value;
}
