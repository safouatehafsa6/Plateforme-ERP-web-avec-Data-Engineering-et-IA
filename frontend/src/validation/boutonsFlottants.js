// Logique PURE des boutons flottants (sans React) : valeurs par défaut, visibilité, validation du formulaire.
// Les règles de validation reproduisent celles de l'API (app/services/boutons_flottants.py) pour guider la saisie ;
// l'API reste l'autorité et revalide tout.

export const ICONES = [
  "bell", "bot", "headset", "message-circle", "log-in", "user-plus", "moon", "globe", "phone", "mail",
  "help-circle", "info", "star", "heart", "shopping-cart", "file-text", "calculator", "video", "users",
  "settings", "calendar", "zap", "gift", "megaphone", "book-open", "life-buoy", "link", "external-link",
  "home", "search", "sparkles", "credit-card", "shield-check", "bookmark",
];
export const ACTIONS = {
  assistant: "Ouvrir l'assistant IA",
  notifications: "Afficher les notifications",
  support: "Assistance / Contact",
  theme: "Basculer le thème clair/sombre",
  langue: "Choisir la langue",
  route: "Ouvrir une page de la plateforme",
  url: "Ouvrir un lien externe (https, mailto, tel)",
  whatsapp: "Ouvrir WhatsApp",
};
export const ACTIONS_INTEGREES = ["assistant", "notifications", "support", "theme", "langue"];
export const POSITIONS = {
  "haut-gauche": "Haut gauche", "haut-droite": "Haut droite",
  "milieu-gauche": "Milieu gauche", "milieu-droite": "Milieu droite",
  "bas-gauche": "Bas gauche", "bas-droite": "Bas droite",
};
export const POSITIONS_PRINCIPAL = { auto: "Automatique (bas, côté de la langue)", ...POSITIONS };
export const TAILLES = { petit: "Petit", moyen: "Moyen", grand: "Grand" };
export const TAILLES_PX = { petit: 46, moyen: 58, grand: 72 };
export const AUDIENCES = { tous: "Tout le monde", public: "Visiteurs non connectés", connecte: "Utilisateurs connectés" };
export const PROFILS = {
  plateforme: "Super administrateur", admin_entreprise: "Administrateur d'entreprise", interne: "Collaborateur interne", externe: "Utilisateur externe",
};
export const APPAREILS = { tous: "Tous les appareils", mobile: "Mobile / tablette", ordinateur: "Ordinateur" };
export const LANGUES = { fr: "Français", en: "English", ar: "العربية" };
export const PAGES_CONNUES = [
  ["/dashboard", "Tableau de bord"], ["/ventes", "Ventes"], ["/achats", "Achats"], ["/stock", "Stock"], ["/prospects", "Prospects"],
  ["/clients", "Clients"], ["/facturation", "Facturation"], ["/comptabilite", "Comptabilité"], ["/calculs", "Calculs"],
  ["/room-live", "Room Live"], ["/support", "Support"], ["/contact", "Contact"], ["/tarifs", "Tarifs"], ["/fonctionnalites", "Fonctionnalités"],
  ["/inscription", "Inscription"], ["/", "Connexion"],
];

const t = (fr, en, ar) => ({ fr, en, ar });
const bouton = (id, o) => ({
  id, couleur: null, taille: "moyen", placement: "menu", position: null, actif: true, cible: null, nouvel_onglet: false,
  audience: "tous", profils: [], appareils: "tous", routes_incluses: [], routes_exclues: [], affiche_du: null, affiche_jusqu_au: null,
  systeme: true, ...o,
});

// Réplique du menu d'aide d'origine (identique aux boutons « système » de l'API) : utilisée tant que l'API
// n'a pas répondu ou si elle est injoignable, pour que l'aide ne disparaisse jamais.
export const CONFIG_PAR_DEFAUT = {
  config: { actif: true, position: "auto", taille: "moyen", couleur: null, icone: "headset", version: 0 },
  boutons: [
    bouton(-1, { cle: "notifications", titres: t("Notifications", "Notifications", "الإشعارات"), icone: "bell", action: "notifications", audience: "connecte", ordre: 10 }),
    bouton(-2, { cle: "assistant", titres: t("Assistant IA", "AI Assistant", "مساعد الذكاء الاصطناعي"), icone: "bot", action: "assistant", audience: "connecte", ordre: 20 }),
    bouton(-3, { cle: "support", titres: t("Assistance / Contact", "Support / Contact", "الدعم / التواصل"), icone: "headset", action: "support", ordre: 30 }),
    bouton(-4, { cle: "whatsapp", titres: t("WhatsApp", "WhatsApp", "واتساب"), icone: "message-circle", action: "whatsapp", ordre: 40, nouvel_onglet: true }),
    bouton(-5, { cle: "connexion", titres: t("Connexion", "Sign in", "تسجيل الدخول"), icone: "log-in", action: "route", cible: "/", audience: "public", ordre: 50 }),
    bouton(-6, { cle: "inscription", titres: t("Créer un compte", "Create account", "إنشاء حساب"), icone: "user-plus", action: "route", cible: "/inscription", audience: "public", ordre: 60 }),
    bouton(-7, { cle: "theme", titres: t("Mode sombre / clair", "Dark / light mode", "الوضع الداكن / الفاتح"), icone: "moon", action: "theme", ordre: 90 }),
    bouton(-8, { cle: "langue", titres: t("Langue", "Language", "اللغة"), icone: "globe", action: "langue", ordre: 100 }),
  ],
  version: 0,
};

