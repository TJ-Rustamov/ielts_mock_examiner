import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

type StudyMode = 'writing' | 'speaking';
type Theme = 'light' | 'dark';

interface ThemeContextType {
  studyMode: StudyMode;
  setStudyMode: (mode: StudyMode) => void;
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | null>(null);

export const useThemeContext = () => {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useThemeContext must be used within ThemeProvider');
  return ctx;
};

export const ThemeProvider = ({ children }: { children: ReactNode }) => {
  const [studyMode, setStudyMode] = useState<StudyMode>('writing');
  const [theme, setTheme] = useState<Theme>('light');

  useEffect(() => {
    const root = document.documentElement;
    if (studyMode === 'speaking') {
      root.classList.add('speaking');
    } else {
      root.classList.remove('speaking');
    }
  }, [studyMode]);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [theme]);

  const toggleTheme = () => setTheme(t => t === 'light' ? 'dark' : 'light');

  return (
    <ThemeContext.Provider value={{ studyMode, setStudyMode, theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};
