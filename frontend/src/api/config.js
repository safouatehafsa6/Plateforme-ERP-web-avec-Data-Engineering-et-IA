// Centralise l'URL de base de l'API pour ne jamais la répéter dans le code.
// En développement, elle pointe vers le backend local (voir docker-compose.yml).
export const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

export async function apiPost(endpoint, body) {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await res.json().catch(() => null);

  if (!res.ok) {
    throw new Error(data?.message || "Une erreur est survenue.");
  }

  return data;
}
