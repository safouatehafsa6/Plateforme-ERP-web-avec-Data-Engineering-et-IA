import { API_BASE_URL } from "./config";

/** Appel authentifié ; l'erreur lancée porte `status` et `data` (utile pour les 409 « doublon »). */
export async function api(endpoint, options = {}) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item?.msg || "Donnée invalide.").join(" ")
      : detail || data?.message || `Erreur ${res.status}`;
    const erreur = new Error(typeof message === "string" ? message : `Erreur ${res.status}`);
    erreur.status = res.status;
    erreur.data = data;
    throw erreur;
  }
  return data;
}
