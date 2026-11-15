import { API_BASE_URL } from "./config";

function entetes(extra = {}) {
  const token = localStorage.getItem("token");
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...extra };
}

async function requete(chemin, options = {}) {
  const reponse = await fetch(`${API_BASE_URL}/idp${chemin}`, { ...options, headers: entetes(options.headers || {}) });
  const data = await reponse.json().catch(() => null);
  if (!reponse.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail) ? detail.map((d) => d?.msg || "Donnée invalide.").join(" ") : detail;
    throw new Error(typeof message === "string" && message ? message : `Erreur ${reponse.status}`);
  }
  return data;
}

const json = (methode, corps) => ({
  method: methode, headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps),
});

/** Dépose un fichier (multipart : l'en-tête Content-Type est posé par le navigateur). */
export function deposerDocument(fichier) {
  const formulaire = new FormData();
  formulaire.append("fichier", fichier);
  return requete("/documents", { method: "POST", body: formulaire });
}
export const listerDocuments = (statut) => requete(`/documents${statut ? `?statut=${statut}` : ""}`);
export const detailDocument = (id) => requete(`/documents/${id}`);
export const corrigerDocument = (id, corrections) => requete(`/documents/${id}`, json("PATCH", corrections));
export const validerDocument = (id) => requete(`/documents/${id}/valider`, { method: "POST" });
export const rejeterDocument = (id, motif) => requete(`/documents/${id}/rejeter`, json("POST", { motif }));
export const champsPersonnalises = () => requete("/champs-personnalises");

export async function telechargerOriginal(id, nom) {
  const reponse = await fetch(`${API_BASE_URL}/idp/documents/${id}/fichier`, { headers: entetes() });
  if (!reponse.ok) {
    const data = await reponse.json().catch(() => ({}));
    throw new Error(data.detail || `Erreur ${reponse.status}`);
  }
  const url = URL.createObjectURL(await reponse.blob());
  const lien = document.createElement("a");
  lien.href = url;
  lien.download = nom || `document-${id}`;
  document.body.appendChild(lien);
  lien.click();
  lien.remove();
  URL.revokeObjectURL(url);
}

// ---- Intégration dans les modules (Achats) ----
export const propositionIntegration = (id) => requete(`/documents/${id}/integration`);
export const integrerDocument = (id, choix) => requete(`/documents/${id}/integrer`, json("POST", choix));
