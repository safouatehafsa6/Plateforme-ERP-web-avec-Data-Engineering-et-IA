// sessionsApi.js — appels authentifiés liés aux sessions / appareils.
import { API_BASE_URL } from "./config";

async function appelAuth(methode, endpoint) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: methode,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  const data = await res.json().catch(() => null);

  if (!res.ok) {
    // 401 = session fermée, expirée ou jeton invalide : le jeton local
    // ne sert plus à rien.
    if (res.status === 401) localStorage.removeItem("token");
    const erreur = new Error(data?.detail || data?.message || `Erreur ${res.status}.`);
    erreur.status = res.status;
    throw erreur;
  }
  return data;
}

export const listerMesSessions = () => appelAuth("GET", "/sessions");
export const fermerMaSession = (id) => appelAuth("DELETE", `/sessions/${id}`);
export const fermerLesAutresSessions = () => appelAuth("POST", "/sessions/autres/revoquer");

export const listerSessionsEntreprise = () => appelAuth("GET", "/admin/sessions");
export const fermerSessionEntreprise = (id) => appelAuth("DELETE", `/admin/sessions/${id}`);
export const fermerSessionsUtilisateur = (id, typeCompte) =>
  appelAuth("DELETE", `/admin/sessions/utilisateur/${id}?type_compte=${typeCompte}`);

// Déconnexion réelle : on invalide la session côté serveur, puis on
// supprime le jeton local même si l'appel échoue (réseau coupé, etc.).
export async function deconnecter() {
  try {
    await appelAuth("POST", "/sessions/deconnexion");
  } catch {
    /* ignoré : le jeton local est supprimé dans tous les cas */
  } finally {
    localStorage.removeItem("token");
  }
}

// Journal de securite (phase A)
export const listerMesEvenements = (limite = 20) => appelAuth("GET", `/sessions/evenements?limit=${limite}`);
export const listerEvenementsEntreprise = (limite = 30) => appelAuth("GET", `/admin/sessions/evenements?limit=${limite}`);
