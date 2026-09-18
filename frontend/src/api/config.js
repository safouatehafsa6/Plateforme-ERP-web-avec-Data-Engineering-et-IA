// Centralise l'URL de base de l'API pour ne jamais la répéter dans le code.
// En développement, elle pointe vers le backend local (voir docker-compose.yml).
export const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

export async function apiGet(endpoint) {
  const res = await fetch(`${API_BASE_URL}${endpoint}`);
  const data = await res.json().catch(() => null);

  // Sans cette vérification, une erreur serveur (404, 500...) était
  // silencieusement traitée comme une réponse valide : l'appelant
  // recevait un objet sans les champs attendus et n'affichait rien,
  // sans le moindre message d'erreur (cas du captcha resté vide).
  if (!res.ok) {
    const erreur = new Error(data?.message || `Erreur ${res.status} sur ${endpoint}.`);
    erreur.data = data;
    throw erreur;
  }

  return data;
}

export async function apiPost(endpoint, body) {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await res.json().catch(() => null);

  if (!res.ok) {
    // On attache la réponse complète à l'erreur : le frontend a besoin de
    // savoir si un captcha ou un reCAPTCHA est désormais exigé, pas
    // seulement qu'une erreur s'est produite.
    const erreur = new Error(data?.message || "Une erreur est survenue.");
    erreur.data = data;
    throw erreur;
  }

  return data;
}
