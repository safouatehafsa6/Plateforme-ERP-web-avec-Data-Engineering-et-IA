import { API_BASE_URL } from "./config";

export async function ameliorerTexte(texte, mode = "correction", langue = "fr") {
  const token = localStorage.getItem("token");
  const response = await fetch(`${API_BASE_URL}/assistant/reformuler`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ texte, mode, langue }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Erreur ${response.status}`);
  return data.texte || texte;
}
