// Stockage en mémoire (suffisant pour un seul serveur / une démo de stage ;
// en production, on utiliserait Redis pour partager l'état entre plusieurs
// instances du backend).

const DUREE_VALIDITE_CAPTCHA_MS = 5 * 60 * 1000; // 5 minutes
const FENETRE_BLOCAGE_MS = 15 * 60 * 1000; // 15 minutes
const SEUIL_PROTECTION = 2; // conforme à la demande : dès 2 échecs consécutifs

const captchasActifs = new Map(); // id -> { code, expiration }
const tentativesParEmail = new Map(); // email -> { echecs, derniereTentative }

export function enregistrerCaptcha(id, code) {
  captchasActifs.set(id, { code, expiration: Date.now() + DUREE_VALIDITE_CAPTCHA_MS });
}

export function verifierEtConsommerCaptcha(id, valeurSaisie) {
  const entree = captchasActifs.get(id);
  captchasActifs.delete(id); // usage unique, qu'il soit correct ou non

  if (!entree) return false; // expiré, déjà utilisé, ou inexistant
  if (Date.now() > entree.expiration) return false;

  return entree.code.toUpperCase() === String(valeurSaisie || "").toUpperCase();
}

export function etatProtection(email) {
  const entree = tentativesParEmail.get(email);
  if (!entree) return { echecs: 0, protectionActive: false };

  // Réinitialise la fenêtre si le dernier échec date de plus de 15 minutes.
  if (Date.now() - entree.derniereTentative > FENETRE_BLOCAGE_MS) {
    tentativesParEmail.delete(email);
    return { echecs: 0, protectionActive: false };
  }

  return { echecs: entree.echecs, protectionActive: entree.echecs >= SEUIL_PROTECTION };
}

export function enregistrerEchec(email) {
  const actuel = tentativesParEmail.get(email) || { echecs: 0 };
  tentativesParEmail.set(email, { echecs: actuel.echecs + 1, derniereTentative: Date.now() });
}

export function reinitialiserTentatives(email) {
  tentativesParEmail.delete(email);
}
