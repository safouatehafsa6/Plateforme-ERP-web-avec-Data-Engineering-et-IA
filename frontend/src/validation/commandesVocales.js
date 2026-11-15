/**
 * Commandes vocales de l'assistant (arabe, français, anglais) : fonction pure, sans React ni réseau.
 *
 * Principe de sécurité : une phrase n'est traitée comme COMMANDE que si elle est courte et
 * composée d'un verbe d'action + d'un module connu (ex. « ouvre les ventes, s'il te plaît »).
 * Toute vraie question (« quelles sont les ventes du mois ? ») est laissée à l'assistant IA.
 * Les actions sensibles (déconnexion) exigent une confirmation orale explicite.
 */

const ACCENTS = /[\u0300-\u036f]/g;
const TASHKEEL = /[\u064B-\u065F\u0670\u0640]/g;       // voyelles brèves et tatwil arabes

export function normaliserCommande(texte) {
  return String(texte || "")
    .toLowerCase()
    .normalize("NFD").replace(ACCENTS, "")
    .replace(TASHKEEL, "")
    .replace(/[أإآٱ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه")
    .replace(/[’'`´]/g, " ")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const VERBES = new Set([
  "ouvre", "ouvrir", "va", "aller", "allons", "affiche", "afficher", "montre", "montrer", "acces", "accede",
  "open", "go", "show", "display", "navigate", "launch",
  "افتح", "افتحي", "اذهب", "اعرض", "اظهر", "انتقل",
]);
const BRUIT = new Set([
  "le", "la", "les", "l", "un", "une", "des", "du", "de", "d", "au", "aux", "module", "page", "espace", "section",
  "dans", "vers", "sur", "a", "moi", "me", "s", "il", "te", "plait", "vous", "svp", "stp", "merci", "please",
  "the", "to", "my", "me", "a", "an", "of", "section", "tab",
  "من", "فضلك", "الى", "الي", "في", "صفحه", "وحده", "قسم", "ال",
]);

// chemin : route de l'application. Les synonymes sont déjà normalisés (sans accent, a/h arabes unifiés).
export const MODULES = [
  { chemin: "/dashboard", nom: "tableau de bord", mots: ["tableau de bord", "dashboard", "accueil", "home", "لوحه التحكم", "لوحه القياده"] },
  { chemin: "/ventes", nom: "ventes", mots: ["ventes", "vente", "sales", "المبيعات", "مبيعات"] },
  { chemin: "/achats", nom: "achats", mots: ["achats", "achat", "purchases", "purchasing", "المشتريات", "مشتريات"] },
  { chemin: "/clients", nom: "clients", mots: ["clients", "client", "customers", "العملاء", "عملاء"] },
  { chemin: "/prospects", nom: "prospects", mots: ["prospects", "prospect", "leads", "العملاء المحتملين"] },
  { chemin: "/fournisseurs", nom: "fournisseurs", mots: ["fournisseurs", "fournisseur", "suppliers", "الموردين", "موردين"] },
  { chemin: "/stock", nom: "stock", mots: ["stock", "inventaire", "inventory", "المخزون", "مخزون"] },
  { chemin: "/facturation", nom: "facturation", mots: ["facturation", "factures", "invoicing", "invoices", "الفوتره", "الفواتير"] },
  { chemin: "/comptabilite", nom: "comptabilité", mots: ["comptabilite", "accounting", "المحاسبه"] },
  { chemin: "/calculs", nom: "calculs", mots: ["calculs", "calcul", "calculations", "calculator", "الحسابات", "حسابات"] },
  { chemin: "/room-live", nom: "Room Live", mots: ["room live", "roomlive", "visioconference", "reunion en ligne", "غرفه مباشره", "الغرفه المباشره"] },
  { chemin: "/documents-ia", nom: "documents intelligents", mots: ["documents ia", "documents intelligents", "idp", "ocr", "smart documents", "intelligent documents", "المستندات الذكيه", "ocr الذكي"] },
  { chemin: "/support", nom: "support", mots: ["support", "aide", "help", "الدعم", "المساعده"] },
  { chemin: "/parametres", nom: "paramètres", mots: ["parametres", "parametre", "settings", "الاعدادات", "اعدادات"] },
];

const DOCUMENTS_RAG = ["documents", "les documents", "documents rag", "base documentaire", "المستندات", "مستندات"];
const NOTIFICATIONS = ["notifications", "notification", "mes notifications", "les notifications", "الاشعارات", "اشعاراتي"];
const VERBES_LECTURE = new Set(["lis", "lire", "lit", "read", "اقرا", "اقرأ"]);
const OUI = new Set(["oui", "ouais", "confirme", "confirmer", "d accord", "yes", "yeah", "confirm", "ok", "نعم", "اجل", "تاكيد", "اكد"]);
const NON = new Set(["non", "annule", "annuler", "stop", "no", "cancel", "لا", "الغاء", "الغي"]);

const DECONNEXION = ["deconnexion", "deconnecte moi", "me deconnecter", "deconnecter", "se deconnecter", "logout", "log out", "sign out", "تسجيل الخروج", "سجل خروجي"];
const CONVERSATION_ON = ["mode conversation", "active la conversation", "activer le mode conversation", "conversation mode", "start conversation", "وضع المحادثه", "فعل المحادثه"];
const CONVERSATION_OFF = ["arrete la conversation", "arreter la conversation", "fin de la conversation", "stop conversation", "end conversation", "اوقف المحادثه", "انهاء المحادثه"];

// Les synonymes sont comparés « épurés » des mots vides, comme la phrase prononcée
// (« tableau de bord » devient « tableau bord » des deux côtés).
const epurer = (texte) => texte.split(" ").filter((m) => m && !BRUIT.has(m)).join(" ");
const DOCUMENTS_RAG_E = DOCUMENTS_RAG.map(epurer);
const NOTIFICATIONS_E = NOTIFICATIONS.map(epurer);

function contientMot(texte, mot) {
  return ` ${texte} `.includes(` ${mot} `);
}

/**
 * @returns {null | {type: string, ...}}
 *   navigation {chemin, nom} · documents · notifications · deconnexion {sensible:true}
 *   confirmer · annuler · conversation {actif}
 */
export function interpreter(texte, { confirmationEnAttente = false } = {}) {
  const t = normaliserCommande(texte);
  if (!t) return null;
  const mots = t.split(" ");

  if (confirmationEnAttente && mots.length <= 3) {
    if (OUI.has(t) || mots.some((m) => OUI.has(m))) return { type: "confirmer" };
    if (NON.has(t) || mots.some((m) => NON.has(m))) return { type: "annuler" };
  }

  if (CONVERSATION_OFF.some((c) => t === c || contientMot(t, c))) return { type: "conversation", actif: false };
  if (CONVERSATION_ON.some((c) => t === c || contientMot(t, c))) return { type: "conversation", actif: true };
  const utiles = mots.filter((m) => !BRUIT.has(m));
  if (utiles.length > 4) return null;                // une vraie question n'est jamais une commande

  if (DECONNEXION.some((c) => t === c || contientMot(t, c))) return { type: "deconnexion", sensible: true };

  const aVerbe = utiles.some((m) => VERBES.has(m));
  const aLecture = utiles.some((m) => VERBES_LECTURE.has(m));
  const sansVerbe = utiles.filter((m) => !VERBES.has(m) && !VERBES_LECTURE.has(m)).join(" ");

  if ((aVerbe || aLecture) && NOTIFICATIONS_E.includes(sansVerbe)) return { type: "notifications" };
  if (aVerbe && DOCUMENTS_RAG_E.includes(sansVerbe)) return { type: "documents" };
  if (NOTIFICATIONS_E.includes(utiles.join(" ")) && mots.length > 1) return { type: "notifications" };

  if (aVerbe) {
    // Le module le plus spécifique d'abord (« documents ia » avant « documents »).
    const candidats = MODULES.flatMap((m) => m.mots.map((mot) => ({ m, mot })))
      .sort((a, b) => b.mot.length - a.mot.length);
    for (const { m, mot } of candidats) {
      if (sansVerbe === epurer(mot)) return { type: "navigation", chemin: m.chemin, nom: m.nom };
    }
  }
  return null;
}
