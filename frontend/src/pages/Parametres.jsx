import { useState } from "react";
import { Settings, Palette, Languages, ToggleLeft, ToggleRight } from "lucide-react";
import { useTheme } from "../context/ThemeContext";
import { useLangue } from "../context/LangueContext";

const FEATURES = [
  ["ventes", "Ventes"],
  ["achats", "Achats"],
  ["fournisseurs", "Fournisseurs"],
  ["clients", "Clients"],
  ["stock", "Stock"],
  ["facturation", "Facturation"],
  ["comptabilite", "Comptabilité"],
];

function readFeatures() {
  try {
    const saved = JSON.parse(localStorage.getItem("erp_features") || "null");
    return Object.fromEntries(FEATURES.map(([k]) => [k, saved?.[k] !== false]));
  } catch {
    return Object.fromEntries(FEATURES.map(([k]) => [k, true]));
  }
}

export default function Parametres() {
  const { theme, changerTheme, themes } = useTheme();
  const { langueActuelle, changerLangue, langues } = useLangue();
  const [features, setFeatures] = useState(readFeatures);

  function toggleFeature(key) {
    const next = { ...features, [key]: !features[key] };
    setFeatures(next);
    localStorage.setItem("erp_features", JSON.stringify(next));
  }

  return (
    <main className="page-shell parametres-page">
      <div className="page-head">
        <div>
          <h1><Settings size={24} /> Paramètres</h1>
          <p>Configuration de l’interface et activation des fonctionnalités de la plateforme.</p>
        </div>
      </div>

      <section className="panel parametres-section">
        <div className="parametres-section__title"><Palette size={20} /><h2>Apparence</h2></div>
        <div className="parametres-grid">
          <label>Thème
            <select value={theme} onChange={(e) => changerTheme(e.target.value)}>
              {themes.map((t) => <option key={t.code} value={t.code}>{t.nom}</option>)}
            </select>
          </label>
        </div>
      </section>

      <section className="panel parametres-section">
        <div className="parametres-section__title"><Languages size={20} /><h2>Langue</h2></div>
        <div className="parametres-grid">
          <label>Langue de l’interface
            <select value={langueActuelle.code} onChange={(e) => changerLangue(e.target.value)}>
              {langues.map((l) => <option key={l.code} value={l.code}>{l.nom}</option>)}
            </select>
          </label>
        </div>
      </section>

      <section className="panel parametres-section">
        <div className="parametres-section__title"><Settings size={20} /><h2>Fonctionnalités</h2></div>
        <p className="parametres-muted">Activez ou désactivez l’affichage des modules dans la navigation.</p>
        <div className="parametres-features">
          {FEATURES.map(([key, label]) => (
            <button type="button" className="parametres-feature" key={key} onClick={() => toggleFeature(key)}>
              <span>{label}</span>
              {features[key] ? <ToggleRight size={28} /> : <ToggleLeft size={28} />}
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}