// --------------------------------------------------------------------------- affichage
/** Profils d'une session : un même compte peut en cumuler plusieurs (ex. interne + admin_entreprise). */
export function profilsSession(session) {
  if (!session) return [];
  if (session.role === "super_admin" || session.type === "plateforme") return ["plateforme"];
  if (session.type === "externe") return ["externe"];
  if (session.nomBase) return session.role === "Admin" ? ["interne", "admin_entreprise"] : ["interne"];
  return [];
}

/** « /clients » correspond à /clients et /clients/12, pas à /clientele ; « / » ne correspond qu'à l'accueil. */
export function correspondRoute(chemin, prefixe) {
  if (!prefixe) return false;
  if (prefixe === "/") return chemin === "/";
  return chemin === prefixe || chemin.startsWith(`${prefixe}/`);
}

export function titreBouton(bouton, langue) {
  const titres = bouton.titres || {};
  return titres[langue] || titres.fr || bouton.cle || "";
}

/** contexte : { session, pathname, mobile, maintenant, numeroWhatsapp } */
export function boutonVisible(b, { session = null, pathname = "/", mobile = false, maintenant = new Date(), numeroWhatsapp = "" } = {}) {
  if (!b || b.actif === false) return false;
  if (b.affiche_du && new Date(b.affiche_du) > maintenant) return false;
  if (b.affiche_jusqu_au && new Date(b.affiche_jusqu_au) <= maintenant) return false;
  if (b.audience === "public" && session) return false;
  if (b.audience === "connecte" && !session) return false;
  if ((b.action === "notifications" || b.action === "assistant") && !session) return false;
  if (b.profils?.length && !b.profils.some((p) => profilsSession(session).includes(p))) return false;
  if (b.appareils === "mobile" && !mobile) return false;
  if (b.appareils === "ordinateur" && mobile) return false;
  if (b.routes_incluses?.length && !b.routes_incluses.some((p) => correspondRoute(pathname, p))) return false;
  if (b.routes_exclues?.some((p) => correspondRoute(pathname, p))) return false;
  if (b.action === "whatsapp" && !String(b.cible || numeroWhatsapp || "").replace(/\D/g, "")) return false;
  return true;
}

export function trierBoutons(boutons) {
  return [...boutons].sort((a, b) => (a.ordre - b.ordre) || (a.id - b.id));
}

/** Position effective du bouton principal (« auto » : en bas, côté fin de la langue). */
export function positionEffective(position, rtl) {
  return position && position !== "auto" ? position : (rtl ? "bas-gauche" : "bas-droite");
}

