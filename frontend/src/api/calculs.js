// Appels API et formatage du module « Calculs ».
import { API_BASE_URL } from "./config";

export async function apiCalculs(endpoint, options = {}) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_BASE_URL}/calculs${endpoint}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    // Erreurs de validation FastAPI (422) : liste d'objets ; on affiche un message lisible.
    const message = typeof detail === "string" ? detail
      : Array.isArray(detail) ? "Données invalides : vérifiez les champs saisis." : `Erreur ${res.status}`;
    throw new Error(message);
  }
  return data;
}

// Télécharge un rapport (PDF ou Word) avec le jeton d'authentification.
export async function telechargerRapport(id, format, type = "detaille") {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_BASE_URL}/calculs/${id}/export?format=${format}&type=${type}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(typeof data?.detail === "string" ? data.detail : `Export impossible (erreur ${res.status}).`);
  }
  const blob = await res.blob();
  const nom = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "")?.[1] || `calcul.${format}`;
  const lien = document.createElement("a");
  lien.href = URL.createObjectURL(blob);
  lien.download = nom;
  document.body.appendChild(lien);
  lien.click();
  lien.remove();
  setTimeout(() => URL.revokeObjectURL(lien.href), 2000);
}

const formatMontant = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmtMontant = (v) => formatMontant.format(Number(v));
export const fmtTaux = (v) => `${new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(Number(v))} %`;
export const fmtDate = (iso) => (iso ? new Date(`${String(iso).slice(0, 10)}T00:00:00`).toLocaleDateString("fr-FR") : "");
export const fmtDateHeure = (iso) => (iso ? new Date(iso).toLocaleString("fr-FR") : "");

// Aperçu du nombre de jours (le serveur reste la référence).
export function joursPrevus(debut, fin, inclureDernierJour) {
  if (!debut || !fin) return null;
  const d = new Date(`${debut}T00:00:00`), f = new Date(`${fin}T00:00:00`);
  const jours = Math.round((f - d) / 86400000) + (inclureDernierJour ? 1 : 0);
  return jours >= 1 ? jours : null;
}

export const MODES = { taux_unique: "Taux unique", taux_variable: "Taux variables" };
