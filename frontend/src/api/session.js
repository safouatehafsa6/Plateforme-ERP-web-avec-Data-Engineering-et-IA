// session.js — lecture du jeton JWT stocké après connexion.
//
// Le jeton est simplement décodé (pas vérifié) côté navigateur : c'est
// suffisant pour adapter l'affichage (quels menus montrer), jamais pour
// autoriser quoi que ce soit. Toute autorisation réelle est revérifiée
// côté backend à partir de la signature du jeton.

export function lireSession() {
  const token = localStorage.getItem("token");
  if (!token) return null;

  try {
    const charge = token.split(".")[1];
    const json = atob(charge.replace(/-/g, "+").replace(/_/g, "/"));
    const donnees = JSON.parse(decodeURIComponent(escape(json)));

    // Jeton expiré : on le considère comme absent.
    if (donnees.exp && Date.now() >= donnees.exp * 1000) {
      localStorage.removeItem("token");
      return null;
    }
    return donnees; // { id, email, role, nomBase?, entrepriseId? }
  } catch {
    return null;
  }
}

// Vrai pour un compte rattaché à une entreprise (Administrateur Client ou
// collaborateur), faux pour le Super Administrateur de la plateforme.
export function estCompteEntreprise(session) {
  return Boolean(session && session.nomBase);
}

export function estAdminEntreprise(session) {
  return Boolean(session && session.nomBase && session.role === "Admin");
}

export function estSuperAdmin(session) {
  return Boolean(session && session.role === "super_admin");
}
