import { useEffect, useId, useRef, useState } from "react";
import { API_BASE_URL } from "../api/config";

const TYPES = {
  fr: { client: "client", fournisseur: "fournisseur", produit: "produit", terme: "terme" },
  en: { client: "customer", fournisseur: "supplier", produit: "product", terme: "term" },
  ar: { client: "زبون", fournisseur: "مورد", produit: "منتج", terme: "مصطلح" },
};

// Champ de saisie avec suggestions pendant la frappe (mots, expressions, termes métier,
// noms réels de clients / fournisseurs / produits). Le serveur filtre selon les permissions.
// Clavier : ↑ ↓ pour choisir, Tab ou Entrée pour accepter, Échap pour fermer.
// Sans suggestion active, Entrée garde son comportement normal (envoi du formulaire).
export default function ChampSuggestions({ value, onChange, placeholder, ariaLabel, langue = "fr", module }) {
  const idListe = useId();
  const [items, setItems] = useState([]);
  const [actif, setActif] = useState(-1);
  const [ouvert, setOuvert] = useState(false);
  const [debutAccepte, setDebutAccepte] = useState(null);
  const controleur = useRef(null);

  useEffect(() => {
    if (!value || value.trim().length < 2 || /\s$/.test(value) || value === debutAccepte) {
      setItems([]);
      return undefined;
    }
    const minuteur = setTimeout(async () => {
      controleur.current?.abort();
      controleur.current = new AbortController();
      try {
        const params = new URLSearchParams({ q: value, langue });
        if (module) params.set("module", module);
        const res = await fetch(`${API_BASE_URL}/suggestions?${params}`, {
          headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
          signal: controleur.current.signal,
        });
        if (!res.ok) { setItems([]); return; }
        const data = await res.json();
        setItems(Array.isArray(data.suggestions) ? data.suggestions : []);
        setActif(-1);
      } catch {
        // Les suggestions sont un confort : en cas d'erreur ou d'annulation, on n'affiche rien.
      }
    }, 150);
    return () => clearTimeout(minuteur);
  }, [value, langue, module]);

  useEffect(() => () => controleur.current?.abort(), []);

  function accepter(item) {
    const fin = value.lastIndexOf(item.remplace);
    const base = fin >= 0 ? value.slice(0, fin) : value;
    const nouveau = `${base}${item.texte} `;
    setDebutAccepte(nouveau);
    onChange(nouveau);
    setItems([]);
    setOuvert(false);
  }

  function touche(e) {
    const visible = ouvert && items.length > 0;
    if (!visible) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActif((i) => (i + 1) % items.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActif((i) => (i <= 0 ? items.length - 1 : i - 1)); }
    else if (e.key === "Escape") { setOuvert(false); }
    else if (e.key === "Tab" || (e.key === "Enter" && actif >= 0)) {
      const choisi = items[actif >= 0 ? actif : 0];
      if (e.key === "Enter" || choisi) { e.preventDefault(); accepter(choisi); }
    }
  }

  const visible = ouvert && items.length > 0;
  const libelles = TYPES[langue] || TYPES.fr;
  return (
    <div className="champ-suggestions">
      <input
        value={value}
        onChange={(e) => { onChange(e.target.value); setOuvert(true); }}
        onKeyDown={touche}
        onFocus={() => setOuvert(true)}
        onBlur={() => setOuvert(false)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        role="combobox"
        aria-expanded={visible}
        aria-controls={idListe}
        aria-autocomplete="list"
        aria-activedescendant={visible && actif >= 0 ? `${idListe}-${actif}` : undefined}
        autoComplete="off"
      />
      {visible && (
        <ul className="champ-suggestions__liste" role="listbox" id={idListe}>
          {items.map((item, i) => (
            <li
              key={`${item.type}-${item.texte}`}
              id={`${idListe}-${i}`}
              role="option"
              aria-selected={i === actif}
              className={i === actif ? "champ-suggestions__option champ-suggestions__option--active" : "champ-suggestions__option"}
              onMouseDown={(e) => { e.preventDefault(); accepter(item); }}
            >
              <span className="champ-suggestions__texte">{item.texte}</span>
              <span className="champ-suggestions__meta">
                {libelles[item.type] || item.type}{item.detail ? ` · ${item.detail}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