// --------------------------------------------------------------------------- formulaire d'administration
const RE_ROUTE = /^\/[A-Za-z0-9_\-/.]*(\?[A-Za-z0-9_\-=&%.]*)?(#[A-Za-z0-9_-]*)?$/;
const RE_PREFIXE = /^\/[A-Za-z0-9_\-/]*$/;
const RE_URL = /^(https:\/\/[^\s/$.?#][^\s]*|mailto:[^\s@]+@[^\s@]+\.[^\s@]{2,}|tel:\+?[0-9]{6,15})$/i;

export function erreurCible(action, cible, nouvelOnglet = false) {
  const c = String(cible ?? "").trim();
  if (ACTIONS_INTEGREES.includes(action)) return c ? "Cette action intégrée n'accepte aucune cible." : "";
  if (action === "route") {
    if (!c) return "Indiquez la page interne (ex. /clients).";
    if (c.length > 200 || c.startsWith("//") || c.includes("..") || !RE_ROUTE.test(c)) return "Chemin interne invalide : il doit commencer par « / ».";
    return nouvelOnglet ? "Le nouvel onglet ne concerne que les liens externes." : "";
  }
  if (action === "url") {
    if (!c) return "Indiquez l'adresse du lien.";
    return c.length > 500 || !RE_URL.test(c) ? "Lien invalide : seuls https://, mailto: et tel: sont acceptés." : "";
  }
  if (action === "whatsapp") {
    if (!c) return "";
    return /^[0-9]{6,15}$/.test(c.replace(/[\s+().-]/g, "")) ? "" : "Numéro WhatsApp invalide (6 à 15 chiffres, indicatif inclus).";
  }
  return "Action inconnue.";
}

export function listeDepuisTexte(texte) {
  return [...new Set(String(texte ?? "").split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean))];
}

export function validerBouton(f = {}) {
  const e = {};
  const fr = String(f.titres?.fr ?? "").trim();
  if (!fr) e.titre = "Le titre en français est obligatoire.";
  for (const [lang, texte] of Object.entries(f.titres || {})) {
    if (String(texte ?? "").trim().length > 40) e.titre = "Un titre ne peut pas dépasser 40 caractères.";
    if (!LANGUES[lang]) e.titre = `Langue inconnue « ${lang} ».`;
  }
  if (!ICONES.includes(f.icone)) e.icone = "Choisissez une icône.";
  if (f.couleur && !/^#[0-9a-fA-F]{6}$/.test(f.couleur)) e.couleur = "Couleur invalide (#RRGGBB).";
  const cible = erreurCible(f.action, f.cible, f.nouvel_onglet);
  if (!ACTIONS[f.action]) e.action = "Choisissez une action.";
  else if (cible) e.cible = cible;
  if (f.placement === "libre" && !POSITIONS[f.position]) e.position = "Choisissez la position du bouton libre.";
  const ordre = Number(f.ordre);
  if (!Number.isInteger(ordre) || ordre < 0 || ordre > 9999) e.ordre = "Ordre : entier de 0 à 9999.";
  if (f.audience === "public" && f.profils?.length) e.profils = "Un bouton pour visiteurs ne peut pas cibler un profil connecté.";
  if ((f.action === "notifications" || f.action === "assistant") && f.audience === "public") e.audience = "Cette action nécessite un utilisateur connecté.";
  for (const [champ, liste] of [["routes_incluses", f.routes_incluses], ["routes_exclues", f.routes_exclues]]) {
    if ((liste || []).length > 20) e[champ] = "20 pages maximum.";
    else if ((liste || []).some((p) => p.length > 100 || !RE_PREFIXE.test(p) || p.includes(".."))) e[champ] = "Utilisez des préfixes comme /clients.";
  }
  if (f.affiche_du && f.affiche_jusqu_au && new Date(f.affiche_jusqu_au) <= new Date(f.affiche_du)) e.dates = "La date de fin doit suivre la date de début.";
  return e;
}

export function boutonVide() {
  return {
    cle: "", titres: { fr: "", en: "", ar: "" }, icone: "star", couleur: "", taille: "moyen", placement: "menu", position: "",
    ordre: 200, actif: true, action: "route", cible: "", nouvel_onglet: false, audience: "tous", profils: [], appareils: "tous",
    routes_incluses: [], routes_exclues: [], affiche_du: "", affiche_jusqu_au: "",
  };
}

const versLocal = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};

/** Bouton de l'API → valeurs du formulaire. */
export function formDepuisBouton(b) {
  return {
    ...boutonVide(), ...b, titres: { fr: "", en: "", ar: "", ...(b.titres || {}) }, couleur: b.couleur || "", position: b.position || "",
    cible: b.cible || "", affiche_du: versLocal(b.affiche_du), affiche_jusqu_au: versLocal(b.affiche_jusqu_au),
  };
}

/** Valeurs du formulaire → corps attendu par l'API (champs vides = null, dates en ISO UTC). */
export function payloadDepuisForm(f) {
  const iso = (v) => (v ? new Date(v).toISOString() : null);
  const titres = Object.fromEntries(Object.entries(f.titres || {}).map(([k, v]) => [k, String(v ?? "").trim()]).filter(([, v]) => v));
  return {
    ...(f.cle ? { cle: f.cle } : {}), titres, icone: f.icone, couleur: f.couleur || null, taille: f.taille, placement: f.placement,
    position: f.placement === "libre" ? f.position || null : null, ordre: Number(f.ordre), actif: Boolean(f.actif), action: f.action,
    cible: String(f.cible ?? "").trim() || null, nouvel_onglet: Boolean(f.nouvel_onglet), audience: f.audience, profils: f.profils || [],
    appareils: f.appareils, routes_incluses: f.routes_incluses || [], routes_exclues: f.routes_exclues || [],
    affiche_du: iso(f.affiche_du), affiche_jusqu_au: iso(f.affiche_jusqu_au),
  };
}

/** Résumé lisible de la visibilité d'un bouton (liste d'administration). */
export function resumeVisibilite(b) {
  const morceaux = [AUDIENCES[b.audience] || b.audience];
  if (b.profils?.length) morceaux.push(b.profils.map((p) => PROFILS[p] || p).join(", "));
  if (b.appareils && b.appareils !== "tous") morceaux.push(APPAREILS[b.appareils]);
  if (b.routes_incluses?.length) morceaux.push(`pages : ${b.routes_incluses.join(", ")}`);
  if (b.routes_exclues?.length) morceaux.push(`sauf : ${b.routes_exclues.join(", ")}`);
  if (b.affiche_du || b.affiche_jusqu_au) morceaux.push("période limitée");
  return morceaux.join(" · ");
}
