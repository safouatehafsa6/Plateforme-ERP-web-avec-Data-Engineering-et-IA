
// Centralise l'URL de base de l'API pour ne jamais la répéter dans le code.
// L'API est accessible depuis Windows et Rocky Linux via l'adresse IP de la VM.
// Par defaut, l'API est jointe sur la MEME machine que celle qui sert la page
// (window.location.hostname) : "localhost" en local, l'IP de la VM sinon.
// "http://localhost:8000" en dur pointait vers le PC Windows, pas vers la VM.
export const API_BASE_URL =
  import.meta.env.VITE_API_URL ||
  `${window.location.protocol}//${window.location.hostname}:8000/api`;

// Identifiant aleatoire de CE navigateur, cree une fois et conserve. Il est
// envoye a la connexion (en-tete X-Appareil-Id) pour reconnaitre l'appareil ;
// le serveur n'en garde que l'empreinte.
export function identifiantAppareil() {
  try {
    let id = localStorage.getItem("appareil_id");
    if (!id) {
      if (window.crypto && window.crypto.randomUUID) {
        id = window.crypto.randomUUID();
      } else {
        const octets = new Uint8Array(16);
        window.crypto.getRandomValues(octets);
        id = Array.from(octets, (o) => o.toString(16).padStart(2, "0")).join("");
      }
      localStorage.setItem("appareil_id", id);
    }
    return id;
  } catch {
    return "";
  }
}

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

export async function apiPost(endpoint, body, entetes = {}) {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Appareil-Id": identifiantAppareil(), ...entetes },
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
