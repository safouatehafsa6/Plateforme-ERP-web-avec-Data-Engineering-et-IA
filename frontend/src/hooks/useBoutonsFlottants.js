import { useEffect, useState } from "react";
import { API_BASE_URL } from "../api/config";
import { CONFIG_PAR_DEFAUT } from "../validation/boutonsFlottants";

const CLE_CACHE = "erp:boutons-flottants:v1";
const INTERVALLE_MS = 60_000;

function lireCache() {
  try {
    const brut = JSON.parse(sessionStorage.getItem(CLE_CACHE) || "null");
    return brut && Array.isArray(brut.boutons) && brut.config ? brut : null;
  } catch { return null; }
}

/** Configuration des boutons flottants définie par l'administrateur.
 *  Premier affichage : dernière configuration connue (ou celle d'origine) — jamais d'écran vide ni de clignotement.
 *  Actualisation : au chargement, toutes les minutes, au retour sur l'onglet, et immédiatement après une
 *  modification dans l'administration (événement « erp:boutons-refresh »). */
export default function useBoutonsFlottants() {
  const [donnees, setDonnees] = useState(() => lireCache() || CONFIG_PAR_DEFAUT);

  useEffect(() => {
    let actif = true;
    let controleur = null;

    async function charger() {
      controleur?.abort();
      controleur = new AbortController();
      try {
        const res = await fetch(`${API_BASE_URL}/boutons-flottants`, { signal: controleur.signal });
        if (!res.ok) return;                       // on garde la dernière configuration valide
        const json = await res.json();
        if (!actif || !json?.config || !Array.isArray(json.boutons)) return;
        try { sessionStorage.setItem(CLE_CACHE, JSON.stringify(json)); } catch { /* stockage indisponible */ }
        setDonnees((ancien) => (ancien.version === json.version && ancien.boutons.length === json.boutons.length ? ancien : json));
      } catch { /* réseau indisponible : configuration conservée */ }
    }

    const auRetour = () => { if (document.visibilityState === "visible") charger(); };
    charger();
    const minuteur = window.setInterval(auRetour, INTERVALLE_MS);
    window.addEventListener("erp:boutons-refresh", charger);
    document.addEventListener("visibilitychange", auRetour);
    return () => {
      actif = false;
      controleur?.abort();
      window.clearInterval(minuteur);
      window.removeEventListener("erp:boutons-refresh", charger);
      document.removeEventListener("visibilitychange", auRetour);
    };
  }, []);

  return donnees;
}
