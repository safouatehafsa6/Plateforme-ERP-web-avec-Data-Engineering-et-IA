import { createContext, useContext, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { LANGUES } from "../i18n";

const LangueContext = createContext(null);

export function LangueProvider({ children }) {
  const { i18n } = useTranslation();
  const [langueActuelle, setLangueActuelle] = useState(
    LANGUES.find((l) => l.code === i18n.language) || LANGUES[0]
  );

  const changerLangue = useCallback((code) => {
    const langue = LANGUES.find((l) => l.code === code);
    if (!langue) return;

    i18n.changeLanguage(code);
    document.documentElement.dir = langue.dir;
    document.documentElement.lang = code;
    setLangueActuelle(langue);
  }, [i18n]);

  return (
    <LangueContext.Provider value={{ langueActuelle, changerLangue, langues: LANGUES }}>
      {children}
    </LangueContext.Provider>
  );
}

// Hook pratique : n'importe quelle page ou composant peut faire
// const { langueActuelle, changerLangue } = useLangue();
export function useLangue() {
  const ctx = useContext(LangueContext);
  if (!ctx) throw new Error("useLangue doit être utilisé à l'intérieur de <LangueProvider>");
  return ctx;
}
