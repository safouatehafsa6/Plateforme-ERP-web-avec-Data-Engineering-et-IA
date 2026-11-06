import { validerClient } from "./client.js";

export const STATUTS = { nouveau: "Nouveau", contacte: "Contacté", qualifie: "Qualifié", perdu: "Perdu", converti: "Converti" };
export const SOURCES = {
  site_web: "Site web", recommandation: "Recommandation", salon: "Salon / événement", appel_entrant: "Appel entrant",
  reseaux_sociaux: "Réseaux sociaux", campagne: "Campagne", autre: "Autre",
};
export const TYPES_SUIVI = { appel: "Appel", email: "E-mail", rendez_vous: "Rendez-vous", note: "Note", relance: "Relance" };
export const LIBELLES_EVENEMENTS = {
  ...TYPES_SUIVI,
  creation: "Création", modification: "Modification", statut: "Changement de statut", conversion: "Conversion en client",
  archivage: "Archivage", reactivation: "Réactivation",
};

// Miroir de app/services/prospects.py : l'API reste l'autorité, ceci évite seulement des allers-retours inutiles.
const TRANSITIONS = {
  nouveau: ["contacte", "qualifie", "perdu"],
  contacte: ["qualifie", "perdu"],
  qualifie: ["contacte", "perdu"],
  perdu: ["nouveau", "contacte"],
  converti: [],
};
const STATUTS_CONVERTIBLES = ["nouveau", "contacte", "qualifie"];

export function transitionsPossibles(statut) {
  return TRANSITIONS[statut] ?? [];
}

export function peutFaire(droits, action) {
  return Array.isArray(droits) && droits.includes(action);
}

/** Opérations proposées pour un prospect selon son état ET les permissions du compte. */
export function actionsDisponibles(prospect, droits) {
  if (!prospect) return {};
  const actif = !prospect.archive && prospect.statut !== "converti";
  return {
    modifier: actif && peutFaire(droits, "modifier"),
    changerStatut: actif && peutFaire(droits, "modifier"),
    ajouterSuivi: actif && peutFaire(droits, "creer"),
    convertir: !prospect.archive && STATUTS_CONVERTIBLES.includes(prospect.statut) && peutFaire(droits, "valider"),
    archiver: !prospect.archive && peutFaire(droits, "supprimer"),
    reactiver: Boolean(prospect.archive) && peutFaire(droits, "supprimer"),
  };
}

export function normaliserProspect(values = {}) {
  const texte = (v) => String(v ?? "").trim() || null;
  return {
    nom: String(values.nom ?? "").trim(),
    contact: texte(values.contact),
    email: texte(values.email),
    telephone: texte(values.telephone),
    adresse: texte(values.adresse),
    source: values.source && SOURCES[values.source] ? values.source : "autre",
    besoin: texte(values.besoin),
  };
}

/** Mêmes règles que le client + au moins un moyen de contact (sinon aucun suivi ni contrôle de doublon possible). */
export function validerProspect(values = {}) {
  const prospect = normaliserProspect(values);
  const erreurs = validerClient(prospect);
  if (!prospect.email && !prospect.telephone) {
    erreurs.moyen_contact = "Renseignez au moins une adresse e-mail ou un numéro de téléphone.";
  }
  if (prospect.contact && prospect.contact.length > 150) erreurs.contact = "Le contact ne peut pas dépasser 150 caractères.";
  if (prospect.besoin && prospect.besoin.length > 2000) erreurs.besoin = "Le besoin ne peut pas dépasser 2000 caractères.";
  return erreurs;
}

export function validerChangementStatut({ statut, commentaire } = {}) {
  const erreurs = {};
  if (!statut) erreurs.statut = "Choisissez un statut.";
  if (statut === "perdu" && !String(commentaire ?? "").trim()) erreurs.commentaire = "Indiquez le motif de la perte du prospect.";
  return erreurs;
}

export function validerMotifArchivage(motif) {
  return String(motif ?? "").trim().length < 3 ? "Indiquez un motif (3 caractères minimum)." : "";
}

/** La date d'un suivi ne peut pas être dans le futur ; la relance ne peut pas précéder le suivi. */
export function validerSuivi(values = {}, maintenant = new Date()) {
  const erreurs = {};
  const contenu = String(values.contenu ?? "").trim();
  if (!contenu) erreurs.contenu = "Décrivez l'échange.";
  else if (contenu.length > 4000) erreurs.contenu = "Le texte ne peut pas dépasser 4000 caractères.";
  if (!TYPES_SUIVI[values.type_evenement]) erreurs.type_evenement = "Choisissez un type de suivi.";

  let dateEvenement = maintenant;
  if (values.date_evenement) {
    dateEvenement = new Date(values.date_evenement);
    if (Number.isNaN(dateEvenement.getTime())) erreurs.date_evenement = "Date invalide.";
    else if (dateEvenement.getTime() > maintenant.getTime() + 5 * 60 * 1000) erreurs.date_evenement = "La date ne peut pas être dans le futur.";
  }
  if (values.prochaine_relance && !erreurs.date_evenement) {
    const jourSuivi = [dateEvenement.getFullYear(), dateEvenement.getMonth(), dateEvenement.getDate()];
    const relance = new Date(`${values.prochaine_relance}T00:00:00`);
    if (relance < new Date(jourSuivi[0], jourSuivi[1], jourSuivi[2])) erreurs.prochaine_relance = "La relance ne peut pas précéder la date du suivi.";
  }
  return erreurs;
}

/** « 2026-03-04T10:30 » (datetime-local, heure locale) → ISO UTC attendu par l'API ; vide → null. */
export function versIsoUtc(valeurLocale) {
  if (!valeurLocale) return null;
  const d = new Date(valeurLocale);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

const MOTIFS = { email: "même e-mail", telephone: "même téléphone", nom_identique: "même nom", nom_similaire: "nom proche" };

export function libelleDoublon(d) {
  const nature = d.entite === "client" ? "Client" : "Prospect";
  const motifs = (d.motifs ?? []).map((m) => MOTIFS[m] ?? m).join(", ");
  return `${nature}${d.archive ? " archivé" : ""} « ${d.nom} » — ${motifs}`;
}

/** Analyse la réponse 409 de l'API : peut-on forcer, et que proposer ? */
export function analyserConflitDoublon(erreur) {
  const data = erreur?.data;
  if (erreur?.status !== 409 || !data || !Array.isArray(data.doublons)) return null;
  return {
    message: data.detail,
    confirmable: data.code === "DOUBLON_POSSIBLE" && data.confirmable === true,
    doublons: data.doublons,
    clients: data.doublons.filter((d) => d.entite === "client" && !d.archive),
    archives: data.doublons.filter((d) => d.archive),
  };
}

export function formaterDateHeure(valeur) {
  if (!valeur) return "—";
  const d = new Date(valeur);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });
}

/** Phrase lisible pour une ligne d'historique. */
export function resumeEvenement(e) {
  const d = e.details ?? {};
  if (e.type_evenement === "statut") return `${STATUTS[d.avant] ?? d.avant} → ${STATUTS[d.apres] ?? d.apres}${e.contenu ? ` — ${e.contenu}` : ""}`;
  if (e.type_evenement === "modification") return `Champs modifiés : ${Object.keys(d.changements ?? {}).join(", ") || "—"}`;
  return e.contenu || "";
}
